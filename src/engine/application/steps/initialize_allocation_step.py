"""Pipeline step that materialises the initial allocation for month 0.

The monthly pipeline carries ``SimulationState.allocation`` and
``SimulationState.allocation_target`` forward between months: rebalancing and
market evolution refresh them at the end of every month, and
``BuildDecisionContextStep`` consumes them at the start of the next month.

Month 0 has no carried-over values.  This step derives the portfolio's initial
value-weighted allocation once (before ``BuildDecisionContextStep``) and seeds
both ``allocation`` and ``allocation_target`` with it.  On every subsequent
month the fields are already populated, so the step is a no-op.
"""

from __future__ import annotations

from engine.application.pipeline import PipelineStep
from engine.application.simulation import SimulationState
from engine.domain.model.allocation import AllocationTarget
from engine.domain.services.portfolio_market_evolution_service import (
    PortfolioMarketEvolutionService,
)


class InitializeAllocationStep(PipelineStep):
    """PipelineStep that seeds the initial allocation before the first month."""

    sequence_order = 0

    def __init__(self, evolution_service: PortfolioMarketEvolutionService | None = None) -> None:
        self.evolution_service = evolution_service or PortfolioMarketEvolutionService()

    def execute(self, state: SimulationState) -> SimulationState:
        self._validate_state(state)

        if state.allocation is not None:
            return state

        assert state.market_snapshot is not None

        allocation = self.evolution_service.derive_allocation(
            portfolio=state.portfolio,
            market_snapshot=state.market_snapshot,
        )

        state.allocation = allocation
        state.allocation_target = AllocationTarget(weights=allocation.weights)

        return state

    def _validate_state(self, state: SimulationState) -> None:
        if state.portfolio is None:
            raise ValueError("SimulationState.portfolio is required")
        if state.market_snapshot is None:
            raise ValueError("SimulationState.market_snapshot is required")
        if state.context is None:
            raise ValueError("SimulationState.context is required")
