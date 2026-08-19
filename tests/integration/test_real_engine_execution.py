"""P4-CX – Real engine execution through a CLI-constructed plan (regression).

These tests exercise the ACTUAL simulation engine (not a mock) using a plan
built by the shared CLI builders with the intended ``equity``/``bond`` asset
model. They lock in two corrective fixes:

1. The initial portfolio must use ``equity``/``bond`` assets aligned with the
   dataset loader (the previous synthetic ``id="initial"`` asset was unpriced by
   the market universe and crashed real runs with "Missing market price").
2. ``SimulationState.allocation`` / ``allocation_target`` must be materialised
   by the order-0 ``InitializeAllocationStep`` before ``BuildDecisionContextStep``
   (the previous pipeline crashed with "SimulationState.allocation is required").

The ``sequential`` case is the regression guard; the ``parallel`` case also
exercises process-boundary serialization (mapping proxy pickling) of the plan.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Money
from fbf.core.domain.policies import ConstantAllocationPolicy, ConstantWithdrawalPolicy
from fbf.core.execution.strategies.parallel_executor import parallel_execute, sequential_execute
from fbf.core.study.builder import build_initial_portfolio
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import ResearchPlan, materialize_research_plan


def _loader_asset(asset_id: str) -> AssetClass:
    """Match the dataset loader's snapshot key convention (empty name)."""
    return AssetClass(id=asset_id, name="", description="")


def _make_equity_bond_dataset(months: int = 36) -> Dataset:
    snapshots = []
    for i in range(months):
        m = i + 1
        year = 2000 + (m - 1) // 12
        month = ((m - 1) % 12) + 1
        snapshots.append(
            MarketSnapshot(
                date=date(year, month, 1),
                index_levels={
                    _loader_asset("equity"): Decimal("100.00"),
                    _loader_asset("bond"): Decimal("50.00"),
                },
                inflation=Decimal("0.00"),
                inflation_cumulative=Decimal("0.00"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100.00"),
            )
        )
    return Dataset(snapshots=snapshots, frequency="monthly", version="v1")


def _build_plan(horizon_months: int = 12, param_sweep: int = 1) -> tuple[Dataset, ResearchPlan]:
    """Build a single-cohort plan aligned to the dataset origin.

    A single cohort whose start date equals ``dataset.start_date`` satisfies the
    frozen engine's ``dataset[0].date == context.start_date`` contract without
    needing per-cohort dataset slicing (a separate, out-of-scope work item).  This
    locks in the two authorised Model A fixes through the real fbf.core.
    """
    dataset = _make_equity_bond_dataset(36)
    alloc = ConstantAllocationPolicy(equity_allocation=Decimal("0.75"))
    withdraw = ConstantWithdrawalPolicy(withdrawal_rate=Decimal("0.04"))
    experiment = ExperimentDefinition(
        name="regression",
        description="Real-engine regression",
        dataset=dataset,
        horizon_months=horizon_months,
        initial_wealth=Money(Decimal("1000000"), Money.ZERO.currency),
        cohorts=(CohortSpecification(start_date=dataset.start_date),),
        allocation_policies=(alloc,),
        withdrawal_policies=(withdraw,),
    )
    param_configs = (
        ParameterConfiguration({"withdrawal_rate": 0.03 + i * 0.005})
        for i in range(param_sweep)
    )
    plan = materialize_research_plan(
        experiment_def=experiment,
        canonical_trajectory=dataset,
        cohorts=experiment.cohorts,
        param_configs=tuple(param_configs),
        initial_portfolio=build_initial_portfolio(experiment.initial_wealth),
        horizon_resolver=lambda c: horizon_months,
        policy_resolver=lambda c: (alloc, withdraw),
    )
    return dataset, plan


class TestRealEngineSequential:
    """Real ``sequential_execute`` through a CLI-built equity/bond plan."""

    def test_sequential_execute_runs_to_success(self) -> None:
        _, plan = _build_plan()
        result = sequential_execute(plan)
        assert len(result.results) == 1
        assert result.results[0].statistics.success is True

    def test_plan_uses_equity_bond_assets_not_synthetic_initial(self) -> None:
        dataset, plan = _build_plan()
        snapshot_keys = set(dataset[0].index_levels)
        assert "equity" in {a.id for a in snapshot_keys}
        for unit in plan.units:
            assets = {h.asset_class for h in unit.initial_portfolio.holdings}
            assert "initial" not in {a.id for a in assets}
            assert assets <= snapshot_keys


class TestRealEngineParallel:
    """Real ``parallel_execute`` (ProcessPoolExecutor) over a CLI-built plan."""

    @pytest.mark.parametrize("param_sweep", [4])
    def test_parallel_execution_serializes_and_runs(self, param_sweep: int) -> None:
        _, plan = _build_plan(param_sweep=param_sweep)
        expected = len(plan.units)
        result = parallel_execute(plan, max_workers=2)
        assert len(result.results) == expected
        assert all(r.statistics.success for r in result.results)
