from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from engine.application.steps.market_evolution_step import MarketEvolutionStep
from engine.application.simulation import SimulationState
from engine.application.simulation_context import SimulationContext
from engine.domain.model.asset import AssetClass
from engine.domain.model.allocation import Allocation
from engine.domain.model.dataset import Dataset
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.money import Money
from engine.domain.model.portfolio import AssetHolding, Portfolio
from engine.domain.policies import AllocationPolicy, WithdrawalPolicy
from engine.domain.services.portfolio_market_evolution_service import (
    PortfolioMarketEvolutionService,
)


class DummyDataset(Dataset):
    pass


class DummyMarketSnapshot(MarketSnapshot):
    pass


class DummyAllocationPolicy(AllocationPolicy):
    def decide(self, context: object):
        raise AssertionError("Should not be called")


class DummyWithdrawalPolicy(WithdrawalPolicy):
    def decide(self, context: object):
        raise AssertionError("Should not be called")


class RecordingMarketEvolutionService(PortfolioMarketEvolutionService):
    def __init__(self) -> None:
        self.calls = 0

    def apply_market_evolution(self, portfolio: Portfolio, market_snapshot: MarketSnapshot):
        self.calls += 1
        return super().apply_market_evolution(portfolio, market_snapshot)


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
    market_snapshot: MarketSnapshot,
    current_wealth: Money,
    dataset: Dataset | None = None,
) -> SimulationState:
    dataset = dataset or make_dataset(market_snapshot)
    context = make_context(portfolio, dataset)
    return SimulationState(
        context=context,
        current_date=date(2000, 1, 1),
        period_index=0,
        portfolio=portfolio,
        allocation=allocation,
        allocation_target=None,
        market_snapshot=market_snapshot,
        current_wealth=current_wealth,
        peak_wealth=current_wealth,
    )


def test_market_evolution_step_delegates_to_service() -> None:
    asset = AssetClass(id="eq", name="Equity", description="Equity")
    portfolio = Portfolio([AssetHolding(asset_class=asset, units=Decimal("100"))])
    allocation = Allocation(weights={asset: Decimal("1")})
    market_snapshot = DummyMarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={asset: Decimal("110")},
        inflation=Decimal("0.01"),
        inflation_cumulative=Decimal("0.01"),
        is_ath=False,
        is_underwater=False,
        running_ath=Decimal("110"),
    )
    service = RecordingMarketEvolutionService()
    state = make_state(portfolio, allocation, market_snapshot, Money(Decimal("10000"), Money.ZERO.currency))
    step = MarketEvolutionStep(evolution_service=service)

    updated_state = step.execute(state)

    assert updated_state is state
    assert service.calls == 1
    assert updated_state.portfolio is not portfolio
    assert updated_state.current_wealth == Money(Decimal("11000"), Money.ZERO.currency)
    assert updated_state.allocation == Allocation(weights={asset: Decimal("1")})


def test_market_evolution_step_requires_required_state() -> None:
    asset = AssetClass(id="eq", name="Equity", description="Equity")
    portfolio = Portfolio([AssetHolding(asset_class=asset, units=Decimal("100"))])
    allocation = Allocation(weights={asset: Decimal("1")})
    market_snapshot = DummyMarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={asset: Decimal("100")},
        inflation=Decimal("0.01"),
        inflation_cumulative=Decimal("0.01"),
        is_ath=False,
        is_underwater=False,
        running_ath=Decimal("100"),
    )
    state = make_state(portfolio, allocation, market_snapshot, Money(Decimal("10000"), Money.ZERO.currency))

    state.portfolio = None  # type: ignore[assignment]
    step = MarketEvolutionStep()
    with pytest.raises(ValueError, match="SimulationState.portfolio is required"):
        step.execute(state)

    state.portfolio = portfolio
    state.market_snapshot = None  # type: ignore[assignment]
    with pytest.raises(ValueError, match="SimulationState.market_snapshot is required"):
        step.execute(state)

    state.market_snapshot = market_snapshot
    state.current_wealth = None
    with pytest.raises(ValueError, match="SimulationState.current_wealth is required"):
        step.execute(state)


def test_market_evolution_step_does_not_modify_unrelated_state() -> None:
    asset = AssetClass(id="eq", name="Equity", description="Equity")
    portfolio = Portfolio([AssetHolding(asset_class=asset, units=Decimal("100"))])
    allocation = Allocation(weights={asset: Decimal("1")})
    market_snapshot = DummyMarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={asset: Decimal("110")},
        inflation=Decimal("0.01"),
        inflation_cumulative=Decimal("0.01"),
        is_ath=False,
        is_underwater=False,
        running_ath=Decimal("110"),
    )
    current_wealth = Money(Decimal("10000"), Money.ZERO.currency)
    state = make_state(portfolio, allocation, market_snapshot, current_wealth)
    step = MarketEvolutionStep()

    preserved = {
        "context": state.context,
        "current_date": state.current_date,
        "period_index": state.period_index,
        "allocation_target": state.allocation_target,
        "peak_wealth": state.peak_wealth,
        "failure_state": state.failure_state,
    }

    step.execute(state)

    assert state.context is preserved["context"]
    assert state.current_date == preserved["current_date"]
    assert state.period_index == preserved["period_index"]
    assert state.allocation_target == preserved["allocation_target"]
    assert state.peak_wealth == preserved["peak_wealth"]
    assert state.failure_state == preserved["failure_state"]
