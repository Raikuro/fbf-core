"""Numba-accelerated scalar simulation kernel.

This module provides a high-performance scalar kernel that replicates the
reference Decimal engine's monthly trajectory computation using float64
arithmetic with Numba JIT compilation.

Mathematical equivalence
------------------------
The reference engine's monthly pipeline (withdraw → rebalance → market
evolution) reduces to a scalar recurrence when the allocation target is
constant and rebalancing is performed at the same snapshot used for
market evolution:

    V_0      = value(initial_portfolio @ snapshot_0)
    C        = V_0 * withdrawal_rate / 12          (constant real withdrawal)
    g_m      = sum_j w_j * P_{j,m+1} / P_{j,m}   (varies by month)
    V_{m+1}  = (V_m - C) * g_m

where ``w_j`` are the **constant** target allocation weights and
``P_{j,m}`` are the asset-class index levels.  The weights ``w_j`` are
constant across all months because the portfolio is rebalanced to the same
target each month.  The growth factor ``g_m`` varies by month because the
price returns ``P_{j,m+1}/P_{j,m}`` change.

For glidepath strategies, the target weights vary by month according to
a precomputed equity-weight sequence:

    g_m      = w_m * equity_return[m] + (1 - w_m) * bond_return[m]

where ``w_m`` is the equity weight for month ``m`` (after rebalancing).

The engine fails at month ``m`` when ``V_m < C`` (depletion at the
withdrawal step).  On depletion, the remaining value is 0 (all holdings
are sold), matching the reference engine's ``remaining_value = Money.ZERO``.

Performance
-----------
- Numba scalar: ~0.003ms per 720-month trajectory (~16,000× faster than reference)
- Numba parallel: ~0.003ms per trajectory at batch=78,255 (~171× faster than reference)
- Precomputed growth factors are shared across batch trajectories

Limitations
-----------
- Float64 precision (~1e-15 per step) — not bit-exact with Decimal reference
- FixedRealWithdrawalPolicy only
- No additional cash flows, costs, or taxes
- Portfolio state after rebalancing is completely determined by total value
  and target weights.
"""

from __future__ import annotations

from decimal import Decimal

import numba
import numpy as np
from numpy.typing import NDArray

from fbf.core.domain.model.money import Currency, Money


@numba.njit(cache=True)
def _compute_workbook_scr(
    growth_factors: NDArray[np.float64],
    horizon: int,
    fee_annual: float,
) -> float:
    """Compute workbook SCR from growth factors (with fee already embedded).

    SCR = 1 / (Sum_{t=0..T-1} 1/P[t]) * 12

    Where P[t] is cumulative growth factor WITH FEE EMBEDDED:
    P[0] = 1
    P[t] = P[t-1] * growth_factors[t-1]  (growth_factors already include fee)

    Parameters
    ----------
    growth_factors:
        Monthly growth factors (1 + return) WITH FEE EMBEDDED, length >= horizon.
    horizon:
        Number of months (T).
    fee_annual:
        Annual fee (e.g., 0.0005 for 0.05%). NOT USED - kept for API compatibility.
        Fee is already embedded in growth_factors.

    Returns
    -------
    SCR as annual rate (e.g., 0.04 for 4%).
    """
    # Build cumulative growth factors P
    P_T = 1.0
    sum_inv_P = 1.0  # 1/P[0] = 1

    for m in range(1, horizon):
        P_T *= growth_factors[m - 1]
        sum_inv_P += 1.0 / P_T

    # SCR = 1 / (Sum_{t=0..T-1} 1/P[t]) * 12
    scr = 1.0 / sum_inv_P * 12.0
    return scr


@numba.njit(cache=True)
def _simulate_trajectory_workbook(
    growth_factors: NDArray[np.float64],
    initial_value: float,
    withdrawal_monthly: float,
    horizon: int,
) -> tuple[float, bool, int, float]:
    """Simulate one trajectory with the SWR Toolbox workbook recurrence.

    Matches ``SWR_Toolbox_v2.0.xlsx`` ``Case Study``:

        P(t) = (P(t-1) - W(t)) * (1 + R(t))    for t = 1 .. horizon

    The withdrawal precedes the growth in every period, and the return of the
    final period is compounded (the trajectory is reported at the *end* of the
    final month).  ``growth_factors[m]`` is ``1 + R(t)`` for the ``m``-th
    (0-based) period and is applied *after* the withdrawal, so all ``horizon``
    entries are used.  This is the exact recurrence of the Decimal fast path
    (``fast_path._evaluate_workbook_scr_path``) and of the canonical ERN oracle.

    Depletion semantics match the reference engine: when the portfolio value is
    insufficient to cover the withdrawal, the remaining value is 0 (all
    holdings are sold).  The exact-boundary case (value == withdrawal) is NOT
    depleted — the withdrawal succeeds with remaining value 0.

    Parameters
    ----------
    growth_factors:
        Precomputed growth factors (length >= horizon), fee already embedded.
    initial_value:
        Portfolio value at the pre-retirement snapshot.
    withdrawal_monthly:
        Constant real monthly withdrawal ``C``.
    horizon:
        Number of withdrawal / growth periods.

    Returns
    -------
    tuple of (final_value, success, failure_month, post_withdrawal_value)

    On depletion, final_value is 0.0.  On success, failure_month is -1.
    """
    value = initial_value

    for m in range(horizon):
        if value < withdrawal_monthly:
            return 0.0, False, m, 0.0

        value -= withdrawal_monthly
        value *= growth_factors[m]

    return value, True, -1, value


@numba.njit(cache=True)
def _simulate_trajectory(
    growth_factors: NDArray[np.float64],
    initial_value: float,
    withdrawal_monthly: float,
    horizon: int,
) -> tuple[float, bool, int, float]:
    """Simulate one trajectory using the scalar recurrence (beginning-of-period).

    Kept for backward compatibility with non-workbook contexts.

    The recurrence matches the reference engine's monthly pipeline:
    withdrawal → rebalance → market evolution.  Growth is applied for months
    0..horizon-2 (transition to the next month).  The final month (horizon-1)
    has no further growth because there is no next snapshot.

    Depletion semantics match the reference engine: when the portfolio value
    is insufficient to cover the withdrawal, the remaining value is 0
    (all holdings are sold).  The exact-boundary case (value == withdrawal)
    is NOT depleted — the withdrawal succeeds with remaining value 0.

    Parameters
    ----------
    growth_factors:
        Precomputed growth factors (length = horizon).  Only entries
        0..horizon-2 are used; the last entry is ignored.
    initial_value:
        Portfolio value at month 0.
    withdrawal_monthly:
        Constant real monthly withdrawal ``C``.
    horizon:
        Number of months to simulate.

    Returns
    -------
    tuple of (final_value, success, failure_month, post_withdrawal_value)

    On depletion, final_value is 0.0 (matching the reference engine's
    ``remaining_value = Money.ZERO``).  On success, failure_month is -1
    (the wrapper converts this to None to match the reference engine's
    ``SimulationStatistics.failure_month = None``).
    """
    value = initial_value

    for m in range(horizon):
        if value < withdrawal_monthly:
            return 0.0, False, m, 0.0

        value -= withdrawal_monthly

        if m < horizon - 1:
            value *= growth_factors[m]

    return value, True, -1, value


