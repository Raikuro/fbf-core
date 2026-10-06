"""Public application entry point for standard study execution."""

from __future__ import annotations

from typing import Any

from fbf.core.execution import ExecutionOptions, ResearchExecutionResult, execute_study_plan
from fbf.core.study import StudyConfiguration, build_study_plan


def run_study(
    config: StudyConfiguration,
    data_dir: str,
    initial_wealth: Any,
    options: ExecutionOptions | None = None,
) -> Any:
    """Execute a standard study from configuration to results.

    This is the outermost public application entry point for standard study execution.
    It composes the study planning and execution phases into a single operation.

    Parameters
    ----------
    config:
        The study configuration parsed from YAML or constructed programmatically.
    data_dir:
        Path to the dataset directory containing canonical data files.
    initial_wealth:
        The initial portfolio wealth for the study.
    options:
        Execution options controlling backend, strategy, workers, etc.

    Returns
    -------
    ResearchExecutionResult
        The complete execution result containing per-unit simulation results.
    """
    built = build_study_plan(config, data_dir, initial_wealth)
    return execute_study_plan(built, options=options)


__all__ = [
    "run_study",
    "ExecutionOptions",
    "ResearchExecutionResult",
    "StudyConfiguration",
]
