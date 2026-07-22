"""Statistics builder for simulation results.

Responsible for constructing SimulationStatistics from completed simulation state.
The runner delegates all statistics calculation to this component, remaining purely
an orchestration layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from engine.application.simulation import SimulationStatistics, SimulationState


class SimulationStatisticsBuilder(ABC):
    """Abstract builder for constructing SimulationStatistics from SimulationState."""

    @abstractmethod
    def build(self, state: SimulationState) -> SimulationStatistics:
        """Construct SimulationStatistics from the completed simulation state.

        Args:
            state: The completed SimulationState after execution terminates.

        Returns:
            SimulationStatistics with all required metrics.
        """
        raise NotImplementedError


class DefaultSimulationStatisticsBuilder(SimulationStatisticsBuilder):
    """Default implementation that constructs available statistics from state.

    This builder constructs statistics that are available immediately from the
    execution state. Statistics requiring specialized calculation (such as
    max_drawdown or execution_time_seconds) should be implemented in dedicated
    calculator components and integrated here when available.
    """

    def build(self, state: SimulationState) -> SimulationStatistics:
        """Construct statistics from the completed state.

        Currently constructs:
        - final_wealth: from state.current_wealth or context.initial_wealth
        - success: from status == COMPLETED and no failure_state
        - failure_month: from state.period_index if failed
        - months_simulated: from timeline length

        Deferred to future calculators:
        - max_drawdown: requires timeline analysis
        - execution_time_seconds: requires timing instrumentation
        """
        from engine.application.simulation import ExecutionStatus
        
        final_wealth = state.current_wealth or state.context.initial_wealth
        success = (
            state.status == ExecutionStatus.COMPLETED
            and state.failure_state is None
        )
        failure_month = state.period_index if state.failure_state else None

        return SimulationStatistics(
            final_wealth=final_wealth,
            max_drawdown=0.0,  # Placeholder: requires dedicated calculator
            success=success,
            failure_month=failure_month,
            months_simulated=len(state.monthly_results),
            execution_time_seconds=0.0,  # Placeholder: requires timing instrumentation
        )
