"""Part 49 Experiment A: preliminary leverage calculation.

Reproduces the analytical relationship behind the article's Table 01.  The
table reports an implied annual spending rate for a fixed real margin loan,
given an initial portfolio, a final portfolio target, and a final loan target.

The published cells are reproduced within the table's 0.01 percentage-point
display precision by a constant annual loan draw with continuous compounding:

    annual_loan_draw = loan_target * rate / (exp(rate * horizon) - 1)

At a zero real rate the limit is ``loan_target / horizon``.  Sixteen of the 18
published cells match after rounding to two decimal percentage points; two
three-percent cells differ by one display unit, so the tests use the table's
display precision rather than a fabricated tighter tolerance.

This module is an analytical reconstruction of published methodology.  It does
not execute a simulation and does not validate the current canonical dataset.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

_ONE = Decimal("1")


@dataclass(frozen=True)
class Part49PreliminaryLeverage:
    """Result of the Part 49 preliminary leverage calculation."""

    initial_capital: Decimal
    final_portfolio_target: Decimal
    final_loan_target: Decimal
    real_interest_rate: Decimal
    horizon_years: int
    annual_loan_draw: Decimal
    implied_spending_rate: Decimal


def calculate_preliminary_leverage(
    *,
    initial_capital: Decimal,
    final_portfolio_target: Decimal,
    final_loan_target: Decimal,
    real_interest_rate: Decimal,
    horizon_years: int,
) -> Part49PreliminaryLeverage:
    """Calculate the implied spending rate for a final margin loan target."""
    if initial_capital <= 0:
        raise ValueError("initial_capital must be positive")
    if final_portfolio_target <= 0:
        raise ValueError("final_portfolio_target must be positive")
    if final_loan_target < 0:
        raise ValueError("final_loan_target must be non-negative")
    if final_loan_target > final_portfolio_target:
        raise ValueError("final_loan_target cannot exceed final_portfolio_target")
    if real_interest_rate < 0:
        raise ValueError("real_interest_rate must be non-negative")
    if horizon_years <= 0:
        raise ValueError("horizon_years must be positive")

    horizon = Decimal(horizon_years)
    if real_interest_rate == 0:
        annual_loan_draw = final_loan_target / horizon
    else:
        growth = (real_interest_rate * horizon).exp()
        annual_loan_draw = (
            final_loan_target * real_interest_rate / (growth - _ONE)
        )

    return Part49PreliminaryLeverage(
        initial_capital=initial_capital,
        final_portfolio_target=final_portfolio_target,
        final_loan_target=final_loan_target,
        real_interest_rate=real_interest_rate,
        horizon_years=horizon_years,
        annual_loan_draw=annual_loan_draw,
        implied_spending_rate=annual_loan_draw / initial_capital,
    )
