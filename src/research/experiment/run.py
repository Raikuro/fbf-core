"""Experiment run placeholder for the Research package."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from .definition import ExperimentDefinition


@dataclass(frozen=True)
class ExperimentRun:
    definition: ExperimentDefinition
    run_id: str
    execution_date: date
    state: str
    configuration: dict[str, object]
