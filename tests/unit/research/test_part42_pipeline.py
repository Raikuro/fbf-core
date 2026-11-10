"""Focused unit tests for Part 42 planning caches and context injection."""

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
    Part42ExecutionContext,
    Part42ExperimentConfig,
    _build_omy_evaluate,
    get_experiment_configs,
    run_failsafe_search,
    run_fixed_swr,
)
from fbf.core.study.builder import BuiltStudy, build_initial_portfolio
from tests.fixtures.accumulation import _snapshot

CANONICAL_PART42_EXPERIMENT_IDS = (
    "A",
    "B",
    "C",
    "D",
    "E_delay",
    "E_contrib",
    "F_baseline",
    "F_delay",
    "F_contrib",
    "G_2yr",
)

SOCIAL_SECURITY_EXPERIMENT_IDS = ("F_baseline", "F_delay", "F_contrib", "G_2yr")


def _flat_dataset(num_snapshots: int) -> Dataset:
    base = date(2020, 1, 1)
    snapshots = [
        _snapshot(base + timedelta(days=30 * month), Decimal("1"), Decimal("1"))
        for month in range(num_snapshots)
    ]
    return Dataset(snapshots=snapshots, frequency="monthly")


def _context(
    dataset: Dataset,
    initial_wealth: Money | None = None,
) -> Part42ExecutionContext:
    return Part42ExecutionContext(
        manifest=cast(Any, None),
        trajectory=dataset,
        initial_wealth=(
            initial_wealth
            if initial_wealth is not None
            else Money(Decimal("2000000"), Currency.EUR)
        ),
    )


def _experiment(
    *,
    omy_months: int = 12,
    contribution: str = "5000",
    omy: bool = True,
) -> Part42ExperimentConfig:
    return Part42ExperimentConfig(
        id="test",
        name="test",
        horizon_years=2,
        omy=omy,
        omy_contribution=Money(Decimal(contribution), Currency.EUR),
        omy_duration_months=omy_months,
    )


def test_accumulation_cache_reuses_identical_inputs() -> None:
    ctx = _context(_flat_dataset(40))
    experiment = _experiment()

    first = ctx.accumulation_portfolio("2020-01-01", experiment)
    second = ctx.accumulation_portfolio("2020-01-01", experiment)

    assert second is first


def test_accumulation_cache_distinguishes_omy_duration() -> None:
    ctx = _context(_flat_dataset(40))

    twelve_months = ctx.accumulation_portfolio(
        "2020-01-01", _experiment(omy_months=12)
    )
    twenty_four_months = ctx.accumulation_portfolio(
        "2020-01-01", _experiment(omy_months=24)
    )

    assert twelve_months != twenty_four_months


def test_accumulation_cache_distinguishes_contribution() -> None:
    ctx = _context(_flat_dataset(40))

    no_contribution = ctx.accumulation_portfolio(
        "2020-01-01", _experiment(contribution="0")
    )
    with_contribution = ctx.accumulation_portfolio(
        "2020-01-01", _experiment(contribution="5000")
    )

    assert no_contribution != with_contribution


def test_accumulation_cache_distinguishes_initial_wealth() -> None:
    dataset = _flat_dataset(40)
    low_wealth = _context(dataset, Money(Decimal("1000000"), Currency.EUR))
    high_wealth = _context(dataset, Money(Decimal("2000000"), Currency.EUR))
    experiment = _experiment()

    low_result = low_wealth.accumulation_portfolio("2020-01-01", experiment)
    high_result = high_wealth.accumulation_portfolio("2020-01-01", experiment)

    assert low_result != high_result


def test_accumulation_portfolio_skips_accumulation_when_omy_disabled() -> None:
    ctx = _context(_flat_dataset(40))
    experiment = _experiment(omy=False)
    expected = build_initial_portfolio(
        ctx.initial_wealth,
        ctx.dataset_for("2020-01-01", 1),
    )

    assert ctx.accumulation_portfolio("2020-01-01", experiment) == expected


