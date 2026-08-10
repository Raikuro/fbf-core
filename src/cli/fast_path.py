"""Closed-form fast path for constant-allocation + fixed-real-withdrawal studies.

This module provides an explicit, opt-in fast execution path for the exact
policy family used by the ERN acceptance grid:

- ``ConstantAllocationPolicy`` (constant equity/bond target weights, rebalanced
  every month) and
- ``FixedRealWithdrawalPolicy`` (constant real monthly withdrawal amount).

For this policy family the engine's monthly pipeline has a closed-form
recurrence on the portfolio value ``V``:

    V_0      = value(initial_portfolio @ snapshot_0)
    C        = V_0 * withdrawal_rate / 12          (constant real withdrawal)
    V_{m+1}  = (V_m - C) * g_m
    g_m      = sum_j weight_j * index_j[m+1] / index_j[m]

where the engine fails at month ``m`` when ``V_m < C`` (depletion at the
withdrawal step).  Success, failure month, and final wealth are derived from
this O(horizon) recurrence instead of running the full 9-step pipeline.
Measured on the ERN 180-cell grid the combined ``--fast-path`` (float closed
form + horizon chaining) is ~4.2x faster end-to-end; a single closed-form path
alone is ~2.3x faster than the reference recursion (see
``tests/benchmarks/test_fast_path_performance.py``).

The reference (Decimal, full pipeline) engine is intentionally untouched: this
module wraps it and delegates every non-eligible context back to it.  Eligible
contexts can be evaluated in ``float`` (fast) or ``decimal`` (near-exact)
precision; the ``float`` path is validated against the reference engine by
``tests/cli/test_fast_path.py``.

This path is a guarded optimization.  It is only exercised when the CLI caller
explicitly selects ``FastPathSimulationExecutor`` / ``ChainedFastPathSimulationExecutor``
(e.g. via the ``--fast-path`` flag on ``sim-retire run``); the default execution
path remains the reference engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, cast

from cli.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from engine.application.executor import SimulationExecutor
from engine.application.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    ExperimentRun,
    SimulationResult,
    SimulationStatistics,
    SimulationTimeline,
)
from engine.application.simulation_context import SimulationContext
from engine.domain.model.money import Currency, Money
from infrastructure.execution.parallel_executor import _create_default_simulation_executor
from research.domain.plan import ResearchPlan

_EquityId = "equity"

Precision = Literal["float", "decimal"]


def _to_decimal(value: float | Decimal) -> Decimal:
    """Convert a recurrence value to Decimal, losslessly from float via str()."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


@dataclass(frozen=True)
class ClosedFormPath:
    """Per-month closed-form evaluation of one cohort.

    Attributes
    ----------
    withdrawal:
        The constant real monthly withdrawal ``C``.
    monthly_values:
        Pre-withdrawal portfolio value ``V_m`` for each simulated month
        ``m = 0..len(monthly_values)-1``.  On failure the list ends at the
        failing month; on success it spans the full requested horizon.
    failure_month:
        0-indexed month of depletion, or ``None`` when every withdrawal
        succeeded.
    """

    withdrawal: Decimal
    monthly_values: tuple[Decimal, ...]
    failure_month: int | None


def is_fast_path_eligible(context: SimulationContext) -> bool:
    """Return True when *context* can be evaluated by the closed-form path.

    Eligibility is restricted to the exact policy classes whose semantics the
    recurrence encodes.  Any other policy pair (or a horizon below one month)
    falls back to the reference engine.  The dataset must also cover the full
    horizon: the recurrence reads monthly index levels up to
    ``horizon_months - 1``, so a dataset shorter than the horizon is refused.
    """
    if not isinstance(context.allocation_policy, ConstantAllocationPolicy):
        return False
    if not isinstance(context.withdrawal_policy, FixedRealWithdrawalPolicy):
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
    return not any(h.asset_class not in context.dataset[0].index_levels for h in holdings)


