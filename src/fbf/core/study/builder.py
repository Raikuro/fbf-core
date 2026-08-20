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

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.money import Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies import (
    ConstantAllocationPolicy,
    ConstantWithdrawalPolicy,
    FixedRealWithdrawalPolicy,
)
from fbf.core.domain.policies.allocation_policy import AllocationPolicy
from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy
from fbf.core.persistence.studies.sqlite.codecs import DefaultDatasetResolver
from fbf.core.study.internal.cohort.generator import CohortGenerator
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.axis import ParameterAxis
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.internal.parameter.engine import ParameterSweepEngine
from fbf.core.study.plan import (
    ResearchPlan,
    materialize_research_plan,
)


def load_yaml(path: Path) -> dict[str, Any]:
    """Load and parse a YAML file.  Raises FileNotFoundError, yaml.YAMLError, or ValueError."""
    try:
        import yaml
    except ImportError as err:
        raise RuntimeError(

                "PyYAML is not installed in fbf-core. "
                "Pass a dict directly to StudyConfiguration.from_dict()."

        ) from err
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        msg = f"Expected YAML mapping at root of {path}, got {type(data).__name__}"
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
# v0.6 — study configuration model
#
# One normalized interpretation of study YAML, consumed by run, validate,
# compare and optimize.  There is a single materialization flow:
#
#     YAML -> StudyConfiguration -> parameter configurations ->
#       per-cohort/per-configuration units -> ResearchPlan
#
# The study YAML is the sole source of study-definition parameters.  The three
# value-bearing fields (``allocation_policy.equity_allocation``,
# ``withdrawal_policy.withdrawal_rate``, ``cohorts.horizon_years``) are all
# arrays; their Cartesian product is the study configuration space.  There is
# no base/fallback/override layer and no implicit default.
# ---------------------------------------------------------------------------


_ALLOCATION_POLICY_TYPES = frozenset({"ConstantAllocationPolicy"})
_WITHDRAWAL_POLICY_TYPES = frozenset({"FixedRealWithdrawalPolicy", "ConstantWithdrawalPolicy"})


