"""ERN forward-projection constants and boundary behaviour.

Source: ERN Part 1 §4 (Dec 7 2016) — first-party ERN evidence.

Verifies:
- Canonical constants (6.6% equity, 0% bond for 120 months, 2.6% bond after)
- October 2016 uses forward projection (NOT September 2016's historical return)
- Bond zero-rate period: Oct 2016 – Sep 2026 (months 1–120)
- Bond long-term rate: Oct 2026 onward (month 121+)
- Equity forward rate applied consistently across the full projection
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from fbf.core.datasets.ern import (
    _BOND_FORWARD_ANNUAL,
    _BOND_FORWARD_ANNUAL_AFTER,
    _BOND_FORWARD_DELAY_MONTHS,
    _EQUITY_FORWARD_ANNUAL,
    _HISTORICAL_END,
    _PROJECTION_END,
    load_ern_dataset,
)

if TYPE_CHECKING:
    from fbf.core.domain.model.dataset import Dataset
    from fbf.core.domain.model.market_snapshot import MarketSnapshot

_DATA_DIR = Path("data/ern")


# ---------------------------------------------------------------------------
# Constant canonicality
# ---------------------------------------------------------------------------


class TestForwardConstants:
    """Verify constants match ERN Part 1 §4 canonical specification."""

    def test_equity_forward_is_6_6_percent(self) -> None:
        """Equity forward = 6.6% real p.a. (Part 1 §4)."""
        assert pytest.approx(0.066, abs=1e-9) == _EQUITY_FORWARD_ANNUAL

    def test_bond_forward_is_zero(self) -> None:
        """Bond zero-rate = 0.0% real p.a. for first 120 months."""
        assert _BOND_FORWARD_ANNUAL == 0.0

    def test_bond_forward_after_is_2_6_percent(self) -> None:
        """Bond long-term = 2.6% real p.a. after month 120."""
        assert pytest.approx(0.026, abs=1e-9) == _BOND_FORWARD_ANNUAL_AFTER

    def test_bond_delay_is_120_months(self) -> None:
        """Bond zero-rate period = 120 months (10 years)."""
        assert _BOND_FORWARD_DELAY_MONTHS == 120

    def test_historical_end_is_october_2016(self) -> None:
        """Forward projection begins October 2016."""
        assert _HISTORICAL_END.year == 2016
        assert _HISTORICAL_END.month == 10

    def test_projection_end_is_november_2075(self) -> None:
        """Projection extends through November 2075."""
        assert _PROJECTION_END.year == 2075
        assert _PROJECTION_END.month == 11


# ---------------------------------------------------------------------------
# First-forward-month semantics
# ---------------------------------------------------------------------------


class TestFirstForwardMonth:
    """October 2016 must use the forward projection, not Sep 2016's return."""

    @pytest.fixture(scope="class")
    def dataset(self) -> Dataset:
        return load_ern_dataset(_DATA_DIR)

    def _snapshot_by_date(self, dataset: Dataset, year: int, month: int) -> MarketSnapshot:
        for s in dataset.snapshots:
            if s.date.year == year and s.date.month == month:
                return s
        raise AssertionError(f"No snapshot for {year}-{month:02d}")

    def _eq_level(self, snapshot: MarketSnapshot) -> float:
        return float(snapshot.index_levels[list(snapshot.index_levels.keys())[0]])

    def test_october_2016_uses_forward_rate(self, dataset: Dataset) -> None:
        """Oct 2016 equity must differ from Sep 2016 equity × (1+sep_return).

        The old bug reused September 2016's historical return for October.
        The fix applies the forward rate (6.6% p.a.) to October directly.
        """
        sep = self._snapshot_by_date(dataset, 2016, 9)
        oct_ = self._snapshot_by_date(dataset, 2016, 10)
        sep_eq = self._eq_level(sep)
        oct_eq = self._eq_level(oct_)
        # Forward rate monthly: (1.066)^(1/12) - 1
        expected_oct_eq = sep_eq * (1 + (1.066) ** (1 / 12) - 1)
        assert oct_eq == pytest.approx(expected_oct_eq, rel=1e-9), (
            f"Oct 2016 equity {oct_eq} should be Sep equity "
            f"{sep_eq} × forward monthly rate, not Sep historical return"
        )

    def test_october_2016_equity_growth_is_forward_rate(self, dataset: Dataset) -> None:
        """Oct 2016 / Sep 2016 equity ratio matches the forward monthly rate."""
        sep = self._snapshot_by_date(dataset, 2016, 9)
        oct_ = self._snapshot_by_date(dataset, 2016, 10)
        ratio = self._eq_level(oct_) / self._eq_level(sep)
        expected_ratio = (1.066) ** (1 / 12)
        assert ratio == pytest.approx(expected_ratio, rel=1e-9)

    def test_november_2016_also_uses_forward_rate(self, dataset: Dataset) -> None:
        """Nov 2016 equity = Oct 2016 equity × forward monthly rate."""
        oct_ = self._snapshot_by_date(dataset, 2016, 10)
        nov = self._snapshot_by_date(dataset, 2016, 11)
        ratio = self._eq_level(nov) / self._eq_level(oct_)
        expected_ratio = (1.066) ** (1 / 12)
        assert ratio == pytest.approx(expected_ratio, rel=1e-9)


