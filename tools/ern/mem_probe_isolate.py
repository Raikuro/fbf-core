#!/usr/bin/env python3
"""Isolate plan-build vs execution memory for the executor.

Measures: (1) peak RSS after building the full 313,020-unit plan (no execution);
(2) peak RSS after a short parallel run restricted to ONE worker batch.
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

from fbf.core.study.builder import StudyConfiguration, build_study_plan
from fbf.core.domain.model.money import Currency, Money
from fbf.core.execution.strategies.parallel_executor import (
    _execute_batch_on_shared_state,
    _initialize_worker,
)
from fbf.core.execution.strategies.reference import (
    ReferenceSimulationExecutor,
)

DATA_DIR = Path("data/ern")
STUDY = Path("examples/studies/ern_grid.yaml")


def peak_mib() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def main() -> int:
    t0 = time.perf_counter()
    data = yaml.safe_load(STUDY.read_text())
    config = StudyConfiguration.from_yaml(data)
    built = build_study_plan(config, str(DATA_DIR), Money(Decimal("1000000"), Currency.EUR))
    plan = built.plan
    exp_def = built.experiment_definition
    t1 = time.perf_counter()
    print(f"plan built in {t1 - t0:.1f}s; units={len(plan.units):,}", flush=True)
    print(f"peak RSS after plan build: {peak_mib():.1f} MiB", flush=True)

    slice_units = plan.units[: 5 * 180]
    print(f"\nin-process one-batch run on {len(slice_units)} units...", flush=True)
    _initialize_worker(exp_def, slice_units, ReferenceSimulationExecutor())
    t2 = time.perf_counter()
    batch = slice_units[: 3 * 180]
    results = _execute_batch_on_shared_state(batch, summary_only=True)
    t3 = time.perf_counter()
    print(f"  ran {len(results):,} units in {t3 - t2:.1f}s", flush=True)
    print(f"peak RSS after in-process batch: {peak_mib():.1f} MiB", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
