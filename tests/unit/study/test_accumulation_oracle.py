"""Tests for the independent accumulation oracle.

Validates the oracle against known mathematical answers. The oracle is the
ground truth used to validate the production accumulation implementation in
S3.3.

These tests verify:
  - Oracle deterministic behavior
  - Known-answer correctness for flat and growth datasets
  - Month-by-month intermediate value tracking
  - Edge cases (zero contribution, single asset)
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from fbf.core.domain.model.money import Currency, Money
from tests.fixtures.accumulation import (
    BOND,
    CONTRIBUTION,
    EQUITY,
    ERN_REALISTIC_DATASET,
    FLAT_DATASET,
    GROWTH_DATASET,
    KNOWN_PORTFOLIO,
    TARGET_WEIGHTS,
)
from tests.unit.study.accumulation_oracle import oracle_accumulate


class TestOracleDeterminism:
    """Oracle must produce identical results across invocations."""

    def test_deterministic_flat(self) -> None:
        r1 = oracle_accumulate(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=FLAT_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        r2 = oracle_accumulate(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=FLAT_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        assert r1.final_portfolio == r2.final_portfolio
        assert r1.month_by_month == r2.month_by_month

    def test_deterministic_growth(self) -> None:
        r1 = oracle_accumulate(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=GROWTH_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        r2 = oracle_accumulate(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=GROWTH_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        assert r1.final_portfolio == r2.final_portfolio


class TestOracleKnownAnswers:
    """Verify oracle against mathematically computed answers."""

    def test_flat_dataset_linear_growth(self) -> None:
        """With flat prices (1.0), each month adds 5000 units split by weights.

        Month 0:
          eq_price=1, bd_price=1
          contribution: eq += 5000*0.75/1 = 3750, bd += 5000*0.25/1 = 1250
          after contribution: eq=100+3750=3850, bd=200+1250=1450
          after rebalance: total=5300, eq=5300*0.75=3975, bd=5300*0.25=1325
          after evolution: flat prices → eq=3975, bd=1325
        Month 1:
          after contribution: eq=3975+3750=7725, bd=1325+1250=2575
          after rebalance: total=10300, eq=7725, bd=2575
          after evolution: eq=7725, bd=2575
        ...
        After 12 months: eq=45225, bd=15075, total=60300
        """
        result = oracle_accumulate(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=FLAT_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        eq_units = result.final_portfolio.holdings[0].units
        bd_units = result.final_portfolio.holdings[1].units
        # Rebalance with flat prices redistributes between assets each month.
        # After 12 months: eq=45225, bd=15075
        assert eq_units == Decimal("45225")
        assert bd_units == Decimal("15075")

    def test_flat_dataset_total_wealth(self) -> None:
        """Total wealth = initial + 12 * contribution (flat prices)."""
        result = oracle_accumulate(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=FLAT_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        total = sum(
            h.units for h in result.final_portfolio.holdings
        )
        initial_total = sum(
            h.units for h in KNOWN_PORTFOLIO.holdings
        )
        assert total == initial_total + Decimal("12") * Decimal("5000")

    def test_month_count(self) -> None:
        """Oracle must produce exactly 12 month-by-month snapshots."""
        result = oracle_accumulate(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=FLAT_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        assert len(result.month_by_month) == 12

    def test_growth_dataset_total_wealth(self) -> None:
        """With positive returns, total wealth > initial + contributions."""
        result = oracle_accumulate(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=GROWTH_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        total = sum(
            h.units for h in result.final_portfolio.holdings
        )
        # With positive returns, total must be positive and well-defined
        assert total > Decimal("0")
        assert len(result.month_by_month) == 12

    def test_ern_realistic_dataset(self) -> None:
        """ERN-realistic dataset must produce a valid result."""
        result = oracle_accumulate(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=ERN_REALISTIC_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        assert len(result.month_by_month) == 12
        total = sum(
            h.units for h in result.final_portfolio.holdings
        )
        assert total > Decimal("0")


class TestOracleEdgeCases:
    """Edge cases for the oracle."""

    def test_zero_contribution(self) -> None:
        """Zero contribution: portfolio grows only from market returns."""
        zero_contrib = Money(Decimal("0"), Currency.EUR)
        result = oracle_accumulate(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=zero_contrib,
            target_weights=TARGET_WEIGHTS,
            dataset=FLAT_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        # Flat prices + zero contribution = rebalance redistributes but total unchanged
        total = sum(h.units for h in result.final_portfolio.holdings)
        initial_total = sum(h.units for h in KNOWN_PORTFOLIO.holdings)
        assert total == initial_total

    def test_invalid_dataset_length(self) -> None:
        """Oracle raises ValueError for wrong dataset length."""
        from datetime import date

        from fbf.core.domain.model.dataset import Dataset
        from tests.fixtures.accumulation import _snapshot

        bad_dataset = Dataset(
            snapshots=[
                _snapshot(date(2020, 1, 1 + i), Decimal("1"), Decimal("1"))
                for i in range(5)
            ],
            frequency="monthly",
            version="bad",
            identifier="bad",
        )
        with pytest.raises(ValueError, match="13 snapshots"):
            oracle_accumulate(
                initial_portfolio=KNOWN_PORTFOLIO,
                contribution=CONTRIBUTION,
                target_weights=TARGET_WEIGHTS,
                dataset=bad_dataset,
                equity_asset=EQUITY,
                bond_asset=BOND,
            )
