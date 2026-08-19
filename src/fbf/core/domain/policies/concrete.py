"""Execution-grade policy implementations for simulation execution.

These subclass the frozen domain abstract policies (AllocationPolicy,
WithdrawalPolicy) and implement working decide() methods suitable for
real simulation execution.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fbf.core.domain.model.allocation import AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.decision_context import DecisionContext
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies.allocation_policy import AllocationPolicy
from fbf.core.domain.policies.decisions import AllocationDecision, WithdrawalDecision
from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy


class ConstantAllocationPolicy(AllocationPolicy):
    """Fixed equity/bond split allocation policy.

    YAML type: "ConstantAllocationPolicy"
    YAML params: equity_allocation (Decimal, 0.0-1.0)

    The attribute name ``equity_allocation`` matches the key expected by
    ``AllocationPolicyCodec.dump()`` (see ``codecs.py`` line 103), enabling
    lossless round-trip persistence through the existing codec.
    """

    def __init__(self, equity_allocation: Decimal) -> None:
        self.equity_allocation = equity_allocation

    def decide(self, context: DecisionContext) -> AllocationDecision:
        equity = AssetClass(id="equity", name="", description="")
        bond = AssetClass(id="bond", name="", description="")
        return AllocationDecision(
            reason="ConstantAllocationPolicy",
            allocation_target=AllocationTarget(weights={
                equity: self.equity_allocation,
                bond: Decimal("1") - self.equity_allocation,
            }),
        )


class ConstantWithdrawalPolicy(WithdrawalPolicy):
    """Fixed-rate withdrawal policy.

    YAML type: "ConstantWithdrawalPolicy"
    YAML params: withdrawal_rate (Decimal, 0.0-1.0 annual)

    Withdrawal = portfolio_value * withdrawal_rate / 12 (monthly).
    Real amount uses the same value (inflation adjustment deferred).
    """

    def __init__(self, withdrawal_rate: Decimal) -> None:
        self.withdrawal_rate = withdrawal_rate

    def decide(self, context: DecisionContext) -> WithdrawalDecision:
        total = sum(h.units for h in context.portfolio.holdings)
        monthly = total * self.withdrawal_rate / Decimal("12")
        return WithdrawalDecision(
            reason="ConstantWithdrawalPolicy",
            nominal_amount=Money(monthly, Currency.EUR),
            real_amount=Money(monthly, Currency.EUR),
        )


class FixedRealWithdrawalPolicy(WithdrawalPolicy):
    """Fixed-real withdrawal policy.

    YAML type: "FixedRealWithdrawalPolicy"
    YAML params: withdrawal_rate (Decimal, 0.0-1.0 annual)

    The monthly withdrawal is computed once at the cohort start as
    ``initial_portfolio_value * withdrawal_rate / 12``, where
    ``initial_portfolio_value`` prices the initial portfolio holdings at the
    cohort's first dataset snapshot.  The amount stays constant in real
    (index-level) units for the entire horizon.
    """

    def __init__(self, withdrawal_rate: Decimal) -> None:
        self.withdrawal_rate = withdrawal_rate

    def decide(self, context: DecisionContext) -> WithdrawalDecision:
        sim_context: Any = getattr(context, "simulation_context", None)
        if (
            sim_context is None
            or not hasattr(sim_context, "dataset")
            or not hasattr(sim_context, "initial_portfolio")
        ):
            raise TypeError(
                "FixedRealWithdrawalPolicy requires a DecisionContext with simulation_context"
            )
        initial_snapshot = sim_context.dataset[0]
        total = Money.ZERO
        for holding in sim_context.initial_portfolio.holdings:
            price = initial_snapshot.index_levels[holding.asset_class]
            total += Money(holding.units * price, Currency.EUR)
        monthly = total.amount * self.withdrawal_rate / Decimal("12")
        return WithdrawalDecision(
            reason="FixedRealWithdrawalPolicy",
            nominal_amount=Money(monthly, Currency.EUR),
            real_amount=Money(monthly, Currency.EUR),
        )
