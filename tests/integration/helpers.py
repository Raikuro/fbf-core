"""Test helpers for integration tests.

Provides reusable factory functions, assertion utilities,
and convenience wrappers shared by all integration test packages.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

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
    ExperimentRun,
    SimulationResult,
    SimulationStatistics,
    SimulationTimeline,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.result import ResearchExecutionResult
from fbf.core.persistence.studies.sqlite.sqlite_repository import SQLiteRepository
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan

# ---------------------------------------------------------------------------
# Shared test asset
# ---------------------------------------------------------------------------

_HELPER_ASSET = AssetClass(
    id="acwi", name="ACWI", description="Global equities"
)


# ---------------------------------------------------------------------------
# Dataset factories
# ---------------------------------------------------------------------------


def make_snapshot(d: date) -> MarketSnapshot:
    return MarketSnapshot(
        date=d,
        index_levels={_HELPER_ASSET: Decimal("100.00")},
        inflation=Decimal("0.00"),
        inflation_cumulative=Decimal("0.00"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100.00"),
    )


def make_dataset(num_months: int = 500, start_year: int = 1871) -> Dataset:
    snapshots = []
    year = start_year
    month = 1
    for _ in range(num_months):
        snapshots.append(make_snapshot(date(year, month, 1)))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return Dataset(snapshots=snapshots, frequency="monthly", version="INTEGRATION_TEST_v1")


# ---------------------------------------------------------------------------
# Policy stubs
# ---------------------------------------------------------------------------


class HelperAllocationPolicy(AllocationPolicy):
    def __init__(self, equity_allocation: Decimal = Decimal("0.75")) -> None:
        self.equity_allocation = equity_allocation

    def decide(self, context: object) -> AllocationDecision:
        equity = AssetClass(id="equity", name="Equity", description="")
        bond = AssetClass(id="bond", name="Bond", description="")
        return AllocationDecision(
            reason="helper_allocation",
            allocation_target=AllocationTarget(weights={
                equity: self.equity_allocation,
                bond: Decimal("1") - self.equity_allocation,
            }),
        )


class HelperWithdrawalPolicy(WithdrawalPolicy):
    def __init__(self, withdrawal_rate: Decimal = Decimal("0.04")) -> None:
        self.withdrawal_rate = withdrawal_rate

    def decide(self, context: object) -> WithdrawalDecision:
        total = Decimal("1000000")
        monthly = total * self.withdrawal_rate / Decimal("12")
        return WithdrawalDecision(
            reason="helper_withdrawal",
            nominal_amount=Money(monthly, Currency.EUR),
            real_amount=Money(monthly, Currency.EUR),
        )


# ---------------------------------------------------------------------------
# Domain object factories
# ---------------------------------------------------------------------------


def make_experiment(
    name: str = "helper-experiment",
    dataset: Dataset | None = None,
    horizon_months: int = 120,
    initial_wealth: Money | None = None,
) -> ExperimentDefinition:
    if dataset is None:
        dataset = make_dataset(horizon_months + 12, start_year=2000)
    if initial_wealth is None:
        initial_wealth = Money(Decimal("1000000"), Currency.EUR)
    return ExperimentDefinition(
        name=name,
        description=f"Helper experiment: {name}",
        dataset=dataset,
        horizon_months=horizon_months,
        initial_wealth=initial_wealth,
        cohorts=(
            CohortSpecification(start_date=date(2000, 1, 1)),
        ),
        allocation_policies=(HelperAllocationPolicy(),),
        withdrawal_policies=(HelperWithdrawalPolicy(),),
    )


def make_plan(
    experiment: ExperimentDefinition | None = None,
    num_units: int = 3,
) -> ResearchPlan:
    if experiment is None:
        experiment = make_experiment()
    units: list[PlannedSimulationUnit] = []
    for i in range(num_units):
        cohort_date = date(2000, i + 1, 1)
        sliced = experiment.dataset.slice(cohort_date, experiment.horizon_months)
        units.append(
            PlannedSimulationUnit(
                cohort=CohortSpecification(start_date=cohort_date),
                parameter_config=ParameterConfiguration(
                    values={"withdrawal_rate": 0.04}
                ),
                allocation_policy=HelperAllocationPolicy(),
                withdrawal_policy=HelperWithdrawalPolicy(),
                initial_portfolio=Portfolio(
                    holdings=(
                        AssetHolding(
                            asset_class=_HELPER_ASSET, units=Decimal("1000")
                        ),
                    )
                ),
                dataset=sliced,
            )
        )
    return ResearchPlan(experiment_definition=experiment, units=tuple(units))


def make_simulation_result(
    final_wealth: str = "500000.00",
    success: bool = True,
    failure_month: int | None = None,
    months_simulated: int = 120,
) -> SimulationResult:
    return SimulationResult(
        timeline=SimulationTimeline(monthly_results=()),
        statistics=SimulationStatistics(
            final_wealth=Money(Decimal(final_wealth), Currency.EUR),
            max_drawdown=0.05,
            success=success,
            failure_month=failure_month,
            failure_state=None,
            months_simulated=months_simulated,
            execution_time_seconds=0.01,
        ),
    )


def make_execution_result(
    plan: ResearchPlan | None = None,
) -> ResearchExecutionResult:
    if plan is None:
        plan = make_plan()

    from fbf.core.execution.pipeline.simulation import (
        ExperimentDefinition as EngineExperimentDefinition,
    )
    sim_contexts = tuple(
        SimulationContext(
            experiment_name=plan.experiment_definition.name,
            cohort=unit.cohort.start_date.isoformat(),
            start_date=unit.cohort.start_date,
            horizon_months=plan.experiment_definition.horizon_months,
            initial_wealth=plan.experiment_definition.initial_wealth,
            initial_portfolio=unit.initial_portfolio,
            dataset=plan.experiment_definition.dataset,
            allocation_policy=unit.allocation_policy,
            withdrawal_policy=unit.withdrawal_policy,
        )
        for unit in plan.units
    )
    engine_def = EngineExperimentDefinition(
        name=plan.experiment_definition.name,
        description=plan.experiment_definition.description,
        simulation_contexts=sim_contexts,
    )
    sim_results = tuple(
        make_simulation_result(str(500000 + i * 1000))
        for i in range(len(plan.units))
    )
    experiment_run = ExperimentRun(
        definition=engine_def, simulation_results=sim_results
    )
    return ResearchExecutionResult(
        plan=plan, experiment_result=experiment_run
    )


# ---------------------------------------------------------------------------
# YAML study file creation
# ---------------------------------------------------------------------------


_STUDY_YAML_TEMPLATE = """\
metadata:
  name: "{name}"
  version: "{version}"
  description: "{description}"