@numba.njit(cache=True)
def _simulate_trajectory_constant_nominal(
    growth_factors: NDArray[np.float64],
    initial_value: float,
    withdrawal_rate: float,
    horizon: int,
) -> tuple[float, bool, int, float]:
    """Simulate one trajectory with constant nominal withdrawal (beginning-of-period).

    This matches the legacy pipeline's behavior for ConstantWithdrawalPolicy:
    withdrawal is computed as a percentage of the current portfolio value,
    then growth is applied.

    Recurrence:
        V_0 = initial_value
        For m in 0..horizon-1:
            C_m = V_m * withdrawal_rate / 12
            If C_m > V_m: failure at month m
            V_m' = V_m - C_m = V_m * (1 - withdrawal_rate/12)
            If m < horizon - 1: V_{m+1} = V_m' * growth_factors[m]
        Final value = V_horizon (after last withdrawal, no growth)

    Parameters
    ----------
    growth_factors:
        Precomputed growth factors (length = horizon).  Only entries
        0..horizon-2 are used; the last entry is ignored.
    initial_value:
        Portfolio value at month 0.
    withdrawal_rate:
        Annual withdrawal rate (e.g., 0.04 for 4%). Monthly rate = withdrawal_rate/12.
    horizon:
        Number of months to simulate.

    Returns
    -------
    tuple of (final_value, success, failure_month, post_withdrawal_value)

    On depletion, final_value is 0.0. On success, failure_month is -1.
    """
    value = initial_value
    rate_monthly = withdrawal_rate / 12.0
    factor = 1.0 - rate_monthly

    for m in range(horizon):
        # Withdrawal scales with current portfolio value
        withdrawal_monthly = value * rate_monthly

        # Depletion check: withdrawal exceeds portfolio value
        if withdrawal_monthly > value:
            return 0.0, False, m, 0.0

        # Apply withdrawal
        value = value * factor

        # Apply growth (except for the last month)
        if m < horizon - 1:
            value *= growth_factors[m]

    return value, True, -1, value


@numba.njit(cache=True)
def _simulate_batch_constant_nominal(
    growth_factors: NDArray[np.float64],
    initial_values: NDArray[np.float64],
    withdrawal_rates: NDArray[np.float64],
    horizons: NDArray[np.int32],
    n_trajectories: int,
) -> tuple[
    NDArray[np.float64],
    NDArray[np.bool_],
    NDArray[np.int32],
    NDArray[np.float64],
]:
    """Simulate a batch of trajectories with constant nominal withdrawal."""
    final_values = np.empty(n_trajectories, dtype=np.float64)
    successes = np.empty(n_trajectories, dtype=np.bool_)
    failure_months = np.empty(n_trajectories, dtype=np.int32)
    post_withdrawal_values = np.empty(n_trajectories, dtype=np.float64)

    for i in range(n_trajectories):
        fv, ok, fm, pwv = _simulate_trajectory_constant_nominal(
            growth_factors,
            initial_values[i],
            withdrawal_rates[i],
            int(horizons[i]),
        )
        final_values[i] = fv
        successes[i] = ok
        failure_months[i] = fm
        post_withdrawal_values[i] = pwv

    return final_values, successes, failure_months, post_withdrawal_values


@numba.njit(parallel=True, cache=True)
def _simulate_batch_constant_nominal_parallel(
    growth_factors: NDArray[np.float64],
    initial_values: NDArray[np.float64],
    withdrawal_rates: NDArray[np.float64],
    horizons: NDArray[np.int32],
    n_trajectories: int,
) -> tuple[
    NDArray[np.float64],
    NDArray[np.bool_],
    NDArray[np.int32],
    NDArray[np.float64],
]:
    """Simulate a batch of trajectories in parallel with constant nominal withdrawal."""
    final_values = np.empty(n_trajectories, dtype=np.float64)
    successes = np.empty(n_trajectories, dtype=np.bool_)
    failure_months = np.empty(n_trajectories, dtype=np.int32)
    post_withdrawal_values = np.empty(n_trajectories, dtype=np.float64)

    for i in numba.prange(n_trajectories):  # type: ignore[attr-defined, no-untyped-call]
        fv, ok, fm, pwv = _simulate_trajectory_constant_nominal(
            growth_factors,
            initial_values[i],
            withdrawal_rates[i],
            int(horizons[i]),
        )
        final_values[i] = fv
        successes[i] = ok
        failure_months[i] = fm
        post_withdrawal_values[i] = pwv

    return final_values, successes, failure_months, post_withdrawal_values


@numba.njit(cache=True)
def _simulate_trajectory_escalating(
    growth_factors: NDArray[np.float64],
    initial_value: float,
    withdrawal_rate: float,
    escalation_rate: float,
    horizon: int,
    annual: bool,
) -> tuple[float, bool, int, float]:
    """Simulate one trajectory with an annually escalating withdrawal schedule.

    Matches ``EscalatingWithdrawalPolicy``: the withdrawal is a fixed,
    value-independent amount derived from the *initial* value,

        C_year = initial_value * withdrawal_rate * (1 + escalation_rate) ** year

    where ``year = m // 12``.  With ``annual=True`` a single lump withdrawal is
    taken at each annual boundary (``m % 12 == 0``) and zero otherwise; with
    ``annual=False`` the annual amount is divided by twelve and taken every
    month.

    The recurrence follows the workbook (beginning-of-period) convention used
    by the other Numba kernels::

        V_0 = initial_value
        C_m = schedule(m)
        if C_m > V_m: failure at month m
        V_{m+1} = (V_m - C_m) * growth_factors[m]     (growth only for m < horizon-1)

    Parameters
    ----------
    growth_factors:
        Precomputed growth factors (length = horizon).  Only entries
        ``0..horizon-2`` are used; the last entry is ignored.
    initial_value:
        Portfolio value at month 0 (the withdrawal base).
    withdrawal_rate:
        Initial annual withdrawal rate (e.g. ``0.035`` for 3.5%).
    escalation_rate:
        Annual escalation rate (e.g. ``0.02`` for 2%).
    horizon:
        Number of months to simulate.
    annual:
        ``True`` for one lump sum per year, ``False`` for monthly twelfth.

    Returns
    -------
    tuple of (final_value, success, failure_month, post_withdrawal_value)

    On depletion, final_value is 0.0.  On success, failure_month is -1.

    The timing rules encoded here (first annual lump at ``m = 0``, withdrawal
    before growth, no growth after the final withdrawal, and the depletion
    boundary) are intentional strategy semantics documented in
    ``docs/DESIGN.md`` ("Withdrawal Timing Semantics"), and pinned by the
    independent-recurrence and schedule-contract tests in
    ``tests/unit/strategies/test_numba_escalating.py``.
    """
    value = initial_value
    base_annual = initial_value * withdrawal_rate

    for m in range(horizon):
        year = m // 12
        escalated = base_annual * (1.0 + escalation_rate) ** year

        if annual and m % 12 != 0:
            withdrawal = 0.0
        elif annual:
            withdrawal = escalated
        else:
            withdrawal = escalated / 12.0

        if withdrawal > value:
            return 0.0, False, m, 0.0

        value -= withdrawal

        if m < horizon - 1:
            value *= growth_factors[m]

    return value, True, -1, value


