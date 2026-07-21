"""Allocation policy abstractions for the Engine domain."""

from __future__ import annotations

from .policy import Policy
from .decisions import AllocationDecision
from ..model.decision_context import DecisionContext


class AllocationPolicy(Policy):
    """Policy that decides the allocation target for a simulation."""

    def decide(self, context: DecisionContext) -> AllocationDecision:
        raise NotImplementedError
