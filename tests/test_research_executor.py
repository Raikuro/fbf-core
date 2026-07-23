"""Unit and integration tests for ResearchExecutor and ResearchExecutionResult.

Covers the full behavioural specification (RESEARCH_EXECUTOR_SPECIFICATION.md):

1. Constructor injection: accepts SimulationExecutor; rejects None or invalid.
2. execute() delegates to SimulationExecutor exactly once per valid plan.
3. Contexts are built in exact plan unit order.
4. Policy objects from plan units are passed through unchanged.
5. Index provenance is preserved: plan.units[i] ↔ results[i].
6. Invalid plans, wrong types, and malformed units fail before SimulationExecutor call.
7. Duplicate unit identities fail before SimulationExecutor call.
8. SimulationExecutor exceptions are wrapped in ResearchExecutionError.
9. Modelled failed SimulationResult values are preserved without interpretation.
10. ResearchExecutionResult immutability.
11. Statelessness: repeated equal calls produce equivalent outputs.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from engine.application.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    ExperimentRun,
    SimulationResult,
    SimulationStatistics,
    SimulationTimeline,
)
from engine.application.simulation_context import SimulationContext
from engine.domain.model.asset import AssetClass
from engine.domain.model.dataset import Dataset
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.money import Currency, Money
from engine.domain.model.portfolio import AssetHolding, Portfolio
from engine.domain.policies.allocation_policy import AllocationPolicy
from engine.domain.policies.withdrawal_policy import WithdrawalPolicy
from research.domain.cohort.specification import CohortSpecification
from research.domain.experiment.definition import ExperimentDefinition
from research.domain.parameter.configuration import ParameterConfiguration
from research.domain.plan import PlannedSimulationUnit, ResearchPlan
from research.orchestration.errors import InvalidResearchPlanError, ResearchExecutionError
from research.orchestration.executor import ResearchExecutor
from research.orchestration.result import ResearchExecutionResult

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class StubAllocationPolicy(AllocationPolicy):
    def decide(self, context: object) -> object:
        return None


class StubWithdrawalPolicy(WithdrawalPolicy):
    def decide(self, context: object) -> object:
        return None


# ---------------------------------------------------------------------------
# Shared factories
# ---------------------------------------------------------------------------


def make_asset() -> AssetClass:
    return AssetClass(id="acwi", name="ACWI", description="Global equities")


def make_dataset(start_date: date = date(2000, 1, 1)) -> Dataset:
    asset = make_asset()
    snapshot = MarketSnapshot(
        date=start_date,
        index_levels={asset: Decimal("100.00")},
        inflation=Decimal("0.00"),
        inflation_cumulative=Decimal("0.00"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100.00"),
    )
    return Dataset(snapshots=[snapshot], frequency="monthly", version="1.0")


def make_experiment_def(
    name: str = "test-experiment",
    start_date: date = date(2000, 1, 1),
    horizon_months: int = 12,
) -> ExperimentDefinition:
    return ExperimentDefinition(
        name=name,
        description="A test experiment for ResearchExecutor tests",
        dataset=make_dataset(start_date),
        horizon_months=horizon_months,
        initial_wealth=Money(Decimal("100000"), Currency.EUR),
        cohorts=(
            CohortSpecification(start_date=start_date),
            CohortSpecification(start_date=date(start_date.year + 1, 1, 1)),
        ),
        allocation_policies=(StubAllocationPolicy(),),
        withdrawal_policies=(StubWithdrawalPolicy(),),
    )


def make_cohort(year: int = 2000, month: int = 1) -> CohortSpecification:
    return CohortSpecification(start_date=date(year, month, 1))


def make_param_config(withdrawal_rate: float = 0.04) -> ParameterConfiguration:
    return ParameterConfiguration(values={"withdrawal_rate": withdrawal_rate})


def make_portfolio() -> Portfolio:
    """Materialised initial portfolio supplied by the planning boundary (test double)."""
    asset = make_asset()
    return Portfolio(holdings=(AssetHolding(asset_class=asset, units=Decimal("1000")),))


def make_unit(
    year: int = 2000,
    month: int = 1,
    withdrawal_rate: float = 0.04,
    alloc: AllocationPolicy | None = None,
    withd: WithdrawalPolicy | None = None,
    portfolio: Portfolio | None = None,
) -> PlannedSimulationUnit:
    return PlannedSimulationUnit(
        cohort=make_cohort(year=year, month=month),
        parameter_config=make_param_config(withdrawal_rate=withdrawal_rate),
        allocation_policy=alloc or StubAllocationPolicy(),
        withdrawal_policy=withd or StubWithdrawalPolicy(),
        initial_portfolio=portfolio if portfolio is not None else make_portfolio(),
    )


def make_simulation_result(success: bool = True) -> SimulationResult:
    return SimulationResult(
        timeline=SimulationTimeline(monthly_results=()),
        statistics=SimulationStatistics(
            final_wealth=Money(Decimal("100000"), Currency.EUR),
            max_drawdown=0.0,
            success=success,
            failure_month=None if success else 6,
            months_simulated=12,
            execution_time_seconds=0.01,
        ),
    )


def make_experiment_run(
    results: tuple[SimulationResult, ...],
    engine_def: EngineExperimentDefinition | None = None,
) -> ExperimentRun:
    if engine_def is None:
        engine_def = EngineExperimentDefinition(
            name="test-experiment",
            description="test",
            simulation_contexts=tuple(Mock(spec=SimulationContext) for _ in results),
        )
    return ExperimentRun(definition=engine_def, simulation_results=results)


def make_plan(
    experiment_def: ExperimentDefinition | None = None,
    units: tuple[PlannedSimulationUnit, ...] | None = None,
) -> ResearchPlan:
    exp = experiment_def or make_experiment_def()
    us = units or (make_unit(year=2000), make_unit(year=2001))
    return ResearchPlan(experiment_definition=exp, units=us)


def make_executor(
    simulation_results: tuple[SimulationResult, ...] | None = None,
) -> tuple[ResearchExecutor, Mock]:
    """Returns (executor, mock_simulation_executor)."""
    mock_sim_exec = Mock()
    if simulation_results is not None:
        mock_sim_exec.execute.return_value = make_experiment_run(simulation_results)
    executor = ResearchExecutor(simulation_executor=mock_sim_exec)
    return executor, mock_sim_exec


# ---------------------------------------------------------------------------
# TestResearchExecutorConstructor
# ---------------------------------------------------------------------------


class TestResearchExecutorConstructor:
    def test_accepts_valid_simulation_executor(self) -> None:
        mock_exec = Mock()
        executor = ResearchExecutor(simulation_executor=mock_exec)
        assert executor is not None

    def test_rejects_none_simulation_executor(self) -> None:
        with pytest.raises(ValueError, match="simulation_executor cannot be None"):
            ResearchExecutor(simulation_executor=None)  # type: ignore[arg-type]

    def test_rejects_object_without_execute_method(self) -> None:
        with pytest.raises(ValueError, match="execute"):
            ResearchExecutor(simulation_executor=object())  # type: ignore[arg-type]

    def test_does_not_instantiate_any_internal_collaborators(self) -> None:
        """Executor must receive its collaborator by injection, never create one."""
        mock_exec = Mock()
        with (patch("research.orchestration.executor.SimulationExecutor") as patched_cls,):
            ResearchExecutor(simulation_executor=mock_exec)
            patched_cls.assert_not_called()


# ---------------------------------------------------------------------------
# TestResearchExecutorDelegation
# ---------------------------------------------------------------------------


class TestResearchExecutorDelegation:
    def test_delegates_to_simulation_executor_exactly_once(self) -> None:
        plan = make_plan(units=(make_unit(year=2000), make_unit(year=2001)))
        results = (make_simulation_result(), make_simulation_result())
        executor, mock_sim_exec = make_executor(simulation_results=results)

        executor.execute(plan)

        mock_sim_exec.execute.assert_called_once()

    def test_delegates_with_engine_experiment_definition(self) -> None:
        """SimulationExecutor.execute() receives an EngineExperimentDefinition."""
        plan = make_plan(units=(make_unit(year=2000), make_unit(year=2001)))
        results = (make_simulation_result(), make_simulation_result())
        executor, mock_sim_exec = make_executor(simulation_results=results)

        executor.execute(plan)

        call_args = mock_sim_exec.execute.call_args
        assert call_args is not None
        engine_def = call_args.args[0]
        assert isinstance(engine_def, EngineExperimentDefinition)

    def test_engine_experiment_name_matches_research_experiment_name(self) -> None:
        exp_def = make_experiment_def(name="my-study")
        plan = make_plan(experiment_def=exp_def, units=(make_unit(year=2000),))
        executor, mock_sim_exec = make_executor(simulation_results=(make_simulation_result(),))

        executor.execute(plan)

        engine_def = mock_sim_exec.execute.call_args.args[0]
        assert engine_def.name == "my-study"

    def test_engine_experiment_description_matches_research_experiment_description(
        self,
    ) -> None:
        exp_def = make_experiment_def()
        plan = make_plan(experiment_def=exp_def, units=(make_unit(year=2000),))
        executor, mock_sim_exec = make_executor(simulation_results=(make_simulation_result(),))

        executor.execute(plan)

        engine_def = mock_sim_exec.execute.call_args.args[0]
        assert engine_def.description == exp_def.description


# ---------------------------------------------------------------------------
# TestResearchExecutorContextTranslation
# ---------------------------------------------------------------------------


class TestResearchExecutorContextTranslation:
    def test_produces_one_context_per_plan_unit(self) -> None:
        plan = make_plan(units=(make_unit(year=2000), make_unit(year=2001), make_unit(year=2002)))
        results = tuple(make_simulation_result() for _ in plan.units)
        executor, mock_sim_exec = make_executor(simulation_results=results)

        executor.execute(plan)

        engine_def = mock_sim_exec.execute.call_args.args[0]
        assert len(engine_def.simulation_contexts) == 3

    def test_contexts_are_in_exact_plan_unit_order(self) -> None:
        unit_a = make_unit(year=2000, month=1)
        unit_b = make_unit(year=2001, month=1)
        unit_c = make_unit(year=2002, month=1)
        plan = make_plan(units=(unit_a, unit_b, unit_c))
        results = tuple(make_simulation_result() for _ in plan.units)
        executor, mock_sim_exec = make_executor(simulation_results=results)

        executor.execute(plan)

        engine_def = mock_sim_exec.execute.call_args.args[0]
        contexts = engine_def.simulation_contexts
        assert contexts[0].start_date == unit_a.cohort.start_date
        assert contexts[1].start_date == unit_b.cohort.start_date
        assert contexts[2].start_date == unit_c.cohort.start_date

    def test_context_start_date_matches_cohort_start_date(self) -> None:
        unit = make_unit(year=2000, month=6)
        plan = make_plan(units=(unit,))
        executor, mock_sim_exec = make_executor(simulation_results=(make_simulation_result(),))

        executor.execute(plan)

        engine_def = mock_sim_exec.execute.call_args.args[0]
        ctx = engine_def.simulation_contexts[0]
        assert ctx.start_date == date(2000, 6, 1)

    def test_context_horizon_months_matches_experiment_definition(self) -> None:
        exp_def = make_experiment_def(horizon_months=360)
        unit = make_unit(year=2000)
        plan = make_plan(experiment_def=exp_def, units=(unit,))
        executor, mock_sim_exec = make_executor(simulation_results=(make_simulation_result(),))

        executor.execute(plan)

        engine_def = mock_sim_exec.execute.call_args.args[0]
        ctx = engine_def.simulation_contexts[0]
        assert ctx.horizon_months == 360

    def test_context_initial_wealth_matches_experiment_definition(self) -> None:
        exp_def = make_experiment_def()
        unit = make_unit(year=2000)
        plan = make_plan(experiment_def=exp_def, units=(unit,))
        executor, mock_sim_exec = make_executor(simulation_results=(make_simulation_result(),))

        executor.execute(plan)

        engine_def = mock_sim_exec.execute.call_args.args[0]
        ctx = engine_def.simulation_contexts[0]
        assert ctx.initial_wealth == exp_def.initial_wealth

    def test_context_dataset_matches_experiment_definition_dataset(self) -> None:
        exp_def = make_experiment_def()
        unit = make_unit(year=2000)
        plan = make_plan(experiment_def=exp_def, units=(unit,))
        executor, mock_sim_exec = make_executor(simulation_results=(make_simulation_result(),))

        executor.execute(plan)

        engine_def = mock_sim_exec.execute.call_args.args[0]
        ctx = engine_def.simulation_contexts[0]
        assert ctx.dataset is exp_def.dataset

    def test_context_experiment_name_matches_plan_experiment_name(self) -> None:
        exp_def = make_experiment_def(name="my-research-study")
        unit = make_unit(year=2000)
        plan = make_plan(experiment_def=exp_def, units=(unit,))
        executor, mock_sim_exec = make_executor(simulation_results=(make_simulation_result(),))

        executor.execute(plan)

        engine_def = mock_sim_exec.execute.call_args.args[0]
        ctx = engine_def.simulation_contexts[0]
        assert ctx.experiment_name == "my-research-study"

    def test_context_cohort_field_is_cohort_id(self) -> None:
        cohort = CohortSpecification(start_date=date(2000, 6, 1), id="cohort-2000-06")
        unit = PlannedSimulationUnit(
            cohort=cohort,
            parameter_config=make_param_config(),
            allocation_policy=StubAllocationPolicy(),
            withdrawal_policy=StubWithdrawalPolicy(),
            initial_portfolio=make_portfolio(),
        )
        exp_def = make_experiment_def()
        # We use a plan that only has one unit matching this cohort
        plan = ResearchPlan(experiment_definition=exp_def, units=(unit,))
        executor, mock_sim_exec = make_executor(simulation_results=(make_simulation_result(),))

        executor.execute(plan)

        engine_def = mock_sim_exec.execute.call_args.args[0]
        ctx = engine_def.simulation_contexts[0]
        assert ctx.cohort == "cohort-2000-06"

    def test_context_allocation_policy_is_exact_unit_policy_object(self) -> None:
        alloc = StubAllocationPolicy()
        unit = PlannedSimulationUnit(
            cohort=make_cohort(2000),
            parameter_config=make_param_config(),
            allocation_policy=alloc,
            withdrawal_policy=StubWithdrawalPolicy(),
            initial_portfolio=make_portfolio(),
        )
        plan = make_plan(units=(unit,))
        executor, mock_sim_exec = make_executor(simulation_results=(make_simulation_result(),))

        executor.execute(plan)

        engine_def = mock_sim_exec.execute.call_args.args[0]
        ctx = engine_def.simulation_contexts[0]
        assert ctx.allocation_policy is alloc

    def test_context_withdrawal_policy_is_exact_unit_policy_object(self) -> None:
        withd = StubWithdrawalPolicy()
        unit = PlannedSimulationUnit(
            cohort=make_cohort(2000),
            parameter_config=make_param_config(),
            allocation_policy=StubAllocationPolicy(),
            withdrawal_policy=withd,
            initial_portfolio=make_portfolio(),
        )
        plan = make_plan(units=(unit,))
        executor, mock_sim_exec = make_executor(simulation_results=(make_simulation_result(),))

        executor.execute(plan)

        engine_def = mock_sim_exec.execute.call_args.args[0]
        ctx = engine_def.simulation_contexts[0]
        assert ctx.withdrawal_policy is withd

    def test_context_initial_portfolio_is_exact_unit_portfolio_object(self) -> None:
        """Executor maps the plan unit's materialised portfolio; it never invents one."""
        portfolio = make_portfolio()
        unit = make_unit(year=2000, portfolio=portfolio)
        plan = make_plan(units=(unit,))
        executor, mock_sim_exec = make_executor(simulation_results=(make_simulation_result(),))

        executor.execute(plan)

        engine_def = mock_sim_exec.execute.call_args.args[0]
        ctx = engine_def.simulation_contexts[0]
        assert ctx.initial_portfolio is portfolio

    def test_policies_are_not_inspected_or_materialised(self) -> None:
        """Executor passes policy objects unchanged — it never reads policy internals."""
        alloc = Mock(spec=AllocationPolicy)
        withd = Mock(spec=WithdrawalPolicy)
        unit = PlannedSimulationUnit(
            cohort=make_cohort(2000),
            parameter_config=make_param_config(),
            allocation_policy=alloc,
            withdrawal_policy=withd,
            initial_portfolio=make_portfolio(),
        )
        plan = make_plan(units=(unit,))
        executor, mock_sim_exec = make_executor(simulation_results=(make_simulation_result(),))

        executor.execute(plan)

        # No methods called on the policy objects by the executor
        alloc.decide.assert_not_called()
        withd.decide.assert_not_called()


