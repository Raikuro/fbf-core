"""Unit and end-to-end tests for application-level experiment orchestration."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal
from unittest.mock import Mock

import pytest

from engine.application.executor import SimulationExecutor
from engine.application.pipeline import PipelineStep, SimulationPipeline
from engine.application.runner import SimulationRunner
from engine.application.simulation import (
    ExecutionStatus,
    ExperimentDefinition,
    ExperimentRun,
    SimulationResult,
    SimulationStatistics,
    SimulationTimeline,
)
from engine.application.simulation_context import SimulationContext
from engine.domain.model.money import Currency, Money
from engine.domain.model.portfolio import Portfolio


class ExecutorDataset:
    """Minimal immutable-in-practice dataset used by executor tests."""

    def __init__(self, snapshot_date: date) -> None:
        self._snapshot = Mock(date=snapshot_date)

    def __getitem__(self, index: int):
        if index != 0:
            raise IndexError(index)
        return self._snapshot

    def __len__(self) -> int:
        return 1


class CompleteSimulationStep(PipelineStep):
    """Contract-faithful pipeline step that completes a single execution."""

    sequence_order = 1

    def execute(self, state):
        state.status = ExecutionStatus.COMPLETED
        return state


def make_context(cohort: str) -> SimulationContext:
    start_date = date(2020, 1, 1)
    return SimulationContext(
        experiment_name="executor-test",
        cohort=cohort,
        start_date=start_date,
        horizon_months=1,
        initial_wealth=Money(Decimal("1000"), Currency.EUR),
        initial_portfolio=Mock(spec=Portfolio),
        dataset=ExecutorDataset(start_date),
        allocation_policy=Mock(),
        withdrawal_policy=Mock(),
    )


def make_result(success: bool = True) -> SimulationResult:
    return SimulationResult(
        timeline=SimulationTimeline(monthly_results=()),
        statistics=SimulationStatistics(
            final_wealth=Money(Decimal("1000"), Currency.EUR),
            max_drawdown=0.0,
            success=success,
            failure_month=None if success else 0,
            months_simulated=0,
            execution_time_seconds=0.0,
        ),
    )


class TestExperimentContracts:
    def test_definition_requires_an_immutable_context_tuple(self):
        with pytest.raises(TypeError, match="must be a tuple"):
            ExperimentDefinition("test", "description", [make_context("one")])

    def test_definition_rejects_repeated_context_identity(self):
        context = make_context("one")

        with pytest.raises(ValueError, match="must not contain duplicates"):
            ExperimentDefinition("test", "description", (context, context))

    def test_definition_rejects_non_context_items(self):
        with pytest.raises(ValueError, match="must contain SimulationContext"):
            ExperimentDefinition("test", "description", (object(),))

    def test_run_requires_one_result_per_declared_context(self):
        definition = ExperimentDefinition("test", "description", (make_context("one"),))

        with pytest.raises(ValueError, match="must match the definition context count"):
            ExperimentRun(definition, ())

    def test_public_experiment_models_are_immutable(self):
        definition = ExperimentDefinition("test", "description", ())
        run = ExperimentRun(definition, ())

        with pytest.raises(FrozenInstanceError):
            definition.name = "changed"
        with pytest.raises(FrozenInstanceError):
            run.simulation_results = ()


class TestSimulationExecutorUnit:
    def test_constructor_requires_an_injected_runner_with_run(self):
        with pytest.raises(ValueError, match="simulation_runner"):
            SimulationExecutor(None)
        with pytest.raises(ValueError, match="simulation_runner"):
            SimulationExecutor(object())

    def test_execute_delegates_every_context_once_and_preserves_order(self):
        first_context = make_context("first")
        second_context = make_context("second")
        definition = ExperimentDefinition(
            "test", "description", (first_context, second_context)
        )
        first_result = make_result()
        second_result = make_result()
        runner = Mock()
        runner.run.side_effect = (first_result, second_result)

        run = SimulationExecutor(runner).execute(definition)

        assert runner.run.call_args_list[0].args == (first_context,)
        assert runner.run.call_args_list[1].args == (second_context,)
        assert run.definition is definition
        assert run.simulation_results == (first_result, second_result)

    def test_execute_aggregates_modelled_simulation_failure(self):
        definition = ExperimentDefinition(
            "test", "description", (make_context("failed"), make_context("successful"))
        )
        failed_result = make_result(success=False)
        successful_result = make_result(success=True)
        runner = Mock()
        runner.run.side_effect = (failed_result, successful_result)

        run = SimulationExecutor(runner).execute(definition)

        assert runner.run.call_count == 2
        assert run.simulation_results == (failed_result, successful_result)

    def test_empty_definition_does_not_invoke_runner(self):
        runner = Mock()

        run = SimulationExecutor(runner).execute(
            ExperimentDefinition("empty", "description", ())
        )

        runner.run.assert_not_called()
        assert run.simulation_results == ()

    def test_unexpected_runner_error_propagates_without_partial_result(self):
        definition = ExperimentDefinition(
            "test", "description", (make_context("first"), make_context("second"))
        )
        runner = Mock()
        runner.run.side_effect = RuntimeError("runner failure")

        with pytest.raises(RuntimeError, match="runner failure"):
            SimulationExecutor(runner).execute(definition)

        runner.run.assert_called_once_with(definition.simulation_contexts[0])


class TestSimulationExecutorIntegration:
    def test_executes_multiple_contexts_through_real_runner(self):
        runner = SimulationRunner(SimulationPipeline([CompleteSimulationStep()]))
        definition = ExperimentDefinition(
            "integration",
            "runs independent contexts end to end",
            (make_context("2020-01"), make_context("2020-02")),
        )

        run = SimulationExecutor(runner).execute(definition)

        assert isinstance(run, ExperimentRun)
        assert len(run.simulation_results) == 2
        assert all(isinstance(result, SimulationResult) for result in run.simulation_results)
        assert all(result.statistics.success for result in run.simulation_results)
        assert run.simulation_results[0] is not run.simulation_results[1]

    def test_repeated_equal_definitions_produce_equivalent_ordered_runs(self):
        runner = SimulationRunner(SimulationPipeline([CompleteSimulationStep()]))
        definition = ExperimentDefinition(
            "deterministic",
            "same ordered inputs",
            (make_context("2020-01"), make_context("2020-02")),
        )
        executor = SimulationExecutor(runner)

        first_run = executor.execute(definition)
        second_run = executor.execute(definition)

        assert first_run == second_run
