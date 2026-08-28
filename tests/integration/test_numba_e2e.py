"""R7.5.5 — Small black-box E2E: Numba executor through the real study path.

Exercises the complete path:
  ExperimentDefinition → ResearchPlan → Executor → Numba backend → Results

Verifies that the optimized backend is externally indistinguishable from
the reference backend for the supported cases.
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
from fbf.core.execution.strategies.numba_executor import NumbaSimulationExecutor
from fbf.core.execution.strategies.parallel_executor import (
    _create_default_simulation_executor,
    sequential_execute,
)
from fbf.core.study.builder import BuiltStudy, build_initial_portfolio
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan

_EQ = AssetClass(id="equity", name="", description="")
_BD = AssetClass(id="bond", name="", description="")

WEALTH_TOLERANCE = Decimal("0.01")


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
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return Dataset(snapshots=snapshots, frequency="monthly", version="1.0")


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

    dataset = _make_dataset(max(horizons) + 1)
    longest = max(horizons)

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
                        Money(Decimal("1000000"), Currency.EUR)
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
                        dataset=dataset.slice(cohort.start_date, h),
                    )
                    units.append(unit)

    return dataset, ResearchPlan(
        experiment_definition=experiment,
        units=tuple(units),
    )


def _compare_results(
    ref_results: tuple[object, ...],
    numba_results: tuple[object, ...],
    label: str,
) -> None:
    assert len(ref_results) == len(numba_results), (
        f"{label}: result count mismatch ({len(numba_results)} vs {len(ref_results)})"
    )
    for i, (ref_r, numba_r) in enumerate(zip(ref_results, numba_results, strict=True)):
        ref_s = ref_r.statistics
        numba_s = numba_r.statistics
        prefix = f"{label}[{i}]"
        assert numba_s.success == ref_s.success, (
            f"{prefix}: success mismatch ({numba_s.success} vs {ref_s.success})"
        )
        assert numba_s.failure_month == ref_s.failure_month, (
            f"{prefix}: failure_month mismatch"
        )
        assert numba_s.months_simulated == ref_s.months_simulated, (
            f"{prefix}: months_simulated mismatch"
        )
        if ref_s.success:
            diff = abs(ref_s.final_wealth.amount - numba_s.final_wealth.amount)
            assert diff < WEALTH_TOLERANCE, (
                f"{prefix}: final_wealth diff {diff} exceeds tolerance"
            )


class TestNumbaE2ESmall:
    """Small black-box E2E through the real study path."""

    def test_reference_matches_numba_via_sequential(self) -> None:
        """Run the same plan through reference and Numba, compare all results."""
        _, plan = _build_plan()

        ref_result = sequential_execute(
            plan, simulation_executor=_create_default_simulation_executor()
        )
        numba_result = sequential_execute(
            plan, simulation_executor=NumbaSimulationExecutor()
        )

        _compare_results(
            ref_result.experiment_result.simulation_results,
            numba_result.experiment_result.simulation_results,
            "sequential_e2e",
        )

    def test_execute_study_plan_numba_mode(self) -> None:
        """Test the execute_study_plan API with backend=FAST."""
        _, plan = _build_plan(cohorts=1, weights=[0.6], rates=[0.04], horizons=[120])

        built = BuiltStudy(
            plan=plan,
            experiment_definition=plan.experiment_definition,
            cohorts=plan.experiment_definition.cohorts,
            param_configs=(),
        )

        ref_result = execute_study_plan(built)
        numba_result = execute_study_plan(
            built, options=ExecutionOptions(backend=ExecutionBackend.FAST)
        )

        _compare_results(
            ref_result.experiment_result.simulation_results,
            numba_result.experiment_result.simulation_results,
            "study_plan_numba",
        )

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
        assert report.longest_path_evaluations == report.groups
        assert report.independent_evaluations > 0
