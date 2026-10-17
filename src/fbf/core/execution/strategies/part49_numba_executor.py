"""Numba-accelerated executor for Part 49 leverage studies.

Mirrors :mod:`fbf.core.execution.strategies.part52_numba_executor` but drives
the Part 49 debt recurrence: a fixed monthly loan draw derived from initial
wealth (``loan_draw_rate``), no compound-drawdown tracking, and no ATH-triggered
repayment.

Interest accrual honours ``SimulationContext.debt_interest_rate_is_real`` so
the Numba path matches the legacy ``InterestAccrualStep`` exactly: when the flag
is set the annual rate is applied as ``annual/12`` with no CPI adjustment,
otherwise the CPI-adjusted real rate is used.

The kernel consumes only precomputed monthly rates and weighted portfolio growth
factors, so this executor groups eligible contexts by the parameters that drive
the recurrence (see ``_part49_group_key``), splits each group into identity-prefix
clusters, caches growth factors by dataset identity, and runs one kernel per
unique horizon.  Ineligible contexts raise ``UnsupportedConfigurationError``
rather than silently delegating to the reference Decimal engine.
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
from fbf.core.domain.policies.frequency import WithdrawalFrequency
from fbf.core.domain.policies.part49_withdrawal import Part49WithdrawalPolicy
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
from fbf.core.execution.strategies.part52_numba_executor import _compute_monthly_rates

# Growth-factor cache key: (start_date, equity_allocation, expense_ratio,
# dataset_token).  Identical to the Part 52 key because the growth factors are a
# function of the market trajectory, allocation and fee only.
GFKey = tuple[date, Decimal, Decimal, int]


@dataclass(frozen=True)
class Part49NumbaReport:
    """Execution report for a single Part 49 Numba executor run."""

    logical_units: int
    groups: int
    longest_path_evaluations: int
    derived_results: int
    independent_evaluations: int
    month_work: int
    gf_cache_hits: int
    gf_cache_misses: int


def is_part49_context(context: SimulationContext) -> bool:
    """Return True when *context* uses the Part 49 leverage withdrawal policy."""
    return isinstance(context.withdrawal_policy, Part49WithdrawalPolicy)


def is_part49_eligible(context: SimulationContext) -> bool:
    """Return True when *context* can use the Part 49 Numba backend.

    Eligibility requires:
    - ConstantAllocationPolicy (constant equity/bond target weights)
    - Part49WithdrawalPolicy with MONTHLY frequency
    - ``expense_ratio`` absent or zero (the legacy Part 49 fee applies a
      timing-corrected deduction that the additive growth-factor convention does
      not reproduce; non-zero fees are rejected rather than approximated)
    - horizon_months >= 1
    - Dataset covers the full horizon
    - Exactly 2 holdings (one equity, one bond)
    - All held asset classes in dataset
    - An interest-rate source covering the full horizon: either a schedule at
      least ``horizon_months`` long, or a fixed scalar ``interest_rate``.
    """
    if not isinstance(context.allocation_policy, ConstantAllocationPolicy):
        return False
    if context.allocation_policy.allocations is not None:
        # Explicit N-asset allocations are only supported by the fixed-real
        # workbook path; Part 49 falls back to the reference backend.
        return False
    if not isinstance(context.withdrawal_policy, Part49WithdrawalPolicy):
        return False
    if context.withdrawal_policy.frequency is not WithdrawalFrequency.MONTHLY:
        # ANNUAL is not modelled by the Part 49 kernel (see module docstring).
        return False
    if context.expense_ratio is not None and context.expense_ratio != 0:
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
    schedule = context.interest_rate_schedule
    if schedule is not None and len(schedule) >= context.horizon_months:
        return True
    return context.interest_rate is not None


def _gf_cache_key(context: SimulationContext) -> GFKey:
    """Cache key for growth-factor identity (dataset token disambiguates data)."""
    allocation = cast(ConstantAllocationPolicy, context.allocation_policy)
    equity_weight = allocation.equity_allocation
    assert equity_weight is not None
    fee = context.expense_ratio or Decimal("0")
    return (context.start_date, equity_weight, fee, _dataset_token(context))


def _part49_group_key(context: SimulationContext) -> tuple[object, ...]:
    """Derivation-group key for Part 49 contexts.

    Includes every context field that drives the shared Part 49 trajectory:
    allocation, withdrawal/loan-draw rates, frequency, the real-interest flag,
    the scalar interest rate, LTV settings, and the initial portfolio (the
    withdrawal base).  ``horizon_months`` is the derivation dimension, while
    ``initial_wealth`` and ``final_value_target`` are per-context evaluation
    dimensions consumed only by ``_apply_part49_fv_check``, so they are excluded.
    ``interest_rate_schedule`` is validated separately during clustering.
    """
    allocation = cast(ConstantAllocationPolicy, context.allocation_policy)
    withdrawal = cast(Part49WithdrawalPolicy, context.withdrawal_policy)
    return (
        context.start_date,
        allocation.equity_allocation,
        context.expense_ratio,
        context.initial_portfolio,
        withdrawal.withdrawal_rate,
        withdrawal.frequency,
        context.loan_draw_rate,
        context.debt_interest_rate_is_real,
        context.interest_rate,
        context.ltv_limit,
        context.ltv_enforcement,
    )


def _compute_part49_monthly_rates(
    context: SimulationContext, horizon: int
) -> tuple[Decimal, ...]:
    """Precompute real monthly interest rates, honouring the real-rate flag.

    When ``debt_interest_rate_is_real`` is True the annual rate is applied as
    ``annual_rate / 12`` with no CPI adjustment, matching
    ``InterestAccrualStep``.  Otherwise the CPI-adjusted real rate from
    ``_compute_monthly_rates`` is used unchanged.
    """
    if context.debt_interest_rate_is_real:
        schedule = context.interest_rate_schedule
        rates: list[Decimal] = []
        for m in range(horizon):
            if schedule is not None and m < len(schedule):
                annual_rate = schedule[m]
            else:
                annual_rate = context.interest_rate or Decimal("0")
            rates.append(annual_rate / Decimal("12"))
        return tuple(rates)
    return _compute_monthly_rates(context, horizon)


def _part49_rates_prefix_compatible(
    candidate: SimulationContext, representative: SimulationContext
) -> bool:
    """Return True when two contexts can share a derived monthly-rate prefix.

    Mirrors ``_monthly_rates_prefix_compatible`` but uses the Part 49 rate
    convention (including the real-rate flag).  Datasets are already required to
    be object-identity prefixed by the caller, so this isolates the interest-rate
    schedule and the real-rate flag.
    """
    horizon = min(candidate.horizon_months, representative.horizon_months)
    return _compute_part49_monthly_rates(
        candidate, horizon
    ) == _compute_part49_monthly_rates(representative, horizon)


class Part49NumbaExecutor(SimulationExecutor):
    """Numba-accelerated executor for Part 49 leverage studies.

    Groups eligible Part 49 contexts by trajectory key, precomputes growth
    factors and per-cohort monthly rates (honouring the real-rate flag), and runs
    the Part 49 scalar kernel.  Ineligible configurations raise
    ``UnsupportedConfigurationError``.

    Advertises ``processes_whole_definition = True`` so progress wrappers pass
    the full definition through unchanged.
    """

    processes_whole_definition = True

    def __init__(
        self,
        reference_executor: SimulationExecutor | None = None,
        profiler: Profiler | None = None,
    ) -> None:
        self._reference = reference_executor or _create_default_simulation_executor()
        self._profiler = profiler or NoOpProfiler()
        self._last_report: Part49NumbaReport | None = None
        self._gf_cache: dict[GFKey, NDArray[np.float64]] = {}
        self._price_float_cache: dict[int, NDArray[np.float64]] = {}
        self._index_series_cache: dict[int, dict[object, tuple[Decimal, ...]]] = {}
        # Strong references that keep dataset-identity tokens unique for the
        # executor's lifetime (see ``execute``).
        self._dataset_refs: dict[int, Dataset] = {}

    @property
    def report(self) -> Part49NumbaReport | None:
        return self._last_report

    def execute(self, definition: EngineExperimentDefinition) -> ExperimentRun:
        profiler = self._profiler

        # Cache keys embed an object-identity token for each context's dataset
        # (``_dataset_token``).  Holding a strong reference keeps those tokens
        # unique for the executor's lifetime.
        for context in definition.simulation_contexts:
            dataset = context.dataset
            self._dataset_refs[id(dataset)] = dataset

        # --- Pass 1: group eligible contexts by trajectory parameters ---
        profiler.start("part49_grouping")
        key_to_contexts: dict[tuple[object, ...], list[SimulationContext]] = {}
        for context in definition.simulation_contexts:
            if not is_part49_eligible(context):
                raise UnsupportedConfigurationError(
                    "Part49NumbaExecutor received an unsupported configuration "
                    f"(cohort={context.cohort!r}, "
                    f"start_date={context.start_date.isoformat()!r}). "
                    "Part 49 Numba execution requires a ConstantAllocationPolicy "
                    "without explicit allocations, a MONTHLY "
                    "Part49WithdrawalPolicy, no expense ratio, a two-asset "
                    "(equity + bond) portfolio covered by the dataset, and an "
                    "interest-rate source covering the horizon (an FFR schedule "
                    "at least horizon_months long, or a fixed scalar "
                    "interest_rate)."
                )
            key_to_contexts.setdefault(_part49_group_key(context), []).append(context)
        profiler.stop("part49_grouping")

        # --- Pass 1b: split each parameter group into identity-prefix clusters ---
        prefix_memo: dict[tuple[int, int], bool] = {}
        clusters: list[list[SimulationContext]] = []
        for contexts in key_to_contexts.values():
            clusters.extend(
                _trajectory_clusters(
                    contexts, prefix_memo, _part49_rates_prefix_compatible
                )
            )

        # --- Pass 2: precompute growth factors per cluster representative ---
        profiler.start("part49_growth_factors")
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
        profiler.stop("part49_growth_factors")

        # --- Pass 3: simulate each cluster ---
        profiler.start("part49_kernel_execution")
        from fbf.core.execution.strategies.numba_kernel import (
            _PART52_DEPLETED,
            _PART52_MARGIN_CALL_IMPOSSIBLE,
            _PART52_MARGIN_CALL_TERMINAL,
            _simulate_part49,
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
            withdrawal_policy = cast(Part49WithdrawalPolicy, sample_ctx.withdrawal_policy)

            # Initial portfolio value (withdrawal and loan-draw base)
            initial_snapshot = sample_ctx.dataset[0]
            total = sum(
                holding.units * initial_snapshot.index_levels[holding.asset_class]
                for holding in sample_ctx.initial_portfolio.holdings
            )
            v0 = float(total)

            # Fixed monthly portfolio withdrawal and loan draw
            portfolio_withdrawal = v0 * float(withdrawal_policy.withdrawal_rate) / 12.0
            loan_draw = v0 * float(sample_ctx.loan_draw_rate or Decimal("0")) / 12.0

            ltv_limit = float(sample_ctx.ltv_limit) if sample_ctx.ltv_limit else 0.5
            ltv_enforcement = sample_ctx.ltv_enforcement

            gf_key = _gf_cache_key(sample_ctx)
            growth_factors_full = self._gf_cache[gf_key]

            horizon_result_cache: dict[tuple[int, object, object], SimulationResult] = {}

            for horizon, h_contexts in horizon_to_ctxs.items():
                month_work += horizon
                growth_factors_arr = growth_factors_full[:horizon]

                monthly_rates = _compute_part49_monthly_rates(sample_ctx, horizon)
                mr_arr = np.array([float(r) for r in monthly_rates], dtype=np.float64)

                (
                    _final_val,
                    _kernel_success,
                    fail_month,
                    _final_loan,
                    failure_reason,
                ) = _simulate_part49(
                    growth_factors_arr, mr_arr, v0, portfolio_withdrawal,
                    loan_draw, ltv_limit, horizon,
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
                        # portfolio value, matching the legacy pipeline.
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
                    result = _apply_part49_fv_check(base, ctx)
                    horizon_result_cache[cache_key] = result
                    results[id(ctx)] = result
                    derived_count += 1
        profiler.stop("part49_kernel_execution")

        profiler.start("part49_assembly")
        ordered_results: list[SimulationResult] = [
            results[id(context)] for context in definition.simulation_contexts
        ]
        profiler.stop("part49_assembly")

        longest_path_evaluations = sum(
            len({c.horizon_months for c in cluster}) for cluster in clusters
        )
        self._last_report = Part49NumbaReport(
            logical_units=len(definition.simulation_contexts),
            groups=len(clusters),
            longest_path_evaluations=longest_path_evaluations,
            derived_results=derived_count - longest_path_evaluations,
            independent_evaluations=independent_count,
            month_work=month_work,
            gf_cache_hits=gf_hits,
            gf_cache_misses=gf_misses,
        )

        profiler.record("part49_groups", len(clusters))
        profiler.record("part49_derived", derived_count)
        profiler.record("part49_independent", independent_count)
        profiler.record("part49_month_work", month_work)
        profiler.record("part49_gf_cache_hits", gf_hits)
        profiler.record("part49_gf_cache_misses", gf_misses)

        return ExperimentRun(definition=definition, simulation_results=tuple(ordered_results))


def _apply_part49_fv_check(
    result: SimulationResult, context: SimulationContext
) -> SimulationResult:
    """Apply the final-value success criterion, matching the legacy pipeline.

    The legacy ``StatisticsBuilder`` flips only ``success``: when the FV target
    is missed by a trajectory that survived to the horizon, ``failure_month``
    and ``failure_state`` remain those of the underlying run (``None``).  This
    differs from the shared ``_apply_fv_check`` helpers, which stamp the horizon
    as the failure month, and is required for Part 49 to match the Decimal
    reference exactly.
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
    return SimulationResult(timeline=result.timeline, statistics=statistics)


def _money(value: float) -> Money:
    """Convert a float to a Money object."""
    return Money(Decimal(str(value)), Currency.EUR)
