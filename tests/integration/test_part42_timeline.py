"""Part 42 fixed-horizon timeline integration coverage."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
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


def _growing_dataset(num_snapshots: int) -> Dataset:
    base = date(1871, 1, 1)
    equity = Decimal("100")
    bond = Decimal("100")
    snapshots = []
    for month in range(num_snapshots):
        snapshots.append(
            _snapshot(base + timedelta(days=30 * month), equity, bond)
        )
        equity *= Decimal("1.006")
        bond *= Decimal("1.002")
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
    omy: bool = True,
) -> Part42ExperimentConfig:
    return Part42ExperimentConfig(
        id="test",
        name="test",
        horizon_years=horizon_years,
        omy=omy,
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
    omy: bool = True,
    social_security: bool = False,
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
            omy=omy,
            social_security=social_security,
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


def test_part42_30y_no_omy_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    built = _build(
        monkeypatch,
        horizon_years=30,
        omy_duration_months=12,
        omy=False,
    )
    assert len(built.cohorts) == 2099
    unit = built.plan.units[0]
    assert unit.horizon_months == 361
    assert len(unit.dataset) == 361
    assert unit.dataset.snapshots[0].date == unit.cohort.start_date
    assert unit.withdrawal_base == Money(Decimal("2000000"), Currency.EUR)


def test_part42_50y_24m_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    built = _build(monkeypatch, horizon_years=50, omy_duration_months=24)
    assert len(built.cohorts) == 1859
    unit = built.plan.units[0]
    assert unit.horizon_months == 577
    assert len(unit.dataset) == 577
    assert unit.dataset.snapshots[0].date == unit.cohort.start_date + timedelta(days=30 * 24)


def test_part42_plan_attaches_social_security_schedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = _build(
        monkeypatch,
        horizon_years=50,
        omy_duration_months=12,
        social_security=True,
    )
    unit = built.plan.units[0]
    schedule = unit.external_cash_flow_schedule
    assert schedule is not None
    assert schedule.start_period == 348
    assert schedule.end_period == 588
    assert schedule.horizon_transitions == 588
    assert schedule.monthly_amount == Money(Decimal("3000"), Currency.EUR)


@pytest.mark.parametrize(
    ("omy", "omy_duration_months"), [(False, 12), (True, 12), (True, 24)]
)
def test_part42_30y_social_security_is_rejected(
    omy: bool,
    omy_duration_months: int,
) -> None:
    from fbf.core.research.part42_plan import build_part42_study_plan

    with pytest.raises(UnsupportedConfigurationError, match="Social Security"):
        build_part42_study_plan(
            experiment_id="test",
            base_config=_base_config(horizon_years=30),
            data_dir="unused",
            omy_config=_experiment(
                horizon_years=30,
                omy_duration_months=omy_duration_months,
                social_security=True,
                omy=omy,
            ),
        )


def test_part42_fixed_swr_rejects_social_security_for_30y() -> None:
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


def test_part42_failsafe_rejects_social_security_for_30y() -> None:
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


def test_part42_omy_evaluate_rejects_social_security_for_30y() -> None:
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


def test_fixed_swr_uses_schedule_aware_builder_for_social_security(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fbf.core.research import part42_pipeline

    experiment = _experiment(
        horizon_years=50,
        omy_duration_months=12,
        social_security=True,
        omy=False,
    )
    captured: list[dict[str, Any]] = []

    def fake_build(**kwargs: Any) -> Any:
        captured.append(kwargs)
        return SimpleNamespace(plan=None)

    def fake_execute(_built: Any, _options: ExecutionOptions) -> Any:
        return SimpleNamespace(
            experiment_result=SimpleNamespace(simulation_results=())
        )

    monkeypatch.setattr(part42_pipeline, "build_part42_study_plan", fake_build)
    monkeypatch.setattr(part42_pipeline, "execute_study_plan", fake_execute)

    result = run_fixed_swr(
        experiment,
        cohort_dates=("1871-01-01",),
        data_dir="unused",
        options=ExecutionOptions(summary_only=True),
    )

    assert result.social_security is True
    assert len(captured) == 1
    assert captured[0]["omy_config"] is experiment
    assert captured[0]["data_dir"] == "unused"


def test_failsafe_evaluation_uses_schedule_aware_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fbf.core.research import part42_pipeline

    dataset = _flat_dataset(601)
    ctx = SimpleNamespace(
        trajectory=dataset,
        initial_wealth=Money(Decimal("2000000"), Currency.EUR),
    )
    experiment = _experiment(
        horizon_years=50,
        omy_duration_months=12,
        social_security=True,
        omy=False,
    )
    captured: list[dict[str, Any]] = []

    def fake_build(**kwargs: Any) -> Any:
        captured.append(kwargs)
        return SimpleNamespace(plan=None)

    def fake_execute(_built: Any, _options: ExecutionOptions) -> Any:
        return SimpleNamespace(
            experiment_result=SimpleNamespace(
                simulation_results=(SimpleNamespace(statistics=SimpleNamespace(success=True)),)
            )
        )

    monkeypatch.setattr(part42_pipeline, "build_part42_study_plan", fake_build)
    monkeypatch.setattr("fbf.core.execution.execute_study_plan", fake_execute)

    evaluate = _build_omy_evaluate(
        cast(Any, ctx),
        experiment,
        cohort_dates=("1871-01-01",),
        options=ExecutionOptions(summary_only=True),
    )

    assert evaluate([(0, Decimal("0.04"))]) == (True,)
    assert len(captured) == 1
    assert captured[0]["omy_config"] is experiment
    assert captured[0]["dataset"] is dataset


def test_fixed_swr_social_security_executes_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset = _growing_dataset(601)
    monkeypatch.setattr(
        "fbf.core.research.part42_plan.load_canonical_dataset",
        lambda _path: dataset,
    )
    experiment = _experiment(
        horizon_years=50,
        omy_duration_months=12,
        social_security=True,
        omy=False,
    )

    result = run_fixed_swr(
        experiment,
        cohort_dates=("1871-01-01",),
        data_dir="unused",
        options=ExecutionOptions(summary_only=True),
    )

    assert result.cohort_count == 1
    assert result.per_cohort_success == (True,)


def test_failsafe_social_security_executes_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset = _growing_dataset(601)
    ctx = SimpleNamespace(
        trajectory=dataset,
        initial_wealth=Money(Decimal("2000000"), Currency.EUR),
    )
    experiment = _experiment(
        horizon_years=50,
        omy_duration_months=12,
        social_security=True,
        omy=False,
    )

    result = run_failsafe_search(
        cast(Any, ctx),
        experiment,
        cohort_dates=("1871-01-01",),
        options=ExecutionOptions(summary_only=True),
    )

    assert result.cohort_count == 1
    assert len(result.per_cohort_swrs) == 1
    assert result.per_cohort_swrs[0] >= Decimal("0")


def test_part42_social_security_autoselects_numba_and_materializes_flows() -> None:
    from fbf.core.execution import execute_study_plan
    from fbf.core.research.part42_plan import build_part42_study_plan

    dataset = _growing_dataset(601)
    built = build_part42_study_plan(
        experiment_id="test",
        base_config=_base_config(horizon_years=50),
        data_dir=None,
        omy_config=_experiment(
            horizon_years=50,
            omy_duration_months=12,
            social_security=True,
            omy=False,
        ),
        dataset=dataset,
    )

    result = execute_study_plan(
        built, ExecutionOptions(materialize_timeline=True)
    )
    timeline = result.experiment_result.simulation_results[0].timeline.monthly_results

    assert len(timeline) == 601
    assert timeline[0].net_cash_flow == Money(Decimal("0"), Currency.EUR)
    assert timeline[360].net_cash_flow is not None
    assert timeline[361].net_cash_flow is not None
    assert (
        timeline[360].net_cash_flow.amount
        - timeline[361].net_cash_flow.amount
        == Decimal("3000")
    )
