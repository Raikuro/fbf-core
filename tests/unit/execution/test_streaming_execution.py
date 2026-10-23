"""Unit tests for the streaming execution API."""

from __future__ import annotations

import gc
import weakref
from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest

import fbf.core.execution as execution_api
from fbf.core.domain.policies import BuyAndHoldAllocationPolicy
from fbf.core.execution import (
    ExecutionBackend,
    ExecutionOptions,
    ExecutionStrategy,
    execute_study_plan,
    iter_execute_study_plan,
)
from fbf.core.execution.errors import (
    InvalidResearchPlanError,
    UnsupportedConfigurationError,
)
from fbf.core.execution.executor import ResearchExecutor
from fbf.core.study.builder import BuiltStudy
from fbf.core.study.plan import ResearchPlan
from tests.unit.execution.conftest import make_plan


def _built(plan: ResearchPlan) -> BuiltStudy:
    return BuiltStudy(
        plan=plan,
        experiment_definition=plan.experiment_definition,
        cohorts=plan.experiment_definition.cohorts,
        param_configs=(),
    )


def _collect(
    built: BuiltStudy,
    options: ExecutionOptions,
    *,
    max_units_per_slice: int,
) -> tuple[list[Any], list[Any], list[int]]:
    units: list[Any] = []
    results: list[Any] = []
    starts: list[int] = []
    for chunk in iter_execute_study_plan(
        built, options, max_units_per_slice=max_units_per_slice
    ):
        starts.append(chunk.start_index)
        units.extend(chunk.result.plan.units)
        results.extend(chunk.result.results)
    return units, results, starts


class TestStreamingEquivalence:
    @pytest.mark.parametrize(
        ("options", "label"),
        [
            (
                ExecutionOptions(
                    backend=ExecutionBackend.FAST,
                    strategy=ExecutionStrategy.SEQUENTIAL,
                    materialize_timeline=True,
                ),
                "numba-materialized",
            ),
            (
                ExecutionOptions(
                    backend=ExecutionBackend.FAST,
                    strategy=ExecutionStrategy.SEQUENTIAL,
                    summary_only=True,
                ),
                "numba-summary",
            ),
            (
                ExecutionOptions(
                    backend=ExecutionBackend.DECIMAL_FAST_PATH,
                    strategy=ExecutionStrategy.SEQUENTIAL,
                ),
                "reference",
            ),
        ],
    )
    def test_slices_reproduce_full_plan(
        self, options: ExecutionOptions, label: str
    ) -> None:
        if options.backend == ExecutionBackend.FAST:
            pytest.importorskip("numba")
        built = _built(make_plan(cohorts=2, horizons=[12, 24]))
        full = execute_study_plan(built, options)
        units, results, starts = _collect(
            built, options, max_units_per_slice=2
        )

        assert tuple(units) == built.plan.units
        assert results == list(full.results)
        assert starts == [0, 2]

    def test_reference_timelines_are_equivalent(self) -> None:
        plan = make_plan(cohorts=2, horizons=[12, 24])
        units = tuple(
            replace(
                unit,
                allocation_policy=BuyAndHoldAllocationPolicy(Decimal("0.5")),
            )
            for unit in plan.units
        )
        built = _built(
            ResearchPlan(
                experiment_definition=plan.experiment_definition,
                units=units,
            )
        )
        options = ExecutionOptions(
            backend=ExecutionBackend.DECIMAL_FAST_PATH,
            strategy=ExecutionStrategy.SEQUENTIAL,
        )
        full = execute_study_plan(built, options)
        _, results, _ = _collect(built, options, max_units_per_slice=2)
        assert [len(result.timeline.monthly_results) for result in results] == [
            12,
            24,
            12,
            24,
        ]
        assert results == list(full.results)

    def test_slice_plan_preserves_definition_and_unit_identity(self) -> None:
        built = _built(make_plan(cohorts=2, horizons=[12, 24]))
        options = ExecutionOptions(
            backend=ExecutionBackend.FAST,
            strategy=ExecutionStrategy.SEQUENTIAL,
            summary_only=True,
        )
        pytest.importorskip("numba")
        for chunk in iter_execute_study_plan(
            built, options, max_units_per_slice=2
        ):
            assert (
                chunk.result.plan.experiment_definition
                is built.plan.experiment_definition
            )
            for sliced_unit, original_unit in zip(
                chunk.result.plan.units,
                built.plan.units[
                    chunk.start_index : chunk.start_index
                    + len(chunk.result.plan.units)
                ],
                strict=True,
            ):
                assert sliced_unit is original_unit

    def test_progress_is_cumulative_and_final(self) -> None:
        built = _built(make_plan(cohorts=2, horizons=[12]))
        events: list[tuple[int, int]] = []
        options = ExecutionOptions(
            backend=ExecutionBackend.FAST,
            strategy=ExecutionStrategy.SEQUENTIAL,
            summary_only=True,
            progress_callback=lambda done, total: events.append((done, total)),
        )
        pytest.importorskip("numba")
        slices = list(
            iter_execute_study_plan(built, options, max_units_per_slice=1)
        )
        assert [len(chunk.result.results) for chunk in slices] == [1, 1]
        assert events == [(1, 2), (2, 2)]


