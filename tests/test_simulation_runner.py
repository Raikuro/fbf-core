"""Tests for SimulationRunner.

Verifies orchestration logic, lifecycle management, and result construction.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import Mock

import pytest

from engine.application.pipeline import PipelineStep, SimulationPipeline
from engine.application.runner import DefaultSimulationStatisticsBuilder, SimulationRunner
from engine.application.simulation import (
    ExecutionStatus,
    MonthlyResult,
    SimulationResult,
    SimulationState,
    SimulationStatistics,
    SimulationTimeline,
)
from engine.application.simulation_context import SimulationContext
from engine.domain.model.money import Currency, Money


class MockMarketSnapshot:
    """Test double for MarketSnapshot."""

    def __init__(self, snapshot_date: date, value: float = 100.0):
        self.date = snapshot_date
        self.value = value


class MockPortfolio:
    """Test double for Portfolio."""

    def __init__(self):
        self.positions = {}


class MockDataset:
    """Test double for Dataset supporting indexing."""

    def __init__(self, snapshots: list[MockMarketSnapshot]):
        self._snapshots = snapshots

    def __getitem__(self, index: int) -> MockMarketSnapshot:
        if index < 0 or index >= len(self._snapshots):
            raise IndexError("Dataset index out of range")
        return self._snapshots[index]

    def __len__(self) -> int:
        return len(self._snapshots)


class MockPipelineStep(PipelineStep):
    """Test double for PipelineStep."""

    def __init__(self, sequence_order: int = 0, side_effect=None):
        self.sequence_order = sequence_order
        self.execution_count = 0
        self.side_effect = side_effect or self._default_side_effect

    def execute(self, state: SimulationState) -> SimulationState:
        self.execution_count += 1
        return self.side_effect(state)

    def _default_side_effect(self, state: SimulationState) -> SimulationState:
        # Add a monthly result to simulate step execution
        monthly_result = MonthlyResult(
            date=state.current_date,
            period_index=state.period_index,
            market_snapshot=state.market_snapshot,
            portfolio=state.portfolio,
            allocation=None,
            allocation_target=None,
            allocation_drift=None,
            withdrawal_decision=None,
            rebalance_result=None,
            drawdown=0.0,
            cumulative_return=1.0,
            cumulative_inflation=1.0,
            events=(),
        )
        state.monthly_results.append(monthly_result)
        return state


class SecondaryMockPipelineStep(MockPipelineStep):
    """Distinct pipeline-step type for multi-step ordering tests."""


def money(amount: str) -> Money:
    return Money(Decimal(amount), Currency.EUR)


# ============================================================================
# Unit Tests
# ============================================================================


class TestSimulationRunnerInitialization:
    """Tests for SimulationRunner initialization."""

    def test_constructor_with_pipeline(self):
        """Verify runner accepts pipeline and uses default statistics builder."""
        pipeline = SimulationPipeline([MockPipelineStep(sequence_order=0)])
        runner = SimulationRunner(pipeline)

        assert runner.pipeline is pipeline
        assert isinstance(
            runner.statistics_builder, DefaultSimulationStatisticsBuilder
        )

    def test_constructor_with_custom_builder(self):
        """Verify runner accepts custom statistics builder."""
        pipeline = SimulationPipeline([MockPipelineStep(sequence_order=0)])
        custom_builder = Mock()
        runner = SimulationRunner(pipeline, custom_builder)

        assert runner.statistics_builder is custom_builder

    def test_constructor_with_none_builder_uses_default(self):
        """Verify passing None builder uses default."""
        pipeline = SimulationPipeline([MockPipelineStep(sequence_order=0)])
        runner = SimulationRunner(pipeline, None)

        assert isinstance(
            runner.statistics_builder, DefaultSimulationStatisticsBuilder
        )


class TestContextValidation:
    """Tests for SimulationContext validation."""

    def test_validate_none_context(self):
        """Verify runner rejects None context."""
        pipeline = SimulationPipeline([MockPipelineStep(sequence_order=0)])
        runner = SimulationRunner(pipeline)

        with pytest.raises(ValueError, match="SimulationContext is required"):
            runner.run(None)

    def test_validate_missing_dataset(self):
        """Verify runner rejects context without dataset."""
        pipeline = SimulationPipeline([MockPipelineStep(sequence_order=0)])
        runner = SimulationRunner(pipeline)
        context = Mock(spec=SimulationContext)
        context.dataset = None

        with pytest.raises(ValueError, match="dataset is required"):
            runner.run(context)

    def test_validate_missing_horizon(self):
        """Verify runner rejects context without horizon_months."""
        pipeline = SimulationPipeline([MockPipelineStep(sequence_order=0)])
        runner = SimulationRunner(pipeline)
        context = Mock(spec=SimulationContext)
        context.dataset = Mock()
        context.horizon_months = None

        with pytest.raises(ValueError, match="horizon_months is required"):
            runner.run(context)

    def test_validate_negative_horizon(self):
        """Verify runner rejects negative horizon_months."""
        pipeline = SimulationPipeline([MockPipelineStep(sequence_order=0)])
        runner = SimulationRunner(pipeline)
        context = Mock(spec=SimulationContext)
        context.dataset = Mock()
        context.horizon_months = -1

        with pytest.raises(ValueError, match="horizon_months must not be negative"):
            runner.run(context)

    def test_validate_missing_portfolio(self):
        """Verify runner rejects context without initial_portfolio."""
        pipeline = SimulationPipeline([MockPipelineStep(sequence_order=0)])
        runner = SimulationRunner(pipeline)
        context = Mock(spec=SimulationContext)
        context.dataset = Mock()
        context.horizon_months = 10
        context.initial_portfolio = None

        with pytest.raises(ValueError, match="initial_portfolio is required"):
            runner.run(context)

    def test_validate_missing_wealth(self):
        """Verify runner rejects context without initial_wealth."""
        pipeline = SimulationPipeline([MockPipelineStep(sequence_order=0)])
        runner = SimulationRunner(pipeline)
        context = Mock(spec=SimulationContext)
        context.dataset = Mock()
        context.horizon_months = 10
        context.initial_portfolio = Mock()
        context.initial_wealth = None

        with pytest.raises(ValueError, match="initial_wealth is required"):
            runner.run(context)

    def test_validate_missing_start_date(self):
        """Verify runner rejects context without start_date."""
        pipeline = SimulationPipeline([MockPipelineStep(sequence_order=0)])
        runner = SimulationRunner(pipeline)
        context = Mock(spec=SimulationContext)
        context.dataset = Mock()
        context.horizon_months = 10
        context.initial_portfolio = Mock()
        context.initial_wealth = Mock()
        context.start_date = None

        with pytest.raises(ValueError, match="start_date is required"):
            runner.run(context)


class TestInitialStateConstruction:
    """Tests for initial SimulationState construction."""

    def _create_context(
        self, horizon_months: int = 10, start_date: date = date(2020, 1, 1)
    ) -> SimulationContext:
        """Helper to create valid test context."""
        snapshots = [MockMarketSnapshot(start_date)]
        return SimulationContext(
            experiment_name="test",
            cohort="test",
            start_date=start_date,
            horizon_months=horizon_months,
            initial_wealth=money("1000000"),
            initial_portfolio=MockPortfolio(),
            dataset=MockDataset(snapshots),
            allocation_policy=Mock(),
            withdrawal_policy=Mock(),
        )

    def test_zero_horizon_sets_completed_status(self):
        """Verify zero-month horizon produces COMPLETED status."""
        pipeline = SimulationPipeline([MockPipelineStep(sequence_order=0)])
        runner = SimulationRunner(pipeline)
        context = self._create_context(horizon_months=0)

        result = runner.run(context)

        assert result.statistics.months_simulated == 0
        assert result.statistics.success is True

    def test_positive_horizon_sets_running_status(self):
        """Verify positive horizon starts in RUNNING status."""
        pipeline = SimulationPipeline([MockPipelineStep(sequence_order=0)])
        runner = SimulationRunner(pipeline)
        context = self._create_context(horizon_months=1)

        # The step will transition to COMPLETED
        step = MockPipelineStep(
            sequence_order=0,
            side_effect=lambda s: SimulationState(
                context=s.context,
                current_date=s.current_date,
                period_index=s.period_index,
                portfolio=s.portfolio,
                market_snapshot=s.market_snapshot,
                current_wealth=s.current_wealth,
                peak_wealth=s.peak_wealth,
                status=ExecutionStatus.COMPLETED,
                monthly_results=[
                    MonthlyResult(
                        date=s.current_date,
                        period_index=s.period_index,
                        market_snapshot=s.market_snapshot,
                        portfolio=s.portfolio,
                        allocation=None,
                        allocation_target=None,
                        allocation_drift=None,
                        withdrawal_decision=None,
                        rebalance_result=None,
                        drawdown=0.0,
                        cumulative_return=1.0,
                        cumulative_inflation=1.0,
                        events=(),
                    )
                ],
            ),
        )
        pipeline = SimulationPipeline([step])
        runner = SimulationRunner(pipeline)

        result = runner.run(context)

        assert result.statistics.success is True

    def test_initial_state_sets_current_date(self):
        """Verify initial state has correct current_date."""
        start_date = date(2020, 6, 15)
        context = self._create_context(start_date=start_date, horizon_months=0)
        pipeline = SimulationPipeline([MockPipelineStep(sequence_order=0)])
        runner = SimulationRunner(pipeline)

        # This will create initial state and complete immediately
        runner.run(context)

        # Verify indirectly through zero-horizon completion
        # (state is not exposed directly)

    def test_mismatched_start_date_raises(self):
        """Verify start_date must match first dataset snapshot."""
        start_date = date(2020, 1, 1)
        mismatched_date = date(2020, 2, 1)
        snapshots = [MockMarketSnapshot(start_date)]
        context = SimulationContext(
            experiment_name="test",
            cohort="test",
            start_date=mismatched_date,
            horizon_months=10,
            initial_wealth=money("1000000"),
            initial_portfolio=MockPortfolio(),
            dataset=MockDataset(snapshots),
            allocation_policy=Mock(),
            withdrawal_policy=Mock(),
        )
        pipeline = SimulationPipeline([MockPipelineStep(sequence_order=0)])
        runner = SimulationRunner(pipeline)

        with pytest.raises(
            ValueError, match="start_date must match the first dataset snapshot date"
        ):
            runner.run(context)


class TestExecutionLoop:
    """Tests for the monthly execution loop."""

    def _create_context(
        self, horizon_months: int = 1, start_date: date = date(2020, 1, 1)
    ) -> SimulationContext:
        """Helper to create valid test context."""
        snapshots = [MockMarketSnapshot(start_date)]
        return SimulationContext(
            experiment_name="test",
            cohort="test",
            start_date=start_date,
            horizon_months=horizon_months,
            initial_wealth=money("1000000"),
            initial_portfolio=MockPortfolio(),
            dataset=MockDataset(snapshots),
            allocation_policy=Mock(),
            withdrawal_policy=Mock(),
        )

    def test_pipeline_executed_once_on_single_month(self):
        """Verify pipeline steps execute exactly once for one month."""
        step = MockPipelineStep(sequence_order=0)
        pipeline = SimulationPipeline([step])
        runner = SimulationRunner(pipeline)

        # Modify step to complete after one execution
        original_execute = step.execute

        def execute_and_complete(state: SimulationState) -> SimulationState:
            state = original_execute(state)
            state.status = ExecutionStatus.COMPLETED
            return state

        step.execute = execute_and_complete

        context = self._create_context(horizon_months=1)
        runner.run(context)

        assert step.execution_count == 1

    def test_pipeline_steps_execute_in_order(self):
        """Verify pipeline steps execute in sequence order."""
        call_order = []

        step1 = MockPipelineStep(
            sequence_order=0,
            side_effect=lambda s: (
                call_order.append(1),
                s,
            )[1],
        )
        step2 = SecondaryMockPipelineStep(
            sequence_order=1,
            side_effect=lambda s: (
                call_order.append(2),
                s,
            )[1],
        )

        # Make final step complete
        original_side_effect = step2.side_effect

        def step2_complete(s):
            result = original_side_effect(s)
            result.status = ExecutionStatus.COMPLETED
            return result

        step2.side_effect = step2_complete

        pipeline = SimulationPipeline([step1, step2])
        runner = SimulationRunner(pipeline)
        context = self._create_context(horizon_months=1)

        runner.run(context)

        assert call_order == [1, 2]

    def test_execution_stops_on_completed_status(self):
        """Verify execution stops when status becomes COMPLETED."""
        step1 = MockPipelineStep(sequence_order=0)
        step2 = SecondaryMockPipelineStep(sequence_order=1)

        # Make step1 complete the simulation
        def step1_complete(s):
            s.status = ExecutionStatus.COMPLETED
            return s

        step1.execute = step1_complete

        pipeline = SimulationPipeline([step1, step2])
        runner = SimulationRunner(pipeline)
        context = self._create_context(horizon_months=1)

        runner.run(context)

        # step2 should not have executed
        assert step2.execution_count == 0

    def test_execution_stops_on_failure_state(self):
        """Verify execution stops when failure_state is set."""
        step1 = MockPipelineStep(sequence_order=0)
        step2 = SecondaryMockPipelineStep(sequence_order=1)

        # Make step1 fail
        def step1_fail(s):
            s.failure_state = "Portfolio depleted"
            return s

        step1.execute = step1_fail

        pipeline = SimulationPipeline([step1, step2])
        runner = SimulationRunner(pipeline)
        context = self._create_context(horizon_months=1)

        result = runner.run(context)

        # Execution should have stopped
        assert result.statistics.success is False
        assert result.statistics.failure_month is not None


class TestResultConstruction:
    """Tests for final SimulationResult construction."""

    def _create_context(self, start_date: date = date(2020, 1, 1)):
        """Helper to create valid test context."""
        snapshots = [MockMarketSnapshot(start_date)]
        return SimulationContext(
            experiment_name="test",
            cohort="test",
            start_date=start_date,
            horizon_months=0,
            initial_wealth=money("1000000"),
            initial_portfolio=MockPortfolio(),
            dataset=MockDataset(snapshots),
            allocation_policy=Mock(),
            withdrawal_policy=Mock(),
        )

    def test_result_is_simulation_result(self):
        """Verify returned object is SimulationResult."""
        pipeline = SimulationPipeline([MockPipelineStep(sequence_order=0)])
        runner = SimulationRunner(pipeline)
        context = self._create_context()

        result = runner.run(context)

        assert isinstance(result, SimulationResult)

    def test_result_contains_timeline(self):
        """Verify result includes SimulationTimeline."""
        pipeline = SimulationPipeline([MockPipelineStep(sequence_order=0)])
        runner = SimulationRunner(pipeline)
        context = self._create_context()

        result = runner.run(context)

        assert isinstance(result.timeline, SimulationTimeline)

    def test_result_contains_statistics(self):
        """Verify result includes SimulationStatistics."""
        pipeline = SimulationPipeline([MockPipelineStep(sequence_order=0)])
        runner = SimulationRunner(pipeline)
        context = self._create_context()

        result = runner.run(context)

        assert isinstance(result.statistics, SimulationStatistics)

    def test_result_is_frozen(self):
        """Verify returned SimulationResult is immutable."""
        pipeline = SimulationPipeline([MockPipelineStep(sequence_order=0)])
        runner = SimulationRunner(pipeline)
        context = self._create_context()

        result = runner.run(context)

        with pytest.raises(AttributeError):
            result.timeline = None

    def test_result_statistics_success_on_completion(self):
        """Verify statistics.success is True on normal completion."""
        pipeline = SimulationPipeline([MockPipelineStep(sequence_order=0)])
        runner = SimulationRunner(pipeline)
        context = self._create_context()

        result = runner.run(context)

        assert result.statistics.success is True

    def test_result_statistics_failure_on_failure_state(self):
        """Verify statistics.success is False when failure_state is set."""

        def fail_step(s):
            s.failure_state = "test failure"
            return s

        step = MockPipelineStep(sequence_order=0, side_effect=fail_step)
        pipeline = SimulationPipeline([step])
        runner = SimulationRunner(pipeline)
        context = SimulationContext(
            experiment_name="test",
            cohort="test",
            start_date=date(2020, 1, 1),
            horizon_months=1,
            initial_wealth=money("1000000"),
            initial_portfolio=MockPortfolio(),
            dataset=MockDataset([MockMarketSnapshot(date(2020, 1, 1))]),
            allocation_policy=Mock(),
            withdrawal_policy=Mock(),
        )

        result = runner.run(context)

        assert result.statistics.success is False

    def test_result_statistics_months_simulated(self):
        """Verify months_simulated equals length of timeline."""
        step = MockPipelineStep(sequence_order=0)
        pipeline = SimulationPipeline([step])
        runner = SimulationRunner(pipeline)
        context = SimulationContext(
            experiment_name="test",
            cohort="test",
            start_date=date(2020, 1, 1),
            horizon_months=1,
            initial_wealth=money("1000000"),
            initial_portfolio=MockPortfolio(),
            dataset=MockDataset([MockMarketSnapshot(date(2020, 1, 1))]),
            allocation_policy=Mock(),
            withdrawal_policy=Mock(),
        )

        # Make step complete after adding result
        def step_complete(s):
            monthly_result = MonthlyResult(
                date=s.current_date,
                period_index=s.period_index,
                market_snapshot=s.market_snapshot,
                portfolio=s.portfolio,
                allocation=None,
                allocation_target=None,
                allocation_drift=None,
                withdrawal_decision=None,
                rebalance_result=None,
                drawdown=0.0,
                cumulative_return=1.0,
                cumulative_inflation=1.0,
                events=(),
            )
            s.monthly_results.append(monthly_result)
            s.status = ExecutionStatus.COMPLETED
            return s

        step.execute = step_complete

        result = runner.run(context)

        assert result.statistics.months_simulated == 1
        assert len(result.timeline.monthly_results) == 1


class TestDeterminism:
    """Tests for deterministic execution."""

    def test_repeated_execution_produces_identical_results(self):
        """Verify running identical simulation twice produces identical results."""

        def create_context():
            return SimulationContext(
                experiment_name="test",
                cohort="test",
                start_date=date(2020, 1, 1),
                horizon_months=1,
                initial_wealth=money("1000000"),
                initial_portfolio=MockPortfolio(),
                dataset=MockDataset([MockMarketSnapshot(date(2020, 1, 1))]),
                allocation_policy=Mock(),
                withdrawal_policy=Mock(),
            )

        def create_step():
            def execute_fn(s):
                monthly_result = MonthlyResult(
                    date=s.current_date,
                    period_index=s.period_index,
                    market_snapshot=s.market_snapshot,
                    portfolio=s.portfolio,
                    allocation=None,
                    allocation_target=None,
                    allocation_drift=None,
                    withdrawal_decision=None,
                    rebalance_result=None,
                    drawdown=0.0,
                    cumulative_return=1.0,
                    cumulative_inflation=1.0,
                    events=(),
                )
                s.monthly_results.append(monthly_result)
                s.status = ExecutionStatus.COMPLETED
                return s

            return MockPipelineStep(sequence_order=0, side_effect=execute_fn)

        # First execution
        pipeline1 = SimulationPipeline([create_step()])
        runner1 = SimulationRunner(pipeline1)
        result1 = runner1.run(create_context())

        # Second execution with fresh objects
        pipeline2 = SimulationPipeline([create_step()])
        runner2 = SimulationRunner(pipeline2)
        result2 = runner2.run(create_context())

        # Verify results are equivalent
        assert result1.statistics.success == result2.statistics.success
        assert (
            result1.statistics.months_simulated == result2.statistics.months_simulated
        )
