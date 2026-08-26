"""Numba-accelerated executor with horizon derivation and growth-factor cache.

Executor that evaluates eligible contexts (ConstantAllocationPolicy +
FixedRealWithdrawalPolicy) using the Numba scalar kernel, reusing a
longest-horizon evaluation to derive shorter-horizon results for
prefix-consistent context families.

Growth factors depend only on (start_date, equity_allocation) and are
cached per executor instance to eliminate redundant computation across
groups sharing the same trajectory and allocation.

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

Growth-factor caching
---------------------
Growth factors are a function of (market trajectory, allocation weights)
only.  They do not depend on withdrawal rate, initial wealth, or horizon.
The cache key is (start_date, equity_allocation).  For the ERN workload
(78,255 trajectory groups), this reduces growth-factor construction from
78,255 builds to 8,695 unique builds (88.9% reduction).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray

from fbf.core.domain.model.money import Currency, Money
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
from fbf.core.execution.profiling import NoOpProfiler, Profiler
from fbf.core.execution.strategies.fast_path import (
    _group_key,
    _index_series,
    _weights_by_class,
    is_fast_path_eligible,
)
from fbf.core.execution.strategies.parallel_executor import (
    _create_default_simulation_executor,
)

# Type for growth-factor cache key: (start_date, equity_allocation)
GFKey = tuple[date, Decimal]

# Type for price-float cache key: (start_date, number of price snapshots)
_PriceCacheKey = tuple[date, int]


@dataclass(frozen=True)
class NumbaReport:
    """Execution report for a single Numba executor run."""

    logical_units: int
    groups: int
    longest_path_evaluations: int
    derived_results: int
    independent_evaluations: int
    month_work: int
    gf_cache_hits: int
    gf_cache_misses: int


def _is_numba_eligible(context: SimulationContext) -> bool:
    """Return True when *context* can use the Numba backend.

    Same eligibility criteria as the fast path: ConstantAllocationPolicy
    + FixedRealWithdrawalPolicy, sufficient dataset, two-asset portfolio.
    """
    return is_fast_path_eligible(context)


def _gf_cache_key(context: SimulationContext) -> GFKey:
    """Minimal cache key for growth-factor identity.

    Growth factors depend only on (market trajectory, allocation weights).
    The start_date determines the trajectory prefix; the equity_allocation
    determines the target weights.  Withdrawal rate, initial wealth,
    horizon, and final_value_target do not affect growth factors.
    """
    allocation = cast(ConstantAllocationPolicy, context.allocation_policy)
    return (context.start_date, allocation.equity_allocation)


class NumbaSimulationExecutor(SimulationExecutor):
    """Numba-accelerated executor with horizon derivation and GF cache.

    Contexts sharing the same cohort start date, initial wealth, initial
    portfolio, allocation weights and withdrawal rate are evaluated together:
    the longest horizon is run once through the Numba kernel and every
    shorter horizon is derived by replaying the recurrence from the same
    initial value and growth factors.

    Growth factors are cached by (start_date, equity_allocation) to avoid
    redundant computation across groups sharing the same trajectory and
    allocation but differing in withdrawal rate.

    Non-eligible contexts are delegated to the reference Decimal executor.

    Advertises ``processes_whole_definition = True`` so progress wrappers
    pass the full definition through unchanged (preserving group-level
    optimisation).
    """

    processes_whole_definition = True

    def __init__(
        self,
        reference_executor: SimulationExecutor | None = None,
        profiler: Profiler | None = None,
    ) -> None:
        self._reference = reference_executor or _create_default_simulation_executor()
        self._profiler = profiler or NoOpProfiler()
        self._last_report: NumbaReport | None = None
        self._gf_cache: dict[GFKey, Any] = {}
        self._price_float_cache: dict[_PriceCacheKey, NDArray[np.float64]] = {}
        self._index_series_cache: dict[_PriceCacheKey, dict[object, tuple[Decimal, ...]]] = {}

    @property
    def report(self) -> NumbaReport | None:
        """Return the report recorded by the most recent ``execute`` call."""
        return self._last_report

    @property
    def gf_cache(self) -> dict[GFKey, Any]:
        """Return the current growth-factor cache (read-only for inspection)."""
        return self._gf_cache

    def execute(self, definition: EngineExperimentDefinition) -> ExperimentRun:
        profiler = self._profiler

        # --- Pass 1: group eligible contexts and find max horizon per GF key ---
        profiler.start("numba_grouping")
        key_to_group: dict[tuple[object, ...], int] = {}
        group_contexts: list[list[SimulationContext]] = []
        order: list[tuple[int, int]] = []
        gf_key_to_max_horizon: dict[GFKey, int] = {}
        gf_key_to_sample_ctx: dict[GFKey, SimulationContext] = {}

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

            # Track max horizon and sample context per growth-factor cache key.
            gf_k = _gf_cache_key(context)
            h = context.horizon_months
            if h > gf_key_to_max_horizon.get(gf_k, 0):
                gf_key_to_max_horizon[gf_k] = h
                gf_key_to_sample_ctx[gf_k] = context
        profiler.stop("numba_grouping")

        # --- Pass 2: precompute growth factors at max horizon per cache key ---
        profiler.start("numba_growth_factors")
        from fbf.core.execution.strategies.numba_kernel import (
            _compute_growth_factors_numpy,
            _materialize_price_float,
            _simulate_trajectory,
        )

        gf_cache_new = 0
        gf_cache_reused = 0
        for gf_k, max_h in gf_key_to_max_horizon.items():
            cached = self._gf_cache.get(gf_k)
            if cached is not None and len(cached) >= max_h:
                gf_cache_reused += 1
                continue
            gf_cache_new += 1
            # Use the precomputed sample context (longest horizon for this key).
            sample_ctx = gf_key_to_sample_ctx[gf_k]
            weights = _weights_by_class(sample_ctx)

            # Cache _index_series by (start_date, n_prices) — independent of allocation.
            n_prices = sample_ctx.horizon_months
            series_key: _PriceCacheKey = (gf_k[0], n_prices)
            if series_key not in self._index_series_cache:
                self._index_series_cache[series_key] = _index_series(sample_ctx)
            series = self._index_series_cache[series_key]
            asset_classes = tuple(series.keys())

            # Cache price arrays by (start_date, n_prices) — independent of allocation.
            price_key: _PriceCacheKey = (
                gf_k[0], len(series[asset_classes[0]])
            )
            if price_key not in self._price_float_cache:
                self._price_float_cache[price_key] = _materialize_price_float(
                    asset_classes, series
                )
            prices_f = self._price_float_cache[price_key]
            weights_f = np.array(
                [float(weights[ac]) for ac in asset_classes], dtype=np.float64
            )
            self._gf_cache[gf_k] = _compute_growth_factors_numpy(
                weights_f, prices_f, max_h
            )
        profiler.stop("numba_growth_factors")

        # --- Pass 3: simulate each group using cached growth factors ---
        profiler.start("numba_kernel_execution")
        results: dict[int, SimulationResult] = {}
        derived_count = 0
        independent_count = 0
        month_work = 0
        gf_hits = gf_cache_reused
        gf_misses = gf_cache_new

        for _, contexts in enumerate(group_contexts):
            # All contexts in a group share trajectory parameters; only horizon differs.
            # Run the kernel once per unique horizon using GF sliced to that horizon.
            horizon_to_ctxs: dict[int, list[SimulationContext]] = {}
            for ctx in contexts:
                horizon_to_ctxs.setdefault(ctx.horizon_months, []).append(ctx)

            # Compute initial portfolio value (same for all contexts in the group).
            sample_ctx = contexts[0]
            initial_snapshot = sample_ctx.dataset[0]
            total = sum(
                holding.units * initial_snapshot.index_levels[holding.asset_class]
                for holding in sample_ctx.initial_portfolio.holdings
            )
            v0 = float(total)
            withdrawal_policy = cast(FixedRealWithdrawalPolicy, sample_ctx.withdrawal_policy)
            c = v0 * float(withdrawal_policy.withdrawal_rate) / 12.0

            gf_key = _gf_cache_key(sample_ctx)
            growth_factors_full = self._gf_cache[gf_key]

            # Per-horizon kernel results cache within this group.
            horizon_result_cache: dict[tuple[int, object], SimulationResult] = {}

            for horizon, h_contexts in horizon_to_ctxs.items():
                month_work += horizon
                growth_factors_arr = growth_factors_full[:horizon]

                _final_val, _kernel_success, fail_month, _ = _simulate_trajectory(
                    growth_factors_arr, v0, c, horizon
                )

                for ctx in h_contexts:
                    cache_key = (horizon, ctx.final_value_target)
                    if cache_key in horizon_result_cache:
                        results[id(ctx)] = horizon_result_cache[cache_key]
                        continue

                    if 0 <= fail_month < horizon:
                        success = False
                        failure_month = fail_month
                        final_value = 0.0
                        months_simulated = fail_month
                    else:
                        final_value = _final_val
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
                    horizon_result_cache[cache_key] = result
                    results[id(ctx)] = result
                    derived_count += 1
        profiler.stop("numba_kernel_execution")

        # Assemble results in original definition order.
        profiler.start("numba_assembly")
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
        profiler.stop("numba_assembly")

        self._last_report = NumbaReport(
            logical_units=len(definition.simulation_contexts),
            groups=len(group_contexts),
            longest_path_evaluations=sum(
                len({c.horizon_months for c in g}) for g in group_contexts
            ),
            derived_results=derived_count - sum(
                len({c.horizon_months for c in g}) for g in group_contexts
            ),
            independent_evaluations=independent_count,
            month_work=month_work,
            gf_cache_hits=gf_hits,
            gf_cache_misses=gf_misses,
        )

        profiler.record("numba_groups", len(group_contexts))
        profiler.record("numba_derived", derived_count)
        profiler.record("numba_independent", independent_count)
        profiler.record("numba_month_work", month_work)
        profiler.record("numba_gf_cache_hits", gf_hits)
        profiler.record("numba_gf_cache_misses", gf_misses)

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
