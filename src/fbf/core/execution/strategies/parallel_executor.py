"""Parallel execution engine for research studies (v0.4).

Provides deterministic parallel execution of a ``ResearchPlan`` across multiple worker
processes using ``ProcessPoolExecutor``. Guarantees bit-for-bit equivalence to
sequential execution.
"""

from __future__ import annotations

import math
import os
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass

from fbf.core.execution.executor import ResearchExecutor
from fbf.core.execution.pipeline.executor import SimulationExecutor
from fbf.core.execution.pipeline.pipeline import SimulationPipeline
from fbf.core.execution.pipeline.runner import SimulationRunner
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    ExperimentRun,
    SimulationResult,
    SimulationTimeline,
)
from fbf.core.execution.pipeline.steps.allocation_decision_step import AllocationDecisionStep
from fbf.core.execution.pipeline.steps.build_decision_context_step import BuildDecisionContextStep
from fbf.core.execution.pipeline.steps.initialize_allocation_step import InitializeAllocationStep
from fbf.core.execution.pipeline.steps.market_evolution_step import MarketEvolutionStep
from fbf.core.execution.pipeline.steps.monthly_result_builder_step import MonthlyResultBuilderStep
from fbf.core.execution.pipeline.steps.portfolio_rebalance_step import PortfolioRebalanceStep
from fbf.core.execution.pipeline.steps.simulation_state_update_step import SimulationStateUpdateStep
from fbf.core.execution.pipeline.steps.withdrawal_decision_step import WithdrawalDecisionStep
from fbf.core.execution.pipeline.steps.withdrawal_execution_step import WithdrawalExecutionStep
from fbf.core.execution.result import ResearchExecutionResult
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan


def _create_default_simulation_executor() -> SimulationExecutor:
    """Create a default engine SimulationExecutor with the standard 9-step pipeline."""
    pipeline = SimulationPipeline(
        [
            InitializeAllocationStep(),
            BuildDecisionContextStep(),
            WithdrawalDecisionStep(),
            WithdrawalExecutionStep(),
            AllocationDecisionStep(),
            PortfolioRebalanceStep(),
            MarketEvolutionStep(),
            MonthlyResultBuilderStep(),
            SimulationStateUpdateStep(),
        ]
    )
    runner = SimulationRunner(pipeline)
    return SimulationExecutor(runner)


class _ProgressReportingSimulationExecutor(SimulationExecutor):
    """SimulationExecutor wrapper that reports per-context completion progress.

    ``ResearchExecutor`` delegates exactly once to ``SimulationExecutor.execute``,
    which runs every context in plan order. This wrapper hooks that single call and
    delegates one context at a time to the inner executor, firing
    ``callback(completed, total)`` after each unit's context finishes.  It gives
    per-unit progress reporting in sequential execution without altering the
    orchestrator contract or simulation semantics.

    Executors that advertise ``processes_whole_definition = True`` (e.g. the
    fast path) are passed the full definition unchanged: splitting it
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

    The per-month timeline is dropped so the result can be transferred between
    worker processes (or retained by a caller that only needs aggregate
    statistics, e.g. the CLI completion summary) without shipping hundreds of
    megabytes of monthly payloads. Simulation semantics are unchanged; this
    only discards the detailed timeline of an already-completed run.
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


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    """Configuration for parallel execution.

    Fields
    ------
    max_workers:
        Maximum number of worker processes/threads (None = conservative
        default: min(8, os.cpu_count())).
    timeout_seconds:
        Timeout in seconds for execution per task/batch.
    use_processes:
        True to use ProcessPoolExecutor (CPU-bound), False for ThreadPoolExecutor.
    chunk_size:
        Units per task chunk when fine-grained progress is requested. ``None``
        (the default) uses worker-sized batches so a large plan is dispatched as
        a few tens of tasks instead of one task per unit; set a positive integer
        explicitly to opt into per-chunk granularity (used only for progress
        smoothing in the summary-only path).
    enable_progress:
        True to enable progress tracking callbacks.
    """

    max_workers: int | None = None
    timeout_seconds: float | None = None
    use_processes: bool = True
    chunk_size: int | None = None
    enable_progress: bool = True


# Conservative cap for *implicit* worker selection: when no explicit
# ``--workers`` / ``max_workers`` override is provided, never auto-scale to
# every logical CPU.  Explicit overrides (``--workers N``, ``--workers max``,
# ``ERN_E2E_WORKERS``) bypass this entirely.
_DEFAULT_MAX_WORKERS = 8


def default_max_workers() -> int:
    """Return the conservative default worker count.

    ``min(_DEFAULT_MAX_WORKERS, os.cpu_count() or 1)`` — hosts with 8 or fewer
    logical CPUs get their full count; larger hosts are capped at 8.  Only used
    when the caller provides no explicit worker override.
    """
    return min(_DEFAULT_MAX_WORKERS, os.cpu_count() or 1)


def create_work_batches(
    plan: ResearchPlan,
    max_workers: int,
) -> Sequence[Sequence[PlannedSimulationUnit]]:
    """Create deterministic work batches for distribution to workers.

    Batch size is calculated as ceil(len(plan.units) / max_workers).
    Batches maintain strict deterministic ordering.

    Parameters
    ----------
    plan:
        The research plan containing units to execute.
    max_workers:
        Number of workers to partition work across.

    Returns
    -------
    Sequence[Sequence[PlannedSimulationUnit]]
        Ordered sequence of unit batches.
    """
    if max_workers <= 0:
        raise ValueError(f"max_workers must be positive (> 0), got {max_workers}")
    if len(plan.units) == 0:
        return []

    batch_size = math.ceil(len(plan.units) / max_workers)
    batches: list[tuple[PlannedSimulationUnit, ...]] = []
    for i in range(0, len(plan.units), batch_size):
        batches.append(plan.units[i : i + batch_size])
    return batches


def create_chunked_batches(
    plan: ResearchPlan,
    chunk_size: int,
) -> Sequence[Sequence[PlannedSimulationUnit]]:
    """Create fine-grained deterministic unit chunks (``chunk_size`` units each).

    Used when a progress callback wants smoother intermediate progress in the
    summary-only path, where each chunk's result payload is tiny (aggregate
    statistics only) so the extra per-chunk IPC cost is negligible.
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive (> 0), got {chunk_size}")
    batches: list[tuple[PlannedSimulationUnit, ...]] = []
    for i in range(0, len(plan.units), chunk_size):
        batches.append(plan.units[i : i + chunk_size])
    return batches


