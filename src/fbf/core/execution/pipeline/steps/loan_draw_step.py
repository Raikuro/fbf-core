"""Pipeline step that executes a loan draw (Part 49).

This step increases the loan balance by the draw amount and adds borrowed
funds to the portfolio as liquid cash. The loan draw occurs AFTER
withdrawal execution per S4 Design Review.

NON-PRODUCTION PLACEHOLDER: The current implementation adds borrowed funds
to the first holding in the portfolio. This is economically incorrect and
must be replaced with a canonical cash representation in K.5.
"""

from __future__ import annotations

from decimal import Decimal

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.execution.pipeline.pipeline import PipelineStep
from fbf.core.execution.pipeline.simulation import SimulationState


class LoanDrawStep(PipelineStep):
    """PipelineStep that executes a loan draw.

    This step implements Step 3 of the K.1 semantic contract:
    - Increase loan_balance by loan_draw_amount
    - Add borrowed funds to portfolio (as liquid cash)
    - Debt becomes active immediately upon borrowing
    - Newly borrowed funds participate in market returns this period
    - Newly borrowed funds are NOT used for current-period withdrawal

    ERN Part 49 grounding: loan_draw_amount = initial_wealth × loan_draw_rate / 12.
    This is fixed across all months and computed from initial_wealth at beginning of period.

    The loan draw amount is read from the WithdrawalDecision computed in
    the WithdrawalDecisionStep.

    NON-PRODUCTION PLACEHOLDER: The current implementation adds borrowed funds
    to the first holding in the portfolio. This is economically incorrect and
    must be replaced with a canonical cash representation in K.5.
    """

    sequence_order = 35

    def execute(self, state: SimulationState) -> SimulationState:
        """Execute the loan draw.

        NON-PRODUCTION PLACEHOLDER: Adds borrowed funds to first holding.
        K.5 must implement canonical cash representation.

        Semantic contract (ERN Part 49):
        - loan_draw_amount represents the portion of retirement spending
          financed through debt, not unrestricted investment leverage.
        - portfolio withdrawal + loan_draw_amount = total retirement spending
        - loan_draw_amount is computed from initial_wealth × loan_draw_rate / 12
        - Negative values are rejected (ValueError)
        - Zero values are no-ops
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

        # Add borrowed funds to portfolio as liquid cash
        # This makes the funds available for withdrawal in this period
        state.portfolio = self._add_borrowed_funds_to_portfolio(
            state.portfolio, loan_draw_amount
        )

        return state

    def _add_borrowed_funds_to_portfolio(
        self, portfolio: Portfolio, amount: Decimal
    ) -> Portfolio:
        """Add borrowed funds to the portfolio as liquid cash.

        NON-PRODUCTION PLACEHOLDER: This method adds borrowed funds to the
        first holding in the portfolio. This is economically incorrect because:
        1. Borrowed cash is added to an arbitrary asset class (first holding)
        2. No separate cash tracking exists
        3. Rebalancing calculations are corrupted
        4. This is NOT valid for production research results

        K.5 must implement canonical representation:
        - Option 1: Dedicated AssetClass.CASH holding
        - Option 2: Cash-balance in SimulationState
        - Option 3: Portfolio-level cash sub-account
        """
        if not portfolio.holdings:
            # Create a new cash holding
            cash_holding = AssetHolding(
                asset_class=AssetClass(id="cash", name="Cash", description="Liquid cash"),
                units=amount,
            )
            return Portfolio(holdings=(cash_holding,))
        else:
            # Add to the first holding by creating a new Portfolio
            # In a real implementation, this would be a dedicated cash holding
            first_holding = portfolio.holdings[0]
            new_holding = AssetHolding(
                asset_class=first_holding.asset_class,
                units=first_holding.units + amount,
            )
            new_holdings = (new_holding,) + tuple(portfolio.holdings[1:])
            return Portfolio(holdings=new_holdings)

    def _validate_state(self, state: SimulationState) -> None:
        if state.portfolio is None:
            raise ValueError("SimulationState.portfolio is required")
        if state.interest_rate <= 0:
            return  # No validation needed if debt is not configured
