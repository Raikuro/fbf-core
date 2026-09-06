"""SWR optimization and comparative strategy analytics."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fbf.core.domain.model.money import Money
from fbf.core.domain.optimizer.strategy_comparator import StrategyComparator
from fbf.core.domain.optimizer.types import (
    EvaluationResult,
    GroupingDimension,
    RankingRule,
    StrategyComparisonReport,
)
from fbf.core.optimization.part52_evaluator import (
    Part52Evaluator,
    Part52EvaluatorConfig,
)
from fbf.core.optimization.swr_optimizer import (
    EvaluationOutcome,
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


def optimize_part52(
    *,
    data_dir: str,
    initial_wealth: Money,
    drawdown_threshold: Decimal,
    debt_interest_rate: Decimal,
    ltv_limit: Decimal = Decimal("0.50"),
    ltv_enforcement: bool = True,
    ffr_dataset_identifier: str | None = None,
    ffr_spread: Decimal | None = None,
    borrow_pcts: tuple[Decimal, ...] | None = None,
    domain_min: Decimal = Decimal("0.030"),
    domain_max: Decimal = Decimal("0.055"),
    precision: Decimal = Decimal("0.0001"),
    workers: int | None = None,
) -> SWROptimizationResult:
    """Find maximum Part 52 withdrawal rate with timing leverage.

    Uses SWROptimizer binary search with a Part52Evaluator that tests
    each candidate WR against a grid of Borrow% values. Delegates
    simulation execution to the existing optimized execution path
    (fast path + parallel workers).

    Parameters
    ----------
    data_dir:
        Path to the dataset directory.
    initial_wealth:
        Starting portfolio value.
    drawdown_threshold:
        Index drawdown threshold for borrowing activation.
    debt_interest_rate:
        Annual interest rate on the margin loan.
    ltv_limit:
        Maximum loan-to-value ratio (default 50%).
    ltv_enforcement:
        Whether the engine enforces LTV limits via margin calls.
    ffr_dataset_identifier:
        FFR dataset identifier for floating-rate interest (None for fixed).
    ffr_spread:
        Spread over FFR for floating-rate interest (None for fixed).
    borrow_pcts:
        Grid of Borrow% values to test.  None uses the default grid
        {0%, 10%, 20%, 30%, 40%, 50%}.
    domain_min:
        Minimum WR to search (default 3.0%).
    domain_max:
        Maximum WR to search (default 5.5%).
    precision:
        WR precision for binary search convergence (default 0.01%).
    workers:
        Number of parallel workers (None for auto).

    Returns
    -------
    SWROptimizationResult
        candidate_value: Maximum feasible WR (or None).
        provenance: Selected B%, success count, LTV stats.
        diagnostic: Convergence description.
    """
    from fbf.core.optimization.part52_evaluator import DEFAULT_BORROW_PCTS

    evaluator_config = Part52EvaluatorConfig(
        data_dir=data_dir,
        initial_wealth=initial_wealth,
        drawdown_threshold=drawdown_threshold,
        debt_interest_rate=debt_interest_rate,
        ltv_limit=ltv_limit,
        ltv_enforcement=ltv_enforcement,
        ffr_dataset_identifier=ffr_dataset_identifier,
        ffr_spread=ffr_spread,
        borrow_pcts=borrow_pcts if borrow_pcts is not None else DEFAULT_BORROW_PCTS,
        workers=workers,
    )
    evaluator = Part52Evaluator(evaluator_config)

    optimizer = SWROptimizer()
    return optimizer.optimize(
        evaluator=evaluator,
        domain_min=domain_min,
        domain_max=domain_max,
        precision=precision,
    )


__all__ = [
    "SWROptimizer",
    "EvaluationOutcome",
    "SWROptimizationResult",
    "OptimizerOutcome",
    "StrategyComparator",
    "StrategyComparisonReport",
    "EvaluationResult",
    "GroupingDimension",
    "RankingRule",
    "optimize_study_swr",
    "Part52Evaluator",
    "Part52EvaluatorConfig",
    "optimize_part52",
]
