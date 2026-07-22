"""CohortGenerator utility for the Research domain.

Generates chronologically ordered, horizon-feasible CohortSpecification
sequences from historical Dataset snapshots.
"""

from __future__ import annotations

from datetime import date
from typing import Sequence

from engine.domain.model.dataset import Dataset

from research.domain.cohort.specification import CohortSpecification


class CohortGenerator:
    """Stateless utility for generating horizon-feasible CohortSpecification sequences.

    Translates historical Dataset snapshots and a simulation horizon into
    chronologically ordered, validated CohortSpecification tuples.

    All methods are @staticmethod. This class is never instantiated.

    Output guarantees (all strategies):
        - Ordering:    Results are sorted by start_date in strict ascending order,
                       regardless of input ordering or generation strategy.
        - Uniqueness:  No two returned CohortSpecification objects share the same
                       start_date (canonical identity). Uniqueness is evaluated
                       strictly by start_date; the external id plays no role.
        - Feasibility: Every returned cohort has at least horizon_months of
                       remaining dataset history.
        - Immutability: The returned tuple and its CohortSpecification elements
                        are immutable.
    """

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_common(dataset: Dataset | None, horizon_months: int) -> None:
        """Validate arguments shared by all generation strategies.

        Raises:
            ValueError: If dataset is None, empty, horizon_months <= 0, or the
                        dataset contains fewer snapshots than horizon_months.
        """
        if dataset is None:
            raise ValueError("CohortGenerator dataset cannot be None.")
        if len(dataset.snapshots) == 0:
            raise ValueError("CohortGenerator dataset contains no snapshots.")
        if horizon_months <= 0:
            raise ValueError(
                "CohortGenerator horizon_months must be positive (> 0)."
            )
        if len(dataset.snapshots) < horizon_months:
            raise ValueError(
                f"CohortGenerator dataset is shorter than horizon_months "
                f"({len(dataset.snapshots)} snapshots < {horizon_months} months)."
            )

    @staticmethod
    def _is_feasible(index: int, total_snapshots: int, horizon_months: int) -> bool:
        """Return True if the snapshot at `index` has sufficient remaining history."""
        return (total_snapshots - index) >= horizon_months

    # ------------------------------------------------------------------
    # Public strategies
    # ------------------------------------------------------------------

    @staticmethod
    def generate_rolling_monthly(
        dataset: Dataset,
        horizon_months: int,
    ) -> tuple[CohortSpecification, ...]:
        """Generate all horizon-feasible cohorts from the full dataset history.

        Scans dataset.snapshots from the first to the last snapshot date.
        A snapshot at index i is included if and only if:

            len(dataset.snapshots) - i >= horizon_months

        Tail snapshots that cannot satisfy horizon_months are silently excluded.
        No error is raised when tail windows are infeasible.

        Args:
            dataset:        Valid non-null Dataset containing market snapshots.
            horizon_months: Strictly positive integer simulation horizon (> 0).

        Returns:
            Chronologically ordered (ascending start_date) tuple of
            CohortSpecification instances, one per feasible snapshot date.

        Raises:
            ValueError: If dataset is None.
            ValueError: If dataset contains zero snapshots.
            ValueError: If horizon_months <= 0.
            ValueError: If len(dataset.snapshots) < horizon_months.
        """
        CohortGenerator._validate_common(dataset, horizon_months)

        total = len(dataset.snapshots)
        cohorts = [
            CohortSpecification(start_date=snapshot.date)
            for i, snapshot in enumerate(dataset.snapshots)
            if CohortGenerator._is_feasible(i, total, horizon_months)
        ]

        return tuple(sorted(cohorts, key=lambda c: c.start_date))

    @staticmethod
    def generate_range(
        dataset: Dataset,
        horizon_months: int,
        start_date: date,
        end_date: date,
    ) -> tuple[CohortSpecification, ...]:
        """Generate feasible cohorts within the closed interval [start_date, end_date].

        Considers only snapshot dates D where start_date <= D <= end_date.
        Within that range, a snapshot at index i is included if and only if:

            len(dataset.snapshots) - i >= horizon_months

        Tail dates inside the range that cannot satisfy horizon_months are silently
        excluded. No error is raised for infeasible tail windows within the range.

        Args:
            dataset:        Valid non-null Dataset containing market snapshots.
            horizon_months: Strictly positive integer simulation horizon (> 0).
            start_date:     Inclusive lower bound of the cohort date range.
            end_date:       Inclusive upper bound of the cohort date range.

        Returns:
            Chronologically ordered (ascending start_date) tuple of
            CohortSpecification instances for feasible snapshot dates
            within [start_date, end_date].

        Raises:
            ValueError: If dataset is None.
            ValueError: If dataset contains zero snapshots.
            ValueError: If horizon_months <= 0.
            ValueError: If len(dataset.snapshots) < horizon_months.
            ValueError: If start_date > end_date.
            ValueError: If no snapshots in [start_date, end_date] satisfy horizon_months.
        """
        CohortGenerator._validate_common(dataset, horizon_months)

        if start_date > end_date:
            raise ValueError(
                f"CohortGenerator start_date must not be after end_date "
                f"({start_date} > {end_date})."
            )

        total = len(dataset.snapshots)
        cohorts = [
            CohortSpecification(start_date=snapshot.date)
            for i, snapshot in enumerate(dataset.snapshots)
            if start_date <= snapshot.date <= end_date
            and CohortGenerator._is_feasible(i, total, horizon_months)
        ]

        if not cohorts:
            raise ValueError(
                f"CohortGenerator no feasible cohorts found in requested range "
                f"[{start_date}, {end_date}] for horizon_months={horizon_months}."
            )

        return tuple(sorted(cohorts, key=lambda c: c.start_date))

    @staticmethod
    def from_start_dates(
        dataset: Dataset,
        horizon_months: int,
        start_dates: Sequence[date],
    ) -> tuple[CohortSpecification, ...]:
        """Generate CohortSpecifications for an explicit sequence of start dates.

        Every date in start_dates is strictly validated. Fail-fast semantics apply:
        if any requested date is missing from the dataset or has insufficient
        remaining history, a ValueError is raised immediately.

        This method is intended for reproducibility and exact-cohort use cases
        where partial results would corrupt a study's reproducibility contract.

        Duplicate dates in start_dates are deduplicated before validation,
        preserving the uniqueness output guarantee.

        Args:
            dataset:        Valid non-null Dataset containing market snapshots.
            horizon_months: Strictly positive integer simulation horizon (> 0).
            start_dates:    Non-empty sequence of explicitly requested start dates.

        Returns:
            Chronologically ordered (ascending start_date) tuple of
            CohortSpecification instances, one per unique requested date.

        Raises:
            ValueError: If dataset is None.
            ValueError: If dataset contains zero snapshots.
            ValueError: If horizon_months <= 0.
            ValueError: If len(dataset.snapshots) < horizon_months.
            ValueError: If start_dates is empty.
            ValueError: If any requested date does not exist in dataset.snapshots.
            ValueError: If any requested date exists but has fewer than
                        horizon_months remaining snapshots to dataset end.
        """
        CohortGenerator._validate_common(dataset, horizon_months)

        if not start_dates:
            raise ValueError("CohortGenerator start_dates cannot be empty.")

        # Build index: date -> position for O(1) lookup and feasibility check
        date_to_index: dict[date, int] = {
            snapshot.date: i for i, snapshot in enumerate(dataset.snapshots)
        }
        total = len(dataset.snapshots)

        # Deduplicate to satisfy the uniqueness output guarantee.
        # dict.fromkeys retains first occurrence and preserves insertion order
        # (Python 3.7+ language guarantee), but that order is irrelevant here:
        # the final sort unconditionally imposes chronological ordering by
        # start_date, which takes precedence over any input ordering.
        unique_dates = dict.fromkeys(start_dates)

        cohorts: list[CohortSpecification] = []
        for requested_date in unique_dates:
            if requested_date not in date_to_index:
                raise ValueError(
                    f"CohortGenerator requested date {requested_date} not found "
                    f"in dataset."
                )
            idx = date_to_index[requested_date]
            if not CohortGenerator._is_feasible(idx, total, horizon_months):
                raise ValueError(
                    f"CohortGenerator requested date {requested_date} has "
                    f"insufficient remaining horizon "
                    f"({total - idx} snapshots remaining, {horizon_months} required)."
                )
            cohorts.append(CohortSpecification(start_date=requested_date))

        return tuple(sorted(cohorts, key=lambda c: c.start_date))