@numba.njit(cache=True)
def _simulate_trajectory_buy_and_hold(
    equity_growth: NDArray[np.float64],
    bond_growth: NDArray[np.float64],
    initial_value: float,
    equity_weight: float,
    withdrawal_monthly: float,
    horizon: int,
) -> tuple[float, bool, int, float]:
    """Simulate one buy-and-hold trajectory with explicit unit/weight tracking.

    Buy-and-hold establishes the target equity/bond split once and never
    rebalances.  Withdrawals are funded by selling both holdings pro rata,
    which preserves the weights immediately before the withdrawal; between
    withdrawals the weights drift with the asset-specific returns::

        V_0 = initial_value,  w_0 = equity_weight
        for m in 0 .. horizon-1:
            if withdrawal_monthly > V_m: failure at month m
            V_m <- V_m - withdrawal_monthly          (pro rata: w unchanged)
            if m < horizon - 1:
                g_e = equity_growth[m], g_b = bond_growth[m]
                G   = w_m * g_e + (1 - w_m) * g_b
                w_{m+1} = w_m * g_e / G
                V_{m+1} = V_m * G

    The recurrence follows the same beginning-of-period convention as the other
    Numba kernels (withdrawal before growth, growth only for ``m < horizon - 1``);
    the target allocation is applied once before the first growth period.

    Parameters
    ----------
    equity_growth:
        Per-asset monthly equity growth factors ``P_{m+1} / P_m`` (length =
        horizon).  Only entries ``0..horizon-2`` are used.
    bond_growth:
        Per-asset monthly bond growth factors (length = horizon).
    initial_value:
        Portfolio value at month 0 (the withdrawal base).
    equity_weight:
        Target equity allocation applied once at the start (0.0-1.0).
    withdrawal_monthly:
        Constant monthly withdrawal amount.
    horizon:
        Number of months to simulate.

    Returns
    -------
    tuple of (final_value, success, failure_month, post_withdrawal_value)

    On depletion, final_value is 0.0.  On success, failure_month is -1.
    """
    value = initial_value
    weight = equity_weight

    for m in range(horizon):
        if withdrawal_monthly > value:
            return 0.0, False, m, 0.0

        value -= withdrawal_monthly

        if m < horizon - 1:
            ge = equity_growth[m]
            gb = bond_growth[m]
            blended = weight * ge + (1.0 - weight) * gb
            if blended != 0.0:
                weight = weight * ge / blended
            value *= blended

    return value, True, -1, value


@numba.njit(cache=True)
def _simulate_batch_escalating(
    growth_factors: NDArray[np.float64],
    initial_values: NDArray[np.float64],
    withdrawal_rates: NDArray[np.float64],
    escalation_rates: NDArray[np.float64],
    horizons: NDArray[np.int32],
    n_trajectories: int,
    annual: bool,
) -> tuple[
    NDArray[np.float64],
    NDArray[np.bool_],
    NDArray[np.int32],
    NDArray[np.float64],
]:
    """Simulate a batch of trajectories with annually escalating withdrawal."""
    final_values = np.empty(n_trajectories, dtype=np.float64)
    successes = np.empty(n_trajectories, dtype=np.bool_)
    failure_months = np.empty(n_trajectories, dtype=np.int32)
    post_withdrawal_values = np.empty(n_trajectories, dtype=np.float64)

    for i in range(n_trajectories):
        fv, ok, fm, pwv = _simulate_trajectory_escalating(
            growth_factors,
            initial_values[i],
            withdrawal_rates[i],
            escalation_rates[i],
            int(horizons[i]),
            annual,
        )
        final_values[i] = fv
        successes[i] = ok
        failure_months[i] = fm
        post_withdrawal_values[i] = pwv

    return final_values, successes, failure_months, post_withdrawal_values


@numba.njit(parallel=True, cache=True)
def _simulate_batch_escalating_parallel(
    growth_factors: NDArray[np.float64],
    initial_values: NDArray[np.float64],
    withdrawal_rates: NDArray[np.float64],
    escalation_rates: NDArray[np.float64],
    horizons: NDArray[np.int32],
    n_trajectories: int,
    annual: bool,
) -> tuple[
    NDArray[np.float64],
    NDArray[np.bool_],
    NDArray[np.int32],
    NDArray[np.float64],
]:
    """Simulate a batch of escalating-withdrawal trajectories in parallel."""
    final_values = np.empty(n_trajectories, dtype=np.float64)
    successes = np.empty(n_trajectories, dtype=np.bool_)
    failure_months = np.empty(n_trajectories, dtype=np.int32)
    post_withdrawal_values = np.empty(n_trajectories, dtype=np.float64)

    for i in numba.prange(n_trajectories):  # type: ignore[attr-defined, no-untyped-call]
        fv, ok, fm, pwv = _simulate_trajectory_escalating(
            growth_factors,
            initial_values[i],
            withdrawal_rates[i],
            escalation_rates[i],
            int(horizons[i]),
            annual,
        )
        final_values[i] = fv
        successes[i] = ok
        failure_months[i] = fm
        post_withdrawal_values[i] = pwv

    return final_values, successes, failure_months, post_withdrawal_values


@numba.njit(cache=True)
def _simulate_batch_buy_and_hold(
    equity_growth: NDArray[np.float64],
    bond_growth: NDArray[np.float64],
    initial_values: NDArray[np.float64],
    equity_weights: NDArray[np.float64],
    withdrawals_monthly: NDArray[np.float64],
    horizons: NDArray[np.int32],
    n_trajectories: int,
) -> tuple[
    NDArray[np.float64],
    NDArray[np.bool_],
    NDArray[np.int32],
    NDArray[np.float64],
]:
    """Simulate a batch of buy-and-hold trajectories sharing one trajectory."""
    final_values = np.empty(n_trajectories, dtype=np.float64)
    successes = np.empty(n_trajectories, dtype=np.bool_)
    failure_months = np.empty(n_trajectories, dtype=np.int32)
    post_withdrawal_values = np.empty(n_trajectories, dtype=np.float64)

    for i in range(n_trajectories):
        fv, ok, fm, pwv = _simulate_trajectory_buy_and_hold(
            equity_growth,
            bond_growth,
            initial_values[i],
            equity_weights[i],
            withdrawals_monthly[i],
            int(horizons[i]),
        )
        final_values[i] = fv
        successes[i] = ok
        failure_months[i] = fm
        post_withdrawal_values[i] = pwv

    return final_values, successes, failure_months, post_withdrawal_values


@numba.njit(parallel=True, cache=True)
def _simulate_batch_buy_and_hold_parallel(
    equity_growth: NDArray[np.float64],
    bond_growth: NDArray[np.float64],
    initial_values: NDArray[np.float64],
    equity_weights: NDArray[np.float64],
    withdrawals_monthly: NDArray[np.float64],
    horizons: NDArray[np.int32],
    n_trajectories: int,
) -> tuple[
    NDArray[np.float64],
    NDArray[np.bool_],
    NDArray[np.int32],
    NDArray[np.float64],
]:
    """Simulate a batch of buy-and-hold trajectories in parallel."""
    final_values = np.empty(n_trajectories, dtype=np.float64)
    successes = np.empty(n_trajectories, dtype=np.bool_)
    failure_months = np.empty(n_trajectories, dtype=np.int32)
    post_withdrawal_values = np.empty(n_trajectories, dtype=np.float64)

    for i in numba.prange(n_trajectories):  # type: ignore[attr-defined, no-untyped-call]
        fv, ok, fm, pwv = _simulate_trajectory_buy_and_hold(
            equity_growth,
            bond_growth,
            initial_values[i],
            equity_weights[i],
            withdrawals_monthly[i],
            int(horizons[i]),
        )
        final_values[i] = fv
        successes[i] = ok
        failure_months[i] = fm
        post_withdrawal_values[i] = pwv

    return final_values, successes, failure_months, post_withdrawal_values


