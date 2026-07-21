from __future__ import annotations

from datetime import date

from engine.application.pipeline import SimulationPipeline
from engine.application.simulation import (
    SimulationResult,
    SimulationStatistics,
    SimulationTimeline,
    SimulationState,
)
from engine.application.simulation_context import SimulationContext


def _advance_month(current_date: date) -> date:
    year = current_date.year + (current_date.month // 12)
    month = current_date.month % 12 + 1
    return date(year, month, min(current_date.day, 28))


class SimulationRunner:
    """Executes a single Simulation using the Engine application services."""

    def __init__(self, pipeline: SimulationPipeline) -> None:
        self.pipeline = pipeline

    def run(self, context: SimulationContext) -> SimulationResult:
        state = SimulationState(
            context=context,
            current_date=context.start_date,
            period_index=0,
            portfolio=context.initial_portfolio,
            current_wealth=context.initial_wealth,
            peak_wealth=context.initial_wealth,
        )

        for _ in range(context.horizon_months):
            state = self.pipeline.execute(state)
            if state.failure_state is not None:
                break
            state.current_date = _advance_month(state.current_date)
            state.period_index += 1

        final_wealth = state.current_wealth or context.initial_wealth
        statistics = SimulationStatistics(
            final_wealth=final_wealth,
            max_drawdown=0.0,
            success=state.failure_state is None,
            failure_month=state.period_index if state.failure_state else None,
            months_simulated=len(state.monthly_results),
            execution_time_seconds=0.0,
        )

        return SimulationResult(
            timeline=SimulationTimeline(monthly_results=tuple(state.monthly_results)),
            statistics=statistics,
        )
