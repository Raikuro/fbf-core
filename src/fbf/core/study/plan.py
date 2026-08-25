"""Research domain plan value objects.

Contains ``PlannedSimulationUnit`` and ``ResearchPlan`` — the immutable Public Research
Domain Contracts that represent a fully materialised study ready for execution.

These are pure value objects. Construction belongs exclusively to a dedicated planning
component (to be introduced in a future milestone). ``ResearchExecutor`` consumes these
objects but never builds, modifies, or reorders them.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.portfolio import Portfolio
from fbf.core.domain.policies.allocation_policy import AllocationPolicy
from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration

if TYPE_CHECKING:
    from fbf.core.study.internal.experiment.definition import ExperimentDefinition


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
    dataset:
        A fully materialised cohort-sliced Dataset ready for engine execution.
    horizon_months:
        The per-unit simulation horizon in months. When ``None`` the executor
        falls back to the shared ``ExperimentDefinition.horizon_months``
        (the pre-grid behaviour); plans produced by the planner always set it
        explicitly so the executor reads the horizon from the unit.
    """

    cohort: CohortSpecification
    parameter_config: ParameterConfiguration
    allocation_policy: AllocationPolicy
    withdrawal_policy: WithdrawalPolicy
    initial_portfolio: Portfolio
    dataset: Dataset
    horizon_months: int | None = None
    final_value_target: Decimal | None = None

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
        if self.dataset is None or not isinstance(self.dataset, Dataset):
            raise ValueError(
                "PlannedSimulationUnit.dataset must be a valid engine Dataset instance"
            )
        if self.horizon_months is not None and (
            not isinstance(self.horizon_months, int)
            or isinstance(self.horizon_months, bool)
            or self.horizon_months <= 0
        ):
            raise ValueError(
                "PlannedSimulationUnit.horizon_months must be a positive integer or None"
            )
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


def materialize_research_plan(
    experiment_def: ExperimentDefinition,
    canonical_trajectory: Dataset,
    cohorts: tuple[CohortSpecification, ...],
    param_configs: tuple[ParameterConfiguration, ...],
    initial_portfolio: Portfolio,
    horizon_resolver: Callable[[ParameterConfiguration], int],
    policy_resolver: Callable[
        [ParameterConfiguration], tuple[AllocationPolicy, WithdrawalPolicy]
    ],
    target_resolver: Callable[[ParameterConfiguration], Decimal | None] | None = None,
) -> ResearchPlan:
    """Build a ResearchPlan whose units take horizon and policies per parameter config.

    All units are sliced from a single *canonical_trajectory*: a unit with a
    shorter horizon receives the prefix of the trajectory that the longest
    horizon would use. The trajectory is shared across the whole study and
    never independently re-loaded per horizon.

    Parameters
    ----------
    experiment_def:
        The shared source study definition (canonical trajectory reference).
    canonical_trajectory:
        The canonical dataset; shorter-horizon units are prefix slices of it.
        Ownership belongs to the planning boundary that resolved it.
    cohorts:
        Horizon-feasible cohort specifications, generated against the longest
        horizon so every cohort is feasible for every declared horizon.
    param_configs:
        The Cartesian parameter space; each configuration resolves to a
        per-unit horizon (via *horizon_resolver*) and per-unit policies (via
        *policy_resolver*).
    initial_portfolio:
        Materialised initial portfolio shared by every unit.
    horizon_resolver:
        Maps a parameter configuration to its ``horizon_months``.
    policy_resolver:
        Maps a parameter configuration to the ``(allocation, withdrawal)``
        policy pair for its unit.
    target_resolver:
        Maps a parameter configuration to its ``final_value_target``
        (a ``Decimal`` fraction of initial wealth, or ``None`` when no
        final-value criterion is configured).  When ``None`` is passed,
        all units default to ``final_value_target=None``.

    Returns
    -------
    ResearchPlan
        A normal immutable plan; ``(cohort.start_date, parameter_config)``
        uniqueness is enforced by ``ResearchPlan`` itself.
    """
    dataset_cache: dict[tuple[date, int], Dataset] = {}
    units: list[PlannedSimulationUnit] = []
    for cohort in cohorts:
        for param_config in param_configs:
            horizon_months = horizon_resolver(param_config)
            alloc_policy, withdrawal_policy = policy_resolver(param_config)
            final_value_target = (
                target_resolver(param_config) if target_resolver is not None else None
            )
            cache_key = (cohort.start_date, horizon_months)
            if cache_key not in dataset_cache:
                dataset_cache[cache_key] = canonical_trajectory.slice(
                    cohort.start_date, horizon_months
                )
            units.append(
                PlannedSimulationUnit(
                    cohort=cohort,
                    parameter_config=param_config,
                    allocation_policy=alloc_policy,
                    withdrawal_policy=withdrawal_policy,
                    initial_portfolio=initial_portfolio,
                    dataset=dataset_cache[cache_key],
                    horizon_months=horizon_months,
                    final_value_target=final_value_target,
                )
            )
    return ResearchPlan(experiment_definition=experiment_def, units=tuple(units))

