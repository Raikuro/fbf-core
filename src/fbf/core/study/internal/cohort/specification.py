"""CohortSpecification value object for the Research package."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CohortSpecification:
    """Immutable value object representing the specification of a single historical cohort window.

    Attributes:
        start_date: The canonical start date of the cohort (used for chronological ordering).
        id: Optional external identifier for reporting, serialization, and references.
    """

    start_date: date
    id: str | None = None

    def __post_init__(self) -> None:
        """Validates cohort invariants and generates default ID if omitted."""
        if self.start_date is None:
            raise ValueError("CohortSpecification start_date cannot be None.")
        if not isinstance(self.start_date, date):
            raise TypeError("CohortSpecification start_date must be a datetime.date instance.")

        if self.id is None:
            object.__setattr__(self, "id", self.start_date.isoformat())
        elif not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("CohortSpecification id cannot be empty or whitespace.")
        else:
            object.__setattr__(self, "id", self.id.strip())
