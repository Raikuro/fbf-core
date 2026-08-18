"""Integration tests for real multi-cohort research plan execution.

Verifies end-to-end execution across multiple rolling cohorts:
- Domain materialization (Dataset.slice & materialize_research_plan)
- Per-cohort dataset alignment (unit.dataset[0].date == unit.cohort.start_date)
- Caching identity (unit_a.dataset is unit_b.dataset for same cohort)
- Stateless ResearchExecutor -> SimulationExecutor -> SimulationRunner pipeline
- Sequential execution & parallel ProcessPoolExecutor execution
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from engine.domain.model.allocation import AllocationTarget
from engine.domain.model.asset import AssetClass
from engine.domain.model.dataset import Dataset
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.money import Currency, Money
from engine.domain.model.portfolio import AssetHolding, Portfolio
from engine.domain.policies.allocation_policy import AllocationPolicy
from engine.domain.policies.decisions import AllocationDecision, WithdrawalDecision
from engine.domain.policies.withdrawal_policy import WithdrawalPolicy
from infrastructure.execution.parallel_executor import (
    _create_default_simulation_executor,
    parallel_execute,
    sequential_execute,
)
from research.domain.cohort.specification import CohortSpecification
from research.domain.experiment.definition import ExperimentDefinition
from research.domain.parameter.configuration import ParameterConfiguration
from research.domain.plan import ResearchPlan, materialize_research_plan
from research.orchestration.executor import ResearchExecutor

_ASSET = AssetClass(id="acwi", name="ACWI", description="Global equities")


class IntegrationAllocationPolicy(AllocationPolicy):
    def decide(self, context: object) -> AllocationDecision:
        return AllocationDecision(
            reason="integration",
            allocation_target=AllocationTarget(weights={_ASSET: Decimal("1.0")}),
        )


class IntegrationWithdrawalPolicy(WithdrawalPolicy):
    def decide(self, context: object) -> WithdrawalDecision:
        return WithdrawalDecision(
            reason="integration",
            nominal_amount=Money(Decimal("100"), Currency.EUR),
            real_amount=Money(Decimal("100"), Currency.EUR),
        )


def make_large_dataset(num_months: int = 120, start_year: int = 2000) -> Dataset:
    snapshots = []
    for i in range(num_months):
        m = i + 1
        year = start_year + (m - 1) // 12
        month = ((m - 1) % 12) + 1
        snapshots.append(
            MarketSnapshot(
                date=date(year, month, 1),
                index_levels={_ASSET: Decimal(100 + i)},
                inflation=Decimal("0.00"),
                inflation_cumulative=Decimal("0.00"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal(100 + i),
            )
        )
    return Dataset(snapshots=snapshots, frequency="monthly", version="MULTI_COHORT_v1")


def make_multi_cohort_experiment(horizon_months: int = 12) -> ExperimentDefinition:
    dataset = make_large_dataset(120)
    return ExperimentDefinition(
        name="multi-cohort-experiment",
        description="Multi-cohort integration test",
        dataset=dataset,
        horizon_months=horizon_months,
        initial_wealth=Money(Decimal("100000"), Currency.EUR),
        cohorts=(
            CohortSpecification(start_date=date(2000, 1, 1), id="c1"),
            CohortSpecification(start_date=date(2000, 6, 1), id="c2"),
            CohortSpecification(start_date=date(2001, 1, 1), id="c3"),
        ),
        allocation_policies=(IntegrationAllocationPolicy(),),
        withdrawal_policies=(IntegrationWithdrawalPolicy(),),
    )


class TestMultiCohortExecution:
    def _make_plan(
        self,
        exp: ExperimentDefinition,
        param_configs: tuple[ParameterConfiguration, ...],
        portfolio: Portfolio,
    ) -> ResearchPlan:
        return materialize_research_plan(
            experiment_def=exp,
            canonical_trajectory=exp.dataset,
            cohorts=exp.cohorts,
            param_configs=param_configs,
            initial_portfolio=portfolio,
            horizon_resolver=lambda c: exp.horizon_months,
            policy_resolver=lambda c: (
                exp.allocation_policies[0],
                exp.withdrawal_policies[0],
            ),
        )

    def test_plan_materialization_assigns_cohort_datasets(self) -> None:
        exp = make_multi_cohort_experiment(horizon_months=12)
        param_configs = (
            ParameterConfiguration(values={"rate": 0.03}),
            ParameterConfiguration(values={"rate": 0.04}),
        )
        portfolio = Portfolio(holdings=(AssetHolding(asset_class=_ASSET, units=Decimal("1000")),))

        plan = self._make_plan(exp, param_configs, portfolio)

        assert len(plan) == 6  # 3 cohorts * 2 param configs

        # Verify cohort alignment & horizon length
        for unit in plan:
            assert unit.dataset is not None
            assert unit.dataset[0].date == unit.cohort.start_date
            assert len(unit.dataset) == 12

        # Verify dataset identity caching per cohort
        c1_units = [u for u in plan if u.cohort.start_date == date(2000, 1, 1)]
        assert len(c1_units) == 2
        assert c1_units[0].dataset is c1_units[1].dataset

        c2_units = [u for u in plan if u.cohort.start_date == date(2000, 6, 1)]
        assert len(c2_units) == 2
        assert c2_units[0].dataset is c2_units[1].dataset

        # Different cohorts receive different dataset instances
        assert c1_units[0].dataset is not c2_units[0].dataset

    def test_sequential_multi_cohort_real_engine_execution(self) -> None:
        exp = make_multi_cohort_experiment(horizon_months=12)
        portfolio = Portfolio(holdings=(AssetHolding(asset_class=_ASSET, units=Decimal("1000")),))

        plan = self._make_plan(
            exp,
            (ParameterConfiguration(values={"rate": 0.04}),),
            portfolio,
        )

        sim_executor = _create_default_simulation_executor()
        research_executor = ResearchExecutor(simulation_executor=sim_executor)

        result = research_executor.execute(plan)

        assert len(result.results) == 3
        for res in result.results:
            assert res.statistics.success is True
            assert res.statistics.months_simulated == 12

    def test_parallel_process_pool_multi_cohort_execution(self) -> None:
        exp = make_multi_cohort_experiment(horizon_months=12)
        portfolio = Portfolio(holdings=(AssetHolding(asset_class=_ASSET, units=Decimal("1000")),))

        plan = self._make_plan(
            exp,
            (
                ParameterConfiguration(values={"rate": 0.03}),
                ParameterConfiguration(values={"rate": 0.04}),
            ),
            portfolio,
        )

        sim_executor = _create_default_simulation_executor()

        # Exercise ProcessPoolExecutor parallel execution
        parallel_res = parallel_execute(plan, simulation_executor=sim_executor, max_workers=2)
        assert len(parallel_res.results) == 6
        for res in parallel_res.results:
            assert res.statistics.success is True
            assert res.statistics.months_simulated == 12

        # Exercise sequential execution wrapper
        seq_res = sequential_execute(plan, simulation_executor=sim_executor)
        assert len(seq_res.results) == 6
        for res in seq_res.results:
            assert res.statistics.success is True
            assert res.statistics.months_simulated == 12
