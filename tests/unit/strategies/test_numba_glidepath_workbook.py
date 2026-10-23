"""Differential validation: glidepath Numba path vs workbook recurrence.

The shared timing mechanics come from ``SWR_Toolbox_v2.0.xlsx``
(``Case Study``) and ``Timing-Leverage-Calc.xlsx`` (``Calc``):

    P(t) = (P(t-1) - W(t)) * (1 + R(t))

The withdrawal precedes growth in every period, the final period's return is
compounded, and the pre-retirement snapshot is the base row (no withdrawal).
The context horizon therefore contains ``horizon - 1`` withdrawal / growth
periods.

The glidepath weight sequence itself is the simulator extension: the workbook
uses a fixed 120-month linear transition, while ERN advances relative to the
beginning-of-period underwater state.  These tests keep that extension and
validate only the shared recurrence against an independent Decimal model.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import cast

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import FixedRealWithdrawalPolicy
from fbf.core.domain.policies.glidepath import (
    GlidepathAllocationPolicy,
    GlidepathCadence,
)
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    SimulationResult,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.numba_executor import NumbaSimulationExecutor
from fbf.core.study.builder import build_initial_portfolio

_EQ = AssetClass(id="equity", name="", description="")
_BD = AssetClass(id="bond", name="", description="")

_WEALTH = Decimal("1000000")
_TOLERANCE = Decimal("0.01")


def _snap(
    d: date,
    equity_price: Decimal,
    bond_price: Decimal,
    *,
    is_underwater: bool = False,
) -> MarketSnapshot:
    return MarketSnapshot(
        date=d,
        index_levels={_EQ: equity_price, _BD: bond_price},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=not is_underwater,
        is_underwater=is_underwater,
        running_ath=equity_price if not is_underwater else equity_price * Decimal("1.25"),
    )


def _build_dataset(
    equity_returns: list[Decimal],
    bond_returns: list[Decimal],
    underwater_flags: list[bool],
) -> Dataset:
    """Dataset with ``len(equity_returns) + 1`` snapshots.

    ``underwater_flags`` has one entry per withdrawal / growth period.
    """
    assert len(equity_returns) == len(bond_returns) == len(underwater_flags)
    pe = Decimal("100")
    pb = Decimal("100")
    d = date(2000, 1, 1)
    snapshots = [
        _snap(d, pe, pb, is_underwater=underwater_flags[0]),
    ]
    for m, (eq_ret, bd_ret) in enumerate(
        zip(equity_returns, bond_returns, strict=True)
    ):
        pe *= eq_ret
        pb *= bd_ret
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
        flags_index = min(m + 1, len(underwater_flags) - 1)
        snapshots.append(
            _snap(d, pe, pb, is_underwater=underwater_flags[flags_index])
        )
    return Dataset(snapshots=tuple(snapshots), frequency="monthly")


def _build_context(
    dataset: Dataset,
    policy: GlidepathAllocationPolicy,
    withdrawal_rate: Decimal,
    fee: Decimal,
) -> SimulationContext:
    start = dataset[0].date
    return SimulationContext(
        experiment_name="glidepath-workbook",
        cohort="test",
        start_date=start,
        horizon_months=len(dataset.snapshots),
        initial_wealth=Money(_WEALTH, Currency.EUR),
        initial_portfolio=build_initial_portfolio(
            Money(_WEALTH, Currency.EUR), dataset
        ),
        dataset=dataset,
        allocation_policy=policy,
        withdrawal_policy=FixedRealWithdrawalPolicy(
            withdrawal_rate=withdrawal_rate
        ),
        expense_ratio=fee,
    )


def _run(context: SimulationContext) -> SimulationResult:
    executor = NumbaSimulationExecutor(materialize_timeline=True)
    definition = EngineExperimentDefinition(
        name="glidepath-workbook",
        description="glidepath workbook differential",
        simulation_contexts=(context,),
    )
    return executor.execute(definition).simulation_results[0]


def _weights(
    policy: GlidepathAllocationPolicy,
    underwater_flags: list[bool],
    periods: int,
) -> list[Decimal]:
    weights: list[Decimal] = []
    for m in range(periods):
        if policy.cadence is GlidepathCadence.ANNUAL:
            advancements = m // 12
        elif policy.mode == "passive":
            advancements = m
        else:
            advancements = sum(1 for flag in underwater_flags[: m + 1] if flag)
        raw = policy.start_equity + policy.slope * advancements
        weights.append(min(raw, policy.end_equity))
    return weights


def _workbook_recurrence(
    dataset: Dataset,
    policy: GlidepathAllocationPolicy,
    withdrawal_rate: Decimal,
    fee: Decimal,
) -> tuple[Decimal, bool, int | None, list[Decimal]]:
    """Independent Decimal implementation of the workbook recurrence.

    Returns ``(final_value, success, failure_month, withdrawals)`` where
    ``failure_month`` uses the base-row convention (first period is month 1).
    """
    periods = len(dataset.snapshots) - 1
    underwater_flags = [snap.is_underwater for snap in dataset.snapshots]
    weights = _weights(policy, underwater_flags, periods)
    withdrawal = _WEALTH * withdrawal_rate / Decimal("12")
    fee_monthly = fee / Decimal("12")
    value = _WEALTH
    withdrawals: list[Decimal] = [Decimal("0")]

    for m in range(periods):
        if value < withdrawal:
            return Decimal("0"), False, m + 1, withdrawals
        value -= withdrawal
        eq_ret = (
            dataset.snapshots[m + 1].index_levels[_EQ]
            / dataset.snapshots[m].index_levels[_EQ]
        )
        bd_ret = (
            dataset.snapshots[m + 1].index_levels[_BD]
            / dataset.snapshots[m].index_levels[_BD]
        )
        growth = weights[m] * eq_ret + (Decimal("1") - weights[m]) * bd_ret
        value *= growth - fee_monthly
        withdrawals.append(withdrawal)

    return value, True, None, withdrawals


@pytest.mark.parametrize("mode", ["passive", "active"])
def test_glidepath_matches_workbook_recurrence_with_fee(mode: str) -> None:
    periods = 24
    equity_returns = [Decimal("1.006") for _ in range(periods)]
    bond_returns = [Decimal("1.002") for _ in range(periods)]
    underwater_flags = [m % 3 == 0 for m in range(periods)]
    dataset = _build_dataset(equity_returns, bond_returns, underwater_flags)

    policy = GlidepathAllocationPolicy(
        start_equity=Decimal("0.60"),
        end_equity=Decimal("0.90"),
        slope=Decimal("0.01"),
        mode=mode,
    )
    withdrawal_rate = Decimal("0.04")
    fee = Decimal("0.006")
    context = _build_context(dataset, policy, withdrawal_rate, fee)

    expected_value, expected_success, expected_failure, expected_withdrawals = (
        _workbook_recurrence(dataset, policy, withdrawal_rate, fee)
    )
    result = _run(context)

    assert result.statistics.success is expected_success
    assert result.statistics.failure_month == expected_failure
    assert result.statistics.months_simulated == context.horizon_months
    assert abs(result.statistics.final_wealth.amount - expected_value) < _TOLERANCE

    timeline = result.timeline
    assert len(timeline.monthly_results) == context.horizon_months
    for m, monthly in enumerate(timeline.monthly_results):
        decision = monthly.withdrawal_decision
        assert decision is not None
        assert (
            abs(decision.nominal_amount.amount - expected_withdrawals[m])
            < _TOLERANCE
        )


def test_glidepath_compounds_terminal_period_and_skips_base_withdrawal() -> None:
    horizon = 13
    dataset = _build_dataset(
        [Decimal("1")] * (horizon - 1),
        [Decimal("1")] * (horizon - 1),
        [False] * (horizon - 1),
    )
    policy = GlidepathAllocationPolicy(
        start_equity=Decimal("0.60"),
        end_equity=Decimal("1.00"),
        slope=Decimal("0.01"),
        mode="passive",
    )
    withdrawal_rate = Decimal("0.12")
    context = _build_context(dataset, policy, withdrawal_rate, Decimal("0"))

    expected_value, expected_success, expected_failure, _ = _workbook_recurrence(
        dataset, policy, withdrawal_rate, Decimal("0")
    )
    result = _run(context)

    monthly_withdrawal = _WEALTH * withdrawal_rate / Decimal("12")
    # 12 growth periods (horizon - 1), all with a growth factor of 1.
    assert expected_value == _WEALTH - monthly_withdrawal * Decimal("12")
    assert result.statistics.success is expected_success
    assert result.statistics.failure_month is expected_failure
    assert abs(result.statistics.final_wealth.amount - expected_value) < _TOLERANCE
    assert result.timeline.monthly_results[0].withdrawal_decision is not None
    assert (
        result.timeline.monthly_results[0].withdrawal_decision.nominal_amount.amount
        == Decimal("0")
    )


def test_glidepath_depletion_reports_base_row_month() -> None:
    horizon = 20
    dataset = _build_dataset(
        [Decimal("1")] * (horizon - 1),
        [Decimal("1")] * (horizon - 1),
        [False] * (horizon - 1),
    )
    policy = GlidepathAllocationPolicy(
        start_equity=Decimal("0.60"),
        end_equity=Decimal("0.90"),
        slope=Decimal("0.01"),
        mode="passive",
    )
    # Monthly withdrawal 100_000: after ten periods the value is exactly 0 and
    # the eleventh period cannot be funded.
    withdrawal_rate = Decimal("1.2")
    context = _build_context(dataset, policy, withdrawal_rate, Decimal("0"))

    expected_value, expected_success, expected_failure, _ = _workbook_recurrence(
        dataset, policy, withdrawal_rate, Decimal("0")
    )
    result = _run(context)

    assert expected_success is False
    assert expected_failure == 11
    assert result.statistics.success is False
    assert result.statistics.failure_month == expected_failure
    assert result.statistics.final_wealth.amount == expected_value
    assert result.statistics.months_simulated == expected_failure
    assert len(result.timeline.monthly_results) == expected_failure


def test_annual_cadence_matches_workbook_recurrence_with_fee() -> None:
    periods = 24
    dataset = _build_dataset(
        [Decimal("1.006")] * periods,
        [Decimal("1.002")] * periods,
        [False] * periods,
    )
    policy = GlidepathAllocationPolicy(
        start_equity=Decimal("0.60"),
        end_equity=Decimal("0.90"),
        slope=Decimal("0.01"),
        mode="passive",
        cadence=GlidepathCadence.ANNUAL,
    )
    withdrawal_rate = Decimal("0.04")
    fee = Decimal("0.006")
    context = _build_context(dataset, policy, withdrawal_rate, fee)

    expected_value, expected_success, expected_failure, _ = _workbook_recurrence(
        dataset, policy, withdrawal_rate, fee
    )
    result = _run(context)

    assert result.statistics.success is expected_success
    assert result.statistics.failure_month == expected_failure
    assert abs(result.statistics.final_wealth.amount - expected_value) < _TOLERANCE


def test_fixed_real_glidepath_groups_by_withdrawal_rate() -> None:
    periods = 24
    dataset = _build_dataset(
        [Decimal("1.006")] * periods,
        [Decimal("1.002")] * periods,
        [False] * periods,
    )
    policy = GlidepathAllocationPolicy(
        start_equity=Decimal("0.60"),
        end_equity=Decimal("0.90"),
        slope=Decimal("0.01"),
        mode="passive",
    )
    low_rate = _build_context(dataset, policy, Decimal("0.04"), Decimal("0"))
    high_rate = _build_context(dataset, policy, Decimal("0.08"), Decimal("0"))

    executor = NumbaSimulationExecutor()
    definition = EngineExperimentDefinition(
        name="glidepath-workbook",
        description="withdrawal-rate grouping regression",
        simulation_contexts=(low_rate, high_rate),
    )
    run = executor.execute(definition)

    report = executor.report
    assert report is not None
    assert report.groups == 2
    for context, result in zip(
        (low_rate, high_rate), run.simulation_results, strict=True
    ):
        expected_value, expected_success, expected_failure, _ = (
            _workbook_recurrence(
                dataset,
                policy,
                cast(FixedRealWithdrawalPolicy, context.withdrawal_policy).withdrawal_rate,
                Decimal("0"),
            )
        )
        assert result.statistics.success is expected_success
        assert result.statistics.failure_month == expected_failure
        assert (
            abs(result.statistics.final_wealth.amount - expected_value)
            < _TOLERANCE
        )


def test_fixed_real_glidepath_groups_by_cadence() -> None:
    periods = 24
    dataset = _build_dataset(
        [Decimal("1.006")] * periods,
        [Decimal("1.002")] * periods,
        [False] * periods,
    )
    monthly = GlidepathAllocationPolicy(
        start_equity=Decimal("0.60"),
        end_equity=Decimal("0.90"),
        slope=Decimal("0.01"),
        mode="passive",
    )
    annual = GlidepathAllocationPolicy(
        start_equity=Decimal("0.60"),
        end_equity=Decimal("0.90"),
        slope=Decimal("0.01"),
        mode="passive",
        cadence=GlidepathCadence.ANNUAL,
    )
    withdrawal_rate = Decimal("0.04")
    monthly_ctx = _build_context(dataset, monthly, withdrawal_rate, Decimal("0"))
    annual_ctx = _build_context(dataset, annual, withdrawal_rate, Decimal("0"))

    executor = NumbaSimulationExecutor()
    definition = EngineExperimentDefinition(
        name="glidepath-workbook",
        description="cadence grouping regression",
        simulation_contexts=(monthly_ctx, annual_ctx),
    )
    run = executor.execute(definition)

    report = executor.report
    assert report is not None
    assert report.groups == 2
    for policy, result in zip(
        (monthly, annual), run.simulation_results, strict=True
    ):
        expected_value, expected_success, expected_failure, _ = (
            _workbook_recurrence(
                dataset,
                policy,
                withdrawal_rate,
                Decimal("0"),
            )
        )
        assert result.statistics.success is expected_success
        assert result.statistics.failure_month == expected_failure
        assert (
            abs(result.statistics.final_wealth.amount - expected_value)
            < _TOLERANCE
        )
