"""Part 20 execution streams bundles without retaining whole-plan results."""

from __future__ import annotations

import gc
import weakref
from collections.abc import Iterator
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import fbf.core.research.part20_planner as planner
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import GlidepathAllocationPolicy
from fbf.core.execution import (
    ExecutionBackend,
    ExecutionOptions,
    ExecutionStrategy,
    execute_study_plan,
    iter_execute_study_plan,
)
from fbf.core.research.part20_planner import (
    Part20ExecutionContext,
    Part20PlanBundle,
    extract_successes,
)
from fbf.core.study.builder import BuiltStudy, build_initial_portfolio
from fbf.core.study.plan import ResearchPlan
from tests.unit.execution.conftest import make_plan

MANIFEST_PATH = Path("data/ern/cohort_manifest_part3.json")


def _mixed_plan() -> ResearchPlan:
    """Return a small Part20-like static/glidepath plan."""
    base = make_plan(cohorts=2, horizons=[12, 24])
    glidepath = GlidepathAllocationPolicy(
        start_equity=Decimal("0.60"),
        end_equity=Decimal("0.90"),
        slope=Decimal("0.01"),
        mode="passive",
    )
    units = tuple(
        replace(
            unit,
            allocation_policy=glidepath if index % 2 else unit.allocation_policy,
            initial_portfolio=build_initial_portfolio(
                Money(Decimal("1000000"), Currency.EUR), unit.dataset
            ),
        )
        for index, unit in enumerate(base.units)
    )
    return ResearchPlan(
        experiment_definition=base.experiment_definition,
        units=units,
    )


@pytest.mark.skipif(not MANIFEST_PATH.is_file(), reason="manifest not present")
def test_part20_streaming_matches_whole_plan_and_releases_slices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _mixed_plan()
    ctx = Part20ExecutionContext.create(
        MANIFEST_PATH, plan.experiment_definition.dataset
    )
    bundle = Part20PlanBundle(
        plan=plan,
        param_configs=tuple(unit.parameter_config for unit in plan.units),
        cohorts=plan.experiment_definition.cohorts,
        strategies=(),
    )
    built = BuiltStudy(
        plan=plan,
        experiment_definition=plan.experiment_definition,
        cohorts=bundle.cohorts,
        param_configs=bundle.param_configs,
    )
    options = ExecutionOptions(
        backend=ExecutionBackend.FAST,
        strategy=ExecutionStrategy.SEQUENTIAL,
        summary_only=True,
        workers=1,
    )
    full = execute_study_plan(
        built,
        replace(options, strategy=ExecutionStrategy.AUTO),
    )
    expected = extract_successes(full.results)
    del full
    gc.collect()

    original = iter_execute_study_plan
    references: list[weakref.ReferenceType[Any]] = []
    slice_sizes: list[int] = []

    def wrapped(
        plan_arg: BuiltStudy,
        options_arg: ExecutionOptions | None = None,
        *,
        max_units_per_slice: int | None = None,
    ) -> Iterator[Any]:
        assert max_units_per_slice is None
        iterator = original(
            plan_arg,
            options_arg,
            max_units_per_slice=1,
        )
        previous: weakref.ReferenceType[Any] | None = None
        for chunk in iterator:
            if previous is not None:
                gc.collect()
                assert previous() is None
            slice_sizes.append(len(chunk.result.results))
            references.append(weakref.ref(chunk.result.results[0]))
            previous = references[-1]
            yield chunk
            del chunk

    monkeypatch.setattr(planner, "iter_execute_study_plan", wrapped)

    actual = ctx.execute(bundle, options)

    assert actual == expected
    assert slice_sizes == [2, 2]
    assert sum(slice_sizes) == len(plan.units)
    assert len(references) == len(plan.experiment_definition.cohorts)
    assert ctx.stats.executions == 1
    assert ctx.stats.units_executed == len(plan.units)
    assert ctx.glidepath_gf_cache
    gc.collect()
    assert all(reference() is None for reference in references)