@numba.njit(cache=True)
def _simulate_batch(
    growth_factors: NDArray[np.float64],
    initial_values: NDArray[np.float64],
    withdrawals_monthly: NDArray[np.float64],
    horizons: NDArray[np.int32],
    n_trajectories: int,
) -> tuple[
    NDArray[np.float64],
    NDArray[np.bool_],
    NDArray[np.int32],
    NDArray[np.float64],
]:
    """Simulate a batch of trajectories sequentially.

    All trajectories share the same growth_factors array (precomputed from
    target weights and price returns).

    Returns
    -------
    tuple of (final_values, successes, failure_months, post_withdrawal_values)
    """
    final_values = np.empty(n_trajectories, dtype=np.float64)
    successes = np.empty(n_trajectories, dtype=np.bool_)
    failure_months = np.empty(n_trajectories, dtype=np.int32)
    post_withdrawal_values = np.empty(n_trajectories, dtype=np.float64)

    for i in range(n_trajectories):
        fv, ok, fm, pwv = _simulate_trajectory(
            growth_factors,
            initial_values[i],
            withdrawals_monthly[i],
            int(horizons[i]),
        )
        final_values[i] = fv
        successes[i] = ok
        failure_months[i] = fm
        post_withdrawal_values[i] = pwv

    return final_values, successes, failure_months, post_withdrawal_values


@numba.njit(parallel=True, cache=True)
def _simulate_batch_parallel(
    growth_factors: NDArray[np.float64],
    initial_values: NDArray[np.float64],
    withdrawals_monthly: NDArray[np.float64],
    horizons: NDArray[np.int32],
    n_trajectories: int,
) -> tuple[
    NDArray[np.float64],
    NDArray[np.bool_],
    NDArray[np.int32],
    NDArray[np.float64],
]:
    """Simulate a batch of trajectories in parallel using numba.prange."""
    final_values = np.empty(n_trajectories, dtype=np.float64)
    successes = np.empty(n_trajectories, dtype=np.bool_)
    failure_months = np.empty(n_trajectories, dtype=np.int32)
    post_withdrawal_values = np.empty(n_trajectories, dtype=np.float64)

    for i in numba.prange(n_trajectories):  # type: ignore[attr-defined, no-untyped-call]
        fv, ok, fm, pwv = _simulate_trajectory(
            growth_factors,
            initial_values[i],
            withdrawals_monthly[i],
            int(horizons[i]),
        )
        final_values[i] = fv
        successes[i] = ok
        failure_months[i] = fm
        post_withdrawal_values[i] = pwv

    return final_values, successes, failure_months, post_withdrawal_values


def compute_growth_factors(
    asset_classes: tuple[object, ...],
    target_weights: dict[object, Decimal],
    price_series: dict[object, tuple[Decimal, ...]],
    horizon: int,
    fee_annual: Decimal = Decimal("0"),
) -> NDArray[np.float64]:
    """Precompute the constant growth factors for each month (with fee embedded).

    ``growth_factors[m] = sum_j w_j * P_{j,m+1} / P_{j,m} - fee_annual/12``

    Entries 0..horizon-1 are meaningful for end-of-period trajectories
    (T growth periods for T months).  For beginning-of-period trajectories,
    only entries 0..horizon-2 are used (T-1 growth periods).

    Parameters
    ----------
    asset_classes:
        Ordered tuple of asset class objects.
    target_weights:
        Target allocation weights keyed by asset class.
    price_series:
        Monthly index levels keyed by asset class.
    horizon:
        Number of months to simulate.
    fee_annual:
        Annual fee (e.g., 0.0005 for 0.05%). Applied monthly as fee_annual/12.

    Returns
    -------
    NDArray of float64 growth factors, length = horizon.
    """
    n_assets = len(asset_classes)
    n_prices = len(price_series[asset_classes[0]])

    prices = np.empty((n_assets, n_prices), dtype=np.float64)
    weights = np.empty(n_assets, dtype=np.float64)

    for j, asset_class in enumerate(asset_classes):
        weights[j] = float(target_weights[asset_class])
        series = price_series[asset_class]
        for m in range(n_prices):
            prices[j, m] = float(series[m])

    n_growth = min(horizon, n_prices - 1)
    growth_factors = np.ones(horizon, dtype=np.float64)

    fee_monthly = float(fee_annual) / 12.0

    for m in range(n_growth):
        g = 0.0
        for j in range(n_assets):
            g += weights[j] * prices[j, m + 1] / prices[j, m]
        growth_factors[m] = g - fee_monthly

    return growth_factors


def _materialize_price_float(
    asset_classes: tuple[object, ...],
    price_series: dict[object, tuple[Decimal, ...]],
) -> NDArray[np.float64]:
    """Convert Decimal price series to a float64 array.

    This is the dataset-level materialization: prices depend only on the
    market trajectory, not on allocation weights.  Cache by
    ``(start_date, n_prices)``.

    Returns
    -------
    NDArray of float64, shape ``(n_assets, n_prices)``.
    """
    n_assets = len(asset_classes)
    n_prices = len(price_series[asset_classes[0]])

    prices_float = np.empty((n_assets, n_prices), dtype=np.float64)

    for j, asset_class in enumerate(asset_classes):
        series = price_series[asset_class]
        for m in range(n_prices):
            prices_float[j, m] = float(series[m])

    return prices_float


def _materialize_float_series(
    asset_classes: tuple[object, ...],
    target_weights: dict[object, Decimal],
    price_series: dict[object, tuple[Decimal, ...]],
) -> tuple[NDArray[np.float64], NDArray[np.float64], int]:
    """Convert Decimal weights and price series to float arrays once.

    Returns
    -------
    tuple of (weights_float, prices_float, n_prices)
        weights_float: shape (n_assets,), float64
        prices_float: shape (n_assets, n_prices), float64
        n_prices: number of price points per asset
    """
    n_assets = len(asset_classes)
    n_prices = len(price_series[asset_classes[0]])

    weights_float = np.empty(n_assets, dtype=np.float64)
    prices_float = np.empty((n_assets, n_prices), dtype=np.float64)

    for j, asset_class in enumerate(asset_classes):
        weights_float[j] = float(target_weights[asset_class])
        series = price_series[asset_class]
        for m in range(n_prices):
            prices_float[j, m] = float(series[m])

    return weights_float, prices_float, n_prices


def _compute_growth_factors_numpy(
    weights_float: NDArray[np.float64],
    prices_float: NDArray[np.float64],
    horizon: int,
    fee_annual: float = 0.0,
) -> NDArray[np.float64]:
    """Compute growth factors using vectorized NumPy operations (with fee embedded).

    Parameters
    ----------
    weights_float:
        Float64 array of target allocation weights, shape (n_assets,).
    prices_float:
        Float64 array of price series, shape (n_assets, n_prices).
    horizon:
        Number of months to simulate.
    fee_annual:
        Annual fee (e.g., 0.0005 for 0.05%). Applied monthly as fee_annual/12.

    Returns
    -------
    NDArray of float64 growth factors, length = horizon.
    """
    n_prices = prices_float.shape[1]
    n_growth = min(horizon, n_prices - 1)

    ratios = prices_float[:, 1:] / prices_float[:, :-1]
    growth = np.dot(weights_float, ratios)

    growth_factors = np.ones(horizon, dtype=np.float64)
    fee_monthly = fee_annual / 12.0
    growth_factors[:n_growth] = growth[:n_growth] - fee_monthly

    return growth_factors


