from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from engine.application.steps.withdrawal_execution_step import WithdrawalExecutionStep
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
from engine.domain.services.portfolio_withdrawal_service import (
    WithdrawalExecutionResult,
    PortfolioWithdrawalService,
)


class DummyAllocationPolicy(AllocationPolicy):
    def decide(self, context: object) -> PolicyDecision:
        return PolicyDecision(reason="dummy")


class DummyWithdrawalPolicy(WithdrawalPolicy):
    def decide(self, context: object) -> WithdrawalDecision:
        return WithdrawalDecision(
            reason="dummy",
            nominal_amount=Money(Decimal("10"), Money.ZERO.currency),
            real_amount=Money(Decimal("10"), Money.ZERO.currency),
        )


class DummyWithdrawalService(PortfolioWithdrawalService):
    def __init__(self) -> None:
        self.calls = 0

    def execute_withdrawal(
        self,
        portfolio: Portfolio,
        requested_withdrawal: WithdrawalDecision,
        market_snapshot: MarketSnapshot,
    ) -> WithdrawalExecutionResult:
        self.calls += 1
        return WithdrawalExecutionResult(
            requested_withdrawal=requested_withdrawal,
            portfolio=portfolio,
            depleted=False,
            shortfall=None,
            remaining_value=Money(Decimal("100"), Money.ZERO.currency),
        )


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
    decision = WithdrawalDecision(
        reason="test",
        nominal_amount=Money(Decimal("10"), Money.ZERO.currency),
        real_amount=Money(Decimal("10"), Money.ZERO.currency),
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
        withdrawal_decision=decision,
    )


def test_withdrawal_execution_step_delegates_to_service_once() -> None:
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
    service = DummyWithdrawalService()
    step = WithdrawalExecutionStep(withdrawal_service=service)

    step.execute(state)

    assert service.calls == 1


def test_withdrawal_execution_step_updates_portfolio_and_current_wealth() -> None:
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
    step = WithdrawalExecutionStep()

    updated_state = step.execute(state)

    assert updated_state.portfolio != portfolio
    assert updated_state.portfolio.holdings[0].units == Decimal("99.900")
    assert updated_state.current_wealth == Money(Decimal("9990"), Money.ZERO.currency)
    assert updated_state.failure_state is None


def test_withdrawal_execution_step_sets_failure_state_on_depletion() -> None:
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
    service = DummyWithdrawalService()
    step = WithdrawalExecutionStep(withdrawal_service=service)
    service_result = WithdrawalExecutionResult(
        requested_withdrawal=state.withdrawal_decision,
        portfolio=portfolio,
        depleted=True,
        shortfall=Money(Decimal("1"), Money.ZERO.currency),
        remaining_value=Money(Decimal("0"), Money.ZERO.currency),
    )
    service.execute_withdrawal = lambda portfolio, requested_withdrawal, market_snapshot: service_result  # type: ignore[assignment]

    result_state = step.execute(state)

    assert result_state.failure_state == "depleted"
    assert result_state.current_wealth == Money(Decimal("0"), Money.ZERO.currency)


def test_withdrawal_execution_step_raises_when_missing_withdrawal_decision() -> None:
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
    state.withdrawal_decision = None
    step = WithdrawalExecutionStep()

    with pytest.raises(ValueError, match="SimulationState.withdrawal_decision is required"):
        step.execute(state)


def test_withdrawal_execution_step_does_not_modify_unrelated_state() -> None:
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
    step = WithdrawalExecutionStep()

    preserved = {
        "context": state.context,
        "period_index": state.period_index,
        "allocation": state.allocation,
        "allocation_target": state.allocation_target,
        "market_snapshot": state.market_snapshot,
    }

    step.execute(state)

    assert state.context == preserved["context"]
    assert state.period_index == preserved["period_index"]
    assert state.allocation == preserved["allocation"]
    assert state.allocation_target == preserved["allocation_target"]
    assert state.market_snapshot == preserved["market_snapshot"]
