from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Sequence

from .asset import AssetClass


@dataclass
class AssetHolding:
    """Mutable holding value for a specific AssetClass.

    Responsibilities:
    - represent the euro value invested in a single asset class

    Invariants:
    - value is never negative
    """

    asset_class: AssetClass
    value: Decimal


@dataclass(frozen=True)
class Portfolio:
    """Immutable portfolio snapshot representing asset holdings.

    Responsibilities:
    - represent the state of holdings at a specific instant
    - preserve the invariant that total value equals the sum of holdings

    Invariants:
    - holdings are non-empty
    - total_value equals the sum of all AssetHolding values
    """

    holdings: Sequence[AssetHolding]
    total_value: Decimal
    allocation: Mapping[AssetClass, Decimal]
