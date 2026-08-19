from __future__ import annotations

from fbf.core.domain.services.portfolio_market_evolution_service import (
    PortfolioMarketEvolutionService,
)
from fbf.core.execution.pipeline.pipeline import PipelineStep
from fbf.core.execution.pipeline.simulation import SimulationState


class MarketEvolutionStep(PipelineStep):
    """PipelineStep that applies market evolution to the portfolio."""

    sequence_order = 60

    def __init__(self, evolution_service: PortfolioMarketEvolutionService | None = None) -> None:
        self.evolution_service = evolution_service or PortfolioMarketEvolutionService()

    def execute(self, state: SimulationState) -> SimulationState:
        self._validate_state(state)
        assert state.market_snapshot is not None

        result = self.evolution_service.apply_market_evolution(
            portfolio=state.portfolio,
            market_snapshot=state.market_snapshot,
        )

        state.portfolio = result.portfolio
        state.allocation = result.allocation
        state.current_wealth = result.current_value

        return state

    def _validate_state(self, state: SimulationState) -> None:
        if state.portfolio is None:
            raise ValueError("SimulationState.portfolio is required")
        if state.market_snapshot is None:
            raise ValueError("SimulationState.market_snapshot is required")
        if state.current_wealth is None:
            raise ValueError("SimulationState.current_wealth is required")
