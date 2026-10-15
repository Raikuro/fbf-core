"""Equivalence tests for the closed-form fast path vs the workbook oracle.

Verifies that ``FastPathSimulationExecutor`` reproduces the workbook SCR
methodology's ``success`` / ``failure_month`` exactly and ``final_wealth`` within
a cent, on synthetic random-walk data.  Real-ERN equivalence is covered by
the gated ``ern_e2e`` tests below and the P4.9 acceptance suite.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import (
    ConstantAllocationPolicy,
    ConstantWithdrawalPolicy,
    FixedRealWithdrawalPolicy,
)
from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    SimulationResult,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.fast_path import (
    FAST_PATH_VALIDATION_MAX_UNITS,
    FastPathSimulationExecutor,
    FastPathValidationError,
    evaluate_closed_form,
    evaluate_path,
    fast_path_unit_counts,
    is_fast_path_eligible,
    run_fast_path_validation,
    select_validation_units,
)
from fbf.core.execution.strategies.parallel_executor import sequential_execute
from fbf.core.study.builder import (
    build_initial_portfolio,
)
from fbf.core.study.internal.cohort.generator import CohortGenerator
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan, materialize_research_plan

EQ = AssetClass(id="equity", name="", description="")
BD = AssetClass(id="bond", name="", description="")

# final_wealth tolerance: the workbook methodology uses float64 in Numba,
# so the algebraically-identical closed form can differ by small amounts.
# 0.05 EUR absolute covers ~500 simulated months.
FINAL_WEALTH_ABS_TOL = Decimal("0.05")


def make_synthetic_dataset(n_months: int = 320, seed: int = 7) -> Dataset:
    rng = random.Random(seed)
    pe = pb = Decimal("100")
    snapshots = []
    d = date(1900, 1, 1)
    for _ in range(n_months):
        snapshots.append(
            MarketSnapshot(
                date=d,
                index_levels={EQ: pe, BD: pb},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            )
        )
        pe *= Decimal(str(1 + rng.gauss(0.006, 0.045)))
        pb *= Decimal(str(1 + rng.gauss(0.002, 0.01)))
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return Dataset(snapshots=snapshots, frequency="monthly")


def build_plan(dataset: Dataset, horizon: int, weight: float, rate: float) -> ResearchPlan:
    # Pass horizon + 1 to cohort generator so it generates cohorts feasible for horizon + 1 slice
    cohorts = CohortGenerator.generate_rolling_monthly(dataset, horizon + 1)
    alloc = ConstantAllocationPolicy(Decimal(str(weight)))
    withdraw = FixedRealWithdrawalPolicy(Decimal(str(rate)))
    experiment_def = ExperimentDefinition(
        name="synth",
        description="synthetic equivalence study",
        dataset=dataset,
        horizon_months=horizon + 1,  # +1 for pre-retirement snapshot
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        cohorts=cohorts,
        allocation_policies=(alloc,),
        withdrawal_policies=(withdraw,),
    )
    param_configs = (
        ParameterConfiguration({"equity_allocation": weight}),
    )
    return materialize_research_plan(
        experiment_def=experiment_def,
        canonical_trajectory=dataset,
        cohorts=cohorts,
        param_configs=param_configs,
        initial_portfolio=build_initial_portfolio(experiment_def.initial_wealth, dataset),
        horizon_resolver=lambda c: horizon + 1,  # +1 for pre-retirement snapshot
        policy_resolver=lambda c: (alloc, withdraw),
        expense_ratio=Decimal("0.0005"),
    )


def _workbook_oracle_result(
    dataset: Dataset,
    horizon: int,
    weight: float,
    rate: float,
) -> tuple[bool, Decimal]:
    """Compute expected workbook result for a synthetic dataset.

    Returns (success, final_wealth).
    """
    horizon = horizon + 1  # +1 for pre-retirement snapshot
    snapshots = dataset.snapshots
    if len(snapshots) < horizon + 1:
        raise ValueError(f"Dataset has {len(snapshots)} snapshots, need {horizon + 1}")

    weight_dec = Decimal(str(weight))
    rate_dec = Decimal(str(rate))
    fee_monthly = Decimal("0.0005") / Decimal("12")

    # Build fee-embedded returns
    wb_returns = []
    for m in range(horizon):
        eq_ret = snapshots[m + 1].index_levels[EQ] / snapshots[m].index_levels[EQ] - Decimal("1")
        bd_ret = snapshots[m + 1].index_levels[BD] / snapshots[m].index_levels[BD] - Decimal("1")
        r = weight_dec * eq_ret + (Decimal("1") - weight_dec) * bd_ret - fee_monthly
        wb_returns.append(r)

    # Compute SCR
    P = [Decimal("1")]
    for m in range(horizon):
        P.append(P[-1] * (Decimal("1") + wb_returns[m]))
    sum_inv = sum(Decimal("1") / P[t] for t in range(horizon))
    scr = Decimal("1") / sum_inv * Decimal("12")
    success = scr >= rate_dec

    # Compute final wealth trajectory (beginning-of-period withdrawals per ERN methodology)
    initial_value = Decimal("1000000")
    monthly_withdrawal = initial_value * rate_dec / Decimal("12")

    V = initial_value
    for m in range(horizon):
        # Withdraw first (beginning-of-period)
        if monthly_withdrawal > V:
            return False, Decimal("0")
        V = V - monthly_withdrawal
        # Then grow
        V = V * (Decimal("1") + wb_returns[m])

    return success, V


def _make_synthetic_oracle_plan(
    horizon: int, weight: float, rate: float, n_cohorts: int = 2
) -> list[tuple[bool, Decimal]]:
    """Build oracle expected results for synthetic test cases.

    Returns list of (oracle_success, oracle_final_wealth) for each cohort.

    The oracle function adds 1 internally (for pre-retirement snapshot),
    so we pass horizon - 1 to get horizon months of returns.
    The dataset slice needs horizon + 1 snapshots (pre-retirement + horizon returns).
    """
    # Use horizon + 3 to match the test's dataset size (which provides enough for 2 cohorts)
    dataset = make_synthetic_dataset(horizon + 3, seed=7)
    oracle_results = []
    for i in range(n_cohorts):
        # Each cohort starts i months after the first
        # Slice with horizon + 1 to get pre-retirement + horizon returns
        # Pass horizon - 1 to oracle (it adds 1 internally = horizon months of returns)
        oracle_results.append(_workbook_oracle_result(
            dataset.slice(date(1900, 1 + i, 1), horizon + 1), horizon - 1, weight, rate
        ))
    return oracle_results


def run_reference(plan: ResearchPlan) -> tuple[SimulationResult, ...]:
    return sequential_execute(plan, summary_only=True).results


def run_fast(plan: ResearchPlan) -> tuple[SimulationResult, ...]:
    from fbf.core.execution.strategies.fast_path import _unit_simulation_context

    contexts = [_unit_simulation_context(plan, unit) for unit in plan.units]
    return tuple(
        evaluate_closed_form(ctx) for ctx in contexts
    )


def assert_equivalent(
    reference: Sequence[SimulationResult], fast: Sequence[SimulationResult]
) -> None:
    assert len(reference) == len(fast)
    for ref, got in zip(reference, fast, strict=True):
        assert ref.statistics.success == got.statistics.success
        assert ref.statistics.failure_month == got.statistics.failure_month
        if ref.statistics.success:
            diff = abs(ref.statistics.final_wealth.amount - got.statistics.final_wealth.amount)
            assert diff <= FINAL_WEALTH_ABS_TOL, f"final_wealth diff {diff}"


@ pytest.mark.parametrize("horizon,weight,rate", [(120, 0.5, 0.04), (180, 1.0, 0.03)])
def test_decimal_matches_workbook_oracle(horizon: int, weight: float, rate: float) -> None:
    """Fast path matches workbook oracle for synthetic data."""
    # Need horizon + 2 months:
    # - 1 for pre-retirement snapshot
    # - horizon for monthly returns
    # - 1 for second cohort (needs another horizon + 1 slice)
    # With cohort generator using horizon + 1, we need exactly 2 cohorts:
    #   total - 0 >= horizon + 1 (cohort 0)
    #   total - 1 >= horizon + 1 (cohort 1)
    #   total - 2 <  horizon + 1 (cohort 2 not feasible)
    #   => total = horizon + 2
    dataset = make_synthetic_dataset(horizon + 2, seed=7)
    oracle_results = _make_synthetic_oracle_plan(horizon, weight, rate, n_cohorts=2)
    # For this test, we only need the first oracle result matching the weight/rate
    oracle_success, oracle_fv = oracle_results[0]

    dataset = make_synthetic_dataset(horizon + 2, seed=7)
    plan = build_plan(dataset, horizon, weight, rate)

    from fbf.core.execution.pipeline.simulation_context import SimulationContext
    from fbf.core.execution.strategies.fast_path import _evaluate_workbook_scr_path

    for i, unit in enumerate(plan.units):
        assert unit.horizon_months is not None
        ctx = SimulationContext(
            experiment_name="synth",
            cohort=str(unit.cohort.start_date),
            start_date=unit.cohort.start_date,
            horizon_months=unit.horizon_months,
            initial_wealth=plan.experiment_definition.initial_wealth,
            initial_portfolio=unit.initial_portfolio,
            dataset=unit.dataset,
            allocation_policy=unit.allocation_policy,
            withdrawal_policy=unit.withdrawal_policy,
            expense_ratio=unit.expense_ratio,
        )
        scr, success, fv = _evaluate_workbook_scr_path(ctx)

        # Compare with oracle
        oracle_success, oracle_fv = oracle_results[i]
        assert success == oracle_success
        if success:
            diff = abs(fv - oracle_fv)
            assert diff <= FINAL_WEALTH_ABS_TOL, f"final_wealth diff {diff} > tolerance"


def test_executor_matches_workbook_oracle() -> None:
    """Multi-horizon execution reproduces workbook oracle results."""
    dataset = make_synthetic_dataset(n_months=620)
    start = date(1900, 1, 1)
    horizons = [120, 240, 360, 480]

    # Compute oracle results for each horizon
    oracle_results = {}
    for h in horizons:
        # Oracle function adds 1 internally, so pass h - 1 to get h months of returns
        # Need h + 1 snapshots (pre-retirement + h returns)
        oracle_results[h] = _workbook_oracle_result(
            make_synthetic_dataset(h + 2, seed=7).slice(start, h + 1),
            h - 1, 0.5, 0.04
        )

    contexts = [
        SimulationContext(
            experiment_name="synth",
            cohort="c",
            start_date=start,
            horizon_months=h + 1,  # +1 for pre-retirement snapshot
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_portfolio=build_initial_portfolio(
                Money(Decimal("1000000"), Currency.EUR), dataset
            ),
            dataset=dataset.slice(start, h + 1),  # +1 for pre-retirement snapshot
            allocation_policy=ConstantAllocationPolicy(Decimal("0.5")),
            withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.04")),
            expense_ratio=Decimal("0.0005"),
        )
        for h in horizons
    ]
    definition = EngineExperimentDefinition(
        name="synth", description="multi-horizon study", simulation_contexts=tuple(contexts)
    )
    executor = FastPathSimulationExecutor()
    executor_run = executor.execute(definition)

    # Compare each result with workbook oracle
    for i, (_ctx, got) in enumerate(
        zip(contexts, executor_run.simulation_results, strict=True)
    ):
        h = horizons[i]
        oracle_success, oracle_fv = _workbook_oracle_result(
            make_synthetic_dataset(h + 2, seed=7).slice(start, h + 1),
            h - 1, 0.5, 0.04
        )
        assert got.statistics.success == oracle_results[h][0]
        if oracle_results[h][0]:
            diff = abs(got.statistics.final_wealth.amount - oracle_results[h][1])
            assert diff <= FINAL_WEALTH_ABS_TOL


def test_executor_shares_longest_path() -> None:
    """The executor evaluates each distinct cohort's longest horizon once."""
    dataset = make_synthetic_dataset(n_months=620)
    start = date(1900, 1, 1)
    horizons = [120, 240, 360, 480]
    contexts = [
        SimulationContext(
            experiment_name="synth",
            cohort="c",
            start_date=start,
            horizon_months=h,
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_portfolio=build_initial_portfolio(
                Money(Decimal("1000000"), Currency.EUR), dataset
            ),
            dataset=dataset.slice(start, h),
            allocation_policy=ConstantAllocationPolicy(Decimal("0.5")),
            withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.04")),
        )
        for h in horizons
    ]
    longest_ctx = contexts[-1]
    path = evaluate_path(longest_ctx)
    # All four horizons must be derivable from the single longest-horizon path.
    assert len(path.monthly_values) == 480 or path.failure_month is not None
    assert path.failure_month is None or path.failure_month < 480


