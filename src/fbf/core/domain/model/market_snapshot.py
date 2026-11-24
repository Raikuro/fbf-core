"""Market snapshot model for the Engine domain.

Contains the immutable MarketSnapshot object used by simulations.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Any

from .asset import AssetClass


@dataclass(frozen=True)
class MarketSnapshot:
    """Immutable market snapshot for a single period."""

    date: date
    index_levels: Mapping[AssetClass, Decimal]
    inflation: Decimal
    inflation_cumulative: Decimal
    # ATH/underwater based on CPI-adjusted real total-return equity index
    is_ath: bool
    is_underwater: bool
    running_ath: Decimal
    cape: Decimal | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "index_levels", MappingProxyType(dict(self.index_levels))
        )
        if self.date is None:
            raise ValueError("MarketSnapshot date must be set")
        if not isinstance(self.date, date) or isinstance(self.date, datetime):
            raise TypeError("MarketSnapshot date must be a date")
        for key, value in self.index_levels.items():
            if not isinstance(key, AssetClass):
                raise TypeError(
                    "MarketSnapshot index_levels keys must be AssetClass"
                )
            if value is None:
                raise ValueError(
                    "MarketSnapshot index_levels must not contain None"
                )
            if not isinstance(value, Decimal):
                raise TypeError(
                    "MarketSnapshot index_levels values must be Decimal"
                )
            if not value.is_finite():
                raise ValueError(
                    "MarketSnapshot index_levels values must be finite"
                )
            if value < 0:
                raise ValueError(
                    "MarketSnapshot index_levels values must be non-negative"
                )
        for field_name, value in (
            ("inflation", self.inflation),
            ("inflation_cumulative", self.inflation_cumulative),
            ("running_ath", self.running_ath),
        ):
            if not isinstance(value, Decimal):
                raise TypeError(
                    f"MarketSnapshot {field_name} must be a Decimal"
                )
            if not value.is_finite():
                raise ValueError(
                    f"MarketSnapshot {field_name} must be finite"
                )
        if not isinstance(self.is_ath, bool):
            raise TypeError("MarketSnapshot is_ath must be a bool")
        if not isinstance(self.is_underwater, bool):
            raise TypeError("MarketSnapshot is_underwater must be a bool")
        if self.cape is not None:
            if not isinstance(self.cape, Decimal):
                raise TypeError(
                    "MarketSnapshot cape must be a Decimal or None"
                )
            if not self.cape.is_finite():
                raise ValueError("MarketSnapshot cape must be finite")

    def __getstate__(self) -> dict[str, Any]:
        state = {
            field.name: getattr(self, field.name)
            for field in fields(self)
            if field.init
        }
        state["index_levels"] = dict(self.index_levels)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        type(self).__init__(self, **state)
