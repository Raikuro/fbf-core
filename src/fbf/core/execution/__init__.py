"""Simulation execution engine, runners, and execution strategies."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from fbf.core.execution.profiling import (
    ExecutionProfiler,
    NoOpProfiler,
    Profiler,
    ProfileReport,
)
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

    ``DEFAULT`` executes with exact Decimal semantics.  It automatically uses
    the optimized fast path when the workload is eligible and falls back to
    the legacy Decimal reference for ineligible contexts.

    ``FAST`` executes with float64 numerical semantics for maximum throughput.
    Currently implemented with Numba; the implementation may evolve without
    changing the public name.
    """

    DEFAULT = "default"
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
# AUTO routing policy for DEFAULT backend
# ---------------------------------------------------------------------------
# The DEFAULT backend benefits from parallelism at meaningful workloads but
# incurs measurable overhead (process creation, IPC, result aggregation) for
# small plans.
#
# The threshold below is the minimum unit count at which the AUTO strategy
# selects parallel execution for the DEFAULT backend, provided that multiple
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
        Execution backend selection.  ``DEFAULT`` uses exact Decimal semantics
        (fast-path with legacy fallback).  ``FAST`` uses float64 semantics
        (currently Numba).  Default is ``DEFAULT``.
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
    """

    backend: ExecutionBackend = ExecutionBackend.DEFAULT
    strategy: ExecutionStrategy = ExecutionStrategy.AUTO
    workers: int | None = None
    batch_size: int | None = None
    progress_callback: ProgressCallback | None = None
    profiler: Profiler = field(default_factory=NoOpProfiler)

    @staticmethod
    def with_profiling(**kwargs: Any) -> ExecutionOptions:
        """Create ExecutionOptions with profiling enabled.

        Convenience factory for consumers that want to collect execution
        profiling data.  Equivalent to::

            ExecutionOptions(profiler=ExecutionProfiler(), **kwargs)
        """
        return ExecutionOptions(profiler=ExecutionProfiler(), **kwargs)


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

    Backend and strategy are read directly from ``options.backend`` and
    ``options.strategy``.  Unsupported combinations (``FAST`` + ``PARALLEL``)
    raise ``ValueError``.

    When ``strategy=AUTO``:

    - ``FAST`` always resolves to sequential (parallel was measured as
      counterproductive at all scales).
    - ``DEFAULT`` selects parallel when the plan has at least
      ``_DEFAULT_PARALLEL_UNIT_THRESHOLD`` units *and* more than one worker
      is available; otherwise sequential.  The ``workers`` option acts as an
      optional resource hint / upper bound, not a directive to parallelize.
    """
    opt = options or ExecutionOptions()
    built = plan if isinstance(plan, BuiltStudy) else plan.built_study
    profiler = opt.profiler

    profiler.start("total")

    backend = opt.backend
    strategy = opt.strategy

    # --- Backend selection ---
    sim_executor: Any = None
    if backend == ExecutionBackend.FAST:
        try:
            from fbf.core.execution.strategies.numba_executor import NumbaSimulationExecutor
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "FAST backend requires the optional Numba dependency. "
                "Install it with: pip install fbf-core[numba]"
            ) from exc
        # Verify numba is actually importable (the executor imports it lazily
        # inside execute(); fail early with a clear message rather than a
        # confusing error deep in the execution path).
        try:
            import numba as _numba_mod  # noqa: F401
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "FAST backend requires the optional Numba dependency. "
                "Install it with: pip install fbf-core[numba]"
            ) from exc
        sim_executor = NumbaSimulationExecutor(profiler=profiler)
    elif backend == ExecutionBackend.DEFAULT:
        from fbf.core.execution.strategies.fast_path import FastPathSimulationExecutor

        sim_executor = FastPathSimulationExecutor(profiler=profiler)

    # --- Strategy selection ---
    # ``workers`` is an optional resource hint, not a strategy directive.
    # When not provided, the execution layer inspects host capabilities.
    workers = opt.workers if opt.workers is not None else kwargs.get("workers")

    if strategy == ExecutionStrategy.SEQUENTIAL:
        use_parallel = False
    elif strategy == ExecutionStrategy.PARALLEL:
        if backend == ExecutionBackend.FAST:
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
        else:
            # DEFAULT: workload-aware routing.
            total_units = len(built.plan.units)
            available_workers = workers if workers is not None else min(8, os.cpu_count() or 1)
            use_parallel = (
                total_units >= _DEFAULT_PARALLEL_UNIT_THRESHOLD
                and available_workers > 1
            )

    if use_parallel:
        result = parallel_execute(
            plan=built.plan,
            max_workers=workers,
            simulation_executor=sim_executor,
            progress_callback=opt.progress_callback,
            profiler=profiler,
        )
    else:
        result = sequential_execute(
            plan=built.plan,
            simulation_executor=sim_executor,
            progress_callback=opt.progress_callback,
            profiler=profiler,
        )

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
]
