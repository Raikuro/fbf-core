"""C3 — Multi-Cohort Validation: Part 49 Production Path Isolation.

Validates that the corrected Part 49 production path behaves correctly across
multiple independent cohorts without cross-cohort state contamination or
accidental sharing of cohort-specific portfolio state.

This test exercises the ACTUAL production research-layer path:
    StudyConfiguration -> build_study_plan -> materialize_research_plan
    -> PlannedSimulationUnit -> ResearchExecutor -> SimulationContext
    -> SimulationRunner -> debt-aware production pipeline

It does NOT manually construct SimulationContext, SimulationState, or Portfolio.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import ConstantAllocationPolicy
from fbf.core.domain.policies.part49_withdrawal import Part49WithdrawalPolicy
from fbf.core.execution.executor import ResearchExecutor
from fbf.core.execution.pipeline.simulation import SimulationResult
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.parallel_executor import (
    _create_default_simulation_executor,
    parallel_execute,
    sequential_execute,
)
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan, materialize_research_plan

# ---------------------------------------------------------------------------
# Asset classes matching the dataset loader convention
# ---------------------------------------------------------------------------

EQUITY = AssetClass(id="equity", name="", description="")
BOND = AssetClass(id="bond", name="", description="")


# ---------------------------------------------------------------------------
# Dataset construction
# ---------------------------------------------------------------------------

def _make_dataset(
    n_months: int = 600,
    start_year: int = 1970,
    equity_prices: Sequence[Decimal] | None = None,
    bond_prices: Sequence[Decimal] | None = None,
) -> Dataset:
    """Create a multi-year dataset with varying equity and bond prices.

    Default: 50 years of monthly data (600 months) starting Jan 1970.
    Prices are synthetic but realistic enough to exercise debt mechanics.
    """
    from fbf.core.domain.model.market_snapshot import MarketSnapshot

    snapshots = []
    for i in range(n_months):
        m = i + 1
        year = start_year + (m - 1) // 12
        month = ((m - 1) % 12) + 1

        if equity_prices is not None:
            ep = equity_prices[i]
        else:
            # Synthetic: equity drifts upward with some volatility
            ep = Decimal("100") + Decimal(str(i * 0.5))

        bp = (
            bond_prices[i]
            if bond_prices is not None
            else Decimal("50") + Decimal(str(i * 0.1))
        )

        snapshots.append(
            MarketSnapshot(
                date=date(year, month, 1),
                index_levels={EQUITY: ep, BOND: bp},
                inflation=Decimal("0.002"),
                inflation_cumulative=Decimal(str(round(i * 0.002, 6))),
                is_ath=(i == 0),
                is_underwater=False,
                running_ath=ep,
            )
        )
    return Dataset(snapshots=snapshots, frequency="monthly", version="C3_v1")


# ---------------------------------------------------------------------------
# Experiment definition
# ---------------------------------------------------------------------------

INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)
HORIZON_YEARS = 30
HORIZON_MONTHS = HORIZON_YEARS * 12 + 1  # 361

# Part 49 debt parameters (ERN configuration)
INTEREST_RATE = Decimal("0.015")
LTV_LIMIT = Decimal("0.75")
LOAN_DRAW_RATE = Decimal("0.01")
WITHDRAWAL_RATE = Decimal("0.03")
EQUITY_ALLOCATION = Decimal("0.75")

NUM_COHORTS = 12


def _build_experiment(
    dataset: Dataset,
    n_cohorts: int = NUM_COHORTS,
) -> tuple[ExperimentDefinition, tuple[CohortSpecification, ...]]:
    """Build an ExperimentDefinition with n_cohorts rolling cohorts."""
    # Generate rolling monthly cohorts
    cohorts: list[CohortSpecification] = []
    for i in range(n_cohorts):
        m = i + 1
        year = 1970 + (m - 1) // 12
        month = ((m - 1) % 12) + 1
        cohorts.append(CohortSpecification(start_date=date(year, month, 1)))

    exp_def = ExperimentDefinition(
        name="c3-multi-cohort-validation",
        description="C3 multi-cohort validation with Part 49 debt",
        dataset=dataset,
        horizon_months=HORIZON_MONTHS,
        initial_wealth=INITIAL_WEALTH,
        cohorts=tuple(cohorts),
        allocation_policies=(ConstantAllocationPolicy(equity_allocation=EQUITY_ALLOCATION),),
        withdrawal_policies=(Part49WithdrawalPolicy(withdrawal_rate=WITHDRAWAL_RATE),),
    )
    return exp_def, tuple(cohorts)


def _build_plan(
    dataset: Dataset,
    cohorts: tuple[CohortSpecification, ...],
    exp_def: ExperimentDefinition,
    param_configs: tuple[ParameterConfiguration, ...] | None = None,
) -> ResearchPlan:
    """Build a ResearchPlan via the production materialize_research_plan path."""
    if param_configs is None:
        param_configs = (ParameterConfiguration(
            {"withdrawal_rate": 0.03, "horizon_years": 30}
        ),)

    from fbf.core.domain.model.portfolio import AssetHolding, Portfolio

    # Placeholder portfolio — materialize_research_plan builds per-cohort portfolios
    placeholder_portfolio = Portfolio(
        holdings=(
            AssetHolding(asset_class=EQUITY, units=Decimal("1")),
            AssetHolding(asset_class=BOND, units=Decimal("1")),
        )
    )

    return materialize_research_plan(
        experiment_def=exp_def,
        canonical_trajectory=dataset,
        cohorts=cohorts,
        param_configs=param_configs,
        initial_portfolio=placeholder_portfolio,
        horizon_resolver=lambda pc: HORIZON_MONTHS,
        policy_resolver=lambda pc: (
            ConstantAllocationPolicy(equity_allocation=EQUITY_ALLOCATION),
            Part49WithdrawalPolicy(withdrawal_rate=WITHDRAWAL_RATE),
        ),
        interest_rate=INTEREST_RATE,
        ltv_limit=LTV_LIMIT,
        ltv_enforcement=False,  # ERN Part 49: observe, don't enforce
        loan_draw_rate=LOAN_DRAW_RATE,
    )


def _execute_plan(plan: ResearchPlan) -> list[tuple[PlannedSimulationUnit, SimulationResult]]:
    """Execute a plan through the real production pipeline and return results."""
    executor = ResearchExecutor(
        simulation_executor=_create_default_simulation_executor()
    )
    result = executor.execute(plan)
    return list(zip(plan.units, result.results, strict=True))


# ---------------------------------------------------------------------------
# Test 1: Multi-cohort initialization — initial portfolio invariant
# ---------------------------------------------------------------------------


class TestInitialPortfolioInvariant:
    """Verify portfolio_value_at_snapshot[0] == initial_wealth for every cohort."""

    def test_initial_portfolio_value_equals_initial_wealth(self) -> None:
        dataset = _make_dataset()
        exp_def, cohorts = _build_experiment(dataset, n_cohorts=NUM_COHORTS)

        plan = _build_plan(dataset, cohorts, exp_def)

        assert len(plan.units) == NUM_COHORTS

        for unit in plan.units:
            # Verify per-cohort portfolio was built from the cohort dataset
            assert unit.initial_portfolio is not None
            assert len(unit.initial_portfolio.holdings) == 2  # equity + bond

            # Verify portfolio value at snapshot[0] == initial_wealth
            snapshot0 = unit.dataset[0]
            portfolio_value = sum(
                h.units * snapshot0.index_levels[h.asset_class]
                for h in unit.initial_portfolio.holdings
            )
            assert portfolio_value == INITIAL_WEALTH.amount, (
                f"Cohort {unit.cohort.start_date}: "
                f"portfolio_value={portfolio_value} != initial_wealth={INITIAL_WEALTH.amount}"
            )

    def test_cohort_datasets_are_sliced_correctly(self) -> None:
        """Each cohort's dataset starts at its start_date."""
        dataset = _make_dataset()
        exp_def, cohorts = _build_experiment(dataset, n_cohorts=NUM_COHORTS)

        plan = _build_plan(dataset, cohorts, exp_def)

        for unit in plan.units:
            assert unit.dataset[0].date == unit.cohort.start_date, (
                f"Cohort {unit.cohort.start_date}: "
                f"dataset starts at {unit.dataset[0].date}"
            )
            assert len(unit.dataset) == HORIZON_MONTHS, (
                f"Cohort {unit.cohort.start_date}: "
                f"dataset length={len(unit.dataset)} != {HORIZON_MONTHS}"
            )


