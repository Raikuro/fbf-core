"""Pipeline step that constructs a DecisionContext for the current month."""

from __future__ import annotations

from decimal import Decimal

from fbf.core.domain.model.decision_context import DebtInfo, DecisionContext
from fbf.core.execution.pipeline.pipeline import PipelineStep
from fbf.core.execution.pipeline.simulation import SimulationState


class BuildDecisionContextStep(PipelineStep):
    """PipelineStep that builds the domain DecisionContext."""

    sequence_order = 10

    def execute(self, state: SimulationState) -> SimulationState:
        self._validate_state(state)
        assert state.allocation is not None
        assert state.allocation_target is not None
        assert state.market_snapshot is not None

        # Build DebtInfo if debt is active
        debt_info = None
        if state.interest_rate > 0:
            # Compute portfolio value for net_worth derivation
            portfolio_value = Decimal("0")
            for holding in state.portfolio.holdings:
                price = state.market_snapshot.index_levels.get(holding.asset_class, Decimal("0"))
                portfolio_value += holding.units * price

            debt_info = DebtInfo(
                loan_balance=state.loan_balance,
                interest_rate=state.interest_rate,
                ltv_limit=state.ltv_limit,
                portfolio_value=portfolio_value,
            )

        decision_context = DecisionContext(
            date=state.current_date,
            period_index=state.period_index,
            simulation_context=state.context,
            portfolio=state.portfolio,
            current_allocation=state.allocation,
            target_allocation=state.allocation_target,
            market_snapshot=state.market_snapshot,
            dataset=state.context.dataset,
            debt_info=debt_info,
        )

        state.decision_context = decision_context
        return state

    def _validate_state(self, state: SimulationState) -> None:
        if state.portfolio is None:
            raise ValueError("SimulationState.portfolio is required")
        if state.allocation is None:
            raise ValueError("SimulationState.allocation is required")
        if state.allocation_target is None:
            raise ValueError("SimulationState.allocation_target is required")
        if state.market_snapshot is None:
            raise ValueError("SimulationState.market_snapshot is required")
        if state.context is None:
            raise ValueError("SimulationState.context is required")
        if state.context.dataset is None:
            raise ValueError("SimulationContext.dataset is required")
        if state.current_date is None:
            raise ValueError("SimulationState.current_date is required")
        if state.period_index is None:
            raise ValueError("SimulationState.period_index is required")
