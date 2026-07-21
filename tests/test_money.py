from __future__ import annotations

from decimal import Decimal

from engine.domain.model.money import Currency, Money


def test_money_addition_same_currency() -> None:
    money_a = Money(Decimal("100.00"), Currency.EUR)
    money_b = Money(Decimal("50.00"), Currency.EUR)

    result = money_a + money_b

    assert result.amount == Decimal("150.00")
    assert result.currency == Currency.EUR


def test_money_subtraction_same_currency() -> None:
    money_a = Money(Decimal("100.00"), Currency.EUR)
    money_b = Money(Decimal("50.00"), Currency.EUR)

    result = money_a - money_b

    assert result.amount == Decimal("50.00")
    assert result.currency == Currency.EUR


def test_money_multiplication_by_scalar() -> None:
    money = Money(Decimal("100.00"), Currency.EUR)

    result = money * 2

    assert result.amount == Decimal("200.00")
    assert result.currency == Currency.EUR


def test_money_division_by_scalar() -> None:
    money = Money(Decimal("100.00"), Currency.EUR)

    result = money / 4

    assert result.amount == Decimal("25.00")
    assert result.currency == Currency.EUR


def test_money_comparison_same_currency() -> None:
    money_a = Money(Decimal("100.00"), Currency.EUR)
    money_b = Money(Decimal("200.00"), Currency.EUR)

    assert money_a < money_b
    assert money_b > money_a
    assert money_a <= money_b
    assert money_b >= money_a
