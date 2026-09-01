"""Tests for the authoritative in-process DatasetCache (P4.11 Phase 1).

Covers:
- repeated resolution triggers exactly one underlying file load,
- repeated resolution returns the identical Dataset object,
- prefix slicing of a longer dataset is value-equivalent to a shorter
  independently-loaded dataset (generic, synthetic),
- ERN prefix identity: h720 sliced to h360 is value-equivalent to the
  committed h360 dataset,
- persistence context reuses the same cache instead of loading again,
- cache unit behaviour: path normalization, no failure caching, clear.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.persistence.studies.sqlite import (
    DatasetCache,
    DefaultDatasetResolver,
    clear_default_dataset_cache,
    context as context_module,
)
from fbf.core.persistence.studies.sqlite.context import (
    _dataset_to_dict,
    create_persistence_context,
)
from fbf.core.persistence.studies.sqlite.errors import StudyNotFoundError

EQ = AssetClass(id="equity", name="Equity", description="")
BD = AssetClass(id="bond", name="Bond", description="")

ERN_DATA_DIR = Path("data/ern").resolve()


@pytest.fixture(autouse=True)
def _isolated_default_cache() -> Iterator[None]:
    clear_default_dataset_cache()
    yield
    clear_default_dataset_cache()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _snapshot(day: int, level: Decimal = Decimal("100.00")) -> MarketSnapshot:
    return MarketSnapshot(
        date=date(2000, 1, day),
        index_levels={EQ: level, BD: level / Decimal("2")},
        inflation=Decimal("0.00"),
        inflation_cumulative=Decimal("1.00"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100.00"),
    )


def _write_dataset_file(
    data_dir: Path, stem: str, snapshots: list[MarketSnapshot], version: str = "1.0"
) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    dataset = Dataset(snapshots=snapshots, frequency="monthly", version=version)
    path = data_dir / f"{stem}.json"
    path.write_text(json.dumps(_dataset_to_dict(dataset)), encoding="utf-8")
    return path


def _value_equal(a: MarketSnapshot, b: MarketSnapshot) -> bool:
    return (
        a.date == b.date
        and a.index_levels == b.index_levels
        and a.inflation == b.inflation
        and a.inflation_cumulative == b.inflation_cumulative
        and a.is_ath == b.is_ath
        and a.is_underwater == b.is_underwater
        and a.running_ath == b.running_ath
    )


def _count_file_loads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    real = context_module._load_dataset_from_file

    def spy(path: Path) -> Dataset:
        calls.append(str(path))
        return real(path)

    monkeypatch.setattr(context_module, "_load_dataset_from_file", spy)
    return calls


# ---------------------------------------------------------------------------
# Cache unit behaviour
# ---------------------------------------------------------------------------


class TestDatasetCacheUnit:
    def test_load_dir_loads_once_per_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_dataset_file(tmp_path, "ds_a", [_snapshot(1), _snapshot(2)], version="A")
        _write_dataset_file(tmp_path, "ds_b", [_snapshot(3)], version="B")
        calls = _count_file_loads(monkeypatch)

        cache = DatasetCache()
        first = cache.load_dir(str(tmp_path))
        second = cache.load_dir(str(tmp_path))

        assert first is second
        assert first["ds_a"] is second["ds_a"]
        assert first["ds_b"] is second["ds_b"]
        assert sorted(calls) == sorted([str(tmp_path / "ds_a.json"), str(tmp_path / "ds_b.json")])
        assert len(calls) == 2

    def test_load_dir_normalizes_paths(self, tmp_path: Path) -> None:
        cache = DatasetCache()
        _write_dataset_file(tmp_path, "ds_a", [_snapshot(1)], version="A")

        absolute = cache.load_dir(str(tmp_path))
        with_trailing_slash = cache.load_dir(str(tmp_path) + "/")
        relative = cache.load_dir(Path(".").joinpath(tmp_path).as_posix())

        assert absolute is with_trailing_slash is relative

    def test_failures_are_not_cached(self, tmp_path: Path) -> None:
        cache = DatasetCache()
        missing = tmp_path / "missing"
        with pytest.raises(StudyNotFoundError):
            cache.load_dir(str(missing))

        _write_dataset_file(missing, "ds_a", [_snapshot(1)], version="A")
        mapping = cache.load_dir(str(missing))
        assert mapping["ds_a"].version == "A"

    def test_clear_forces_reload(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_dataset_file(tmp_path, "ds_a", [_snapshot(1)], version="A")
        calls = _count_file_loads(monkeypatch)

        cache = DatasetCache()
        first = cache.load_dir(str(tmp_path))
        cache.clear()
        second = cache.load_dir(str(tmp_path))

        assert first["ds_a"] is not second["ds_a"]
        assert len(calls) == 2


# ---------------------------------------------------------------------------
# Repeated resolution through the public loader path
# ---------------------------------------------------------------------------


class TestRepeatedResolution:
    def test_resolution_loads_once(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from fbf.core.study.builder import resolve_dataset

        _write_dataset_file(tmp_path, "ds_a", [_snapshot(1), _snapshot(2)], version="A")
        calls = _count_file_loads(monkeypatch)

        first = resolve_dataset("ds_a", str(tmp_path))
        second = resolve_dataset("ds_a", str(tmp_path))

        assert first is second
        assert calls == [str(tmp_path / "ds_a.json")]

    def test_resolution_returns_same_object(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from fbf.core.study.builder import resolve_dataset

        _write_dataset_file(tmp_path, "ds_a", [_snapshot(1)], version="A")
        _count_file_loads(monkeypatch)

        a = resolve_dataset("ds_a", str(tmp_path))
        b = resolve_dataset("ds_a", str(tmp_path))
        c = DefaultDatasetResolver.from_data_dir(str(tmp_path)).resolve("ds_a")

        assert a is b is c

    def test_unknown_identifier_still_raises(self, tmp_path: Path) -> None:
        from fbf.core.study.builder import resolve_dataset

        _write_dataset_file(tmp_path, "ds_a", [_snapshot(1)], version="A")
        with pytest.raises(StudyNotFoundError):
            resolve_dataset("MISSING", str(tmp_path))


# ---------------------------------------------------------------------------
# Prefix slicing value-equivalence (generic, synthetic)
# ---------------------------------------------------------------------------


class TestPrefixSlicing:
    def test_slice_of_long_dataset_equals_short_file(self, tmp_path: Path) -> None:
        _write_dataset_file(
            tmp_path, "long", [_snapshot(1), _snapshot(2), _snapshot(3), _snapshot(4)], version="L"
        )
        _write_dataset_file(tmp_path, "short", [_snapshot(1), _snapshot(2)], version="S")

        long_ds = DefaultDatasetResolver.from_data_dir(str(tmp_path)).resolve("long")
        short_ds = DefaultDatasetResolver.from_data_dir(str(tmp_path)).resolve("short")

        sliced = long_ds.slice(short_ds.start_date, len(short_ds))

        assert len(sliced) == len(short_ds)
        assert sliced.frequency == short_ds.frequency
        for got, expected in zip(sliced.snapshots, short_ds.snapshots, strict=True):
            assert _value_equal(got, expected)

    def test_slices_of_same_dataset_share_snapshot_objects(self, tmp_path: Path) -> None:
        _write_dataset_file(
            tmp_path, "long", [_snapshot(1), _snapshot(2), _snapshot(3), _snapshot(4)], version="L"
        )

        long_ds = DefaultDatasetResolver.from_data_dir(str(tmp_path)).resolve("long")
        start = long_ds.start_date

        short = long_ds.slice(start, 2)
        long_ = long_ds.slice(start, 4)

        assert all(a is b for a, b in zip(short.snapshots, long_.snapshots, strict=False))


# ---------------------------------------------------------------------------
# ERN prefix identity (verified on committed acceptance data)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not ERN_DATA_DIR.is_dir(), reason="ERN data directory not present")
class TestErnPrefixIdentity:
    def test_h720_sliced_to_h360_equals_h360_dataset(self) -> None:
        from fbf.core.study.builder import resolve_dataset

        h360 = resolve_dataset("ern_swr_h360", str(ERN_DATA_DIR))
        h720 = resolve_dataset("ern_swr_h720", str(ERN_DATA_DIR))

        sliced = h720.slice(h360.start_date, len(h360))

        assert len(sliced) == len(h360)
        assert h360.start_date == h720.start_date
        for got, expected in zip(sliced.snapshots, h360.snapshots, strict=True):
            assert _value_equal(got, expected)

    def test_cached_resolution_is_single_object_across_horizons(self) -> None:
        from fbf.core.study.builder import resolve_dataset

        h360a = resolve_dataset("ern_swr_h360", str(ERN_DATA_DIR))
        h360b = resolve_dataset("ern_swr_h360", str(ERN_DATA_DIR))
        assert h360a is h360b


# ---------------------------------------------------------------------------
# Persistence context reuse
# ---------------------------------------------------------------------------


class TestPersistenceContextReuse:
    def test_persistence_context_reuses_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_dataset_file(tmp_path, "ds_a", [_snapshot(1)], version="A")
        calls = _count_file_loads(monkeypatch)

        resolver = DefaultDatasetResolver.from_data_dir(str(tmp_path))
        direct = resolver.resolve("ds_a")

        ctx = create_persistence_context(str(tmp_path))
        via_context = ctx.dataset_resolver.resolve("ds_a")

        assert isinstance(ctx.dataset_resolver, DefaultDatasetResolver)
        assert direct is via_context
        assert calls == [str(tmp_path / "ds_a.json")]

    def test_persistence_context_and_resolve_dataset_share_objects(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from fbf.core.study.builder import resolve_dataset

        _write_dataset_file(tmp_path, "ds_a", [_snapshot(1)], version="A")
        calls = _count_file_loads(monkeypatch)

        resolved = resolve_dataset("ds_a", str(tmp_path))
        ctx = create_persistence_context(str(tmp_path))
        via_context = ctx.dataset_resolver.resolve("ds_a")

        assert resolved is via_context
        assert len(calls) == 1


# ---------------------------------------------------------------------------
# C6.2 — Dataset / non-Dataset artifact boundary
# ---------------------------------------------------------------------------


class TestArtifactBoundary:
    """Verify that _load_datasets_from_dir skips non-Dataset JSON artifacts."""

    def test_non_dataset_json_is_ignored(self, tmp_path: Path) -> None:
        """A JSON file without frequency/snapshots must not be loaded as a Dataset."""
        (tmp_path / "cohort_manifest.json").write_text(
            json.dumps({"version": "1.0", "cohorts": []}), encoding="utf-8"
        )
        _write_dataset_file(tmp_path, "ds_a", [_snapshot(1)], version="A")

        cache = DatasetCache()
        datasets = cache.load_dir(str(tmp_path))

        assert "ds_a" in datasets
        assert "cohort_manifest" not in datasets

    def test_provenance_json_is_ignored(self, tmp_path: Path) -> None:
        """A provenance metadata JSON must not be loaded as a Dataset."""
        (tmp_path / "ern_real_returns.provenance.json").write_text(
            json.dumps({"source": "test", "sha256": "abc"}), encoding="utf-8"
        )
        _write_dataset_file(tmp_path, "ds_a", [_snapshot(1)], version="A")

        cache = DatasetCache()
        datasets = cache.load_dir(str(tmp_path))

        assert "ds_a" in datasets
        assert "ern_real_returns.provenance" not in datasets

    def test_cohort_manifest_json_is_ignored(self, tmp_path: Path) -> None:
        """The cohort_manifest_part3.json structure must not be loaded as a Dataset."""
        manifest = {
            "version": "1.0",
            "description": "Part 3 cohort manifest",
            "cohort_range": {"first": "1871-02-01", "last": "2015-12-01", "total": 1739},
        }
        (tmp_path / "cohort_manifest_part3.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        _write_dataset_file(tmp_path, "ds_a", [_snapshot(1)], version="A")

        cache = DatasetCache()
        datasets = cache.load_dir(str(tmp_path))

        assert "ds_a" in datasets
        assert "cohort_manifest_part3" not in datasets

    def test_valid_dataset_json_still_loads(self, tmp_path: Path) -> None:
        """A valid Dataset JSON must continue to load correctly."""
        _write_dataset_file(tmp_path, "ds_valid", [_snapshot(1), _snapshot(2)], version="V")

        cache = DatasetCache()
        datasets = cache.load_dir(str(tmp_path))

        assert "ds_valid" in datasets
        assert datasets["ds_valid"].version == "V"
        assert len(datasets["ds_valid"]) == 2

    def test_multiple_valid_datasets_resolve(self, tmp_path: Path) -> None:
        """Multiple valid Dataset files must all be loaded and resolvable."""
        _write_dataset_file(tmp_path, "ds_a", [_snapshot(1)], version="A")
        _write_dataset_file(tmp_path, "ds_b", [_snapshot(2)], version="B")
        (tmp_path / "skipped.json").write_text(
            json.dumps({"not": "a dataset"}), encoding="utf-8"
        )

        cache = DatasetCache()
        datasets = cache.load_dir(str(tmp_path))

        assert set(datasets) == {"ds_a", "ds_b"}
        assert datasets["ds_a"].version == "A"
        assert datasets["ds_b"].version == "B"

    def test_malformed_dataset_file_raises(self, tmp_path: Path) -> None:
        """A JSON file that has frequency but missing snapshots must raise."""
        (tmp_path / "broken.json").write_text(
            json.dumps({"version": "1.0", "frequency": "monthly"}),
            encoding="utf-8",
        )
        cache = DatasetCache()
        with pytest.raises((StudyNotFoundError, KeyError, TypeError)):
            cache.load_dir(str(tmp_path))

    def test_empty_directory_returns_empty_mapping(self, tmp_path: Path) -> None:
        """An empty directory must return an empty dataset mapping."""
        cache = DatasetCache()
        datasets = cache.load_dir(str(tmp_path))
        assert dict(datasets) == {}

    def test_non_json_files_are_ignored(self, tmp_path: Path) -> None:
        """CSV and other non-JSON files must be silently skipped."""
        (tmp_path / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
        _write_dataset_file(tmp_path, "ds_a", [_snapshot(1)], version="A")

        cache = DatasetCache()
        datasets = cache.load_dir(str(tmp_path))

        assert set(datasets) == {"ds_a"}


@pytest.mark.skipif(not ERN_DATA_DIR.is_dir(), reason="ERN data directory not present")
class TestErnArtifactBoundary:
    """Verify the fix against the real data/ern/ directory."""

    def test_ern_dir_loads_only_datasets(self) -> None:
        """data/ern/ must load only valid Datasets, skipping manifest/provenance."""
        cache = DatasetCache()
        datasets = cache.load_dir(str(ERN_DATA_DIR))

        known_datasets = {
            "ern_swr_h360", "ern_swr_h480", "ern_swr_h600",
            "ern_swr_h720", "ern_cape_1871_2016",
        }
        assert set(datasets.keys()) >= known_datasets
        assert "cohort_manifest_part3" not in datasets
        assert "ern_real_returns_1871_2016.provenance" not in datasets

    def test_ern_h720_resolves_after_boundary_fix(self) -> None:
        """ern_swr_h720 must resolve correctly after the artifact boundary fix."""
        from fbf.core.study.builder import resolve_dataset

        h720 = resolve_dataset("ern_swr_h720", str(ERN_DATA_DIR))
        assert h720 is not None
        assert len(h720) > 0

    def test_ern_h360_resolves_after_boundary_fix(self) -> None:
        """ern_swr_h360 must resolve correctly after the artifact boundary fix."""
        from fbf.core.study.builder import resolve_dataset

        h360 = resolve_dataset("ern_swr_h360", str(ERN_DATA_DIR))
        assert h360 is not None
        assert len(h360) > 0
