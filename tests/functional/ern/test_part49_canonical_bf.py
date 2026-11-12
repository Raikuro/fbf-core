"""Canonical Part 49 Experiments B-F (buy-and-hold, production dataset).

The module is gated by ``@pytest.mark.ern_e2e`` and ``RUN_ERN_E2E=1``.  It
exercises the production Numba path through :func:`fbf.core.application.run_study`.

Experiments B and C are intentionally dual-mode:

* Mode 1 (observe-only) reproduces the article's portfolio/loan charts.
* Mode 2 (75% LTV enforcement) validates terminal margin-call semantics.

The two modes answer different questions and must not be collapsed into one
result.
"""

from __future__ import annotations

import copy
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from fbf.core.application import run_study
from fbf.core.domain.model.money import Currency, Money
from fbf.core.execution import (
    ExecutionBackend,
    ExecutionOptions,
    ResearchExecutionResult,
)
from fbf.core.execution.pipeline.simulation import MonthlyResult, SimulationResult
from fbf.core.study import StudyConfiguration
from fbf.core.study.internal.cohort.specification import CohortSpecification

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PART49_YAML = _REPO_ROOT / "examples" / "studies" / "ern_part49.yaml"
_DATA_DIR = _REPO_ROOT / "data" / "inputs" / "ern"
_INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)

_ZERO = Decimal("0")
_DIAGNOSTIC_LP_TOLERANCE = Decimal("0.05")
_DIAGNOSTIC_1929_LP_TOLERANCE = Decimal("0.07")


def _config(
    *,
    equity: tuple[Decimal, ...],
    rates: tuple[Decimal, ...],
    withdrawal_rate: Decimal,
    loan_draw_rate: Decimal,
    ltv_enforcement: bool,
) -> StudyConfiguration:
    raw = copy.deepcopy(yaml.safe_load(_PART49_YAML.read_text(encoding="utf-8")))
    raw["allocation_policy"]["type"] = "BuyAndHoldAllocationPolicy"
    raw["allocation_policy"]["equity_allocation"] = list(equity)
    raw["withdrawal_policy"]["withdrawal_rate"] = [withdrawal_rate]
    raw["debt"]["interest_rate"] = list(rates)
    raw["debt"]["ltv_enforcement"] = ltv_enforcement
    raw["debt"]["loan_draw_rate"] = loan_draw_rate
    raw["debt"]["interest_rate_is_real"] = True
    raw["cohorts"]["horizon_years"] = [30]
    raw["cohorts"]["cohort_horizon_years"] = 60
    return StudyConfiguration.from_yaml(raw)


def _run(
    config: StudyConfiguration,
    cohort_filter: Callable[[CohortSpecification], bool],
    *,
    materialize_timeline: bool,
) -> ResearchExecutionResult:
    return run_study(
        config=config,
        data_dir=str(_DATA_DIR),
        initial_wealth=_INITIAL_WEALTH,
        options=ExecutionOptions(
            backend=ExecutionBackend.FAST,
            materialize_timeline=materialize_timeline,
            summary_only=not materialize_timeline,
        ),
        cohort_filter=cohort_filter,
    )


def _single_cohort(
    year: int, month: int
) -> Callable[[CohortSpecification], bool]:
    return lambda cohort: cohort.start_date == date(year, month, 1)


def _portfolio_value(month_result: MonthlyResult) -> Decimal:
    return sum(
        (
            holding.units * month_result.market_snapshot.index_levels[holding.asset_class]
            for holding in month_result.portfolio.holdings
        ),
        _ZERO,
    )


def _find(
    result: ResearchExecutionResult, equity: Decimal, rate: Decimal
) -> SimulationResult:
    for unit, simulation in zip(
        result.plan.units,
        result.experiment_result.simulation_results,
        strict=True,
    ):
        unit_equity = Decimal(str(unit.parameter_config.values["equity_allocation"]))
        unit_rate = Decimal(str(unit.parameter_config.values["interest_rate"]))
        if unit_equity == equity and unit_rate == rate:
            return simulation
    raise AssertionError(f"unit not found: equity={equity}, rate={rate}")


def _first_portfolio_below_loan(simulation: SimulationResult) -> int | None:
    assert simulation.timeline is not None
    for month_index, month in enumerate(simulation.timeline.monthly_results):
        assert month.debt_snapshot is not None
        if month.debt_snapshot.net_worth < _ZERO:
            return month_index
    return None


def _max_ltv(simulation: SimulationResult) -> Decimal:
    assert simulation.timeline is not None
    return max(
        (
            month.debt_snapshot.ltv
            for month in simulation.timeline.monthly_results
            if month.debt_snapshot is not None
        ),
        default=_ZERO,
    )


