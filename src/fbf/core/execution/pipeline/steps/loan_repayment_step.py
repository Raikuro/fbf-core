"""Pipeline step that executes loan repayment (Part 52).

When is_repayment is True, this step computes the excess withdrawal
(double withdrawal minus normal budget) and repays the lesser of the
excess and the outstanding loan balance.
"""

from __future__ import annotations

from decimal import Decimal

from fbf.core.execution.pipeline.pipeline import PipelineStep
from fbf.core.execution.pipeline.simulation import SimulationState


class LoanRepaymentStep(PipelineStep):
    """PipelineStep that executes loan repayment.

    This step only executes when WithdrawalDecision.is_repayment is True.
    It computes the excess as nominal_amount - spending_budget and repays
    the lesser of the excess and the outstanding loan balance.

    Sequence order: 32 (after WithdrawalExecutionStep at 30).
    """

    sequence_order = 32

    def execute(self, state: SimulationState) -> SimulationState:
        """Execute loan repayment.

        Authoritative behavior:
        - Only execute when is_repayment is True
        - Only execute when loan_balance > 0
        - Repayment = min(excess, loan_balance)
        - loan_balance -= repayment

        Also records period_draw_repay for the ERN spreadsheet artifact:
        positive = draw, negative = repay, zero = neutral.
        """
        if state.withdrawal_decision is None:
            state.period_draw_repay = Decimal("0")
            return state

        loan_draw = state.withdrawal_decision.loan_draw_amount

        if state.withdrawal_decision.is_repayment and state.loan_balance > 0:
            # Compute excess: nominal_amount - spending_budget
            # REPAY: nominal_amount = C, spending_budget = C - D_{t-1}
            # excess = C - (C - D_{t-1}) = D_{t-1}
            nominal_amount = state.withdrawal_decision.nominal_amount.amount
            spending_budget = state.withdrawal_decision.spending_budget
            excess = nominal_amount - spending_budget

            # Repay the lesser of excess and loan_balance
            repayment = min(excess, state.loan_balance)
            state.loan_balance -= repayment
            state.period_draw_repay = -repayment
        elif loan_draw > 0:
            state.period_draw_repay = loan_draw
        else:
            state.period_draw_repay = Decimal("0")

        return state

    def _validate_state(self, state: SimulationState) -> None:
        if state.portfolio is None:
            raise ValueError("SimulationState.portfolio is required")
