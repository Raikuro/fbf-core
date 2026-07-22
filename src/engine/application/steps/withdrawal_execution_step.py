"""Pipeline step that executes a previously requested withdrawal."""

from __future__ import annotations

from engine.application.pipeline import PipelineStep
from engine.application.simulation import SimulationState
from engine.domain.services.portfolio_withdrawal_service import (
    PortfolioWithdrawalService,
)


class WithdrawalExecutionStep(PipelineStep):
    """PipelineStep that applies the withdrawal decision to the portfolio."""

    sequence_order = 30

    def __init__(self, withdrawal_service: PortfolioWithdrawalService | None = None) -> None:
        self.withdrawal_service = withdrawal_service or PortfolioWithdrawalService()

    def execute(self, state: SimulationState) -> SimulationState:
        self._validate_state(state)

        result = self.withdrawal_service.execute_withdrawal(
            portfolio=state.portfolio,
            requested_withdrawal=state.withdrawal_decision,
            market_snapshot=state.market_snapshot,
        )

        state.portfolio = result.portfolio
        state.current_wealth = result.remaining_value
        if result.depleted:
            state.failure_state = "depleted"

        return state

    def _validate_state(self, state: SimulationState) -> None:
        if state.withdrawal_decision is None:
            raise ValueError("SimulationState.withdrawal_decision is required")
        if state.portfolio is None:
            raise ValueError("SimulationState.portfolio is required")
        if state.market_snapshot is None:
            raise ValueError("SimulationState.market_snapshot is required")
