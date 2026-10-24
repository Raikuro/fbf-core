"""Simulation execution engine, runners, and execution strategies."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

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
from fbf.core.study.builder import BuiltStudy
from fbf.core.study.plan import ResearchPlan

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

    from fbf.core.execution.pipeline.simulation_context import SimulationContext
    from fbf.core.execution.strategies.numba_executor import GlidepathGFKey


def sequential_execute(*args: Any, **kwargs: Any) -> ResearchExecutionResult:
    """Execute through the public sequential Core operation."""
    from fbf.core.execution.strategies.parallel_executor import sequential_execute as implementation

    return implementation(*args, **kwargs)


def parallel_execute(*args: Any, **kwargs: Any) -> ResearchExecutionResult:
    """Execute through the public parallel Core operation."""
    from fbf.core.execution.strategies.parallel_executor import parallel_execute as implementation

    return implementation(*args, **kwargs)


def __getattr__(name: str) -> Any:
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
    It is currently implemented with Numba.  Execution is fail-closed: workloads
    the Numba kernels cannot execute raise ``UnsupportedConfigurationError``
    rather than falling back to another engine.

    When no backend is specified (the default ``None``), AUTO dispatch selects
    the same Numba executor appropriate to the workload and raises if no Numba
    kernel supports it.
    """

    FAST = "fast"


class ExecutionStrategy(StrEnum):
    """Execution strategy selection.

    ``AUTO`` selects the Numba executor appropriate to the workload without
    consulting host resources.  It is the default and always resolves to
    single-process execution.

    ``SEQUENTIAL`` explicitly forces single-process execution.

    ``PARALLEL`` explicitly requests multiprocessing.  Not supported by the
    Numba backend; raises ``ValueError``.
    """

    AUTO = "auto"
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


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
        dispatch: the system selects the Numba executor appropriate to the
        workload and raises if no Numba kernel supports it.  ``FAST``
        explicitly requests the optimized float64 backend (currently Numba).
        Default is ``None``.
    strategy:
        Execution strategy (``AUTO``, ``SEQUENTIAL``, or ``PARALLEL``).
        ``PARALLEL`` is not supported by the ``FAST`` backend.
        Default is ``AUTO``.
    workers:
        Retained for API compatibility.  Ignored: the Numba backend always
        executes sequentially.
    batch_size:
        Retained for API compatibility.  Ignored: the Numba backend always
        executes sequentially.
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
    """AUTO dispatch: select the validated Numba executor for the workload.

    Returns the SimulationExecutor for the selected workload.  Plans made
    entirely of Part 52, Part 49, or Part 49 buy-and-hold units use the
    dedicated executor for that workload.  Any other plan is admitted only
    when every unit is eligible for the generic Numba kernels, which may mix
    generic policy families in one executor.  Otherwise
    ``UnsupportedConfigurationError`` is raised.
    """
    try:
        import numba as _numba_mod  # noqa: F401
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Execution requires the optional Numba dependency. "
            "Install it with: pip install fbf-core[numba]"
        ) from exc

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

    from fbf.core.execution.strategies.numba_executor import (
        NumbaSimulationExecutor,
        is_numba_context_eligible,
    )

    if all(is_numba_context_eligible(ctx) for ctx in contexts):
        return NumbaSimulationExecutor(
            profiler=profiler,
            glidepath_gf_cache=glidepath_gf_cache,
            materialize_timeline=materialize_timeline,
        )

    raise UnsupportedConfigurationError(
        "No Numba executor supports this plan. Supported workloads are "
        "Part 52, Part 49, fixed-real, constant-nominal, escalating, "
        "buy-and-hold, and glidepath policies with a monthly withdrawal "
        "frequency (escalating supports monthly or annual); debt and LTV "
        "configurations belong to the dedicated Part 49/52 executors."
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

        # A plan containing any Part 52 workload must be entirely
        # Part52-Numba-eligible, otherwise the request is rejected rather than
        # routed to another engine.
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
                    "(Part 52 combined with other policies), ANNUAL frequency, "
                    "and schedule-less Part 52 configurations without a fixed "
                    "interest_rate are unsupported by the FAST backend."
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
                    "FAST backend."
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
                    "escalating, buy-and-hold, and glidepath policies when the "
                    "generic kernels' dataset, portfolio, and value invariants "
                    "hold; non-escalating generic withdrawals require monthly "
                    "frequency; debt and LTV configurations belong to the "
                    "dedicated Part 49/52 executors."
                )

            sim_executor = NumbaSimulationExecutor(
                profiler=profiler,
                glidepath_gf_cache=opt.glidepath_gf_cache,
                materialize_timeline=opt.materialize_timeline,
            )
    return sim_executor


def _validate_execution_strategy(opt: ExecutionOptions) -> None:
    """Reject unsupported execution strategies before dispatch."""
    if opt.strategy == ExecutionStrategy.PARALLEL:
        raise ValueError(
            "The Numba backend does not support parallel execution. "
            "Use strategy=ExecutionStrategy.AUTO or "
            "strategy=ExecutionStrategy.SEQUENTIAL instead."
        )


def execute_study_plan(
    plan: BuiltStudy,
    options: ExecutionOptions | None = None,
) -> ResearchExecutionResult:
    """High-level application service to execute a study plan.

    The ``profiler`` in ``options`` (default: ``NoOpProfiler``) is resolved
    once and propagated to the underlying sequential or parallel execution.
    When an ``ExecutionProfiler`` is provided, phase timings and metrics
    are recorded and accessible via ``options.profiler.get_report()``.

    Backend and strategy are read from ``options.backend`` and
    ``options.strategy``.  ``PARALLEL`` is unsupported and raises
    ``ValueError``.

    Backend selection (``options.backend``):

    - ``None`` (default): AUTO dispatch selects the Numba executor appropriate
      to the workload.
    - ``FAST``: explicitly request the optimized Numba backend.

    Strategy selection (``options.strategy``):

    - ``AUTO``: resolves to sequential.
    - ``SEQUENTIAL``: force single-process execution.
    - ``PARALLEL``: multiprocessing is not supported by the Numba backend;
      raises ``ValueError``.
    """
    opt = options or ExecutionOptions()
    built = plan
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
    _validate_execution_strategy(opt)
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
    plan: BuiltStudy,
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
    built = plan
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

        _validate_execution_strategy(opt)

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
    "UnsupportedConfigurationError",
    "NumbaSimulationExecutor",
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
