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

from cli.builders import (
    build_cohort_specs,
    build_dataset_family,
    build_grid_research_plan,
    build_parameter_configs,
)
from cli.fast_path import ChainedFastPathSimulationExecutor, FastPathSimulationExecutor
from cli.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
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
from research.domain.experiment.definition import ExperimentDefinition

DATA_DIR = Path("data/ern")
STUDY = Path("examples/studies/ern_grid.yaml")


def build_plan(subset_cohorts: int | None):
    data = yaml.safe_load(STUDY.read_text())
    family = build_dataset_family(data["datasets"], DATA_DIR)
    canonical = family.canonical
    longest_horizon_years = max(family.horizons)
    cohorts = build_cohort_specs(canonical, longest_horizon_years * 12)
    if subset_cohorts is not None:
        cohorts = cohorts[:subset_cohorts]
    configs = build_parameter_configs(data["parameters"])
    alloc = ConstantAllocationPolicy(Decimal("0.5"))
    withdraw = FixedRealWithdrawalPolicy(Decimal("0.04"))
    exp_def = ExperimentDefinition(
        name=data["metadata"]["name"],
        description=data["metadata"]["description"],
        dataset=canonical,
        horizon_months=longest_horizon_years * 12,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        cohorts=cohorts,
        allocation_policies=(alloc,),
        withdrawal_policies=(withdraw,),
    )
    plan = build_grid_research_plan(
        exp_def,
        family,
        cohorts,
        configs,
        alloc,
        withdraw,
        default_horizon_years=longest_horizon_years,
    )
    return plan


def run_parallel(plan, executor: SimulationExecutor, workers: int):
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
    month_work_ref = sum(u.horizon_months for u in plan.units)
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
