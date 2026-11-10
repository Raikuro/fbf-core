"""Unit tests for the external cash-flow schedule value object."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from fbf.core.domain.model.cash_flow import ExternalCashFlowSchedule
from fbf.core.domain.model.money import Currency, Money


def _money(amount: str = "3000") -> Money:
    return Money(Decimal(amount), Currency.EUR)


def test_amount_at_is_inclusive_start_and_exclusive_end() -> None:
    schedule = ExternalCashFlowSchedule(
        start_period=3,
        end_period=6,
        monthly_amount=_money(),
        horizon_transitions=10,
    )

    assert schedule.amount_at(2) == Money(Decimal("0"), Currency.EUR)
    assert schedule.amount_at(3) == _money()
    assert schedule.amount_at(5) == _money()
    assert schedule.amount_at(6) == Money(Decimal("0"), Currency.EUR)
    assert schedule.amount_at(9) == Money(Decimal("0"), Currency.EUR)


def test_schedule_is_immutable() -> None:
    schedule = ExternalCashFlowSchedule(
        start_period=0, end_period=1, monthly_amount=_money()
    )

    with pytest.raises(FrozenInstanceError):
        schedule.start_period = 1  # type: ignore[misc]


def test_negative_amount_is_supported() -> None:
    schedule = ExternalCashFlowSchedule(
        start_period=0, end_period=1, monthly_amount=_money("-100")
    )

    assert schedule.amount_at(0) == _money("-100")


def test_rejects_negative_start() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        ExternalCashFlowSchedule(
            start_period=-1, end_period=1, monthly_amount=_money()
        )


def test_rejects_empty_or_reversed_interval() -> None:
    with pytest.raises(ValueError, match="less than end_period"):
        ExternalCashFlowSchedule(
            start_period=2, end_period=2, monthly_amount=_money()
        )
    with pytest.raises(ValueError, match="less than end_period"):
        ExternalCashFlowSchedule(
            start_period=3, end_period=2, monthly_amount=_money()
        )


def test_rejects_non_finite_amount() -> None:
    with pytest.raises(ValueError, match="finite"):
        ExternalCashFlowSchedule(
            start_period=0,
            end_period=1,
            monthly_amount=Money(Decimal("Infinity"), Currency.EUR),
        )


def test_rejects_invalid_horizon() -> None:
    with pytest.raises(ValueError, match="positive"):
        ExternalCashFlowSchedule(
            start_period=0,
            end_period=1,
            monthly_amount=_money(),
            horizon_transitions=0,
        )
    with pytest.raises(ValueError, match="must not exceed"):
        ExternalCashFlowSchedule(
            start_period=0,
            end_period=6,
            monthly_amount=_money(),
            horizon_transitions=5,
        )


def test_rejects_wrong_types() -> None:
    with pytest.raises(TypeError, match="start_period"):
        ExternalCashFlowSchedule(
            start_period=0.0,  # type: ignore[arg-type]
            end_period=1,
            monthly_amount=_money(),
        )
    with pytest.raises(TypeError, match="monthly_amount"):
        ExternalCashFlowSchedule(
            start_period=0,
            end_period=1,
            monthly_amount=Decimal("3000"),  # type: ignore[arg-type]
        )
