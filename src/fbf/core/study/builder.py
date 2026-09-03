"""Reusable CLI builders — translate YAML input into domain objects.

Every CLI command that constructs an ExperimentDefinition or ResearchPlan
from a YAML file uses these functions.  They form the adapter between the
CLI presentation layer and the frozen domain layer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.money import Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies import (
    AllocationPolicyType,
    ConstantAllocationPolicy,
    ConstantWithdrawalPolicy,
    FixedRealWithdrawalPolicy,
    GlidepathAllocationPolicy,
    WithdrawalPolicyType,
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
            "PyYAML is not installed. YAML loading is an optional capability "
            "that requires PyYAML. Install it with: pip install fbf-core[dev]. "
            "Alternatively, pass a dict directly to StudyConfiguration.from_dict()."
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


def _parse_optional_decimal_array(
    data: dict[str, Any], key: str
) -> tuple[Decimal, ...] | None:
    """Parse an optional decimal value array from the study YAML root mapping.

    Returns ``None`` when the key is absent or explicitly set to ``null``.
    Raises ``ValueError`` when the key is present but structurally invalid.
    """
    raw = data.get(key)
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{key} must be a non-empty list of decimal numbers when provided")
    values: list[Decimal] = []
    for item in raw:
        try:
            values.append(Decimal(str(item)))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError(f"{key} must contain only decimal numbers") from None
    return tuple(values)


def _parse_optional_decimal_scalar(
    data: dict[str, Any], key: str
) -> Decimal | None:
    """Parse an optional decimal scalar from a mapping.

    Returns ``None`` when the key is absent or explicitly set to ``null``.
    Raises ``ValueError`` when the key is present but not a valid number.
    """
    raw = data.get(key)
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{key} must be a valid decimal number") from None


def _parse_optional_string_array(
    data: dict[str, Any], key: str
) -> tuple[str, ...] | None:
    """Parse an optional string value array from a mapping.

    Returns ``None`` when the key is absent or explicitly set to ``null``.
    Raises ``ValueError`` when the key is present but structurally invalid.
    """
    raw = data.get(key)
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{key} must be a non-empty list of strings when provided")
    for item in raw:
        if not isinstance(item, str):
            raise ValueError(f"{key} must contain only strings") from None
    return tuple(raw)


def build_allocation_policy(policy_type: str, scalar: Decimal) -> AllocationPolicy:
    """Build the concrete allocation policy for the declared YAML ``type``."""
    policy_enum = AllocationPolicyType.from_yaml_name(policy_type)
    if policy_enum is AllocationPolicyType.CONSTANT:
        return ConstantAllocationPolicy(equity_allocation=scalar)
    raise ValueError(f"Unsupported allocation policy type: {policy_type!r}")


def build_glidepath_allocation_policy(
    start_equity: Decimal,
    end_equity: Decimal,
    slope: Decimal,
    mode: str,
) -> GlidepathAllocationPolicy:
    """Build a GlidepathAllocationPolicy from its four parameters."""
    return GlidepathAllocationPolicy(
        start_equity=start_equity,
        end_equity=end_equity,
        slope=slope,
        mode=mode,
    )


def build_withdrawal_policy(policy_type: str, scalar: Decimal) -> WithdrawalPolicy:
    """Build the concrete withdrawal policy for the declared YAML ``type``."""
    policy_enum = WithdrawalPolicyType.from_yaml_name(policy_type)
    if policy_enum is WithdrawalPolicyType.FIXED_REAL:
        return FixedRealWithdrawalPolicy(withdrawal_rate=scalar)
    if policy_enum is WithdrawalPolicyType.CONSTANT:
        return ConstantWithdrawalPolicy(withdrawal_rate=scalar)
    raise ValueError(f"Unsupported withdrawal policy type: {policy_type!r}")


@dataclass(frozen=True)
class StudyConfiguration:
    """The normalized study configuration — the single YAML interpretation layer.

    All four CLI consumers (``run``, ``validate``, ``compare``, ``optimize``)
    build their plans from this object; no command parses study YAML directly.

    The study YAML is the sole source of study-definition parameters.  Two
    parameterization modes are supported:

    **Mode A — Independent axis arrays (Cartesian product):**
    Each value-bearing field is an array; the Cartesian product of the arrays
    is the study configuration space.

    **Mode B — Explicit parameter combinations:**
    ``allocation_policy.configurations`` lists individual parameter dicts.
    Each dict specifies one complete policy configuration.  The
    ``withdrawal_rate`` and ``horizon_years`` axes are still Cartesian-producted
    with the explicit configurations.

    ``configurations`` and axis-based policy parameters are mutually exclusive.

    Fields
    ------
    name / description / version:
        Study metadata.
    dataset_identifier:
        The single canonical runtime dataset (``dataset.identifier``).
    allocation_policy_type / allocation_policy_values:
        The declared allocation policy and its ``equity_allocation`` array
        (Mode A only; empty tuple in Mode B).
    withdrawal_policy_type / withdrawal_policy_values:
        The declared withdrawal policy and its ``withdrawal_rate`` array.
    horizon_years:
        The declared ``cohorts.horizon_years`` array.
    explicit_configurations:
        Explicit policy parameter dicts (Mode B only; ``None`` in Mode A).
        Each dict maps parameter names to scalar values appropriate for the
        declared ``allocation_policy_type``.
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
    final_value_target_values: tuple[Decimal, ...] | None = None
    glidepath_start_values: tuple[Decimal, ...] | None = None
    glidepath_end_values: tuple[Decimal, ...] | None = None
    glidepath_slope_values: tuple[Decimal, ...] | None = None
    glidepath_mode_values: tuple[str, ...] | None = None
    explicit_configurations: tuple[dict[str, Any], ...] | None = None
    # Part 42 OMY parameters (None when OMY is not configured)
    omy_contribution_amount: Decimal | None = None
    omy_equity_weight: Decimal | None = None
    omy_bond_weight: Decimal | None = None
    omy_original_initial_wealth: Decimal | None = None

    @classmethod
    def from_yaml(cls, data: dict[str, Any]) -> StudyConfiguration:
        """Parse a validated ``StudyConfiguration`` from raw study YAML.

        Raises
        ------
        ValueError
            For any structurally invalid or unsupported study declaration,
            including any leftover v0.5 ``parameters`` / ``window_years`` /
            ``cohorts.type`` keys, or ambiguous simultaneous use of
            ``configurations`` and axis-based policy parameters.
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
        if not isinstance(allocation_policy_type, str):
            raise ValueError("allocation_policy.type must be a string")
        allocation_policy_enum = AllocationPolicyType.from_yaml_name(allocation_policy_type)

        allocation_policy_values: tuple[Decimal, ...] = ()
        glidepath_start_values: tuple[Decimal, ...] | None = None
        glidepath_end_values: tuple[Decimal, ...] | None = None
        glidepath_slope_values: tuple[Decimal, ...] | None = None
        glidepath_mode_values: tuple[str, ...] | None = None
        explicit_configurations: tuple[dict[str, Any], ...] | None = None

        raw_configurations = allocation_policy.get("configurations")
        has_axis_arrays = False

        if allocation_policy_enum is AllocationPolicyType.GLIDEPATH:
            glidepath_start_values = _parse_optional_decimal_array(
                allocation_policy, "start_equity"
            )
            glidepath_end_values = _parse_optional_decimal_array(
                allocation_policy, "end_equity"
            )
            glidepath_slope_values = _parse_optional_decimal_array(
                allocation_policy, "slope"
            )
            glidepath_mode_values = _parse_optional_string_array(
                allocation_policy, "mode"
            )
            has_axis_arrays = any(
                v is not None
                for v in (
                    glidepath_start_values,
                    glidepath_end_values,
                    glidepath_slope_values,
                    glidepath_mode_values,
                )
            )
        else:
            allocation_policy_values = _parse_optional_decimal_array(
                allocation_policy, "equity_allocation"
            ) or ()
            has_axis_arrays = bool(allocation_policy.get("equity_allocation"))

        if raw_configurations is not None:
            if has_axis_arrays:
                raise ValueError(
                    "allocation_policy.configurations and axis-based policy "
                    "parameters are mutually exclusive; use one or the other, "
                    "not both"
                )
            if not isinstance(raw_configurations, list) or not raw_configurations:
                raise ValueError(
                    "allocation_policy.configurations must be a non-empty list "
                    "of parameter dictionaries"
                )
            parsed_configs: list[dict[str, Any]] = []
            for i, entry in enumerate(raw_configurations):
                if not isinstance(entry, dict):
                    raise ValueError(
                        f"allocation_policy.configurations[{i}] must be a mapping"
                    )
                parsed_configs.append(entry)
            explicit_configurations = tuple(parsed_configs)
        elif allocation_policy_enum is AllocationPolicyType.GLIDEPATH:
            if glidepath_start_values is None:
                raise ValueError(
                    "allocation_policy.start_equity is required for "
                    "GlidepathAllocationPolicy"
                )
            if glidepath_end_values is None:
                raise ValueError(
                    "allocation_policy.end_equity is required for "
                    "GlidepathAllocationPolicy"
                )
            if glidepath_slope_values is None:
                raise ValueError(
                    "allocation_policy.slope is required for "
                    "GlidepathAllocationPolicy"
                )
            if glidepath_mode_values is None:
                raise ValueError(
                    "allocation_policy.mode is required for "
                    "GlidepathAllocationPolicy"
                )

        withdrawal_policy = data.get("withdrawal_policy")
        if not isinstance(withdrawal_policy, dict):
            raise ValueError("withdrawal_policy must be a mapping")
        withdrawal_policy_type = withdrawal_policy.get("type")
        if not isinstance(withdrawal_policy_type, str):
            raise ValueError("withdrawal_policy.type must be a string")
        WithdrawalPolicyType.from_yaml_name(withdrawal_policy_type)
        withdrawal_policy_values = _parse_decimal_values(
            withdrawal_policy, "withdrawal_rate"
        )

        final_value_target_values = _parse_optional_decimal_array(
            data, "final_value_target"
        )

        # Parse optional OMY configuration
        omy_data = data.get("omy")
        omy_contribution_amount: Decimal | None = None
        omy_equity_weight: Decimal | None = None
        omy_bond_weight: Decimal | None = None
        omy_original_initial_wealth: Decimal | None = None
        if omy_data is not None:
            if not isinstance(omy_data, dict):
                raise ValueError("omy must be a mapping")
            omy_contribution_amount = _parse_optional_decimal_scalar(
                omy_data, "contribution_amount"
            )
            omy_equity_weight = _parse_optional_decimal_scalar(
                omy_data, "equity_weight"
            )
            omy_bond_weight = _parse_optional_decimal_scalar(
                omy_data, "bond_weight"
            )
            omy_original_initial_wealth = _parse_optional_decimal_scalar(
                omy_data, "original_initial_wealth"
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
            final_value_target_values=final_value_target_values,
            glidepath_start_values=glidepath_start_values,
            glidepath_end_values=glidepath_end_values,
            glidepath_slope_values=glidepath_slope_values,
            glidepath_mode_values=glidepath_mode_values,
            explicit_configurations=explicit_configurations,
            omy_contribution_amount=omy_contribution_amount,
            omy_equity_weight=omy_equity_weight,
            omy_bond_weight=omy_bond_weight,
            omy_original_initial_wealth=omy_original_initial_wealth,
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

    Two modes are supported:

    **Mode A — Cartesian product (default):**
    For CONSTANT allocation: Cartesian product of
    ``equity_allocation`` x ``withdrawal_rate`` x ``horizon_years``.
    For GLIDEPATH allocation: Cartesian product of
    ``glidepath_start`` x ``glidepath_end`` x ``glidepath_slope`` x
    ``glidepath_mode`` x ``withdrawal_rate`` x ``horizon_years``.

    **Mode B — Explicit configurations:**
    When ``config.explicit_configurations`` is set, each dict is converted
    to a base ``ParameterConfiguration`` and crossed with the
    ``withdrawal_rate`` and ``horizon_years`` axes.  The ``final_value_target``
    axis is also crossed when present.
    """
    if config.explicit_configurations is not None:
        return _build_configs_from_explicit(config)

    if config.allocation_policy_type == "GlidepathAllocationPolicy":
        axes = [
            ParameterAxis(
                name="glidepath_start",
                values=tuple(float(v) for v in (config.glidepath_start_values or ())),
            ),
            ParameterAxis(
                name="glidepath_end",
                values=tuple(float(v) for v in (config.glidepath_end_values or ())),
            ),
            ParameterAxis(
                name="glidepath_slope",
                values=tuple(float(v) for v in (config.glidepath_slope_values or ())),
            ),
            ParameterAxis(
                name="glidepath_mode",
                values=tuple(config.glidepath_mode_values or ()),
            ),
        ]
    else:
        axes = [
            ParameterAxis(
                name="equity_allocation",
                values=tuple(float(value) for value in config.allocation_policy_values),
            ),
        ]
    axes.extend([
        ParameterAxis(
            name="withdrawal_rate",
            values=tuple(float(value) for value in config.withdrawal_policy_values),
        ),
        ParameterAxis(
            name="horizon_years",
            values=tuple(int(value) for value in config.horizon_years),
        ),
    ])
    if config.final_value_target_values is not None:
        axes.append(
            ParameterAxis(
                name="final_value_target",
                values=tuple(float(value) for value in config.final_value_target_values),
            )
        )
    return ParameterSweepEngine.cartesian_product(axes)


