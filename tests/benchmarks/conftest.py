"""Shared fixtures and timing utilities for performance benchmarks.

Reuses P4.1 integration framework where possible.
Provides benchmark-specific domain object factories and a
simple wall-clock timer that prints results to stdout.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies.allocation_policy import AllocationPolicy
from fbf.core.domain.policies.decisions import AllocationDecision, WithdrawalDecision
from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy
from fbf.core.persistence.studies.sqlite import (
    PersistenceReconstructionContext,
    SQLiteRepository,
    create_persistence_context,
)
from fbf.core.persistence.studies.sqlite.codecs import DefaultDatasetResolver
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BENCHMARK_ASSET = AssetClass(
    id="acwi", name="ACWI", description="Global equities"
)

# ---------------------------------------------------------------------------
# Timing utility (unused – benchmarks use inline time.perf_counter)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Dataset factories
# ---------------------------------------------------------------------------


def _snapshot(d: date) -> MarketSnapshot:
    return MarketSnapshot(
        date=d,
        index_levels={BENCHMARK_ASSET: Decimal("100.00")},
        inflation=Decimal("0.00"),
        inflation_cumulative=Decimal("0.00"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100.00"),
    )


def make_benchmark_dataset(num_months: int, version: str = "BENCHMARK_v1") -> Dataset:
    snapshots = []
    for i in range(num_months):
        m = i + 1
        year = 2000 + (m - 1) // 12
        month = ((m - 1) % 12) + 1
        snapshots.append(_snapshot(date(year, month, 1)))
    return Dataset(snapshots=snapshots, frequency="monthly", version=version)


# ---------------------------------------------------------------------------
# Policy stubs (identical semantics to integration helpers)
# ---------------------------------------------------------------------------


class BenchmarkAllocationPolicy(AllocationPolicy):
    def __init__(self, equity_allocation: Decimal = Decimal("0.75")) -> None:
        self.equity_allocation = equity_allocation

    def decide(self, context: object) -> AllocationDecision:
        from fbf.core.domain.model.allocation import AllocationTarget

        equity = AssetClass(id="equity", name="Equity", description="")
        bond = AssetClass(id="bond", name="Bond", description="")
        return AllocationDecision(
            reason="benchmark_allocation",
            allocation_target=AllocationTarget(
                weights={
                    equity: self.equity_allocation,
                    bond: Decimal("1") - self.equity_allocation,
                }
            ),
        )


class BenchmarkWithdrawalPolicy(WithdrawalPolicy):
    def __init__(self, withdrawal_rate: Decimal = Decimal("0.04")) -> None:
        self.withdrawal_rate = withdrawal_rate

    def decide(self, context: object) -> WithdrawalDecision:
        total = Decimal("1000000")
        monthly = total * self.withdrawal_rate / Decimal("12")
        return WithdrawalDecision(
            reason="benchmark_withdrawal",
            nominal_amount=Money(monthly, Currency.EUR),
            real_amount=Money(monthly, Currency.EUR),
        )


# ---------------------------------------------------------------------------
# Plan factory
# ---------------------------------------------------------------------------


def make_benchmark_plan(
    num_units: int = 4,
    horizon_months: int = 60,
    dataset: Dataset | None = None,
) -> ResearchPlan:
    if dataset is None:
        dataset = make_benchmark_dataset(horizon_months + 12)
    experiment = ExperimentDefinition(
        name="benchmark-experiment",
        description="Benchmark experiment definition",
        dataset=dataset,
        horizon_months=horizon_months,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        cohorts=tuple(
            CohortSpecification(start_date=date(2000, 1 + i, 1))
            for i in range(min(num_units, 12))
        ),
        allocation_policies=(BenchmarkAllocationPolicy(),),
        withdrawal_policies=(BenchmarkWithdrawalPolicy(),),
    )
    units = tuple(
        PlannedSimulationUnit(
            cohort=CohortSpecification(start_date=date(2000, 1 + i, 1)),
            parameter_config=ParameterConfiguration(values={"withdrawal_rate": 0.04}),
            allocation_policy=BenchmarkAllocationPolicy(),
            withdrawal_policy=BenchmarkWithdrawalPolicy(),
            initial_portfolio=Portfolio(
                holdings=(
                    AssetHolding(asset_class=BENCHMARK_ASSET, units=Decimal("1000")),
                )
            ),
            dataset=dataset.slice(date(2000, 1 + i, 1), horizon_months),
        )
        for i in range(num_units)
    )
    return ResearchPlan(experiment_definition=experiment, units=units)


# ---------------------------------------------------------------------------
# Repository helpers
# ---------------------------------------------------------------------------


def make_benchmark_repo(path: Path) -> SQLiteRepository:
    return SQLiteRepository(str(path))


def make_persistence_context(dataset: Dataset) -> PersistenceReconstructionContext:
    resolver = DefaultDatasetResolver(datasets={dataset.version: dataset})
    ctx = create_persistence_context()
    return PersistenceReconstructionContext(
        dataset_resolver=resolver,
        policy_codecs=ctx.policy_codecs,
        simulation_result_codec=ctx.simulation_result_codec,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bm_dataset_small() -> Dataset:
    return make_benchmark_dataset(60)


@pytest.fixture
def bm_dataset_medium() -> Dataset:
    return make_benchmark_dataset(120)


@pytest.fixture
def bm_small_plan(bm_dataset_small: Dataset) -> ResearchPlan:
    return make_benchmark_plan(num_units=2, horizon_months=12, dataset=bm_dataset_small)


@pytest.fixture
def bm_medium_plan(bm_dataset_medium: Dataset) -> ResearchPlan:
    return make_benchmark_plan(num_units=4, horizon_months=60, dataset=bm_dataset_medium)

@pytest.fixture
def bm_plan_8_units(bm_dataset_medium: Dataset) -> ResearchPlan:
    return make_benchmark_plan(num_units=8, horizon_months=60, dataset=bm_dataset_medium)

@pytest.fixture
def bm_persistence_context(bm_dataset_medium: Dataset) -> PersistenceReconstructionContext:
    return make_persistence_context(bm_dataset_medium)


@pytest.fixture
def bm_repo(tmp_path: Path) -> Iterator[SQLiteRepository]:
    repo = make_benchmark_repo(tmp_path / "benchmark.db")
    yield repo
