"""Authoritative in-process cache for loaded datasets.

Single ownership of dataset loading within a process: every resolver and
persistence context obtains its datasets from the same ``DatasetCache``
instance, so a given dataset identifier is read from disk at most once and
every subsequent resolution returns the identical ``Dataset`` object.

The cache is deliberately generic and dataset-agnostic: it keys entries by
data directory and has no knowledge of specific identifiers, horizons, or
policy families.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from engine.domain.model.dataset import Dataset


class DatasetCache:
    """Process-local cache of loaded datasets, keyed by data directory.

    A directory is scanned and its JSON datasets parsed at most once per cache
    lifetime.  Subsequent ``load_dir`` calls for the same directory return the
    same identifier-to-Dataset mapping, preserving object identity for every
    caller (resolvers, persistence contexts, study builders).

    Datasets are immutable once loaded; files modified on disk after a
    directory has been cached are intentionally not re-read (a dataset is
    loaded once per process).
    """

    def __init__(self) -> None:
        self._by_dir: dict[str, Mapping[str, Dataset]] = {}

    def load_dir(self, data_dir: str) -> Mapping[str, Dataset]:
        """Return the identifier-to-Dataset mapping for ``data_dir``, loading once.

        The directory is resolved to a canonical absolute path so logically
        identical paths (relative vs absolute, symlinked) share one cache
        entry.  Load failures are never cached: a missing or unreadable
        directory is re-attempted on the next call.
        """
        key = str(Path(data_dir).resolve())
        cached = self._by_dir.get(key)
        if cached is not None:
            return cached
        from .context import _load_datasets_from_dir

        datasets = _load_datasets_from_dir(data_dir)
        self._by_dir[key] = datasets
        return datasets

    def clear(self) -> None:
        """Drop all cached datasets (test isolation / teardown)."""
        self._by_dir.clear()


_DEFAULT_CACHE: DatasetCache | None = None


def get_default_dataset_cache() -> DatasetCache:
    """Return the process-wide default dataset cache, created lazily.

    Every loader path (``DefaultDatasetResolver.from_data_dir`` and therefore
    ``resolve_dataset`` and ``create_persistence_context``) funnels through
    this single instance, which is the authoritative in-process cache.
    """
    global _DEFAULT_CACHE
    if _DEFAULT_CACHE is None:
        _DEFAULT_CACHE = DatasetCache()
    return _DEFAULT_CACHE


def clear_default_dataset_cache() -> None:
    """Reset the process-wide cache (test isolation / teardown)."""
    global _DEFAULT_CACHE
    _DEFAULT_CACHE = None