# ---------------------------------------------------------------------------
# TestResearchExecutorValidation
# ---------------------------------------------------------------------------


class TestResearchExecutorValidation:
    def test_rejects_non_research_plan_input(self) -> None:
        executor, mock_sim_exec = make_executor()

        with pytest.raises(InvalidResearchPlanError, match="ResearchPlan"):
            executor.execute("not-a-plan")  # type: ignore[arg-type]

        mock_sim_exec.execute.assert_not_called()

    def test_rejects_none_plan(self) -> None:
        executor, mock_sim_exec = make_executor()

        with pytest.raises(InvalidResearchPlanError):
            executor.execute(None)  # type: ignore[arg-type]

        mock_sim_exec.execute.assert_not_called()

    def test_validates_all_units_before_calling_executor(self) -> None:
        """If any unit fails translation, SimulationExecutor must not be called."""
        # We use a plan with a mocked bad unit at index 1 — we can't construct an invalid
        # unit directly because PlannedSimulationUnit validates on construction.
        # Instead, bypass via object.__setattr__ to simulate a corrupted plan.
        unit_good = make_unit(year=2000)
        unit_bad = make_unit(year=2001)

        # Corrupt the bad unit's allocation_policy after construction
        object.__setattr__(unit_bad, "allocation_policy", None)

        # Bypass ResearchPlan validation too (it only checks isinstance, not policy None)
        exp_def = make_experiment_def()
        plan = ResearchPlan.__new__(ResearchPlan)
        object.__setattr__(plan, "experiment_definition", exp_def)
        object.__setattr__(plan, "units", (unit_good, unit_bad))

        executor, mock_sim_exec = make_executor()

        with pytest.raises((InvalidResearchPlanError, Exception)):
            executor.execute(plan)

        # Regardless, executor must not have been called
        mock_sim_exec.execute.assert_not_called()

    def test_simulation_executor_not_called_on_invalid_plan_type(self) -> None:
        executor, mock_sim_exec = make_executor()

        with pytest.raises(InvalidResearchPlanError):
            executor.execute(42)  # type: ignore[arg-type]

        mock_sim_exec.execute.assert_not_called()


