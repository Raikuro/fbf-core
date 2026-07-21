"""Portfolio model objects for the Engine domain.

Contains portfolio holdings definitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from .asset import AssetClass


@dataclass(frozen=True)
class AssetHolding:
    """Immutable ownership position for a specific AssetClass."""

    asset_class: AssetClass
    units: Decimal


@dataclass(frozen=True)
class Portfolio:
    """Immutable portfolio snapshot representing asset ownership."""

    holdings: Sequence[AssetHolding]

    def __post_init__(self) -> None:
        if any(holding.units < Decimal("0") for holding in self.holdings):
            raise ValueError("AssetHolding units must not be negative")
