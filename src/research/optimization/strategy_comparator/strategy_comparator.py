from typing import Protocol, Mapping, Sequence
from dataclasses import dataclass

class EvaluationResult:
    """Placeholder for EvaluationResult."""
    pass

class Evaluator(Protocol):
    """Abstract evaluator to provide evaluation artifacts."""
    def get_evaluation(self, label: str) -> EvaluationResult: ...

@dataclass(frozen=True)
class StrategyComparisonReport:
    """Immutable report containing aggregated metrics and ranking."""
    aggregated_metrics: Mapping[str, Mapping[str, float]]
    ranking: Sequence[str]
    provenance: Mapping[str, Sequence[str]]

class RankingRule:
    """Placeholder for RankingRule."""
    pass

class StrategyComparator:
    """
    Consumer component for comparative analytics.
    """
    def __init__(self, metrics: Sequence[str], ranking_rule: RankingRule):
        self._metrics = metrics
        self._ranking_rule = ranking_rule

    def compare(self, strategy_map: Mapping[str, Evaluator]) -> StrategyComparisonReport:
        """
        Produces a deterministic report from the provided strategies.
        """
        raise NotImplementedError("To be implemented.")
