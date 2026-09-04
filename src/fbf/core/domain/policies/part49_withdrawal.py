"""Part 49 leverage-aware withdrawal policy.

Implements the ERN Part 49 (Using Leverage in Retirement) withdrawal semantics:
total_spending = portfolio_withdrawal + loan_draw.  Both are fixed fractions of
initial_wealth, computed once at cohort start.

The ``loan_draw_rate`` is read from ``SimulationContext.loan_draw_rate``.  When
``loan_draw_rate`` is ``None`` or zero, the policy behaves identically to
``FixedRealWithdrawalPolicy`` (no leverage).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fbf.core.domain.model.decision_context import DecisionContext
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies.decisions import WithdrawalDecision
from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy


class Part49WithdrawalPolicy(WithdrawalPolicy):
    """Withdrawal policy for Part 49 leverage studies.

    Computes both the portfolio withdrawal and the loan draw as fixed
    fractions of initial wealth.  The loan draw rate is read from the
    simulation context (set via ``SimulationContext.loan_draw_rate``).

    Parameters
    ----------
    withdrawal_rate:
        Annual portfolio withdrawal rate (e.g. ``Decimal("0.04")`` for 4%).
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
                "Part49WithdrawalPolicy requires a DecisionContext with simulation_context"
            )

        initial_snapshot = sim_context.dataset[0]
        total = Money.ZERO
        for holding in sim_context.initial_portfolio.holdings:
            price = initial_snapshot.index_levels[holding.asset_class]
            total += Money(holding.units * price, Currency.EUR)

        monthly_withdrawal = total.amount * self.withdrawal_rate / Decimal("12")

        loan_draw_rate: Decimal = getattr(sim_context, "loan_draw_rate", None) or Decimal("0")
        monthly_loan = total.amount * loan_draw_rate / Decimal("12")

        return WithdrawalDecision(
            reason="Part49WithdrawalPolicy",
            nominal_amount=Money(monthly_withdrawal, Currency.EUR),
            real_amount=Money(monthly_withdrawal, Currency.EUR),
            loan_draw_amount=monthly_loan,
        )
