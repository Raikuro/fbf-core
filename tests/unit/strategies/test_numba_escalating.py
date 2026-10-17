"""Escalating withdrawal (B3): kernel, executor, and routing tests.

Validates the ``EscalatingWithdrawalPolicy`` Numba kernel and its integration
into ``NumbaSimulationExecutor``.

The withdrawal schedule is value-independent and frozen at:

    C_year = initial_value * withdrawal_rate * (1 + escalation_rate) ** (m // 12)

with one lump sum per year (``ANNUAL``) or a monthly twelfth (``MONTHLY``).
Correctness is established from two independent angles:

1. Closed-form hand calculation on a flat market.
2. An independent Decimal recurrence, plus a differential against the legacy
   pipeline (fee = 0, where the two methodologies coincide).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import ConstantAllocationPolicy, EscalatingWithdrawalPolicy
from fbf.core.domain.policies.frequency import WithdrawalFrequency
from fbf.core.execution import _auto_select_backend
from fbf.core.execution.pipeline.default_pipeline import create_default_pipeline
from fbf.core.execution.pipeline.runner import SimulationRunner
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.profiling import NoOpProfiler
from fbf.core.execution.strategies.numba_executor import NumbaSimulationExecutor
from fbf.core.execution.strategies.numba_kernel import (
    _simulate_trajectory_escalating,
    simulate_batch_escalating,
    simulate_single_escalating,
)
from fbf.core.study.builder import build_initial_portfolio
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan

_EQ = AssetClass(id="equity", name="", description="")
_BD = AssetClass(id="bond", name="", description="")

_WEALTH = Decimal("1000000")
_TOLERANCE = Decimal("0.01")

ANNUAL = WithdrawalFrequency.ANNUAL
MONTHLY = WithdrawalFrequency.MONTHLY


# ---------------------------------------------------------------------------
# Datasets and helpers
# ---------------------------------------------------------------------------


def _flat_dataset(n_months: int) -> Dataset:
    """Flat market: every index level is 100 (all growth factors equal 1)."""
    snaps = []
    d = date(1900, 1, 1)
    for _ in range(n_months):
        snaps.append(
            MarketSnapshot(
                date=d,
                index_levels={_EQ: Decimal("100"), _BD: Decimal("100")},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            )
        )
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return Dataset(snapshots=tuple(snaps), frequency="monthly")


def _growing_dataset(n_months: int) -> Dataset:
    """Growing market: equity +0.6%/mo, bond +0.2%/mo."""
    pe = pb = Decimal("100")
    snaps = []
    d = date(1900, 1, 1)
    for _ in range(n_months):
        snaps.append(
            MarketSnapshot(
                date=d,
                index_levels={_EQ: pe, _BD: pb},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            )
        )
        pe *= Decimal("1.006")
        pb *= Decimal("1.002")
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return Dataset(snapshots=tuple(snaps), frequency="monthly")


def _make_context(
    dataset: Dataset,
    horizon: int,
    w: str = "0.6",
    rate: str = "0.035",
    esc: str = "0.02",
    freq: WithdrawalFrequency = ANNUAL,
    wealth: Decimal = _WEALTH,
    fvt: Decimal | None = None,
) -> SimulationContext:
    start = dataset[0].date
    portfolio = build_initial_portfolio(Money(_WEALTH, Currency.EUR), dataset)
    return SimulationContext(
        experiment_name="test",
        cohort=f"c-{horizon}",
        start_date=start,
        horizon_months=horizon,
        initial_wealth=Money(wealth, Currency.EUR),
        initial_portfolio=portfolio,
        dataset=dataset.slice(start, horizon),
        allocation_policy=ConstantAllocationPolicy(Decimal(w)),
        withdrawal_policy=EscalatingWithdrawalPolicy(
            withdrawal_rate=Decimal(rate),
            escalation_rate=Decimal(esc),
            frequency=freq,
        ),
        final_value_target=fvt,
    )


def _run_numba(contexts: list[SimulationContext]) -> list[tuple[bool, int | None, Decimal, int]]:
    executor = NumbaSimulationExecutor()
    definition = EngineExperimentDefinition(
        name="test", description="test", simulation_contexts=tuple(contexts)
    )
    run = executor.execute(definition)
    return [
        (
            r.statistics.success,
            r.statistics.failure_month,
            r.statistics.final_wealth.amount,
            r.statistics.months_simulated,
        )
        for r in run.simulation_results
    ]


def _recurrence(
    growth_factors: list[Decimal],
    initial_value: Decimal,
    withdrawal_rate: Decimal,
    escalation_rate: Decimal,
    horizon: int,
    annual: bool,
) -> tuple[Decimal, bool, int | None]:
    """Independent Decimal implementation of the escalating recurrence."""
    value = initial_value
    base = initial_value * withdrawal_rate
    one = Decimal("1")
    for m in range(horizon):
        escalated = base * (one + escalation_rate) ** (m // 12)
        if annual and m % 12 != 0:
            withdrawal = Decimal("0")
        elif annual:
            withdrawal = escalated
        else:
            withdrawal = escalated / Decimal("12")
        if withdrawal > value:
            return Decimal("0"), False, m
        value -= withdrawal
        if m < horizon - 1:
            value *= growth_factors[m]
    return value, True, None


def _growth_factors(dataset: Dataset, horizon: int, w: Decimal) -> list[Decimal]:
    snaps = dataset.snapshots
    gfs = []
    for m in range(horizon):
        eq = snaps[m + 1].index_levels[_EQ] / snaps[m].index_levels[_EQ]
        bd = snaps[m + 1].index_levels[_BD] / snaps[m].index_levels[_BD]
        gfs.append(w * eq + (Decimal("1") - w) * bd)
    return gfs


# ---------------------------------------------------------------------------
# Kernel tests
# ---------------------------------------------------------------------------


class TestEscalatingKernelHandCalculated:
    def test_flat_annual_closed_form(self) -> None:
        gf = np.ones(36, dtype=np.float64)
        final, ok, fm, _ = _simulate_trajectory_escalating(
            gf, 1_000_000.0, 0.035, 0.02, 36, True
        )
        # Withdrawals: 35000 + 35700 + 36414 = 107114; final = 1e6 - 107114.
        assert ok is True
        assert fm == -1
        assert abs(final - 892886.0) < 1e-6

    def test_flat_monthly_closed_form(self) -> None:
        gf = np.ones(36, dtype=np.float64)
        final, ok, fm, _ = _simulate_trajectory_escalating(
            gf, 1_000_000.0, 0.035, 0.02, 36, False
        )
        # Monthly twelfths of the same annual totals -> identical final value.
        assert ok is True
        assert fm == -1
        assert abs(final - 892886.0) < 1e-3

    def test_zero_escalation_matches_flat_annual(self) -> None:
        gf = np.ones(36, dtype=np.float64)
        final, _, _, _ = _simulate_trajectory_escalating(
            gf, 1_000_000.0, 0.04, 0.0, 36, True
        )
        assert abs(final - (1_000_000.0 - 3 * 40_000.0)) < 1e-6

    def test_depletion_boundary_hand_calculated(self) -> None:
        gf = np.ones(36, dtype=np.float64)
        final, ok, fm, _ = _simulate_trajectory_escalating(
            gf, 1_000_000.0, 0.5, 0.0, 36, True
        )
        # m=0: 500000 -> 500000; m=12: exactly 500000 -> 0 (not depleted);
        # m=24: 500000 > 0 -> failure.
        assert ok is False
        assert fm == 24
        assert final == 0.0

    @pytest.mark.parametrize("annual", [True, False])
    def test_kernel_matches_independent_recurrence(self, annual: bool) -> None:
        horizon = 83
        dataset = _growing_dataset(horizon + 1)
        gf = np.array([float(g) for g in _growth_factors(dataset, horizon, Decimal("0.6"))])
        final, ok, fm, _ = _simulate_trajectory_escalating(
            gf, 1_000_000.0, 0.035, 0.02, horizon, annual
        )
        exp_value, exp_ok, exp_fm = _recurrence(
            _growth_factors(dataset, horizon, Decimal("0.6")),
            _WEALTH,
            Decimal("0.035"),
            Decimal("0.02"),
            horizon,
            annual,
        )
        assert ok is exp_ok
        assert (fm if fm >= 0 else None) == exp_fm
        assert abs(Decimal(str(final)) - exp_value) < _TOLERANCE

    def test_annual_and_monthly_timing_differ_on_non_flat_market(self) -> None:
        horizon = 24
        dataset = _growing_dataset(horizon + 1)
        gf = np.array([float(g) for g in _growth_factors(dataset, horizon, Decimal("0.6"))])
        annual_final, _, _, _ = _simulate_trajectory_escalating(
            gf, 1_000_000.0, 0.035, 0.02, horizon, True
        )
        monthly_final, _, _, _ = _simulate_trajectory_escalating(
            gf, 1_000_000.0, 0.035, 0.02, horizon, False
        )
        assert annual_final != monthly_final


class TestEscalatingScheduleContract:
    """Explicit month-by-month schedule and boundary checks.

    The kernel returns only the terminal value, so these cases use controlled
    growth factors and *literal* monthly withdrawals to make the withdrawal
    timing, the annual escalation boundary, and the withdrawal-before-growth
    ordering directly observable in the terminal value.
    """

    def test_annual_schedule_month_by_month(self) -> None:
        horizon = 14
        gf_list = [Decimal("1.10")] * 13 + [Decimal("1")]
        # One literal lump per year at m % 12 == 0, including m = 0.
        withdrawals = [
            Decimal("120000"),  # m=0  year 0
            *([Decimal("0")] * 11),  # m=1..11
            Decimal("132000"),  # m=12 year 1 (120000 * 1.10)
            Decimal("0"),  # m=13
        ]
        assert len(withdrawals) == horizon

        value = _WEALTH
        for m, c in enumerate(withdrawals):
            value -= c
            if m < horizon - 1:
                value *= gf_list[m]

        gf = np.array([float(g) for g in gf_list])
        final, ok, fm, _ = _simulate_trajectory_escalating(
            gf, float(_WEALTH), 0.12, 0.10, horizon, True
        )
        assert ok is True
        assert fm == -1
        assert abs(Decimal(str(final)) - value) < _TOLERANCE
        # Explicit terminal value for the enumerated trajectory above.
        assert abs(Decimal(str(final)) - Decimal("2892798.668665928")) < Decimal("0.01")

    def test_monthly_schedule_month_by_month(self) -> None:
        horizon = 14
        gf_list = [Decimal("1.10")] * 13 + [Decimal("1")]
        # One twelfth each month; escalation at the m = 12 annual boundary.
        withdrawals = [Decimal("10000")] * 12 + [Decimal("11000")] * 2
        assert len(withdrawals) == horizon

        value = _WEALTH
        for m, c in enumerate(withdrawals):
            value -= c
            if m < horizon - 1:
                value *= gf_list[m]

        gf = np.array([float(g) for g in gf_list])
        final, ok, fm, _ = _simulate_trajectory_escalating(
            gf, float(_WEALTH), 0.12, 0.10, horizon, False
        )
        assert ok is True
        assert fm == -1
        assert abs(Decimal(str(final)) - value) < _TOLERANCE
        # The two frequencies must differ once growth makes timing matter.
        annual_final, _, _, _ = _simulate_trajectory_escalating(
            gf, float(_WEALTH), 0.12, 0.10, horizon, True
        )
        assert final != annual_final

    def test_exact_boundary_withdrawal_is_not_depleted(self) -> None:
        gf = np.ones(1, dtype=np.float64)
        final, ok, fm, _ = _simulate_trajectory_escalating(
            gf, 1_000_000.0, 1.0, 0.0, 1, True
        )
        # withdrawal == value exactly: not depleted, terminal value 0.
        assert ok is True
        assert fm == -1
        assert final == 0.0

    def test_exceeding_withdrawal_depletes_at_its_month(self) -> None:
        gf = np.ones(13, dtype=np.float64)
        final, ok, fm, _ = _simulate_trajectory_escalating(
            gf, 1_000_000.0, 1.0, 0.0, 13, True
        )
        # m=0 drains to exactly 0 without failing; the next *annual boundary*
        # (m=12) schedules another 1,000,000 against 0 wealth.
        assert ok is False
        assert fm == 12
        assert final == 0.0


class TestEscalatingKernelWrappers:
    def test_flat_annual_closed_form(self) -> None:
        gf = np.ones(36, dtype=np.float64)
        ok, fm, wealth, months = simulate_single_escalating(
            gf, Money(_WEALTH, Currency.EUR), Decimal("0.035"), Decimal("0.02"), 36, True
        )
        assert ok is True
        assert fm is None
        assert months == 36
        assert abs(wealth.amount - Decimal("892886.0")) < _TOLERANCE

    def test_batch_matches_single(self) -> None:
        gf = np.ones(36, dtype=np.float64)
        results = simulate_batch_escalating(
            gf,
            [Money(_WEALTH, Currency.EUR)] * 12,
            [Decimal("0.035")] * 12,
            [Decimal("0.02")] * 12,
            [36] * 12,
            True,
            parallel=False,
        )
        assert len(results) == 12
        for ok, fm, wealth, months in results:
            assert ok is True
            assert fm is None
            assert months == 36
            assert abs(wealth.amount - Decimal("892886.0")) < _TOLERANCE

    def test_batch_parallel_path_matches_sequential(self) -> None:
        gf = np.ones(36, dtype=np.float64)
        args = (
            [Money(_WEALTH, Currency.EUR)] * 12,
            [Decimal("0.035")] * 12,
            [Decimal("0.02")] * 12,
            [36] * 12,
            True,
        )
        sequential = simulate_batch_escalating(gf, *args, parallel=False)
        parallel = simulate_batch_escalating(gf, *args, parallel=True)
        assert [r[2].amount for r in sequential] == [r[2].amount for r in parallel]


# ---------------------------------------------------------------------------
# Executor tests
# ---------------------------------------------------------------------------


class TestEscalatingExecutorDifferential:
    @pytest.mark.parametrize("freq", [ANNUAL, MONTHLY])
    def test_matches_legacy_pipeline_without_fees(self, freq: WithdrawalFrequency) -> None:
        """With fee=0 the Numba path and the legacy pipeline coincide."""
        horizon = 60
        context = _make_context(_growing_dataset(horizon + 1), horizon, freq=freq)
        numba = _run_numba([context])[0]
        legacy = SimulationRunner(pipeline=create_default_pipeline()).run(context)

        assert numba[0] == legacy.statistics.success
        assert abs(numba[2] - legacy.statistics.final_wealth.amount) < Decimal("0.01")

    @pytest.mark.parametrize("freq", [ANNUAL, MONTHLY])
    def test_matches_independent_recurrence(self, freq: WithdrawalFrequency) -> None:
        horizon = 72
        dataset = _growing_dataset(horizon + 1)
        context = _make_context(dataset, horizon, w="0.75", rate="0.04", esc="0.03", freq=freq)
        ok, fm, wealth, months = _run_numba([context])[0]
        exp_value, exp_ok, exp_fm = _recurrence(
            _growth_factors(dataset, horizon, Decimal("0.75")),
            _WEALTH,
            Decimal("0.04"),
            Decimal("0.03"),
            horizon,
            freq is ANNUAL,
        )
        assert ok is exp_ok
        assert fm == exp_fm
        assert months == (horizon if ok else fm)
        assert abs(wealth - exp_value) < _TOLERANCE

    def test_grouping_places_shared_trajectory_in_one_cluster(self) -> None:
        base = _growing_dataset(121)
        long_ctx = _make_context(base, 120)
        short_ctx = _make_context(base, 60)

        executor = NumbaSimulationExecutor()
        definition = EngineExperimentDefinition(
            name="test",
            description="test",
            simulation_contexts=(long_ctx, short_ctx),
        )
        run = executor.execute(definition)

        report = executor.report
        assert report is not None
        assert report.groups == 1

        # Both horizons must still be correct against the independent recurrence.
        for ctx, result in zip((long_ctx, short_ctx), run.simulation_results, strict=True):
            exp_value, exp_ok, _ = _recurrence(
                _growth_factors(base, ctx.horizon_months, Decimal("0.6")),
                _WEALTH,
                Decimal("0.035"),
                Decimal("0.02"),
                ctx.horizon_months,
                True,
            )
            assert result.statistics.success is exp_ok
            assert abs(result.statistics.final_wealth.amount - exp_value) < _TOLERANCE

    def test_final_value_target_applied_per_context(self) -> None:
        base = _flat_dataset(37)
        surviving = _make_context(base, 36)
        demanding = _make_context(base, 36, fvt=Decimal("5"))
        results = _run_numba([surviving, demanding])
        assert results[0][0] is True
        assert results[1][0] is False

    def test_fv_threshold_independent_of_initial_wealth(self) -> None:
        """Contexts sharing a path but differing in ``initial_wealth`` must not
        share an FV verdict (the threshold is ``initial_wealth * target``)."""
        base = _flat_dataset(37)
        # Flat 36-month final value is 892886; target 0.9 gives thresholds
        # 900000 (fail) and 891000 (pass) for the two wealth bases.
        failing = _make_context(base, 36, wealth=Decimal("1000000"), fvt=Decimal("0.9"))
        passing = _make_context(base, 36, wealth=Decimal("990000"), fvt=Decimal("0.9"))
        results = _run_numba([failing, passing])
        assert results[0][0] is False
        assert results[0][1] == 36
        assert results[1][0] is True

    def test_glidepath_allocation_is_not_escalating_eligible(self) -> None:
        from fbf.core.domain.policies import GlidepathAllocationPolicy

        context = _make_context(_flat_dataset(37), 36)
        glide_ctx = SimulationContext(
            experiment_name=context.experiment_name,
            cohort=context.cohort,
            start_date=context.start_date,
            horizon_months=context.horizon_months,
            initial_wealth=context.initial_wealth,
            initial_portfolio=context.initial_portfolio,
            dataset=context.dataset,
            allocation_policy=GlidepathAllocationPolicy(
                start_equity=Decimal("0.7"),
                end_equity=Decimal("0.9"),
                slope=Decimal("0.02"),
                mode="passive",
            ),
            withdrawal_policy=context.withdrawal_policy,
        )
        # Ineligible for the escalating kernel; falls back to the reference
        # path and still returns a well-formed result.
        results = _run_numba([glide_ctx])
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Routing tests
# ---------------------------------------------------------------------------


class TestEscalatingRouting:
    def test_auto_select_routes_escalating_to_numba(self) -> None:
        from fbf.core.execution.strategies.numba_executor import NumbaSimulationExecutor
        from fbf.core.study.builder import BuiltStudy

        dataset = _growing_dataset(121)
        start = dataset[0].date
        cohort = CohortSpecification(start_date=start)
        policy = EscalatingWithdrawalPolicy(
            withdrawal_rate=Decimal("0.035"),
            escalation_rate=Decimal("0.02"),
            frequency=ANNUAL,
        )
        portfolio = build_initial_portfolio(Money(_WEALTH, Currency.EUR), dataset)
        experiment = ExperimentDefinition(
            name="test",
            description="test",
            dataset=dataset,
            horizon_months=120,
            initial_wealth=Money(_WEALTH, Currency.EUR),
            cohorts=(cohort,),
            allocation_policies=(ConstantAllocationPolicy(Decimal("0.6")),),
            withdrawal_policies=(policy,),
        )
        unit = PlannedSimulationUnit(
            cohort=cohort,
            parameter_config=ParameterConfiguration(
                {"equity_allocation": 0.6, "withdrawal_rate": 0.035, "horizon_years": 10}
            ),
            allocation_policy=ConstantAllocationPolicy(Decimal("0.6")),
            withdrawal_policy=policy,
            initial_portfolio=portfolio,
            dataset=dataset.slice(start, 120),
            horizon_months=120,
        )
        plan = ResearchPlan(experiment_definition=experiment, units=(unit,))
        built = BuiltStudy(
            plan=plan,
            experiment_definition=experiment,
            cohorts=(cohort,),
            param_configs=(),
        )

        executor = _auto_select_backend(built, NoOpProfiler())
        assert isinstance(executor, NumbaSimulationExecutor)
