"""Unit tests for lazy cohort-aligned plan slicing."""

from __future__ import annotations

import inspect
from datetime import date
from decimal import Decimal

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from fbf.core.execution.slicing import iter_cohort_slices
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan

_WEALTH = Money(Decimal("1000000"), Currency.EUR)
_EQUITY = AssetClass(id="equity", name="Equity", description="")
_BOND = AssetClass(id="bond", name="Bond", description="")


def _make_dataset(months: int = 12) -> Dataset:
    snapshots = []
    current = date(2000, 1, 1)
    for _ in range(months):
        snapshots.append(
            MarketSnapshot(
                date=current,
                index_levels={_EQUITY: Decimal("100"), _BOND: Decimal("100")},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            )
        )
        month = current.month
        current = date(current.year + month // 12, month % 12 + 1, 1)
    return Dataset(snapshots=tuple(snapshots), frequency="monthly")


def _make_portfolio() -> Portfolio:
    return Portfolio(
        holdings=(
            AssetHolding(asset_class=_EQUITY, units=Decimal("10")),
            AssetHolding(asset_class=_BOND, units=Decimal("10")),
        )
    )


def _make_unit(
    dataset: Dataset,
    start_date: date,
    index: int,
    portfolio: Portfolio,
) -> PlannedSimulationUnit:
    return PlannedSimulationUnit(
        cohort=CohortSpecification(start_date=start_date),
        parameter_config=ParameterConfiguration(values={"index": index}),
        allocation_policy=ConstantAllocationPolicy(Decimal("0.5")),
        withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.04")),
        initial_portfolio=portfolio,
        dataset=dataset,
    )


def _make_plan(groups: tuple[tuple[date, int], ...]) -> ResearchPlan:
    dataset = _make_dataset()
    portfolio = _make_portfolio()
    cohort_dates = tuple(dict.fromkeys(d for d, _ in groups))
    cohort_specs = tuple(CohortSpecification(start_date=d) for d in cohort_dates)
    units: list[PlannedSimulationUnit] = []
    index = 0
    for start_date, count in groups:
        for _ in range(count):
            units.append(_make_unit(dataset, start_date, index, portfolio))
            index += 1
    experiment = ExperimentDefinition(
        name="slicing-test",
        description="slicing test",
        dataset=dataset,
        horizon_months=12,
        initial_wealth=_WEALTH,
        cohorts=cohort_specs,
        allocation_policies=(ConstantAllocationPolicy(Decimal("0.5")),),
        withdrawal_policies=(FixedRealWithdrawalPolicy(Decimal("0.04")),),
    )
    return ResearchPlan(experiment_definition=experiment, units=tuple(units))


def _starts(units: tuple[PlannedSimulationUnit, ...]) -> tuple[date, ...]:
    return tuple(unit.cohort.start_date for unit in units)


class TestIterCohortSlices:
    def test_is_lazy_generator(self) -> None:
        plan = _make_plan(((date(2000, 1, 1), 2),))
        slices = iter_cohort_slices(plan, max_units_per_slice=1)
        assert inspect.isgenerator(slices)

    def test_preserves_order_and_covers_units_exactly_once(self) -> None:
        plan = _make_plan(
            (
                (date(2000, 1, 1), 3),
                (date(2001, 1, 1), 4),
                (date(2002, 1, 1), 2),
            )
        )
        slices = list(iter_cohort_slices(plan, max_units_per_slice=4))
        flattened = tuple(unit for chunk in slices for unit in chunk)
        assert flattened == plan.units
        assert len(flattened) == len(plan.units)

    def test_starts_new_slice_only_at_cohort_boundary(self) -> None:
        plan = _make_plan(
            (
                (date(2000, 1, 1), 3),
                (date(2001, 1, 1), 3),
                (date(2002, 1, 1), 3),
            )
        )
        slices = list(iter_cohort_slices(plan, max_units_per_slice=4))
        assert tuple(_starts(chunk) for chunk in slices) == (
            (
                date(2000, 1, 1),
                date(2000, 1, 1),
                date(2000, 1, 1),
                date(2001, 1, 1),
                date(2001, 1, 1),
                date(2001, 1, 1),
            ),
            (date(2002, 1, 1), date(2002, 1, 1), date(2002, 1, 1)),
        )

    def test_oversized_cohort_is_never_split(self) -> None:
        plan = _make_plan(
            (
                (date(2000, 1, 1), 10),
                (date(2001, 1, 1), 2),
            )
        )
        slices = list(iter_cohort_slices(plan, max_units_per_slice=4))
        assert _starts(slices[0]) == (date(2000, 1, 1),) * 10
        assert slices[1] == plan.units[10:]

    def test_limit_is_a_target_not_an_absolute_bound(self) -> None:
        plan = _make_plan(
            (
                (date(2000, 1, 1), 3),
                (date(2001, 1, 1), 3),
            )
        )
        slices = list(iter_cohort_slices(plan, max_units_per_slice=4))
        assert len(slices) == 1
        assert len(slices[0]) == 6

    def test_non_contiguous_cohorts_keep_original_order(self) -> None:
        plan = _make_plan(
            (
                (date(2000, 1, 1), 1),
                (date(2001, 1, 1), 1),
                (date(2000, 1, 1), 1),
            )
        )
        slices = list(iter_cohort_slices(plan, max_units_per_slice=1))
        assert tuple(_starts(chunk) for chunk in slices) == (
            (date(2000, 1, 1),),
            (date(2001, 1, 1),),
            (date(2000, 1, 1),),
        )

    def test_single_cohort_larger_than_limit_yields_one_slice(self) -> None:
        plan = _make_plan(((date(2000, 1, 1), 25),))
        slices = list(iter_cohort_slices(plan, max_units_per_slice=5))
        assert slices == [plan.units]

    def test_rejects_non_positive_limit(self) -> None:
        plan = _make_plan(((date(2000, 1, 1), 1),))
        for limit in (0, -1):
            with pytest.raises(ValueError, match="max_units_per_slice"):
                list(iter_cohort_slices(plan, max_units_per_slice=limit))
