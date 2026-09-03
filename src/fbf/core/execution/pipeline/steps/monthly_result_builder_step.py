from __future__ import annotations

from decimal import Decimal

from fbf.core.execution.pipeline.pipeline import PipelineStep
from fbf.core.execution.pipeline.simulation import DebtSnapshot, MonthlyResult, SimulationState


class MonthlyResultBuilderStep(PipelineStep):
    """PipelineStep that captures the current state into a MonthlyResult."""

    sequence_order = 70

    def execute(self, state: SimulationState) -> SimulationState:
        self._validate_state(state)
        assert state.market_snapshot is not None

        # Build debt snapshot if debt is configured
        debt_snapshot = None
        if state.interest_rate > 0:
            # Compute LTV
            portfolio_value = Decimal("0")
            for holding in state.portfolio.holdings:
                price = state.market_snapshot.index_levels.get(holding.asset_class)
                if price is not None:
                    portfolio_value += holding.units * price

            ltv = Decimal("0")
            if portfolio_value > 0 and state.loan_balance > 0:
                ltv = state.loan_balance / portfolio_value

            net_worth = portfolio_value - state.loan_balance

            debt_snapshot = DebtSnapshot(
                loan_balance=state.loan_balance,
                cash_balance=state.cash_balance,
                ltv=ltv,
                net_worth=net_worth,
            )

        monthly_result = MonthlyResult(
            date=state.current_date,
            period_index=state.period_index,
            market_snapshot=state.market_snapshot,
            portfolio=state.portfolio,
            allocation=state.allocation,
            allocation_target=state.allocation_target,
            allocation_drift=state.allocation_drift,
            withdrawal_decision=state.withdrawal_decision,
            rebalance_result=None,
            drawdown=0.0,
            cumulative_return=0.0,
            cumulative_inflation=0.0,
            events=(),
            debt_snapshot=debt_snapshot,
        )

        state.monthly_results.append(monthly_result)
        return state

    def _validate_state(self, state: SimulationState) -> None:
        if state.current_date is None:
            raise ValueError("SimulationState.current_date is required")
        if state.period_index is None:
            raise ValueError("SimulationState.period_index is required")
        if state.portfolio is None:
            raise ValueError("SimulationState.portfolio is required")
        if state.market_snapshot is None:
            raise ValueError("SimulationState.market_snapshot is required")
        if state.current_wealth is None:
            raise ValueError("SimulationState.current_wealth is required")
        if state.monthly_results is None:
            raise ValueError("SimulationState.monthly_results is required")
        if not isinstance(state.monthly_results, list):
            raise TypeError("SimulationState.monthly_results must be a list")