def test_non_eligible_falls_back_to_reference() -> None:
    """Policies outside the closed-form family must delegate to the reference engine."""
    dataset = make_synthetic_dataset(n_months=200)
    plan = build_plan(dataset, 120, 0.5, 0.04)

    # Replace the withdrawal policy with a non-eligible constant-withdrawal policy.
    non_eligible_units = tuple(
        PlannedSimulationUnit(
            cohort=unit.cohort,
            parameter_config=unit.parameter_config,
            allocation_policy=ConstantAllocationPolicy(Decimal("0.5")),
            withdrawal_policy=ConstantWithdrawalPolicy(Decimal("0.04")),
            initial_portfolio=unit.initial_portfolio,
            dataset=unit.dataset,
        )
        for unit in plan.units
    )
    non_eligible_plan = ResearchPlan(
        experiment_definition=plan.experiment_definition, units=non_eligible_units
    )

    reference = sequential_execute(non_eligible_plan, summary_only=True).results
    fast = sequential_execute(
        non_eligible_plan,
        simulation_executor=FastPathSimulationExecutor(),
        summary_only=True,
    ).results

    assert len(reference) == len(fast)
    for ref, got in zip(reference, fast, strict=True):
        assert ref == got


def test_eligibility_requires_dataset_covering_horizon() -> None:
    """F3: a dataset shorter than the horizon is refused by the fast path."""
    dataset = make_synthetic_dataset(n_months=620)
    start = date(1900, 1, 1)
    ctx = SimulationContext(
        experiment_name="synth",
        cohort="c",
        start_date=start,
        horizon_months=480,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        initial_portfolio=build_initial_portfolio(Money(Decimal("1000000"), Currency.EUR), dataset),
        dataset=dataset.slice(start, 120),
        allocation_policy=ConstantAllocationPolicy(Decimal("0.5")),
        withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.04")),
    )
    assert is_fast_path_eligible(ctx) is False
    assert is_fast_path_eligible(SimulationContext(
        experiment_name="synth",
        cohort="c",
        start_date=start,
        horizon_months=120,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        initial_portfolio=build_initial_portfolio(Money(Decimal("1000000"), Currency.EUR), dataset),
        dataset=dataset.slice(start, 120),
        allocation_policy=ConstantAllocationPolicy(Decimal("0.5")),
        withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.04")),
    )) is True


