from __future__ import annotations

from datetime import date
from decimal import Decimal

from engine.application.pipeline import PipelineStep, SimulationPipeline
from engine.application.steps.allocation_decision_step import AllocationDecisionStep
from engine.application.steps.build_decision_context_step import BuildDecisionContextStep
from engine.application.steps.market_evolution_step import MarketEvolutionStep
from engine.application.steps.monthly_result_builder_step import MonthlyResultBuilderStep
from engine.application.steps.portfolio_rebalance_step import PortfolioRebalanceStep
from engine.application.steps.simulation_state_update_step import SimulationStateUpdateStep
from engine.application.steps.withdrawal_decision_step import WithdrawalDecisionStep
from engine.application.steps.withdrawal_execution_step import WithdrawalExecutionStep
from engine.application.simulation import ExecutionStatus, SimulationState
from engine.application.simulation_context import SimulationContext
from engine.domain.model.asset import AssetClass
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


def test_complete_pipeline_accepts_all_concrete_steps() -> None:
    steps = (
        BuildDecisionContextStep(),
        WithdrawalDecisionStep(),
        WithdrawalExecutionStep(),
        AllocationDecisionStep(),
        PortfolioRebalanceStep(),
        MarketEvolutionStep(),
        MonthlyResultBuilderStep(),
        SimulationStateUpdateStep(),
    )

    pipeline = SimulationPipeline(steps)

    assert pipeline.steps == steps
    assert all(isinstance(step, PipelineStep) for step in steps)


def make_context(portfolio: Portfolio, dataset: Dataset, horizon_months: int = 2) -> SimulationContext:
    return SimulationContext(
        experiment_name="test",
        cohort="A",
        start_date=date(2000, 1, 1),
        horizon_months=horizon_months,
        initial_wealth=Money(Decimal("1000"), Money.ZERO.currency),
        initial_portfolio=portfolio,
        dataset=dataset,
        allocation_policy=DummyAllocationPolicy(),
        withdrawal_policy=DummyWithdrawalPolicy(),
    )


def make_dataset(market_snapshot: MarketSnapshot, market_snapshot_next: MarketSnapshot) -> Dataset:
    return DummyDataset(snapshots=[market_snapshot, market_snapshot_next], frequency="M", version="1.0")


def make_state(
    portfolio: Portfolio,
    market_snapshot: MarketSnapshot,
    current_wealth: Money,
    horizon_months: int = 2,
) -> SimulationState:
    dataset = make_dataset(market_snapshot, market_snapshot)
    context = make_context(portfolio, dataset, horizon_months)
    return SimulationState(
        context=context,
        current_date=date(2000, 1, 1),
        period_index=0,
        portfolio=portfolio,
        market_snapshot=market_snapshot,
        current_wealth=current_wealth,
        peak_wealth=current_wealth,
        status=ExecutionStatus.RUNNING,
    )


