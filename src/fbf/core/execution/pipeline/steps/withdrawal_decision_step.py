"""Pipeline step that obtains the monthly withdrawal decision."""

from __future__ import annotations

from fbf.core.domain.policies.decisions import WithdrawalDecision
from fbf.core.execution.pipeline.pipeline import PipelineStep
from fbf.core.execution.pipeline.simulation import SimulationState


class WithdrawalDecisionStep(PipelineStep):
    """PipelineStep that requests the monthly withdrawal decision."""

    sequence_order = 20

    def execute(self, state: SimulationState) -> SimulationState:
        self._validate_state(state)
        assert state.decision_context is not None

        decision = state.context.withdrawal_policy.decide(state.decision_context)
        self._validate_decision(decision)

        state.withdrawal_decision = decision
        return state

    def _validate_state(self, state: SimulationState) -> None:
        if state.decision_context is None:
            raise ValueError("SimulationState.decision_context is required")
        if state.context is None:
            raise ValueError("SimulationState.context is required")
        if state.context.withdrawal_policy is None:
            raise ValueError("SimulationContext.withdrawal_policy is required")

    def _validate_decision(self, decision: object) -> None:
        if not isinstance(decision, WithdrawalDecision):
            raise TypeError(
                "WithdrawalPolicy.decide must return a WithdrawalDecision"
            )
