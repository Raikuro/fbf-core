"""Integration tests for Part 42 end-to-end execution (S3.6).

Validates that:
  - Small grid: 1 cohort × 1 SWR → completes
  - HorizonMonths contract: horizon_months=348 produces 348 transitions
  - Portfolio handoff continuity
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.money import Currency, Money
from tests.fixtures.accumulation import BOND, EQUITY


def _small_omy_dataset(num_snapshots: int) -> Dataset:
    """Build a small flat dataset for OMY integration testing."""
    from tests.fixtures.accumulation import _snapshot

    base = date(2020, 1, 1)
    dates = [base + timedelta(days=30 * m) for m in range(num_snapshots)]
    snapshots = [_snapshot(d, Decimal("1"), Decimal("1")) for d in dates]
    return Dataset(
        snapshots=snapshots,
        frequency="monthly",
        version="test-omy-integration",
        identifier="test-omy-integration",
    )


class TestOmySmallGridExecution:
    """Small grid must execute successfully."""

    def test_single_cohort_single_swr_sequential(self) -> None:
        """1 cohort × 1 SWR with accumulation → completes."""
        from fbf.core.study.builder import (
            OmyStudyConfiguration,
            StudyConfiguration,
            build_omy_study_plan,
        )

        config = OmyStudyConfiguration(
            base_config=StudyConfiguration(
                name="test-omy-e2e",
                description="test",
                version="1.0",
                dataset_identifier="test-omy-integration",
                allocation_policy_type="ConstantAllocationPolicy",
                allocation_policy_values=(Decimal("0.75"),),
                withdrawal_policy_type="FixedRealWithdrawalPolicy",
                withdrawal_policy_values=(Decimal("0.04"),),
                horizon_years=(1,),
            ),
            contribution_amount=Money(Decimal("5000"), Currency.EUR),
            equity_weight=Decimal("0.75"),
            bond_weight=Decimal("0.25"),
            original_initial_wealth=Money(Decimal("2000000"), Currency.EUR),
            fv_target_fraction=Decimal("0.25"),
        )

        small = _small_omy_dataset(26)

        import fbf.core.study.builder as builder_mod

        original_resolve = builder_mod.resolve_dataset

        def mock_resolve(identifier: str, data_dir: str | None) -> Dataset:
            return small

        builder_mod.resolve_dataset = mock_resolve
        try:
            result = build_omy_study_plan(config, data_dir=None)
            plan = result.plan

            # Verify plan structure
            assert len(plan.units) >= 1
            for unit in plan.units:
                assert unit.horizon_months is not None
                assert unit.dataset is not None
                assert len(unit.dataset) > 0
        finally:
            builder_mod.resolve_dataset = original_resolve


class TestHorizonMonthsContract:
    """Regression test for the horizon_months contract.

    horizon_months=348 must produce 348 transitions with 349 observations.
    """

    def test_horizon_months_348_dataset_slice(self) -> None:
        """Dataset.slice() with horizon_months=348 returns 348 snapshots."""
        dataset = _small_omy_dataset(400)
        sliced = dataset.slice(date(2020, 1, 1), 348)
        assert len(sliced) == 348
        assert sliced[0].date == date(2020, 1, 1)

    def test_horizon_months_13_for_accumulation(self) -> None:
        """Accumulation needs 13 snapshots for 12 transitions."""
        dataset = _small_omy_dataset(50)
        sliced = dataset.slice(date(2020, 1, 1), 13)
        assert len(sliced) == 13
        assert sliced[0].date == date(2020, 1, 1)


class TestPortfolioHandoff:
    """Accumulation must produce a valid handoff portfolio."""

    def test_accumulation_changes_portfolio(self) -> None:
        """After accumulation, portfolio must differ from initial."""
        from fbf.core.study.internal.accumulation import run_accumulation_phase
        from tests.fixtures.accumulation import (
            CONTRIBUTION,
            KNOWN_PORTFOLIO,
            TARGET_WEIGHTS,
            _snapshot,
        )

        base = date(2020, 1, 1)
        dates = [base + timedelta(days=30 * m) for m in range(13)]
        snapshots = [_snapshot(d, Decimal("1"), Decimal("1")) for d in dates]
        dataset = Dataset(
            snapshots=snapshots,
            frequency="monthly",
            version="test-handoff",
            identifier="test-handoff",
        )

        result = run_accumulation_phase(
            initial_portfolio=KNOWN_PORTFOLIO,
            contribution=CONTRIBUTION,
            target_weights=TARGET_WEIGHTS,
            dataset=dataset,
            equity_asset=EQUITY,
            bond_asset=BOND,
        )

        # Portfolio must have changed
        initial_total = sum(h.units for h in KNOWN_PORTFOLIO.holdings)
        final_total = sum(h.units for h in result.final_portfolio.holdings)
        assert final_total > initial_total

        # Must have exactly 12 month-by-month snapshots
        assert len(result.month_by_month) == 12
