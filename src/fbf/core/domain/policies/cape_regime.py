"""CAPE regime classification for retirement cohort analysis.

Classifies historical retirement start dates into four CAPE regimes
as used in the Early Retirement Now (ERN) Part 3 equity valuation study.

Regime boundaries (inclusive/exclusive):
    CAPE < 15           -> BELOW_15
    15 <= CAPE < 20     -> MODERATE
    20 <= CAPE < 30     -> HIGH
    CAPE >= 30          -> EXTREME

Boundary behaviour is explicit:
    - CAPE exactly 15.00 falls in MODERATE (min_inclusive=15)
    - CAPE exactly 20.00 falls in HIGH   (min_inclusive=20)
    - CAPE exactly 30.00 falls in EXTREME (min_inclusive=30)
    - CAPE below 15.00    falls in BELOW_15 (max_exclusive=15)

The classification uses the CAPE value known at the retirement start date,
never future CAPE values, to avoid look-ahead bias.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from decimal import Decimal, InvalidOperation
from typing import Optional


class CapeRegime(Enum):
    """The four CAPE regimes used in the ERN Part 3 study."""

    BELOW_15 = auto()
    """CAPE < 15: low valuation regime"""

    MODERATE = auto()
    """15 <= CAPE < 20: moderate valuation regime"""

    HIGH = auto()
    """20 <= CAPE < 30: high valuation regime"""

    EXTREME = auto()
    """CAPE >= 30: extremely high valuation regime"""


@dataclass(frozen=True)
class CapeRegimeClassification:
    """Immutable CAPE regime classification result.

    Attributes:
        regime: The CAPE regime category.
        cape_value: The CAPE value at the retirement start date, or None if unavailable.
    """

    regime: CapeRegime
    cape_value: Optional[Decimal] = None


def classify_cape_regime(cape: Decimal) -> CapeRegime:
    """Classify a CAPE value into one of the four regimes.

    Boundary behaviour:
        - CAPE < 15           -> BELOW_15
        - CAPE == 15          -> MODERATE (min_inclusive)
        - 15 < CAPE < 20     -> MODERATE
        - CAPE == 20          -> HIGH   (min_inclusive)
        - 20 < CAPE < 30     -> HIGH
        - CAPE == 30          -> EXTREME (min_inclusive)
        - CAPE > 30           -> EXTREME

    Args:
        cape: The CAPE value at the retirement start date.

    Returns:
        The corresponding CapeRegime enum value.

    Raises:
        ValueError: If cape is negative or otherwise invalid.
    """
    if cape < 0:
        raise ValueError(f"CAPE cannot be negative: {cape}")

    if cape < Decimal("15"):
        return CapeRegime.BELOW_15
    elif cape < Decimal("20"):
        return CapeRegime.MODERATE
    elif cape < Decimal("30"):
        return CapeRegime.HIGH
    else:
        return CapeRegime.EXTREME


def classify_cape_regime_from_decimal_string(
    cape_str: str,
) -> tuple[CapeRegime, Decimal]:
    """Classify a CAPE value given as a decimal string.

    Returns (regime, cape_decimal) tuple for convenience.

    Args:
        cape_str: CAPE value as a string (e.g. "14.99", "15.00", "29.99").

    Returns:
        Tuple of (CapeRegime, Decimal) representing the classification.

    Raises:
        ValueError: If the string cannot be parsed as a valid Decimal.
    """
    try:
        cape = Decimal(cape_str)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid CAPE value: {cape_str!r}") from exc

    regime = classify_cape_regime(cape)
    return regime, cape


# Convenience functions for common test cases
def test_boundary(cape_value: str, expected_regime: CapeRegime) -> bool:
    """Test a CAPE boundary case.

    Args:
        cape_value: CAPE value as string.
        expected_regime: Expected regime enum.

    Returns:
        True if classification matches expected, False otherwise.
    """
    regime, _ = classify_cape_regime_from_decimal_string(cape_value)
    return regime == expected_regime


# Pre-defined boundary test cases (from requirement #13)
BOUNDARY_TEST_CASES = [
    # (cape_string, expected_regime)
    ("14.99", CapeRegime.BELOW_15),  # Just below 15
    ("15.00", CapeRegime.MODERATE),  # Exactly 15 -> MODERATE
    ("19.99", CapeRegime.MODERATE),  # Just below 20
    ("20.00", CapeRegime.HIGH),  # Exactly 20 -> HIGH
    ("29.99", CapeRegime.HIGH),  # Just below 30
    ("30.00", CapeRegime.EXTREME),  # Exactly 30 -> EXTREME
]

# Assert all boundary test cases pass at import time
for cape_str, expected in BOUNDARY_TEST_CASES:
    actual, _ = classify_cape_regime_from_decimal_string(cape_str)
    assert actual == expected, f"Boundary test failed: {cape_str} -> {actual}, expected {expected}"