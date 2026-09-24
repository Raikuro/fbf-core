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
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ReturnSequence:
    """Prescribed deterministic return sequence (domain layer).

    Represents monthly equity and bond returns derived from prescribed
    annual source data via the documented annual-to-monthly conversion.

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


def annual_to_monthly(annual_return: Decimal) -> Decimal:
    """Convert an annual return to a monthly return using geometric compounding.

    This is the documented implementation assumption for Experiment E:

        monthly_return = (1 + annual_return) ** (1/12) - 1

    Parameters
    ----------
    annual_return:
        Annual return as a Decimal fraction (e.g., Decimal("0.10") for 10%).

    Returns
    -------
    Decimal
        Monthly return that compounds to the annual return over 12 months.
    """
    return (Decimal("1") + annual_return) ** (Decimal("1") / Decimal("12")) - Decimal("1")


def expand_annual_to_monthly(annual_returns: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
    """Expand a tuple of 10 annual returns into 120 monthly returns.

    Each annual return is expanded into 12 identical monthly returns that
    compound exactly to the annual return.

    Parameters
    ----------
    annual_returns:
        Tuple of 10 annual returns (Decimal fractions).

    Returns
    -------
    tuple[Decimal, ...]
        Tuple of 120 monthly returns.
    """
    if len(annual_returns) != 10:
        raise ValueError(f"Expected 10 annual returns, got {len(annual_returns)}")

    monthly = []
    for annual in annual_returns:
        monthly_return = annual_to_monthly(annual)
        monthly.extend([monthly_return] * 12)

    if len(monthly) != 120:
        raise ValueError(f"Expected 120 monthly returns after expansion, got {len(monthly)}")

    return tuple(monthly)
