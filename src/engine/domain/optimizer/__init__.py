"""Domain optimizer package.

Contains optimizer abstractions for finding safe withdrawal rates and related search results.
"""

from .optimizer import Optimizer, OptimizationResult
from .strategy_comparator import StrategyComparator
from .types import EvaluationResult, Evaluator, InvalidInputError, RankingRule, StrategyComparisonReport

__all__ = [
    "EvaluationResult",
    "Evaluator",
    "InvalidInputError",
    "Optimizer",
    "OptimizationResult",
    "RankingRule",
    "StrategyComparisonReport",
    "StrategyComparator",
]
