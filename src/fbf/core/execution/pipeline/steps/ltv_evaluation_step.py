"""Pipeline step that evaluates LTV and executes margin calls (Part 49).

This step implements Step 8 of the K.1 semantic contract:
- Compute portfolio_value at end-of-period prices
- Compute ltv = loan_balance / portfolio_value (if loan_balance > 0, else 0)
- If ltv > ltv_limit:
  - MARGIN CALL TRIGGERED
  - liquidation_amount = (loan_balance - ltv_limit × portfolio_value) / (1 - ltv_limit)
  - If liquidation_amount > portfolio_value:
    - Sell entire portfolio
    - Repay loan by liquidation_amount
    - (Failure detection is handled by FailureDetectionStep)
  - Else:
    - Sell assets worth liquidation_amount
    - Repay loan by liquidation_amount
    - LTV is now exactly ltv_limit
"""

from __future__ import annotations

from decimal import Decimal

from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.execution.pipeline.pipeline import PipelineStep
from fbf.core.execution.pipeline.simulation import SimulationState


class LTVEvaluationStep(PipelineStep):
    """PipelineStep that evaluates LTV and executes margin calls.

    This step enforces the LTV constraint and handles margin calls.
    Liquidation restores LTV to the limit when mathematically possible.
    Failure detection is handled by FailureDetectionStep.
    """

    sequence_order = 66

    def execute(self, state: SimulationState) -> SimulationState:
        self._validate_state(state)

        # If no debt is configured, this is a no-op
        if state.interest_rate <= 0:
            return state

        # If no loan balance, no LTV evaluation needed
        if state.loan_balance <= 0:
            return state

        # Calculate current portfolio value
        portfolio_value = self._calculate_portfolio_value(state)

        # If portfolio is zero, liquidation is not possible
        # FailureDetectionStep will handle this as insolvency
        if portfolio_value <= 0:
            return state

        # Calculate LTV
        ltv = state.loan_balance / portfolio_value

        # Check if LTV exceeds limit
        if ltv <= state.ltv_limit:
            # No margin call needed
            return state

        # Margin call triggered
        liquidation_amount = self._calculate_liquidation(
            state.loan_balance, portfolio_value, state.ltv_limit
        )

        # Check if liquidation is possible
        if liquidation_amount > portfolio_value:
            # Unsatisfiable margin call
            # Sell entire portfolio and repay loan
            state.portfolio = self._execute_liquidation(
                state.portfolio, portfolio_value, state.market_snapshot
            )
            state.loan_balance -= portfolio_value
            # FailureDetectionStep will detect this as unsatisfiable margin call
            return state

        # Execute liquidation: sell assets and repay loan
        state.portfolio = self._execute_liquidation(
            state.portfolio, liquidation_amount, state.market_snapshot
        )

        # Reduce loan balance by liquidation amount (proceeds repay loan)
        state.loan_balance -= liquidation_amount

        return state

    def _calculate_liquidation(
        self,
        loan_balance: Decimal,
        portfolio_value: Decimal,
        ltv_limit: Decimal,
    ) -> Decimal:
        """Calculate the liquidation amount required to restore LTV to the limit.

        Formula: liquidation_amount = (loan_balance - ltv_limit × portfolio_value) / (1 - ltv_limit)

        This formula accounts for the proportional reduction in both portfolio
        and debt when proceeds are used to repay the loan.
        """
        numerator = loan_balance - ltv_limit * portfolio_value
        denominator = Decimal("1") - ltv_limit

        if denominator <= 0:
            # ltv_limit >= 1.0 is invalid; return the full portfolio
            return portfolio_value

        return numerator / denominator

    def _calculate_portfolio_value(self, state: SimulationState) -> Decimal:
        """Calculate the current portfolio value."""
        if state.market_snapshot is None:
            return Decimal("0")

        total = Decimal("0")
        for holding in state.portfolio.holdings:
            price = state.market_snapshot.index_levels.get(holding.asset_class)
            if price is not None:
                total += holding.units * price
        return total

    def _execute_liquidation(
        self,
        portfolio: Portfolio,
        liquidation_amount: Decimal,
        market_snapshot: MarketSnapshot | None,
    ) -> Portfolio:
        """Execute liquidation by selling assets proportionally.

        Assets are sold proportionally to current holdings to maintain
        the target allocation after the forced sale.
        """
        if market_snapshot is None:
            return portfolio

        # Calculate total portfolio value
        total_value = Decimal("0")
        for holding in portfolio.holdings:
            price = market_snapshot.index_levels.get(holding.asset_class)
            if price is not None:
                total_value += holding.units * price

        if total_value <= 0:
            return portfolio

        # Calculate the fraction to sell
        sell_fraction = liquidation_amount / total_value

        # Sell assets proportionally
        new_holdings = []
        for holding in portfolio.holdings:
            price = market_snapshot.index_levels.get(holding.asset_class)
            if price is not None:
                # Sell fraction of this holding
                units_sold = holding.units * sell_fraction
                remaining_units = holding.units - units_sold
                if remaining_units > 0:
                    new_holdings.append(
                        AssetHolding(
                            asset_class=holding.asset_class,
                            units=remaining_units,
                        )
                    )

        return Portfolio(holdings=tuple(new_holdings))

    def _validate_state(self, state: SimulationState) -> None:
        if state.portfolio is None:
            raise ValueError("SimulationState.portfolio is required")
        if state.market_snapshot is None:
            raise ValueError("SimulationState.market_snapshot is required")
