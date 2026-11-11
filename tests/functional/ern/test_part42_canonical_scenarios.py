"""Canonical Part 42 fixed-SWR inventory E2E.

The inventory is the ten scenarios returned by
:func:`fbf.core.research.part42_pipeline.get_experiment_configs`, executed through
the production ``run_fixed_swr`` research path on the frozen canonical dataset.

This E2E validates:

* the exact canonical scenario inventory and configuration matrix;
* the actual executed cohort population and unit count, not the requested
  ``cohort_dates`` argument (which ``run_fixed_swr`` does not use as a filter);
* every plan unit's handoff date, retirement horizon, policies, withdrawal base,
  final-value target, and Social Security schedule;
* every cohort against an independent Decimal recurrence, including exact
  success/failure, exact failure month, and final wealth within $0.01;
* the directional improvement relationships between scenarios.

Failsafe search and the retired published-table audit are deliberately outside
this E2E.  The 30Y + Social Security rejection contract remains covered by the
focused integration tests.

The workload is gated by ``RUN_ERN_E2E=1`` through the centralized skip hook in
``tests/conftest.py``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from fbf.core.datasets import load_canonical_dataset
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import Portfolio
from fbf.core.domain.policies.concrete import (
    ConstantAllocationPolicy,
    FixedRealWithdrawalPolicy,
)
from fbf.core.execution import ExecutionOptions, execute_study_plan
from fbf.core.execution.result import ResearchExecutionResult
from fbf.core.research import part42_pipeline
from fbf.core.research.part42_pipeline import (
    Part42ExperimentConfig,
    Part42FixedSWRResult,
    get_experiment_configs,
    run_fixed_swr,
)
from fbf.core.study.builder import BuiltStudy
from tests.support.ern.constants import DATA_DIR
from tests.support.ern.part42_recurrence import (
    Part42RecurrenceResult,
    simulate_part42_cohort,
)

INITIAL_WEALTH = Decimal("2000000")
EQUITY_WEIGHT = Decimal("0.75")
BOND_WEIGHT = Decimal("0.25")
WITHDRAWAL_RATE = Decimal("0.04")
CONTRIBUTION = Decimal("5000")
SS_AMOUNT = Decimal("3000")
SS_START_YEAR = 31
SS_PAYMENTS = 240
EXPECTED_TOTAL_UNITS = 19310


@dataclass(frozen=True)
class ScenarioExpectation:
    experiment_id: str
    cohort_count: int
    total_snapshots: int
    accumulation_snapshots: int
    omy_months: int
    contribution: Decimal
    final_value_target: Decimal
    social_security: bool
    ss_start_period: int | None = None
    ss_end_period: int | None = None

    @property
    def horizon_months(self) -> int:
        return self.total_snapshots - self.omy_months


@dataclass(frozen=True)
class ScenarioRun:
    summary: Part42FixedSWRResult
    execution: ResearchExecutionResult


@dataclass(frozen=True)
class CanonicalInventory:
    dataset: Dataset
    date_index: dict[date, int]
    runs: dict[str, ScenarioRun]
    oracle: dict[str, dict[date, Part42RecurrenceResult]]
    execution_time_s: float


EXPECTATIONS: tuple[ScenarioExpectation, ...] = (
    ScenarioExpectation("A", 2099, 361, 1, 0, Decimal("0"), Decimal("0.25"), False),
    ScenarioExpectation("B", 2099, 361, 13, 12, Decimal("0"), Decimal("0.25"), False),
    ScenarioExpectation("C", 2099, 361, 13, 12, CONTRIBUTION, Decimal("0.25"), False),
    ScenarioExpectation("D", 1859, 601, 1, 0, Decimal("0"), Decimal("0"), False),
    ScenarioExpectation("E_delay", 1859, 601, 13, 12, Decimal("0"), Decimal("0"), False),
    ScenarioExpectation(
        "E_contrib", 1859, 601, 13, 12, CONTRIBUTION, Decimal("0"), False
    ),
    ScenarioExpectation(
        "F_baseline", 1859, 601, 1, 0, Decimal("0"), Decimal("0"), True, 360, 600
    ),
    ScenarioExpectation(
        "F_delay", 1859, 601, 13, 12, Decimal("0"), Decimal("0"), True, 348, 588
    ),
    ScenarioExpectation(
        "F_contrib", 1859, 601, 13, 12, CONTRIBUTION, Decimal("0"), True, 348, 588
    ),
    ScenarioExpectation(
        "G_2yr", 1859, 601, 25, 24, CONTRIBUTION, Decimal("0"), True, 336, 576
    ),
)

CONFIGS_BY_ID = {config.id: config for config in get_experiment_configs()}


def _value(portfolio: Portfolio, snapshot: MarketSnapshot) -> Decimal:
    return sum(
        (
            holding.units * snapshot.index_levels[holding.asset_class]
            for holding in portfolio.holdings
        ),
        Decimal("0"),
    )


def _assert_config(expectation: ScenarioExpectation) -> None:
    config = CONFIGS_BY_ID[expectation.experiment_id]
    assert config.id == expectation.experiment_id
    assert config.horizon_years == (expectation.total_snapshots - 1) // 12
    assert config.omy is (expectation.omy_months > 0)
    assert config.omy_duration_months == (expectation.omy_months or 12)
    assert config.omy_contribution.amount == expectation.contribution
    assert config.fixed_swr == WITHDRAWAL_RATE
    assert config.fv_target == expectation.final_value_target
    assert config.social_security is expectation.social_security
    assert config.ss_start_year == SS_START_YEAR
    assert config.ss_amount == Money(SS_AMOUNT, Currency.EUR)


def _simulate(
    dataset: Dataset,
    date_index: dict[date, int],
    unit: object,
    expectation: ScenarioExpectation,
) -> Part42RecurrenceResult:
    from fbf.core.study.plan import PlannedSimulationUnit

    assert isinstance(unit, PlannedSimulationUnit)
    return simulate_part42_cohort(
        dataset,
        cohort_index=date_index[unit.cohort.start_date],
        total_horizon_months=expectation.total_snapshots - 1,
        omy_months=expectation.omy_months,
        contribution_monthly=expectation.contribution,
        initial_wealth=INITIAL_WEALTH,
        withdrawal_rate=WITHDRAWAL_RATE,
        equity_weight=EQUITY_WEIGHT,
        bond_weight=BOND_WEIGHT,
        final_value_target=expectation.final_value_target,
        social_security=expectation.social_security,
        ss_start_year=SS_START_YEAR,
        ss_monthly_amount=SS_AMOUNT,
    )


@pytest.fixture(scope="session")
def canonical_inventory() -> CanonicalInventory:
    dataset = load_canonical_dataset(Path(DATA_DIR))
    date_index = {
        snapshot.date: index for index, snapshot in enumerate(dataset.snapshots)
    }
    runs: dict[str, ScenarioRun] = {}
    oracle: dict[str, dict[date, Part42RecurrenceResult]] = {}
    real_execute = execute_study_plan
    captured: list[ResearchExecutionResult] = []

    def capture(built: BuiltStudy, options: ExecutionOptions) -> ResearchExecutionResult:
        result = real_execute(built, options)
        captured.append(result)
        return result

    start = time.perf_counter()
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(part42_pipeline, "execute_study_plan", capture)
        for expectation in EXPECTATIONS:
            config: Part42ExperimentConfig = CONFIGS_BY_ID[expectation.experiment_id]
            summary = run_fixed_swr(
                config,
                cohort_dates=(),
                data_dir=str(DATA_DIR),
                options=ExecutionOptions(summary_only=True),
            )
            assert len(captured) == 1
            execution = captured.pop()
            runs[expectation.experiment_id] = ScenarioRun(summary, execution)
            oracle[expectation.experiment_id] = {
                unit.cohort.start_date: _simulate(
                    dataset, date_index, unit, expectation
                )
                for unit in execution.plan.units
            }
    elapsed = time.perf_counter() - start
    return CanonicalInventory(dataset, date_index, runs, oracle, elapsed)


@pytest.mark.ern_e2e
def test_part42_canonical_inventory_ids_and_configuration() -> None:
    configs = get_experiment_configs()
    assert [config.id for config in configs] == [
        expectation.experiment_id for expectation in EXPECTATIONS
    ]
    assert len(configs) == len(EXPECTATIONS) == 10
    assert not any(
        config.horizon_years == 30 and config.omy_duration_months == 24
        for config in configs
    )
    for expectation in EXPECTATIONS:
        _assert_config(expectation)


@pytest.mark.ern_e2e
def test_part42_canonical_executed_population_and_plan_contract(
    canonical_inventory: CanonicalInventory,
) -> None:
    dataset = canonical_inventory.dataset
    date_index = canonical_inventory.date_index
    total_units = 0
    for expectation in EXPECTATIONS:
        run = canonical_inventory.runs[expectation.experiment_id]
        units = run.execution.plan.units
        results = run.execution.results
        total_units += len(units)

        expected_dates = tuple(
            snapshot.date
            for snapshot in dataset.snapshots[
                : len(dataset.snapshots) - expectation.total_snapshots + 1
            ]
        )
        assert len(units) == expectation.cohort_count
        assert len(results) == expectation.cohort_count
        assert run.summary.cohort_count == expectation.cohort_count
        assert (
            len(run.execution.plan.experiment_definition.cohorts)
            == expectation.cohort_count
        )
        assert tuple(unit.cohort.start_date for unit in units) == expected_dates

        for unit in units:
            start_index = date_index[unit.cohort.start_date]
            retirement_index = start_index + expectation.omy_months
            assert (
                unit.dataset.snapshots[0].date
                == dataset.snapshots[retirement_index].date
            )
            assert len(unit.dataset) == expectation.horizon_months
            assert unit.horizon_months == expectation.horizon_months
            assert unit.final_value_target == expectation.final_value_target

            assert isinstance(unit.allocation_policy, ConstantAllocationPolicy)
            assert unit.allocation_policy.equity_allocation == EQUITY_WEIGHT
            assert isinstance(unit.withdrawal_policy, FixedRealWithdrawalPolicy)
            assert unit.withdrawal_policy.withdrawal_rate == WITHDRAWAL_RATE

            effective_base = (
                unit.withdrawal_base.amount
                if unit.withdrawal_base is not None
                else _value(unit.initial_portfolio, unit.dataset[0])
            )
            assert abs(effective_base - INITIAL_WEALTH) < Decimal("0.01")

            schedule = unit.external_cash_flow_schedule
            if not expectation.social_security:
                assert schedule is None
                continue
            assert schedule is not None
            assert schedule.start_period == expectation.ss_start_period
            assert schedule.end_period == expectation.ss_end_period
            assert schedule.end_period - schedule.start_period == SS_PAYMENTS
            assert schedule.horizon_transitions == expectation.horizon_months - 1
            assert schedule.monthly_amount == Money(SS_AMOUNT, Currency.EUR)

    assert total_units == EXPECTED_TOTAL_UNITS


@pytest.mark.ern_e2e
def test_part42_canonical_independent_recurrence_matches_every_cohort(
    canonical_inventory: CanonicalInventory,
) -> None:
    for expectation in EXPECTATIONS:
        run = canonical_inventory.runs[expectation.experiment_id]
        oracle = canonical_inventory.oracle[expectation.experiment_id]
        for unit, result in zip(
            run.execution.plan.units, run.execution.results, strict=True
        ):
            expected = oracle[unit.cohort.start_date]
            production_handoff = _value(unit.initial_portfolio, unit.dataset[0])
            assert abs(production_handoff - expected.handoff_wealth) < Decimal("0.01")

            statistics = result.statistics
            assert statistics.success is expected.success
            assert statistics.failure_month == expected.failure_month
            assert abs(statistics.final_wealth.amount - expected.final_wealth) < Decimal(
                "0.01"
            )

            if expectation.social_security:
                if expected.failure_month is None:
                    assert expected.ss_payments_applied == SS_PAYMENTS
            else:
                assert expected.ss_payments_applied == 0

        assert run.summary.per_cohort_success == tuple(
            result.statistics.success for result in run.execution.results
        )
        assert run.summary.failures == sum(
            1 for result in run.execution.results if not result.statistics.success
        )


@pytest.mark.ern_e2e
def test_part42_canonical_directional_success_invariants(
    canonical_inventory: CanonicalInventory,
) -> None:
    successes: dict[str, dict[date, bool]] = {}
    for expectation in EXPECTATIONS:
        run = canonical_inventory.runs[expectation.experiment_id]
        successes[expectation.experiment_id] = {
            unit.cohort.start_date: result.statistics.success
            for unit, result in zip(
                run.execution.plan.units, run.execution.results, strict=True
            )
        }

    relationships = (
        ("C", "B"),
        ("E_contrib", "E_delay"),
        ("F_contrib", "F_delay"),
        ("F_baseline", "D"),
        ("F_delay", "E_delay"),
        ("F_contrib", "E_contrib"),
    )
    for stronger, weaker in relationships:
        stronger_successes = successes[stronger]
        weaker_successes = successes[weaker]
        assert sum(stronger_successes.values()) >= sum(weaker_successes.values())
        for cohort_date, weaker_success in weaker_successes.items():
            if weaker_success:
                assert stronger_successes[cohort_date]

    for expectation in EXPECTATIONS:
        count = len(successes[expectation.experiment_id])
        assert 0 < count == expectation.cohort_count
        assert 0 < sum(successes[expectation.experiment_id].values()) < count
