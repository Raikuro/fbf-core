"""ERN forward-projection constants and boundary behaviour.

Source: SWR Toolbox v2.0 workbook, Parameters & Main Results B787:B790.

Verifies:
- First phase (months 1–120): 4.0% equity, 2.5% bonds
- Second phase (month 121+): 5.5% equity, 2.25% bonds
- Annual-to-monthly conversion matches workbook cached values
- June 2026 uses historical data; July 2026 uses forward projection
- Phase boundary: Jul 2026 – Jun 2036, then Jul 2036 onward
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from fbf.core.datasets.ern import (
    _BOND_FORWARD_ANNUAL,
    _BOND_FORWARD_ANNUAL_AFTER,
    _EQUITY_FORWARD_ANNUAL,
    _EQUITY_FORWARD_ANNUAL_AFTER,
    _FORWARD_PHASE_MONTHS,
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
    """Verify constants match the SWR Toolbox v2.0 workbook."""

    def test_equity_forward_first_phase(self) -> None:
        """First-phase equity = 4.0% real p.a."""
        assert Decimal("0.04") == _EQUITY_FORWARD_ANNUAL

    def test_equity_forward_second_phase(self) -> None:
        """Second-phase equity = 5.5% real p.a."""
        assert Decimal("0.055") == _EQUITY_FORWARD_ANNUAL_AFTER

    def test_bond_forward_first_phase(self) -> None:
        """First-phase bonds = 2.5% real p.a."""
        assert Decimal("0.025") == _BOND_FORWARD_ANNUAL

    def test_bond_forward_second_phase(self) -> None:
        """Second-phase bonds = 2.25% real p.a."""
        assert Decimal("0.0225") == _BOND_FORWARD_ANNUAL_AFTER

    def test_forward_phase_is_120_months(self) -> None:
        """Both asset classes switch phase after 120 months (10 years)."""
        assert _FORWARD_PHASE_MONTHS == 120

    @pytest.mark.parametrize(
        ("annual_rate", "expected_monthly"),
        [
            ("0.04", Decimal("0.003273739782")),
            ("0.055", Decimal("0.004471698917")),
            ("0.025", Decimal("0.002059836270")),
            ("0.0225", Decimal("0.001855937535")),
        ],
    )
    def test_monthly_conversion_matches_workbook(
        self, annual_rate: str, expected_monthly: Decimal
    ) -> None:
        """Monthly conversion matches Asset Returns cached values."""
        monthly = (
            (Decimal("1") + Decimal(annual_rate)) ** (Decimal("1") / Decimal("12"))
            - Decimal("1")
        )
        assert monthly.quantize(Decimal("0.000000000001")) == expected_monthly

    def test_projection_starts_july_2026(self) -> None:
        """Historical data ends June 2026; forward projection begins July 2026.

        The workbook's Asset Returns sheet contains actual historical observations
        through June 2026. Projection begins at the first month after historical
        data ends. _HISTORICAL_END is the first forward month = July 2026.
        """
        assert _HISTORICAL_END.year == 2026
        assert _HISTORICAL_END.month == 7

    def test_projection_end_is_december_2075(self) -> None:
        """Canonical full coverage extends through December 2075."""
        assert _PROJECTION_END.year == 2075
        assert _PROJECTION_END.month == 12


# ---------------------------------------------------------------------------
# First-forward-month semantics
# ---------------------------------------------------------------------------


class TestFirstForwardMonth:
    """July 2026 must use the forward projection, not June 2026's historical return."""

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

    def test_july_2026_uses_forward_rate(self, dataset: Dataset) -> None:
        """Jul 2026 equity must use forward rate, not Jun 2026's historical return."""
        jun = self._snapshot_by_date(dataset, 2026, 6)
        jul = self._snapshot_by_date(dataset, 2026, 7)
        jun_eq = self._eq_level(jun)
        jul_eq = self._eq_level(jul)
        # First-phase monthly equity: (1.04)^(1/12) - 1
        expected_jul_eq = jun_eq * (1 + (1.04) ** (1 / 12) - 1)
        assert jul_eq == pytest.approx(expected_jul_eq, rel=1e-9), (
            f"Jul 2026 equity {jul_eq} should be Jun equity "
            f"{jun_eq} × forward monthly rate, not Jun historical return"
        )

    def test_july_2026_equity_growth_is_forward_rate(self, dataset: Dataset) -> None:
        """Jul 2026 / Jun 2026 equity ratio matches the forward monthly rate."""
        jun = self._snapshot_by_date(dataset, 2026, 6)
        jul = self._snapshot_by_date(dataset, 2026, 7)
        ratio = self._eq_level(jul) / self._eq_level(jun)
        expected_ratio = (1.04) ** (1 / 12)
        assert ratio == pytest.approx(expected_ratio, rel=1e-9)

    def test_august_2026_also_uses_forward_rate(self, dataset: Dataset) -> None:
        """Aug 2026 equity = Jul 2026 equity × forward monthly rate."""
        jul = self._snapshot_by_date(dataset, 2026, 7)
        aug = self._snapshot_by_date(dataset, 2026, 8)
        ratio = self._eq_level(aug) / self._eq_level(jul)
        expected_ratio = (1.04) ** (1 / 12)
        assert ratio == pytest.approx(expected_ratio, rel=1e-9)


