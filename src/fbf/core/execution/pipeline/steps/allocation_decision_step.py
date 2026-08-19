"""Pipeline step that obtains the monthly allocation decision."""

from __future__ import annotations

from fbf.core.domain.policies.decisions import AllocationDecision
from fbf.core.execution.pipeline.pipeline import PipelineStep
from fbf.core.execution.pipeline.simulation import SimulationState


class AllocationDecisionStep(PipelineStep):
    """PipelineStep that requests an allocation decision."""

    sequence_order = 40

    def execute(self, state: SimulationState) -> SimulationState:
        self._validate_state(state)
        assert state.decision_context is not None

        decision = state.context.allocation_policy.decide(state.decision_context)
        if not isinstance(decision, AllocationDecision):
            raise TypeError("AllocationPolicy.decide must return an AllocationDecision")

        state.allocation_decision = decision
        return state

    def _validate_state(self, state: SimulationState) -> None:
        if state.decision_context is None:
            raise ValueError("SimulationState.decision_context is required")
        if state.context is None:
            raise ValueError("SimulationState.context is required")
        if state.context.allocation_policy is None:
            raise ValueError("SimulationContext.allocation_policy is required")
