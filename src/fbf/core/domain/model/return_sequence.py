"""ReturnSequence domain model for prescribed deterministic returns.

This module provides the ReturnSequence abstraction that represents
prescribed deterministic return sequences at the domain layer.

The prescribed Experiment E source data is annual, but the existing
simulation engine consumes monthly returns. The annual-to-monthly
conversion uses the documented assumption:

    monthly_return = (1 + annual_return) ** (1/12) - 1

IMPORTANT: Each 12-month block must compound exactly to its source
annual return. This monthly series is an implementation adapter — it
is NOT claimed to be an article-published monthly sequence.

Bull→Bear reversal occurs at the ANNUAL sequence level BEFORE monthly
expansion. Do not rely on reversing an already-expanded sequence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, DecimalException

_MIN_RETURN = Decimal("-1")


def _validate_return_value(
    value: object,
    *,
    context: str,
    field: str,
    index: int | None = None,
) -> None:
    """Validate one simple return against the supported mathematical domain."""
    location = f"{context} {field}" if index is None else f"{context} {field}[{index}]"
    if not isinstance(value, Decimal):
        raise TypeError(f"{location} must be a Decimal")
    if not value.is_finite():
        raise ValueError(f"{location} must be finite")
    if value < _MIN_RETURN:
        raise ValueError(
            f"{location} must be greater than or equal to -1"
        )


@dataclass(frozen=True, slots=True)
class ReturnSequence:
    """Prescribed deterministic return sequence (domain layer).

    Represents monthly equity and bond returns derived from prescribed
    annual source data via the documented annual-to-monthly conversion.
    Returns must be finite Decimal fractions greater than or equal to -1.
    A return of exactly -1 is a mathematically valid total loss.

    Attributes
    ----------
    equity_returns:
        120 monthly equity returns (Decimal fractions, e.g. 0.01 for 1%).
    bond_returns:
        120 monthly bond returns (Decimal fractions).
    start_date:
        The date of the first monthly return period.
    frequency:
        Return frequency, always "monthly" for engine consumption.
    name:
        Optional identifier for the sequence (e.g., "ERN_Table01_BearBull").
    """

    equity_returns: tuple[Decimal, ...]
    bond_returns: tuple[Decimal, ...]
    start_date: date
    frequency: str = "monthly"
    name: str = ""

    def __post_init__(self) -> None:
        if len(self.equity_returns) != 120:
            raise ValueError(
                "ReturnSequence must have exactly 120 equity returns, "
                f"got {len(self.equity_returns)}"
            )
        if len(self.bond_returns) != 120:
            raise ValueError(
                "ReturnSequence must have exactly 120 bond returns, "
                f"got {len(self.bond_returns)}"
            )
        if self.frequency != "monthly":
            raise ValueError(
                f"ReturnSequence frequency must be 'monthly', got {self.frequency!r}"
            )
        for index, value in enumerate(self.equity_returns):
            _validate_return_value(
                value,
                context="ReturnSequence",
                field="equity_returns",
                index=index,
            )
        for index, value in enumerate(self.bond_returns):
            _validate_return_value(
                value,
                context="ReturnSequence",
                field="bond_returns",
                index=index,
            )

    def reverse(self) -> ReturnSequence:
        """Return a new sequence with annual source reversed before monthly expansion.

        The Bear→Bull and Bull→Bear sequences must be conceptually different
        annual sequences. This method reverses the annual source sequence
        before monthly expansion (conceptually), not the already-expanded
        monthly sequence.

        Returns
        -------
        ReturnSequence
            New sequence with reversed returns and updated name.
        """
        return ReturnSequence(
            equity_returns=tuple(reversed(self.equity_returns)),
            bond_returns=tuple(reversed(self.bond_returns)),
            start_date=self.start_date,
            frequency=self.frequency,
            name=f"{self.name}_reversed" if self.name else "reversed",
        )


def _convert_annual_to_monthly(
    annual_return: Decimal,
    *,
    context: str,
    field: str,
    index: int | None = None,
) -> Decimal:
    """Apply the documented conversion, reporting context-range failures clearly."""
    location = f"{context} {field}" if index is None else f"{context} {field}[{index}]"
    try:
        return (
            (Decimal("1") + annual_return)
            ** (Decimal("1") / Decimal("12"))
            - Decimal("1")
        )
    except DecimalException as exc:
        raise ValueError(
            f"{location} cannot be converted under the active Decimal context"
        ) from exc


def annual_to_monthly(annual_return: Decimal) -> Decimal:
    """Convert an annual return to a monthly return using geometric compounding.

    This is the documented implementation assumption for Experiment E:

        monthly_return = (1 + annual_return) ** (1/12) - 1

    Parameters
    ----------
    annual_return:
        Annual return as a Decimal fraction (e.g., Decimal("0.10") for 10%).
        Must be finite and greater than or equal to -1.

    Returns
    -------
    Decimal
        Monthly return that compounds to the annual return over 12 months.

    Notes
    -----
    The active Decimal context must be able to evaluate the documented
    expression. A valid finite input can still overflow an intermediate
    operation; this raises ``ValueError`` rather than leaking a raw decimal
    exception. No arbitrary upper bound is applied to the input domain.
    """
    _validate_return_value(
        annual_return,
        context="annual_to_monthly",
        field="annual_return",
    )
    return _convert_annual_to_monthly(
        annual_return,
        context="annual_to_monthly",
        field="annual_return",
    )


def expand_annual_to_monthly(annual_returns: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
    """Expand a tuple of 10 annual returns into 120 monthly returns.

    Each annual return is expanded into 12 identical monthly returns that
    compound exactly to the annual return.

    Parameters
    ----------
    annual_returns:
        Tuple of 10 annual returns (Decimal fractions). Each value must be
        finite and greater than or equal to -1.

    Returns
    -------
    tuple[Decimal, ...]
        Tuple of 120 monthly returns.

    Notes
    -----
    Context-range failures are reported with the annual-return index.
    """
    if len(annual_returns) != 10:
        raise ValueError(f"Expected 10 annual returns, got {len(annual_returns)}")

    for index, annual in enumerate(annual_returns):
        _validate_return_value(
            annual,
            context="expand_annual_to_monthly",
            field="annual_returns",
            index=index,
        )

    monthly = []
    for index, annual in enumerate(annual_returns):
        monthly_return = _convert_annual_to_monthly(
            annual,
            context="expand_annual_to_monthly",
            field="annual_returns",
            index=index,
        )
        monthly.extend([monthly_return] * 12)

    if len(monthly) != 120:
        raise ValueError(f"Expected 120 monthly returns after expansion, got {len(monthly)}")

    return tuple(monthly)
