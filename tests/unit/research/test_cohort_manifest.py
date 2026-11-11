from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from fbf.core.datasets.ern import PreparedDatasetMetadata
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.research.cohort_manifest import build_effective_manifest
from fbf.core.research.part3_planner import (
    CohortManifest,
    Part3PlannerConfig,
    materialize_part3_plan,
)
from fbf.core.study import CohortSpecification

_ASSET = AssetClass(id="equity", name="Equity", description="")
_CUTOFF = date(2000, 3, 1)
_CAPE_ROWS = (
    ("2000-01-01", Decimal("10")),
    ("2000-02-01", Decimal("20")),
    ("2000-03-01", Decimal("30")),
)


def _add_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _dataset(start: date, count: int) -> Dataset:
    snapshots = tuple(
        MarketSnapshot(
            date=_add_months(start, offset),
            index_levels={_ASSET: Decimal("100")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("0"),
            is_ath=True,
            is_underwater=False,
            running_ath=Decimal("100"),
        )
        for offset in range(count)
    )
    return Dataset(snapshots=snapshots, frequency="monthly")


def _metadata(dataset: Dataset) -> PreparedDatasetMetadata:
    return PreparedDatasetMetadata(
        historical_data_cutoff=_CUTOFF,
        projection_start=_add_months(_CUTOFF, 1),
        projection_end=dataset.end_date,
        historical_snapshot_count=3,
        projected_snapshot_count=len(dataset) - 3,
        snapshot_count=len(dataset),
        phase_months=120,
        equity_annual=Decimal("0.04"),
        equity_annual_after=Decimal("0.055"),
        bond_annual=Decimal("0.025"),
        bond_annual_after=Decimal("0.0225"),
        inflation_mode="zero",
        inflation_annual_rate=Decimal("0"),
        ffr_policy="last_observed_at_cutoff",
        ffr_constant_rate=None,
        legacy_mode=False,
    )


def _manifest(*, require_cape: bool) -> CohortManifest:
    dataset = _dataset(date(2000, 1, 1), 24)
    return build_effective_manifest(
        dataset=dataset,
        metadata=_metadata(dataset),
        cape_rows=_CAPE_ROWS,
        cohort_start=date(2000, 2, 1),
        cohort_end=date(2000, 6, 1),
        require_cape=require_cape,
    )


def test_cape_independent_manifest_allows_post_cutoff_cohorts() -> None:
    manifest = _manifest(require_cape=False)
    entries = {entry.cohort_date: entry for entry in manifest.cohorts}

    assert len(manifest.cohorts) == 5
    assert entries["2000-03-01"].cape_available is True
    assert entries["2000-04-01"].cape_available is False
    assert entries["2000-04-01"].cape_value is None
    assert entries["2000-04-01"].start_month_index == 2
    assert entries["2000-04-01"].max_horizon_months == 21


def test_cape_independent_part3_plan_accepts_post_cutoff_cohorts() -> None:
    dataset = _dataset(date(2000, 1, 1), 24)
    manifest = build_effective_manifest(
        dataset=dataset,
        metadata=_metadata(dataset),
        cape_rows=_CAPE_ROWS,
        cohort_start=date(2000, 2, 1),
        cohort_end=date(2000, 6, 1),
        require_cape=False,
    )
    config = Part3PlannerConfig(
        equity_allocations=(Decimal("1"),),
        withdrawal_rates=(Decimal("0.04"),),
        horizon_years=(1,),
        final_value_targets=None,
        allocation_policy_type="ConstantAllocationPolicy",
        withdrawal_policy_type="FixedRealWithdrawalPolicy",
    )

    result = materialize_part3_plan(
        manifest=manifest,
        canonical_trajectory=dataset,
        config=config,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
    )

    assert len(result.cohorts) == 5
    assert len(result.plan.units) == 5
    assert result.get_cape_metadata(
        CohortSpecification(start_date=date(2000, 4, 1))
    ) == (None, None)


def test_cape_dependent_manifest_rejects_post_cutoff_cohorts() -> None:
    with pytest.raises(ValueError, match="CAPE conditioning"):
        _manifest(require_cape=True)
