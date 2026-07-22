"""Integration tests for SimulationRunner.

End-to-end tests verifying complete simulation execution across multiple months.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock
from typing import Sequence

import pytest

from engine.application.runner import SimulationRunner
from engine.application.simulation import (
    ExecutionStatus,
    SimulationState,
    MonthlyResult,
)
from engine.application.simulation_context import SimulationContext
from engine.application.pipeline import SimulationPipeline, PipelineStep
from engine.domain.model.dataset import Dataset
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.money import Money
from engine.domain.model.portfolio import Portfolio


class IntegrationMarketSnapshot(MarketSnapshot):
    """Market snapshot for integration tests."""

    def __init__(self, snapshot_date: date):
        self.date = snapshot_date


class IntegrationPortfolio(Portfolio):
    """Portfolio stub for integration tests."""

    def __init__(self):
        self.positions = {}


class IntegrationDataset(Dataset):
    """Dataset supporting multi-month snapshots."""

    def __init__(self, num_months: int, start_date: date = date(2020, 1, 1)):
        self._snapshots = [
            IntegrationMarketSnapshot(
                date(
                    start_date.year + (start_date.month + i - 1) // 12,
                    ((start_date.month + i - 1) % 12) + 1,
                    start_date.day,
                )
            )
            for i in range(num_months)
        ]

    def __getitem__(self, index: int) -> MarketSnapshot:
        if index < 0 or index >= len(self._snapshots):
            raise IndexError("Dataset index out of range")
        return self._snapshots[index]

    def __len__(self) -> int:
        return len(self._snapshots)


class MonthlyProgressionStep(PipelineStep):
    """Step that advances simulation month and tracks execution."""

    def __init__(self, sequence_order: int = 0):
        self.sequence_order = sequence_order
        self.execution_count = 0

    def execute(self, state: SimulationState) -> SimulationState:
        """Execute step, recording monthly result and advancing state."""
        self.execution_count += 1

        # Create monthly result for this month
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

        # Check if simulation should continue
        next_period = state.period_index + 1
        horizon = state.context.horizon_months

        if next_period >= horizon:
            # Simulation complete
            state.status = ExecutionStatus.COMPLETED
        else:
            # Advance to next month
            state.period_index = next_period
            current_date = state.current_date
            new_month = current_date.month + 1
            new_year = current_date.year
            if new_month > 12:
                new_month = 1
                new_year += 1
            state.current_date = date(new_year, new_month, current_date.day)

            # Get next market snapshot
            if next_period < len(state.context.dataset):
                state.market_snapshot = state.context.dataset[next_period]

        return state


# ============================================================================
# Integration Tests
# ============================================================================


class TestSimulationRunnerIntegration:
    """End-to-end integration tests for SimulationRunner."""

    def test_complete_single_month_simulation(self):
        """Verify complete simulation execution for a single month."""
        dataset = IntegrationDataset(num_months=1)
        context = SimulationContext(
            experiment_name="test_integration",
            cohort="2020-01",
            start_date=date(2020, 1, 1),
            horizon_months=1,
            initial_wealth=Money("1000000"),
            initial_portfolio=IntegrationPortfolio(),
            dataset=dataset,
            allocation_policy=Mock(),
            withdrawal_policy=Mock(),
        )

        step = MonthlyProgressionStep(sequence_order=0)
        pipeline = SimulationPipeline([step])
        runner = SimulationRunner(pipeline)

        result = runner.run(context)

        # Verify execution
        assert result.statistics.success is True
        assert result.statistics.months_simulated == 1
        assert len(result.timeline.monthly_results) == 1
        assert step.execution_count == 1

    def test_complete_three_month_simulation(self):
        """Verify complete simulation execution for three months."""
        dataset = IntegrationDataset(num_months=3)
        context = SimulationContext(
            experiment_name="test_integration_3m",
            cohort="2020-01",
            start_date=date(2020, 1, 1),
            horizon_months=3,
            initial_wealth=Money("1000000"),
            initial_portfolio=IntegrationPortfolio(),
            dataset=dataset,
            allocation_policy=Mock(),
            withdrawal_policy=Mock(),
        )

        step = MonthlyProgressionStep(sequence_order=0)
        pipeline = SimulationPipeline([step])
        runner = SimulationRunner(pipeline)

        result = runner.run(context)

        # Verify execution
        assert result.statistics.success is True
        assert result.statistics.months_simulated == 3
        assert len(result.timeline.monthly_results) == 3
        assert step.execution_count == 3

    def test_complete_twelve_month_simulation(self):
        """Verify complete simulation execution for full year."""
        dataset = IntegrationDataset(num_months=12)
        context = SimulationContext(
            experiment_name="test_integration_1y",
            cohort="2020-01",
            start_date=date(2020, 1, 1),
            horizon_months=12,
            initial_wealth=Money("1000000"),
            initial_portfolio=IntegrationPortfolio(),
            dataset=dataset,
            allocation_policy=Mock(),
            withdrawal_policy=Mock(),
        )

        step = MonthlyProgressionStep(sequence_order=0)
        pipeline = SimulationPipeline([step])
        runner = SimulationRunner(pipeline)

        result = runner.run(context)

        # Verify execution
        assert result.statistics.success is True
        assert result.statistics.months_simulated == 12
        assert len(result.timeline.monthly_results) == 12
        assert step.execution_count == 12

    def test_timeline_dates_progress_correctly(self):
        """Verify timeline contains results with correct progressive dates."""
        dataset = IntegrationDataset(num_months=3, start_date=date(2020, 3, 15))
        context = SimulationContext(
            experiment_name="test_dates",
            cohort="2020-03",
            start_date=date(2020, 3, 15),
            horizon_months=3,
            initial_wealth=Money("1000000"),
            initial_portfolio=IntegrationPortfolio(),
            dataset=dataset,
            allocation_policy=Mock(),
            withdrawal_policy=Mock(),
        )

        step = MonthlyProgressionStep(sequence_order=0)
        pipeline = SimulationPipeline([step])
        runner = SimulationRunner(pipeline)

        result = runner.run(context)

        # Verify timeline progression
        timeline = result.timeline.monthly_results
        assert len(timeline) == 3

        assert timeline[0].date == date(2020, 3, 15)
        assert timeline[0].period_index == 0

        assert timeline[1].date == date(2020, 4, 15)
        assert timeline[1].period_index == 1

        assert timeline[2].date == date(2020, 5, 15)
        assert timeline[2].period_index == 2

    def test_multi_step_pipeline_execution_order(self):
        """Verify all pipeline steps execute in correct order for each month."""
        dataset = IntegrationDataset(num_months=2)
        context = SimulationContext(
            experiment_name="test_multi_step",
            cohort="2020-01",
            start_date=date(2020, 1, 1),
            horizon_months=2,
            initial_wealth=Money("1000000"),
            initial_portfolio=IntegrationPortfolio(),
            dataset=dataset,
            allocation_policy=Mock(),
            withdrawal_policy=Mock(),
        )

        execution_log = []

        class LoggingStep(PipelineStep):
            def __init__(self, sequence_order: int, name: str):
                self.sequence_order = sequence_order
                self.name = name

            def execute(self, state: SimulationState) -> SimulationState:
                execution_log.append(
                    f"Month {state.period_index}: {self.name}"
                )
                return state

        class FinalProgressionStep(PipelineStep):
            def __init__(self):
                self.sequence_order = 2

            def execute(self, state: SimulationState) -> SimulationState:
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

                next_period = state.period_index + 1
                if next_period >= state.context.horizon_months:
                    state.status = ExecutionStatus.COMPLETED
                else:
                    state.period_index = next_period
                    current_date = state.current_date
                    new_month = current_date.month + 1
                    new_year = current_date.year
                    if new_month > 12:
                        new_month = 1
                        new_year += 1
                    state.current_date = date(new_year, new_month, current_date.day)
                    if next_period < len(state.context.dataset):
                        state.market_snapshot = state.context.dataset[next_period]

                return state

        steps = [
            LoggingStep(0, "Step1"),
            LoggingStep(1, "Step2"),
            FinalProgressionStep(),
        ]
        pipeline = SimulationPipeline(steps)
        runner = SimulationRunner(pipeline)

        result = runner.run(context)

        # Verify execution order and count
        assert len(execution_log) == 4  # 2 steps × 2 months
        assert execution_log[0] == "Month 0: Step1"
        assert execution_log[1] == "Month 0: Step2"
        assert execution_log[2] == "Month 1: Step1"
        assert execution_log[3] == "Month 1: Step2"

    def test_simulation_terminates_on_failure(self):
        """Verify simulation terminates immediately when failure_state is set."""
        dataset = IntegrationDataset(num_months=12)
        context = SimulationContext(
            experiment_name="test_failure",
            cohort="2020-01",
            start_date=date(2020, 1, 1),
            horizon_months=12,
            initial_wealth=Money("1000000"),
            initial_portfolio=IntegrationPortfolio(),
            dataset=dataset,
            allocation_policy=Mock(),
            withdrawal_policy=Mock(),
        )

        class FailureStep(PipelineStep):
            def __init__(self):
                self.sequence_order = 0
                self.execution_count = 0

            def execute(self, state: SimulationState) -> SimulationState:
                self.execution_count += 1

                # Fail on month 3
                if state.period_index == 2:
                    state.failure_state = "Portfolio depleted"
                    return state

                # Create monthly result
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

                # Advance if not failed
                next_period = state.period_index + 1
                if next_period < state.context.horizon_months:
                    state.period_index = next_period
                    current_date = state.current_date
                    new_month = current_date.month + 1
                    new_year = current_date.year
                    if new_month > 12:
                        new_month = 1
                        new_year += 1
                    state.current_date = date(new_year, new_month, current_date.day)
                    if next_period < len(state.context.dataset):
                        state.market_snapshot = state.context.dataset[next_period]
                else:
                    state.status = ExecutionStatus.COMPLETED

                return state

        step = FailureStep()
        pipeline = SimulationPipeline([step])
        runner = SimulationRunner(pipeline)

        result = runner.run(context)

        # Verify simulation stopped at failure
        assert result.statistics.success is False
        assert result.statistics.failure_month is not None
        assert result.statistics.months_simulated == 2
        assert step.execution_count == 3  # Months 0, 1, 2 (where it fails)

    def test_result_immutability(self):
        """Verify the returned SimulationResult is immutable."""
        dataset = IntegrationDataset(num_months=1)
        context = SimulationContext(
            experiment_name="test_immutable",
            cohort="2020-01",
            start_date=date(2020, 1, 1),
            horizon_months=1,
            initial_wealth=Money("1000000"),
            initial_portfolio=IntegrationPortfolio(),
            dataset=dataset,
            allocation_policy=Mock(),
            withdrawal_policy=Mock(),
        )

        step = MonthlyProgressionStep(sequence_order=0)
        pipeline = SimulationPipeline([step])
        runner = SimulationRunner(pipeline)

        result = runner.run(context)

        # Attempt to modify should raise
        with pytest.raises(AttributeError):
            result.timeline = None

        with pytest.raises(AttributeError):
            result.statistics = None

    def test_zero_horizon_completes_without_execution(self):
        """Verify zero-horizon simulation completes without executing steps."""
        dataset = IntegrationDataset(num_months=0)
        context = SimulationContext(
            experiment_name="test_zero",
            cohort="2020-01",
            start_date=date(2020, 1, 1),
            horizon_months=0,
            initial_wealth=Money("1000000"),
            initial_portfolio=IntegrationPortfolio(),
            dataset=dataset,
            allocation_policy=Mock(),
            withdrawal_policy=Mock(),
        )

        step = MonthlyProgressionStep(sequence_order=0)
        pipeline = SimulationPipeline([step])
        runner = SimulationRunner(pipeline)

        result = runner.run(context)

        # Verify zero execution
        assert result.statistics.success is True
        assert result.statistics.months_simulated == 0
        assert len(result.timeline.monthly_results) == 0
        assert step.execution_count == 0
