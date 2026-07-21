"""Asset model objects for the Engine domain.

Contains asset class and series domain objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Sequence


@dataclass(frozen=True)
class AssetClass:
    """Immutable identifier for a financial asset category."""

    id: str
    name: str
    description: str


@dataclass(frozen=True)
class AssetSeries:
    """Immutable historical series for a single AssetClass."""

    asset_class: AssetClass
    dates: Sequence[date]
    values: Sequence[Decimal]
    inflation: Sequence[Decimal] | None = None
