from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Sequence


@dataclass(frozen=True)
class AssetClass:
    """Immutable identifier for a financial asset category.

    Responsibilities:
    - represent the identity of an asset class used by the simulator
    - carry stable metadata for the asset class

    Invariants:
    - id is unique within a Dataset
    """

    id: str
    name: str
    description: str


@dataclass(frozen=True)
class AssetSeries:
    """Immutable historical series for a single AssetClass.

    Responsibilities:
    - represent the ordered time series for one asset class
    - expose metadata used by Dataset construction

    Invariants:
    - dates are strictly ordered
    - values correspond to Total Return index levels
    """

    asset_class: AssetClass
    dates: Sequence[date]
    values: Sequence[Decimal]
    inflation: Sequence[Decimal] | None = None
