"""Simulation execution engine, runners, and execution strategies."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import numpy as np
from numpy.typing import NDArray

from fbf.core.execution.deterministic import (
    DeterministicResult,
    DeterministicTrajectory,
    execute_deterministic_trajectory,
)
from fbf.core.execution.errors import UnsupportedConfigurationError
from fbf.core.execution.executor import ResearchExecutor
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
from fbf.core.execution.slicing import iter_cohort_slices
from fbf.core.execution.strategies.fast_path import FastPathValidationError
from fbf.core.execution.strategies.numba_executor import GlidepathGFKey
from fbf.core.study.builder import BuiltStudy, StudyPlanResult
from fbf.core.study.plan import ResearchPlan

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
    from fbf.core.execution.reporting import (
        expected_reference_report as implementation,
    )

    return implementation(*args, **kwargs)


def reference_month_work(*args: Any, **kwargs: Any) -> int:
    from fbf.core.execution.reporting import reference_month_work as implementation

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

# Slice targets for the streaming API.  These are memory-control targets, not
# hard bounds: a cohort is never split.  They are validated empirically by the
# isolated memory benchmark.
_DEFAULT_SUMMARY_SLICE_UNITS: int = 20_000
_DEFAULT_MATERIALIZED_SLICE_UNITS: int = 500


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
    materialize_timeline:
        When ``True``, the optimized (Numba) executors reconstruct the full
        per-month ``SimulationTimeline`` for every unit instead of returning
        empty timelines.  This is opt-in because it increases the aggregation
        cost and memory footprint substantially.  Mutually exclusive with
        ``summary_only``.  Default is ``False``.
    max_materialized_units:
        Safety limit for full-plan execution when ``materialize_timeline`` is
        enabled.  Plans above this unit count raise
        ``UnsupportedConfigurationError``; use ``iter_execute_study_plan`` for
        bounded, slice-at-a-time processing.  ``None`` disables the guard.
        Default is ``1_000``.
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
    materialize_timeline: bool = False
    max_materialized_units: int | None = 1_000

    def __post_init__(self) -> None:
        if self.materialize_timeline and self.summary_only:
            raise ValueError(
                "ExecutionOptions.summary_only and materialize_timeline are "
                "mutually exclusive: summary_only strips the timelines that "
                "materialize_timeline requests."
            )
        if self.max_materialized_units is not None and (
            self.max_materialized_units <= 0
        ):
            raise ValueError(
                "ExecutionOptions.max_materialized_units must be positive or "
                f"None, got {self.max_materialized_units}"
            )

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
                # Mirror the real execution context exactly: the per-unit
                # horizon is authoritative and falls back to the shared
                # experiment horizon only when the unit predates per-unit
                # horizons.  Keeping this in lockstep is what makes dispatch
                # eligibility agree with executor eligibility.
                horizon_months=(
                    unit.horizon_months
                    if unit.horizon_months is not None
                    else plan.experiment_definition.horizon_months
                ),
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
                debt_interest_rate_is_real=unit.debt_interest_rate_is_real,
            )
            contexts.append(ctx)
        return tuple(contexts)
    return ()


def _auto_select_backend(
    built: Any,
    profiler: Any,
    glidepath_gf_cache: dict[GlidepathGFKey, NDArray[np.float64]] | None = None,
    materialize_timeline: bool = False,
) -> Any:
    """AUTO dispatch: select the best validated backend for the workload.

    Returns the SimulationExecutor for the selected backend.  When numba is
    available and all units are FAST-eligible (Part52, FixedReal, escalating,
    buy-and-hold, or glidepath), the optimized Numba executor is used.
    Otherwise the Decimal fast-path (REFERENCE fallback) is used.
    """
    try:
        import numba as _numba_mod  # noqa: F401
    except ModuleNotFoundError:
        from fbf.core.execution.strategies.fast_path import FastPathSimulationExecutor
        from fbf.core.execution.strategies.parallel_executor import (
            _create_reference_simulation_executor,
        )

        return FastPathSimulationExecutor(
            reference_executor=_create_reference_simulation_executor(),
            profiler=profiler,
        )

    from fbf.core.execution.strategies.part52_numba_executor import (
        is_part52_eligible,
    )

    contexts = _extract_simulation_contexts(built.plan)
    all_part52 = all(is_part52_eligible(ctx) for ctx in contexts)

    if all_part52:
        from fbf.core.execution.strategies.part52_numba_executor import (
            Part52NumbaExecutor,
        )

        return Part52NumbaExecutor(
            profiler=profiler, materialize_timeline=materialize_timeline
        )

    from fbf.core.execution.strategies.part49_numba_executor import (
        is_part49_eligible,
    )

    all_part49 = all(is_part49_eligible(ctx) for ctx in contexts)

    if all_part49:
        from fbf.core.execution.strategies.part49_numba_executor import (
            Part49NumbaExecutor,
        )

        return Part49NumbaExecutor(
            profiler=profiler, materialize_timeline=materialize_timeline
        )

    from fbf.core.execution.strategies.part49_buy_and_hold_numba_executor import (
        is_part49_buy_and_hold_eligible,
    )

    all_part49_buy_and_hold = all(
        is_part49_buy_and_hold_eligible(ctx) for ctx in contexts
    )

    if all_part49_buy_and_hold:
        from fbf.core.execution.strategies.part49_buy_and_hold_numba_executor import (
            Part49BuyAndHoldNumbaExecutor,
        )

        return Part49BuyAndHoldNumbaExecutor(
            profiler=profiler, materialize_timeline=materialize_timeline
        )

    from fbf.core.execution.strategies.fast_path import is_fast_path_eligible
    from fbf.core.execution.strategies.numba_executor import (
        _is_buy_and_hold_eligible,
        _is_escalating_eligible,
        _is_glidepath_eligible,
    )

    all_fixed_real = all(is_fast_path_eligible(ctx) for ctx in contexts)

    if all_fixed_real:
        from fbf.core.execution.strategies.numba_executor import (
            NumbaSimulationExecutor,
        )

        return NumbaSimulationExecutor(
            profiler=profiler, materialize_timeline=materialize_timeline
        )

    all_escalating = all(_is_escalating_eligible(ctx) for ctx in contexts)

    if all_escalating:
        from fbf.core.execution.strategies.numba_executor import (
            NumbaSimulationExecutor,
        )

        return NumbaSimulationExecutor(
            profiler=profiler, materialize_timeline=materialize_timeline
        )

    all_buy_and_hold = all(_is_buy_and_hold_eligible(ctx) for ctx in contexts)

    if all_buy_and_hold:
        from fbf.core.execution.strategies.numba_executor import (
            NumbaSimulationExecutor,
        )

        return NumbaSimulationExecutor(
            profiler=profiler, materialize_timeline=materialize_timeline
        )

    all_glidepath = all(_is_glidepath_eligible(ctx) for ctx in contexts)

    if all_glidepath:
        from fbf.core.execution.strategies.numba_executor import (
            NumbaSimulationExecutor,
        )

        return NumbaSimulationExecutor(
            profiler=profiler,
            glidepath_gf_cache=glidepath_gf_cache,
            materialize_timeline=materialize_timeline,
        )

    from fbf.core.execution.strategies.fast_path import FastPathSimulationExecutor
    from fbf.core.execution.strategies.parallel_executor import (
        _create_reference_simulation_executor,
    )

    # No optimized backend matches the whole workload.  The fast path's
    # ineligible-context fallback is allocation-aware, so a buy-and-hold unit
    # that reaches here is delegated to the buy-and-hold pipeline rather than to
    # the rebalancing default pipeline.
    return FastPathSimulationExecutor(
        reference_executor=_create_reference_simulation_executor(),
        profiler=profiler,
    )


def _select_simulation_executor(
    built: Any,
    opt: ExecutionOptions,
) -> Any:
    """Resolve the backend executor for a complete plan exactly once."""
    profiler = opt.profiler
    backend = opt.backend
    sim_executor: Any = None
    if backend is None:
        # AUTO dispatch: capability-driven routing
        sim_executor = _auto_select_backend(
            built, profiler, opt.glidepath_gf_cache, opt.materialize_timeline
        )
    elif backend == ExecutionBackend.FAST:
        try:
            import numba as _numba_mod  # noqa: F401
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "FAST backend requires the optional Numba dependency. "
                "Install it with: pip install fbf-core[numba]"
            ) from exc

        # FAST guarantees Numba execution: a plan containing any Part 52
        # workload must be entirely Part52-Numba-eligible, otherwise the
        # request is rejected rather than silently routed to the Decimal
        # reference engine.
        from fbf.core.execution.strategies.part49_numba_executor import (
            is_part49_context,
            is_part49_eligible,
        )
        from fbf.core.execution.strategies.part52_numba_executor import (
            is_part52_context,
            is_part52_eligible,
        )

        fast_contexts = _extract_simulation_contexts(built.plan)
        has_part52 = any(is_part52_context(ctx) for ctx in fast_contexts)
        has_part49 = any(is_part49_context(ctx) for ctx in fast_contexts)

        if has_part52:
            if not all(is_part52_eligible(ctx) for ctx in fast_contexts):
                raise UnsupportedConfigurationError(
                    "FAST backend cannot execute this plan on Numba: it contains "
                    "Part 52 workloads that are not Numba-eligible. Mixed plans "
                    "(Part 52 combined with other policies) and schedule-less "
                    "Part 52 configurations without a fixed interest_rate are "
                    "unsupported by the FAST backend. Use backend=AUTO to route "
                    "unsupported workloads through the reference engine."
                )
            from fbf.core.execution.strategies.part52_numba_executor import (
                Part52NumbaExecutor,
            )

            sim_executor = Part52NumbaExecutor(
                profiler=profiler, materialize_timeline=opt.materialize_timeline
            )
        elif has_part49:
            from fbf.core.execution.strategies.part49_buy_and_hold_numba_executor import (
                is_part49_buy_and_hold_eligible,
            )

            if all(is_part49_eligible(ctx) for ctx in fast_contexts):
                from fbf.core.execution.strategies.part49_numba_executor import (
                    Part49NumbaExecutor,
                )

                sim_executor = Part49NumbaExecutor(
                    profiler=profiler, materialize_timeline=opt.materialize_timeline
                )
            elif all(
                is_part49_buy_and_hold_eligible(ctx) for ctx in fast_contexts
            ):
                from fbf.core.execution.strategies.part49_buy_and_hold_numba_executor import (
                    Part49BuyAndHoldNumbaExecutor,
                )

                sim_executor = Part49BuyAndHoldNumbaExecutor(
                    profiler=profiler, materialize_timeline=opt.materialize_timeline
                )
            else:
                raise UnsupportedConfigurationError(
                    "FAST backend cannot execute this plan on Numba: it contains "
                    "Part 49 workloads that are not Numba-eligible. Mixed plans "
                    "(Part 49 combined with other policies) and unsupported "
                    "Part 49 configurations (ANNUAL frequency, non-zero expense "
                    "ratio, explicit multi-asset allocations, an insufficient "
                    "dataset, or no interest-rate source) are unsupported by the "
                    "FAST backend. Use backend=AUTO to route unsupported "
                    "workloads through the reference engine."
                )
        else:
            from fbf.core.execution.strategies.numba_executor import (
                NumbaSimulationExecutor,
                is_numba_context_eligible,
            )

            unsupported = next(
                (
                    ctx
                    for ctx in fast_contexts
                    if not is_numba_context_eligible(ctx)
                ),
                None,
            )
            if unsupported is not None:
                raise UnsupportedConfigurationError(
                    "FAST backend cannot execute this plan on Numba: a context "
                    "is not supported by the generic Numba kernels "
                    f"(cohort={unsupported.cohort!r}, "
                    f"start_date={unsupported.start_date.isoformat()!r}). "
                    "The FAST backend supports fixed-real, constant-nominal, "
                    "escalating, zero-fee buy-and-hold, and glidepath policies "
                    "when the generic kernels' dataset, portfolio, and value "
                    "invariants hold; debt and LTV configurations belong to the "
                    "dedicated Part 49/52 executors. Use backend=AUTO to route "
                    "unsupported workloads through the reference engine."
                )

            sim_executor = NumbaSimulationExecutor(
                profiler=profiler,
                glidepath_gf_cache=opt.glidepath_gf_cache,
                materialize_timeline=opt.materialize_timeline,
                require_all_eligible=True,
            )
    elif backend == ExecutionBackend.REFERENCE:
        from fbf.core.execution.strategies.fast_path import FastPathSimulationExecutor
        from fbf.core.execution.strategies.parallel_executor import (
            _create_reference_simulation_executor,
        )

        sim_executor = FastPathSimulationExecutor(
            reference_executor=_create_reference_simulation_executor(),
            profiler=profiler,
        )
    return sim_executor


def _use_parallel_execution(
    opt: ExecutionOptions,
    workers: int | None,
    sim_executor: Any,
) -> bool:
    """Resolve the execution strategy for a complete plan without side effects."""
    backend = opt.backend
    strategy = opt.strategy
    if strategy == ExecutionStrategy.SEQUENTIAL:
        use_parallel = False
    elif strategy == ExecutionStrategy.PARALLEL:
        from fbf.core.execution.strategies.numba_executor import (
            NumbaSimulationExecutor,
        )
        from fbf.core.execution.strategies.part49_buy_and_hold_numba_executor import (
            Part49BuyAndHoldNumbaExecutor,
        )
        from fbf.core.execution.strategies.part49_numba_executor import (
            Part49NumbaExecutor,
        )
        from fbf.core.execution.strategies.part52_numba_executor import (
            Part52NumbaExecutor,
        )

        if backend == ExecutionBackend.FAST or isinstance(
            sim_executor,
            (
                Part49NumbaExecutor,
                Part49BuyAndHoldNumbaExecutor,
                Part52NumbaExecutor,
                NumbaSimulationExecutor,
            ),
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
            from fbf.core.execution.strategies.part49_buy_and_hold_numba_executor import (
                Part49BuyAndHoldNumbaExecutor,
            )
            from fbf.core.execution.strategies.part49_numba_executor import (
                Part49NumbaExecutor,
            )
            from fbf.core.execution.strategies.part52_numba_executor import (
                Part52NumbaExecutor,
            )

            if isinstance(
                sim_executor,
                (
                    Part49NumbaExecutor,
                    Part49BuyAndHoldNumbaExecutor,
                    Part52NumbaExecutor,
                    NumbaSimulationExecutor,
                ),
            ):
                use_parallel = False
            else:
                # REFERENCE path: use parallel when workers available.
                available_workers = workers if workers is not None else min(8, os.cpu_count() or 1)
                use_parallel = available_workers > 1
        else:
            # REFERENCE: use parallel when workers available.
            available_workers = workers if workers is not None else min(8, os.cpu_count() or 1)
            use_parallel = available_workers > 1
    return use_parallel


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

    if (
        opt.materialize_timeline
        and opt.max_materialized_units is not None
        and len(built.plan.units) > opt.max_materialized_units
    ):
        raise UnsupportedConfigurationError(
            "Full-plan trajectory materialization is potentially "
            f"memory-intensive: the plan has {len(built.plan.units)} units, "
            "above ExecutionOptions.max_materialized_units="
            f"{opt.max_materialized_units}. Use iter_execute_study_plan for "
            "bounded slice-at-a-time processing, or raise/disable "
            "max_materialized_units explicitly if the full result is required."
        )

    profiler.start("total")

    # --- Backend selection ---
    profiler.start("backend_selection")
    sim_executor = _select_simulation_executor(built, opt)
    profiler.stop("backend_selection")

    # --- Strategy selection ---
    profiler.start("strategy_selection")
    # ``workers`` is an optional resource hint, not a strategy directive.
    # When not provided, the execution layer inspects host capabilities.
    workers = opt.workers if opt.workers is not None else kwargs.get("workers")

    use_parallel = _use_parallel_execution(opt, workers, sim_executor)

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


@dataclass(frozen=True, slots=True)
class ExecutionSlice:
    """One contiguous cohort-aligned slice of a streamed execution.

    ``result.plan.units`` are the original unit objects and
    ``result.results`` are positionally aligned with them.  ``start_index`` is
    the global index of the first unit in the complete plan, so callers can
    reconstruct full-plan provenance without retaining every slice.
    """

    start_index: int
    result: ResearchExecutionResult


def iter_execute_study_plan(
    plan: StudyPlanResult | BuiltStudy,
    options: ExecutionOptions | None = None,
    *,
    max_units_per_slice: int | None = None,
) -> Iterator[ExecutionSlice]:
    """Execute a study plan lazily in cohort-aligned slices.

    The backend and executor are resolved once for the complete plan.  Every
    unit is validated before the first slice is yielded, preserving the
    full-plan fail-fast guarantee without retaining translated contexts.  Each
    yielded slice holds only its own results; the iterator never accumulates
    slices internally.

    ``max_units_per_slice`` overrides the default target.  The target is not an
    absolute memory bound: a cohort larger than the target is emitted intact.

    To keep only one slice resident, release the previous slice before advancing
    (for example ``del chunk`` at the end of the loop body).  The iterator drops
    its own reference on resume, but a plain ``for`` loop keeps the previous
    slice bound until the next slice is yielded.
    """
    opt = options or ExecutionOptions()
    built = plan if isinstance(plan, BuiltStudy) else plan.built_study
    profiler = opt.profiler

    if max_units_per_slice is None:
        slice_limit = (
            _DEFAULT_SUMMARY_SLICE_UNITS
            if opt.summary_only
            else _DEFAULT_MATERIALIZED_SLICE_UNITS
        )
    else:
        slice_limit = max_units_per_slice
        if slice_limit <= 0:
            raise ValueError(
                f"max_units_per_slice must be positive, got {slice_limit}"
            )

    profiler.start("total")
    try:
        profiler.start("backend_selection")
        sim_executor = _select_simulation_executor(built, opt)
        profiler.stop("backend_selection")

        workers = opt.workers
        use_parallel = _use_parallel_execution(opt, workers, sim_executor)

        profiler.start("context_translation")
        ResearchExecutor(sim_executor).validate_units(built.plan)
        profiler.stop("context_translation")

        total_units = len(built.plan.units)
        completed = 0
        start_index = 0
        for units in iter_cohort_slices(
            built.plan, max_units_per_slice=slice_limit
        ):
            sub_plan = ResearchPlan(
                experiment_definition=built.plan.experiment_definition,
                units=units,
            )
            if use_parallel:
                slice_result = parallel_execute(
                    plan=sub_plan,
                    max_workers=workers,
                    simulation_executor=sim_executor,
                    progress_callback=None,
                    summary_only=opt.summary_only,
                    profiler=profiler,
                )
            else:
                slice_result = sequential_execute(
                    plan=sub_plan,
                    simulation_executor=sim_executor,
                    progress_callback=None,
                    summary_only=opt.summary_only,
                    profiler=profiler,
                )
            completed += len(units)
            if opt.progress_callback is not None:
                opt.progress_callback(completed, total_units)
            slice_start = start_index
            start_index += len(units)
            yield ExecutionSlice(start_index=slice_start, result=slice_result)
            del slice_result
            del sub_plan
            del units
    finally:
        profiler.stop("total")

__all__ = [
    "DeterministicTrajectory",
    "DeterministicResult",
    "execute_deterministic_trajectory",
    "ExecutionBackend",
    "ExecutionStrategy",
    "ExecutionOptions",
    "ExecutionSlice",
    "execute_study_plan",
    "iter_execute_study_plan",
    "ResearchExecutionResult",
    "parallel_execute",
    "sequential_execute",
    "FastPathSimulationExecutor",
    "FastPathValidationError",
    "UnsupportedConfigurationError",
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
