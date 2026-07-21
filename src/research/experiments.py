"""Research package experiments.

Contains experiment definitions and builders for scientific studies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from engine.domain.dataset import Dataset
from engine.domain.policies import AllocationPolicy, WithdrawalPolicy


@dataclass(frozen=True)
class ExperimentDefinition:
    name: str
    description: str
    dataset: Dataset
    horizon_months: int
    cohorts: Sequence[str]
    allocation_policies: Sequence[AllocationPolicy]
    withdrawal_policies: Sequence[WithdrawalPolicy]
    targets: Sequence[float]
    optimizer: str | None = None
