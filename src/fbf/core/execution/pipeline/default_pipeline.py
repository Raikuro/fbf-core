"""Default pipeline configuration for simulations with debt support.

This module provides a factory function to create a pipeline that includes
the debt-related steps (loan draw, interest accrual, LTV evaluation,
failure detection).
"""

from __future__ import annotations

from fbf.core.execution.pipeline.pipeline import SimulationPipeline
from fbf.core.execution.pipeline.steps.allocation_decision_step import (
    AllocationDecisionStep,
)
from fbf.core.execution.pipeline.steps.build_decision_context_step import (
    BuildDecisionContextStep,
)
from fbf.core.execution.pipeline.steps.failure_detection_step import (
    FailureDetectionStep,
)
from fbf.core.execution.pipeline.steps.initialize_allocation_step import (
    InitializeAllocationStep,
)
from fbf.core.execution.pipeline.steps.interest_accrual_step import (
    InterestAccrualStep,
)
from fbf.core.execution.pipeline.steps.loan_draw_step import LoanDrawStep
from fbf.core.execution.pipeline.steps.ltv_evaluation_step import LTVEvaluationStep
from fbf.core.execution.pipeline.steps.market_evolution_step import MarketEvolutionStep
from fbf.core.execution.pipeline.steps.monthly_result_builder_step import (
    MonthlyResultBuilderStep,
)
from fbf.core.execution.pipeline.steps.portfolio_rebalance_step import (
    PortfolioRebalanceStep,
)
from fbf.core.execution.pipeline.steps.simulation_state_update_step import (
    SimulationStateUpdateStep,
)
from fbf.core.execution.pipeline.steps.withdrawal_decision_step import (
    WithdrawalDecisionStep,
)
from fbf.core.execution.pipeline.steps.withdrawal_execution_step import (
    WithdrawalExecutionStep,
)


def create_default_pipeline() -> SimulationPipeline:
    """Create the default pipeline with debt support.

    Pipeline order (matching K.1 semantic contract and S4 Design Review):
    10: InitializeAllocation
    20: BuildDecisionContext
    25: WithdrawalDecision
    30: WithdrawalExecution (sell assets to raise cash)
    35: LoanDraw (borrow from margin - AFTER withdrawal per S4 Design Review)
    40: AllocationDecision
    50: PortfolioRebalance
    60: MarketEvolution
    65: InterestAccrual
    66: LTVEvaluation
    70: MonthlyResultBuilder
    75: FailureDetection
    80: SimulationStateUpdate
    """
    return SimulationPipeline(
        steps=[
            InitializeAllocationStep(),
            BuildDecisionContextStep(),
            WithdrawalDecisionStep(),
            WithdrawalExecutionStep(),  # After withdrawal - sell assets first
            LoanDrawStep(),  # After withdrawal - borrowed funds NOT for current withdrawal
            AllocationDecisionStep(),
            PortfolioRebalanceStep(),
            MarketEvolutionStep(),
            InterestAccrualStep(),
            LTVEvaluationStep(),
            MonthlyResultBuilderStep(),
            FailureDetectionStep(),
            SimulationStateUpdateStep(),
        ]
    )
