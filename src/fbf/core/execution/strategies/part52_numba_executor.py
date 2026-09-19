"""Numba-accelerated executor for Part52 timing-leverage studies.

Implements a scalar-state Numba kernel that replicates the Part52 pipeline's
behavioral semantics: compound drawdown tracking, FFR-based interest accrual,
loan draw/repay, cash-first consumption, and LTV enforcement.

The executor groups eligible Part52 contexts by (start_date, equity_allocation),
precomputes growth factors and per-cohort monthly rates / equity prices, and
runs the Part52 kernel per unique horizon.  Ineligible contexts are delegated
to the reference Decimal engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray

from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import ConstantAllocationPolicy
from fbf.core.domain.policies.part52_withdrawal import Part52WithdrawalPolicy
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
)
from fbf.core.execution.strategies.parallel_executor import (
    _create_default_simulation_executor,
)

# Type for growth-factor cache key: (start_date, equity_allocation)
GFKey = tuple[date, Decimal]

# Type for price-float cache key: (start_date, number of price snapshots)
_PriceCacheKey = tuple[date, int]


@dataclass(frozen=True)
class Part52NumbaReport:
    """Execution report for a single Part52 Numba executor run."""

    logical_units: int
    groups: int
    longest_path_evaluations: int
    derived_results: int
    independent_evaluations: int
    month_work: int
    gf_cache_hits: int
    gf_cache_misses: int


def is_part52_eligible(context: SimulationContext) -> bool:
    """Return True when *context* can use the Part52 Numba backend.

    Eligibility requires:
    - ConstantAllocationPolicy (constant equity/bond target weights)
    - Part52WithdrawalPolicy (timing-leverage withdrawal)
    - horizon_months >= 1
    - Dataset covers full horizon
    - Exactly 2 holdings (one equity, one bond)
    - All held asset classes in dataset
    - expense_ratio is None or 0 (no expense deduction in kernel)
    - interest_rate_schedule is not None (FFR-based interest)
    """
    if not isinstance(context.allocation_policy, ConstantAllocationPolicy):
        return False
    if not isinstance(context.withdrawal_policy, Part52WithdrawalPolicy):
        return False
    if context.horizon_months is None or context.horizon_months < 1:
        return False
    if context.dataset is None or len(context.dataset.snapshots) < 1:
        return False
    if len(context.dataset.snapshots) < context.horizon_months:
        return False
    holdings = context.initial_portfolio.holdings
    if not holdings:
        return False
    if len(holdings) != 2:
        return False
    if sum(1 for h in holdings if h.asset_class.id == "equity") != 1:
        return False
    if any(h.asset_class not in context.dataset[0].index_levels for h in holdings):
        return False
    # Expense deduction is a no-op in the kernel; reject if non-zero
    expense_ratio = context.expense_ratio
    if expense_ratio is not None and expense_ratio != Decimal("0"):
        return False
    # Interest rate schedule is required for FFR-based interest
    return context.interest_rate_schedule is not None


def _gf_cache_key(context: SimulationContext) -> GFKey:
    """Cache key for growth-factor identity: (start_date, equity_allocation)."""
    allocation = cast(ConstantAllocationPolicy, context.allocation_policy)
    return (context.start_date, allocation.equity_allocation)


def _compute_monthly_rates(
    context: SimulationContext, horizon: int
) -> tuple[Decimal, ...]:
    """Precompute CPI-adjusted real monthly interest rates for the cohort.

    Formula: r_m = (1 + annual_rate_m / 12) * (CPI_{m-1} / CPI_m) - 1

    For real-terms datasets (CPI=0), simplifies to annual_rate_m / 12.
    """
    schedule = context.interest_rate_schedule
    if schedule is None:
        return tuple(Decimal("0") for _ in range(horizon))

    rates: list[Decimal] = []
    for m in range(horizon):
        # Annual rate from schedule (or fallback to static rate)
        annual_rate = schedule[m] if m < len(schedule) else context.interest_rate or Decimal("0")

        # CPI ratio
        snapshot_curr = context.dataset[m] if m < len(context.dataset) else None
        snapshot_prev = context.dataset[m - 1] if m > 0 and m - 1 < len(context.dataset) else None

        if snapshot_curr is None or snapshot_prev is None:
            rates.append(annual_rate / Decimal("12"))
            continue

        cpi_curr = snapshot_curr.inflation_cumulative
        cpi_prev = snapshot_prev.inflation_cumulative

        if cpi_curr == 0 or cpi_prev == 0:
            rates.append(annual_rate / Decimal("12"))
        else:
            cpi_ratio = cpi_prev / cpi_curr
            nominal_monthly = annual_rate / Decimal("12")
            real_monthly = (Decimal("1") + nominal_monthly) * cpi_ratio - Decimal("1")
            rates.append(real_monthly)

    return tuple(rates)


def _compute_growth_factors_for_part52(
    context: SimulationContext, horizon: int
) -> NDArray[np.float64]:
    """Compute growth factors for the cohort's equity allocation and trajectory.

    g_m = sum_j w_j * P_{j,m} / P_{j,m-1}
    """
    weights = _weights_by_class(context)
    series = _index_series(context)
    asset_classes = tuple(series.keys())

    # Build price array
    n_prices = min(horizon + 1, len(series[asset_classes[0]]))
    prices = np.empty((len(asset_classes), n_prices), dtype=np.float64)
    for j, ac in enumerate(asset_classes):
        for p in range(n_prices):
            prices[j, p] = float(series[ac][p])

    weights_arr = np.array([float(weights[ac]) for ac in asset_classes], dtype=np.float64)

    # Growth factors: g_m = sum_j w_j * P_{j,m+1} / P_{j,m}
    n_growth = min(horizon, n_prices - 1)
    growth_factors = np.ones(horizon, dtype=np.float64)
    for m in range(n_growth):
        g = 0.0
        for j in range(len(asset_classes)):
            if prices[j, m] > 0.0:
                g += weights_arr[j] * prices[j, m + 1] / prices[j, m]
        growth_factors[m] = g

    return growth_factors


def _extract_equity_prices(
    context: SimulationContext, horizon: int
) -> NDArray[np.float64]:
    """Extract equity index levels for compound drawdown computation."""
    prices = np.ones(horizon + 1, dtype=np.float64)
    for m in range(min(horizon + 1, len(context.dataset))):
        snapshot = context.dataset[m]
        for ac in snapshot.index_levels:
            if ac.id == "equity":
                prices[m] = float(snapshot.index_levels[ac])
                break
    return prices


class Part52NumbaExecutor(SimulationExecutor):
    """Numba-accelerated executor for Part52 timing-leverage studies.

    Groups eligible Part52 contexts by trajectory key, precomputes growth
    factors and per-cohort monthly rates, and runs the Part52 scalar kernel.
    Delegates ineligible contexts to the reference Decimal engine.

    Advertises ``processes_whole_definition = True`` so progress wrappers
    pass the full definition through unchanged.
    """

    processes_whole_definition = True

    def __init__(
        self,
        reference_executor: SimulationExecutor | None = None,
        profiler: Profiler | None = None,
    ) -> None:
        self._reference = reference_executor or _create_default_simulation_executor()
        self._profiler = profiler or NoOpProfiler()
        self._last_report: Part52NumbaReport | None = None
        self._gf_cache: dict[GFKey, Any] = {}
        self._price_float_cache: dict[_PriceCacheKey, NDArray[np.float64]] = {}
        self._index_series_cache: dict[_PriceCacheKey, dict[object, tuple[Decimal, ...]]] = {}

    @property
    def report(self) -> Part52NumbaReport | None:
        return self._last_report

    def execute(self, definition: EngineExperimentDefinition) -> ExperimentRun:
        profiler = self._profiler

        # --- Pass 1: group eligible contexts ---
        profiler.start("part52_grouping")
        key_to_group: dict[tuple[object, ...], int] = {}
        group_contexts: list[list[SimulationContext]] = []
        order: list[tuple[int, int]] = []
        gf_key_to_max_horizon: dict[GFKey, int] = {}
        gf_key_to_sample_ctx: dict[GFKey, SimulationContext] = {}

        for index, context in enumerate(definition.simulation_contexts):
            if not is_part52_eligible(context):
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

            gf_k = _gf_cache_key(context)
            h = context.horizon_months
            if h > gf_key_to_max_horizon.get(gf_k, 0):
                gf_key_to_max_horizon[gf_k] = h
                gf_key_to_sample_ctx[gf_k] = context
        profiler.stop("part52_grouping")

        # --- Pass 2: precompute growth factors ---
        profiler.start("part52_growth_factors")
        from fbf.core.execution.strategies.numba_kernel import (
            _compute_growth_factors_numpy,
            _materialize_price_float,
        )

        gf_cache_new = 0
        gf_cache_reused = 0
        for gf_k, max_h in gf_key_to_max_horizon.items():
            cached = self._gf_cache.get(gf_k)
            if cached is not None and len(cached) >= max_h:
                gf_cache_reused += 1
                continue
            gf_cache_new += 1
            sample_ctx = gf_key_to_sample_ctx[gf_k]
            weights = _weights_by_class(sample_ctx)

            n_prices = sample_ctx.horizon_months
            series_key: _PriceCacheKey = (gf_k[0], n_prices)
            if series_key not in self._index_series_cache:
                self._index_series_cache[series_key] = _index_series(sample_ctx)
            series = self._index_series_cache[series_key]
            asset_classes = tuple(series.keys())

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
        profiler.stop("part52_growth_factors")

        # --- Pass 3: simulate each group ---
        profiler.start("part52_kernel_execution")
        from fbf.core.execution.strategies.numba_kernel import _simulate_part52

        results: dict[int, SimulationResult] = {}
        derived_count = 0
        independent_count = 0
        month_work = 0
        gf_hits = gf_cache_reused
        gf_misses = gf_cache_new

        for _, contexts in enumerate(group_contexts):
            horizon_to_ctxs: dict[int, list[SimulationContext]] = {}
            for ctx in contexts:
                horizon_to_ctxs.setdefault(ctx.horizon_months, []).append(ctx)

            sample_ctx = contexts[0]
            withdrawal_policy = cast(Part52WithdrawalPolicy, sample_ctx.withdrawal_policy)

            # Initial portfolio value
            initial_snapshot = sample_ctx.dataset[0]
            total = sum(
                holding.units * initial_snapshot.index_levels[holding.asset_class]
                for holding in sample_ctx.initial_portfolio.holdings
            )
            v0 = float(total)

            # Canonical monthly withdrawal
            c = v0 * float(withdrawal_policy.withdrawal_rate) / 12.0

            # Parameters
            threshold = float(withdrawal_policy.drawdown_threshold)
            borrow_pct = float(withdrawal_policy.borrow_pct)
            ltv_limit = float(sample_ctx.ltv_limit) if sample_ctx.ltv_limit else 0.5

            gf_key = _gf_cache_key(sample_ctx)
            growth_factors_full = self._gf_cache[gf_key]

            horizon_result_cache: dict[tuple[int, object], SimulationResult] = {}

            for horizon, h_contexts in horizon_to_ctxs.items():
                month_work += horizon
                growth_factors_arr = growth_factors_full[:horizon]

                # Precompute monthly rates for this cohort
                monthly_rates = _compute_monthly_rates(sample_ctx, horizon)
                mr_arr = np.array([float(r) for r in monthly_rates], dtype=np.float64)

                # Extract equity prices
                eq_prices = _extract_equity_prices(sample_ctx, horizon)

                # Run kernel
                _final_val, _kernel_success, fail_month, _final_loan = _simulate_part52(
                    growth_factors_arr, mr_arr, eq_prices,
                    v0, c, threshold, borrow_pct, ltv_limit, horizon,
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
                            failure_state=None if success else "depleted",
                            months_simulated=months_simulated,
                            execution_time_seconds=0.0,
                        ),
                    )
                    result = _apply_fv_check(base, ctx)
                    horizon_result_cache[cache_key] = result
                    results[id(ctx)] = result
                    derived_count += 1
        profiler.stop("part52_kernel_execution")

        # Assemble results in original order
        profiler.start("part52_assembly")
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
        profiler.stop("part52_assembly")

        self._last_report = Part52NumbaReport(
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

        profiler.record("part52_groups", len(group_contexts))
        profiler.record("part52_derived", derived_count)
        profiler.record("part52_independent", independent_count)
        profiler.record("part52_month_work", month_work)
        profiler.record("part52_gf_cache_hits", gf_hits)
        profiler.record("part52_gf_cache_misses", gf_misses)

        return ExperimentRun(definition=definition, simulation_results=tuple(ordered_results))


def _money(value: float) -> Money:
    """Convert a float to a Money object."""
    return Money(Decimal(str(value)), Currency.EUR)


def _apply_fv_check(result: SimulationResult, context: SimulationContext) -> SimulationResult:
    """Return a copy of *result* with the FV check applied."""
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
        failure_state=None if survived else result.statistics.failure_state,
        months_simulated=result.statistics.months_simulated,
        execution_time_seconds=result.statistics.execution_time_seconds,
    )
    return SimulationResult(
        timeline=result.timeline,
        statistics=statistics,
    )