def test_simulation_state_update_advances_snapshot_and_date() -> None:
    asset = AssetClass(id="eq", name="Equity", description="Equity")
    portfolio = Portfolio([AssetHolding(asset_class=asset, units=Decimal("100"))])
    current_snapshot = DummyMarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={asset: Decimal("100")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=False,
        is_underwater=False,
        running_ath=Decimal("100"),
    )
    next_snapshot = DummyMarketSnapshot(
        date=date(2000, 2, 1),
        index_levels={asset: Decimal("110")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=False,
        is_underwater=False,
        running_ath=Decimal("110"),
    )
    dataset = DummyDataset(snapshots=[current_snapshot, next_snapshot], frequency="M", version="1.0")
    context = make_context(portfolio, dataset)
    state = SimulationState(
        context=context,
        current_date=current_snapshot.date,
        period_index=0,
        portfolio=portfolio,
        market_snapshot=current_snapshot,
        current_wealth=Money(Decimal("10000"), Money.ZERO.currency),
        peak_wealth=Money(Decimal("10000"), Money.ZERO.currency),
        status=ExecutionStatus.RUNNING,
    )
    step = SimulationStateUpdateStep()

    updated_state = step.execute(state)

    assert updated_state.current_date == date(2000, 2, 1)
    assert updated_state.period_index == 1
    assert updated_state.market_snapshot == next_snapshot
    assert updated_state.status == ExecutionStatus.RUNNING
    assert updated_state.portfolio == portfolio
    assert updated_state.current_wealth == Money(Decimal("10000"), Money.ZERO.currency)


def test_simulation_state_update_completes_when_dataset_exhausted() -> None:
    asset = AssetClass(id="eq", name="Equity", description="Equity")
    portfolio = Portfolio([AssetHolding(asset_class=asset, units=Decimal("100"))])
    current_snapshot = DummyMarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={asset: Decimal("100")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=False,
        is_underwater=False,
        running_ath=Decimal("100"),
    )
    dataset = DummyDataset(snapshots=[current_snapshot], frequency="M", version="1.0")
    context = make_context(portfolio, dataset, horizon_months=2)
    state = SimulationState(
        context=context,
        current_date=current_snapshot.date,
        period_index=0,
        portfolio=portfolio,
        market_snapshot=current_snapshot,
        current_wealth=Money(Decimal("10000"), Money.ZERO.currency),
        peak_wealth=Money(Decimal("10000"), Money.ZERO.currency),
        status=ExecutionStatus.RUNNING,
    )
    step = SimulationStateUpdateStep()

    updated_state = step.execute(state)

    assert updated_state.status == ExecutionStatus.COMPLETED
    assert updated_state.market_snapshot == current_snapshot
    assert updated_state.period_index == 0
    assert updated_state.current_date == date(2000, 1, 1)


def test_simulation_state_update_completes_at_horizon() -> None:
    asset = AssetClass(id="eq", name="Equity", description="Equity")
    portfolio = Portfolio([AssetHolding(asset_class=asset, units=Decimal("100"))])
    current_snapshot = DummyMarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={asset: Decimal("100")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=False,
        is_underwater=False,
        running_ath=Decimal("100"),
    )
    next_snapshot = DummyMarketSnapshot(
        date=date(2000, 2, 1),
        index_levels={asset: Decimal("110")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=False,
        is_underwater=False,
        running_ath=Decimal("110"),
    )
    dataset = DummyDataset(snapshots=[current_snapshot, next_snapshot], frequency="M", version="1.0")
    context = make_context(portfolio, dataset, horizon_months=1)
    state = SimulationState(
        context=context,
        current_date=current_snapshot.date,
        period_index=0,
        portfolio=portfolio,
        market_snapshot=current_snapshot,
        current_wealth=Money(Decimal("10000"), Money.ZERO.currency),
        peak_wealth=Money(Decimal("10000"), Money.ZERO.currency),
        status=ExecutionStatus.RUNNING,
    )
    step = SimulationStateUpdateStep()

    updated_state = step.execute(state)

    assert updated_state.status == ExecutionStatus.COMPLETED
    assert updated_state.period_index == 0
    assert updated_state.current_date == date(2000, 1, 1)
    assert updated_state.market_snapshot == current_snapshot


def test_simulation_state_update_is_deterministic() -> None:
    asset = AssetClass(id="eq", name="Equity", description="Equity")
    portfolio = Portfolio([AssetHolding(asset_class=asset, units=Decimal("100"))])
    current_snapshot = DummyMarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={asset: Decimal("100")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=False,
        is_underwater=False,
        running_ath=Decimal("100"),
    )
    next_snapshot = DummyMarketSnapshot(
        date=date(2000, 2, 1),
        index_levels={asset: Decimal("110")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=False,
        is_underwater=False,
        running_ath=Decimal("110"),
    )
    dataset = DummyDataset(snapshots=[current_snapshot, next_snapshot], frequency="M", version="1.0")
    context = make_context(portfolio, dataset)
    state_one = SimulationState(
        context=context,
        current_date=current_snapshot.date,
        period_index=0,
        portfolio=portfolio,
        market_snapshot=current_snapshot,
        current_wealth=Money(Decimal("10000"), Money.ZERO.currency),
        peak_wealth=Money(Decimal("10000"), Money.ZERO.currency),
        status=ExecutionStatus.RUNNING,
    )
    state_two = SimulationState(
        context=context,
        current_date=current_snapshot.date,
        period_index=0,
        portfolio=portfolio,
        market_snapshot=current_snapshot,
        current_wealth=Money(Decimal("10000"), Money.ZERO.currency),
        peak_wealth=Money(Decimal("10000"), Money.ZERO.currency),
        status=ExecutionStatus.RUNNING,
    )
    step = SimulationStateUpdateStep()

    first = step.execute(state_one)
    second = step.execute(state_two)

    assert first.current_date == second.current_date
    assert first.period_index == second.period_index
    assert first.market_snapshot == second.market_snapshot
    assert first.status == second.status
    assert first.current_wealth == second.current_wealth
