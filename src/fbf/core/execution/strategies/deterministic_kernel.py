"""Numba kernel for deterministic two-asset trajectories.

The kernel tracks equity and bond units separately so that weights drift
between rebalance dates.  Withdrawals and rebalances occur at the beginning
of a period, after the prior period's growth and fee deduction.  The fee is
charged on the beginning-of-period portfolio value and is deducted from the
end-of-period value:

    V_t = V_{t-1} * (1 + g_t) - V_{t-1} * fee_annual / 12 - W_t

where ``g_t`` is the portfolio return between ``t-1`` and ``t``.  This is the
workbook convention used by ``SWR_Toolbox_v2.0.xlsx`` (``Case Study`` and
``Asset Returns``), not the legacy stale-base expense correction.

The kernel records post-withdrawal, post-rebalance values.  Growth for the
transition into month ``m`` is applied before the withdrawal at ``m``.  The
last snapshot has no subsequent growth.

Depletion semantics follow the existing optimized kernels: a withdrawal
strictly greater than the available value fails; an exact-boundary withdrawal
succeeds with value zero.  On failure the kernel returns the failure month and
the number of completed months, and the caller materializes only completed
months.
"""

from __future__ import annotations

import numba
import numpy as np
from numpy.typing import NDArray


@numba.njit(cache=True)
def simulate_deterministic_two_asset(
    equity_prices: NDArray[np.float64],
    bond_prices: NDArray[np.float64],
    target_equity_weights: NDArray[np.float64],
    rebalance_flags: NDArray[np.bool_],
    fixed_withdrawal_amounts: NDArray[np.float64],
    use_proportional_withdrawal: bool,
    proportional_rate: float,
    proportional_annual: bool,
    fee_annual: float,
    initial_wealth: float,
    initial_equity_weight: float,
    horizon: int,
    out_values: NDArray[np.float64],
    out_actual_equity_weights: NDArray[np.float64],
    out_target_equity_weights: NDArray[np.float64],
    out_withdrawals: NDArray[np.float64],
) -> tuple[float, bool, int, int]:
    """Simulate one deterministic two-asset trajectory.

    ``fixed_withdrawal_amounts`` is ignored when
    ``use_proportional_withdrawal`` is true.  ``proportional_annual`` selects
    a full annual rate at boundaries (``m % 12 == 0``) versus one twelfth every
    month.  The proportional withdrawal is based on the current portfolio value;
    fixed withdrawals are value-independent.

    Returns ``(final_value, success, failure_month, months_completed)``.
    On success ``failure_month == -1`` and ``months_completed == horizon``.
    """
    if horizon <= 0:
        return initial_wealth, True, -1, 0

    equity_price_0 = equity_prices[0]
    bond_price_0 = bond_prices[0]
    value = initial_wealth
    equity_units = value * initial_equity_weight / equity_price_0
    bond_units = value * (1.0 - initial_equity_weight) / bond_price_0

    monthly_rate = proportional_rate
    if not proportional_annual:
        monthly_rate = proportional_rate / 12.0

    withdrawal = 0.0
    if use_proportional_withdrawal:
        withdrawal = value * monthly_rate
    else:
        withdrawal = fixed_withdrawal_amounts[0]

    if withdrawal > value:
        return 0.0, False, 0, 0

    value -= withdrawal
    if rebalance_flags[0]:
        if value > 0.0:
            equity_units = value * target_equity_weights[0] / equity_price_0
            bond_units = value * (1.0 - target_equity_weights[0]) / bond_price_0
        else:
            equity_units = 0.0
            bond_units = 0.0
    elif initial_wealth > 0.0:
        scale = value / initial_wealth
        equity_units *= scale
        bond_units *= scale

    out_values[0] = value
    out_target_equity_weights[0] = target_equity_weights[0]
    out_withdrawals[0] = withdrawal
    if value > 0.0:
        actual_weight = equity_units * equity_price_0 / value
        if actual_weight < 0.0:
            actual_weight = 0.0
        elif actual_weight > 1.0:
            actual_weight = 1.0
        out_actual_equity_weights[0] = actual_weight
    else:
        out_actual_equity_weights[0] = target_equity_weights[0]

    for m in range(1, horizon):
        begin_value = value
        gross_value = (
            equity_units * equity_prices[m] + bond_units * bond_prices[m]
        )
        fee = begin_value * fee_annual / 12.0
        value = gross_value - fee
        if value < 0.0:
            value = 0.0
            equity_units = 0.0
            bond_units = 0.0
        elif gross_value > 0.0:
            scale = value / gross_value
            equity_units *= scale
            bond_units *= scale
        else:
            value = 0.0
            equity_units = 0.0
            bond_units = 0.0

        if use_proportional_withdrawal:
            withdrawal = (
                0.0
                if proportional_annual and m % 12 != 0
                else value * monthly_rate
            )
        else:
            withdrawal = fixed_withdrawal_amounts[m]

        if withdrawal > value:
            return 0.0, False, m, m

        value -= withdrawal
        if rebalance_flags[m]:
            if value > 0.0:
                equity_units = (
                    value * target_equity_weights[m] / equity_prices[m]
                )
                bond_units = (
                    value * (1.0 - target_equity_weights[m]) / bond_prices[m]
                )
            else:
                equity_units = 0.0
                bond_units = 0.0

        out_values[m] = value
        out_target_equity_weights[m] = target_equity_weights[m]
        out_withdrawals[m] = withdrawal
        if value > 0.0:
            actual_weight = equity_units * equity_prices[m] / value
            if actual_weight < 0.0:
                actual_weight = 0.0
            elif actual_weight > 1.0:
                actual_weight = 1.0
            out_actual_equity_weights[m] = actual_weight
        else:
            out_actual_equity_weights[m] = target_equity_weights[m]

    return value, True, -1, horizon


__all__ = ["simulate_deterministic_two_asset"]
