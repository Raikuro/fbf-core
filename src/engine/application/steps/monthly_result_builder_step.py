from __future__ import annotations

from engine.application.simulation import MonthlyResult, SimulationState


class MonthlyResultBuilderStep:
    """PipelineStep that captures the current state into a MonthlyResult."""

    sequence_order = 70

    def execute(self, state: SimulationState) -> SimulationState:
        self._validate_state(state)

        monthly_result = MonthlyResult(
            date=state.current_date,
            period_index=state.period_index,
            market_snapshot=state.market_snapshot,
            portfolio=state.portfolio,
            allocation=state.allocation,
            allocation_target=state.allocation_target,
            allocation_drift=state.allocation_drift,
            withdrawal_decision=state.withdrawal_decision,
            rebalance_result=None,
            drawdown=0.0,
            cumulative_return=0.0,
            cumulative_inflation=0.0,
            events=tuple(),
        )

        state.monthly_results.append(monthly_result)
        return state

    def _validate_state(self, state: SimulationState) -> None:
        if state.current_date is None:
            raise ValueError("SimulationState.current_date is required")
        if state.period_index is None:
            raise ValueError("SimulationState.period_index is required")
        if state.portfolio is None:
            raise ValueError("SimulationState.portfolio is required")
        if state.market_snapshot is None:
            raise ValueError("SimulationState.market_snapshot is required")
        if state.current_wealth is None:
            raise ValueError("SimulationState.current_wealth is required")
        if state.monthly_results is None:
            raise ValueError("SimulationState.monthly_results is required")
        if not isinstance(state.monthly_results, list):
            raise TypeError("SimulationState.monthly_results must be a list")
