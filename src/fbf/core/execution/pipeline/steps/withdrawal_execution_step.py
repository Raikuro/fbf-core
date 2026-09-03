"""Pipeline step that executes a previously requested withdrawal.

Authoritative Part 49 cash lifecycle:
- LoanDrawStep: cash_balance += loan_draw_amount
- WithdrawalExecutionStep: consume cash first, then sell portfolio assets
- End-of-period: cash_balance = 0 (all consumed for spending)

Total retirement spending = portfolio withdrawal + margin-loan draw
Both sources fund the same spending event.
"""

from __future__ import annotations

from decimal import Decimal

from fbf.core.domain.services.portfolio_withdrawal_service import (
    PortfolioWithdrawalService,
)
from fbf.core.execution.pipeline.pipeline import PipelineStep
from fbf.core.execution.pipeline.simulation import SimulationState


class WithdrawalExecutionStep(PipelineStep):
    """PipelineStep that applies the withdrawal decision to the portfolio.

    This step executes the portfolio withdrawal with cash consumption:
    1. Consume available cash from cash_balance (from loan draw)
    2. Sell portfolio assets for remaining withdrawal amount
    3. If portfolio becomes depleted, set failure_state = "depleted"

    The cash lifecycle ensures borrowed funds are consumed for spending,
    not retained as additional investment capital.

    current_wealth is always updated from the withdrawal service result
    to keep the downstream PortfolioRebalanceStep accurate.
    """

    sequence_order = 30

    def __init__(self, withdrawal_service: PortfolioWithdrawalService | None = None) -> None:
        self.withdrawal_service = withdrawal_service or PortfolioWithdrawalService()

    def execute(self, state: SimulationState) -> SimulationState:
        """Execute withdrawal with cash consumption.

        Authoritative behavior:
        - total_spending = portfolio_withdrawal_amount (from WithdrawalDecision)
        - cash_consumed = min(cash_balance, total_spending)
        - portfolio_sold = total_spending - cash_consumed
        - cash_balance -= cash_consumed
        - Sell portfolio assets worth portfolio_sold
        """
        self._validate_state(state)
        assert state.withdrawal_decision is not None
        assert state.market_snapshot is not None

        # Total spending for this period
        total_spending = state.withdrawal_decision.nominal_amount.amount

        # Consume available cash first (from loan draw)
        cash_consumed = min(state.cash_balance, total_spending)
        state.cash_balance -= cash_consumed

        # Remaining amount to be funded by portfolio sale
        portfolio_sale_amount = total_spending - cash_consumed

        if portfolio_sale_amount > 0:
            # Sell portfolio assets for the remaining amount
            from fbf.core.domain.model.money import Currency, Money
            from fbf.core.domain.policies.decisions import WithdrawalDecision

            portfolio_withdrawal = WithdrawalDecision(
                reason=state.withdrawal_decision.reason,
                nominal_amount=Money(portfolio_sale_amount, Currency.EUR),
                real_amount=Money(portfolio_sale_amount, Currency.EUR),
                loan_draw_amount=Decimal("0"),
            )

            result = self.withdrawal_service.execute_withdrawal(
                portfolio=state.portfolio,
                requested_withdrawal=portfolio_withdrawal,
                market_snapshot=state.market_snapshot,
            )

            state.portfolio = result.portfolio
            state.current_wealth = result.remaining_value

            if result.depleted:
                state.failure_state = "depleted"
        else:
            # No portfolio sale needed (fully cash-funded or zero spending).
            # Must still update current_wealth so downstream rebalance uses
            # the correct portfolio value at current market prices.
            result = self.withdrawal_service.execute_withdrawal(
                portfolio=state.portfolio,
                requested_withdrawal=state.withdrawal_decision,
                market_snapshot=state.market_snapshot,
            )
            state.current_wealth = result.remaining_value

        return state

    def _validate_state(self, state: SimulationState) -> None:
        if state.withdrawal_decision is None:
            raise ValueError("SimulationState.withdrawal_decision is required")
        if state.portfolio is None:
            raise ValueError("SimulationState.portfolio is required")
        if state.market_snapshot is None:
            raise ValueError("SimulationState.market_snapshot is required")
