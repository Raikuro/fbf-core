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

from fbf.core.study.builder import StudyConfiguration, build_study_plan
from fbf.core.domain.model.money import Currency, Money
from fbf.core.execution.strategies.parallel_executor import sequential_execute
from fbf.core.execution.strategies.reference_chaining import (
    ChainedReferenceSimulationExecutor,
)
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.plan import ResearchPlan

DATA_DIR = Path("data/ern")
STUDY = Path("examples/studies/ern_grid.yaml")


def _build() -> tuple[ResearchPlan, tuple[CohortSpecification, ...]]:
    data = yaml.safe_load(STUDY.read_text())
    config = StudyConfiguration.from_yaml(data)
    built = build_study_plan(config, str(DATA_DIR), Money(Decimal("1000000"), Currency.EUR))
    return built.plan, built.cohorts


def main() -> int:
    def peak() -> float:
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # MiB

    t0 = time.perf_counter()
    plan, cohorts = _build()
    t1 = time.perf_counter()
    print(f"plan built in {t1 - t0:.1f}s ({len(plan.units):,} units)", flush=True)

    subset = _plan_for_first_cohorts(plan, cohorts, 200)
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
    plan: ResearchPlan,
    cohorts: tuple[CohortSpecification, ...],
    cohort_count: int,
) -> ResearchPlan:
    """Return *plan* restricted to the first `cohort_count` cohorts."""
    keep = {c.start_date for c in cohorts[:cohort_count]}
    units = tuple(u for u in plan.units if u.cohort.start_date in keep)
    return ResearchPlan(experiment_definition=plan.experiment_definition, units=units)


if __name__ == "__main__":
    raise SystemExit(main())