# ---------------------------------------------------------------------------
# 120-month projection phase boundary
# ---------------------------------------------------------------------------


class TestBondPhaseBoundary:
    """Bonds grow at 2.5% for months 1–120 and 2.25% from month 121."""

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

    def test_bond_first_phase_jun_2036(self, dataset: Dataset) -> None:
        """Jun 2036 is the last first-phase month: 2.5% annual monthly growth."""
        may = self._snapshot_by_date(dataset, 2036, 5)
        jun = self._snapshot_by_date(dataset, 2036, 6)
        ratio = self._bond_level(jun) / self._bond_level(may)
        expected_ratio = (1.025) ** (1 / 12)
        assert ratio == pytest.approx(expected_ratio, rel=1e-9)

    def test_bond_switches_at_jul_2036(self, dataset: Dataset) -> None:
        """Jul 2036 bond growth from Jun 2036 must be 2.25% p.a. monthly."""
        jun = self._snapshot_by_date(dataset, 2036, 6)
        jul = self._snapshot_by_date(dataset, 2036, 7)
        ratio = self._bond_level(jul) / self._bond_level(jun)
        expected_ratio = (1.0225) ** (1 / 12)
        assert ratio == pytest.approx(expected_ratio, rel=1e-9), (
            f"Jul 2036 bond ratio {ratio} should match "
            f"(1.0225)^(1/12) = {expected_ratio}"
        )

    def test_bond_stays_in_second_phase_after_jul_2036(self, dataset: Dataset) -> None:
        """Aug 2036 bond growth continues at 2.25% p.a. monthly."""
        jul = self._snapshot_by_date(dataset, 2036, 7)
        aug = self._snapshot_by_date(dataset, 2036, 8)
        ratio = self._bond_level(aug) / self._bond_level(jul)
        expected_ratio = (1.0225) ** (1 / 12)
        assert ratio == pytest.approx(expected_ratio, rel=1e-9)


class TestEquityPhaseBoundary:
    """Equity grows at 4.0% for months 1–120 and 5.5% from month 121."""

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

    def test_equity_first_phase_jun_2036(self, dataset: Dataset) -> None:
        """Jun 2036 is the last first-phase month: 4.0% annual monthly growth."""
        may = self._snapshot_by_date(dataset, 2036, 5)
        jun = self._snapshot_by_date(dataset, 2036, 6)
        ratio = self._eq_level(jun) / self._eq_level(may)
        expected_ratio = (1.04) ** (1 / 12)
        assert ratio == pytest.approx(expected_ratio, rel=1e-9)

    def test_equity_switches_at_jul_2036(self, dataset: Dataset) -> None:
        """Jul 2036 equity growth from Jun 2036 must be 5.5% p.a. monthly."""
        jun = self._snapshot_by_date(dataset, 2036, 6)
        jul = self._snapshot_by_date(dataset, 2036, 7)
        ratio = self._eq_level(jul) / self._eq_level(jun)
        expected_ratio = (1.055) ** (1 / 12)
        assert ratio == pytest.approx(expected_ratio, rel=1e-9), (
            f"Jul 2036 equity ratio {ratio} should match "
            f"(1.055)^(1/12) = {expected_ratio}"
        )

    def test_equity_stays_in_second_phase_after_jul_2036(self, dataset: Dataset) -> None:
        """Aug 2036 equity growth continues at 5.5% p.a. monthly."""
        jul = self._snapshot_by_date(dataset, 2036, 7)
        aug = self._snapshot_by_date(dataset, 2036, 8)
        ratio = self._eq_level(aug) / self._eq_level(jul)
        expected_ratio = (1.055) ** (1 / 12)
        assert ratio == pytest.approx(expected_ratio, rel=1e-9)


