from __future__ import annotations

from decimal import Decimal
from datetime import date

import pytest

from engine.domain.model.asset import AssetClass
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.dataset import Dataset


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
        Dataset(snapshots=[snapshot_a, snapshot_b], frequency="monthly", version="1.0")


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
        Dataset(snapshots=[snapshot, snapshot], frequency="monthly", version="1.0")


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
    dataset = Dataset(snapshots=[snapshot], frequency="monthly", version="1.0")

    assert len(dataset) == 1
    assert dataset[0].date == date(2000, 1, 1)
    assert dataset.start_date == date(2000, 1, 1)
    assert dataset.end_date == date(2000, 1, 1)