# ---------------------------------------------------------------------------
# Test 2: Sequential cohort isolation
# ---------------------------------------------------------------------------


class TestSequentialCohortIsolation:
    """Run cohorts sequentially and verify independent results."""

    def test_sequential_execution_produces_independent_results(self) -> None:
        dataset = _make_dataset()
        exp_def, cohorts = _build_experiment(dataset, n_cohorts=NUM_COHORTS)

        plan = _build_plan(dataset, cohorts, exp_def)
        pairs = _execute_plan(plan)

        assert len(pairs) == NUM_COHORTS

        for unit, result in pairs:
            # Every cohort must complete successfully
            assert result.statistics.success is True, (
                f"Cohort {unit.cohort.start_date}: failed "
                f"(failure_month={result.statistics.failure_month})"
            )
            # Must have simulated the full horizon
            assert result.statistics.months_simulated == HORIZON_MONTHS, (
                f"Cohort {unit.cohort.start_date}: "
                f"months_simulated={result.statistics.months_simulated}"
            )

    def test_debt_snapshots_present_for_all_cohorts(self) -> None:
        """When debt is configured, every cohort must produce debt snapshots."""
        dataset = _make_dataset()
        exp_def, cohorts = _build_experiment(dataset, n_cohorts=NUM_COHORTS)

        plan = _build_plan(dataset, cohorts, exp_def)
        pairs = _execute_plan(plan)

        for unit, result in pairs:
            debt_snapshots = [
                mr.debt_snapshot
                for mr in result.timeline.monthly_results
                if mr.debt_snapshot is not None
            ]
            assert len(debt_snapshots) > 0, (
                f"Cohort {unit.cohort.start_date}: no debt snapshots"
            )
            # Loan balance must grow over time (interest accrual + draws)
            assert debt_snapshots[-1].loan_balance > debt_snapshots[0].loan_balance, (
                f"Cohort {unit.cohort.start_date}: loan_balance did not grow"
            )


