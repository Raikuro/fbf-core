"""Pipeline step that accrues interest on the loan balance (Part 49).

This step implements Step 7 of the K.1 semantic contract:
- monthly_rate = annual_interest_rate / 12
- interest = loan_balance × monthly_rate
- loan_balance += interest
- Interest is capitalized at end of period
"""

from __future__ import annotations

from decimal import Decimal

from fbf.core.execution.pipeline.pipeline import PipelineStep
from fbf.core.execution.pipeline.simulation import SimulationState


class InterestAccrualStep(PipelineStep):
    """PipelineStep that accrues interest on the loan balance.

    This step capitalizes interest at the end of the period.
    Interest is calculated as: loan_balance × (annual_rate / 12).
    """

    sequence_order = 65

    def execute(self, state: SimulationState) -> SimulationState:
        self._validate_state(state)

        # If no debt is configured, this is a no-op
        if state.interest_rate <= 0:
            return state

        # If no loan balance, no interest to accrue
        if state.loan_balance <= 0:
            return state

        # Calculate monthly interest
        monthly_rate = state.interest_rate / Decimal("12")
        interest = state.loan_balance * monthly_rate

        # Capitalize interest (add to loan balance)
        state.loan_balance += interest

        return state

    def _validate_state(self, state: SimulationState) -> None:
        if state.portfolio is None:
            raise ValueError("SimulationState.portfolio is required")
        if state.market_snapshot is None:
            raise ValueError("SimulationState.market_snapshot is required")