@pytest.mark.ern_e2e
def test_experiment_b_chart_reproduction_observe_only() -> None:
    """Mode 1: Nov 1965 chart reproduction, no forced liquidation."""
    result = _run(
        _config(
            equity=(Decimal("0.75"), Decimal("1.0")),
            rates=(Decimal("0.015"), Decimal("0.03")),
            withdrawal_rate=Decimal("0"),
            loan_draw_rate=Decimal("0.04"),
            ltv_enforcement=False,
        ),
        _single_cohort(1965, 11),
        materialize_timeline=True,
    )

    for equity in (Decimal("0.75"), Decimal("1.0")):
        for rate in (Decimal("0.015"), Decimal("0.03")):
            simulation = _find(result, equity, rate)
            crossing = _first_portfolio_below_loan(simulation)
            assert crossing is not None
            assert 180 <= crossing <= 200, (
                f"equity={equity} rate={rate}: portfolio<loan at {crossing}, "
                "expected the article's 180-200 window"
            )


@pytest.mark.ern_e2e
def test_experiment_b_enforcement_is_terminal() -> None:
    """Mode 2: 75% LTV enforcement terminates without recovery."""
    result = _run(
        _config(
            equity=(Decimal("0.75"), Decimal("1.0")),
            rates=(Decimal("0.015"), Decimal("0.03")),
            withdrawal_rate=Decimal("0"),
            loan_draw_rate=Decimal("0.04"),
            ltv_enforcement=True,
        ),
        _single_cohort(1965, 11),
        materialize_timeline=False,
    )

    for simulation in result.experiment_result.simulation_results:
        stats = simulation.statistics
        assert stats.success is False
        assert stats.failure_state == "margin_call_terminal"
        assert stats.failure_month is not None
        assert stats.months_simulated <= stats.failure_month + 1


@pytest.mark.ern_e2e
def test_experiment_c_chart_reproduction_observe_only() -> None:
    """Mode 1: Sep 1929 chart reproduction, no forced liquidation."""
    result = _run(
        _config(
            equity=(Decimal("0.75"), Decimal("1.0")),
            rates=(Decimal("0.015"), Decimal("0.03")),
            withdrawal_rate=Decimal("0"),
            loan_draw_rate=Decimal("0.04"),
            ltv_enforcement=False,
        ),
        _single_cohort(1929, 9),
        materialize_timeline=True,
    )

    anchor = _find(result, Decimal("0.75"), Decimal("0.03"))
    assert anchor.timeline is not None
    month_238 = anchor.timeline.monthly_results[238]
    assert month_238.debt_snapshot is not None
    portfolio = _portfolio_value(month_238)
    loan = month_238.debt_snapshot.loan_balance
    net_worth = portfolio - loan

    assert abs(portfolio - Decimal("1185000")) / Decimal("1185000") <= Decimal("0.05")
    assert abs(loan - Decimal("1085000")) / Decimal("1085000") <= Decimal("0.05")
    assert net_worth >= 0
    assert abs(net_worth - Decimal("100000")) <= Decimal("75000")

    one_and_half = _find(result, Decimal("0.75"), Decimal("0.015"))
    assert one_and_half.timeline is not None
    assert len(one_and_half.timeline.monthly_results) == 361
    assert one_and_half.timeline.monthly_results[238].debt_snapshot is not None
    assert one_and_half.timeline.monthly_results[238].debt_snapshot.loan_balance > _ZERO


@pytest.mark.ern_e2e
def test_experiment_c_enforcement_is_terminal() -> None:
    """Mode 2: Sep 1929 75% LTV enforcement terminates without recovery."""
    result = _run(
        _config(
            equity=(Decimal("0.75"), Decimal("1.0")),
            rates=(Decimal("0.015"), Decimal("0.03")),
            withdrawal_rate=Decimal("0"),
            loan_draw_rate=Decimal("0.04"),
            ltv_enforcement=True,
        ),
        _single_cohort(1929, 9),
        materialize_timeline=False,
    )

    for simulation in result.experiment_result.simulation_results:
        stats = simulation.statistics
        assert stats.success is False
        assert stats.failure_state == "margin_call_terminal"
        assert stats.failure_month is not None
        assert stats.months_simulated <= stats.failure_month + 1


