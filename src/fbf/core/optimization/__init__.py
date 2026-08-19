"""SWR optimization and comparative strategy analytics."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fbf.core.optimization.strategy_comparator import StrategyComparator, StrategyComparisonReport
from fbf.core.optimization.swr_optimizer import (
    Evaluator,
    OptimizerOutcome,
    SWROptimizationResult,
    SWROptimizer,
)


def optimize_study_swr(
    evaluator: Evaluator,
    domain_min: Decimal = Decimal("0.01"),
    domain_max: Decimal = Decimal("0.10"),
    precision: Decimal = Decimal("0.0001"),
    **kwargs: Any,
) -> SWROptimizationResult:
    """Solve for maximum Safe Withdrawal Rate satisfying target success rate."""
    optimizer = SWROptimizer()
    return optimizer.optimize(
        evaluator=evaluator,
        domain_min=domain_min,
        domain_max=domain_max,
        precision=precision,
        **kwargs,
    )


__all__ = [
    "SWROptimizer",
    "SWROptimizationResult",
    "OptimizerOutcome",
    "StrategyComparator",
    "StrategyComparisonReport",
    "optimize_study_swr",
]
