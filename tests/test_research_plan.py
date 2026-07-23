"""Unit tests for ResearchPlan and PlannedSimulationUnit domain value objects.

Covers:
- PlannedSimulationUnit construction, immutability, and validation
- ResearchPlan construction, validation, uniqueness enforcement, and sequence protocol
- ResearchPlan immutability guarantees
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest

from engine.domain.model.asset import AssetClass
from engine.domain.model.money import Currency, Money
from engine.domain.model.portfolio import AssetHolding, Portfolio
from engine.domain.policies.allocation_policy import AllocationPolicy
from engine.domain.policies.withdrawal_policy import WithdrawalPolicy
from research.domain.cohort.specification import CohortSpecification
from research.domain.experiment.definition import ExperimentDefinition
from research.domain.parameter.configuration import ParameterConfiguration
from research.domain.plan import PlannedSimulationUnit, ResearchPlan

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


def make_cohort(year: int = 2000, month: int = 1, day: int = 1) -> CohortSpecification:
    return CohortSpecification(start_date=date(year, month, day))


def make_param_config(**kwargs: object) -> ParameterConfiguration:
    values = {"withdrawal_rate": 0.04, **kwargs}
    return ParameterConfiguration(values=values)


def make_portfolio() -> Portfolio:
    """Materialised initial portfolio supplied by the planning boundary (test double)."""
    asset = AssetClass(id="acwi", name="ACWI", description="Global equities")
    return Portfolio(holdings=(AssetHolding(asset_class=asset, units=Decimal("1000")),))


def make_unit(
    year: int = 2000,
    month: int = 1,
    param_override: dict | None = None,
    alloc: AllocationPolicy | None = None,
    withd: WithdrawalPolicy | None = None,
    portfolio: Portfolio | None = None,
) -> PlannedSimulationUnit:
    return PlannedSimulationUnit(
        cohort=make_cohort(year=year, month=month),
        parameter_config=make_param_config(**(param_override or {})),
        allocation_policy=alloc or StubAllocationPolicy(),
        withdrawal_policy=withd or StubWithdrawalPolicy(),
        initial_portfolio=portfolio if portfolio is not None else make_portfolio(),
    )


# ---------------------------------------------------------------------------
# PlannedSimulationUnit tests
# ---------------------------------------------------------------------------


class TestPlannedSimulationUnitConstruction:
    def test_constructs_with_all_valid_fields(self) -> None:
        cohort = make_cohort()
        config = make_param_config()
        alloc = StubAllocationPolicy()
        withd = StubWithdrawalPolicy()
        portfolio = make_portfolio()

        unit = PlannedSimulationUnit(
            cohort=cohort,
            parameter_config=config,
            allocation_policy=alloc,
            withdrawal_policy=withd,
            initial_portfolio=portfolio,
        )

        assert unit.cohort is cohort
        assert unit.parameter_config is config
        assert unit.allocation_policy is alloc
        assert unit.withdrawal_policy is withd
        assert unit.initial_portfolio is portfolio

    def test_rejects_none_cohort(self) -> None:
        with pytest.raises(ValueError, match="cohort cannot be None"):
            PlannedSimulationUnit(
                cohort=None,  # type: ignore[arg-type]
                parameter_config=make_param_config(),
                allocation_policy=StubAllocationPolicy(),
                withdrawal_policy=StubWithdrawalPolicy(),
                initial_portfolio=make_portfolio(),
            )

    def test_rejects_none_parameter_config(self) -> None:
        with pytest.raises(ValueError, match="parameter_config cannot be None"):
            PlannedSimulationUnit(
                cohort=make_cohort(),
                parameter_config=None,  # type: ignore[arg-type]
                allocation_policy=StubAllocationPolicy(),
                withdrawal_policy=StubWithdrawalPolicy(),
                initial_portfolio=make_portfolio(),
            )

    def test_rejects_none_allocation_policy(self) -> None:
        with pytest.raises(ValueError, match="allocation_policy cannot be None"):
            PlannedSimulationUnit(
                cohort=make_cohort(),
                parameter_config=make_param_config(),
                allocation_policy=None,  # type: ignore[arg-type]
                withdrawal_policy=StubWithdrawalPolicy(),
                initial_portfolio=make_portfolio(),
            )

    def test_rejects_none_withdrawal_policy(self) -> None:
        with pytest.raises(ValueError, match="withdrawal_policy cannot be None"):
            PlannedSimulationUnit(
                cohort=make_cohort(),
                parameter_config=make_param_config(),
                allocation_policy=StubAllocationPolicy(),
                withdrawal_policy=None,  # type: ignore[arg-type]
                initial_portfolio=make_portfolio(),
            )

    def test_rejects_none_initial_portfolio(self) -> None:
        with pytest.raises(ValueError, match="initial_portfolio cannot be None"):
            PlannedSimulationUnit(
                cohort=make_cohort(),
                parameter_config=make_param_config(),
                allocation_policy=StubAllocationPolicy(),
                withdrawal_policy=StubWithdrawalPolicy(),
                initial_portfolio=None,  # type: ignore[arg-type]
            )


class TestPlannedSimulationUnitImmutability:
    def test_unit_is_frozen(self) -> None:
        unit = make_unit()
        with pytest.raises(FrozenInstanceError):
            unit.cohort = make_cohort(year=1999)  # type: ignore[misc]

    def test_unit_is_frozen_on_policy_fields(self) -> None:
        unit = make_unit()
        with pytest.raises(FrozenInstanceError):
            unit.allocation_policy = StubAllocationPolicy()  # type: ignore[misc]


class TestPlannedSimulationUnitIdentity:
    def test_canonical_identity_is_cohort_start_date_and_parameter_config(self) -> None:
        """Two units sharing (start_date, parameter_config) are considered equivalent."""
        cohort = make_cohort(2000)
        config = make_param_config(withdrawal_rate=0.04)
        alloc_a = StubAllocationPolicy()
        alloc_b = StubAllocationPolicy()

        unit_a = PlannedSimulationUnit(
            cohort=cohort,
            parameter_config=config,
            allocation_policy=alloc_a,
            withdrawal_policy=StubWithdrawalPolicy(),
            initial_portfolio=make_portfolio(),
        )
        unit_b = PlannedSimulationUnit(
            cohort=cohort,
            parameter_config=config,
            allocation_policy=alloc_b,  # different policy instance
            withdrawal_policy=StubWithdrawalPolicy(),
            initial_portfolio=make_portfolio(),
        )
        # ResearchPlan uniqueness is by (start_date, parameter_config); verify key matches
        key_a = (unit_a.cohort.start_date, unit_a.parameter_config)
        key_b = (unit_b.cohort.start_date, unit_b.parameter_config)
        assert key_a == key_b


# ---------------------------------------------------------------------------
# ResearchPlan tests
# ---------------------------------------------------------------------------


class TestResearchPlanConstruction:
    def test_constructs_with_single_unit(self, minimal_experiment_def) -> None:
        unit = make_unit()
        plan = ResearchPlan(experiment_definition=minimal_experiment_def, units=(unit,))

        assert len(plan) == 1
        assert plan[0] is unit

    def test_constructs_with_multiple_distinct_units(self, minimal_experiment_def) -> None:
        units = (make_unit(year=2000), make_unit(year=2001))
        plan = ResearchPlan(experiment_definition=minimal_experiment_def, units=units)

        assert len(plan) == 2

    def test_coerces_list_of_units_to_tuple(self, minimal_experiment_def) -> None:
        units_list = [make_unit(year=2000), make_unit(year=2001)]
        plan = ResearchPlan(
            experiment_definition=minimal_experiment_def,
            units=units_list,  # type: ignore[arg-type]
        )

        assert isinstance(plan.units, tuple)
        assert len(plan) == 2


class TestResearchPlanValidation:
    def test_rejects_empty_units_tuple(self, minimal_experiment_def) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            ResearchPlan(experiment_definition=minimal_experiment_def, units=())

    def test_rejects_none_experiment_definition(self) -> None:
        with pytest.raises(ValueError, match="experiment_definition cannot be None"):
            ResearchPlan(
                experiment_definition=None,  # type: ignore[arg-type]
                units=(make_unit(),),
            )

    def test_rejects_non_planned_unit_element(self, minimal_experiment_def) -> None:
        with pytest.raises(TypeError, match="not a PlannedSimulationUnit"):
            ResearchPlan(
                experiment_definition=minimal_experiment_def,
                units=("not-a-unit",),  # type: ignore[arg-type]
            )

    def test_rejects_duplicate_identity_same_cohort_same_config(
        self, minimal_experiment_def
    ) -> None:
        cohort = make_cohort(2000)
        config = make_param_config()
        unit_a = PlannedSimulationUnit(
            cohort=cohort,
            parameter_config=config,
            allocation_policy=StubAllocationPolicy(),
            withdrawal_policy=StubWithdrawalPolicy(),
            initial_portfolio=make_portfolio(),
        )
        unit_b = PlannedSimulationUnit(
            cohort=cohort,
            parameter_config=config,
            allocation_policy=StubAllocationPolicy(),
            withdrawal_policy=StubWithdrawalPolicy(),
            initial_portfolio=make_portfolio(),
        )

        with pytest.raises(ValueError, match="Duplicate"):
            ResearchPlan(
                experiment_definition=minimal_experiment_def,
                units=(unit_a, unit_b),
            )

    def test_allows_same_cohort_with_different_config(self, minimal_experiment_def) -> None:
        cohort = make_cohort(2000)
        config_a = make_param_config(withdrawal_rate=0.03)
        config_b = make_param_config(withdrawal_rate=0.05)
        unit_a = PlannedSimulationUnit(
            cohort=cohort,
            parameter_config=config_a,
            allocation_policy=StubAllocationPolicy(),
            withdrawal_policy=StubWithdrawalPolicy(),
            initial_portfolio=make_portfolio(),
        )
        unit_b = PlannedSimulationUnit(
            cohort=cohort,
            parameter_config=config_b,
            allocation_policy=StubAllocationPolicy(),
            withdrawal_policy=StubWithdrawalPolicy(),
            initial_portfolio=make_portfolio(),
        )

        plan = ResearchPlan(
            experiment_definition=minimal_experiment_def,
            units=(unit_a, unit_b),
        )
        assert len(plan) == 2

    def test_allows_same_config_with_different_cohort(self, minimal_experiment_def) -> None:
        unit_a = make_unit(year=2000, param_override={"withdrawal_rate": 0.04})
        unit_b = make_unit(year=2001, param_override={"withdrawal_rate": 0.04})

        plan = ResearchPlan(
            experiment_definition=minimal_experiment_def,
            units=(unit_a, unit_b),
        )
        assert len(plan) == 2


class TestResearchPlanImmutability:
    def test_plan_is_frozen(self, minimal_experiment_def) -> None:
        plan = ResearchPlan(
            experiment_definition=minimal_experiment_def,
            units=(make_unit(),),
        )

        with pytest.raises(FrozenInstanceError):
            plan.units = ()  # type: ignore[misc]

    def test_plan_experiment_definition_is_frozen(self, minimal_experiment_def) -> None:
        plan = ResearchPlan(
            experiment_definition=minimal_experiment_def,
            units=(make_unit(),),
        )

        with pytest.raises(FrozenInstanceError):
            plan.experiment_definition = minimal_experiment_def  # type: ignore[misc]


class TestResearchPlanSequenceProtocol:
    def test_len_returns_unit_count(self, minimal_experiment_def) -> None:
        units = (make_unit(year=2000), make_unit(year=2001), make_unit(year=2002))
        plan = ResearchPlan(experiment_definition=minimal_experiment_def, units=units)

        assert len(plan) == 3

    def test_getitem_returns_correct_unit_by_index(self, minimal_experiment_def) -> None:
        unit_a = make_unit(year=2000)
        unit_b = make_unit(year=2001)
        plan = ResearchPlan(experiment_definition=minimal_experiment_def, units=(unit_a, unit_b))

        assert plan[0] is unit_a
        assert plan[1] is unit_b

    def test_iter_yields_units_in_order(self, minimal_experiment_def) -> None:
        unit_a = make_unit(year=2000)
        unit_b = make_unit(year=2001)
        unit_c = make_unit(year=2002)
        plan = ResearchPlan(
            experiment_definition=minimal_experiment_def,
            units=(unit_a, unit_b, unit_c),
        )

        iterated = list(plan)
        assert iterated == [unit_a, unit_b, unit_c]

    def test_order_is_preserved_exactly(self, minimal_experiment_def) -> None:
        units = tuple(make_unit(year=y) for y in range(2000, 2010))
        plan = ResearchPlan(experiment_definition=minimal_experiment_def, units=units)

        for i, unit in enumerate(plan):
            assert unit is units[i]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_experiment_def() -> ExperimentDefinition:
    from engine.domain.model.asset import AssetClass
    from engine.domain.model.dataset import Dataset
    from engine.domain.model.market_snapshot import MarketSnapshot

    asset = AssetClass(id="acwi", name="ACWI", description="Global equities")
    snapshot = MarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={asset: Decimal("100.00")},
        inflation=Decimal("0.00"),
        inflation_cumulative=Decimal("0.00"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100.00"),
    )
    dataset = Dataset(snapshots=[snapshot], frequency="monthly", version="1.0")

    return ExperimentDefinition(
        name="test-experiment",
        description="A minimal test experiment definition",
        dataset=dataset,
        horizon_months=12,
        initial_wealth=Money(Decimal("100000"), Currency.EUR),
        cohorts=(
            CohortSpecification(start_date=date(2000, 1, 1)),
            CohortSpecification(start_date=date(2001, 1, 1)),
        ),
        allocation_policies=(StubAllocationPolicy(),),
        withdrawal_policies=(StubWithdrawalPolicy(),),
    )
