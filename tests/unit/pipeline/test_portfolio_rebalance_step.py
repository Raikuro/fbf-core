from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import NoReturn

import pytest

from fbf.core.domain.model.allocation import Allocation, AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies import AllocationPolicy, WithdrawalPolicy
from fbf.core.domain.policies.decisions import AllocationDecision
from fbf.core.domain.services.portfolio_rebalance_service import (
    PortfolioRebalanceResult,
    PortfolioRebalanceService,
)
from fbf.core.execution.pipeline.simulation import SimulationState
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.pipeline.steps.portfolio_rebalance_step import PortfolioRebalanceStep


class DummyDataset(Dataset):
    pass


class DummyMarketSnapshot(MarketSnapshot):
    pass


class DummyWithdrawalPolicy(WithdrawalPolicy):
    def decide(self, context: object) -> NoReturn:
        raise AssertionError("Should not be called")


class DummyAllocationPolicy(AllocationPolicy):
    def decide(self, context: object) -> NoReturn:
        raise AssertionError("Should not be called")


class RecordingRebalanceService(PortfolioRebalanceService):
    def __init__(self) -> None:
        self.calls = 0

    def execute_rebalance(
        self,
        portfolio: Portfolio,
        allocation_decision: AllocationDecision,
        market_snapshot: MarketSnapshot,
        *,
        portfolio_value: Money | None = None,
    ) -> PortfolioRebalanceResult:
        self.calls += 1
        return super().execute_rebalance(
            portfolio, allocation_decision, market_snapshot, portfolio_value=portfolio_value
        )


def make_context(portfolio: Portfolio, dataset: Dataset) -> SimulationContext:
    return SimulationContext(
        experiment_name="test",
        cohort="A",
        start_date=date(2000, 1, 1),
        horizon_months=1,
        initial_wealth=Money(Decimal("1000"), Money.ZERO.currency),
        initial_portfolio=portfolio,
        dataset=dataset,
        allocation_policy=DummyAllocationPolicy(),
        withdrawal_policy=DummyWithdrawalPolicy(),
    )


def make_dataset(market_snapshot: MarketSnapshot) -> Dataset:
    return DummyDataset(snapshots=[market_snapshot], frequency="M", version="1.0")


def make_state(
    portfolio: Portfolio,
    allocation: Allocation,
    allocation_target: AllocationTarget,
    market_snapshot: MarketSnapshot,
    rebalance_service: PortfolioRebalanceService | None = None,
) -> SimulationState:
    dataset = make_dataset(market_snapshot)
    context = make_context(portfolio, dataset)
    state = SimulationState(
        context=context,
        current_date=date(2000, 1, 1),
        period_index=0,
        portfolio=portfolio,
        allocation=allocation,
        allocation_target=allocation_target,
        market_snapshot=market_snapshot,
        current_wealth=Money(Decimal("1000"), Money.ZERO.currency),
        peak_wealth=Money(Decimal("1000"), Money.ZERO.currency),
    )
    state.allocation_decision = AllocationDecision(
        reason="test",
        allocation_target=allocation_target,
    )
    return state


def test_portfolio_rebalance_step_delegates_to_service() -> None:
    asset = AssetClass(id="eq", name="Equity", description="Equity")
    portfolio = Portfolio([AssetHolding(asset_class=asset, units=Decimal("100"))])
    allocation = Allocation(weights={asset: Decimal("1")})
    allocation_target = AllocationTarget(weights={asset: Decimal("1")})
    market_snapshot = DummyMarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={asset: Decimal("100")},
        inflation=Decimal("0.01"),
        inflation_cumulative=Decimal("0.01"),
        is_ath=False,
        is_underwater=False,
        running_ath=Decimal("100"),
    )
    service = RecordingRebalanceService()
    state = make_state(portfolio, allocation, allocation_target, market_snapshot)
    step = PortfolioRebalanceStep(rebalance_service=service)

    updated_state = step.execute(state)

    assert updated_state is state
    assert service.calls == 1
    assert updated_state.portfolio is not portfolio
    assert updated_state.allocation == allocation
    assert updated_state.allocation_target == allocation_target
    assert updated_state.current_wealth == Money(Decimal("1000"), Money.ZERO.currency)


def test_portfolio_rebalance_step_raises_when_missing_allocation_decision() -> None:
    asset = AssetClass(id="eq", name="Equity", description="Equity")
    portfolio = Portfolio([AssetHolding(asset_class=asset, units=Decimal("100"))])
    allocation = Allocation(weights={asset: Decimal("1")})
    allocation_target = AllocationTarget(weights={asset: Decimal("1")})
    market_snapshot = DummyMarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={asset: Decimal("100")},
        inflation=Decimal("0.01"),
        inflation_cumulative=Decimal("0.01"),
        is_ath=False,
        is_underwater=False,
        running_ath=Decimal("100"),
    )
    state = make_state(portfolio, allocation, allocation_target, market_snapshot)
    state.allocation_decision = None
    step = PortfolioRebalanceStep()

    with pytest.raises(ValueError, match="SimulationState.allocation_decision is required"):
        step.execute(state)


def test_portfolio_rebalance_step_does_not_modify_unrelated_state() -> None:
    asset = AssetClass(id="eq", name="Equity", description="Equity")
    portfolio = Portfolio([AssetHolding(asset_class=asset, units=Decimal("100"))])
    allocation = Allocation(weights={asset: Decimal("1")})
    allocation_target = AllocationTarget(weights={asset: Decimal("1")})
    market_snapshot = DummyMarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={asset: Decimal("100")},
        inflation=Decimal("0.01"),
        inflation_cumulative=Decimal("0.01"),
        is_ath=False,
        is_underwater=False,
        running_ath=Decimal("100"),
    )
    state = make_state(portfolio, allocation, allocation_target, market_snapshot)
    step = PortfolioRebalanceStep()

    preserved = {
        "context": state.context,
        "current_date": state.current_date,
        "period_index": state.period_index,
        "peak_wealth": state.peak_wealth,
        "failure_state": state.failure_state,
    }

    step.execute(state)

    assert state.context is preserved["context"]
    assert state.current_date == preserved["current_date"]
    assert state.period_index == preserved["period_index"]
    assert state.peak_wealth == preserved["peak_wealth"]
    assert state.failure_state == preserved["failure_state"]
