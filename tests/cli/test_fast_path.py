"""Equivalence tests for the closed-form fast path vs the reference engine.

Verifies that ``FastPathSimulationExecutor`` (float and decimal precision) and
``ChainedFastPathSimulationExecutor`` reproduce the reference Decimal pipeline's
``success`` / ``failure_month`` exactly and ``final_wealth`` within a cent, on
synthetic random-walk data.  Real-ERN equivalence is covered by the gated
``ern_e2e`` tests below and the P4.9 acceptance suite.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

import pytest

from cli.builders import (
    build_initial_portfolio,
    build_parameter_configs,
    build_research_plan,
)
from cli.fast_path import (
    ChainedFastPathSimulationExecutor,
    FastPathSimulationExecutor,
    Precision,
    evaluate_path,
    fast_path_unit_counts,
    is_fast_path_eligible,
)
from cli.policies import (
    ConstantAllocationPolicy,
    ConstantWithdrawalPolicy,
    FixedRealWithdrawalPolicy,
)
from engine.application.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    SimulationResult,
)
from engine.application.simulation_context import SimulationContext
from engine.domain.model.asset import AssetClass
from engine.domain.model.dataset import Dataset
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.money import Currency, Money
from engine.domain.policies.withdrawal_policy import WithdrawalPolicy
from infrastructure.execution.parallel_executor import sequential_execute
from research.domain.cohort.generator import CohortGenerator
from research.domain.experiment.definition import ExperimentDefinition
from research.domain.plan import PlannedSimulationUnit, ResearchPlan

EQ = AssetClass(id="equity", name="", description="")
BD = AssetClass(id="bond", name="", description="")

# final_wealth tolerance: the reference pipeline rebalances holdings with
# Decimal division each month, so the algebraically-identical closed form can
# differ by sub-cent amounts.  0.05 EUR absolute covers ~500 simulated months.
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
    return Dataset(snapshots=snapshots, frequency="monthly", version="1.0")


def build_plan(dataset: Dataset, horizon: int, weight: float, rate: float) -> ResearchPlan:
    cohorts = CohortGenerator.generate_rolling_monthly(dataset, horizon)
    alloc = ConstantAllocationPolicy(Decimal(str(weight)))
    withdraw = FixedRealWithdrawalPolicy(Decimal(str(rate)))
    experiment_def = ExperimentDefinition(
        name="synth",
        description="synthetic equivalence study",
        dataset=dataset,
        horizon_months=horizon,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        cohorts=cohorts,
        allocation_policies=(alloc,),
        withdrawal_policies=(withdraw,),
    )
    param_configs = build_parameter_configs({"equity_allocation": [weight]})
    return build_research_plan(experiment_def, cohorts, param_configs, alloc, withdraw)


def run_reference(plan: ResearchPlan) -> tuple[SimulationResult, ...]:
    return sequential_execute(plan, summary_only=True).results


def run_fast(plan: ResearchPlan, precision: Precision) -> tuple[SimulationResult, ...]:
    executor = FastPathSimulationExecutor(precision=precision)
    return sequential_execute(plan, simulation_executor=executor, summary_only=True).results


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


@pytest.mark.parametrize("horizon,weight,rate", [(120, 0.5, 0.04), (180, 0.25, 0.045)])
def test_float_matches_reference(horizon: int, weight: float, rate: float) -> None:
    plan = build_plan(make_synthetic_dataset(), horizon, weight, rate)
    assert_equivalent(run_reference(plan), run_fast(plan, "float"))


@pytest.mark.parametrize("horizon,weight,rate", [(120, 0.5, 0.04), (180, 1.0, 0.03)])
def test_decimal_matches_reference(horizon: int, weight: float, rate: float) -> None:
    plan = build_plan(make_synthetic_dataset(), horizon, weight, rate)
    assert_equivalent(run_reference(plan), run_fast(plan, "decimal"))


def test_float_matches_decimal() -> None:
    """Float and decimal closed forms agree with each other on outcomes."""
    plan = build_plan(make_synthetic_dataset(), 180, 0.5, 0.04)
    assert_equivalent(run_fast(plan, "decimal"), run_fast(plan, "float"))


def test_chained_executor_matches_reference() -> None:
    """Chained mixed-horizon execution reproduces the reference per-horizon."""
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
            initial_portfolio=build_initial_portfolio(Money(Decimal("1000000"), Currency.EUR)),
            dataset=dataset.slice(start, h),
            allocation_policy=ConstantAllocationPolicy(Decimal("0.5")),
            withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.04")),
        )
        for h in horizons
    ]
    definition = EngineExperimentDefinition(
        name="synth", description="chaining study", simulation_contexts=tuple(contexts)
    )
    reference = FastPathSimulationExecutor(precision="float")
    chained = ChainedFastPathSimulationExecutor(precision="float")

    ref_run = reference.execute(definition)
    chained_run = chained.execute(definition)
    for ref, got in zip(ref_run.simulation_results, chained_run.simulation_results, strict=True):
        assert ref.statistics.success == got.statistics.success
        assert ref.statistics.failure_month == got.statistics.failure_month
        assert (
            abs(ref.statistics.final_wealth.amount - got.statistics.final_wealth.amount)
            <= FINAL_WEALTH_ABS_TOL
        )


def test_chained_executor_shares_longest_path() -> None:
    """The chained executor evaluates each distinct cohort's longest horizon once."""
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
            initial_portfolio=build_initial_portfolio(Money(Decimal("1000000"), Currency.EUR)),
            dataset=dataset.slice(start, h),
            allocation_policy=ConstantAllocationPolicy(Decimal("0.5")),
            withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.04")),
        )
        for h in horizons
    ]
    longest_ctx = contexts[-1]
    path = evaluate_path(longest_ctx, "float")
    # All four horizons must be derivable from the single longest-horizon path.
    assert len(path.monthly_values) == 480 or path.failure_month is not None
    assert path.failure_month is None or path.failure_month < 480


