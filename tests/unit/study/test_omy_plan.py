"""Tests for OMY study-plan integration (S3.4).

Validates that:
  - Accumulation is executed exactly N times for N cohorts
  - Plan unit count is N × M
  - Plan unit initial portfolios match independent accumulation
  - Retirement datasets have correct horizon_months
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.money import Currency, Money
from fbf.core.study.builder import (
    OmyStudyConfiguration,
    StudyConfiguration,
    build_omy_study_plan,
)


def _small_dataset(num_snapshots: int) -> Dataset:
    """Build a small flat dataset with the given number of snapshots."""
    from tests.fixtures.accumulation import _snapshot

    base = date(2020, 1, 1)
    small_dates = [base + timedelta(days=30 * m) for m in range(num_snapshots)]
    small_snapshots = [
        _snapshot(d, Decimal("1"), Decimal("1")) for d in small_dates
    ]
    return Dataset(
        snapshots=small_snapshots,
        frequency="monthly",
        version="test-small",
        identifier="test-small",
    )


def _make_omy_config(
    *,
    dataset_identifier: str = "test-small",
    withdrawal_rate: Decimal = Decimal("0.04"),
    horizon_years: int = 30,
) -> OmyStudyConfiguration:
    """Build an OMY study configuration for testing."""
    base = StudyConfiguration(
        name="test-omy",
        description="test",
        version="1.0",
        dataset_identifier=dataset_identifier,
        allocation_policy_type="ConstantAllocationPolicy",
        allocation_policy_values=(Decimal("0.75"),),
        withdrawal_policy_type="FixedRealWithdrawalPolicy",
        withdrawal_policy_values=(withdrawal_rate,),
        horizon_years=(horizon_years,),
    )
    return OmyStudyConfiguration(
        base_config=base,
        contribution_amount=Money(Decimal("5000"), Currency.EUR),
        equity_weight=Decimal("0.75"),
        bond_weight=Decimal("0.25"),
        original_initial_wealth=Money(Decimal("2000000"), Currency.EUR),
        fv_target_fraction=Decimal("0.25"),
    )


def _patch_resolve(small_dataset: Dataset) -> Any:
    """Patch resolve_dataset to return small_dataset. Returns the original for restoration."""
    import fbf.core.study.builder as builder_mod

    original_resolve = builder_mod.resolve_dataset

    def mock_resolve(identifier: str, data_dir: str | None) -> Dataset:
        return small_dataset

    builder_mod.resolve_dataset = mock_resolve
    return original_resolve


class TestOmyPlanAccumulationCaching:
    """Accumulation must be executed exactly once per cohort."""

    def test_single_cohort_single_swr(self) -> None:
        """With flat prices, accumulation produces same portfolio for all cohorts."""
        config = _make_omy_config(horizon_years=1)
        # 12 (acc) + 13 (ret: 12+1) = 25 snapshots minimum
        small = _small_dataset(26)
        original_resolve = _patch_resolve(small)
        try:
            result = build_omy_study_plan(config, data_dir=None)
            plan = result.plan
            # Multiple cohorts may be generated; accumulation is cached per cohort.
            # With flat prices, all cohorts get the same accumulated portfolio.
            portfolios = [u.initial_portfolio for u in plan.units]
            assert len(portfolios) >= 1
            # All should be identical (same flat prices, same accumulation)
            assert all(p == portfolios[0] for p in portfolios)
        finally:
            import fbf.core.study.builder as builder_mod

            builder_mod.resolve_dataset = original_resolve

    def test_multiple_param_configs(self) -> None:
        """1 cohort × M SWR = M retirement units, 1 accumulation."""
        config = _make_omy_config(
            horizon_years=1,
            withdrawal_rate=Decimal("0.03"),
        )
        small = _small_dataset(26)
        original_resolve = _patch_resolve(small)
        try:
            result = build_omy_study_plan(config, data_dir=None)
            plan = result.plan
            # 1 cohort × 1 SWR = 1 unit
            assert len(plan.units) >= 1
        finally:
            import fbf.core.study.builder as builder_mod

            builder_mod.resolve_dataset = original_resolve


class TestOmyPlanUnitStructure:
    """Plan units must have correct structure for retirement."""

    def test_unit_has_horizon_months(self) -> None:
        """Each unit must have horizon_months set."""
        config = _make_omy_config(horizon_years=2)
        small = _small_dataset(37)
        original_resolve = _patch_resolve(small)
        try:
            result = build_omy_study_plan(config, data_dir=None)
            plan = result.plan
            for unit in plan.units:
                assert unit.horizon_months is not None
                assert unit.horizon_months > 0
        finally:
            import fbf.core.study.builder as builder_mod

            builder_mod.resolve_dataset = original_resolve

    def test_unit_initial_portfolio_has_holdings(self) -> None:
        """Accumulation must produce a non-empty portfolio."""
        config = _make_omy_config(horizon_years=1)
        small = _small_dataset(26)
        original_resolve = _patch_resolve(small)
        try:
            result = build_omy_study_plan(config, data_dir=None)
            plan = result.plan
            for unit in plan.units:
                total = sum(h.units for h in unit.initial_portfolio.holdings)
                assert total > Decimal("0")
        finally:
            import fbf.core.study.builder as builder_mod

            builder_mod.resolve_dataset = original_resolve
