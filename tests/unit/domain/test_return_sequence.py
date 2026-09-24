"""Unit tests for ReturnSequence and annual-to-monthly conversion.

Verifies the prescribed deterministic return sequence abstraction
and the documented annual-to-monthly conversion assumption.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from fbf.core.domain.model.return_sequence import (
    ReturnSequence,
    annual_to_monthly,
    expand_annual_to_monthly,
)

# Tolerance for Decimal compounding precision
_COMPOUND_TOLERANCE = Decimal("0.000000001")  # 1e-9


def _compounds_to(monthly: Decimal, annual: Decimal) -> bool:
    """Check if monthly return compounds to annual within tolerance."""
    compounded = (Decimal("1") + monthly) ** 12 - Decimal("1")
    return abs(compounded - annual) < _COMPOUND_TOLERANCE


class TestReturnSequence:
    """Tests for ReturnSequence construction and validation."""

    def test_valid_construction(self) -> None:
        eq_returns = tuple(Decimal("0.01") for _ in range(120))
        bond_returns = tuple(Decimal("0.005") for _ in range(120))
        seq = ReturnSequence(
            equity_returns=eq_returns,
            bond_returns=bond_returns,
            start_date=date(1929, 9, 1),
            name="Test_Sequence",
        )
        assert len(seq.equity_returns) == 120
        assert len(seq.bond_returns) == 120
        assert seq.start_date == date(1929, 9, 1)
        assert seq.frequency == "monthly"
        assert seq.name == "Test_Sequence"

    def test_invalid_equity_returns_length(self) -> None:
        eq_returns = tuple(Decimal("0.01") for _ in range(119))
        bond_returns = tuple(Decimal("0.005") for _ in range(120))
        with pytest.raises(ValueError, match="exactly 120 equity returns"):
            ReturnSequence(
                equity_returns=eq_returns,
                bond_returns=bond_returns,
                start_date=date(1929, 9, 1),
            )

    def test_invalid_bond_returns_length(self) -> None:
        eq_returns = tuple(Decimal("0.01") for _ in range(120))
        bond_returns = tuple(Decimal("0.005") for _ in range(119))
        with pytest.raises(ValueError, match="exactly 120 bond returns"):
            ReturnSequence(
                equity_returns=eq_returns,
                bond_returns=bond_returns,
                start_date=date(1929, 9, 1),
            )

    def test_invalid_frequency(self) -> None:
        eq_returns = tuple(Decimal("0.01") for _ in range(120))
        bond_returns = tuple(Decimal("0.005") for _ in range(120))
        with pytest.raises(ValueError, match="frequency must be 'monthly'"):
            ReturnSequence(
                equity_returns=eq_returns,
                bond_returns=bond_returns,
                start_date=date(1929, 9, 1),
                frequency="annual",
            )


class TestReturnSequenceReverse:
    """Tests for ReturnSequence.reverse() semantics.

    The Bear→Bull and Bull→Bear sequences must be conceptually different
    annual sequences. Reverse operates at the annual source level
    conceptually (reverses the 120 monthly returns as a unit).
    """

    def test_reverse_returns_new_sequence(self) -> None:
        eq_returns = tuple(Decimal(str(i)) for i in range(120))
        bond_returns = tuple(Decimal(str(i * 2)) for i in range(120))
        seq = ReturnSequence(
            equity_returns=eq_returns,
            bond_returns=bond_returns,
            start_date=date(1929, 9, 1),
            name="BearBull",
        )
        reversed_seq = seq.reverse()

        assert reversed_seq.equity_returns == tuple(reversed(eq_returns))
        assert reversed_seq.bond_returns == tuple(reversed(bond_returns))
        assert reversed_seq.start_date == date(1929, 9, 1)
        assert reversed_seq.name == "BearBull_reversed"

    def test_reverse_preserves_lengths(self) -> None:
        eq_returns = tuple(Decimal("0.01") for _ in range(120))
        bond_returns = tuple(Decimal("0.005") for _ in range(120))
        seq = ReturnSequence(
            equity_returns=eq_returns,
            bond_returns=bond_returns,
            start_date=date(1929, 9, 1),
        )
        reversed_seq = seq.reverse()
        assert len(reversed_seq.equity_returns) == 120
        assert len(reversed_seq.bond_returns) == 120

    def test_reverse_name_empty(self) -> None:
        eq_returns = tuple(Decimal("0.01") for _ in range(120))
        bond_returns = tuple(Decimal("0.005") for _ in range(120))
        seq = ReturnSequence(
            equity_returns=eq_returns,
            bond_returns=bond_returns,
            start_date=date(1929, 9, 1),
            name="",
        )
        reversed_seq = seq.reverse()
        assert reversed_seq.name == "reversed"


class TestAnnualToMonthly:
    """Tests for the documented annual-to-monthly conversion.

    monthly_return = (1 + annual_return) ** (1/12) - 1

    This is an implementation adapter — NOT claimed to be an
    article-published monthly series. Each 12-month block must
    compound exactly to its source annual return (within Decimal precision).
    """

    def test_zero_return(self) -> None:
        monthly = annual_to_monthly(Decimal("0"))
        assert monthly == Decimal("0")

    def test_positive_return(self) -> None:
        annual = Decimal("0.10")  # 10%
        monthly = annual_to_monthly(annual)
        # (1 + monthly)^12 - 1 should equal annual (within tolerance)
        assert _compounds_to(monthly, annual)

    def test_negative_return(self) -> None:
        annual = Decimal("-0.20")  # -20%
        monthly = annual_to_monthly(annual)
        assert _compounds_to(monthly, annual)

    def test_exact_compounding_property(self) -> None:
        """Each 12-month block must compound exactly to source annual return."""
        test_rates = [
            Decimal("0.00"),
            Decimal("0.01"),
            Decimal("0.05"),
            Decimal("0.10"),
            Decimal("0.20"),
            Decimal("-0.10"),
            Decimal("-0.25"),
            Decimal("0.50"),
        ]
        for annual in test_rates:
            monthly = annual_to_monthly(annual)
            assert _compounds_to(monthly, annual), (
                f"Failed for annual={annual}: monthly={monthly}"
            )


class TestExpandAnnualToMonthly:
    """Tests for expanding 10 annual returns to 120 monthly returns."""

    def test_expand_10_annual_to_120_monthly(self) -> None:
        annual_returns = tuple(Decimal("0.10") for _ in range(10))
        monthly = expand_annual_to_monthly(annual_returns)
        assert len(monthly) == 120

    def test_each_annual_expands_to_12_identical_monthly(self) -> None:
        annual_returns: tuple[Decimal, ...] = (Decimal("0.10"), Decimal("0.05"), Decimal("0.00"))
        # Only 3 for testing, but function requires 10
        annual_returns = tuple(list(annual_returns) + [Decimal("0.00")] * 7)
        monthly = expand_annual_to_monthly(annual_returns)

        # First 12 should be identical (from 10%)
        first_12 = monthly[:12]
        assert all(m == first_12[0] for m in first_12)

        # Next 12 should be identical (from 5%)
        next_12 = monthly[12:24]
        assert all(m == next_12[0] for m in next_12)

    def test_invalid_annual_count_raises(self) -> None:
        annual_returns = tuple(Decimal("0.10") for _ in range(9))
        with pytest.raises(ValueError, match="Expected 10 annual returns"):
            expand_annual_to_monthly(annual_returns)

        annual_returns = tuple(Decimal("0.10") for _ in range(11))
        with pytest.raises(ValueError, match="Expected 10 annual returns"):
            expand_annual_to_monthly(annual_returns)

    def test_compounding_preserved_per_block(self) -> None:
        """Each 12-month block compounds exactly to its source annual return."""
        annual_returns = (
            Decimal("0.10"),
            Decimal("0.05"),
            Decimal("0.00"),
            Decimal("-0.10"),
            Decimal("0.20"),
            Decimal("-0.25"),
            Decimal("0.07"),
            Decimal("0.03"),
            Decimal("-0.05"),
            Decimal("0.15"),
        )
        monthly = expand_annual_to_monthly(annual_returns)

        for i, annual in enumerate(annual_returns):
            block = monthly[i * 12 : (i + 1) * 12]
            # All 12 in block should be identical
            assert all(m == block[0] for m in block)
            # Block should compound to annual (within tolerance)
            assert _compounds_to(block[0], annual), f"Block {i} failed: {block[0]} -> {annual}"
