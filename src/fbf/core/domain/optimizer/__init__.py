"""Domain optimizer package.

Contains optimizer abstractions for finding safe withdrawal rates and related search results.
"""

from .optimizer import OptimizationResult, Optimizer
from .strategy_comparator import StrategyComparator
from .types import (
    EvaluationError,
    EvaluationResult,
    Evaluator,
    InvalidInputError,
    MetricDefinition,
    MetricDirection,
    RankingRule,
    StrategyComparisonReport,
)

__all__ = [
    "EvaluationResult",
    "Evaluator",
    "InvalidInputError",
    "EvaluationError",
    "MetricDefinition",
    "MetricDirection",
    "Optimizer",
    "OptimizationResult",
    "RankingRule",
    "StrategyComparisonReport",
    "StrategyComparator",
]
