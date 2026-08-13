#!/usr/bin/env python3
"""Isolate plan-build vs execution memory for the chained executor.

Measures: (1) peak RSS after building the full 313,020-unit plan (no execution);
(2) peak RSS after a short parallel chained run restricted to ONE worker batch.
This tells us whether the full-grid parallel run can be bounded by slicing into
cohort-sized sub-plans rather than dispatching the whole plan at once.
"""

from __future__ import annotations

import resource
import sys
import time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import yaml

from cli.builders import (
    build_cohort_specs,
    build_dataset_family,
    build_grid_research_plan,
    build_parameter_configs,
)
from cli.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from engine.domain.model.money import Currency, Money
from infrastructure.execution.parallel_executor import (
    _execute_batch_on_shared_state,
    _initialize_worker,
)
from infrastructure.execution.reference_chaining import (
    ChainedReferenceSimulationExecutor,
)
from research.domain.experiment.definition import ExperimentDefinition

DATA_DIR = Path("data/ern")
STUDY = Path("examples/studies/ern_grid.yaml")


def peak_mib() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def main() -> int:
    t0 = time.perf_counter()
    data = yaml.safe_load(STUDY.read_text())
    family = build_dataset_family(data["datasets"], DATA_DIR)
    longest_horizon_years = max(family.horizons)
    cohorts = build_cohort_specs(family.canonical, longest_horizon_years * 12)
    configs = build_parameter_configs(data["parameters"])
    alloc = ConstantAllocationPolicy(Decimal("0.5"))
    withdraw = FixedRealWithdrawalPolicy(Decimal("0.04"))
    exp_def = ExperimentDefinition(
        name=data["metadata"]["name"],
        description=data["metadata"]["description"],
        dataset=family.canonical,
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
    t1 = time.perf_counter()
    print(f"plan built in {t1 - t0:.1f}s; units={len(plan.units):,}", flush=True)
    print(f"peak RSS after plan build: {peak_mib():.1f} MiB", flush=True)

    slice_units = plan.units[: 5 * 180]
    print(f"\nin-process one-batch run on {len(slice_units)} units...", flush=True)
    _initialize_worker(exp_def, slice_units, ChainedReferenceSimulationExecutor())
    t2 = time.perf_counter()
    batch = slice_units[: 3 * 180]
    results = _execute_batch_on_shared_state(batch, summary_only=True)
    t3 = time.perf_counter()
    print(f"  ran {len(results):,} units in {t3 - t2:.1f}s", flush=True)
    print(f"peak RSS after in-process batch: {peak_mib():.1f} MiB", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
