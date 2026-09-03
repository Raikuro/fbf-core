"""Statistics builder for simulation results.

Responsible for constructing SimulationStatistics from completed simulation state.
The runner delegates all statistics calculation to this component, remaining purely
an orchestration layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from fbf.core.execution.pipeline.simulation import SimulationState, SimulationStatistics


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

        Success requires:
        1. The simulation survived every month (status == COMPLETED, no failure_state).
        2. If a ``final_value_target`` is configured, the final wealth must be
           >= target_fraction * initial_wealth.

        Depletion during execution is an intrinsic failure and takes precedence:
        a depleted portfolio is always unsuccessful regardless of the target.
        """
        from fbf.core.execution.pipeline.simulation import ExecutionStatus

        final_wealth = state.current_wealth or state.context.initial_wealth
        survived = (
            state.status == ExecutionStatus.COMPLETED
            and state.failure_state is None
        )

        success = survived
        if survived and state.context.final_value_target is not None:
            threshold = state.context.final_value_target * state.context.initial_wealth.amount
            if final_wealth.amount < threshold:
                success = False

        failure_month = state.period_index if state.failure_state else None

        return SimulationStatistics(
            final_wealth=final_wealth,
            max_drawdown=0.0,  # Placeholder: requires dedicated calculator
            success=success,
            failure_month=failure_month,
            failure_state=state.failure_state,
            months_simulated=len(state.monthly_results),
            execution_time_seconds=0.0,  # Placeholder: requires timing instrumentation
        )
