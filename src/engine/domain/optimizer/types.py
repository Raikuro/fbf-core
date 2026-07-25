"""Domain types for StrategyComparator and related components."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence, Literal


@dataclass(frozen=True)
class EvaluationResult:
    """Evaluation result for a strategy label."""

    label: str
    metrics: Mapping[str, float]
    provenance: Mapping[str, Sequence[str]]


class Evaluator(Protocol):
    """Abstract evaluator to provide evaluation artifacts."""

    def get_evaluations(self, label: str) -> Sequence[EvaluationResult]: ...


class InvalidInputError(ValueError):
    """Raised when input validation fails."""

    pass


class EvaluationError(Exception):
    """Raised when evaluation execution fails."""

    pass


@dataclass(frozen=True)
class RankingRule:
    """Deterministic ranking rule for strategies."""

    primary_metric: str
    tie_breakers: Sequence[str]


GroupingDimension = Literal["parameter_config", "cohort", "global"]


@dataclass(frozen=True)
class StrategyComparisonReport:
    """Immutable report containing aggregated metrics, ranking, provenance, and diagnostics."""

    aggregated_metrics: Mapping[str, Mapping[str, Mapping[str, float]]]
    ranking: Mapping[str, Sequence[str]]
    provenance: Mapping[str, Mapping[str, Sequence[str]]]
    diagnostics: Mapping[str, Mapping[str, str]]