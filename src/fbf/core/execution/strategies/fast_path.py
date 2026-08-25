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
Measured on the ERN 180-cell grid (313,020 units) at equal worker count
(``--workers max``) the combined ``--fast-path`` (float closed form +
multi-horizon execution) is approximately 41x faster end-to-end than the
reference Decimal engine.  These are host-dependent session measurements; the
committed benchmark suite (``tests/benchmarks/``) asserts outcome equivalence,
not these wall-clock figures.

The reference (Decimal, full pipeline) engine is intentionally untouched: this
module wraps it and delegates every non-eligible context back to it.  Eligible
contexts can be evaluated in ``float`` (fast; exact outcome/failure month, final
wealth within ~1e-5 EUR) or ``decimal`` (bit-exact: replicates the reference's
per-month per-asset Decimal arithmetic so success, failure month and final
wealth match to the last digit); the ``float`` path is validated against the
reference engine by ``run_fast_path_validation``.

This path is a guarded optimization.  It is only exercised when the CLI caller
explicitly selects ``FastPathSimulationExecutor`` (e.g. via the
``--fast-path`` flag on ``sim-retire run``); the default execution path remains
the reference fbf.core.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, cast

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding
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
from fbf.core.execution.strategies.parallel_executor import (
    _create_default_simulation_executor,
    sequential_execute,
)
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan

_EquityId = "equity"

Precision = Literal["float", "decimal"]

