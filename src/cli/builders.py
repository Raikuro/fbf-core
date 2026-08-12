"""Reusable CLI builders — translate YAML input into domain objects.

Every CLI command that constructs an ExperimentDefinition or ResearchPlan
from a YAML file uses these functions.  They form the adapter between the
CLI presentation layer and the frozen domain layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from cli.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
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
from research.domain.plan import (
    ResearchPlan,
    datasets_are_prefix_consistent,
    materialize_grid_research_plan,
    materialize_research_plan,
)


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
    """Build an equity/bond ``Portfolio`` representing the initial wealth.

    Uses the same ``AssetClass`` objects the dataset loader produces
    (``id="equity"`` / ``id="bond"``, ``name=""`` / ``description=""``) so the
    engine can price and rebalance the initial holdings against the resolved
    ``equity``/``bond`` market universe.  The initial capital is funded into
    both holdings; the month-0 allocation policy rebalances to its target split.
    """
    equity = AssetClass(id="equity", name="", description="")
    bond = AssetClass(id="bond", name="", description="")

    equity_units = initial_wealth.amount * Decimal("0.5")
    bond_units = initial_wealth.amount * Decimal("0.5")

    return Portfolio(
        holdings=(
            AssetHolding(asset_class=equity, units=equity_units),
            AssetHolding(asset_class=bond, units=bond_units),
        )
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
    portfolio = build_initial_portfolio(experiment_def.initial_wealth)
    return materialize_research_plan(
        experiment_def=experiment_def,
        cohorts=cohorts,
        param_configs=param_configs,
        alloc_policy=alloc_policy,
        withdrawal_policy=withdrawal_policy,
        initial_portfolio=portfolio,
    )


@dataclass(frozen=True)
class ResolvedDatasetFamily:
    """A resolved ``datasets:`` declaration sharing one canonical trajectory.

    Fields
    ------
    canonical:
        The longest declared dataset; every shorter-horizon unit is a prefix
        slice of it, so the four declared ERN trajectories collapse into one.
    horizons:
        Mapping ``horizon_years`` -> resolved ``Dataset`` for every declared
        entry (used only for the prefix-consistency family check).
    """

    canonical: Dataset
    horizons: dict[int, Dataset]


def build_dataset_family(
    datasets_data: list[Any], data_dir: str | None
) -> ResolvedDatasetFamily:
    """Resolve a ``datasets:`` declaration into a prefix-consistent family.

    Loads every declared dataset (through the DatasetCache), picks the longest
    as the canonical trajectory and fails loudly if any shorter dataset is not
    a value-identical prefix of it.
    """
    entries: list[tuple[str, int]] = []
    for entry in datasets_data:
        if not isinstance(entry, dict):
            raise ValueError("Each datasets entry must be a mapping")
        identifier = entry.get("identifier")
        horizon_years = entry.get("horizon_years")
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError("datasets identifier must be a non-empty string")
        if (
            not isinstance(horizon_years, int)
            or isinstance(horizon_years, bool)
            or horizon_years <= 0
        ):
            raise ValueError("datasets horizon_years must be a positive integer")
        entries.append((identifier, horizon_years))
    if not entries:
        raise ValueError("datasets must declare at least one dataset")

    resolved: dict[int, Dataset] = {}
    for identifier, horizon_years in entries:
        if horizon_years in resolved:
            raise ValueError(
                f"datasets declares duplicate horizon_years={horizon_years}"
            )
        resolved[horizon_years] = resolve_dataset(identifier, data_dir)

    canonical_horizon = max(resolved, key=lambda h: len(resolved[h].snapshots))
    canonical = resolved[canonical_horizon]

    for horizon_years, dataset in resolved.items():
        if dataset is canonical:
            continue
        if not datasets_are_prefix_consistent(canonical, dataset):
            identifier = dataset.identifier or "<unknown>"
            raise ValueError(
                f"Declared dataset {identifier!r} (horizon_years={horizon_years}) is "
                f"not a prefix of the canonical trajectory "
                f"{(canonical.identifier or '<unknown>')!r}; datasets in a horizon "
                f"family must be prefix-consistent"
            )

    return ResolvedDatasetFamily(canonical=canonical, horizons=resolved)


def build_grid_research_plan(
    experiment_def: ExperimentDefinition,
    dataset_family: ResolvedDatasetFamily,
    cohorts: tuple[CohortSpecification, ...],
    param_configs: tuple[ParameterConfiguration, ...],
    alloc_policy: AllocationPolicy,
    withdrawal_policy: WithdrawalPolicy,
    default_horizon_years: int,
) -> ResearchPlan:
    """Build a grid ResearchPlan with per-unit horizons and parameterised policies.

    Parameter values drive the policies: ``equity_allocation`` resolves to a
    ``ConstantAllocationPolicy`` and ``withdrawal_rate`` to a
    ``FixedRealWithdrawalPolicy``.  A unit whose parameter configuration does
    not carry a given key keeps the corresponding literal policy.
    """
    portfolio = build_initial_portfolio(experiment_def.initial_wealth)

    def _resolve_horizon(config: ParameterConfiguration) -> int:
        if "horizon_years" in config.values:
            return int(config.get("horizon_years")) * 12
        return default_horizon_years * 12

    # Policies are pure functions of their single Decimal parameter, so a grid
    # of ~300k units would otherwise materialize ~600k fresh policy objects.
    # Sharing one instance per distinct parameter value is safe (nothing mutates
    # a policy after construction) and sharply cuts memory during plan building.
    _alloc_by_weight: dict[Decimal, AllocationPolicy] = {}
    _withdraw_by_rate: dict[Decimal, WithdrawalPolicy] = {}

    def _resolve_policies(
        config: ParameterConfiguration,
    ) -> tuple[AllocationPolicy, WithdrawalPolicy]:
        if "equity_allocation" in config.values:
            weight = Decimal(str(config.get("equity_allocation")))
            resolved_alloc = _alloc_by_weight.get(weight)
            if resolved_alloc is None:
                resolved_alloc = ConstantAllocationPolicy(equity_allocation=weight)
                _alloc_by_weight[weight] = resolved_alloc
        else:
            resolved_alloc = alloc_policy
        if "withdrawal_rate" in config.values:
            rate = Decimal(str(config.get("withdrawal_rate")))
            resolved_withd = _withdraw_by_rate.get(rate)
            if resolved_withd is None:
                resolved_withd = FixedRealWithdrawalPolicy(withdrawal_rate=rate)
                _withdraw_by_rate[rate] = resolved_withd
        else:
            resolved_withd = withdrawal_policy
        return resolved_alloc, resolved_withd

    return materialize_grid_research_plan(
        experiment_def=experiment_def,
        canonical_trajectory=dataset_family.canonical,
        cohorts=cohorts,
        param_configs=param_configs,
        initial_portfolio=portfolio,
        horizon_resolver=_resolve_horizon,
        policy_resolver=_resolve_policies,
    )