# Per-worker state seeded once by ProcessPoolExecutor(initializer=...) so the
# large shared experiment definition (and its dataset) is transferred once per
# worker instead of being pickled into every task submission. This removes the
# dominant per-task IPC cost for large datasets (see the summary-only path).
_WORKER_EXPERIMENT_DEFINITION: ExperimentDefinition | None = None
_WORKER_UNITS: tuple[PlannedSimulationUnit, ...] | None = None
_WORKER_SIMULATION_EXECUTOR: SimulationExecutor | None = None


def _initialize_worker(
    exp_def: ExperimentDefinition,
    units: Sequence[PlannedSimulationUnit],
    simulation_executor: SimulationExecutor | None,
) -> None:
    """Seed per-worker shared state once (pool ``initializer``/``initargs``).

    Runs once in each worker before any task. Subsequent tasks carry only unit
    index ranges, so the (potentially large) experiment definition and unit
    datasets are never re-pickled per task.
    """
    global _WORKER_EXPERIMENT_DEFINITION, _WORKER_UNITS, _WORKER_SIMULATION_EXECUTOR
    _WORKER_EXPERIMENT_DEFINITION = exp_def
    _WORKER_UNITS = tuple(units)
    _WORKER_SIMULATION_EXECUTOR = simulation_executor


def _execute_batch_on_shared_state(
    units: Sequence[PlannedSimulationUnit],
    summary_only: bool,
) -> tuple[SimulationResult, ...]:
    """Run a batch of units against the worker's shared experiment definition.

    Memory is bounded per worker: timelines are stripped (or a result discarded)
    as each unit completes, so a worker never holds more than one unit's monthly
    payload regardless of the dispatch batch size.  Executors that advertise
    ``processes_whole_definition = True`` (e.g. the fast path) still
    receive the whole batch as a single definition, since splitting it would
    silently disable their cross-context optimisation (horizon derivation); their
    footprint is small because they never materialize per-month timelines.
    """
    exp_def = _WORKER_EXPERIMENT_DEFINITION
    sim_executor = _WORKER_SIMULATION_EXECUTOR or _create_default_simulation_executor()
    if exp_def is None:
        raise RuntimeError(
            "Worker shared execution state is not initialised; "
            "the pool must be created with _initialize_worker as initializer"
        )
    research_executor = ResearchExecutor(sim_executor)
    if getattr(type(sim_executor), "processes_whole_definition", False):
        sub_plan = ResearchPlan(experiment_definition=exp_def, units=tuple(units))
        result = research_executor.execute(sub_plan)
        if summary_only:
            return tuple(_to_summary_result(r) for r in result.results)
        return result.results
    results: list[SimulationResult] = []
    for unit in units:
        sub_plan = ResearchPlan(experiment_definition=exp_def, units=(unit,))
        run = research_executor.execute(sub_plan)
        unit_result = run.results[0]
        results.append(_to_summary_result(unit_result) if summary_only else unit_result)
    return tuple(results)


