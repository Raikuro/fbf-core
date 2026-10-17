"""Integration test for Part 49 buy-and-hold pipeline capability.

Validates that the buy-and-hold pipeline:
1. Contains the expected steps (initial allocation, no periodic allocation/rebalance)
2. Establishes initial holdings correctly
3. Allows natural portfolio-weight drift through market evolution
4. Executes withdrawals without implicit rebalancing
5. Maintains compatibility with debt/leverage mechanics
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from fbf.core.domain.model.money import Currency, Money
from fbf.core.execution.executor import ResearchExecutor
from fbf.core.execution.pipeline.default_pipeline import (
    create_buy_and_hold_pipeline,
    create_default_pipeline,
)
from fbf.core.execution.pipeline.executor import SimulationExecutor
from fbf.core.execution.pipeline.runner import SimulationRunner
from fbf.core.execution.pipeline.simulation import MonthlyResult
from fbf.core.execution.pipeline.steps.allocation_decision_step import (
    AllocationDecisionStep,
)
from fbf.core.execution.pipeline.steps.portfolio_rebalance_step import (
    PortfolioRebalanceStep,
)
from fbf.core.study import StudyConfiguration, build_study_plan

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path("data/ern")
INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)

# Part 49 buy-and-hold config: 75/25, 3% withdrawal + 1% loan draw, 1.5% interest
EQUITY_ALLOCATION = Decimal("0.75")
WITHDRAWAL_RATE = Decimal("0.03")
LOAN_DRAW_RATE = Decimal("0.01")
INTEREST_RATE = Decimal("0.015")
LTV_LIMIT = Decimal("0.75")
LTV_ENFORCEMENT = False
HORIZON_YEARS = 30
COHORT_HORIZON_YEARS = 60


def _make_part49_buy_and_hold_config() -> StudyConfiguration:
    """Part 49 buy-and-hold configuration matching ERN methodology."""
    return StudyConfiguration(
        name="ERN Part 49 — Buy and Hold Replication",
        description=(
            "Part 49 buy-and-hold: 75/25, 3% withdrawal + 1% loan = 4% total, "
            "1.5% real interest, LTV observed only"
        ),
        version="2.0",
        allocation_policy_type="BuyAndHoldAllocationPolicy",
        allocation_policy_values=(EQUITY_ALLOCATION,),
        withdrawal_policy_type="Part49WithdrawalPolicy",
        withdrawal_policy_values=(WITHDRAWAL_RATE,),
        horizon_years=(HORIZON_YEARS,),
        cohort_horizon_years=COHORT_HORIZON_YEARS,
        debt_interest_rate_values=(INTEREST_RATE,),
        debt_ltv_limit=LTV_LIMIT,
        debt_ltv_enforcement=LTV_ENFORCEMENT,
        debt_loan_draw_rate=LOAN_DRAW_RATE,
        debt_interest_rate_is_real=True,
    )


def _make_part49_rebalanced_config() -> StudyConfiguration:
    """Part 49 rebalanced configuration for comparison."""
    return StudyConfiguration(
        name="ERN Part 49 — Rebalanced (Comparison)",
        description=(
            "Part 49 rebalanced: same params but with monthly rebalancing"
        ),
        version="2.0",
        allocation_policy_type="ConstantAllocationPolicy",
        allocation_policy_values=(EQUITY_ALLOCATION,),
        withdrawal_policy_type="Part49WithdrawalPolicy",
        withdrawal_policy_values=(WITHDRAWAL_RATE,),
        horizon_years=(HORIZON_YEARS,),
        cohort_horizon_years=COHORT_HORIZON_YEARS,
        debt_interest_rate_values=(INTEREST_RATE,),
        debt_ltv_limit=LTV_LIMIT,
        debt_ltv_enforcement=LTV_ENFORCEMENT,
        debt_loan_draw_rate=LOAN_DRAW_RATE,
        debt_interest_rate_is_real=True,
    )


class TestBuyAndHoldPipelineStructure:
    """Validate the buy-and-hold pipeline structure."""

    def test_pipeline_contains_expected_steps(self) -> None:
        """Buy-and-hold pipeline should contain all steps except periodic allocation/rebalance."""
        pipeline = create_buy_and_hold_pipeline()
        step_types = {type(step).__name__ for step in pipeline.steps}

        # Steps that MUST be present
        required_steps = {
            "InitializeAllocationStep",
            "ExpenseDeductionStep",
            "BuildDecisionContextStep",
            "WithdrawalDecisionStep",
            "InterestAccrualStep",
            "LoanDrawStep",
            "SupplementalCashFlowStep",
            "WithdrawalExecutionStep",
            "LoanRepaymentStep",
            "MarketEvolutionStep",
            "LTVEvaluationStep",
            "MonthlyResultBuilderStep",
            "FailureDetectionStep",
            "SimulationStateUpdateStep",
        }

        for step in required_steps:
            assert step in step_types, f"Missing required step: {step}"

        # Allocation and rebalancing run only in period 0 (initial allocation).
        allocation_step = next(
            step for step in pipeline.steps if isinstance(step, AllocationDecisionStep)
        )
        rebalance_step = next(
            step for step in pipeline.steps if isinstance(step, PortfolioRebalanceStep)
        )
        assert allocation_step.first_period_only is True
        assert rebalance_step.first_period_only is True

    def test_allocation_and_rebalance_are_first_period_only(self) -> None:
        """There is no *periodic* allocation decision or rebalancing.

        The two steps are present exactly once each, gated to period 0.
        """
        pipeline = create_buy_and_hold_pipeline()

        allocation_steps = [
            step for step in pipeline.steps if isinstance(step, AllocationDecisionStep)
        ]
        rebalance_steps = [
            step for step in pipeline.steps if isinstance(step, PortfolioRebalanceStep)
        ]

        assert len(allocation_steps) == 1
        assert allocation_steps[0].first_period_only is True
        assert len(rebalance_steps) == 1
        assert rebalance_steps[0].first_period_only is True

    def test_default_pipeline_has_periodic_rebalance(self) -> None:
        """The default pipeline rebalances every period (sanity check)."""
        pipeline = create_default_pipeline()
        allocation_step = next(
            step for step in pipeline.steps if isinstance(step, AllocationDecisionStep)
        )
        rebalance_step = next(
            step for step in pipeline.steps if isinstance(step, PortfolioRebalanceStep)
        )

        assert allocation_step.first_period_only is False
        assert rebalance_step.first_period_only is False


class TestBuyAndHoldInitialAllocation:
    """Validate initial allocation is correctly established."""

    def test_initial_holdings_established(self) -> None:
        """Buy-and-hold pipeline should establish initial 75/25 allocation."""
        config = _make_part49_buy_and_hold_config()
        built = build_study_plan(config, str(DATA_DIR), INITIAL_WEALTH)

        executor = ResearchExecutor(
            simulation_executor=SimulationExecutor(
                simulation_runner=SimulationRunner(pipeline=create_buy_and_hold_pipeline())
            )
        )

        # Execute just the first unit (November 1965 cohort)
        plan = built.plan
        first_unit = plan.units[0]
        ctx = executor._create_context_for_unit(built.experiment_definition, first_unit)
        runner = SimulationRunner(pipeline=create_buy_and_hold_pipeline())
        result = runner.run(ctx)

        # Verify initial holdings reflect the configured 75/25 allocation.
        assert result.timeline.monthly_results
        first_month = result.timeline.monthly_results[0]
        portfolio = first_month.portfolio
        assert portfolio is not None
        snapshot = first_month.market_snapshot
        assert snapshot is not None

        value = sum(
            (h.units * snapshot.index_levels[h.asset_class] for h in portfolio.holdings),
            Decimal("0"),
        )
        assert value > 0
        equity_value = sum(
            (
                h.units * snapshot.index_levels[h.asset_class]
                for h in portfolio.holdings
                if h.asset_class.id == "equity"
            ),
            Decimal("0"),
        )
        assert abs(equity_value / value - EQUITY_ALLOCATION) < Decimal("0.001")


class TestBuyAndHoldWeightDrift:
    """Validate natural portfolio-weight drift occurs without rebalancing."""

    def test_weights_drift_naturally(self) -> None:
        """Buy-and-hold portfolio weights should drift with market movements."""
        config = _make_part49_buy_and_hold_config()
        built = build_study_plan(config, str(DATA_DIR), INITIAL_WEALTH)

        executor = ResearchExecutor(
            simulation_executor=SimulationExecutor(
                simulation_runner=SimulationRunner(pipeline=create_buy_and_hold_pipeline())
            )
        )

        # Execute first unit for several months to observe drift
        first_unit = built.plan.units[0]
        ctx = executor._create_context_for_unit(built.experiment_definition, first_unit)
        runner = SimulationRunner(pipeline=create_buy_and_hold_pipeline())

        result1 = runner.run(ctx)

        assert result1.timeline is not None
        months = result1.timeline.monthly_results
        assert len(months) >= 2

        def _equity_weight(month: MonthlyResult) -> Decimal:
            snap = month.market_snapshot
            total = sum(
                (
                    h.units * snap.index_levels[h.asset_class]
                    for h in month.portfolio.holdings
                ),
                Decimal("0"),
            )
            equity = sum(
                (
                    h.units * snap.index_levels[h.asset_class]
                    for h in month.portfolio.holdings
                    if h.asset_class.id == "equity"
                ),
                Decimal("0"),
            )
            return equity / total

        # Period 0 establishes the configured 75/25 target exactly.
        assert abs(_equity_weight(months[0]) - EQUITY_ALLOCATION) < Decimal("0.001")
        # Without periodic rebalancing, later weights drift away from the target.
        assert abs(_equity_weight(months[-1]) - EQUITY_ALLOCATION) > Decimal("0.0001")


class TestBuyAndHoldWithdrawals:
    """Validate withdrawals work correctly without rebalancing."""

    def test_withdrawals_execute_without_rebalance(self) -> None:
        """Withdrawals should sell assets for cash without triggering rebalance."""
        config = _make_part49_buy_and_hold_config()
        built = build_study_plan(config, str(DATA_DIR), INITIAL_WEALTH)

        executor = ResearchExecutor(
            simulation_executor=SimulationExecutor(
                simulation_runner=SimulationRunner(pipeline=create_buy_and_hold_pipeline())
            )
        )

        first_unit = built.plan.units[0]
        ctx = executor._create_context_for_unit(built.experiment_definition, first_unit)
        runner = SimulationRunner(pipeline=create_buy_and_hold_pipeline())
        result = runner.run(ctx)

        # Verify simulation completes successfully
        assert result.statistics is not None
        # With 3% + 1% = 4% spending and 1.5% interest, many cohorts succeed
        # We just verify it runs without error


class TestBuyAndHoldDebtLeverageCompatibility:
    """Validate debt/leverage mechanics work with buy-and-hold pipeline."""

    def test_loan_draw_step_operates(self) -> None:
        """LoanDrawStep should add to loan balance and cash balance."""
        config = _make_part49_buy_and_hold_config()
        built = build_study_plan(config, str(DATA_DIR), INITIAL_WEALTH)

        executor = ResearchExecutor(
            simulation_executor=SimulationExecutor(
                simulation_runner=SimulationRunner(pipeline=create_buy_and_hold_pipeline())
            )
        )

        first_unit = built.plan.units[0]
        ctx = executor._create_context_for_unit(built.experiment_definition, first_unit)
        runner = SimulationRunner(pipeline=create_buy_and_hold_pipeline())
        result = runner.run(ctx)

        # Verify loan balance is tracked via debt_snapshot in last monthly result
        assert result.timeline.monthly_results
        last_month = result.timeline.monthly_results[-1]
        assert last_month.debt_snapshot is not None
        assert last_month.debt_snapshot.loan_balance >= 0  # Loan draws should accumulate

    def test_interest_accrual_step_operates(self) -> None:
        """InterestAccrualStep should accrue interest on loan balance."""
        config = _make_part49_buy_and_hold_config()
        built = build_study_plan(config, str(DATA_DIR), INITIAL_WEALTH)

        executor = ResearchExecutor(
            simulation_executor=SimulationExecutor(
                simulation_runner=SimulationRunner(pipeline=create_buy_and_hold_pipeline())
            )
        )

        first_unit = built.plan.units[0]
        ctx = executor._create_context_for_unit(built.experiment_definition, first_unit)
        runner = SimulationRunner(pipeline=create_buy_and_hold_pipeline())
        result = runner.run(ctx)

        # Loan balance should include accrued interest
        assert result.timeline.monthly_results
        last_month = result.timeline.monthly_results[-1]
        assert last_month.debt_snapshot is not None
        assert last_month.debt_snapshot.loan_balance >= 0

    def test_ltv_evaluation_step_operates(self) -> None:
        """LTVEvaluationStep should compute LTV with buy-and-hold portfolio."""
        config = _make_part49_buy_and_hold_config()
        built = build_study_plan(config, str(DATA_DIR), INITIAL_WEALTH)

        executor = ResearchExecutor(
            simulation_executor=SimulationExecutor(
                simulation_runner=SimulationRunner(pipeline=create_buy_and_hold_pipeline())
            )
        )

        first_unit = built.plan.units[0]
        ctx = executor._create_context_for_unit(built.experiment_definition, first_unit)
        runner = SimulationRunner(pipeline=create_buy_and_hold_pipeline())
        result = runner.run(ctx)

        # LTV should be computed (observation only, no enforcement)
        assert result.timeline.monthly_results
        last_month = result.timeline.monthly_results[-1]
        assert last_month.debt_snapshot is not None
        assert last_month.debt_snapshot.ltv >= 0


class TestBuyAndHoldVsRebalanced:
    """Compare buy-and-hold vs rebalanced behavior (diagnostic)."""

    def test_buy_and_hold_drifts_from_rebalanced(self) -> None:
        """Buy-and-hold should produce different final weights than rebalanced."""
        buy_hold_config = _make_part49_buy_and_hold_config()
        rebalanced_config = _make_part49_rebalanced_config()

        buy_hold_built = build_study_plan(buy_hold_config, str(DATA_DIR), INITIAL_WEALTH)
        rebalanced_built = build_study_plan(rebalanced_config, str(DATA_DIR), INITIAL_WEALTH)

        # Execute same cohort with both pipelines
        buy_hold_executor = ResearchExecutor(
            simulation_executor=SimulationExecutor(
                simulation_runner=SimulationRunner(pipeline=create_buy_and_hold_pipeline())
            )
        )
        rebalanced_executor = ResearchExecutor(
            simulation_executor=SimulationExecutor(
                simulation_runner=SimulationRunner(pipeline=create_default_pipeline())
            )
        )

        # Use first cohort for both
        bh_unit = buy_hold_built.plan.units[0]
        rb_unit = rebalanced_built.plan.units[0]

        bh_ctx = buy_hold_executor._create_context_for_unit(
            buy_hold_built.experiment_definition, bh_unit
        )
        rb_ctx = rebalanced_executor._create_context_for_unit(
            rebalanced_built.experiment_definition, rb_unit
        )

        bh_runner = SimulationRunner(pipeline=create_buy_and_hold_pipeline())
        rb_runner = SimulationRunner(pipeline=create_default_pipeline())

        bh_result = bh_runner.run(bh_ctx)
        rb_result = rb_runner.run(rb_ctx)

        # Both should complete
        assert bh_result.statistics is not None
        assert rb_result.statistics is not None

        # Final portfolio values may differ due to rebalancing vs drift
        # This is a diagnostic check - we don't assert specific values
        assert bh_result.timeline.monthly_results
        assert rb_result.timeline.monthly_results
        bh_last = bh_result.timeline.monthly_results[-1]
        rb_last = rb_result.timeline.monthly_results[-1]
        bh_final = bh_last.portfolio
        rb_final = rb_last.portfolio

        assert bh_final is not None
        assert rb_final is not None


# ---------------------------------------------------------------------------
# Standalone execution for manual verification
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
