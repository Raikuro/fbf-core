"""Withdrawal policy abstractions for the Engine domain."""

from __future__ import annotations

from .policy import Policy
from .decisions import WithdrawalDecision
from ..model.decision_context import DecisionContext


class WithdrawalPolicy(Policy):
    """Policy that decides the withdrawal amount for a simulation."""

    def decide(self, context: DecisionContext) -> WithdrawalDecision:
        raise NotImplementedError
