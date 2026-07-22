from __future__ import annotations

from datetime import date

from engine.application.pipeline import SimulationPipeline
from engine.application.simulation import (
    ExecutionStatus,
    SimulationResult,
    SimulationTimeline,
    SimulationState,
)
from engine.application.simulation_context import SimulationContext
from engine.application.statistics_builder import (
    DefaultSimulationStatisticsBuilder,
    SimulationStatisticsBuilder,
)


def _advance_month(current_date: date) -> date:
    year = current_date.year + (current_date.month // 12)
    month = current_date.month % 12 + 1
    return date(year, month, min(current_date.day, 28))


class SimulationRunner:
    """Executes a single Simulation using the Engine application services."""

    def __init__(
        self,
        pipeline: SimulationPipeline,
        statistics_builder: SimulationStatisticsBuilder | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.statistics_builder = (
            statistics_builder
            if statistics_builder is not None
            else DefaultSimulationStatisticsBuilder()
        )

    def run(self, context: SimulationContext) -> SimulationResult:
        self._validate_context(context)
        state = self._initialize_state(context)

        while state.status == ExecutionStatus.RUNNING:
            for step in self.pipeline.steps:
                state = step.execute(state)
                if state.failure_state is not None:
                    state.status = ExecutionStatus.FAILED
                    break
                if state.status != ExecutionStatus.RUNNING:
                    break
            if state.status != ExecutionStatus.RUNNING:
                break

        return self._build_result(state)

    def _validate_context(self, context: SimulationContext) -> None:
        if context is None:
            raise ValueError("SimulationContext is required")
        if context.dataset is None:
            raise ValueError("SimulationContext.dataset is required")
        if context.horizon_months is None:
            raise ValueError("SimulationContext.horizon_months is required")
        if context.horizon_months < 0:
            raise ValueError("SimulationContext.horizon_months must not be negative")
        if context.initial_portfolio is None:
            raise ValueError("SimulationContext.initial_portfolio is required")
        if context.initial_wealth is None:
            raise ValueError("SimulationContext.initial_wealth is required")
        if context.start_date is None:
            raise ValueError("SimulationContext.start_date is required")

    def _initialize_state(self, context: SimulationContext) -> SimulationState:
        if context.horizon_months == 0:
            status = ExecutionStatus.COMPLETED
            market_snapshot = None
        else:
            status = ExecutionStatus.RUNNING
            try:
                market_snapshot = context.dataset[0]
            except IndexError as exc:
                raise ValueError(
                    "SimulationContext.dataset must provide an initial MarketSnapshot "
                    "for a positive horizon"
                ) from exc
            if market_snapshot.date != context.start_date:
                raise ValueError(
                    "SimulationContext.start_date must match the first dataset snapshot date"
                )

        return SimulationState(
            context=context,
            current_date=context.start_date,
            period_index=0,
            portfolio=context.initial_portfolio,
            market_snapshot=market_snapshot,
            current_wealth=context.initial_wealth,
            peak_wealth=context.initial_wealth,
            status=status,
        )

    def _build_result(self, state: SimulationState) -> SimulationResult:
        statistics = self.statistics_builder.build(state)

        return SimulationResult(
            timeline=SimulationTimeline(monthly_results=tuple(state.monthly_results)),
            statistics=statistics,
        )
