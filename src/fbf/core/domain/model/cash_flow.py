"""External cash-flow schedule value object.

The engine's withdrawal policies model outflows from the portfolio.  Some
research scenarios also require external inflows (for example Social
Security).  This module represents a single contiguous, constant, monthly
external cash-flow interval in transition-period space.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from fbf.core.domain.model.money import Money


@dataclass(frozen=True, slots=True)
class ExternalCashFlowSchedule:
    """Immutable monthly external cash-flow interval.

    Period indices are simulation transition indices.  ``start_period`` is
    inclusive and ``end_period`` is exclusive, so the schedule covers periods
    ``start_period .. end_period - 1``.  A positive ``monthly_amount`` is an
    inflow to the portfolio; a negative amount is an outflow supported by the
    portfolio.  ``amount_at`` returns zero outside the interval.

    ``horizon_transitions`` is optional so callers can validate a schedule
    against a simulation horizon when the two are known together.  When it is
    provided, the interval must fit entirely inside that horizon.
    """

    start_period: int
    end_period: int
    monthly_amount: Money
    horizon_transitions: int | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.start_period, int)
            or isinstance(self.start_period, bool)
        ):
            raise TypeError("ExternalCashFlowSchedule.start_period must be an int")
        if (
            not isinstance(self.end_period, int)
            or isinstance(self.end_period, bool)
        ):
            raise TypeError("ExternalCashFlowSchedule.end_period must be an int")
        if self.start_period < 0:
            raise ValueError(
                "ExternalCashFlowSchedule.start_period must be non-negative"
            )
        if self.start_period >= self.end_period:
            raise ValueError(
                "ExternalCashFlowSchedule.start_period must be less than end_period"
            )
        if not isinstance(self.monthly_amount, Money):
            raise TypeError(
                "ExternalCashFlowSchedule.monthly_amount must be a Money instance"
            )
        if not self.monthly_amount.amount.is_finite():
            raise ValueError(
                "ExternalCashFlowSchedule.monthly_amount must be finite"
            )
        if self.horizon_transitions is not None:
            if (
                not isinstance(self.horizon_transitions, int)
                or isinstance(self.horizon_transitions, bool)
            ):
                raise TypeError(
                    "ExternalCashFlowSchedule.horizon_transitions must be an int or None"
                )
            if self.horizon_transitions <= 0:
                raise ValueError(
                    "ExternalCashFlowSchedule.horizon_transitions must be positive"
                )
            if self.end_period > self.horizon_transitions:
                raise ValueError(
                    "ExternalCashFlowSchedule.end_period must not exceed "
                    "horizon_transitions"
                )

    def amount_at(self, period: int) -> Money:
        """Return the signed external amount at *period*.

        The returned value is positive for an inflow and negative for an
        outflow.  Periods outside ``[start_period, end_period)`` return zero.
        """
        if self.start_period <= period < self.end_period:
            return self.monthly_amount
        return Money(Decimal("0"), self.monthly_amount.currency)


__all__ = ["ExternalCashFlowSchedule"]
