"""R6 Final Check — Terminal Depletion Verification.

End-to-end verification that depleted trajectories terminate correctly,
including execution, horizon chaining, in-memory results, and SQLite persistence.
"""

from __future__ import annotations

import json
import sqlite3
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
from fbf.core.domain.policies.concrete import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from fbf.core.execution.pipeline.pipeline import SimulationPipeline
from fbf.core.execution.pipeline.runner import SimulationRunner
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition,
    ExperimentRun,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.pipeline.steps.allocation_decision_step import AllocationDecisionStep
from fbf.core.execution.pipeline.steps.build_decision_context_step import BuildDecisionContextStep
from fbf.core.execution.pipeline.steps.initialize_allocation_step import InitializeAllocationStep
from fbf.core.execution.pipeline.steps.market_evolution_step import MarketEvolutionStep
from fbf.core.execution.pipeline.steps.monthly_result_builder_step import MonthlyResultBuilderStep
from fbf.core.execution.pipeline.steps.portfolio_rebalance_step import PortfolioRebalanceStep
from fbf.core.execution.pipeline.steps.simulation_state_update_step import SimulationStateUpdateStep
from fbf.core.execution.pipeline.steps.withdrawal_decision_step import WithdrawalDecisionStep
from fbf.core.execution.pipeline.steps.withdrawal_execution_step import WithdrawalExecutionStep
from fbf.core.persistence.studies.sqlite.codecs import SimulationResultCodec
from fbf.core.persistence.studies.sqlite.sqlite_repository import (
    ExperimentIdentity,
    PersistenceReconstructionContext,
    SQLiteRepository,
)
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import (
    ExperimentDefinition as ResearchExperimentDefinition,
)
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _make_asset(id: str = "ACWI") -> AssetClass:
    return AssetClass(id=id, name=id, description=f"Asset {id}")


def _make_dataset(
    start: date, months: int, base_price: Decimal = Decimal("100")
) -> list[MarketSnapshot]:
    """Create a minimal dataset with constant prices for equity and bond.

    Uses empty name/description to match ConstantAllocationPolicy's AssetClass.
    """
    equity = AssetClass(id="equity", name="", description="")
    bond = AssetClass(id="bond", name="", description="")
    snapshots = []
    current = start
    for _ in range(months):
        snapshots.append(
            MarketSnapshot(
                date=current,
                index_levels={equity: base_price, bond: base_price},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=False,
                is_underwater=False,
                running_ath=base_price,
            )
        )
        # Advance month
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return snapshots


def _make_portfolio(equity_units: Decimal = Decimal("10000")) -> Portfolio:
    equity = AssetClass(id="equity", name="", description="")
    return Portfolio(holdings=(AssetHolding(asset_class=equity, units=equity_units),))


def _make_context(
    start_date: date,
    horizon_months: int,
    initial_wealth: Money,
    initial_portfolio: Portfolio,
    dataset: list[MarketSnapshot],
    withdrawal_rate: Decimal = Decimal("0.04"),
) -> SimulationContext:
    return SimulationContext(
        experiment_name="test",
        cohort="test_cohort",
        start_date=start_date,
        horizon_months=horizon_months,
        initial_wealth=initial_wealth,
        initial_portfolio=initial_portfolio,
        dataset=Dataset(snapshots=tuple(dataset), frequency="M", version="1.0", identifier="test"),
        allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("1.0")),
        withdrawal_policy=FixedRealWithdrawalPolicy(withdrawal_rate=withdrawal_rate),
    )


def _make_pipeline() -> SimulationPipeline:
    return SimulationPipeline(
        [
            InitializeAllocationStep(),
            BuildDecisionContextStep(),
            WithdrawalDecisionStep(),
            WithdrawalExecutionStep(),
            AllocationDecisionStep(),
            PortfolioRebalanceStep(),
            MarketEvolutionStep(),
            MonthlyResultBuilderStep(),
            SimulationStateUpdateStep(),
        ]
    )


# ---------------------------------------------------------------------------
# A. Execution proof — concrete depleted trajectory
# ---------------------------------------------------------------------------

