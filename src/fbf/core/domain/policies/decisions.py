"""Policy decision placeholders for the Engine domain."""

from __future__ import annotations

from dataclasses import dataclass

from ..model.allocation import AllocationTarget
from ..model.money import Money


@dataclass(frozen=True)
class PolicyDecision:
    """Immutable result produced by a Policy."""

    reason: str


@dataclass(frozen=True)
class AllocationDecision(PolicyDecision):
    """Allocation decision returned by an AllocationPolicy."""

    allocation_target: AllocationTarget


@dataclass(frozen=True)
class WithdrawalDecision(PolicyDecision):
    """Withdrawal decision returned by a WithdrawalPolicy."""

    nominal_amount: Money
    real_amount: Money
