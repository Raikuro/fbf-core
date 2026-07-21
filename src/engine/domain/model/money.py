"""Money value object for the Engine domain.

This module contains the Money value object used by monetary calculations.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from enum import Enum
from typing import Any, ClassVar


class Currency(Enum):
    EUR = "EUR"


@dataclass(frozen=True)
class Money:
    """Immutable monetary value object.

    Responsibilities:
    - represent a precise monetary amount
    - encapsulate Decimal-based money semantics

    Invariants:
    - amount is a Decimal
    - currency is a Currency
    """

    amount: Decimal
    currency: Currency

    ZERO: ClassVar["Money"]

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError("Money.amount must be a Decimal")
        if not isinstance(self.currency, Currency):
            raise TypeError("Money.currency must be a Currency")
        if self.amount.is_nan():
            raise ValueError("Money.amount must not be NaN")

    @classmethod
    def zero(cls) -> "Money":
        return cls.ZERO

    def __add__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, multiplier: Any) -> Money:
        if isinstance(multiplier, (int, Decimal)):
            return Money(self.amount * Decimal(multiplier), self.currency)
        return NotImplemented

    def __rmul__(self, multiplier: Any) -> Money:
        return self.__mul__(multiplier)

    def __truediv__(self, divisor: Any) -> Money:
        if isinstance(divisor, int):
            if divisor == 0:
                raise ZeroDivisionError("Division by zero is not allowed")
            return Money(self.amount / Decimal(divisor), self.currency)
        if isinstance(divisor, Decimal):
            if divisor == 0:
                raise ZeroDivisionError("Division by zero is not allowed")
            return Money(self.amount / divisor, self.currency)
        return NotImplemented

    def __lt__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.amount >= other.amount

    def quantize(self, quantum: Decimal, rounding: str = ROUND_HALF_EVEN) -> Money:
        try:
            quantized_amount = self.amount.quantize(quantum, rounding=rounding)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("Invalid quantization parameters") from exc
        return Money(quantized_amount, self.currency)

    def _assert_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise TypeError("Cannot operate on Money values with different currencies")


Money.ZERO = Money(Decimal("0"), Currency.EUR)
