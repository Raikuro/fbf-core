from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from engine.application.steps.build_decision_context_step import BuildDecisionContextStep
from engine.application.simulation import SimulationState
from engine.application.simulation_context import SimulationContext
from engine.domain.model.asset import AssetClass
from engine.domain.model.allocation import Allocation, AllocationTarget
from engine.domain.model.dataset import Dataset
from engine.domain.model.money import Money
from engine.domain.model.portfolio import AssetHolding, Portfolio
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.policies.decisions import PolicyDecision
from engine.domain.policies import AllocationPolicy, WithdrawalPolicy


class DummyAllocationPolicy(AllocationPolicy):
    def decide(self, context: object) -> PolicyDecision:
        return PolicyDecision(reason="dummy")


class DummyWithdrawalPolicy(WithdrawalPolicy):
    def decide(self, context: object) -> PolicyDecision:
        return PolicyDecision(reason="dummy")


class DummyDataset(Dataset):
    pass


class DummyMarketSnapshot(MarketSnapshot):
    pass


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
    dataset: Dataset,
) -> SimulationState:
    context = make_context(portfolio, dataset)
    return SimulationState(
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


def test_build_decision_context_step_transforms_state() -> None:
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
    dataset = make_dataset(market_snapshot)

    state = make_state(portfolio, allocation, allocation_target, market_snapshot, dataset)
    step = BuildDecisionContextStep()

    before_fields = dict(
        current_date=state.current_date,
        period_index=state.period_index,
        portfolio=state.portfolio,
        allocation=state.allocation,
        allocation_target=state.allocation_target,
        market_snapshot=state.market_snapshot,
        current_wealth=state.current_wealth,
        peak_wealth=state.peak_wealth,
    )

    updated_state = step.execute(state)

    assert updated_state is state
    assert updated_state.decision_context is not None
    assert updated_state.decision_context.date == state.current_date
    assert updated_state.decision_context.period_index == state.period_index
    assert updated_state.decision_context.portfolio == state.portfolio
    assert updated_state.decision_context.current_allocation == state.allocation
    assert updated_state.decision_context.target_allocation == state.allocation_target
    assert updated_state.decision_context.market_snapshot == state.market_snapshot
    assert updated_state.decision_context.dataset == state.context.dataset

    for field_name, expected in before_fields.items():
        assert getattr(state, field_name) == expected


def test_build_decision_context_step_raises_when_missing_required_state() -> None:
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
    dataset = make_dataset(market_snapshot)

    state = make_state(portfolio, allocation, allocation_target, market_snapshot, dataset)
    state.portfolio = None  # type: ignore[assignment]
    step = BuildDecisionContextStep()

    with pytest.raises(ValueError, match="SimulationState.portfolio is required"):
        step.execute(state)


def test_build_decision_context_step_constructs_new_decision_context_each_time() -> None:
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
    dataset = make_dataset(market_snapshot)

    state = make_state(portfolio, allocation, allocation_target, market_snapshot, dataset)
    step = BuildDecisionContextStep()

    first_context = step.execute(state).decision_context
    second_context = step.execute(state).decision_context

    assert first_context is not None
    assert second_context is not None
    assert first_context is not second_context


def test_build_decision_context_step_does_not_modify_unrelated_state() -> None:
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
    dataset = make_dataset(market_snapshot)

    state = make_state(portfolio, allocation, allocation_target, market_snapshot, dataset)
    step = BuildDecisionContextStep()

    original_status = state.status
    original_failure_state = state.failure_state
    original_monthly_results = list(state.monthly_results)

    step.execute(state)

    assert state.status == original_status
    assert state.failure_state == original_failure_state
    assert state.monthly_results == original_monthly_results
