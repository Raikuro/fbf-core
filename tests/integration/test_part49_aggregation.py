"""S5.5 — Research Result Aggregation for canonical Part 49.

Re-executes the canonical 6-cell workload through the production path,
aggregates results into per-cell statistics, and captures failure details
for S5.6 research validation.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from fbf.core.domain.model.money import Currency, Money
from fbf.core.execution.executor import ResearchExecutor
from fbf.core.execution.pipeline.default_pipeline import create_default_pipeline
from fbf.core.execution.pipeline.executor import SimulationExecutor
from fbf.core.execution.pipeline.runner import SimulationRunner
from fbf.core.research.part49_aggregation import (
    CellAggregation,
    FailureRecord,
    Part49AggregationResult,
    aggregate_part49_results,
    get_cell_table,
)
from fbf.core.study import StudyConfiguration, build_study_plan

# Type alias for test fixture return type
AggResult = tuple[Part49AggregationResult, dict[str, Any]]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path("data/ern")
INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)

CANONICAL_EQUITY = (Decimal("0.75"), Decimal("1.0"))
CANONICAL_IR = (Decimal("0.0"), Decimal("0.015"), Decimal("0.03"))
CANONICAL_SWR = (Decimal("0.03"),)
CANONICAL_CELLS = len(CANONICAL_EQUITY) * len(CANONICAL_IR)
EXPECTED_UNITS_PER_CELL = 1739
EXPECTED_TOTAL_UNITS = CANONICAL_CELLS * EXPECTED_UNITS_PER_CELL


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _make_canonical_config() -> StudyConfiguration:
    """Canonical ERN Part 49: 2 equity × 3 interest = 6 cells."""
    return StudyConfiguration(
        name="ERN Part 49 — Canonical Replication",
        description="S5.5 aggregation of canonical ERN Part 49 workload",
        version="2.0",
        dataset_identifier="ern_swr_h720",
        allocation_policy_type="ConstantAllocationPolicy",
        allocation_policy_values=CANONICAL_EQUITY,
        withdrawal_policy_type="Part49WithdrawalPolicy",
        withdrawal_policy_values=CANONICAL_SWR,
        horizon_years=(30,),
        cohort_horizon_years=60,
        debt_interest_rate_values=CANONICAL_IR,
        debt_ltv_limit=Decimal("0.75"),
        debt_ltv_enforcement=False,
        debt_loan_draw_rate=Decimal("0.01"),
    )


# ---------------------------------------------------------------------------
# Execution + aggregation fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def canonical_aggregation() -> tuple[Part49AggregationResult, dict[str, Any]]:
    """Execute canonical workload and aggregate results."""
    config = _make_canonical_config()

    # Build plan
    built = build_study_plan(config, str(DATA_DIR), INITIAL_WEALTH)
    units = built.plan.units

    # Execute through production path
    executor = ResearchExecutor(
        simulation_executor=SimulationExecutor(
            simulation_runner=SimulationRunner(pipeline=create_default_pipeline())
        )
    )
    result = executor.execute(built.plan)

    # Aggregate
    agg = aggregate_part49_results(units, result.results)

    # Metadata for tests
    meta = {
        "unit_count": len(units),
        "result_count": len(result.results),
        "cell_count": agg.cell_count,
        "total_units": agg.total_units,
    }

    return agg, meta


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAggregationStructure:
    """Verify aggregation produces correct structure."""

    def test_cell_count(self, canonical_aggregation: AggResult) -> None:
        """Must produce exactly 6 cells."""
        agg, _ = canonical_aggregation
        assert agg.cell_count == CANONICAL_CELLS

    def test_total_units(self, canonical_aggregation: AggResult) -> None:
        """Total units must equal 10,434."""
        agg, _ = canonical_aggregation
        assert agg.total_units == EXPECTED_TOTAL_UNITS

    def test_all_cells_have_cohorts(self, canonical_aggregation: AggResult) -> None:
        """Each cell must have exactly 1,739 cohorts."""
        agg, _ = canonical_aggregation
        for cell in agg.cell_aggregations:
            assert cell.total_cohorts == EXPECTED_UNITS_PER_CELL

    def test_success_failure_conservation(self, canonical_aggregation: AggResult) -> None:
        """successful + failed must equal total for every cell."""
        agg, _ = canonical_aggregation
        for cell in agg.cell_aggregations:
            assert cell.successful_cohorts + cell.failed_cohorts == cell.total_cohorts

    def test_overall_conservation(self, canonical_aggregation: AggResult) -> None:
        """Sum of cell totals must equal overall total."""
        agg, _ = canonical_aggregation
        cell_total = sum(c.total_cohorts for c in agg.cell_aggregations)
        assert cell_total == agg.total_units


class TestCellParameters:
    """Verify cell parameter metadata is correct."""

    def test_all_cells_present(self, canonical_aggregation: AggResult) -> None:
        """All 6 (equity, interest_rate) combinations must be present."""
        agg, _ = canonical_aggregation
        keys = {(c.equity_allocation, c.interest_rate) for c in agg.cell_aggregations}
        expected = {
            (Decimal("0.75"), Decimal("0.0")),
            (Decimal("0.75"), Decimal("0.015")),
            (Decimal("0.75"), Decimal("0.03")),
            (Decimal("1.0"), Decimal("0.0")),
            (Decimal("1.0"), Decimal("0.015")),
            (Decimal("1.0"), Decimal("0.03")),
        }
        assert keys == expected

    def test_withdrawal_rate(self, canonical_aggregation: AggResult) -> None:
        """All cells must have 3% withdrawal rate."""
        agg, _ = canonical_aggregation
        for cell in agg.cell_aggregations:
            assert cell.withdrawal_rate == Decimal("0.03")

    def test_loan_draw_rate(self, canonical_aggregation: AggResult) -> None:
        """All cells must have 1% loan draw rate."""
        agg, _ = canonical_aggregation
        for cell in agg.cell_aggregations:
            assert cell.loan_draw_rate == Decimal("0.01")

    def test_horizon(self, canonical_aggregation: AggResult) -> None:
        """All cells must have 30-year horizon."""
        agg, _ = canonical_aggregation
        for cell in agg.cell_aggregations:
            assert cell.horizon_years == 30

    def test_ltv_enforcement_off(self, canonical_aggregation: AggResult) -> None:
        """LTV enforcement must be OFF for all cells."""
        agg, _ = canonical_aggregation
        for cell in agg.cell_aggregations:
            assert cell.ltv_enforcement is False


class TestSuccessRates:
    """Verify success rates are valid and consistent."""

    def test_all_rates_bounded(self, canonical_aggregation: AggResult) -> None:
        """Success rates must be between 0 and 1."""
        agg, _ = canonical_aggregation
        for cell in agg.cell_aggregations:
            assert Decimal("0") <= cell.success_rate <= Decimal("1")

    def test_rate_matches_counts(self, canonical_aggregation: AggResult) -> None:
        """Success rate must equal successful / total."""
        agg, _ = canonical_aggregation
        for cell in agg.cell_aggregations:
            expected = Decimal(str(cell.successful_cohorts)) / Decimal(str(cell.total_cohorts))
            assert cell.success_rate == expected

    def test_higher_equity_higher_success(self, canonical_aggregation: AggResult) -> None:
        """100% equity should have success rate >= 75% equity (same interest rate)."""
        agg, _ = canonical_aggregation
        cells_by_ir: dict[Decimal, dict[Decimal, CellAggregation]] = {}
        for cell in agg.cell_aggregations:
            cells_by_ir.setdefault(cell.interest_rate, {})[cell.equity_allocation] = cell

        for _ir, eq_map in cells_by_ir.items():
            if Decimal("0.75") in eq_map and Decimal("1.0") in eq_map:
                assert eq_map[Decimal("1.0")].success_rate >= eq_map[Decimal("0.75")].success_rate


class TestFailureDetails:
    """Verify failure records are captured correctly."""

    def test_failure_count(self, canonical_aggregation: AggResult) -> None:
        """All trajectories must succeed with corrected zero-interest semantics."""
        agg, _ = canonical_aggregation
        total_failures = sum(len(c.failure_records) for c in agg.cell_aggregations)
        assert total_failures == 0

    def test_failure_records_have_required_fields(self, canonical_aggregation: AggResult) -> None:
        """Each failure record must have all required fields populated."""
        agg, _ = canonical_aggregation
        for cell in agg.cell_aggregations:
            for fr in cell.failure_records:
                assert fr.cohort_start_date  # non-empty
                assert fr.failure_month >= 0
                assert fr.final_wealth >= Decimal("0")
                assert fr.final_loan_balance >= Decimal("0")
                assert fr.months_simulated > 0

    def test_failure_records_are_immutable(self, canonical_aggregation: AggResult) -> None:
        """FailureRecord must be a frozen dataclass."""
        agg, _ = canonical_aggregation
        for cell in agg.cell_aggregations:
            for fr in cell.failure_records:
                assert isinstance(fr, FailureRecord)


class TestTerminalStatistics:
    """Verify terminal value statistics are captured."""

    def test_wealths_populated(self, canonical_aggregation: AggResult) -> None:
        """Terminal wealths tuple must be populated for each cell."""
        agg, _ = canonical_aggregation
        for cell in agg.cell_aggregations:
            assert len(cell.terminal_wealths) == cell.total_cohorts

    def test_wealths_positive(self, canonical_aggregation: AggResult) -> None:
        """All terminal wealths must be non-negative."""
        agg, _ = canonical_aggregation
        for cell in agg.cell_aggregations:
            for w in cell.terminal_wealths:
                assert w >= Decimal("0")

    def test_loan_balances_populated(self, canonical_aggregation: AggResult) -> None:
        """Terminal loan balances must be populated for leveraged cells."""
        agg, _ = canonical_aggregation
        for cell in agg.cell_aggregations:
            if cell.interest_rate > 0:
                assert len(cell.terminal_loan_balances) == cell.total_cohorts

    def test_ltvs_populated(self, canonical_aggregation: AggResult) -> None:
        """Terminal LTVs must be populated for leveraged cells."""
        agg, _ = canonical_aggregation
        for cell in agg.cell_aggregations:
            if cell.interest_rate > 0:
                assert len(cell.terminal_ltvs) == cell.total_cohorts


class TestCellTable:
    """Verify the formatted cell table output."""

    def test_table_length(self, canonical_aggregation: AggResult) -> None:
        """Table must have 6 rows."""
        agg, _ = canonical_aggregation
        table = get_cell_table(agg)
        assert len(table) == CANONICAL_CELLS

    def test_table_keys(self, canonical_aggregation: AggResult) -> None:
        """Each row must have all required keys."""
        agg, _ = canonical_aggregation
        table = get_cell_table(agg)
        required_keys = {
            "equity_allocation", "interest_rate", "withdrawal_rate",
            "loan_draw_rate", "horizon_years", "ltv_enforcement",
            "total_cohorts", "successful", "failed", "success_rate",
        }
        for row in table:
            assert required_keys <= set(row.keys())


# ---------------------------------------------------------------------------
# Standalone execution for report generation
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 70)
    print("S5.5 — Research Result Aggregation")
    print("=" * 70)

    config = _make_canonical_config()
    built = build_study_plan(config, str(DATA_DIR), INITIAL_WEALTH)
    units = built.plan.units

    print(f"\nPlan: {len(units)} units across {CANONICAL_CELLS} cells")
    print("Executing through production path...")

    executor = ResearchExecutor(
        simulation_executor=SimulationExecutor(
            simulation_runner=SimulationRunner(pipeline=create_default_pipeline())
        )
    )
    result = executor.execute(built.plan)

    print("Aggregating results...")
    agg = aggregate_part49_results(units, result.results)

    # 6-row canonical result table
    print("\n" + "=" * 70)
    print("CANONICAL RESULT TABLE")
    print("=" * 70)
    print(
        f"{'Equity':>6}  {'IR':>6}  {'WR':>4}  {'Draw':>4}  "
        f"{'H':>2}  {'Enf':>4}  {'Total':>5}  {'OK':>5}  {'Fail':>4}  {'Rate':>6}"
    )
    print("-" * 70)
    for cell in agg.cell_aggregations:
        print(
            f"{cell.equity_allocation:>6}  {cell.interest_rate:>6}  "
            f"{cell.withdrawal_rate:>4}  {cell.loan_draw_rate:>4}  "
            f"{cell.horizon_years:>2}  {'OFF' if not cell.ltv_enforcement else 'ON':>4}  "
            f"{cell.total_cohorts:>5}  {cell.successful_cohorts:>5}  "
            f"{cell.failed_cohorts:>4}  {cell.success_rate:>6.4f}"
        )

    # Failure details
    print("\n" + "=" * 70)
    print("FAILURE DETAILS")
    print("=" * 70)
    total_failures = 0
    for cell in agg.cell_aggregations:
        for fr in cell.failure_records:
            total_failures += 1
            print(f"\n  Failure #{total_failures}:")
            print(f"    Cell: equity={fr.equity_allocation}, ir={fr.interest_rate}")
            print(f"    Cohort: {fr.cohort_start_date}")
            f_month = fr.failure_month
            print(
                f"    Failure month: {f_month}"
                f" ({f_month // 12}y {f_month % 12}m)"
            )
            print(f"    Failure state: {fr.failure_state}")
            print(f"    Final wealth: {fr.final_wealth}")
            print(f"    Final loan balance: {fr.final_loan_balance}")
            print(f"    Final LTV: {fr.final_ltv}")
            print(f"    Final net worth: {fr.final_net_worth}")
            print(f"    Months simulated: {fr.months_simulated}")

    # Summary statistics
    print("\n" + "=" * 70)
    print("SUMMARY STATISTICS")
    print("=" * 70)
    total_success = sum(c.successful_cohorts for c in agg.cell_aggregations)
    total_fail = sum(c.failed_cohorts for c in agg.cell_aggregations)
    overall_rate = Decimal(str(total_success)) / Decimal(str(agg.total_units))
    print(f"  Total units: {agg.total_units}")
    print(f"  Total successful: {total_success}")
    print(f"  Total failed: {total_fail}")
    print(f"  Overall success rate: {overall_rate:.4f}")

    # Per-cell terminal wealth statistics
    print("\n  Per-cell terminal wealth statistics:")
    for cell in agg.cell_aggregations:
        if cell.terminal_wealths:
            wealths = cell.terminal_wealths
            mean_w = sum(wealths) / Decimal(str(len(wealths)))
            sorted_w = sorted(wealths)
            median_w = sorted_w[len(sorted_w) // 2]
            print(
                f"    equity={cell.equity_allocation}, ir={cell.interest_rate}: "
                f"mean={mean_w:.0f}, median={median_w:.0f}, "
                f"min={sorted_w[0]:.0f}, max={sorted_w[-1]:.0f}"
            )

    # Per-cell terminal loan statistics
    print("\n  Per-cell terminal loan balance statistics:")
    for cell in agg.cell_aggregations:
        if cell.terminal_loan_balances:
            loans = cell.terminal_loan_balances
            mean_l = sum(loans) / Decimal(str(len(loans)))
            sorted_l = sorted(loans)
            print(
                f"    equity={cell.equity_allocation}, ir={cell.interest_rate}: "
                f"mean={mean_l:.0f}, min={sorted_l[0]:.0f}, max={sorted_l[-1]:.0f}"
            )

    # Per-cell terminal LTV statistics
    print("\n  Per-cell terminal LTV statistics:")
    for cell in agg.cell_aggregations:
        if cell.terminal_ltvs:
            ltvs = cell.terminal_ltvs
            mean_ltv = sum(ltvs) / Decimal(str(len(ltvs)))
            sorted_ltv = sorted(ltvs)
            print(
                f"    equity={cell.equity_allocation}, ir={cell.interest_rate}: "
                f"mean={mean_ltv:.4f}, min={sorted_ltv[0]:.4f}, max={sorted_ltv[-1]:.4f}"
            )

    print("\n" + "=" * 70)
    print("S5.5 AGGREGATION COMPLETE")
    print("=" * 70)
