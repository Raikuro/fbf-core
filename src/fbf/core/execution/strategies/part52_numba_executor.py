"""Numba-accelerated executor for Part52 timing-leverage studies.

Implements a scalar-state Numba kernel that replicates the Part52 pipeline's
behavioral semantics: compound drawdown tracking, FFR-based interest accrual,
loan draw/repay, cash-first consumption, and LTV enforcement.

The executor groups eligible Part52 contexts by the parameters that drive the
kernel (see ``_part52_group_key``), splits each group into identity-prefix
clusters so derived horizons only reuse a trajectory whose snapshots are the
very same objects, precomputes growth factors keyed by dataset identity and
per-cohort monthly rates / equity prices, and runs the Part52 kernel per unique
horizon.  Interest accrual uses a per-month FFR schedule when present and the
fixed scalar ``interest_rate`` otherwise, mirroring the legacy
``InterestAccrualStep``.  Ineligible contexts raise
``UnsupportedConfigurationError`` rather than delegating to the reference
Decimal engine, so the numerical conventions are never silently mixed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import cast

import numpy as np
from numpy.typing import NDArray

from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import ConstantAllocationPolicy
from fbf.core.domain.policies.part52_withdrawal import Part52WithdrawalPolicy
from fbf.core.execution.errors import UnsupportedConfigurationError
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
    _dataset_token,
    _index_series,
    _trajectory_clusters,
    _weights_by_class,
)
from fbf.core.execution.strategies.parallel_executor import (
    _create_default_simulation_executor,
)

# Growth-factor cache key: (start_date, equity_allocation, expense_ratio,
# dataset_token).  The dataset token disambiguates contexts that share a start
# date but not a market trajectory.
GFKey = tuple[date, Decimal, Decimal, int]


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


def is_part52_context(context: SimulationContext) -> bool:
    """Return True when *context* uses the Part 52 timing-leverage withdrawal policy.

    Distinguishes a Part 52 workload from other policies so dispatch can apply
    Part 52-specific contracts before checking full Numba eligibility.
    """
    return isinstance(context.withdrawal_policy, Part52WithdrawalPolicy)


def is_part52_eligible(context: SimulationContext) -> bool:
    """Return True when *context* can use the Part52 Numba backend.

    Eligibility requires:
    - ConstantAllocationPolicy (constant equity/bond target weights)
    - Part52WithdrawalPolicy (timing-leverage withdrawal)
    - horizon_months >= 1
    - Dataset covers full horizon
    - Exactly 2 holdings (one equity, one bond)
    - All held asset classes in dataset
    - An interest-rate source covering the full horizon: either an FFR
      schedule at least ``horizon_months`` long, or a fixed scalar
      ``interest_rate`` (the schedule-less fixed-rate / pre-1928 path).
    - expense_ratio is supported (additive fee embedded in growth factors)
    """
    if not isinstance(context.allocation_policy, ConstantAllocationPolicy):
        return False
    if context.allocation_policy.allocations is not None:
        # Explicit N-asset allocations are only supported by the fixed-real
        # workbook path; Part52 falls back to the reference backend.
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
    # Interest-rate source covering the full horizon: an FFR schedule of at
    # least ``horizon_months`` entries, otherwise a fixed scalar rate.  This
    # mirrors ``InterestAccrualStep``, which uses ``interest_rate`` both when
    # no schedule is present and beyond a shorter schedule's length.
    schedule = context.interest_rate_schedule
    if schedule is not None and len(schedule) >= context.horizon_months:
        return True
    return context.interest_rate is not None


def _gf_cache_key(context: SimulationContext) -> GFKey:
    """Cache key for growth-factor identity.

    Includes the dataset token so growth factors computed from one trajectory
    are never reused for a context built from different data (even when the
    start date, allocation, and fee coincide).
    """
    allocation = cast(ConstantAllocationPolicy, context.allocation_policy)
    equity_weight = allocation.equity_allocation
    assert equity_weight is not None
    fee = context.expense_ratio or Decimal("0")
    return (context.start_date, equity_weight, fee, _dataset_token(context))


def _part52_group_key(context: SimulationContext) -> tuple[object, ...]:
    """Derivation-group key for Part52 contexts.

    Includes every context field that the shared Part52 kernel path consumes,
    except:

    - ``horizon_months``: the derivation dimension.  Each horizon is simulated
      independently from the representative's growth factors/equity prices
      sliced to that horizon.
    - ``final_value_target`` and ``initial_wealth``: per-context *evaluation*
      dimensions.  They are consumed only by ``_apply_fv_check``, which is
      applied per context after the shared path is computed, so they do not
      affect the shared trajectory.
    - ``interest_rate_schedule``: allowed to differ in length across horizons
      (it is a per-horizon prefix of the same FFR-aligned series), so it cannot
      be part of a horizon-independent key.  Its shared-prefix requirement is
      enforced by ``_monthly_rates_prefix_compatible`` during clustering.
    - dataset identity, enforced separately by the identity-prefix guard.

    Sharing a group is only valid when all of the remaining fields agree,
    because the longest-horizon representative's parameters drive every derived
    horizon.
    """
    allocation = cast(ConstantAllocationPolicy, context.allocation_policy)
    withdrawal = cast(Part52WithdrawalPolicy, context.withdrawal_policy)
    return (
        context.start_date,
        allocation.equity_allocation,
        context.expense_ratio,
        context.initial_portfolio,
        withdrawal.withdrawal_rate,
        withdrawal.borrow_pct,
        withdrawal.drawdown_threshold,
        withdrawal.frequency,
        context.interest_rate,
        context.ltv_limit,
        context.ltv_enforcement,
    )


def _compute_monthly_rates(
    context: SimulationContext, horizon: int
) -> tuple[Decimal, ...]:
    """Precompute CPI-adjusted real monthly interest rates for the cohort.

    Formula: r_m = (1 + annual_rate_m / 12) * (CPI_{m-1} / CPI_m) - 1

    For real-terms datasets (CPI=0), simplifies to annual_rate_m / 12.

    The annual rate for month *m* is the FFR schedule entry at *m* when a
    schedule covers that month, otherwise the fixed scalar ``interest_rate``.
    This mirrors ``InterestAccrualStep`` so schedule-backed and schedule-less
    (fixed-rate / pre-1928) Part 52 workloads share one accrual convention.
    """
    schedule = context.interest_rate_schedule

    rates: list[Decimal] = []
    for m in range(horizon):
        # Annual rate from the schedule, or the fixed scalar rate when the
        # schedule is absent or shorter than the horizon.
        if schedule is not None and m < len(schedule):
            annual_rate = schedule[m]
        else:
            annual_rate = context.interest_rate or Decimal("0")

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


def _monthly_rates_prefix_compatible(
    candidate: SimulationContext, representative: SimulationContext
) -> bool:
    """Return True when two contexts can share a derived monthly-rate prefix.

    ``_compute_monthly_rates`` for a derived horizon is evaluated once from the
    cluster representative and reused by every member, so clustering two
    contexts is only valid when their consumed monthly-rate prefixes agree over
    the shorter horizon.  Datasets are already required to be object-identity
    prefixed by the caller, so the CPI component matches; this check therefore
    isolates the interest-rate schedule (and the static ``interest_rate``
    fallback beyond a schedule's length).

    The predicate is symmetric and cheap relative to a kernel run: it is only
    consulted once per (candidate, representative) pair while clustering.
    """
    horizon = min(candidate.horizon_months, representative.horizon_months)
    return _compute_monthly_rates(candidate, horizon) == _compute_monthly_rates(
        representative, horizon
    )


def _compute_growth_factors_for_part52(
    context: SimulationContext, horizon: int
) -> NDArray[np.float64]:
    """Compute growth factors for the cohort's equity allocation and trajectory.

    g_m = sum_j w_j * P_{j,m} / P_{j,m-1} - fee_annual/12
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

    fee_annual = float(context.expense_ratio or Decimal("0"))
    fee_monthly = fee_annual / 12.0

    # Growth factors: g_m = sum_j w_j * P_{j,m+1} / P_{j,m} - fee_monthly
    n_growth = min(horizon, n_prices - 1)
    growth_factors = np.ones(horizon, dtype=np.float64)
    for m in range(n_growth):
        g = 0.0
        for j in range(len(asset_classes)):
            if prices[j, m] > 0.0:
                g += weights_arr[j] * prices[j, m + 1] / prices[j, m]
        growth_factors[m] = g - fee_monthly

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
        self._gf_cache: dict[GFKey, NDArray[np.float64]] = {}
        self._price_float_cache: dict[int, NDArray[np.float64]] = {}
        self._index_series_cache: dict[int, dict[object, tuple[Decimal, ...]]] = {}
        # Strong references that keep dataset-identity tokens unique for the
        # executor's lifetime (see ``execute``).
        self._dataset_refs: dict[int, Dataset] = {}

    @property
    def report(self) -> Part52NumbaReport | None:
        return self._last_report

    def execute(self, definition: EngineExperimentDefinition) -> ExperimentRun:
        profiler = self._profiler

        # Cache keys embed an object-identity token for each context's dataset
        # (``_dataset_token``).  Holding a strong reference to every dataset the
        # executor has seen keeps those tokens unique for the executor's
        # lifetime, so cached growth factors and materialised prices remain
        # valid across execute calls without risking an id reused by a different
        # trajectory.
        for context in definition.simulation_contexts:
            dataset = context.dataset
            self._dataset_refs[id(dataset)] = dataset

        # --- Pass 1: group eligible contexts by trajectory parameters ---
        # Fail fast on any unsupported configuration: the Part 52 Numba kernel
        # must never silently delegate to the reference Decimal engine, whose
        # fee/ordering conventions may differ.
        profiler.start("part52_grouping")
        key_to_contexts: dict[tuple[object, ...], list[SimulationContext]] = {}
        for context in definition.simulation_contexts:
            if not is_part52_eligible(context):
                raise UnsupportedConfigurationError(
                    "Part52NumbaExecutor received an unsupported configuration "
                    f"(cohort={context.cohort!r}, "
                    f"start_date={context.start_date.isoformat()!r}). "
                    "Part 52 Numba execution requires a ConstantAllocationPolicy "
                    "without explicit allocations, a Part52WithdrawalPolicy, a "
                    "two-asset (equity + bond) portfolio covered by the dataset, "
                    "and an interest-rate source covering the horizon (an FFR "
                    "schedule at least horizon_months long, or a fixed scalar "
                    "interest_rate)."
                )
            key_to_contexts.setdefault(_part52_group_key(context), []).append(context)
        profiler.stop("part52_grouping")

        # --- Pass 1b: split each parameter group into identity-prefix clusters ---
        # Contexts that share trajectory parameters but were built from different
        # market data must never derive from one another; the identity-prefix
        # guard enforces this and keeps derivation correct.  The monthly-rate
        # prefix guard additionally prevents deriving from a representative whose
        # FFR schedule diverges within a shorter member's horizon.
        prefix_memo: dict[tuple[int, int], bool] = {}
        clusters: list[list[SimulationContext]] = []
        for contexts in key_to_contexts.values():
            clusters.extend(
                _trajectory_clusters(
                    contexts, prefix_memo, _monthly_rates_prefix_compatible
                )
            )

        # --- Pass 2: precompute growth factors per cluster representative ---
        profiler.start("part52_growth_factors")
        from fbf.core.execution.strategies.numba_kernel import (
            _compute_growth_factors_numpy,
            _materialize_price_float,
        )

        gf_cache_new = 0
        gf_cache_reused = 0
        for cluster in clusters:
            representative = cluster[0]
            max_h = max(ctx.horizon_months for ctx in cluster)
            gf_k = _gf_cache_key(representative)
            cached = self._gf_cache.get(gf_k)
            if cached is not None and len(cached) >= max_h:
                gf_cache_reused += 1
                continue
            gf_cache_new += 1
            weights = _weights_by_class(representative)

            dataset_key = _dataset_token(representative)
            if dataset_key not in self._index_series_cache:
                self._index_series_cache[dataset_key] = _index_series(representative)
            series = self._index_series_cache[dataset_key]
            asset_classes = tuple(series.keys())

            if dataset_key not in self._price_float_cache:
                self._price_float_cache[dataset_key] = _materialize_price_float(
                    asset_classes, series
                )
            prices_f = self._price_float_cache[dataset_key]
            weights_f = np.array(
                [float(weights[ac]) for ac in asset_classes], dtype=np.float64
            )
            fee_annual = float(representative.expense_ratio or Decimal("0"))
            self._gf_cache[gf_k] = _compute_growth_factors_numpy(
                weights_f, prices_f, max_h, fee_annual
            )
        profiler.stop("part52_growth_factors")

        # --- Pass 3: simulate each cluster ---
        profiler.start("part52_kernel_execution")
        from fbf.core.execution.strategies.numba_kernel import (
            _PART52_DEPLETED,
            _PART52_MARGIN_CALL_IMPOSSIBLE,
            _PART52_MARGIN_CALL_TERMINAL,
            _simulate_part52,
        )

        _failure_state_by_reason = {
            _PART52_DEPLETED: "depleted",
            _PART52_MARGIN_CALL_IMPOSSIBLE: "margin_call_impossible",
            _PART52_MARGIN_CALL_TERMINAL: "margin_call_terminal",
        }

        results: dict[int, SimulationResult] = {}
        derived_count = 0
        independent_count = 0
        month_work = 0
        gf_hits = gf_cache_reused
        gf_misses = gf_cache_new

        for contexts in clusters:
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
            ltv_enforcement = sample_ctx.ltv_enforcement

            gf_key = _gf_cache_key(sample_ctx)
            growth_factors_full = self._gf_cache[gf_key]

            horizon_result_cache: dict[tuple[int, object, object], SimulationResult] = {}

            for horizon, h_contexts in horizon_to_ctxs.items():
                month_work += horizon
                growth_factors_arr = growth_factors_full[:horizon]

                # Precompute monthly rates for this cohort
                monthly_rates = _compute_monthly_rates(sample_ctx, horizon)
                mr_arr = np.array([float(r) for r in monthly_rates], dtype=np.float64)

                # Extract equity prices
                eq_prices = _extract_equity_prices(sample_ctx, horizon)

                # Run kernel
                (
                    _final_val,
                    _kernel_success,
                    fail_month,
                    _final_loan,
                    failure_reason,
                ) = _simulate_part52(
                    growth_factors_arr, mr_arr, eq_prices,
                    v0, c, threshold, borrow_pct, ltv_limit, horizon,
                    ltv_enforcement,
                )

                for ctx in h_contexts:
                    cache_key = (horizon, ctx.initial_wealth, ctx.final_value_target)
                    if cache_key in horizon_result_cache:
                        results[id(ctx)] = horizon_result_cache[cache_key]
                        continue

                    if 0 <= fail_month < horizon:
                        success = False
                        failure_month = fail_month
                        failure_state = _failure_state_by_reason[failure_reason]
                        # Depletion reports a zero final value; a terminal
                        # margin-call liquidation reports the post-liquidation
                        # portfolio value, matching the legacy pipeline and the
                        # independent oracle.
                        final_value = (
                            _final_val
                            if failure_reason == _PART52_MARGIN_CALL_TERMINAL
                            else 0.0
                        )
                        months_simulated = fail_month
                    else:
                        final_value = _final_val
                        success = True
                        failure_month = None
                        failure_state = None
                        months_simulated = horizon

                    final_wealth = _money(final_value)

                    base = SimulationResult(
                        timeline=SimulationTimeline(monthly_results=()),
                        statistics=SimulationStatistics(
                            final_wealth=final_wealth,
                            max_drawdown=0.0,
                            success=success,
                            failure_month=failure_month,
                            failure_state=failure_state,
                            months_simulated=months_simulated,
                            execution_time_seconds=0.0,
                        ),
                    )
                    result = _apply_fv_check(base, ctx)
                    horizon_result_cache[cache_key] = result
                    results[id(ctx)] = result
                    derived_count += 1
        profiler.stop("part52_kernel_execution")

        # Assemble results in original order.  Every context is eligible by
        # construction (Pass 1 raises otherwise), so results are complete.
        profiler.start("part52_assembly")
        ordered_results: list[SimulationResult] = [
            results[id(context)] for context in definition.simulation_contexts
        ]
        profiler.stop("part52_assembly")

        longest_path_evaluations = sum(
            len({c.horizon_months for c in cluster}) for cluster in clusters
        )
        self._last_report = Part52NumbaReport(
            logical_units=len(definition.simulation_contexts),
            groups=len(clusters),
            longest_path_evaluations=longest_path_evaluations,
            derived_results=derived_count - longest_path_evaluations,
            independent_evaluations=independent_count,
            month_work=month_work,
            gf_cache_hits=gf_hits,
            gf_cache_misses=gf_misses,
        )

        profiler.record("part52_groups", len(clusters))
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
    """Return a copy of *result* with the FV check applied.

    A final-value target miss is an evaluation-criterion failure, not an
    operational terminal failure: only ``success`` is flipped, while
    ``failure_month`` and ``failure_state`` remain those of the underlying
    result (``None`` for a trajectory that survived to the horizon).
    """
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
        failure_month=result.statistics.failure_month,
        failure_state=result.statistics.failure_state,
        months_simulated=result.statistics.months_simulated,
        execution_time_seconds=result.statistics.execution_time_seconds,
    )
    return SimulationResult(
        timeline=result.timeline,
        statistics=statistics,
    )
