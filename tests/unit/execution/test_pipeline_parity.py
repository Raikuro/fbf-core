"""Pipeline parity tests.

Verifies that the parallel executor's production pipeline and the
canonical default pipeline contain the same steps in the same order,
and that a leveraged scenario produces identical results through both
execution paths.

This prevents the class of defect where LoanRepaymentStep was present
in the canonical pipeline but missing from the parallel executor's
pipeline.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from fbf.core.execution.pipeline.default_pipeline import create_default_pipeline
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.parallel_executor import (
    _create_default_simulation_executor,
)

EQUITY = AssetClass(id="equity", name="", description="")
BOND = AssetClass(id="bond", name="", description="")


# ---------------------------------------------------------------------------
# Structural parity
# ---------------------------------------------------------------------------


class TestPipelineStructuralParity:
    """The canonical and parallel-executor pipelines must contain the
    same step types in the same order."""

    def test_step_types_and_order_match(self) -> None:
        canonical = create_default_pipeline()
        parallel = _create_default_simulation_executor()

        canonical_types = [type(step) for step in canonical.steps]
        parallel_types = [type(step) for step in parallel._simulation_runner.pipeline.steps]

        assert canonical_types == parallel_types, (
            "Canonical and parallel pipeline step types differ:\n"
            f"  canonical:  {[t.__name__ for t in canonical_types]}\n"
            f"  parallel:   {[t.__name__ for t in parallel_types]}"
        )

    def test_canonical_has_repayment_step(self) -> None:
        from fbf.core.execution.pipeline.steps.loan_repayment_step import LoanRepaymentStep

        pipeline = create_default_pipeline()
        step_types = [type(step) for step in pipeline.steps]
        assert LoanRepaymentStep in step_types

    def test_parallel_has_repayment_step(self) -> None:
        from fbf.core.execution.pipeline.steps.loan_repayment_step import LoanRepaymentStep

        executor = _create_default_simulation_executor()
        step_types = [type(step) for step in executor._simulation_runner.pipeline.steps]
        assert LoanRepaymentStep in step_types


# ---------------------------------------------------------------------------
# Behavioral parity: leveraged scenario
# ---------------------------------------------------------------------------


def _make_debt_dataset() -> Dataset:
    """12-month dataset with equity drawdown and recovery for leverage testing."""
    snapshots = []
    equity_levels = [
        "100",    # M0: ATH
        "95",     # M1: -5%
        "85",     # M2: -15% → drawdown >= 20% threshold
        "80",     # M3: -20% → deep drawdown
        "82",     # M4: slight recovery
        "90",     # M5: recovery
        "101",    # M6: NEW ATH → triggers repayment
        "105",    # M7
        "110",    # M8
        "108",    # M9
        "112",    # M10
        "115",    # M11
    ]
    for i, eq in enumerate(equity_levels):
        snapshots.append(MarketSnapshot(
            date=date(2020, 1 + i, 1) if i < 12 else date(2021, 1, 1),
            index_levels={EQUITY: Decimal(eq), BOND: Decimal("50")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=(Decimal(eq) >= Decimal("100")),
            is_underwater=(Decimal(eq) < Decimal("100")),
            running_ath=max(Decimal(e) for e in equity_levels[: i + 1]),
        ))
    return Dataset(
        snapshots=tuple(snapshots),
        frequency="monthly",
        version="test",
        identifier="debt-parity-test",
    )


def _make_leveraged_context(dataset: Dataset) -> SimulationContext:
    """Context with Part52-like debt parameters."""
    return SimulationContext(
        experiment_name="parity-test",
        cohort="2020-01",
        start_date=date(2020, 1, 1),
        horizon_months=12,
        initial_wealth=Money(Decimal("100000"), Currency.EUR),
        initial_portfolio=Portfolio(holdings=(
            AssetHolding(asset_class=EQUITY, units=Decimal("500")),
            AssetHolding(asset_class=BOND, units=Decimal("1000")),
        )),
        dataset=dataset,
        allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.75")),
        withdrawal_policy=FixedRealWithdrawalPolicy(withdrawal_rate=Decimal("0.04")),
        interest_rate=Decimal("0.015"),
        ltv_limit=Decimal("0.50"),
        ltv_enforcement=True,
    )


def _run_and_extract(executor: object, context: SimulationContext) -> list[dict[str, object]]:
    """Run a single context through an executor and extract key financial metrics."""
    from fbf.core.execution.pipeline.executor import SimulationExecutor

    assert isinstance(executor, SimulationExecutor)
    definition = EngineExperimentDefinition(
        name="parity-test",
        description="parity-test",
        simulation_contexts=(context,),
    )
    run = executor.execute(definition)
    result = run.simulation_results[0]

    timeline = []
    for mr in result.timeline.monthly_results:
        portfolio_value = Decimal("0")
        for h in mr.portfolio.holdings:
            price = mr.market_snapshot.index_levels.get(h.asset_class)
            if price is not None:
                portfolio_value += h.units * price

        loan_balance = mr.debt_snapshot.loan_balance if mr.debt_snapshot else Decimal("0")
        ltv = mr.debt_snapshot.ltv if mr.debt_snapshot else Decimal("0")
        nw = mr.debt_snapshot.net_worth if mr.debt_snapshot else portfolio_value

        timeline.append({
            "month": mr.period_index,
            "date": mr.date.isoformat(),
            "portfolio_value": str(portfolio_value),
            "loan_balance": str(loan_balance),
            "ltv": str(ltv),
            "net_worth": str(nw),
            "is_repayment": mr.is_repayment,
            "success": result.statistics.success,
            "final_wealth": str(result.statistics.final_wealth.amount),
        })
    return timeline


class TestLeveragedSequentialParallelParity:
    """A leveraged scenario must produce identical results through both
    the canonical pipeline (via SimulationExecutor) and the parallel
    executor's reference pipeline."""

    def test_leveraged_results_match(self) -> None:
        from fbf.core.execution.pipeline.executor import SimulationExecutor
        from fbf.core.execution.pipeline.runner import SimulationRunner

        dataset = _make_debt_dataset()
        context = _make_leveraged_context(dataset)

        # Canonical pipeline
        canonical_pipeline = create_default_pipeline()
        canonical_runner = SimulationRunner(canonical_pipeline)
        canonical_executor = SimulationExecutor(canonical_runner)

        # Parallel executor's reference pipeline
        parallel_executor = _create_default_simulation_executor()

        canonical_timeline = _run_and_extract(canonical_executor, context)
        parallel_timeline = _run_and_extract(parallel_executor, context)

        assert len(canonical_timeline) == len(parallel_timeline), (
            f"Timeline length differs: {len(canonical_timeline)} vs {len(parallel_timeline)}"
        )

        for _i, (cp, pp) in enumerate(zip(canonical_timeline, parallel_timeline, strict=True)):
            assert cp["portfolio_value"] == pp["portfolio_value"], (
                f"M{cp['month']}: portfolio_value differs "
                f"(canonical={cp['portfolio_value']}, parallel={pp['portfolio_value']})"
            )
            assert cp["loan_balance"] == pp["loan_balance"], (
                f"M{cp['month']}: loan_balance differs "
                f"(canonical={cp['loan_balance']}, parallel={pp['loan_balance']})"
            )
            assert cp["ltv"] == pp["ltv"], (
                f"M{cp['month']}: ltv differs "
                f"(canonical={cp['ltv']}, parallel={pp['ltv']})"
            )
            assert cp["net_worth"] == pp["net_worth"], (
                f"M{cp['month']}: net_worth differs "
                f"(canonical={cp['net_worth']}, parallel={pp['net_worth']})"
            )
            assert cp["is_repayment"] == pp["is_repayment"], (
                f"M{cp['month']}: is_repayment differs "
                f"(canonical={cp['is_repayment']}, parallel={pp['is_repayment']})"
            )

        # Final outcomes
        assert canonical_timeline[-1]["success"] == parallel_timeline[-1]["success"]
        assert canonical_timeline[-1]["final_wealth"] == parallel_timeline[-1]["final_wealth"]

    def test_leveraged_executor_paths_produce_same_result(self) -> None:
        """Both executor construction paths yield functionally equivalent results.

        One path constructs SimulationExecutor directly with the canonical
        pipeline.  The other goes through _create_default_simulation_executor()
        which constructs the parallel executor's reference.  Both must produce
        the same simulation outcomes.
        """
        from fbf.core.execution.pipeline.executor import SimulationExecutor
        from fbf.core.execution.pipeline.runner import SimulationRunner

        dataset = _make_debt_dataset()
        context = _make_leveraged_context(dataset)

        # Path A: canonical
        runner_a = SimulationRunner(create_default_pipeline())
        exec_a = SimulationExecutor(runner_a)

        # Path B: parallel reference
        exec_b = _create_default_simulation_executor()

        from fbf.core.execution.pipeline.simulation import SimulationResult as SimResult

        def _run(executor: SimulationExecutor) -> SimResult:
            definition = EngineExperimentDefinition(
                name="test", description="test",
                simulation_contexts=(context,),
            )
            result = executor.execute(definition).simulation_results[0]
            assert isinstance(result, SimResult)
            return result

        result_a = _run(exec_a)
        result_b = _run(exec_b)

        # Both must agree on success and final wealth
        assert result_a.statistics.success == result_b.statistics.success
        assert result_a.statistics.final_wealth == result_b.statistics.final_wealth
        assert result_a.statistics.failure_month == result_b.statistics.failure_month
