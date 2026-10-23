"""Numba-accelerated executor for leveraged buy-and-hold (Part 49) studies.

Combines two capabilities:

* buy-and-hold allocation — the target equity/bond split is established once
  and never rebalanced, so weights drift with the asset-specific returns; and
* the Part 49 debt recurrence — a fixed monthly loan draw derived from the
  initial portfolio value (``loan_draw_rate``), interest on the prior balance,
  and the ``ltv_limit`` / ``ltv_enforcement`` rules.

The executor is selected by :func:`is_part49_buy_and_hold_eligible`;
buy-and-hold configurations that are *not* eligible are rejected rather than
simulated by a rebalancing or legacy reference pipeline.

Interest accrual honours ``SimulationContext.debt_interest_rate_is_real`` so the
Numba path matches the legacy ``InterestAccrualStep`` exactly: when the flag is
set the annual rate is applied as ``annual/12`` with no CPI adjustment,
otherwise the CPI-adjusted real rate is used.

The kernel consumes precomputed monthly rates and per-asset growth factors, so
this executor groups eligible contexts by the parameters that drive the
recurrence (see ``_part49_buy_and_hold_group_key``), splits each group into
identity-prefix clusters, caches growth factors by dataset identity, and runs
one kernel per unique horizon.  Ineligible contexts raise
``UnsupportedConfigurationError`` rather than silently delegating to the
reference Decimal engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import cast

import numpy as np
from numpy.typing import NDArray

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import BuyAndHoldAllocationPolicy
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
from fbf.core.execution.strategies.eligibility import (
    _dataset_token,
    _index_series,
    _trajectory_clusters,
)
from fbf.core.execution.strategies.part49_numba_executor import (
    _apply_part49_fv_check,
    _compute_part49_monthly_rates,
    _part49_rates_prefix_compatible,
)

# Per-asset monthly growth factors keyed by dataset-identity token.  Buy-and-hold
# weights drift endogenously, so a single blended series cannot be precomputed;
# the per-asset ratios are trajectory-only and shared across allocations,
# withdrawal rates, and horizons.
BHGrowth = tuple[NDArray[np.float64], NDArray[np.float64]]


@dataclass(frozen=True)
class Part49BuyAndHoldNumbaReport:
    """Execution report for a single leveraged buy-and-hold executor run."""

    logical_units: int
    groups: int
    longest_path_evaluations: int
    derived_results: int
    independent_evaluations: int
    month_work: int
    gf_cache_hits: int
    gf_cache_misses: int


def is_part49_buy_and_hold_eligible(context: SimulationContext) -> bool:
    """Return True when *context* can use the leveraged buy-and-hold Numba backend.

    Eligibility requires:
    - BuyAndHoldAllocationPolicy (no periodic equity/bond rebalancing)
    - Part49WithdrawalPolicy with MONTHLY frequency
    - ``expense_ratio`` absent or zero (the legacy buy-and-hold fee applies a
      timing correction on a stale base without a periodic rebalance; non-zero
      fees are rejected rather than approximated, see ``TODO.md``)
    - horizon_months >= 1
    - Dataset covers the full horizon
    - Exactly 2 holdings (one equity, one bond) covered by the dataset
    - An interest-rate source covering the full horizon: either a schedule at
      least ``horizon_months`` long, or a fixed scalar ``interest_rate``.
    """
    if not isinstance(context.allocation_policy, BuyAndHoldAllocationPolicy):
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


def _part49_buy_and_hold_group_key(context: SimulationContext) -> tuple[object, ...]:
    """Derivation-group key for leveraged buy-and-hold contexts.

    Includes every context field that drives the shared trajectory: the drift
    base (``initial_portfolio``), the equity allocation, withdrawal/loan-draw
    rates, frequency, the real-interest flag, the scalar interest rate, and the
    LTV settings.  ``horizon_months`` is the derivation dimension, while
    ``initial_wealth`` and ``final_value_target`` are per-context evaluation
    dimensions consumed only by ``_apply_part49_fv_check``, so they are excluded.
    ``interest_rate_schedule`` is validated separately during clustering.
    """
    allocation = cast(BuyAndHoldAllocationPolicy, context.allocation_policy)
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


class Part49BuyAndHoldNumbaExecutor(SimulationExecutor):
    """Numba-accelerated executor for leveraged buy-and-hold (Part 49) studies.

    Groups eligible contexts by trajectory key, precomputes per-asset growth
    factors and per-cohort monthly rates (honouring the real-rate flag), and runs
    the leveraged buy-and-hold scalar kernel.  Ineligible configurations raise
    ``UnsupportedConfigurationError``.

    Advertises ``processes_whole_definition = True`` so progress wrappers pass
    the full definition through unchanged.
    """

    processes_whole_definition = True

    def __init__(
        self,
        profiler: Profiler | None = None,
        materialize_timeline: bool = False,
    ) -> None:
        self._profiler = profiler or NoOpProfiler()
        self._materialize_timeline = materialize_timeline
        self._last_report: Part49BuyAndHoldNumbaReport | None = None
        self._bh_growth_cache: dict[int, BHGrowth] = {}
        self._price_float_cache: dict[int, NDArray[np.float64]] = {}
        self._index_series_cache: dict[int, dict[object, tuple[Decimal, ...]]] = {}
        # Strong references that keep dataset-identity tokens unique for the
        # executor's lifetime (see ``execute``).
        self._dataset_refs: dict[int, Dataset] = {}

    @property
    def report(self) -> Part49BuyAndHoldNumbaReport | None:
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
        profiler.start("part49_bh_grouping")
        key_to_contexts: dict[tuple[object, ...], list[SimulationContext]] = {}
        for context in definition.simulation_contexts:
            if not is_part49_buy_and_hold_eligible(context):
                raise UnsupportedConfigurationError(
                    "Part49BuyAndHoldNumbaExecutor received an unsupported "
                    f"configuration (cohort={context.cohort!r}, "
                    f"start_date={context.start_date.isoformat()!r}). "
                    "Leveraged buy-and-hold Numba execution requires a "
                    "BuyAndHoldAllocationPolicy, a MONTHLY Part49WithdrawalPolicy, "
                    "no expense ratio, a two-asset (equity + bond) portfolio "
                    "covered by the dataset, and an interest-rate source covering "
                    "the horizon (an FFR schedule at least horizon_months long, or "
                    "a fixed scalar interest_rate)."
                )
            key_to_contexts.setdefault(
                _part49_buy_and_hold_group_key(context), []
            ).append(context)
        profiler.stop("part49_bh_grouping")

        # --- Pass 1b: split each parameter group into identity-prefix clusters ---
        prefix_memo: dict[tuple[int, int], bool] = {}
        clusters: list[list[SimulationContext]] = []
        for contexts in key_to_contexts.values():
            clusters.extend(
                _trajectory_clusters(
                    contexts, prefix_memo, _part49_rates_prefix_compatible
                )
            )

        # --- Pass 2: precompute per-asset growth factors per cluster ---
        profiler.start("part49_bh_growth_factors")
        gf_cache_new = 0
        gf_cache_reused = 0
        for cluster in clusters:
            representative = cluster[0]
            dataset_key = _dataset_token(representative)
            cached = self._bh_growth_cache.get(dataset_key)
            if cached is not None:
                gf_cache_reused += 1
                continue
            gf_cache_new += 1
            self._buy_and_hold_growth_factors(representative)
        profiler.stop("part49_bh_growth_factors")

        # --- Pass 3: simulate each cluster ---
        profiler.start("part49_bh_kernel_execution")
        from fbf.core.execution.strategies.numba_kernel import (
            _PART52_DEPLETED,
            _PART52_MARGIN_CALL_IMPOSSIBLE,
            _PART52_MARGIN_CALL_TERMINAL,
            _simulate_part49_buy_and_hold,
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
            allocation = cast(BuyAndHoldAllocationPolicy, sample_ctx.allocation_policy)
            equity_weight = float(allocation.equity_allocation)
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

            equity_growth_full, bond_growth_full = self._bh_growth_cache[
                _dataset_token(sample_ctx)
            ]

            horizon_result_cache: dict[tuple[int, object, object], SimulationResult] = {}

            for horizon, h_contexts in horizon_to_ctxs.items():
                month_work += horizon
                equity_growth = equity_growth_full[:horizon]
                bond_growth = bond_growth_full[:horizon]

                monthly_rates = _compute_part49_monthly_rates(sample_ctx, horizon)
                mr_arr = np.array([float(r) for r in monthly_rates], dtype=np.float64)

                out_values = (
                    np.empty(horizon, dtype=np.float64)
                    if self._materialize_timeline
                    else None
                )
                out_loan = (
                    np.empty(horizon, dtype=np.float64)
                    if self._materialize_timeline
                    else None
                )
                out_weights = (
                    np.empty(horizon, dtype=np.float64)
                    if self._materialize_timeline
                    else None
                )
                (
                    _final_val,
                    _kernel_success,
                    fail_month,
                    _final_loan,
                    failure_reason,
                ) = _simulate_part49_buy_and_hold(
                    equity_growth, bond_growth, mr_arr, v0, equity_weight,
                    portfolio_withdrawal, loan_draw, ltv_limit, horizon,
                    ltv_enforcement,
                    out_values,
                    out_loan,
                    out_weights,
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

                    timeline = None
                    if out_values is not None:
                        from fbf.core.execution.strategies.trajectory import (
                            build_simulation_timeline,
                        )

                        timeline = build_simulation_timeline(
                            ctx,
                            out_values,
                            n_months=months_simulated,
                            withdrawal_reason=type(
                                ctx.withdrawal_policy
                            ).__name__,
                            withdrawal_amounts=[
                                Decimal(str(portfolio_withdrawal))
                            ]
                            * months_simulated,
                            loan_draw_amount=Decimal(str(loan_draw)),
                            actual_equity_weights=out_weights,
                            loan_balances=out_loan,
                        )

                    final_wealth = _money(final_value)

                    base = SimulationResult(
                        timeline=timeline
                        or SimulationTimeline(monthly_results=()),
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
        profiler.stop("part49_bh_kernel_execution")

        profiler.start("part49_bh_assembly")
        ordered_results: list[SimulationResult] = [
            results[id(context)] for context in definition.simulation_contexts
        ]
        profiler.stop("part49_bh_assembly")

        longest_path_evaluations = sum(
            len({c.horizon_months for c in cluster}) for cluster in clusters
        )
        self._last_report = Part49BuyAndHoldNumbaReport(
            logical_units=len(definition.simulation_contexts),
            groups=len(clusters),
            longest_path_evaluations=longest_path_evaluations,
            derived_results=derived_count - longest_path_evaluations,
            independent_evaluations=independent_count,
            month_work=month_work,
            gf_cache_hits=gf_hits,
            gf_cache_misses=gf_misses,
        )

        profiler.record("part49_bh_groups", len(clusters))
        profiler.record("part49_bh_derived", derived_count)
        profiler.record("part49_bh_independent", independent_count)
        profiler.record("part49_bh_month_work", month_work)
        profiler.record("part49_bh_gf_cache_hits", gf_hits)
        profiler.record("part49_bh_gf_cache_misses", gf_misses)

        return ExperimentRun(definition=definition, simulation_results=tuple(ordered_results))

    def _buy_and_hold_growth_factors(
        self, context: SimulationContext
    ) -> BHGrowth:
        """Return (equity_growth, bond_growth) monthly factors for *context*.

        The factors are ``P_{m+1}/P_m`` per asset and depend only on the dataset
        trajectory, so they are cached by dataset-identity token and shared
        across allocations, withdrawal rates, and horizons.
        """
        dataset_key = _dataset_token(context)
        cached = self._bh_growth_cache.get(dataset_key)
        if cached is not None:
            return cached

        from fbf.core.execution.strategies.numba_kernel import (
            _materialize_price_float,
        )

        if dataset_key not in self._index_series_cache:
            self._index_series_cache[dataset_key] = _index_series(context)
        series = self._index_series_cache[dataset_key]
        asset_classes = tuple(series.keys())
        if dataset_key not in self._price_float_cache:
            self._price_float_cache[dataset_key] = _materialize_price_float(
                asset_classes, series
            )
        prices_f = self._price_float_cache[dataset_key]

        equity_row = next(
            i
            for i, ac in enumerate(asset_classes)
            if cast(AssetClass, ac).id == "equity"
        )
        bond_row = next(
            i
            for i, ac in enumerate(asset_classes)
            if cast(AssetClass, ac).id == "bond"
        )
        equity_prices = prices_f[equity_row]
        bond_prices = prices_f[bond_row]
        growth = (
            equity_prices[1:] / equity_prices[:-1],
            bond_prices[1:] / bond_prices[:-1],
        )
        self._bh_growth_cache[dataset_key] = growth
        return growth


def _money(value: float) -> Money:
    """Convert a float to a Money object."""
    return Money(Decimal(str(value)), Currency.EUR)
