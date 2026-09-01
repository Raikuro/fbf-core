"""Tests for persistence context factory and dataset loading (Package P3.2).

Covers:
- Dataset JSON serialization round-trip
- Dataset file loading (single file, directory)
- DefaultDatasetResolver.from_data_dir()
- create_persistence_context() factory
- Error cases: missing file, bad JSON, unknown identifier
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.persistence.studies.sqlite import (
    DefaultDatasetResolver,
    PersistenceReconstructionContext,
    RepositoryError,
    StudyNotFoundError,
    create_persistence_context,
)
from fbf.core.persistence.studies.sqlite.context import (
    _dataset_to_dict,
    _dict_to_dataset,
    _load_dataset_from_file,
    _load_datasets_from_dir,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_ASSET_ONE = AssetClass(id="acwi", name="ACWI", description="Global equities")
_ASSET_TWO = AssetClass(id="bonds", name="Bonds", description="Fixed income")

_SNAPSHOT = MarketSnapshot(
    date=date(2000, 1, 31),
    index_levels={_ASSET_ONE: Decimal("100.00"), _ASSET_TWO: Decimal("99.50")},
    inflation=Decimal("0.0025"),
    inflation_cumulative=Decimal("1.0250"),
    is_ath=True,
    is_underwater=False,
    running_ath=Decimal("100.00"),
)

_DATASET = Dataset(
    snapshots=[_SNAPSHOT],
    frequency="monthly",
    version="ACWI_2000",
)

_MULTI_SNAPSHOT_DATASET = Dataset(
    snapshots=[
        MarketSnapshot(
            date=date(2000, 1, 31),
            index_levels={_ASSET_ONE: Decimal("100.00")},
            inflation=Decimal("0.00"),
            inflation_cumulative=Decimal("1.0000"),
            is_ath=True,
            is_underwater=False,
            running_ath=Decimal("100.00"),
        ),
        MarketSnapshot(
            date=date(2000, 2, 29),
            index_levels={_ASSET_ONE: Decimal("102.50")},
            inflation=Decimal("0.0010"),
            inflation_cumulative=Decimal("1.0010"),
            is_ath=True,
            is_underwater=False,
            running_ath=Decimal("102.50"),
        ),
    ],
    frequency="monthly",
    version="ASSET_2000",
)


# ---------------------------------------------------------------------------
# Dataset JSON round-trip
# ---------------------------------------------------------------------------


class TestDatasetJsonRoundTrip:
    def test_dataset_to_dict_and_back(self) -> None:
        d = _dataset_to_dict(_DATASET)
        restored = _dict_to_dataset(d)
        assert restored.version == _DATASET.version
        assert restored.frequency == _DATASET.frequency
        assert len(restored) == len(_DATASET)
        original_snap = _DATASET[0]
        restored_snap = restored[0]
        assert restored_snap.date == original_snap.date
        assert restored_snap.inflation == original_snap.inflation
        assert restored_snap.inflation_cumulative == original_snap.inflation_cumulative
        assert restored_snap.is_ath == original_snap.is_ath
        assert restored_snap.is_underwater == original_snap.is_underwater
        assert restored_snap.running_ath == original_snap.running_ath
        assert list(restored_snap.index_levels.keys())[0].id == "acwi"
        assert list(restored_snap.index_levels.values())[0] == Decimal("100.00")

    def test_multi_snapshot_round_trip(self) -> None:
        d = _dataset_to_dict(_MULTI_SNAPSHOT_DATASET)
        restored = _dict_to_dataset(d)
        assert len(restored) == 2
        for orig, rest in zip(_MULTI_SNAPSHOT_DATASET, restored, strict=True):
            assert rest.date == orig.date
            assert len(rest.index_levels) == 1
            assert list(rest.index_levels.keys())[0].id == "acwi"

    def test_json_format_structure(self) -> None:
        d = _dataset_to_dict(_DATASET)
        assert d["version"] == "ACWI_2000"
        assert d["frequency"] == "monthly"
        assert len(d["snapshots"]) == 1
        snap = d["snapshots"][0]
        assert snap["date"] == "2000-01-31"
        assert isinstance(snap["inflation"], str)
        assert isinstance(snap["inflation_cumulative"], str)
        assert isinstance(snap["is_ath"], bool)
        assert isinstance(snap["running_ath"], str)
        assert snap["index_levels"] == {"acwi": "100.00", "bonds": "99.50"}


# ---------------------------------------------------------------------------
# Single file loading
# ---------------------------------------------------------------------------


class TestLoadDatasetFromFile:
    def test_load_from_file(self, tmp_path: Path) -> None:
        file_path = tmp_path / "test_dataset.json"
        data = _dataset_to_dict(_DATASET)
        file_path.write_text(json.dumps(data), encoding="utf-8")
        loaded = _load_dataset_from_file(file_path)
        assert loaded.version == _DATASET.version
        assert loaded.frequency == _DATASET.frequency
        assert loaded[0].date == _DATASET[0].date
        assert list(loaded[0].index_levels.keys())[0].id == "acwi"
        assert list(loaded[0].index_levels.values())[0] == Decimal("100.00")

    def test_file_not_found_raises_study_not_found(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.json"
        with pytest.raises(StudyNotFoundError):
            _load_dataset_from_file(missing)

    def test_bad_json_raises_study_not_found(self, tmp_path: Path) -> None:
        file_path = tmp_path / "bad.json"
        file_path.write_text("not valid json", encoding="utf-8")
        with pytest.raises(StudyNotFoundError):
            _load_dataset_from_file(file_path)

    def test_missing_required_field_raises_key_error(self, tmp_path: Path) -> None:
        file_path = tmp_path / "incomplete.json"
        file_path.write_text(json.dumps({"version": "x", "frequency": "monthly"}), encoding="utf-8")
        with pytest.raises(KeyError):
            _load_dataset_from_file(file_path)

    def test_non_dataset_json_returns_none(self, tmp_path: Path) -> None:
        file_path = tmp_path / "not_a_dataset.json"
        file_path.write_text(json.dumps({"version": "x"}), encoding="utf-8")
        result = _load_dataset_from_file(file_path)
        assert result is None


# ---------------------------------------------------------------------------
# Directory loading
# ---------------------------------------------------------------------------


class TestLoadDatasetsFromDir:
    def test_load_all_json_files(self, tmp_path: Path) -> None:
        d1 = _dataset_to_dict(Dataset(
            snapshots=[MarketSnapshot(
                date=date(2000, 1, 31), index_levels={_ASSET_ONE: Decimal("100")},
                inflation=Decimal("0"), inflation_cumulative=Decimal("1"),
                is_ath=True, is_underwater=False, running_ath=Decimal("100"),
            )],
            frequency="monthly", version="DS1",
        ))
        d2 = _dataset_to_dict(Dataset(
            snapshots=[MarketSnapshot(
                date=date(2000, 1, 31), index_levels={_ASSET_ONE: Decimal("200")},
                inflation=Decimal("0"), inflation_cumulative=Decimal("1"),
                is_ath=True, is_underwater=False, running_ath=Decimal("200"),
            )],
            frequency="yearly", version="DS2",
        ))
        (tmp_path / "DS1.json").write_text(json.dumps(d1), encoding="utf-8")
        (tmp_path / "DS2.json").write_text(json.dumps(d2), encoding="utf-8")
        (tmp_path / "readme.txt").write_text("not a dataset", encoding="utf-8")
        result = _load_datasets_from_dir(str(tmp_path))
        assert set(result) == {"DS1", "DS2"}
        assert result["DS1"].version == "DS1"
        assert result["DS2"].version == "DS2"
        assert result["DS1"].frequency == "monthly"
        assert result["DS2"].frequency == "yearly"

    def test_non_existent_dir_raises(self, tmp_path: Path) -> None:
        missing = str(tmp_path / "does_not_exist")
        with pytest.raises(StudyNotFoundError):
            _load_datasets_from_dir(missing)

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        result = _load_datasets_from_dir(str(tmp_path))
        assert result == {}


# ---------------------------------------------------------------------------
# DefaultDatasetResolver.from_data_dir
# ---------------------------------------------------------------------------


class TestDefaultDatasetResolverFromDir:
    def test_from_data_dir_resolves_known(self, tmp_path: Path) -> None:
        data = _dataset_to_dict(_DATASET)
        (tmp_path / "ACWI_2000.json").write_text(json.dumps(data), encoding="utf-8")
        resolver = DefaultDatasetResolver.from_data_dir(str(tmp_path))
        dataset = resolver.resolve("ACWI_2000")
        assert dataset.version == "ACWI_2000"

    def test_from_data_dir_unknown_raises(self, tmp_path: Path) -> None:
        data = _dataset_to_dict(_DATASET)
        (tmp_path / "ACWI_2000.json").write_text(json.dumps(data), encoding="utf-8")
        resolver = DefaultDatasetResolver.from_data_dir(str(tmp_path))
        with pytest.raises(RepositoryError):
            resolver.resolve("UNKNOWN")

    def test_from_data_dir_invalid_dir_raises(self) -> None:
        with pytest.raises(StudyNotFoundError):
            DefaultDatasetResolver.from_data_dir("/invalid/path/xyz")

    def test_original_constructor_unchanged(self) -> None:
        resolver = DefaultDatasetResolver(datasets={"X": _DATASET})
        assert resolver.resolve("X").version == "ACWI_2000"
        with pytest.raises(StudyNotFoundError):
            resolver.resolve("Y")


# ---------------------------------------------------------------------------
# create_persistence_context factory
# ---------------------------------------------------------------------------


class TestCreatePersistenceContext:
    def test_factory_returns_valid_context(self) -> None:
        ctx = create_persistence_context()
        assert isinstance(ctx, PersistenceReconstructionContext)
        assert isinstance(ctx.dataset_resolver, DefaultDatasetResolver)
        assert len(ctx.policy_codecs) == 2
        assert ctx.simulation_result_codec is not None

    def test_factory_empty_resolver_raises_on_resolve(self) -> None:
        ctx = create_persistence_context()
        with pytest.raises(StudyNotFoundError):
            ctx.dataset_resolver.resolve("ANY")

    def test_factory_with_data_dir(self, tmp_path: Path) -> None:
        data = _dataset_to_dict(_DATASET)
        (tmp_path / "ACWI_2000.json").write_text(json.dumps(data), encoding="utf-8")
        ctx = create_persistence_context(data_dir=str(tmp_path))
        dataset = ctx.dataset_resolver.resolve("ACWI_2000")
        assert dataset.version == "ACWI_2000"

    def test_factory_with_data_dir_unknown_raises(self, tmp_path: Path) -> None:
        data = _dataset_to_dict(_DATASET)
        (tmp_path / "ACWI_2000.json").write_text(json.dumps(data), encoding="utf-8")
        ctx = create_persistence_context(data_dir=str(tmp_path))
        with pytest.raises(StudyNotFoundError):
            ctx.dataset_resolver.resolve("MISSING")

    def test_factory_without_data_dir_resolver_is_empty(self) -> None:
        ctx = create_persistence_context()
        with pytest.raises(StudyNotFoundError):
            ctx.dataset_resolver.resolve("ANY")