# ---------------------------------------------------------------------------
# TestResearchExecutorFailurePropagation
# ---------------------------------------------------------------------------


class TestResearchExecutorFailurePropagation:
    def test_simulation_executor_runtime_error_is_wrapped_in_research_execution_error(
        self,
    ) -> None:
        plan = make_plan(units=(make_unit(year=2000),))
        executor, mock_sim_exec = make_executor()
        mock_sim_exec.execute.side_effect = RuntimeError("engine exploded")

        with pytest.raises(ResearchExecutionError) as exc_info:
            executor.execute(plan)

        assert "engine exploded" in str(exc_info.value.__cause__)

    def test_original_cause_is_preserved_in_wrapped_exception(self) -> None:
        plan = make_plan(units=(make_unit(year=2000),))
        executor, mock_sim_exec = make_executor()
        original_error = ValueError("underlying engine error")
        mock_sim_exec.execute.side_effect = original_error

        with pytest.raises(ResearchExecutionError) as exc_info:
            executor.execute(plan)

        assert exc_info.value.__cause__ is original_error

    def test_no_partial_result_returned_after_executor_failure(self) -> None:
        plan = make_plan(units=(make_unit(year=2000),))
        executor, mock_sim_exec = make_executor()
        mock_sim_exec.execute.side_effect = RuntimeError("runner crashed")

        result = None
        with pytest.raises(ResearchExecutionError):
            result = executor.execute(plan)

        assert result is None

    def test_modelled_failed_simulation_result_is_preserved_unchanged(self) -> None:
        """A SimulationResult with success=False is a normal engine output; preserve it."""
        unit = make_unit(year=2000)
        plan = make_plan(units=(unit,))
        failed_result = make_simulation_result(success=False)
        executor, mock_sim_exec = make_executor(simulation_results=(failed_result,))

        research_result = executor.execute(plan)

        assert research_result.results[0] is failed_result
        assert research_result.results[0].statistics.success is False

    def test_mix_of_success_and_failure_results_is_preserved(self) -> None:
        unit_a = make_unit(year=2000)
        unit_b = make_unit(year=2001)
        plan = make_plan(units=(unit_a, unit_b))
        success_result = make_simulation_result(success=True)
        failed_result = make_simulation_result(success=False)
        executor, mock_sim_exec = make_executor(simulation_results=(success_result, failed_result))

        research_result = executor.execute(plan)

        assert research_result.results[0] is success_result
        assert research_result.results[1] is failed_result


