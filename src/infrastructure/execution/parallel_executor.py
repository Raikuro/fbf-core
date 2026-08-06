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

from engine.application.executor import SimulationExecutor
from engine.application.pipeline import SimulationPipeline
from engine.application.runner import SimulationRunner
from engine.application.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    ExperimentRun,
    SimulationResult,
)
from engine.application.steps.allocation_decision_step import AllocationDecisionStep
from engine.application.steps.build_decision_context_step import BuildDecisionContextStep
from engine.application.steps.market_evolution_step import MarketEvolutionStep
from engine.application.steps.monthly_result_builder_step import MonthlyResultBuilderStep
from engine.application.steps.portfolio_rebalance_step import PortfolioRebalanceStep
from engine.application.steps.simulation_state_update_step import SimulationStateUpdateStep
from engine.application.steps.withdrawal_decision_step import WithdrawalDecisionStep
from engine.application.steps.withdrawal_execution_step import WithdrawalExecutionStep
from research.domain.experiment.definition import ExperimentDefinition
from research.domain.plan import PlannedSimulationUnit, ResearchPlan
from research.orchestration.executor import ResearchExecutor
from research.orchestration.result import ResearchExecutionResult


def _create_default_simulation_executor() -> SimulationExecutor:
    """Create a default engine SimulationExecutor with the standard 8-step pipeline."""
    pipeline = SimulationPipeline(
        [
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


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    """Configuration for parallel execution.

    Fields
    ------
    max_workers:
        Maximum number of worker processes/threads (None = os.cpu_count() or 1).
    timeout_seconds:
        Timeout in seconds for execution per task/batch.
    use_processes:
        True to use ProcessPoolExecutor (CPU-bound), False for ThreadPoolExecutor.
    chunk_size:
        Units per task chunk.
    enable_progress:
        True to enable progress tracking callbacks.
    """

    max_workers: int | None = None
    timeout_seconds: float | None = None
    use_processes: bool = True
    chunk_size: int = 1
    enable_progress: bool = True


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


def _worker_execute_batch(
    exp_def: ExperimentDefinition,
    units: Sequence[PlannedSimulationUnit],
    simulation_executor: SimulationExecutor | None = None,
) -> tuple[SimulationResult, ...]:
    """Worker task function executing a batch of units.

    Parameters
    ----------
    exp_def:
        The shared experiment definition.
    units:
        The subset of planned simulation units assigned to this worker.
    simulation_executor:
        Optional custom SimulationExecutor.

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
) -> ResearchExecutionResult:
    """Execute a research plan sequentially with a single worker.

    Parameters
    ----------
    plan:
        The immutable research plan to execute.
    simulation_executor:
        Optional custom SimulationExecutor. If None, default 8-step pipeline executor is used.

    Returns
    -------
    ResearchExecutionResult
        Aggregated result preserving plan-unit provenance.
    """
    sim_exec = simulation_executor or _create_default_simulation_executor()
    research_executor = ResearchExecutor(sim_exec)
    return research_executor.execute(plan)


def parallel_execute(
    plan: ResearchPlan,
    max_workers: int | None = None,
    config: ExecutionConfig | None = None,
    simulation_executor: SimulationExecutor | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
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

    Returns
    -------
    ResearchExecutionResult
        Aggregated result with bit-for-bit equivalence to sequential_execute(plan).
    """
    if config is None:
        config = ExecutionConfig()

    effective_workers = max_workers if max_workers is not None else config.max_workers
    if effective_workers is None or effective_workers <= 0:
        effective_workers = os.cpu_count() or 1

    total_units = len(plan.units)
    if total_units == 0:
        return sequential_execute(plan, simulation_executor=simulation_executor)

    if effective_workers == 1:
        res = sequential_execute(plan, simulation_executor=simulation_executor)
        if progress_callback is not None:
            progress_callback(total_units, total_units)
        return res

    batches = create_work_batches(plan, effective_workers)
    executor_cls = ProcessPoolExecutor if config.use_processes else ThreadPoolExecutor

    all_simulation_results: list[SimulationResult] = []
    completed_count = 0

    with executor_cls(max_workers=effective_workers) as executor:
        futures = [
            executor.submit(
                _worker_execute_batch,
                plan.experiment_definition,
                batch,
                simulation_executor,
            )
            for batch in batches
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
