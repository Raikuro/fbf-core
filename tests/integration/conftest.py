"""Shared fixtures for integration testing.

These fixtures are the reusable infrastructure for all integration
test packages (P4.1 through P4.5).  They provide managed temporary
databases, persistence reconstruction contexts, sample YAML studies,
and CLI-invocation helpers that isolate each test from persistent state.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from cli.main import main

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies.allocation_policy import AllocationPolicy
from fbf.core.domain.policies.decisions import AllocationDecision, WithdrawalDecision
from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy
from fbf.core.persistence.studies.sqlite import (
    create_persistence_context,
)
from fbf.core.persistence.studies.sqlite.codecs import DefaultDatasetResolver
from fbf.core.persistence.studies.sqlite.sqlite_repository import (
    PersistenceReconstructionContext,
    SQLiteRepository,
)
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan

# ---------------------------------------------------------------------------
# Asset class singleton reused across all integration fixtures
# ---------------------------------------------------------------------------

_INTEGRATION_ASSET = AssetClass(
    id="acwi", name="ACWI", description="Global equities"
)


# ---------------------------------------------------------------------------
# Dataset helpers
# ---------------------------------------------------------------------------


def _make_snapshot(d: date) -> MarketSnapshot:
    return MarketSnapshot(
        date=d,
        index_levels={_INTEGRATION_ASSET: Decimal("100.00")},
        inflation=Decimal("0.00"),
        inflation_cumulative=Decimal("0.00"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100.00"),
    )


def _make_dataset(num_months: int, start_year: int = 1871) -> Dataset:
    snapshots = []
    year = start_year
    month = 1
    for _ in range(num_months):
        snapshots.append(_make_snapshot(date(year, month, 1)))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return Dataset(snapshots=snapshots, frequency="monthly", version="INTEGRATION_TEST_v1")


# ---------------------------------------------------------------------------
# Policy stubs for integration fixtures
# ---------------------------------------------------------------------------


class _IntegrationAllocationPolicy(AllocationPolicy):
    def __init__(self, equity_allocation: Decimal = Decimal("0.75")) -> None:
        self.equity_allocation = equity_allocation

    def decide(self, context: object) -> AllocationDecision:
        from fbf.core.domain.model.allocation import AllocationTarget
        equity = AssetClass(id="equity", name="Equity", description="")
        bond = AssetClass(id="bond", name="Bond", description="")
        return AllocationDecision(
            reason="integration_allocation",
            allocation_target=AllocationTarget(weights={
                equity: self.equity_allocation,
                bond: Decimal("1") - self.equity_allocation,
            }),
        )


class _IntegrationWithdrawalPolicy(WithdrawalPolicy):
    def __init__(self, withdrawal_rate: Decimal = Decimal("0.04")) -> None:
        self.withdrawal_rate = withdrawal_rate

    def decide(self, context: object) -> WithdrawalDecision:
        total = Decimal("1000000")
        monthly = total * self.withdrawal_rate / Decimal("12")
        return WithdrawalDecision(
            reason="integration_withdrawal",
            nominal_amount=Money(monthly, Currency.EUR),
            real_amount=Money(monthly, Currency.EUR),
        )


# ---------------------------------------------------------------------------
# Persistence – managed temporary database
# ---------------------------------------------------------------------------


@pytest.fixture
def integration_db_path(tmp_path: Path) -> Path:
    return tmp_path / "integration_test.db"


@pytest.fixture
def integration_repo(integration_db_path: Path) -> Iterator[SQLiteRepository]:
    repo = SQLiteRepository(str(integration_db_path))
    yield repo


@pytest.fixture
def persistence_context() -> PersistenceReconstructionContext:
    return create_persistence_context()


@pytest.fixture
def persistence_context_with_dataset(
    sample_dataset: Dataset,
) -> PersistenceReconstructionContext:
    resolver = DefaultDatasetResolver(
        datasets={sample_dataset.version: sample_dataset}
    )
    ctx = create_persistence_context()
    return PersistenceReconstructionContext(
        dataset_resolver=resolver,
        policy_codecs=ctx.policy_codecs,
        simulation_result_codec=ctx.simulation_result_codec,
    )


# ---------------------------------------------------------------------------
# Sample domain objects for integration tests
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_dataset() -> Dataset:
    return _make_dataset(500, start_year=2000)


@pytest.fixture
def sample_experiment(sample_dataset: Dataset) -> ExperimentDefinition:
    return ExperimentDefinition(
        name="integration-test-experiment",
        description="Integration test experiment definition",
        dataset=sample_dataset,
        horizon_months=120,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        cohorts=(
            CohortSpecification(start_date=date(2000, 1, 1)),
            CohortSpecification(start_date=date(2000, 2, 1)),
        ),
        allocation_policies=(_IntegrationAllocationPolicy(),),
        withdrawal_policies=(_IntegrationWithdrawalPolicy(),),
    )


@pytest.fixture
def sample_plan(sample_experiment: ExperimentDefinition) -> ResearchPlan:
    dataset1 = sample_experiment.dataset.slice(date(2000, 1, 1), 120)
    dataset2 = sample_experiment.dataset.slice(date(2000, 2, 1), 120)
    unit1 = PlannedSimulationUnit(
        cohort=CohortSpecification(start_date=date(2000, 1, 1)),
        parameter_config=ParameterConfiguration(values={"withdrawal_rate": 0.04}),
        allocation_policy=_IntegrationAllocationPolicy(),
        withdrawal_policy=_IntegrationWithdrawalPolicy(),
        initial_portfolio=Portfolio(
            holdings=(AssetHolding(asset_class=_INTEGRATION_ASSET, units=Decimal("1000")),)
        ),
        dataset=dataset1,
    )
    unit2 = PlannedSimulationUnit(
        cohort=CohortSpecification(start_date=date(2000, 2, 1)),
        parameter_config=ParameterConfiguration(values={"withdrawal_rate": 0.04}),
        allocation_policy=_IntegrationAllocationPolicy(),
        withdrawal_policy=_IntegrationWithdrawalPolicy(),
        initial_portfolio=Portfolio(
            holdings=(AssetHolding(asset_class=_INTEGRATION_ASSET, units=Decimal("1000")),)
        ),
        dataset=dataset2,
    )
    return ResearchPlan(experiment_definition=sample_experiment, units=(unit1, unit2))


# ---------------------------------------------------------------------------
# YAML study file fixture
# ---------------------------------------------------------------------------


_INTEGRATION_STUDY_YAML = """\
metadata:
  name: "Integration Test Study"
  version: "1.0"
  description: "Standard study for integration testing"

dataset:
  identifier: "INTEGRATION_TEST_v1"

cohorts:
  horizon_years: [30]

allocation_policy:
  type: "ConstantAllocationPolicy"
  equity_allocation: [0.75]

withdrawal_policy:
  type: "ConstantWithdrawalPolicy"
  withdrawal_rate: [0.04]
"""


@pytest.fixture
def study_yaml_path(tmp_path: Path) -> Path:
    path = tmp_path / "study.yaml"
    path.write_text(_INTEGRATION_STUDY_YAML, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# CLI invocation helper
# ---------------------------------------------------------------------------


@pytest.fixture
def invoke_cli() -> Any:
    """Return a callable that invokes CLI main() with args and captures output."""
    def _invoke(args: list[str]) -> int:
        return main(args)
    return _invoke
