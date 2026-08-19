"""Market snapshot model for the Engine domain.

Contains the immutable MarketSnapshot object used by simulations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .asset import AssetClass


@dataclass(frozen=True)
class MarketSnapshot:
    """Immutable market snapshot for a single period."""

    date: date
    index_levels: dict[AssetClass, Decimal]
    inflation: Decimal
    inflation_cumulative: Decimal
    is_ath: bool
    is_underwater: bool
    running_ath: Decimal

    def __post_init__(self) -> None:
        if self.date is None:
            raise ValueError("MarketSnapshot date must be set")
        if any(value is None for value in self.index_levels.values()):
            raise ValueError("MarketSnapshot index_levels must not contain None")
