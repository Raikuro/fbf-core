"""Independent Decimal recurrences for Part 49 and Part 52 debt trajectories.

These helpers deliberately do not import the production executors or the Numba
kernel.  They model the documented monthly ordering with exact Decimal
arithmetic so tests can validate the production path without using the legacy
pipeline as an oracle.

The recurrences cover the fee-free debt mechanics only.  Part 49 fees are
rejected by the executor, and the Part 52 fee convention is a separate
pre-existing divergence, so all comparisons that use this module pass a zero
fee.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext

_ZERO = Decimal("0")
_ONE = Decimal("1")


@dataclass(frozen=True)
class DebtReferenceResult:
    """Outcome of an independent monthly debt recurrence."""

    final_value: Decimal
    success: bool
    failure_month: int | None
    failure_state: str | None
    final_loan: Decimal
    months_simulated: int


def compute_monthly_rates(
    cpi_cumulative: Sequence[Decimal],
    horizon: int,
    *,
    annual_rate_schedule: Sequence[Decimal] | None,
    fixed_annual_rate: Decimal | None,
    real_rate: bool,
) -> tuple[Decimal, ...]:
    """Compute the monthly debt interest rates consumed by the recurrences.

    ``real_rate=True`` applies ``annual / 12`` directly (the Part 49
    ``debt_interest_rate_is_real`` bypass).  Otherwise the rate is CPI-adjusted
    as ``(1 + annual / 12) * CPI[m-1] / CPI[m] - 1``, falling back to
    ``annual / 12`` when either CPI level is zero or when no prior level exists.
    """
    rates: list[Decimal] = []
    for month in range(horizon):
        if annual_rate_schedule is not None and month < len(annual_rate_schedule):
            annual_rate = annual_rate_schedule[month]
        else:
            annual_rate = fixed_annual_rate or _ZERO

        monthly_rate = annual_rate / Decimal("12")
        if real_rate or month == 0:
            rates.append(monthly_rate)
            continue

        cpi_curr = cpi_cumulative[month] if month < len(cpi_cumulative) else _ZERO
        cpi_prev = cpi_cumulative[month - 1] if month - 1 < len(cpi_cumulative) else _ZERO
        if cpi_curr == 0 or cpi_prev == 0:
            rates.append(monthly_rate)
        else:
            rates.append((_ONE + monthly_rate) * cpi_prev / cpi_curr - _ONE)
    return tuple(rates)


def _growth_factors(
    equity_prices: Sequence[Decimal],
    bond_prices: Sequence[Decimal],
    equity_weight: Decimal,
    horizon: int,
) -> tuple[Decimal, ...]:
    factors: list[Decimal] = []
    for month in range(horizon):
        equity_growth = equity_prices[month + 1] / equity_prices[month]
        bond_growth = bond_prices[month + 1] / bond_prices[month]
        factors.append(equity_weight * equity_growth + (_ONE - equity_weight) * bond_growth)
    return tuple(factors)


def _apply_final_value_target(
    final_value: Decimal,
    *,
    success: bool,
    failure_month: int | None,
    failure_state: str | None,
    final_loan: Decimal,
    months_simulated: int,
    final_value_target: Decimal | None,
    initial_wealth: Decimal | None,
) -> DebtReferenceResult:
    if success and final_value_target is not None:
        if initial_wealth is None:
            raise ValueError("initial_wealth is required with final_value_target")
        success = final_value >= final_value_target * initial_wealth
    return DebtReferenceResult(
        final_value=final_value,
        success=success,
        failure_month=failure_month,
        failure_state=failure_state,
        final_loan=final_loan,
        months_simulated=months_simulated,
    )


def simulate_part49_reference(
    equity_prices: Sequence[Decimal],
    bond_prices: Sequence[Decimal],
    *,
    initial_value: Decimal,
    equity_weight: Decimal,
    withdrawal_rate: Decimal,
    loan_draw_rate: Decimal,
    monthly_rates: Sequence[Decimal],
    ltv_limit: Decimal,
    ltv_enforcement: bool,
    horizon: int,
    final_value_target: Decimal | None = None,
    initial_wealth: Decimal | None = None,
) -> DebtReferenceResult:
    """Run the Part 49 fixed-draw, monthly-rebalanced debt recurrence.

    Ordering per month: interest on the prior loan balance, fixed loan draw,
    portfolio withdrawal, LTV enforcement, failure detection, then market
    growth.  The final month has no subsequent growth, matching the executor.
    """
    with localcontext() as context:
        context.prec = 50

        portfolio_withdrawal = initial_value * withdrawal_rate / Decimal("12")
        loan_draw = initial_value * loan_draw_rate / Decimal("12")
        growth_factors = _growth_factors(
            equity_prices, bond_prices, equity_weight, horizon
        )

        value = initial_value
        loan = _ZERO

        for month in range(horizon):
            if loan > 0:
                loan += loan * monthly_rates[month]
            loan += loan_draw

            value -= portfolio_withdrawal
            if value < 0:
                value = _ZERO

            if ltv_enforcement and loan > 0 and value > 0:
                ltv = loan / value
                if ltv > ltv_limit:
                    liquidation = (loan - ltv_limit * value) / (_ONE - ltv_limit)
                    if liquidation > value:
                        loan -= value
                        value = _ZERO
                    else:
                        value -= liquidation
                        loan -= liquidation
                        return DebtReferenceResult(
                            final_value=value,
                            success=False,
                            failure_month=month,
                            failure_state="margin_call_terminal",
                            final_loan=loan,
                            months_simulated=month,
                        )

            if value <= 0:
                return DebtReferenceResult(
                    final_value=_ZERO,
                    success=False,
                    failure_month=month,
                    failure_state="depleted",
                    final_loan=loan,
                    months_simulated=month,
                )
            if ltv_enforcement and loan > value and loan > 0:
                return DebtReferenceResult(
                    final_value=value,
                    success=False,
                    failure_month=month,
                    failure_state="margin_call_impossible",
                    final_loan=loan,
                    months_simulated=month,
                )

            if month < horizon - 1:
                value *= growth_factors[month]

        return _apply_final_value_target(
            value,
            success=True,
            failure_month=None,
            failure_state=None,
            final_loan=loan,
            months_simulated=horizon,
            final_value_target=final_value_target,
            initial_wealth=initial_wealth,
        )


def simulate_part52_reference(
    equity_prices: Sequence[Decimal],
    bond_prices: Sequence[Decimal],
    *,
    initial_value: Decimal,
    equity_weight: Decimal,
    withdrawal_rate: Decimal,
    borrow_pct: Decimal,
    drawdown_threshold: Decimal,
    monthly_rates: Sequence[Decimal],
    ltv_limit: Decimal,
    ltv_enforcement: bool,
    horizon: int,
    final_value_target: Decimal | None = None,
    initial_wealth: Decimal | None = None,
) -> DebtReferenceResult:
    """Run the Part 52 timing-leverage debt recurrence.

    The recurrence tracks the portfolio value, loan balance, compound
    drawdown, and previous draw/repay amount.  Borrowing is triggered when the
    compound drawdown is at or below ``-drawdown_threshold``; repayment is
    triggered at a fresh ATH (compound drawdown exactly zero) while a loan is
    outstanding.
    """
    with localcontext() as context:
        context.prec = 50

        budget = initial_value * withdrawal_rate / Decimal("12")
        growth_factors = _growth_factors(
            equity_prices, bond_prices, equity_weight, horizon
        )

        value = initial_value
        loan = _ZERO
        compound_drawdown = _ZERO
        previous_draw_repay = _ZERO
        previous_equity = equity_prices[0]

        for month in range(horizon):
            if loan > 0:
                loan += loan * monthly_rates[month]

            draw = _ZERO
            is_repayment = False
            if compound_drawdown <= -drawdown_threshold:
                draw = budget * borrow_pct
            elif compound_drawdown == 0 and loan > 0:
                is_repayment = True

            if draw > 0:
                loan += draw

            cash_consumed = draw if draw < budget else budget
            portfolio_sale = budget - cash_consumed
            if portfolio_sale > 0:
                value -= portfolio_sale
                if value < 0:
                    value = _ZERO

            if is_repayment and loan > 0:
                excess = previous_draw_repay
                if excess < 0:
                    excess = _ZERO
                repayment = excess if excess < loan else loan
                loan -= repayment
                previous_draw_repay = -repayment
            elif draw > 0:
                previous_draw_repay = draw
            else:
                previous_draw_repay = _ZERO

            if ltv_enforcement and loan > 0 and value > 0:
                ltv = loan / value
                if ltv > ltv_limit:
                    liquidation = (loan - ltv_limit * value) / (_ONE - ltv_limit)
                    if liquidation > value:
                        loan -= value
                        value = _ZERO
                    else:
                        value -= liquidation
                        loan -= liquidation
                        return DebtReferenceResult(
                            final_value=value,
                            success=False,
                            failure_month=month,
                            failure_state="margin_call_terminal",
                            final_loan=loan,
                            months_simulated=month,
                        )

            if value <= 0:
                return DebtReferenceResult(
                    final_value=_ZERO,
                    success=False,
                    failure_month=month,
                    failure_state="depleted",
                    final_loan=loan,
                    months_simulated=month,
                )
            if ltv_enforcement and loan > value and loan > 0:
                return DebtReferenceResult(
                    final_value=value,
                    success=False,
                    failure_month=month,
                    failure_state="margin_call_impossible",
                    final_loan=loan,
                    months_simulated=month,
                )

            if month < horizon - 1:
                value *= growth_factors[month]

            equity_curr = (
                equity_prices[month + 1]
                if month + 1 < len(equity_prices)
                else previous_equity
            )
            if previous_equity > 0:
                raw_drawdown = (
                    (_ONE + compound_drawdown) * equity_curr / previous_equity - _ONE
                )
                compound_drawdown = raw_drawdown if raw_drawdown < 0 else _ZERO
            else:
                compound_drawdown = _ZERO
            previous_equity = equity_curr

        return _apply_final_value_target(
            value,
            success=True,
            failure_month=None,
            failure_state=None,
            final_loan=loan,
            months_simulated=horizon,
            final_value_target=final_value_target,
            initial_wealth=initial_wealth,
        )


__all__ = [
    "DebtReferenceResult",
    "compute_monthly_rates",
    "simulate_part49_reference",
    "simulate_part52_reference",
]