def _weights_by_class(
    context: SimulationContext,
) -> dict[object, Decimal]:
    """Map each held asset class to its constant target weight.

    ConstantAllocationPolicy defines equity weight ``w`` and assigns the residual
    ``1 - w`` to every other (bond) asset class.
    """
    allocation = cast(ConstantAllocationPolicy, context.allocation_policy)
    equity_weight = allocation.equity_allocation
    weights: dict[object, Decimal] = {}
    for holding in context.initial_portfolio.holdings:
        if holding.asset_class.id == _EquityId:
            weights[holding.asset_class] = equity_weight
        else:
            weights[holding.asset_class] = Decimal("1") - equity_weight
    return weights


def _index_series(context: SimulationContext) -> dict[object, tuple[Decimal, ...]]:
    """Return per-asset-class monthly index levels across the dataset."""
    snapshots = context.dataset.snapshots
    return {
        holding.asset_class: tuple(
            snapshot.index_levels[holding.asset_class] for snapshot in snapshots
        )
        for holding in context.initial_portfolio.holdings
    }


def _dataset_is_identity_prefix(candidate: SimulationContext, longest: SimulationContext) -> bool:
    """Return True when *candidate*'s dataset is a prefix of *longest*'s.

    Horizon chaining derives shorter horizons from a single longest-horizon
    path, which is only valid when the shorter context follows the identical
    index trajectory (dataset values) for every month it simulates.  The check
    is *identity-based*: it passes only when the candidate's ``MarketSnapshot``
    objects are the very same objects held by the longest context's dataset.
    ``Dataset.slice`` shares the underlying snapshot objects, so the legitimate
    prefix-sliced chaining pattern (the same source trajectory sliced to
    different horizons) passes in O(months) cheap identity comparisons with no
    Decimal work.

    Contexts built from different data fail the check and are evaluated
    individually; their results are never derived from another context's path.
    Failing to chain is always safe (correct results, just no reuse).
    """
    candidate_snapshots = candidate.dataset.snapshots
    longest_snapshots = longest.dataset.snapshots
    if len(candidate_snapshots) > len(longest_snapshots):
        return False
    return all(a is b for a, b in zip(candidate_snapshots, longest_snapshots, strict=False))


def evaluate_path(
    context: SimulationContext,
    precision: Precision = "float",
) -> ClosedFormPath:
    """Evaluate *context* with the closed-form recurrence.

    Parameters
    ----------
    context:
        A context validated by :func:`is_fast_path_eligible`.
    precision:
        ``"float"`` (fast; ~1e-15 per step) or ``"decimal"`` (near-exact).
    """
    initial_snapshot = context.dataset[0]
    total = Money.ZERO
    for holding in context.initial_portfolio.holdings:
        price = initial_snapshot.index_levels[holding.asset_class]
        total += Money(holding.units * price, Currency.EUR)
    withdrawal_policy = cast(FixedRealWithdrawalPolicy, context.withdrawal_policy)
    withdrawal = total.amount * withdrawal_policy.withdrawal_rate / Decimal("12")

    weights = _weights_by_class(context)
    series = _index_series(context)
    asset_classes = tuple(series.keys())
    horizon = context.horizon_months

    if precision == "float":
        monthly, failure_month = _evaluate_float_recurrence(
            weights=weights,
            series=series,
            asset_classes=asset_classes,
            horizon=horizon,
            v0=float(total.amount),
            c=float(withdrawal),
        )
    else:
        monthly, failure_month = _evaluate_decimal_recurrence(
            weights=weights,
            series=series,
            asset_classes=asset_classes,
            horizon=horizon,
            v0=total.amount,
            c=withdrawal,
        )

    return ClosedFormPath(
        withdrawal=withdrawal,
        monthly_values=tuple(monthly),
        failure_month=failure_month,
    )


