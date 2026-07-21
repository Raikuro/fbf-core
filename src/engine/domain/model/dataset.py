"""Dataset model objects for the Engine domain.

Contains the immutable Dataset aggregate used by simulations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterator, Sequence

from .market_snapshot import MarketSnapshot


@dataclass(frozen=True)
class Dataset:
    """Immutable historical dataset used by the Engine."""

    snapshots: Sequence[MarketSnapshot]
    frequency: str
    version: str

    def __post_init__(self) -> None:
        if not self.snapshots:
            raise ValueError("Dataset must contain at least one MarketSnapshot")
        dates = [snapshot.date for snapshot in self.snapshots]
        if dates != sorted(dates):
            raise ValueError("Dataset snapshots must be ordered by date")
        if len(set(dates)) != len(dates):
            raise ValueError("Dataset snapshots must have unique dates")

    def __len__(self) -> int:
        return len(self.snapshots)

    def __getitem__(self, index: int) -> MarketSnapshot:
        return self.snapshots[index]

    def __iter__(self) -> Iterator[MarketSnapshot]:
        return iter(self.snapshots)

    @property
    def start_date(self) -> date:
        return self.snapshots[0].date

    @property
    def end_date(self) -> date:
        return self.snapshots[-1].date