class TestExecutionTermination:
    """Verify that a depleted trajectory terminates at the depletion month."""

    def test_depleted_trajectory_terminates_at_depletion_month(self) -> None:
        """A trajectory with high withdrawal rate depletes before the horizon.

        Uses 100% annual withdrawal rate on a $10,000 portfolio = $833/month.
        Should deplete within ~12 months.
        """
        start = date(1970, 1, 1)
        horizon = 60  # 5 years = 60 months
        initial_wealth = Money(Decimal("10000"), Currency.EUR)
        initial_portfolio = _make_portfolio(Decimal("100"))  # 100 units at $100 = $10,000
        dataset = _make_dataset(start, horizon, base_price=Decimal("100"))

        # 100% annual withdrawal rate = $10,000 * 1.0 / 12 = $833.33/month
        ctx = _make_context(start, horizon, initial_wealth, initial_portfolio, dataset,
                           withdrawal_rate=Decimal("1.0"))

        pipeline = _make_pipeline()
        runner = SimulationRunner(pipeline)
        result = runner.run(ctx)

        # Verify: trajectory did NOT complete the full horizon
        assert result.statistics.success is False
        assert result.statistics.failure_month is not None
        assert result.statistics.failure_month < horizon

        # Verify: timeline contains only the months actually simulated
        # Depletion happens at WithdrawalExecutionStep (step 30).
        # When depletion is detected, the inner loop breaks immediately.
        # Steps 40-80 (including MonthlyResultBuilderStep at step 70) do NOT execute.
        # Therefore, the depletion month is NOT in the timeline.
        # The timeline contains months 0 through (failure_month - 1).
        assert len(result.timeline.monthly_results) == result.statistics.failure_month

        # Verify: the last recorded month has a date consistent with the failure month
        if result.timeline.monthly_results:
            last_month = result.timeline.monthly_results[-1]
            # failure_month is the period_index where failure occurred
            # The last recorded month should be at period_index = failure_month - 1
            assert last_month.period_index == result.statistics.failure_month - 1

    def test_depletion_at_initial_withdrawal(self) -> None:
        """A trajectory that depletes on the very first withdrawal."""
        start = date(1970, 1, 1)
        horizon = 60
        # Very small portfolio: $100 (1 unit at $100)
        initial_wealth = Money(Decimal("100"), Currency.EUR)
        equity = AssetClass(id="equity", name="", description="")
        initial_portfolio = Portfolio(
            holdings=(AssetHolding(asset_class=equity, units=Decimal("1")),)
        )
        dataset = _make_dataset(start, horizon, base_price=Decimal("100"))

        # 1000% annual withdrawal rate = $100 * 10.0 / 12 = $83.33/month
        # That should deplete in ~1 month
        ctx = _make_context(start, horizon, initial_wealth, initial_portfolio, dataset,
                           withdrawal_rate=Decimal("10.0"))

        pipeline = _make_pipeline()
        runner = SimulationRunner(pipeline)
        result = runner.run(ctx)

        assert result.statistics.success is False
        assert result.statistics.failure_month is not None
        # Should deplete very quickly
        assert result.statistics.failure_month <= 2

    def test_non_depleted_trajectory_completes_horizon(self) -> None:
        """A trajectory with sustainable withdrawal completes the full horizon."""
        start = date(1970, 1, 1)
        horizon = 12  # 1 year
        initial_wealth = Money(Decimal("1000000"), Currency.EUR)
        initial_portfolio = _make_portfolio(Decimal("10000"))
        dataset = _make_dataset(start, horizon, base_price=Decimal("100"))

        # 4% annual withdrawal rate = $1,000,000 * 0.04 / 12 = $3,333/month
        # On a $1,000,000 portfolio, this is sustainable
        ctx = _make_context(start, horizon, initial_wealth, initial_portfolio, dataset,
                           withdrawal_rate=Decimal("0.04"))

        pipeline = _make_pipeline()
        runner = SimulationRunner(pipeline)
        result = runner.run(ctx)

        assert result.statistics.success is True
        assert result.statistics.failure_month is None
        assert len(result.timeline.monthly_results) == horizon


# ---------------------------------------------------------------------------
# B. Pipeline proof — no steps execute after depletion
# ---------------------------------------------------------------------------