def compute_growth_factors_varying_weights(
    equity_weights: NDArray[np.float64],
    equity_prices: NDArray[np.float64],
    bond_prices: NDArray[np.float64],
    horizon: int,
    fee_annual: float = 0.0,
) -> NDArray[np.float64]:
    """Compute growth factors with time-varying equity weights (with fee embedded).

    For glidepath strategies, the equity weight changes each month.
    The growth factor for month m is:

        g_m = w_m * equity_return[m] + (1 - w_m) * bond_return[m] - fee_annual/12

    where w_m is the equity weight after rebalancing at month m.

    Parameters
    ----------
    equity_weights:
        Float64 array of equity weights per month, length >= horizon.
        equity_weights[m] is the weight AFTER rebalancing at month m.
    equity_prices:
        Float64 array of equity index levels, length >= horizon.
    bond_prices:
        Float64 array of bond index levels, length >= horizon.
    horizon:
        Number of months to simulate.
    fee_annual:
        Annual fee (e.g., 0.0005 for 0.05%). Applied monthly as fee_annual/12.

    Returns
    -------
    NDArray of float64 growth factors, length = horizon.
    """
    n_prices = len(equity_prices)
    n_growth = min(horizon, n_prices - 1)

    growth_factors = np.ones(horizon, dtype=np.float64)
    fee_monthly = fee_annual / 12.0

    for m in range(n_growth):
        eq_ret = equity_prices[m + 1] / equity_prices[m]
        bd_ret = bond_prices[m + 1] / bond_prices[m]
        w = equity_weights[m]
        growth_factors[m] = w * eq_ret + (1.0 - w) * bd_ret - fee_monthly

    return growth_factors


@numba.njit(cache=True)
def compute_growth_factors_varying_weights_batch(
    equity_weights: NDArray[np.float64],
    equity_prices: NDArray[np.float64],
    bond_prices: NDArray[np.float64],
    horizon: int,
    fee_annual: float = 0.0,
) -> NDArray[np.float64]:
    """Batched version: compute growth factors for multiple sequences at once (with fee embedded).

    Parameters
    ----------
    equity_weights:
        2D array of shape (batch, horizon) with equity weights per month.
    equity_prices:
        2D array of shape (batch, n_prices) with equity index levels.
    bond_prices:
        2D array of shape (batch, n_prices) with bond index levels.
    horizon:
        Number of months to simulate.
    fee_annual:
        Annual fee (e.g., 0.0005 for 0.05%). Applied monthly as fee_annual/12.

    Returns
    -------
    2D array of shape (batch, horizon) with growth factors for each sequence.
    """
    batch_size, n_prices = equity_prices.shape
    n_growth = min(horizon, n_prices - 1)

    # Compute returns for all sequences at once
    equity_returns = equity_prices[:, 1:] / equity_prices[:, :-1]  # (batch, n_prices-1)
    bond_returns = bond_prices[:, 1:] / bond_prices[:, :-1]  # (batch, n_prices-1)

    # Equity weights for the growth months
    weights = equity_weights[:, :n_growth]  # (batch, n_growth)

    # Vectorized computation
    eq_ret = equity_returns[:, :n_growth]  # (batch, n_growth)
    bd_ret = bond_returns[:, :n_growth]    # (batch, n_growth)

    fee_monthly = fee_annual / 12.0

    growth_factors = np.ones((batch_size, horizon), dtype=np.float64)
    growth_factors[:, :n_growth] = weights * eq_ret + (1.0 - weights) * bd_ret - fee_monthly

    return growth_factors


@numba.njit(cache=True)
def _simulate_trajectory_varying(
    growth_factors: NDArray[np.float64],
    initial_value: float,
    withdrawal_monthly: float,
    horizon: int,
) -> tuple[float, bool, int, float]:
    """Simulate one trajectory using precomputed growth factors.

    Same recurrence as _simulate_trajectory but accepts precomputed
    growth_factors array (which may be from varying weights).

    Parameters
    ----------
    growth_factors:
        Precomputed growth factors (length = horizon).  Only entries
        0..horizon-2 are used; the last entry is ignored.
    initial_value:
        Portfolio value at month 0.
    withdrawal_monthly:
        Constant real monthly withdrawal ``C``.
    horizon:
        Number of months to simulate.

    Returns
    -------
    tuple of (final_value, success, failure_month, post_withdrawal_value)

    On depletion, final_value is 0.0 (matching the reference engine's
    ``remaining_value = Money.ZERO``).  On success, failure_month is -1
    (the wrapper converts this to None to match the reference engine's
    ``SimulationStatistics.failure_month = None``).
    """
    value = initial_value

    for m in range(horizon):
        if value < withdrawal_monthly:
            return 0.0, False, m, 0.0

        value -= withdrawal_monthly

        if m < horizon - 1:
            value *= growth_factors[m]

    return value, True, -1, value


@numba.njit(cache=True)
def _simulate_batch_varying(
    growth_factors: NDArray[np.float64],
    initial_values: NDArray[np.float64],
    withdrawals_monthly: NDArray[np.float64],
    horizons: NDArray[np.int32],
    n_trajectories: int,
) -> tuple[
    NDArray[np.float64],
    NDArray[np.bool_],
    NDArray[np.int32],
    NDArray[np.float64],
]:
    """Simulate a batch of trajectories with precomputed growth factors (varying weights)."""
    final_values = np.empty(n_trajectories, dtype=np.float64)
    successes = np.empty(n_trajectories, dtype=np.bool_)
    failure_months = np.empty(n_trajectories, dtype=np.int32)
    post_withdrawal_values = np.empty(n_trajectories, dtype=np.float64)

    for i in range(n_trajectories):
        fv, ok, fm, pwv = _simulate_trajectory_varying(
            growth_factors,
            initial_values[i],
            withdrawals_monthly[i],
            int(horizons[i]),
        )
        final_values[i] = fv
        successes[i] = ok
        failure_months[i] = fm
        post_withdrawal_values[i] = pwv

    return final_values, successes, failure_months, post_withdrawal_values


@numba.njit(parallel=True, cache=True)
def _simulate_batch_varying_parallel(
    growth_factors: NDArray[np.float64],
    initial_values: NDArray[np.float64],
    withdrawals_monthly: NDArray[np.float64],
    horizons: NDArray[np.int32],
    n_trajectories: int,
) -> tuple[
    NDArray[np.float64],
    NDArray[np.bool_],
    NDArray[np.int32],
    NDArray[np.float64],
]:
    """Simulate a batch of trajectories in parallel using numba.prange (varying weights)."""
    final_values = np.empty(n_trajectories, dtype=np.float64)
    successes = np.empty(n_trajectories, dtype=np.bool_)
    failure_months = np.empty(n_trajectories, dtype=np.int32)
    post_withdrawal_values = np.empty(n_trajectories, dtype=np.float64)

    for i in numba.prange(n_trajectories):  # type: ignore[attr-defined, no-untyped-call]
        fv, ok, fm, pwv = _simulate_trajectory_varying(
            growth_factors,
            initial_values[i],
            withdrawals_monthly[i],
            int(horizons[i]),
        )
        final_values[i] = fv
        successes[i] = ok
        failure_months[i] = fm
        post_withdrawal_values[i] = pwv

    return final_values, successes, failure_months, post_withdrawal_values


