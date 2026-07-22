"""Pipeline step that obtains the monthly allocation decision."""

from __future__ import annotations

from engine.application.pipeline import PipelineStep
from engine.application.simulation import SimulationState
from engine.domain.policies.decisions import AllocationDecision
from engine.domain.policies.allocation_policy import AllocationPolicy


class AllocationDecisionStep(PipelineStep):
    """PipelineStep that requests an allocation decision."""

    sequence_order = 40

    def execute(self, state: SimulationState) -> SimulationState:
        self._validate_state(state)

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
