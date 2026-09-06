"""Part 52 timing-leverage evaluator for SWR optimization.

Implements the Evaluator protocol for use with SWROptimizer to find the
maximum withdrawal rate where all cohorts succeed with timing leverage.

The evaluator tests each candidate withdrawal rate against a grid of
Borrow% values, returning success if any Borrow% achieves full cohort
feasibility (all cohorts survive and meet the terminal wealth target).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from fbf.core.domain.model.money import Money
from fbf.core.execution import (
    ExecutionOptions,
    ExecutionStrategy,
    execute_study_plan,
)
from fbf.core.optimization.swr_optimizer import EvaluationOutcome
from fbf.core.study import StudyConfiguration, build_study_plan

# Default Borrow% grid for Part 52 optimization.
# Includes 0% (non-leveraged baseline) through 50% in 10% steps.
DEFAULT_BORROW_PCTS: tuple[Decimal, ...] = tuple(
    Decimal(p) / Decimal("100") for p in range(0, 51, 10)
)


@dataclass(frozen=True)
class Part52EvaluatorConfig:
    """Configuration for the Part 52 evaluator.

    Attributes
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
        Maximum loan-to-value ratio (e.g. 0.50 for 50%).
    ltv_enforcement:
        Whether the engine enforces LTV limits via margin calls.
    ffr_dataset_identifier:
        FFR dataset identifier for floating-rate interest (None for fixed).
    ffr_spread:
        Spread over FFR for floating-rate interest (None for fixed).
    borrow_pcts:
        Grid of Borrow% values to test.
    horizon_years:
        Simulation horizon in years.
    cohort_horizon_years:
        Cohort generation horizon (ERN uses 60y for comparability).
    workers:
        Number of parallel workers (None for auto).
    """

    data_dir: str
    initial_wealth: Money
    drawdown_threshold: Decimal
    debt_interest_rate: Decimal
    ltv_limit: Decimal = Decimal("0.50")
    ltv_enforcement: bool = True
    ffr_dataset_identifier: str | None = None
    ffr_spread: Decimal | None = None
    borrow_pcts: tuple[Decimal, ...] = DEFAULT_BORROW_PCTS
    horizon_years: int = 30
    cohort_horizon_years: int = 60
    workers: int | None = None


class Part52Evaluator:
    """Evaluator for Part 52 timing-leverage SWR optimization.

    Tests each candidate withdrawal rate against a grid of Borrow% values.
    Returns success if any Borrow% achieves full cohort feasibility.

    This evaluator delegates simulation execution to the existing optimized
    execution path (fast path + parallel workers), creating no duplicate
    worker or batching logic.
    """

    def __init__(self, config: Part52EvaluatorConfig) -> None:
        self._config = config

    def evaluate(self, candidate: Any) -> EvaluationOutcome:
        """Evaluate a candidate withdrawal rate.

        Parameters
        ----------
        candidate:
            The withdrawal rate to evaluate (Decimal, e.g. Decimal("0.0391")).

        Returns
        -------
        EvaluationOutcome
            success=True if any Borrow% achieves all-cohort feasibility.
            provenance includes the selected B%, success count, and LTV stats.
        """
        wr = Decimal(str(candidate))
        config = self._config
        best_outcome: EvaluationOutcome | None = None

        for b_pct in config.borrow_pcts:
            outcome = self._evaluate_single(wr, b_pct)
            if outcome.success:
                return outcome
            if best_outcome is None:
                best_outcome = outcome

        return best_outcome or EvaluationOutcome(
            success=False,
            provenance={"error": "no B% values tested"},
        )

    def _evaluate_single(self, wr: Decimal, b_pct: Decimal) -> EvaluationOutcome:
        """Evaluate one (WR, B%) combination."""
        config = self._config

        study_config = StudyConfiguration(
            name=f"part52_opt_wr={wr}_b={b_pct}",
            description="Part 52 SWR optimization evaluation",
            version="1.0",
            dataset_identifier="ern_swr_h720",
            allocation_policy_type="ConstantAllocationPolicy",
            allocation_policy_values=(Decimal("0.75"),),
            withdrawal_policy_type="Part52WithdrawalPolicy",
            withdrawal_policy_values=(wr,),
            horizon_years=(config.horizon_years,),
            cohort_horizon_years=config.cohort_horizon_years,
            debt_interest_rate=config.debt_interest_rate,
            debt_ltv_limit=config.ltv_limit,
            debt_ltv_enforcement=config.ltv_enforcement,
            debt_borrow_pct=b_pct,
            debt_drawdown_threshold=config.drawdown_threshold,
            ffr_dataset_identifier=config.ffr_dataset_identifier,
            ffr_spread=config.ffr_spread,
        )

        built = build_study_plan(study_config, config.data_dir, config.initial_wealth)

        options = ExecutionOptions(
            strategy=ExecutionStrategy.AUTO,
            workers=config.workers,
        )

        result = execute_study_plan(built, options)

        sims = result.results
        total = len(sims)
        successful = sum(1 for s in sims if s.statistics.success)
        all_success = successful == total

        # Compute max post-liquidation LTV across all cohorts
        max_ltv = Decimal("0")
        for sim in sims:
            for mr in sim.timeline.monthly_results:
                if mr.debt_snapshot and mr.debt_snapshot.ltv > max_ltv:
                    max_ltv = mr.debt_snapshot.ltv

        provenance: dict[str, Any] = {
            "withdrawal_rate": str(wr),
            "borrow_pct": str(b_pct),
            "success_count": successful,
            "total_count": total,
            "all_success": all_success,
            "max_post_enforcement_ltv": str(max_ltv),
            "ltv_limit": str(config.ltv_limit),
            "ltv_enforcement": config.ltv_enforcement,
        }

        return EvaluationOutcome(success=all_success, provenance=provenance)
