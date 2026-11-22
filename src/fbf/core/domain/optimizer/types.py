"""Domain types for StrategyComparator and related components."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Literal, Protocol


class InvalidInputError(ValueError):
    """Raised when input validation fails."""

    pass


class EvaluationError(Exception):
    """Raised when evaluation execution fails."""

    pass


class MetricDirection(Enum):
    """Optimization direction for a ranked metric."""

    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


@dataclass(frozen=True)
class MetricDefinition:
    """Definition of a metric participating in comparison and ranking."""

    name: str
    direction: MetricDirection

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise InvalidInputError("metric name must be a non-empty string")
        if self.direction not in (MetricDirection.MAXIMIZE, MetricDirection.MINIMIZE):
            raise InvalidInputError(
                f"invalid direction for metric {self.name!r}: {self.direction!r}"
            )


@dataclass(frozen=True)
class EvaluationResult:
    """Evaluation result for a strategy label."""

    label: str
    metrics: Mapping[str, Decimal | None]
    provenance: Mapping[str, Sequence[str]]


class Evaluator(Protocol):
    """Abstract evaluator to provide evaluation artifacts."""

    def get_evaluations(self, label: str) -> Sequence[EvaluationResult]: ...


@dataclass(frozen=True)
class RankingRule:
    """Deterministic ranking rule for strategies."""

    primary_metric: str
    tie_breakers: Sequence[str]


GroupingDimension = Literal["parameter_config", "cohort", "global"]


@dataclass(frozen=True)
class StrategyComparisonReport:
    """Immutable report containing aggregated metrics, ranking, provenance, and diagnostics."""

    aggregated_metrics: Mapping[str, Mapping[str, Mapping[str, Decimal | None]]]
    ranking: Mapping[str, Sequence[str]]
    provenance: Mapping[str, Mapping[str, Sequence[str]]]
    diagnostics: Mapping[str, Mapping[str, str]]
