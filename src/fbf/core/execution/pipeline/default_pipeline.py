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
from fbf.core.execution.pipeline.steps.expense_deduction_step import (
    ExpenseDeductionStep,
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
from fbf.core.execution.pipeline.steps.loan_repayment_step import LoanRepaymentStep
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

    Pipeline order (K.5.1 corrected, ERN Part 52 interest ordering):
    0: InitializeAllocation
    5: ExpenseDeduction (ERN-precise expense + C-timing correction)
    10: BuildDecisionContext
    20: WithdrawalDecision
    26: InterestAccrual (ERN: interest on prior balance BEFORE draw)
    28: LoanDraw (ERN: new draw added AFTER interest accrual)
    30: WithdrawalExecution (consume cash first, then sell assets)
    32: LoanRepayment (Part 52: repay at fresh ATH)
    40: AllocationDecision
    50: PortfolioRebalance
    60: MarketEvolution
    66: LTVEvaluation
    70: MonthlyResultBuilder
    75: FailureDetection
    80: SimulationStateUpdate

    ERN ordering (from spreadsheet):
        T(N) = Y(N-1) * (1 + M(N))    [interest on prior balance]
        Y(N) = X(N) + T(N)             [draw added after interest]

    Cash lifecycle:
    - InterestAccrualStep: loan_balance += interest (on prior balance only)
    - LoanDrawStep: cash_balance += loan_draw_amount
    - WithdrawalExecutionStep: cash_balance -= min(cash_balance, total_spending)
                                portfolio -= (total_spending - cash_consumed)
    - LoanRepaymentStep: loan_balance -= repayment (no cash change)
    - End-of-period: cash_balance = 0 (all consumed for spending)
    """
    return SimulationPipeline(
        steps=[
            InitializeAllocationStep(),
            ExpenseDeductionStep(),  # ERN-precise expense + C-timing correction
            BuildDecisionContextStep(),
            WithdrawalDecisionStep(),
            InterestAccrualStep(),  # BEFORE draw: interest on prior balance (ERN order)
            LoanDrawStep(),  # AFTER interest: new draw does not accrue interest same month
            WithdrawalExecutionStep(),  # Consume cash first, then sell assets
            LoanRepaymentStep(),  # Part 52: repay at fresh ATH
            AllocationDecisionStep(),
            PortfolioRebalanceStep(),
            MarketEvolutionStep(),
            LTVEvaluationStep(),
            MonthlyResultBuilderStep(),
            FailureDetectionStep(),
            SimulationStateUpdateStep(),
        ]
    )
