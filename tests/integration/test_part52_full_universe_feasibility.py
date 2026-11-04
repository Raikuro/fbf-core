"""Part 52 A10 full-universe feasibility diagnostic.

This module checks that the production feasibility helper can account for the
entire A10 distribution universe, that its gross-survival result agrees with
the oracle execution for every unit, and that the three workbook constraints
are combined consistently. It also groups the metrics by the documented
coverage layers so the gross-survival and feasibility counts are not conflated
with historical-data coverage.

All numerical counts and values produced here are diagnostics tied to the
current canonical dataset vintage. They are not canonical acceptance constants
and do not establish historical or canonical validation. Coverage boundaries
and their exact group sizes are owned by
``tests/integration/test_part52_cohort_coverage.py``.

The resolved reporting hierarchy is: historical-market (``1,506``) primary,
workbook-FFR (``1,453``) sensitivity, distribution (``1,739``) projection-only,
and legacy terminal (``1,452``) retired.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from fbf.core.domain.model.money import Currency, Money
from fbf.core.execution import (
    ExecutionOptions,
    ExecutionStrategy,
    _extract_simulation_contexts,
    execute_study_plan,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.part52_numba_executor import (
    Part52FeasibilityMetrics,
    evaluate_part52_feasibility,
)
from fbf.core.study import BuiltStudy, StudyConfiguration, build_study_plan

pytestmark = pytest.mark.research_validation

DATA_DIR = Path("data/ern")
INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)
EXPECTED_UNITS = 1739
SIMULATION_HORIZON_MONTHS = 30 * 12
MARKET_HISTORY_END = date(2026, 6, 1)
FFR_WORKBOOK_END = date(2021, 12, 1)
MIN_NET_WORTH_TARGET = Decimal("1000")
FINAL_NET_WORTH_TARGET = Decimal("250000")
FINAL_NET_WORTH_TARGET_TOLERANCE = Decimal("0.01")
MAX_LOAN_TO_PORTFOLIO_LIMIT = Decimal("0.50")


@dataclass(frozen=True)
class FeasibilityLayer:
    """Aggregated feasibility diagnostics for one coverage layer."""

    name: str
    total: int
    gross_survival: int
    min_net_worth_ok: int
    final_net_worth_ok: int
    max_loan_to_portfolio_ok: int
    feasible: int

    def format(self) -> str:
        return (
            f"{self.name}: total={self.total}, "
            f"gross_survival={self.gross_survival}, "
            f"min_net_worth_ok={self.min_net_worth_ok}, "
            f"final_net_worth_ok={self.final_net_worth_ok}, "
            f"max_loan_to_portfolio_ok={self.max_loan_to_portfolio_ok}, "
            f"feasible={self.feasible}"
        )


def _build_a10_config() -> StudyConfiguration:
    """Build the canonical A10 configuration.

    Parameters mirror the A10 entry in
    ``tests/oracle/ern/test_part52_replication.py``. This diagnostic duplicates
    only the fixed configuration so it can run without the 11-scenario oracle
    fixture.
    """
    return StudyConfiguration(
        name="ERN_Part52_A10_full_universe_feasibility",
        description="Diagnostic A10 full-universe feasibility accounting",
        version="1.0",
        allocation_policy_type="ConstantAllocationPolicy",
        allocation_policy_values=(Decimal("0.75"),),
        withdrawal_policy_type="Part52WithdrawalPolicy",
        withdrawal_policy_values=(Decimal("0.0439"),),
        horizon_years=(30,),
        cohort_horizon_years=60,
        ffr_spread=Decimal("0.005"),
        debt_ltv_limit=MAX_LOAN_TO_PORTFOLIO_LIMIT,
        debt_ltv_enforcement=False,
        debt_borrow_pct=Decimal("0.3186"),
        debt_drawdown_threshold=None,
    )


def _add_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _terminal_snapshot_date(start_date: date) -> date:
    return _add_months(start_date, SIMULATION_HORIZON_MONTHS)


def _latest_consumed_ffr_date(start_date: date) -> date:
    return _add_months(start_date, SIMULATION_HORIZON_MONTHS - 1)


def _summarize(
    name: str,
    metrics: tuple[Part52FeasibilityMetrics, ...],
) -> FeasibilityLayer:
    return FeasibilityLayer(
        name=name,
        total=len(metrics),
        gross_survival=sum(1 for metric in metrics if metric.gross_survival),
        min_net_worth_ok=sum(1 for metric in metrics if metric.min_net_worth_ok),
        final_net_worth_ok=sum(1 for metric in metrics if metric.final_net_worth_ok),
        max_loan_to_portfolio_ok=sum(
            1 for metric in metrics if metric.max_loan_to_portfolio_ok
        ),
        feasible=sum(1 for metric in metrics if metric.feasible),
    )


def _assert_layer_accounting(layer: FeasibilityLayer) -> None:
    assert 0 <= layer.feasible <= layer.gross_survival <= layer.total, layer.format()
    assert 0 <= layer.feasible <= layer.min_net_worth_ok <= layer.total, layer.format()
    assert 0 <= layer.feasible <= layer.final_net_worth_ok <= layer.total, layer.format()
    assert 0 <= layer.feasible <= layer.max_loan_to_portfolio_ok <= layer.total, layer.format()


@pytest.fixture(scope="module")
def a10_full_universe() -> tuple[
    BuiltStudy,
    tuple[SimulationContext, ...],
    tuple[Part52FeasibilityMetrics, ...],
    tuple[bool, ...],
]:
    built = build_study_plan(_build_a10_config(), str(DATA_DIR), INITIAL_WEALTH)
    result = execute_study_plan(
        built,
        options=ExecutionOptions(
            strategy=ExecutionStrategy.AUTO,
            workers=None,
        ),
    )
    contexts = _extract_simulation_contexts(built.plan)
    metrics = tuple(evaluate_part52_feasibility(context) for context in contexts)
    oracle_successes = tuple(
        simulation_result.statistics.success
        for simulation_result in result.experiment_result.simulation_results
    )
    return built, contexts, metrics, oracle_successes


def test_a10_full_universe_feasibility_matches_oracle_gross_survival(
    a10_full_universe: tuple[
        BuiltStudy,
        tuple[SimulationContext, ...],
        tuple[Part52FeasibilityMetrics, ...],
        tuple[bool, ...],
    ],
) -> None:
    built, _contexts, metrics, oracle_successes = a10_full_universe

    assert len(built.plan.units) == EXPECTED_UNITS
    assert len(metrics) == EXPECTED_UNITS
    assert len(oracle_successes) == EXPECTED_UNITS

    for index, (metric, oracle_success) in enumerate(
        zip(metrics, oracle_successes, strict=True)
    ):
        start_date = built.plan.units[index].cohort.start_date
        assert metric.gross_survival is oracle_success, (
            f"gross-survival mismatch at unit {index} ({start_date}): "
            f"helper={metric.gross_survival}, oracle={oracle_success}"
        )
        assert metric.feasible == (
            metric.gross_survival
            and metric.min_net_worth_ok
            and metric.final_net_worth_ok
            and metric.max_loan_to_portfolio_ok
        ), f"inconsistent three-constraint conjunction at unit {index} ({start_date})"
        assert metric.min_net_worth_target == MIN_NET_WORTH_TARGET
        assert (
            abs(metric.final_net_worth_target - FINAL_NET_WORTH_TARGET)
            <= FINAL_NET_WORTH_TARGET_TOLERANCE
        )
        assert metric.max_loan_to_portfolio_limit == MAX_LOAN_TO_PORTFOLIO_LIMIT


def test_a10_full_universe_and_coverage_layer_accounting(
    a10_full_universe: tuple[
        BuiltStudy,
        tuple[SimulationContext, ...],
        tuple[Part52FeasibilityMetrics, ...],
        tuple[bool, ...],
    ],
) -> None:
    built, _contexts, metrics, _oracle_successes = a10_full_universe

    historical_market_indices = tuple(
        index
        for index, unit in enumerate(built.plan.units)
        if _terminal_snapshot_date(unit.cohort.start_date) <= MARKET_HISTORY_END
    )
    workbook_ffr_indices = tuple(
        index
        for index, unit in enumerate(built.plan.units)
        if _latest_consumed_ffr_date(unit.cohort.start_date) <= FFR_WORKBOOK_END
    )
    legacy_terminal_indices = tuple(
        index
        for index, unit in enumerate(built.plan.units)
        if _terminal_snapshot_date(unit.cohort.start_date) <= FFR_WORKBOOK_END
    )

    assert set(legacy_terminal_indices) <= set(workbook_ffr_indices)
    assert set(workbook_ffr_indices) <= set(historical_market_indices)
    assert set(historical_market_indices) <= set(range(len(metrics)))

    layers = (
        _summarize("distribution", metrics),
        _summarize(
            "historical_market",
            tuple(metrics[index] for index in historical_market_indices),
        ),
        _summarize(
            "workbook_ffr",
            tuple(metrics[index] for index in workbook_ffr_indices),
        ),
        _summarize(
            "legacy_terminal_2021_12",
            tuple(metrics[index] for index in legacy_terminal_indices),
        ),
    )

    for layer in layers:
        _assert_layer_accounting(layer)

    assert tuple(layer.total for layer in layers) == (1739, 1506, 1453, 1452)
    assert layers[0].total >= layers[1].total >= layers[2].total >= layers[3].total
    assert layers[0].gross_survival == sum(1 for metric in metrics if metric.gross_survival)

    print("\nA10 full-universe feasibility diagnostics (current dataset vintage):")
    for layer in layers:
        print(f"  {layer.format()}")
