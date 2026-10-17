"""Execution-grade policy implementations for simulation execution.

These subclass the frozen domain abstract policies (AllocationPolicy,
WithdrawalPolicy) and implement working decide() methods suitable for
real simulation execution.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from fbf.core.domain.model.allocation import AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.decision_context import DecisionContext
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies.allocation_policy import AllocationPolicy
from fbf.core.domain.policies.decisions import AllocationDecision, WithdrawalDecision
from fbf.core.domain.policies.frequency import WithdrawalFrequency
from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy

_EQUITY_ID = "equity"


class ConstantAllocationPolicy(AllocationPolicy):
    """Constant target allocation policy with periodic rebalancing.

    Two mutually exclusive forms are supported:

    * **Legacy (two-asset):** ``equity_allocation`` is a scalar ``Decimal`` in
      ``[0, 1]``; the remaining weight is assigned to the single other held
      asset class. Behavior is unchanged from the original policy.
    * **Explicit (N ≥ 2):** ``allocations`` maps every held asset-class id to
      its target weight. The mapping is authoritative — weights are never
      inferred or residual-distributed — and must be complete, non-negative,
      and sum to exactly ``1``.

    Supplying neither form, or both, is rejected. For the explicit form
    ``equity_allocation`` is ``None`` so that no legacy reader can silently
    consume a partial value; use :func:`resolve_target_weights` instead.

    YAML type: "ConstantAllocationPolicy"
    YAML params: ``equity_allocation`` (legacy) or ``allocations`` (explicit).
    """

    def __init__(
        self,
        equity_allocation: Decimal | None = None,
        *,
        allocations: Mapping[str, Decimal] | None = None,
    ) -> None:
        if equity_allocation is None and allocations is None:
            raise ValueError(
                "ConstantAllocationPolicy requires either equity_allocation or "
                "allocations"
            )
        if equity_allocation is not None and allocations is not None:
            raise ValueError(
                "ConstantAllocationPolicy accepts equity_allocation or allocations, "
                "not both"
            )
        if allocations is not None:
            self.allocations: tuple[tuple[str, Decimal], ...] | None = (
                _validate_explicit_allocations(allocations)
            )
            self.equity_allocation: Decimal | None = None
        else:
            self.allocations = None
            self.equity_allocation = equity_allocation

    def decide(self, context: DecisionContext) -> AllocationDecision:
        if self.allocations is None:
            equity = AssetClass(id=_EQUITY_ID, name="", description="")
            bond = AssetClass(id="bond", name="", description="")
            assert self.equity_allocation is not None
            return AllocationDecision(
                reason="ConstantAllocationPolicy",
                allocation_target=AllocationTarget(weights={
                    equity: self.equity_allocation,
                    bond: Decimal("1") - self.equity_allocation,
                }),
            )

        held_by_id = {
            holding.asset_class.id: holding.asset_class
            for holding in context.portfolio.holdings
        }
        target: dict[AssetClass, Decimal] = {}
        for asset_id, weight in self.allocations:
            asset_class = held_by_id.get(asset_id)
            if asset_class is None:
                raise ValueError(
                    f"ConstantAllocationPolicy allocations reference unknown asset "
                    f"class {asset_id!r}"
                )
            target[asset_class] = weight
        if len(target) != len(held_by_id):
            missing = sorted(set(held_by_id) - {k for k, _ in self.allocations})
            raise ValueError(
                "ConstantAllocationPolicy allocations must cover every held asset "
                f"class; missing {missing}"
            )
        return AllocationDecision(
            reason="ConstantAllocationPolicy",
            allocation_target=AllocationTarget(weights=target),
        )


def _validate_explicit_allocations(
    allocations: Mapping[str, Decimal],
) -> tuple[tuple[str, Decimal], ...]:
    """Validate and canonicalize an explicit asset-class weight mapping."""
    if not isinstance(allocations, Mapping):
        raise TypeError("allocations must be a mapping of asset-class id to Decimal")
    if len(allocations) < 2:
        raise ValueError("allocations must define at least two asset classes")
    items: list[tuple[str, Decimal]] = []
    for asset_id, weight in allocations.items():
        if not isinstance(asset_id, str) or not asset_id:
            raise ValueError("allocations keys must be non-empty asset-class id strings")
        if not isinstance(weight, Decimal):
            raise TypeError(f"allocations[{asset_id!r}] must be a Decimal")
        if weight < 0 or weight > 1:
            raise ValueError(f"allocations[{asset_id!r}] must be within [0, 1]")
        items.append((asset_id, weight))
    total = sum((weight for _, weight in items), Decimal("0"))
    if total != Decimal("1"):
        raise ValueError("allocations weights must sum to exactly 1")
    items.sort(key=lambda item: item[0])
    return tuple(items)


def resolve_target_weights(
    policy: ConstantAllocationPolicy,
    asset_classes: Sequence[AssetClass],
) -> tuple[Decimal, ...]:
    """Return target weights aligned with *asset_classes* (engine series order).

    This is the single validator/ordering authority for allocation weights.
    For the explicit form it requires exact asset-class coverage (no missing or
    extra ids, no duplicate held ids). For the legacy form it mirrors the
    historical ``equity→w`` / every-other-class→``1-w`` split.
    """
    if not isinstance(policy, ConstantAllocationPolicy):
        raise TypeError("resolve_target_weights requires a ConstantAllocationPolicy")
    classes = list(asset_classes)
    if policy.allocations is not None:
        return _resolve_explicit_weights(policy.allocations, classes)
    equity_weight = policy.equity_allocation
    if equity_weight is None:
        raise ValueError("legacy ConstantAllocationPolicy has no equity_allocation")
    return tuple(
        equity_weight if asset_class.id == _EQUITY_ID else Decimal("1") - equity_weight
        for asset_class in classes
    )


def _resolve_explicit_weights(
    allocations: tuple[tuple[str, Decimal], ...],
    asset_classes: Sequence[AssetClass],
) -> tuple[Decimal, ...]:
    ids = [asset_class.id for asset_class in asset_classes]
    if len(ids) != len(set(ids)):
        raise ValueError("asset classes contain duplicate ids")
    expected = {asset_id for asset_id, _ in allocations}
    if set(ids) != expected:
        missing = sorted(expected - set(ids))
        extra = sorted(set(ids) - expected)
        raise ValueError(
            "explicit allocations must exactly cover the held asset classes "
            f"(missing={missing}, unexpected={extra})"
        )
    weight_by_id = dict(allocations)
    return tuple(weight_by_id[asset_id] for asset_id in ids)


def allocation_identity(
    policy: ConstantAllocationPolicy,
    asset_classes: Sequence[AssetClass],
) -> tuple[tuple[str, Decimal], ...]:
    """Return an order-insensitive canonical identity for cache/group keys.

    Combines each held asset-class id with its resolved weight, sorted by id, so
    that reordered-but-equal allocations share an identity while distinct
    allocations never collide.
    """
    weights = resolve_target_weights(policy, asset_classes)
    return tuple(
        sorted(
            (asset_class.id, weight)
            for asset_class, weight in zip(asset_classes, weights, strict=True)
        )
    )


class BuyAndHoldAllocationPolicy(AllocationPolicy):
    """Buy-and-hold allocation policy.

    YAML type: "BuyAndHoldAllocationPolicy"
    YAML params: equity_allocation (Decimal, 0.0-1.0)

    The initial equity/bond allocation is established once at simulation start.
    There is no periodic portfolio rebalancing. Subsequent market movements
    naturally change portfolio weights. Withdrawals may sell assets to obtain
    cash, but this does not trigger rebalancing.

    This policy returns the same initial allocation target on every call.
    The buy-and-hold behavior is enforced by applying the allocation target
    once in period 0: ``create_buy_and_hold_pipeline`` includes
    AllocationDecisionStep and PortfolioRebalanceStep restricted to the first
    period, after which the weights drift with market movements.
    """

    def __init__(self, equity_allocation: Decimal) -> None:
        self.equity_allocation = equity_allocation
        self._initial_target: AllocationTarget | None = None

    def decide(self, context: DecisionContext) -> AllocationDecision:
        if self._initial_target is None:
            equity = AssetClass(id="equity", name="", description="")
            bond = AssetClass(id="bond", name="", description="")
            self._initial_target = AllocationTarget(weights={
                equity: self.equity_allocation,
                bond: Decimal("1") - self.equity_allocation,
            })
        return AllocationDecision(
            reason="BuyAndHoldAllocationPolicy",
            allocation_target=self._initial_target,
        )


class ConstantWithdrawalPolicy(WithdrawalPolicy):
    """Fixed-rate withdrawal policy.

    YAML type: "ConstantWithdrawalPolicy"
    YAML params: withdrawal_rate (Decimal, 0.0-1.0 annual)

    Withdrawal = portfolio_value * withdrawal_rate / 12 (monthly).
    Real amount uses the same value (inflation adjustment deferred).
    """

    def __init__(
        self,
        withdrawal_rate: Decimal,
        *,
        frequency: WithdrawalFrequency = WithdrawalFrequency.MONTHLY,
    ) -> None:
        super().__init__(frequency=frequency)
        self.withdrawal_rate = withdrawal_rate

    def _decide_active(self, context: DecisionContext) -> WithdrawalDecision:
        portfolio_value = Decimal("0")
        for holding in context.portfolio.holdings:
            price = context.market_snapshot.index_levels.get(holding.asset_class)
            if price is not None:
                portfolio_value += holding.units * price
        if self.frequency is WithdrawalFrequency.ANNUAL:
            amount = portfolio_value * self.withdrawal_rate
        else:
            amount = portfolio_value * self.withdrawal_rate / Decimal("12")
        return WithdrawalDecision(
            reason="ConstantWithdrawalPolicy",
            nominal_amount=Money(amount, Currency.EUR),
            real_amount=Money(amount, Currency.EUR),
        )


class FixedRealWithdrawalPolicy(WithdrawalPolicy):
    """Fixed-real withdrawal policy.

    YAML type: "FixedRealWithdrawalPolicy"
    YAML params: withdrawal_rate (Decimal, 0.0-1.0 annual)

    The monthly withdrawal is computed once at the cohort start as
    ``initial_wealth * withdrawal_rate / 12``, where ``initial_wealth``
    is the experiment's fixed initial wealth (independent of cohort start
    date or current market prices).  The amount stays constant in real
    (index-level) units for the entire horizon.
    """

    def __init__(
        self,
        withdrawal_rate: Decimal,
        *,
        frequency: WithdrawalFrequency = WithdrawalFrequency.MONTHLY,
    ) -> None:
        super().__init__(frequency=frequency)
        self.withdrawal_rate = withdrawal_rate

    def _decide_active(self, context: DecisionContext) -> WithdrawalDecision:
        sim_context: Any = getattr(context, "simulation_context", None)
        if sim_context is None or not hasattr(sim_context, "initial_wealth"):
            raise TypeError(
                "FixedRealWithdrawalPolicy requires a DecisionContext with simulation_context"
            )
        initial_wealth: Money = sim_context.initial_wealth
        if self.frequency is WithdrawalFrequency.ANNUAL:
            amount = initial_wealth.amount * self.withdrawal_rate
        else:
            amount = initial_wealth.amount * self.withdrawal_rate / Decimal("12")
        return WithdrawalDecision(
            reason="FixedRealWithdrawalPolicy",
            nominal_amount=Money(amount, Currency.EUR),
            real_amount=Money(amount, Currency.EUR),
        )
