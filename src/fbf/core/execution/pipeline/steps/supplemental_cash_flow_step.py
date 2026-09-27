"""Supplemental cash flow pipeline step for Part 42 Social Security.

Adds external income (Social Security/pension) to cash_balance before
WithdrawalExecutionStep consumes it.
"""

from __future__ import annotations

from decimal import Decimal

from fbf.core.execution.pipeline.pipeline import PipelineStep
from fbf.core.execution.pipeline.simulation import SimulationState


class SupplementalCashFlowStep(PipelineStep):
    """PipelineStep that adds supplemental income to cash_balance.

    This step runs between LoanDrawStep (28) and WithdrawalExecutionStep (30)
    to inject external income (e.g., Social Security) into the cash balance,
    reducing the required portfolio withdrawal.

    Authoritative Part 42 semantics:
    - Social Security: $3,000/month starting in year 31 of retirement
    - The income is added to cash_balance and consumed first by
      WithdrawalExecutionStep, reducing portfolio sales.
    - Supplemental income does not affect loan balance or interest accrual.
    """

    sequence_order = 29  # After LoanDrawStep (28), before WithdrawalExecutionStep (30)

    def __init__(
        self,
        ss_amount: Decimal = Decimal("3000"),
        ss_start_period: int = 360,  # Period index when SS starts (0-indexed)
        ss_active: bool = True,
    ) -> None:
        self.ss_amount = ss_amount
        self.ss_start_period = ss_start_period
        self.ss_active = ss_active

    def execute(self, state: SimulationState) -> SimulationState:
        if not self.ss_active:
            return state

        # Add SS income to cash_balance when period_index >= ss_start_period
        if state.period_index >= self.ss_start_period:
            state.cash_balance += self.ss_amount

        return state

    def _validate_state(self, state: SimulationState) -> None:
        pass  # No specific validation needed
