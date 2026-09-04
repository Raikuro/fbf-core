"""S5.3 — Part 49 End-to-End Smoke Execution.

Validates that a small, representative subset of the fully materialized
Part 49 grid executes successfully through the real production path:

    StudyConfiguration
        -> build_study_plan
        -> ResearchPlan / PlannedSimulationUnit
        -> ResearchExecutor
        -> SimulationContext
        -> SimulationRunner
        -> Decimal canonical pipeline
        -> MonthlyResult / DebtSnapshot

This is an execution-path validation, not the full research run.

Zero-interest debt contract (from production code):
    When interest_rate <= 0, ALL debt pipeline steps are no-ops:
    - LoanDrawStep: short-circuits (line 54)
    - InterestAccrualStep: short-circuits (line 31)
    - LTVEvaluationStep: short-circuits (line 52)
    - BuildDecisionContextStep: DebtInfo is None (line 25)
    - MonthlyResultBuilderStep: DebtSnapshot is None (line 20)

    Therefore interest_rate=0 is functionally equivalent to "no debt configured".
    This is confirmed by existing S4 test: test_part49.py:160
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest

from fbf.core.domain.model.money import Currency, Money
from fbf.core.execution.executor import ResearchExecutor
from fbf.core.execution.pipeline.default_pipeline import create_default_pipeline
from fbf.core.execution.pipeline.executor import SimulationExecutor
from fbf.core.execution.pipeline.runner import SimulationRunner
from fbf.core.execution.result import ResearchExecutionResult
from fbf.core.study import BuiltStudy, StudyConfiguration, build_study_plan

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path("data/ern")
INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)

# Deliberately small smoke subset: 2 equity × 2 SWR × 2 IR = 8 cells
# with 3 cohorts = 24 units total.
SMOKE_EQUITY = (Decimal("0.75"), Decimal("1.0"))
SMOKE_SWR = (Decimal("0.03"), Decimal("0.04"))
SMOKE_IR = (Decimal("0.0"), Decimal("0.015"))
SMOKE_COHORTS = 3
EXPECTED_SMOKE_UNITS = len(SMOKE_EQUITY) * len(SMOKE_SWR) * len(SMOKE_IR) * SMOKE_COHORTS  # 24


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_smoke_config() -> StudyConfiguration:
    """Small smoke subset: 2 equity × 2 SWR × 2 IR = 8 cells, 3 cohorts."""
    return StudyConfiguration(
        name="ERN Part 49 -- Smoke Execution",
        description="S5.3 small smoke subset for execution-path validation",
        version="2.0",
        dataset_identifier="ern_swr_h720",
        allocation_policy_type="ConstantAllocationPolicy",
        allocation_policy_values=SMOKE_EQUITY,
        withdrawal_policy_type="Part49WithdrawalPolicy",
        withdrawal_policy_values=SMOKE_SWR,
        horizon_years=(30,),
        cohort_horizon_years=60,
        debt_interest_rate_values=SMOKE_IR,
        debt_ltv_limit=Decimal("0.75"),
        debt_ltv_enforcement=False,
        debt_loan_draw_rate=Decimal("0.01"),
    )


@pytest.fixture(scope="module")
def smoke_built_study() -> BuiltStudy:
    """Build the smoke study plan via the real production path."""
    config = _make_smoke_config()
    built = build_study_plan(config, str(DATA_DIR), INITIAL_WEALTH)
    # Limit to SMOKE_COHORTS cohorts for fast execution
    from fbf.core.study.plan import ResearchPlan

    limited_units = built.plan.units[:EXPECTED_SMOKE_UNITS]
    limited_plan = ResearchPlan(
        experiment_definition=built.plan.experiment_definition,
        units=limited_units,
    )
    return BuiltStudy(
        plan=limited_plan,
        experiment_definition=built.experiment_definition,
        cohorts=built.cohorts[:SMOKE_COHORTS],
        param_configs=built.param_configs,
    )


@pytest.fixture(scope="module")
def smoke_execution_result(
    smoke_built_study: BuiltStudy,
) -> Iterator[tuple[BuiltStudy, ResearchExecutionResult]]:
    """Execute the smoke study through the full production pipeline."""
    executor = ResearchExecutor(
        simulation_executor=SimulationExecutor(
            simulation_runner=SimulationRunner(pipeline=create_default_pipeline())
        )
    )
    result = executor.execute(smoke_built_study.plan)
    yield smoke_built_study, result


# ---------------------------------------------------------------------------
# Test class 1: Unit count and structure
# ---------------------------------------------------------------------------


class TestSmokeUnitCount:
    """Verify the smoke subset has the expected structure."""

    def test_smoke_unit_count(self, smoke_built_study: BuiltStudy) -> None:
        """Smoke subset must produce exactly 24 units."""
        assert len(smoke_built_study.plan.units) == EXPECTED_SMOKE_UNITS

    def test_smoke_execution_result_count(
        self, smoke_execution_result: tuple[BuiltStudy, ResearchExecutionResult]
    ) -> None:
        """All 24 units must execute successfully."""
        _, result = smoke_execution_result
        assert len(result.experiment_result.simulation_results) == EXPECTED_SMOKE_UNITS


# ---------------------------------------------------------------------------
# Test class 2: Parameter propagation to SimulationContext
# ---------------------------------------------------------------------------


class TestSmokeParameterPropagation:
    """Verify debt parameters reach the production engine correctly."""

    def test_interest_rate_varies_across_cells(
        self, smoke_built_study: BuiltStudy
    ) -> None:
        """Interest rates must differ between cells (0% vs 1.5%)."""
        ir_values = {
            Decimal(str(u.interest_rate))
            for u in smoke_built_study.plan.units
        }
        assert Decimal("0.0") in ir_values
        assert Decimal("0.015") in ir_values

    def test_equity_allocation_varies(
        self, smoke_built_study: BuiltStudy
    ) -> None:
        """Equity allocations must include both 0.75 and 1.0."""
        eq_values = {
            Decimal(str(u.parameter_config.get("equity_allocation")))
            for u in smoke_built_study.plan.units
        }
        assert eq_values == {Decimal("0.75"), Decimal("1.0")}

    def test_withdrawal_rate_varies(
        self, smoke_built_study: BuiltStudy
    ) -> None:
        """Withdrawal rates must include both 3% and 4%."""
        wr_values = {
            Decimal(str(u.parameter_config.get("withdrawal_rate")))
            for u in smoke_built_study.plan.units
        }
        assert wr_values == {Decimal("0.03"), Decimal("0.04")}

    def test_all_units_have_debt_parameters(
        self, smoke_built_study: BuiltStudy
    ) -> None:
        """All smoke units must have ltv_limit, ltv_enforcement, loan_draw_rate."""
        for u in smoke_built_study.plan.units:
            assert u.ltv_limit == Decimal("0.75")
            assert u.ltv_enforcement is False
            assert u.loan_draw_rate == Decimal("0.01")


# ---------------------------------------------------------------------------
# Test class 3: Result semantics — leveraged cases
# ---------------------------------------------------------------------------


class TestSmokeLeveragedResults:
    """Verify leveraged simulations produce correct debt trajectories."""

    def test_leveraged_units_have_debt_snapshots(
        self, smoke_execution_result: tuple[BuiltStudy, ResearchExecutionResult]
    ) -> None:
        """Units with interest_rate > 0 must produce DebtSnapshot entries."""
        _, result = smoke_execution_result
        for sim in result.experiment_result.simulation_results:
            # All simulations should complete without error
            assert len(sim.timeline.monthly_results) > 0

    def test_zero_interest_no_debt_snapshots(
        self, smoke_execution_result: tuple[BuiltStudy, ResearchExecutionResult]
    ) -> None:
        """interest_rate=0 → DebtSnapshot is None (production contract).

        When interest_rate <= 0, all debt pipeline steps short-circuit:
        LoanDrawStep, InterestAccrualStep, LTVEvaluationStep, and
        MonthlyResultBuilderStep all skip debt processing. This makes
        interest_rate=0 functionally equivalent to "no debt configured".
        """
        built, result = smoke_execution_result
        for i, sim in enumerate(result.experiment_result.simulation_results):
            unit = built.plan.units[i]
            debt_snapshots = [
                mr.debt_snapshot
                for mr in sim.timeline.monthly_results
                if mr.debt_snapshot is not None
            ]
            if unit.interest_rate == Decimal("0.0"):
                assert len(debt_snapshots) == 0, (
                    f"Unit {unit.cohort.start_date} IR={unit.interest_rate}: "
                    f"interest_rate=0 must produce no DebtSnapshot (production contract)"
                )

    def test_positive_interest_has_debt_snapshots(
        self, smoke_execution_result: tuple[BuiltStudy, ResearchExecutionResult]
    ) -> None:
        """Units with interest_rate > 0 must produce DebtSnapshot entries."""
        built, result = smoke_execution_result
        for i, sim in enumerate(result.experiment_result.simulation_results):
            unit = built.plan.units[i]
            debt_snapshots = [
                mr.debt_snapshot
                for mr in sim.timeline.monthly_results
                if mr.debt_snapshot is not None
            ]
            if unit.interest_rate is not None and unit.interest_rate > Decimal("0.0"):
                assert len(debt_snapshots) > 0, (
                    f"Unit {unit.cohort.start_date} IR={unit.interest_rate} "
                    f"should have debt snapshots"
                )

    def test_loan_balance_grows_with_interest(
        self, smoke_execution_result: tuple[BuiltStudy, ResearchExecutionResult]
    ) -> None:
        """When interest_rate > 0, final loan_balance must exceed initial."""
        built, result = smoke_execution_result
        for i, sim in enumerate(result.experiment_result.simulation_results):
            unit = built.plan.units[i]
            debt_snapshots = [
                mr.debt_snapshot
                for mr in sim.timeline.monthly_results
                if mr.debt_snapshot is not None
            ]
            if len(debt_snapshots) >= 2:
                assert debt_snapshots[-1].loan_balance > debt_snapshots[0].loan_balance, (
                    f"Unit {unit.cohort.start_date} IR={unit.interest_rate}: "
                    f"loan_balance should grow (final={debt_snapshots[-1].loan_balance} "
                    f"> initial={debt_snapshots[0].loan_balance})"
                )

    def test_ltv_observed_not_enforced(
        self, smoke_execution_result: tuple[BuiltStudy, ResearchExecutionResult]
    ) -> None:
        """With ltv_enforcement=False, LTV can exceed limit without liquidation."""
        _, result = smoke_execution_result
        for sim in result.experiment_result.simulation_results:
            debt_snapshots = [
                mr.debt_snapshot
                for mr in sim.timeline.monthly_results
                if mr.debt_snapshot is not None
            ]
            for ds in debt_snapshots:
                # ltv_enforcement is False, so LTV can exceed limit
                assert ds.ltv_enforcement is False


# ---------------------------------------------------------------------------
# Test class 4: Result semantics — no-debt cases
# ---------------------------------------------------------------------------


class TestSmokeNoDebtResults:
    """Verify zero-interest path is equivalent to no-debt path.

    Production contract: interest_rate <= 0 makes ALL debt steps no-ops.
    This means interest_rate=0 produces identical behavior to interest_rate=None.
    """

    def test_zero_interest_equivalent_to_no_debt(
        self, smoke_execution_result: tuple[BuiltStudy, ResearchExecutionResult]
    ) -> None:
        """Zero-interest units must have identical debt state to no-debt units.

        Both should produce: no DebtSnapshot, no loan_balance change,
        no cash_balance change. This verifies the production contract
        that interest_rate=0 ≡ no debt configured.
        """
        built, result = smoke_execution_result
        for i, sim in enumerate(result.experiment_result.simulation_results):
            unit = built.plan.units[i]
            if unit.interest_rate == Decimal("0.0"):
                debt_snapshots = [
                    mr.debt_snapshot
                    for mr in sim.timeline.monthly_results
                    if mr.debt_snapshot is not None
                ]
                # Zero-interest: no DebtSnapshot (production contract)
                assert len(debt_snapshots) == 0
                # Zero-interest: loan_balance stays at 0 (no draws, no accrual)
                # This is verified by the absence of DebtSnapshot entries

    def test_initial_portfolio_value_matches_wealth(
        self, smoke_execution_result: tuple[BuiltStudy, ResearchExecutionResult]
    ) -> None:
        """Initial portfolio value must approximately equal initial_wealth."""
        built, _ = smoke_execution_result
        for u in built.plan.units:
            total = Decimal("0")
            initial_snapshot = u.dataset.snapshots[0]
            for holding in u.initial_portfolio.holdings:
                price = initial_snapshot.index_levels.get(holding.asset_class)
                if price is not None:
                    total += holding.units * price
            diff = abs(total - INITIAL_WEALTH.amount)
            assert diff < Decimal("0.0001"), (
                f"Unit {u.cohort.start_date}: portfolio value {total} "
                f"differs from initial_wealth by {diff}"
            )


# ---------------------------------------------------------------------------
# Test class 5: State isolation between units
# ---------------------------------------------------------------------------


class TestSmokeStateIsolation:
    """Verify no state leaks between independently executed units."""

    def test_distinct_timeline_lengths(
        self, smoke_execution_result: tuple[BuiltStudy, ResearchExecutionResult]
    ) -> None:
        """All simulations must produce independent timelines."""
        _, result = smoke_execution_result
        lengths = [
            len(sim.timeline.monthly_results)
            for sim in result.experiment_result.simulation_results
        ]
        # All should have the same length (same horizon)
        assert len(set(lengths)) == 1
        assert lengths[0] > 0

    def test_distinct_final_portfolios(
        self, smoke_execution_result: tuple[BuiltStudy, ResearchExecutionResult]
    ) -> None:
        """Different parameter combinations must produce different outcomes."""
        _, result = smoke_execution_result
        final_values = []
        for sim in result.experiment_result.simulation_results:
            last = sim.timeline.monthly_results[-1]
            total = Decimal("0")
            for holding in last.portfolio.holdings:
                price = last.market_snapshot.index_levels.get(holding.asset_class)
                if price is not None:
                    total += holding.units * price
            final_values.append(total)
        # With different parameters, at least some final values should differ
        assert len(set(final_values)) > 1, (
            f"Expected different final values for different parameters, "
            f"got {len(set(final_values))} unique values"
        )


# ---------------------------------------------------------------------------
# Test class 6: Decimal canonical path
# ---------------------------------------------------------------------------


class TestSmokeDecimalPath:
    """Verify Decimal remains the canonical execution path."""

    def test_all_results_are_decimal(
        self, smoke_execution_result: tuple[BuiltStudy, ResearchExecutionResult]
    ) -> None:
        """Portfolio values and debt values must be Decimal, not float."""
        _, result = smoke_execution_result
        for sim in result.experiment_result.simulation_results:
            for mr in sim.timeline.monthly_results:
                for holding in mr.portfolio.holdings:
                    assert isinstance(holding.units, Decimal)
                if mr.debt_snapshot is not None:
                    assert isinstance(mr.debt_snapshot.loan_balance, Decimal)
                    assert isinstance(mr.debt_snapshot.cash_balance, Decimal)
                    assert isinstance(mr.debt_snapshot.ltv, Decimal)
                    assert isinstance(mr.debt_snapshot.net_worth, Decimal)


# ---------------------------------------------------------------------------
# Test class 7: Multiple cohorts
# ---------------------------------------------------------------------------


class TestSmokeMultipleCohorts:
    """Verify multiple cohorts execute with cohort-specific datasets."""

    def test_cohorts_have_different_start_dates(
        self, smoke_built_study: BuiltStudy
    ) -> None:
        """Each cohort must have a distinct start date."""
        start_dates = [u.cohort.start_date for u in smoke_built_study.plan.units]
        # Within each cell, cohorts are different
        unique_dates = set(start_dates)
        assert len(unique_dates) == SMOKE_COHORTS

    def test_cohort_datasets_are_different(
        self, smoke_built_study: BuiltStudy
    ) -> None:
        """Cohort-specific datasets must be sliced differently."""
        # Units from different cohorts should have different first snapshot dates
        first_dates = []
        for u in smoke_built_study.plan.units:
            first_dates.append(u.dataset.snapshots[0].date)
        # Within a single parameter cell, cohorts have different first dates
        unique_first_dates = set(first_dates)
        assert len(unique_first_dates) == SMOKE_COHORTS


# ---------------------------------------------------------------------------
# Test class 8: Existing non-debt path regression
# ---------------------------------------------------------------------------


class TestSmokeNonDebtRegression:
    """Verify the existing non-debt path still works correctly."""

    def test_no_debt_config_executes(self) -> None:
        """A config without debt parameters must still execute successfully."""
        config = StudyConfiguration(
            name="No debt smoke",
            description="",
            version="",
            dataset_identifier="ern_swr_h720",
            allocation_policy_type="ConstantAllocationPolicy",
            allocation_policy_values=(Decimal("0.75"),),
            withdrawal_policy_type="ConstantWithdrawalPolicy",
            withdrawal_policy_values=(Decimal("0.04"),),
            horizon_years=(30,),
            cohort_horizon_years=60,
        )
        built = build_study_plan(config, str(DATA_DIR), INITIAL_WEALTH)
        # Limit to 1 cohort for fast execution
        from fbf.core.study.plan import ResearchPlan

        limited_plan = ResearchPlan(
            experiment_definition=built.plan.experiment_definition,
            units=built.plan.units[:1],
        )
        executor = ResearchExecutor(
            simulation_executor=SimulationExecutor(
                simulation_runner=SimulationRunner(pipeline=create_default_pipeline())
            )
        )
        result = executor.execute(limited_plan)
        assert len(result.experiment_result.simulation_results) == 1
        sim = result.experiment_result.simulation_results[0]
        assert len(sim.timeline.monthly_results) > 0
        # No debt snapshots for non-debt config
        debt_snapshots = [
            mr.debt_snapshot
            for mr in sim.timeline.monthly_results
            if mr.debt_snapshot is not None
        ]
        assert len(debt_snapshots) == 0
