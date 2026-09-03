"""Tests for Part 3 execution integration.

Validates ``adapt_part3_to_builtin``, ``Part3ExecutionResult``, and
the ``execute_part3_pipeline`` orchestrator.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies.cape_regime import CapeRegime
from fbf.core.execution.pipeline.simulation import (
    ExperimentRun,
    SimulationResult,
    SimulationStatistics,
)
from fbf.core.execution.result import ResearchExecutionResult
from fbf.core.research.part3_aggregation import (
    Part3AggregationResult,
)
from fbf.core.research.part3_pipeline import (
    Part3ExecutionResult,
    adapt_part3_to_builtin,
    execute_part3_pipeline,
)
from fbf.core.research.part3_planner import CapeMetadata, Part3PlanResult
from fbf.core.study.builder import BuiltStudy
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import ResearchPlan

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


_D = date.fromisoformat


def _cohort(d: str) -> CohortSpecification:
    return CohortSpecification(start_date=_D(d))


def _params(horizon: int, equity: str, withdrawal: str) -> ParameterConfiguration:
    return ParameterConfiguration(
        values={
            "horizon_years": horizon,
            "equity_allocation": equity,
            "withdrawal_rate": withdrawal,
        }
    )


def _mock_experiment_def() -> Any:
    """Build a minimal ExperimentDefinition-like object."""
    mock = MagicMock()
    mock.name = "test"
    mock.description = "test experiment"
    return mock


def _minimal_plan_result(
    cohorts: list[CohortSpecification],
    param_configs: list[ParameterConfiguration],
    cape_metadata: Mapping[date, CapeMetadata],
) -> Part3PlanResult:
    """Build a minimal Part3PlanResult for testing the adapter.

    The ``plan`` is a mock to avoid ResearchPlan's non-empty units
    validation (which requires PlannedSimulationUnit objects).  The
    adapter only reads ``plan.experiment_definition``.

    ``cohorts`` and ``param_configs`` may have different lengths (the
    planner produces a cross-product).
    """

    mock_exp = _mock_experiment_def()
    mock_plan = MagicMock(spec=ResearchPlan)
    mock_plan.experiment_definition = mock_exp

    registry = {d.isoformat(): v for d, v in cape_metadata.items()}

    def get_cape(spec: CohortSpecification) -> CapeMetadata:
        return registry.get(spec.start_date.isoformat(), (None, None))

    return Part3PlanResult(
        plan=mock_plan,
        get_cape_metadata=get_cape,
        cohorts=tuple(cohorts),
        param_configs=tuple(param_configs),
    )


def _mock_execution_result(
    n_units: int,
) -> ResearchExecutionResult:
    """Build a mock ResearchExecutionResult with n_units results."""
    results = tuple(
        SimulationResult(
            timeline=None,  # type: ignore[arg-type]
            statistics=SimulationStatistics(
                final_wealth=Money(Decimal("100000"), Currency.EUR),
                max_drawdown=0.0,
                success=True,
                failure_month=None,
            failure_state=None,
                months_simulated=360,
                execution_time_seconds=0.0,
            ),
        )
        for _ in range(n_units)
    )
    experiment_run = MagicMock(spec=ExperimentRun)
    experiment_run.simulation_results = results
    result = MagicMock(spec=ResearchExecutionResult)
    result.results = results
    result.experiment_result = experiment_run
    return result


# ---------------------------------------------------------------------------
# adapt_part3_to_builtin tests
# ---------------------------------------------------------------------------


class TestAdaptPart3ToBuiltin:
    """Unit tests for the Part3PlanResult → BuiltStudy adapter."""

    def test_returns_built_study(self) -> None:
        cohorts = [_cohort("1980-01-01")]
        params = [_params(30, "1.0", "0.04")]
        cape = {_D("1980-01-01"): (Decimal("25"), "HIGH")}
        pr = _minimal_plan_result(cohorts, params, cape)

        builtin = adapt_part3_to_builtin(pr)

        assert isinstance(builtin, BuiltStudy)

    def test_plan_preserved(self) -> None:
        cohorts = [_cohort("1980-01-01")]
        params = [_params(30, "1.0", "0.04")]
        cape = {_D("1980-01-01"): (Decimal("25"), "HIGH")}
        pr = _minimal_plan_result(cohorts, params, cape)

        builtin = adapt_part3_to_builtin(pr)

        assert builtin.plan is pr.plan

    def test_experiment_definition_preserved(self) -> None:
        cohorts = [_cohort("1980-01-01")]
        params = [_params(30, "1.0", "0.04")]
        cape = {_D("1980-01-01"): (Decimal("25"), "HIGH")}
        pr = _minimal_plan_result(cohorts, params, cape)

        builtin = adapt_part3_to_builtin(pr)

        assert builtin.experiment_definition is pr.plan.experiment_definition

    def test_cohorts_from_plan_result(self) -> None:
        cohorts = [_cohort("1980-01-01"), _cohort("1990-01-01")]
        params = [_params(30, "1.0", "0.04"), _params(30, "1.0", "0.04")]
        cape = {
            _D("1980-01-01"): (Decimal("25"), "HIGH"),
            _D("1990-01-01"): (Decimal("12"), "BELOW_15"),
        }
        pr = _minimal_plan_result(cohorts, params, cape)

        builtin = adapt_part3_to_builtin(pr)

        assert builtin.cohorts == tuple(cohorts)

    def test_param_configs_from_plan_result(self) -> None:
        cohorts = [_cohort("1980-01-01"), _cohort("1985-01-01")]
        params = [_params(30, "1.0", "0.04"), _params(40, "0.6", "0.03")]
        cape = {
            _D("1980-01-01"): (Decimal("25"), "HIGH"),
            _D("1985-01-01"): (Decimal("18"), "MODERATE"),
        }
        pr = _minimal_plan_result(cohorts, params, cape)

        builtin = adapt_part3_to_builtin(pr)

        assert len(builtin.param_configs) == 2

    def test_plan_none_raises(self) -> None:
        pr = _minimal_plan_result([], [], {})
        object.__setattr__(pr, "plan", None)

        with pytest.raises(ValueError, match="cannot be None"):
            adapt_part3_to_builtin(pr)

    def test_experiment_definition_none_raises(self) -> None:
        pr = _minimal_plan_result([], [], {})
        pr.plan.experiment_definition = None  # type: ignore[misc, assignment]

        with pytest.raises(ValueError, match="experiment_definition"):
            adapt_part3_to_builtin(pr)


# ---------------------------------------------------------------------------
# Part3ExecutionResult tests
# ---------------------------------------------------------------------------


class TestPart3ExecutionResult:
    """Unit tests for the Part3ExecutionResult dataclass."""

    def test_results_property(self) -> None:
        n = 5
        exec_result = _mock_execution_result(n)
        agg = Part3AggregationResult(
            regime_aggregations=(),
            total_units=n,
            excluded_no_cape=0,
        )
        p3r = Part3ExecutionResult(execution=exec_result, aggregation=agg)

        assert len(p3r.results) == n

    def test_total_units(self) -> None:
        exec_result = _mock_execution_result(10)
        agg = Part3AggregationResult(
            regime_aggregations=(),
            total_units=10,
            excluded_no_cape=0,
        )
        p3r = Part3ExecutionResult(execution=exec_result, aggregation=agg)

        assert p3r.total_units == 10

    def test_frozen(self) -> None:
        exec_result = _mock_execution_result(1)
        agg = Part3AggregationResult(
            regime_aggregations=(),
            total_units=1,
            excluded_no_cape=0,
        )
        p3r = Part3ExecutionResult(execution=exec_result, aggregation=agg)

        with pytest.raises(AttributeError):
            p3r.total_units = 20  # type: ignore[misc]


# ---------------------------------------------------------------------------
# execute_part3_pipeline tests (mocked execution)
# ---------------------------------------------------------------------------


class TestExecutePart3Pipeline:
    """Tests for the pipeline orchestrator with mocked execution."""

    @patch("fbf.core.research.part3_pipeline.execute_study_plan")
    def test_calls_execute_study_plan(self, mock_exec: Any) -> None:
        """Pipeline calls execute_study_plan with a BuiltStudy."""
        cohorts = [_cohort("1980-01-01")]
        params = [_params(30, "1.0", "0.04")]
        cape = {_D("1980-01-01"): (Decimal("25"), "HIGH")}
        pr = _minimal_plan_result(cohorts, params, cape)

        mock_exec.return_value = _mock_execution_result(1)

        execute_part3_pipeline(pr)

        mock_exec.assert_called_once()
        call_args = mock_exec.call_args
        assert isinstance(call_args[0][0], BuiltStudy)

    @patch("fbf.core.research.part3_pipeline.execute_study_plan")
    def test_aggregates_results(self, mock_exec: Any) -> None:
        """Pipeline aggregates results by CAPE regime."""
        cohorts = [_cohort("1980-01-01")]
        params = [_params(30, "1.0", "0.04")]
        cape = {_D("1980-01-01"): (Decimal("25"), "HIGH")}
        pr = _minimal_plan_result(cohorts, params, cape)

        mock_exec.return_value = _mock_execution_result(1)

        result = execute_part3_pipeline(pr)

        assert isinstance(result, Part3ExecutionResult)
        assert result.aggregation.total_units == 1

    @patch("fbf.core.research.part3_pipeline.execute_study_plan")
    def test_forwards_options(self, mock_exec: Any) -> None:
        """Pipeline forwards ExecutionOptions to execute_study_plan."""
        from fbf.core.execution import ExecutionBackend, ExecutionOptions

        cohorts = [_cohort("1980-01-01")]
        params = [_params(30, "1.0", "0.04")]
        cape = {_D("1980-01-01"): (Decimal("25"), "HIGH")}
        pr = _minimal_plan_result(cohorts, params, cape)
        opts = ExecutionOptions(backend=ExecutionBackend.FAST)

        mock_exec.return_value = _mock_execution_result(1)

        execute_part3_pipeline(pr, options=opts)

        call_args = mock_exec.call_args
        assert call_args[1].get("options") is opts or call_args[0][1] is opts

    @patch("fbf.core.research.part3_pipeline.execute_study_plan")
    def test_multiple_regimes(self, mock_exec: Any) -> None:
        """Pipeline aggregates multiple regimes correctly."""
        cohorts = [_cohort("1980-01-01"), _cohort("1990-01-01")]
        params = [_params(30, "1.0", "0.04")]  # single param config
        cape = {
            _D("1980-01-01"): (Decimal("25"), "HIGH"),
            _D("1990-01-01"): (Decimal("12"), "BELOW_15"),
        }
        pr = _minimal_plan_result(cohorts, params, cape)

        # First succeeds, second fails
        results = (
            SimulationResult(
                timeline=None,  # type: ignore[arg-type]
                statistics=SimulationStatistics(
                    final_wealth=Money(Decimal("100000"), Currency.EUR),
                    max_drawdown=0.0,
                    success=True,
                    failure_month=None,
            failure_state=None,
                    months_simulated=360,
                    execution_time_seconds=0.0,
                ),
            ),
            SimulationResult(
                timeline=None,  # type: ignore[arg-type]
                statistics=SimulationStatistics(
                    final_wealth=Money(Decimal("0"), Currency.EUR),
                    max_drawdown=1.0,
                    success=False,
                    failure_month=120,
            failure_state=None,
                    months_simulated=120,
                    execution_time_seconds=0.0,
                ),
            ),
        )
        exec_result = MagicMock(spec=ResearchExecutionResult)
        exec_result.results = results
        mock_exec.return_value = exec_result

        result = execute_part3_pipeline(pr)

        regimes = {a.cape_regime for a in result.aggregation.regime_aggregations}
        assert regimes == {CapeRegime.HIGH, CapeRegime.BELOW_15}
        by_regime = {a.cape_regime: a for a in result.aggregation.regime_aggregations}
        assert by_regime[CapeRegime.HIGH].successful_cohorts == 1
        assert by_regime[CapeRegime.BELOW_15].successful_cohorts == 0
