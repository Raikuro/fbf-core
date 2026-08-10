"""Execution-grade policy implementations for CLI commands.

These subclass the frozen domain abstract policies (AllocationPolicy,
WithdrawalPolicy) and implement working decide() methods suitable for
real simulation execution.
"""

from decimal import Decimal

from engine.application.simulation_context import SimulationContext
from engine.domain.model.allocation import AllocationTarget
from engine.domain.model.asset import AssetClass
from engine.domain.model.decision_context import DecisionContext
from engine.domain.model.money import Currency, Money
from engine.domain.policies.allocation_policy import AllocationPolicy
from engine.domain.policies.decisions import AllocationDecision, WithdrawalDecision
from engine.domain.policies.withdrawal_policy import WithdrawalPolicy


class ConstantAllocationPolicy(AllocationPolicy):
    """Fixed equity/bond split allocation policy.

    YAML type: "ConstantAllocationPolicy"
    YAML params: equity_ratio (Decimal, 0.0-1.0)

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

    YAML type: "ConstantInflationAdjustedWithdrawalPolicy"
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
        sim_context = context.simulation_context
        if not isinstance(sim_context, SimulationContext):
            raise TypeError(
                "FixedRealWithdrawalPolicy requires a SimulationContext"
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