def simulate_batch_varying(
    growth_factors: NDArray[np.float64],
    initial_values: list[Money],
    withdrawal_rates: list[Decimal],
    horizons: list[int],
    *,
    parallel: bool = True,
) -> list[tuple[bool, int | None, Money, int]]:
    """Simulate a batch of trajectories with precomputed growth factors.

    Parameters
    ----------
    growth_factors:
        Precomputed growth factors (shared across all trajectories).
    initial_values:
        Initial portfolio values for each trajectory.
    withdrawal_rates:
        Annual withdrawal rates for each trajectory.
    horizons:
        Horizon in months for each trajectory.
    parallel:
        If True, use Numba parallel execution (recommended for batch > 10).

    Returns
    -------
    List of (success, failure_month, final_wealth, months_simulated) tuples.
    """
    n = len(initial_values)
    if n == 0:
        return []

    v0 = np.array([float(m.amount) for m in initial_values], dtype=np.float64)
    c = np.array(
        [
            float(v.amount) * float(r) / 12.0
            for v, r in zip(initial_values, withdrawal_rates, strict=True)
        ],
        dtype=np.float64,
    )
    h = np.array(horizons, dtype=np.int32)

    if parallel and n > 10:
        final_vals, successes, fail_months, _ = _simulate_batch_varying_parallel(
            growth_factors, v0, c, h, n
        )
    else:
        final_vals, successes, fail_months, _ = _simulate_batch_varying(
            growth_factors, v0, c, h, n
        )

    results: list[tuple[bool, int | None, Money, int]] = []
    for i in range(n):
        fv = Money(Decimal(str(final_vals[i])), Currency.EUR)
        if successes[i]:
            results.append((True, None, fv, int(h[i])))
        else:
            results.append((False, int(fail_months[i]), fv, int(fail_months[i])))

    return results


def simulate_single(
    growth_factors: NDArray[np.float64],
    initial_value: Money,
    withdrawal_rate: Decimal,
    horizon: int,
) -> tuple[bool, int | None, Money, int]:
    """Simulate a single trajectory and return results compatible with the
    reference engine's SimulationStatistics format.

    Parameters
    ----------
    growth_factors:
        Precomputed growth factors (length = horizon).
    initial_value:
        Initial portfolio value.
    withdrawal_rate:
        Annual real withdrawal rate (e.g., 0.04 for 4%).
    horizon:
        Number of months to simulate.

    Returns
    -------
    tuple of (success, failure_month, final_wealth, months_simulated)
    """
    v0 = float(initial_value.amount)
    c = v0 * float(withdrawal_rate) / 12.0

    final_value, success, failure_month, _ = _simulate_trajectory(
        growth_factors, v0, c, horizon
    )

    if success:
        final_wealth = Money(Decimal(str(final_value)), Currency.EUR)
        return True, None, final_wealth, horizon
    else:
        final_wealth = Money(Decimal(str(final_value)), Currency.EUR)
        return False, failure_month, final_wealth, failure_month


def simulate_batch(
    growth_factors: NDArray[np.float64],
    initial_values: list[Money],
    withdrawal_rates: list[Decimal],
    horizons: list[int],
    *,
    parallel: bool = True,
) -> list[tuple[bool, int | None, Money, int]]:
    """Simulate a batch of trajectories.

    Parameters
    ----------
    growth_factors:
        Precomputed growth factors (shared across all trajectories).
    initial_values:
        Initial portfolio values for each trajectory.
    withdrawal_rates:
        Annual withdrawal rates for each trajectory.
    horizons:
        Horizon in months for each trajectory.
    parallel:
        If True, use Numba parallel execution (recommended for batch > 10).

    Returns
    -------
    List of (success, failure_month, final_wealth, months_simulated) tuples.
    """
    n = len(initial_values)
    if n == 0:
        return []

    v0 = np.array([float(m.amount) for m in initial_values], dtype=np.float64)
    c = np.array(
        [
            float(v.amount) * float(r) / 12.0
            for v, r in zip(initial_values, withdrawal_rates, strict=True)
        ],
        dtype=np.float64,
    )
    h = np.array(horizons, dtype=np.int32)

    if parallel and n > 10:
        final_vals, successes, fail_months, _ = _simulate_batch_parallel(
            growth_factors, v0, c, h, n
        )
    else:
        final_vals, successes, fail_months, _ = _simulate_batch(
            growth_factors, v0, c, h, n
        )

    results: list[tuple[bool, int | None, Money, int]] = []
    for i in range(n):
        fv = Money(Decimal(str(final_vals[i])), Currency.EUR)
        if successes[i]:
            results.append((True, None, fv, int(h[i])))
        else:
            results.append((False, int(fail_months[i]), fv, int(fail_months[i])))

    return results


def simulate_single_constant_nominal(
    growth_factors: NDArray[np.float64],
    initial_value: Money,
    withdrawal_rate: Decimal,
    horizon: int,
) -> tuple[bool, int | None, Money, int]:
    """Simulate a single trajectory with constant nominal withdrawal.

    Parameters
    ----------
    growth_factors:
        Precomputed growth factors (length = horizon).
    initial_value:
        Initial portfolio value.
    withdrawal_rate:
        Annual withdrawal rate (e.g., 0.04 for 4%).
    horizon:
        Number of months to simulate.

    Returns
    -------
    tuple of (success, failure_month, final_wealth, months_simulated)
    """
    v0 = float(initial_value.amount)
    r = float(withdrawal_rate)

    final_value, success, failure_month, _ = _simulate_trajectory_constant_nominal(
        growth_factors, v0, r, horizon
    )

    if success:
        final_wealth = Money(Decimal(str(final_value)), Currency.EUR)
        return True, None, final_wealth, horizon
    else:
        final_wealth = Money(Decimal(str(final_value)), Currency.EUR)
        return False, failure_month, final_wealth, failure_month


def simulate_batch_constant_nominal(
    growth_factors: NDArray[np.float64],
    initial_values: list[Money],
    withdrawal_rates: list[Decimal],
    horizons: list[int],
    *,
    parallel: bool = True,
) -> list[tuple[bool, int | None, Money, int]]:
    """Simulate a batch of trajectories with constant nominal withdrawal.

    Parameters
    ----------
    growth_factors:
        Precomputed growth factors (shared across all trajectories).
    initial_values:
        Initial portfolio values for each trajectory.
    withdrawal_rates:
        Annual withdrawal rates for each trajectory.
    horizons:
        Horizon in months for each trajectory.
    parallel:
        If True, use Numba parallel execution (recommended for batch > 10).

    Returns
    -------
    List of (success, failure_month, final_wealth, months_simulated) tuples.
    """
    n = len(initial_values)
    if n == 0:
        return []

    v0 = np.array([float(m.amount) for m in initial_values], dtype=np.float64)
    r = np.array([float(rate) for rate in withdrawal_rates], dtype=np.float64)
    h = np.array(horizons, dtype=np.int32)

    if parallel and n > 10:
        final_vals, successes, fail_months, _ = _simulate_batch_constant_nominal_parallel(
            growth_factors, v0, r, h, n
        )
    else:
        final_vals, successes, fail_months, _ = _simulate_batch_constant_nominal(
            growth_factors, v0, r, h, n
        )

    results: list[tuple[bool, int | None, Money, int]] = []
    for i in range(n):
        fv = Money(Decimal(str(final_vals[i])), Currency.EUR)
        if successes[i]:
            results.append((True, None, fv, int(h[i])))
        else:
            results.append((False, int(fail_months[i]), fv, int(fail_months[i])))

    return results


def simulate_single_escalating(
    growth_factors: NDArray[np.float64],
    initial_value: Money,
    withdrawal_rate: Decimal,
    escalation_rate: Decimal,
    horizon: int,
    annual: bool,
) -> tuple[bool, int | None, Money, int]:
    """Simulate a single trajectory with an annually escalating withdrawal.

    Parameters
    ----------
    growth_factors:
        Precomputed growth factors (length = horizon).
    initial_value:
        Initial portfolio value (the withdrawal base).
    withdrawal_rate:
        Initial annual withdrawal rate (e.g. ``0.035`` for 3.5%).
    escalation_rate:
        Annual escalation rate (e.g. ``0.02`` for 2%).
    horizon:
        Number of months to simulate.
    annual:
        ``True`` for one lump sum per year, ``False`` for a monthly twelfth.

    Returns
    -------
    tuple of (success, failure_month, final_wealth, months_simulated)
    """
    v0 = float(initial_value.amount)
    r = float(withdrawal_rate)
    esc = float(escalation_rate)

    final_value, success, failure_month, _ = _simulate_trajectory_escalating(
        growth_factors, v0, r, esc, horizon, annual
    )

    final_wealth = Money(Decimal(str(final_value)), Currency.EUR)
    if success:
        return True, None, final_wealth, horizon
    return False, failure_month, final_wealth, failure_month


