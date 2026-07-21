from __future__ import annotations

from engine.application.simulation import SimulationState
from engine.domain.services.portfolio_rebalance_service import (
    PortfolioRebalanceService,
)


class PortfolioRebalanceStep:
    """PipelineStep that applies an allocation decision to the portfolio."""

    sequence_order = 50

    def __init__(self, rebalance_service: PortfolioRebalanceService | None = None) -> None:
        self.rebalance_service = rebalance_service or PortfolioRebalanceService()

    def execute(self, state: SimulationState) -> SimulationState:
        self._validate_state(state)

        result = self.rebalance_service.execute_rebalance(
            portfolio=state.portfolio,
            allocation_decision=state.allocation_decision,
            market_snapshot=state.market_snapshot,
        )

        state.portfolio = result.portfolio
        state.allocation = result.allocation
        state.allocation_target = result.allocation_target
        state.current_wealth = result.current_value

        return state

    def _validate_state(self, state: SimulationState) -> None:
        if state.allocation_decision is None:
            raise ValueError("SimulationState.allocation_decision is required")
        if state.portfolio is None:
            raise ValueError("SimulationState.portfolio is required")
        if state.market_snapshot is None:
            raise ValueError("SimulationState.market_snapshot is required")
