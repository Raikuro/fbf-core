"""Unit tests for GlidepathAllocationPolicy.

Verifies passive and active glidepath temporal semantics independently
of full-pipeline execution or ERN aggregate results.

Convention: slope is expressed as a **fraction** (e.g. 0.005 for 0.5
percentage points).  The YAML/builder layer converts percentage points
to fractions before constructing the policy.
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
from fbf.core.domain.policies.glidepath import GlidepathAllocationPolicy

_EQUITY = AssetClass(id="equity", name="", description="")
_BOND = AssetClass(id="bond", name="", description="")

# Slope constants in fraction terms
_SLOPE_0_5_PP = Decimal("0.005")  # 0.5 percentage points
_SLOPE_1_0_PP = Decimal("0.01")   # 1.0 percentage points


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


def _dataset(underwater_flags: list[bool]) -> Dataset:
    base = date(2020, 1, 1)
    snaps = [_snap(uw, base + timedelta(days=30 * i)) for i, uw in enumerate(underwater_flags)]
    return Dataset(snapshots=snaps, frequency="monthly", version="1.0")


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


class TestGlidepathAllocationPolicyInit:
    def test_valid_construction(self) -> None:
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.6"),
            end_equity=Decimal("1.0"),
            slope=_SLOPE_0_5_PP,
            mode="passive",
        )
        assert p.start_equity == Decimal("0.6")
        assert p.end_equity == Decimal("1.0")
        assert p.slope == _SLOPE_0_5_PP
        assert p.mode == "passive"

    def test_invalid_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="passive.*active"):
            GlidepathAllocationPolicy(
                start_equity=Decimal("0.6"),
                end_equity=Decimal("1.0"),
                slope=_SLOPE_0_5_PP,
                mode="invalid",
            )

    def test_negative_slope_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            GlidepathAllocationPolicy(
                start_equity=Decimal("0.6"),
                end_equity=Decimal("1.0"),
                slope=Decimal("-0.001"),
                mode="passive",
            )


class TestPassiveGlidepath:
    def test_period_zero_returns_start(self) -> None:
        ds = _dataset([False, False, False])
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.6"),
            end_equity=Decimal("1.0"),
            slope=_SLOPE_0_5_PP,
            mode="passive",
        )
        assert _equity_weight(p, ds, 0) == Decimal("0.6")

    def test_advancement_follows_elapsed_periods(self) -> None:
        ds = _dataset([False] * 10)
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.6"),
            end_equity=Decimal("1.0"),
            slope=_SLOPE_0_5_PP,
            mode="passive",
        )
        # period 0: 0.6 + 0.005*0 = 0.6
        assert _equity_weight(p, ds, 0) == Decimal("0.6")
        # period 1: 0.6 + 0.005*1 = 0.605
        assert _equity_weight(p, ds, 1) == Decimal("0.605")
        # period 4: 0.6 + 0.005*4 = 0.62
        assert _equity_weight(p, ds, 4) == Decimal("0.62")

    def test_capped_at_end_equity(self) -> None:
        ds = _dataset([False] * 100)
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.6"),
            end_equity=Decimal("0.8"),
            slope=_SLOPE_0_5_PP,
            mode="passive",
        )
        # period 40: 0.6 + 0.005*40 = 0.8 — exactly at cap
        assert _equity_weight(p, ds, 40) == Decimal("0.8")
        # period 50: 0.6 + 0.005*50 = 0.85 — capped at 0.8
        assert _equity_weight(p, ds, 50) == Decimal("0.8")

    def test_bond_is_complement(self) -> None:
        ds = _dataset([False] * 10)
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.6"),
            end_equity=Decimal("1.0"),
            slope=_SLOPE_0_5_PP,
            mode="passive",
        )
        ctx = _context(ds, 5)
        decision = p.decide(ctx)
        total = sum(decision.allocation_target.weights.values())
        assert total == Decimal("1")


class TestActiveGlidepath:
    def test_advancement_follows_qualifying_periods(self) -> None:
        # T F F T F F T — exactly 3 qualifying periods at period 6
        ds = _dataset([True, False, False, True, False, False, True])
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.6"),
            end_equity=Decimal("1.0"),
            slope=_SLOPE_0_5_PP,
            mode="active",
        )
        # period 0: 1 underwater (T) -> 0.6 + 0.005*1 = 0.605
        assert _equity_weight(p, ds, 0) == Decimal("0.605")
        # period 1: 1 underwater (T,F) -> 0.6 + 0.005*1 = 0.605
        assert _equity_weight(p, ds, 1) == Decimal("0.605")
        # period 2: 1 underwater (T,F,F) -> 0.6 + 0.005*1 = 0.605
        assert _equity_weight(p, ds, 2) == Decimal("0.605")
        # period 3: 2 underwater (T,F,F,T) -> 0.6 + 0.005*2 = 0.61
        assert _equity_weight(p, ds, 3) == Decimal("0.61")
        # period 4: 2 underwater (T,F,F,T,F) -> 0.6 + 0.005*2 = 0.61
        assert _equity_weight(p, ds, 4) == Decimal("0.61")
        # period 5: 2 underwater (T,F,F,T,F,F) -> 0.6 + 0.005*2 = 0.61
        assert _equity_weight(p, ds, 5) == Decimal("0.61")
        # period 6: 3 underwater (T,F,F,T,F,F,T) -> 0.6 + 0.005*3 = 0.615
        assert _equity_weight(p, ds, 6) == Decimal("0.615")

    def test_no_advancement_when_never_underwater(self) -> None:
        ds = _dataset([False] * 10)
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.6"),
            end_equity=Decimal("1.0"),
            slope=_SLOPE_0_5_PP,
            mode="active",
        )
        for i in range(10):
            assert _equity_weight(p, ds, i) == Decimal("0.6")

    def test_all_underwater_equals_passive_after_period_zero(self) -> None:
        # Active counts dataset[0:M+1] (includes current), passive uses period_index.
        # They differ by exactly 1 advancement when all periods are underwater.
        ds = _dataset([True] * 20)
        active = GlidepathAllocationPolicy(
            start_equity=Decimal("0.6"),
            end_equity=Decimal("1.0"),
            slope=_SLOPE_0_5_PP,
            mode="active",
        )
        passive = GlidepathAllocationPolicy(
            start_equity=Decimal("0.6"),
            end_equity=Decimal("1.0"),
            slope=_SLOPE_0_5_PP,
            mode="passive",
        )
        for i in range(20):
            active_w = _equity_weight(active, ds, i)
            passive_w = _equity_weight(passive, ds, i)
            # Active is exactly one slope-step ahead of passive
            assert active_w == passive_w + _SLOPE_0_5_PP, (
                f"Period {i}: active={active_w}, passive={passive_w}"
            )

    def test_transitions_into_underwater(self) -> None:
        # F F F T T T — advancement starts at period 3
        ds = _dataset([False, False, False, True, True, True])
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.6"),
            end_equity=Decimal("1.0"),
            slope=_SLOPE_0_5_PP,
            mode="active",
        )
        assert _equity_weight(p, ds, 0) == Decimal("0.6")
        assert _equity_weight(p, ds, 1) == Decimal("0.6")
        assert _equity_weight(p, ds, 2) == Decimal("0.6")
        assert _equity_weight(p, ds, 3) == Decimal("0.605")
        assert _equity_weight(p, ds, 4) == Decimal("0.61")
        assert _equity_weight(p, ds, 5) == Decimal("0.615")

    def test_transitions_out_of_underwater(self) -> None:
        # T T T F F F — advancement stops after period 2
        ds = _dataset([True, True, True, False, False, False])
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.6"),
            end_equity=Decimal("1.0"),
            slope=_SLOPE_0_5_PP,
            mode="active",
        )
        assert _equity_weight(p, ds, 0) == Decimal("0.605")
        assert _equity_weight(p, ds, 1) == Decimal("0.61")
        assert _equity_weight(p, ds, 2) == Decimal("0.615")
        assert _equity_weight(p, ds, 3) == Decimal("0.615")
        assert _equity_weight(p, ds, 4) == Decimal("0.615")
        assert _equity_weight(p, ds, 5) == Decimal("0.615")

    def test_capped_at_end_equity(self) -> None:
        # All underwater, slope large enough to hit cap
        ds = _dataset([True] * 100)
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.6"),
            end_equity=Decimal("0.8"),
            slope=_SLOPE_0_5_PP,
            mode="active",
        )
        # period 40: 0.6 + 0.005*40 = 0.8
        assert _equity_weight(p, ds, 40) == Decimal("0.8")
        assert _equity_weight(p, ds, 50) == Decimal("0.8")


class TestEdgeCases:
    def test_start_equals_end(self) -> None:
        ds = _dataset([True] * 10)
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.8"),
            end_equity=Decimal("0.8"),
            slope=_SLOPE_0_5_PP,
            mode="passive",
        )
        for i in range(10):
            assert _equity_weight(p, ds, i) == Decimal("0.8")

    def test_slope_zero(self) -> None:
        ds = _dataset([True] * 10)
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.6"),
            end_equity=Decimal("1.0"),
            slope=Decimal("0"),
            mode="passive",
        )
        for i in range(10):
            assert _equity_weight(p, ds, i) == Decimal("0.6")

    def test_slope_zero_active(self) -> None:
        ds = _dataset([True] * 10)
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.6"),
            end_equity=Decimal("1.0"),
            slope=Decimal("0"),
            mode="active",
        )
        for i in range(10):
            assert _equity_weight(p, ds, i) == Decimal("0.6")

    def test_full_range_passive(self) -> None:
        # 0.6 to 1.0 over 80 periods with slope 0.005 (0.5 pp)
        ds = _dataset([False] * 81)
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.6"),
            end_equity=Decimal("1.0"),
            slope=_SLOPE_0_5_PP,
            mode="passive",
        )
        # period 0: 0.6 + 0.005*0 = 0.6
        assert _equity_weight(p, ds, 0) == Decimal("0.6")
        # period 80: 0.6 + 0.005*80 = 1.0
        assert _equity_weight(p, ds, 80) == Decimal("1.0")

    def test_one_percent_slope(self) -> None:
        ds = _dataset([False] * 11)
        p = GlidepathAllocationPolicy(
            start_equity=Decimal("0.6"),
            end_equity=Decimal("1.0"),
            slope=_SLOPE_1_0_PP,
            mode="passive",
        )
        # period 0: 0.6 + 0.01*0 = 0.6
        assert _equity_weight(p, ds, 0) == Decimal("0.6")
        # period 1: 0.6 + 0.01*1 = 0.61
        assert _equity_weight(p, ds, 1) == Decimal("0.61")
        # period 10: 0.6 + 0.01*10 = 0.7
        assert _equity_weight(p, ds, 10) == Decimal("0.7")
