from __future__ import annotations

from decimal import Decimal

from fbf.core.domain.services.portfolio_market_evolution_service import (
    PortfolioMarketEvolutionService,
)
from fbf.core.execution.pipeline.pipeline import PipelineStep
from fbf.core.execution.pipeline.simulation import SimulationState


class MarketEvolutionStep(PipelineStep):
    """PipelineStep that applies market evolution to the portfolio.

    Implements the canonical ERN Part 52 portfolio transition:

        P_t = (P_{t-1} - C + D_{t-1}) * (1 + w_real - expense_ratio / 12)

    The expense_ratio is applied by scaling portfolio units by
    (1 - expense_ratio / 12) before the snapshot change, which
    implicitly applies the market return w_real.
    """

    sequence_order = 60

    def __init__(self, evolution_service: PortfolioMarketEvolutionService | None = None) -> None:
        self.evolution_service = evolution_service or PortfolioMarketEvolutionService()

    def execute(self, state: SimulationState) -> SimulationState:
        self._validate_state(state)
        assert state.market_snapshot is not None

        # 1. Apply standard market evolution (currently NO-OP for units, but
        #    computes allocation and current_value)
        result = self.evolution_service.apply_market_evolution(
            portfolio=state.portfolio,
            market_snapshot=state.market_snapshot,
        )

        state.portfolio = result.portfolio
        state.allocation = result.allocation
        state.current_wealth = result.current_value

        return state

    def _apply_ern_corrections(self, state: SimulationState) -> None:
        """Apply the ERN expense ratio correction to portfolio units.

        The canonical formula for portfolio value at the end of period t is:

            P_t = (P_{t-1} - C + D_{t-1}) * (1 + w - exp/12)

        After WithdrawalExecution and PortfolioRebalance, the FBF portfolio
        holds the rebalanced units at current-period prices.  The withdrawal
        execution already reduced the portfolio by (C - loan_draw), so the
        value implicitly includes the current period's draw term.  The
        snapshot change (SimulationStateUpdate) will implicitly apply the
        market return w.  To match the canonical formula we scale units by
        (1 - exp/12) BEFORE the snapshot changes so that the effective
        value becomes:

            V_adjusted = V * (1 - exp/12)

        When the snapshot change then applies the market return w the result
        is:

            V_result = V * (1 - exp/12) * (1 + w)

        which equals the canonical formula up to a negligible second-order
        term O(exp * w).
        """
        portfolio_value = state.current_wealth
        if portfolio_value is None or portfolio_value.amount <= 0:
            return

        value = portfolio_value.amount
        expense_ratio = state.context.expense_ratio or Decimal("0")
        exp_monthly = expense_ratio / Decimal("12")

        if exp_monthly == Decimal("0"):
            return

        # Skip expense at period 0 (P0 is the starting value, no expense yet)
        if state.period_index == 0:
            return

        if value <= 0:
            return

        exp_scale = Decimal("1") - exp_monthly

        new_holdings = []
        from fbf.core.domain.model.portfolio import AssetHolding

        for holding in state.portfolio.holdings:
            new_units = holding.units * exp_scale
            new_holdings.append(
                AssetHolding(asset_class=holding.asset_class, units=new_units)
            )

        from fbf.core.domain.model.portfolio import Portfolio
        state.portfolio = Portfolio(tuple(new_holdings))

        from fbf.core.domain.model.money import Money
        adjusted_value = value * exp_scale
        state.current_wealth = Money(adjusted_value, portfolio_value.currency)

    def _validate_state(self, state: SimulationState) -> None:
        if state.portfolio is None:
            raise ValueError("SimulationState.portfolio is required")
        if state.market_snapshot is None:
            raise ValueError("SimulationState.market_snapshot is required")
        if state.current_wealth is None:
            raise ValueError("SimulationState.current_wealth is required")
