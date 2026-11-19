"""Single-process research plan execution orchestration."""

from __future__ import annotations

from collections.abc import Callable

from fbf.core.execution.executor import ResearchExecutor
from fbf.core.execution.pipeline.executor import SimulationExecutor
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    ExperimentRun,
    SimulationResult,
    SimulationTimeline,
)
from fbf.core.execution.profiling import NoOpProfiler, Profiler
from fbf.core.execution.result import ResearchExecutionResult
from fbf.core.study.plan import ResearchPlan


class _ProgressReportingSimulationExecutor(SimulationExecutor):
    """SimulationExecutor wrapper that reports per-context completion progress.

    ``ResearchExecutor`` delegates exactly once to ``SimulationExecutor.execute``,
    which runs every context in plan order. This wrapper hooks that single call and
    delegates one context at a time to the inner executor, firing
    ``callback(completed, total)`` after each unit's context finishes.  It gives
    per-unit progress reporting in single-process execution without altering the
    orchestrator contract or simulation semantics.

    Executors that advertise ``processes_whole_definition = True`` are passed
    the full definition unchanged: splitting it
    into single-context calls would silently disable their cross-context
    optimisation (horizon derivation).  Progress is then reported once, after the
    whole definition completes.
    """

    def __init__(
        self,
        inner: SimulationExecutor,
        callback: Callable[[int, int], None],
        total: int,
    ) -> None:
        self._inner = inner
        self._callback = callback
        self._total = total
        self._completed = 0

    def execute(self, definition: EngineExperimentDefinition) -> ExperimentRun:
        # Check the advertised class attribute rather than the instance: probing
        # an instance with getattr would auto-create truthy attributes on Mock
        # wrappers in tests and wrongly skip the per-context progress loop.
        if getattr(type(self._inner), "processes_whole_definition", False):
            run = self._inner.execute(definition)
            self._completed += len(run.simulation_results)
            self._callback(self._completed, self._total)
            return run
        results: list[SimulationResult] = []
        for context in definition.simulation_contexts:
            single = EngineExperimentDefinition(
                name=definition.name,
                description=definition.description,
                simulation_contexts=(context,),
            )
            run = self._inner.execute(single)
            self._completed += 1
            self._callback(self._completed, self._total)
            results.append(run.simulation_results[0])
        return ExperimentRun(
            definition=definition,
            simulation_results=tuple(results),
        )


def _to_summary_result(result: SimulationResult) -> SimulationResult:
    """Return a copy of a SimulationResult carrying only its aggregate statistics.

    The per-month timeline is dropped so a result can be retained by a caller
    that only needs aggregate statistics, e.g. the CLI completion summary,
    without retaining hundreds of megabytes of monthly payloads. Simulation
    semantics are unchanged; this only discards the detailed timeline of an
    already-completed run.
    """
    return SimulationResult(
        timeline=SimulationTimeline(monthly_results=()),
        statistics=result.statistics,
    )


def _strip_result_timelines(result: ResearchExecutionResult) -> ResearchExecutionResult:
    """Return a copy of a ResearchExecutionResult with per-month timelines stripped."""
    summary_run = ExperimentRun(
        definition=result.experiment_result.definition,
        simulation_results=tuple(_to_summary_result(r) for r in result.results),
    )
    return ResearchExecutionResult(
        plan=result.plan,
        experiment_result=summary_run,
    )


def execute_plan(
    plan: ResearchPlan,
    simulation_executor: SimulationExecutor | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    summary_only: bool = False,
    profiler: Profiler | None = None,
) -> ResearchExecutionResult:
    """Execute a research plan with the single production orchestration path.

    Parameters
    ----------
    plan:
        The immutable research plan to execute.
    simulation_executor:
        Optional custom SimulationExecutor.
    progress_callback:
        Optional callback(completed_units, total_units) for progress reporting.
    summary_only:
        When True, per-month timelines are stripped before returning.
    profiler:
        Optional profiler for timing.  Default is ``NoOpProfiler`` (zero overhead).

    Returns
    -------
    ResearchExecutionResult
        The ordered execution result.
    """
    profiler = profiler or NoOpProfiler()

    profiler.start("execution_setup")
    if simulation_executor is None:
        raise ValueError("simulation_executor is required")
    sim_exec = simulation_executor
    if progress_callback is not None:
        sim_exec = _ProgressReportingSimulationExecutor(
            sim_exec,
            progress_callback,
            total=len(plan.units),
        )
    profiler.stop("execution_setup")

    profiler.start("execution")
    research_executor = ResearchExecutor(sim_exec, profiler=profiler)
    result = research_executor.execute(plan)
    profiler.stop("execution")

    if summary_only:
        profiler.start("execution_strip_timelines")
        result = _strip_result_timelines(result)
        profiler.stop("execution_strip_timelines")

    profiler.record("execution_units", len(plan.units))
    return result


__all__ = ["execute_plan"]
