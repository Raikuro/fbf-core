"""Pipeline step that detects simulation failure states (Part 49).

This step implements Step 10 of the K.1 semantic contract:
- Portfolio depletion: portfolio_value ≤ 0
- Unsatisfiable margin call: loan_balance > portfolio_value AND loan_balance > 0
"""

from __future__ import annotations

from decimal import Decimal

from fbf.core.execution.pipeline.pipeline import PipelineStep
from fbf.core.execution.pipeline.simulation import SimulationState


class FailureDetectionStep(PipelineStep):
    """PipelineStep that detects simulation failure states.

    This step implements the failure detection logic from the K.1 semantic
    contract. It runs after LTV evaluation and before state update.

    Failure states:
    - "depleted": portfolio_value ≤ 0 (regardless of loan balance)
    - "margin_call_impossible": loan_balance > portfolio_value AND loan_balance > 0
    """

    sequence_order = 75

    def execute(self, state: SimulationState) -> SimulationState:
        self._validate_state(state)

        # Calculate current portfolio value
        portfolio_value = self._calculate_portfolio_value(state)

        # Check failure conditions
        if portfolio_value <= 0:
            # Portfolio depleted (this includes both clean depletion and insolvency)
            state.failure_state = "depleted"
        elif state.loan_balance > portfolio_value and state.loan_balance > 0:
            # Unsatisfiable margin call
            state.failure_state = "margin_call_impossible"

        return state

    def _calculate_portfolio_value(self, state: SimulationState) -> Decimal:
        """Calculate the current portfolio value."""
        if state.market_snapshot is None:
            return Decimal("0")

        total = Decimal("0")
        for holding in state.portfolio.holdings:
            price = state.market_snapshot.index_levels.get(holding.asset_class)
            if price is not None:
                total += holding.units * price
        return total

    def _validate_state(self, state: SimulationState) -> None:
        if state.portfolio is None:
            raise ValueError("SimulationState.portfolio is required")
        if state.market_snapshot is None:
            raise ValueError("SimulationState.market_snapshot is required")
