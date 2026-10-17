"""Dispatch-contract tests for Part 52 workloads.

These verify the routing contract at the ``execute_study_plan`` boundary:

- FAST (explicit Numba backend) must reject any plan it cannot execute on
  Numba, including schedule-less Part 52 configurations with no rate source
  and mixed plans, instead of silently routing them to the Decimal engine.
- AUTO preserves graceful routing: a schedule-less fixed-rate Part 52 plan is
  executed on the Part 52 Numba executor.
- The context horizon used for eligibility mirrors the real execution horizon
  (per-unit horizon, falling back to the experiment horizon when absent).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import EllipsisType

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies import ConstantAllocationPolicy
from fbf.core.domain.policies.concrete import ConstantWithdrawalPolicy
from fbf.core.domain.policies.part52_withdrawal import Part52WithdrawalPolicy
from fbf.core.execution import (
    ExecutionBackend,
    ExecutionOptions,
    NoOpProfiler,
    UnsupportedConfigurationError,
    _auto_select_backend,
    _extract_simulation_contexts,
    execute_study_plan,
)
from fbf.core.execution.strategies.part52_numba_executor import Part52NumbaExecutor
from fbf.core.study.builder import BuiltStudy
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan

EQUITY = AssetClass(id="equity", name="", description="")
BOND = AssetClass(id="bond", name="", description="")

INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)
WITHDRAWAL_RATE = Decimal("0.0391")
BORROW_PCT = Decimal("0.4108")
DRAWDOWN_THRESHOLD = Decimal("0.20")
INTEREST_RATE = Decimal("0.015")
LTV_LIMIT = Decimal("0.50")

_Schedule = tuple[Decimal, ...] | None | EllipsisType


def _make_dataset(months: int) -> Dataset:
    snapshots = []
    current = date(1965, 11, 1)
    for _ in range(months + 1):
        snapshots.append(
            MarketSnapshot(
                date=current,
                index_levels={EQUITY: Decimal("100"), BOND: Decimal("100")},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            )
        )
        current = date(current.year + (current.month // 12), current.month % 12 + 1, 1)
    return Dataset(snapshots=tuple(snapshots), frequency="monthly")


def _part52_unit(
    cohort_date: date,
    horizon_months: int | None,
    dataset: Dataset,
    *,
    schedule: _Schedule = ...,
    rate: Decimal | None = INTEREST_RATE,
) -> PlannedSimulationUnit:
    if schedule is ...:
        schedule = (
            tuple(INTEREST_RATE for _ in range(horizon_months))
            if horizon_months
            else None
        )
    return PlannedSimulationUnit(
        cohort=CohortSpecification(start_date=cohort_date),
        parameter_config=ParameterConfiguration(values={"withdrawal_rate": 0.0391}),
        allocation_policy=ConstantAllocationPolicy(Decimal("0.75")),
        withdrawal_policy=Part52WithdrawalPolicy(
            withdrawal_rate=WITHDRAWAL_RATE,
            borrow_pct=BORROW_PCT,
            drawdown_threshold=DRAWDOWN_THRESHOLD,
        ),
        initial_portfolio=Portfolio(
            holdings=(
                AssetHolding(asset_class=EQUITY, units=Decimal("7500")),
                AssetHolding(asset_class=BOND, units=Decimal("2500")),
            )
        ),
        dataset=dataset,
        horizon_months=horizon_months,
        interest_rate=rate,
        interest_rate_schedule=schedule,
        ltv_limit=LTV_LIMIT,
        ltv_enforcement=False,
        expense_ratio=None,
    )


def _non_part52_unit(cohort_date: date, dataset: Dataset) -> PlannedSimulationUnit:
    return PlannedSimulationUnit(
        cohort=CohortSpecification(start_date=cohort_date),
        parameter_config=ParameterConfiguration(values={"withdrawal_rate": 0.04}),
        allocation_policy=ConstantAllocationPolicy(Decimal("0.60")),
        withdrawal_policy=ConstantWithdrawalPolicy(Decimal("0.04")),
        initial_portfolio=Portfolio(
            holdings=(AssetHolding(asset_class=EQUITY, units=Decimal("10000")),)
        ),
        dataset=dataset,
        horizon_months=12,
    )


def _built_plan(
    units: tuple[PlannedSimulationUnit, ...],
    horizon_months: int = 12,
) -> BuiltStudy:
    experiment = ExperimentDefinition(
        name="Part52 dispatch contract",
        description="Part 52 dispatch contract",
        dataset=units[0].dataset,
        horizon_months=horizon_months,
        initial_wealth=INITIAL_WEALTH,
        cohorts=tuple(unit.cohort for unit in units),
        allocation_policies=tuple(unit.allocation_policy for unit in units),
        withdrawal_policies=tuple(unit.withdrawal_policy for unit in units),
    )
    plan = ResearchPlan(experiment_definition=experiment, units=units)
    return BuiltStudy(
        plan=plan,
        experiment_definition=experiment,
        cohorts=tuple(unit.cohort for unit in units),
        param_configs=tuple(unit.parameter_config for unit in units),
    )


class TestHorizonAgreement:
    """Eligibility horizon must equal the real execution horizon."""

    def test_missing_unit_horizon_falls_back_to_experiment_horizon(self) -> None:
        dataset = _make_dataset(12)
        unit = _part52_unit(date(1965, 11, 1), None, dataset)
        built = _built_plan((unit,), horizon_months=12)

        contexts = _extract_simulation_contexts(built.plan)
        assert contexts[0].horizon_months == 12

        # A schedule of exactly ``experiment.horizon_months`` entries must be
        # accepted, so AUTO routes this plan to the Part 52 Numba executor.
        assert isinstance(
            _auto_select_backend(built, NoOpProfiler()), Part52NumbaExecutor
        )


class TestFastStrictness:
    """Explicit FAST must never silently fall back to the Decimal engine."""

    def test_schedule_less_without_rate_raises(self) -> None:
        dataset = _make_dataset(12)
        unit = _part52_unit(date(1965, 11, 1), 12, dataset, schedule=None, rate=None)
        built = _built_plan((unit,))

        with pytest.raises(UnsupportedConfigurationError):
            execute_study_plan(
                built, ExecutionOptions(backend=ExecutionBackend.FAST)
            )

    def test_mixed_plan_raises(self) -> None:
        dataset = _make_dataset(12)
        units = (
            _part52_unit(date(1965, 11, 1), 12, dataset),
            _non_part52_unit(date(1966, 1, 1), dataset),
        )
        built = _built_plan(units)

        with pytest.raises(UnsupportedConfigurationError):
            execute_study_plan(
                built, ExecutionOptions(backend=ExecutionBackend.FAST)
            )

    def test_schedule_less_with_rate_runs(self) -> None:
        dataset = _make_dataset(12)
        unit = _part52_unit(date(1965, 11, 1), 12, dataset, schedule=None)
        built = _built_plan((unit,))

        fast = execute_study_plan(
            built, ExecutionOptions(backend=ExecutionBackend.FAST)
        )
        reference = execute_study_plan(
            built, ExecutionOptions(backend=ExecutionBackend.REFERENCE)
        )

        assert len(fast.experiment_result.simulation_results) == 1
        fast_wealth = fast.experiment_result.simulation_results[0].statistics.final_wealth
        ref_wealth = reference.experiment_result.simulation_results[0].statistics.final_wealth
        assert abs(fast_wealth.amount - ref_wealth.amount) < Decimal("0.01")

    def test_auto_routes_schedule_less_with_rate_to_part52(self) -> None:
        dataset = _make_dataset(12)
        unit = _part52_unit(date(1965, 11, 1), 12, dataset, schedule=None)
        built = _built_plan((unit,))

        assert isinstance(
            _auto_select_backend(built, NoOpProfiler()), Part52NumbaExecutor
        )
