"""Part 49 Experiment A: published Table 01 analytical reproduction."""

from __future__ import annotations

from decimal import Decimal

import pytest

from fbf.core.research.part49_preliminary import (
    calculate_preliminary_leverage,
)

_INITIAL_CAPITAL = Decimal("1000000")
_FINAL_PORTFOLIO_TARGET = Decimal("3000000")
_HORIZON_YEARS = 30
_TABLE_DISPLAY_PRECISION = Decimal("0.0001")

_TABLE_01: dict[tuple[Decimal, Decimal], Decimal] = {
    (Decimal("2250000"), Decimal("0")): Decimal("0.0750"),
    (Decimal("2250000"), Decimal("0.015")): Decimal("0.0594"),
    (Decimal("2250000"), Decimal("0.03")): Decimal("0.0462"),
    (Decimal("2000000"), Decimal("0")): Decimal("0.0667"),
    (Decimal("2000000"), Decimal("0.015")): Decimal("0.0528"),
    (Decimal("2000000"), Decimal("0.03")): Decimal("0.0411"),
    (Decimal("1750000"), Decimal("0")): Decimal("0.0583"),
    (Decimal("1750000"), Decimal("0.015")): Decimal("0.0462"),
    (Decimal("1750000"), Decimal("0.03")): Decimal("0.0359"),
    (Decimal("1500000"), Decimal("0")): Decimal("0.0500"),
    (Decimal("1500000"), Decimal("0.015")): Decimal("0.0396"),
    (Decimal("1500000"), Decimal("0.03")): Decimal("0.0308"),
    (Decimal("1250000"), Decimal("0")): Decimal("0.0417"),
    (Decimal("1250000"), Decimal("0.015")): Decimal("0.0330"),
    (Decimal("1250000"), Decimal("0.03")): Decimal("0.0257"),
    (Decimal("1000000"), Decimal("0")): Decimal("0.0333"),
    (Decimal("1000000"), Decimal("0.015")): Decimal("0.0264"),
    (Decimal("1000000"), Decimal("0.03")): Decimal("0.0205"),
}

_TABLE_01_CASES = [
    pytest.param(
        loan_target,
        real_rate,
        expected_rate,
        id=f"loan_{loan_target}_rate_{real_rate}",
    )
    for (loan_target, real_rate), expected_rate in _TABLE_01.items()
]


def _calculate(
    loan_target: Decimal,
    real_rate: Decimal,
) -> Decimal:
    result = calculate_preliminary_leverage(
        initial_capital=_INITIAL_CAPITAL,
        final_portfolio_target=_FINAL_PORTFOLIO_TARGET,
        final_loan_target=loan_target,
        real_interest_rate=real_rate,
        horizon_years=_HORIZON_YEARS,
    )
    return result.implied_spending_rate


@pytest.mark.parametrize(
    ("final_loan_target", "real_interest_rate", "expected_spending_rate"),
    _TABLE_01_CASES,
)
def test_reproduces_published_table_01(
    final_loan_target: Decimal,
    real_interest_rate: Decimal,
    expected_spending_rate: Decimal,
) -> None:
    actual = _calculate(final_loan_target, real_interest_rate)
    assert abs(actual - expected_spending_rate) <= _TABLE_DISPLAY_PRECISION


def test_zero_rate_limit_is_linear_amortization() -> None:
    loan_target = Decimal("2250000")
    result = calculate_preliminary_leverage(
        initial_capital=_INITIAL_CAPITAL,
        final_portfolio_target=_FINAL_PORTFOLIO_TARGET,
        final_loan_target=loan_target,
        real_interest_rate=Decimal("0"),
        horizon_years=_HORIZON_YEARS,
    )

    assert result.annual_loan_draw == loan_target / Decimal(_HORIZON_YEARS)
    assert result.implied_spending_rate == Decimal("0.075")


def test_higher_real_rate_reduces_implied_spending() -> None:
    draws = [
        calculate_preliminary_leverage(
            initial_capital=_INITIAL_CAPITAL,
            final_portfolio_target=_FINAL_PORTFOLIO_TARGET,
            final_loan_target=Decimal("2250000"),
            real_interest_rate=rate,
            horizon_years=_HORIZON_YEARS,
        ).annual_loan_draw
        for rate in (Decimal("0"), Decimal("0.015"), Decimal("0.03"))
    ]

    assert draws[0] > draws[1] > draws[2]


def test_maximum_loan_from_25_percent_margin_requirement() -> None:
    minimum_equity = _FINAL_PORTFOLIO_TARGET * Decimal("0.25")
    maximum_loan = _FINAL_PORTFOLIO_TARGET - minimum_equity

    assert minimum_equity == Decimal("750000")
    assert maximum_loan == Decimal("2250000")


@pytest.mark.parametrize(
    ("final_loan_target", "real_interest_rate"),
    [
        (Decimal("-1"), Decimal("0")),
        (Decimal("3000001"), Decimal("0")),
        (Decimal("1000000"), Decimal("-0.01")),
    ],
)
def test_rejects_invalid_analytical_inputs(
    final_loan_target: Decimal,
    real_interest_rate: Decimal,
) -> None:
    with pytest.raises(ValueError):
        calculate_preliminary_leverage(
            initial_capital=_INITIAL_CAPITAL,
            final_portfolio_target=_FINAL_PORTFOLIO_TARGET,
            final_loan_target=final_loan_target,
            real_interest_rate=real_interest_rate,
            horizon_years=_HORIZON_YEARS,
        )
