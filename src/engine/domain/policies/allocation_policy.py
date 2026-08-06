"""Allocation policy abstractions for the Engine domain."""

from __future__ import annotations

from ..model.decision_context import DecisionContext
from .decisions import AllocationDecision
from .policy import Policy


class AllocationPolicy(Policy):
    """Policy that decides the allocation target for a simulation."""

    def decide(self, context: DecisionContext) -> AllocationDecision:
        raise NotImplementedError
