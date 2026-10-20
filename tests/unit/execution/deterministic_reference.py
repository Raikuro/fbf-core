"""Independent Decimal reference for the deterministic two-asset kernel.

This module deliberately does not import the production deterministic adapter
or Numba kernel.  It computes the beginning-of-period recurrence with exact
Decimal arithmetic so tests can validate the float64 kernel independently.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext


@dataclass(frozen=True)
class ReferenceResult:
    values: tuple[Decimal, ...]
    actual_equity_weights: tuple[Decimal, ...]
    target_equity_weights: tuple[Decimal, ...]
    withdrawals: tuple[Decimal, ...]
    success: bool
    failure_month: int | None
    final_value: Decimal


def simulate_reference(
    equity_prices: Sequence[Decimal],
    bond_prices: Sequence[Decimal],
    target_equity_weights: Sequence[Decimal],
    rebalance_flags: Sequence[bool],
    *,
    fixed_withdrawal_amounts: Sequence[Decimal] | None,
    proportional_rate: Decimal | None,
    proportional_annual: bool,
    fee_annual: Decimal,
    initial_wealth: Decimal,
    initial_equity_weight: Decimal,
    horizon: int,
) -> ReferenceResult:
    """Run the reference recurrence over *horizon* monthly snapshots."""
    with localcontext() as context:
        context.prec = 50
        value = initial_wealth
        equity_units = (
            value * initial_equity_weight / equity_prices[0]
        )
        bond_units = (
            value * (Decimal("1") - initial_equity_weight) / bond_prices[0]
        )

        def withdrawal_at(month: int, current_value: Decimal) -> Decimal:
            if proportional_rate is not None:
                rate = proportional_rate
                if not proportional_annual:
                    rate /= Decimal("12")
                if proportional_annual and month % 12 != 0:
                    return Decimal("0")
                return current_value * rate
            assert fixed_withdrawal_amounts is not None
            return fixed_withdrawal_amounts[month]

        def rebalance(month: int, current_value: Decimal) -> None:
            nonlocal equity_units, bond_units
            if current_value > 0:
                equity_units = (
                    current_value * target_equity_weights[month] / equity_prices[month]
                )
                bond_units = (
                    current_value
                    * (Decimal("1") - target_equity_weights[month])
                    / bond_prices[month]
                )
            else:
                equity_units = Decimal("0")
                bond_units = Decimal("0")

        values: list[Decimal] = []
        actual_weights: list[Decimal] = []
        withdrawals: list[Decimal] = []

        withdrawal = withdrawal_at(0, value)
        if withdrawal > value:
            return ReferenceResult((), (), (), (), False, 0, Decimal("0"))

        value -= withdrawal
        if rebalance_flags[0]:
            rebalance(0, value)
        elif initial_wealth > 0:
            scale = value / initial_wealth
            equity_units *= scale
            bond_units *= scale

        values.append(value)
        withdrawals.append(withdrawal)
        if value > 0:
            actual_weights.append(
                equity_units * equity_prices[0] / value
            )
        else:
            actual_weights.append(target_equity_weights[0])

        for month in range(1, horizon):
            begin_value = value
            gross_value = (
                equity_units * equity_prices[month]
                + bond_units * bond_prices[month]
            )
            fee = begin_value * fee_annual / Decimal("12")
            value = gross_value - fee
            if value < 0:
                value = Decimal("0")
                equity_units = Decimal("0")
                bond_units = Decimal("0")
            elif gross_value > 0:
                scale = value / gross_value
                equity_units *= scale
                bond_units *= scale
            else:
                value = Decimal("0")
                equity_units = Decimal("0")
                bond_units = Decimal("0")

            withdrawal = withdrawal_at(month, value)
            if withdrawal > value:
                return ReferenceResult(
                    tuple(values),
                    tuple(actual_weights),
                    tuple(target_equity_weights[:month]),
                    tuple(withdrawals),
                    False,
                    month,
                    Decimal("0"),
                )

            value -= withdrawal
            if rebalance_flags[month]:
                rebalance(month, value)

            values.append(value)
            withdrawals.append(withdrawal)
            if value > 0:
                actual_weights.append(
                    equity_units * equity_prices[month] / value
                )
            else:
                actual_weights.append(target_equity_weights[month])

        return ReferenceResult(
            tuple(values),
            tuple(actual_weights),
            tuple(target_equity_weights[:horizon]),
            tuple(withdrawals),
            True,
            None,
            value,
        )


__all__ = ["ReferenceResult", "simulate_reference"]
