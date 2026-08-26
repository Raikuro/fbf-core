#!/usr/bin/env python3
"""Standalone Numba performance benchmark and scaling driver.

Purpose:
- Workload scaling (profiling Numba executor at 1, 50, 200, 500, and full cohorts)
- Parallelism scaling experiments (sequential vs 2, 4, 8, max workers)
- RSS memory measurement
- Numba-specific GF cache and execution metrics
- Performance regression investigation

For ordinary execution phase diagnostics, use the CLI flag:
    sim-retire run ... --profile

Usage:
    python tools/ern/profile_numba_executor.py
"""

from __future__ import annotations

import gc
import os
import resource
import sys
import time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import yaml

from fbf.core.domain.model.money import Currency, Money
from fbf.core.execution.executor import ResearchExecutor
from fbf.core.execution.pipeline.executor import SimulationExecutor
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
)
from fbf.core.execution.strategies.numba_executor import NumbaSimulationExecutor
from fbf.core.execution.strategies.parallel_executor import (
    parallel_execute,
    sequential_execute,
)
from fbf.core.study.builder import StudyConfiguration, build_study_plan
from fbf.core.study.plan import ResearchPlan

DATA_DIR = Path("data/ern")
STUDY = Path("examples/studies/ern_grid.yaml")


def _peak_rss_mib() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def _build_full_plan():
    data = yaml.safe_load(STUDY.read_text())
    config = StudyConfiguration.from_yaml(data)
    t0 = time.perf_counter()
    built = build_study_plan(config, str(DATA_DIR), Money(Decimal("1000000"), Currency.EUR))
    t_build = time.perf_counter() - t0
    return built, t_build


def _create_engine_definition(
    plan: ResearchPlan,
    executor: SimulationExecutor,
) -> EngineExperimentDefinition:
    """Convert a ResearchPlan's units to an ExperimentDefinition with SimulationContexts."""
    research_executor = ResearchExecutor(executor)
    contexts = [
        research_executor._create_context_for_unit(plan.experiment_definition, unit)
        for unit in plan.units
    ]
    return EngineExperimentDefinition(
        name=plan.experiment_definition.name,
        description=plan.experiment_definition.description,
        simulation_contexts=tuple(contexts),
    )


def profile_numba_at_scale(
    executor: NumbaSimulationExecutor,
    definition: EngineExperimentDefinition,
    scale_name: str,
) -> dict:
    """Run Numba executor and collect all metrics."""
    gc.collect()
    rss_before = _peak_rss_mib()

    t0 = time.perf_counter()
    _ = executor.execute(definition)
    t_wall = time.perf_counter() - t0

    gc.collect()
    rss_after = _peak_rss_mib()

    report = executor.report
    assert report is not None

    return {
        "scale": scale_name,
        "n_units": report.logical_units,
        "n_groups": report.groups,
        "n_unique_horizons": report.longest_path_evaluations,
        "gf_entries": len(executor.gf_cache),
        "gf_hits": report.gf_cache_hits,
        "gf_misses": report.gf_cache_misses,
        "kernel_evals": report.longest_path_evaluations,
        "month_work": report.month_work,
        "wall_clock": t_wall,
        "peak_rss_mib": rss_after - rss_before,
        "units_per_sec": report.logical_units / t_wall if t_wall > 0 else 0,
    }