def _evaluate_float_recurrence(
    weights: dict[object, Decimal],
    series: dict[object, tuple[Decimal, ...]],
    asset_classes: tuple[object, ...],
    horizon: int,
    v0: float,
    c: float,
) -> tuple[list[Decimal], int | None]:
    """Closed-form recurrence in double precision (fast path)."""
    w = [float(weights[a]) for a in asset_classes]
    idx = [[float(v) for v in series[a][: horizon + 1]] for a in asset_classes]
    monthly: list[Decimal] = []
    value = v0
    for m in range(horizon):
        if value < c:
            monthly.append(_to_decimal(value))
            return monthly, m
        monthly.append(_to_decimal(value))
        if m < horizon - 1:
            growth = 0.0
            for j in range(len(asset_classes)):
                growth += w[j] * (idx[j][m + 1] / idx[j][m])
            value = (value - c) * growth
    return monthly, None


def _evaluate_decimal_recurrence(
    weights: dict[object, Decimal],
    series: dict[object, tuple[Decimal, ...]],
    asset_classes: tuple[object, ...],
    horizon: int,
    v0: Decimal,
    c: Decimal,
) -> tuple[list[Decimal], int | None]:
    """Closed-form recurrence in Decimal (near-exact path)."""
    w = [weights[a] for a in asset_classes]
    idx = [series[a][: horizon + 1] for a in asset_classes]
    monthly: list[Decimal] = []
    value = v0
    for m in range(horizon):
        if value < c:
            monthly.append(value)
            return monthly, m
        monthly.append(value)
        if m < horizon - 1:
            growth = Decimal("0")
            for j in range(len(asset_classes)):
                growth += w[j] * (idx[j][m + 1] / idx[j][m])
            value = (value - c) * growth
    return monthly, None


def _outcome_for_horizon(
    path: ClosedFormPath,
    horizon: int,
    withdrawal: Decimal,
) -> tuple[bool, int | None, Money, int]:
    """Derive (success, failure_month, final_wealth, months_simulated) for *horizon*."""
    fail = path.failure_month
    if fail is not None and fail < horizon:
        return False, fail, Money(Decimal("0"), Currency.EUR), fail
    final_value = path.monthly_values[horizon - 1] - withdrawal
    final_wealth = Money(final_value.quantize(Decimal("0.01")), Currency.EUR)
    return True, None, final_wealth, horizon


def _build_result(
    context: SimulationContext,
    path: ClosedFormPath,
    horizon: int,
) -> SimulationResult:
    withdrawal = path.withdrawal
    success, failure_month, final_wealth, months_simulated = _outcome_for_horizon(
        path, horizon, withdrawal
    )
    statistics = SimulationStatistics(
        final_wealth=final_wealth,
        max_drawdown=0.0,
        success=success,
        failure_month=failure_month,
        months_simulated=months_simulated,
        execution_time_seconds=0.0,
    )
    return SimulationResult(
        timeline=SimulationTimeline(monthly_results=()),
        statistics=statistics,
    )


def evaluate_closed_form(
    context: SimulationContext,
    precision: Precision = "float",
) -> SimulationResult:
    """Return a ``SimulationResult`` for *context* via the closed form."""
    path = evaluate_path(context, precision)
    return _build_result(context, path, context.horizon_months)


class FastPathSimulationExecutor(SimulationExecutor):
    """SimulationExecutor that uses the closed form for eligible contexts.

    Non-eligible contexts are delegated to the reference engine unchanged.
    ``precision`` selects the closed-form arithmetic; the reference path always
    runs the standard Decimal pipeline.
    """

    def __init__(
        self,
        reference_executor: SimulationExecutor | None = None,
        precision: Precision = "float",
    ) -> None:
        self._reference = reference_executor or _create_default_simulation_executor()
        self._precision = precision

    def execute(self, definition: EngineExperimentDefinition) -> ExperimentRun:
        results: list[SimulationResult] = []
        for context in definition.simulation_contexts:
            if is_fast_path_eligible(context):
                results.append(evaluate_closed_form(context, self._precision))
            else:
                single = EngineExperimentDefinition(
                    name=definition.name,
                    description=definition.description,
                    simulation_contexts=(context,),
                )
                run = self._reference.execute(single)
                results.append(run.simulation_results[0])
        return ExperimentRun(definition=definition, simulation_results=tuple(results))


