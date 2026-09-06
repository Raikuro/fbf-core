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


def load_ffr_rates(
    ffr_dataset_identifier: str, data_dir: str | None
) -> tuple[tuple[date, Decimal], ...]:
    """Load an FFR (Federal Funds Rate) dataset from a JSON file.

    The FFR dataset is a rate-only time series (not a ``MarketSnapshot``).
    It is loaded directly from the data directory, bypassing the standard
    ``Dataset`` loader.

    Parameters
    ----------
    ffr_dataset_identifier:
        Filename stem of the FFR JSON file (e.g. ``"ffr_monthly"``).
    data_dir:
        Directory containing the FFR JSON file. Must be provided explicitly.

    Returns
    -------
    tuple[tuple[date, Decimal], ...]
        Ordered (date, annual_rate) pairs from the FFR dataset.

    Raises
    ------
    FileNotFoundError
        If the FFR dataset file does not exist.
    ValueError
        If the file format is invalid.
    """
    if data_dir is None:
        raise ValueError(
            "data_dir is required for FFR dataset resolution"
        )
    ffr_path = Path(data_dir) / f"{ffr_dataset_identifier}.json"
    if not ffr_path.exists():
        raise FileNotFoundError(
            f"FFR dataset not found: {ffr_path}"
        )

    import json

    raw = json.loads(ffr_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "rates" not in raw:
        raise ValueError(
            f"FFR dataset {ffr_path} must contain a 'rates' key"
        )
    if not isinstance(raw["rates"], list):
        raise ValueError(
            f"FFR dataset {ffr_path} 'rates' must be a list"
        )

    rates: list[tuple[date, Decimal]] = []
    for entry in raw["rates"]:
        d = date.fromisoformat(entry["date"])
        r = Decimal(str(entry["rate"]))
        rates.append((d, r))

    if not rates:
        raise ValueError(f"FFR dataset {ffr_path} contains no rates")
    return tuple(rates)


def build_interest_rate_schedule(
    ffr_rates: tuple[tuple[date, Decimal], ...],
    spread: Decimal,
    start_date: date,
    horizon_months: int,
) -> tuple[Decimal, ...]:
    """Build an interest rate schedule from FFR data + spread.

    Maps FFR rates to simulation periods by date alignment. The FFR rate
    for month M is the rate observed in month M (no lag/lead).

    Parameters
    ----------
    ffr_rates:
        Ordered (date, annual_rate) pairs from the FFR dataset.
    spread:
        Spread to add to each FFR rate (e.g. 0.0050 for FFR + 0.50%).
    start_date:
        Start date of the simulation cohort.
    horizon_months:
        Number of months in the simulation horizon.

    Returns
    -------
    tuple[Decimal, ...]
        Per-period annual interest rates (FFR + spread) for the simulation.

    Raises
    ------
    ValueError
        If the FFR dataset does not cover the required period.
    """
    # Build date -> rate lookup
    rate_map: dict[date, Decimal] = dict(ffr_rates)
    available_dates = sorted(rate_map.keys())
    earliest = available_dates[0] if available_dates else None
    latest = available_dates[-1] if available_dates else None

    schedule: list[Decimal] = []
    import calendar

    for month_idx in range(horizon_months):
        # Calculate period date by adding months
        total_months = (start_date.year * 12 + start_date.month - 1) + month_idx
        year = total_months // 12
        month = total_months % 12 + 1
        day = min(start_date.day, calendar.monthrange(year, month)[1])
        period_date = date(year, month, day)

        rate = rate_map.get(period_date)
        if rate is None:
            raise ValueError(
                f"No FFR rate available for {period_date}. "
                f"Available range: {earliest} to {latest}. "
                f"Requested start_date={start_date}, horizon_months={horizon_months}, "
                f"period_date={period_date}. "
                f"Provide FFR data covering the full simulation period, or restrict "
                f"cohorts to dates within the available rate dataset."
            )
        schedule.append(rate + spread)

    return tuple(schedule)


def build_cohort_specs(
    dataset: Dataset, horizon_months: int
) -> tuple[CohortSpecification, ...]:
    """Generate all horizon-feasible rolling monthly cohorts from *dataset*."""
    return CohortGenerator.generate_rolling_monthly(dataset, horizon_months)


def build_initial_portfolio(initial_wealth: Money, dataset: Dataset) -> Portfolio:
    """Build an ``Portfolio`` representing the initial wealth.

    Derives asset classes from the dataset's initial snapshot and constructs
    holdings so that the portfolio value at that snapshot equals
    ``initial_wealth`` exactly:

    ``units_i = (initial_wealth × weight_i) / price_i[0]``

    where ``weight_i = 1 / n_assets`` for each asset class.

    This ensures the invariant:

    ``portfolio_value_at_snapshot[0] == initial_wealth``

    The month-0 allocation policy rebalances to its target split afterward.
    """
    initial_snapshot = dataset[0]
    asset_classes = list(initial_snapshot.index_levels.keys())

    n_assets = len(asset_classes)
    weight = Decimal("1") / Decimal(str(n_assets))

    holdings = []
    for asset_class in asset_classes:
        price = initial_snapshot.index_levels[asset_class]
        units = (initial_wealth.amount * weight) / price
        holdings.append(AssetHolding(asset_class=asset_class, units=units))

    return Portfolio(holdings=tuple(holdings))


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


def build_withdrawal_policy(
    policy_type: str,
    scalar: Decimal,
    *,
    borrow_pct: Decimal | None = None,
    drawdown_threshold: Decimal | None = None,
) -> WithdrawalPolicy:
    """Build a WithdrawalPolicy from its YAML type name and scalar value."""
    policy_enum = WithdrawalPolicyType.from_yaml_name(policy_type)
    if policy_enum is WithdrawalPolicyType.FIXED_REAL:
        return FixedRealWithdrawalPolicy(withdrawal_rate=scalar)
    if policy_enum is WithdrawalPolicyType.CONSTANT:
        return ConstantWithdrawalPolicy(withdrawal_rate=scalar)
    if policy_enum is WithdrawalPolicyType.PART49:
        from fbf.core.domain.policies.part49_withdrawal import Part49WithdrawalPolicy
        return Part49WithdrawalPolicy(withdrawal_rate=scalar)
    if policy_enum is WithdrawalPolicyType.PART52:
        return build_part52_withdrawal_policy(
            withdrawal_rate=scalar,
            borrow_pct=borrow_pct or Decimal("0"),
            drawdown_threshold=drawdown_threshold or Decimal("0.20"),
        )
    raise ValueError(f"Unsupported withdrawal policy type: {policy_type!r}")


def build_part52_withdrawal_policy(
    withdrawal_rate: Decimal,
    borrow_pct: Decimal,
    drawdown_threshold: Decimal,
) -> WithdrawalPolicy:
    """Build a Part52WithdrawalPolicy from its three parameters."""
    from fbf.core.domain.policies.part52_withdrawal import Part52WithdrawalPolicy
    return Part52WithdrawalPolicy(
        withdrawal_rate=withdrawal_rate,
        borrow_pct=borrow_pct,
        drawdown_threshold=drawdown_threshold,
    )


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
    # Optional: specify a different horizon for cohort generation.
    # ERN uses a fixed cohort set determined by the longest horizon (60y)
    # across ALL studies for comparability. When set, cohorts are generated
    # for this horizon even if the actual simulation horizons are shorter.
    cohort_horizon_years: int | None = None
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
    # Part 49 debt parameters (None when leverage is not configured)
    # debt_interest_rate is the legacy scalar; debt_interest_rate_values is the
    # new array form for grid-axis support. When values is set, it takes precedence.
    debt_interest_rate: Decimal | None = None
    debt_interest_rate_values: tuple[Decimal, ...] | None = None
    debt_ltv_limit: Decimal | None = None
    debt_ltv_enforcement: bool = True
    debt_loan_draw_rate: Decimal | None = None
    # Part 52 timing-leverage parameters
    debt_borrow_pct: Decimal | None = None
    debt_borrow_pct_values: tuple[Decimal, ...] | None = None
    debt_drawdown_threshold: Decimal | None = None
    debt_drawdown_threshold_values: tuple[Decimal, ...] | None = None
    # S6.2 FFR integration parameters
    ffr_dataset_identifier: str | None = None
    ffr_spread: Decimal | None = None

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

        # Parse optional debt (Part 49) configuration
        debt_data = data.get("debt")
        debt_interest_rate: Decimal | None = None
        debt_interest_rate_values: tuple[Decimal, ...] | None = None
        debt_ltv_limit: Decimal | None = None
        debt_ltv_enforcement: bool = True
        debt_loan_draw_rate: Decimal | None = None
        # Part 52 timing-leverage parameters
        debt_borrow_pct: Decimal | None = None
        debt_borrow_pct_values: tuple[Decimal, ...] | None = None
        debt_drawdown_threshold: Decimal | None = None
        debt_drawdown_threshold_values: tuple[Decimal, ...] | None = None
        # S6.2 FFR integration parameters
        ffr_dataset_identifier: str | None = None
        ffr_spread: Decimal | None = None
        if debt_data is not None:
            if not isinstance(debt_data, dict):
                raise ValueError("debt must be a mapping")
            # Support both scalar and array forms for interest_rate
            raw_ir = debt_data.get("interest_rate")
            if isinstance(raw_ir, list):
                debt_interest_rate_values = tuple(
                    Decimal(str(v)) for v in raw_ir
                )
            elif raw_ir is not None:
                debt_interest_rate = _parse_optional_decimal_scalar(
                    debt_data, "interest_rate"
                )
            debt_ltv_limit = _parse_optional_decimal_scalar(
                debt_data, "ltv_limit"
            )
            debt_ltv_enforcement = debt_data.get("ltv_enforcement", True)
            if not isinstance(debt_ltv_enforcement, bool):
                raise ValueError("debt.ltv_enforcement must be a boolean")
            debt_loan_draw_rate = _parse_optional_decimal_scalar(
                debt_data, "loan_draw_rate"
            )
            # Validate coherence: loan_draw_rate requires interest_rate
            has_interest = (
                debt_interest_rate is not None
                or debt_interest_rate_values is not None
            )
            if debt_loan_draw_rate is not None and not has_interest:
                raise ValueError(
                    "debt.interest_rate is required when debt.loan_draw_rate "
                    "is set; the loan draw step requires a non-zero interest "
                    "rate to activate"
                )

            # Parse Part 52 timing-leverage parameters
            raw_borrow_pct = debt_data.get("borrow_pct")
            if isinstance(raw_borrow_pct, list):
                debt_borrow_pct_values = tuple(
                    Decimal(str(v)) for v in raw_borrow_pct
                )
            elif raw_borrow_pct is not None:
                debt_borrow_pct = _parse_optional_decimal_scalar(
                    debt_data, "borrow_pct"
                )
            raw_drawdown_threshold = debt_data.get("drawdown_threshold")
            if isinstance(raw_drawdown_threshold, list):
                debt_drawdown_threshold_values = tuple(
                    Decimal(str(v)) for v in raw_drawdown_threshold
                )
            elif raw_drawdown_threshold is not None:
                debt_drawdown_threshold = _parse_optional_decimal_scalar(
                    debt_data, "drawdown_threshold"
                )

            # Parse S6.2 FFR integration parameters
            raw_ffr = debt_data.get("ffr")
            if isinstance(raw_ffr, dict):
                ffr_dataset_identifier = raw_ffr.get("dataset_identifier")
                if ffr_dataset_identifier is not None:
                    ffr_dataset_identifier = str(ffr_dataset_identifier)
                raw_spread = raw_ffr.get("spread")
                if raw_spread is not None:
                    ffr_spread = Decimal(str(raw_spread))

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
            debt_interest_rate=debt_interest_rate,
            debt_interest_rate_values=debt_interest_rate_values,
            debt_ltv_limit=debt_ltv_limit,
            debt_ltv_enforcement=debt_ltv_enforcement,
            debt_loan_draw_rate=debt_loan_draw_rate,
            debt_borrow_pct=debt_borrow_pct,
            debt_borrow_pct_values=debt_borrow_pct_values,
            debt_drawdown_threshold=debt_drawdown_threshold,
            debt_drawdown_threshold_values=debt_drawdown_threshold_values,
            ffr_dataset_identifier=ffr_dataset_identifier,
            ffr_spread=ffr_spread,
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
    # Generic interest-rate axis: when multiple values are provided, they become
    # a grid dimension (like equity_allocation or withdrawal_rate).  A single
    # value is still treated as a one-element axis so the resolver works uniformly.
    if config.debt_interest_rate_values is not None:
        axes.append(
            ParameterAxis(
                name="interest_rate",
                values=tuple(float(v) for v in config.debt_interest_rate_values),
            )
        )
    elif config.debt_interest_rate is not None:
        axes.append(
            ParameterAxis(
                name="interest_rate",
                values=(float(config.debt_interest_rate),),
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
            resolved_withd = build_withdrawal_policy(
                config.withdrawal_policy_type,
                rate,
                borrow_pct=config.debt_borrow_pct,
                drawdown_threshold=config.debt_drawdown_threshold,
            )
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


def _make_interest_rate_resolver(
    config: StudyConfiguration,
) -> Callable[[ParameterConfiguration], Decimal | None]:
    """Per-configuration interest rate resolver.

    Returns ``None`` when leverage is not configured, making debt steps no-ops.
    When the ``interest_rate`` axis exists in the parameter configuration, the
    value is extracted from it.  Otherwise falls back to the scalar
    ``debt_interest_rate``.
    """

    def resolve(param_config: ParameterConfiguration) -> Decimal | None:
        try:
            raw = param_config.get("interest_rate")
        except KeyError:
            raw = None
        if raw is not None:
            return Decimal(str(raw))
        return config.debt_interest_rate

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
    # Cohort horizon: use cohort_horizon_years if set, otherwise longest horizon.
    # ERN uses a fixed cohort set determined by the longest horizon (60y) across
    # ALL studies for comparability. When cohort_horizon_years is set, cohorts
    # are generated for this horizon even if the actual simulation horizons are shorter.
    if config.cohort_horizon_years is not None:
        cohort_horizon_months = config.cohort_horizon_years * 12 + 1
    else:
        longest_horizon_years = _longest_horizon_years(config)
        cohort_horizon_months = longest_horizon_years * 12 + 1
    cohorts = build_cohort_specs(dataset, cohort_horizon_months)
    if not cohorts:
        raise ValueError(
            f"Dataset {config.dataset_identifier!r} is too small for a "
            f"{config.cohort_horizon_years or _longest_horizon_years(config)}-year "
            f"({cohort_horizon_months}-observation) horizon"
        )
    param_configs = _build_unified_parameter_configs(config)

    representative_allocation, representative_withdrawal = _representative_policies(config)

    experiment_def = ExperimentDefinition(
        name=config.name,
        description=config.description or config.name,
        dataset=dataset,
        horizon_months=cohort_horizon_months,
        initial_wealth=initial_wealth,
        cohorts=cohorts,
        allocation_policies=(representative_allocation,),
        withdrawal_policies=(representative_withdrawal,),
    )

    portfolio = build_initial_portfolio(initial_wealth, dataset)

    # Load FFR rates if configured
    ffr_rates: tuple[tuple[date, Decimal], ...] | None = None
    ffr_spread: Decimal | None = None
    if config.ffr_dataset_identifier is not None:
        ffr_rates = load_ffr_rates(config.ffr_dataset_identifier, data_dir)
        ffr_spread = config.ffr_spread if config.ffr_spread is not None else Decimal("0")

    plan = materialize_research_plan(
        experiment_def=experiment_def,
        canonical_trajectory=dataset,
        cohorts=cohorts,
        param_configs=param_configs,
        initial_portfolio=portfolio,
        horizon_resolver=_make_horizon_resolver(config),
        policy_resolver=_make_policy_resolver(config),
        target_resolver=_make_target_resolver(config),
        interest_rate_resolver=_make_interest_rate_resolver(config),
        ffr_rates=ffr_rates,
        ffr_spread=ffr_spread,
        ltv_limit=config.debt_ltv_limit,
        ltv_enforcement=config.debt_ltv_enforcement,
        loan_draw_rate=config.debt_loan_draw_rate,
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
    initial_portfolio = build_initial_portfolio(config.original_initial_wealth, dataset)

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
