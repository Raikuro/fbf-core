"""Simulation execution engine, runners, and execution strategies."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import numpy as np
from numpy.typing import NDArray

from fbf.core.execution.profiling import (
    CompositeProfiler,
    CpuProfiler,
    EnhancedProfileReport,
    ExecutionProfiler,
    MemoryProfiler,
    NestedPhaseTiming,
    NoOpProfiler,
    Profiler,
    ProfileReport,
)
from fbf.core.execution.result import ResearchExecutionResult
from fbf.core.execution.strategies.fast_path import FastPathValidationError
from fbf.core.execution.strategies.numba_executor import GlidepathGFKey
from fbf.core.study.builder import BuiltStudy, StudyPlanResult

if TYPE_CHECKING:
    from fbf.core.execution.pipeline.simulation_context import SimulationContext


def sequential_execute(*args: Any, **kwargs: Any) -> ResearchExecutionResult:
    """Execute through the public sequential Core operation."""
    from fbf.core.execution.strategies.parallel_executor import sequential_execute as implementation

    return implementation(*args, **kwargs)


def parallel_execute(*args: Any, **kwargs: Any) -> ResearchExecutionResult:
    """Execute through the public parallel Core operation."""
    from fbf.core.execution.strategies.parallel_executor import parallel_execute as implementation

    return implementation(*args, **kwargs)


def execute_reference(*args: Any, **kwargs: Any) -> ResearchExecutionResult:
    """Execute the public Reference operation."""
    from fbf.core.execution.strategies.reference import (
        execute_reference as implementation,
    )

    return implementation(*args, **kwargs)


def expected_reference_report(*args: Any, **kwargs: Any) -> Any:
    from fbf.core.execution.strategies.reference import (
        expected_reference_report as implementation,
    )

    return implementation(*args, **kwargs)


def reference_month_work(*args: Any, **kwargs: Any) -> int:
    from fbf.core.execution.strategies.fast_path import reference_month_work as implementation

    return implementation(*args, **kwargs)


def fast_path_unit_counts(*args: Any, **kwargs: Any) -> tuple[int, int]:
    from fbf.core.execution.strategies.fast_path import fast_path_unit_counts as implementation

    return implementation(*args, **kwargs)


def expected_report(*args: Any, **kwargs: Any) -> Any:
    from fbf.core.execution.strategies.fast_path import expected_report as implementation

    return implementation(*args, **kwargs)


def run_fast_path_validation(*args: Any, **kwargs: Any) -> Any:
    from fbf.core.execution.strategies.fast_path import run_fast_path_validation as implementation

    return implementation(*args, **kwargs)


def execute_numba(*args: Any, **kwargs: Any) -> ResearchExecutionResult:
    """Execute through the Numba-accelerated backend."""
    from fbf.core.execution.strategies.numba_executor import NumbaSimulationExecutor
    from fbf.core.execution.strategies.parallel_executor import sequential_execute as impl

    kwargs.setdefault("simulation_executor", NumbaSimulationExecutor())
    return impl(*args, **kwargs)


def __getattr__(name: str) -> Any:
    if name == "FastPathSimulationExecutor":
        from fbf.core.execution.strategies.fast_path import FastPathSimulationExecutor

        return FastPathSimulationExecutor
    if name == "NumbaSimulationExecutor":
        from fbf.core.execution.strategies.numba_executor import NumbaSimulationExecutor

        return NumbaSimulationExecutor
    raise AttributeError(name)

ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True)
class ProgressEvent:
    completed_units: int
    total_units: int


class ExecutionBackend(StrEnum):
    """Public execution backend selection.

    ``FAST`` executes with float64 numerical semantics for maximum throughput.
    Currently implemented with Numba; the implementation may evolve without
    changing the public name.

    ``REFERENCE`` executes with exact Decimal semantics.  It is the
    authoritative reference implementation against which optimized backends
    are validated.  Used for validation, debugging, oracle comparisons,
    and regression testing.

    When no backend is specified (the default ``None``), the AUTO dispatch
    selects the best validated backend for the workload: FAST when all units
    are eligible, REFERENCE otherwise.
    """

    REFERENCE = "reference"
    FAST = "fast"


class ExecutionStrategy(StrEnum):
    """Execution strategy selection.

    ``AUTO`` lets the execution backend choose the appropriate strategy based on
    workload size, backend capabilities, and available host resources.

    ``SEQUENTIAL`` forces single-process execution regardless of workload.

    ``PARALLEL`` explicitly requests multiprocessing.  Not supported by the
    ``FAST`` backend; raises ``ValueError`` if combined with ``FAST``.
    """

    AUTO = "auto"
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


# ---------------------------------------------------------------------------
# AUTO routing policy for REFERENCE backend
# ---------------------------------------------------------------------------
# The REFERENCE backend benefits from parallelism at meaningful workloads but
# incurs measurable overhead (process creation, IPC, result aggregation) for
# small plans.
#
# The threshold below is the minimum unit count at which the AUTO strategy
# selects parallel execution for the REFERENCE backend, provided that multiple
# workers are available.
#
# Measured crossover on the reference development host (4 workers, 120-month
# horizon, Fast Path Decimal):
#
#   100 units:  0.97x  (parallel neutral)
#   200 units:  0.86x  (parallel slightly slower)
#   300 units:  1.08x  (parallel neutral)
#   400 units:  1.28x  (parallel beneficial)
#   500 units:  1.42x  (parallel clearly beneficial)
#  1000 units:  1.66x
#  5000 units:  2.35x
# 10000 units:  2.43x
#
# The threshold is set conservatively at 500 units — above the measured
# crossover point where parallel execution consistently provides a clear
# benefit.  This is an execution-routing policy, not a backend invariant;
# it may be adjusted as batching, overhead, or host hardware changes.
_DEFAULT_PARALLEL_UNIT_THRESHOLD: int = 500


@dataclass(frozen=True)
class ExecutionOptions:
    """Configuration for study plan execution.

    Attributes
    ----------
    backend:
        Execution backend selection.  ``None`` (the default) enables AUTO
        dispatch: the system selects the best validated backend for the
        workload (FAST when all units are eligible, REFERENCE otherwise).
        ``REFERENCE`` explicitly requests the authoritative Decimal reference
        implementation.  ``FAST`` explicitly requests the optimized float64
        backend (currently Numba).  Default is ``None``.
    strategy:
        Execution strategy (``AUTO``, ``SEQUENTIAL``, or ``PARALLEL``).
        ``PARALLEL`` is not supported by the ``FAST`` backend.
        Default is ``AUTO``.
    workers:
        Number of worker processes.  ``None`` uses the default.
    batch_size:
        Units per batch for parallel dispatch.  ``None`` uses worker-sized
        batches.
    progress_callback:
        Optional callback ``(completed_units, total_units)`` for progress
        reporting.
    profiler:
        Profiler instance for execution timing.  Default is ``NoOpProfiler``
        (zero overhead).  Pass ``ExecutionProfiler()`` to collect timings.
        The profiler is resolved once here and propagated to executors.
    summary_only:
        When ``True``, per-month timelines are stripped from the returned
        results after simulation completes.  Callers that only need
        aggregate statistics (success, failure month, final wealth) avoid
        the cost of serializing hundreds of megabytes of monthly payloads
        through IPC in the parallel path.  The simulation itself is
        unchanged; only the returned ``SimulationResult`` objects carry
        empty timelines.  Default is ``False`` to preserve existing
        behaviour for callers that require full timeline data.
    """

    backend: ExecutionBackend | None = None
    strategy: ExecutionStrategy = ExecutionStrategy.AUTO
    workers: int | None = None
    batch_size: int | None = None
    progress_callback: ProgressCallback | None = None
    profiler: Profiler = field(default_factory=NoOpProfiler)
    summary_only: bool = False
    # Optional shared glidepath growth-factor cache for persistent caching
    # across multiple execute_study_plan invocations within a single bisection search.
    glidepath_gf_cache: Any = field(default=None)

    @staticmethod
    def with_profiling(**kwargs: Any) -> ExecutionOptions:
        """Create ExecutionOptions with profiling enabled.

        Convenience factory for consumers that want to collect execution
        profiling data.  Equivalent to::

            ExecutionOptions(profiler=ExecutionProfiler(), **kwargs)
        """
        return ExecutionOptions(profiler=ExecutionProfiler(), **kwargs)


def _extract_simulation_contexts(
    plan: Any,
) -> tuple[SimulationContext, ...]:
    """Extract SimulationContext objects from a plan for eligibility checking.

    This is a lightweight check that creates minimal contexts to test
    eligibility without running the full execution pipeline.
    """
    from fbf.core.execution.pipeline.simulation_context import (
        SimulationContext,
    )

    if hasattr(plan, "units"):
        contexts = []
        for unit in plan.units:
            ctx = SimulationContext(
                experiment_name="eligibility_check",
                cohort=str(unit.cohort.start_date),
                start_date=unit.cohort.start_date,
                horizon_months=unit.horizon_months or 360,
                initial_wealth=plan.experiment_definition.initial_wealth,
                initial_portfolio=unit.initial_portfolio,
                dataset=unit.dataset,
                allocation_policy=unit.allocation_policy,
                withdrawal_policy=unit.withdrawal_policy,
                final_value_target=unit.final_value_target,
                loan_draw_rate=unit.loan_draw_rate,
                interest_rate=unit.interest_rate,
                interest_rate_schedule=unit.interest_rate_schedule,
                ltv_limit=unit.ltv_limit,
                ltv_enforcement=unit.ltv_enforcement,
                expense_ratio=unit.expense_ratio,
            )
            contexts.append(ctx)
        return tuple(contexts)
    return ()


def _auto_select_backend(
    built: Any,
    profiler: Any,
    glidepath_gf_cache: dict[GlidepathGFKey, NDArray[np.float64]] | None = None,
) -> Any:
    """AUTO dispatch: select the best validated backend for the workload.

    Returns the SimulationExecutor for the selected backend.  When numba is
    available and all units are FAST-eligible (Part52, FixedReal, or glidepath),
    the optimized Numba executor is used.  Otherwise the Decimal fast-path
    (REFERENCE fallback) is used.
    """
    try:
        import numba as _numba_mod  # noqa: F401
    except ModuleNotFoundError:
        from fbf.core.execution.strategies.fast_path import FastPathSimulationExecutor

        return FastPathSimulationExecutor(profiler=profiler)

    from fbf.core.execution.strategies.part52_numba_executor import (
        is_part52_eligible,
    )

    contexts = _extract_simulation_contexts(built.plan)
    all_part52 = all(is_part52_eligible(ctx) for ctx in contexts)

    if all_part52:
        from fbf.core.execution.strategies.part52_numba_executor import (
            Part52NumbaExecutor,
        )

        return Part52NumbaExecutor(profiler=profiler)

    from fbf.core.execution.strategies.fast_path import is_fast_path_eligible
    from fbf.core.execution.strategies.numba_executor import _is_glidepath_eligible

    all_fixed_real = all(is_fast_path_eligible(ctx) for ctx in contexts)

    if all_fixed_real:
        from fbf.core.execution.strategies.numba_executor import (
            NumbaSimulationExecutor,
        )

        return NumbaSimulationExecutor(profiler=profiler)

    all_glidepath = all(_is_glidepath_eligible(ctx) for ctx in contexts)

    if all_glidepath:
        from fbf.core.execution.strategies.numba_executor import (
            NumbaSimulationExecutor,
        )

        return NumbaSimulationExecutor(
            profiler=profiler,
            glidepath_gf_cache=glidepath_gf_cache,
        )

    from fbf.core.execution.strategies.fast_path import FastPathSimulationExecutor

    return FastPathSimulationExecutor(profiler=profiler)


def execute_study_plan(
    plan: StudyPlanResult | BuiltStudy,
    options: ExecutionOptions | None = None,
    **kwargs: Any,
) -> ResearchExecutionResult:
    """High-level application service to execute a study plan.

    The ``profiler`` in ``options`` (default: ``NoOpProfiler``) is resolved
    once and propagated to the underlying sequential or parallel execution.
    When an ``ExecutionProfiler`` is provided, phase timings and metrics
    are recorded and accessible via ``options.profiler.get_report()``.

    Backend and strategy are read from ``options.backend`` and
    ``options.strategy``.  Unsupported combinations (``FAST`` + ``PARALLEL``)
    raise ``ValueError``.

    Backend selection (``options.backend``):

    - ``None`` (default): AUTO dispatch selects the best validated backend.
      FAST when all units are Part52-eligible or FixedReal-eligible,
      REFERENCE otherwise.
    - ``FAST``: explicitly request the optimized Numba backend.
    - ``REFERENCE``: explicitly request the authoritative Decimal reference.

    Strategy selection (``options.strategy``):

    - ``AUTO``: ``FAST`` always resolves to sequential.  ``REFERENCE`` selects
      parallel when the plan has at least ``_DEFAULT_PARALLEL_UNIT_THRESHOLD``
      units *and* more than one worker is available; otherwise sequential.
    - ``SEQUENTIAL``: force single-process execution.
    - ``PARALLEL``: explicitly request multiprocessing.  Not supported by
      ``FAST``; raises ``ValueError``.
    """
    opt = options or ExecutionOptions()
    built = plan if isinstance(plan, BuiltStudy) else plan.built_study
    profiler = opt.profiler

    profiler.start("total")

    backend = opt.backend
    strategy = opt.strategy

    # --- Backend selection ---
    profiler.start("backend_selection")
    sim_executor: Any = None
    if backend is None:
        # AUTO dispatch: capability-driven routing
        sim_executor = _auto_select_backend(built, profiler, opt.glidepath_gf_cache)
    elif backend == ExecutionBackend.FAST:
        try:
            import numba as _numba_mod  # noqa: F401
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "FAST backend requires the optional Numba dependency. "
                "Install it with: pip install fbf-core[numba]"
            ) from exc

        # Check if the workload is Part52-eligible for the dedicated kernel
        from fbf.core.execution.strategies.part52_numba_executor import (
            is_part52_eligible,
        )

        all_part52 = all(
            is_part52_eligible(ctx)
            for ctx in _extract_simulation_contexts(built.plan)
        )

        if all_part52:
            from fbf.core.execution.strategies.part52_numba_executor import (
                Part52NumbaExecutor,
            )

            sim_executor = Part52NumbaExecutor(profiler=profiler)
        else:
            from fbf.core.execution.strategies.numba_executor import (
                NumbaSimulationExecutor,
            )

            sim_executor = NumbaSimulationExecutor(
                profiler=profiler,
                glidepath_gf_cache=opt.glidepath_gf_cache,
            )
    elif backend == ExecutionBackend.REFERENCE:
        from fbf.core.execution.strategies.fast_path import FastPathSimulationExecutor

        sim_executor = FastPathSimulationExecutor(profiler=profiler)
    profiler.stop("backend_selection")

    # --- Strategy selection ---
    profiler.start("strategy_selection")
    # ``workers`` is an optional resource hint, not a strategy directive.
    # When not provided, the execution layer inspects host capabilities.
    workers = opt.workers if opt.workers is not None else kwargs.get("workers")

    if strategy == ExecutionStrategy.SEQUENTIAL:
        use_parallel = False
    elif strategy == ExecutionStrategy.PARALLEL:
        from fbf.core.execution.strategies.numba_executor import (
            NumbaSimulationExecutor,
        )
        from fbf.core.execution.strategies.part52_numba_executor import (
            Part52NumbaExecutor,
        )

        if backend == ExecutionBackend.FAST or isinstance(
            sim_executor, (Part52NumbaExecutor, NumbaSimulationExecutor)
        ):
            raise ValueError(
                "FAST backend does not support parallel execution. "
                "Use strategy=ExecutionStrategy.AUTO or "
                "strategy=ExecutionStrategy.SEQUENTIAL instead."
            )
        use_parallel = True
    else:  # AUTO
        if backend == ExecutionBackend.FAST:
            # Parallel was measured as counterproductive for Numba at all scales.
            use_parallel = False
        elif backend is None:
            # AUTO dispatch selected a backend; FAST always sequential.
            from fbf.core.execution.strategies.numba_executor import (
                NumbaSimulationExecutor,
            )
            from fbf.core.execution.strategies.part52_numba_executor import (
                Part52NumbaExecutor,
            )

            if isinstance(sim_executor, (Part52NumbaExecutor, NumbaSimulationExecutor)):
                use_parallel = False
            else:
                # REFERENCE path: use parallel when workers available.
                available_workers = workers if workers is not None else min(8, os.cpu_count() or 1)
                use_parallel = available_workers > 1
        else:
            # REFERENCE: use parallel when workers available.
            available_workers = workers if workers is not None else min(8, os.cpu_count() or 1)
            use_parallel = available_workers > 1

    if use_parallel:
        profiler.stop("strategy_selection")
        profiler.start("parallel_dispatch")
        result = parallel_execute(
            plan=built.plan,
            max_workers=workers,
            simulation_executor=sim_executor,
            progress_callback=opt.progress_callback,
            summary_only=opt.summary_only,
            profiler=profiler,
        )
        profiler.stop("parallel_dispatch")
    else:
        profiler.stop("strategy_selection")
        profiler.start("sequential_dispatch")
        result = sequential_execute(
            plan=built.plan,
            simulation_executor=sim_executor,
            progress_callback=opt.progress_callback,
            summary_only=opt.summary_only,
            profiler=profiler,
        )
        profiler.stop("sequential_dispatch")

    profiler.record("total_units", len(built.plan.units))
    profiler.stop("total")

    return result


__all__ = [
    "ExecutionBackend",
    "ExecutionStrategy",
    "ExecutionOptions",
    "execute_study_plan",
    "ResearchExecutionResult",
    "parallel_execute",
    "sequential_execute",
    "FastPathSimulationExecutor",
    "FastPathValidationError",
    "NumbaSimulationExecutor",
    "reference_month_work",
    "execute_reference",
    "execute_numba",
    "expected_reference_report",
    "fast_path_unit_counts",
    "expected_report",
    "run_fast_path_validation",
    "ProgressCallback",
    "ProgressEvent",
    "Profiler",
    "NoOpProfiler",
    "ExecutionProfiler",
    "ProfileReport",
    "NestedPhaseTiming",
    "EnhancedProfileReport",
    "CpuProfiler",
    "MemoryProfiler",
    "CompositeProfiler",
]
