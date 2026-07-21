"""Experiment definition placeholder for the Research package."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from engine.domain.model.dataset import Dataset


@dataclass(frozen=True)
class ExperimentDefinition:
    name: str
    description: str
    dataset: Dataset
    horizon_months: int
    cohorts: Sequence[str]
    allocation_policies: Sequence[object]
    withdrawal_policies: Sequence[object]
    targets: Sequence[float]
    optimizer: str | None = None
