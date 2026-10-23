"""Public application entry point for standard study execution."""

from __future__ import annotations

from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.money import Money
from fbf.core.execution import ExecutionOptions, ResearchExecutionResult, execute_study_plan
from fbf.core.study import StudyConfiguration, build_study_plan


def run_study(
    config: StudyConfiguration,
    data_dir: str,
    initial_wealth: Money,
    options: ExecutionOptions | None = None,
    *,
    dataset: Dataset | None = None,
) -> ResearchExecutionResult:
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
        Execution options controlling backend, strategy, result materialization,
        and profiling.
    dataset:
        Optional pre-built dataset.  When supplied, it is used directly
        instead of loading CSV data from ``data_dir``.

    Returns
    -------
    ResearchExecutionResult
        The complete execution result containing per-unit simulation results.
    """
    built = build_study_plan(
        config,
        data_dir,
        initial_wealth,
        dataset=dataset,
    )
    return execute_study_plan(built, options=options)


__all__ = [
    "run_study",
    "ExecutionOptions",
    "ResearchExecutionResult",
    "StudyConfiguration",
]