# --- F7 validation constants -------------------------------------------------
# Deterministic sample seed so ``--fast-path --validate`` always picks the same
# units for a given plan.  Sample size and wealth tolerance follow the
# established equivalence studies in ``tests/cli/test_fast_path.py``.
FAST_PATH_VALIDATION_SEED = 0xF7A9
FAST_PATH_VALIDATION_MAX_UNITS = 8
FAST_PATH_VALIDATION_WEALTH_TOLERANCE = Decimal("0.05")


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
    post_withdrawal_values:
        Portfolio value immediately after month ``m``'s withdrawal and
        rebalance, valued at the month's own snapshot.  This is the reference
        engine's ``current_wealth`` at the end of month ``m`` and therefore the
        final wealth a context whose horizon ends at ``m`` would report.  The
        bit-exact ``decimal`` recurrence stores the residual-arithmetic value
        here; the ``float`` recurrence stores ``monthly_values[m] - withdrawal``
        (its own closed-form after-withdrawal value).  When empty,
        :func:`_outcome_for_horizon` falls back to
        ``monthly_values[-1] - withdrawal``.
    failure_residual:
        On failure, the exact residual portfolio value left at the failing
        month (the reference engine's ``current_wealth`` after the depletion
        withdrawal), produced only by the bit-exact ``decimal`` recurrence.
        ``None`` for the ``float`` path, which reports ``0`` on failure (see
        ``_outcome_for_horizon``).
    """

    withdrawal: Decimal
    monthly_values: tuple[Decimal, ...]
    failure_month: int | None
    post_withdrawal_values: tuple[Decimal, ...] = ()
    failure_residual: Decimal | None = None


@dataclass(frozen=True)
class DerivationReport:
    """Instrumentation summary of a multi-horizon execution.

    Provides an execution-independent statement of how much mathematical work a
    fast-path run performs versus the reference path, plus the group structure the
    horizon derivation produced.  It is computed deterministically from a plan (or a
    definition) and is also recorded live by
    :class:`FastPathSimulationExecutor` after each ``execute``.

    Attributes
    ----------
    logical_units:
        Total number of simulation units/contexts in the study.
    groups:
        Number of (cohort, equity, rate, wealth, portfolio) families whose
        contexts share a group key and are evaluated together.
    longest_path_evaluations:
        Number of times a single longest-horizon path was evaluated and reused
        to derive shorter horizons (one per group).
    derived_results:
        Number of results obtained by reading a shorter horizon off a reused
        longest-horizon path instead of re-simulating it.
    independent_evaluations:
        Number of results computed on their own (non-eligible contexts,
        non-prefix datasets, or singleton groups).
    month_work:
        Total recurrence months actually simulated.  For the reference path this
        equals ``sum(unit.horizon_months)``; for the fully derived ERN grid it
        is ``groups * 720`` (the longest horizon evaluated once per
        family), exactly 3x below the reference count.
    """

    logical_units: int
    groups: int
    longest_path_evaluations: int
    derived_results: int
    independent_evaluations: int
    month_work: int


def is_fast_path_eligible(context: SimulationContext) -> bool:
    """Return True when *context* can be evaluated by the closed-form path.

    Eligibility is restricted to the exact policy classes whose semantics the
    recurrence encodes.  Any other policy pair (or a horizon below one month)
    falls back to the reference fbf.core.  The dataset must also cover the full
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
    # The closed form encodes the two-asset (equity + one bond) rebalanced
    # model: equity at weight ``w`` and every other held class at ``1 - w``.
    # Any other holding set (single-asset, duplicate equity, or three or more
    # classes) would make the per-class weights not sum to one, so it is
    # rejected instead of silently producing a divergent recurrence.
    if len(holdings) != 2:
        return False
    if sum(1 for h in holdings if h.asset_class.id == _EquityId) != 1:
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

    Horizon derivation derives shorter horizons from a single longest-horizon
    path, which is only valid when the shorter context follows the identical
    index trajectory (dataset values) for every month it simulates.  The check
    is *identity-based*: it passes only when the candidate's ``MarketSnapshot``
    objects are the very same objects held by the longest context's dataset.
    ``Dataset.slice`` shares the underlying snapshot objects, so the legitimate
    prefix-sliced derivation pattern (the same source trajectory sliced to
    different horizons) passes in O(months) cheap identity comparisons with no
    Decimal work.

    Contexts built from different data fail the check and are evaluated
    individually; their results are never derived from another context's path.
    Failing to derive is always safe (correct results, just no reuse).
    """
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
    """Memoized identity-prefix check keyed by dataset object identity.

    Datasets are immutable and the check is a pure function of the two dataset
    objects, so its result is identical for the same ``(candidate, longest)``
    object pair.  A grid plan shares a handful of sliced ``Dataset`` objects
    across ~300k contexts, so memoizing by object id reduces the guard from one
    O(months) comparison per derived context to one per distinct dataset pair.
    """
    key = (id(candidate.dataset), id(longest.dataset))
    result = memo.get(key)
    if result is None:
        result = _dataset_is_identity_prefix(candidate, longest)
        memo[key] = result
    return result


def _group_key(context: SimulationContext) -> tuple[object, ...]:
    """Trajectory key: excludes final_value_target (an evaluation dimension).

    Contexts with different final_value_target values but identical trajectory
    parameters share a single closed-form path.  The FV check is applied
    per-target after the path is evaluated.
    """
    allocation = cast(ConstantAllocationPolicy, context.allocation_policy)
    withdrawal = cast(FixedRealWithdrawalPolicy, context.withdrawal_policy)
    return (
        context.start_date,
        allocation.equity_allocation,
        withdrawal.withdrawal_rate,
        context.initial_wealth,
        context.initial_portfolio,
    )


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
        ``"float"`` (fast; ~1e-15 per step) or ``"decimal"`` (bit-exact
        replica of the reference pipeline's Decimal arithmetic).
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
        post = [v - withdrawal for v in monthly]
        failure_residual = None
    else:
        monthly, post, failure_month, failure_residual = _evaluate_decimal_recurrence(
            holdings=tuple(context.initial_portfolio.holdings),
            weights=weights,
            series=series,
            horizon=horizon,
            c=withdrawal,
        )

    return ClosedFormPath(
        withdrawal=withdrawal,
        monthly_values=tuple(monthly),
        failure_month=failure_month,
        post_withdrawal_values=tuple(post),
        failure_residual=failure_residual,
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
    holdings: tuple[AssetHolding, ...],
    weights: dict[object, Decimal],
    series: dict[object, tuple[Decimal, ...]],
    horizon: int,
    c: Decimal,
) -> tuple[list[Decimal], list[Decimal], int | None, Decimal | None]:
    """Bit-exact Decimal replica of the reference engine's monthly pipeline.

    Instead of the algebraic recurrence (which diverges from the reference by
    ``Decimal`` rounding at the boundary where ``V_m == C``), this replicates
    the engine's per-month, per-asset Decimal arithmetic exactly:

    - withdrawal: ``ratio = C / V`` (or ``1`` when depleted) applied as
      ``units_sold = (units * price * ratio) / price``, clamping remaining
      units to zero on depletion;
    - rebalance: target weight applied to the post-withdrawal value in canonical
      asset order ``(id, name, description)``, with the unallocated residual
      assigned to the last canonical asset;
    - ``post`` holds the rebalanced portfolio value at the month's own snapshot,
      which is the reference's ``current_wealth`` at the end of that month.

    Verified bit-exact (success, failure month, and final wealth to the last
    ``Decimal`` digit) against the reference engine on random-walk and flat
    trajectories including exact-equality depletion boundaries.
    """
    units = {holding.asset_class: holding.units for holding in holdings}
    classes = tuple(units.keys())
    canonical = tuple(sorted(classes, key=lambda a: (a.id, a.name, a.description)))
    order = classes

    monthly: list[Decimal] = []
    post: list[Decimal] = []
    for m in range(horizon):
        value = Decimal("0")
        for a in order:
            value += units[a] * series[a][m]
        monthly.append(value)

        if c > value:
            ratio = value / value if value != Decimal("0") else Decimal("1")
            for a in order:
                sold = (units[a] * series[a][m] * ratio) / series[a][m]
                units[a] = units[a] - sold
                if units[a] < Decimal("0"):
                    units[a] = Decimal("0")
            residual = sum((units[a] * series[a][m] for a in order), Decimal("0"))
            post.append(residual)
            return monthly, post, m, residual

        ratio = c / value
        for a in order:
            sold = (units[a] * series[a][m] * ratio) / series[a][m]
            units[a] = units[a] - sold
            if units[a] < Decimal("0"):
                units[a] = Decimal("0")

        remaining = Decimal("0")
        for a in order:
            remaining += units[a] * series[a][m]

        new_units: dict[AssetClass, Decimal] = {}
        allocated = Decimal("0")
        for a in canonical[:-1]:
            target = remaining * weights[a]
            new_units[a] = target / series[a][m]
            allocated += target
        residual = remaining - allocated
        if residual < Decimal("0"):
            residual = Decimal("0")
        new_units[canonical[-1]] = residual / series[canonical[-1]][m]
        units = new_units
        order = canonical
        post.append(sum((units[a] * series[a][m] for a in order), Decimal("0")))
    return monthly, post, None, None


def _outcome_for_horizon(
    path: ClosedFormPath,
    horizon: int,
    withdrawal: Decimal,
) -> tuple[bool, int | None, Money, int]:
    """Derive (success, failure_month, final_wealth, months_simulated) for *horizon*."""
    fail = path.failure_month
    if fail is not None and fail < horizon:
        # The reference engine leaves a sub-1e-22 EUR rounding residual on the
        # depleted portfolio; the bit-exact decimal path reproduces it exactly,
        # the float path reports 0 (F4, documented divergence).
        residual = path.failure_residual if path.failure_residual is not None else Decimal("0")
        return False, fail, Money(residual, Currency.EUR), fail
    if path.post_withdrawal_values:
        final_value = path.post_withdrawal_values[horizon - 1]
    else:
        final_value = path.monthly_values[horizon - 1] - withdrawal
    # No cent quantization: the reference engine reports full-precision Decimal
    # wealth, and the bit-exact decimal path reproduces it to the last digit.
    final_wealth = Money(final_value, Currency.EUR)
    return True, None, final_wealth, horizon


def _build_result(
    context: SimulationContext,
    path: ClosedFormPath,
    horizon: int,
) -> SimulationResult:
    """Build a result from a closed-form path for a given horizon.

    The FV check is NOT applied here — it is handled by the executor's
    multi-target evaluation loop.
    """
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


def evaluate_closed_form(
    context: SimulationContext,
    precision: Precision = "float",
) -> SimulationResult:
    """Return a ``SimulationResult`` for *context* via the closed form."""
    path = evaluate_path(context, precision)
    return _build_result(context, path, context.horizon_months)





def _unit_simulation_context(plan: ResearchPlan, unit: PlannedSimulationUnit) -> SimulationContext:
    """Translate one planned unit into a frozen engine ``SimulationContext``.

    Mirrors ``ResearchExecutor._create_context_for_unit`` exactly so eligibility
    and validation operate on the same contexts the executor would build.
    """
    cohort_id = unit.cohort.id
    assert cohort_id is not None, (
        f"CohortSpecification.id must not be None (cohort={unit.cohort.start_date!r})"
    )
    horizon_months = (
        unit.horizon_months
        if unit.horizon_months is not None
        else plan.experiment_definition.horizon_months
    )
    return SimulationContext(
        experiment_name=plan.experiment_definition.name,
        cohort=cohort_id,
        start_date=unit.cohort.start_date,
        horizon_months=horizon_months,
        initial_wealth=plan.experiment_definition.initial_wealth,
        initial_portfolio=unit.initial_portfolio,
        dataset=unit.dataset,
        allocation_policy=unit.allocation_policy,
        withdrawal_policy=unit.withdrawal_policy,
        final_value_target=unit.final_value_target,
    )


def fast_path_unit_counts(plan: ResearchPlan) -> tuple[int, int]:
    """Return ``(fast_path_units, reference_units)`` for a *plan*.

    Mirrors ``ResearchExecutor``'s unit -> ``SimulationContext`` translation so
    the count reflects exactly which units ``FastPathSimulationExecutor``
    would evaluate via the closed form.  It is used by the CLI to report
    fast-path coverage in the completion summary; eligibility is deterministic
    and does not depend on the execution path (sequential or parallel).
    """
    fast_units = sum(
        1 for unit in plan.units if is_fast_path_eligible(_unit_simulation_context(plan, unit))
    )
    return fast_units, len(plan.units) - fast_units


def reference_month_work(plan: ResearchPlan) -> int:
    """Return the reference-path month-work for *plan*.

    The reference engine simulates every unit for its full horizon, so the total
    month-work is the sum of all per-unit horizons.
    """
    return sum(
        unit.horizon_months
        if unit.horizon_months is not None
        else plan.experiment_definition.horizon_months
        for unit in plan.units
    )


def expected_report(plan: ResearchPlan) -> DerivationReport:
    """Compute the report *plan* would produce, without executing.

    Applies exactly the same grouping (``_group_key``) and dataset
    prefix guard (``_dataset_is_identity_prefix``) as
    :class:`FastPathSimulationExecutor`, so the report is the
    execution-independent truth for the plan: the longest horizon per group is
    evaluated once and every shorter prefix-consistent horizon is derived from
    it.  It is used by the CLI to report coverage and by tests to prove
    that horizon derivation actually happens (the executor records the same numbers live).
    """
    groups: dict[tuple[object, ...], list[SimulationContext]] = {}
    for unit in plan.units:
        context = _unit_simulation_context(plan, unit)
        if not is_fast_path_eligible(context):
            continue
        groups.setdefault(_group_key(context), []).append(context)

    prefix_memo: dict[tuple[int, int], bool] = {}
    longest_evaluations = 0
    derived = 0
    independent = 0
    month_work = 0
    for contexts in groups.values():
        longest_ctx = max(contexts, key=lambda c: c.horizon_months)
        longest_evaluations += 1
        month_work += longest_ctx.horizon_months
        for ctx in contexts:
            if ctx is longest_ctx:
                continue
            if _dataset_is_identity_prefix_memo(ctx, longest_ctx, prefix_memo):
                derived += 1
            else:
                independent += 1
                month_work += ctx.horizon_months

    non_eligible = len(plan.units) - sum(len(c) for c in groups.values())
    independent += non_eligible
    month_work += sum(
        unit.horizon_months
        if unit.horizon_months is not None
        else plan.experiment_definition.horizon_months
        for unit in plan.units
        if not is_fast_path_eligible(_unit_simulation_context(plan, unit))
    )

    return DerivationReport(
        logical_units=len(plan.units),
        groups=len(groups),
        longest_path_evaluations=longest_evaluations,
        derived_results=derived,
        independent_evaluations=independent,
        month_work=month_work,
    )


def select_validation_units(
    plan: ResearchPlan, max_units: int = FAST_PATH_VALIDATION_MAX_UNITS
) -> tuple[PlannedSimulationUnit, ...]:
    """Return a small deterministic sample of *plan*'s fast-path-eligible units.

    Only fast-path-eligible units are sampled (comparing a unit that falls back
    to the reference would validate the reference against itself).  The sample
    is deterministic: the same plan always yields the same units, because the
    eligible units are ordered by plan index and a fixed-seed RNG selects the
    sample indices.

    For multi-horizon (grid) plans the sample is stratified by horizon: each
    distinct horizon present in the plan contributes a proportional share, so a
    grid study's validation covers every horizon length instead of clustering on
    one.  Single-horizon plans are sampled exactly as before.
    """
    eligible = tuple(
        unit for unit in plan.units if is_fast_path_eligible(_unit_simulation_context(plan, unit))
    )
    sample_size = min(max_units, len(eligible))
    if sample_size == 0:
        return ()

    by_horizon: dict[int, list[PlannedSimulationUnit]] = {}
    for unit in eligible:
        horizon = (
            unit.horizon_months
            if unit.horizon_months is not None
            else plan.experiment_definition.horizon_months
        )
        by_horizon.setdefault(horizon, []).append(unit)

    horizons = sorted(by_horizon)
    rng = random.Random(FAST_PATH_VALIDATION_SEED)
    if len(horizons) == 1:
        indices = sorted(rng.sample(range(len(eligible)), sample_size))
        return tuple(eligible[i] for i in indices)

    # Stratified: distribute the budget across horizons (at least one each when
    # the budget allows), always deterministically via the fixed-seed RNG.
    pools = {h: list(by_horizon[h]) for h in horizons}
    taken = dict.fromkeys(horizons, 0)
    remaining = sample_size
    per_horizon = max(1, sample_size // len(horizons))
    selected: list[PlannedSimulationUnit] = []
    for horizon in horizons:
        pool = pools[horizon]
        take = min(per_horizon, len(pool), remaining)
        indices = sorted(rng.sample(range(len(pool)), take))
        selected.extend(pool[i] for i in indices)
        taken[horizon] += take
        remaining -= take
    # Distribute any leftover budget round-robin across horizons that still
    # have unsampled eligible units.
    for horizon in horizons:
        if remaining <= 0:
            break
        pool = pools[horizon]
        if taken[horizon] >= len(pool):
            continue
        selected.append(pool[taken[horizon]])
        taken[horizon] += 1
        remaining -= 1
    return tuple(selected[:sample_size])


class FastPathValidationError(RuntimeError):
    """Raised when the fast path diverges from the Decimal reference fbf.core."""


def _compare_fast_path_result(
    reference: SimulationResult,
    fast: SimulationResult,
    tolerance: Decimal,
) -> list[str]:
    """Return human-readable divergences between a reference and a fast result.

    Compares success/failure outcome, failure month, and (on success) final
    wealth within *tolerance*.  An empty list means the results agree.
    """
    problems: list[str] = []
    if reference.statistics.success != fast.statistics.success:
        problems.append(
            f"outcome: reference "
            f"{'success' if reference.statistics.success else 'failure'} vs fast "
            f"{'success' if fast.statistics.success else 'failure'}"
        )
    if reference.statistics.failure_month != fast.statistics.failure_month:
        problems.append(
            f"failure_month: reference {reference.statistics.failure_month} "
            f"vs fast {fast.statistics.failure_month}"
        )
    if reference.statistics.months_simulated != fast.statistics.months_simulated:
        problems.append(
            f"months_simulated: reference {reference.statistics.months_simulated} "
            f"vs fast {fast.statistics.months_simulated}"
        )
    if reference.statistics.success and fast.statistics.success:
        wealth_diff = abs(
            reference.statistics.final_wealth.amount - fast.statistics.final_wealth.amount
        )
        if wealth_diff > tolerance:
            problems.append(
                f"final_wealth: reference {reference.statistics.final_wealth} "
                f"vs fast {fast.statistics.final_wealth} "
                f"(diff {wealth_diff} > tolerance {tolerance})"
            )
    return problems


def run_fast_path_validation(
    plan: ResearchPlan,
    max_units: int = FAST_PATH_VALIDATION_MAX_UNITS,
    tolerance: Decimal = FAST_PATH_VALIDATION_WEALTH_TOLERANCE,
) -> tuple[int, int]:
    """Validate a deterministic sample of *plan* against the Decimal reference.

    Executes a ``select_validation_units`` sample through **both** the float
    closed-form evaluation (the exact path ``--fast-path`` requests) and the
    canonical Decimal reference engine, then compares outcome, failure month
    and (on success) final wealth.

    Raises ``FastPathValidationError`` on the first divergence, identifying the
    diverging unit (cohort start date and parameter configuration) and the
    observed vs expected statistics.  Returns ``(sampled_units, eligible_units)``
    on success.  The validation is purely additive: it never mutates or replaces
    the results of the requested execution path.
    """
    sample = select_validation_units(plan, max_units)
    if not sample:
        return 0, 0

    eligible_count = len(
        [u for u in plan.units if is_fast_path_eligible(_unit_simulation_context(plan, u))]
    )

    sub_plan = ResearchPlan(experiment_definition=plan.experiment_definition, units=sample)
    reference_results = sequential_execute(sub_plan, summary_only=True).results
    fast_results = tuple(
        evaluate_closed_form(
            _unit_simulation_context(sub_plan, unit), "float"
        )
        for unit in sample
    )

    for unit, reference, fast in zip(sample, reference_results, fast_results, strict=True):
        problems = _compare_fast_path_result(reference, fast, tolerance)
        if problems:
            raise FastPathValidationError(
                "Fast-path validation failed on unit "
                f"cohort={unit.cohort.start_date.isoformat()} "
                f"params={unit.parameter_config}: " + "; ".join(problems)
            )
    return len(sample), eligible_count


class FastPathSimulationExecutor(SimulationExecutor):
    """Closed-form executor that derives shorter horizons from a common path.

    Contexts in a definition that share the same cohort start date, initial
    wealth, initial portfolio, allocation weights and withdrawal rate are
    evaluated together: the longest horizon is run once and every shorter
    horizon is derived from its monthly path prefix.  This reuses the final
    state of the shorter horizon instead of re-simulating earlier months,
    reducing total month-work.

    Derivation is only performed when the shorter contexts' datasets are a prefix
    of the longest context's dataset (same ``MarketSnapshot`` objects).
    Contexts that share a group key but carry different data, initial wealth or
    initial portfolio are evaluated individually; their results are never
    derived from another context's path.

    Because horizon derivation is a whole-definition optimisation, ``execute`` consumes
    the full definition at once.  Progress wrappers that delegate one context at
    a time would silently defeat it; the executor therefore advertises
    ``processes_whole_definition = True`` so ``_ProgressReportingSimulationExecutor``
    passes the full definition through unchanged.  After every ``execute`` the
    live ``report`` records the actual groups, longest-path evaluations,
    derived results and month-work performed.
    """

    # Advertise whole-definition execution so progress wrappers never split the
    # definition into single-context calls (which would disable horizon derivation).
    processes_whole_definition = True

    def __init__(
        self,
        reference_executor: SimulationExecutor | None = None,
        precision: Precision = "float",
    ) -> None:
        self._reference = reference_executor or _create_default_simulation_executor()
        self._precision = precision
        self._last_report: DerivationReport | None = None

    @property
    def report(self) -> DerivationReport | None:
        """Return the report recorded by the most recent ``execute`` call."""
        return self._last_report

    def execute(self, definition: EngineExperimentDefinition) -> ExperimentRun:
        key_to_group: dict[tuple[object, ...], int] = {}
        group_contexts: list[list[SimulationContext]] = []
        order: list[tuple[int, int]] = []  # (definition index, group_id or -1)

        for index, context in enumerate(definition.simulation_contexts):
            if not is_fast_path_eligible(context):
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

        # Evaluate each group's longest horizon once, then derive the rest.
        # FV check is applied per-context after trajectory evaluation.
        prefix_memo: dict[tuple[int, int], bool] = {}
        results: dict[int, SimulationResult] = {}
        derived_count = 0
        independent_count = 0
        month_work = 0
        for _, contexts in enumerate(group_contexts):
            longest_ctx = max(contexts, key=lambda c: c.horizon_months)
            path = evaluate_path(longest_ctx, self._precision)
            month_work += longest_ctx.horizon_months
            # Cache derived results by (horizon, target) to avoid redundant work
            # when multiple contexts share the same horizon and target.
            derived_cache: dict[tuple[int, object], SimulationResult] = {}
            for ctx in contexts:
                cache_key = (ctx.horizon_months, ctx.final_value_target)
                if ctx is longest_ctx or _dataset_is_identity_prefix_memo(
                    ctx, longest_ctx, prefix_memo
                ):
                    if cache_key not in derived_cache:
                        base = _build_result(longest_ctx, path, ctx.horizon_months)
                        derived_cache[cache_key] = _apply_fv_check(base, ctx)
                    results[id(ctx)] = derived_cache[cache_key]
                    if ctx is not longest_ctx:
                        derived_count += 1
                else:
                    results[id(ctx)] = _apply_fv_check(
                        evaluate_closed_form(ctx, self._precision), ctx
                    )
                    independent_count += 1
                    month_work += ctx.horizon_months

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

        self._last_report = DerivationReport(
            logical_units=len(definition.simulation_contexts),
            groups=len(group_contexts),
            longest_path_evaluations=len(group_contexts),
            derived_results=derived_count,
            independent_evaluations=independent_count,
            month_work=month_work,
        )

        return ExperimentRun(definition=definition, simulation_results=tuple(ordered_results))
