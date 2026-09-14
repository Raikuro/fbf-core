"""Tests for persistence context factory and CanonicalDatasetLoader.

Covers:
- CanonicalDatasetLoader loads from CSV
- create_persistence_context() factory
- Error cases: missing data dir
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fbf.core.persistence.studies.sqlite import (
    CanonicalDatasetLoader,
    PersistenceReconstructionContext,
    create_persistence_context,
)
from fbf.core.persistence.studies.sqlite.errors import StudyNotFoundError

# ---------------------------------------------------------------------------
# CanonicalDatasetLoader
# ---------------------------------------------------------------------------


class TestCanonicalDatasetLoader:
    def test_load_from_data_dir(self) -> None:
        loader = CanonicalDatasetLoader("data/ern")
        dataset = loader.load()
        assert dataset.frequency == "monthly"
        assert len(dataset) > 0

    def test_load_from_nonexistent_dir_raises(self, tmp_path: Path) -> None:
        loader = CanonicalDatasetLoader(str(tmp_path / "nonexistent"))
        with pytest.raises((FileNotFoundError, StudyNotFoundError)):
            loader.load()


# ---------------------------------------------------------------------------
# create_persistence_context factory
# ---------------------------------------------------------------------------


class TestCreatePersistenceContext:
    def test_factory_returns_valid_context(self) -> None:
        ctx = create_persistence_context("data/ern")
        assert isinstance(ctx, PersistenceReconstructionContext)
        assert isinstance(ctx.dataset_loader, CanonicalDatasetLoader)
        assert ctx.simulation_result_codec is not None

    def test_factory_loads_dataset(self) -> None:
        ctx = create_persistence_context("data/ern")
        dataset = ctx.dataset_loader.load()
        assert dataset.frequency == "monthly"
        assert len(dataset) > 0
