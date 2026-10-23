"""Unit tests for execution-plan reporting helpers."""

from __future__ import annotations

import ast
from datetime import date
from decimal import Decimal
from pathlib import Path

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import Portfolio
from fbf.core.domain.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from fbf.core.execution import reporting
from fbf.core.execution.strategies.fast_path import (
    reference_month_work as fast_path_reference_month_work,
)
from fbf.core.execution.strategies.reference import (
    ReferenceReport,
    expected_reference_report as reference_expected_reference_report,
)
from fbf.core.study.builder import build_initial_portfolio
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import (
    PlannedSimulationUnit,
    ResearchPlan,
    materialize_research_plan,
)

_WEALTH = Money(Decimal("1000000"), Currency.EUR)
_START = date(2000, 1, 1)
_EQUITY = AssetClass(id="equity", name="", description="")
_BOND = AssetClass(id="bond", name="", description="")


def _month_after(start: date, offset: int) -> date:
    month = start.month - 1 + offset
    return date(start.year + month // 12, month % 12 + 1, 1)


def _make_dataset(months: int) -> Dataset:
    return Dataset(
        snapshots=tuple(
            MarketSnapshot(
                date=_month_after(_START, offset),
                index_levels={_EQUITY: Decimal("100"), _BOND: Decimal("100")},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            )
            for offset in range(months)
        ),
        frequency="monthly",
    )


def _make_plan(horizons: tuple[int, ...]) -> ResearchPlan:
    dataset = _make_dataset(max(horizons))
    cohort = CohortSpecification(start_date=_START)
    allocation = ConstantAllocationPolicy(Decimal("0.5"))
    withdrawal = FixedRealWithdrawalPolicy(Decimal("0.04"))
    experiment = ExperimentDefinition(
        name="reporting",
        description="reporting test",
        dataset=dataset,
        horizon_months=max(horizons),
        initial_wealth=_WEALTH,
        cohorts=(cohort,),
        allocation_policies=(allocation,),
        withdrawal_policies=(withdrawal,),
    )
    configs = tuple(
        ParameterConfiguration(values={"horizon_months": horizon})
        for horizon in horizons
    )
    return materialize_research_plan(
        experiment_def=experiment,
        canonical_trajectory=dataset,
        cohorts=(cohort,),
        param_configs=configs,
        initial_portfolio=build_initial_portfolio(_WEALTH, dataset),
        horizon_resolver=lambda config: int(config.get("horizon_months")),
        policy_resolver=lambda _config: (allocation, withdrawal),
    )


def _make_unit(
    dataset: Dataset,
    horizon_months: int | None,
    allocation: ConstantAllocationPolicy,
    withdrawal: FixedRealWithdrawalPolicy,
    portfolio: Portfolio,
) -> PlannedSimulationUnit:
    return PlannedSimulationUnit(
        cohort=CohortSpecification(start_date=_START),
        parameter_config=ParameterConfiguration(
            values={"horizon_months": horizon_months if horizon_months is not None else 0}
        ),
        allocation_policy=allocation,
        withdrawal_policy=withdrawal,
        initial_portfolio=portfolio,
        dataset=dataset,
        horizon_months=horizon_months,
    )


class TestExpectedReferenceReport:
    def test_prefix_consistent_horizons_are_derived(self) -> None:
        plan = _make_plan((24, 36))

        report = reporting.expected_reference_report(plan)

        assert report == ReferenceReport(
            logical_units=2,
            groups=1,
            longest_path_evaluations=1,
            derived_results=1,
            independent_evaluations=0,
            month_work=36,
        )

    def test_non_prefix_dataset_is_counted_independently(self) -> None:
        long_dataset = _make_dataset(36)
        short_dataset = _make_dataset(24)
        allocation = ConstantAllocationPolicy(Decimal("0.5"))
        withdrawal = FixedRealWithdrawalPolicy(Decimal("0.04"))
        portfolio = build_initial_portfolio(_WEALTH, long_dataset)
        experiment = ExperimentDefinition(
            name="reporting",
            description="reporting test",
            dataset=long_dataset,
            horizon_months=36,
            initial_wealth=_WEALTH,
            cohorts=(CohortSpecification(start_date=_START),),
            allocation_policies=(allocation,),
            withdrawal_policies=(withdrawal,),
        )
        plan = ResearchPlan(
            experiment_definition=experiment,
            units=(
                _make_unit(long_dataset, 36, allocation, withdrawal, portfolio),
                _make_unit(short_dataset, 24, allocation, withdrawal, portfolio),
            ),
        )

        report = reporting.expected_reference_report(plan)

        assert report == ReferenceReport(
            logical_units=2,
            groups=1,
            longest_path_evaluations=1,
            derived_results=0,
            independent_evaluations=1,
            month_work=60,
        )

    def test_none_horizon_uses_experiment_default(self) -> None:
        dataset = _make_dataset(48)
        allocation = ConstantAllocationPolicy(Decimal("0.5"))
        withdrawal = FixedRealWithdrawalPolicy(Decimal("0.04"))
        experiment = ExperimentDefinition(
            name="reporting",
            description="reporting test",
            dataset=dataset,
            horizon_months=48,
            initial_wealth=_WEALTH,
            cohorts=(CohortSpecification(start_date=_START),),
            allocation_policies=(allocation,),
            withdrawal_policies=(withdrawal,),
        )
        plan = ResearchPlan(
            experiment_definition=experiment,
            units=(
                _make_unit(
                    dataset,
                    None,
                    allocation,
                    withdrawal,
                    build_initial_portfolio(_WEALTH, dataset),
                ),
            ),
        )

        report = reporting.expected_reference_report(plan)

        assert report.month_work == 48
        assert reporting.reference_month_work(plan) == 48


class TestReportCompatibility:
    def test_public_facade_no_longer_exports_report_helpers(self) -> None:
        import fbf.core.execution as execution

        assert "expected_reference_report" not in execution.__all__
        assert "reference_month_work" not in execution.__all__
        assert not hasattr(execution, "expected_reference_report")
        assert not hasattr(execution, "reference_month_work")

    def test_reporting_module_remains_the_implementation(self) -> None:
        plan = _make_plan((24, 36))

        assert reporting.expected_reference_report(plan).month_work == 36
        assert reporting.reference_month_work(plan) == 60

    def test_legacy_module_aliases_preserve_object_identity(self) -> None:
        assert ReferenceReport is reporting.ReferenceReport
        assert reference_expected_reference_report is reporting.expected_reference_report
        assert fast_path_reference_month_work is reporting.reference_month_work

    def test_reporting_module_has_no_executor_imports(self) -> None:
        assert reporting.__file__ is not None
        tree = ast.parse(Path(reporting.__file__).read_text(encoding="utf-8"))
        modules: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                modules.append(node.module)
            elif isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)

        assert not any(
            module.startswith("fbf.core.execution.strategies")
            or module.startswith("fbf.core.execution.pipeline")
            for module in modules
        )
