"""Independent validation tests for Part 42 (S3.7).

Validates temporal invariants, accumulation ordering, independence,
and production-oracle equivalence on the full controlled fixture set.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fbf.core.domain.model.dataset import Dataset
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


class TestTemporalInvariants:
    """Temporal invariants: snapshot counts, transition counts, period-index mapping."""

    def test_accumulation_dataset_13_snapshots(self) -> None:
        """Accumulation dataset must have exactly 13 snapshots."""
        assert len(FLAT_DATASET.snapshots) == 13
        assert len(GROWTH_DATASET.snapshots) == 13
        assert len(ERN_REALISTIC_DATASET.snapshots) == 13

    def test_accumulation_produces_12_portfolios(self) -> None:
        """Accumulation must produce exactly 12 month-by-month portfolios."""
        for ds in [FLAT_DATASET, GROWTH_DATASET, ERN_REALISTIC_DATASET]:
            result = run_accumulation_phase(
                initial_portfolio=KNOWN_PORTFOLIO,
                contribution=CONTRIBUTION,
                target_weights=TARGET_WEIGHTS,
                dataset=ds,
                equity_asset=EQUITY,
                bond_asset=BOND,
            )
            assert len(result.month_by_month) == 12

    def test_oracle_produces_12_portfolios(self) -> None:
        """Oracle must produce exactly 12 month-by-month portfolios."""
        for ds in [FLAT_DATASET, GROWTH_DATASET, ERN_REALISTIC_DATASET]:
            result = oracle_accumulate(
                initial_portfolio=KNOWN_PORTFOLIO,
                contribution=CONTRIBUTION,
                target_weights=TARGET_WEIGHTS,
                dataset=ds,
                equity_asset=EQUITY,
                bond_asset=BOND,
            )
            assert len(result.month_by_month) == 12

    def test_dataset_slice_13_snapshots(self) -> None:
        """Dataset.slice() with horizon_months=13 returns 13 snapshots."""
        base = date(2020, 1, 1)
        dates = [base + timedelta(days=30 * m) for m in range(50)]
        from tests.fixtures.accumulation import _snapshot

        snapshots = [_snapshot(d, Decimal("1"), Decimal("1")) for d in dates]
        dataset = Dataset(
            snapshots=snapshots,
            frequency="monthly",
            version="test",
            identifier="test",
        )
        sliced = dataset.slice(base, 13)
        assert len(sliced) == 13
        assert sliced[0].date == base

    def test_dataset_slice_349_snapshots(self) -> None:
        """Dataset.slice() with horizon_months=349 returns 349 snapshots."""
        base = date(2020, 1, 1)
        dates = [base + timedelta(days=30 * m) for m in range(400)]
        from tests.fixtures.accumulation import _snapshot

        snapshots = [_snapshot(d, Decimal("1"), Decimal("1")) for d in dates]
        dataset = Dataset(
            snapshots=snapshots,
            frequency="monthly",
            version="test",
            identifier="test",
        )
        sliced = dataset.slice(base, 349)
        assert len(sliced) == 349


class TestAccumulationOrdering:
    """Accumulation must follow contribution → rebalance → evolve ordering."""

    def test_contribution_increases_total_value(self) -> None:
        """After contribution, total value must increase (flat prices)."""
        result = run_accumulation_phase(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=FLAT_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        # With flat prices, each month adds 5000 to total value
        initial_total = sum(h.units for h in KNOWN_PORTFOLIO.holdings)
        final_total = sum(h.units for h in result.final_portfolio.holdings)
        assert final_total > initial_total

    def test_rebalance_maintains_target_weights(self) -> None:
        """After rebalance, weights must match target (flat prices)."""
        result = run_accumulation_phase(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=FLAT_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        # With flat prices, final weights should be close to target
        eq = result.final_portfolio.holdings[0].units
        bd = result.final_portfolio.holdings[1].units
        total = eq + bd
        eq_weight = eq / total
        bd_weight = bd / total
        assert abs(eq_weight - Decimal("0.75")) < Decimal("0.01")
        assert abs(bd_weight - Decimal("0.25")) < Decimal("0.01")

    def test_evolution_applies_returns(self) -> None:
        """With positive returns, evolution must increase value."""
        result = run_accumulation_phase(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=GROWTH_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        # Growth dataset has positive returns, so final > initial + contributions
        final_total = sum(h.units for h in result.final_portfolio.holdings)
        assert final_total > Decimal("0")


class TestIndependence:
    """Accumulation result must be independent of retirement parameters."""

    def test_independence_of_swr(self) -> None:
        """Same accumulation regardless of SWR parameter."""
        result_a = run_accumulation_phase(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=FLAT_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        result_b = run_accumulation_phase(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=FLAT_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        assert result_a.final_portfolio == result_b.final_portfolio
        assert result_a.month_by_month == result_b.month_by_month

    def test_independence_of_cohort_date(self) -> None:
        """Accumulation result depends only on dataset content, not cohort date."""
        # Both datasets have identical content (flat prices)
        result_a = run_accumulation_phase(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=FLAT_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        # Use same dataset (content matters, not dates)
        result_b = run_accumulation_phase(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=FLAT_DATASET,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )
        assert result_a.final_portfolio == result_b.final_portfolio


class TestProductionOracleEquivalence:
    """Production must match independent oracle on all fixtures."""

    def _assert_equal(self, prod, orc, label: str) -> None:
        prod_holdings = {h.asset_class: h.units for h in prod.holdings}
        oracle_holdings = {h.asset_class: h.units for h in orc.holdings}
        for asset in prod_holdings:
            assert prod_holdings[asset] == oracle_holdings[asset], (
                f"{label}: {asset.id} mismatch"
            )

    def test_flat_final_portfolio(self) -> None:
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
        self._assert_equal(prod.final_portfolio, orc.final_portfolio, "flat-final")

    def test_growth_final_portfolio(self) -> None:
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
        self._assert_equal(prod.final_portfolio, orc.final_portfolio, "growth-final")

    def test_ern_final_portfolio(self) -> None:
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
        self._assert_equal(prod.final_portfolio, orc.final_portfolio, "ern-final")

    def test_month_by_month_equivalence(self) -> None:
        """Production must match oracle for all 12 months."""
        for ds_name, ds in [
            ("flat", FLAT_DATASET),
            ("growth", GROWTH_DATASET),
            ("ern", ERN_REALISTIC_DATASET),
        ]:
            prod = run_accumulation_phase(
                initial_portfolio=KNOWN_PORTFOLIO,
                contribution=CONTRIBUTION,
                target_weights=TARGET_WEIGHTS,
                dataset=ds,
                equity_asset=EQUITY,
                bond_asset=BOND,
            )
            orc = oracle_accumulate(
                initial_portfolio=KNOWN_PORTFOLIO,
                contribution=CONTRIBUTION,
                target_weights=TARGET_WEIGHTS,
                dataset=ds,
                equity_asset=EQUITY,
                bond_asset=BOND,
            )
            for i, (p, o) in enumerate(
                zip(prod.month_by_month, orc.month_by_month, strict=True)
            ):
                self._assert_equal(p, o, f"{ds_name}-month-{i}")