class TestMaterializationGuard:
    def test_full_plan_above_limit_raises(self) -> None:
        built = _built(make_plan(cohorts=2, horizons=[12, 24]))
        options = ExecutionOptions(
            backend=ExecutionBackend.FAST,
            strategy=ExecutionStrategy.SEQUENTIAL,
            materialize_timeline=True,
            max_materialized_units=3,
        )
        pytest.importorskip("numba")
        with pytest.raises(
            UnsupportedConfigurationError, match="iter_execute_study_plan"
        ):
            execute_study_plan(built, options)

    def test_guard_can_be_disabled(self) -> None:
        built = _built(make_plan(cohorts=2, horizons=[12, 24]))
        options = ExecutionOptions(
            backend=ExecutionBackend.FAST,
            strategy=ExecutionStrategy.SEQUENTIAL,
            materialize_timeline=True,
            max_materialized_units=None,
        )
        pytest.importorskip("numba")
        result = execute_study_plan(built, options)
        assert len(result.results) == 4

    def test_summary_only_is_not_guarded(self) -> None:
        built = _built(make_plan(cohorts=2, horizons=[12, 24]))
        options = ExecutionOptions(
            backend=ExecutionBackend.FAST,
            strategy=ExecutionStrategy.SEQUENTIAL,
            summary_only=True,
            max_materialized_units=1,
        )
        pytest.importorskip("numba")
        result = execute_study_plan(built, options)
        assert len(result.results) == 4

    def test_streaming_ignores_full_plan_limit(self) -> None:
        built = _built(make_plan(cohorts=2, horizons=[12, 24]))
        options = ExecutionOptions(
            backend=ExecutionBackend.FAST,
            strategy=ExecutionStrategy.SEQUENTIAL,
            materialize_timeline=True,
            max_materialized_units=1,
        )
        pytest.importorskip("numba")
        slices = list(
            iter_execute_study_plan(built, options, max_units_per_slice=2)
        )
        assert sum(len(chunk.result.results) for chunk in slices) == 4

    def test_rejects_non_positive_limit(self) -> None:
        with pytest.raises(ValueError, match="max_materialized_units"):
            ExecutionOptions(materialize_timeline=True, max_materialized_units=0)


class TestStreamingSafety:
    def test_backend_selection_happens_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        built = _built(make_plan(cohorts=2, horizons=[12]))
        original = execution_api._select_simulation_executor
        calls = 0

        def counted(built_arg: Any, opt: ExecutionOptions) -> Any:
            nonlocal calls
            calls += 1
            return original(built_arg, opt)

        monkeypatch.setattr(execution_api, "_select_simulation_executor", counted)
        pytest.importorskip("numba")
        list(
            iter_execute_study_plan(
                built,
                ExecutionOptions(
                    backend=ExecutionBackend.FAST,
                    strategy=ExecutionStrategy.SEQUENTIAL,
                    summary_only=True,
                ),
                max_units_per_slice=1,
            )
        )
        assert calls == 1

    def test_invalid_unit_fails_before_first_slice(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        built = _built(make_plan(cohorts=2, horizons=[12, 24]))
        original = ResearchExecutor._create_context_for_unit
        target_index = 3
        calls = 0

        def failing(
            self: ResearchExecutor, experiment_def: Any, unit: Any
        ) -> Any:
            nonlocal calls
            index = calls
            calls += 1
            if index == target_index:
                raise InvalidResearchPlanError("late invalid unit")
            return original(self, experiment_def, unit)

        monkeypatch.setattr(ResearchExecutor, "_create_context_for_unit", failing)
        iterator = iter_execute_study_plan(
            built,
            ExecutionOptions(
                backend=ExecutionBackend.DECIMAL_FAST_PATH,
                strategy=ExecutionStrategy.SEQUENTIAL,
            ),
            max_units_per_slice=2,
        )
        with pytest.raises(InvalidResearchPlanError, match="late invalid unit"):
            next(iterator)

    def test_previous_slice_can_be_reclaimed(self) -> None:
        built = _built(make_plan(cohorts=2, horizons=[12, 24]))
        pytest.importorskip("numba")
        iterator = iter_execute_study_plan(
            built,
            ExecutionOptions(
                backend=ExecutionBackend.FAST,
                strategy=ExecutionStrategy.SEQUENTIAL,
                materialize_timeline=True,
            ),
            max_units_per_slice=2,
        )
        first = next(iterator)
        ref = weakref.ref(first.result.results[0])
        second = next(iterator)
        assert second.start_index == 2
        del first
        gc.collect()
        assert ref() is None

    def test_iterator_releases_previous_slice_before_next_execution(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        built = _built(make_plan(cohorts=2, horizons=[12, 24]))
        original = execution_api.sequential_execute
        refs: list[weakref.ReferenceType[Any]] = []

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            result = original(*args, **kwargs)
            refs.append(weakref.ref(result.results[0]))
            if len(refs) == 2:
                gc.collect()
                assert refs[0]() is None
            return result

        monkeypatch.setattr(execution_api, "sequential_execute", wrapped)
        iterator = iter_execute_study_plan(
            built,
            ExecutionOptions(
                backend=ExecutionBackend.DECIMAL_FAST_PATH,
                strategy=ExecutionStrategy.SEQUENTIAL,
            ),
            max_units_per_slice=2,
        )
        first = next(iterator)
        del first
        second = next(iterator)
        assert second.start_index == 2
        assert len(refs) == 2

    def test_rejects_non_positive_slice_limit(self) -> None:
        built = _built(make_plan(cohorts=1, horizons=[12]))
        with pytest.raises(ValueError, match="max_units_per_slice"):
            next(
                iter_execute_study_plan(
                    built,
                    ExecutionOptions(
                        backend=ExecutionBackend.DECIMAL_FAST_PATH,
                        strategy=ExecutionStrategy.SEQUENTIAL,
                    ),
                    max_units_per_slice=0,
                )
            )
