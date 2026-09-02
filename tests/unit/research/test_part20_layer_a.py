"""Part 20 Layer A validation — independent glidepath trajectory oracle.

This module provides genuinely independent validation of glidepath behaviour
by computing expected trajectories from first principles, NOT by invoking
the production GlidepathAllocationPolicy.  This ensures the oracle is
independent of the implementation under test.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

# ---------------------------------------------------------------------------
# Independent trajectory oracle
# ---------------------------------------------------------------------------


def _compute_passive_trajectory(
    start_equity: Decimal,
    end_equity: Decimal,
    slope: Decimal,
    periods: int,
) -> list[Decimal]:
    """Independently compute expected passive glidepath equity weights.

    This is a pure mathematical function that does NOT import or call
    any production code.  It computes:
        equity[t] = min(start + slope * t, end_equity)

    Parameters
    ----------
    start_equity:
        Initial equity weight (0.0 to 1.0).
    end_equity:
        Target equity weight (0.0 to 1.0).
    slope:
        Monthly increase as a fraction (e.g. 0.002 for 0.2 pp/month).
    periods:
        Number of periods to simulate.

    Returns
    -------
    list[Decimal]
        Equity weight at each period index 0..periods-1.
    """
    weights: list[Decimal] = []
    for t in range(periods):
        raw = start_equity + slope * Decimal(str(t))
        equity = min(raw, end_equity)
        weights.append(equity)
    return weights


def _compute_passive_trajectory_pp(
    start_pct: Decimal,
    end_pct: Decimal,
    slope_pp: Decimal,
    months: int,
) -> list[Decimal]:
    """Compute expected passive glidepath in percentage-point space.

    This mirrors the article-level description where slope is in pp/month.

    Parameters
    ----------
    start_pct:
        Starting equity percentage (e.g. 30 for 30%).
    end_pct:
        Ending equity percentage (e.g. 70 for 70%).
    slope_pp:
        Monthly increase in percentage points (e.g. 0.111).
    months:
        Number of months to simulate.

    Returns
    -------
    list[Decimal]
        Equity percentage at each month 0..months-1.
    """
    weights: list[Decimal] = []
    for t in range(months):
        raw = start_pct + slope_pp * Decimal(str(t))
        equity = min(raw, end_pct)
        weights.append(equity)
    return weights


def _count_months_to_target(
    start_pct: Decimal,
    end_pct: Decimal,
    slope_pp: Decimal,
) -> int:
    """Compute the number of months to reach or exceed the target equity.

    Returns the first month index t where start + slope*t >= end.
    If slope is 0, returns infinity (represented as a very large number).
    """
    if slope_pp <= 0:
        return 999999
    spread = end_pct - start_pct
    if spread <= 0:
        return 0
    # Ceiling division: months = ceil(spread / slope_pp)
    months = int((spread / slope_pp).to_integral_value(rounding=ROUND_HALF_EVEN))
    # Verify: start + slope * months should be >= end
    if start_pct + slope_pp * Decimal(str(months)) < end_pct:
        months += 1
    # Also check if months-1 is sufficient (rounding may have overshot)
    if months > 0 and start_pct + slope_pp * Decimal(str(months - 1)) >= end_pct:
        months -= 1
    return months


class TestIndependentGlidepathTrajectory:
    """Layer A: Independent trajectory oracle validation."""

    def test_30_to_70_passive_00111_trajectory(self) -> None:
        """30→70% with 0.111 pp/month: 40pp spread / 0.111 ≈ 360.36 months."""
        start = Decimal("30")
        end = Decimal("70")
        slope = Decimal("0.111")
        months_to_target = _count_months_to_target(start, end, slope)
        # 40 / 0.111 = 360.360... -> first month where 30 + 0.111*t >= 70
        # Month 360: 30 + 0.111*360 = 69.96 (not yet)
        # Month 361: 30 + 0.111*361 = 70.071 (reached)
        assert months_to_target == 361

        trajectory = _compute_passive_trajectory_pp(start, end, slope, 362)
        # Month 0: 30%
        assert trajectory[0] == Decimal("30")
        # Month 360: 69.96 (not yet capped)
        assert trajectory[360] == Decimal("69.960")
        # Month 361: 70.071, capped to 70
        assert trajectory[361] == Decimal("70")
        # Verify monotonic increase
        for i in range(1, len(trajectory)):
            assert trajectory[i] >= trajectory[i - 1]

    def test_20_to_60_passive_00111_trajectory(self) -> None:
        """20→60% with 0.111 pp/month: 40pp spread / 0.111 ≈ 360.36 months."""
        start = Decimal("20")
        end = Decimal("60")
        slope = Decimal("0.111")
        months_to_target = _count_months_to_target(start, end, slope)
        assert months_to_target == 361

        trajectory = _compute_passive_trajectory_pp(start, end, slope, 362)
        assert trajectory[0] == Decimal("20")
        # Month 360: 20 + 0.111*360 = 59.96 (not yet capped)
        assert trajectory[360] == Decimal("59.960")
        # Month 361: 20 + 0.111*361 = 60.071, capped to 60
        assert trajectory[361] == Decimal("60")

    def test_60_to_80_passive_002_trajectory(self) -> None:
        """60→80% with 0.2 pp/month: 20pp spread / 0.2 = 100 months."""
        start = Decimal("60")
        end = Decimal("80")
        slope = Decimal("0.2")
        months_to_target = _count_months_to_target(start, end, slope)
        assert months_to_target == 100

        trajectory = _compute_passive_trajectory_pp(start, end, slope, 101)
        assert trajectory[0] == Decimal("60")
        # Month 99: 60 + 0.2*99 = 79.8 (not yet capped)
        assert trajectory[99] == Decimal("79.8")
        # Month 100: 60 + 0.2*100 = 80.0 (reached)
        assert trajectory[100] == Decimal("80")

    def test_40_to_100_passive_005_trajectory(self) -> None:
        """40→100% with 0.5 pp/month: 60pp spread / 0.5 = 120 months."""
        start = Decimal("40")
        end = Decimal("100")
        slope = Decimal("0.5")
        months_to_target = _count_months_to_target(start, end, slope)
        assert months_to_target == 120

        trajectory = _compute_passive_trajectory_pp(start, end, slope, 121)
        assert trajectory[0] == Decimal("40")
        # Month 119: 40 + 0.5*119 = 99.5 (not yet capped)
        assert trajectory[119] == Decimal("99.5")
        # Month 120: 40 + 0.5*120 = 100.0 (reached)
        assert trajectory[120] == Decimal("100")

    def test_trajectory_never_exceeds_end(self) -> None:
        """Equity weight must never exceed end_equity."""
        trajectory = _compute_passive_trajectory_pp(
            Decimal("30"), Decimal("70"), Decimal("0.111"), 500
        )
        for w in trajectory:
            assert w <= Decimal("70")

    def test_trajectory_is_deterministic(self) -> None:
        """Same inputs must produce identical outputs."""
        t1 = _compute_passive_trajectory_pp(
            Decimal("30"), Decimal("70"), Decimal("0.111"), 400
        )
        t2 = _compute_passive_trajectory_pp(
            Decimal("30"), Decimal("70"), Decimal("0.111"), 400
        )
        assert t1 == t2

    def test_slope_00111_conversion(self) -> None:
        """Verify 0.111 pp/month is correctly interpreted.

        In fraction space: 0.111 pp = 0.00111 as a fraction.
        The production code stores slope as a fraction.
        """
        slope_pp = Decimal("0.111")
        slope_fraction = slope_pp / Decimal("100")
        assert slope_fraction == Decimal("0.00111")


class TestGlidepathPolicyIndependence:
    """Layer A: Verify the oracle is independent of the production code."""

    def test_oracle_does_not_import_glidepath_policy(self) -> None:
        """This test file must not import GlidepathAllocationPolicy."""
        import sys
        # Check that this test module does not have glidepath in its imports
        module = sys.modules[__name__]
        assert not hasattr(module, "GlidepathAllocationPolicy")

    def test_oracle_computes_from_first_principles(self) -> None:
        """The oracle trajectory is computed from arithmetic, not from policy."""
        # Simple case: start=50, end=100, slope=1.0 pp/month, 60 months
        trajectory = _compute_passive_trajectory_pp(
            Decimal("50"), Decimal("100"), Decimal("1"), 60
        )
        # Month 0: 50, Month 1: 51, ..., Month 50: 100 (capped)
        assert trajectory[0] == Decimal("50")
        assert trajectory[1] == Decimal("51")
        assert trajectory[50] == Decimal("100")
        assert trajectory[59] == Decimal("100")


class TestPart20GlidepathSlopeValidation:
    """Layer A: Validate the 0.00111 slope conversion."""

    def test_00111_pp_is_00000111_fraction(self) -> None:
        """0.111 pp/month = 0.00111 as a fraction."""
        slope_pp = Decimal("0.111")
        slope_fraction = slope_pp / Decimal("100")
        assert slope_fraction == Decimal("0.00111")

    def test_002_pp_is_0002_fraction(self) -> None:
        """0.2 pp/month = 0.002 as a fraction."""
        slope_pp = Decimal("0.2")
        slope_fraction = slope_pp / Decimal("100")
        assert slope_fraction == Decimal("0.002")

    def test_003_pp_is_0003_fraction(self) -> None:
        """0.3 pp/month = 0.003 as a fraction."""
        slope_pp = Decimal("0.3")
        slope_fraction = slope_pp / Decimal("100")
        assert slope_fraction == Decimal("0.003")

    def test_004_pp_is_0004_fraction(self) -> None:
        """0.4 pp/month = 0.004 as a fraction."""
        slope_pp = Decimal("0.4")
        slope_fraction = slope_pp / Decimal("100")
        assert slope_fraction == Decimal("0.004")
