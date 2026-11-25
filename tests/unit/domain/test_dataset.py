from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot

_ASSET = AssetClass(id="acwi", name="ACWI", description="Global equities")
_ASSET_B = AssetClass(id="bond", name="Bond", description="Government bonds")
_ASSET_C = AssetClass(id="gold", name="Gold", description="Gold")


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


def _make_snapshot_with_assets(
    day: date, assets: dict[AssetClass, str]
) -> MarketSnapshot:
    return MarketSnapshot(
        date=day,
        index_levels={asset: Decimal(level) for asset, level in assets.items()},
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


def test_monthly_frequency_is_accepted() -> None:
    dataset = Dataset(
        snapshots=[_make_snapshot(date(2000, 1, 1))],
        frequency="monthly",
    )

    assert dataset.frequency == "monthly"


@pytest.mark.parametrize("frequency", ["annual", "weekly", "", "Monthly"])
@pytest.mark.parametrize(
    "snapshots",
    [
        [_make_snapshot(date(2000, 1, 1))],
        [_make_snapshot(date(2000, 1, 1)), _make_snapshot(date(2000, 2, 1))],
    ],
    ids=["single_snapshot", "multiple_snapshots"],
)
def test_non_monthly_frequency_is_rejected(
    snapshots: list[MarketSnapshot], frequency: str
) -> None:
    with pytest.raises(ValueError, match="frequency must be 'monthly'"):
        Dataset(snapshots=snapshots, frequency=frequency)


def test_monthly_frequency_does_not_require_calendar_spacing() -> None:
    dataset = Dataset(
        snapshots=[
            _make_snapshot(date(2000, 1, 1)),
            _make_snapshot(date(2000, 1, 2)),
        ],
        frequency="monthly",
    )

    assert len(dataset) == 2


def test_consistent_two_asset_datasets_are_accepted() -> None:
    dataset = Dataset(
        snapshots=[
            _make_snapshot_with_assets(
                date(2000, 1, 1), {_ASSET: "100.00", _ASSET_B: "50.00"}
            ),
            _make_snapshot_with_assets(
                date(2000, 2, 1), {_ASSET: "101.00", _ASSET_B: "51.00"}
            ),
        ],
        frequency="monthly",
    )

    assert [set(snapshot.index_levels) for snapshot in dataset] == [
        {_ASSET, _ASSET_B},
        {_ASSET, _ASSET_B},
    ]


def test_consistent_three_asset_datasets_are_accepted() -> None:
    dataset = Dataset(
        snapshots=[
            _make_snapshot_with_assets(
                date(2000, 1, 1),
                {_ASSET: "100.00", _ASSET_B: "50.00", _ASSET_C: "25.00"},
            ),
            _make_snapshot_with_assets(
                date(2000, 2, 1),
                {_ASSET: "101.00", _ASSET_B: "51.00", _ASSET_C: "26.00"},
            ),
        ],
        frequency="monthly",
    )

    assert [set(snapshot.index_levels) for snapshot in dataset] == [
        {_ASSET, _ASSET_B, _ASSET_C},
        {_ASSET, _ASSET_B, _ASSET_C},
    ]


def test_later_snapshot_missing_asset_is_rejected() -> None:
    with pytest.raises(ValueError) as exc_info:
        Dataset(
            snapshots=[
                _make_snapshot_with_assets(
                    date(2000, 1, 1), {_ASSET: "100.00", _ASSET_B: "50.00"}
                ),
                _make_snapshot_with_assets(
                    date(2000, 2, 1), {_ASSET: "101.00"}
                ),
            ],
            frequency="monthly",
        )

    message = str(exc_info.value)
    assert "2000-01-01" in message
    assert "2000-02-01" in message
    assert "missing" in message
    assert "bond" in message


def test_later_snapshot_additional_asset_is_rejected() -> None:
    with pytest.raises(ValueError) as exc_info:
        Dataset(
            snapshots=[
                _make_snapshot_with_assets(date(2000, 1, 1), {_ASSET: "100.00"}),
                _make_snapshot_with_assets(
                    date(2000, 2, 1), {_ASSET: "101.00", _ASSET_B: "51.00"}
                ),
            ],
            frequency="monthly",
        )

    message = str(exc_info.value)
    assert "2000-01-01" in message
    assert "2000-02-01" in message
    assert "extra" in message
    assert "bond" in message


def test_consistently_empty_asset_sets_are_accepted() -> None:
    dataset = Dataset(
        snapshots=[
            _make_snapshot_with_assets(date(2000, 1, 1), {}),
            _make_snapshot_with_assets(date(2000, 2, 1), {}),
        ],
        frequency="monthly",
    )

    assert all(not snapshot.index_levels for snapshot in dataset)


def test_single_snapshot_with_empty_asset_set_is_accepted() -> None:
    dataset = Dataset(
        snapshots=[_make_snapshot_with_assets(date(2000, 1, 1), {})],
        frequency="monthly",
    )

    assert len(dataset) == 1
    assert not dataset[0].index_levels


def test_dataset_slice_preserves_asset_set_invariant() -> None:
    dataset = Dataset(
        snapshots=[
            _make_snapshot_with_assets(
                date(2000, month, 1), {_ASSET: "100.00", _ASSET_B: "50.00"}
            )
            for month in range(1, 5)
        ],
        frequency="monthly",
    )

    sliced = dataset.slice(date(2000, 2, 1), 2)

    assert len(sliced) == 2
    assert all(
        set(snapshot.index_levels) == {_ASSET, _ASSET_B} for snapshot in sliced
    )


def test_dataset_slice_preserves_monthly_frequency() -> None:
    dataset = Dataset(
        snapshots=[_make_snapshot(date(2000, month, 1)) for month in range(1, 5)],
        frequency="monthly",
    )

    sliced = dataset.slice(date(2000, 2, 1), 2)

    assert sliced.frequency == "monthly"
