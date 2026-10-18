"""Cross-path contract for the workbook outcome.

``failure_month`` is exclusively the month of an *operational terminal failure*
(the portfolio reaching zero).  It is never inferred from ``SCR < rate`` and is
never merely the horizon at which a success criterion is evaluated.

These tests exercise the three production workbook paths -- the Decimal closed
form, the Fast Path group executor and the Numba executor -- and require them to
agree on ``success`` / ``failure_month`` / ``failure_state`` / ``months_simulated``
for the same context.  The expected month is derived independently from the
authoritative workbook recurrence (``SWR_Toolbox_v2.0.xlsx`` ``Case Study``:
withdraw before growth; fee embedded additively in returns).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.fast_path import (
    FastPathSimulationExecutor,
    evaluate_closed_form,
)
from fbf.core.execution.strategies.numba_executor import NumbaSimulationExecutor
from fbf.core.study.builder import build_initial_portfolio

_EQ = AssetClass(id="equity", name="", description="")
_BD = AssetClass(id="bond", name="", description="")

_INITIAL_WEALTH = Decimal("1000000")

# (horizon, rate): flat zero-return dataset, 50/50 allocation, zero fee.
#  - 60 / 0.04  : SCR (12/59) well above rate -> sustainable, no failure.
#  - 100 / 0.30 : monthly 25,000 -> exhausted on the 41st withdrawal (month 41).
#  - 120 / 0.15 : SCR (12/119) below rate, monthly 12,500 -> month 81, far
#                 short of the horizon, so a fabricated horizon month is wrong.
_SCENARIOS = [
    (60, Decimal("0.04")),
    (100, Decimal("0.30")),
    (120, Decimal("0.15")),
]


def _flat_dataset(n_months: int) -> Dataset:
    snapshots = []
    d = date(1900, 1, 1)
    for _ in range(n_months):
        snapshots.append(
            MarketSnapshot(
                date=d,
                index_levels={_EQ: Decimal("100"), _BD: Decimal("100")},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            )
        )
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return Dataset(snapshots=snapshots, frequency="monthly")


def _context(horizon: int, rate: Decimal) -> SimulationContext:
    dataset = _flat_dataset(horizon + 1)
    start = dataset[0].date
    return SimulationContext(
        experiment_name="wb-outcome",
        cohort=str(start),
        start_date=start,
        horizon_months=horizon,
        initial_wealth=Money(_INITIAL_WEALTH, Currency.EUR),
        initial_portfolio=build_initial_portfolio(Money(_INITIAL_WEALTH, Currency.EUR), dataset),
        dataset=dataset,
        allocation_policy=ConstantAllocationPolicy(Decimal("0.5")),
        withdrawal_policy=FixedRealWithdrawalPolicy(rate),
        expense_ratio=Decimal("0"),
    )


def _definition(context: SimulationContext) -> EngineExperimentDefinition:
    return EngineExperimentDefinition(
        name="wb-outcome",
        description="workbook outcome contract",
        simulation_contexts=(context,),
    )


def _expected_depletion_month(rate: Decimal, horizon: int) -> int | None:
    """Independent workbook recurrence: withdraw before growth, flat returns.

    Returns the reported month (0-based period index + 1, month 0 being the
    pre-retirement snapshot) or ``None`` when the trajectory survives.
    """
    periods = horizon - 1
    monthly = _INITIAL_WEALTH * rate / Decimal("12")
    value = _INITIAL_WEALTH
    for m in range(periods):
        if value < monthly:
            return m + 1
        value -= monthly
    return None


@pytest.mark.parametrize("horizon,rate", _SCENARIOS)
def test_workbook_outcome_consistent_across_paths(horizon: int, rate: Decimal) -> None:
    context = _context(horizon, rate)
    expected_month = _expected_depletion_month(rate, horizon)
    expected_success = expected_month is None
    expected_months = horizon if expected_month is None else expected_month
    expected_state = None if expected_month is None else "depleted"

    closed = evaluate_closed_form(context).statistics
    fast = (
        FastPathSimulationExecutor()
        .execute(_definition(context))
        .simulation_results[0]
        .statistics
    )
    numba = (
        NumbaSimulationExecutor()
        .execute(_definition(context))
        .simulation_results[0]
        .statistics
    )

    for label, stats in (
        ("evaluate_closed_form", closed),
        ("FastPathSimulationExecutor", fast),
        ("NumbaSimulationExecutor", numba),
    ):
        assert stats.success == expected_success, label
        assert stats.failure_month == expected_month, label
        assert stats.failure_state == expected_state, label
        assert stats.months_simulated == expected_months, label


def test_depletion_month_is_not_the_horizon() -> None:
    """An unsustainable rate reports the actual depletion month, not the horizon."""
    horizon, rate = 120, Decimal("0.15")
    context = _context(horizon, rate)
    stats = evaluate_closed_form(context).statistics

    assert stats.success is False
    assert stats.failure_state == "depleted"
    assert stats.failure_month is not None
    assert stats.failure_month < horizon
    assert stats.failure_month == _expected_depletion_month(rate, horizon)
    assert stats.months_simulated == stats.failure_month


def test_sustainable_path_has_no_failure_fields() -> None:
    horizon, rate = 60, Decimal("0.04")
    context = _context(horizon, rate)
    stats = evaluate_closed_form(context).statistics

    assert stats.success is True
    assert stats.failure_month is None
    assert stats.failure_state is None
    assert stats.months_simulated == horizon
