from __future__ import annotations

from datetime import date
from decimal import Decimal

from engine.application.steps.allocation_decision_step import AllocationDecisionStep
from engine.application.steps.build_decision_context_step import BuildDecisionContextStep
from engine.application.steps.market_evolution_step import MarketEvolutionStep
from engine.application.steps.portfolio_rebalance_step import PortfolioRebalanceStep
from engine.application.steps.withdrawal_decision_step import WithdrawalDecisionStep
from engine.application.steps.withdrawal_execution_step import WithdrawalExecutionStep
from engine.application.simulation import SimulationState
from engine.application.simulation_context import SimulationContext
from engine.domain.model.asset import AssetClass
from engine.domain.model.allocation import Allocation, AllocationTarget
from engine.domain.model.dataset import Dataset
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.money import Money
from engine.domain.model.portfolio import AssetHolding, Portfolio
from engine.domain.policies.decisions import AllocationDecision, WithdrawalDecision
from engine.domain.policies import AllocationPolicy, WithdrawalPolicy
from engine.domain.services.portfolio_rebalance_service import PortfolioRebalanceService


class DummyDataset(Dataset):
    pass


class DummyMarketSnapshot(MarketSnapshot):
    pass


class WithdrawalPolicy60(WithdrawalPolicy):
    def decide(self, context: object) -> WithdrawalDecision:
        return WithdrawalDecision(
            reason="withdraw",
            nominal_amount=Money(Decimal("1000"), Money.ZERO.currency),
            real_amount=Money(Decimal("1000"), Money.ZERO.currency),
        )


class AllocationPolicy6040(AllocationPolicy):
    def decide(self, context: object) -> AllocationDecision:
        asset_a = AssetClass(id="a", name="Equity", description="Equity")
        asset_b = AssetClass(id="b", name="Bond", description="Bond")
        return AllocationDecision(
            reason="rebalance",
            allocation_target=AllocationTarget(
                weights={asset_a: Decimal("0.6"), asset_b: Decimal("0.4")}
            ),
        )


def make_context(portfolio: Portfolio, dataset: Dataset) -> SimulationContext:
    return SimulationContext(
        experiment_name="test",
        cohort="A",
        start_date=date(2000, 1, 1),
        horizon_months=1,
        initial_wealth=Money(Decimal("10000"), Money.ZERO.currency),
        initial_portfolio=portfolio,
        dataset=dataset,
        allocation_policy=AllocationPolicy6040(),
        withdrawal_policy=WithdrawalPolicy60(),
    )


def make_dataset(market_snapshot: MarketSnapshot) -> Dataset:
    return DummyDataset(snapshots=[market_snapshot], frequency="M", version="1.0")


def test_portfolio_rebalance_integration_100_equity_withdrawal_then_6040() -> None:
    asset_a = AssetClass(id="a", name="Equity", description="Equity")
    asset_b = AssetClass(id="b", name="Bond", description="Bond")
    initial_portfolio = Portfolio([AssetHolding(asset_class=asset_a, units=Decimal("100"))])
    market_snapshot = DummyMarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={asset_a: Decimal("100"), asset_b: Decimal("100")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=False,
        is_underwater=False,
        running_ath=Decimal("100"),
    )
    dataset = make_dataset(market_snapshot)
    context = make_context(initial_portfolio, dataset)
    state = SimulationState(
        context=context,
        current_date=context.start_date,
        period_index=0,
        portfolio=initial_portfolio,
        allocation=Allocation(weights={asset_a: Decimal("1")}),
        allocation_target=AllocationTarget(weights={asset_a: Decimal("1")}),
        market_snapshot=market_snapshot,
        current_wealth=Money(Decimal("10000"), Money.ZERO.currency),
        peak_wealth=Money(Decimal("10000"), Money.ZERO.currency),
    )

    steps = [
        BuildDecisionContextStep(),
        WithdrawalDecisionStep(),
        WithdrawalExecutionStep(),
        AllocationDecisionStep(),
        PortfolioRebalanceStep(),
        MarketEvolutionStep(),
    ]

    for step in steps:
        state = step.execute(state)

    assert state.portfolio is not initial_portfolio
    assert state.current_wealth == Money(Decimal("9000.00"), Money.ZERO.currency)
    assert state.allocation == Allocation(weights={asset_a: Decimal("0.6"), asset_b: Decimal("0.4")})
    assert state.allocation_target == AllocationTarget(weights={asset_a: Decimal("0.6"), asset_b: Decimal("0.4")})
    assert state.portfolio.holdings[0].units == Decimal("54")
    assert state.portfolio.holdings[1].units == Decimal("36")
    assert state.market_snapshot == market_snapshot
    assert state.failure_state is None
