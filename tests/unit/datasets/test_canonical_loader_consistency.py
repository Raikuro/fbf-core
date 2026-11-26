"""Canonical loader consistency invariants.

These tests exercise canonical-loader-specific validation.  They do not
broaden the generic ``Dataset`` or ``MarketSnapshot`` constructors, and they
verify that prescribed/custom datasets remain unaffected.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from fbf.core.datasets import ern
from fbf.core.datasets.ern import (
    PreparedErnDataset,
    ProjectionConfig,
    prepare_ern_dataset,
)
from fbf.core.datasets.prescribed import build_prescribed_dataset
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.return_sequence import ReturnSequence

_END_DATE = date(1871, 6, 1)
_EXTENDED_END_DATE = date(1871, 7, 1)
_DEFAULT_EQUITY = (
    ("1871-02-01", Decimal("0.01")),
    ("1871-03-01", Decimal("0.02")),
    ("1871-04-01", Decimal("-0.01")),
)
_DEFAULT_BOND = (
    ("1871-02-01", Decimal("0.005")),
    ("1871-03-01", Decimal("0.006")),
    ("1871-04-01", Decimal("0.004")),
)
_DEFAULT_CPI = (
    ("1871-02-01", Decimal("100.1")),
    ("1871-03-01", Decimal("100.2")),
    ("1871-04-01", Decimal("100.3")),
)


def _write_csv(path: Path, rows: tuple[tuple[str, Decimal], ...]) -> None:
    lines = ["date,value", *(f"{raw_date},{value}" for raw_date, value in rows)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _make_data_dir(
    tmp_path: Path,
    *,
    equity: tuple[tuple[str, Decimal], ...] = _DEFAULT_EQUITY,
    bond: tuple[tuple[str, Decimal], ...] = _DEFAULT_BOND,
    cpi: tuple[tuple[str, Decimal], ...] = _DEFAULT_CPI,
) -> Path:
    data_dir = tmp_path / "ern"
    data_dir.mkdir()
    _write_csv(data_dir / "spx_tr_real.csv", equity)
    _write_csv(data_dir / "bond_10y_tr_real.csv", bond)
    _write_csv(data_dir / "cpi.csv", cpi)
    return data_dir


def _prepare(
    data_dir: Path, *, end_date: date = _END_DATE
) -> PreparedErnDataset:
    return prepare_ern_dataset(
        data_dir,
        config=ProjectionConfig(end_date=end_date),
    )


def _dataset_without_date(dataset: Dataset, missing: date) -> Dataset:
    return Dataset(
        snapshots=tuple(
            snapshot for snapshot in dataset.snapshots if snapshot.date != missing
        ),
        frequency=dataset.frequency,
    )


def _replace_snapshot(
    dataset: Dataset, index: int, **changes: Any
) -> Dataset:
    snapshots = list(dataset.snapshots)
    snapshots[index] = replace(snapshots[index], **changes)
    return Dataset(snapshots=tuple(snapshots), frequency=dataset.frequency)


def _patch_builder(
    monkeypatch: pytest.MonkeyPatch,
    transform: Callable[[Dataset], Dataset],
) -> None:
    original = ern._build_ern_dataset

    def wrapper(*args: Any, **kwargs: Any) -> Dataset:
        return transform(original(*args, **kwargs))

    monkeypatch.setattr(ern, "_build_ern_dataset", wrapper)


def _asset_ids(snapshot: MarketSnapshot) -> set[str]:
    return {asset.id for asset in snapshot.index_levels}


def test_valid_synthetic_canonical_dataset_passes(tmp_path: Path) -> None:
    prepared = _prepare(_make_data_dir(tmp_path))

    assert prepared.dataset.end_date == _END_DATE
    assert prepared.metadata.projection_end == _END_DATE
    assert prepared.metadata.snapshot_count == len(prepared.dataset) == 6
    assert prepared.metadata.historical_snapshot_count == 4
    assert prepared.metadata.projected_snapshot_count == 2
    assert all(_asset_ids(snapshot) == {"equity", "bond"} for snapshot in prepared.dataset)


def test_canonical_dataset_passes_validation() -> None:
    prepared = prepare_ern_dataset(Path("data/inputs/ern"))

    assert prepared.metadata.projection_end == prepared.dataset.end_date


def test_missing_first_historical_return_date_is_rejected(tmp_path: Path) -> None:
    data_dir = _make_data_dir(tmp_path, equity=_DEFAULT_EQUITY[1:])

    with pytest.raises(ValueError, match="return coverage must start at 1871-02-01"):
        _prepare(data_dir)


def test_discontinuous_historical_return_dates_are_rejected(tmp_path: Path) -> None:
    equity = tuple(
        row for row in _DEFAULT_EQUITY if row[0] != "1871-03-01"
    )
    data_dir = _make_data_dir(tmp_path, equity=equity)

    with pytest.raises(ValueError, match="return coverage must be contiguous monthly"):
        _prepare(data_dir)


def test_duplicate_historical_return_dates_are_rejected(tmp_path: Path) -> None:
    equity = (
        _DEFAULT_EQUITY[0],
        _DEFAULT_EQUITY[1],
        _DEFAULT_EQUITY[1],
        _DEFAULT_EQUITY[2],
    )
    data_dir = _make_data_dir(tmp_path, equity=equity)

    with pytest.raises(ValueError, match="return dates must be strictly increasing"):
        _prepare(data_dir)


def test_unsorted_historical_return_dates_are_rejected(tmp_path: Path) -> None:
    equity = (
        _DEFAULT_EQUITY[1],
        _DEFAULT_EQUITY[0],
        _DEFAULT_EQUITY[2],
    )
    data_dir = _make_data_dir(tmp_path, equity=equity)

    with pytest.raises(ValueError, match="return dates must be strictly increasing"):
        _prepare(data_dir)


def test_discontinuous_projection_dates_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = _make_data_dir(tmp_path)
    _patch_builder(
        monkeypatch,
        lambda dataset: _dataset_without_date(dataset, date(1871, 6, 1)),
    )

    with pytest.raises(ValueError, match="projection coverage must be contiguous monthly"):
        _prepare(data_dir, end_date=_EXTENDED_END_DATE)


def test_missing_cpi_for_historical_return_month_is_rejected(tmp_path: Path) -> None:
    cpi = tuple(row for row in _DEFAULT_CPI if row[0] != "1871-03-01")
    data_dir = _make_data_dir(tmp_path, cpi=cpi)

    with pytest.raises(
        ValueError,
        match="Canonical historical snapshot 1871-03-01 has no CPI observation",
    ):
        _prepare(data_dir)


def test_synthetic_base_snapshot_cpi_exception_is_accepted(tmp_path: Path) -> None:
    prepared = _prepare(_make_data_dir(tmp_path))

    base = prepared.dataset.snapshots[0]
    assert base.date == date(1871, 1, 31)
    assert base.inflation_cumulative == Decimal("0")


def test_incorrect_running_ath_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = _make_data_dir(tmp_path)
    _patch_builder(
        monkeypatch,
        lambda dataset: _replace_snapshot(
            dataset,
            2,
            running_ath=dataset.snapshots[2].running_ath + Decimal("1"),
        ),
    )

    with pytest.raises(ValueError, match="running ATH mismatch"):
        _prepare(data_dir)


def test_incorrect_is_ath_flag_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = _make_data_dir(tmp_path)
    _patch_builder(
        monkeypatch,
        lambda dataset: _replace_snapshot(dataset, 1, is_ath=False),
    )

    with pytest.raises(ValueError, match="is_ath mismatch"):
        _prepare(data_dir)


def test_incorrect_is_underwater_flag_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = _make_data_dir(tmp_path)
    _patch_builder(
        monkeypatch,
        lambda dataset: _replace_snapshot(dataset, 1, is_underwater=True),
    )

    with pytest.raises(ValueError, match="is_underwater mismatch"):
        _prepare(data_dir)


def test_ath_tie_is_accepted(tmp_path: Path) -> None:
    equity = (
        ("1871-02-01", Decimal("0.01")),
        ("1871-03-01", Decimal("0.02")),
        ("1871-04-01", Decimal("0")),
    )
    prepared = _prepare(_make_data_dir(tmp_path, equity=equity))
    snapshots = {snapshot.date: snapshot for snapshot in prepared.dataset}

    march = snapshots[date(1871, 3, 1)]
    april = snapshots[date(1871, 4, 1)]
    assert april.running_ath == march.running_ath
    assert april.is_ath is True
    assert april.is_underwater is False


def test_missing_canonical_asset_class_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = _make_data_dir(tmp_path)

    def remove_bond(dataset: Dataset) -> Dataset:
        return Dataset(
            snapshots=tuple(
                replace(
                    snapshot,
                    index_levels={
                        asset: level
                        for asset, level in snapshot.index_levels.items()
                        if asset.id != "bond"
                    },
                )
                for snapshot in dataset
            ),
            frequency=dataset.frequency,
        )

    _patch_builder(monkeypatch, remove_bond)

    with pytest.raises(ValueError, match="exactly asset classes"):
        _prepare(data_dir)


def test_unexpected_canonical_asset_class_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = _make_data_dir(tmp_path)
    cash = AssetClass(id="cash", name="", description="")

    def add_cash(dataset: Dataset) -> Dataset:
        return Dataset(
            snapshots=tuple(
                replace(
                    snapshot,
                    index_levels={
                        **dict(snapshot.index_levels),
                        cash: Decimal("1"),
                    },
                )
                for snapshot in dataset
            ),
            frequency=dataset.frequency,
        )

    _patch_builder(monkeypatch, add_cash)

    with pytest.raises(ValueError, match="exactly asset classes"):
        _prepare(data_dir)


def test_projection_end_metadata_disagreement_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = _make_data_dir(tmp_path)
    _patch_builder(
        monkeypatch,
        lambda dataset: _dataset_without_date(dataset, date(1871, 7, 1)),
    )

    with pytest.raises(ValueError, match="projection coverage must end at metadata"):
        _prepare(data_dir, end_date=_EXTENDED_END_DATE)


def test_non_month_start_projection_end_is_rejected(tmp_path: Path) -> None:
    data_dir = _make_data_dir(tmp_path)

    with pytest.raises(ValueError, match="projection.end_date must be the first day"):
        prepare_ern_dataset(
            data_dir,
            config=ProjectionConfig(end_date=date(1871, 6, 15)),
        )


def test_non_month_start_required_through_is_rejected(tmp_path: Path) -> None:
    data_dir = _make_data_dir(tmp_path)

    with pytest.raises(ValueError, match="required_through must be the first day"):
        prepare_ern_dataset(data_dir, required_through=date(1871, 6, 15))


def test_canonical_checks_do_not_apply_to_prescribed_or_custom_datasets() -> None:
    sequence = ReturnSequence(
        equity_returns=tuple(Decimal("0") for _ in range(120)),
        bond_returns=tuple(Decimal("0") for _ in range(120)),
        start_date=date(1929, 9, 1),
    )
    prescribed = build_prescribed_dataset(sequence)
    assert len(prescribed) == 120

    custom_asset = AssetClass(id="custom", name="", description="")
    custom_snapshot = MarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={custom_asset: Decimal("100")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=True,
        is_underwater=True,
        running_ath=Decimal("999"),
    )
    custom = Dataset(snapshots=(custom_snapshot,), frequency="monthly")
    assert custom[0].is_ath is True
    assert custom[0].is_underwater is True
