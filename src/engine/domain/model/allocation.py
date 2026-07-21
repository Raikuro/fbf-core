"""Allocation model objects for the Engine domain.

Contains allocation-related value objects and targets.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .asset import AssetClass


@dataclass(frozen=True)
class Allocation:
    """Immutable portfolio allocation representation."""

    weights: dict[AssetClass, Decimal]

    def __post_init__(self) -> None:
        total = sum(self.weights.values())
        if total != Decimal("1"):
            raise ValueError("Allocation weights must sum to 1.00")
        if any(value < Decimal("0") for value in self.weights.values()):
            raise ValueError("Allocation weights must not be negative")

    def __getitem__(self, asset_class: AssetClass) -> Decimal:
        return self.weights[asset_class]


@dataclass(frozen=True)
class AllocationTarget:
    """Immutable target allocation for a policy decision."""

    weights: dict[AssetClass, Decimal]

    def __post_init__(self) -> None:
        total = sum(self.weights.values())
        if total != Decimal("1"):
            raise ValueError("AllocationTarget weights must sum to 1.00")
        if any(value < Decimal("0") for value in self.weights.values()):
            raise ValueError("AllocationTarget weights must not be negative")

    def __getitem__(self, asset_class: AssetClass) -> Decimal:
        return self.weights[asset_class]