@pytest.mark.ern_e2e
def test_experiment_d_chart_04_observe_only() -> None:
    """$20k portfolio + $20k loan, Nov 1965, observe-only."""
    result = _run(
        _config(
            equity=(Decimal("0.75"),),
            rates=(Decimal("0"), Decimal("0.015"), Decimal("0.03")),
            withdrawal_rate=Decimal("0.02"),
            loan_draw_rate=Decimal("0.02"),
            ltv_enforcement=False,
        ),
        _single_cohort(1965, 11),
        materialize_timeline=True,
    )

    expected = {
        Decimal("0"): Decimal("0.7160"),
        Decimal("0.015"): Decimal("0.8445"),
        Decimal("0.03"): Decimal("0.9311"),
    }
    measured: dict[Decimal, Decimal] = {}
    for rate in (Decimal("0"), Decimal("0.015"), Decimal("0.03")):
        simulation = _find(result, Decimal("0.75"), rate)
        assert simulation.timeline is not None
        month_201 = simulation.timeline.monthly_results[200]
        assert month_201.debt_snapshot is not None
        measured[rate] = month_201.debt_snapshot.ltv
        assert abs(measured[rate] - expected[rate]) <= _DIAGNOSTIC_LP_TOLERANCE

    assert measured[Decimal("0")] < measured[Decimal("0.015")] < measured[Decimal("0.03")]


@pytest.mark.ern_e2e
def test_experiment_e_chart_05_06_observe_only() -> None:
    """$30k portfolio + $10k loan, 1965 and 1929, observe-only."""
    for cohort, expected, tolerance in (
        (
            (1965, 11),
            {Decimal("0.015"): Decimal("0.5768"), Decimal("0.03"): Decimal("0.7025")},
            _DIAGNOSTIC_LP_TOLERANCE,
        ),
        (
            (1929, 9),
            {Decimal("0.015"): Decimal("0.5562"), Decimal("0.03"): Decimal("0.6774")},
            _DIAGNOSTIC_1929_LP_TOLERANCE,
        ),
    ):
        result = _run(
            _config(
                equity=(Decimal("0.75"),),
                rates=(Decimal("0"), Decimal("0.015"), Decimal("0.03")),
                withdrawal_rate=Decimal("0.03"),
                loan_draw_rate=Decimal("0.01"),
                ltv_enforcement=False,
            ),
            _single_cohort(*cohort),
            materialize_timeline=True,
        )

        measured: dict[Decimal, Decimal] = {}
        for rate in (Decimal("0"), Decimal("0.015"), Decimal("0.03")):
            simulation = _find(result, Decimal("0.75"), rate)
            measured[rate] = _max_ltv(simulation)
            assert measured[rate] < Decimal("0.75")
        assert measured[Decimal("0")] < measured[Decimal("0.015")] < measured[Decimal("0.03")]

        for rate, expected_lp in expected.items():
            assert abs(measured[rate] - expected_lp) <= tolerance, (
                f"cohort={cohort} rate={rate}: max L/P {measured[rate]} "
                f"vs article {expected_lp}"
            )


@pytest.mark.ern_e2e
def test_experiment_f_historical_4pct_universe() -> None:
    """1925-1990 historical 4% conclusion, 792 cohorts x 6 configs."""
    result = _run(
        _config(
            equity=(Decimal("0.75"), Decimal("1.0")),
            rates=(Decimal("0"), Decimal("0.015"), Decimal("0.03")),
            withdrawal_rate=Decimal("0.03"),
            loan_draw_rate=Decimal("0.01"),
            ltv_enforcement=False,
        ),
        lambda cohort: date(1925, 1, 1) <= cohort.start_date <= date(1990, 12, 1),
        materialize_timeline=False,
    )

    assert len(result.plan.units) == 4752
    assert len(result.experiment_result.simulation_results) == 4752

    successes: dict[float, int] = defaultdict(int)
    failures: list[tuple[date, float, float, int | None, str | None]] = []
    states: Counter[str | None] = Counter()

    for unit, simulation in zip(
        result.plan.units,
        result.experiment_result.simulation_results,
        strict=True,
    ):
        equity = float(unit.parameter_config.values["equity_allocation"])
        rate = float(unit.parameter_config.values["interest_rate"])
        stats = simulation.statistics
        states[stats.failure_state] += 1
        if stats.success:
            successes[equity] += 1
        else:
            failures.append(
                (
                    unit.cohort.start_date,
                    equity,
                    rate,
                    stats.failure_month,
                    stats.failure_state,
                )
            )

    assert successes[0.75] == 2376
    assert successes[1.0] == 2373
    assert len(failures) == 3
    assert states == Counter({None: 4749, "depleted": 3})

    for start_date, equity, _rate, failure_month, failure_state in failures:
        assert start_date == date(1929, 8, 1)
        assert equity == 1.0
        assert failure_month == 295
        assert failure_state == "depleted"
