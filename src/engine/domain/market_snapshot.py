from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Mapping

from .asset import AssetClass


@dataclass(frozen=True)
class MarketSnapshot:
    """Immutable market snapshot for a single period.

    Responsibilities:
    - represent market state for one simulation period
    - expose data derived from historical asset series

    Invariants:
    - contains values for every AssetClass in the Dataset
    - current_date corresponds to the snapshot period
    """

    date: date
    returns: Mapping[AssetClass, Decimal]
    total_return_index: Mapping[AssetClass, Decimal]
    inflation: Decimal
    inflation_cumulative: Decimal
    is_ath: bool
    is_underwater: bool
    running_ath: Decimal
