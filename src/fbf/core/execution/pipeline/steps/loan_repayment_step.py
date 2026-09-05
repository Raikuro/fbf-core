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
    It computes the excess as portfolio_withdrawal - budget (where budget
    is portfolio_withdrawal / 2 in repayment mode) and repays the lesser
    of the excess and the outstanding loan balance.

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
        """
        if state.withdrawal_decision is None:
            return state

        if not state.withdrawal_decision.is_repayment:
            return state

        if state.loan_balance <= 0:
            return state

        # Compute excess: double withdrawal minus normal budget
        # In repayment mode, portfolio_withdrawal = budget * 2
        # So budget = portfolio_withdrawal / 2
        portfolio_withdrawal = state.withdrawal_decision.nominal_amount.amount
        budget = portfolio_withdrawal / Decimal("2")
        excess = portfolio_withdrawal - budget  # = budget

        # Repay the lesser of excess and loan_balance
        repayment = min(excess, state.loan_balance)
        state.loan_balance -= repayment

        return state

    def _validate_state(self, state: SimulationState) -> None:
        if state.portfolio is None:
            raise ValueError("SimulationState.portfolio is required")