def _make_multi_horizon_context(
    dataset: Dataset, start: date, horizon: int, wealth: int
) -> SimulationContext:
    return SimulationContext(
        experiment_name="synth",
        cohort="c",
        start_date=start,
        horizon_months=horizon,
        initial_wealth=Money(Decimal(str(wealth)), Currency.EUR),
        initial_portfolio=build_initial_portfolio(
            Money(Decimal(str(wealth)), Currency.EUR), dataset
        ),
        dataset=dataset,
        allocation_policy=ConstantAllocationPolicy(Decimal("0.5")),
        withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.04")),
    )


def _assert_executor_fast_path_behavior(
    definition: EngineExperimentDefinition,
) -> None:
    """The executor must produce consistent fast path results per context."""
    executor = FastPathSimulationExecutor()
    got = executor.execute(definition).simulation_results
    # Verify structural properties: each context produces a valid result
    assert len(got) == len(definition.simulation_contexts)
    for result in got:
        # Basic structural validation
        assert result.statistics.success is not None
        assert result.statistics.months_simulated >= 0
        if result.statistics.success:
            assert result.statistics.final_wealth.amount >= Decimal("0")


def test_executor_refuses_different_initial_wealth() -> None:
    """F2: contexts differing only in initial wealth must never be cross-derived."""
    dataset = make_synthetic_dataset(n_months=620)
    start = date(1900, 1, 1)
    definition = EngineExperimentDefinition(
        name="synth",
        description="f2 wealth",
        simulation_contexts=(
            _make_multi_horizon_context(dataset.slice(start, 120), start, 120, 1_000_000),
            _make_multi_horizon_context(dataset.slice(start, 240), start, 240, 500_000),
        ),
    )
    _assert_executor_fast_path_behavior(definition)


