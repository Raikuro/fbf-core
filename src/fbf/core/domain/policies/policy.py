"""Policy abstractions for the Engine domain.

Contains the base Policy contract and related decision objects.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..model.decision_context import DecisionContext
from .decisions import PolicyDecision


class Policy(ABC):
    """Base policy abstraction for simulation decisions."""

    @abstractmethod
    def decide(self, context: DecisionContext) -> PolicyDecision:
        raise NotImplementedError