def simulate_batch_escalating(
    growth_factors: NDArray[np.float64],
    initial_values: list[Money],
    withdrawal_rates: list[Decimal],
    escalation_rates: list[Decimal],
    horizons: list[int],
    annual: bool,
    *,
    parallel: bool = True,
) -> list[tuple[bool, int | None, Money, int]]:
    """Simulate a batch of annually escalating withdrawal trajectories.

    All trajectories share one growth-factor array and one withdrawal cadence
    (the executor groups contexts accordingly).

    Parameters
    ----------
    growth_factors:
        Precomputed growth factors (shared across all trajectories).
    initial_values:
        Initial portfolio values (the withdrawal bases).
    withdrawal_rates:
        Initial annual withdrawal rates.
    escalation_rates:
        Annual escalation rates.
    horizons:
        Horizon in months for each trajectory.
    annual:
        ``True`` for one lump sum per year, ``False`` for a monthly twelfth.
    parallel:
        If True, use Numba parallel execution (recommended for batch > 10).

    Returns
    -------
    List of (success, failure_month, final_wealth, months_simulated) tuples.
    """
    n = len(initial_values)
    if n == 0:
        return []

    v0 = np.array([float(m.amount) for m in initial_values], dtype=np.float64)
    r = np.array([float(rate) for rate in withdrawal_rates], dtype=np.float64)
    esc = np.array([float(rate) for rate in escalation_rates], dtype=np.float64)
    h = np.array(horizons, dtype=np.int32)

    if parallel and n > 10:
        final_vals, successes, fail_months, _ = _simulate_batch_escalating_parallel(
            growth_factors, v0, r, esc, h, n, annual
        )
    else:
        final_vals, successes, fail_months, _ = _simulate_batch_escalating(
            growth_factors, v0, r, esc, h, n, annual
        )

    results: list[tuple[bool, int | None, Money, int]] = []
    for i in range(n):
        fv = Money(Decimal(str(final_vals[i])), Currency.EUR)
        if successes[i]:
            results.append((True, None, fv, int(h[i])))
        else:
            results.append((False, int(fail_months[i]), fv, int(fail_months[i])))

    return results


def simulate_single_buy_and_hold(
    equity_growth: NDArray[np.float64],
    bond_growth: NDArray[np.float64],
    initial_value: Money,
    equity_weight: Decimal,
    withdrawal_rate: Decimal,
    horizon: int,
) -> tuple[bool, int | None, Money, int]:
    """Simulate a single buy-and-hold trajectory.

    Parameters
    ----------
    equity_growth:
        Monthly equity growth factors ``P_{m+1} / P_m`` (length = horizon).
    bond_growth:
        Monthly bond growth factors (length = horizon).
    initial_value:
        Initial portfolio value (the real withdrawal base).
    equity_weight:
        Target equity allocation applied once at the start.
    withdrawal_rate:
        Constant annual real withdrawal rate (e.g. ``0.04`` for 4%).
    horizon:
        Number of months to simulate.

    Returns
    -------
    tuple of (success, failure_month, final_wealth, months_simulated)
    """
    v0 = float(initial_value.amount)
    weight = float(equity_weight)
    c = v0 * float(withdrawal_rate) / 12.0

    final_value, success, failure_month, _ = _simulate_trajectory_buy_and_hold(
        equity_growth, bond_growth, v0, weight, c, horizon
    )

    final_wealth = Money(Decimal(str(final_value)), Currency.EUR)
    if success:
        return True, None, final_wealth, horizon
    return False, failure_month, final_wealth, failure_month


def simulate_batch_buy_and_hold(
    equity_growth: NDArray[np.float64],
    bond_growth: NDArray[np.float64],
    initial_values: list[Money],
    equity_weights: list[Decimal],
    withdrawal_rates: list[Decimal],
    horizons: list[int],
    *,
    parallel: bool = True,
) -> list[tuple[bool, int | None, Money, int]]:
    """Simulate a batch of buy-and-hold trajectories sharing one trajectory.

    All trajectories share the same per-asset growth-factor arrays (the
    executor groups contexts accordingly).

    Parameters
    ----------
    equity_growth, bond_growth:
        Monthly per-asset growth factors (shared across all trajectories).
    initial_values:
        Initial portfolio values (the withdrawal bases).
    equity_weights:
        Target equity allocations applied once at the start.
    withdrawal_rates:
        Constant annual real withdrawal rates.
    horizons:
        Horizon in months for each trajectory.
    parallel:
        If True, use Numba parallel execution (recommended for batch > 10).

    Returns
    -------
    List of (success, failure_month, final_wealth, months_simulated) tuples.
    """
    n = len(initial_values)
    if n == 0:
        return []

    v0 = np.array([float(m.amount) for m in initial_values], dtype=np.float64)
    w = np.array([float(weight) for weight in equity_weights], dtype=np.float64)
    c = np.array(
        [
            float(v.amount) * float(r) / 12.0
            for v, r in zip(initial_values, withdrawal_rates, strict=True)
        ],
        dtype=np.float64,
    )
    h = np.array(horizons, dtype=np.int32)

    if parallel and n > 10:
        final_vals, successes, fail_months, _ = _simulate_batch_buy_and_hold_parallel(
            equity_growth, bond_growth, v0, w, c, h, n
        )
    else:
        final_vals, successes, fail_months, _ = _simulate_batch_buy_and_hold(
            equity_growth, bond_growth, v0, w, c, h, n
        )

    results: list[tuple[bool, int | None, Money, int]] = []
    for i in range(n):
        fv = Money(Decimal(str(final_vals[i])), Currency.EUR)
        if successes[i]:
            results.append((True, None, fv, int(h[i])))
        else:
            results.append((False, int(fail_months[i]), fv, int(fail_months[i])))

    return results


# ---------------------------------------------------------------------------
# Part52 Numba kernel
# ---------------------------------------------------------------------------


