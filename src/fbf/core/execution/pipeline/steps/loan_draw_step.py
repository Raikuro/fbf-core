"""Pipeline step that executes a loan draw (Part 49).

This step increases the loan balance by the draw amount and adds borrowed
funds to the cash balance. The loan draw occurs AFTER withdrawal execution
per S4 Design Review.

Authoritative Part 49 semantics:
- loan_draw_amount = initial_wealth × loan_draw_rate / 12
- portfolio withdrawal + loan_draw_amount = total retirement spending
- loan_draw_amount finances consumption (retirement spending), not investment
- Independent investment leverage is NOT part of Part 49

Canonical representation: Borrowed funds are added to cash_balance in
SimulationState, not to portfolio holdings. This preserves clean separation
between investment portfolio and borrowed liquidity.
"""

from __future__ import annotations

from fbf.core.execution.pipeline.pipeline import PipelineStep
from fbf.core.execution.pipeline.simulation import SimulationState


class LoanDrawStep(PipelineStep):
    """PipelineStep that executes a loan draw.

    This step implements Step 3 of the K.1 semantic contract:
    - Increase loan_balance by loan_draw_amount
    - Add borrowed funds to cash_balance
    - Debt becomes active immediately upon borrowing
    - Newly borrowed funds participate in market returns this period
    - Newly borrowed funds are NOT used for current-period withdrawal

    ERN Part 49 grounding: loan_draw_amount = initial_wealth × loan_draw_rate / 12.
    This is fixed across all months and computed from initial_wealth at beginning of period.

    The loan draw amount is read from the WithdrawalDecision computed in
    the WithdrawalDecisionStep.
    """

    sequence_order = 28

    def execute(self, state: SimulationState) -> SimulationState:
        """Execute the loan draw.

        Authoritative behavior:
        - loan_draw_amount < 0: REJECTED (ValueError)
        - loan_draw_amount = 0: NO-OP
        - loan_draw_amount > 0: ACTIVE (loan balance increases, cash balance increases)
        """
        self._validate_state(state)

        # If no debt is configured, this is a no-op
        if state.interest_rate <= 0:
            return state

        # Read loan draw amount from withdrawal decision
        if state.withdrawal_decision is None:
            return state

        loan_draw_amount = state.withdrawal_decision.loan_draw_amount

        # Explicit rejection for negative draws (K.4.2 requirement)
        if loan_draw_amount < 0:
            raise ValueError(
                f"loan_draw_amount must be non-negative, got {loan_draw_amount}"
            )

        # No-op for zero draws
        if loan_draw_amount == 0:
            return state

        # Increase loan balance
        state.loan_balance += loan_draw_amount

        # Add borrowed funds to cash balance (canonical representation)
        state.cash_balance += loan_draw_amount

        return state

    def _validate_state(self, state: SimulationState) -> None:
        if state.portfolio is None:
            raise ValueError("SimulationState.portfolio is required")
        if state.interest_rate <= 0:
            return  # No validation needed if debt is not configured
