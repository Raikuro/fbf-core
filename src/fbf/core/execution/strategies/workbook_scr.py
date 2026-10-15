"""Workbook SCR (Safe Consumption Rate) computation for workbook fidelity.

This module implements the exact SCR formula from the SWR Toolbox v2.0.xlsx workbook.

Workbook Methodology (SWR_Toolbox_v2.0.xlsx):
- Monthly portfolio returns have fee EMBEDDED: AF_t = w_eq*eq_ret + w_bd*bd_ret - fee/12
- SCR = 1 / (Sum_{t=0..T-1} 1/P[t]) * 12  (for basic ERN: ct_r=0, ct_s=1, FV=0)
  Where P[t] = cumulative growth factor with fee embedded
- Final wealth: FV = growth_T - AI * (WR/12)
  Where growth_T = P[T], AI = growth_T * Sum_{t=0..T-1} 1/P[t]

Key difference from legacy implementation:
- Fee is EMBEDDED in monthly returns (compounds over time)
- NOT subtracted in SCR formula
"""

from __future__ import annotations

from decimal import Decimal

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.policies import ConstantAllocationPolicy
from fbf.core.execution.pipeline.simulation_context import SimulationContext


class InsufficientDataError(ValueError):
    """Raised when dataset doesn't have enough snapshots for workbook SCR."""
    pass


def compute_workbook_growth_factors(
    context: SimulationContext,
    horizon: int,
) -> tuple[dict[int, Decimal], Decimal]:
    """Compute cumulative growth factors P for a context (with fee embedded).

    Returns (P_dict, initial_value) where P_dict maps month index to Decimal growth factor.
    Month 0 = start date, P[0] = 1.

    Requires at least horizon + 1 snapshots (to compute T months of returns).
    """
    weights: dict[AssetClass, Decimal] = {}
    allocation = context.allocation_policy
    if isinstance(allocation, ConstantAllocationPolicy):
        for holding in context.initial_portfolio.holdings:
            if holding.asset_class.id == "equity":
                weights[holding.asset_class] = allocation.equity_allocation
            else:
                weights[holding.asset_class] = Decimal("1") - allocation.equity_allocation
    else:
        raise NotImplementedError("Only ConstantAllocationPolicy supported for workbook SCR")

    snapshots = context.dataset.snapshots
    if len(snapshots) < horizon + 1:
        raise InsufficientDataError(
            f"Dataset has {len(snapshots)} snapshots, need {horizon + 1} for workbook SCR"
        )

    fee_annual = context.expense_ratio or Decimal("0")
    fee_monthly = fee_annual / Decimal("12")

    # Compute monthly portfolio returns WITH FEE EMBEDDED
    monthly_returns = []
    for m in range(horizon):
        r = Decimal("0")
        for asset_class, weight in weights.items():
            idx_m = snapshots[m].index_levels[asset_class]
            idx_m1 = snapshots[m + 1].index_levels[asset_class]
            r += weight * (idx_m1 / idx_m - Decimal("1"))
        # Embed fee in monthly return
        r -= Decimal(str(fee_monthly))
        monthly_returns.append(r)

    # Build cumulative growth factors P (with fee embedded)
    P = {0: Decimal("1")}
    for m in range(1, horizon + 1):
        P[m] = P[m - 1] * (Decimal("1") + monthly_returns[m - 1])

    # Initial portfolio value at start date
    initial_value = Decimal("0")
    for holding in context.initial_portfolio.holdings:
        initial_value += holding.units * snapshots[0].index_levels[holding.asset_class]

    return P, initial_value


def compute_workbook_scr(
    P: dict[int, Decimal],
    start: int,
    T: int,
    fee_annual: Decimal,
    ct_r: Decimal = Decimal("0"),
    ct_s: Decimal = Decimal("1"),
) -> Decimal:
    """Compute SCR using workbook formula (fee embedded in P).

    For basic ERN (ct_r=0, ct_s=1, FV=0):
    SCR = 1 / (Sum_{t=0..T-1} 1/P[t]) * 12

    Where P[t] = cumulative growth factor with fee embedded.

    Parameters
    ----------
    P: Cumulative growth factors (P[0] = 1) WITH FEE EMBEDDED
    start: Start month index (0-based)
    T: Horizon in months (number of withdrawals)
    fee_annual: Annual fee (e.g., 0.0005 for 0.05%) - NOT USED, kept for API compatibility
    ct_r: Coefficient for AJ term (default 0 for basic ERN)
    ct_s: Coefficient for AI term (default 1 for basic ERN)

    Returns
    -------
    SCR as annual rate (e.g., 0.04 for 4%)
    """
    # For basic ERN: SCR = 1 / (Sum_{t=0..T-1} 1/P[t]) * 12
    # P[t] already includes fee
    sum_inv_P = sum(
        Decimal("1") / P[start + t] for t in range(T)
    )
    scr = Decimal("1") / sum_inv_P * Decimal("12")
    return scr


def workbook_scr_success(
    context: SimulationContext,
    target_rate: Decimal,
    fee_annual: Decimal = Decimal("0.0005"),
) -> bool:
    """Check if a context's cohort succeeds using workbook SCR methodology.

    Success if SCR >= target_rate.

    Parameters
    ----------
    context: SimulationContext with ConstantAllocationPolicy
    target_rate: Target annual withdrawal rate (e.g., 0.04 for 4%)
    fee_annual: Annual expense ratio (default 0.05%)

    Returns
    -------
    True if SCR >= target_rate for this cohort
    """
    horizon = context.horizon_months
    P, _ = compute_workbook_growth_factors(context, horizon)
    scr = compute_workbook_scr(P, 0, horizon, fee_annual)
    return scr >= target_rate