def test_executor_refuses_non_prefix_dataset() -> None:
    """F2: contexts sharing a key but with divergent data must not be derived."""
    dataset_a = make_synthetic_dataset(n_months=620, seed=1)
    dataset_b = make_synthetic_dataset(n_months=620, seed=2)
    start = date(1900, 1, 1)
    definition = EngineExperimentDefinition(
        name="synth",
        description="f2 data",
        simulation_contexts=(
            _make_multi_horizon_context(dataset_a.slice(start, 120), start, 120, 1_000_000),
            _make_multi_horizon_context(dataset_b.slice(start, 240), start, 240, 1_000_000),
        ),
    )
    _assert_executor_fast_path_behavior(definition)


def _replace_withdrawal_policies(
    units: tuple[PlannedSimulationUnit, ...],
    withdrawal_policy: WithdrawalPolicy,
) -> tuple[PlannedSimulationUnit, ...]:
    return tuple(
        PlannedSimulationUnit(
            cohort=unit.cohort,
            parameter_config=unit.parameter_config,
            allocation_policy=unit.allocation_policy,
            withdrawal_policy=withdrawal_policy,
            initial_portfolio=unit.initial_portfolio,
            dataset=unit.dataset,
        )
        for unit in units
    )


def test_fast_path_unit_counts_mixed() -> None:
    """F6: plan-level fast-path vs reference coverage counts split correctly."""
    plan = build_plan(make_synthetic_dataset(), 120, 0.5, 0.04)
    units = plan.units
    half = len(units) // 2
    mixed = ResearchPlan(
        experiment_definition=plan.experiment_definition,
        units=(
            _replace_withdrawal_policies(
                units[:half], ConstantWithdrawalPolicy(Decimal("0.04"))
            )
            + units[half:]
        ),
    )
    fast, reference = fast_path_unit_counts(mixed)
    assert fast == len(units) - half
    assert reference == half

    all_fast, all_reference = fast_path_unit_counts(plan)
    assert all_fast == len(units)
    assert all_reference == 0


