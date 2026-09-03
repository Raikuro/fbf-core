"""Tests for the Part 3 research planner.

Verifies deterministic plan generation from the canonical cohort manifest,
per-cohort horizon constraints, CAPE metadata isolation, and engine boundary
preservation.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Money
from fbf.core.research.part3_planner import (
    CohortManifest,
    CohortManifestEntry,
    Part3PlannerConfig,
    build_cape_registry,
    load_manifest,
    materialize_part3_plan,
)
from fbf.core.study.internal.cohort.specification import CohortSpecification

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

EQ = AssetClass(id="equity", name="", description="")
BD = AssetClass(id="bond", name="", description="")

MANIFEST_PATH = Path("data/ern/cohort_manifest_part3.json")
H720_PATH = Path("data/ern/ern_swr_h720.json")


def _snapshot(
    day: int,
    equity: Decimal = Decimal("100"),
    bond: Decimal = Decimal("50"),
) -> MarketSnapshot:
    return MarketSnapshot(
        date=date(2000, 1, day),
        index_levels={EQ: equity, BD: bond},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("1"),
        is_ath=True,
        is_underwater=False,
        running_ath=equity,
    )


def _make_minimal_manifest(
    cohorts: list[dict[str, Any]] | None = None,
) -> CohortManifest:
    """Build a minimal manifest for testing."""
    if cohorts is None:
        cohorts = [
            {
                "cohort_date": "2000-01-01",
                "market_available": True,
                "cape_available": True,
                "cape_value": 25.0,
                "cape_regime": "HIGH",
                "start_month_index": 0,
                "max_horizon_months": 240,
            },
            {
                "cohort_date": "2000-02-01",
                "market_available": True,
                "cape_available": True,
                "cape_value": 14.0,
                "cape_regime": "BELOW_15",
                "start_month_index": 1,
                "max_horizon_months": 239,
            },
            {
                "cohort_date": "2000-03-01",
                "market_available": False,
                "cape_available": False,
                "cape_value": None,
                "cape_regime": None,
                "start_month_index": 2,
                "max_horizon_months": 238,
            },
        ]
    entries = tuple(CohortManifestEntry(**c) for c in cohorts)
    return CohortManifest(
        version="1.0",
        description="test manifest",
        market_source="test",
        cape_source="test",
        fee=0.0005,
        statistics={"total_cohorts": len(entries)},
        cohorts=entries,
    )


def _make_minimal_trajectory(num_months: int = 24) -> Dataset:
    """Build a minimal monthly dataset trajectory for testing.

    Creates snapshots on the first of each month starting from 2000-01-01.
    This matches the cohort start dates from the minimal manifest.
    """
    snapshots = []
    for i in range(num_months):
        month = (i % 12) + 1
        year = 2000 + (i // 12)
        snapshots.append(
            MarketSnapshot(
                date=date(year, month, 1),
                index_levels={EQ: Decimal("100"), BD: Decimal("50")},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("1"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            )
        )
    return Dataset(snapshots=snapshots, frequency="monthly", version="1.0")


# ---------------------------------------------------------------------------
# Manifest loading tests
# ---------------------------------------------------------------------------


class TestManifestLoading:
    @pytest.mark.skipif(not MANIFEST_PATH.is_file(), reason="Manifest not present")
    def test_load_manifest_cohort_count(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        assert len(manifest.cohorts) == 1739

    @pytest.mark.skipif(not MANIFEST_PATH.is_file(), reason="Manifest not present")
    def test_load_manifest_first_cohort(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        first = manifest.cohorts[0]
        assert first.cohort_date == "1871-02-01"
        assert first.market_available is True
        assert first.cape_available is False
        assert first.cape_value is None
        assert first.cape_regime is None

    @pytest.mark.skipif(not MANIFEST_PATH.is_file(), reason="Manifest not present")
    def test_load_manifest_statistics(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        assert manifest.statistics["total_cohorts"] == 1739
        assert manifest.statistics["cape_available"] == 1485

    @pytest.mark.skipif(not MANIFEST_PATH.is_file(), reason="Manifest not present")
    def test_load_manifest_is_deterministic(self) -> None:
        m1 = load_manifest(MANIFEST_PATH)
        m2 = load_manifest(MANIFEST_PATH)
        assert m1.cohorts == m2.cohorts
        assert m1.statistics == m2.statistics


# ---------------------------------------------------------------------------
# CAPE registry tests
# ---------------------------------------------------------------------------


class TestCapeRegistry:
    def test_cape_lookup_existing_cohort(self) -> None:
        manifest = _make_minimal_manifest()
        registry = build_cape_registry(manifest)
        cohort = CohortSpecification(start_date=date(2000, 1, 1))
        cape_value, regime = registry(cohort)
        assert cape_value == Decimal("25.0")
        assert regime == "HIGH"

    def test_cape_lookup_missing_cohort(self) -> None:
        manifest = _make_minimal_manifest()
        registry = build_cape_registry(manifest)
        cohort = CohortSpecification(start_date=date(1999, 12, 1))
        cape_value, regime = registry(cohort)
        assert cape_value is None
        assert regime is None

    def test_cape_lookup_unavailable_cape(self) -> None:
        manifest = _make_minimal_manifest()
        registry = build_cape_registry(manifest)
        # 2000-03-01 has cape_available=False
        cohort = CohortSpecification(start_date=date(2000, 3, 1))
        cape_value, regime = registry(cohort)
        assert cape_value is None
        assert regime is None

    def test_cape_registry_is_deterministic(self) -> None:
        manifest = _make_minimal_manifest()
        r1 = build_cape_registry(manifest)
        r2 = build_cape_registry(manifest)
        cohort = CohortSpecification(start_date=date(2000, 1, 1))
        assert r1(cohort) == r2(cohort)


# ---------------------------------------------------------------------------
# Plan materialization tests
# ---------------------------------------------------------------------------


WEALTH = Money(Decimal("1000000"), Money.ZERO.currency)


class TestPart3PlanMaterialization:
    def test_market_available_cohorts_only(self) -> None:
        manifest = _make_minimal_manifest()
        trajectory = _make_minimal_trajectory(24)
        config = Part3PlannerConfig(
            equity_allocations=(Decimal("0.5"),),
            withdrawal_rates=(Decimal("0.04"),),
            horizon_years=(1,),
            final_value_targets=None,
            allocation_policy_type="ConstantAllocationPolicy",
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
        )
        result = materialize_part3_plan(
            manifest=manifest,
            canonical_trajectory=trajectory,
            config=config,
            initial_wealth=WEALTH,
        )
        # Only 2 market-available cohorts (2000-01-01, 2000-02-01)
        cohort_dates = {u.cohort.start_date.isoformat() for u in result.plan}
        assert "2000-03-01" not in cohort_dates
        assert len(cohort_dates) == 2

    def test_parameter_cartesian_product(self) -> None:
        manifest = _make_minimal_manifest()
        trajectory = _make_minimal_trajectory(24)
        config = Part3PlannerConfig(
            equity_allocations=(Decimal("0.5"), Decimal("1.0")),
            withdrawal_rates=(Decimal("0.04"),),
            horizon_years=(1,),
            final_value_targets=None,
            allocation_policy_type="ConstantAllocationPolicy",
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
        )
        result = materialize_part3_plan(
            manifest=manifest,
            canonical_trajectory=trajectory,
            config=config,
            initial_wealth=WEALTH,
        )
        # 2 cohorts x 2 allocations x 1 rate x 1 horizon = 4 units
        assert len(result.plan) == 4

    def test_horizon_constraint_applied(self) -> None:
        """Cohort with max_horizon_months=12 gets capped even if config requests 24."""
        cohorts = [
            {
                "cohort_date": "2000-01-01",
                "market_available": True,
                "cape_available": True,
                "cape_value": 20.0,
                "cape_regime": "MODERATE",
                "start_month_index": 0,
                "max_horizon_months": 12,
            },
        ]
        manifest = _make_minimal_manifest(cohorts)
        trajectory = _make_minimal_trajectory(24)
        config = Part3PlannerConfig(
            equity_allocations=(Decimal("0.5"),),
            withdrawal_rates=(Decimal("0.04"),),
            horizon_years=(2,),  # requests 24 months
            final_value_targets=None,
            allocation_policy_type="ConstantAllocationPolicy",
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
        )
        result = materialize_part3_plan(
            manifest=manifest,
            canonical_trajectory=trajectory,
            config=config,
            initial_wealth=WEALTH,
        )
        # Effective horizon should be min(25, 12) = 12
        assert result.plan[0].horizon_months == 12

    def test_no_cape_in_planned_units(self) -> None:
        """PlannedSimulationUnit must not contain CAPE state."""
        manifest = _make_minimal_manifest()
        trajectory = _make_minimal_trajectory(24)
        config = Part3PlannerConfig(
            equity_allocations=(Decimal("0.5"),),
            withdrawal_rates=(Decimal("0.04"),),
            horizon_years=(1,),
            final_value_targets=None,
            allocation_policy_type="ConstantAllocationPolicy",
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
        )
        result = materialize_part3_plan(
            manifest=manifest,
            canonical_trajectory=trajectory,
            config=config,
            initial_wealth=WEALTH,
        )
        unit = result.plan[0]
        # Verify no CAPE-related attributes exist on PlannedSimulationUnit
        assert not hasattr(unit, "cape")
        assert not hasattr(unit, "cape_value")
        assert not hasattr(unit, "cape_regime")

    def test_cape_metadata_returned_separately(self) -> None:
        """CAPE metadata is returned via the registry, not in the plan."""
        manifest = _make_minimal_manifest()
        trajectory = _make_minimal_trajectory(24)
        config = Part3PlannerConfig(
            equity_allocations=(Decimal("0.5"),),
            withdrawal_rates=(Decimal("0.04"),),
            horizon_years=(1,),
            final_value_targets=None,
            allocation_policy_type="ConstantAllocationPolicy",
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
        )
        result = materialize_part3_plan(
            manifest=manifest,
            canonical_trajectory=trajectory,
            config=config,
            initial_wealth=WEALTH,
        )
        # CAPE metadata is accessible via the registry
        cohort = result.plan[0].cohort
        cape_value, regime = result.get_cape_metadata(cohort)
        assert cape_value == Decimal("25.0")
        assert regime == "HIGH"

    def test_deterministic_plan_generation(self) -> None:
        """Repeated materialization produces identical plans."""
        manifest = _make_minimal_manifest()
        trajectory = _make_minimal_trajectory(24)
        config = Part3PlannerConfig(
            equity_allocations=(Decimal("0.5"), Decimal("1.0")),
            withdrawal_rates=(Decimal("0.04"),),
            horizon_years=(1,),
            final_value_targets=(Decimal("0.0"),),
            allocation_policy_type="ConstantAllocationPolicy",
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
        )
        r1 = materialize_part3_plan(manifest, trajectory, config, WEALTH)
        r2 = materialize_part3_plan(manifest, trajectory, config, WEALTH)
        assert len(r1.plan) == len(r2.plan)
        for u1, u2 in zip(r1.plan, r2.plan, strict=True):
            assert u1.cohort.start_date == u2.cohort.start_date
            assert u1.parameter_config == u2.parameter_config
            assert u1.horizon_months == u2.horizon_months

    def test_cohort_ordering_is_stable(self) -> None:
        """Cohorts appear in manifest order (chronological)."""
        manifest = _make_minimal_manifest()
        trajectory = _make_minimal_trajectory(24)
        config = Part3PlannerConfig(
            equity_allocations=(Decimal("0.5"),),
            withdrawal_rates=(Decimal("0.04"),),
            horizon_years=(1,),
            final_value_targets=None,
            allocation_policy_type="ConstantAllocationPolicy",
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
        )
        result = materialize_part3_plan(manifest, trajectory, config, WEALTH)
        dates = [u.cohort.start_date for u in result.plan]
        # Within each parameter config, cohorts should be in manifest order
        assert dates == sorted(dates)

    def test_empty_manifest_raises(self) -> None:
        manifest = _make_minimal_manifest(cohorts=[])
        trajectory = _make_minimal_trajectory(24)
        config = Part3PlannerConfig(
            equity_allocations=(Decimal("0.5"),),
            withdrawal_rates=(Decimal("0.04"),),
            horizon_years=(1,),
            final_value_targets=None,
            allocation_policy_type="ConstantAllocationPolicy",
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
        )
        with pytest.raises(ValueError, match="No market-available cohorts"):
            materialize_part3_plan(manifest, trajectory, config, WEALTH)


# ---------------------------------------------------------------------------
# ERN integration tests (require real data)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not MANIFEST_PATH.is_file(), reason="Manifest not present")
@pytest.mark.skipif(not H720_PATH.is_file(), reason="h720 not present")
class TestPart3ErnIntegration:
    def test_manifest_cohort_count(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        assert len(manifest.cohorts) == 1739

    def test_market_available_count(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        market_available = sum(1 for c in manifest.cohorts if c.market_available)
        assert market_available == 1739

    def test_cape_available_count(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        cape_available = sum(1 for c in manifest.cohorts if c.cape_available)
        assert cape_available == 1485

    def test_regime_distribution(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        from collections import Counter
        regimes = Counter(c.cape_regime for c in manifest.cohorts if c.cape_available)
        assert regimes["BELOW_15"] == 632
        assert regimes["MODERATE"] == 470
        assert regimes["HIGH"] == 330
        assert regimes["EXTREME"] == 53


# ---------------------------------------------------------------------------
# Manifest index convention regression tests (C6.7.1)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not MANIFEST_PATH.is_file(), reason="Manifest not present")
@pytest.mark.skipif(not H720_PATH.is_file(), reason="h720 not present")
class TestManifestIndexConvention:
    """Regression tests proving the manifest's start_month_index convention
    and corrected max_horizon computation.

    The manifest uses start_month_index = trajectory_index - 1.
    max_horizon = n_snapshots - trajectory_index = n_snapshots - (start_month_index + 1).
    """

    def test_start_month_index_offset(self) -> None:
        """start_month_index is trajectory_index - 1 for all cohorts."""
        from fbf.core.study.builder import resolve_dataset

        manifest = load_manifest(MANIFEST_PATH)
        dataset = resolve_dataset("ern_swr_h720", "data/ern")
        traj_date_to_idx = {s.date.isoformat(): i for i, s in enumerate(dataset)}

        for entry in manifest.cohorts:
            traj_idx = traj_date_to_idx[entry.cohort_date]
            assert entry.start_month_index == traj_idx - 1, (
                f"{entry.cohort_date}: start_month_index={entry.start_month_index} "
                f"but trajectory_index={traj_idx}"
            )

    def test_max_horizon_formula(self) -> None:
        """max_horizon = n_snapshots - trajectory_index for all cohorts."""
        from fbf.core.study.builder import resolve_dataset

        manifest = load_manifest(MANIFEST_PATH)
        dataset = resolve_dataset("ern_swr_h720", "data/ern")
        n = len(dataset)
        traj_date_to_idx = {s.date.isoformat(): i for i, s in enumerate(dataset)}

        for entry in manifest.cohorts:
            traj_idx = traj_date_to_idx[entry.cohort_date]
            expected = n - traj_idx
            assert entry.max_horizon_months == expected, (
                f"{entry.cohort_date}: max_horizon={entry.max_horizon_months} "
                f"but expected {expected} (n={n}, traj_idx={traj_idx})"
            )

    def test_first_cohort_max_horizon(self) -> None:
        """1871-02-01: trajectory index 1, max_horizon = 2459 - 1 = 2458."""
        manifest = load_manifest(MANIFEST_PATH)
        first = manifest.cohorts[0]
        assert first.cohort_date == "1871-02-01"
        assert first.max_horizon_months == 2458

    def test_2015_10_01_max_horizon(self) -> None:
        """2015-10-01: trajectory index 1737, max_horizon = 2459 - 1737 = 722."""
        manifest = load_manifest(MANIFEST_PATH)
        entry = [c for c in manifest.cohorts if c.cohort_date == "2015-10-01"][0]
        assert entry.max_horizon_months == 722

    def test_2015_11_01_max_horizon(self) -> None:
        """2015-11-01: trajectory index 1738, max_horizon = 2459 - 1738 = 721."""
        manifest = load_manifest(MANIFEST_PATH)
        entry = [c for c in manifest.cohorts if c.cohort_date == "2015-11-01"][0]
        assert entry.max_horizon_months == 721

    def test_2015_12_01_max_horizon(self) -> None:
        """2015-12-01: trajectory index 1739, max_horizon = 2459 - 1739 = 720."""
        manifest = load_manifest(MANIFEST_PATH)
        entry = [c for c in manifest.cohorts if c.cohort_date == "2015-12-01"][0]
        assert entry.max_horizon_months == 720

    def test_60y_eligibility_count(self) -> None:
        """1,738 cohorts have max_horizon >= 721 (full 60-year eligibility)."""
        manifest = load_manifest(MANIFEST_PATH)
        eligible = sum(1 for c in manifest.cohorts if c.max_horizon_months >= 721)
        assert eligible == 1738

    def test_2015_12_01_truncated_for_60y(self) -> None:
        """2015-12-01 has max_horizon=720, one month short of 721 (60-year)."""
        manifest = load_manifest(MANIFEST_PATH)
        entry = [c for c in manifest.cohorts if c.cohort_date == "2015-12-01"][0]
        assert entry.max_horizon_months == 720
        assert entry.max_horizon_months < 721

    def test_no_systematic_offset(self) -> None:
        """max_horizon - (n_snapshots - trajectory_index) == 0 for all cohorts."""
        from fbf.core.study.builder import resolve_dataset

        manifest = load_manifest(MANIFEST_PATH)
        dataset = resolve_dataset("ern_swr_h720", "data/ern")
        n = len(dataset)
        traj_date_to_idx = {s.date.isoformat(): i for i, s in enumerate(dataset)}

        for entry in manifest.cohorts:
            traj_idx = traj_date_to_idx[entry.cohort_date]
            correct = n - traj_idx
            assert entry.max_horizon_months == correct, (
                f"{entry.cohort_date}: off by {entry.max_horizon_months - correct}"
            )

    def test_horizon_eligibility_h720(self) -> None:
        """h720 eligibility = 1739 (all cohorts have max_horizon >= 720)."""
        manifest = load_manifest(MANIFEST_PATH)
        assert manifest.statistics["horizon_eligibility"]["h720"] == 1739