class TestPipelineTermination:
    """Verify that no pipeline steps execute after depletion is detected."""

    def test_no_steps_after_depletion(self) -> None:
        """When WithdrawalExecutionStep sets failure_state, steps 40-80 are skipped."""
        start = date(1970, 1, 1)
        horizon = 60
        initial_wealth = Money(Decimal("100"), Currency.EUR)
        equity = AssetClass(id="equity", name="", description="")
        initial_portfolio = Portfolio(
            holdings=(AssetHolding(asset_class=equity, units=Decimal("1")),)
        )
        dataset = _make_dataset(start, horizon, base_price=Decimal("100"))

        # 1000% annual withdrawal rate = $100 * 10.0 / 12 = $83.33/month
        ctx = _make_context(start, horizon, initial_wealth, initial_portfolio, dataset,
                           withdrawal_rate=Decimal("10.0"))

        pipeline = _make_pipeline()
        runner = SimulationRunner(pipeline)
        result = runner.run(ctx)

        # Verify: failure detected
        assert result.statistics.failure_month is not None

        # Verify: no monthly results recorded for the depletion month
        # Because depletion happens at step 30, and MonthlyResultBuilderStep is at step 70
        # The timeline should only contain months before depletion
        assert len(result.timeline.monthly_results) == result.statistics.failure_month


# ---------------------------------------------------------------------------
# C. Horizon chaining proof
# ---------------------------------------------------------------------------

class TestHorizonChaining:
    """Verify that a terminal trajectory propagates correctly across horizons."""

    def test_depleted_trajectory_fails_all_horizons(self) -> None:
        """A trajectory that depletes early should fail for all longer horizons."""
        start = date(1970, 1, 1)
        initial_wealth = Money(Decimal("10000"), Currency.EUR)
        initial_portfolio = _make_portfolio(Decimal("100"))

        # Create dataset long enough for the longest horizon
        max_horizon = 60 * 12  # 60 years in months
        dataset = _make_dataset(start, max_horizon, base_price=Decimal("100"))

        horizons_years = [30, 40, 50, 60]
        results = {}

        for years in horizons_years:
            horizon_months = years * 12
            # 100% annual withdrawal rate on $10,000 = $833/month
            ctx = _make_context(start, horizon_months, initial_wealth, initial_portfolio, dataset,
                               withdrawal_rate=Decimal("1.0"))

            pipeline = _make_pipeline()
            runner = SimulationRunner(pipeline)
            result = runner.run(ctx)
            results[years] = result

        # All horizons should report failure
        for years in horizons_years:
            assert results[years].statistics.success is False, f"Horizon {years} should fail"
            assert results[years].statistics.failure_month is not None

        # The failure month should be the same for all horizons
        # (depletion happens at the same point regardless of requested horizon)
        failure_months = [results[y].statistics.failure_month for y in horizons_years]
        assert len(set(failure_months)) == 1, (
            f"Failure months should be identical: {failure_months}"
        )

        # The timeline length should be the same for all horizons
        # (they all simulate the same trajectory up to depletion)
        timeline_lengths = [len(results[y].timeline.monthly_results) for y in horizons_years]
        assert len(set(timeline_lengths)) == 1, (
            f"Timeline lengths should be identical: {timeline_lengths}"
        )

        # The timeline should NOT contain trailing zero months
        for years in horizons_years:
            result = results[years]
            # Timeline should only contain months up to (failure_month - 1)
            assert len(result.timeline.monthly_results) == result.statistics.failure_month


# ---------------------------------------------------------------------------
# D. Persistence proof
# ---------------------------------------------------------------------------

