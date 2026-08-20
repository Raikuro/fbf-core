"""Simulation execution engine, runners, and execution strategies."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from fbf.core.execution.result import ResearchExecutionResult
from fbf.core.execution.strategies.fast_path import FastPathValidationError
from fbf.core.study.builder import BuiltStudy, StudyPlanResult


def sequential_execute(*args: Any, **kwargs: Any) -> ResearchExecutionResult:
    """Execute through the public sequential Core operation."""
    from fbf.core.execution.strategies.parallel_executor import sequential_execute as implementation

    return implementation(*args, **kwargs)


def parallel_execute(*args: Any, **kwargs: Any) -> ResearchExecutionResult:
    """Execute through the public parallel Core operation."""
    from fbf.core.execution.strategies.parallel_executor import parallel_execute as implementation

    return implementation(*args, **kwargs)


def execute_reference_chained(*args: Any, **kwargs: Any) -> ResearchExecutionResult:
    """Execute the public exact chained-reference operation."""
    from fbf.core.execution.strategies.reference_chaining import (
        execute_reference_chained as implementation,
    )

    return implementation(*args, **kwargs)


def expected_reference_chaining_report(*args: Any, **kwargs: Any) -> Any:
    from fbf.core.execution.strategies.reference_chaining import (
        expected_reference_chaining_report as implementation,
    )

    return implementation(*args, **kwargs)


def reference_month_work(*args: Any, **kwargs: Any) -> int:
    from fbf.core.execution.strategies.fast_path import reference_month_work as implementation

    return implementation(*args, **kwargs)


def fast_path_unit_counts(*args: Any, **kwargs: Any) -> tuple[int, int]:
    from fbf.core.execution.strategies.fast_path import fast_path_unit_counts as implementation

    return implementation(*args, **kwargs)


def expected_chaining_report(*args: Any, **kwargs: Any) -> Any:
    from fbf.core.execution.strategies.fast_path import expected_chaining_report as implementation

    return implementation(*args, **kwargs)


def run_fast_path_validation(*args: Any, **kwargs: Any) -> Any:
    from fbf.core.execution.strategies.fast_path import run_fast_path_validation as implementation

    return implementation(*args, **kwargs)


def __getattr__(name: str) -> Any:
    if name == "ChainedFastPathSimulationExecutor":
        from fbf.core.execution.strategies.fast_path import ChainedFastPathSimulationExecutor

        return ChainedFastPathSimulationExecutor
    raise AttributeError(name)

ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True)
class ProgressEvent:
    completed_units: int
    total_units: int


class ExecutionMode(StrEnum):
    AUTO = "auto"
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    FAST = "fast"
    EXACT = "exact"


@dataclass(frozen=True)
class ExecutionOptions:
    mode: ExecutionMode = ExecutionMode.AUTO
    workers: int | None = None
    batch_size: int | None = None
    use_fast_path: bool = False
    progress_callback: ProgressCallback | None = None


def execute_study_plan(
    plan: StudyPlanResult | BuiltStudy,
    options: ExecutionOptions | None = None,
    **kwargs: Any,
) -> ResearchExecutionResult:
    """High-level application service to execute a study plan."""
    opt = options or ExecutionOptions()
    built = plan if isinstance(plan, BuiltStudy) else plan.built_study

    workers = opt.workers if opt.workers is not None else kwargs.get("workers", 1)
    if workers > 1:
        return parallel_execute(
            plan=built.plan,
            max_workers=workers,
            progress_callback=opt.progress_callback,
        )
    return sequential_execute(
        plan=built.plan,
        progress_callback=opt.progress_callback,
    )


__all__ = [
    "ExecutionMode",
    "ExecutionOptions",
    "execute_study_plan",
    "ResearchExecutionResult",
    "parallel_execute",
    "sequential_execute",
    "ChainedFastPathSimulationExecutor",
    "FastPathValidationError",
    "reference_month_work",
    "execute_reference_chained",
    "expected_reference_chaining_report",
    "fast_path_unit_counts",
    "expected_chaining_report",
    "run_fast_path_validation",
    "ProgressCallback",
    "ProgressEvent",
]
