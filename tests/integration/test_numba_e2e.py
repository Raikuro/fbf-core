"""R7.5.5 — Small black-box E2E: Numba executor through the real study path.

Exercises the complete path:
  ExperimentDefinition → ResearchPlan → Executor → Numba backend → Results

Verifies that the optimized backend matches the workbook oracle for the
supported cases (static allocations with FixedRealWithdrawalPolicy).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from fbf.core.execution import ExecutionBackend, ExecutionOptions, execute_study_plan
from fbf.core.execution.executor import ResearchExecutor
from fbf.core.execution.pipeline.simulation import SimulationResult
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.numba_executor import NumbaSimulationExecutor
from fbf.core.study.builder import BuiltStudy, build_initial_portfolio
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan
from tests.unit.strategies.workbook_oracle_test_helper import (
    WorkbookOracleResult,
    compute_workbook_oracle_result,
)

_EQ = AssetClass(id="equity", name="", description="")
_BD = AssetClass(id="bond", name="", description="")

# Float64 precision tolerance for Numba vs Decimal workbook oracle
# Numba uses float64 (~15-17 decimal digits) which can accumulate ~0.1% error over 360 months
WEALTH_TOLERANCE = Decimal("10.0")


def _make_dataset(months: int = 721) -> Dataset:
    pe = pb = Decimal("100")
    snapshots = []
    d = date(1900, 1, 1)
    for _ in range(months):
        snapshots.append(
            MarketSnapshot(
                date=d,
                index_levels={_EQ: pe, _BD: pb},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            )
        )
        pe *= Decimal("1.006")
        pb *= Decimal("1.002")
        d = date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)
    return Dataset(snapshots=snapshots, frequency="monthly")


def _build_plan(
    cohorts: int = 2,
    weights: list[float] | None = None,
    rates: list[float] | None = None,
    horizons: list[int] | None = None,
) -> tuple[Dataset, ResearchPlan]:
    if weights is None:
        weights = [0.5, 0.75]
    if rates is None:
        rates = [0.03, 0.04]
    if horizons is None:
        horizons = [120, 360]

    longest = max(horizons)
    # Need enough snapshots for the last cohort (cohorts-1 months later) + longest horizon + 1
    dataset = _make_dataset(longest + cohorts + 1)

    cohort_specs = tuple(
        CohortSpecification(start_date=date(1900, 1 + i, 1))
        for i in range(cohorts)
    )

    experiment = ExperimentDefinition(
        name="numba_e2e",
        description="Numba E2E validation",
        dataset=dataset,
        horizon_months=longest,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        cohorts=cohort_specs,
        allocation_policies=tuple(
            ConstantAllocationPolicy(Decimal(str(w))) for w in weights
        ),
        withdrawal_policies=tuple(
            FixedRealWithdrawalPolicy(Decimal(str(r))) for r in rates
        ),
    )

    units = []
    for cohort in cohort_specs:
        for w in weights:
            for r in rates:
                for h in horizons:
                    portfolio = build_initial_portfolio(
                        Money(Decimal("1000000"), Currency.EUR), dataset
                    )
                    param_config = ParameterConfiguration({
                        "equity_allocation": w,
                        "withdrawal_rate": r,
                        "horizon_years": h // 12,
                    })
                    unit = PlannedSimulationUnit(
                        cohort=cohort,
                        parameter_config=param_config,
                        allocation_policy=ConstantAllocationPolicy(Decimal(str(w))),
                        withdrawal_policy=FixedRealWithdrawalPolicy(Decimal(str(r))),
                        initial_portfolio=portfolio,
                        dataset=dataset.slice(cohort.start_date, h + 1),  # +1 for workbook
                        horizon_months=h,
                    )
                    units.append(unit)

    return dataset, ResearchPlan(
        experiment_definition=experiment,
        units=tuple(units),
    )


def _compute_oracle_results(plan: ResearchPlan) -> list[WorkbookOracleResult]:
    """Compute expected workbook oracle results for all units in plan."""
    results = []
    default_horizon = plan.experiment_definition.horizon_months
    for unit in plan.units:
        # Use unit's horizon_months or fall back to experiment definition
        horizon = unit.horizon_months if unit.horizon_months is not None else default_horizon
        # Reconstruct context from unit - use the unit's actual dataset and portfolio
        ctx = SimulationContext(
            experiment_name=plan.experiment_definition.name,
            cohort=str(unit.cohort.start_date),
            start_date=unit.cohort.start_date,
            horizon_months=horizon,
            initial_wealth=plan.experiment_definition.initial_wealth,
            initial_portfolio=unit.initial_portfolio,
            dataset=unit.dataset,
            allocation_policy=unit.allocation_policy,
            withdrawal_policy=unit.withdrawal_policy,
            final_value_target=unit.final_value_target,
        )
        results.append(compute_workbook_oracle_result(ctx))
    return results


def _run_numba(plan: ResearchPlan) -> tuple[SimulationResult, ...]:
    numba_exec = NumbaSimulationExecutor()
    research_exec = ResearchExecutor(numba_exec)
    result = research_exec.execute(plan)
    return tuple(result.experiment_result.simulation_results)


def _assert_matches_workbook(
    oracle: WorkbookOracleResult,
    numba: SimulationResult,
    label: str,
) -> None:
    numba_s = numba.statistics
    assert numba_s.success == oracle.success, (
        f"{label}: success mismatch ({numba_s.success} vs {oracle.success})"
    )
    assert numba_s.failure_month == oracle.failure_month, (
        f"{label}: failure_month mismatch ({numba_s.failure_month} vs {oracle.failure_month})"
    )
    assert numba_s.months_simulated == oracle.months_simulated, (
        f"{label}: months_simulated mismatch "
        f"({numba_s.months_simulated} vs {oracle.months_simulated})"
    )
    if oracle.success:
        diff = abs(oracle.final_wealth - numba_s.final_wealth.amount)
        assert diff < WEALTH_TOLERANCE, (
            f"{label}: final_wealth diff {diff} exceeds tolerance "
            f"(oracle={oracle.final_wealth}, "
            f"numba={numba_s.final_wealth.amount})"
        )


class TestNumbaE2EVsWorkbook:
    """Small black-box E2E through the real study path vs workbook oracle."""

    def test_numba_via_sequential_matches_workbook(self) -> None:
        """Run plan through Numba and compare against workbook oracle."""
        _, plan = _build_plan()

        oracle_results = _compute_oracle_results(plan)
        numba_results = _run_numba(plan)

        assert len(oracle_results) == len(numba_results), (
            f"result count mismatch ({len(numba_results)} vs {len(oracle_results)})"
        )
        for i, (oracle, numba) in enumerate(zip(oracle_results, numba_results, strict=True)):
            _assert_matches_workbook(oracle, numba, f"sequential_e2e[{i}]")

    def test_execute_study_plan_numba_mode_matches_workbook(self) -> None:
        """Test the execute_study_plan API with backend=FAST against workbook oracle."""
        _, plan = _build_plan(cohorts=1, weights=[0.6], rates=[0.04], horizons=[120])

        built = BuiltStudy(
            plan=plan,
            experiment_definition=plan.experiment_definition,
            cohorts=plan.experiment_definition.cohorts,
            param_configs=(),
        )

        numba_result = execute_study_plan(
            built,
            options=ExecutionOptions(
                backend=ExecutionBackend.FAST, summary_only=True
            ),
        )

        oracle_results = _compute_oracle_results(plan)
        numba_results = numba_result.experiment_result.simulation_results

        assert len(oracle_results) == len(numba_results)
        for i, (oracle, numba) in enumerate(zip(oracle_results, numba_results, strict=True)):
            _assert_matches_workbook(oracle, numba, f"study_plan_numba[{i}]")

    def test_numba_report_accuracy(self) -> None:
        """Verify the Numba executor's report matches expected group structure."""
        _, plan = _build_plan()

        numba_exec = NumbaSimulationExecutor()
        research_exec = ResearchExecutor(numba_exec)
        research_exec.execute(plan)

        report = numba_exec.report
        assert report is not None
        assert report.logical_units == len(plan.units)
        assert report.groups > 0
        # Each group evaluates its longest horizon; with 2 cohorts x 2 weights x 2 rates = 8 groups
        # Each group has 2 horizons (120, 360), so longest_path_evaluations = 8 * 2 = 16
        assert report.longest_path_evaluations == 16
        assert report.independent_evaluations == 0