class TestPersistenceConsistency:
    """Verify SQLite persistence consistency for depleted trajectories."""

    def test_persisted_months_match_in_memory(self, tmp_path: Path) -> None:
        """SQLite row count must match in-memory timeline length."""
        start = date(1970, 1, 1)
        horizon = 60
        initial_wealth = Money(Decimal("10000"), Currency.EUR)
        initial_portfolio = _make_portfolio(Decimal("100"))
        dataset = _make_dataset(start, horizon, base_price=Decimal("100"))

        # 100% annual withdrawal rate
        ctx = _make_context(start, horizon, initial_wealth, initial_portfolio, dataset,
                           withdrawal_rate=Decimal("1.0"))

        # Execute
        pipeline = _make_pipeline()
        runner = SimulationRunner(pipeline)
        result = runner.run(ctx)

        # Verify in-memory properties
        assert result.statistics.success is False
        failure_month = result.statistics.failure_month
        assert failure_month is not None
        in_memory_months = len(result.timeline.monthly_results)
        assert in_memory_months == failure_month

        # Create experiment and plan for persistence
        ds = Dataset(
            snapshots=tuple(dataset),
            frequency="monthly",
            version="1.0",
            identifier="test_dataset",
        )

        experiment = ResearchExperimentDefinition(
            name="Depletion Test",
            description="Test depletion persistence",
            dataset=ds,
            horizon_months=horizon,
            initial_wealth=initial_wealth,
            cohorts=(CohortSpecification(start_date=start, id="coh1"),),
            allocation_policies=(AllocationPolicy(),),
            withdrawal_policies=(FixedRealWithdrawalPolicy(withdrawal_rate=Decimal("1.0")),),
        )

        unit = PlannedSimulationUnit(
            cohort=CohortSpecification(start_date=start, id="coh1"),
            parameter_config=type('PC', (), {'values': {'equity_allocation': '1.0'}})(),
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("1.0")),
            withdrawal_policy=FixedRealWithdrawalPolicy(withdrawal_rate=Decimal("1.0")),
            initial_portfolio=initial_portfolio,
            dataset=ds,
            horizon_months=horizon,
        )

        plan = ResearchPlan(
            experiment_definition=experiment,
            units=(unit,),
        )

        # Create engine result
        engine_def = ExperimentDefinition(
            name="test",
            description="test",
            simulation_contexts=(ctx,),
        )
        experiment_run = ExperimentRun(
            definition=engine_def,
            simulation_results=(result,),
        )

        from fbf.core.execution.result import ResearchExecutionResult
        research_result = ResearchExecutionResult(
            plan=plan,
            experiment_result=experiment_run,
        )

        # Persist to SQLite
        db_path = tmp_path / "test_depletion.db"
        repo = SQLiteRepository(str(db_path))

        from fbf.core.persistence.studies.sqlite.codecs import (
            AllocationPolicyCodec,
            DefaultDatasetResolver,
            WithdrawalPolicyCodec,
        )

        context = PersistenceReconstructionContext(
            dataset_resolver=DefaultDatasetResolver(datasets={"test_dataset": ds}),
            policy_codecs={
                ("allocation", "AllocationPolicy"): AllocationPolicyCodec(),
                ("withdrawal", "WithdrawalPolicy"): WithdrawalPolicyCodec(),
            },
            simulation_result_codec=SimulationResultCodec(),
        )

        identity = ExperimentIdentity(name="Depletion Test", revision="1.0")
        experiment_id = repo.save_experiment(identity, experiment, context)
        plan_id = repo.save_plan(plan, experiment_id, context)
        result_id = repo.save_execution_result(
            plan_id, research_result, context, duration_seconds=1.0
        )

        # Query SQLite
        with sqlite3.connect(str(db_path)) as conn:
            rows = conn.execute(
                """
                SELECT unit_index, COUNT(*) AS persisted_months,
                       MIN(month_index) AS first_month,
                       MAX(month_index) AS last_month
                FROM simulation_results
                WHERE execution_result_id = ?
                GROUP BY unit_index
                """,
                (result_id,),
            ).fetchall()

            assert len(rows) == 1
            unit_idx, persisted_months, first_month, last_month = rows[0]

            # Verify: persisted months = in-memory months
            assert persisted_months == in_memory_months, (
                f"Persisted months ({persisted_months}) != in-memory months ({in_memory_months})"
            )

            # Verify: first month is 0
            assert first_month == 0

            # Verify: last month is failure_month - 1
            assert last_month == failure_month - 1

            # Verify: no rows after depletion
            after_depletion = conn.execute(
                """
                SELECT COUNT(*)
                FROM simulation_results
                WHERE execution_result_id = ?
                  AND unit_index = ?
                  AND month_index >= ?
                """,
                (result_id, unit_idx, failure_month),
            ).fetchone()[0]
            assert after_depletion == 0, (
                f"Found {after_depletion} rows after depletion month {failure_month}"
            )

    def test_statistics_on_final_row(self, tmp_path: Path) -> None:
        """Statistics are attached to the final persisted row, not a fake future row."""
        start = date(1970, 1, 1)
        horizon = 60
        initial_wealth = Money(Decimal("10000"), Currency.EUR)
        initial_portfolio = _make_portfolio(Decimal("100"))
        dataset = _make_dataset(start, horizon, base_price=Decimal("100"))

        ctx = _make_context(start, horizon, initial_wealth, initial_portfolio, dataset,
                           withdrawal_rate=Decimal("1.0"))

        pipeline = _make_pipeline()
        runner = SimulationRunner(pipeline)
        result = runner.run(ctx)

        failure_month = result.statistics.failure_month
        assert failure_month is not None

        # Create experiment/plan for persistence
        ds = Dataset(
            snapshots=tuple(dataset),
            frequency="monthly",
            version="1.0",
            identifier="test_dataset",
        )

        experiment = ResearchExperimentDefinition(
            name="Stats Test",
            description="Test statistics persistence",
            dataset=ds,
            horizon_months=horizon,
            initial_wealth=initial_wealth,
            cohorts=(CohortSpecification(start_date=start, id="coh1"),),
            allocation_policies=(AllocationPolicy(),),
            withdrawal_policies=(FixedRealWithdrawalPolicy(withdrawal_rate=Decimal("1.0")),),
        )

        unit = PlannedSimulationUnit(
            cohort=CohortSpecification(start_date=start, id="coh1"),
            parameter_config=type('PC', (), {'values': {'equity_allocation': '1.0'}})(),
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("1.0")),
            withdrawal_policy=FixedRealWithdrawalPolicy(withdrawal_rate=Decimal("1.0")),
            initial_portfolio=initial_portfolio,
            dataset=ds,
            horizon_months=horizon,
        )

        plan = ResearchPlan(
            experiment_definition=experiment,
            units=(unit,),
        )

        engine_def = ExperimentDefinition(
            name="test",
            description="test",
            simulation_contexts=(ctx,),
        )
        experiment_run = ExperimentRun(
            definition=engine_def,
            simulation_results=(result,),
        )

        from fbf.core.execution.result import ResearchExecutionResult
        research_result = ResearchExecutionResult(
            plan=plan,
            experiment_result=experiment_run,
        )

        # Persist to SQLite
        db_path = tmp_path / "test_depletion.db"
        repo = SQLiteRepository(str(db_path))

        from fbf.core.persistence.studies.sqlite.codecs import (
            AllocationPolicyCodec,
            DefaultDatasetResolver,
            WithdrawalPolicyCodec,
        )

        context = PersistenceReconstructionContext(
            dataset_resolver=DefaultDatasetResolver(datasets={"test_dataset": ds}),
            policy_codecs={
                ("allocation", "AllocationPolicy"): AllocationPolicyCodec(),
                ("withdrawal", "WithdrawalPolicy"): WithdrawalPolicyCodec(),
            },
            simulation_result_codec=SimulationResultCodec(),
        )

        identity = ExperimentIdentity(name="Stats Test", revision="1.0")
        experiment_id = repo.save_experiment(identity, experiment, context)
        plan_id = repo.save_plan(plan, experiment_id, context)
        result_id = repo.save_execution_result(
            plan_id, research_result, context, duration_seconds=1.0
        )

        # Query SQLite for statistics
        with sqlite3.connect(str(db_path)) as conn:
            stats_rows = conn.execute(
                """
                SELECT month_index, final_month, statistics_payload_json
                FROM simulation_results
                WHERE execution_result_id = ?
                  AND statistics_payload_json IS NOT NULL
                """,
                (result_id,),
            ).fetchall()

            # Statistics should be on exactly one row
            assert len(stats_rows) == 1
            stats_month_idx, final_month, stats_json = stats_rows[0]

            # The statistics row should be the final month (failure_month - 1)
            assert final_month == 1
            assert stats_month_idx == failure_month - 1

            # Parse and verify statistics
            stats = json.loads(stats_json)
            assert stats["success"] is False
            assert stats["failure_month"] == failure_month
            assert stats["months_simulated"] == failure_month

    def test_no_fake_rows_at_requested_horizon(self, tmp_path: Path) -> None:
        """No rows should exist at the requested horizon month for depleted trajectories."""
        start = date(1970, 1, 1)
        horizon = 60
        initial_wealth = Money(Decimal("10000"), Currency.EUR)
        initial_portfolio = _make_portfolio(Decimal("100"))
        dataset = _make_dataset(start, horizon, base_price=Decimal("100"))

        ctx = _make_context(start, horizon, initial_wealth, initial_portfolio, dataset,
                           withdrawal_rate=Decimal("1.0"))

        pipeline = _make_pipeline()
        runner = SimulationRunner(pipeline)
        result = runner.run(ctx)

        failure_month = result.statistics.failure_month
        assert failure_month is not None
        assert failure_month < horizon  # Depletion before horizon

        # Create experiment/plan for persistence
        ds = Dataset(
            snapshots=tuple(dataset),
            frequency="monthly",
            version="1.0",
            identifier="test_dataset",
        )

        experiment = ResearchExperimentDefinition(
            name="Fake Row Test",
            description="Test no fake rows",
            dataset=ds,
            horizon_months=horizon,
            initial_wealth=initial_wealth,
            cohorts=(CohortSpecification(start_date=start, id="coh1"),),
            allocation_policies=(AllocationPolicy(),),
            withdrawal_policies=(FixedRealWithdrawalPolicy(withdrawal_rate=Decimal("1.0")),),
        )

        unit = PlannedSimulationUnit(
            cohort=CohortSpecification(start_date=start, id="coh1"),
            parameter_config=type('PC', (), {'values': {'equity_allocation': '1.0'}})(),
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("1.0")),
            withdrawal_policy=FixedRealWithdrawalPolicy(withdrawal_rate=Decimal("1.0")),
            initial_portfolio=initial_portfolio,
            dataset=ds,
            horizon_months=horizon,
        )

        plan = ResearchPlan(
            experiment_definition=experiment,
            units=(unit,),
        )

        engine_def = ExperimentDefinition(
            name="test",
            description="test",
            simulation_contexts=(ctx,),
        )
        experiment_run = ExperimentRun(
            definition=engine_def,
            simulation_results=(result,),
        )

        from fbf.core.execution.result import ResearchExecutionResult
        research_result = ResearchExecutionResult(
            plan=plan,
            experiment_result=experiment_run,
        )

        db_path = tmp_path / "test_stats.db"
        repo = SQLiteRepository(str(db_path))

        from fbf.core.persistence.studies.sqlite.codecs import (
            AllocationPolicyCodec,
            DefaultDatasetResolver,
            WithdrawalPolicyCodec,
        )

        context = PersistenceReconstructionContext(
            dataset_resolver=DefaultDatasetResolver(datasets={"test_dataset": ds}),
            policy_codecs={
                ("allocation", "AllocationPolicy"): AllocationPolicyCodec(),
                ("withdrawal", "WithdrawalPolicy"): WithdrawalPolicyCodec(),
            },
            simulation_result_codec=SimulationResultCodec(),
        )

        identity = ExperimentIdentity(name="Fake Row Test", revision="1.0")
        experiment_id = repo.save_experiment(identity, experiment, context)
        plan_id = repo.save_plan(plan, experiment_id, context)
        result_id = repo.save_execution_result(
            plan_id, research_result, context, duration_seconds=1.0
        )

        with sqlite3.connect(str(db_path)) as conn:
            # Check: no row at the requested horizon month
            row_at_horizon = conn.execute(
                """
                SELECT COUNT(*)
                FROM simulation_results
                WHERE execution_result_id = ?
                  AND month_index = ?
                """,
                (result_id, horizon),
            ).fetchone()[0]
            assert row_at_horizon == 0, (
                f"Found a row at the requested horizon month {horizon} for depleted trajectory"
            )

            # Check: no rows beyond the failure month
            rows_beyond_failure = conn.execute(
                """
                SELECT COUNT(*)
                FROM simulation_results
                WHERE execution_result_id = ?
                  AND month_index >= ?
                """,
                (result_id, failure_month),
            ).fetchone()[0]
            assert rows_beyond_failure == 0, (
                f"Found {rows_beyond_failure} rows at or beyond failure month {failure_month}"
            )