# ---------------------------------------------------------------------------
# 120-month bond zero-rate boundary
# ---------------------------------------------------------------------------


class TestBondZeroRateBoundary:
    """Bond must be at 0% for months 1–120 (Oct 2016 – Sep 2026)
    and switch to 2.6% at month 121 (Oct 2026)."""

    @pytest.fixture(scope="class")
    def dataset(self) -> Dataset:
        return load_ern_dataset(_DATA_DIR)

    def _snapshot_by_date(self, dataset: Dataset, year: int, month: int) -> MarketSnapshot:
        for s in dataset.snapshots:
            if s.date.year == year and s.date.month == month:
                return s
        raise AssertionError(f"No snapshot for {year}-{month:02d}")

    def _bond_level(self, snapshot: MarketSnapshot) -> float:
        keys = list(snapshot.index_levels.keys())
        return float(snapshot.index_levels[keys[1]])

    def test_bond_zero_rate_sep_2026(self, dataset: Dataset) -> None:
        """Sep 2026 bond growth from Aug 2026 must be ≈ 0% (fee drag only)."""
        aug = self._snapshot_by_date(dataset, 2026, 8)
        sep = self._snapshot_by_date(dataset, 2026, 9)
        aug_bond = self._bond_level(aug)
        sep_bond = self._bond_level(sep)
        # With 0% return and 0.05%/12 fee, monthly factor = (1 - 0.0005/12)
        expected_sep = aug_bond * (1 - 0.0005 / 12)
        assert sep_bond == pytest.approx(expected_sep, rel=1e-9)

    def test_bond_switches_at_oct_2026(self, dataset: Dataset) -> None:
        """Oct 2026 bond growth from Sep 2026 must be ≈ 2.6% p.a. monthly."""
        sep = self._snapshot_by_date(dataset, 2026, 9)
        oct_ = self._snapshot_by_date(dataset, 2026, 10)
        sep_bond = self._bond_level(sep)
        oct_bond = self._bond_level(oct_)
        ratio = oct_bond / sep_bond
        expected_ratio = (1.026) ** (1 / 12)
        assert ratio == pytest.approx(expected_ratio, rel=1e-9), (
            f"Oct 2026 bond ratio {ratio} should match "
            f"(1.026)^(1/12) = {expected_ratio}"
        )

    def test_bond_stays_at_2_6_after_oct_2026(self, dataset: Dataset) -> None:
        """Nov 2026 bond growth continues at 2.6% p.a. monthly."""
        oct_ = self._snapshot_by_date(dataset, 2026, 10)
        nov = self._snapshot_by_date(dataset, 2026, 11)
        ratio = self._bond_level(nov) / self._bond_level(oct_)
        expected_ratio = (1.026) ** (1 / 12)
        assert ratio == pytest.approx(expected_ratio, rel=1e-9)

    def test_bond_zero_rate_applies_for_120_months(self, dataset: Dataset) -> None:
        """Bond at zero rate for exactly 120 months (Oct 2016 – Sep 2026).

        Month 1 = Oct 2016, Month 120 = Sep 2026.
        Month 121 = Oct 2026 switches to 2.6%.
        """
        oct_2016 = self._snapshot_by_date(dataset, 2016, 10)
        sep_2026 = self._snapshot_by_date(dataset, 2026, 9)
        oct_2026 = self._snapshot_by_date(dataset, 2026, 10)

        # Bond at Sep 2026 should be less than at Oct 2016 (fee drag only)
        assert self._bond_level(sep_2026) < self._bond_level(oct_2016)

        # Bond at Oct 2026 should be GREATER than at Sep 2026 (2.6% kicks in)
        assert self._bond_level(oct_2026) > self._bond_level(sep_2026)


# ---------------------------------------------------------------------------
# Equity forward rate consistency
# ---------------------------------------------------------------------------


