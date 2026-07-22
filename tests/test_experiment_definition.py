"""Unit tests for ExperimentDefinition domain value object."""

from datetime import date
from decimal import Decimal
import pytest
from dataclasses import FrozenInstanceError

from engine.domain import AssetClass, Dataset, MarketSnapshot, Money
from engine.domain.model.money import Currency
from engine.domain.policies import AllocationPolicy, WithdrawalPolicy
from research import CohortSpecification, ExperimentDefinition


class MockAllocationPolicy(AllocationPolicy):

    def decide(self, context: object) -> object:
        return None


class MockWithdrawalPolicy(WithdrawalPolicy):

    def decide(self, context: object) -> object:
        return None


@pytest.fixture
def dummy_dataset() -> Dataset:
    asset = AssetClass(id="acwi", name="ACWI", description="Global equities")
    snapshot = MarketSnapshot(
        date=date(1871, 1, 1),
        index_levels={asset: Decimal("100.00")},
        inflation=Decimal("0.00"),
        inflation_cumulative=Decimal("0.00"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100.00"),
    )
    return Dataset(snapshots=[snapshot], frequency="monthly", version="1.0")


@pytest.fixture
def dummy_cohorts() -> tuple[CohortSpecification, ...]:
    return (
        CohortSpecification(start_date=date(1871, 1, 1)),
        CohortSpecification(start_date=date(1871, 2, 1)),
    )


@pytest.fixture
def dummy_allocations() -> tuple[MockAllocationPolicy, ...]:
    return (MockAllocationPolicy(),)


@pytest.fixture
def dummy_withdrawals() -> tuple[MockWithdrawalPolicy, ...]:
    return (MockWithdrawalPolicy(),)


def test_experiment_definition_valid_creation(
    dummy_dataset: Dataset,
    dummy_cohorts: tuple[CohortSpecification, ...],
    dummy_allocations: tuple[MockAllocationPolicy, ...],
    dummy_withdrawals: tuple[MockWithdrawalPolicy, ...],
) -> None:
    exp = ExperimentDefinition(
        name="ERN Part 19 Study",
        description="Equity Glidepath Evaluation",
        dataset=dummy_dataset,
        horizon_months=360,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        cohorts=dummy_cohorts,
        allocation_policies=dummy_allocations,
        withdrawal_policies=dummy_withdrawals,
    )

    assert exp.name == "ERN Part 19 Study"
    assert exp.description == "Equity Glidepath Evaluation"
    assert exp.dataset == dummy_dataset
    assert exp.horizon_months == 360
    assert exp.initial_wealth == Money(Decimal("1000000"), Currency.EUR)
    assert isinstance(exp.cohorts, tuple)
    assert len(exp.cohorts) == 2
    assert isinstance(exp.allocation_policies, tuple)
    assert len(exp.allocation_policies) == 1
    assert isinstance(exp.withdrawal_policies, tuple)
    assert len(exp.withdrawal_policies) == 1


def test_experiment_definition_defensive_tuple_coercion(
    dummy_dataset: Dataset,
    dummy_cohorts: tuple[CohortSpecification, ...],
    dummy_allocations: tuple[MockAllocationPolicy, ...],
    dummy_withdrawals: tuple[MockWithdrawalPolicy, ...],
) -> None:
    # Pass mutable lists
    cohorts_list = list(dummy_cohorts)
    alloc_list = list(dummy_allocations)
    withd_list = list(dummy_withdrawals)

    exp = ExperimentDefinition(
        name="ERN Part 19 Study",
        description="Equity Glidepath Evaluation",
        dataset=dummy_dataset,
        horizon_months=360,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        cohorts=cohorts_list,  # type: ignore[arg-type]
        allocation_policies=alloc_list,  # type: ignore[arg-type]
        withdrawal_policies=withd_list,  # type: ignore[arg-type]
    )

    assert isinstance(exp.cohorts, tuple)
    assert isinstance(exp.allocation_policies, tuple)
    assert isinstance(exp.withdrawal_policies, tuple)


def test_experiment_definition_immutability(
    dummy_dataset: Dataset,
    dummy_cohorts: tuple[CohortSpecification, ...],
    dummy_allocations: tuple[MockAllocationPolicy, ...],
    dummy_withdrawals: tuple[MockWithdrawalPolicy, ...],
) -> None:
    exp = ExperimentDefinition(
        name="ERN Study",
        description="Description",
        dataset=dummy_dataset,
        horizon_months=360,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        cohorts=dummy_cohorts,
        allocation_policies=dummy_allocations,
        withdrawal_policies=dummy_withdrawals,
    )

    with pytest.raises(FrozenInstanceError):
        exp.name = "Modified Name"  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        exp.horizon_months = 480  # type: ignore[misc]


def test_experiment_definition_validation_empty_name(
    dummy_dataset: Dataset,
    dummy_cohorts: tuple[CohortSpecification, ...],
    dummy_allocations: tuple[MockAllocationPolicy, ...],
    dummy_withdrawals: tuple[MockWithdrawalPolicy, ...],
) -> None:
    with pytest.raises(ValueError, match="name cannot be empty"):
        ExperimentDefinition(
            name="   ",
            description="Description",
            dataset=dummy_dataset,
            horizon_months=360,
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            cohorts=dummy_cohorts,
            allocation_policies=dummy_allocations,
            withdrawal_policies=dummy_withdrawals,
        )


def test_experiment_definition_validation_empty_description(
    dummy_dataset: Dataset,
    dummy_cohorts: tuple[CohortSpecification, ...],
    dummy_allocations: tuple[MockAllocationPolicy, ...],
    dummy_withdrawals: tuple[MockWithdrawalPolicy, ...],
) -> None:
    with pytest.raises(ValueError, match="description cannot be empty"):
        ExperimentDefinition(
            name="Study",
            description="",
            dataset=dummy_dataset,
            horizon_months=360,
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            cohorts=dummy_cohorts,
            allocation_policies=dummy_allocations,
            withdrawal_policies=dummy_withdrawals,
        )


def test_experiment_definition_validation_null_dataset(
    dummy_cohorts: tuple[CohortSpecification, ...],
    dummy_allocations: tuple[MockAllocationPolicy, ...],
    dummy_withdrawals: tuple[MockWithdrawalPolicy, ...],
) -> None:
    with pytest.raises(ValueError, match="dataset cannot be None"):
        ExperimentDefinition(
            name="Study",
            description="Description",
            dataset=None,  # type: ignore[arg-type]
            horizon_months=360,
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            cohorts=dummy_cohorts,
            allocation_policies=dummy_allocations,
            withdrawal_policies=dummy_withdrawals,
        )


def test_experiment_definition_validation_invalid_horizon(
    dummy_dataset: Dataset,
    dummy_cohorts: tuple[CohortSpecification, ...],
    dummy_allocations: tuple[MockAllocationPolicy, ...],
    dummy_withdrawals: tuple[MockWithdrawalPolicy, ...],
) -> None:
    with pytest.raises(ValueError, match="horizon_months must be positive"):
        ExperimentDefinition(
            name="Study",
            description="Description",
            dataset=dummy_dataset,
            horizon_months=0,
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            cohorts=dummy_cohorts,
            allocation_policies=dummy_allocations,
            withdrawal_policies=dummy_withdrawals,
        )


def test_experiment_definition_validation_invalid_initial_wealth(
    dummy_dataset: Dataset,
    dummy_cohorts: tuple[CohortSpecification, ...],
    dummy_allocations: tuple[MockAllocationPolicy, ...],
    dummy_withdrawals: tuple[MockWithdrawalPolicy, ...],
) -> None:
    with pytest.raises(ValueError, match="initial_wealth must be positive"):
        ExperimentDefinition(
            name="Study",
            description="Description",
            dataset=dummy_dataset,
            horizon_months=360,
            initial_wealth=Money(Decimal("0"), Currency.EUR),
            cohorts=dummy_cohorts,
            allocation_policies=dummy_allocations,
            withdrawal_policies=dummy_withdrawals,
        )


def test_experiment_definition_validation_empty_cohorts(
    dummy_dataset: Dataset,
    dummy_allocations: tuple[MockAllocationPolicy, ...],
    dummy_withdrawals: tuple[MockWithdrawalPolicy, ...],
) -> None:
    with pytest.raises(ValueError, match="cohorts cannot be empty"):
        ExperimentDefinition(
            name="Study",
            description="Description",
            dataset=dummy_dataset,
            horizon_months=360,
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            cohorts=(),
            allocation_policies=dummy_allocations,
            withdrawal_policies=dummy_withdrawals,
        )


def test_experiment_definition_validation_invalid_cohort_element(
    dummy_dataset: Dataset,
    dummy_allocations: tuple[MockAllocationPolicy, ...],
    dummy_withdrawals: tuple[MockWithdrawalPolicy, ...],
) -> None:
    with pytest.raises(ValueError, match="cohorts contain invalid elements"):
        ExperimentDefinition(
            name="Study",
            description="Description",
            dataset=dummy_dataset,
            horizon_months=360,
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            cohorts=("1871-01-01",),  # type: ignore[arg-type]
            allocation_policies=dummy_allocations,
            withdrawal_policies=dummy_withdrawals,
        )


def test_experiment_definition_validation_duplicate_cohort_dates(
    dummy_dataset: Dataset,
    dummy_allocations: tuple[MockAllocationPolicy, ...],
    dummy_withdrawals: tuple[MockWithdrawalPolicy, ...],
) -> None:
    # Same canonical start_date, different external IDs
    c1 = CohortSpecification(start_date=date(1871, 1, 1), id="COHORT_1")
    c2 = CohortSpecification(start_date=date(1871, 1, 1), id="COHORT_2")

    with pytest.raises(ValueError, match="cohorts contain duplicate start dates"):
        ExperimentDefinition(
            name="Study",
            description="Description",
            dataset=dummy_dataset,
            horizon_months=360,
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            cohorts=(c1, c2),
            allocation_policies=dummy_allocations,
            withdrawal_policies=dummy_withdrawals,
        )


def test_experiment_definition_validation_empty_policies(
    dummy_dataset: Dataset,
    dummy_cohorts: tuple[CohortSpecification, ...],
    dummy_allocations: tuple[MockAllocationPolicy, ...],
    dummy_withdrawals: tuple[MockWithdrawalPolicy, ...],
) -> None:
    with pytest.raises(ValueError, match="allocation_policies cannot be empty"):
        ExperimentDefinition(
            name="Study",
            description="Description",
            dataset=dummy_dataset,
            horizon_months=360,
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            cohorts=dummy_cohorts,
            allocation_policies=(),
            withdrawal_policies=dummy_withdrawals,
        )

    with pytest.raises(ValueError, match="withdrawal_policies cannot be empty"):
        ExperimentDefinition(
            name="Study",
            description="Description",
            dataset=dummy_dataset,
            horizon_months=360,
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            cohorts=dummy_cohorts,
            allocation_policies=dummy_allocations,
            withdrawal_policies=(),
        )


def test_experiment_definition_structural_equality_and_hashing(
    dummy_dataset: Dataset,
    dummy_cohorts: tuple[CohortSpecification, ...],
    dummy_allocations: tuple[MockAllocationPolicy, ...],
    dummy_withdrawals: tuple[MockWithdrawalPolicy, ...],
) -> None:
    exp1 = ExperimentDefinition(
        name="Study A",
        description="Description A",
        dataset=dummy_dataset,
        horizon_months=360,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        cohorts=dummy_cohorts,
        allocation_policies=dummy_allocations,
        withdrawal_policies=dummy_withdrawals,
    )

    exp2 = ExperimentDefinition(
        name="Study A",
        description="Description A",
        dataset=dummy_dataset,
        horizon_months=360,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        cohorts=dummy_cohorts,
        allocation_policies=dummy_allocations,
        withdrawal_policies=dummy_withdrawals,
    )

    exp3 = ExperimentDefinition(
        name="Study B",
        description="Description B",
        dataset=dummy_dataset,
        horizon_months=360,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        cohorts=dummy_cohorts,
        allocation_policies=dummy_allocations,
        withdrawal_policies=dummy_withdrawals,
    )

    assert exp1 == exp2
    assert exp1 != exp3
    assert hash(exp1) == hash(exp2)
    assert hash(exp1) != hash(exp3)


def test_experiment_definition_exclusions(
    dummy_dataset: Dataset,
    dummy_cohorts: tuple[CohortSpecification, ...],
    dummy_allocations: tuple[MockAllocationPolicy, ...],
    dummy_withdrawals: tuple[MockWithdrawalPolicy, ...],
) -> None:
    exp = ExperimentDefinition(
        name="Study",
        description="Description",
        dataset=dummy_dataset,
        horizon_months=360,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        cohorts=dummy_cohorts,
        allocation_policies=dummy_allocations,
        withdrawal_policies=dummy_withdrawals,
    )

    # Exclusions check: targets, total_simulations, is_single_simulation do NOT exist
    assert not hasattr(exp, "targets")
    assert not hasattr(exp, "total_simulations")
    assert not hasattr(exp, "is_single_simulation")
