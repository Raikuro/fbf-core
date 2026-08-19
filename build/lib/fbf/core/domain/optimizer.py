from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class OptimizationResult:
    """Immutable result returned by an Optimizer."""

    optimal_rate: float
    iterations: int
    convergence_history: Sequence[float]


class Optimizer:
    """Optimizer abstraction for finding the Safe Withdrawal Rate."""

    def search(self, initial_context: object) -> OptimizationResult:
        raise NotImplementedError