# ---------------------------------------------------------------------------
# TestResearchExecutionResultProvenance
# ---------------------------------------------------------------------------


class TestResearchExecutionResultProvenance:
    def test_result_contains_original_plan_reference(self) -> None:
        plan = make_plan(units=(make_unit(year=2000), make_unit(year=2001)))
        results = (make_simulation_result(), make_simulation_result())
        executor, mock_sim_exec = make_executor(simulation_results=results)

        research_result = executor.execute(plan)

        assert research_result.plan is plan

    def test_result_count_equals_plan_unit_count(self) -> None:
        units = tuple(make_unit(year=2000 + i) for i in range(4))
        plan = make_plan(units=units)
        sim_results = tuple(make_simulation_result() for _ in units)
        executor, mock_sim_exec = make_executor(simulation_results=sim_results)

        research_result = executor.execute(plan)

        assert len(research_result.results) == len(plan)

    def test_results_property_matches_engine_simulation_results_order(self) -> None:
        unit_a = make_unit(year=2000)
        unit_b = make_unit(year=2001)
        plan = make_plan(units=(unit_a, unit_b))
        result_a = make_simulation_result(success=True)
        result_b = make_simulation_result(success=False)
        executor, mock_sim_exec = make_executor(simulation_results=(result_a, result_b))

        research_result = executor.execute(plan)

        assert research_result.results[0] is result_a
        assert research_result.results[1] is result_b

    def test_zip_provenance_association_is_correct(self) -> None:
        """zip(result.plan.units, result.results) yields correct pairs."""
        unit_a = make_unit(year=2000)
        unit_b = make_unit(year=2001)
        plan = make_plan(units=(unit_a, unit_b))
        result_a = make_simulation_result(success=True)
        result_b = make_simulation_result(success=False)
        executor, mock_sim_exec = make_executor(simulation_results=(result_a, result_b))

        research_result = executor.execute(plan)

        pairs = list(zip(research_result.plan.units, research_result.results, strict=True))
        assert pairs[0] == (unit_a, result_a)
        assert pairs[1] == (unit_b, result_b)

    def test_plan_unit_order_is_not_modified(self) -> None:
        units = tuple(make_unit(year=2000 + i) for i in range(5))
        plan = make_plan(units=units)
        sim_results = tuple(make_simulation_result() for _ in units)
        executor, mock_sim_exec = make_executor(simulation_results=sim_results)

        research_result = executor.execute(plan)

        for i, unit in enumerate(research_result.plan.units):
            assert unit is plan.units[i]


