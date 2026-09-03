"""Benchmark helpers — synthetic domain object factories.

These are independent of the P4.1 integration helpers and are
optimised for performance benchmark setup.
"""

from __future__ import annotations

from decimal import Decimal

from fbf.core.domain.model.money import Currency, Money
from fbf.core.execution.pipeline.simulation import (
    ExperimentRun,
    SimulationResult,
    SimulationStatistics,
    SimulationTimeline,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.result import ResearchExecutionResult
from fbf.core.study.plan import ResearchPlan


def make_simulation_result(
    final_wealth: str = "500000.00",
    success: bool = True,
    failure_month: int | None = None,
    months_simulated: int = 120,
) -> SimulationResult:
    """Create a deterministic synthetic simulation result."""
    return SimulationResult(
        timeline=SimulationTimeline(monthly_results=()),
        statistics=SimulationStatistics(
            final_wealth=Money(Decimal(final_wealth), Currency.EUR),
            max_drawdown=0.05,
            success=success,
            failure_month=failure_month,
            failure_state=None,
            months_simulated=months_simulated,
            execution_time_seconds=0.01,
        ),
    )


def make_execution_result(plan: ResearchPlan) -> ResearchExecutionResult:
    """Create a synthetic execution result matching the plan structure."""
    from .conftest import BenchmarkAllocationPolicy, BenchmarkWithdrawalPolicy

    sim_contexts = tuple(
        SimulationContext(
            experiment_name=plan.experiment_definition.name,
            cohort=unit.cohort.start_date.isoformat(),
            start_date=unit.cohort.start_date,
            horizon_months=plan.experiment_definition.horizon_months,
            initial_wealth=plan.experiment_definition.initial_wealth,
            initial_portfolio=unit.initial_portfolio,
            dataset=plan.experiment_definition.dataset,
            allocation_policy=BenchmarkAllocationPolicy(),
            withdrawal_policy=BenchmarkWithdrawalPolicy(),
        )
        for unit in plan.units
    )
    from fbf.core.execution.pipeline.simulation import (
        ExperimentDefinition as EngineExperimentDefinition,
    )

    engine_def = EngineExperimentDefinition(
        name=plan.experiment_definition.name,
        description=plan.experiment_definition.description,
        simulation_contexts=sim_contexts,
    )
    sim_results = tuple(
        make_simulation_result(str(500000 + i * 1000))
        for i in range(len(plan.units))
    )
    experiment_run = ExperimentRun(
        definition=engine_def, simulation_results=sim_results
    )
    return ResearchExecutionResult(
        plan=plan, experiment_result=experiment_run
    )