def _worker_execute_index_batch(
    index_batch: Sequence[int],
    summary_only: bool = False,
) -> tuple[SimulationResult, ...]:
    """Worker task that executes the units at ``index_batch`` from shared state.

    The task payload is only the integer index range; the experiment definition
    and unit datasets were seeded once per worker by ``_initialize_worker``.
    """
    units = _WORKER_UNITS
    if units is None:
        raise RuntimeError(
            "Worker shared unit state is not initialised; "
            "the pool must be created with _initialize_worker as initializer"
        )
    batch = tuple(units[i] for i in index_batch)
    return _execute_batch_on_shared_state(batch, summary_only)


def _worker_execute_batch(
    exp_def: ExperimentDefinition,
    units: Sequence[PlannedSimulationUnit],
    simulation_executor: SimulationExecutor | None = None,
    summary_only: bool = False,
) -> tuple[SimulationResult, ...]:
    """Worker task function executing a batch of units.

    Kept for API compatibility and direct in-process use; the parallel path uses
    ``_worker_execute_index_batch`` against initializer-seeded shared state so
    the experiment definition is not re-pickled for every task.

    Parameters
    ----------
    exp_def:
        The shared experiment definition.
    units:
        The subset of planned simulation units assigned to this worker.
    simulation_executor:
        Optional custom SimulationExecutor.
    summary_only:
        When True, per-month timelines are stripped from the returned results
        (only aggregate statistics are transferred back to the parent process).

    Returns
    -------
    tuple[SimulationResult, ...]
        Ordered engine simulation results for the batch.
    """
    sim_executor = (
        simulation_executor
        if simulation_executor is not None
        else _create_default_simulation_executor()
    )
    research_executor = ResearchExecutor(sim_executor)
    sub_plan = ResearchPlan(experiment_definition=exp_def, units=tuple(units))
    result = research_executor.execute(sub_plan)
    if summary_only:
        return tuple(_to_summary_result(r) for r in result.results)
    return result.results


def _worker_execute_batch_safe(
    exp_def: ExperimentDefinition,
    units: Sequence[PlannedSimulationUnit],
    simulation_executor: SimulationExecutor | None = None,
) -> tuple[tuple[SimulationResult | None, Exception | None], ...]:
    """Worker task executing units safely, capturing exceptions per unit.

    Parameters
    ----------
    exp_def:
        The shared experiment definition.
    units:
        The subset of planned units.
    simulation_executor:
        Optional custom SimulationExecutor.

    Returns
    -------
    tuple[tuple[SimulationResult | None, Exception | None], ...]
        Sequence of (result, exception) pairs matching units index.
    """
    sim_executor = (
        simulation_executor
        if simulation_executor is not None
        else _create_default_simulation_executor()
    )
    research_executor = ResearchExecutor(sim_executor)

    unit_results: list[tuple[SimulationResult | None, Exception | None]] = []
    for unit in units:
        try:
            sub_plan = ResearchPlan(experiment_definition=exp_def, units=(unit,))
            exec_res = research_executor.execute(sub_plan)
            unit_results.append((exec_res.results[0], None))
        except Exception as exc:
            unit_results.append((None, exc))
    return tuple(unit_results)


def sequential_execute(
    plan: ResearchPlan,
    simulation_executor: SimulationExecutor | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    summary_only: bool = False,
) -> ResearchExecutionResult:
    """Execute a research plan sequentially with a single worker.

    Parameters
    ----------
    plan:
        The immutable research plan to execute.
    simulation_executor:
        Optional custom SimulationExecutor. If None, default 9-step pipeline executor is used.
    progress_callback:
        Optional callback ``(completed_units, total_units)`` invoked as units complete.
    summary_only:
        When True, per-month timelines are stripped from the returned results
        (aggregate statistics only).

    Returns
    -------
    ResearchExecutionResult
        Aggregated result preserving plan-unit provenance.
    """
    sim_exec = simulation_executor or _create_default_simulation_executor()
    if progress_callback is not None:
        sim_exec = _ProgressReportingSimulationExecutor(
            sim_exec,
            progress_callback,
            total=len(plan.units),
        )
    research_executor = ResearchExecutor(sim_exec)
    result = research_executor.execute(plan)
    if summary_only:
        return _strip_result_timelines(result)
    return result


