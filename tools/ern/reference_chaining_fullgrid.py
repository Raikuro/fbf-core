#!/usr/bin/env python3
"""P4.11 deferred — full-grid Reference horizon-chaining equivalence (memory-bounded).

Proves ``ChainedReferenceSimulationExecutor`` reproduces the canonical Reference
Decimal execution **bit-exactly on every aggregate statistic over all 313,020
units** of the ERN grid, while bounding memory by processing the plan in
cohort-sized slices.

Why slices?  Each completed chained result materializes ~0.37 MiB of timeline
payload, so the whole grid would need ~110 GiB in a single process and a
whole-plan multi-worker dispatch would put ~7 GiB in every worker (OOM on this
host).  Slicing by ``--slice-cohorts N`` keeps per-worker residency at
``N * 180 / workers ~ < 1 GiB`` and still preserves horizon chaining within a
slice (each cohort keeps all its horizons grouped), so the exact 3.0x
month-work reduction is intact and the equivalence argument is unaffected.

Usage:
    python tools/ern/reference_chaining_fullgrid.py [--workers N] [--slice-cohorts N]

Prints per-slice and cumulative wall-clock for Reference independent vs
Reference chained, then an exact-match check over the entire 313,020 units.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import yaml

from cli.builders import StudyConfiguration, build_study_plan
from engine.application.simulation import SimulationResult
from engine.domain.model.money import Currency, Money
from infrastructure.execution.parallel_executor import parallel_execute
from infrastructure.execution.reference_chaining import (
    ChainedReferenceSimulationExecutor,
)
from research.domain.cohort.specification import CohortSpecification
from research.domain.plan import ResearchPlan

DATA_DIR = Path("data/ern")
STUDY = Path("examples/studies/ern_grid.yaml")


def _cohort_plan(cohorts: tuple[CohortSpecification, ...]) -> ResearchPlan:
    data = yaml.safe_load(STUDY.read_text())
    config = StudyConfiguration.from_yaml(data)
    built = build_study_plan(config, str(DATA_DIR), Money(Decimal("1000000"), Currency.EUR))
    keep = {c.start_date for c in cohorts}
    units = tuple(u for u in built.plan.units if u.cohort.start_date in keep)
    return ResearchPlan(experiment_definition=built.plan.experiment_definition, units=units)


def _slices(
    cohorts: tuple[CohortSpecification, ...], size: int
) -> Iterator[tuple[CohortSpecification, ...]]:
    for i in range(0, len(cohorts), size):
        yield cohorts[i : i + size]


def compare_slice(
    ref_results: tuple[SimulationResult, ...],
    chain_results: tuple[SimulationResult, ...],
) -> list[str]:
    mismatches: list[str] = []
    for i, (a, b) in enumerate(zip(ref_results, chain_results, strict=True)):
        as_, bs = a.statistics, b.statistics
        if (
            as_.success != bs.success
            or as_.failure_month != bs.failure_month
            or as_.months_simulated != bs.months_simulated
            or as_.final_wealth != bs.final_wealth
            or as_.max_drawdown != bs.max_drawdown
        ):
            mismatches.append(
                f"unit[{i}] ref({as_.success},{as_.failure_month},{as_.months_simulated},"
                f"{as_.final_wealth.amount},{as_.max_drawdown}) vs "
                f"chained({bs.success},{bs.failure_month},{bs.months_simulated},"
                f"{bs.final_wealth.amount},{bs.max_drawdown})"
            )
            if len(mismatches) >= 5:
                break
    return mismatches


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--slice-cohorts", type=int, default=100)
    args = parser.parse_args()

    data = yaml.safe_load(STUDY.read_text())
    config = StudyConfiguration.from_yaml(data)
    built = build_study_plan(config, str(DATA_DIR), Money(Decimal("1000000"), Currency.EUR))
    cohorts = built.cohorts

    chained_ex = ChainedReferenceSimulationExecutor()

    total_units = 0
    total_mismatch = 0
    ref_times: list[float] = []
    chain_times: list[float] = []
    slices = list(_slices(cohorts, args.slice_cohorts))
    print(f"cohorts: {len(cohorts):,} in {len(slices)} slices "
          f"(slice={args.slice_cohorts}, workers={args.workers})", flush=True)

    for si, slice_cohorts in enumerate(slices, start=1):
        plan = _cohort_plan(tuple(slice_cohorts))
        n = len(plan.units)
        print(f"[slice {si}/{len(slices)}] {n:,} units...", flush=True)

        t0 = time.perf_counter()
        ref_res = parallel_execute(
            plan, max_workers=args.workers, simulation_executor=None, summary_only=True
        )
        t1 = time.perf_counter()
        ref_elapsed = t1 - t0
        ref_times.append(ref_elapsed)

        t0 = time.perf_counter()
        chain_res = parallel_execute(
            plan, max_workers=args.workers, simulation_executor=chained_ex, summary_only=True
        )
        t1 = time.perf_counter()
        chain_elapsed = t1 - t0
        chain_times.append(chain_elapsed)

        mismatches = compare_slice(ref_res.results, chain_res.results)
        total_mismatch += len(mismatches)
        total_units += n
        print(f"   ref {ref_elapsed:.1f}s / chain {chain_elapsed:.1f}s"
              f" / exact={len(mismatches) == 0}", flush=True)
        if mismatches:
            for m in mismatches[:5]:
                print("   " + m)
            sys.exit(1)

    print()
    print(f"=== Full-grid equivalence over {total_units:,} units ===")
    print(f"  mismatches: {total_mismatch:,}")
    t_ref = sum(ref_times)
    t_chain = sum(chain_times)
    print(f"  Reference independent cumulative: {t_ref:.1f}s")
    print(f"  Reference chained cumulative:     {t_chain:.1f}s")
    print(f"  wall-clock speedup: {t_ref / t_chain:.2f}x "
          f"(month-work reduction is exactly 3.0x)")
    return 0 if total_mismatch == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
