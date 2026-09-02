"""Tests for the production accumulation implementation.

Validates the production accumulation phase against the independent oracle.
The production implementation must produce numerically identical results to
the oracle on all controlled fixtures.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from fbf.core.study.internal.accumulation import run_accumulation_phase
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


def _assert_portfolios_equal(
    production: object,
    oracle: object,
    label: str,
) -> None:
    """Assert two portfolios have identical holdings."""
    prod_holdings = {h.asset_class: h.units for h in production.holdings}
    oracle_holdings = {h.asset_class: h.units for h in oracle.holdings}
    assert prod_holdings.keys() == oracle_holdings.keys(), (
        f"{label}: asset mismatch"
    )
    for asset in prod_holdings:
        assert prod_holdings[asset] == oracle_holdings[asset], (
            f"{label}: {asset.id} mismatch — "
            f"production={prod_holdings[asset]}, oracle={oracle_holdings[asset]}"
        )


class TestProductionVsOracle:
    """Production must match independent oracle on all fixtures."""

    @pytest.fixture()
    def _flat_result(self):
        prod = run_accumulation_phase(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=FLAT_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        orc = oracle_accumulate(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=FLAT_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        return prod, orc

    @pytest.fixture()
    def _growth_result(self):
        prod = run_accumulation_phase(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=GROWTH_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        orc = oracle_accumulate(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=GROWTH_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        return prod, orc

    @pytest.fixture()
    def _ern_result(self):
        prod = run_accumulation_phase(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=ERN_REALISTIC_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        orc = oracle_accumulate(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=ERN_REALISTIC_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        return prod, orc

    def test_flat_final_portfolio(self, _flat_result) -> None:
        prod, orc = _flat_result
        _assert_portfolios_equal(prod.final_portfolio, orc.final_portfolio, "flat-final")

    def test_flat_month_by_month(self, _flat_result) -> None:
        prod, orc = _flat_result
        assert len(prod.month_by_month) == len(orc.month_by_month)
        for i, (p, o) in enumerate(
            zip(prod.month_by_month, orc.month_by_month, strict=True)
        ):
            _assert_portfolios_equal(p, o, f"flat-month-{i}")

    def test_growth_final_portfolio(self, _growth_result) -> None:
        prod, orc = _growth_result
        _assert_portfolios_equal(prod.final_portfolio, orc.final_portfolio, "growth-final")

    def test_growth_month_by_month(self, _growth_result) -> None:
        prod, orc = _growth_result
        for i, (p, o) in enumerate(
            zip(prod.month_by_month, orc.month_by_month, strict=True)
        ):
            _assert_portfolios_equal(p, o, f"growth-month-{i}")

    def test_ern_final_portfolio(self, _ern_result) -> None:
        prod, orc = _ern_result
        _assert_portfolios_equal(prod.final_portfolio, orc.final_portfolio, "ern-final")

    def test_ern_month_by_month(self, _ern_result) -> None:
        prod, orc = _ern_result
        for i, (p, o) in enumerate(
            zip(prod.month_by_month, orc.month_by_month, strict=True)
        ):
            _assert_portfolios_equal(p, o, f"ern-month-{i}")


class TestProductionDeterminism:
    """Production accumulation must be deterministic."""

    def test_deterministic(self) -> None:
        r1 = run_accumulation_phase(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=FLAT_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        r2 = run_accumulation_phase(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=FLAT_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        assert r1.final_portfolio == r2.final_portfolio
        assert r1.month_by_month == r2.month_by_month


class TestProductionEdgeCases:
    """Edge cases for the production implementation."""

    def test_invalid_dataset_length(self) -> None:
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
            run_accumulation_phase(
                initial_portfolio=KNOWN_PORTFOLIO,
                contribution=CONTRIBUTION,
                target_weights=TARGET_WEIGHTS,
                dataset=bad_dataset,
                equity_asset=EQUITY,
                bond_asset=BOND,
            )

    def test_month_count(self) -> None:
        result = run_accumulation_phase(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=FLAT_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        assert len(result.month_by_month) == 12
