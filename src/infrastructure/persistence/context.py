"""Dataset file loading and persistence context factory.

Provides infrastructure for loading Dataset objects from JSON files
and creating fully wired PersistenceReconstructionContext instances.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from engine.domain.model.asset import AssetClass
from engine.domain.model.dataset import Dataset
from engine.domain.model.market_snapshot import MarketSnapshot
from infrastructure.persistence.codecs import (
    AllocationPolicyCodec,
    DefaultDatasetResolver,
    SimulationResultCodec,
    WithdrawalPolicyCodec,
)
from infrastructure.persistence.errors import StudyNotFoundError
from infrastructure.persistence.sqlite_repository import (
    PersistenceReconstructionContext,
)


# ---------------------------------------------------------------------------
# Private helpers: Dataset ↔ dict (JSON-safe format)
# ---------------------------------------------------------------------------


def _snapshot_to_dict(snapshot: MarketSnapshot) -> dict[str, Any]:
    return {
        "date": snapshot.date.isoformat(),
        "inflation": str(snapshot.inflation),
        "inflation_cumulative": str(snapshot.inflation_cumulative),
        "is_ath": snapshot.is_ath,
        "is_underwater": snapshot.is_underwater,
        "running_ath": str(snapshot.running_ath),
        "index_levels": {
            asset_class.id: str(value)
            for asset_class, value in snapshot.index_levels.items()
        },
    }


def _snapshot_from_dict(raw: dict[str, Any]) -> MarketSnapshot:
    return MarketSnapshot(
        date=date.fromisoformat(raw["date"]),
        inflation=Decimal(raw["inflation"]),
        inflation_cumulative=Decimal(raw["inflation_cumulative"]),
        is_ath=raw["is_ath"],
        is_underwater=raw["is_underwater"],
        running_ath=Decimal(raw["running_ath"]),
        index_levels={
            AssetClass(id=k, name="", description=""): Decimal(v)
            for k, v in raw["index_levels"].items()
        },
    )


def _dataset_to_dict(dataset: Dataset) -> dict[str, Any]:
    return {
        "version": dataset.version,
        "frequency": dataset.frequency,
        "snapshots": [_snapshot_to_dict(s) for s in dataset.snapshots],
    }


def _dict_to_dataset(raw: dict[str, Any]) -> Dataset:
    return Dataset(
        version=raw["version"],
        frequency=raw["frequency"],
        snapshots=[_snapshot_from_dict(s) for s in raw["snapshots"]],
    )


# ---------------------------------------------------------------------------
# Dataset file I/O
# ---------------------------------------------------------------------------


def _load_dataset_from_file(path: Path) -> Dataset:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise StudyNotFoundError(
            f"Failed to load dataset from '{path}': {exc}"
        ) from exc
    return _dict_to_dataset(raw)


def _load_datasets_from_dir(data_dir: str) -> Mapping[str, Dataset]:
    directory = Path(data_dir)
    if not directory.is_dir():
        raise StudyNotFoundError(
            f"Dataset directory not found: '{data_dir}'"
        )
    datasets: dict[str, Dataset] = {}
    for file_path in sorted(directory.iterdir()):
        if file_path.suffix.lower() == ".json":
            dataset = _load_dataset_from_file(file_path)
            datasets[file_path.stem] = dataset
    return datasets


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_persistence_context(
    data_dir: str | None = None,
) -> PersistenceReconstructionContext:
    if data_dir is not None:
        resolver = DefaultDatasetResolver.from_data_dir(data_dir)
    else:
        resolver = DefaultDatasetResolver()
    return PersistenceReconstructionContext(
        dataset_resolver=resolver,
        policy_codecs={
            ("allocation", "AllocationPolicy"): AllocationPolicyCodec(),
            ("withdrawal", "WithdrawalPolicy"): WithdrawalPolicyCodec(),
        },
        simulation_result_codec=SimulationResultCodec(),
    )
