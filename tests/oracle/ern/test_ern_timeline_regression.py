"""P1.12R remediation regression: corrected engine timeline vs canonical oracle.

The engine remediation changed the cohort window from ``d_c..d_{c+T-1}`` (old,
defective: initial withdrawal deferred until d_c, T observations) to the literal
ERN window ``d_{c-1}..d_{c+T-1}`` (initial withdrawal at the previous month's
closing price, T+1 observations, T return intervals).  These tests pin the two
regression targets that failed Gate 2:

* the boundary cohort 306 cell (0% equity / 3.25% / 30y) — oracle 79%, engine
  must now also be 79% and the single cohort 306 itself must fail like the
  oracle;
* the nine formerly divergent cells (all 0% equity, every rate, 30y) — the
  engine must now agree with the oracle cohort-by-cohort (exact per-cohort
  Decimal equality) and at every cell percentage.

The oracle per-cohort values are computed with the canonical implementation
(``tools/ern/reference_oracle.py``) which is NOT modified by the remediation.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pytest

from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from fbf.core.execution.pipeline.pipeline import SimulationPipeline
from fbf.core.execution.pipeline.runner import SimulationRunner
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.pipeline.steps.allocation_decision_step import AllocationDecisionStep
from fbf.core.execution.pipeline.steps.build_decision_context_step import BuildDecisionContextStep
from fbf.core.execution.pipeline.steps.initialize_allocation_step import InitializeAllocationStep
from fbf.core.execution.pipeline.steps.market_evolution_step import MarketEvolutionStep
from fbf.core.execution.pipeline.steps.monthly_result_builder_step import MonthlyResultBuilderStep
from fbf.core.execution.pipeline.steps.portfolio_rebalance_step import PortfolioRebalanceStep
from fbf.core.execution.pipeline.steps.simulation_state_update_step import SimulationStateUpdateStep
from fbf.core.execution.pipeline.steps.withdrawal_decision_step import WithdrawalDecisionStep
from fbf.core.execution.pipeline.steps.withdrawal_execution_step import WithdrawalExecutionStep
from fbf.core.execution.strategies.fast_path import evaluate_closed_form
from fbf.core.study import StudyConfiguration, build_study_plan
from tools.ern.reference_oracle import (
    build_extended,
    cohort_annual_swr,
    load_real_returns,
    prefix_tables,
)

from .constants import COHORTS_PER_CELL, RATES

DATA_DIR = Path("data/ern").resolve()
HORIZON_MONTHS = {30: 361, 40: 481, 50: 601, 60: 721}
WEIGHT = 0.0
DIVERGENT_CELLS = [(WEIGHT, rate, 30) for rate in RATES]


def _make_study_config(weight: float, rate: float, horizons: tuple[int, ...]) -> StudyConfiguration:
    return StudyConfiguration(
        name="regression",
        description="",
        version="",
        dataset_identifier="ern_swr_h720",
        allocation_policy_type="ConstantAllocationPolicy",
        allocation_policy_values=(Decimal(str(weight)),),
        withdrawal_policy_type="FixedRealWithdrawalPolicy",
        withdrawal_policy_values=(Decimal(str(rate)),),
        horizon_years=horizons,
    )


def _reference_pipeline() -> SimulationRunner:
    pipeline = SimulationPipeline(
        [
            InitializeAllocationStep(),
            BuildDecisionContextStep(),
            WithdrawalDecisionStep(),
            WithdrawalExecutionStep(),
            AllocationDecisionStep(),
            PortfolioRebalanceStep(),
            MarketEvolutionStep(),
            MonthlyResultBuilderStep(),
            SimulationStateUpdateStep(),
        ]
    )
    return SimulationRunner(pipeline)


@pytest.fixture(scope="module")
def grid_plan():
    """The grid-shaped plan (all four horizons): 1739 cohorts, 6956 units.

    The cohort set is fixed by the longest horizon (721 observations -> 1739
    cohorts on the 2459-snapshot h720 dataset), exactly matching the oracle's
    cohort census START_FIRST=1..START_LAST=1739.
    """
    config = _make_study_config(0.5, 0.04, (30, 40, 50, 60))
    return build_study_plan(config, str(DATA_DIR), Money(Decimal("1000000"), Currency.EUR))


def _units_by_horizon(plan):
    by_horizon: dict[int, list] = defaultdict(list)
    for unit in plan.units:
        by_horizon[unit.horizon_months].append(unit)
    return by_horizon


def _oracle_success(weight: float, rate: float, horizon_years: int) -> list[bool]:
    """Per-cohort oracle success for a cell (cohort start 1..1739)."""
    T = HORIZON_MONTHS[horizon_years] - 1
    r_eq, r_bd = load_real_returns(DATA_DIR / "ern_real_returns_1871_2016.csv")
    P, pre = prefix_tables(*build_extended(r_eq, r_bd), weight)
    return [
        cohort_annual_swr(P, pre, start, T) >= rate for start in range(1, COHORTS_PER_CELL + 1)
    ]


def _engine_contexts(plan, by_horizon, weight, rate, horizon_years, cohorts):
    """Engine contexts for one cell over the requested cohort indices (0-based)."""
    units = by_horizon[HORIZON_MONTHS[horizon_years]]
    cap = plan.experiment_definition.initial_wealth
    alloc = ConstantAllocationPolicy(equity_allocation=Decimal(str(weight)))
    withdraw = FixedRealWithdrawalPolicy(withdrawal_rate=Decimal(str(rate)))
    return tuple(
        SimulationContext(
            experiment_name=plan.experiment_definition.name,
            cohort=unit.cohort.id,
            start_date=unit.cohort.start_date,
            horizon_months=unit.horizon_months,
            initial_wealth=cap,
            initial_portfolio=unit.initial_portfolio,
            dataset=unit.dataset,
            allocation_policy=alloc,
            withdrawal_policy=withdraw,
        )
        for i, unit in enumerate(units)
        if i in cohorts
    )


def _engine_success(
    plan, by_horizon, weight, rate, horizon_years, precision, *, cohorts: set[int] | None = None
) -> list[bool]:
    """Per-cohort engine success for a full cell (fast path, chosen precision)."""
    units = by_horizon[HORIZON_MONTHS[horizon_years]]
    cap = plan.experiment_definition.initial_wealth
    alloc = ConstantAllocationPolicy(equity_allocation=Decimal(str(weight)))
    withdraw = FixedRealWithdrawalPolicy(withdrawal_rate=Decimal(str(rate)))
    contexts = tuple(
        SimulationContext(
            experiment_name=plan.experiment_definition.name,
            cohort=unit.cohort.id,
            start_date=unit.cohort.start_date,
            horizon_months=unit.horizon_months,
            initial_wealth=cap,
            initial_portfolio=unit.initial_portfolio,
            dataset=unit.dataset,
            allocation_policy=alloc,
            withdrawal_policy=withdraw,
        )
        for i, unit in enumerate(units)
        if cohorts is None or i in cohorts
    )
    results = tuple(
        evaluate_closed_form(ctx, precision) for ctx in contexts
    )
    return [r.statistics.success for r in results]


def test_plan_exposes_pre_retirement_snapshot(grid_plan) -> None:
    """The corrected plan anchors every cohort at its pre-retirement snapshot."""
    by_horizon = _units_by_horizon(grid_plan.plan)
    first = by_horizon[HORIZON_MONTHS[30]][0]
    assert first.cohort.start_date.isoformat() == "1871-01-31"  # d_{-1}
    assert first.dataset[0].date == first.cohort.start_date
    assert len(first.dataset) == HORIZON_MONTHS[30]  # T+1 observations
    assert first.horizon_months == HORIZON_MONTHS[30]
    assert len(by_horizon[HORIZON_MONTHS[30]]) == COHORTS_PER_CELL


def test_boundary_cohort_306_reference_pipeline_matches_oracle(grid_plan) -> None:
    """Cohort 306 (0% / 3.25% / 30y) fails through the full reference engine.

    The engine's cohort 306 retires in July-1896 (base snapshot 1896-07-01);
    the oracle's cohort start 307 covers the same window.  Both must report a
    failure — the old engine passed it by deferring the initial withdrawal.
    """
    by_horizon = _units_by_horizon(grid_plan.plan)
    unit = by_horizon[HORIZON_MONTHS[30]][306]
    assert unit.cohort.start_date.isoformat() == "1896-07-01"  # old d_305 = base for c=306

    oracle_ok = _oracle_success(0.0, 0.0325, 30)[306]  # oracle start 307 -> index 306
    context = _engine_contexts(
        grid_plan.plan, by_horizon, 0.0, 0.0325, 30, {306}
    )[0]
    result = _reference_pipeline().run(context)

    assert oracle_ok is False
    assert result.statistics.success is False
    assert result.statistics.failure_month is not None


def test_boundary_cell_306_engine_percentage_matches_oracle(grid_plan) -> None:
    """The 0% / 3.25% / 30y cell is 79% for BOTH oracle and corrected engine."""
    oracle_ok = _oracle_success(0.0, 0.0325, 30)
    oracle_pct = round(100 * sum(oracle_ok) / COHORTS_PER_CELL)
    engine_ok = _engine_success(
        grid_plan.plan, _units_by_horizon(grid_plan.plan), 0.0, 0.0325, 30, "decimal"
    )
    engine_pct = round(100 * sum(engine_ok) / COHORTS_PER_CELL)

    assert oracle_pct == 79
    assert engine_pct == 79
    assert sum(engine_ok) == sum(oracle_ok)


def test_formerly_divergent_cells_match_oracle_per_cohort(grid_plan) -> None:
    """All nine formerly divergent cells now match the oracle cohort-by-cohort.

    Exact per-cohort Decimal equality: every one of the 9 x 1739 simulated
    cohorts must land on the same success/failure verdict as the oracle.
    """
    by_horizon = _units_by_horizon(grid_plan.plan)
    mismatches = []
    for weight, rate, horizon_years in DIVERGENT_CELLS:
        engine_ok = _engine_success(
            grid_plan.plan, by_horizon, weight, rate, horizon_years, "decimal"
        )
        oracle_ok = _oracle_success(weight, rate, horizon_years)
        assert len(engine_ok) == COHORTS_PER_CELL
        for idx, (engine, oracle) in enumerate(zip(engine_ok, oracle_ok, strict=True)):
            if engine != oracle:
                mismatches.append((weight, rate, horizon_years, idx, engine, oracle))

    assert mismatches == [], (
        f"{len(mismatches)} per-cohort verdicts disagree with the oracle: "
        f"{mismatches[:10]}"
    )
