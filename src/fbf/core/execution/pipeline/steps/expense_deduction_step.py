"""Pipeline step that applies ERN-precise expense and timing correction.

This implements the canonical ERN Part 52 formula EXACTLY:

    P_t = (P_{t-1} - C + D_{t-1}) * (1 + w_real - expense_ratio / 12)

The snapshot change implicitly applies the market return w_real by revaluing
the same units at new prices.  This step then deducts:

    total = V_{t-1} * exp/12 + (C - D_{t-1}) * r_t

where r_t = w_t - exp/12 and D_{t-1} is the previous period's net loan
draw/repay.

After this step and WithdrawalExecution subtracting (C - D_t), the result
is the canonical P_t (exact when D_t = D_{t-1}, i.e., constant loan draw).
"""

from __future__ import annotations

from decimal import Decimal

from fbf.core.execution.pipeline.pipeline import PipelineStep
from fbf.core.execution.pipeline.simulation import SimulationState


class ExpenseDeductionStep(PipelineStep):
    """Applies ERN-precise expense and timing correction.

    Runs at sequence_order=5 (after InitializeAllocation, before
    BuildDecisionContext).  The snapshot has already been advanced by the
    previous period's SimulationStateUpdateStep, so the portfolio is now
    valued at current-period prices, implicitly including the market return
    w_t.

    This step:
    1. Computes the weighted real return w_t from the snapshot change
    2. Computes r_t = w_t - exp/12
    3. Deducts expense: V_{t-1} * exp/12
    4. Deducts timing correction: (C - D_{t-1}) * r_t
    5. Scales portfolio units proportionally

    Total deduction: expense + timing = V_{t-1}*exp/12 + (C - D_{t-1})*r_t

    Skipped at period 0 (no prior period to correct for).
    """

    sequence_order = 5

    def execute(self, state: SimulationState) -> SimulationState:
        self._validate_state(state)

        if state.period_index == 0:
            return state

        if state.previous_portfolio_value <= 0:
            return state

        expense_ratio = state.context.expense_ratio or Decimal("0")
        exp_monthly = expense_ratio / Decimal("12")

        if exp_monthly == Decimal("0"):
            return state

        assert state.market_snapshot is not None
        current_value = Decimal("0")
        for holding in state.portfolio.holdings:
            price = state.market_snapshot.index_levels.get(holding.asset_class)
            if price is not None:
                current_value += holding.units * price

        if current_value <= 0:
            return state

        v_prev = state.previous_portfolio_value

        w_t = current_value / v_prev - Decimal("1")

        r_t = w_t - exp_monthly

        expense = v_prev * exp_monthly

        c_monthly = self._get_canonical_c(state)
        d_prev = state.previous_draw_repay
        timing_correction = (c_monthly - d_prev) * r_t

        total_deduction = expense + timing_correction

        new_value = current_value - total_deduction
        if new_value <= 0:
            return state

        scale_factor = new_value / current_value

        from fbf.core.domain.model.portfolio import AssetHolding, Portfolio

        new_holdings = []
        for holding in state.portfolio.holdings:
            new_units = holding.units * scale_factor
            new_holdings.append(
                AssetHolding(asset_class=holding.asset_class, units=new_units)
            )
        state.portfolio = Portfolio(tuple(new_holdings))

        from fbf.core.domain.model.money import Currency, Money

        state.current_wealth = Money(new_value, Currency.EUR)

        return state

    def _get_canonical_c(self, state: SimulationState) -> Decimal:
        """Return the cached canonical monthly withdrawal C."""
        if state.canonical_c is not None:
            return state.canonical_c

        ctx = state.context
        if ctx.withdrawal_policy is None:
            return Decimal("0")

        rate = getattr(ctx.withdrawal_policy, "withdrawal_rate", None)
        if rate is None:
            return Decimal("0")

        initial_wealth = ctx.initial_wealth
        if initial_wealth is None:
            return Decimal("0")

        return Decimal(str(rate)) * initial_wealth.amount / Decimal("12")

    def _validate_state(self, state: SimulationState) -> None:
        if state.portfolio is None:
            raise ValueError("SimulationState.portfolio is required")
        if state.market_snapshot is None:
            raise ValueError("SimulationState.market_snapshot is required")
        if state.context is None:
            raise ValueError("SimulationState.context is required")