def parallel_execute(
    plan: ResearchPlan,
    max_workers: int | None = None,
    config: ExecutionConfig | None = None,
    simulation_executor: SimulationExecutor | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    summary_only: bool = False,
) -> ResearchExecutionResult:
    """Execute a research plan in parallel using ProcessPoolExecutor.

    Guarantees deterministic results identical to sequential execution.

    Parameters
    ----------
    plan:
        The immutable research plan to execute.
    max_workers:
        Optional worker count override.
    config:
        Optional execution configuration.
    simulation_executor:
        Optional custom SimulationExecutor.
    progress_callback:
        Optional callback(completed_units, total_units) for progress reporting.
    summary_only:
        When True, workers strip per-month timelines before transferring results
        back to the parent (aggregate statistics only). Avoids shipping hundreds
        of megabytes of monthly payloads when the caller only needs aggregates.

    Returns
    -------
    ResearchExecutionResult
        Aggregated result with bit-for-bit equivalence to sequential_execute(plan).
    """
    if config is None:
        config = ExecutionConfig()

    effective_workers = max_workers if max_workers is not None else config.max_workers
    if effective_workers is None or effective_workers <= 0:
        effective_workers = default_max_workers()

    total_units = len(plan.units)
    if total_units == 0:
        return sequential_execute(
            plan,
            simulation_executor=simulation_executor,
            progress_callback=progress_callback,
            summary_only=summary_only,
        )

    if effective_workers == 1:
        return sequential_execute(
            plan,
            simulation_executor=simulation_executor,
            progress_callback=progress_callback,
            summary_only=summary_only,
        )

    if (
        progress_callback is not None
        and summary_only
        and config.chunk_size is not None
        and config.chunk_size > 0
    ):
        # Explicitly requested fine-grained chunks give smooth progress updates;
        # each chunk's payload is tiny in summary-only mode. This is opt-in via
        # ExecutionConfig.chunk_size: the default (None) dispatches worker-sized
        # batches so a 300k-unit grid runs as a few dozen tasks rather than one
        # task per unit.
        batches = create_chunked_batches(plan, config.chunk_size)
    else:
        batches = create_work_batches(plan, effective_workers)
    executor_cls = ProcessPoolExecutor if config.use_processes else ThreadPoolExecutor

    # Map unit batches to index ranges. The experiment definition and unit
    # datasets are seeded once per worker via the pool initializer, and tasks
    # carry only these integer index ranges, eliminating per-task re-pickling of
    # the (potentially large) experiment definition.
    all_unit_indexes = tuple(range(total_units))
    index_batches: list[tuple[int, ...]] = []
    offset = 0
    for batch in batches:
        index_batches.append(all_unit_indexes[offset : offset + len(batch)])
        offset += len(batch)
    assert offset == total_units

    all_simulation_results: list[SimulationResult] = []
    completed_count = 0

    with executor_cls(
        max_workers=effective_workers,
        initializer=_initialize_worker,
        initargs=(plan.experiment_definition, plan.units, simulation_executor),
    ) as executor:
        futures = [
            executor.submit(
                _worker_execute_index_batch,
                index_batch,
                summary_only,
            )
            for index_batch in index_batches
        ]

        for future in futures:
            if config.timeout_seconds is not None:
                batch_results = future.result(timeout=config.timeout_seconds)
            else:
                batch_results = future.result()

            all_simulation_results.extend(batch_results)
            completed_count += len(batch_results)
            if progress_callback is not None:
                progress_callback(completed_count, total_units)

    # Reconstruct Engine SimulationContexts for engine ExperimentRun
    sim_exec = simulation_executor or _create_default_simulation_executor()
    research_executor = ResearchExecutor(sim_exec)

    contexts = [
        research_executor._create_context_for_unit(plan.experiment_definition, unit)
        for unit in plan.units
    ]
    engine_def = EngineExperimentDefinition(
        name=plan.experiment_definition.name,
        description=plan.experiment_definition.description,
        simulation_contexts=tuple(contexts),
    )
    experiment_run = ExperimentRun(
        definition=engine_def,
        simulation_results=tuple(all_simulation_results),
    )
    return ResearchExecutionResult(plan=plan, experiment_result=experiment_run)


class ParallelExecutor:
    """Execute research studies with multi-core support."""

    def __init__(
        self,
        config: ExecutionConfig | None = None,
        simulation_executor: SimulationExecutor | None = None,
    ) -> None:
        """Initialize ParallelExecutor with execution configuration."""
        self.config = config if config is not None else ExecutionConfig()
        self.simulation_executor = simulation_executor

    def execute_plan(
        self,
        plan: ResearchPlan,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> ResearchExecutionResult:
        """Execute a research plan in parallel.

        Parameters
        ----------
        plan:
            Immutable research plan to execute.
        progress_callback:
            Optional callback(completed, total) for progress updates.

        Returns
        -------
        ResearchExecutionResult
            Aggregated execution results.
        """
        return parallel_execute(
            plan=plan,
            config=self.config,
            simulation_executor=self.simulation_executor,
            progress_callback=progress_callback,
        )
