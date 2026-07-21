from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from .model.decision_context import DecisionContext


class Policy(ABC):
    """Base policy abstraction for simulation decisions.

    Responsibilities:
    - define the contract for decision-making in the Engine

    Invariants:
    - policies never mutate the Portfolio or access infrastructure
    """

    @abstractmethod
    def before_simulation(self, context: DecisionContext) -> None:
        raise NotImplementedError

    @abstractmethod
    def before_month(self, context: DecisionContext) -> None:
        raise NotImplementedError

    @abstractmethod
    def decide(self, context: DecisionContext) -> "PolicyDecision":
        raise NotImplementedError

    @abstractmethod
    def after_month(self, context: DecisionContext) -> None:
        raise NotImplementedError

    @abstractmethod
    def after_simulation(self, context: DecisionContext) -> None:
        raise NotImplementedError


@dataclass(frozen=True)
class PolicyDecision(ABC):
    """Immutable result produced by a Policy.

    Responsibilities:
    - represent the output of a decision-making step

    Invariants:
    - decision objects contain no behaviour
    """

    reason: str
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class AllocationDecision(PolicyDecision):
    """Allocation decision returned by an AllocationPolicy."""

    allocation_target: Any


@dataclass(frozen=True)
class WithdrawalDecision(PolicyDecision):
    """Withdrawal decision returned by a WithdrawalPolicy."""

    nominal_amount: Any
    real_amount: Any
