"""Buy-and-hold (B4): unit-tracking kernel, executor, and routing tests.

Validates the ``BuyAndHoldAllocationPolicy`` Numba kernel and its integration
into ``NumbaSimulationExecutor``.

Buy-and-hold establishes the target equity/bond split once and never
rebalances.  Withdrawals are funded by selling both holdings pro rata, which
preserves the weights immediately before the withdrawal; between withdrawals
the weights drift with the asset-specific returns::

    V_0 = initial_value,  w_0 = equity_weight
    for m in 0 .. horizon-1:
        if C > V_m: failure at month m
        V_m <- V_m - C                        (pro rata: w unchanged)
        if m < horizon - 1:
            G = w_m * ge[m] + (1 - w_m) * gb[m]
            w_{m+1} = w_m * ge[m] / G
            V_{m+1} = V_m * G

Correctness is established from two independent angles:

1. Closed-form hand calculations on controlled markets.
2. An independent Decimal unit-tracking recurrence, plus a differential against
   the legacy buy-and-hold pipeline (fee = 0, where the two methodologies
   coincide).
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
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies import (
    BuyAndHoldAllocationPolicy,
    ConstantAllocationPolicy,
    FixedRealWithdrawalPolicy,
)
from fbf.core.execution import _auto_select_backend
from fbf.core.execution.pipeline.default_pipeline import create_buy_and_hold_pipeline
from fbf.core.execution.pipeline.runner import SimulationRunner
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.profiling import NoOpProfiler
from fbf.core.execution.strategies.numba_executor import (
    NumbaSimulationExecutor,
    _is_buy_and_hold_eligible,
)
from fbf.core.execution.strategies.numba_kernel import (
    _simulate_trajectory_buy_and_hold,
    simulate_batch_buy_and_hold,
    simulate_single_buy_and_hold,
)
from fbf.core.study.builder import BuiltStudy, build_initial_portfolio
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan

_EQ = AssetClass(id="equity", name="", description="")
_BD = AssetClass(id="bond", name="", description="")

_WEALTH = Decimal("1000000")
_TOLERANCE = Decimal("0.01")


# ---------------------------------------------------------------------------
# Datasets and helpers
# ---------------------------------------------------------------------------


def _bh_dataset(
    n_months: int,
    eq_growth: str = "1.006",
    bd_growth: str = "1.002",
) -> Dataset:
    """Market with a constant monthly equity/bond growth ratio."""
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
        pe *= Decimal(eq_growth)
        pb *= Decimal(bd_growth)
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return Dataset(snapshots=tuple(snaps), frequency="monthly")


def _flat_dataset(n_months: int) -> Dataset:
    """Flat market: every index level is 100 (all growth factors equal 1)."""
    return _bh_dataset(n_months, eq_growth="1", bd_growth="1")


def _clone_dataset(dataset: Dataset) -> Dataset:
    """Rebuild a dataset with fresh (value-identical) snapshot objects."""
    snapshots = tuple(
        MarketSnapshot(
            date=snap.date,
            index_levels=dict(snap.index_levels),
            inflation=snap.inflation,
            inflation_cumulative=snap.inflation_cumulative,
            is_ath=snap.is_ath,
            is_underwater=snap.is_underwater,
            running_ath=snap.running_ath,
        )
        for snap in dataset.snapshots
    )
    return Dataset(snapshots=snapshots, frequency=dataset.frequency)


def _make_context(
    dataset: Dataset,
    horizon: int,
    w: str = "0.6",
    rate: str = "0.04",
    wealth: Decimal = _WEALTH,
    fvt: Decimal | None = None,
    fee: Decimal | None = None,
    portfolio: Portfolio | None = None,
) -> SimulationContext:
    start = dataset[0].date
    if portfolio is None:
        portfolio = build_initial_portfolio(Money(_WEALTH, Currency.EUR), dataset)
    return SimulationContext(
        experiment_name="test",
        cohort=f"c-{horizon}",
        start_date=start,
        horizon_months=horizon,
        initial_wealth=Money(wealth, Currency.EUR),
        initial_portfolio=portfolio,
        dataset=dataset.slice(start, horizon),
        allocation_policy=BuyAndHoldAllocationPolicy(Decimal(w)),
        withdrawal_policy=FixedRealWithdrawalPolicy(withdrawal_rate=Decimal(rate)),
        final_value_target=fvt,
        expense_ratio=fee,
    )


def _run_numba(
    contexts: list[SimulationContext],
) -> list[tuple[bool, int | None, Decimal, int]]:
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


def _bh_returns(
    dataset: Dataset, horizon: int
) -> tuple[list[Decimal], list[Decimal]]:
    """Per-asset monthly gross returns for months 0..horizon-2."""
    snaps = dataset.snapshots
    eq = [
        snaps[m + 1].index_levels[_EQ] / snaps[m].index_levels[_EQ]
        for m in range(horizon - 1)
    ]
    bd = [
        snaps[m + 1].index_levels[_BD] / snaps[m].index_levels[_BD]
        for m in range(horizon - 1)
    ]
    return eq, bd


def _bh_recurrence(
    eq_returns: list[Decimal],
    bd_returns: list[Decimal],
    initial_value: Decimal,
    w0: Decimal,
    withdrawal_rate: Decimal,
    horizon: int,
) -> tuple[Decimal, bool, int | None, Decimal]:
    """Independent Decimal unit-tracking buy-and-hold recurrence.

    Returns ``(final_value, success, failure_month, final_equity_weight)``.
    """
    value = initial_value
    weight = w0
    one = Decimal("1")
    withdrawal = initial_value * withdrawal_rate / Decimal("12")
    for m in range(horizon):
        if withdrawal > value:
            return Decimal("0"), False, m, weight
        value -= withdrawal
        if m < horizon - 1:
            ge = eq_returns[m]
            gb = bd_returns[m]
            blended = weight * ge + (one - weight) * gb
            if blended != 0:
                weight = weight * ge / blended
            value *= blended
    return value, True, None, weight


# ---------------------------------------------------------------------------
# Kernel tests
# ---------------------------------------------------------------------------


class TestBuyAndHoldKernelHandCalculated:
    def test_flat_market_constant_split(self) -> None:
        # Flat market: weight stays at 0.5 and each month withdraws C = 40000/12.
        eq = np.ones(60, dtype=np.float64)
        bd = np.ones(60, dtype=np.float64)
        final, ok, fm, _ = _simulate_trajectory_buy_and_hold(
            eq, bd, 1_000_000.0, 0.5, 1_000_000.0 * 0.04 / 12.0, 60
        )
        assert ok is True
        assert fm == -1
        assert abs(final - (1_000_000.0 - 60.0 * 1_000_000.0 * 0.04 / 12.0)) < 1e-6

    def test_zero_withdrawal_equals_weighted_buy_and_hold(self) -> None:
        # With no withdrawals the terminal value decomposes exactly into the
        # two buy-and-hold legs: V = w*V0*prod(ge) + (1-w)*V0*prod(gb).
        eq = np.array([1.01] * 23, dtype=np.float64)
        bd = np.array([1.001] * 23, dtype=np.float64)
        final, ok, _, _ = _simulate_trajectory_buy_and_hold(
            eq, bd, 1_000_000.0, 0.7, 0.0, 24
        )
        expected = 0.7 * 1_000_000.0 * 1.01**23 + 0.3 * 1_000_000.0 * 1.001**23
        assert ok is True
        assert abs(final - expected) < 1e-6

    @pytest.mark.parametrize("w", ["0.0", "1.0"])
    def test_full_allocation_matches_single_asset(self, w: str) -> None:
        horizon = 24
        eq = np.array([1.01] * (horizon - 1), dtype=np.float64)
        bd = np.array([1.001] * (horizon - 1), dtype=np.float64)
        c = 1_000_000.0 * 0.04 / 12.0
        final, ok, _, _ = _simulate_trajectory_buy_and_hold(
            eq, bd, 1_000_000.0, float(w), c, horizon
        )
        # Reproduce with an explicit single-asset loop.
        growth = 1.01 if w == "1.0" else 1.001
        value = 1_000_000.0
        for m in range(horizon):
            value -= c
            if m < horizon - 1:
                value *= growth
        assert ok is True
        assert abs(final - value) < 1e-9

    def test_weights_drift_versus_rebalanced(self) -> None:
        # On a strongly equity-driven market, buy-and-hold ends higher than a
        # constant-weight (rebalanced) model because winning weight is allowed
        # to run.
        horizon = 24
        eq = np.array([1.02] * (horizon - 1), dtype=np.float64)
        bd = np.array([1.0] * (horizon - 1), dtype=np.float64)
        final_bh, _, _, _ = _simulate_trajectory_buy_and_hold(
            eq, bd, 1_000_000.0, 0.5, 0.0, horizon
        )
        # Constant-weight 50/50 rebalanced: blended = 0.5*1.02 + 0.5*1.0.
        value = 1_000_000.0
        for _ in range(horizon - 1):
            value *= 0.5 * 1.02 + 0.5 * 1.0
        assert final_bh > value

    def test_exact_boundary_withdrawal_is_not_depleted(self) -> None:
        eq = np.ones(100, dtype=np.float64)
        bd = np.ones(100, dtype=np.float64)
        # C = 10000/mo; 100 withdrawals exactly exhaust the portfolio.
        final, ok, fm, _ = _simulate_trajectory_buy_and_hold(
            eq, bd, 1_000_000.0, 0.5, 10_000.0, 100
        )
        assert ok is True
        assert fm == -1
        assert final == 0.0

    def test_exceeding_withdrawal_depletes_at_its_month(self) -> None:
        eq = np.ones(101, dtype=np.float64)
        bd = np.ones(101, dtype=np.float64)
        final, ok, fm, _ = _simulate_trajectory_buy_and_hold(
            eq, bd, 1_000_000.0, 0.5, 10_000.0, 101
        )
        # Months 0..99 drain to exactly 0; month 100 schedules another 10000
        # against 0 wealth.
        assert ok is False
        assert fm == 100
        assert final == 0.0

    @pytest.mark.parametrize("w", ["0.0", "0.25", "0.5", "0.75", "1.0"])
    @pytest.mark.parametrize("horizon", [1, 12, 60, 83])
    def test_kernel_matches_independent_recurrence(self, w: str, horizon: int) -> None:
        dataset = _bh_dataset(horizon + 1)
        eq_dec, bd_dec = _bh_returns(dataset, horizon)
        eq = np.array([float(g) for g in eq_dec], dtype=np.float64)
        bd = np.array([float(g) for g in bd_dec], dtype=np.float64)
        c = float(_WEALTH * Decimal("0.04") / 12)
        final, ok, fm, _ = _simulate_trajectory_buy_and_hold(
            eq, bd, float(_WEALTH), float(Decimal(w)), c, horizon
        )
        exp_value, exp_ok, exp_fm, _ = _bh_recurrence(
            eq_dec, bd_dec, _WEALTH, Decimal(w), Decimal("0.04"), horizon
        )
        assert ok is exp_ok
        assert (fm if fm >= 0 else None) == exp_fm
        assert abs(Decimal(str(final)) - exp_value) < _TOLERANCE

    def test_depletion_matches_independent_recurrence(self) -> None:
        horizon = 80
        dataset = _flat_dataset(horizon + 1)
        eq_dec, bd_dec = _bh_returns(dataset, horizon)
        eq = np.array([float(g) for g in eq_dec], dtype=np.float64)
        bd = np.array([float(g) for g in bd_dec], dtype=np.float64)
        # rate 0.7 -> C = 58333.33/mo; depletes at month 17, clear of the
        # razor-thin float/Decimal rounding boundary that sits at a withdrawal
        # multiple (e.g. rate 0.5, where 24 * C == 1,000,000 in exact Decimal).
        c = float(_WEALTH * Decimal("0.7") / 12)
        final, ok, fm, _ = _simulate_trajectory_buy_and_hold(
            eq, bd, float(_WEALTH), 0.5, c, horizon
        )
        exp_value, exp_ok, exp_fm, _ = _bh_recurrence(
            eq_dec, bd_dec, _WEALTH, Decimal("0.5"), Decimal("0.7"), horizon
        )
        assert ok is exp_ok is False
        assert fm == exp_fm
        assert final == 0.0
        assert exp_value == 0


class TestBuyAndHoldKernelWrappers:
    def test_single_matches_recurrence(self) -> None:
        dataset = _bh_dataset(61)
        horizon = 60
        eq_dec, bd_dec = _bh_returns(dataset, horizon)
        eq = np.array([float(g) for g in eq_dec], dtype=np.float64)
        bd = np.array([float(g) for g in bd_dec], dtype=np.float64)
        ok, fm, wealth, months = simulate_single_buy_and_hold(
            eq, bd, Money(_WEALTH, Currency.EUR), Decimal("0.75"), Decimal("0.04"), horizon
        )
        exp_value, exp_ok, exp_fm, _ = _bh_recurrence(
            eq_dec, bd_dec, _WEALTH, Decimal("0.75"), Decimal("0.04"), horizon
        )
        assert ok is exp_ok
        assert fm is exp_fm
        assert months == horizon
        assert abs(wealth.amount - exp_value) < _TOLERANCE

    def test_batch_matches_single(self) -> None:
        horizon = 60
        dataset = _bh_dataset(horizon + 1)
        eq_dec, bd_dec = _bh_returns(dataset, horizon)
        eq = np.array([float(g) for g in eq_dec], dtype=np.float64)
        bd = np.array([float(g) for g in bd_dec], dtype=np.float64)

        single = simulate_single_buy_and_hold(
            eq, bd, Money(_WEALTH, Currency.EUR), Decimal("0.75"), Decimal("0.04"), horizon
        )
        results = simulate_batch_buy_and_hold(
            eq,
            bd,
            [Money(_WEALTH, Currency.EUR)] * 12,
            [Decimal("0.75")] * 12,
            [Decimal("0.04")] * 12,
            [horizon] * 12,
            parallel=False,
        )
        assert len(results) == 12
        for ok, fm, wealth, months in results:
            assert (ok, fm, months) == (single[0], single[1], single[3])
            assert wealth.amount == single[2].amount

    def test_batch_parallel_path_matches_sequential(self) -> None:
        horizon = 60
        dataset = _bh_dataset(horizon + 1)
        eq_dec, bd_dec = _bh_returns(dataset, horizon)
        eq = np.array([float(g) for g in eq_dec], dtype=np.float64)
        bd = np.array([float(g) for g in bd_dec], dtype=np.float64)
        args = (
            [Money(_WEALTH, Currency.EUR)] * 12,
            [Decimal("0.75")] * 12,
            [Decimal("0.04")] * 12,
            [horizon] * 12,
        )
        sequential = simulate_batch_buy_and_hold(eq, bd, *args, parallel=False)
        parallel = simulate_batch_buy_and_hold(eq, bd, *args, parallel=True)
        assert [r[2].amount for r in sequential] == [r[2].amount for r in parallel]


# ---------------------------------------------------------------------------
# Executor tests
# ---------------------------------------------------------------------------


class TestBuyAndHoldExecutorDifferential:
    @pytest.mark.parametrize("w", ["0.0", "0.5", "0.75", "1.0"])
    def test_matches_legacy_buy_and_hold_pipeline_without_fees(self, w: str) -> None:
        """With fee=0 the Numba path and the legacy pipeline coincide."""
        horizon = 60
        context = _make_context(_bh_dataset(horizon + 1), horizon, w=w)
        numba = _run_numba([context])[0]
        legacy = SimulationRunner(pipeline=create_buy_and_hold_pipeline()).run(context)

        assert numba[0] == legacy.statistics.success
        assert abs(numba[2] - legacy.statistics.final_wealth.amount) < Decimal("0.01")

    @pytest.mark.parametrize(
        ("w", "expected"),
        [
            ("0.0", Decimal("912841.9501773246703430786791")),
            ("0.5", Decimal("1047594.632679556454083283290")),
            ("0.75", Decimal("1115363.729927754720634587074")),
            ("1.0", Decimal("1183366.467387228912518654144")),
        ],
    )
    def test_matches_hand_derived_recurrence_and_legacy(self, w: str, expected: Decimal) -> None:
        """Anchor the kernel to the independently derived unit-tracking path.

        These terminal values were produced by the Decimal unit-tracking
        recurrence (and independently confirmed by the corrected legacy
        buy-and-hold pipeline) for FixedReal 4%, 60 months, equity +0.6%/mo,
        bond +0.2%/mo, initial value 1,000,000.
        """
        horizon = 60
        context = _make_context(_bh_dataset(horizon + 1), horizon, w=w)
        numba = _run_numba([context])[0]
        legacy = SimulationRunner(pipeline=create_buy_and_hold_pipeline()).run(context)

        assert numba[0] is True
        assert abs(numba[2] - expected) < _TOLERANCE
        assert abs(legacy.statistics.final_wealth.amount - expected) < _TOLERANCE

    @pytest.mark.parametrize("w", ["0.25", "0.6", "0.9"])
    def test_matches_independent_recurrence(self, w: str) -> None:
        horizon = 72
        dataset = _bh_dataset(horizon + 1)
        context = _make_context(dataset, horizon, w=w, rate="0.04")
        ok, fm, wealth, months = _run_numba([context])[0]
        eq_dec, bd_dec = _bh_returns(dataset, horizon)
        exp_value, exp_ok, exp_fm, _ = _bh_recurrence(
            eq_dec, bd_dec, _WEALTH, Decimal(w), Decimal("0.04"), horizon
        )
        assert ok is exp_ok
        assert fm == exp_fm
        assert months == (horizon if ok else fm)
        assert abs(wealth - exp_value) < _TOLERANCE

    def test_initial_allocation_is_applied_at_month_zero(self) -> None:
        """The configured split is the starting point, not the 50/50 default."""
        horizon = 12
        dataset = _bh_dataset(horizon + 1)

        finals = {
            w: _run_numba([_make_context(dataset, horizon, w=w, rate="0")])[0][2]
            for w in ("0.0", "0.5", "1.0")
        }
        # No withdrawals, so the terminal value is a strictly increasing
        # function of the (fixed) initial equity allocation on a market whose
        # equity leg outperforms.
        assert finals["0.0"] < finals["0.5"] < finals["1.0"]

    def test_final_value_target_applied_per_context(self) -> None:
        base = _flat_dataset(61)
        surviving = _make_context(base, 60, w="0.5", rate="0")
        demanding = _make_context(base, 60, w="0.5", rate="0", fvt=Decimal("1.5"))
        results = _run_numba([surviving, demanding])
        assert results[0][0] is True
        assert results[1][0] is False


class TestBuyAndHoldEligibility:
    def test_buy_and_hold_fixed_real_is_eligible(self) -> None:
        assert _is_buy_and_hold_eligible(_make_context(_bh_dataset(37), 36)) is True

    def test_fee_excludes_eligibility(self) -> None:
        context = _make_context(_bh_dataset(37), 36, fee=Decimal("0.0005"))
        assert _is_buy_and_hold_eligible(context) is False

    def test_constant_allocation_is_not_buy_and_hold_eligible(self) -> None:
        base = _bh_dataset(37)
        context = _make_context(base, 36)
        constant = SimulationContext(
            experiment_name=context.experiment_name,
            cohort=context.cohort,
            start_date=context.start_date,
            horizon_months=context.horizon_months,
            initial_wealth=context.initial_wealth,
            initial_portfolio=context.initial_portfolio,
            dataset=context.dataset,
            allocation_policy=ConstantAllocationPolicy(Decimal("0.6")),
            withdrawal_policy=context.withdrawal_policy,
        )
        assert _is_buy_and_hold_eligible(constant) is False

    def test_initial_portfolio_value_mismatch_is_not_eligible(self) -> None:
        base = _flat_dataset(37)
        context = _make_context(base, 36, wealth=Decimal("990000"))
        assert _is_buy_and_hold_eligible(context) is False
        # Falls back to the reference executor and still yields a result.
        assert len(_run_numba([context])) == 1

    def test_leveraged_part49_is_not_eligible(self) -> None:
        """Leverage uses ``Part49WithdrawalPolicy`` (C4), never the B4 kernel."""
        from fbf.core.domain.policies.part49_withdrawal import (
            Part49WithdrawalPolicy,
        )

        context = _make_context(_bh_dataset(37), 36)
        leveraged = SimulationContext(
            experiment_name=context.experiment_name,
            cohort="leveraged",
            start_date=context.start_date,
            horizon_months=context.horizon_months,
            initial_wealth=context.initial_wealth,
            initial_portfolio=context.initial_portfolio,
            dataset=context.dataset,
            allocation_policy=BuyAndHoldAllocationPolicy(Decimal("0.6")),
            withdrawal_policy=Part49WithdrawalPolicy(withdrawal_rate=Decimal("0.04")),
            loan_draw_rate=Decimal("0.4"),
            interest_rate=Decimal("0.02"),
        )
        assert _is_buy_and_hold_eligible(leveraged) is False
        # Falls back to the reference executor and still yields a result.
        assert len(_run_numba([leveraged])) == 1

    def test_three_asset_portfolio_is_not_eligible(self) -> None:
        gold = AssetClass(id="gold", name="", description="")
        base = _bh_dataset(37)
        portfolio = build_initial_portfolio(Money(_WEALTH, Currency.EUR), base)
        three_asset = Portfolio(
            holdings=(
                *portfolio.holdings,
                AssetHolding(asset_class=gold, units=Decimal("1")),
            )
        )
        context = _make_context(base, 36, portfolio=three_asset)
        assert _is_buy_and_hold_eligible(context) is False


class TestBuyAndHoldGrouping:
    def test_shared_trajectory_is_one_cluster(self) -> None:
        base = _bh_dataset(121)
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

        for ctx, result in zip((long_ctx, short_ctx), run.simulation_results, strict=True):
            eq_dec, bd_dec = _bh_returns(base, ctx.horizon_months)
            exp_value, exp_ok, _, _ = _bh_recurrence(
                eq_dec, bd_dec, _WEALTH, Decimal("0.6"), Decimal("0.04"), ctx.horizon_months
            )
            assert result.statistics.success is exp_ok
            assert abs(result.statistics.final_wealth.amount - exp_value) < _TOLERANCE

    def test_different_allocations_are_separate_groups(self) -> None:
        base = _bh_dataset(61)
        a = _make_context(base, 60, w="0.25")
        b = _make_context(base, 60, w="0.75")

        executor = NumbaSimulationExecutor()
        executor.execute(
            EngineExperimentDefinition(
                name="test",
                description="test",
                simulation_contexts=(a, b),
            )
        )
        report = executor.report
        assert report is not None
        assert report.groups == 2

    def test_distinct_datasets_are_not_merged(self) -> None:
        base = _bh_dataset(61)
        a = _make_context(base, 60)
        b = _make_context(_clone_dataset(base), 60)
        # Same trajectory parameters (identical values, same units) but distinct
        # snapshot objects: the identity guard must keep them separate.
        executor = NumbaSimulationExecutor()
        executor.execute(
            EngineExperimentDefinition(
                name="test",
                description="test",
                simulation_contexts=(a, b),
            )
        )
        report = executor.report
        assert report is not None
        assert report.groups == 2


# ---------------------------------------------------------------------------
# Routing tests
# ---------------------------------------------------------------------------


class TestBuyAndHoldRouting:
    def _built_plan(self) -> BuiltStudy:
        dataset = _bh_dataset(121)
        start = dataset[0].date
        cohort = CohortSpecification(start_date=start)
        policy = BuyAndHoldAllocationPolicy(Decimal("0.6"))
        portfolio = build_initial_portfolio(Money(_WEALTH, Currency.EUR), dataset)
        experiment = ExperimentDefinition(
            name="test",
            description="test",
            dataset=dataset,
            horizon_months=120,
            initial_wealth=Money(_WEALTH, Currency.EUR),
            cohorts=(cohort,),
            allocation_policies=(policy,),
            withdrawal_policies=(FixedRealWithdrawalPolicy(withdrawal_rate=Decimal("0.04")),),
        )
        unit = PlannedSimulationUnit(
            cohort=cohort,
            parameter_config=ParameterConfiguration(
                {"equity_allocation": 0.6, "withdrawal_rate": 0.04, "horizon_years": 10}
            ),
            allocation_policy=policy,
            withdrawal_policy=FixedRealWithdrawalPolicy(withdrawal_rate=Decimal("0.04")),
            initial_portfolio=portfolio,
            dataset=dataset.slice(start, 120),
            horizon_months=120,
        )
        plan = ResearchPlan(experiment_definition=experiment, units=(unit,))
        return BuiltStudy(
            plan=plan,
            experiment_definition=experiment,
            cohorts=(cohort,),
            param_configs=(),
        )

    def test_auto_select_routes_buy_and_hold_to_numba(self) -> None:
        built = self._built_plan()
        executor = _auto_select_backend(built, NoOpProfiler())
        assert isinstance(executor, NumbaSimulationExecutor)

    def test_auto_select_does_not_broaden_eligibility_for_mixed_plan(self) -> None:
        """A plan mixing buy-and-hold and other policies must not use the
        buy-and-hold Numba dispatch."""
        built = self._built_plan()
        unit = built.plan.units[0]
        constant_unit = PlannedSimulationUnit(
            cohort=unit.cohort,
            parameter_config=ParameterConfiguration(
                {"equity_allocation": 0.7, "withdrawal_rate": 0.04, "horizon_years": 10}
            ),
            allocation_policy=ConstantAllocationPolicy(Decimal("0.7")),
            withdrawal_policy=unit.withdrawal_policy,
            initial_portfolio=unit.initial_portfolio,
            dataset=unit.dataset,
            horizon_months=unit.horizon_months,
        )
        mixed = ResearchPlan(
            experiment_definition=built.plan.experiment_definition,
            units=(unit, constant_unit),
        )
        mixed_built = BuiltStudy(
            plan=mixed,
            experiment_definition=built.experiment_definition,
            cohorts=built.cohorts,
            param_configs=(),
        )
        # One buy-and-hold unit and one constant-allocation unit: not all units
        # share the buy-and-hold eligibility, so the buy-and-hold dispatch is
        # not selected.  (Constant-allocation units are also not all eligible,
        # so the plan falls through to the Decimal fast path.)
        executor = _auto_select_backend(mixed_built, NoOpProfiler())
        assert not isinstance(executor, NumbaSimulationExecutor)