@numba.njit(cache=True)
def _simulate_part52(
    growth_factors: NDArray[np.float64],
    monthly_rates: NDArray[np.float64],
    equity_prices: NDArray[np.float64],
    initial_value: float,
    withdrawal_monthly: float,
    threshold: float,
    borrow_pct: float,
    ltv_limit: float,
    horizon: int,
    ltv_enforcement: bool = True,
) -> tuple[float, bool, int, float]:
    """Simulate one Part52 trajectory using the scalar recurrence.

    The recurrence replicates the 15-step pipeline's behavioral semantics:
    compound drawdown tracking, FFR-based interest accrual, loan draw/repay,
    cash-first consumption, proportional portfolio sale, and LTV enforcement.

    State variables (all float64):
        V              portfolio value
        Y              loan balance
        cDD            compound (path-dependent) real total-return drawdown
        d_prev         previous period's draw/repay (positive=draw, negative=repay)
        eq_prev        previous equity index level

    Parameters
    ----------
    growth_factors:
        Precomputed growth factors g_m = sum_j w_j * P_{j,m} / P_{j,m-1}.
        Length = horizon.  Entry m is used for the transition from month m to m+1.
    monthly_rates:
        Precomputed CPI-adjusted real monthly interest rates.
        Length = horizon.  Entry m is the rate for month m.
    equity_prices:
        Equity index levels P_{equity,m} for m = 0..horizon.
        Length = horizon + 1.
    initial_value:
        Portfolio value at month 0.
    withdrawal_monthly:
        Constant real monthly withdrawal C.
    threshold:
        Drawdown threshold (positive, e.g. 0.20).
    borrow_pct:
        Borrowing percentage (e.g. 0.4108).
    ltv_limit:
        Loan-to-value limit (e.g. 0.50).
    horizon:
        Number of months to simulate.
    ltv_enforcement:
        When True, enforce LTV limit with forced liquidation and fail on
        unsatisfiable margin calls.  When False, observe LTV only (ERN
        canonical replication mode).

    Returns
    -------
    tuple of (final_value, success, failure_month, final_loan_balance)

    On depletion, final_value is 0.  On LTV failure, final_loan_balance > 0
    with final_value potentially zero.
    """
    # --- Initial state (month 0) ---
    V = initial_value
    Y = 0.0
    cDD = 0.0
    d_prev = 0.0
    eq_prev = equity_prices[0]

    for m in range(horizon):
        # --- Interest accrual (step 26) ---
        # Interest on PRIOR balance only (before new draw).
        if Y > 0.0:
            interest = Y * monthly_rates[m]
            Y += interest

        # --- Loan draw (step 28) ---
        # BORROW condition: compound_dd <= -threshold
        # REPAY condition: compound_dd == 0 and loan_balance > 0
        # Note: cDD is computed from the PREVIOUS equity ratio, not the current.
        # At period 0, cDD = 0 (no prior history).
        draw = 0.0
        is_repay = False
        if cDD <= -threshold:
            # BORROW
            draw = withdrawal_monthly * borrow_pct
        elif cDD == 0.0 and Y > 0.0:
            # REPAY
            is_repay = True

        # Add draw to loan and cash balances
        if draw > 0.0:
            Y += draw

        # --- Withdrawal execution (step 30) ---
        # Cash-first consumption, then portfolio sale.
        # total_spending = C (constant in all modes).
        cash_consumed = min(draw, withdrawal_monthly)
        portfolio_sale = withdrawal_monthly - cash_consumed

        if portfolio_sale > 0.0:
            V -= portfolio_sale
            if V < 0.0:
                V = 0.0

        # --- Loan repayment (step 32) ---
        # excess = nominal_amount - spending_budget = C - (C - D_{t-1}) = D_{t-1}
        # repayment = min(excess, loan_balance) = min(d_prev, Y)
        if is_repay and Y > 0.0:
            excess = d_prev  # D_{t-1}
            if excess < 0.0:
                excess = 0.0  # clamp: repay only when d_prev > 0
            repayment = excess
            if repayment > Y:
                repayment = Y
            Y -= repayment
            d_prev = -repayment
        elif draw > 0.0:
            d_prev = draw
        else:
            d_prev = 0.0

        # --- LTV evaluation (step 66) ---
        # The pipeline evaluates LTV after MarketEvolutionStep (seq 60), which
        # revalues from dataset[m-1] to dataset[m].  At this point the kernel's
        # portfolio value is post-gf[m-1] (from the previous iteration's growth)
        # and post-withdrawal.  Checking LTV before applying gf[m] ensures we
        # use the same valuation as the pipeline's LTV check.  Applying gf[m]
        # first would understate the portfolio during a market decline and trigger
        # premature liquidation that the pipeline would not trigger yet.
        if ltv_enforcement and Y > 0.0 and V > 0.0:
            ltv = Y / V
            if ltv > ltv_limit:
                # Margin call: liquidate to restore LTV to limit
                liq = (Y - ltv_limit * V) / (1.0 - ltv_limit)
                if liq > V:
                    # Unsatisfiable: sell entire portfolio
                    Y -= V
                    V = 0.0
                else:
                    V -= liq
                    Y -= liq

        # --- Failure detection (step 75) ---
        if V <= 0.0:
            return 0.0, False, m, Y
        if ltv_enforcement and Y > V and Y > 0.0:
            return V, False, m, Y

        # --- Growth (implicit in price change) ---
        # Applied AFTER LTV evaluation.  gf[m] corresponds to the pipeline's
        # MarketEvolutionStep at period m+1 (dataset[m] → dataset[m+1]).
        if m < horizon - 1:
            V *= growth_factors[m]

        # --- Compound drawdown (step 10 for NEXT period) ---
        # cDD = min(0, (1 + prev_cDD) * eq_curr / eq_prev - 1)
        eq_curr = equity_prices[m + 1] if m + 1 < len(equity_prices) else eq_prev
        if eq_prev > 0.0:
            raw = (1.0 + cDD) * (eq_curr / eq_prev) - 1.0
            cDD = min(0.0, raw)
        else:
            cDD = 0.0
        eq_prev = eq_curr

    return V, True, -1, Y


@numba.njit(parallel=True, cache=True)
def _simulate_part52_batch(
    growth_factors: NDArray[np.float64],
    monthly_rates_all: NDArray[np.float64],
    equity_prices_all: NDArray[np.float64],
    initial_values: NDArray[np.float64],
    withdrawals_monthly: NDArray[np.float64],
    thresholds: NDArray[np.float64],
    borrow_pcts: NDArray[np.float64],
    ltv_limits: NDArray[np.float64],
    horizons: NDArray[np.int32],
    offsets: NDArray[np.int32],
    ltv_enforcements: NDArray[np.bool_],
    n_trajectories: int,
) -> tuple[
    NDArray[np.float64],
    NDArray[np.bool_],
    NDArray[np.int32],
    NDArray[np.float64],
]:
    """Simulate a batch of Part52 trajectories in parallel using numba.prange.

    All trajectories share the same growth_factors (same equity allocation and
    trajectory), but may differ in monthly_rates, equity_prices offsets,
    parameters, and horizons.

    Parameters
    ----------
    growth_factors:
        Shared growth factors for the common equity allocation/trajectory.
    monthly_rates_all:
        Concatenated monthly rate arrays for all trajectories.
    equity_prices_all:
        Concatenated equity price arrays for all trajectories.
    initial_values:
        Initial portfolio values.
    withdrawals_monthly:
        Monthly withdrawal amounts (C).
    thresholds:
        Drawdown thresholds.
    borrow_pcts:
        Borrowing percentages.
    ltv_limits:
        LTV limits.
    horizons:
        Horizon in months per trajectory.
    offsets:
        Starting offset into monthly_rates_all and equity_prices_all per trajectory.
    ltv_enforcements:
        Per-trajectory LTV enforcement flags.
    n_trajectories:
        Total number of trajectories.
    """
    final_values = np.empty(n_trajectories, dtype=np.float64)
    successes = np.empty(n_trajectories, dtype=np.bool_)
    failure_months = np.empty(n_trajectories, dtype=np.int32)
    final_loan_balances = np.empty(n_trajectories, dtype=np.float64)

    for i in numba.prange(n_trajectories):  # type: ignore[attr-defined, no-untyped-call]
        h = int(horizons[i])
        off = int(offsets[i])

        # Slice per-trajectory arrays
        mr = monthly_rates_all[off : off + h]
        ep = equity_prices_all[off : off + h + 1]

        fv, ok, fm, y_final = _simulate_part52(
            growth_factors, mr, ep,
            initial_values[i], withdrawals_monthly[i],
            thresholds[i], borrow_pcts[i], ltv_limits[i], h,
            ltv_enforcements[i],
        )
        final_values[i] = fv
        successes[i] = ok
        failure_months[i] = fm
        final_loan_balances[i] = y_final

    return final_values, successes, failure_months, final_loan_balances
