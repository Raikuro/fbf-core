from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot

_ASSET = AssetClass(id="acwi", name="ACWI", description="Global equities")


def _make_snapshot(day: date, level: str = "100.00") -> MarketSnapshot:
    return MarketSnapshot(
        date=day,
        index_levels={_ASSET: Decimal(level)},
        inflation=Decimal("0.00"),
        inflation_cumulative=Decimal("0.00"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100.00"),
    )


def test_dataset_ordering_validation() -> None:
    asset = AssetClass(id="acwi", name="ACWI", description="Global equities")
    snapshot_a = MarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={asset: Decimal("100.00")},
        inflation=Decimal("0.00"),
        inflation_cumulative=Decimal("0.00"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100.00"),
    )
    snapshot_b = MarketSnapshot(
        date=date(1999, 12, 1),
        index_levels={asset: Decimal("98.00")},
        inflation=Decimal("0.00"),
        inflation_cumulative=Decimal("0.00"),
        is_ath=False,
        is_underwater=False,
        running_ath=Decimal("100.00"),
    )

    with pytest.raises(ValueError):
        Dataset(snapshots=[snapshot_a, snapshot_b], frequency="monthly")


def test_dataset_unique_dates_validation() -> None:
    asset = AssetClass(id="acwi", name="ACWI", description="Global equities")
    snapshot = MarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={asset: Decimal("100.00")},
        inflation=Decimal("0.00"),
        inflation_cumulative=Decimal("0.00"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100.00"),
    )

    with pytest.raises(ValueError):
        Dataset(snapshots=[snapshot, snapshot], frequency="monthly")


def test_dataset_slice_access() -> None:
    asset = AssetClass(id="acwi", name="ACWI", description="Global equities")
    snapshot = MarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={asset: Decimal("100.00")},
        inflation=Decimal("0.00"),
        inflation_cumulative=Decimal("0.00"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100.00"),
    )
    dataset = Dataset(snapshots=[snapshot], frequency="monthly")

    assert len(dataset) == 1
    assert dataset[0].date == date(2000, 1, 1)
    assert dataset.start_date == date(2000, 1, 1)
    assert dataset.end_date == date(2000, 1, 1)


def test_list_input_is_normalized_to_tuple() -> None:
    snapshot = _make_snapshot(date(2000, 1, 1))

    dataset = Dataset(snapshots=[snapshot], frequency="monthly")

    assert isinstance(dataset.snapshots, tuple)
    assert dataset.snapshots == (snapshot,)


def test_original_list_mutation_does_not_affect_dataset() -> None:
    first = _make_snapshot(date(2000, 1, 1))
    snapshots = [first]
    dataset = Dataset(snapshots=snapshots, frequency="monthly")

    snapshots.append(_make_snapshot(date(2000, 2, 1)))

    assert len(dataset) == 1
    assert dataset.snapshots == (first,)


def test_exposed_snapshots_cannot_be_modified() -> None:
    snapshot = _make_snapshot(date(2000, 1, 1))
    dataset = Dataset(snapshots=(snapshot,), frequency="monthly")
    snapshots: Any = dataset.snapshots

    with pytest.raises(AttributeError):
        snapshots.append(_make_snapshot(date(2000, 2, 1)))
    with pytest.raises(TypeError):
        snapshots[0] = _make_snapshot(date(2000, 2, 1))

    assert dataset.snapshots == (snapshot,)


def test_equivalent_list_and_tuple_inputs_compare_equal() -> None:
    snapshot = _make_snapshot(date(2000, 1, 1))

    list_backed = Dataset(snapshots=[snapshot], frequency="monthly")
    tuple_backed = Dataset(snapshots=(snapshot,), frequency="monthly")

    assert list_backed == tuple_backed


def test_empty_snapshots_are_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="Dataset must contain at least one MarketSnapshot",
    ):
        Dataset(snapshots=[], frequency="monthly")
