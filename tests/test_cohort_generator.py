"""Unit tests for CohortGenerator temporal windowing utility.

Covers all three generation strategies, all validation/fail-fast rules,
and the frozen output guarantees (ordering, uniqueness, feasibility,
immutability, determinism).
"""

from datetime import date
from decimal import Decimal

import pytest

from engine.domain import AssetClass, Dataset, MarketSnapshot
from research import CohortGenerator, CohortSpecification


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_snapshot(d: date) -> MarketSnapshot:
    """Construct a minimal valid MarketSnapshot for the given date."""
    asset = AssetClass(id="acwi", name="ACWI", description="Global equities")
    return MarketSnapshot(
        date=d,
        index_levels={asset: Decimal("100.00")},
        inflation=Decimal("0.00"),
        inflation_cumulative=Decimal("0.00"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100.00"),
    )


def _make_dataset(num_months: int, start_year: int = 1871) -> Dataset:
    """Construct a Dataset with `num_months` monthly snapshots starting from start_year-01-01.

    Months are produced by incrementing month-by-month from the given start.
    """
    snapshots = []
    year = start_year
    month = 1
    for _ in range(num_months):
        snapshots.append(_make_snapshot(date(year, month, 1)))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return Dataset(snapshots=snapshots, frequency="monthly", version="1.0")


@pytest.fixture
def dataset_100() -> Dataset:
    """Dataset with 100 monthly snapshots starting 1871-01."""
    return _make_dataset(100)


@pytest.fixture
def dataset_5() -> Dataset:
    """Small dataset with 5 monthly snapshots starting 1871-01."""
    return _make_dataset(5)


# ---------------------------------------------------------------------------
# Common validation tests (shared by all strategies)
# ---------------------------------------------------------------------------


class TestCommonValidation:
    """Validation rules shared across all three generation strategies."""

    def test_none_dataset_rolling(self) -> None:
        with pytest.raises(ValueError, match="dataset cannot be None"):
            CohortGenerator.generate_rolling_monthly(None, 12)  # type: ignore[arg-type]

    def test_none_dataset_range(self) -> None:
        with pytest.raises(ValueError, match="dataset cannot be None"):
            CohortGenerator.generate_range(
                None, 12, date(1871, 1, 1), date(1880, 1, 1)  # type: ignore[arg-type]
            )

    def test_none_dataset_from_start_dates(self) -> None:
        with pytest.raises(ValueError, match="dataset cannot be None"):
            CohortGenerator.from_start_dates(
                None, 12, [date(1871, 1, 1)]  # type: ignore[arg-type]
            )

    def test_zero_horizon_rolling(self, dataset_100: Dataset) -> None:
        with pytest.raises(ValueError, match="horizon_months must be positive"):
            CohortGenerator.generate_rolling_monthly(dataset_100, 0)

    def test_negative_horizon_range(self, dataset_100: Dataset) -> None:
        with pytest.raises(ValueError, match="horizon_months must be positive"):
            CohortGenerator.generate_range(
                dataset_100, -1, date(1871, 1, 1), date(1880, 1, 1)
            )

    def test_negative_horizon_from_start_dates(self, dataset_100: Dataset) -> None:
        with pytest.raises(ValueError, match="horizon_months must be positive"):
            CohortGenerator.from_start_dates(
                dataset_100, -5, [date(1871, 1, 1)]
            )

    def test_dataset_shorter_than_horizon_rolling(self, dataset_5: Dataset) -> None:
        with pytest.raises(ValueError, match="dataset is shorter than horizon_months"):
            CohortGenerator.generate_rolling_monthly(dataset_5, 10)

    def test_dataset_shorter_than_horizon_range(self, dataset_5: Dataset) -> None:
        with pytest.raises(ValueError, match="dataset is shorter than horizon_months"):
            CohortGenerator.generate_range(
                dataset_5, 10, date(1871, 1, 1), date(1880, 1, 1)
            )

    def test_dataset_shorter_than_horizon_from_start_dates(self, dataset_5: Dataset) -> None:
        with pytest.raises(ValueError, match="dataset is shorter than horizon_months"):
            CohortGenerator.from_start_dates(
                dataset_5, 10, [date(1871, 1, 1)]
            )


# ---------------------------------------------------------------------------
# generate_rolling_monthly tests
# ---------------------------------------------------------------------------


class TestGenerateRollingMonthly:
    """Tests for the rolling monthly generation strategy."""

    def test_correct_count_100_snapshots_horizon_36(self, dataset_100: Dataset) -> None:
        """100 snapshots with horizon=36 should yield exactly 65 cohorts."""
        cohorts = CohortGenerator.generate_rolling_monthly(dataset_100, 36)
        assert len(cohorts) == 65

    def test_correct_count_exact_horizon_equals_dataset(self, dataset_5: Dataset) -> None:
        """Dataset of 5 snapshots with horizon=5 yields exactly 1 cohort."""
        cohorts = CohortGenerator.generate_rolling_monthly(dataset_5, 5)
        assert len(cohorts) == 1
        assert cohorts[0].start_date == date(1871, 1, 1)

    def test_correct_count_horizon_1(self, dataset_100: Dataset) -> None:
        """With horizon=1, every snapshot is feasible → 100 cohorts."""
        cohorts = CohortGenerator.generate_rolling_monthly(dataset_100, 1)
        assert len(cohorts) == 100

    def test_returns_tuple(self, dataset_100: Dataset) -> None:
        cohorts = CohortGenerator.generate_rolling_monthly(dataset_100, 36)
        assert isinstance(cohorts, tuple)

    def test_elements_are_cohort_specifications(self, dataset_100: Dataset) -> None:
        cohorts = CohortGenerator.generate_rolling_monthly(dataset_100, 36)
        assert all(isinstance(c, CohortSpecification) for c in cohorts)

    def test_ordering_guarantee(self, dataset_100: Dataset) -> None:
        """Result must be sorted by start_date ascending regardless of strategy."""
        cohorts = CohortGenerator.generate_rolling_monthly(dataset_100, 36)
        dates = [c.start_date for c in cohorts]
        assert dates == sorted(dates), "Cohorts must be in ascending start_date order"

    def test_first_cohort_is_dataset_start(self, dataset_100: Dataset) -> None:
        cohorts = CohortGenerator.generate_rolling_monthly(dataset_100, 36)
        assert cohorts[0].start_date == dataset_100.snapshots[0].date

    def test_last_cohort_is_feasible(self, dataset_100: Dataset) -> None:
        """The last returned cohort must have >= horizon_months remaining snapshots."""
        horizon = 36
        cohorts = CohortGenerator.generate_rolling_monthly(dataset_100, horizon)
        last_date = cohorts[-1].start_date
        snapshot_dates = [s.date for s in dataset_100.snapshots]
        last_index = snapshot_dates.index(last_date)
        remaining = len(dataset_100.snapshots) - last_index
        assert remaining >= horizon

    def test_tail_snapshots_silently_excluded(self, dataset_100: Dataset) -> None:
        """Dates after the last feasible cohort must not appear in the result."""
        horizon = 36
        cohorts = CohortGenerator.generate_rolling_monthly(dataset_100, horizon)
        last_feasible_date = cohorts[-1].start_date
        snapshot_dates = [s.date for s in dataset_100.snapshots]
        last_feasible_index = snapshot_dates.index(last_feasible_date)
        # Snapshots after the last feasible index should not be in cohorts
        infeasible_dates = {
            s.date
            for i, s in enumerate(dataset_100.snapshots)
            if i > last_feasible_index
        }
        returned_dates = {c.start_date for c in cohorts}
        assert infeasible_dates.isdisjoint(returned_dates)

    def test_no_duplicate_start_dates(self, dataset_100: Dataset) -> None:
        """Uniqueness guarantee: no two cohorts share the same start_date."""
        cohorts = CohortGenerator.generate_rolling_monthly(dataset_100, 36)
        start_dates = [c.start_date for c in cohorts]
        assert len(start_dates) == len(set(start_dates))

    def test_default_id_equals_isoformat(self, dataset_100: Dataset) -> None:
        """CohortGenerator must not inject custom ids; default isoformat applies."""
        cohorts = CohortGenerator.generate_rolling_monthly(dataset_100, 1)
        for c in cohorts:
            assert c.id == c.start_date.isoformat()

    def test_no_error_when_entire_dataset_is_horizon(self, dataset_5: Dataset) -> None:
        """No error when dataset length == horizon_months (exactly 1 feasible cohort)."""
        cohorts = CohortGenerator.generate_rolling_monthly(dataset_5, 5)
        assert len(cohorts) == 1

    def test_determinism(self, dataset_100: Dataset) -> None:
        """Two calls with identical inputs must return identical results."""
        first = CohortGenerator.generate_rolling_monthly(dataset_100, 36)
        second = CohortGenerator.generate_rolling_monthly(dataset_100, 36)
        assert first == second


# ---------------------------------------------------------------------------
# generate_range tests
# ---------------------------------------------------------------------------


class TestGenerateRange:
    """Tests for the range-bounded generation strategy."""

    def test_valid_range_returns_expected_cohorts(self, dataset_100: Dataset) -> None:
        """Cohorts within a valid range containing feasible windows are returned."""
        # dataset_100 runs 1871-01 to 1879-04 (100 months).
        # horizon=12: feasible up to index 88 (1879-04 - 11 months = 1878-05).
        start = date(1872, 1, 1)
        end = date(1873, 12, 1)
        cohorts = CohortGenerator.generate_range(dataset_100, 12, start, end)
        assert len(cohorts) > 0
        assert all(start <= c.start_date <= end for c in cohorts)

    def test_ordering_guarantee(self, dataset_100: Dataset) -> None:
        """Result must be sorted by start_date ascending."""
        cohorts = CohortGenerator.generate_range(
            dataset_100, 12, date(1871, 1, 1), date(1875, 12, 1)
        )
        dates = [c.start_date for c in cohorts]
        assert dates == sorted(dates)

    def test_no_duplicate_start_dates(self, dataset_100: Dataset) -> None:
        """Uniqueness guarantee: no two cohorts share the same start_date."""
        cohorts = CohortGenerator.generate_range(
            dataset_100, 12, date(1871, 1, 1), date(1876, 1, 1)
        )
        start_dates = [c.start_date for c in cohorts]
        assert len(start_dates) == len(set(start_dates))

    def test_returns_tuple(self, dataset_100: Dataset) -> None:
        cohorts = CohortGenerator.generate_range(
            dataset_100, 12, date(1871, 1, 1), date(1873, 1, 1)
        )
        assert isinstance(cohorts, tuple)

    def test_boundary_dates_inclusive(self, dataset_100: Dataset) -> None:
        """start_date and end_date boundaries are inclusive."""
        snapshot_dates = [s.date for s in dataset_100.snapshots]
        first_date = snapshot_dates[0]
        # Use a range of exactly 1 month containing the first snapshot
        cohorts = CohortGenerator.generate_range(
            dataset_100, 1, first_date, first_date
        )
        assert len(cohorts) == 1
        assert cohorts[0].start_date == first_date

    def test_raises_when_start_date_after_end_date(self, dataset_100: Dataset) -> None:
        with pytest.raises(ValueError, match="start_date must not be after end_date"):
            CohortGenerator.generate_range(
                dataset_100, 12, date(1875, 1, 1), date(1872, 1, 1)
            )

    def test_raises_when_no_feasible_cohorts_in_range(self, dataset_100: Dataset) -> None:
        """Range entirely in the infeasible tail raises ValueError."""
        # dataset_100 has 100 snapshots; with horizon=36, indices 65-99 are infeasible.
        # Last snapshot is at index 99 → its date is in the infeasible region.
        last_date = dataset_100.snapshots[-1].date
        with pytest.raises(ValueError, match="no feasible cohorts found in requested range"):
            CohortGenerator.generate_range(
                dataset_100, 36, last_date, last_date
            )

    def test_infeasible_tail_silently_excluded_within_range(self, dataset_100: Dataset) -> None:
        """Infeasible tail dates inside the range are excluded without error.

        The 100-snapshot dataset with horizon=36 has its last feasible cohort
        at index 64 (1876-05-01). Snapshots at index 65+ are infeasible.
        A range that spans the boundary [1875-01-01, last_snapshot] should
        return only the feasible cohorts within it, silently dropping the tail.
        """
        horizon = 36
        # Start well before the feasibility boundary (index 64 = 1876-05-01)
        start = date(1875, 1, 1)
        end = dataset_100.snapshots[-1].date  # 1879-04-01, in infeasible tail
        cohorts = CohortGenerator.generate_range(dataset_100, horizon, start, end)
        # Feasible cohorts must be returned (no ValueError)
        assert len(cohorts) > 0
        # The last snapshot date must NOT appear in the result (it is infeasible)
        assert all(c.start_date != dataset_100.snapshots[-1].date for c in cohorts)
        # All returned cohorts must be within the requested range
        assert all(start <= c.start_date <= end for c in cohorts)

    def test_equal_start_end_date_feasible(self, dataset_5: Dataset) -> None:
        """A range of one date that is feasible returns exactly one cohort."""
        # dataset_5 has 5 snapshots with horizon=5: only index 0 is feasible.
        first_date = dataset_5.snapshots[0].date
        cohorts = CohortGenerator.generate_range(dataset_5, 5, first_date, first_date)
        assert len(cohorts) == 1
        assert cohorts[0].start_date == first_date

    def test_determinism(self, dataset_100: Dataset) -> None:
        """Two calls with identical inputs must return identical results."""
        first = CohortGenerator.generate_range(
            dataset_100, 12, date(1872, 1, 1), date(1874, 12, 1)
        )
        second = CohortGenerator.generate_range(
            dataset_100, 12, date(1872, 1, 1), date(1874, 12, 1)
        )
        assert first == second


# ---------------------------------------------------------------------------
# from_start_dates tests
# ---------------------------------------------------------------------------


class TestFromStartDates:
    """Tests for the explicit date windowing strategy."""

    def test_valid_explicit_dates_produce_cohorts(self, dataset_100: Dataset) -> None:
        """Valid dates with sufficient horizon produce CohortSpecification objects."""
        # First two snapshots of dataset_100 are always feasible with horizon=1
        d1 = dataset_100.snapshots[0].date
        d2 = dataset_100.snapshots[1].date
        cohorts = CohortGenerator.from_start_dates(dataset_100, 1, [d1, d2])
        assert len(cohorts) == 2
        assert cohorts[0].start_date == d1
        assert cohorts[1].start_date == d2

    def test_ordering_guarantee_regardless_of_input_order(self, dataset_100: Dataset) -> None:
        """Result is ordered by start_date ascending even if input is descending."""
        d1 = dataset_100.snapshots[0].date  # earliest
        d2 = dataset_100.snapshots[5].date  # later
        d3 = dataset_100.snapshots[10].date  # latest

        # Supply in reverse order
        cohorts = CohortGenerator.from_start_dates(dataset_100, 1, [d3, d1, d2])
        dates = [c.start_date for c in cohorts]
        assert dates == sorted(dates)
        assert dates == [d1, d2, d3]

    def test_no_duplicate_start_dates_when_input_has_duplicates(
        self, dataset_100: Dataset
    ) -> None:
        """Duplicate input dates are deduplicated; uniqueness guarantee is preserved."""
        d = dataset_100.snapshots[0].date
        cohorts = CohortGenerator.from_start_dates(dataset_100, 1, [d, d, d])
        assert len(cohorts) == 1
        assert cohorts[0].start_date == d

    def test_returns_tuple(self, dataset_100: Dataset) -> None:
        d = dataset_100.snapshots[0].date
        cohorts = CohortGenerator.from_start_dates(dataset_100, 1, [d])
        assert isinstance(cohorts, tuple)

    def test_single_valid_date(self, dataset_100: Dataset) -> None:
        d = dataset_100.snapshots[0].date
        cohorts = CohortGenerator.from_start_dates(dataset_100, 36, [d])
        assert len(cohorts) == 1
        assert cohorts[0].start_date == d

    def test_raises_when_start_dates_empty(self, dataset_100: Dataset) -> None:
        with pytest.raises(ValueError, match="start_dates cannot be empty"):
            CohortGenerator.from_start_dates(dataset_100, 12, [])

    def test_raises_when_date_missing_from_dataset(self, dataset_100: Dataset) -> None:
        """A date not present in the dataset raises ValueError immediately."""
        missing_date = date(2099, 1, 1)
        with pytest.raises(ValueError, match="not found in dataset"):
            CohortGenerator.from_start_dates(dataset_100, 12, [missing_date])

    def test_raises_when_date_has_insufficient_horizon(self, dataset_100: Dataset) -> None:
        """A date in the infeasible tail raises ValueError."""
        # The very last snapshot (index 99) cannot satisfy horizon=36
        # because only 1 snapshot remains.
        last_date = dataset_100.snapshots[-1].date
        with pytest.raises(ValueError, match="insufficient remaining horizon"):
            CohortGenerator.from_start_dates(dataset_100, 36, [last_date])

    def test_fails_fast_on_first_invalid_date(self, dataset_100: Dataset) -> None:
        """ValueError is raised as soon as an invalid date is encountered."""
        valid_date = dataset_100.snapshots[0].date
        missing_date = date(2099, 6, 1)
        with pytest.raises(ValueError, match="not found in dataset"):
            CohortGenerator.from_start_dates(
                dataset_100, 1, [valid_date, missing_date]
            )

    def test_fails_fast_on_first_infeasible_date(self, dataset_100: Dataset) -> None:
        """ValueError is raised for the first infeasible date, even if others are valid."""
        valid_date = dataset_100.snapshots[0].date
        infeasible_date = dataset_100.snapshots[-1].date  # last snapshot, insufficient horizon
        with pytest.raises(ValueError, match="insufficient remaining horizon"):
            CohortGenerator.from_start_dates(
                dataset_100, 36, [valid_date, infeasible_date]
            )

    def test_default_id_equals_isoformat(self, dataset_100: Dataset) -> None:
        """CohortGenerator must not inject custom ids; default isoformat applies."""
        d = dataset_100.snapshots[0].date
        cohorts = CohortGenerator.from_start_dates(dataset_100, 1, [d])
        assert cohorts[0].id == d.isoformat()

    def test_determinism(self, dataset_100: Dataset) -> None:
        """Two calls with identical inputs must return identical results."""
        dates = [dataset_100.snapshots[i].date for i in range(5)]
        first = CohortGenerator.from_start_dates(dataset_100, 1, dates)
        second = CohortGenerator.from_start_dates(dataset_100, 1, dates)
        assert first == second

    def test_three_canonical_study_cohorts(self, dataset_100: Dataset) -> None:
        """Multiple valid explicit cohorts are returned correctly in order."""
        snapshot_dates = [s.date for s in dataset_100.snapshots]
        # Pick indices 0, 10, 20 — all feasible with horizon=36
        d0 = snapshot_dates[0]
        d10 = snapshot_dates[10]
        d20 = snapshot_dates[20]
        cohorts = CohortGenerator.from_start_dates(dataset_100, 36, [d20, d0, d10])
        assert [c.start_date for c in cohorts] == [d0, d10, d20]


# ---------------------------------------------------------------------------
# Cross-strategy output guarantee tests
# ---------------------------------------------------------------------------


class TestOutputGuarantees:
    """Verify that the frozen output guarantees hold across all strategies."""

    def test_all_strategies_return_immutable_tuple(self, dataset_100: Dataset) -> None:
        snap_dates = [s.date for s in dataset_100.snapshots]
        rolling = CohortGenerator.generate_rolling_monthly(dataset_100, 12)
        ranged = CohortGenerator.generate_range(
            dataset_100, 12, snap_dates[0], snap_dates[10]
        )
        explicit = CohortGenerator.from_start_dates(dataset_100, 12, [snap_dates[0]])
        for result in (rolling, ranged, explicit):
            assert isinstance(result, tuple)

    def test_all_strategies_elements_are_frozen_dataclasses(
        self, dataset_100: Dataset
    ) -> None:
        from dataclasses import FrozenInstanceError

        snap_dates = [s.date for s in dataset_100.snapshots]
        cohorts = CohortGenerator.generate_rolling_monthly(dataset_100, 12)
        with pytest.raises(FrozenInstanceError):
            cohorts[0].start_date = date(2000, 1, 1)  # type: ignore[misc]

    def test_all_strategies_no_infeasible_cohorts_returned(
        self, dataset_100: Dataset
    ) -> None:
        """Every returned cohort must have >= horizon_months remaining snapshots."""
        horizon = 36
        snap_dates = [s.date for s in dataset_100.snapshots]
        date_to_index = {s.date: i for i, s in enumerate(dataset_100.snapshots)}
        total = len(dataset_100.snapshots)

        for cohorts in [
            CohortGenerator.generate_rolling_monthly(dataset_100, horizon),
            CohortGenerator.generate_range(
                dataset_100, horizon, snap_dates[0], snap_dates[-1]
            ),
            CohortGenerator.from_start_dates(
                dataset_100, horizon, [snap_dates[0], snap_dates[10]]
            ),
        ]:
            for c in cohorts:
                idx = date_to_index[c.start_date]
                remaining = total - idx
                assert remaining >= horizon, (
                    f"Cohort {c.start_date} has only {remaining} snapshots "
                    f"remaining but horizon is {horizon}."
                )
