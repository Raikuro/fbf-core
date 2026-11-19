"""Unit tests for single-process plan execution orchestration."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import Mock

import pytest

from fbf.core.domain.model.allocation import AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies.allocation_policy import AllocationPolicy
from fbf.core.domain.policies.decisions import AllocationDecision, WithdrawalDecision
from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    ExperimentRun,
    SimulationResult,
    SimulationStatistics,
    SimulationTimeline,
)
from fbf.core.execution.plan_executor import execute_plan
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan


class DummyAllocationPolicy(AllocationPolicy):
    def decide(self, context: object) -> AllocationDecision:
        portfolio = getattr(context, "portfolio", None)
        asset = (
            portfolio.holdings[0].asset_class
            if portfolio and portfolio.holdings
            else make_asset()
        )
        return AllocationDecision(
            reason="dummy",
            allocation_target=AllocationTarget(weights={asset: Decimal("1.0")}),
        )


class DummyWithdrawalPolicy(WithdrawalPolicy):
    def decide(self, context: object) -> WithdrawalDecision:
        return WithdrawalDecision(
            reason="dummy",
            nominal_amount=Money(Decimal("100"), Currency.EUR),
            real_amount=Money(Decimal("100"), Currency.EUR),
        )


def make_asset() -> AssetClass:
    return AssetClass(id="acwi", name="ACWI", description="Global equities")


def make_dataset(start_date: date = date(2000, 1, 1)) -> Dataset:
    asset = make_asset()
    snapshot = MarketSnapshot(
        date=start_date,
        index_levels={asset: Decimal("100.00")},
        inflation=Decimal("0.00"),
        inflation_cumulative=Decimal("0.00"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100.00"),
    )
    return Dataset(snapshots=[snapshot], frequency="monthly")


def make_minimal_dataset(year: int = 2000, month: int = 1) -> Dataset:
    """Minimal single-snapshot Dataset aligned to a cohort start date."""
    return make_dataset(start_date=date(year, month, 1))


def make_experiment_def() -> ExperimentDefinition:
    return ExperimentDefinition(
        name="plan-executor-test-experiment",
        description="Experiment for plan executor tests",
        dataset=make_dataset(),
        horizon_months=12,
        initial_wealth=Money(Decimal("100000"), Currency.EUR),
        cohorts=(CohortSpecification(start_date=date(2000, 1, 1)),),
        allocation_policies=(DummyAllocationPolicy(),),
        withdrawal_policies=(DummyWithdrawalPolicy(),),
    )


def make_unit(month: int = 1, withdrawal_rate: float = 0.04) -> PlannedSimulationUnit:
    asset = make_asset()
    portfolio = Portfolio(
        holdings=(AssetHolding(asset_class=asset, units=Decimal("1000")),)
    )
    return PlannedSimulationUnit(
        cohort=CohortSpecification(start_date=date(2000, month, 1)),
        parameter_config=ParameterConfiguration(
            values={"withdrawal_rate": withdrawal_rate}
        ),
        allocation_policy=DummyAllocationPolicy(),
        withdrawal_policy=DummyWithdrawalPolicy(),
        initial_portfolio=portfolio,
        dataset=make_minimal_dataset(year=2000, month=month),
    )


def make_simulation_result(unit_idx: int) -> SimulationResult:
    return SimulationResult(
        timeline=SimulationTimeline(monthly_results=()),
        statistics=SimulationStatistics(
            final_wealth=Money(Decimal(100000 + unit_idx * 1000), Currency.EUR),
            max_drawdown=0.0,
            success=True,
            failure_month=None,
            failure_state=None,
            months_simulated=12,
            execution_time_seconds=0.01,
        ),
    )


def make_test_plan(num_units: int = 12) -> ResearchPlan:
    exp_def = make_experiment_def()
    units = tuple(
        make_unit(month=((i % 12) + 1), withdrawal_rate=0.03 + (i * 0.001))
        for i in range(num_units)
    )
    return ResearchPlan(experiment_definition=exp_def, units=units)


def make_mock_simulation_executor(num_units: int) -> Mock:
    """Return a mock SimulationExecutor with deterministic per-context results."""
    mock_exec = Mock()

    def mock_execute(engine_def: EngineExperimentDefinition) -> ExperimentRun:
        sim_results = tuple(
            make_simulation_result(ctx.start_date.month + ctx.start_date.year * 12)
            for ctx in engine_def.simulation_contexts
        )
        return ExperimentRun(definition=engine_def, simulation_results=sim_results)

    mock_exec.execute.side_effect = mock_execute
    return mock_exec


def test_execute_plan_preserves_order_and_plan() -> None:
    plan = make_test_plan(num_units=12)
    executor = make_mock_simulation_executor(12)

    result = execute_plan(plan, simulation_executor=executor)

    assert result.plan == plan
    assert len(result.results) == 12
    assert result.results == tuple(
        make_simulation_result(
            unit.cohort.start_date.month + unit.cohort.start_date.year * 12
        )
        for unit in plan.units
    )


def test_execute_plan_progress_callback_per_unit() -> None:
    plan = make_test_plan(num_units=8)
    executor = make_mock_simulation_executor(8)

    progress_reports: list[tuple[int, int]] = []

    def callback(completed: int, total: int) -> None:
        progress_reports.append((completed, total))

    result = execute_plan(
        plan,
        simulation_executor=executor,
        progress_callback=callback,
    )

    assert progress_reports == [(i, 8) for i in range(1, 9)]
    assert len(result.results) == 8


def test_execute_plan_summary_only_strips_timelines() -> None:
    plan = make_test_plan(num_units=6)
    executor = make_mock_simulation_executor(6)

    full = execute_plan(plan, simulation_executor=executor)
    summary = execute_plan(plan, simulation_executor=executor, summary_only=True)

    assert len(summary.results) == len(full.results) == 6
    for summary_result, full_result in zip(
        summary.results, full.results, strict=True
    ):
        assert summary_result.timeline.monthly_results == ()
        assert summary_result.statistics == full_result.statistics


def test_execute_plan_requires_simulation_executor() -> None:
    plan = make_test_plan(num_units=1)

    with pytest.raises(ValueError, match="simulation_executor is required"):
        execute_plan(plan)
