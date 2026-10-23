"""Shared eligibility and trajectory-grouping helpers for Numba executors.

These helpers define which simulation contexts the optimized kernels can
execute and how contexts are grouped for cross-horizon trajectory derivation.
They are independent of any execution strategy: context eligibility is limited
to the policy families whose semantics the Numba kernels encode, and trajectory
derivation is only valid across dataset object-identity prefixes.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import cast

from fbf.core.domain.policies import (
    ConstantAllocationPolicy,
    FixedRealWithdrawalPolicy,
    allocation_identity,
    resolve_target_weights,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext

_EquityId = "equity"


def is_constant_allocation_eligible(context: SimulationContext) -> bool:
    """Return True when *context* can be evaluated by a constant-allocation kernel.

    Eligibility is restricted to the exact policy classes whose semantics the
    recurrence encodes.  Any other policy pair (or a horizon below one month)
    is rejected.  The dataset must also cover the full horizon: the recurrence
    reads monthly index levels up to ``horizon_months - 1``, so a dataset
    shorter than the horizon is refused.
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
    asset_classes = tuple(holding.asset_class for holding in holdings)
    if any(
        asset_class not in context.dataset[0].index_levels
        for asset_class in asset_classes
    ):
        return False
    # The scalar form encodes the two-asset (equity + one bond) rebalanced
    # model: equity at weight ``w`` and every other held class at ``1 - w``.
    # Any other holding set (single-asset, duplicate equity, or three or more
    # classes) would make the per-class weights ambiguous, so it is rejected.
    # The explicit form is accepted whenever its mapping exactly covers the
    # held asset classes.
    if context.allocation_policy.allocations is None:
        if len(holdings) != 2:
            return False
        return sum(1 for h in holdings if h.asset_class.id == _EquityId) == 1
    try:
        resolve_target_weights(context.allocation_policy, asset_classes)
    except (ValueError, TypeError):
        return False
    return True


def _weights_by_class(
    context: SimulationContext,
) -> dict[object, Decimal]:
    """Map each held asset class to its constant target weight.

    Weights are resolved by :func:`~fbf.core.domain.policies.resolve_target_weights`,
    the single authority for allocation semantics and asset ordering. The
    scalar form assigns equity ``w`` and every other class ``1 - w``; the
    explicit form uses the policy's complete mapping.
    """
    allocation = cast(ConstantAllocationPolicy, context.allocation_policy)
    asset_classes = tuple(h.asset_class for h in context.initial_portfolio.holdings)
    weights = resolve_target_weights(allocation, asset_classes)
    return dict(zip(asset_classes, weights, strict=True))


def _index_series(context: SimulationContext) -> dict[object, tuple[Decimal, ...]]:
    """Return per-asset-class monthly index levels across the dataset."""
    snapshots = context.dataset.snapshots
    return {
        holding.asset_class: tuple(
            snapshot.index_levels[holding.asset_class] for snapshot in snapshots
        )
        for holding in context.initial_portfolio.holdings
    }


def _dataset_is_identity_prefix(
    candidate: SimulationContext, longest: SimulationContext
) -> bool:
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
    return all(
        a is b
        for a, b in zip(candidate_snapshots, longest_snapshots, strict=False)
    )


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


def _dataset_token(context: SimulationContext) -> int:
    """Return an O(1) object-identity token for *context*'s exact dataset.

    Two contexts share a token iff they reference the very same ``Dataset``
    object.  Because ``Dataset.slice`` creates a new object per ``(start_date,
    horizon)`` slice, the token distinguishes different trajectories *and*
    different horizons.

    It is safe for cache keys only while the referenced dataset stays alive.
    Executors that key caches on it retain a strong reference to every dataset
    they have seen for their own lifetime, so a token is never reused by a
    different dataset and cached entries remain valid across ``execute`` calls.
    """
    return id(context.dataset)


def _trajectory_clusters(
    contexts: list[SimulationContext],
    memo: dict[tuple[int, int], bool],
    compatible: Callable[[SimulationContext, SimulationContext], bool] | None = None,
) -> list[list[SimulationContext]]:
    """Partition *contexts* into identity-prefix trajectory clusters.

    Each returned cluster's first element is its longest-horizon representative,
    and every other member's dataset is an object-identity prefix of the
    representative's dataset (see :func:`_dataset_is_identity_prefix`).  Contexts
    built from different data therefore never share a cluster, so deriving a
    shorter member's trajectory from the representative is always valid.  Failing
    to cluster is always safe: a lone context is evaluated independently.

    ``compatible`` is an optional, symmetric predicate that a candidate and a
    cluster representative must additionally satisfy to share a cluster.  It is
    used by executors whose derived quantity depends on more than the market
    trajectory (e.g. a debt interest-rate schedule), so that two contexts are
    only clustered when every quantity derived from the representative is valid
    for the candidate.  It is consulted only after the identity-prefix guard
    succeeds, so it may assume the datasets are identity-prefixed.
    """
    clusters: list[list[SimulationContext]] = []
    for context in contexts:
        for cluster in clusters:
            representative = cluster[0]
            if not (
                _dataset_is_identity_prefix_memo(context, representative, memo)
                or _dataset_is_identity_prefix_memo(representative, context, memo)
            ):
                continue
            if compatible is not None and not compatible(context, representative):
                continue
            if context.horizon_months > representative.horizon_months:
                cluster.insert(0, context)
            else:
                cluster.append(context)
            break
        else:
            clusters.append([context])
    return clusters


def _group_key(context: SimulationContext) -> tuple[object, ...]:
    """Trajectory key for constant-allocation, fixed-real contexts.

    ``final_value_target`` is excluded because it is an evaluation dimension:
    contexts that differ only in the target share one trajectory path.
    """
    allocation = cast(ConstantAllocationPolicy, context.allocation_policy)
    withdrawal = cast(FixedRealWithdrawalPolicy, context.withdrawal_policy)
    asset_classes = tuple(h.asset_class for h in context.initial_portfolio.holdings)
    return (
        context.start_date,
        allocation_identity(allocation, asset_classes),
        withdrawal.withdrawal_rate,
        context.initial_wealth,
        context.initial_portfolio,
    )
