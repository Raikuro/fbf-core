"""Published-ERN fixture and dataset-injection tests."""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal

from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.study import StudyConfiguration, build_study_plan
from fbf.core.study.internal.cohort.generator import CohortGenerator
from tests.support.ern.constants import ORACLE_CSV
from tests.support.ern.published_dataset import (
    PUBLISHED_DATA_DIR,
    PUBLISHED_EQUITY_FORWARD_ANNUAL,
    PUBLISHED_PROJECTION_END,
    load_published_ern_dataset,
)
from tools.ern import reference_oracle


def _snapshot(dataset: Dataset, iso_date: str) -> MarketSnapshot:
    for snapshot in dataset.snapshots:
        if snapshot.date.isoformat() == iso_date:
            return snapshot
    raise AssertionError(f"No snapshot for {iso_date}")


def _level(snapshot: MarketSnapshot, asset_id: str) -> Decimal:
    for asset_class, level in snapshot.index_levels.items():
        if asset_class.id == asset_id:
            return level
    raise AssertionError(f"No level for {asset_id}")


def _monthly(annual: Decimal) -> Decimal:
    return (Decimal("1") + annual) ** (Decimal("1") / Decimal("12")) - Decimal("1")


def test_published_dataset_shape_and_cohorts() -> None:
    dataset = load_published_ern_dataset()
    assert len(dataset.snapshots) == 2459
    assert dataset.snapshots[0].date == date(1871, 1, 31)
    assert dataset.snapshots[-1].date == date(2075, 11, 1)
    assert len(CohortGenerator.generate_rolling_monthly(dataset, 721)) == 1739


def test_published_projection_boundary() -> None:
    dataset = load_published_ern_dataset()

    sep_2016 = _snapshot(dataset, "2016-09-01")
    oct_2016 = _snapshot(dataset, "2016-10-01")
    nov_2016 = _snapshot(dataset, "2016-11-01")
    aug_2026 = _snapshot(dataset, "2026-08-01")
    sep_2026 = _snapshot(dataset, "2026-09-01")
    oct_2026 = _snapshot(dataset, "2026-10-01")

    assert _level(oct_2016, "equity") / _level(sep_2016, "equity") - 1 == _monthly(
        PUBLISHED_EQUITY_FORWARD_ANNUAL
    )
    assert _level(oct_2016, "bond") == _level(sep_2016, "bond")
    assert _level(nov_2016, "bond") == _level(oct_2016, "bond")
    assert _level(sep_2026, "bond") == _level(aug_2026, "bond")
    assert _level(oct_2026, "bond") / _level(sep_2026, "bond") - 1 == _monthly(
        Decimal("0.026")
    )
    assert _level(oct_2016, "equity") > _level(sep_2016, "equity")
    assert _level(oct_2026, "equity") > _level(sep_2026, "equity")
    assert _snapshot(dataset, "2016-10-01").date < PUBLISHED_PROJECTION_END.date()


def test_reference_oracle_regenerates_pinned_published_table() -> None:
    rows = reference_oracle.build_oracle_table(PUBLISHED_DATA_DIR)
    with open(ORACLE_CSV, newline="", encoding="utf-8") as f:
        pinned = list(csv.reader(f))
    assert [[str(value) for value in row] for row in rows] == pinned


def test_build_study_plan_uses_injected_dataset() -> None:
    dataset = load_published_ern_dataset()
    config = StudyConfiguration(
        name="injection",
        description="",
        version="",
        allocation_policy_type="ConstantAllocationPolicy",
        allocation_policy_values=(Decimal("0.5"),),
        withdrawal_policy_type="FixedRealWithdrawalPolicy",
        withdrawal_policy_values=(Decimal("0.04"),),
        horizon_years=(30,),
        cohort_horizon_years=60,
    )
    built = build_study_plan(
        config,
        "unused-data-dir",
        Money(Decimal("1000000"), Currency.EUR),
        dataset=dataset,
    )
    assert built.experiment_definition.dataset is dataset
    assert len(built.plan.units) == 1739