# ---------------------------------------------------------------------------
# Equity forward rate consistency
# ---------------------------------------------------------------------------


class TestEquityForwardConsistency:
    """Equity must grow at the phase rate through the entire projection."""

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
        """First two forward months: equity ratio matches (1.04)^(1/12)."""
        jul = self._snapshot_by_date(dataset, 2026, 7)
        aug = self._snapshot_by_date(dataset, 2026, 8)
        ratio = self._eq_level(aug) / self._eq_level(jul)
        assert ratio == pytest.approx((1.04) ** (1 / 12), rel=1e-9)

    def test_equity_rate_mid_projection(self, dataset: Dataset) -> None:
        """Mid-projection months: equity ratio matches (1.055)^(1/12)."""
        jan = self._snapshot_by_date(dataset, 2050, 1)
        feb = self._snapshot_by_date(dataset, 2050, 2)
        ratio = self._eq_level(feb) / self._eq_level(jan)
        assert ratio == pytest.approx((1.055) ** (1 / 12), rel=1e-9)

    def test_equity_rate_end_of_projection(self, dataset: Dataset) -> None:
        """End-of-projection months: equity ratio matches (1.055)^(1/12)."""
        oct = self._snapshot_by_date(dataset, 2075, 10)
        nov = self._snapshot_by_date(dataset, 2075, 11)
        ratio = self._eq_level(nov) / self._eq_level(oct)
        assert ratio == pytest.approx((1.055) ** (1 / 12), rel=1e-9)


# ---------------------------------------------------------------------------
# Dataset structural invariants
# ---------------------------------------------------------------------------


class TestDatasetStructure:
    """Dataset structural properties must remain stable after the fix."""

    @pytest.fixture(scope="class")
    def dataset(self) -> Dataset:
        return load_ern_dataset(_DATA_DIR)

    def test_snapshot_count_covers_60y(self, dataset: Dataset) -> None:
        """2460 snapshots provide full 60-year coverage for 2015-12 cohorts."""
        assert len(dataset.snapshots) == 2460

    def test_start_date_unchanged(self, dataset: Dataset) -> None:
        """First snapshot is 1871-01-31."""
        assert str(dataset.snapshots[0].date) == "1871-01-31"

    def test_end_date_covers_60y(self, dataset: Dataset) -> None:
        """Last snapshot is 2075-12-01."""
        assert str(dataset.snapshots[-1].date) == "2075-12-01"


# ---------------------------------------------------------------------------
# Real ATH/Underwater regression (ERN active-glidepath methodology)
# ---------------------------------------------------------------------------


class TestRealAthRegression:
    """ATH/underwater must use the CPI-adjusted real total-return index."""

    @pytest.fixture(scope="class")
    def dataset(self) -> Dataset:
        return load_ern_dataset(_DATA_DIR)

    def _eq_level(self, snapshot: MarketSnapshot) -> Decimal:
        return next(
            level
            for asset, level in snapshot.index_levels.items()
            if asset.id == "equity"
        )

    def test_running_ath_tracks_real_equity(self, dataset: Dataset) -> None:
        """Running ATH is the maximum real equity level observed so far."""
        expected_ath = self._eq_level(dataset.snapshots[1])
        for snapshot in dataset.snapshots[1:]:
            expected_ath = max(expected_ath, self._eq_level(snapshot))
            assert snapshot.running_ath == expected_ath

    def test_underwater_state_at_known_real_drawdowns(self, dataset: Dataset) -> None:
        """Known real drawdowns are underwater, including 2007-10."""
        snapshots = {
            (s.date.year, s.date.month): s for s in dataset.snapshots
        }

        assert snapshots[(2000, 8)].is_underwater is False
        assert snapshots[(2002, 9)].is_underwater is True
        assert snapshots[(2007, 10)].is_underwater is True
        assert snapshots[(2009, 2)].is_underwater is True

    def test_is_underwater_not_always_false(self, dataset: Dataset) -> None:
        """is_underwater must reflect historical drawdowns."""
        underwater_count = sum(1 for s in dataset.snapshots if s.is_underwater)

        assert underwater_count > 1000, (
            f"Expected many underwater months, got {underwater_count}."
        )

    def test_running_ath_monotonic(self, dataset: Dataset) -> None:
        """Running ATH must be monotonically non-decreasing after the first data point."""
        prev_ath = dataset.snapshots[1].running_ath
        for snap in dataset.snapshots[1:]:
            assert snap.running_ath >= prev_ath, (
                f"Running ATH decreased at {snap.date}: {prev_ath} -> {snap.running_ath}"
            )
            prev_ath = snap.running_ath


