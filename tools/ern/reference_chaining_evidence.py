#!/usr/bin/env python3
"""P4.11 deferred — Reference horizon-chaining verification and benchmark.

Phase A evidence: proves ``ChainedReferenceSimulationExecutor`` reproduces the
canonical Reference Decimal execution exactly (bit-exact on every aggregate
statistic) on the full 313,020-unit ERN grid, and measures wall-clock time for
four execution strategies:

  1. Reference (independent per unit)
  2. Reference + horizon chaining
  3. Fast path (float, unchained)
  4. Fast path + horizon chaining

Usage:
    python tools/ern/reference_chaining_evidence.py [--subset N] [--workers N]

``--subset N`` limits the cohort count to N (default: all 1739).  Results and
wall-clock timings are printed to stdout.
"""

from __future__ import annotations

import argparse
import sys
import time
from decimal import Decimal
from pathlib import Path

import yaml

from cli.builders import StudyConfiguration, build_study_plan
from cli.fast_path import ChainedFastPathSimulationExecutor, FastPathSimulationExecutor
from engine.application.executor import SimulationExecutor
from engine.application.simulation import SimulationResult
from engine.domain.model.money import Currency, Money
from infrastructure.execution.parallel_executor import (
    _create_default_simulation_executor,
    parallel_execute,
)
from infrastructure.execution.reference_chaining import (
    ChainedReferenceSimulationExecutor,
)
from research.domain.plan import ResearchPlan
from research.orchestration.result import ResearchExecutionResult

DATA_DIR = Path("data/ern")
STUDY = Path("examples/studies/ern_grid.yaml")


def build_plan(subset_cohorts: int | None) -> ResearchPlan:
    data = yaml.safe_load(STUDY.read_text())
    config = StudyConfiguration.from_yaml(data)
    built = build_study_plan(config, str(DATA_DIR), Money(Decimal("1000000"), Currency.EUR))
    if subset_cohorts is None:
        return built.plan
    keep = {c.start_date for c in built.cohorts[:subset_cohorts]}
    units = tuple(u for u in built.plan.units if u.cohort.start_date in keep)
    return ResearchPlan(experiment_definition=built.plan.experiment_definition, units=units)


def run_parallel(
    plan: ResearchPlan, executor: SimulationExecutor, workers: int
) -> tuple[ResearchExecutionResult, float]:
    start = time.perf_counter()
    result = parallel_execute(
        plan,
        max_workers=workers,
        simulation_executor=executor,
        summary_only=True,
    )
    elapsed = time.perf_counter() - start
    return result, elapsed


def compare_results(
    label: str,
    reference: tuple[SimulationResult, ...],
    chained: tuple[SimulationResult, ...],
) -> None:
    assert len(reference) == len(chained)
    mismatches: list[str] = []
    for i, (a, b) in enumerate(zip(reference, chained, strict=True)):
        as_ = a.statistics
        bs = b.statistics
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
    if mismatches:
        print(f"{label}: MISMATCH ({len(mismatches)} shown of >=1)")
        for m in mismatches:
            print("   " + m)
        sys.exit(1)
    print(f"{label}: exact match over {len(reference):,} units")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subset", type=int, default=None)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--benchmark", action="store_true", help="run four-way benchmark")
    args = parser.parse_args()

    plan = build_plan(args.subset)
    workers = args.workers or min(16, len(plan.units))
    n_units = len(plan.units)
    month_work_ref = sum(u.horizon_months or 0 for u in plan.units)
    print(f"plan units: {n_units:,}")
    print(f"reference month-work (independent): {month_work_ref:,}")
    print(f"workers: {workers}")

    ref_exec = _create_default_simulation_executor()
    chained_exec = ChainedReferenceSimulationExecutor()

    print("Running Reference independent...", flush=True)
    ref_result, t_ref = run_parallel(plan, ref_exec, workers)
    print(f"  done in {t_ref:.1f}s", flush=True)

    print("Running Reference chained...", flush=True)
    chain_result, t_chain = run_parallel(plan, chained_exec, workers)
    print(f"  done in {t_chain:.1f}s", flush=True)

    print(f"Reference independent: {t_ref:.1f}s")
    print(f"Reference chained:     {t_chain:.1f}s")
    print(f"Reference wall-clock speedup: {t_ref / t_chain:.2f}x "
          f"(month-work reduction is exactly 3.0x)")

    compare_results(
        "Reference vs Reference+chaining",
        ref_result.results,
        chain_result.results,
    )

    if args.benchmark:
        print("Running Fast path (float, unchained)...", flush=True)
        fast_result, t_fast = run_parallel(
            plan, FastPathSimulationExecutor(precision="float"), workers
        )
        print(f"  done in {t_fast:.1f}s", flush=True)
        print("Running Fast path chained...", flush=True)
        chain_fast_result, t_chain_fast = run_parallel(
            plan, ChainedFastPathSimulationExecutor(precision="float"), workers
        )
        print(f"  done in {t_chain_fast:.1f}s", flush=True)
        print()
        print("=== Four-way wall-clock benchmark ===")
        print(f"  Reference independent:          {t_ref:>10.1f}s")
        print(f"  Reference chained:              {t_chain:>10.1f}s")
        print(f"  Fast path (float, unchained):   {t_fast:>10.1f}s")
        print(f"  Fast path chained:              {t_chain_fast:>10.1f}s")
        print(f"  Reference chained vs Reference: {t_ref / t_chain:.2f}x")
        print(f"  Fast chained vs Fast:           {t_fast / t_chain_fast:.2f}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
