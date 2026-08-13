#!/usr/bin/env python3
"""Measure sequential peak RSS for plan build + chained Reference execution.

Builds the full ERN grid plan (all 313,020 unit definitions) and runs a
sequential Reference+chaining execution of a subset of cohorts, reporting the
parent process's peak RSS via resource.getrusage.  Sequential execution keeps
every result in memory, so this is the worst-case memory path for the chained
executor and bounds what a full-grid sequential run would need.
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
from infrastructure.execution.parallel_executor import sequential_execute
from infrastructure.execution.reference_chaining import (
    ChainedReferenceSimulationExecutor,
)
from research.domain.experiment.definition import ExperimentDefinition

DATA_DIR = Path("data/ern")
STUDY = Path("examples/studies/ern_grid.yaml")


def main() -> int:
    def peak() -> float:
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # MiB

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
    print(f"plan built in {t1 - t0:.1f}s ({len(plan.units):,} units)", flush=True)

    subset = _plan_for_first_cohorts(
        data, family, cohorts, configs, alloc, withdraw, 200
    )
    t2 = time.perf_counter()
    result = sequential_execute(
        subset,
        simulation_executor=ChainedReferenceSimulationExecutor(),
        summary_only=True,
    )
    t3 = time.perf_counter()
    print(f"sequential chained run of {len(subset.units):,} units in {t3 - t2:.1f}s", flush=True)
    print(f"peak RSS: {peak():.1f} MiB", flush=True)
    print(f"results: {len(result.results):,}", flush=True)
    return 0


def _plan_for_first_cohorts(
    data, family, cohorts, configs, alloc, withdraw, cohort_count: int
):
    """Rebuild a plan limited to the first `cohort_count` cohorts."""
    longest_horizon_years = max(family.horizons)
    sub = cohorts[:cohort_count]
    exp_def = ExperimentDefinition(
        name=data["metadata"]["name"],
        description=data["metadata"]["description"],
        dataset=family.canonical,
        horizon_months=longest_horizon_years * 12,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        cohorts=sub,
        allocation_policies=(alloc,),
        withdrawal_policies=(withdraw,),
    )
    return build_grid_research_plan(
        exp_def,
        family,
        sub,
        configs,
        alloc,
        withdraw,
        default_horizon_years=longest_horizon_years,
    )


if __name__ == "__main__":
    raise SystemExit(main())
