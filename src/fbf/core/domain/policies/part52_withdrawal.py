"""Part 52 timing-leverage withdrawal policy.

Implements the ERN Part 52 (Timing Leverage in Retirement) withdrawal semantics:
- Borrow when compound real total-return drawdown >= threshold (every eligible
  month, regardless of existing loan balance — matching ERN's monthly-draw
  methodology)
- Repay at fresh index ATH (loan_balance > 0)
- Normal withdrawal when neither condition is met

The policy reads compound drawdown from DecisionContext and loan
balance from DebtInfo.

Compound drawdown is the path-dependent, multiplicative real total-return
drawdown: ``cDD = min(0, (1 + prev_cDD) * real_TR_ratio - 1)``. This
matches ERN's exact formula from the Excel spreadsheet.
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

    Each month the drawdown condition is active (index drawdown >= threshold),
    a new loan draw is created, matching ERN's monthly-draw methodology.
    Draws accumulate on the existing loan balance rather than replacing it.

    Production status
    -----------------
    ``Part52NumbaExecutor`` uses this object only as a parameter carrier and
    type identity; it does not call :meth:`decide`. The canonical Part 52
    trajectory, including ``B22=1`` repayment (``C + MIN(loan, C)``), is
    implemented by ``_simulate_part52``.

    The ``decide()`` implementation below is retained for the legacy generic
    decision pipeline. Its ``spending_budget = C - D_{t-1}`` accounting is
    pre-``B22=1`` and must not be treated as the canonical Part 52 contract.

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

        # 2. Use compound (path-dependent) real total-return drawdown
        #    This matches ERN's exact formula from the Excel spreadsheet.
        compound_dd = context.compound_drawdown

        # 3. Get D_{t-1} from context.previous_draw_repay
        d_prev = context.previous_draw_repay

        # 3b. Get current loan balance for REPAY condition check
        loan_balance = Decimal("0")
        if context.debt_info is not None:
            loan_balance = context.debt_info.loan_balance

        # 4. Decision logic (identical structure for both frequencies)
        # drawdown_threshold is positive (e.g., 0.20 for 20% drawdown).
        # Borrow when compound drawdown <= -threshold (more negative = deeper drawdown).
        if compound_dd <= -self.drawdown_threshold:
            # BORROW: activate leverage
            # ERN workbook: W = V - X (portfolio withdrawal = budget - loan_draw)
            # The full budget V is passed as nominal_amount; WithdrawalExecutionStep
            # consumes the loan_draw X from cash first, selling the remainder V - X
            # from the portfolio — matching ERN's W = V - X.
            loan_draw = budget * self.borrow_pct
            nominal_amount = budget
            is_repayment = False
        elif compound_dd == Decimal("0") and loan_balance > 0:
            # REPAY signal. The legacy decision path encodes the repayment
            # through spending_budget below; canonical B22=1 cash flows are
            # implemented by the Numba kernel, not this decision object.
            loan_draw = Decimal("0")
            nominal_amount = budget
            is_repayment = True
        else:
            # NORMAL: no leverage activity
            # nominal = C → portfolio_sale = C
            loan_draw = Decimal("0")
            nominal_amount = budget
            is_repayment = False

        # LEGACY: pre-B22=1 excess accounting for the unused generic decision
        # path. Canonical Part 52 repayment is implemented by the Numba kernel.
        # The legacy consumer derives excess = nominal_amount - spending_budget:
        #   BORROW: C - (C - D_{t-1}) = D_{t-1} (positive but is_repayment=False)
        #   REPAY:  C - (C - D_{t-1}) = D_{t-1}
        #   NORMAL: C - C = 0
        spending_budget = budget - d_prev

        return WithdrawalDecision(
            reason="Part52WithdrawalPolicy",
            nominal_amount=Money(nominal_amount, Currency.EUR),
            real_amount=Money(nominal_amount, Currency.EUR),
            loan_draw_amount=loan_draw,
            is_repayment=is_repayment,
            spending_budget=spending_budget,
        )
