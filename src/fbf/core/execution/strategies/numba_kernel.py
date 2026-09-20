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
- Constant allocation target only (same target weights every month)
- No additional cash flows, costs, or taxes
- Portfolio state after rebalancing is completely determined by total value
  and target weights
"""

from __future__ import annotations

from decimal import Decimal

import numba
import numpy as np
from numpy.typing import NDArray

from fbf.core.domain.model.money import Currency, Money


@numba.njit(cache=True)
def _simulate_trajectory(
    growth_factors: NDArray[np.float64],
    initial_value: float,
    withdrawal_monthly: float,
    horizon: int,
) -> tuple[float, bool, int, float]:
    """Simulate one trajectory using the scalar recurrence.

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
) -> NDArray[np.float64]:
    """Precompute the constant growth factors for each month.

    ``growth_factors[m] = sum_j w_j * P_{j,m+1} / P_{j,m}``

    Only entries 0..horizon-2 are meaningful (the simulation applies growth
    for months 0..horizon-2; the final month has no further growth).  The
    entry at index horizon-1 is filled with 1.0 for safety.

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

    n_growth = min(horizon - 1, n_prices - 1)
    growth_factors = np.ones(horizon, dtype=np.float64)

    for m in range(n_growth):
        g = 0.0
        for j in range(n_assets):
            g += weights[j] * prices[j, m + 1] / prices[j, m]
        growth_factors[m] = g

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
) -> NDArray[np.float64]:
    """Compute growth factors using vectorized NumPy operations.

    Parameters
    ----------
    weights_float:
        Float64 array of target allocation weights, shape (n_assets,).
    prices_float:
        Float64 array of price series, shape (n_assets, n_prices).
    horizon:
        Number of months to simulate.

    Returns
    -------
    NDArray of float64 growth factors, length = horizon.
    """
    n_prices = prices_float.shape[1]
    n_growth = min(horizon - 1, n_prices - 1)

    ratios = prices_float[:, 1:] / prices_float[:, :-1]
    growth = np.dot(weights_float, ratios)

    growth_factors = np.ones(horizon, dtype=np.float64)
    growth_factors[:n_growth] = growth[:n_growth]

    return growth_factors


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
        if Y > 0.0 and V > 0.0:
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
        if Y > V and Y > 0.0:
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
    n_trajectories: int,
) -> tuple[
    NDArray[np.float64],
    NDArray[np.bool_],
    NDArray[np.int32],
    NDArray[np.float64],
]:
    """Simulate a batch of Part52 trajectories in parallel using numba.prange.

    All trajectories share the same growth_factors (same equity allocation and
    market trajectory), but may differ in monthly_rates, equity_prices offsets,
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
        )
        final_values[i] = fv
        successes[i] = ok
        failure_months[i] = fm
        final_loan_balances[i] = y_final

    return final_values, successes, failure_months, final_loan_balances
