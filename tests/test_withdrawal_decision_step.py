from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from engine.application.steps.withdrawal_decision_step import WithdrawalDecisionStep
from engine.application.simulation import SimulationState
from engine.application.simulation_context import SimulationContext
from engine.domain.model.asset import AssetClass
from engine.domain.model.allocation import Allocation, AllocationTarget
from engine.domain.model.dataset import Dataset
from engine.domain.model.money import Money
from engine.domain.model.portfolio import AssetHolding, Portfolio
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.policies.decisions import PolicyDecision, WithdrawalDecision
from engine.domain.policies import AllocationPolicy, WithdrawalPolicy


class DummyAllocationPolicy(AllocationPolicy):
    def decide(self, context: object) -> PolicyDecision:
        return PolicyDecision(reason="dummy")


class DummyWithdrawalPolicy(WithdrawalPolicy):
    def __init__(self) -> None:
        self.calls = 0

    def decide(self, context: object) -> WithdrawalDecision:
        self.calls += 1
        return WithdrawalDecision(
            reason="dummy",
            nominal_amount=Money(Decimal("100"), Money.ZERO.currency),
            real_amount=Money(Decimal("100"), Money.ZERO.currency),
        )


class InvalidWithdrawalPolicy(WithdrawalPolicy):
    def decide(self, context: object) -> object:
        return object()


class DummyDataset(Dataset):
    pass


class DummyMarketSnapshot(MarketSnapshot):
    pass


def make_context(portfolio: Portfolio, dataset: Dataset, withdrawal_policy: WithdrawalPolicy) -> SimulationContext:
    return SimulationContext(
        experiment_name="test",
        cohort="A",
        start_date=date(2000, 1, 1),
        horizon_months=1,
        initial_wealth=Money(Decimal("1000"), Money.ZERO.currency),
        initial_portfolio=portfolio,
        dataset=dataset,
        allocation_policy=DummyAllocationPolicy(),
        withdrawal_policy=withdrawal_policy,
    )


def make_dataset(market_snapshot: MarketSnapshot) -> Dataset:
    return DummyDataset(snapshots=[market_snapshot], frequency="M", version="1.0")


def make_state(
    portfolio: Portfolio,
    allocation: Allocation,
    allocation_target: AllocationTarget,
    market_snapshot: MarketSnapshot,
    withdrawal_policy: WithdrawalPolicy,
) -> SimulationState:
    dataset = make_dataset(market_snapshot)
    context = make_context(portfolio, dataset, withdrawal_policy)
    from engine.domain.model.decision_context import DecisionContext

    decision_context = DecisionContext(
        date=date(2000, 1, 1),
        period_index=0,
        simulation_context=context,
        portfolio=portfolio,
        current_allocation=allocation,
        target_allocation=allocation_target,
        market_snapshot=market_snapshot,
        dataset=dataset,
    )

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
        decision_context=decision_context,
    )


def test_withdrawal_decision_step_stores_withdrawal_decision() -> None:
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
    withdrawal_policy = DummyWithdrawalPolicy()
    state = make_state(portfolio, allocation, allocation_target, market_snapshot, withdrawal_policy)
    step = WithdrawalDecisionStep()

    preserved = {
        "context": state.context,
        "current_date": state.current_date,
        "period_index": state.period_index,
        "portfolio": state.portfolio,
        "allocation": state.allocation,
        "allocation_target": state.allocation_target,
        "market_snapshot": state.market_snapshot,
    }

    updated_state = step.execute(state)

    assert updated_state is state
    assert isinstance(updated_state.withdrawal_decision, WithdrawalDecision)
    assert updated_state.withdrawal_decision.nominal_amount == Money(Decimal("100"), Money.ZERO.currency)
    assert updated_state.withdrawal_decision.real_amount == Money(Decimal("100"), Money.ZERO.currency)
    assert withdrawal_policy.calls == 1

    assert state.context == preserved["context"]
    assert state.current_date == preserved["current_date"]
    assert state.period_index == preserved["period_index"]
    assert state.portfolio == preserved["portfolio"]
    assert state.allocation == preserved["allocation"]
    assert state.allocation_target == preserved["allocation_target"]
    assert state.market_snapshot == preserved["market_snapshot"]


def test_withdrawal_decision_step_raises_when_missing_decision_context() -> None:
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
    withdrawal_policy = DummyWithdrawalPolicy()
    state = make_state(portfolio, allocation, allocation_target, market_snapshot, withdrawal_policy)
    state.decision_context = None
    step = WithdrawalDecisionStep()

    with pytest.raises(ValueError, match="SimulationState.decision_context is required"):
        step.execute(state)


def test_withdrawal_decision_step_raises_when_missing_withdrawal_policy() -> None:
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
    withdrawal_policy = DummyWithdrawalPolicy()
    state = make_state(portfolio, allocation, allocation_target, market_snapshot, withdrawal_policy)
    state.context = SimulationContext(
        experiment_name="test",
        cohort="A",
        start_date=date(2000, 1, 1),
        horizon_months=1,
        initial_wealth=Money(Decimal("1000"), Money.ZERO.currency),
        initial_portfolio=portfolio,
        dataset=make_dataset(market_snapshot),
        allocation_policy=DummyAllocationPolicy(),
        withdrawal_policy=None,  # type: ignore[arg-type]
    )
    step = WithdrawalDecisionStep()

    with pytest.raises(ValueError, match="SimulationContext.withdrawal_policy is required"):
        step.execute(state)


def test_withdrawal_decision_step_raises_when_policy_returns_invalid_type() -> None:
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
    withdrawal_policy = InvalidWithdrawalPolicy()
    state = make_state(portfolio, allocation, allocation_target, market_snapshot, withdrawal_policy)
    step = WithdrawalDecisionStep()

    with pytest.raises(TypeError, match="WithdrawalPolicy.decide must return a WithdrawalDecision"):
        step.execute(state)


def test_withdrawal_decision_step_does_not_modify_unrelated_state() -> None:
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
    withdrawal_policy = DummyWithdrawalPolicy()
    state = make_state(portfolio, allocation, allocation_target, market_snapshot, withdrawal_policy)
    step = WithdrawalDecisionStep()

    preserved = {
        "portfolio": state.portfolio,
        "market_snapshot": state.market_snapshot,
        "allocation": state.allocation,
        "decision_context": state.decision_context,
    }

    step.execute(state)

    assert state.portfolio == preserved["portfolio"]
    assert state.market_snapshot == preserved["market_snapshot"]
    assert state.allocation == preserved["allocation"]
    assert state.decision_context is preserved["decision_context"]