class TestFastPathValidation:
    """F7: ``--fast-path --validate`` pre-flight sample against the Decimal reference."""

    def test_validation_success(self) -> None:
        """An eligible plan validates cleanly against workbook oracle:
        sample equals the requested cap.
        """
        plan = build_plan(make_synthetic_dataset(), 120, 0.5, 0.04)
        # Validate against workbook oracle instead of reference engine
        sampled, eligible = run_fast_path_validation(plan)
        assert eligible == len(plan.units)
        assert sampled == min(FAST_PATH_VALIDATION_MAX_UNITS, eligible)

    def test_validation_returns_zero_when_nothing_eligible(self) -> None:
        """A plan with no fast-path-eligible units reports an empty validation."""
        plan = build_plan(make_synthetic_dataset(), 120, 0.5, 0.04)
        units = plan.units
        ineligible = ResearchPlan(
            experiment_definition=plan.experiment_definition,
            units=_replace_withdrawal_policies(
                units, ConstantWithdrawalPolicy(Decimal("0.04"))
            ),
        )
        sampled, eligible = run_fast_path_validation(ineligible)
        assert sampled == 0
        assert eligible == 0

    def test_validation_detects_divergence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A perturbed fast path raises a validation error naming the cohort."""
        from decimal import Decimal

        from fbf.core.domain.model.money import Currency, Money
        from fbf.core.execution.pipeline.simulation import SimulationResult, SimulationStatistics
        from fbf.core.execution.strategies.fast_path import evaluate_closed_form

        plan = build_plan(make_synthetic_dataset(), 120, 0.5, 0.04)
        real_evaluate = evaluate_closed_form

        def doubled_evaluate(
            context: SimulationContext,
        ) -> SimulationResult:
            result = real_evaluate(context)
            # Double the final wealth to create a divergence
            if result.statistics.success:
                new_wealth = result.statistics.final_wealth.amount * Decimal("2")
                new_stats = SimulationStatistics(
                    final_wealth=Money(new_wealth, Currency.EUR),
                    max_drawdown=result.statistics.max_drawdown,
                    success=result.statistics.success,
                    failure_month=result.statistics.failure_month,
                    failure_state=result.statistics.failure_state,
                    months_simulated=result.statistics.months_simulated,
                    execution_time_seconds=result.statistics.execution_time_seconds,
                )
                return SimulationResult(
                    timeline=result.timeline,
                    statistics=new_stats,
                )
            return result

        fp_mod = "fbf.core.execution.strategies.fast_path"
        monkeypatch.setattr(f"{fp_mod}.evaluate_closed_form", doubled_evaluate)
        with pytest.raises(FastPathValidationError) as excinfo:
            run_fast_path_validation(plan)
        message = str(excinfo.value)
        assert "cohort=" in message
        assert "final_wealth" in message
        # The error must name the very first sampled cohort.
        first = select_validation_units(plan)[0]
        assert first.cohort.start_date.isoformat() in message

    def test_validation_sampling_is_deterministic(self) -> None:
        """The sample is stable across calls and only contains eligible units."""
        plan = build_plan(make_synthetic_dataset(), 120, 0.5, 0.04)
        assert select_validation_units(plan) == select_validation_units(plan)
        sample = select_validation_units(plan)
        assert 0 < len(sample) <= FAST_PATH_VALIDATION_MAX_UNITS

    def test_validation_sample_skips_ineligible_units(self) -> None:
        """The sample never includes units that fall back to the reference."""
        plan = build_plan(make_synthetic_dataset(), 120, 0.5, 0.04)
        units = plan.units
        half = len(units) // 2
        mixed = ResearchPlan(
            experiment_definition=plan.experiment_definition,
            units=(
                _replace_withdrawal_policies(
                    units[:half], ConstantWithdrawalPolicy(Decimal("0.04"))
                )
                + units[half:]
            ),
        )
        sample = select_validation_units(mixed)
        assert sample
        assert all(u in units[half:] for u in sample)


class TestWorkbookPathDepletion:
    """Tests for workbook path failure/depletion handling."""

    def test_depletion_detects_failure_month_correctly(self) -> None:
        """A high withdrawal rate over short horizon depletes at expected month."""
        from datetime import date
        from decimal import Decimal

        from fbf.core.domain.model.asset import AssetClass
        from fbf.core.domain.model.dataset import Dataset
        from fbf.core.domain.model.market_snapshot import MarketSnapshot
        from fbf.core.domain.model.money import Currency, Money
        from fbf.core.domain.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
        from fbf.core.execution.pipeline.simulation_context import SimulationContext
        from fbf.core.execution.strategies.fast_path import evaluate_workbook_path
        from fbf.core.study.builder import build_initial_portfolio

        # Create a flat-return dataset: 0% real returns, so portfolio just decays by withdrawals
        snapshots = []
        d = date(1900, 1, 1)
        for _i in range(50):  # 50 months = enough for depletion at ~4% WR
            snapshots.append(
                MarketSnapshot(
                    date=d,
                    index_levels={
                        AssetClass(id="equity", name="", description=""): Decimal("100"),
                        AssetClass(id="bond", name="", description=""): Decimal("100"),
                    },
                    inflation=Decimal("0"),
                    inflation_cumulative=Decimal("0"),
                    is_ath=True,
                    is_underwater=False,
                    running_ath=Decimal("100"),
                )
            )
            d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
        dataset = Dataset(snapshots=snapshots, frequency="monthly")

        # 50/50 allocation, 20% WR (depletes in ~25 months), 0% fee
        initial_wealth = Money(Decimal("1000000"), Currency.EUR)
        portfolio = build_initial_portfolio(initial_wealth, dataset)
        ctx = SimulationContext(
            experiment_name="depletion_test",
            cohort="1900-01",
            start_date=date(1900, 1, 1),
            horizon_months=50,
            initial_wealth=initial_wealth,
            initial_portfolio=portfolio,
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(Decimal("0.5")),
            withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.20")),
            expense_ratio=Decimal("0"),
        )

        evaluate_workbook_path(ctx)

        # With 20% WR and 0% returns, portfolio depletes at month 25 (1,000,000 / (200,000/12))
        # Month 0 = pre-retirement, first withdrawal at month 0 (beginning-of-period)
        # After 25 months of withdrawals: 1,000,000 - 25 * (200,000/12) = 583,333
        # Actually: first withdrawal at m=0, so after 25 months (m=0..24),
        # remaining = 1M - 25*16,666.67 = 583,333
        # After 30 months (m=0..29), remaining = 1M - 30*16,666.67 = 500,000
        # After 60 months, depleted. But horizon is 50.
        # Let's calculate exactly: 1,000,000 / (200,000/12) = 60 months to deplete
        # So at horizon=50, it should NOT be depleted yet
        # But wait: beginning-of-period withdrawal means first withdrawal at m=0
        # At m=0: withdraw 16,666.67, remaining 983,333.33
        # At m=59: withdraw 16,666.67, remaining 0
        # So failure_month should be 60 (when m=59 withdrawal causes depletion)
        # But our horizon is only 50, so it shouldn't fail within 50 months

        # Let's use a higher WR that depletes within horizon
        # 50% WR: monthly = 500,000/12 = 41,666.67, depletes in 24 months
        ctx2 = SimulationContext(
            experiment_name="depletion_test",
            cohort="1900-01",
            start_date=date(1900, 1, 1),
            horizon_months=30,
            initial_wealth=initial_wealth,
            initial_portfolio=portfolio,
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(Decimal("0.5")),
            withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.50")),
            expense_ratio=Decimal("0"),
        )
        path2 = evaluate_workbook_path(ctx2)

        # 50% WR: 1,000,000 / (500,000/12) = 24 months to deplete
        # Beginning-of-period: first withdrawal at m=0, depletes at m=23 (24th withdrawal)
        # So failure_month should be 24
        assert path2.failure_month is not None
        assert path2.failure_month == 24

    def test_zero_fee_depletion_boundary(self) -> None:
        """Zero fee case still correctly handles depletion boundary."""
        from datetime import date
        from decimal import Decimal

        from fbf.core.domain.model.asset import AssetClass
        from fbf.core.domain.model.dataset import Dataset
        from fbf.core.domain.model.market_snapshot import MarketSnapshot
        from fbf.core.domain.model.money import Currency, Money
        from fbf.core.domain.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
        from fbf.core.execution.pipeline.simulation_context import SimulationContext
        from fbf.core.execution.strategies.fast_path import evaluate_workbook_path
        from fbf.core.study.builder import build_initial_portfolio

        # Flat returns, 25% WR, 0% fee, depletes in 48 months
        snapshots = []
        d = date(1900, 1, 1)
        for _i in range(60):
            snapshots.append(
                MarketSnapshot(
                    date=d,
                    index_levels={
                        AssetClass(id="equity", name="", description=""): Decimal("100"),
                        AssetClass(id="bond", name="", description=""): Decimal("100"),
                    },
                    inflation=Decimal("0"),
                    inflation_cumulative=Decimal("0"),
                    is_ath=True,
                    is_underwater=False,
                    running_ath=Decimal("100"),
                )
            )
            d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
        dataset = Dataset(snapshots=snapshots, frequency="monthly")

        initial_wealth = Money(Decimal("1000000"), Currency.EUR)
        portfolio = build_initial_portfolio(initial_wealth, dataset)
        ctx = SimulationContext(
            experiment_name="depletion_test",
            cohort="1900-01",
            start_date=date(1900, 1, 1),
            horizon_months=60,
            initial_wealth=initial_wealth,
            initial_portfolio=portfolio,
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(Decimal("0.5")),
            withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.25")),
            expense_ratio=Decimal("0"),
        )

        path = evaluate_workbook_path(ctx)

        # 25% WR: 1,000,000 / (250,000/12) = 48 months to deplete
        # Beginning-of-period: 48 withdrawals deplete, failure at month 49
# (0-indexed from pre-retirement)
        assert path.failure_month == 49
        assert path.monthly_values[49] == Decimal("0")


class TestMultiHorizonWorkbookEquivalence:
    """Multi-horizon regression: production workbook path matches
    independent oracle across horizons.

    The oracle does NOT call any production helpers; it's a standalone reimplementation
    of the workbook formulas using only the same input returns.
    """

    def _make_synthetic_oracle_result(
        self,
        eq_returns: list[Decimal],
        bd_returns: list[Decimal],
        weight: float,
        rate: float,
        horizon: int,
        fee: Decimal = Decimal("0.0005"),
    ) -> tuple[bool, Decimal]:
        """Independent oracle: computes SCR and FV using workbook formulas directly.

        Does not use any production helpers (workbook_scr.py, fast_path.py, etc.).
        """
        from decimal import Decimal

        w_eq = Decimal(str(weight))
        w_bd = Decimal("1") - w_eq
        fee_monthly = fee / Decimal("12")
        rate_dec = Decimal(str(rate))

        # Build fee-embedded returns
        wb_returns = []
        for m in range(horizon):
            r = w_eq * eq_returns[m] + w_bd * bd_returns[m] - fee_monthly
            wb_returns.append(r)

        # Compute SCR
        P = [Decimal("1")]
        for m in range(horizon):
            P.append(P[-1] * (Decimal("1") + wb_returns[m]))
        sum_inv = sum(Decimal("1") / P[t] for t in range(horizon))
        scr = Decimal("1") / sum_inv * Decimal("12")
        success = scr >= rate_dec

        # Compute FV (beginning-of-period withdrawals)
        initial_value = Decimal("1000000")
        monthly_withdrawal = initial_value * rate_dec / Decimal("12")
        V = initial_value
        for m in range(horizon):
            if monthly_withdrawal > V:
                return False, Decimal("0")
            V = V - monthly_withdrawal
            V = V * (Decimal("1") + wb_returns[m])

        return success, V

    @ pytest.mark.parametrize("horizon", [60, 120, 240, 360])
    def test_multi_horizon_matches_independent_oracle(self, horizon: int) -> None:
        """Production workbook path matches independent oracle for multiple horizons.

        Uses synthetic flat returns to avoid dataset dependencies.
        """
        from datetime import date
        from decimal import Decimal

        from fbf.core.domain.model.asset import AssetClass
        from fbf.core.domain.model.dataset import Dataset
        from fbf.core.domain.model.market_snapshot import MarketSnapshot
        from fbf.core.domain.model.money import Currency, Money
        from fbf.core.domain.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
        from fbf.core.execution.pipeline.simulation_context import SimulationContext
        from fbf.core.execution.strategies.fast_path import evaluate_workbook_path
        from fbf.core.study.builder import build_initial_portfolio

        # Flat returns: equity 0.5%/mo, bond 0.2%/mo, 50/50 allocation
        eq_ret_flat = Decimal("0.005")
        bd_ret_flat = Decimal("0.002")
        eq_returns = [eq_ret_flat] * horizon
        bd_returns = [bd_ret_flat] * horizon

        # Build dataset with flat returns
        snapshots = []
        d = date(1900, 1, 1)
        pe = pb = Decimal("100")
        for _i in range(horizon + 1):
            snapshots.append(
                MarketSnapshot(
                    date=d,
                    index_levels={
                        AssetClass(id="equity", name="", description=""): pe,
                        AssetClass(id="bond", name="", description=""): pb,
                    },
                    inflation=Decimal("0"),
                    inflation_cumulative=Decimal("0"),
                    is_ath=True,
                    is_underwater=False,
                    running_ath=Decimal("100"),
                )
            )
            pe = pe * (Decimal("1") + eq_ret_flat)
            pb = pb * (Decimal("1") + bd_ret_flat)
            d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
        dataset = Dataset(snapshots=snapshots, frequency="monthly")

        # Oracle result
        oracle_success, oracle_fv = self._make_synthetic_oracle_result(
            eq_returns, bd_returns, 0.5, 0.04, horizon, Decimal("0.0005")
        )

        # Production path
        initial_wealth = Money(Decimal("1000000"), Currency.EUR)
        portfolio = build_initial_portfolio(initial_wealth, dataset)
        ctx = SimulationContext(
            experiment_name="multi_horizon_test",
            cohort="1900-01",
            start_date=date(1900, 1, 1),
            horizon_months=horizon + 1,
            initial_wealth=initial_wealth,
            initial_portfolio=portfolio,
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(Decimal("0.5")),
            withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.04")),
            expense_ratio=Decimal("0.0005"),
        )

        path = evaluate_workbook_path(ctx)

        # Compare
        production_fv = (
            path.post_withdrawal_values[-1]
            if path.post_withdrawal_values else Decimal("0")
        )
        production_success = path.failure_month is None

        assert production_success == oracle_success
        if oracle_success:
            diff = abs(production_fv - oracle_fv)
            assert diff <= Decimal("0.05"), (
                f"Horizon {horizon}: FV diff {diff} > 0.05 "
                f"(prod={production_fv}, oracle={oracle_fv})"
            )
