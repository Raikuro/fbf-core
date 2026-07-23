"""Research domain plan value objects.

Contains ``PlannedSimulationUnit`` and ``ResearchPlan`` — the immutable Public Research
Domain Contracts that represent a fully materialised study ready for execution.

These are pure value objects. Construction belongs exclusively to a dedicated planning
component (to be introduced in a future milestone). ``ResearchExecutor`` consumes these
objects but never builds, modifies, or reorders them.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from engine.domain.model.portfolio import Portfolio
from engine.domain.policies.allocation_policy import AllocationPolicy
from engine.domain.policies.withdrawal_policy import WithdrawalPolicy
from research.domain.cohort.specification import CohortSpecification
from research.domain.parameter.configuration import ParameterConfiguration

if TYPE_CHECKING:
    from research.domain.experiment.definition import ExperimentDefinition


@dataclass(frozen=True, slots=True)
class PlannedSimulationUnit:
    """Immutable representation of one planned simulation run within a ResearchPlan.

    Canonical identity is the value tuple: (cohort.start_date, parameter_config).

    Fields
    ------
    cohort:
        The cohort specification identifying the historical start date for this run.
    parameter_config:
        The domain-agnostic scalar parameter configuration for this run.
    allocation_policy:
        A fully materialised concrete allocation policy ready for engine execution.
    withdrawal_policy:
        A fully materialised concrete withdrawal policy ready for engine execution.
    initial_portfolio:
        A fully materialised initial portfolio ready for engine execution. Ownership of
        portfolio materialisation belongs to the planning boundary that constructs this
        unit; ResearchExecutor maps the value through and never invents it.
    """

    cohort: CohortSpecification
    parameter_config: ParameterConfiguration
    allocation_policy: AllocationPolicy
    withdrawal_policy: WithdrawalPolicy
    initial_portfolio: Portfolio

    def __post_init__(self) -> None:
        if self.cohort is None:
            raise ValueError("PlannedSimulationUnit.cohort cannot be None")
        if self.parameter_config is None:
            raise ValueError("PlannedSimulationUnit.parameter_config cannot be None")
        if self.allocation_policy is None:
            raise ValueError("PlannedSimulationUnit.allocation_policy cannot be None")
        if self.withdrawal_policy is None:
            raise ValueError("PlannedSimulationUnit.withdrawal_policy cannot be None")
        if self.initial_portfolio is None:
            raise ValueError("PlannedSimulationUnit.initial_portfolio cannot be None")
        # Ensure the planner materialised an engine Portfolio value (ownership
        # belongs to the planning boundary). This prevents the executor from
        # inventing or coercing portfolio representations at execution time.
        if not isinstance(self.initial_portfolio, Portfolio):
            raise TypeError(
                "PlannedSimulationUnit.initial_portfolio must be an engine Portfolio instance"
            )


@dataclass(frozen=True, slots=True)
class ResearchPlan:
    """Immutable, fully materialised study plan ready for execution by ResearchExecutor.

    Represents the exact boundary between planning and execution. It is produced
    exclusively by a dedicated planning component and consumed (never mutated) by
    ``ResearchExecutor``.

    Fields
    ------
    experiment_definition:
        The immutable source study definition shared across all planned units.
    units:
        An ordered, non-empty, immutable tuple of ``PlannedSimulationUnit`` objects.
        Uniqueness is enforced by canonical identity ``(unit.cohort.start_date,
        unit.parameter_config)``.
    """

    experiment_definition: ExperimentDefinition
    units: tuple[PlannedSimulationUnit, ...]

    def __post_init__(self) -> None:
        if self.experiment_definition is None:
            raise ValueError("ResearchPlan.experiment_definition cannot be None")

        # Coerce sequences to tuple if needed (defensive coercion)
        if not isinstance(self.units, tuple):
            object.__setattr__(self, "units", tuple(self.units))

        if not self.units:
            raise ValueError("ResearchPlan.units tuple cannot be empty")

        # Verify every element is a PlannedSimulationUnit and identities are unique
        seen_keys: set[tuple[date, ParameterConfiguration]] = set()
        for idx, unit in enumerate(self.units):
            if not isinstance(unit, PlannedSimulationUnit):
                raise TypeError(
                    f"Unit at index {idx} is not a PlannedSimulationUnit: {type(unit)!r}"
                )
            key = (unit.cohort.start_date, unit.parameter_config)
            if key in seen_keys:
                raise ValueError(
                    f"Duplicate PlannedSimulationUnit identity detected in plan at index {idx}: "
                    f"cohort={unit.cohort.start_date.isoformat()!r}, "
                    f"parameter_config={unit.parameter_config!r}"
                )
            seen_keys.add(key)

    def __len__(self) -> int:
        return len(self.units)

    def __getitem__(self, index: int) -> PlannedSimulationUnit:
        return self.units[index]

    def __iter__(self) -> Iterator[PlannedSimulationUnit]:
        return iter(self.units)
