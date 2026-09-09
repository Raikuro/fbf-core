"""Part 52 timing-leverage withdrawal policy.

Implements the ERN Part 52 (Timing Leverage in Retirement) withdrawal semantics:
- Borrow when index drawdown >= threshold (loan_balance == 0)
- Repay at fresh index ATH (loan_balance > 0)
- Normal withdrawal when neither condition is met

The policy reads index-level ATH data from MarketSnapshot and loan
balance from DebtInfo.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fbf.core.domain.model.decision_context import DecisionContext
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies.decisions import WithdrawalDecision
from fbf.core.domain.policies.frequency import WithdrawalFrequency
from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy


class Part52WithdrawalPolicy(WithdrawalPolicy):
    """Withdrawal policy for Part 52 timing-leverage studies.

    Computes both the portfolio withdrawal and the loan draw as fractions
    of the budget.  The budget is computed from initial_wealth at cohort
    start and is constant across all periods.

    In ``MONTHLY`` mode the budget is ``initial_wealth × rate / 12``; in
    ``ANNUAL`` mode it is ``initial_wealth × rate``.  The borrow/repay
    decision logic is identical in both modes and is coupled to the
    withdrawal event — leverage actions occur only when the policy
    produces a non-zero withdrawal.

    Parameters
    ----------
    withdrawal_rate:
        Annual portfolio withdrawal rate (e.g. ``Decimal("0.0391")`` for 3.91%).
    borrow_pct:
        Fraction of the budget funded by the margin loan
        (e.g. ``Decimal("0.4108")`` for 41.08%).
    drawdown_threshold:
        Index drawdown below which borrowing is activated
        (e.g. ``Decimal("0.20")`` for 20%).
    frequency:
        Withdrawal cadence.  ``MONTHLY`` (default) divides the annual rate
        by 12 per invocation.  ``ANNUAL`` uses the full annual rate once
        per year (``period_index % 12 == 0``).
    """

    def __init__(
        self,
        withdrawal_rate: Decimal,
        borrow_pct: Decimal,
        drawdown_threshold: Decimal,
        *,
        frequency: WithdrawalFrequency = WithdrawalFrequency.MONTHLY,
    ) -> None:
        super().__init__(frequency=frequency)
        self.withdrawal_rate = withdrawal_rate
        self.borrow_pct = borrow_pct
        self.drawdown_threshold = drawdown_threshold

    def _decide_active(self, context: DecisionContext) -> WithdrawalDecision:
        sim_context: Any = getattr(context, "simulation_context", None)
        if sim_context is None:
            raise TypeError(
                "Part52WithdrawalPolicy requires a DecisionContext with simulation_context"
            )
        if not hasattr(sim_context, "dataset") or not hasattr(
            sim_context, "initial_portfolio"
        ):
            raise TypeError(
                "Part52WithdrawalPolicy requires a SimulationContext with "
                "dataset and initial_portfolio"
            )

        # 1. Compute budget from initial_wealth
        initial_snapshot = sim_context.dataset[0]
        initial_wealth = Money.ZERO
        for holding in sim_context.initial_portfolio.holdings:
            price = initial_snapshot.index_levels[holding.asset_class]
            initial_wealth += Money(holding.units * price, Currency.EUR)
        if self.frequency is WithdrawalFrequency.ANNUAL:
            budget = initial_wealth.amount * self.withdrawal_rate
        else:
            budget = initial_wealth.amount * self.withdrawal_rate / Decimal("12")

        # 2. Compute index-level drawdown
        equity_asset = None
        for asset_class in context.market_snapshot.index_levels:
            if asset_class.id == "equity":
                equity_asset = asset_class
                break
        if equity_asset is None:
            raise ValueError("MarketSnapshot must contain an equity asset class")

        equity_index = context.market_snapshot.index_levels[equity_asset]
        running_ath = context.market_snapshot.running_ath
        drawdown = Decimal("1") - equity_index / running_ath if running_ath > 0 else Decimal("0")

        # 3. Get current loan balance from debt_info
        loan_balance = Decimal("0")
        if context.debt_info is not None:
            loan_balance = context.debt_info.loan_balance

        # 4. Decision logic (identical structure for both frequencies)
        if drawdown >= self.drawdown_threshold and loan_balance == 0:
            # BORROW: activate leverage
            portfolio_withdrawal = budget * (Decimal("1") - self.borrow_pct)
            loan_draw = budget * self.borrow_pct
            is_repayment = False
        elif context.market_snapshot.is_ath and loan_balance > 0:
            # REPAY: double withdrawal, no loan draw
            portfolio_withdrawal = budget * 2
            loan_draw = Decimal("0")
            is_repayment = True
        else:
            # NORMAL: no leverage activity
            portfolio_withdrawal = budget
            loan_draw = Decimal("0")
            is_repayment = False

        return WithdrawalDecision(
            reason="Part52WithdrawalPolicy",
            nominal_amount=Money(portfolio_withdrawal, Currency.EUR),
            real_amount=Money(portfolio_withdrawal, Currency.EUR),
            loan_draw_amount=loan_draw,
            is_repayment=is_repayment,
        )
