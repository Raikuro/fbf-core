"""Unit tests for CAPE regime classification and aggregation."""

from __future__ import annotations

from decimal import Decimal

import pytest

from fbf.core.domain.policies.cape_regime import (
    BOUNDARY_TEST_CASES,
    CapeRegime,
    CapeRegimeClassification,
    classify_cape_regime,
    classify_cape_regime_from_decimal_string,
)


class TestCapeRegimeBoundary:
    """Test CAPE regime boundary cases as specified in requirement #13."""

    def test_14_99_below_15(self) -> None:
        """14.99 -> <15"""
        regime, _ = classify_cape_regime_from_decimal_string("14.99")
        assert regime == CapeRegime.BELOW_15

    def test_15_00_moderate(self) -> None:
        """15.00 -> 15-20"""
        regime, _ = classify_cape_regime_from_decimal_string("15.00")
        assert regime == CapeRegime.MODERATE

    def test_19_99_moderate(self) -> None:
        """19.99 -> 15-20"""
        regime, _ = classify_cape_regime_from_decimal_string("19.99")
        assert regime == CapeRegime.MODERATE

    def test_20_00_high(self) -> None:
        """20.00 -> 20-30"""
        regime, _ = classify_cape_regime_from_decimal_string("20.00")
        assert regime == CapeRegime.HIGH

    def test_29_99_high(self) -> None:
        """29.99 -> 20-30"""
        regime, _ = classify_cape_regime_from_decimal_string("29.99")
        assert regime == CapeRegime.HIGH

    def test_30_00_extreme(self) -> None:
        """30.00 -> >30"""
        regime, _ = classify_cape_regime_from_decimal_string("30.00")
        assert regime == CapeRegime.EXTREME

    def test_all_boundary_cases(self) -> None:
        """Run all boundary test cases from BOUNDARY_TEST_CASES."""
        for cape_str, expected in BOUNDARY_TEST_CASES:
            regime, _ = classify_cape_regime_from_decimal_string(cape_str)
            assert regime == expected, (
                f"CAPE {cape_str} -> {regime.name}, expected {expected.name}"
            )


class TestCapeRegimeClassification:
    """Test general CAPE regime classification."""

    def test_10_below_15(self) -> None:
        """10.00 -> <15"""
        regime = classify_cape_regime(Decimal("10.00"))
        assert regime == CapeRegime.BELOW_15

    def test_15_moderate(self) -> None:
        """15.00 -> MODERATE"""
        regime = classify_cape_regime(Decimal("15.00"))
        assert regime == CapeRegime.MODERATE

    def test_17_modertate(self) -> None:
        """17.00 -> MODERATE"""
        regime = classify_cape_regime(Decimal("17.00"))
        assert regime == CapeRegime.MODERATE

    def test_25_high(self) -> None:
        """25.00 -> HIGH"""
        regime = classify_cape_regime(Decimal("25.00"))
        assert regime == CapeRegime.HIGH

    def test_30_extreme(self) -> None:
        """30.00 -> EXTREME"""
        regime = classify_cape_regime(Decimal("30.00"))
        assert regime == CapeRegime.EXTREME

    def test_35_extreme(self) -> None:
        """35.00 -> EXTREME"""
        regime = classify_cape_regime(Decimal("35.00"))
        assert regime == CapeRegime.EXTREME

    def test_negative_raises(self) -> None:
        """Negative CAPE should raise ValueError"""
        with pytest.raises(ValueError):
            classify_cape_regime(Decimal("-1.00"))

    def test_zero_is_below_15(self) -> None:
        """0.00 -> <15 (edge case)"""
        regime = classify_cape_regime(Decimal("0.00"))
        assert regime == CapeRegime.BELOW_15


class TestCapeRegimeClassificationImport:
    """Test that the module imports correctly and BOUNDARY_TEST_CASES are valid."""

    def test_boundary_cases_are_valid(self) -> None:
        """All BOUNDARY_TEST_CASES should pass at import time."""
        # This is already verified in the cape_regime module, but we test it here too
        for cape_str, expected in BOUNDARY_TEST_CASES:
            regime, _ = classify_cape_regime_from_decimal_string(cape_str)
            assert regime == expected


class TestCapeRegimeCapeRegimeClassification:
    """Test the CapeRegimeClassification dataclass."""

    def test_creation(self) -> None:
        """Can create CapeRegimeClassification instances."""
        classification = CapeRegimeClassification(
            regime=CapeRegime.BELOW_15, cape_value=Decimal("12.5")
        )
        assert classification.regime == CapeRegime.BELOW_15
        assert classification.cape_value == Decimal("12.5")

    def test_default_cape_value(self) -> None:
        """CapeRegimeClassification with None cape_value."""
        classification = CapeRegimeClassification(regime=CapeRegime.MODERATE)
        assert classification.regime == CapeRegime.MODERATE
        assert classification.cape_value is None