# ---------------------------------------------------------------------------
# E. Avoided work estimate
# ---------------------------------------------------------------------------

class TestAvoidedWork:
    """Quantify how much month-work early termination saves."""

    def test_avoided_work_high_withdrawal(self) -> None:
        """High withdrawal rate causes early depletion, saving significant work."""
        start = date(1970, 1, 1)
        horizon = 60 * 12  # 60 years
        initial_wealth = Money(Decimal("10000"), Currency.EUR)
        initial_portfolio = _make_portfolio(Decimal("100"))
        dataset = _make_dataset(start, horizon, base_price=Decimal("100"))

        # 100% annual withdrawal rate
        ctx = _make_context(start, horizon, initial_wealth, initial_portfolio, dataset,
                           withdrawal_rate=Decimal("1.0"))

        pipeline = _make_pipeline()
        runner = SimulationRunner(pipeline)
        result = runner.run(ctx)

        failure_month = result.statistics.failure_month
        assert failure_month is not None

        requested_work = horizon
        actual_work = failure_month
        avoided_work = requested_work - actual_work
        avoided_pct = avoided_work / requested_work * 100

        print(f"\n  High withdrawal: requested={requested_work} months, "
              f"actual={actual_work} months, avoided={avoided_work} months ({avoided_pct:.1f}%)")

        # Should deplete quickly (within first few months)
        assert failure_month < 15, f"Expected early depletion, got month {failure_month}"
        assert avoided_pct > 95, f"Expected >95% work avoided, got {avoided_pct:.1f}%"

    def test_avoided_work_low_withdrawal(self) -> None:
        """Low withdrawal rate sustains the portfolio for the full horizon."""
        start = date(1970, 1, 1)
        horizon = 12  # 1 year
        initial_wealth = Money(Decimal("1000000"), Currency.EUR)
        initial_portfolio = _make_portfolio(Decimal("10000"))
        dataset = _make_dataset(start, horizon, base_price=Decimal("100"))

        # 4% annual withdrawal rate on $1,000,000
        ctx = _make_context(start, horizon, initial_wealth, initial_portfolio, dataset,
                           withdrawal_rate=Decimal("0.04"))

        pipeline = _make_pipeline()
        runner = SimulationRunner(pipeline)
        result = runner.run(ctx)

        requested_work = horizon
        actual_work = len(result.timeline.monthly_results)
        avoided_work = requested_work - actual_work
        avoided_pct = avoided_work / requested_work * 100

        print(f"\n  Low withdrawal: requested={requested_work} months, "
              f"actual={actual_work} months, avoided={avoided_work} months ({avoided_pct:.1f}%)")

        # Should complete the full horizon
        assert result.statistics.success is True
        assert actual_work == requested_work
        assert avoided_pct == 0.0