dataset:
  identifier: "{dataset_id}"

cohorts:
  horizon_years: [{horizon_years}]

allocation_policy:
  type: "ConstantAllocationPolicy"
  equity_allocation: [{equity_values}]

withdrawal_policy:
  type: "ConstantWithdrawalPolicy"
  withdrawal_rate: [{withdrawal_rate}]
"""


def create_study_yaml(
    path: Path,
    name: str = "Integration Test Study",
    version: str = "1.0",
    description: str = "Study for integration testing",
    dataset_id: str = "INTEGRATION_TEST_v1",
    horizon_years: int = 30,
    withdrawal_rate: float = 0.04,
    equity_values: str = "0.50",
) -> Path:
    content = _STUDY_YAML_TEMPLATE.format(
        name=name,
        version=version,
        description=description,
        dataset_id=dataset_id,
        horizon_years=horizon_years,
        withdrawal_rate=withdrawal_rate,
        equity_values=equity_values,
    )
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Assertion utilities
# ---------------------------------------------------------------------------


def assert_study_exists(
    repo: SQLiteRepository,
    name: str,
) -> None:
    exp_id = repo.find_experiment_by_name(name)
    assert exp_id is not None, (
        f"Expected study {name!r} to exist in repository"
    )


def assert_study_not_exists(
    repo: SQLiteRepository,
    name: str,
) -> None:
    exp_id = repo.find_experiment_by_name(name)
    assert exp_id is None, (
        f"Expected study {name!r} not to exist in repository"
    )
