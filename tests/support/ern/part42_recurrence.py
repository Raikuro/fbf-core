"""Independent Decimal recurrence for canonical Part 42 cohorts.

This module validates the production fixed-SWR path without importing any
production accumulation, research, or execution code.  It uses only the domain
value objects and ``decimal.Decimal``.

The recurrence deliberately mirrors the documented methodology:

* the initial portfolio is split equally across the assets in the cohort's
  first snapshot;
* contributions are applied, the portfolio is rebalanced to the target
  weights, and market evolution is applied for each accumulation month;
* retirement withdrawals use the original pre-OMY wealth as the fixed-real
  base, are applied before growth, and are combined with the scheduled Social
  Security inflow;
* depletion occurs only when a positive net cash flow exceeds the available
  value;
* the final-value target is an evaluation criterion applied after a surviving
  trajectory reaches the horizon.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset


@dataclass(frozen=True)
class Part42RecurrenceResult:
    """Independent outcome for one Part 42 cohort."""

    handoff_wealth: Decimal
    final_wealth: Decimal
    success: bool
    failure_month: int | None
    ss_start_period: int | None
    ss_end_period: int | None
    ss_payments_applied: int


def _asset_by_id(dataset: Dataset, index: int, asset_id: str) -> AssetClass:
    snapshot = dataset.snapshots[index]
    for asset in snapshot.index_levels:
        if asset.id == asset_id:
            return asset
    raise ValueError(f"Dataset snapshot is missing the {asset_id!r} asset class")


def simulate_part42_cohort(
    dataset: Dataset,
    *,
    cohort_index: int,
    total_horizon_months: int,
    omy_months: int,
    contribution_monthly: Decimal,
    initial_wealth: Decimal,
    withdrawal_rate: Decimal,
    equity_weight: Decimal,
    bond_weight: Decimal,
    final_value_target: Decimal,
    social_security: bool,
    ss_start_year: int,
    ss_monthly_amount: Decimal,
) -> Part42RecurrenceResult:
    """Run the independent Part 42 recurrence for one cohort.

    ``cohort_index`` indexes the canonical dataset snapshots.  The accumulation
    phase consumes ``omy_months`` transitions, and retirement consumes the
    remaining ``total_horizon_months - omy_months`` transitions.
    """
    if total_horizon_months <= 0:
        raise ValueError("total_horizon_months must be positive")
    if omy_months < 0:
        raise ValueError("omy_months must be non-negative")
    if omy_months >= total_horizon_months:
        raise ValueError("OMY must leave at least one retirement transition")
    if not 0 <= cohort_index < len(dataset.snapshots):
        raise ValueError("cohort_index is outside the dataset")

    total_snapshots = total_horizon_months + 1
    if cohort_index + total_snapshots > len(dataset.snapshots):
        raise ValueError("cohort has insufficient history for the total horizon")

    equity_asset = _asset_by_id(dataset, cohort_index, "equity")
    bond_asset = _asset_by_id(dataset, cohort_index, "bond")

    first = dataset.snapshots[cohort_index]
    asset_count = len(first.index_levels)
    equal_weight = Decimal("1") / Decimal(asset_count)
    eq_units = initial_wealth * equal_weight / first.index_levels[equity_asset]
    bd_units = initial_wealth * equal_weight / first.index_levels[bond_asset]

    for month in range(omy_months):
        snapshot = dataset.snapshots[cohort_index + month]
        next_snapshot = dataset.snapshots[cohort_index + month + 1]
        eq_price = snapshot.index_levels[equity_asset]
        bd_price = snapshot.index_levels[bond_asset]

        eq_units += contribution_monthly * equity_weight / eq_price
        bd_units += contribution_monthly * bond_weight / bd_price

        total_value = eq_units * eq_price + bd_units * bd_price
        eq_units = total_value * equity_weight / eq_price
        bd_units = total_value * bond_weight / bd_price

        eq_units *= next_snapshot.index_levels[equity_asset] / eq_price
        bd_units *= next_snapshot.index_levels[bond_asset] / bd_price

    retirement_index = cohort_index + omy_months
    retirement_snapshot = dataset.snapshots[retirement_index]
    handoff_wealth = (
        eq_units * retirement_snapshot.index_levels[equity_asset]
        + bd_units * retirement_snapshot.index_levels[bond_asset]
    )

    periods = total_horizon_months - omy_months
    monthly_withdrawal = initial_wealth * withdrawal_rate / Decimal("12")

    ss_start_period: int | None = None
    ss_end_period: int | None = None
    if social_security:
        ss_start_period = (ss_start_year - 1) * 12 - omy_months
        ss_end_period = periods
        if not 0 <= ss_start_period < ss_end_period:
            raise ValueError("Social Security has no payment period")

    value = handoff_wealth
    ss_payments_applied = 0
    for period in range(periods):
        snapshot = dataset.snapshots[retirement_index + period]
        next_snapshot = dataset.snapshots[retirement_index + period + 1]
        growth = (
            equity_weight
            * next_snapshot.index_levels[equity_asset]
            / snapshot.index_levels[equity_asset]
            + bond_weight
            * next_snapshot.index_levels[bond_asset]
            / snapshot.index_levels[bond_asset]
        )

        external = (
            ss_monthly_amount
            if social_security
            and ss_start_period is not None
            and ss_end_period is not None
            and ss_start_period <= period < ss_end_period
            else Decimal("0")
        )
        net_cash_flow = monthly_withdrawal - external
        if net_cash_flow > value:
            return Part42RecurrenceResult(
                handoff_wealth=handoff_wealth,
                final_wealth=Decimal("0"),
                success=False,
                failure_month=period + 1,
                ss_start_period=ss_start_period,
                ss_end_period=ss_end_period,
                ss_payments_applied=ss_payments_applied,
            )

        value = (value - net_cash_flow) * growth
        if external:
            ss_payments_applied += 1

    return Part42RecurrenceResult(
        handoff_wealth=handoff_wealth,
        final_wealth=value,
        success=value >= initial_wealth * final_value_target,
        failure_month=None,
        ss_start_period=ss_start_period,
        ss_end_period=ss_end_period,
        ss_payments_applied=ss_payments_applied,
    )


__all__ = ["Part42RecurrenceResult", "simulate_part42_cohort"]