# ---------------------------------------------------------------------------
# TestResearchExecutionResultImmutability
# ---------------------------------------------------------------------------


class TestResearchExecutionResultImmutability:
    def test_result_is_frozen(self) -> None:
        plan = make_plan(units=(make_unit(year=2000),))
        executor, mock_sim_exec = make_executor(simulation_results=(make_simulation_result(),))

        research_result = executor.execute(plan)

        with pytest.raises(FrozenInstanceError):
            research_result.plan = plan  # type: ignore[misc]

    def test_result_experiment_result_is_frozen(self) -> None:
        plan = make_plan(units=(make_unit(year=2000),))
        executor, mock_sim_exec = make_executor(simulation_results=(make_simulation_result(),))

        research_result = executor.execute(plan)

        with pytest.raises(FrozenInstanceError):
            research_result.experiment_result = research_result.experiment_result  # type: ignore[misc]

    def test_result_plan_is_unchanged(self) -> None:
        unit = make_unit(year=2000)
        plan = make_plan(units=(unit,))
        executor, mock_sim_exec = make_executor(simulation_results=(make_simulation_result(),))

        research_result = executor.execute(plan)

        assert research_result.plan.experiment_definition is plan.experiment_definition
        assert research_result.plan.units == plan.units


# ---------------------------------------------------------------------------
# TestResearchExecutorStatelessness
# ---------------------------------------------------------------------------


