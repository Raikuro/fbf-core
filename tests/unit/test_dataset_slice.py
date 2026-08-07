"""Unit tests for Dataset.slice() domain method.

Covers:
1. Origin cohort: start at first snapshot; H snapshots returned.
2. Middle cohort: start at non-zero dataset index; first returned snapshot equals cohort start;
   H snapshots returned.
3. Last valid cohort: exact horizon boundary works.
4. Missing start date: raises expected ValueError.
5. Insufficient history: raises expected ValueError.
6. Invalid horizon_months: raises expected ValueError.
7. Metadata: frequency and version are preserved.
8. Original dataset: remains unchanged (immutability).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from engine.domain.model.asset import AssetClass
from engine.domain.model.dataset import Dataset
from engine.domain.model.market_snapshot import MarketSnapshot

_ASSET = AssetClass(id="acwi", name="ACWI", description="Global equities")


def make_test_dataset(num_months: int = 48, start_year: int = 2000) -> Dataset:
    snapshots = []
    for i in range(num_months):
        m = i + 1
        year = start_year + (m - 1) // 12
        month = ((m - 1) % 12) + 1
        snapshots.append(
            MarketSnapshot(
                date=date(year, month, 1),
                index_levels={_ASSET: Decimal(100 + i)},
                inflation=Decimal("0.00"),
                inflation_cumulative=Decimal("0.00"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal(100 + i),
            )
        )
    return Dataset(snapshots=snapshots, frequency="monthly", version="SLICE_TEST_v1")


class TestDatasetSlice:
    def test_origin_cohort_slice(self) -> None:
        dataset = make_test_dataset(48)
        sliced = dataset.slice(start_date=date(2000, 1, 1), horizon_months=12)

        assert isinstance(sliced, Dataset)
        assert len(sliced) == 12
        assert sliced.start_date == date(2000, 1, 1)
        assert sliced.end_date == date(2000, 12, 1)
        assert sliced[0].date == date(2000, 1, 1)
        assert sliced[11].date == date(2000, 12, 1)

    def test_middle_cohort_slice(self) -> None:
        dataset = make_test_dataset(48)
        cohort_start = date(2001, 6, 1)
        sliced = dataset.slice(start_date=cohort_start, horizon_months=24)

        assert isinstance(sliced, Dataset)
        assert len(sliced) == 24
        assert sliced.start_date == cohort_start
        assert sliced[0].date == cohort_start
        assert sliced[-1].date == date(2003, 5, 1)

    def test_last_valid_cohort_exact_boundary(self) -> None:
        dataset = make_test_dataset(48)
        # 48 snapshots from 2000-01-01 to 2003-12-01
        # Start at 2003-01-01 -> exactly 12 snapshots remain (2003-01 to 2003-12)
        cohort_start = date(2003, 1, 1)
        sliced = dataset.slice(start_date=cohort_start, horizon_months=12)

        assert len(sliced) == 12
        assert sliced.start_date == cohort_start
        assert sliced.end_date == date(2003, 12, 1)

    def test_missing_start_date_raises_value_error(self) -> None:
        dataset = make_test_dataset(48)
        missing_date = date(1999, 1, 1)
        with pytest.raises(ValueError, match="not found in dataset"):
            dataset.slice(start_date=missing_date, horizon_months=12)

    def test_insufficient_history_raises_value_error(self) -> None:
        dataset = make_test_dataset(48)
        # Start at 2003-06-01 -> only 7 snapshots remain (2003-06 to 2003-12)
        cohort_start = date(2003, 6, 1)
        with pytest.raises(ValueError, match="Insufficient dataset history"):
            dataset.slice(start_date=cohort_start, horizon_months=12)

    def test_invalid_horizon_months_raises_value_error(self) -> None:
        dataset = make_test_dataset(48)
        cohort_start = date(2000, 1, 1)

        with pytest.raises(ValueError, match="positive integer"):
            dataset.slice(start_date=cohort_start, horizon_months=0)

        with pytest.raises(ValueError, match="positive integer"):
            dataset.slice(start_date=cohort_start, horizon_months=-5)

        with pytest.raises(ValueError, match="positive integer"):
            bad: int = True  # bool subclasses int; slice must reject it
            dataset.slice(start_date=cohort_start, horizon_months=bad)

    def test_preserves_metadata(self) -> None:
        dataset = make_test_dataset(48)
        sliced = dataset.slice(start_date=date(2000, 5, 1), horizon_months=6)

        assert sliced.frequency == dataset.frequency
        assert sliced.version == dataset.version

    def test_original_dataset_remains_unchanged(self) -> None:
        dataset = make_test_dataset(48)
        initial_length = len(dataset)
        initial_snapshots = tuple(dataset.snapshots)

        sliced = dataset.slice(start_date=date(2001, 1, 1), horizon_months=12)

        assert len(dataset) == initial_length
        assert tuple(dataset.snapshots) == initial_snapshots
        assert len(sliced) == 12
