"""S5.7 — Canonical Part 49 Performance & Scaling Benchmark.

Measures the real performance and resource characteristics of the canonical
Part 49 workload. This is a measurement and validation phase — no optimization.

Usage:
    python tests/benchmarks/s57_performance_benchmark.py
"""

from __future__ import annotations

import gc
import json
import os
import pickle
import platform
import resource
import statistics
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.money import Currency, Money
from fbf.core.execution.executor import ResearchExecutor
from fbf.core.execution.pipeline.default_pipeline import create_default_pipeline
from fbf.core.execution.pipeline.executor import SimulationExecutor
from fbf.core.execution.pipeline.runner import SimulationRunner
from fbf.core.study import StudyConfiguration, build_study_plan
from fbf.core.study.plan import ResearchPlan

EQUITY = AssetClass(id="equity", name="", description="")
BOND = AssetClass(id="bond", name="", description="")

DATA_DIR = Path("data/ern")
INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)


# ---------------------------------------------------------------------------
# System information
# ---------------------------------------------------------------------------


def _system_info() -> dict[str, Any]:
    """Collect system information."""
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
    }


def _get_peak_rss_bytes() -> int:
    """Get peak RSS in bytes (Linux: ru_maxrss is in KB)."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_maxrss * 1024  # KB → bytes


def _get_current_rss_bytes() -> int:
    """Get current RSS from /proc/self/status."""
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024  # KB → bytes
    except Exception:
        pass
    return _get_peak_rss_bytes()


# ---------------------------------------------------------------------------
# Configuration builders
# ---------------------------------------------------------------------------


def _make_canonical_config() -> StudyConfiguration:
    """Canonical ERN Part 49: 2 equity × 3 interest = 6 cells."""
    return StudyConfiguration(
        name="S5.7 Benchmark — Canonical",
        description="Canonical Part 49 workload for performance measurement",
        version="2.0",
        dataset_identifier="ern_swr_h720",
        allocation_policy_type="ConstantAllocationPolicy",
        allocation_policy_values=(Decimal("0.75"), Decimal("1.0")),
        withdrawal_policy_type="Part49WithdrawalPolicy",
        withdrawal_policy_values=(Decimal("0.03"),),
        horizon_years=(30,),
        cohort_horizon_years=60,
        debt_interest_rate_values=(Decimal("0.0"), Decimal("0.015"), Decimal("0.03")),
        debt_ltv_limit=Decimal("0.75"),
        debt_ltv_enforcement=False,
        debt_loan_draw_rate=Decimal("0.01"),
    )


def _make_baseline_config() -> StudyConfiguration:
    """Non-debt baseline: same grid, no debt parameters."""
    return StudyConfiguration(
        name="S5.7 Benchmark — Baseline",
        description="Non-debt baseline for performance comparison",
        version="2.0",
        dataset_identifier="ern_swr_h720",
        allocation_policy_type="ConstantAllocationPolicy",
        allocation_policy_values=(Decimal("0.75"), Decimal("1.0")),
        withdrawal_policy_type="ConstantWithdrawalPolicy",
        withdrawal_policy_values=(Decimal("0.04"),),
        horizon_years=(30,),
        cohort_horizon_years=60,
    )


# ---------------------------------------------------------------------------
# Benchmark functions
# ---------------------------------------------------------------------------


def _measure_rss_mb() -> float:
    """Get current RSS in MB."""
    return _get_current_rss_bytes() / (1024 * 1024)


def _measure_peak_rss_mb() -> float:
    """Get peak RSS in MB."""
    return _get_peak_rss_bytes() / (1024 * 1024)


def _benchmark_plan_construction(
    config: StudyConfiguration, n_runs: int = 3
) -> dict[str, Any]:
    """Measure study-plan construction time."""
    times: list[float] = []
    built = None
    rss_before = _measure_rss_mb()
    for _ in range(n_runs):
        gc.collect()
        t0 = time.perf_counter()
        built = build_study_plan(config, str(DATA_DIR), INITIAL_WEALTH)
        t1 = time.perf_counter()
        times.append(t1 - t0)
    rss_after = _measure_rss_mb()
    n_units = len(built.plan.units) if built else 0
    return {
        "median_s": statistics.median(times),
        "min_s": min(times),
        "max_s": max(times),
        "n_units": n_units,
        "rss_delta_mb": rss_after - rss_before,
    }


def _benchmark_execution(
    config: StudyConfiguration,
    n_cohorts_limit: int | None = None,
    n_runs: int = 1,
    label: str = "",
) -> dict[str, Any]:
    """Measure execution time for a workload."""
    built = build_study_plan(config, str(DATA_DIR), INITIAL_WEALTH)

    if n_cohorts_limit is not None:
        limited_units = built.plan.units[:n_cohorts_limit]
        limited_plan = ResearchPlan(
            experiment_definition=built.plan.experiment_definition,
            units=limited_units,
        )
        n_units = len(limited_units)
        plan_units = built.plan.units[:n_cohorts_limit]
    else:
        limited_plan = built.plan
        n_units = len(built.plan.units)
        plan_units = built.plan.units

    executor = ResearchExecutor(
        simulation_executor=SimulationExecutor(
            simulation_runner=SimulationRunner(pipeline=create_default_pipeline())
        )
    )

    times: list[float] = []
    rss_before = _measure_rss_mb()
    peak_rss = rss_before
    result = executor.execute(limited_plan)

    for _ in range(n_runs):
        gc.collect()
        t0 = time.perf_counter()
        result = executor.execute(limited_plan)
        t1 = time.perf_counter()
        current_rss = _measure_rss_mb()
        if current_rss > peak_rss:
            peak_rss = current_rss
        times.append(t1 - t0)

    assert result is not None
    sim_results = result.experiment_result.simulation_results
    n_success = sum(1 for r in sim_results if r.statistics.success)
    n_failed = sum(1 for r in sim_results if not r.statistics.success)
    n_months_total = sum(len(r.timeline.monthly_results) for r in sim_results)

    rss_after = _measure_rss_mb()
    med = statistics.median(times)

    return {
        "label": label,
        "n_units": n_units,
        "n_success": n_success,
        "n_failed": n_failed,
        "n_months_total": n_months_total,
        "median_s": med,
        "min_s": min(times),
        "max_s": max(times),
        "throughput_units_per_s": n_units / med if med > 0 else 0,
        "throughput_months_per_s": n_months_total / med if med > 0 else 0,
        "rss_before_mb": rss_before,
        "rss_after_mb": rss_after,
        "peak_rss_mb": peak_rss,
        "rss_growth_mb": rss_after - rss_before,
        "result": result,
        "units": plan_units,
    }


def _measure_result_memory(result: Any) -> dict[str, Any]:
    """Measure memory usage of result objects."""
    sim_results = result.experiment_result.simulation_results

    if sim_results:
        sample_pickle = pickle.dumps(sim_results[0])
        sample_size = len(sample_pickle)
    else:
        sample_size = 0

    total_pickle = sample_size * len(sim_results)

    if sim_results and sim_results[0].timeline.monthly_results:
        mr_pickle = pickle.dumps(sim_results[0].timeline.monthly_results[0])
        mr_size = len(mr_pickle)
    else:
        mr_size = 0

    n_monthly_results = sum(len(r.timeline.monthly_results) for r in sim_results)

    return {
        "n_results": len(sim_results),
        "sample_result_pickle_bytes": sample_size,
        "total_pickle_bytes": total_pickle,
        "total_pickle_mb": total_pickle / (1024 * 1024),
        "monthly_result_pickle_bytes": mr_size,
        "n_monthly_results": n_monthly_results,
        "total_mr_pickle_bytes": mr_size * n_monthly_results,
        "total_mr_pickle_mb": (mr_size * n_monthly_results) / (1024 * 1024),
    }


def _benchmark_aggregation(
    result: Any, units: list[Any], n_runs: int = 3
) -> dict[str, Any]:
    """Measure aggregation time."""
    from fbf.core.research.part49_aggregation import aggregate_part49_results

    times: list[float] = []
    for _ in range(n_runs):
        gc.collect()
        t0 = time.perf_counter()
        aggregate_part49_results(
            tuple(units), result.experiment_result.simulation_results
        )
        t1 = time.perf_counter()
        times.append(t1 - t0)

    return {
        "median_s": statistics.median(times),
        "min_s": min(times),
        "max_s": max(times),
    }


# ---------------------------------------------------------------------------
# Main benchmark
# ---------------------------------------------------------------------------


def run_full_benchmark() -> dict[str, Any]:
    """Run the complete S5.7 benchmark."""
    sys_info = _system_info()
    print("=" * 70)
    print("S5.7 — Canonical Part 49 Performance & Scaling Benchmark")
    print("=" * 70)
    print(f"Python: {sys_info['python']}")
    print(f"Platform: {sys_info['platform']}")
    print(f"CPU count: {sys_info['cpu_count']}")
    print()

    results: dict[str, Any] = {}

    # --- 1. Canonical workload (full 10,434 units) ---
    print("--- 1. Canonical Workload (6 cells × 1,739 cohorts = 10,434 units) ---")
    config = _make_canonical_config()

    plan_result = _benchmark_plan_construction(config, n_runs=3)
    results["plan_construction"] = plan_result
    print(f"  Plan construction: {plan_result['median_s']:.3f}s (median)")
    print(f"  Units materialized: {plan_result['n_units']}")

    print("  Executing canonical workload...")
    exec_result = _benchmark_execution(config, n_runs=1, label="canonical_full")
    results["execution_canonical"] = {
        k: v for k, v in exec_result.items() if k != "result"
    }
    print(f"  Execution time: {exec_result['median_s']:.2f}s")
    print(
        f"  Throughput: {exec_result['throughput_units_per_s']:.1f} units/s, "
        f"{exec_result['throughput_months_per_s']:,.0f} months/s"
    )
    print(
        f"  RSS before: {exec_result['rss_before_mb']:.1f} MB, "
        f"after: {exec_result['rss_after_mb']:.1f} MB, "
        f"peak: {exec_result['peak_rss_mb']:.1f} MB"
    )

    mem_result = _measure_result_memory(exec_result["result"])
    results["result_memory"] = mem_result
    print(f"  Result pickle (total): {mem_result['total_pickle_mb']:.1f} MB")
    print(f"  MonthlyResult pickle (total): {mem_result['total_mr_pickle_mb']:.1f} MB")

    agg_result = _benchmark_aggregation(
        exec_result["result"], exec_result["units"], n_runs=3
    )
    results["aggregation"] = agg_result
    print(f"  Aggregation: {agg_result['median_s']:.3f}s (median)")

    total_time = (
        plan_result["median_s"]
        + exec_result["median_s"]
        + agg_result["median_s"]
    )
    results["total_wall_time_s"] = total_time
    print(f"  Total wall time: {total_time:.2f}s")
    print()

    # --- 2. Baseline (non-debt) ---
    print("--- 2. Baseline (non-debt, same grid) ---")
    baseline_config = _make_baseline_config()
    baseline_exec = _benchmark_execution(
        baseline_config, n_runs=1, label="baseline"
    )
    results["execution_baseline"] = {
        k: v for k, v in baseline_exec.items() if k != "result"
    }
    print(f"  Units: {baseline_exec['n_units']}")
    print(f"  Execution time: {baseline_exec['median_s']:.2f}s")
    print(f"  Peak RSS: {baseline_exec['peak_rss_mb']:.1f} MB")

    if baseline_exec["median_s"] > 0:
        overhead = exec_result["median_s"] / baseline_exec["median_s"]
    else:
        overhead = float("inf")
    results["debt_overhead_ratio"] = overhead
    print(f"  Debt overhead: {overhead:.3f}x")
    print()

    # --- 3. Scaling measurements ---
    print("--- 3. Scaling Measurements ---")
    scaling_configs = [
        (1, "1 cohort"),
        (10, "10 cohorts"),
        (50, "50 cohorts"),
        (100, "100 cohorts"),
        (500, "500 cohorts"),
        (1000, "1000 cohorts"),
        (1739, "1739 cohorts (full)"),
    ]

    scaling_results: list[dict[str, Any]] = []
    for n_cohorts, label in scaling_configs:
        n_units = n_cohorts * 6  # 6 cells
        if n_units > plan_result["n_units"]:
            print(f"  {label}: SKIPPED (exceeds available units)")
            continue

        print(f"  {label} ({n_units} units)...", end=" ", flush=True)
        sc = _benchmark_execution(
            config, n_cohorts_limit=n_cohorts, n_runs=1, label=f"scale_{n_cohorts}"
        )
        scaling_results.append({
            "n_cohorts": n_cohorts,
            "n_units": n_units,
            "time_s": sc["median_s"],
            "peak_rss_mb": sc["peak_rss_mb"],
            "throughput_units_per_s": sc["throughput_units_per_s"],
        })
        print(f"{sc['median_s']:.2f}s, {sc['peak_rss_mb']:.1f} MB")

    results["scaling"] = scaling_results
    print()

    # --- 4. S5.4 memory finding revalidation ---
    print("--- 4. S5.4 Memory Finding Revalidation ---")
    print("  S5.4 reported: ~10.6 GB RSS for 10,434 units")
    peak_gb = exec_result["peak_rss_mb"] / 1024
    print(f"  S5.7 measured: {exec_result['peak_rss_mb']:.1f} MB ({peak_gb:.2f} GB)")
    print()

    # --- 5. Summary ---
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Canonical workload: {exec_result['n_units']} units")
    print(f"Total wall time: {total_time:.2f}s ({total_time / 60:.1f} min)")
    print(f"Throughput: {exec_result['throughput_units_per_s']:.1f} units/s")
    print(f"Peak RSS: {exec_result['peak_rss_mb']:.1f} MB ({peak_gb:.2f} GB)")
    print(f"Debt overhead: {overhead:.3f}x")
    print(f"Result memory (pickle): {mem_result['total_pickle_mb']:.1f} MB")
    print("=" * 70)

    return results


if __name__ == "__main__":
    results = run_full_benchmark()

    output_path = Path("docs/roadmap/s57_benchmark_results.json")
    serializable: dict[str, Any] = {}
    for k, v in results.items():
        if isinstance(v, dict):
            serializable[k] = {
                kk: vv for kk, vv in v.items() if kk != "result"
            }
        else:
            serializable[k] = v

    with open(output_path, "w") as f:
        json.dump(serializable, f, indent=2, default=str)
    print(f"\nResults saved to {output_path}")