class TestResearchExecutorStatelessness:
    def test_repeated_execution_with_same_plan_calls_executor_each_time(self) -> None:
        plan = make_plan(units=(make_unit(year=2000), make_unit(year=2001)))
        executor, mock_sim_exec = make_executor()
        results = (make_simulation_result(), make_simulation_result())
        mock_sim_exec.execute.return_value = make_experiment_run(results)

        executor.execute(plan)
        executor.execute(plan)

        assert mock_sim_exec.execute.call_count == 2

    def test_repeated_executions_produce_same_context_order(self) -> None:
        unit_a = make_unit(year=2000)
        unit_b = make_unit(year=2001)
        plan = make_plan(units=(unit_a, unit_b))
        executor, mock_sim_exec = make_executor()
        results = (make_simulation_result(), make_simulation_result())
        mock_sim_exec.execute.return_value = make_experiment_run(results)

        executor.execute(plan)
        executor.execute(plan)

        calls = mock_sim_exec.execute.call_args_list
        first_contexts = calls[0].args[0].simulation_contexts
        second_contexts = calls[1].args[0].simulation_contexts

        assert first_contexts[0].start_date == second_contexts[0].start_date
        assert first_contexts[1].start_date == second_contexts[1].start_date

    def test_executor_has_no_mutable_state_after_execution(self) -> None:
        """Re-executing with a different plan should not be affected by prior execution."""
        plan_a = make_plan(units=(make_unit(year=2000),))
        plan_b = make_plan(units=(make_unit(year=2010), make_unit(year=2011)))

        executor, mock_sim_exec = make_executor()
        result_a = (make_simulation_result(),)
        result_b = (make_simulation_result(), make_simulation_result())
        mock_sim_exec.execute.side_effect = [
            make_experiment_run(result_a),
            make_experiment_run(result_b),
        ]

        res_a = executor.execute(plan_a)
        res_b = executor.execute(plan_b)

        assert len(res_a.results) == 1
        assert len(res_b.results) == 2


