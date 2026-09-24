"""Unit tests for annual glidepath cadence support.

Verifies that GlidepathAllocationPolicy with ANNUAL cadence advances
the equity target once per 12 periods using period_index // 12,
while preserving existing MONTHLY cadence behavior.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from fbf.core.domain.model.allocation import Allocation, AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.decision_context import DecisionContext
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies.glidepath import GlidepathAllocationPolicy, GlidepathCadence

_EQUITY = AssetClass(id="equity", name="", description="")
_BOND = AssetClass(id="bond", name="", description="")


def _snap(is_underwater: bool, d: date) -> MarketSnapshot:
    return MarketSnapshot(
        date=d,
        index_levels={_EQUITY: Decimal("100"), _BOND: Decimal("100")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=not is_underwater,
        is_underwater=is_underwater,
        running_ath=Decimal("100"),
    )


def _dataset(underwater_flags: list[bool], start: date = date(2020, 1, 1)) -> Dataset:
    snaps = [_snap(uw, start + timedelta(days=30 * i)) for i, uw in enumerate(underwater_flags)]
    return Dataset(snapshots=snaps, frequency="monthly")


def _context(dataset: Dataset, period_index: int) -> DecisionContext:
    portfolio = Portfolio(holdings=(AssetHolding(asset_class=_EQUITY, units=Decimal("1000")),))
    dummy_alloc = Allocation(weights={_EQUITY: Decimal("1")})
    dummy_target = AllocationTarget(weights={_EQUITY: Decimal("1")})
    return DecisionContext(
        date=dataset.snapshots[period_index].date,
        period_index=period_index,
        simulation_context=object(),
        portfolio=portfolio,
        current_allocation=dummy_alloc,
        target_allocation=dummy_target,
        market_snapshot=dataset.snapshots[period_index],
        dataset=dataset,
    )


def _equity_weight(
    policy: GlidepathAllocationPolicy, dataset: Dataset, period_index: int
) -> Decimal:
    ctx = _context(dataset, period_index)
    decision = policy.decide(ctx)
    return decision.allocation_target.weights[_EQUITY]


class TestAnnualCadence:
    """Tests for GlidepathCadence.ANNUAL behavior."""

    def test_period_zero_returns_start_equity(self) -> None:
        """Period 0: initial target (70%) — no advancement yet."""
        ds = _dataset([False] * 120)
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.70"),
            end_equity=Decimal("0.90"),
            slope=Decimal("0.02"),
            mode="passive",
            cadence=GlidepathCadence.ANNUAL,
        )
        assert _equity_weight(p, ds, 0) == Decimal("0.70")

    def test_period_11_still_at_start(self) -> None:
        """Period 11 (end of year 1): still at initial target."""
        ds = _dataset([False] * 120)
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.70"),
            end_equity=Decimal("0.90"),
            slope=Decimal("0.02"),
            mode="passive",
            cadence=GlidepathCadence.ANNUAL,
        )
        assert _equity_weight(p, ds, 11) == Decimal("0.70")

    def test_period_12_first_advancement(self) -> None:
        """Period 12 (start of year 2): first annual advancement to 72%."""
        ds = _dataset([False] * 120)
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.70"),
            end_equity=Decimal("0.90"),
            slope=Decimal("0.02"),
            mode="passive",
            cadence=GlidepathCadence.ANNUAL,
        )
        assert _equity_weight(p, ds, 12) == Decimal("0.72")

    def test_period_23_end_of_year_2(self) -> None:
        """Period 23 (end of year 2): still at 72%."""
        ds = _dataset([False] * 120)
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.70"),
            end_equity=Decimal("0.90"),
            slope=Decimal("0.02"),
            mode="passive",
            cadence=GlidepathCadence.ANNUAL,
        )
        assert _equity_weight(p, ds, 23) == Decimal("0.72")

    def test_period_24_second_advancement(self) -> None:
        """Period 24 (start of year 3): second advancement to 74%."""
        ds = _dataset([False] * 120)
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.70"),
            end_equity=Decimal("0.90"),
            slope=Decimal("0.02"),
            mode="passive",
            cadence=GlidepathCadence.ANNUAL,
        )
        assert _equity_weight(p, ds, 24) == Decimal("0.74")

    def test_period_108_ninth_advancement(self) -> None:
        """Period 108 (start of year 10): ninth advancement to 88%."""
        ds = _dataset([False] * 120)
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.70"),
            end_equity=Decimal("0.90"),
            slope=Decimal("0.02"),
            mode="passive",
            cadence=GlidepathCadence.ANNUAL,
        )
        assert _equity_weight(p, ds, 108) == Decimal("0.88")

    def test_period_119_end_of_year_10(self) -> None:
        """Period 119 (end of year 10): still at 88%."""
        ds = _dataset([False] * 120)
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.70"),
            end_equity=Decimal("0.90"),
            slope=Decimal("0.02"),
            mode="passive",
            cadence=GlidepathCadence.ANNUAL,
        )
        assert _equity_weight(p, ds, 119) == Decimal("0.88")

    def test_period_120_capped_at_end(self) -> None:
        """Period 120: capped at end_equity (90%)."""
        ds = _dataset([False] * 130)
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.70"),
            end_equity=Decimal("0.90"),
            slope=Decimal("0.02"),
            mode="passive",
            cadence=GlidepathCadence.ANNUAL,
        )
        assert _equity_weight(p, ds, 120) == Decimal("0.90")

    def test_bond_is_complement(self) -> None:
        ds = _dataset([False] * 120)
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.70"),
            end_equity=Decimal("0.90"),
            slope=Decimal("0.02"),
            mode="passive",
            cadence=GlidepathCadence.ANNUAL,
        )
        ctx = _context(ds, 12)
        decision = p.decide(ctx)
        total = sum(decision.allocation_target.weights.values())
        assert total == Decimal("1")


class TestMonthlyCadencePreserved:
    """Tests that existing MONTHLY cadence behavior is unchanged."""

    def test_monthly_default_cadence(self) -> None:
        """Default cadence is MONTHLY."""
        _ = _dataset([False] * 10)
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.60"),
            end_equity=Decimal("1.00"),
            slope=Decimal("0.005"),
            mode="passive",
        )
        assert p.cadence == GlidepathCadence.MONTHLY

    def test_monthly_advancement_every_period(self) -> None:
        """Monthly cadence advances every period (existing behavior)."""
        ds = _dataset([False] * 10)
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.60"),
            end_equity=Decimal("1.00"),
            slope=Decimal("0.005"),
            mode="passive",
            cadence=GlidepathCadence.MONTHLY,
        )
        # period 0: 0.6 + 0.005*0 = 0.6
        assert _equity_weight(p, ds, 0) == Decimal("0.60")
        # period 1: 0.6 + 0.005*1 = 0.605
        assert _equity_weight(p, ds, 1) == Decimal("0.605")
        # period 4: 0.6 + 0.005*4 = 0.62
        assert _equity_weight(p, ds, 4) == Decimal("0.62")

    def test_monthly_capped_at_end_equity(self) -> None:
        """Monthly cadence still caps at end_equity."""
        ds = _dataset([False] * 100)
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.60"),
            end_equity=Decimal("0.80"),
            slope=Decimal("0.005"),
            mode="passive",
            cadence=GlidepathCadence.MONTHLY,
        )
        assert _equity_weight(p, ds, 40) == Decimal("0.80")
        assert _equity_weight(p, ds, 50) == Decimal("0.80")


class TestAnnualCadenceWithActiveMode:
    """Tests for active mode with annual cadence (should raise)."""

    def test_active_mode_with_annual_cadence_raises(self) -> None:
        """Active mode is not supported with ANNUAL cadence."""
        with pytest.raises(ValueError, match="Active mode is not supported with ANNUAL cadence"):
            GlidepathAllocationPolicy(
                start_equity=Decimal("0.70"),
                end_equity=Decimal("0.90"),
                slope=Decimal("0.02"),
                mode="active",
                cadence=GlidepathCadence.ANNUAL,
            )


class TestGlidepathCadenceEnum:
    """Tests for GlidepathCadence enum."""

    def test_monthly_value(self) -> None:
        assert GlidepathCadence.MONTHLY.value == "monthly"

    def test_annual_value(self) -> None:
        assert GlidepathCadence.ANNUAL.value == "annual"


class TestBackwardCompatibility:
    """Tests ensuring existing behavior is preserved."""

    def test_existing_tests_still_pass(self) -> None:
        """The original test cases from test_glidepath_policy.py should still pass."""
        # This mirrors TestPassiveGlidepath.test_advancement_follows_elapsed_periods
        ds = _dataset([False] * 10)
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.6"),
            end_equity=Decimal("1.0"),
            slope=Decimal("0.005"),
            mode="passive",
        )
        assert _equity_weight(p, ds, 0) == Decimal("0.6")
        assert _equity_weight(p, ds, 1) == Decimal("0.605")
        assert _equity_weight(p, ds, 4) == Decimal("0.62")

        # This mirrors TestPassiveGlidepath.test_capped_at_end_equity
        ds = _dataset([False] * 100)
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.6"),
            end_equity=Decimal("0.8"),
            slope=Decimal("0.005"),
            mode="passive",
        )
        assert _equity_weight(p, ds, 40) == Decimal("0.8")
        assert _equity_weight(p, ds, 50) == Decimal("0.8")

        # Active mode tests (mirrors TestActiveGlidepath)
        ds = _dataset([True, False, False, True, False, False, True])
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.6"),
            end_equity=Decimal("1.0"),
            slope=Decimal("0.005"),
            mode="active",
        )
        assert _equity_weight(p, ds, 0) == Decimal("0.605")
        assert _equity_weight(p, ds, 3) == Decimal("0.61")
        assert _equity_weight(p, ds, 6) == Decimal("0.615")