def fast_path_unit_counts(plan: ResearchPlan) -> tuple[int, int]:
    """Return ``(fast_path_units, reference_units)`` for a *plan*.

    Mirrors ``ResearchExecutor``'s unit -> ``SimulationContext`` translation so
    the count reflects exactly which units ``FastPathSimulationExecutor`` would
    evaluate via the closed form.  It is used by the CLI to report fast-path
    coverage in the completion summary; eligibility is deterministic and does
    not depend on the execution path (sequential or parallel).
    """
    fast_units = 0
    for unit in plan.units:
        cohort_id = unit.cohort.id
        context = SimulationContext(
            experiment_name=plan.experiment_definition.name,
            cohort=cohort_id if cohort_id is not None else "",
            start_date=unit.cohort.start_date,
            horizon_months=plan.experiment_definition.horizon_months,
            initial_wealth=plan.experiment_definition.initial_wealth,
            initial_portfolio=unit.initial_portfolio,
            dataset=unit.dataset,
            allocation_policy=unit.allocation_policy,
            withdrawal_policy=unit.withdrawal_policy,
        )
        if is_fast_path_eligible(context):
            fast_units += 1
    return fast_units, len(plan.units) - fast_units


class ChainedFastPathSimulationExecutor(FastPathSimulationExecutor):
    """Closed-form executor that chains horizons sharing the same cohort.

    Contexts in a definition that share the same cohort start date, initial
    wealth, initial portfolio, allocation weights and withdrawal rate are
    evaluated together: the longest horizon is run once and every shorter
    horizon is derived from its monthly path prefix.  This reuses the final
    state of the shorter horizon instead of re-simulating earlier months,
    reducing total month-work.

    Chaining is only performed when the shorter contexts' datasets are a prefix
    of the longest context's dataset (same ``MarketSnapshot`` objects).
    Contexts that share a group key but carry different data, initial wealth or
    initial portfolio are evaluated individually; their results are never
    derived from another context's path.
    """

    def execute(self, definition: EngineExperimentDefinition) -> ExperimentRun:
        key_to_group: dict[tuple[object, ...], int] = {}
        group_contexts: list[list[SimulationContext]] = []
        order: list[tuple[int, int]] = []  # (definition index, group_id or -1)

        for index, context in enumerate(definition.simulation_contexts):
            if not is_fast_path_eligible(context):
                order.append((index, -1))
                continue
            allocation = cast(ConstantAllocationPolicy, context.allocation_policy)
            withdrawal = cast(FixedRealWithdrawalPolicy, context.withdrawal_policy)
            key = (
                context.start_date,
                allocation.equity_allocation,
                withdrawal.withdrawal_rate,
                context.initial_wealth,
                context.initial_portfolio,
            )
            if key not in key_to_group:
                group_id = len(group_contexts)
                key_to_group[key] = group_id
                group_contexts.append([])
            else:
                group_id = key_to_group[key]
            group_contexts[group_id].append(context)
            order.append((index, group_id))

        # Evaluate each group's longest horizon once, then derive the rest.
        # Contexts whose dataset is not a prefix of the longest context's are
        # evaluated individually so their results are never cross-derived.
        results: dict[int, SimulationResult] = {}
        for _, contexts in enumerate(group_contexts):
            longest_ctx = max(contexts, key=lambda c: c.horizon_months)
            path = evaluate_path(longest_ctx, self._precision)
            by_horizon: dict[int, SimulationResult] = {}
            for ctx in contexts:
                if ctx is longest_ctx or _dataset_is_identity_prefix(ctx, longest_ctx):
                    if ctx.horizon_months not in by_horizon:
                        by_horizon[ctx.horizon_months] = _build_result(
                            longest_ctx, path, ctx.horizon_months
                        )
                    results[id(ctx)] = by_horizon[ctx.horizon_months]
                else:
                    results[id(ctx)] = evaluate_closed_form(ctx, self._precision)

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
            else:
                ordered_results.append(results[id(definition.simulation_contexts[index])])

        return ExperimentRun(definition=definition, simulation_results=tuple(ordered_results))
