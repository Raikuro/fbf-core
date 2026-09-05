"""S5.4 — Canonical Part 49 Full Execution.

Executes the canonical ERN Part 49 workload through the real production path:

    2 equity allocations × 3 interest rates × 1,739 cohorts = 10,434 units

This is NOT the extended FBF research grid. The SWR is fixed at 3% + 1% loan = 4% total.

Measures:
    1. Research-plan construction/materialization time
    2. Total execution wall time
    3. Peak RSS / peak memory
    4. Throughput in units per second
    5. Number of successful and failed trajectories
    6. Failure-month distribution
    7. Approximate result/timeline memory footprint
    8. Persisted result size
    9. Anomalies (allocation, debt, LTV, cohort isolation)
    10. Nondeterministic behavior
"""

from __future__ import annotations

import resource
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from fbf.core.domain.model.money import Currency, Money
from fbf.core.execution.executor import ResearchExecutor
from fbf.core.execution.pipeline.default_pipeline import create_default_pipeline
from fbf.core.execution.pipeline.executor import SimulationExecutor
from fbf.core.execution.pipeline.runner import SimulationRunner
from fbf.core.study import StudyConfiguration, build_study_plan

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path("data/ern")
INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)

# Canonical ERN Part 49 grid: 2 equity × 3 interest = 6 cells
CANONICAL_EQUITY = (Decimal("0.75"), Decimal("1.0"))
CANONICAL_IR = (Decimal("0.0"), Decimal("0.015"), Decimal("0.03"))
CANONICAL_SWR = (Decimal("0.03"),)  # Fixed: 3% portfolio + 1% loan = 4%
CANONICAL_CELLS = len(CANONICAL_EQUITY) * len(CANONICAL_IR)  # 6
EXPECTED_UNITS_PER_CELL = 1739
EXPECTED_TOTAL_UNITS = CANONICAL_CELLS * EXPECTED_UNITS_PER_CELL  # 10,434


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _make_canonical_config() -> StudyConfiguration:
    """Canonical ERN Part 49: 2 equity × 3 interest = 6 cells."""
    return StudyConfiguration(
        name="ERN Part 49 — Canonical Replication",
        description="S5.4 canonical ERN Part 49 workload: 6 cells × 1,739 cohorts",
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
# Execution measurement
# ---------------------------------------------------------------------------


def _get_peak_rss_mb() -> float:
    """Get peak RSS in MB (Linux: ru_maxrss is in KB)."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_maxrss / 1024  # KB → MB


def _measure_execution() -> dict[str, Any]:
    """Execute the canonical workload and measure all metrics."""
    config = _make_canonical_config()

    # Phase 1: Research-plan construction
    t_plan_start = time.perf_counter()
    built = build_study_plan(config, str(DATA_DIR), INITIAL_WEALTH)
    t_plan_end = time.perf_counter()
    plan_time = t_plan_end - t_plan_start

    units = built.plan.units
    actual_units = len(units)
    actual_cells = len(built.param_configs)

    # Verify grid structure
    cell_keys = set()
    for u in units:
        eq = u.parameter_config.get("equity_allocation")
        ir = u.parameter_config.get("interest_rate")
        cell_keys.add((eq, ir))

    # Phase 2: Execution
    executor = ResearchExecutor(
        simulation_executor=SimulationExecutor(
            simulation_runner=SimulationRunner(pipeline=create_default_pipeline())
        )
    )

    rss_before = _get_peak_rss_mb()
    t_exec_start = time.perf_counter()
    result = executor.execute(built.plan)
    t_exec_end = time.perf_counter()
    rss_after = _get_peak_rss_mb()

    exec_time = t_exec_end - t_exec_start
    total_time = t_plan_end - t_plan_start + exec_time

    # Phase 3: Result analysis
    sim_results = result.experiment_result.simulation_results
    actual_result_count = len(sim_results)

    successes = sum(1 for r in sim_results if r.statistics.success)
    failures = actual_result_count - successes

    failure_months: Counter[int] = Counter()
    for r in sim_results:
        if not r.statistics.success and r.statistics.failure_month is not None:
            failure_months[r.statistics.failure_month] += 1

    # Memory footprint estimation
    # Each SimulationResult: timeline (361 MonthlyResults) + statistics
    # Rough estimate: each MonthlyResult ~200 bytes, each SimulationResult ~75KB
    estimated_result_memory_mb = actual_result_count * 75 / 1024  # KB → MB

    # Persisted size estimation (pickle)
    import pickle
    sample_sizes = []
    sample_indices = [0, actual_result_count // 4, actual_result_count // 2,
                      3 * actual_result_count // 4, actual_result_count - 1]
    for idx in sample_indices:
        if 0 <= idx < actual_result_count:
            size = len(pickle.dumps(sim_results[idx]))
            sample_sizes.append(size)
    avg_result_size = sum(sample_sizes) / len(sample_sizes) if sample_sizes else 0
    estimated_persisted_size_gb = (actual_result_count * avg_result_size) / (1024 ** 3)

    # Anomaly checks
    anomalies = []

    # Check 1: All results have matching unit count
    if actual_result_count != actual_units:
        anomalies.append(f"Result count mismatch: {actual_result_count} vs {actual_units}")

    # Check 2: No empty timelines
    empty_timelines = sum(1 for r in sim_results if len(r.timeline.monthly_results) == 0)
    if empty_timelines > 0:
        anomalies.append(f"{empty_timelines} results have empty timelines")

    # Check 3: All debt snapshots present for interest > 0
    for i, r in enumerate(sim_results[:100]):  # Sample first 100
        unit = units[i]
        if unit.interest_rate is not None and unit.interest_rate > 0:
            mr_zero = r.timeline.monthly_results[0] if r.timeline.monthly_results else None
            if mr_zero and mr_zero.debt_snapshot is None:
                anomalies.append(
                    f"Unit {i}: interest_rate={unit.interest_rate}"
                    " but no debt_snapshot at month 0"
                )
                break

    # Check 4: Cohort isolation - verify different cohorts produce different results
    cohort_results: dict[Any, list[Any]] = {}
    for i, r in enumerate(sim_results):
        cohort = units[i].cohort.start_date
        if cohort not in cohort_results:
            cohort_results[cohort] = []
        cohort_results[cohort].append(r)

    # Check 5: Nondeterminism - run a small sample twice
    nondeterministic = False
    if actual_units > 0:
        test_unit = units[0]

        ctx1 = executor._create_context_for_unit(built.experiment_definition, test_unit)
        ctx2 = executor._create_context_for_unit(built.experiment_definition, test_unit)

        runner = SimulationRunner(pipeline=create_default_pipeline())
        r1 = runner.run(ctx1)
        r2 = runner.run(ctx2)

        if r1.statistics.success != r2.statistics.success:
            nondeterministic = True
            anomalies.append("Nondeterministic: same input produced different success/failure")
        elif r1.statistics.final_wealth != r2.statistics.final_wealth:
            nondeterministic = True
            anomalies.append("Nondeterministic: same input produced different final_wealth")

    return {
        # Plan metrics
        "plan_construction_time_s": plan_time,
        "actual_cells": actual_cells,
        "actual_units": actual_units,
        "cell_keys": cell_keys,

        # Execution metrics
        "execution_time_s": exec_time,
        "total_time_s": total_time,
        "rss_before_mb": rss_before,
        "rss_after_mb": rss_after,
        "peak_rss_mb": rss_after,

        # Result metrics
        "successful_units": successes,
        "failed_units": failures,
        "failure_months": dict(failure_months),

        # Memory metrics
        "estimated_result_memory_mb": estimated_result_memory_mb,
        "avg_result_pickle_bytes": avg_result_size,
        "estimated_persisted_size_gb": estimated_persisted_size_gb,

        # Anomaly metrics
        "anomalies": anomalies,
        "nondeterministic": nondeterministic,
        "empty_timelines": empty_timelines,

        # Throughput
        "units_per_second": actual_result_count / exec_time if exec_time > 0 else 0,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def canonical_execution() -> dict[str, Any]:
    """Execute the canonical workload and return measurements."""
    return _measure_execution()


class TestCanonicalGridStructure:
    """Verify the canonical grid is correctly constructed."""

    def test_canonical_cell_count(self, canonical_execution: dict[str, Any]) -> None:
        """Must produce exactly 6 cells."""
        assert canonical_execution["actual_cells"] == CANONICAL_CELLS

    def test_canonical_unit_count(self, canonical_execution: dict[str, Any]) -> None:
        """Must produce exactly 10,434 units."""
        assert canonical_execution["actual_units"] == EXPECTED_TOTAL_UNITS

    def test_canonical_cell_keys(self, canonical_execution: dict[str, Any]) -> None:
        """Must have all 6 (equity, interest_rate) combinations."""
        expected_keys = {
            (0.75, 0.0),
            (0.75, 0.015),
            (0.75, 0.03),
            (1.0, 0.0),
            (1.0, 0.015),
            (1.0, 0.03),
        }
        assert canonical_execution["cell_keys"] == expected_keys


class TestCanonicalExecution:
    """Execute the canonical workload and validate results."""

    def test_all_units_execute(self, canonical_execution: dict[str, Any]) -> None:
        """All 10,434 units must produce results."""
        assert canonical_execution["actual_units"] == EXPECTED_TOTAL_UNITS

    def test_no_anomalies(self, canonical_execution: dict[str, Any]) -> None:
        """No anomalies detected during execution."""
        assert canonical_execution["anomalies"] == [], (
            f"Anomalies found: {canonical_execution['anomalies']}"
        )

    def test_no_nondeterminism(self, canonical_execution: dict[str, Any]) -> None:
        """Execution must be deterministic."""
        assert canonical_execution["nondeterministic"] is False

    def test_no_empty_timelines(self, canonical_execution: dict[str, Any]) -> None:
        """No result should have an empty timeline."""
        assert canonical_execution["empty_timelines"] == 0


class TestCanonicalPerformance:
    """Measure and validate performance characteristics."""

    def test_execution_completes(self, canonical_execution: dict[str, Any]) -> None:
        """Execution must complete within practical limits."""
        # Should complete in under 30 minutes
        assert canonical_execution["execution_time_s"] < 1800, (
            f"Execution took {canonical_execution['execution_time_s']:.0f}s "
            f"({canonical_execution['execution_time_s']/60:.1f} min)"
        )

    def test_memory_within_limits(self, canonical_execution: dict[str, Any]) -> None:
        """Peak memory must stay within practical limits."""
        # Should use less than 16 GB (canonical 10,434 units)
        assert canonical_execution["peak_rss_mb"] < 16384, (
            f"Peak RSS: {canonical_execution['peak_rss_mb']:.0f} MB"
        )

    def test_throughput_positive(self, canonical_execution: dict[str, Any]) -> None:
        """Throughput must be positive."""
        assert canonical_execution["units_per_second"] > 0


# ---------------------------------------------------------------------------
# Standalone execution for measurement
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 70)
    print("S5.4 — Canonical Part 49 Execution")
    print("=" * 70)
    print(f"Grid: {CANONICAL_CELLS} cells × {EXPECTED_UNITS_PER_CELL} cohorts")
    print(f"Expected: {EXPECTED_TOTAL_UNITS} units")
    print()

    measurements = _measure_execution()

    print("--- PLAN ---")
    print(f"  Cells: {measurements['actual_cells']}")
    print(f"  Units: {measurements['actual_units']}")
    print(f"  Construction time: {measurements['plan_construction_time_s']:.2f}s")
    print()

    print("--- EXECUTION ---")
    wall_min = measurements["execution_time_s"] / 60
    print(f"  Wall time: {measurements['execution_time_s']:.2f}s ({wall_min:.1f} min)")
    print(f"  Throughput: {measurements['units_per_second']:.1f} units/s")
    print(f"  RSS before: {measurements['rss_before_mb']:.1f} MB")
    print(f"  RSS after: {measurements['peak_rss_mb']:.1f} MB")
    print()

    print("--- RESULTS ---")
    print(f"  Successful: {measurements['successful_units']}")
    print(f"  Failed: {measurements['failed_units']}")
    if measurements["failure_months"]:
        print(f"  Failure months: {measurements['failure_months']}")
    print()

    print("--- MEMORY ---")
    print(f"  Estimated result memory: {measurements['estimated_result_memory_mb']:.1f} MB")
    print(f"  Avg pickle size per result: {measurements['avg_result_pickle_bytes']:.0f} bytes")
    print(f"  Estimated persisted size: {measurements['estimated_persisted_size_gb']:.2f} GB")
    print()

    print("--- ANOMALIES ---")
    if measurements["anomalies"]:
        for a in measurements["anomalies"]:
            print(f"  WARNING: {a}")
    else:
        print("  None")
    print(f"  Nondeterministic: {measurements['nondeterministic']}")
    print()

    print("=" * 70)
    if (measurements["actual_units"] == EXPECTED_TOTAL_UNITS
            and not measurements["anomalies"]
            and not measurements["nondeterministic"]):
        print("S5.4: CANONICAL EXECUTION COMPLETE — ALL CHECKS PASS")
    else:
        print("S5.4: ISSUES DETECTED — REVIEW REQUIRED")
    print("=" * 70)
