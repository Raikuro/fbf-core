"""Reusable CLI builders — translate YAML input into domain objects.

Every CLI command that constructs an ExperimentDefinition or ResearchPlan
from a YAML file uses these functions.  They form the adapter between the
CLI presentation layer and the frozen domain layer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

from cli.policies import (
    ConstantAllocationPolicy,
    ConstantWithdrawalPolicy,
    FixedRealWithdrawalPolicy,
)
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


# ---------------------------------------------------------------------------
# v0.5 — unified Study Configuration model
#
# One normalized interpretation of study YAML, consumed by run, validate,
# compare and optimize.  There is a single materialization flow:
#
#     YAML -> StudyConfiguration -> parameter configurations ->
#       per-cohort/per-configuration units -> ResearchPlan
#
# A parameter axis overrides the matching base policy scalar for every unit
# that carries it; a configuration without a given key keeps the base policy.
# ``parameters.horizon_years`` selects the per-unit horizon (a prefix slice of
# the canonical dataset); without it every unit uses the study window.
# ---------------------------------------------------------------------------


_ALLOCATION_POLICY_TYPES = frozenset({"ConstantAllocationPolicy"})
_WITHDRAWAL_POLICY_TYPES = frozenset({"FixedRealWithdrawalPolicy", "ConstantWithdrawalPolicy"})
_DEFAULT_WINDOW_YEARS = 30
_DEFAULT_ALLOCATION_SCALAR = Decimal("0.75")
_DEFAULT_WITHDRAWAL_SCALAR = Decimal("0.04")


def _parse_optional_scalar(policy: dict[str, Any], key: str) -> Decimal | None:
    """Parse an optional decimal scalar from a policy mapping (``None`` if absent)."""
    if key not in policy:
        return None
    try:
        return Decimal(str(policy[key]))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{key} must be a decimal number") from None


def build_allocation_policy(policy_type: str, scalar: Decimal) -> AllocationPolicy:
    """Build the concrete allocation policy for the declared YAML ``type``."""
    if policy_type != "ConstantAllocationPolicy":
        raise ValueError(f"Unsupported allocation policy type: {policy_type!r}")
    return ConstantAllocationPolicy(equity_allocation=scalar)


def build_withdrawal_policy(policy_type: str, scalar: Decimal) -> WithdrawalPolicy:
    """Build the concrete withdrawal policy for the declared YAML ``type``."""
    if policy_type == "FixedRealWithdrawalPolicy":
        return FixedRealWithdrawalPolicy(withdrawal_rate=scalar)
    if policy_type == "ConstantWithdrawalPolicy":
        return ConstantWithdrawalPolicy(withdrawal_rate=scalar)
    raise ValueError(f"Unsupported withdrawal policy type: {policy_type!r}")


@dataclass(frozen=True)
class StudyConfiguration:
    """The normalized study configuration — the single YAML interpretation layer.

    All four CLI consumers (``run``, ``validate``, ``compare``, ``optimize``)
    build their plans from this object; no command parses study YAML directly.

    Fields
    ------
    name / description / version:
        Study metadata.
    dataset_identifier:
        The single canonical runtime dataset (``dataset.identifier``).
    window_years:
        The study/default horizon; used for every unit whose configuration
        does not carry a ``horizon_years`` axis value.
    allocation_policy_type / allocation_policy_scalar:
        The declared allocation policy; the scalar is optional when the
        ``equity_allocation`` parameter axis supplies it per unit.
    withdrawal_policy_type / withdrawal_policy_scalar:
        The declared withdrawal policy; the scalar is optional when the
        ``withdrawal_rate`` parameter axis supplies it per unit.
    parameters:
        Optional parameter axes.  Each axis overrides the matching base scalar
        for every configuration that carries it; ``horizon_years`` selects the
        per-unit horizon.
    """

    name: str
    description: str
    version: str
    dataset_identifier: str
    window_years: int
    allocation_policy_type: str
    allocation_policy_scalar: Decimal | None
    withdrawal_policy_type: str
    withdrawal_policy_scalar: Decimal | None
    parameters: dict[str, tuple[Any, ...]]

    @classmethod
    def from_yaml(cls, data: dict[str, Any]) -> StudyConfiguration:
        """Parse a validated ``StudyConfiguration`` from raw study YAML.

        Raises
        ------
        ValueError
            For any structurally invalid or unsupported study declaration.
        """
        metadata = data.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be a mapping")

        dataset = data.get("dataset")
        if not isinstance(dataset, dict):
            raise ValueError("dataset must be a mapping")
        dataset_identifier = dataset.get("identifier")
        if not isinstance(dataset_identifier, str) or not dataset_identifier.strip():
            raise ValueError("dataset.identifier must be a non-empty string")

        cohorts = data.get("cohorts", {})
        if not isinstance(cohorts, dict):
            raise ValueError("cohorts must be a mapping")
        cohort_type = cohorts.get("type", "monthly_rolling")
        if cohort_type != "monthly_rolling":
            raise ValueError("cohorts.type must be 'monthly_rolling'")
        window_years = cohorts.get("window_years", _DEFAULT_WINDOW_YEARS)
        if (
            not isinstance(window_years, int)
            or isinstance(window_years, bool)
            or window_years <= 0
        ):
            raise ValueError("window_years must be a positive integer")

        allocation_policy = data.get("allocation_policy")
        if not isinstance(allocation_policy, dict):
            raise ValueError("allocation_policy must be a mapping")
        allocation_policy_type = allocation_policy.get("type")
        if allocation_policy_type not in _ALLOCATION_POLICY_TYPES:
            raise ValueError(
                f"Unsupported allocation policy type: {allocation_policy_type!r}"
            )
        allocation_policy_scalar = _parse_optional_scalar(
            allocation_policy, "equity_allocation"
        )

        withdrawal_policy = data.get("withdrawal_policy")
        if not isinstance(withdrawal_policy, dict):
            raise ValueError("withdrawal_policy must be a mapping")
        withdrawal_policy_type = withdrawal_policy.get("type")
        if withdrawal_policy_type not in _WITHDRAWAL_POLICY_TYPES:
            raise ValueError(
                f"Unsupported withdrawal policy type: {withdrawal_policy_type!r}"
            )
        withdrawal_policy_scalar = _parse_optional_scalar(
            withdrawal_policy, "withdrawal_rate"
        )

        parameters_data = data.get("parameters", {})
        if not isinstance(parameters_data, dict):
            raise ValueError("parameters must be a mapping")
        parameters: dict[str, tuple[Any, ...]] = {}
        for name, values in parameters_data.items():
            if not isinstance(values, list) or not values:
                raise ValueError(f"Parameter {name!r} must have a non-empty list of values")
            parameters[name] = tuple(values)

        if allocation_policy_scalar is None and "equity_allocation" not in parameters:
            raise ValueError(
                "allocation_policy.equity_allocation is required unless "
                "parameters.equity_allocation supplies it"
            )
        if withdrawal_policy_scalar is None and "withdrawal_rate" not in parameters:
            raise ValueError(
                "withdrawal_policy.withdrawal_rate is required unless "
                "parameters.withdrawal_rate supplies it"
            )

        return cls(
            name=str(metadata.get("name", "Unnamed Study")),
            description=str(metadata.get("description", "")),
            version=str(metadata.get("version", "")),
            dataset_identifier=dataset_identifier,
            window_years=window_years,
            allocation_policy_type=allocation_policy_type,
            allocation_policy_scalar=allocation_policy_scalar,
            withdrawal_policy_type=withdrawal_policy_type,
            withdrawal_policy_scalar=withdrawal_policy_scalar,
            parameters=parameters,
        )


def _build_unified_parameter_configs(
    config: StudyConfiguration,
) -> tuple[ParameterConfiguration, ...]:
    """Build the parameter configurations for a normalized study.

    Without any parameter axis the study is a single configuration per cohort
    carrying the base policy scalars; with axes it is their Cartesian product.
    """
    axes: list[ParameterAxis] = []
    for name, axis_values in config.parameters.items():
        axes.append(ParameterAxis(name=name, values=axis_values))
    if not axes:
        scalar_values: dict[str, float] = {}
        if config.allocation_policy_scalar is not None:
            scalar_values["equity_allocation"] = float(config.allocation_policy_scalar)
        if config.withdrawal_policy_scalar is not None:
            scalar_values["withdrawal_rate"] = float(config.withdrawal_policy_scalar)
        return (ParameterConfiguration(scalar_values),)
    return ParameterSweepEngine.cartesian_product(axes)


def _longest_horizon_years(config: StudyConfiguration) -> int:
    """The longest horizon needed to make every cohort feasible for every unit."""
    axis_horizons = [
        h
        for h in config.parameters.get("horizon_years", ())
        if isinstance(h, int) and not isinstance(h, bool) and h > 0
    ]
    axis_max = max(axis_horizons) if axis_horizons else 0
    return max(axis_max, config.window_years)


def _make_horizon_resolver(
    config: StudyConfiguration,
) -> Callable[[ParameterConfiguration], int]:
    """Per-configuration horizon: the ``horizon_years`` axis value, else the study window."""

    def resolve(param_config: ParameterConfiguration) -> int:
        if "horizon_years" in param_config.values:
            return int(param_config.get("horizon_years")) * 12
        return config.window_years * 12

    return resolve


def _make_policy_resolver(
    config: StudyConfiguration,
    base_allocation: AllocationPolicy,
    base_withdrawal: WithdrawalPolicy,
) -> Callable[[ParameterConfiguration], tuple[AllocationPolicy, WithdrawalPolicy]]:
    """Per-configuration policies: an axis overrides the base scalar, else the base policy.

    Policies are pure functions of their single scalar, so one instance is
    shared per distinct scalar value (nothing mutates a policy after
    construction), keeping plan building memory-bounded.
    """
    _alloc_by_weight: dict[Decimal, AllocationPolicy] = {}
    _withdraw_by_rate: dict[Decimal, WithdrawalPolicy] = {}

    def resolve(
        param_config: ParameterConfiguration,
    ) -> tuple[AllocationPolicy, WithdrawalPolicy]:
        if "equity_allocation" in param_config.values:
            weight = Decimal(str(param_config.get("equity_allocation")))
            resolved_alloc = _alloc_by_weight.get(weight)
            if resolved_alloc is None:
                resolved_alloc = build_allocation_policy(config.allocation_policy_type, weight)
                _alloc_by_weight[weight] = resolved_alloc
        else:
            resolved_alloc = base_allocation
        if "withdrawal_rate" in param_config.values:
            rate = Decimal(str(param_config.get("withdrawal_rate")))
            resolved_withd = _withdraw_by_rate.get(rate)
            if resolved_withd is None:
                resolved_withd = build_withdrawal_policy(
                    config.withdrawal_policy_type, rate
                )
                _withdraw_by_rate[rate] = resolved_withd
        else:
            resolved_withd = base_withdrawal
        return resolved_alloc, resolved_withd

    return resolve


@dataclass(frozen=True)
class BuiltStudy:
    """A fully built study: its plan plus the components behind it."""

    plan: ResearchPlan
    experiment_definition: ExperimentDefinition
    cohorts: tuple[CohortSpecification, ...]
    param_configs: tuple[ParameterConfiguration, ...]
    base_allocation_policy: AllocationPolicy
    base_withdrawal_policy: WithdrawalPolicy


def build_study_plan(
    config: StudyConfiguration,
    data_dir: str | None,
    initial_wealth: Money,
) -> BuiltStudy:
    """Build the single unified ResearchPlan for a normalized study.

    Every unit is sliced from the single canonical ``dataset``; per-unit
    horizons and policies come from the configuration's parameter axes (with
    the base scalars / study window as the fallback).  This is the only plan
    construction path for every CLI consumer.
    """
    dataset = resolve_dataset(config.dataset_identifier, data_dir)
    longest_horizon_months = _longest_horizon_years(config) * 12
    cohorts = build_cohort_specs(dataset, longest_horizon_months)
    if not cohorts:
        raise ValueError(
            f"Dataset {config.dataset_identifier!r} is too small for a "
            f"{_longest_horizon_years(config)}-year ({longest_horizon_months}-month) horizon"
        )
    param_configs = _build_unified_parameter_configs(config)

    base_allocation = build_allocation_policy(
        config.allocation_policy_type,
        (
            config.allocation_policy_scalar
            if config.allocation_policy_scalar is not None
            else _DEFAULT_ALLOCATION_SCALAR
        ),
    )
    base_withdrawal = build_withdrawal_policy(
        config.withdrawal_policy_type,
        (
            config.withdrawal_policy_scalar
            if config.withdrawal_policy_scalar is not None
            else _DEFAULT_WITHDRAWAL_SCALAR
        ),
    )

    experiment_def = ExperimentDefinition(
        name=config.name,
        description=config.description or config.name,
        dataset=dataset,
        horizon_months=longest_horizon_months,
        initial_wealth=initial_wealth,
        cohorts=cohorts,
        allocation_policies=(base_allocation,),
        withdrawal_policies=(base_withdrawal,),
    )

    portfolio = build_initial_portfolio(initial_wealth)
    plan = materialize_research_plan(
        experiment_def=experiment_def,
        canonical_trajectory=dataset,
        cohorts=cohorts,
        param_configs=param_configs,
        initial_portfolio=portfolio,
        horizon_resolver=_make_horizon_resolver(config),
        policy_resolver=_make_policy_resolver(config, base_allocation, base_withdrawal),
    )
    return BuiltStudy(
        plan=plan,
        experiment_definition=experiment_def,
        cohorts=cohorts,
        param_configs=param_configs,
        base_allocation_policy=base_allocation,
        base_withdrawal_policy=base_withdrawal,
    )