def _build_configs_from_explicit(
    config: StudyConfiguration,
) -> tuple[ParameterConfiguration, ...]:
    """Build parameter configurations from explicit policy configuration dicts.

    Each dict in ``config.explicit_configurations`` becomes the policy-specific
    portion of a base ``ParameterConfiguration``.  The base is then crossed
    with the ``withdrawal_rate``, ``horizon_years``, and optional
    ``final_value_target`` axes.
    """
    assert config.explicit_configurations is not None

    withdrawal_axis = ParameterAxis(
        name="withdrawal_rate",
        values=tuple(float(v) for v in config.withdrawal_policy_values),
    )
    horizon_axis = ParameterAxis(
        name="horizon_years",
        values=tuple(int(v) for v in config.horizon_years),
    )
    shared_axes = [withdrawal_axis, horizon_axis]
    if config.final_value_target_values is not None:
        shared_axes.append(
            ParameterAxis(
                name="final_value_target",
                values=tuple(float(v) for v in config.final_value_target_values),
            )
        )

    base_configs = []
    _SCALAR_TYPES = (bool, int, float, str)
    for i, entry in enumerate(config.explicit_configurations):
        values: dict[str, Any] = {}
        for key, raw_value in entry.items():
            if isinstance(raw_value, _SCALAR_TYPES):
                values[key] = raw_value
            elif isinstance(raw_value, Decimal):
                values[key] = float(raw_value)
            else:
                raise ValueError(
                    f"explicit_configurations[{i}].{key}: unsupported type "
                    f"{type(raw_value).__name__}"
                )
        if not values:
            raise ValueError(
                f"explicit_configurations[{i}] must contain at least one parameter"
            )
        base_configs.append(ParameterConfiguration(values))

    result: list[ParameterConfiguration] = []
    for base in base_configs:
        for combination in ParameterSweepEngine.cartesian_product(shared_axes):
            merged = dict(base.values)
            merged.update(combination.values)
            result.append(ParameterConfiguration(merged))
    return tuple(result)


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

    Policies are pure functions of their parameters, so one instance is
    shared per distinct parameter set (nothing mutates a policy after
    construction), keeping plan building memory-bounded.
    """
    _alloc_by_weight: dict[Decimal, AllocationPolicy] = {}
    _alloc_glidepath: dict[tuple[Decimal, Decimal, Decimal, str], AllocationPolicy] = {}
    _withdraw_by_rate: dict[Decimal, WithdrawalPolicy] = {}

    def resolve(
        param_config: ParameterConfiguration,
    ) -> tuple[AllocationPolicy, WithdrawalPolicy]:
        if config.allocation_policy_type == "GlidepathAllocationPolicy":
            if config.explicit_configurations is not None:
                start = Decimal(str(param_config.get("start_equity")))
                end = Decimal(str(param_config.get("end_equity")))
                slope = Decimal(str(param_config.get("slope")))
                mode = str(param_config.get("mode"))
            else:
                start = Decimal(str(param_config.get("glidepath_start")))
                end = Decimal(str(param_config.get("glidepath_end")))
                slope = Decimal(str(param_config.get("glidepath_slope")))
                mode = str(param_config.get("glidepath_mode"))
            key = (start, end, slope, mode)
            resolved_alloc = _alloc_glidepath.get(key)
            if resolved_alloc is None:
                resolved_alloc = build_glidepath_allocation_policy(start, end, slope, mode)
                _alloc_glidepath[key] = resolved_alloc
        else:
            weight = Decimal(str(param_config.get("equity_allocation")))
            resolved_alloc = _alloc_by_weight.get(weight)
            if resolved_alloc is None:
                resolved_alloc = build_allocation_policy(
                    config.allocation_policy_type, weight
                )
                _alloc_by_weight[weight] = resolved_alloc
        rate = Decimal(str(param_config.get("withdrawal_rate")))
        resolved_withd = _withdraw_by_rate.get(rate)
        if resolved_withd is None:
            resolved_withd = build_withdrawal_policy(config.withdrawal_policy_type, rate)
            _withdraw_by_rate[rate] = resolved_withd
        return resolved_alloc, resolved_withd

    return resolve


def _make_target_resolver(
    config: StudyConfiguration,
) -> Callable[[ParameterConfiguration], Decimal | None]:
    """Per-configuration final-value target from the study's declared value array.

    Returns ``None`` when no ``final_value_target`` axis is declared.
    """
    if config.final_value_target_values is None:
        return lambda param_config: None

    def resolve(param_config: ParameterConfiguration) -> Decimal | None:
        raw = param_config.get("final_value_target")
        if raw is None:
            return None
        return Decimal(str(raw))

    return resolve


def _representative_policies(
    config: StudyConfiguration,
) -> tuple[AllocationPolicy, WithdrawalPolicy]:
    """Policies built from the first declared value of each array.

    These are the experiment-definition policy snapshot used for persistence;
    per-unit policies always come from each unit's parameter configuration.
    """
    representative_alloc: AllocationPolicy
    if config.allocation_policy_type == "GlidepathAllocationPolicy":
        if config.explicit_configurations is not None:
            first = config.explicit_configurations[0]
            representative_alloc = build_glidepath_allocation_policy(
                start_equity=Decimal(str(first["start_equity"])),
                end_equity=Decimal(str(first["end_equity"])),
                slope=Decimal(str(first["slope"])),
                mode=str(first["mode"]),
            )
        else:
            assert config.glidepath_start_values is not None
            assert config.glidepath_end_values is not None
            assert config.glidepath_slope_values is not None
            assert config.glidepath_mode_values is not None
            representative_alloc = build_glidepath_allocation_policy(
                start_equity=config.glidepath_start_values[0],
                end_equity=config.glidepath_end_values[0],
                slope=config.glidepath_slope_values[0],
                mode=config.glidepath_mode_values[0],
            )
    else:
        if config.explicit_configurations is not None:
            first = config.explicit_configurations[0]
            representative_alloc = build_allocation_policy(
                config.allocation_policy_type,
                Decimal(str(first["equity_allocation"])),
            )
        else:
            representative_alloc = build_allocation_policy(
                config.allocation_policy_type, config.allocation_policy_values[0]
            )
    return (
        representative_alloc,
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
        target_resolver=_make_target_resolver(config),
    )
    return BuiltStudy(
        plan=plan,
        experiment_definition=experiment_def,
        cohorts=cohorts,
        param_configs=param_configs,
    )

StudyPlanResult = BuiltStudy


# ---------------------------------------------------------------------------
# Part 42 OMY study-plan builder
#
# Builds a research plan with accumulation pre-processing. For N cohorts
# × M SWR rates: N accumulation executions (once per cohort), N×M retirement
# executions.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OmyStudyConfiguration:
    """Configuration for a Part 42 OMY study.

    Parameters
    ----------
    base_config :
        The base study configuration (dataset, withdrawal, horizon, etc.).
    contribution_amount :
        Monthly contribution amount (constant real).
    equity_weight :
        Target equity allocation weight for accumulation.
    bond_weight :
        Target bond allocation weight for accumulation.
    original_initial_wealth :
        The pre-accumulation initial wealth ($2M for Part 42).
    fv_target_fraction :
        Final-value target as a fraction of original_initial_wealth.
    """

    base_config: StudyConfiguration
    contribution_amount: Money
    equity_weight: Decimal
    bond_weight: Decimal
    original_initial_wealth: Money
    fv_target_fraction: Decimal


def _make_omy_horizon_resolver(
    retirement_horizon_years: int,
) -> Callable[[ParameterConfiguration], int]:
    """Horizon resolver for OMY retirement: fixed horizon, no accumulation."""

    def resolve(param_config: ParameterConfiguration) -> int:
        return retirement_horizon_years * 12 + 1

    return resolve


def build_omy_study_plan(
    config: OmyStudyConfiguration,
    data_dir: str | None,
) -> BuiltStudy:
    """Build a research plan with accumulation pre-processing.

    For each cohort:
      1. Run 12-month accumulation (once, cached per cohort).
      2. Generate retirement units with the accumulated portfolio.

    The accumulation result is cached by cohort start date. All other
    accumulation inputs (contribution, weights, initial portfolio) are
    assumed invariant for Part 42.
    """
    from fbf.core.domain.model.asset import AssetClass
    from fbf.core.study.internal.accumulation import run_accumulation_phase

    equity_asset = AssetClass(id="equity", name="", description="")
    bond_asset = AssetClass(id="bond", name="", description="")

    dataset = resolve_dataset(config.base_config.dataset_identifier, data_dir)

    # For OMY: the full horizon is accumulation (12) + retirement (30y).
    # The dataset must contain enough snapshots for the full horizon.
    retirement_horizon_years = max(config.base_config.horizon_years)
    total_horizon_months = 12 + retirement_horizon_years * 12 + 1

    cohorts = build_cohort_specs(dataset, total_horizon_months)
    if not cohorts:
        raise ValueError(
            f"Dataset {config.base_config.dataset_identifier!r} is too small "
            f"for {retirement_horizon_years + 1}-year OMY horizon"
        )

    param_configs = _build_unified_parameter_configs(config.base_config)

    # Accumulation: once per cohort, cached by start_date.
    accumulation_cache: dict[date, Portfolio] = {}
    accumulation_month_by_month: dict[date, tuple[Portfolio, ...]] = {}

    target_weights = {equity_asset: config.equity_weight, bond_asset: config.bond_weight}
    initial_portfolio = build_initial_portfolio(config.original_initial_wealth)

    for cohort in cohorts:
        start = cohort.start_date
        if start not in accumulation_cache:
            acc_dataset = dataset.slice(start, 13)
            result = run_accumulation_phase(
                initial_portfolio=initial_portfolio,
                contribution=config.contribution_amount,
                target_weights=target_weights,
                dataset=acc_dataset,
                equity_asset=equity_asset,
                bond_asset=bond_asset,
            )
            accumulation_cache[start] = result.final_portfolio
            accumulation_month_by_month[start] = result.month_by_month

    # Verify accumulation uniqueness: exactly N executions for N cohorts
    assert len(accumulation_cache) == len(cohorts)

    # Build retirement plan using accumulated portfolios.
    # For each cohort, the retirement dataset starts at cohort.start_date
    # and the initial_portfolio is the accumulated result.
    retirement_plan = _build_omy_retirement_plan(
        config=config,
        dataset=dataset,
        cohorts=cohorts,
        param_configs=param_configs,
        accumulation_cache=accumulation_cache,
    )

    return retirement_plan


def _build_omy_retirement_plan(
    *,
    config: OmyStudyConfiguration,
    dataset: Dataset,
    cohorts: tuple[CohortSpecification, ...],
    param_configs: tuple[ParameterConfiguration, ...],
    accumulation_cache: dict[date, Portfolio],
) -> BuiltStudy:
    """Build the retirement phase plan using accumulated portfolios."""
    from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan
    retirement_horizon_years = max(config.base_config.horizon_years)
    retirement_horizon_months = retirement_horizon_years * 12 + 1

    representative_allocation, representative_withdrawal = _representative_policies(
        config.base_config
    )

    experiment_def = ExperimentDefinition(
        name=config.base_config.name,
        description=config.base_config.description or config.base_config.name,
        dataset=dataset,
        horizon_months=retirement_horizon_months,
        initial_wealth=config.contribution_amount,  # placeholder; per-unit is set below
        cohorts=cohorts,
        allocation_policies=(representative_allocation,),
        withdrawal_policies=(representative_withdrawal,),
    )

    # Build units: for each (cohort, param_config), the initial_portfolio
    # is the accumulated result for that cohort.
    dataset_cache: dict[tuple[date, int], Dataset] = {}
    units: list[PlannedSimulationUnit] = []
    for cohort in cohorts:
        acc_portfolio = accumulation_cache[cohort.start_date]
        for param_config in param_configs:
            horizon_months = retirement_horizon_months
            alloc_policy, withdrawal_policy = _make_policy_resolver(config.base_config)(
                param_config
            )
            final_value_target = _make_target_resolver(config.base_config)(param_config)
            cache_key = (cohort.start_date, horizon_months)
            if cache_key not in dataset_cache:
                dataset_cache[cache_key] = dataset.slice(
                    cohort.start_date, horizon_months
                )
            units.append(
                PlannedSimulationUnit(
                    cohort=cohort,
                    parameter_config=param_config,
                    allocation_policy=alloc_policy,
                    withdrawal_policy=withdrawal_policy,
                    initial_portfolio=acc_portfolio,
                    dataset=dataset_cache[cache_key],
                    horizon_months=horizon_months,
                    final_value_target=final_value_target,
                )
            )

    plan = ResearchPlan(experiment_definition=experiment_def, units=tuple(units))
    return BuiltStudy(
        plan=plan,
        experiment_definition=experiment_def,
        cohorts=cohorts,
        param_configs=param_configs,
    )