class TestProjectedAthUnits:
    """Projected real equity must be compared with the real ATH."""

    @pytest.fixture(scope="class")
    def dataset(self) -> Dataset:
        return load_ern_dataset(_DATA_DIR)

    def _projected(self, dataset: Dataset) -> list[MarketSnapshot]:
        return [
            s
            for s in dataset.snapshots
            if (s.date.year, s.date.month) >= (2026, 7)
        ]

    def _eq_level(self, snapshot: MarketSnapshot) -> Decimal:
        return next(
            level
            for asset, level in snapshot.index_levels.items()
            if asset.id == "equity"
        )

    def test_boundary_preserves_real_units(self, dataset: Dataset) -> None:
        """Historical/projection boundary flags use real levels and real ATH."""
        snapshots = {
            (s.date.year, s.date.month): s for s in dataset.snapshots
        }

        for key in ((2026, 6), (2026, 7), (2026, 8)):
            snapshot = snapshots[key]
            eq = self._eq_level(snapshot)
            assert snapshot.is_underwater is (eq < snapshot.running_ath)
            assert snapshot.is_ath is (eq >= snapshot.running_ath)

    def test_projection_is_not_permanently_underwater(self, dataset: Dataset) -> None:
        """The all-underwater projection bug must not return."""
        projected = self._projected(dataset)
        underwater = [s for s in projected if s.is_underwater]

        assert underwater
        assert len(underwater) < len(projected)

    def test_projected_underwater_is_a_prefix(self, dataset: Dataset) -> None:
        """Once projection reaches a new real high it cannot be underwater again."""
        projected = self._projected(dataset)
        flags = [s.is_underwater for s in projected]

        first_false = flags.index(False)
        assert not any(flags[first_false:])

    def test_projected_is_ath_resumes_after_historical_drawdown(
        self, dataset: Dataset
    ) -> None:
        """Projection must eventually establish a new real ATH."""
        projected = self._projected(dataset)

        assert any(s.is_ath for s in projected)

    def test_historical_underwater_state_is_unchanged_at_boundary(
        self, dataset: Dataset
    ) -> None:
        """The historical boundary flags remain real-drawdown based."""
        snapshots = {
            (s.date.year, s.date.month): s for s in dataset.snapshots
        }

        assert snapshots[(2026, 5)].is_underwater is False
        assert snapshots[(2026, 6)].is_underwater is True


# ---------------------------------------------------------------------------
# CSV loading utilities
# ---------------------------------------------------------------------------


class TestCSVLoading:
    """Verify _load_csv accepts both YYYY-MM-DD and DD-MM-YYYY."""

    def test_load_csv_yyyy_mm_dd(self, tmp_path: Path) -> None:
        """Canonical YYYY-MM-DD format loads correctly."""
        from fbf.core.datasets.ern import _load_csv

        csv_path = tmp_path / "test.csv"
        csv_path.write_text("date,value\n2020-06-01,0.5\n", encoding="utf-8")
        rows = _load_csv(csv_path)
        assert len(rows) == 1
        assert rows[0] == ("2020-06-01", Decimal("0.5"))

    def test_load_csv_dd_mm_yyyy(self, tmp_path: Path) -> None:
        """Legacy DD-MM-YYYY format loads correctly."""
        from fbf.core.datasets.ern import _load_csv

        csv_path = tmp_path / "test.csv"
        csv_path.write_text("DD-MM-YYYY,value\n01-06-2020,0.5\n", encoding="utf-8")
        rows = _load_csv(csv_path)
        assert len(rows) == 1
        assert rows[0] == ("2020-06-01", Decimal("0.5"))

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
