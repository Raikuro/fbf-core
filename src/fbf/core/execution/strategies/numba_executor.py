"""Numba-accelerated executor with horizon derivation and growth-factor cache.

Executor that evaluates eligible contexts (ConstantAllocationPolicy +
FixedRealWithdrawalPolicy) using the Numba scalar kernel, reusing a
longest-horizon evaluation to derive shorter-horizon results for
prefix-consistent context families.

Growth factors depend only on (market trajectory, allocation weights) and
are cached per executor instance to eliminate redundant computation across
groups sharing the same trajectory and allocation.  Trajectory identity is
part of the cache key (a dataset-identity token), so contexts built from
different market data never share growth factors.

Every context must be handled by one of the Numba kernels; ineligible
contexts are rejected rather than delegated to another engine.

Architecture
------------
The Numba kernel computes the same scalar recurrence as the independent
Decimal oracle::

    V_0      = value(initial_portfolio @ snapshot_0)
    C        = V_0 * withdrawal_rate / 12          (constant real withdrawal)
    g_m      = sum_j w_j * P_{j,m+1} / P_{j,m}   (varies by month)
    V_{m+1}  = (V_m - C) * g_m

Horizon derivation works by replaying the recurrence from the initial
value through the first H months of growth factors, where H is the
shorter horizon.  This is valid because all contexts in a group share
identical growth factors, initial value, and withdrawal amount.

For glidepath strategies, the growth factors vary by month because the
target equity weight changes.  The equity weight sequence is precomputed
from the glidepath parameters (including the monthly or annual cadence) and
the canonical market data:

    g_m = w_m * equity_return[m] + (1 - w_m) * bond_return[m]

where w_m is the equity weight after rebalancing at month m.  Fixed-real
withdrawals use the workbook timing; escalating withdrawals keep their own
documented timing.  The two contracts are evaluated separately.

Growth-factor caching
---------------------
Growth factors are a function of (market trajectory, allocation weights)
only.  They do not depend on withdrawal rate, initial wealth, or horizon.
The cache key is (start_date, equity_allocation, dataset_token) for static
strategies, or (start_date, glidepath_params, cadence, expense_ratio,
dataset_token) for glidepath strategies.  For the ERN workload this
significantly reduces growth-factor computation.

Glidepath growth-factor cache key:
(start_date, glidepath_type, start_equity, end_equity, slope, mode,
cadence, expense_ratio, dataset_token)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import cast

import numpy as np
from numpy.typing import NDArray

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import (
    BuyAndHoldAllocationPolicy,
    ConstantAllocationPolicy,
    ConstantWithdrawalPolicy,
    EscalatingWithdrawalPolicy,
    FixedRealWithdrawalPolicy,
    allocation_identity,
)
from fbf.core.domain.policies.frequency import WithdrawalFrequency
from fbf.core.domain.policies.glidepath import (
    GlidepathAllocationPolicy,
    GlidepathCadence,
)
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
    _group_key,
    _index_series,
    _trajectory_clusters,
    _weights_by_class,
    is_constant_allocation_eligible,
)
from fbf.core.execution.strategies.numba_kernel import (
    _compute_growth_factors_numpy,
    _compute_workbook_scr,
    _materialize_price_float,
    _simulate_trajectory,
    _simulate_trajectory_buy_and_hold,
    _simulate_trajectory_constant_nominal,
    _simulate_trajectory_escalating,
    _simulate_trajectory_workbook,
    compute_growth_factors_varying_weights_batch,
)
from fbf.core.execution.strategies.trajectory import build_simulation_timeline

# Growth-factor cache key (static): (start_date, allocation_identity, dataset_token).
# The allocation identity is the canonical, order-insensitive ``(asset_id, weight)``
# tuple so that distinct allocations never collide.  The dataset token
# disambiguates contexts that share a start date but not a market trajectory.
WeightIdentity = tuple[tuple[str, Decimal], ...]
GFKey = tuple[date, WeightIdentity, int]

# Glidepath trajectory-parameter key (no dataset identity):
# (start_date, glidepath_type, start_equity, end_equity, slope, mode,
#  cadence, expense_ratio, withdrawal_rate, initial_portfolio)
GlidepathGroupKey = tuple[
    date,
    str,
    Decimal,
    Decimal,
    Decimal,
    str,
    GlidepathCadence,
    Decimal,
    Decimal,
    object,
]

# Glidepath growth-factor cache key:
# (start_date, glidepath_type, start_equity, end_equity, slope, mode,
#  cadence, expense_ratio, dataset_token)
GlidepathGFKey = tuple[
    date, str, Decimal, Decimal, Decimal, str, GlidepathCadence, Decimal, int
]

# Glidepath + escalating trajectory key (no dataset identity):
# (start_date, glidepath_type, start_equity, end_equity, slope, mode,
#  cadence, expense_ratio, withdrawal_rate, escalation_rate, frequency,
#  initial_portfolio)
GlidepathEscalatingGroupKey = tuple[
    date,
    str,
    Decimal,
    Decimal,
    Decimal,
    str,
    GlidepathCadence,
    Decimal,
    Decimal,
    Decimal,
    WithdrawalFrequency,
    object,
]


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


def _initial_value_equals_wealth(context: SimulationContext) -> bool:
    """Return True when the initial portfolio's value equals ``initial_wealth``.

    ``build_initial_portfolio`` constructs the initial holdings so that their
    month-0 value equals ``initial_wealth``.  The Numba trajectories derive
    their withdrawal base from that initial portfolio value (``v0``) whereas the
    withdrawal policies derive it from ``context.initial_wealth``.  Sharing one
    evaluated path, and omitting ``initial_wealth`` from the trajectory key,
    therefore requires the two to agree.  The equality is exact for the
    supported two-asset portfolios; for larger portfolios the underlying
    Decimal divisions may round, so a mismatch is rejected here.
    """
    snapshot = context.dataset[0]
    value = Decimal("0")
    for holding in context.initial_portfolio.holdings:
        price = snapshot.index_levels.get(holding.asset_class)
        if price is None:
            return False
        value += holding.units * price
    return value == context.initial_wealth.amount


def _is_constant_nominal_eligible(context: SimulationContext) -> bool:
    """Return True when *context* can use the Numba backend for constant nominal withdrawal.

    Eligibility criteria: ConstantAllocationPolicy + ConstantWithdrawalPolicy,
    monthly frequency, sufficient dataset, two-asset portfolio.
    """
    if not isinstance(context.allocation_policy, ConstantAllocationPolicy):
        return False
    if context.allocation_policy.allocations is not None:
        # Explicit N-asset allocations are only supported by the fixed-real
        # workbook path; constant-nominal rejects them.
        return False
    if not isinstance(context.withdrawal_policy, ConstantWithdrawalPolicy):
        return False
    if context.withdrawal_policy.frequency is not WithdrawalFrequency.MONTHLY:
        return False
    if context.horizon_months is None or context.horizon_months < 1:
        return False
    if context.dataset is None or len(context.dataset.snapshots) < 1:
        return False
    if len(context.dataset.snapshots) < context.horizon_months:
        return False
    holdings = context.initial_portfolio.holdings
    if not holdings or len(holdings) != 2:
        return False
    equity_count = sum(1 for h in holdings if h.asset_class.id == "equity")
    if equity_count != 1:
        return False
    return not any(h.asset_class not in context.dataset[0].index_levels for h in holdings)


def _is_escalating_eligible(context: SimulationContext) -> bool:
    """Return True when *context* can use the Numba backend for escalating withdrawal.

    Eligibility criteria: ConstantAllocationPolicy + EscalatingWithdrawalPolicy,
    sufficient dataset, two-asset portfolio.
    """
    if not isinstance(context.allocation_policy, ConstantAllocationPolicy):
        return False
    if context.allocation_policy.allocations is not None:
        # Explicit N-asset allocations are only supported by the fixed-real
        # workbook path; escalating rejects them.
        return False
    if not isinstance(context.withdrawal_policy, EscalatingWithdrawalPolicy):
        return False
    if context.horizon_months is None or context.horizon_months < 1:
        return False
    if context.dataset is None or len(context.dataset.snapshots) < 1:
        return False
    if len(context.dataset.snapshots) < context.horizon_months:
        return False
    holdings = context.initial_portfolio.holdings
    if not holdings or len(holdings) != 2:
        return False
    equity_count = sum(1 for h in holdings if h.asset_class.id == "equity")
    if equity_count != 1:
        return False
    if any(h.asset_class not in context.dataset[0].index_levels for h in holdings):
        return False
    # The escalating trajectory derives its withdrawal base from ``v0`` while
    # the legacy policy uses ``initial_wealth``; they must agree (see
    # ``_initial_value_equals_wealth``).
    return _initial_value_equals_wealth(context)


def _is_glidepath_escalating_eligible(context: SimulationContext) -> bool:
    """Return True for a glidepath allocation with escalating withdrawals.

    The combined capability uses the documented escalating-withdrawal timing
    (withdrawal before growth, no growth after the final withdrawal) while the
    glidepath target weight advances according to its own cadence.  It is a
    separate contract from the workbook fixed-real glidepath path.
    """
    if not isinstance(context.allocation_policy, GlidepathAllocationPolicy):
        return False
    if not isinstance(context.withdrawal_policy, EscalatingWithdrawalPolicy):
        return False
    if context.horizon_months is None or context.horizon_months < 1:
        return False
    if context.dataset is None or len(context.dataset.snapshots) < 1:
        return False
    if len(context.dataset.snapshots) < context.horizon_months:
        return False
    holdings = context.initial_portfolio.holdings
    if not holdings or len(holdings) != 2:
        return False
    equity_count = sum(1 for h in holdings if h.asset_class.id == "equity")
    if equity_count != 1:
        return False
    if any(h.asset_class not in context.dataset[0].index_levels for h in holdings):
        return False
    return _initial_value_equals_wealth(context)


def _is_glidepath_eligible(context: SimulationContext) -> bool:
    """Return True when *context* is a glidepath strategy eligible for Numba.

    Glidepath eligibility requires:
    - GlidepathAllocationPolicy (passive or active)
    - FixedRealWithdrawalPolicy with monthly frequency
    - Sufficient dataset (horizon months of prices)
    - Two-asset portfolio (equity + bond)
    """
    if not isinstance(context.allocation_policy, GlidepathAllocationPolicy):
        return False
    if not isinstance(context.withdrawal_policy, FixedRealWithdrawalPolicy):
        return False
    if context.withdrawal_policy.frequency is not WithdrawalFrequency.MONTHLY:
        return False
    if context.horizon_months is None or context.horizon_months < 1:
        return False
    if context.dataset is None or len(context.dataset.snapshots) < 1:
        return False
    if len(context.dataset.snapshots) < context.horizon_months:
        return False
    holdings = context.initial_portfolio.holdings
    if not holdings or len(holdings) != 2:
        return False
    equity_count = sum(1 for h in holdings if h.asset_class.id == "equity")
    if equity_count != 1:
        return False
    return not any(h.asset_class not in context.dataset[0].index_levels for h in holdings)


def _is_buy_and_hold_eligible(context: SimulationContext) -> bool:
    """Return True when *context* can use the Numba buy-and-hold kernel.

    Eligibility requires the buy-and-hold allocation policy (no periodic
    rebalancing), a monthly constant-real withdrawal policy, a sufficient
    dataset, and a two-asset (equity + bond) portfolio.  Expense ratios use the
    workbook additive convention (``blended_return - fee/12``) inside the kernel; the
    legacy buy-and-hold fee path was removed, so there is no stale-base
    correction to reproduce.

    The withdrawal base is the value-independent initial portfolio value
    (``v0``) while the withdrawal amount is derived from ``initial_wealth``;
    the two must agree (see ``_initial_value_equals_wealth``).
    """
    if not isinstance(context.allocation_policy, BuyAndHoldAllocationPolicy):
        return False
    if not isinstance(context.withdrawal_policy, FixedRealWithdrawalPolicy):
        return False
    if context.withdrawal_policy.frequency is not WithdrawalFrequency.MONTHLY:
        return False
    if context.horizon_months is None or context.horizon_months < 1:
        return False
    if context.dataset is None or len(context.dataset.snapshots) < 1:
        return False
    if len(context.dataset.snapshots) < context.horizon_months:
        return False
    holdings = context.initial_portfolio.holdings
    if not holdings or len(holdings) != 2:
        return False
    equity_count = sum(1 for h in holdings if h.asset_class.id == "equity")
    if equity_count != 1:
        return False
    if any(h.asset_class not in context.dataset[0].index_levels for h in holdings):
        return False
    return _initial_value_equals_wealth(context)


def is_numba_context_eligible(context: SimulationContext) -> bool:
    """Return True when the generic Numba executor can run *context* itself.

    This is the admission predicate for an explicit ``FAST`` request.  It
    requires one of the generic Numba policy families and rejects context
    features that the generic kernels do not model.  In particular, debt and
    LTV fields belong to the dedicated Part 49/52 executors; the generic
    kernels would otherwise ignore them.

    Fixed-real contexts that use the non-workbook recurrence derive
    their withdrawal from ``v0`` while the reference policy derives it from
    ``initial_wealth``.  Such contexts are admitted only when the two values
    are exactly equal.  Workbook SCR contexts use ``v0`` as their explicit
    starting value and do not require that equality.
    """
    if context.loan_draw_rate is not None or context.ltv_limit is not None:
        return False
    if is_constant_allocation_eligible(context):
        if context.final_value_target not in (None, Decimal("0")):
            return _initial_value_equals_wealth(context)
        return True
    if _is_constant_nominal_eligible(context):
        return True
    if _is_escalating_eligible(context):
        return True
    if _is_glidepath_escalating_eligible(context):
        return True
    if _is_buy_and_hold_eligible(context):
        return True
    if _is_glidepath_eligible(context):
        return _initial_value_equals_wealth(context)
    return False


def _numba_group_key(context: SimulationContext) -> tuple[object, ...] | None:
    """Return the generic Numba grouping key, or ``None`` when ineligible.

    Kept beside :func:`is_numba_context_eligible` so grouping and admission
    use the same policy-family precedence.  This function describes the
    executor's internal routing; ``FAST`` admission additionally applies the
    strict checks in :func:`is_numba_context_eligible`.
    """
    if is_constant_allocation_eligible(context):
        return _group_key(context)
    if _is_constant_nominal_eligible(context):
        return _constant_nominal_group_key(context)
    if _is_escalating_eligible(context):
        return _escalating_group_key(context)
    if _is_glidepath_escalating_eligible(context):
        return _glidepath_escalating_group_key(context)
    if _is_buy_and_hold_eligible(context):
        return _buy_and_hold_group_key(context)
    if _is_glidepath_eligible(context):
        return _glidepath_group_key(context)
    return None


def _buy_and_hold_group_key(context: SimulationContext) -> tuple[object, ...]:
    """Trajectory key for buy-and-hold contexts: excludes initial_wealth.

    The path depends on the market trajectory (``start_date`` + dataset),
    the target equity allocation, the withdrawal rate, the expense ratio, and
    the initial portfolio.  ``initial_wealth`` does not enter the kernel (the
    withdrawal base is ``v0``, derived from the initial portfolio), so it is
    excluded; the FV check is applied per-target afterwards.  Dataset identity
    is enforced separately by the identity-prefix clustering.
    """
    allocation = cast(BuyAndHoldAllocationPolicy, context.allocation_policy)
    withdrawal = cast(FixedRealWithdrawalPolicy, context.withdrawal_policy)
    return (
        context.start_date,
        allocation.equity_allocation,
        withdrawal.withdrawal_rate,
        context.expense_ratio or Decimal("0"),
        context.initial_portfolio,
    )


def _gf_cache_key(context: SimulationContext) -> GFKey:
    """Minimal cache key for growth-factor identity (static strategies).

    Growth factors depend only on (market trajectory, allocation weights).
    The start_date and dataset token determine the trajectory; the canonical
    allocation identity determines the target weights.  Withdrawal rate, initial
    wealth, horizon, and final_value_target do not affect growth factors.
    """
    allocation = cast(ConstantAllocationPolicy, context.allocation_policy)
    asset_classes = tuple(h.asset_class for h in context.initial_portfolio.holdings)
    return (
        context.start_date,
        allocation_identity(allocation, asset_classes),
        _dataset_token(context),
    )


def _constant_nominal_group_key(context: SimulationContext) -> tuple[object, ...]:
    """Trajectory key for constant nominal withdrawal: excludes initial_wealth.

    For ConstantWithdrawalPolicy, the withdrawal amount scales with the
    current portfolio value, not the initial wealth.  Therefore, contexts
    with different initial_wealth but same trajectory parameters can share
    the same growth-factor computation.  The FV check is applied per-target
    after the path is evaluated.
    """
    allocation = cast(ConstantAllocationPolicy, context.allocation_policy)
    withdrawal = cast(ConstantWithdrawalPolicy, context.withdrawal_policy)
    return (
        context.start_date,
        allocation.equity_allocation,
        withdrawal.withdrawal_rate,
        context.initial_portfolio,
    )


def _escalating_group_key(context: SimulationContext) -> tuple[object, ...]:
    """Trajectory key for escalating withdrawal: excludes initial_wealth.

    The withdrawal base is the value-independent initial portfolio value
    (``v0``), escalated by ``(1 + escalation_rate) ** (m // 12)``.  Contexts
    that share the trajectory parameters, withdrawal rate, escalation rate,
    cadence, and initial portfolio therefore share one evaluated path; the FV
    check is applied per-target afterwards.  ``initial_wealth`` does not enter
    the kernel, so it is excluded (matching ``_constant_nominal_group_key``).
    """
    allocation = cast(ConstantAllocationPolicy, context.allocation_policy)
    withdrawal = cast(EscalatingWithdrawalPolicy, context.withdrawal_policy)
    return (
        context.start_date,
        allocation.equity_allocation,
        withdrawal.withdrawal_rate,
        withdrawal.escalation_rate,
        withdrawal.frequency,
        context.initial_portfolio,
    )


def _glidepath_group_key(context: SimulationContext) -> GlidepathGroupKey:
    """Trajectory-parameter key for fixed-real glidepath contexts.

    Withdrawal rate, cadence, expense ratio, and the initial portfolio are
    part of the key: contexts that differ in any of them cannot share one
    evaluated trajectory.  Dataset identity is enforced separately by the
    identity-prefix guard.
    """
    allocation = cast(GlidepathAllocationPolicy, context.allocation_policy)
    withdrawal = cast(FixedRealWithdrawalPolicy, context.withdrawal_policy)
    return (
        context.start_date,
        "glidepath",
        allocation.start_equity,
        allocation.end_equity,
        allocation.slope,
        allocation.mode,
        allocation.cadence,
        context.expense_ratio or Decimal("0"),
        withdrawal.withdrawal_rate,
        context.initial_portfolio,
    )


def _glidepath_escalating_group_key(
    context: SimulationContext,
) -> GlidepathEscalatingGroupKey:
    """Trajectory-parameter key for glidepath + escalating contexts.

    The withdrawal base is the value-independent initial portfolio value
    (``v0``), so ``initial_wealth`` is excluded; the FV check is applied per
    context afterwards.  Withdrawal cadence and escalation rate must match,
    as must the glidepath cadence and expense ratio.
    """
    allocation = cast(GlidepathAllocationPolicy, context.allocation_policy)
    withdrawal = cast(EscalatingWithdrawalPolicy, context.withdrawal_policy)
    return (
        context.start_date,
        "glidepath-escalating",
        allocation.start_equity,
        allocation.end_equity,
        allocation.slope,
        allocation.mode,
        allocation.cadence,
        context.expense_ratio or Decimal("0"),
        withdrawal.withdrawal_rate,
        withdrawal.escalation_rate,
        withdrawal.frequency,
        context.initial_portfolio,
    )


def _glidepath_gf_cache_key(context: SimulationContext) -> GlidepathGFKey:
    """Cache key for glidepath growth factors.

    Growth factors depend on the market trajectory, the glidepath weight
    sequence, and the additive fee.  Withdrawal parameters do not enter the
    key, so fixed-real and escalating contexts may share them.  The dataset
    token keeps contexts built from different data from sharing growth factors.
    """
    allocation = cast(GlidepathAllocationPolicy, context.allocation_policy)
    return (
        context.start_date,
        "glidepath",
        allocation.start_equity,
        allocation.end_equity,
        allocation.slope,
        allocation.mode,
        allocation.cadence,
        context.expense_ratio or Decimal("0"),
        _dataset_token(context),
    )


def _compute_equity_weight_sequence(
    policy: GlidepathAllocationPolicy,
    is_underwater: list[bool],
    horizon: int,
) -> list[Decimal]:
    """Precompute the equity weight sequence for a glidepath.

    The annual cadence advances at ``m // 12`` boundaries: periods 0-11 use
    the initial target, period 12 advances once, and so on.  Monthly passive
    advances every period; active advances only in underwater periods.

    Parameters
    ----------
    policy:
        The glidepath allocation policy.
    is_underwater:
        List of is_underwater flags from the dataset (length >= horizon).
    horizon:
        Number of months to simulate.

    Returns
    -------
    List of equity weights per month (length = horizon).
    equity_weights[m] is the weight AFTER rebalancing at month m.
    """
    weights: list[Decimal] = []
    for m in range(horizon):
        if policy.cadence is GlidepathCadence.ANNUAL:
            advancement_count = m // 12
        elif policy.mode == "passive":
            advancement_count = m
        else:  # active
            advancement_count = sum(1 for i in range(m + 1) if is_underwater[i])
        raw = policy.start_equity + policy.slope * advancement_count
        equity = min(raw, policy.end_equity)
        weights.append(equity)
    return weights


def _extract_is_underwater(dataset: Dataset, horizon: int) -> list[bool]:
    """Extract is_underwater flags from dataset snapshots."""
    return [snap.is_underwater for snap in dataset.snapshots[:horizon]]


class NumbaSimulationExecutor(SimulationExecutor):
    """Numba-accelerated executor with horizon derivation and GF cache.

    Contexts sharing the same cohort start date, initial wealth, initial
    portfolio, allocation weights and withdrawal rate are evaluated together:
    the longest horizon is run once through the Numba kernel and every
    shorter horizon is derived by replaying the recurrence from the same
    initial value and growth factors.  Grouping is further split into
    identity-prefix clusters so a derived context only ever reuses a trajectory
    whose snapshots are the very same objects (see
    ``eligibility._trajectory_clusters``).

    Growth factors are cached by
    (start_date, equity_allocation, dataset_token), so computation is shared
    across groups with the same trajectory and allocation but differing in
    withdrawal rate, while contexts built from different market data never
    share growth factors.

    For glidepath strategies, growth factors are cached by
    (start_date, glidepath_type, start_equity, end_equity, slope, mode,
    dataset_token).  An optional shared glidepath GF cache can be provided to
    persist growth factors across multiple executor invocations (e.g., across
    bisection steps).

    Every context must be eligible for one of the Numba kernels.  An ineligible
    context raises ``UnsupportedConfigurationError``; there is no fallback
    execution engine.

    Advertises ``processes_whole_definition = True`` so progress wrappers
    pass the full definition through unchanged (preserving group-level
    optimisation).
    """

    processes_whole_definition = True

    def __init__(
        self,
        profiler: Profiler | None = None,
        glidepath_gf_cache: (
            dict[GlidepathGFKey, NDArray[np.float64]] | None
        ) = None,
        materialize_timeline: bool = False,
    ) -> None:
        self._profiler = profiler or NoOpProfiler()
        self._materialize_timeline = materialize_timeline
        self._last_report: NumbaReport | None = None
        self._gf_cache: dict[GFKey, NDArray[np.float64]] = {}
        self._glidepath_gf_cache: dict[GlidepathGFKey, NDArray[np.float64]] = {}
        self._shared_glidepath_gf_cache: (
            dict[GlidepathGFKey, NDArray[np.float64]] | None
        ) = glidepath_gf_cache
        self._price_float_cache: dict[int, NDArray[np.float64]] = {}
        self._index_series_cache: dict[int, dict[object, tuple[Decimal, ...]]] = {}
        # Per-asset (equity, bond) monthly growth factors keyed by dataset
        # identity token.  Buy-and-hold weights drift endogenously, so a single
        # blended growth-factor series cannot be precomputed; the per-asset
        # ratios are trajectory-only and shared across allocations/withdrawals.
        self._bh_growth_cache: dict[
            int, tuple[NDArray[np.float64], NDArray[np.float64]]
        ] = {}
        # Strong references that keep dataset-identity tokens unique for the
        # executor's lifetime (see ``execute``).
        self._dataset_refs: dict[int, Dataset] = {}

    @property
    def report(self) -> NumbaReport | None:
        """Return the report recorded by the most recent ``execute`` call."""
        return self._last_report

    @property
    def gf_cache(self) -> dict[GFKey, NDArray[np.float64]]:
        """Return the current growth-factor cache (read-only for inspection)."""
        return self._gf_cache

    def execute(self, definition: EngineExperimentDefinition) -> ExperimentRun:
        profiler = self._profiler

        # Cache keys embed an object-identity token for each context's dataset
        # (``_dataset_token``).  Holding a strong reference to every dataset the
        # executor has seen keeps those tokens unique for the executor's
        # lifetime, so cached growth factors and materialised prices remain
        # valid across execute calls (e.g. a reused worker executor) without
        # risking an id reused by a different trajectory.  The externally
        # supplied glidepath cache is owned by the caller and left untouched.
        for context in definition.simulation_contexts:
            dataset = context.dataset
            self._dataset_refs[id(dataset)] = dataset

        # --- Pass 1: group eligible contexts by trajectory parameters ---
        profiler.start("numba_grouping")
        key_to_contexts: dict[tuple[object, ...], list[SimulationContext]] = {}
        is_eligible: list[bool] = []
        for context in definition.simulation_contexts:
            key = _numba_group_key(context)
            if key is None or not is_numba_context_eligible(context):
                raise UnsupportedConfigurationError(
                    "Numba backend cannot execute this plan: a context is not "
                    "supported by the generic Numba kernels; non-escalating "
                    "generic withdrawals require monthly frequency "
                    f"(cohort={context.cohort!r}, "
                    f"start_date={context.start_date.isoformat()!r})."
                )
            is_eligible.append(True)
            key_to_contexts.setdefault(key, []).append(context)
        profiler.stop("numba_grouping")

        # --- Pass 1b: split each parameter group into identity-prefix clusters ---
        # Contexts that share trajectory parameters but were built from different
        # market data must never derive from one another; the identity-prefix
        # guard enforces this and keeps derivation correct.
        prefix_memo: dict[tuple[int, int], bool] = {}
        clusters: list[list[SimulationContext]] = []
        for contexts in key_to_contexts.values():
            clusters.extend(_trajectory_clusters(contexts, prefix_memo))

        # --- Pass 2a: precompute growth factors for static strategies ---
        profiler.start("numba_growth_factors_static")

        gf_cache_new = 0
        gf_cache_reused = 0
        for cluster in clusters:
            sample_ctx = cluster[0]
            if not (
                is_constant_allocation_eligible(sample_ctx)
                or _is_constant_nominal_eligible(sample_ctx)
                or _is_escalating_eligible(sample_ctx)
            ):
                continue
            max_h = max(ctx.horizon_months for ctx in cluster)
            gf_k = _gf_cache_key(sample_ctx)
            cached = self._gf_cache.get(gf_k)
            if cached is not None and len(cached) >= max_h:
                gf_cache_reused += 1
                continue
            gf_cache_new += 1
            weights = _weights_by_class(sample_ctx)

            # Materialised series/prices are per dataset object, independent of
            # allocation and horizon.
            dataset_key = _dataset_token(sample_ctx)
            if dataset_key not in self._index_series_cache:
                self._index_series_cache[dataset_key] = _index_series(sample_ctx)
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
            self._gf_cache[gf_k] = _compute_growth_factors_numpy(
                weights_f,
                prices_f,
                max_h,
                float(sample_ctx.expense_ratio or Decimal("0")),
            )
        profiler.stop("numba_growth_factors_static")

# --- Pass 2b: precompute growth factors for glidepath strategies ---
        profiler.start("numba_growth_factors_glidepath")
        glidepath_gf_cache_new = 0
        glidepath_gf_cache_reused = 0
        glidepath_gf_shared_hits = 0

        # Collect all glidepath GF computations that need to be performed
        glidepath_computations: list[tuple[GlidepathGFKey, int, SimulationContext]] = []
        for cluster in clusters:
            sample_ctx = cluster[0]
            if not (
                _is_glidepath_eligible(sample_ctx)
                or _is_glidepath_escalating_eligible(sample_ctx)
            ):
                continue
            max_h = max(ctx.horizon_months for ctx in cluster)
            glide_gf_k = _glidepath_gf_cache_key(sample_ctx)
            # Check shared cache first (persists across bisection steps)
            shared_cached = None
            if self._shared_glidepath_gf_cache is not None:
                shared_cached = self._shared_glidepath_gf_cache.get(glide_gf_k)
            if shared_cached is not None and len(shared_cached) >= max_h:
                # Copy from shared to local cache for fast access
                self._glidepath_gf_cache[glide_gf_k] = shared_cached
                glidepath_gf_shared_hits += 1
                continue
            # Check local cache
            cached = self._glidepath_gf_cache.get(glide_gf_k)
            if cached is not None and len(cached) >= max_h:
                glidepath_gf_cache_reused += 1
                continue
            glidepath_gf_cache_new += 1
            glidepath_computations.append((glide_gf_k, max_h, sample_ctx))

        # Batch compute growth factors for all new glidepath entries
        if glidepath_computations:
            # Collect inputs for batch processing
            batch_equity_weights = []
            batch_equity_prices = []
            batch_bond_prices = []
            batch_max_h = []
            batch_keys = []
            batch_fees = []

            for glide_gf_k, max_h, sample_ctx in glidepath_computations:
                # Extract is_underwater sequence from dataset
                is_underwater = _extract_is_underwater(sample_ctx.dataset, max_h)

                # Compute equity weight sequence
                policy = cast(GlidepathAllocationPolicy, sample_ctx.allocation_policy)
                equity_weights_decimal = _compute_equity_weight_sequence(
                    policy, is_underwater, max_h
                )
                equity_weights_float = np.array(
                    [float(w) for w in equity_weights_decimal], dtype=np.float64
                )

                # Extract equity and bond price series (per dataset object).
                glide_series_key = _dataset_token(sample_ctx)
                if glide_series_key not in self._index_series_cache:
                    self._index_series_cache[glide_series_key] = _index_series(sample_ctx)
                series = self._index_series_cache[glide_series_key]

                # Get equity and bond price arrays
                equity_class = cast(
                    AssetClass,
                    next(ac for ac in series if cast(AssetClass, ac).id == "equity"),
                )
                bond_class = cast(
                    AssetClass,
                    next(ac for ac in series if cast(AssetClass, ac).id == "bond"),
                )
                equity_prices = np.array(
                    [float(p) for p in series[equity_class]], dtype=np.float64
                )
                bond_prices = np.array([float(p) for p in series[bond_class]], dtype=np.float64)

                equity_weights_float = np.array(
                    [float(w) for w in equity_weights_decimal], dtype=np.float64
                )

                batch_equity_weights.append(equity_weights_float)
                batch_equity_prices.append(equity_prices)
                batch_bond_prices.append(bond_prices)
                batch_max_h.append(max_h)
                batch_keys.append(glide_gf_k)
                batch_fees.append(float(sample_ctx.expense_ratio or Decimal("0")))

            # Group by (max_h, fee) to avoid shape mismatches and to apply the
            # correct fee per batch.
            from collections import defaultdict

            GroupTuple = tuple[
                NDArray[np.float64],
                NDArray[np.float64],
                NDArray[np.float64],
                GlidepathGFKey,
                float,
            ]
            groups_by_batch: dict[tuple[int, float], list[GroupTuple]] = defaultdict(list)
            for equity_w, eq_prices, bd_prices, max_h, glide_gf_k, fee in zip(
                batch_equity_weights,
                batch_equity_prices,
                batch_bond_prices,
                batch_max_h,
                batch_keys,
                batch_fees,
                strict=True,
            ):
                groups_by_batch[(max_h, fee)].append(
                    (equity_w, eq_prices, bd_prices, glide_gf_k, fee)
                )

            for (max_h, batch_fee), group in groups_by_batch.items():
                if not group:
                    continue
                # All sequences in this group have the same max_h, so we can stack them
                batch_weights = np.stack([item[0] for item in group])
                batch_eq_prices = np.stack([item[1] for item in group])
                batch_bd_prices = np.stack([item[2] for item in group])
                batch_keys = [item[3] for item in group]

                # Compute GFs for this batch
                growth_factors_batch = compute_growth_factors_varying_weights_batch(
                    batch_weights, batch_eq_prices, batch_bd_prices, max_h, batch_fee
                )

                # Store results
                for j, glide_gf_k in enumerate(batch_keys):
                    gf = growth_factors_batch[j, :max_h]
                    self._glidepath_gf_cache[glide_gf_k] = gf
                    if self._shared_glidepath_gf_cache is not None:
                        self._shared_glidepath_gf_cache[glide_gf_k] = gf

        profiler.stop("numba_growth_factors_glidepath")

        # --- Pass 3: simulate each group using cached growth factors ---
        profiler.start("numba_kernel_execution")
        results: dict[int, SimulationResult] = {}
        stats: dict[str, int] = {
            "derived_count": 0,
            "independent_count": 0,
            "month_work": 0,
            "gf_hits": gf_cache_reused,
            "gf_misses": gf_cache_new,
            "glidepath_gf_hits": glidepath_gf_cache_reused + glidepath_gf_shared_hits,
            "glidepath_gf_misses": glidepath_gf_cache_new,
        }

        for cluster in clusters:
            sample_ctx = cluster[0]
            if is_constant_allocation_eligible(sample_ctx):
                self._process_static_group(cluster, results, stats)
            elif _is_constant_nominal_eligible(sample_ctx):
                self._process_constant_nominal_group(cluster, results, stats)
            elif _is_escalating_eligible(sample_ctx):
                self._process_escalating_group(cluster, results, stats)
            elif _is_glidepath_escalating_eligible(sample_ctx):
                self._process_glidepath_escalating_group(cluster, results, stats)
            elif _is_buy_and_hold_eligible(sample_ctx):
                self._process_buy_and_hold_group(cluster, results, stats)
            elif _is_glidepath_eligible(sample_ctx):
                self._process_glidepath_group(cluster, results, stats)
        profiler.stop("numba_kernel_execution")

        # Assemble results in original definition order.
        profiler.start("numba_assembly")
        ordered_results: list[SimulationResult] = []
        for index, context in enumerate(definition.simulation_contexts):
            if not is_eligible[index]:
                raise AssertionError(
                    "an ineligible context reached result assembly after the "
                    "eligibility check"
                )
            ordered_results.append(results[id(context)])
        profiler.stop("numba_assembly")

        longest_path_evaluations = sum(
            len({c.horizon_months for c in cluster}) for cluster in clusters
        )
        self._last_report = NumbaReport(
            logical_units=len(definition.simulation_contexts),
            groups=len(clusters),
            longest_path_evaluations=longest_path_evaluations,
            derived_results=stats["derived_count"] - longest_path_evaluations,
            independent_evaluations=stats["independent_count"],
            month_work=stats["month_work"],
            gf_cache_hits=stats["gf_hits"],
            gf_cache_misses=stats["gf_misses"],
        )

        profiler.record("numba_groups", len(clusters))
        profiler.record("numba_derived", stats["derived_count"])
        profiler.record("numba_independent", stats["independent_count"])
        profiler.record("numba_month_work", stats["month_work"])
        profiler.record("numba_gf_cache_hits", stats["gf_hits"])
        profiler.record("numba_gf_cache_misses", stats["gf_misses"])

        return ExperimentRun(definition=definition, simulation_results=tuple(ordered_results))

    def _use_workbook_scr(self, context: SimulationContext) -> bool:
        """Check if workbook SCR methodology should be used for this context."""
        if not isinstance(context.allocation_policy, ConstantAllocationPolicy):
            return False
        if not isinstance(context.withdrawal_policy, FixedRealWithdrawalPolicy):
            return False
        if context.final_value_target is not None and context.final_value_target != Decimal("0"):
            return False
        if context.loan_draw_rate is not None:
            return False
        return context.ltv_limit is None

    def _process_static_group(
        self,
        contexts: list[SimulationContext],
        results: dict[int, SimulationResult],
        stats: dict[str, int],
    ) -> None:
        """Process a group of static (ConstantAllocationPolicy) contexts."""
        horizon_to_ctxs: dict[int, list[SimulationContext]] = {}
        for ctx in contexts:
            horizon_to_ctxs.setdefault(ctx.horizon_months, []).append(ctx)

        sample_ctx = contexts[0]
        initial_snapshot = sample_ctx.dataset[0]
        v0 = float(sum(
            holding.units * initial_snapshot.index_levels[holding.asset_class]
            for holding in sample_ctx.initial_portfolio.holdings
        ))
        withdrawal_policy = cast(FixedRealWithdrawalPolicy, sample_ctx.withdrawal_policy)
        rate_f = float(withdrawal_policy.withdrawal_rate)
        c = v0 * rate_f / 12.0
        fee_annual = float(sample_ctx.expense_ratio or Decimal("0"))

        gf_key = _gf_cache_key(sample_ctx)
        growth_factors_full = self._gf_cache[gf_key]

        horizon_result_cache: dict[tuple[int, object], SimulationResult] = {}

        use_workbook = self._use_workbook_scr(sample_ctx)

        for horizon, h_contexts in horizon_to_ctxs.items():
            stats["month_work"] += horizon

            if use_workbook:
                # Workbook convention (SWR Toolbox ``Case Study``): the context
                # horizon includes the pre-retirement snapshot, so the number of
                # return / withdrawal periods is ``horizon - 1``.  Withdraw
                # before growth in every period and compound the final month's
                # return, exactly as the workbook SCR model.
                #
                # ``success`` is the SCR verdict (``scr >= rate``).  The
                # operational terminal failure -- the month the trajectory
                # reaches zero -- is taken from the trajectory itself and is
                # never inferred from ``scr < rate``; the reported month uses
                # the same convention as ``numba_executor._process_static_group``
                # (0-based period index + 1, since month 0 is pre-retirement).
                periods = horizon - 1
                growth_factors_arr = growth_factors_full[:periods]
                scr = _compute_workbook_scr(growth_factors_arr, periods, fee_annual)
                success = scr >= rate_f
                out_values = (
                    np.empty(periods + 1, dtype=np.float64)
                    if self._materialize_timeline
                    else None
                )
                final_value, _traj_success, fail_month, _ = _simulate_trajectory_workbook(
                    growth_factors_arr, v0, c, periods, out_values
                )
                failure_month = (
                    fail_month + 1 if 0 <= fail_month < periods else None
                )
                months_simulated = (
                    failure_month if failure_month is not None else horizon
                )
                captured = out_values
                workbook_convention = True
            else:
                growth_factors_arr = growth_factors_full[:horizon]
                out_values = (
                    np.empty(horizon, dtype=np.float64)
                    if self._materialize_timeline
                    else None
                )
                _final_val, _kernel_success, fail_month, _ = _simulate_trajectory(
                    growth_factors_arr, v0, c, horizon, out_values
                )

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
                captured = out_values
                workbook_convention = False

            timeline = None
            if captured is not None:
                c_decimal = Decimal(str(c))
                if workbook_convention:
                    amounts = [Decimal("0")] + [c_decimal] * (months_simulated - 1)
                else:
                    amounts = [c_decimal] * months_simulated
                timeline = build_simulation_timeline(
                    sample_ctx,
                    captured,
                    n_months=months_simulated,
                    withdrawal_reason=type(sample_ctx.withdrawal_policy).__name__,
                    withdrawal_amounts=amounts,
                )

            for ctx in h_contexts:
                cache_key = (horizon, ctx.final_value_target)
                if cache_key in horizon_result_cache:
                    results[id(ctx)] = horizon_result_cache[cache_key]
                    continue

                final_wealth = _money(final_value)

                base = SimulationResult(
                    timeline=timeline or SimulationTimeline(monthly_results=()),
                    statistics=SimulationStatistics(
                        final_wealth=final_wealth,
                        max_drawdown=0.0,
                        success=success,
                        failure_month=failure_month,
                        failure_state=None if failure_month is None else "depleted",
                        months_simulated=months_simulated,
                        execution_time_seconds=0.0,
                    ),
                )
                result = _apply_fv_check(base, ctx)
                horizon_result_cache[cache_key] = result
                results[id(ctx)] = result
                stats["derived_count"] += 1

    def _process_constant_nominal_group(
        self,
        contexts: list[SimulationContext],
        results: dict[int, SimulationResult],
        stats: dict[str, int],
    ) -> None:
        """Process a group of constant nominal withdrawal contexts."""
        horizon_to_ctxs: dict[int, list[SimulationContext]] = {}
        for ctx in contexts:
            horizon_to_ctxs.setdefault(ctx.horizon_months, []).append(ctx)

        sample_ctx = contexts[0]
        initial_snapshot = sample_ctx.dataset[0]
        v0 = float(sum(
            holding.units * initial_snapshot.index_levels[holding.asset_class]
            for holding in sample_ctx.initial_portfolio.holdings
        ))
        withdrawal_policy = cast(ConstantWithdrawalPolicy, sample_ctx.withdrawal_policy)
        rate_f = float(withdrawal_policy.withdrawal_rate)

        gf_key = _gf_cache_key(sample_ctx)
        growth_factors_full = self._gf_cache[gf_key]

        horizon_result_cache: dict[tuple[int, object], SimulationResult] = {}

        for horizon, h_contexts in horizon_to_ctxs.items():
            stats["month_work"] += horizon
            growth_factors_arr = growth_factors_full[:horizon]

            out_values = (
                np.empty(horizon, dtype=np.float64)
                if self._materialize_timeline
                else None
            )
            _final_val, _kernel_success, fail_month, _ = _simulate_trajectory_constant_nominal(
                growth_factors_arr, v0, rate_f, horizon, out_values
            )

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

            timeline = None
            if out_values is not None:
                rate_monthly = Decimal(str(rate_f)) / Decimal("12")
                factor = Decimal("1") - rate_monthly
                amounts = []
                for m in range(months_simulated):
                    post = Decimal(str(float(out_values[m])))
                    amount = (
                        post * rate_monthly / factor
                        if factor != Decimal("0")
                        else post
                    )
                    amounts.append(amount)
                timeline = build_simulation_timeline(
                    sample_ctx,
                    out_values,
                    n_months=months_simulated,
                    withdrawal_reason=type(sample_ctx.withdrawal_policy).__name__,
                    withdrawal_amounts=amounts,
                )

            for ctx in h_contexts:
                cache_key = (horizon, ctx.final_value_target)
                if cache_key in horizon_result_cache:
                    results[id(ctx)] = horizon_result_cache[cache_key]
                    continue

                final_wealth = _money(final_value)

                base = SimulationResult(
                    timeline=timeline or SimulationTimeline(monthly_results=()),
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
                stats["derived_count"] += 1

    def _process_escalating_group(
        self,
        contexts: list[SimulationContext],
        results: dict[int, SimulationResult],
        stats: dict[str, int],
    ) -> None:
        """Process a group of annually escalating withdrawal contexts."""
        horizon_to_ctxs: dict[int, list[SimulationContext]] = {}
        for ctx in contexts:
            horizon_to_ctxs.setdefault(ctx.horizon_months, []).append(ctx)

        sample_ctx = contexts[0]
        initial_snapshot = sample_ctx.dataset[0]
        v0 = float(sum(
            holding.units * initial_snapshot.index_levels[holding.asset_class]
            for holding in sample_ctx.initial_portfolio.holdings
        ))
        withdrawal_policy = cast(EscalatingWithdrawalPolicy, sample_ctx.withdrawal_policy)
        rate_f = float(withdrawal_policy.withdrawal_rate)
        escalation_f = float(withdrawal_policy.escalation_rate)
        annual = withdrawal_policy.frequency is WithdrawalFrequency.ANNUAL

        gf_key = _gf_cache_key(sample_ctx)
        growth_factors_full = self._gf_cache[gf_key]

        # The FV verdict depends on ``initial_wealth * final_value_target``
        # (see ``_apply_fv_check``), so both per-context evaluation dimensions
        # are part of the cache key; sharing a verdict across contexts that
        # differ in either would be incorrect.
        horizon_result_cache: dict[tuple[int, object, object], SimulationResult] = {}

        for horizon, h_contexts in horizon_to_ctxs.items():
            stats["month_work"] += horizon
            growth_factors_arr = growth_factors_full[:horizon]

            out_values = (
                np.empty(horizon, dtype=np.float64)
                if self._materialize_timeline
                else None
            )
            _final_val, _kernel_success, fail_month, _ = _simulate_trajectory_escalating(
                growth_factors_arr, v0, rate_f, escalation_f, horizon, annual, out_values
            )

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

            timeline = None
            if out_values is not None:
                amounts = []
                for m in range(months_simulated):
                    escalated = (
                        Decimal(str(v0))
                        * Decimal(str(rate_f))
                        * (Decimal("1") + Decimal(str(escalation_f)))
                        ** (m // 12)
                    )
                    amounts.append(escalated if annual else escalated / Decimal("12"))
                timeline = build_simulation_timeline(
                    sample_ctx,
                    out_values,
                    n_months=months_simulated,
                    withdrawal_reason=type(sample_ctx.withdrawal_policy).__name__,
                    withdrawal_amounts=amounts,
                )

            for ctx in h_contexts:
                cache_key = (horizon, ctx.initial_wealth, ctx.final_value_target)
                if cache_key in horizon_result_cache:
                    results[id(ctx)] = horizon_result_cache[cache_key]
                    continue

                final_wealth = _money(final_value)

                base = SimulationResult(
                    timeline=timeline or SimulationTimeline(monthly_results=()),
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
                stats["derived_count"] += 1

    def _process_glidepath_escalating_group(
        self,
        contexts: list[SimulationContext],
        results: dict[int, SimulationResult],
        stats: dict[str, int],
    ) -> None:
        """Process glidepath allocation with escalating withdrawals.

        The withdrawal schedule follows the documented escalating contract
        (withdrawal before growth, no growth after the final withdrawal).  The
        glidepath target weight advances according to its configured cadence
        and is rebalanced to monthly before each growth period.
        """
        horizon_to_ctxs: dict[int, list[SimulationContext]] = {}
        for ctx in contexts:
            horizon_to_ctxs.setdefault(ctx.horizon_months, []).append(ctx)

        sample_ctx = contexts[0]
        initial_snapshot = sample_ctx.dataset[0]
        v0 = float(
            sum(
                holding.units * initial_snapshot.index_levels[holding.asset_class]
                for holding in sample_ctx.initial_portfolio.holdings
            )
        )
        allocation = cast(GlidepathAllocationPolicy, sample_ctx.allocation_policy)
        withdrawal_policy = cast(
            EscalatingWithdrawalPolicy, sample_ctx.withdrawal_policy
        )
        rate_f = float(withdrawal_policy.withdrawal_rate)
        escalation_f = float(withdrawal_policy.escalation_rate)
        annual = withdrawal_policy.frequency is WithdrawalFrequency.ANNUAL

        gf_key = _glidepath_gf_cache_key(sample_ctx)
        growth_factors_full = self._glidepath_gf_cache[gf_key]

        horizon_result_cache: dict[tuple[int, object, object], SimulationResult] = {}

        for horizon, h_contexts in horizon_to_ctxs.items():
            stats["month_work"] += horizon
            growth_factors_arr = growth_factors_full[:horizon]

            out_values = (
                np.empty(horizon, dtype=np.float64)
                if self._materialize_timeline
                else None
            )
            _final_val, _kernel_success, fail_month, _ = (
                _simulate_trajectory_escalating(
                    growth_factors_arr,
                    v0,
                    rate_f,
                    escalation_f,
                    horizon,
                    annual,
                    out_values,
                )
            )

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

            timeline = None
            if out_values is not None:
                amounts = []
                for m in range(months_simulated):
                    escalated = (
                        Decimal(str(v0))
                        * Decimal(str(rate_f))
                        * (Decimal("1") + Decimal(str(escalation_f)))
                        ** (m // 12)
                    )
                    amounts.append(escalated if annual else escalated / Decimal("12"))
                is_underwater = _extract_is_underwater(
                    sample_ctx.dataset, horizon
                )
                equity_weights = _compute_equity_weight_sequence(
                    allocation, is_underwater, horizon
                )
                timeline = build_simulation_timeline(
                    sample_ctx,
                    out_values,
                    n_months=months_simulated,
                    withdrawal_reason=type(sample_ctx.withdrawal_policy).__name__,
                    withdrawal_amounts=amounts,
                    target_equity_weights=equity_weights[:months_simulated],
                )

            for ctx in h_contexts:
                cache_key = (horizon, ctx.initial_wealth, ctx.final_value_target)
                if cache_key in horizon_result_cache:
                    results[id(ctx)] = horizon_result_cache[cache_key]
                    continue

                final_wealth = _money(final_value)

                base = SimulationResult(
                    timeline=timeline or SimulationTimeline(monthly_results=()),
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
                stats["derived_count"] += 1

    def _process_buy_and_hold_group(
        self,
        contexts: list[SimulationContext],
        results: dict[int, SimulationResult],
        stats: dict[str, int],
    ) -> None:
        """Process a group of buy-and-hold (BuyAndHoldAllocationPolicy) contexts.

        Buy-and-hold weights drift endogenously with asset-specific returns, so
        the kernel consumes the per-asset monthly growth factors rather than a
        precomputed blended series.
        """
        horizon_to_ctxs: dict[int, list[SimulationContext]] = {}
        for ctx in contexts:
            horizon_to_ctxs.setdefault(ctx.horizon_months, []).append(ctx)

        sample_ctx = contexts[0]
        initial_snapshot = sample_ctx.dataset[0]
        v0 = float(sum(
            holding.units * initial_snapshot.index_levels[holding.asset_class]
            for holding in sample_ctx.initial_portfolio.holdings
        ))
        allocation = cast(BuyAndHoldAllocationPolicy, sample_ctx.allocation_policy)
        equity_weight = float(allocation.equity_allocation)
        withdrawal_policy = cast(FixedRealWithdrawalPolicy, sample_ctx.withdrawal_policy)
        rate_f = float(withdrawal_policy.withdrawal_rate)
        c = float(sample_ctx.initial_wealth.amount) * rate_f / 12.0
        fee_annual = float(sample_ctx.expense_ratio or Decimal("0"))

        equity_growth_full, bond_growth_full = self._buy_and_hold_growth_factors(sample_ctx)

        # The FV verdict depends on ``initial_wealth * final_value_target``
        # (see ``_apply_fv_check``), so both per-context evaluation dimensions
        # are part of the cache key.
        horizon_result_cache: dict[tuple[int, object, object], SimulationResult] = {}

        for horizon, h_contexts in horizon_to_ctxs.items():
            stats["month_work"] += horizon
            equity_growth = equity_growth_full[:horizon]
            bond_growth = bond_growth_full[:horizon]

            out_values = (
                np.empty(horizon, dtype=np.float64)
                if self._materialize_timeline
                else None
            )
            out_weights = (
                np.empty(horizon, dtype=np.float64)
                if self._materialize_timeline
                else None
            )
            _final_val, _kernel_success, fail_month, _ = _simulate_trajectory_buy_and_hold(
                equity_growth,
                bond_growth,
                v0,
                equity_weight,
                c,
                horizon,
                fee_annual,
                out_values,
                out_weights,
            )

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

            timeline = None
            if out_values is not None:
                timeline = build_simulation_timeline(
                    sample_ctx,
                    out_values,
                    n_months=months_simulated,
                    withdrawal_reason=type(sample_ctx.withdrawal_policy).__name__,
                    withdrawal_amounts=[Decimal(str(c))] * months_simulated,
                    actual_equity_weights=out_weights,
                )

            for ctx in h_contexts:
                cache_key = (horizon, ctx.initial_wealth, ctx.final_value_target)
                if cache_key in horizon_result_cache:
                    results[id(ctx)] = horizon_result_cache[cache_key]
                    continue

                final_wealth = _money(final_value)

                base = SimulationResult(
                    timeline=timeline or SimulationTimeline(monthly_results=()),
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
                stats["derived_count"] += 1

    def _buy_and_hold_growth_factors(
        self, context: SimulationContext
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """Return (equity_growth, bond_growth) monthly factors for *context*.

        The factors are ``P_{m+1} / P_m`` per asset and depend only on the
        dataset trajectory, so they are cached by dataset-identity token and
        shared across allocations, withdrawal rates, and horizons.
        """
        dataset_key = _dataset_token(context)
        cached = self._bh_growth_cache.get(dataset_key)
        if cached is not None:
            return cached

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
            i for i, ac in enumerate(asset_classes) if cast(AssetClass, ac).id == "equity"
        )
        bond_row = next(
            i for i, ac in enumerate(asset_classes) if cast(AssetClass, ac).id == "bond"
        )
        equity_prices = prices_f[equity_row]
        bond_prices = prices_f[bond_row]
        growth = (
            equity_prices[1:] / equity_prices[:-1],
            bond_prices[1:] / bond_prices[:-1],
        )
        self._bh_growth_cache[dataset_key] = growth
        return growth

    def _process_glidepath_group(
        self,
        contexts: list[SimulationContext],
        results: dict[int, SimulationResult],
        stats: dict[str, int],
    ) -> None:
        """Process a group of glidepath (GlidepathAllocationPolicy) contexts."""
        horizon_to_ctxs: dict[int, list[SimulationContext]] = {}
        for ctx in contexts:
            horizon_to_ctxs.setdefault(ctx.horizon_months, []).append(ctx)

        sample_ctx = contexts[0]
        initial_snapshot = sample_ctx.dataset[0]
        v0 = float(sum(
            holding.units * initial_snapshot.index_levels[holding.asset_class]
            for holding in sample_ctx.initial_portfolio.holdings
        ))
        withdrawal_policy = cast(FixedRealWithdrawalPolicy, sample_ctx.withdrawal_policy)
        rate_f = float(withdrawal_policy.withdrawal_rate)
        c = float(sample_ctx.initial_wealth.amount) * rate_f / 12.0

        gf_key = _glidepath_gf_cache_key(sample_ctx)
        growth_factors_full = self._glidepath_gf_cache[gf_key]

        horizon_result_cache: dict[tuple[int, object], SimulationResult] = {}

        for horizon, h_contexts in horizon_to_ctxs.items():
            stats["month_work"] += horizon

            # Workbook convention (SWR Toolbox ``Case Study``): the context
            # horizon includes the pre-retirement snapshot, so the number of
            # withdrawal / return periods is ``horizon - 1``.  Withdraw before
            # growth in every period and compound the final period's return.
            # The glidepath weight sequence is the simulator extension: the
            # workbook's own glidepath is a fixed 120-month linear transition,
            # whereas ERN uses an active/passive slope relative to the
            # beginning-of-period underwater state.
            periods = horizon - 1
            growth_factors_arr = growth_factors_full[:periods]

            out_values = (
                np.empty(periods + 1, dtype=np.float64)
                if self._materialize_timeline
                else None
            )
            final_value, traj_success, fail_month, _ = _simulate_trajectory_workbook(
                growth_factors_arr, v0, c, periods, out_values
            )

            success = traj_success
            failure_month = fail_month + 1 if 0 <= fail_month < periods else None
            if failure_month is not None:
                final_value = 0.0
                months_simulated = failure_month
            else:
                months_simulated = horizon

            timeline = None
            if out_values is not None:
                policy = cast(
                    GlidepathAllocationPolicy, sample_ctx.allocation_policy
                )
                # Month 0 is the pre-retirement base row (no withdrawal).  The
                # weight applied to the return from month j-1 to month j is the
                # sequence entry j-1, so the timeline shows the initial weight
                # at month 0 and shifts the sequence by one month thereafter.
                weight_months = max(periods, 1)
                is_underwater = _extract_is_underwater(
                    sample_ctx.dataset, weight_months
                )
                equity_weights = _compute_equity_weight_sequence(
                    policy, is_underwater, weight_months
                )
                timeline_weights = (
                    [equity_weights[0]] + list(equity_weights[: months_simulated - 1])
                    if months_simulated > 0
                    else []
                )
                timeline = build_simulation_timeline(
                    sample_ctx,
                    out_values,
                    n_months=months_simulated,
                    withdrawal_reason=type(sample_ctx.withdrawal_policy).__name__,
                    withdrawal_amounts=[Decimal("0")]
                    + [Decimal(str(c))] * (months_simulated - 1),
                    target_equity_weights=timeline_weights,
                )

            for ctx in h_contexts:
                cache_key = (horizon, ctx.final_value_target)
                if cache_key in horizon_result_cache:
                    results[id(ctx)] = horizon_result_cache[cache_key]
                    continue

                final_wealth = _money(final_value)

                base = SimulationResult(
                    timeline=timeline or SimulationTimeline(monthly_results=()),
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
                stats["derived_count"] += 1


def _money(value: float) -> Money:
    """Convert a float to a Money object."""
    return Money(Decimal(str(value)), Currency.EUR)


def _apply_fv_check(result: SimulationResult, context: SimulationContext) -> SimulationResult:
    """Return a copy of *result* with the FV check applied for *context*'s target.

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
