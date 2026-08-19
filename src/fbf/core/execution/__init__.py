"""Simulation execution engine, runners, and execution strategies."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from fbf.core.execution.result import ResearchExecutionResult
from fbf.core.execution.strategies.parallel_executor import parallel_execute, sequential_execute
from fbf.core.study.builder import BuiltStudy, StudyPlanResult

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
    "ProgressCallback",
    "ProgressEvent",
]
