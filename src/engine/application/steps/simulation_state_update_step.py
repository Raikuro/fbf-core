from __future__ import annotations

from datetime import date

from engine.application.pipeline import PipelineStep
from engine.application.simulation import ExecutionStatus, SimulationState
from engine.domain.model.market_snapshot import MarketSnapshot


class SimulationStateUpdateStep(PipelineStep):
    """PipelineStep that advances state for the next simulation month."""

    sequence_order = 80

    def execute(self, state: SimulationState) -> SimulationState:
        self._validate_state(state)

        if state.status == ExecutionStatus.COMPLETED:
            return state

        if state.failure_state is not None:
            state.status = ExecutionStatus.FAILED
            return state

        if self._has_reached_horizon(state):
            state.status = ExecutionStatus.COMPLETED
            return state

        next_market_snapshot = self._select_next_market_snapshot(state)
        if next_market_snapshot is None:
            state.status = ExecutionStatus.COMPLETED
            return state

        state.current_date = self._advance_month(state.current_date)
        state.period_index += 1
        state.market_snapshot = next_market_snapshot
        state.status = ExecutionStatus.RUNNING

        return state

    def _validate_state(self, state: SimulationState) -> None:
        if state.current_date is None:
            raise ValueError("SimulationState.current_date is required")
        if state.period_index is None:
            raise ValueError("SimulationState.period_index is required")
        if state.market_snapshot is None:
            raise ValueError("SimulationState.market_snapshot is required")
        if state.context is None:
            raise ValueError("SimulationState.context is required")
        if state.context.dataset is None:
            raise ValueError("SimulationState.context.dataset is required")
        if state.context.horizon_months is None:
            raise ValueError("SimulationState.context.horizon_months is required")
        if state.period_index < 0:
            raise ValueError("SimulationState.period_index must not be negative")

    def _has_reached_horizon(self, state: SimulationState) -> bool:
        return state.period_index + 1 >= state.context.horizon_months

    def _select_next_market_snapshot(self, state: SimulationState) -> MarketSnapshot | None:
        dataset = state.context.dataset
        next_index = state.period_index + 1
        if next_index >= len(dataset):
            return None
        return dataset[next_index]

    def _advance_month(self, current_date: date) -> date:
        year = current_date.year + (current_date.month // 12)
        month = current_date.month % 12 + 1
        return date(year, month, min(current_date.day, 28))