def main() -> None:
    print("=" * 72)
    print("R7.7 POST-R7.6 END-TO-END PROFILING")
    print("=" * 72)

    # --- Phase 0: Build the full plan ---
    print("\n[Phase 0] Building full ERN plan...")
    full_built, t_build = _build_full_plan()
    plan = full_built.plan
    n_total = len(plan.units)
    print(f"  Plan built: {n_total:,} units in {t_build:.2f}s")
    print(f"  Cohorts: {len(full_built.cohorts):,}")
    print(f"  Parameter configs: {len(full_built.param_configs):,}")
    print(f"  Peak RSS after build: {_peak_rss_mib():.1f} MiB")

    # --- Phase 1: Profile Numba executor at multiple scales ---
    print("\n[Phase 1] Profiling Numba executor at multiple scales...")

    # Group units by cohort index for subsetting
    cohorts_seen: dict[int, list] = {}
    for i, unit in enumerate(plan.units):
        cohort_idx = i // len(full_built.param_configs)
        cohorts_seen.setdefault(cohort_idx, []).append(unit)

    n_cohorts = len(full_built.cohorts)
    scales = [
        ("small (1 cohort)", 1),
        ("medium (50 cohorts)", min(50, n_cohorts)),
        ("medium (200 cohorts)", min(200, n_cohorts)),
        ("large (500 cohorts)", min(500, n_cohorts)),
        ("full (all cohorts)", n_cohorts),
    ]

    profile_results: list[dict] = []

    for scale_name, n_sel in scales:
        selected_units = []
        for ci in range(n_sel):
            selected_units.extend(cohorts_seen.get(ci, []))

        # Create the engine definition with SimulationContexts
        numba_exec = NumbaSimulationExecutor()
        definition = _create_engine_definition(
            ResearchPlan(
                experiment_definition=plan.experiment_definition,
                units=tuple(selected_units),
            ),
            numba_exec,
        )

        result = profile_numba_at_scale(numba_exec, definition, scale_name)
        profile_results.append(result)

        print(f"\n  --- {scale_name} ---")
        print(f"  Logical units:      {result['n_units']:>10,}")
        print(f"  Trajectory groups:  {result['n_groups']:>10,}")
        print(f"  Unique horizons:    {result['n_unique_horizons']:>10,}")
        print(f"  GF cache entries:   {result['gf_entries']:>10,}")
        print(f"  GF cache hits:      {result['gf_hits']:>10,}")
        print(f"  GF cache misses:    {result['gf_misses']:>10,}")
        print(f"  Kernel evaluations: {result['kernel_evals']:>10,}")
        print(f"  Month work:         {result['month_work']:>10,}")
        print(f"  Wall clock:         {result['wall_clock']:>10.3f}s")
        print(f"  Throughput:         {result['units_per_sec']:>10,.0f} units/s")
        print(f"  Peak RSS delta:     {result['peak_rss_mib']:>10.1f} MiB")

    # --- Phase 2: CPU parallelism scaling ---
    print("\n" + "=" * 72)
    print("[Phase 2] CPU parallelism scaling (full ERN workload)...")
    cpu_count = os.cpu_count() or 1
    print(f"  CPU count: {cpu_count}")

    worker_counts = sorted({1, 2, 4, min(8, cpu_count), cpu_count})
    parallel_results = []

    # Sequential
    gc.collect()
    rss_before = _peak_rss_mib()
    t0 = time.perf_counter()
    _ = sequential_execute(plan, simulation_executor=NumbaSimulationExecutor())
    t_seq = time.perf_counter() - t0
    gc.collect()
    rss_after = _peak_rss_mib()
    parallel_results.append({
        "mode": "sequential",
        "workers": 1,
        "wall_clock": t_seq,
        "peak_rss_delta_mib": rss_after - rss_before,
    })

    # Parallel
    for nw in worker_counts:
        if nw == 1:
            continue
        gc.collect()
        rss_before = _peak_rss_mib()
        t0 = time.perf_counter()
        _ = parallel_execute(
            plan,
            simulation_executor=NumbaSimulationExecutor(),
            max_workers=nw,
        )
        t_par = time.perf_counter() - t0
        gc.collect()
        rss_after = _peak_rss_mib()
        parallel_results.append({
            "mode": "parallel",
            "workers": nw,
            "wall_clock": t_par,
            "peak_rss_delta_mib": rss_after - rss_before,
        })

    print(f"\n  {'Mode':<12} {'Workers':>8} {'Wall (s)':>10} {'RSS Δ (MiB)':>12} {'Speedup':>10}")
    print("  " + "-" * 55)
    for pr in parallel_results:
        speedup = t_seq / pr["wall_clock"] if pr["wall_clock"] > 0 else 0
        print(
            f"  {pr['mode']:<12} {pr['workers']:>8} {pr['wall_clock']:>10.3f} "
            f"{pr['peak_rss_delta_mib']:>12.1f} {speedup:>10.2f}x"
        )

    # --- Phase 3: Summary ---
    print("\n" + "=" * 72)
    print("[Phase 3] Summary")
    print("=" * 72)

    full = profile_results[-1]
    print("\n  Full ERN workload (Numba executor):")
    print(f"    Logical units:        {full['n_units']:>10,}")
    print(f"    Unique trajectory groups: {full['n_groups']:>10,}")
    print(f"    GF cache entries:     {full['gf_entries']:>10,}")
    tot_gf = full['gf_hits'] + full['gf_misses']
    hit_rate = full['gf_hits'] / tot_gf * 100 if tot_gf > 0 else 0
    print(f"    GF cache hit rate:    {hit_rate:>9.1f}%")
    print(f"    Kernel evaluations:   {full['kernel_evals']:>10,}")
    print(f"    Total month work:     {full['month_work']:>10,}")
    print(f"    Wall clock:           {full['wall_clock']:>10.3f}s")
    print(f"    Throughput:           {full['units_per_sec']:>10,.0f} units/s")

    # Parallelism
    print("\n  Parallelism scaling:")
    for pr in parallel_results:
        speedup = t_seq / pr["wall_clock"] if pr["wall_clock"] > 0 else 0
        print(f"    {pr['mode']:<12} w={pr['workers']:<3} → "
              f"{pr['wall_clock']:.3f}s ({speedup:.2f}x)")

    print("\n" + "=" * 72)
    print("PROFILING COMPLETE")
    print("=" * 72)


if __name__ == "__main__":
    main()
