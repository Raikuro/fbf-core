from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from .asset import AssetSeries


@dataclass(frozen=True)
class Dataset:
    """Immutable historical dataset used by the Engine.

    Responsibilities:
    - contain asset series metadata and values
    - provide range and version information

    Invariants:
    - asset_series is non-empty
    - start_date and end_date are determined by the series data
    """

    asset_series: Sequence[AssetSeries]
    start_date: date
    end_date: date
    frequency: str
    version: str