class TestEquityForwardConsistency:
    """Equity must grow at 6.6% p.a. consistently through the entire projection."""

    @pytest.fixture(scope="class")
    def dataset(self) -> Dataset:
        return load_ern_dataset(_DATA_DIR)

    def _snapshot_by_date(self, dataset: Dataset, year: int, month: int) -> MarketSnapshot:
        for s in dataset.snapshots:
            if s.date.year == year and s.date.month == month:
                return s
        raise AssertionError(f"No snapshot for {year}-{month:02d}")

    def _eq_level(self, snapshot: MarketSnapshot) -> float:
        return float(snapshot.index_levels[list(snapshot.index_levels.keys())[0]])

    def test_equity_rate_at_start_of_projection(self, dataset: Dataset) -> None:
        """First two forward months: equity ratio matches (1.066)^(1/12)."""
        oct_ = self._snapshot_by_date(dataset, 2016, 10)
        nov = self._snapshot_by_date(dataset, 2016, 11)
        ratio = self._eq_level(nov) / self._eq_level(oct_)
        assert ratio == pytest.approx((1.066) ** (1 / 12), rel=1e-9)

    def test_equity_rate_mid_projection(self, dataset: Dataset) -> None:
        """Mid-projection months: equity ratio still matches (1.066)^(1/12)."""
        jan = self._snapshot_by_date(dataset, 2050, 1)
        feb = self._snapshot_by_date(dataset, 2050, 2)
        ratio = self._eq_level(feb) / self._eq_level(jan)
        assert ratio == pytest.approx((1.066) ** (1 / 12), rel=1e-9)

    def test_equity_rate_end_of_projection(self, dataset: Dataset) -> None:
        """End-of-projection months: equity ratio still matches (1.066)^(1/12)."""
        oct = self._snapshot_by_date(dataset, 2075, 10)
        nov = self._snapshot_by_date(dataset, 2075, 11)
        ratio = self._eq_level(nov) / self._eq_level(oct)
        assert ratio == pytest.approx((1.066) ** (1 / 12), rel=1e-9)


# ---------------------------------------------------------------------------
# Dataset structural invariants
# ---------------------------------------------------------------------------


class TestDatasetStructure:
    """Dataset structural properties must remain stable after the fix."""

    @pytest.fixture(scope="class")
    def dataset(self) -> Dataset:
        return load_ern_dataset(_DATA_DIR)

    def test_snapshot_count_unchanged(self, dataset: Dataset) -> None:
        """2459 snapshots (unchanged by forward-projection fix)."""
        assert len(dataset.snapshots) == 2459

    def test_start_date_unchanged(self, dataset: Dataset) -> None:
        """First snapshot is 1871-01-31."""
        assert str(dataset.snapshots[0].date) == "1871-01-31"

    def test_end_date_unchanged(self, dataset: Dataset) -> None:
        """Last snapshot is 2075-11-01."""
        assert str(dataset.snapshots[-1].date) == "2075-11-01"


# ---------------------------------------------------------------------------
# Dual-format date loading
# ---------------------------------------------------------------------------


class TestCsvDualFormat:
    """Verify _load_csv accepts both YYYY-MM-DD and DD-MM-YYYY."""

    def test_load_csv_yyyy_mm_dd(self, tmp_path: Path) -> None:
        """Canonical YYYY-MM-DD format loads correctly."""
        from fbf.core.datasets.ern import _load_csv

        csv_path = tmp_path / "test.csv"
        csv_path.write_text("date,value\n2020-06-01,0.5\n", encoding="utf-8")
        rows = _load_csv(csv_path)
        assert len(rows) == 1
        assert rows[0] == ("2020-06-01", 0.5)

    def test_load_csv_dd_mm_yyyy(self, tmp_path: Path) -> None:
        """Legacy DD-MM-YYYY format loads correctly."""
        from fbf.core.datasets.ern import _load_csv

        csv_path = tmp_path / "test.csv"
        csv_path.write_text("DD-MM-YYYY,value\n01-06-2020,0.5\n", encoding="utf-8")
        rows = _load_csv(csv_path)
        assert len(rows) == 1
        assert rows[0] == ("2020-06-01", 0.5)

    def test_load_csv_both_formats_identical(self, tmp_path: Path) -> None:
        """Both formats produce the same normalised result."""
        from fbf.core.datasets.ern import _load_csv

        canon = tmp_path / "canon.csv"
        canon.write_text("date,value\n2020-06-01,0.5\n", encoding="utf-8")
        legacy = tmp_path / "legacy.csv"
        legacy.write_text("DD-MM-YYYY,value\n01-06-2020,0.5\n", encoding="utf-8")

        rows_canon = _load_csv(canon)
        rows_legacy = _load_csv(legacy)
        assert rows_canon == rows_legacy
