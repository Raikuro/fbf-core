"""Dataset model objects for the Engine domain.

Contains the immutable Dataset aggregate used by simulations.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date

from .market_snapshot import MarketSnapshot


@dataclass(frozen=True)
class Dataset:
    """Immutable historical dataset used by the Engine."""

    snapshots: Sequence[MarketSnapshot]
    frequency: str
    version: str
    identifier: str | None = None

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

    def slice(self, start_date: date, horizon_months: int) -> Dataset:
        """Return a sliced sub-Dataset starting at *start_date* for *horizon_months*.

        Parameters
        ----------
        start_date:
            The date of the first MarketSnapshot in the sliced dataset.
        horizon_months:
            The exact number of monthly snapshots required.

        Returns
        -------
        Dataset
            A new immutable Dataset containing snapshots from start_date up to
            start_date + horizon_months.

        Raises
        ------
        ValueError:
            If start_date is not present in the dataset, if horizon_months is not positive,
            or if there are insufficient snapshots available.
        """
        if start_date is None or not isinstance(start_date, date):
            raise ValueError("start_date must be a valid date")
        if (
            horizon_months is None
            or not isinstance(horizon_months, int)
            or isinstance(horizon_months, bool)
            or horizon_months <= 0
        ):
            raise ValueError("horizon_months must be a positive integer (> 0)")

        start_idx: int | None = None
        for i, snapshot in enumerate(self.snapshots):
            if snapshot.date == start_date:
                start_idx = i
                break

        if start_idx is None:
            raise ValueError(f"Start date {start_date.isoformat()!r} not found in dataset")

        if start_idx + horizon_months > len(self.snapshots):
            avail = len(self.snapshots) - start_idx
            raise ValueError(
                f"Insufficient dataset history starting from {start_date.isoformat()!r} "
                f"for horizon_months={horizon_months} (available: {avail})"
            )

        sliced_snapshots = tuple(self.snapshots[start_idx : start_idx + horizon_months])
        return Dataset(
            snapshots=sliced_snapshots,
            frequency=self.frequency,
            version=self.version,
            identifier=self.identifier,
        )