# ---------------------------------------------------------------------------
# Test 3: Isolated vs batched equivalence
# ---------------------------------------------------------------------------


class TestIsolatedVsBatchedEquivalence:
    """Run(cohort alone) == run(cohort as part of multi-cohort execution)."""

    @pytest.mark.parametrize("cohort_idx", range(NUM_COHORTS))
    def test_single_cohort_matches_batch_result(self, cohort_idx: int) -> None:
        dataset = _make_dataset()
        exp_def, all_cohorts = _build_experiment(dataset, n_cohorts=NUM_COHORTS)

        param_config = ParameterConfiguration(
            {"withdrawal_rate": 0.03, "horizon_years": 30}
        )

        # --- Isolated execution: single cohort ---
        single_cohort = (all_cohorts[cohort_idx],)
        isolated_plan = _build_plan(
            dataset, single_cohort, exp_def, param_configs=(param_config,)
        )
        isolated_pairs = _execute_plan(isolated_plan)
        assert len(isolated_pairs) == 1
        isolated_result = isolated_pairs[0][1]

        # --- Batched execution: all cohorts ---
        batched_plan = _build_plan(
            dataset, all_cohorts, exp_def, param_configs=(param_config,)
        )
        batched_pairs = _execute_plan(batched_plan)
        assert len(batched_pairs) == NUM_COHORTS
        batched_result = batched_pairs[cohort_idx][1]

        # Compare statistics
        assert isolated_result.statistics.success == batched_result.statistics.success
        assert isolated_result.statistics.failure_month == batched_result.statistics.failure_month
        assert isolated_result.statistics.months_simulated == (
            batched_result.statistics.months_simulated
        )
        assert isolated_result.statistics.final_wealth == batched_result.statistics.final_wealth

        # Compare monthly debt snapshots
        iso_debts = [
            mr.debt_snapshot
            for mr in isolated_result.timeline.monthly_results
            if mr.debt_snapshot is not None
        ]
        bat_debts = [
            mr.debt_snapshot
            for mr in batched_result.timeline.monthly_results
            if mr.debt_snapshot is not None
        ]
        assert len(iso_debts) == len(bat_debts)
        for i, (iso_d, bat_d) in enumerate(zip(iso_debts, bat_debts, strict=True)):
            assert iso_d.loan_balance == bat_d.loan_balance, (
                f"Cohort {cohort_idx}, month {i}: "
                f"isolated loan={iso_d.loan_balance} != batched loan={bat_d.loan_balance}"
            )
            assert iso_d.ltv == bat_d.ltv, (
                f"Cohort {cohort_idx}, month {i}: "
                f"isolated ltv={iso_d.ltv} != batched ltv={bat_d.ltv}"
            )


