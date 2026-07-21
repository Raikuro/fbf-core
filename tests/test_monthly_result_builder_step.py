from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from engine.application.steps.monthly_result_builder_step import MonthlyResultBuilderStep
from engine.application.simulation import SimulationState, MonthlyResult
from engine.application.simulation_context import SimulationContext
from engine.domain.model.asset import AssetClass
from engine.domain.model.allocation import Allocation, AllocationTarget
from engine.domain.model.dataset import Dataset
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.money import Money
from engine.domain.model.portfolio import AssetHolding, Portfolio
from engine.domain.policies import AllocationPolicy, WithdrawalPolicy


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
    allocation: Allocation | None,
    market_snapshot: MarketSnapshot,
    current_wealth: Money,
) -> SimulationState:
    dataset = make_dataset(market_snapshot)
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


def test_monthly_result_builder_appends_result() -> None:
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
    step = MonthlyResultBuilderStep()

    updated_state = step.execute(state)

    assert updated_state is state
    assert len(updated_state.monthly_results) == 1
    result = updated_state.monthly_results[0]
    assert isinstance(result, MonthlyResult)
    assert result.date == state.current_date
    assert result.period_index == state.period_index
    assert result.market_snapshot == state.market_snapshot
    assert result.portfolio == state.portfolio
    assert result.allocation == state.allocation


def test_monthly_result_builder_requires_required_state() -> None:
    asset = AssetClass(id="eq", name="Equity", description="Equity")
    portfolio = Portfolio([AssetHolding(asset_class=asset, units=Decimal("100"))])
    market_snapshot = DummyMarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={asset: Decimal("100")},
        inflation=Decimal("0.01"),
        inflation_cumulative=Decimal("0.01"),
        is_ath=False,
        is_underwater=False,
        running_ath=Decimal("100"),
    )
    state = make_state(portfolio, None, market_snapshot, Money(Decimal("10000"), Money.ZERO.currency))
    step = MonthlyResultBuilderStep()

    state.current_date = None  # type: ignore[assignment]
    with pytest.raises(ValueError, match="SimulationState.current_date is required"):
        step.execute(state)

    state.current_date = date(2000, 1, 1)
    state.period_index = None  # type: ignore[assignment]
    with pytest.raises(ValueError, match="SimulationState.period_index is required"):
        step.execute(state)

    state.period_index = 0
    state.portfolio = None  # type: ignore[assignment]
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


def test_monthly_result_builder_does_not_mutate_other_state() -> None:
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
    current_wealth = Money(Decimal("10000"), Money.ZERO.currency)
    state = make_state(portfolio, allocation, market_snapshot, current_wealth)
    step = MonthlyResultBuilderStep()

    preserved = {
        "context": state.context,
        "current_date": state.current_date,
        "period_index": state.period_index,
        "portfolio": state.portfolio,
        "allocation": state.allocation,
        "market_snapshot": state.market_snapshot,
        "current_wealth": state.current_wealth,
        "peak_wealth": state.peak_wealth,
        "failure_state": state.failure_state,
    }

    step.execute(state)

    for field_name, expected in preserved.items():
        assert getattr(state, field_name) == expected