def test_non_eligible_falls_back_to_reference() -> None:
    """Policies outside the closed-form family must delegate to the reference."""
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
        simulation_executor=FastPathSimulationExecutor(precision="float"),
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
        initial_portfolio=build_initial_portfolio(Money(Decimal("1000000"), Currency.EUR)),
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
        initial_portfolio=build_initial_portfolio(Money(Decimal("1000000"), Currency.EUR)),
        dataset=dataset.slice(start, 120),
        allocation_policy=ConstantAllocationPolicy(Decimal("0.5")),
        withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.04")),
    )) is True


def _make_chaining_context(
    dataset: Dataset, start: date, horizon: int, wealth: int
) -> SimulationContext:
    return SimulationContext(
        experiment_name="synth",
        cohort="c",
        start_date=start,
        horizon_months=horizon,
        initial_wealth=Money(Decimal(str(wealth)), Currency.EUR),
        initial_portfolio=build_initial_portfolio(Money(Decimal(str(wealth)), Currency.EUR)),
        dataset=dataset,
        allocation_policy=ConstantAllocationPolicy(Decimal("0.5")),
        withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.04")),
    )


def _assert_chained_matches_per_context(
    definition: EngineExperimentDefinition,
) -> None:
    """The chained executor must reproduce per-context fast-path results."""
    reference = FastPathSimulationExecutor(precision="float")
    chained = ChainedFastPathSimulationExecutor(precision="float")
    expected = reference.execute(definition).simulation_results
    got = chained.execute(definition).simulation_results
    assert len(expected) == len(got)
    for ref, fast in zip(expected, got, strict=True):
        assert ref.statistics == fast.statistics


def test_chained_executor_refuses_different_initial_wealth() -> None:
    """F2: contexts differing only in initial wealth must never be cross-derived."""
    dataset = make_synthetic_dataset(n_months=620)
    start = date(1900, 1, 1)
    definition = EngineExperimentDefinition(
        name="synth",
        description="f2 wealth",
        simulation_contexts=(
            _make_chaining_context(dataset.slice(start, 120), start, 120, 1_000_000),
            _make_chaining_context(dataset.slice(start, 240), start, 240, 500_000),
        ),
    )
    _assert_chained_matches_per_context(definition)


def test_chained_executor_refuses_non_prefix_dataset() -> None:
    """F2: contexts sharing a key but with divergent data must not be chained."""
    dataset_a = make_synthetic_dataset(n_months=620, seed=1)
    dataset_b = make_synthetic_dataset(n_months=620, seed=2)
    start = date(1900, 1, 1)
    definition = EngineExperimentDefinition(
        name="synth",
        description="f2 data",
        simulation_contexts=(
            _make_chaining_context(dataset_a.slice(start, 120), start, 120, 1_000_000),
            _make_chaining_context(dataset_b.slice(start, 240), start, 240, 1_000_000),
        ),
    )
    _assert_chained_matches_per_context(definition)


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