# ---------------------------------------------------------------------------
# Test 4: Execution-order independence
# ---------------------------------------------------------------------------


class TestExecutionOrderIndependence:
    """A,B,C,...,J must produce the same per-cohort results as J,I,H,...,A."""

    def test_reversed_execution_order_matches(self) -> None:
        dataset = _make_dataset()
        exp_def, all_cohorts = _build_experiment(dataset, n_cohorts=10)

        param_config = ParameterConfiguration(
            {"withdrawal_rate": 0.03, "horizon_years": 30}
        )

        # Forward order
        forward_plan = _build_plan(
            dataset, all_cohorts, exp_def, param_configs=(param_config,)
        )
        forward_pairs = _execute_plan(forward_plan)

        # Reverse order
        reversed_cohorts = tuple(reversed(all_cohorts))
        reverse_plan = _build_plan(
            dataset, reversed_cohorts, exp_def, param_configs=(param_config,)
        )
        reverse_pairs = _execute_plan(reverse_plan)

        # Build lookup by cohort start_date for forward results
        forward_by_date = {
            unit.cohort.start_date: result
            for unit, result in forward_pairs
        }

        # Compare every cohort's results
        for unit, result in reverse_pairs:
            start_date = unit.cohort.start_date
            fwd = forward_by_date[start_date]
            assert fwd.statistics.success == result.statistics.success, (
                f"Cohort {start_date}: success diverged by order"
            )
            assert fwd.statistics.failure_month == result.statistics.failure_month, (
                f"Cohort {start_date}: failure_month diverged by order"
            )
            assert fwd.statistics.final_wealth == result.statistics.final_wealth, (
                f"Cohort {start_date}: final_wealth diverged by order"
            )

            # Compare debt snapshots
            fwd_debts = [
                mr.debt_snapshot
                for mr in fwd.timeline.monthly_results
                if mr.debt_snapshot is not None
            ]
            rev_debts = [
                mr.debt_snapshot
                for mr in result.timeline.monthly_results
                if mr.debt_snapshot is not None
            ]
            assert len(fwd_debts) == len(rev_debts)
            for i, (fd, rd) in enumerate(zip(fwd_debts, rev_debts, strict=True)):
                assert fd.loan_balance == rd.loan_balance, (
                    f"Cohort {start_date}, month {i}: "
                    f"loan_balance diverged by order"
                )


# ---------------------------------------------------------------------------
# Test 5: State isolation — no mutable debt/portfolio state shared
# ---------------------------------------------------------------------------


