"""ExperimentDefinition domain model for the Research package."""

from __future__ import annotations

from dataclasses import dataclass

from engine.domain import AllocationPolicy, Dataset, Money, WithdrawalPolicy
from research.domain.cohort.specification import CohortSpecification


@dataclass(frozen=True)
class ExperimentDefinition:
    """Immutable declarative specification of a quantitative research study.

    Serves as the public contract of the Research Layer.
    """

    name: str
    description: str
    dataset: Dataset
    horizon_months: int
    initial_wealth: Money
    cohorts: tuple[CohortSpecification, ...]
    allocation_policies: tuple[AllocationPolicy, ...]
    withdrawal_policies: tuple[WithdrawalPolicy, ...]

    def __post_init__(self) -> None:
        """Coerces sequence inputs to immutable tuples and validates local intrinsic invariants."""
        # 1. Name validation
        if self.name is None or not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("ExperimentDefinition name cannot be empty or whitespace.")

        # 2. Description validation
        if (
            self.description is None
            or not isinstance(self.description, str)
            or not self.description.strip()
        ):
            raise ValueError("ExperimentDefinition description cannot be empty or whitespace.")

        # 3. Dataset validation
        if self.dataset is None or not isinstance(self.dataset, Dataset):
            raise ValueError("ExperimentDefinition dataset cannot be None.")

        # 4. Horizon validation
        if (
            self.horizon_months is None
            or not isinstance(self.horizon_months, int)
            or isinstance(self.horizon_months, bool)
            or self.horizon_months <= 0
        ):
            raise ValueError("ExperimentDefinition horizon_months must be positive (> 0).")

        # 5. Initial wealth validation
        if (
            self.initial_wealth is None
            or not isinstance(self.initial_wealth, Money)
            or self.initial_wealth.amount <= 0
        ):
            raise ValueError("ExperimentDefinition initial_wealth must be positive (> 0).")

        # 6. Cohorts validation & defensive coercion (uniqueness based on canonical start_date)
        if self.cohorts is None:
            raise ValueError("ExperimentDefinition cohorts cannot be empty.")
        cohorts_tuple = tuple(self.cohorts)
        if len(cohorts_tuple) == 0:
            raise ValueError("ExperimentDefinition cohorts cannot be empty.")

        for c in cohorts_tuple:
            if not isinstance(c, CohortSpecification):
                raise ValueError("ExperimentDefinition cohorts contain invalid elements.")

        cohort_dates = [c.start_date for c in cohorts_tuple]
        if len(set(cohort_dates)) != len(cohorts_tuple):
            raise ValueError("ExperimentDefinition cohorts contain duplicate start dates.")

        object.__setattr__(self, "cohorts", cohorts_tuple)

        # 7. Allocation policies validation & defensive coercion
        if self.allocation_policies is None:
            raise ValueError("ExperimentDefinition allocation_policies cannot be empty.")
        alloc_tuple = tuple(self.allocation_policies)
        if len(alloc_tuple) == 0:
            raise ValueError("ExperimentDefinition allocation_policies cannot be empty.")

        for ap in alloc_tuple:
            if ap is None or not isinstance(ap, AllocationPolicy):
                raise ValueError(
                    "ExperimentDefinition allocation_policies contain invalid elements."
                )

        object.__setattr__(self, "allocation_policies", alloc_tuple)

        # 8. Withdrawal policies validation & defensive coercion
        if self.withdrawal_policies is None:
            raise ValueError("ExperimentDefinition withdrawal_policies cannot be empty.")
        withd_tuple = tuple(self.withdrawal_policies)
        if len(withd_tuple) == 0:
            raise ValueError("ExperimentDefinition withdrawal_policies cannot be empty.")

        for wp in withd_tuple:
            if wp is None or not isinstance(wp, WithdrawalPolicy):
                raise ValueError(
                    "ExperimentDefinition withdrawal_policies contain invalid elements."
                )

        object.__setattr__(self, "withdrawal_policies", withd_tuple)

    def __hash__(self) -> int:
        """Deterministic hash implementation."""
        return hash(
            (
                self.name,
                self.description,
                id(self.dataset),
                self.horizon_months,
                self.initial_wealth,
                self.cohorts,
                self.allocation_policies,
                self.withdrawal_policies,
            )
        )
