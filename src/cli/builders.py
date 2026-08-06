"""Reusable CLI builders — translate YAML input into domain objects.

Every CLI command that constructs an ExperimentDefinition or ResearchPlan
from a YAML file uses these functions.  They form the adapter between the
CLI presentation layer and the frozen domain layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from engine.domain.model.asset import AssetClass
from engine.domain.model.dataset import Dataset
from engine.domain.model.money import Money
from engine.domain.model.portfolio import AssetHolding, Portfolio
from engine.domain.policies.allocation_policy import AllocationPolicy
from engine.domain.policies.withdrawal_policy import WithdrawalPolicy
from infrastructure.persistence.codecs import DefaultDatasetResolver
from research.domain.cohort.generator import CohortGenerator
from research.domain.cohort.specification import CohortSpecification
from research.domain.experiment.definition import ExperimentDefinition
from research.domain.parameter.axis import ParameterAxis
from research.domain.parameter.configuration import ParameterConfiguration
from research.domain.parameter.engine import ParameterSweepEngine
from research.domain.plan import PlannedSimulationUnit, ResearchPlan


def load_yaml(path: Path) -> dict[str, Any]:
    """Load and parse a YAML file.  Raises FileNotFoundError or yaml.YAMLError."""
    if not path.exists():
        raise FileNotFoundError(str(path))
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        msg = "YAML root must be a mapping"
        raise yaml.YAMLError(msg)
    return data


def resolve_dataset(identifier: str, data_dir: str | None) -> Dataset:
    """Resolve a dataset identifier using DefaultDatasetResolver."""
    if data_dir:
        resolver = DefaultDatasetResolver.from_data_dir(data_dir)
    else:
        resolver = DefaultDatasetResolver()
    return resolver.resolve(identifier)


def build_cohort_specs(
    dataset: Dataset, horizon_months: int
) -> tuple[CohortSpecification, ...]:
    """Generate all horizon-feasible rolling monthly cohorts from *dataset*."""
    return CohortGenerator.generate_rolling_monthly(dataset, horizon_months)


def build_parameter_configs(
    params_data: dict[str, Any]
) -> tuple[ParameterConfiguration, ...]:
    """Build parameter configurations from a YAML ``parameters:`` section."""
    axes: list[ParameterAxis] = []
    for name, values in params_data.items():
        if not isinstance(values, list) or len(values) == 0:
            raise ValueError(
                f"Parameter {name!r} must have a non-empty list of values"
            )
        axes.append(ParameterAxis(name=name, values=tuple(values)))
    if not axes:
        raise ValueError("At least one parameter axis is required")
    return ParameterSweepEngine.cartesian_product(axes)


def build_initial_portfolio(initial_wealth: Money) -> Portfolio:
    """Build a single-asset Portfolio representing the initial wealth."""
    asset = AssetClass(id="initial", name="Initial Portfolio", description="")
    return Portfolio(
        holdings=(AssetHolding(asset_class=asset, units=initial_wealth.amount),)
    )


def build_research_plan(
    experiment_def: ExperimentDefinition,
    cohorts: tuple[CohortSpecification, ...],
    param_configs: tuple[ParameterConfiguration, ...],
    alloc_policy: AllocationPolicy,
    withdrawal_policy: WithdrawalPolicy,
) -> ResearchPlan:
    """Build a fully materialised ResearchPlan from pre-validated components.

    Because ``ResearchPlan`` identity is ``(cohort.start_date, parameter_config)``,
    only one allocation+withdrawal policy pair is used per plan.
    """
    units: list[PlannedSimulationUnit] = []
    portfolio = build_initial_portfolio(experiment_def.initial_wealth)
    for cohort in cohorts:
        for param_config in param_configs:
            units.append(
                PlannedSimulationUnit(
                    cohort=cohort,
                    parameter_config=param_config,
                    allocation_policy=alloc_policy,
                    withdrawal_policy=withdrawal_policy,
                    initial_portfolio=portfolio,
                )
            )
    return ResearchPlan(experiment_definition=experiment_def, units=tuple(units))