class TestStateIsolation:
    """Verify no mutable debt/portfolio state crosses cohort boundaries."""

    def test_per_cohort_portfolios_are_distinct_objects(self) -> None:
        """Each cohort gets its own Portfolio instance (not shared reference)."""
        dataset = _make_dataset()
        exp_def, cohorts = _build_experiment(dataset, n_cohorts=NUM_COHORTS)

        plan = _build_plan(dataset, cohorts, exp_def)

        portfolios = [unit.initial_portfolio for unit in plan.units]
        # All portfolios must be distinct objects
        for i, p1 in enumerate(portfolios):
            for j, p2 in enumerate(portfolios):
                if i != j:
                    assert p1 is not p2, (
                        f"Portfolios for cohorts {i} and {j} are the same object"
                    )

    def test_per_cohort_datasets_are_distinct_objects(self) -> None:
        """Each cohort gets its own Dataset instance (not shared reference)."""
        dataset = _make_dataset()
        exp_def, cohorts = _build_experiment(dataset, n_cohorts=NUM_COHORTS)

        plan = _build_plan(dataset, cohorts, exp_def)

        datasets = [unit.dataset for unit in plan.units]
        for i, d1 in enumerate(datasets):
            for j, d2 in enumerate(datasets):
                if i != j:
                    assert d1 is not d2, (
                        f"Datasets for cohorts {i} and {j} are the same object"
                    )

    def test_simulation_states_are_distinct_during_execution(self) -> None:
        """Verify that execution creates independent SimulationState per cohort."""
        dataset = _make_dataset()
        exp_def, cohorts = _build_experiment(dataset, n_cohorts=4)

        plan = _build_plan(dataset, cohorts, exp_def)

        # Track SimulationState ids through execution
        state_ids: list[int] = []

        from fbf.core.execution.pipeline.runner import SimulationRunner

        original_run = SimulationRunner.run

        def tracking_run(
            self: SimulationRunner, context: SimulationContext
        ) -> SimulationResult:
            result = original_run(self, context)
            state_ids.append(id(result))
            return result

        SimulationRunner.run = tracking_run  # type: ignore[method-assign]
        try:
            _execute_plan(plan)
        finally:
            SimulationRunner.run = original_run  # type: ignore[method-assign]

        # All result states must be distinct objects
        assert len(state_ids) == len(plan.units)
        assert len(set(state_ids)) == len(state_ids), (
            "Multiple cohorts produced the same SimulationState object"
        )


# ---------------------------------------------------------------------------
# Test 6: Dataset immutability
# ---------------------------------------------------------------------------


class TestDatasetImmutability:
    """Verify cohort materialization does not mutate the source dataset."""

    def test_source_dataset_unchanged_after_materialization(self) -> None:
        dataset = _make_dataset()
        exp_def, cohorts = _build_experiment(dataset, n_cohorts=NUM_COHORTS)

        # Snapshot the source dataset before materialization
        original_snapshots = tuple(dataset.snapshots)
        original_len = len(dataset)
        original_start = dataset.start_date
        original_end = dataset.end_date

        _build_plan(dataset, cohorts, exp_def)

        # Verify source dataset is unchanged
        assert len(dataset) == original_len
        assert dataset.start_date == original_start
        assert dataset.end_date == original_end
        assert tuple(dataset.snapshots) == original_snapshots

    def test_cohort_datasets_are_frozen_dataclasses(self) -> None:
        """Sliced datasets are frozen (immutable) Dataclass instances."""
        dataset = _make_dataset()
        exp_def, cohorts = _build_experiment(dataset, n_cohorts=NUM_COHORTS)

        plan = _build_plan(dataset, cohorts, exp_def)

        # Dataset is a frozen dataclass — attribute assignment raises
        for unit in plan.units:
            with pytest.raises(AttributeError):
                unit.dataset.frequency = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Test 7: Determinism across param configs
# ---------------------------------------------------------------------------


