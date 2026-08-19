"""Reference horizon chaining for prefix-consistent datasets.

Executor that reuses a longest-horizon reference Decimal execution to derive
shorter-horizon results for eligible, prefix-consistent context families. The
canonical reference engine remains untouched; this executor delegates every
non-prefix evaluation to the standard engine path.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Money
from fbf.core.domain.model.portfolio import Portfolio
from fbf.core.domain.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from fbf.core.execution.pipeline.executor import SimulationExecutor
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    ExperimentRun,
    SimulationResult,
    SimulationStatistics,
    SimulationTimeline,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.result import ResearchExecutionResult
from fbf.core.execution.strategies.parallel_executor import (
    _create_default_simulation_executor,
    default_max_workers,
    parallel_execute,
)
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan

# Memory-safety budget for the CLI's chained Reference dispatch. Each completed
# chained result materializes ~0.37 MiB of timeline payload per unit, so a slice
# of ``workers * _CHAINED_MAX_UNITS_PER_WORKER`` units keeps per-worker residency
# under ~1 GiB (e.g. 16 workers x 2048 units ~ 12 GiB peak aggregate, inside the
# documented 15 GiB host) while never splitting a cohort (horizon chaining is
# preserved exactly). Whole-plan materialization would need ~110 GiB.
_CHAINED_MAX_UNITS_PER_WORKER = 2048


@dataclass(frozen=True)
class ReferenceChainingReport:
    logical_units: int
    chained_groups: int
    longest_path_evaluations: int
    derived_results: int
    independent_evaluations: int
    month_work: int


def _dataset_is_identity_prefix(
    candidate: SimulationContext,
    longest: SimulationContext,
) -> bool:
    candidate_snapshots = candidate.dataset.snapshots
    longest_snapshots = longest.dataset.snapshots
    if len(candidate_snapshots) > len(longest_snapshots):
        return False
    return all(a is b for a, b in zip(candidate_snapshots, longest_snapshots, strict=False))


def _dataset_is_identity_prefix_memo(
    candidate: SimulationContext,
    longest: SimulationContext,
    memo: dict[tuple[int, int], bool],
) -> bool:
    key = (id(candidate.dataset), id(longest.dataset))
    result = memo.get(key)
    if result is None:
        result = _dataset_is_identity_prefix(candidate, longest)
        memo[key] = result
    return result


def _reference_chaining_group_key(context: SimulationContext) -> tuple[object, ...]:
    allocation = cast(ConstantAllocationPolicy, context.allocation_policy)
    withdrawal = cast(FixedRealWithdrawalPolicy, context.withdrawal_policy)
    return (
        context.start_date,
        allocation.equity_allocation,
        withdrawal.withdrawal_rate,
        context.initial_wealth,
        context.initial_portfolio,
    )


def _unit_horizon_months(plan: ResearchPlan, unit: PlannedSimulationUnit) -> int:
    """Return the effective horizon of *unit* (per-unit, else experiment default)."""
    return (
        unit.horizon_months
        if unit.horizon_months is not None
        else plan.experiment_definition.horizon_months
    )


def _unit_chaining_group_key(
    plan: ResearchPlan, unit: PlannedSimulationUnit
) -> tuple[object, ...]:
    """Return the plan-level chaining group key for *unit*.

    Mirrors ``_reference_chaining_group_key`` on the fields the research
    orchestrator maps into a ``SimulationContext`` (see
    ``ResearchExecutor._create_context_for_unit``): cohort start date, policy
    scalars, experiment initial wealth and the unit's initial portfolio.
    """
    allocation = cast(ConstantAllocationPolicy, unit.allocation_policy)
    withdrawal = cast(FixedRealWithdrawalPolicy, unit.withdrawal_policy)
    return (
        unit.cohort.start_date,
        allocation.equity_allocation,
        withdrawal.withdrawal_rate,
        plan.experiment_definition.initial_wealth,
        unit.initial_portfolio,
    )


def _unit_dataset_is_identity_prefix(
    candidate: PlannedSimulationUnit,
    longest: PlannedSimulationUnit,
) -> bool:
    """Plan-level identity-prefix check on unit datasets (see context variant)."""
    candidate_snapshots = candidate.dataset.snapshots
    longest_snapshots = longest.dataset.snapshots
    if len(candidate_snapshots) > len(longest_snapshots):
        return False
    return all(a is b for a, b in zip(candidate_snapshots, longest_snapshots, strict=False))


def _unit_dataset_is_identity_prefix_memo(
    candidate: PlannedSimulationUnit,
    longest: PlannedSimulationUnit,
    memo: dict[tuple[int, int], bool],
) -> bool:
    key = (id(candidate.dataset), id(longest.dataset))
    result = memo.get(key)
    if result is None:
        result = _unit_dataset_is_identity_prefix(candidate, longest)
        memo[key] = result
    return result


def expected_reference_chaining_report(plan: ResearchPlan) -> ReferenceChainingReport:
    """Compute the chaining report *plan* would produce, without executing.

    Applies exactly the same grouping (``_unit_chaining_group_key``) and dataset
    prefix guard (``_unit_dataset_is_identity_prefix``) as
    :class:`ChainedReferenceSimulationExecutor`, so the report is the
    execution-independent truth for the plan: the longest horizon per family is
    evaluated once through the canonical Reference and every shorter
    prefix-consistent horizon is derived from it.  It is used by the CLI to
    report chaining coverage and by tests to prove that chaining actually
    happens (the executor records the same numbers live).
    """
    groups: dict[tuple[object, ...], list[PlannedSimulationUnit]] = {}
    for unit in plan.units:
        groups.setdefault(_unit_chaining_group_key(plan, unit), []).append(unit)

    prefix_memo: dict[tuple[int, int], bool] = {}
    longest_evaluations = 0
    derived = 0
    independent = 0
    month_work = 0
    for units in groups.values():
        longest_unit = max(units, key=lambda u: _unit_horizon_months(plan, u))
        longest_evaluations += 1
        month_work += _unit_horizon_months(plan, longest_unit)
        for unit in units:
            if unit is longest_unit:
                continue
            if _unit_dataset_is_identity_prefix_memo(unit, longest_unit, prefix_memo):
                derived += 1
            else:
                independent += 1
                month_work += _unit_horizon_months(plan, unit)

    return ReferenceChainingReport(
        logical_units=len(plan.units),
        chained_groups=len(groups),
        longest_path_evaluations=longest_evaluations,
        derived_results=derived,
        independent_evaluations=independent,
        month_work=month_work,
    )


def _compute_portfolio_value(portfolio: Portfolio, market_snapshot: MarketSnapshot) -> Money:
    total = Money.ZERO
    for holding in portfolio.holdings:
        price = market_snapshot.index_levels[holding.asset_class]
        total += Money(holding.units * price, total.currency)
    return total


def _build_derived_result(
    longest_result: SimulationResult,
    longest_horizon: int,
    context: SimulationContext,
) -> SimulationResult:
    if context.horizon_months == longest_horizon:
        return longest_result

    failure_month = longest_result.statistics.failure_month
    prefix = tuple(longest_result.timeline.monthly_results[: context.horizon_months])

    if failure_month is None or context.horizon_months <= failure_month:
        final_wealth = _compute_portfolio_value(
            prefix[-1].portfolio,
            prefix[-1].market_snapshot,
        )
        statistics = SimulationStatistics(
            final_wealth=final_wealth,
            max_drawdown=longest_result.statistics.max_drawdown,
            success=True,
            failure_month=None,
            months_simulated=context.horizon_months,
            execution_time_seconds=0.0,
        )
        timeline = SimulationTimeline(monthly_results=prefix)
        return SimulationResult(timeline=timeline, statistics=statistics)

    # The derived horizon exceeds the failure month: the reference engine records
    # the failure at ``period_index == failure_month``, but the runner breaks out
    # of the pipeline before the MonthlyResultBuilderStep for that month, so the
    # failing month is never written to the timeline.  months_simulated therefore
    # equals failure_month (months 0..failure_month-1), and the final wealth is
    # the residual the reference left on the depleted portfolio.
    prefix = tuple(longest_result.timeline.monthly_results[: failure_month])
    statistics = SimulationStatistics(
        final_wealth=longest_result.statistics.final_wealth,
        max_drawdown=longest_result.statistics.max_drawdown,
        success=False,
        failure_month=failure_month,
        months_simulated=failure_month,
        execution_time_seconds=0.0,
    )
    timeline = SimulationTimeline(monthly_results=prefix)
    return SimulationResult(timeline=timeline, statistics=statistics)


class ChainedReferenceSimulationExecutor(SimulationExecutor):
    """Reference executor with horizon chaining for prefix-consistent datasets."""

    processes_whole_definition = True

    def __init__(
        self,
        reference_executor: SimulationExecutor | None = None,
    ) -> None:
        self._reference = reference_executor or _create_default_simulation_executor()
        self._last_report: ReferenceChainingReport | None = None

    @property
    def chaining_report(self) -> ReferenceChainingReport | None:
        return self._last_report

    def execute(self, definition: EngineExperimentDefinition) -> ExperimentRun:
        key_to_group: dict[tuple[object, ...], int] = {}
        group_contexts: list[list[SimulationContext]] = []
        order: list[tuple[int, int]] = []

        for index, context in enumerate(definition.simulation_contexts):
            key = _reference_chaining_group_key(context)
            if key not in key_to_group:
                key_to_group[key] = len(group_contexts)
                group_contexts.append([])
            group_id = key_to_group[key]
            group_contexts[group_id].append(context)
            order.append((index, group_id))

        results: dict[int, SimulationResult] = {}
        derived_count = 0
        independent_count = 0
        month_work = 0
        prefix_memo: dict[tuple[int, int], bool] = {}

        for contexts in group_contexts:
            longest_ctx = max(contexts, key=lambda c: c.horizon_months)
            longest_result = self._evaluate_reference(longest_ctx)
            longest_horizon = longest_ctx.horizon_months
            month_work += longest_horizon

            for ctx in contexts:
                if ctx is longest_ctx:
                    results[id(ctx)] = longest_result
                    continue
                if _dataset_is_identity_prefix_memo(ctx, longest_ctx, prefix_memo):
                    results[id(ctx)] = _build_derived_result(
                        longest_result, longest_horizon, ctx
                    )
                    derived_count += 1
                else:
                    results[id(ctx)] = self._evaluate_reference(ctx)
                    independent_count += 1
                    month_work += ctx.horizon_months

        ordered_results: list[SimulationResult] = []
        for index, _ in order:
            context = definition.simulation_contexts[index]
            ordered_results.append(results[id(context)])

        self._last_report = ReferenceChainingReport(
            logical_units=len(definition.simulation_contexts),
            chained_groups=len(group_contexts),
            longest_path_evaluations=len(group_contexts),
            derived_results=derived_count,
            independent_evaluations=independent_count,
            month_work=month_work,
        )

        return ExperimentRun(
            definition=definition,
            simulation_results=tuple(ordered_results),
        )

    def _evaluate_reference(self, context: SimulationContext) -> SimulationResult:
        single = EngineExperimentDefinition(
            name=context.experiment_name,
            description=context.experiment_name,
            simulation_contexts=(context,),
        )
        run = self._reference.execute(single)
        return run.simulation_results[0]


# Memory-safe slice dispatch for the CLI's --reference-chained path.
#
# Whole-plan chained materialization holds ~0.37 MiB of timeline payload per
# unit (~110 GiB for the ERN grid), so the CLI never hands the whole plan to a
# single executor call.  It splits the plan into cohort-aligned slices (a cohort
# is never split, so every horizon family stays grouped and the exact month-work
# reduction is preserved) and runs each slice through ``parallel_execute`` with
# the chained executor, then merges results back in original plan order.
_DEFAULT_CHAINED_SLICE_COHORTS = 100


def _slice_plan_units(
    plan: ResearchPlan,
    slice_cohorts: int,
) -> list[tuple[PlannedSimulationUnit, ...]]:
    """Split ``plan.units`` into cohort-aligned slices preserving plan order.

    Relies on the plan being cohort-major ordered (as produced by
    ``materialize_research_plan``), so
    consecutive units sharing a ``start_date`` form one cohort group.
    """
    if slice_cohorts <= 0:
        raise ValueError(f"slice_cohorts must be positive, got {slice_cohorts}")
    cohort_groups: list[list[PlannedSimulationUnit]] = []
    for unit in plan.units:
        if cohort_groups and cohort_groups[-1][0].cohort.start_date == unit.cohort.start_date:
            cohort_groups[-1].append(unit)
        else:
            cohort_groups.append([unit])
    slices: list[tuple[PlannedSimulationUnit, ...]] = []
    for i in range(0, len(cohort_groups), slice_cohorts):
        units: list[PlannedSimulationUnit] = []
        for group in cohort_groups[i : i + slice_cohorts]:
            units.extend(group)
        slices.append(tuple(units))
    return slices


def execute_reference_chained(
    plan: ResearchPlan,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    summary_only: bool = False,
    slice_cohorts: int = _DEFAULT_CHAINED_SLICE_COHORTS,
) -> ResearchExecutionResult:
    """Execute *plan* through the chained Reference executor in cohort slices.

    Each slice is dispatched through ``parallel_execute`` with a shared
    ``ChainedReferenceSimulationExecutor`` and the per-slice results are merged
    back into a single ``ResearchExecutionResult`` preserving original plan
    order and index provenance.  Progress is reported once per completed slice
    with global completed/total counts.
    """
    workers = default_max_workers() if max_workers is None or max_workers <= 0 else max_workers

    slices = _slice_plan_units(plan, slice_cohorts)
    executor = ChainedReferenceSimulationExecutor()

    all_results: list[SimulationResult] = []
    all_contexts: list[SimulationContext] = []
    completed = 0
    total = len(plan.units)

    for slice_units in slices:
        sub_plan = ResearchPlan(
            experiment_definition=plan.experiment_definition,
            units=slice_units,
        )
        sub_result = parallel_execute(
            sub_plan,
            max_workers=workers,
            simulation_executor=executor,
            progress_callback=None,
            summary_only=summary_only,
        )
        all_results.extend(sub_result.experiment_result.simulation_results)
        all_contexts.extend(sub_result.experiment_result.definition.simulation_contexts)
        completed += len(slice_units)
        if progress_callback is not None:
            progress_callback(completed, total)

    engine_def = EngineExperimentDefinition(
        name=plan.experiment_definition.name,
        description=plan.experiment_definition.description,
        simulation_contexts=tuple(all_contexts),
    )
    experiment_run = ExperimentRun(
        definition=engine_def,
        simulation_results=tuple(all_results),
    )
    return ResearchExecutionResult(plan=plan, experiment_result=experiment_run)
