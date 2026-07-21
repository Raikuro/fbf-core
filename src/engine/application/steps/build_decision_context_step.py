"""Pipeline step that constructs a DecisionContext for the current month."""

from __future__ import annotations

from engine.application.simulation import SimulationState
from engine.domain.model.decision_context import DecisionContext


class BuildDecisionContextStep:
    """PipelineStep that builds the domain DecisionContext."""

    sequence_order = 10

    def execute(self, state: SimulationState) -> SimulationState:
        self._validate_state(state)

        decision_context = DecisionContext(
            date=state.current_date,
            period_index=state.period_index,
            simulation_context=state.context,
            portfolio=state.portfolio,
            current_allocation=state.allocation,
            target_allocation=state.allocation_target,
            market_snapshot=state.market_snapshot,
            dataset=state.context.dataset,
        )

        state.decision_context = decision_context
        return state

    def _validate_state(self, state: SimulationState) -> None:
        if state.portfolio is None:
            raise ValueError("SimulationState.portfolio is required")
        if state.allocation is None:
            raise ValueError("SimulationState.allocation is required")
        if state.allocation_target is None:
            raise ValueError("SimulationState.allocation_target is required")
        if state.market_snapshot is None:
            raise ValueError("SimulationState.market_snapshot is required")
        if state.context is None:
            raise ValueError("SimulationState.context is required")
        if state.context.dataset is None:
            raise ValueError("SimulationContext.dataset is required")
        if state.current_date is None:
            raise ValueError("SimulationState.current_date is required")
        if state.period_index is None:
            raise ValueError("SimulationState.period_index is required")