def _parse_decimal_values(policy: dict[str, Any], key: str) -> tuple[Decimal, ...]:
    """Parse a required non-empty decimal value array from a policy mapping."""
    raw_values = policy.get(key)
    if not isinstance(raw_values, list) or not raw_values:
        raise ValueError(f"{key} must be a non-empty list of decimal numbers")
    values: list[Decimal] = []
    for raw in raw_values:
        try:
            values.append(Decimal(str(raw)))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError(f"{key} must contain only decimal numbers") from None
    return tuple(values)


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

    The study YAML is the sole source of study-definition parameters.  Every
    value-bearing field is an array; the Cartesian product of the three arrays
    is the study configuration space.  There is no base/fallback/override layer.

    Fields
    ------
    name / description / version:
        Study metadata.
    dataset_identifier:
        The single canonical runtime dataset (``dataset.identifier``).
    allocation_policy_type / allocation_policy_values:
        The declared allocation policy and its ``equity_allocation`` array.
    withdrawal_policy_type / withdrawal_policy_values:
        The declared withdrawal policy and its ``withdrawal_rate`` array.
    horizon_years:
        The declared ``cohorts.horizon_years`` array.
    """

    name: str
    description: str
    version: str
    dataset_identifier: str
    allocation_policy_type: str
    allocation_policy_values: tuple[Decimal, ...]
    withdrawal_policy_type: str
    withdrawal_policy_values: tuple[Decimal, ...]
    horizon_years: tuple[int, ...]

    @classmethod
    def from_yaml(cls, data: dict[str, Any]) -> StudyConfiguration:
        """Parse a validated ``StudyConfiguration`` from raw study YAML.

        Raises
        ------
        ValueError
            For any structurally invalid or unsupported study declaration,
            including any leftover v0.5 ``parameters`` / ``window_years`` /
            ``cohorts.type`` keys.
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

        if "parameters" in data:
            raise ValueError(
                "parameters is no longer supported; declare values under "
                "allocation_policy.equity_allocation, withdrawal_policy.withdrawal_rate, "
                "and cohorts.horizon_years"
            )

        cohorts = data.get("cohorts")
        if not isinstance(cohorts, dict):
            raise ValueError("cohorts must be a mapping")
        if "type" in cohorts:
            raise ValueError(
                "cohorts.type is no longer supported; cohorts are generated as "
                "rolling monthly windows from cohorts.horizon_years"
            )
        if "window_years" in cohorts:
            raise ValueError(
                "cohorts.window_years is no longer supported; declare cohorts.horizon_years"
            )
        horizon_years = _parse_horizon_years(cohorts)

        allocation_policy = data.get("allocation_policy")
        if not isinstance(allocation_policy, dict):
            raise ValueError("allocation_policy must be a mapping")
        allocation_policy_type = allocation_policy.get("type")
        if allocation_policy_type not in _ALLOCATION_POLICY_TYPES:
            raise ValueError(
                f"Unsupported allocation policy type: {allocation_policy_type!r}"
            )
        allocation_policy_values = _parse_decimal_values(
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
        withdrawal_policy_values = _parse_decimal_values(
            withdrawal_policy, "withdrawal_rate"
        )

        return cls(
            name=str(metadata.get("name", "Unnamed Study")),
            description=str(metadata.get("description", "")),
            version=str(metadata.get("version", "")),
            dataset_identifier=dataset_identifier,
            allocation_policy_type=allocation_policy_type,
            allocation_policy_values=allocation_policy_values,
            withdrawal_policy_type=withdrawal_policy_type,
            withdrawal_policy_values=withdrawal_policy_values,
            horizon_years=horizon_years,
        )


def _parse_horizon_years(cohorts: dict[str, Any]) -> tuple[int, ...]:
    """Parse a required non-empty positive-integer horizon array."""
    raw_values = cohorts.get("horizon_years")
    if not isinstance(raw_values, list) or not raw_values:
        raise ValueError(
            "cohorts.horizon_years must be a non-empty list of positive integers"
        )
    years: list[int] = []
    for raw in raw_values:
        if not isinstance(raw, int) or isinstance(raw, bool) or raw <= 0:
            raise ValueError("cohorts.horizon_years must contain only positive integers")
        years.append(raw)
    return tuple(years)


def _build_unified_parameter_configs(
    config: StudyConfiguration,
) -> tuple[ParameterConfiguration, ...]:
    """Build the study's parameter configurations.

    The Cartesian product of the three declared value arrays
    (``equity_allocation`` x ``withdrawal_rate`` x ``horizon_years``), with
    ``horizon_years`` varying fastest.
    """
    axes = [
        ParameterAxis(
            name="equity_allocation",
            values=tuple(float(value) for value in config.allocation_policy_values),
        ),
        ParameterAxis(
            name="withdrawal_rate",
            values=tuple(float(value) for value in config.withdrawal_policy_values),
        ),
        ParameterAxis(
            name="horizon_years",
            values=tuple(int(value) for value in config.horizon_years),
        ),
    ]
    return ParameterSweepEngine.cartesian_product(axes)


def _longest_horizon_years(config: StudyConfiguration) -> int:
    """The longest declared horizon — makes every cohort feasible for every unit."""
    return max(config.horizon_years)


def _make_horizon_resolver(
    config: StudyConfiguration,
) -> Callable[[ParameterConfiguration], int]:
    """Per-configuration horizon: the ``horizon_years`` value in observations.

    The ERN cash-flow timeline needs one observation for the pre-retirement
    month-end (``d_{c-1}``, where the initial withdrawal is priced) plus one
    per retirement month, i.e. ``horizon_years * 12 + 1`` observations for a
    ``horizon_years``-year retirement.
    """

    def resolve(param_config: ParameterConfiguration) -> int:
        return int(param_config.get("horizon_years")) * 12 + 1

    return resolve


def _make_policy_resolver(
    config: StudyConfiguration,
) -> Callable[[ParameterConfiguration], tuple[AllocationPolicy, WithdrawalPolicy]]:
    """Per-configuration policies from the study's declared value arrays.

    Policies are pure functions of their single scalar, so one instance is
    shared per distinct scalar value (nothing mutates a policy after
    construction), keeping plan building memory-bounded.
    """
    _alloc_by_weight: dict[Decimal, AllocationPolicy] = {}
    _withdraw_by_rate: dict[Decimal, WithdrawalPolicy] = {}

    def resolve(
        param_config: ParameterConfiguration,
    ) -> tuple[AllocationPolicy, WithdrawalPolicy]:
        weight = Decimal(str(param_config.get("equity_allocation")))
        resolved_alloc = _alloc_by_weight.get(weight)
        if resolved_alloc is None:
            resolved_alloc = build_allocation_policy(config.allocation_policy_type, weight)
            _alloc_by_weight[weight] = resolved_alloc
        rate = Decimal(str(param_config.get("withdrawal_rate")))
        resolved_withd = _withdraw_by_rate.get(rate)
        if resolved_withd is None:
            resolved_withd = build_withdrawal_policy(config.withdrawal_policy_type, rate)
            _withdraw_by_rate[rate] = resolved_withd
        return resolved_alloc, resolved_withd

    return resolve


def _representative_policies(
    config: StudyConfiguration,
) -> tuple[AllocationPolicy, WithdrawalPolicy]:
    """Policies built from the first declared value of each array.

    These are the experiment-definition policy snapshot used for persistence;
    per-unit policies always come from each unit's parameter configuration.
    """
    return (
        build_allocation_policy(
            config.allocation_policy_type, config.allocation_policy_values[0]
        ),
        build_withdrawal_policy(
            config.withdrawal_policy_type, config.withdrawal_policy_values[0]
        ),
    )


@dataclass(frozen=True)
class BuiltStudy:
    """A fully built study: its plan plus the components behind it."""

    plan: ResearchPlan
    experiment_definition: ExperimentDefinition
    cohorts: tuple[CohortSpecification, ...]
    param_configs: tuple[ParameterConfiguration, ...]


def build_study_plan(
    config: StudyConfiguration,
    data_dir: str | None,
    initial_wealth: Money,
) -> BuiltStudy:
    """Build the single unified ResearchPlan for a normalized study.

    Every unit is sliced from the single canonical ``dataset``; per-unit
    horizons and policies come from the study's declared value arrays.  This
    is the only plan construction path for every CLI consumer.
    """
    dataset = resolve_dataset(config.dataset_identifier, data_dir)
    longest_horizon_years = _longest_horizon_years(config)
    longest_horizon_months = longest_horizon_years * 12 + 1
    cohorts = build_cohort_specs(dataset, longest_horizon_months)
    if not cohorts:
        raise ValueError(
            f"Dataset {config.dataset_identifier!r} is too small for a "
            f"{longest_horizon_years}-year "
            f"({longest_horizon_months}-observation) horizon"
        )
    param_configs = _build_unified_parameter_configs(config)

    representative_allocation, representative_withdrawal = _representative_policies(config)

    experiment_def = ExperimentDefinition(
        name=config.name,
        description=config.description or config.name,
        dataset=dataset,
        horizon_months=longest_horizon_months,
        initial_wealth=initial_wealth,
        cohorts=cohorts,
        allocation_policies=(representative_allocation,),
        withdrawal_policies=(representative_withdrawal,),
    )

    portfolio = build_initial_portfolio(initial_wealth)
    plan = materialize_research_plan(
        experiment_def=experiment_def,
        canonical_trajectory=dataset,
        cohorts=cohorts,
        param_configs=param_configs,
        initial_portfolio=portfolio,
        horizon_resolver=_make_horizon_resolver(config),
        policy_resolver=_make_policy_resolver(config),
    )
    return BuiltStudy(
        plan=plan,
        experiment_definition=experiment_def,
        cohorts=cohorts,
        param_configs=param_configs,
    )

StudyPlanResult = BuiltStudy