def test_omy_evaluate_uses_context_dataset_and_wealth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory = _flat_dataset(50)
    wealth = Money(Decimal("1234567"), Currency.EUR)
    ctx = _context(trajectory, wealth)
    experiment = _experiment()
    captured: list[BuiltStudy] = []

    def fail_dataset_load(*_args: Any, **_kwargs: Any) -> Dataset:
        raise AssertionError("failsafe evaluation must not reload the canonical dataset")

    def fake_execute(built: BuiltStudy, _options: ExecutionOptions) -> Any:
        captured.append(built)
        statistics = SimpleNamespace(success=True)
        return SimpleNamespace(
            experiment_result=SimpleNamespace(
                simulation_results=(SimpleNamespace(statistics=statistics),)
            )
        )

    monkeypatch.setattr(
        "fbf.core.research.part42_plan.load_canonical_dataset",
        fail_dataset_load,
    )
    monkeypatch.setattr("fbf.core.execution.execute_study_plan", fake_execute)

    evaluate = _build_omy_evaluate(
        ctx,
        experiment,
        cohort_dates=("2020-01-01",),
        options=ExecutionOptions(summary_only=True),
    )

    assert evaluate([(0, Decimal("0.04"))]) == (True,)

    plan = captured[0].plan
    unit = plan.units[0]
    accumulation_dataset = trajectory.slice(date(2020, 1, 1), 13)
    retirement_start = accumulation_dataset.snapshots[-1].date

    assert plan.experiment_definition.dataset is trajectory
    assert plan.experiment_definition.initial_wealth == wealth
    assert unit.withdrawal_base == wealth
    assert unit.dataset.start_date == retirement_start
    assert len(unit.dataset) == 13


def test_omy_evaluate_disables_accumulation_when_omy_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory = _flat_dataset(50)
    ctx = _context(trajectory)
    experiment = _experiment(omy=False)
    captured: list[BuiltStudy] = []

    def fake_execute(built: BuiltStudy, _options: ExecutionOptions) -> Any:
        captured.append(built)
        statistics = SimpleNamespace(success=True)
        return SimpleNamespace(
            experiment_result=SimpleNamespace(
                simulation_results=(SimpleNamespace(statistics=statistics),)
            )
        )

    monkeypatch.setattr("fbf.core.execution.execute_study_plan", fake_execute)

    evaluate = _build_omy_evaluate(
        ctx,
        experiment,
        cohort_dates=("2020-01-01",),
        options=ExecutionOptions(summary_only=True),
    )

    assert evaluate([(0, Decimal("0.04"))]) == (True,)

    plan = captured[0].plan
    unit = plan.units[0]
    assert plan.experiment_definition.horizon_months == 25
    assert unit.horizon_months == 25
    assert len(unit.dataset) == 25
    assert unit.dataset.snapshots[0].date == unit.cohort.start_date


def test_experiment_inventory_is_canonical() -> None:
    configs = get_experiment_configs()
    ids = tuple(config.id for config in configs)

    assert len(configs) == 10
    assert len(ids) == len(set(ids))
    assert ids == CANONICAL_PART42_EXPERIMENT_IDS
    assert "G" not in ids
    assert {
        config.id for config in configs if config.social_security
    } == set(SOCIAL_SECURITY_EXPERIMENT_IDS)


@pytest.mark.parametrize("experiment_id", SOCIAL_SECURITY_EXPERIMENT_IDS)
def test_social_security_scenarios_fail_closed(experiment_id: str) -> None:
    experiment = next(
        config for config in get_experiment_configs() if config.id == experiment_id
    )

    with pytest.raises(UnsupportedConfigurationError, match="Social Security"):
        run_fixed_swr(
            experiment,
            cohort_dates=(),
            data_dir="unused",
            options=ExecutionOptions(summary_only=True),
        )

    with pytest.raises(UnsupportedConfigurationError, match="Social Security"):
        run_failsafe_search(
            cast(Any, None),
            experiment,
            cohort_dates=("1871-01-01",),
            options=ExecutionOptions(summary_only=True),
        )
