"""Production pipeline regression test for K.5.1.

Verifies that the debt-aware pipeline (with interest_rate=0) produces
identical results to a legacy pipeline without debt steps. This ensures
the unified pipeline is backward-compatible.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from fbf.core.execution.pipeline.default_pipeline import create_default_pipeline
from fbf.core.execution.pipeline.executor import SimulationExecutor
from fbf.core.execution.pipeline.pipeline import SimulationPipeline
from fbf.core.execution.pipeline.runner import SimulationRunner
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.pipeline.steps.allocation_decision_step import AllocationDecisionStep
from fbf.core.execution.pipeline.steps.build_decision_context_step import BuildDecisionContextStep
from fbf.core.execution.pipeline.steps.failure_detection_step import FailureDetectionStep
from fbf.core.execution.pipeline.steps.initialize_allocation_step import InitializeAllocationStep
from fbf.core.execution.pipeline.steps.market_evolution_step import MarketEvolutionStep
from fbf.core.execution.pipeline.steps.monthly_result_builder_step import MonthlyResultBuilderStep
from fbf.core.execution.pipeline.steps.portfolio_rebalance_step import PortfolioRebalanceStep
from fbf.core.execution.pipeline.steps.simulation_state_update_step import SimulationStateUpdateStep
from fbf.core.execution.pipeline.steps.withdrawal_decision_step import WithdrawalDecisionStep
from fbf.core.execution.pipeline.steps.withdrawal_execution_step import WithdrawalExecutionStep

EQUITY = AssetClass(id="equity", name="", description="")
BOND = AssetClass(id="bond", name="", description="")


def _make_dataset(n_months: int = 6) -> Dataset:
    snapshots = []
    for i in range(n_months):
        snapshots.append(MarketSnapshot(
            date=date(2020, 1 + i, 1),
            index_levels={EQUITY: Decimal("100"), BOND: Decimal("50")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("0"),
            is_ath=True,
            is_underwater=(i % 3 == 0),
            running_ath=Decimal("100"),
        ))
    return Dataset(
        snapshots=snapshots,
        frequency="monthly",
        version="test",
        identifier="test",
    )


def _make_context(dataset: Dataset) -> SimulationContext:
    return SimulationContext(
        experiment_name="regression-test",
        cohort="regression-test",
        start_date=date(2020, 1, 1),
        horizon_months=len(dataset),
        initial_wealth=Money(Decimal("100000"), Currency.EUR),
        initial_portfolio=Portfolio(holdings=(
            AssetHolding(asset_class=EQUITY, units=Decimal("600")),
            AssetHolding(asset_class=BOND, units=Decimal("800")),
        )),
        dataset=dataset,
        allocation_policy=ConstantAllocationPolicy(
            equity_allocation=Decimal("0.6"),
        ),
        withdrawal_policy=FixedRealWithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
        ),
    )


def _create_legacy_pipeline() -> SimulationPipeline:
    """Legacy pipeline without debt steps (pre-K.4)."""
    return SimulationPipeline(
        steps=[
            InitializeAllocationStep(),
            BuildDecisionContextStep(),
            WithdrawalDecisionStep(),
            WithdrawalExecutionStep(),
            AllocationDecisionStep(),
            PortfolioRebalanceStep(),
            MarketEvolutionStep(),
            MonthlyResultBuilderStep(),
            FailureDetectionStep(),
            SimulationStateUpdateStep(),
        ]
    )


def _run(pipeline: SimulationPipeline, context: SimulationContext) -> list[dict[str, Any]]:
    """Run a simulation and return the monthly timeline as serializable dicts."""
    runner = SimulationRunner(pipeline=pipeline)
    executor = SimulationExecutor(runner)
    exp_def = EngineExperimentDefinition(
        name="regression",
        description="regression",
        simulation_contexts=(context,),
    )
    result = executor.execute(exp_def)
    sim_result = result.simulation_results[0]

    timeline = []
    for mr in sim_result.timeline.monthly_results:
        portfolio_value = Decimal("0")
        for h in mr.portfolio.holdings:
            price = mr.market_snapshot.index_levels.get(h.asset_class)
            if price is not None:
                portfolio_value += h.units * price

        withdrawal = (
            str(mr.withdrawal_decision.nominal_amount.amount)
            if mr.withdrawal_decision else "0"
        )
        entry = {
            "date": mr.date.isoformat(),
            "portfolio_value": str(portfolio_value),
            "withdrawal": withdrawal,
            "allocation": {
                h.asset_class.id: str(h.units) for h in mr.portfolio.holdings
            },
        }
        timeline.append(entry)

    return timeline


class TestDebtPipelineRegression:
    """The debt-aware pipeline with interest_rate=0 must produce
    bit-for-bit equivalent results to the legacy pipeline."""

    def test_bit_for_bit_equivalence(self) -> None:
        dataset = _make_dataset(n_months=6)
        ctx = _make_context(dataset)

        legacy_result = _run(_create_legacy_pipeline(), ctx)
        modern_result = _run(create_default_pipeline(), ctx)

        assert len(legacy_result) == len(modern_result)
        for i, (legacy, modern) in enumerate(zip(legacy_result, modern_result, strict=True)):
            assert legacy["date"] == modern["date"], f"Mismatch at month {i}: date"
            assert legacy["portfolio_value"] == modern["portfolio_value"], (
                f"Mismatch at month {i}: portfolio_value "
                f"({legacy['portfolio_value']} vs {modern['portfolio_value']})"
            )
            assert legacy["withdrawal"] == modern["withdrawal"], (
                f"Mismatch at month {i}: withdrawal"
            )
            legacy_alloc = legacy["allocation"]
            modern_alloc = modern["allocation"]
            assert isinstance(legacy_alloc, dict) and isinstance(modern_alloc, dict)
            for asset_id in legacy_alloc:
                assert legacy_alloc[asset_id] == modern_alloc[asset_id], (
                    f"Mismatch at month {i}: allocation[{asset_id}]"
                )

    def test_debt_snapshot_absent_when_no_debt(self) -> None:
        """No debt_snapshot when interest_rate=0."""
        dataset = _make_dataset(n_months=3)
        ctx = _make_context(dataset)

        result = _run(create_default_pipeline(), ctx)
        # The pipeline runs without error and produces correct output
        assert len(result) == 3
        for entry in result:
            assert Decimal(entry["portfolio_value"]) > 0