# ---------------------------------------------------------------------------
# F. In-memory result size
# ---------------------------------------------------------------------------

class TestInMemoryResultSize:
    """Verify timeline length matches actual months simulated."""

    def test_timeline_length_matches_months_simulated(self) -> None:
        """timeline.monthly_results length must equal statistics.months_simulated."""
        start = date(1970, 1, 1)
        horizon = 60
        initial_wealth = Money(Decimal("10000"), Currency.EUR)
        initial_portfolio = _make_portfolio(Decimal("100"))
        dataset = _make_dataset(start, horizon, base_price=Decimal("100"))

        # 100% annual withdrawal rate
        ctx = _make_context(start, horizon, initial_wealth, initial_portfolio, dataset,
                           withdrawal_rate=Decimal("1.0"))

        pipeline = _make_pipeline()
        runner = SimulationRunner(pipeline)
        result = runner.run(ctx)

        # Verify: timeline length = months_simulated
        assert len(result.timeline.monthly_results) == result.statistics.months_simulated

        # Verify: timeline length = failure_month (for depleted trajectories)
        assert result.statistics.failure_month is not None
        assert len(result.timeline.monthly_results) == result.statistics.failure_month

        # Verify: no synthetic trailing zero months
        # Each monthly result should have a valid date and portfolio
        for i, mr in enumerate(result.timeline.monthly_results):
            assert mr.period_index == i, f"Month {i} has period_index {mr.period_index}"
            assert mr.date is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