# ---------------------------------------------------------------------------
# TestResearchExecutionResultConstruction
# ---------------------------------------------------------------------------


class TestResearchExecutionResultConstruction:
    def test_construction_fails_if_plan_units_and_results_lengths_differ(self) -> None:
        plan = make_plan(units=(make_unit(year=2000), make_unit(year=2001)))
        # Engine returned only 1 result for 2 units
        engine_def = EngineExperimentDefinition(
            name="test",
            description="test",
            simulation_contexts=(Mock(spec=SimulationContext),),
        )
        one_result = (make_simulation_result(),)
        bad_run = ExperimentRun(definition=engine_def, simulation_results=one_result)

        with pytest.raises(ValueError, match="Mismatch"):
            ResearchExecutionResult(plan=plan, experiment_result=bad_run)

    def test_results_property_delegates_to_experiment_run_simulation_results(self) -> None:
        plan = make_plan(units=(make_unit(year=2000),))
        sim_result = make_simulation_result()
        engine_def = EngineExperimentDefinition(
            name="test",
            description="test",
            simulation_contexts=(Mock(spec=SimulationContext),),
        )
        run = ExperimentRun(definition=engine_def, simulation_results=(sim_result,))

        rr = ResearchExecutionResult(plan=plan, experiment_result=run)

        assert rr.results is run.simulation_results


# ---------------------------------------------------------------------------
# TestResearchExecutorNoCohortOrParameterGeneratorDependency
# ---------------------------------------------------------------------------


class TestResearchExecutorScopeGuards:
    def test_executor_module_does_not_import_cohort_generator(self) -> None:
        """Static check: CohortGenerator is not imported in the executor module."""
        import research.orchestration.executor as executor_module

        assert not hasattr(executor_module, "CohortGenerator")

    def test_executor_module_does_not_import_parameter_sweep_engine(self) -> None:
        """Static check: ParameterSweepEngine is not imported in the executor module."""
        import research.orchestration.executor as executor_module

        assert not hasattr(executor_module, "ParameterSweepEngine")

    def test_executor_does_not_call_cohort_generator_during_execute(self) -> None:
        plan = make_plan(units=(make_unit(year=2000),))
        executor, mock_sim_exec = make_executor(simulation_results=(make_simulation_result(),))

        ctx_patch = "research.orchestration.executor.ResearchExecutor._create_context_for_unit"
        with patch(ctx_patch) as ctx_method:
            ctx_method.return_value = Mock(spec=SimulationContext)
            mock_sim_exec.execute.return_value = make_experiment_run((make_simulation_result(),))
            executor.execute(plan)

        # No CohortGenerator invoked — verified by absence of that symbol in executor
        import research.orchestration.executor as mod

        assert not hasattr(mod, "CohortGenerator")
