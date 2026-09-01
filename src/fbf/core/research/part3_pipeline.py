"""Part 3 execution integration — plan → execute → aggregate.

Orchestrates the full Part 3 pipeline: takes a materialized ``Part3PlanResult``,
executes it through the simulation engine, and aggregates results by CAPE regime.

This module belongs to the Research layer.  It does not modify the simulation
engine, the canonical datasets, or the generic planning/execution primitives.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fbf.core.execution import ExecutionOptions, execute_study_plan
from fbf.core.execution.pipeline.simulation import SimulationResult
from fbf.core.execution.result import ResearchExecutionResult
from fbf.core.research.part3_aggregation import Part3AggregationResult, aggregate_part3_results
from fbf.core.research.part3_planner import Part3PlanResult
from fbf.core.study.builder import BuiltStudy

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Result bundle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Part3ExecutionResult:
    """Complete result of the Part 3 pipeline: execution + aggregation.

    Attributes
    ----------
    execution:
        The raw engine execution result containing per-unit SimulationResults.
    aggregation:
        Success rates grouped by CAPE regime, horizon, equity allocation,
        withdrawal rate, and terminal target.
    """

    execution: ResearchExecutionResult
    aggregation: Part3AggregationResult

    @property
    def results(self) -> tuple[SimulationResult, ...]:
        """Ordered tuple of individual SimulationResults from the engine."""
        return self.execution.results

    @property
    def total_units(self) -> int:
        """Total number of simulation units executed."""
        return self.aggregation.total_units


# ---------------------------------------------------------------------------
# Adapter: Part3PlanResult → BuiltStudy
# ---------------------------------------------------------------------------


def adapt_part3_to_builtin(plan_result: Part3PlanResult) -> BuiltStudy:
    """Wrap a ``Part3PlanResult`` as a ``BuiltStudy`` for ``execute_study_plan``.

    The execution layer consumes ``BuiltStudy.plan`` (a ``ResearchPlan``)
    to drive sequential/parallel execution.  This adapter preserves the
    exact ``ResearchPlan`` produced by the Part 3 planner without copying
    or re-materializing units.

    Only the ``experiment_definition`` from the plan is forwarded; cohorts
    and param_configs are extracted from the ``Part3PlanResult`` directly.
    """
    plan = plan_result.plan
    if plan is None:
        raise ValueError("Part3PlanResult.plan cannot be None")

    experiment_def = plan.experiment_definition
    if experiment_def is None:
        raise ValueError(
            "Part3PlanResult.plan.experiment_definition cannot be None"
        )

    return BuiltStudy(
        plan=plan,
        experiment_definition=experiment_def,
        cohorts=plan_result.cohorts,
        param_configs=plan_result.param_configs,
    )


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------


def execute_part3_pipeline(
    plan_result: Part3PlanResult,
    options: ExecutionOptions | None = None,
) -> Part3ExecutionResult:
    """Execute a materialized Part 3 plan and aggregate by CAPE regime.

    Steps:
    1. Adapt ``Part3PlanResult`` → ``BuiltStudy`` for the execution layer.
    2. Call ``execute_study_plan`` (sequential or parallel, per options).
    3. Aggregate simulation results by CAPE regime using the plan's
       manifest-derived metadata.

    No CAPE information enters ``SimulationContext`` or the engine.
    """
    # Step 1: Adapt for execution
    builtin = adapt_part3_to_builtin(plan_result)

    # Step 2: Execute
    execution_result = execute_study_plan(builtin, options)

    # Step 3: Aggregate by CAPE regime
    # The planner produces units in cohort-major order:
    # for each cohort, all param_configs are applied.
    # Replicate cohorts and params to match per-unit execution results.
    n_cohorts = len(plan_result.cohorts)
    n_params = len(plan_result.param_configs)
    expected_units = n_cohorts * n_params
    actual_units = len(execution_result.results)

    if expected_units == actual_units:
        # Cross-product structure: replicate to per-unit alignment
        per_unit_cohorts = tuple(
            c for c in plan_result.cohorts for _ in range(n_params)
        )
        per_unit_params = tuple(
            p for _ in range(n_cohorts) for p in plan_result.param_configs
        )
    elif n_cohorts == actual_units:
        # 1:1 structure (e.g. single param config already broadcast)
        per_unit_cohorts = plan_result.cohorts
        per_unit_params = plan_result.param_configs * n_cohorts
    else:
        raise ValueError(
            f"Cannot reconcile plan structure: {n_cohorts} cohorts, "
            f"{n_params} param_configs, {actual_units} results"
        )

    aggregation = aggregate_part3_results(
        cohorts=per_unit_cohorts,
        param_configs=per_unit_params,
        simulation_results=execution_result.results,
        get_cape_metadata=plan_result.get_cape_metadata,
    )

    return Part3ExecutionResult(
        execution=execution_result,
        aggregation=aggregation,
    )
