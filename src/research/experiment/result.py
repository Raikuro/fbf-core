"""Experiment result placeholder for the Research package."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExperimentResult:
    """Placeholder for experiment execution results."""

    summary: object
    diagnostics: object
