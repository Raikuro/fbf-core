"""Part 42 fixed-horizon timeline integration coverage."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest

from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.money import Currency, Money
from fbf.core.execution import ExecutionOptions, UnsupportedConfigurationError
from fbf.core.research.part42_pipeline import (
    Part42ExperimentConfig,
    _build_omy_evaluate,
    run_failsafe_search,
    run_fixed_swr,
)
from fbf.core.study.builder import BuiltStudy, StudyConfiguration
from tests.fixtures.accumulation import _snapshot


def _flat_dataset(num_snapshots: int) -> Dataset:
    base = date(1871, 1, 1)
    snapshots = [
        _snapshot(base + timedelta(days=30 * m), Decimal("1"), Decimal("1"))
        for m in range(num_snapshots)
    ]
    return Dataset(snapshots=snapshots, frequency="monthly")


def _base_config(*, horizon_years: int) -> StudyConfiguration:
    return StudyConfiguration(
        name="test-part42",
        description="test",
        version="1.0",
        allocation_policy_type="ConstantAllocationPolicy",
        allocation_policy_values=(Decimal("0.75"),),
        withdrawal_policy_type="FixedRealWithdrawalPolicy",
        withdrawal_policy_values=(Decimal("0.04"),),
        horizon_years=(horizon_years,),
    )


def _experiment(
    *,
    horizon_years: int,
    omy_duration_months: int,
    social_security: bool = False,
) -> Part42ExperimentConfig:
    return Part42ExperimentConfig(
        id="test",
        name="test",
        horizon_years=horizon_years,
        omy=True,
        omy_contribution=Money(Decimal("5000"), Currency.EUR),
        omy_duration_months=omy_duration_months,
        social_security=social_security,
        fixed_swr=Decimal("0.04"),
    )


def _build(
    monkeypatch: pytest.MonkeyPatch,
    *,
    horizon_years: int,
    omy_duration_months: int,
) -> BuiltStudy:
    from fbf.core.research.part42_plan import build_part42_study_plan

    dataset = _flat_dataset(2459)
    monkeypatch.setattr(
        "fbf.core.research.part42_plan.load_canonical_dataset",
        lambda _p: dataset,
    )
    return build_part42_study_plan(
        experiment_id="test",
        base_config=_base_config(horizon_years=horizon_years),
        data_dir="unused",
        omy_config=_experiment(
            horizon_years=horizon_years,
            omy_duration_months=omy_duration_months,
        ),
    )


def test_part42_30y_12m_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    built = _build(monkeypatch, horizon_years=30, omy_duration_months=12)
    assert len(built.cohorts) == 2099
    unit = built.plan.units[0]
    assert unit.horizon_months == 349
    assert len(unit.dataset) == 349
    assert unit.dataset.snapshots[0].date == unit.cohort.start_date + timedelta(days=30 * 12)
    assert unit.withdrawal_base == Money(Decimal("2000000"), Currency.EUR)


def test_part42_50y_24m_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    built = _build(monkeypatch, horizon_years=50, omy_duration_months=24)
    assert len(built.cohorts) == 1859
    unit = built.plan.units[0]
    assert unit.horizon_months == 577
    assert len(unit.dataset) == 577
    assert unit.dataset.snapshots[0].date == unit.cohort.start_date + timedelta(days=30 * 24)


def test_part42_fixed_swr_rejects_social_security() -> None:
    experiment = _experiment(
        horizon_years=30,
        omy_duration_months=12,
        social_security=True,
    )
    with pytest.raises(UnsupportedConfigurationError, match="Social Security"):
        run_fixed_swr(
            experiment,
            cohort_dates=(),
            data_dir="unused",
            options=ExecutionOptions(summary_only=True),
        )


def test_part42_failsafe_rejects_social_security() -> None:
    experiment = _experiment(
        horizon_years=30,
        omy_duration_months=12,
        social_security=True,
    )
    with pytest.raises(UnsupportedConfigurationError, match="Social Security"):
        run_failsafe_search(
            cast(Any, None),
            experiment,
            cohort_dates=("1871-01-01",),
            options=ExecutionOptions(summary_only=True),
        )


def test_part42_omy_evaluate_rejects_social_security() -> None:
    experiment = _experiment(
        horizon_years=30,
        omy_duration_months=12,
        social_security=True,
    )
    with pytest.raises(UnsupportedConfigurationError, match="Social Security"):
        _build_omy_evaluate(
            cast(Any, None),
            experiment,
            cohort_dates=(),
            options=ExecutionOptions(summary_only=True),
        )


def test_part42_plan_rejects_social_security() -> None:
    from fbf.core.research.part42_plan import build_part42_study_plan

    with pytest.raises(UnsupportedConfigurationError, match="Social Security"):
        build_part42_study_plan(
            experiment_id="test",
            base_config=_base_config(horizon_years=30),
            data_dir="unused",
            omy_config=_experiment(
                horizon_years=30,
                omy_duration_months=12,
                social_security=True,
            ),
        )
