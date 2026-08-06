"""Withdrawal policy abstractions for the Engine domain."""

from __future__ import annotations

from ..model.decision_context import DecisionContext
from .decisions import WithdrawalDecision
from .policy import Policy


class WithdrawalPolicy(Policy):
    """Policy that decides the withdrawal amount for a simulation."""

    def decide(self, context: DecisionContext) -> WithdrawalDecision:
        raise NotImplementedError