class TestDeterminismAcrossConfigs:
    """Each cohort's result is deterministic regardless of other cohorts' configs."""

    def test_deterministic_results_with_multiple_param_configs(self) -> None:
        dataset = _make_dataset()
        exp_def, cohorts = _build_experiment(dataset, n_cohorts=5)

        param_configs = (
            ParameterConfiguration({"withdrawal_rate": 0.03, "horizon_years": 30}),
            ParameterConfiguration({"withdrawal_rate": 0.04, "horizon_years": 30}),
        )

        plan = _build_plan(dataset, cohorts, exp_def, param_configs=param_configs)

        # 5 cohorts x 2 param_configs = 10 units
        assert len(plan.units) == 10

        # Execute twice and compare
        pairs1 = _execute_plan(plan)
        pairs2 = _execute_plan(plan)

        assert len(pairs1) == len(pairs2)
        for (u1, r1), (u2, r2) in zip(pairs1, pairs2, strict=True):
            assert u1.cohort.start_date == u2.cohort.start_date
            assert r1.statistics.success == r2.statistics.success
            assert r1.statistics.final_wealth == r2.statistics.final_wealth
            assert r1.statistics.months_simulated == r2.statistics.months_simulated


# ---------------------------------------------------------------------------
# Test 8: Per-cohort initial wealth invariant (exhaustive)
# ---------------------------------------------------------------------------


class TestExhaustiveInitialWealthInvariant:
    """For EVERY selected cohort, verify portfolio_value_at_snapshot[0] == initial_wealth."""

    @pytest.mark.parametrize("cohort_idx", range(NUM_COHORTS))
    def test_initial_portfolio_value(self, cohort_idx: int) -> None:
        dataset = _make_dataset()
        exp_def, cohorts = _build_experiment(dataset, n_cohorts=NUM_COHORTS)

        plan = _build_plan(dataset, cohorts, exp_def)
        unit = plan.units[cohort_idx]

        snapshot0 = unit.dataset[0]
        portfolio_value = sum(
            h.units * snapshot0.index_levels[h.asset_class]
            for h in unit.initial_portfolio.holdings
        )
        assert portfolio_value == INITIAL_WEALTH.amount, (
            f"Cohort {unit.cohort.start_date} (idx={cohort_idx}): "
            f"portfolio_value={portfolio_value} != initial_wealth={INITIAL_WEALTH.amount}"
        )


# ---------------------------------------------------------------------------
# Test 9: Sequential vs parallel execution equivalence
# ---------------------------------------------------------------------------


class TestSequentialVsParallelEquivalence:
    """sequential_execute and parallel_execute produce identical results."""

    def test_parallel_matches_sequential(self) -> None:
        dataset = _make_dataset()
        exp_def, cohorts = _build_experiment(dataset, n_cohorts=6)

        plan = _build_plan(dataset, cohorts, exp_def)

        seq_result = sequential_execute(plan)
        par_result = parallel_execute(plan, max_workers=2)

        assert len(seq_result.results) == len(par_result.results)
        for i, (seq, par) in enumerate(zip(seq_result.results, par_result.results, strict=True)):
            assert seq.statistics.success == par.statistics.success, (
                f"Unit {i}: success diverged"
            )
            assert seq.statistics.failure_month == par.statistics.failure_month, (
                f"Unit {i}: failure_month diverged"
            )
            assert seq.statistics.months_simulated == par.statistics.months_simulated, (
                f"Unit {i}: months_simulated diverged"
            )
            assert seq.statistics.final_wealth == par.statistics.final_wealth, (
                f"Unit {i}: final_wealth diverged"
            )


# ---------------------------------------------------------------------------
# Test 10: Cohort results differ (independence proof)
# ---------------------------------------------------------------------------


class TestCohortsProduceDifferentResults:
    """Different cohorts must produce different results (proof of independence)."""

    def test_cohorts_have_distinct_final_wealth(self) -> None:
        """At least some cohorts should differ in final wealth."""
        dataset = _make_dataset()
        exp_def, cohorts = _build_experiment(dataset, n_cohorts=10)

        plan = _build_plan(dataset, cohorts, exp_def)
        pairs = _execute_plan(plan)

        final_wealths = [
            result.statistics.final_wealth
            for _, result in pairs
        ]

        # With different starting dates and market data, at least some
        # cohorts should produce different final wealth values
        unique_wealths = set(final_wealths)
        assert len(unique_wealths) > 1, (
            f"All {len(final_wealths)} cohorts produced identical final_wealth; "
            "expected variation across cohorts"
        )
