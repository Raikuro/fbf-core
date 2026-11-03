"""Integration coverage for explicit cohort-date configuration."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fbf.core.domain.model.money import Currency, Money
from fbf.core.study import StudyConfiguration, build_study_plan


def _config(*, start_date: date | None = None, end_date: date | None = None) -> StudyConfiguration:
    return StudyConfiguration(
        name="cohort-date-integration",
        description="",
        version="1.0",
        allocation_policy_type="ConstantAllocationPolicy",
        allocation_policy_values=(Decimal("0.75"),),
        withdrawal_policy_type="FixedRealWithdrawalPolicy",
        withdrawal_policy_values=(Decimal("0.04"),),
        horizon_years=(30,),
        cohort_horizon_years=60,
        cohort_start_date=start_date,
        cohort_end_date=end_date,
        expense_ratio=Decimal("0.0005"),
    )


def test_default_production_cohort_universe_remains_1739() -> None:
    built = build_study_plan(
        _config(),
        "data/ern",
        Money(Decimal("1000000"), Currency.EUR),
    )

    assert len(built.cohorts) == 1739
    assert built.cohorts[0].start_date == date(1871, 1, 31)
    assert built.cohorts[-1].start_date == date(2015, 11, 1)
    assert len(built.plan.units) == 1739


def test_explicit_range_selects_1925_through_1990_cohorts() -> None:
    built = build_study_plan(
        _config(start_date=date(1925, 1, 1), end_date=date(1990, 12, 1)),
        "data/ern",
        Money(Decimal("1000000"), Currency.EUR),
    )

    assert len(built.cohorts) == 792
    assert built.cohorts[0].start_date == date(1925, 1, 1)
    assert built.cohorts[-1].start_date == date(1990, 12, 1)
    assert len(built.plan.units) == 792
