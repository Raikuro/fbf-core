"""Numba-accelerated executor with horizon derivation.

Executor that evaluates eligible contexts (ConstantAllocationPolicy +
FixedRealWithdrawalPolicy) using the Numba scalar kernel, reusing a
longest-horizon evaluation to derive shorter-horizon results for
prefix-consistent context families.

The canonical reference engine remains untouched; this executor delegates
every non-eligible context to the standard engine path.

Architecture
------------
The Numba kernel computes the same scalar recurrence as the fast path::

    V_0      = value(initial_portfolio @ snapshot_0)
    C        = V_0 * withdrawal_rate / 12          (constant real withdrawal)
    g_m      = sum_j w_j * P_{j,m+1} / P_{j,m}   (varies by month)
    V_{m+1}  = (V_m - C) * g_m

Horizon derivation works by replaying the recurrence from the initial
value through the first H months of growth factors, where H is the
shorter horizon.  This is valid because all contexts in a group share
identical growth factors, initial value, and withdrawal amount.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import cast

from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import FixedRealWithdrawalPolicy
from fbf.core.execution.pipeline.executor import SimulationExecutor
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    ExperimentRun,
    SimulationResult,
    SimulationStatistics,
    SimulationTimeline,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.fast_path import (
    _group_key,
    _index_series,
    _weights_by_class,
    is_fast_path_eligible,
)
from fbf.core.execution.strategies.parallel_executor import (
    _create_default_simulation_executor,
)


@dataclass(frozen=True)
class NumbaReport:
    """Execution report for a single Numba executor run."""

    logical_units: int
    groups: int
    longest_path_evaluations: int
    derived_results: int
    independent_evaluations: int
    month_work: int


def _is_numba_eligible(context: SimulationContext) -> bool:
    """Return True when *context* can use the Numba backend.

    Same eligibility criteria as the fast path: ConstantAllocationPolicy
    + FixedRealWithdrawalPolicy, sufficient dataset, two-asset portfolio.
    """
    return is_fast_path_eligible(context)


class NumbaSimulationExecutor(SimulationExecutor):
    """Numba-accelerated executor with horizon derivation.

    Contexts sharing the same cohort start date, initial wealth, initial
    portfolio, allocation weights and withdrawal rate are evaluated together:
    the longest horizon is run once through the Numba kernel and every
    shorter horizon is derived by replaying the recurrence from the same
    initial value and growth factors.

    Non-eligible contexts are delegated to the reference Decimal executor.

    Advertises ``processes_whole_definition = True`` so progress wrappers
    pass the full definition through unchanged (preserving group-level
    optimisation).
    """

    processes_whole_definition = True

    def __init__(
        self,
        reference_executor: SimulationExecutor | None = None,
    ) -> None:
        self._reference = reference_executor or _create_default_simulation_executor()
        self._last_report: NumbaReport | None = None

    @property
    def report(self) -> NumbaReport | None:
        """Return the report recorded by the most recent ``execute`` call."""
        return self._last_report

    def execute(self, definition: EngineExperimentDefinition) -> ExperimentRun:
        key_to_group: dict[tuple[object, ...], int] = {}
        group_contexts: list[list[SimulationContext]] = []
        order: list[tuple[int, int]] = []

        for index, context in enumerate(definition.simulation_contexts):
            if not _is_numba_eligible(context):
                order.append((index, -1))
                continue
            key = _group_key(context)
            if key not in key_to_group:
                group_id = len(group_contexts)
                key_to_group[key] = group_id
                group_contexts.append([])
            else:
                group_id = key_to_group[key]
            group_contexts[group_id].append(context)
            order.append((index, group_id))

        results: dict[int, SimulationResult] = {}
        derived_count = 0
        independent_count = 0
        month_work = 0

        for _, contexts in enumerate(group_contexts):
            longest_ctx = max(contexts, key=lambda c: c.horizon_months)
            longest_horizon = longest_ctx.horizon_months
            month_work += longest_horizon

            # --- data preparation (shared across the group) ---
            weights = _weights_by_class(longest_ctx)
            series = _index_series(longest_ctx)
            asset_classes = tuple(series.keys())

            # Compute initial portfolio value from holdings x prices at snapshot[0].
            initial_snapshot = longest_ctx.dataset[0]
            total = sum(
                holding.units * initial_snapshot.index_levels[holding.asset_class]
                for holding in longest_ctx.initial_portfolio.holdings
            )
            v0 = float(total)
            withdrawal_policy = cast(FixedRealWithdrawalPolicy, longest_ctx.withdrawal_policy)
            c = v0 * float(withdrawal_policy.withdrawal_rate) / 12.0

            # Precompute growth factors at the longest horizon.
            from fbf.core.execution.strategies.numba_kernel import compute_growth_factors

            growth_factors_arr = compute_growth_factors(
                asset_classes, weights, series, longest_horizon
            )
            growth_list = growth_factors_arr.tolist()

            # --- Numba kernel: one call per group ---
            from fbf.core.execution.strategies.numba_kernel import _simulate_trajectory

            _final_val, _kernel_success, fail_month, _ = _simulate_trajectory(
                growth_factors_arr, v0, c, longest_horizon
            )
            # Track both pre-withdrawal and post-withdrawal values for horizon derivation.
            pre_values = [0.0] * longest_horizon
            post_values = [0.0] * longest_horizon
            value = v0
            for m in range(longest_horizon):
                if value < c:
                    pre_values[m] = 0.0
                    post_values[m] = 0.0
                    break
                pre_values[m] = value
                post_values[m] = value - c
                value = (value - c) * growth_list[m] if m < longest_horizon - 1 else value - c

            # --- derive per-context results ---
            derived_cache: dict[tuple[int, object], SimulationResult] = {}
            for ctx in contexts:
                horizon = ctx.horizon_months
                cache_key = (horizon, ctx.final_value_target)
                if cache_key in derived_cache:
                    results[id(ctx)] = derived_cache[cache_key]
                    continue

                if fail_month is not None and 0 <= fail_month < horizon:
                    success = False
                    failure_month = fail_month
                    final_value = 0.0
                    months_simulated = fail_month
                else:
                    # Post-withdrawal value at the last simulated month,
                    # matching the reference engine's final wealth semantics.
                    final_value = post_values[horizon - 1]
                    success = True
                    failure_month = None
                    months_simulated = horizon

                final_wealth = _money(final_value)

                base = SimulationResult(
                    timeline=SimulationTimeline(monthly_results=()),
                    statistics=SimulationStatistics(
                        final_wealth=final_wealth,
                        max_drawdown=0.0,
                        success=success,
                        failure_month=failure_month,
                        months_simulated=months_simulated,
                        execution_time_seconds=0.0,
                    ),
                )
                result = _apply_fv_check(base, ctx)
                derived_cache[cache_key] = result
                results[id(ctx)] = result
                if ctx is not longest_ctx:
                    derived_count += 1

        # Assemble results in original definition order.
        ordered_results: list[SimulationResult] = []
        for index, group_id in order:
            if group_id == -1:
                context = definition.simulation_contexts[index]
                single = EngineExperimentDefinition(
                    name=definition.name,
                    description=definition.description,
                    simulation_contexts=(context,),
                )
                run = self._reference.execute(single)
                ordered_results.append(run.simulation_results[0])
                independent_count += 1
                month_work += context.horizon_months
            else:
                ordered_results.append(results[id(definition.simulation_contexts[index])])

        self._last_report = NumbaReport(
            logical_units=len(definition.simulation_contexts),
            groups=len(group_contexts),
            longest_path_evaluations=len(group_contexts),
            derived_results=derived_count,
            independent_evaluations=independent_count,
            month_work=month_work,
        )

        return ExperimentRun(definition=definition, simulation_results=tuple(ordered_results))


def _money(value: float) -> Money:
    """Convert a float to a Money object."""
    return Money(Decimal(str(value)), Currency.EUR)


def _apply_fv_check(result: SimulationResult, context: SimulationContext) -> SimulationResult:
    """Return a copy of *result* with the FV check applied for *context*'s target."""
    if context.final_value_target is None:
        return result
    survived = result.statistics.success
    if survived:
        threshold = context.final_value_target * context.initial_wealth.amount
        if result.statistics.final_wealth.amount < threshold:
            survived = False
    if survived == result.statistics.success:
        return result
    statistics = SimulationStatistics(
        final_wealth=result.statistics.final_wealth,
        max_drawdown=result.statistics.max_drawdown,
        success=survived,
        failure_month=None if survived else context.horizon_months,
        months_simulated=result.statistics.months_simulated,
        execution_time_seconds=result.statistics.execution_time_seconds,
    )
    return SimulationResult(
        timeline=result.timeline,
        statistics=statistics,
    )
