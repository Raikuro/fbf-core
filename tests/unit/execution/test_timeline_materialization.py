"""Monthly trajectory materialization tests for the optimized executors.

The value paths are validated against an independent Decimal recurrence (no
Numba, no executor arithmetic), so a drift in the kernel capture arrays or in
the reconstruction is caught rather than masked by comparing two Numba paths.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import (
    BuyAndHoldAllocationPolicy,
    ConstantAllocationPolicy,
    FixedRealWithdrawalPolicy,
)
from fbf.core.domain.policies.allocation_policy import AllocationPolicy
from fbf.core.execution import ExecutionOptions
from fbf.core.execution.pipeline.simulation import (
    DebtSnapshot,
    ExperimentDefinition,
    MonthlyResult,
    SimulationResult,
    SimulationStatistics,
    SimulationTimeline,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.numba_executor import NumbaSimulationExecutor
from fbf.core.persistence.studies.sqlite.codecs import SimulationResultCodec
from fbf.core.study.builder import build_initial_portfolio

EQ = AssetClass(id="equity", name="", description="")
BD = AssetClass(id="bond", name="", description="")


def _dataset(n_months: int, eq_return: Decimal, bd_return: Decimal) -> Dataset:
    snapshots = []
    eq_price = Decimal("100")
    bd_price = Decimal("100")
    current = date(1900, 1, 1)
    for _ in range(n_months + 1):
        snapshots.append(
            MarketSnapshot(
                date=current,
                index_levels={EQ: eq_price, BD: bd_price},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=eq_price,
            )
        )
        eq_price *= Decimal("1") + eq_return
        bd_price *= Decimal("1") + bd_return
        current = date(current.year + (current.month // 12), current.month % 12 + 1, 1)
    return Dataset(snapshots=tuple(snapshots), frequency="monthly")


def _context(
    dataset: Dataset,
    horizon: int,
    *,
    allocation_policy: AllocationPolicy | None = None,
    final_value_target: Decimal | None = None,
) -> SimulationContext:
    wealth = Money(Decimal("1000000"), Currency.EUR)
    return SimulationContext(
        experiment_name="timeline",
        cohort="c",
        start_date=dataset[0].date,
        horizon_months=horizon,
        initial_wealth=wealth,
        initial_portfolio=build_initial_portfolio(wealth, dataset),
        dataset=dataset.slice(dataset[0].date, horizon),
        allocation_policy=allocation_policy
        or ConstantAllocationPolicy(Decimal("0.6")),
        withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.04")),
        final_value_target=final_value_target,
    )


def _run(
    context: SimulationContext, *, materialize: bool
) -> SimulationResult:
    executor = NumbaSimulationExecutor(materialize_timeline=materialize)
    return executor.execute(
        ExperimentDefinition(
            name="timeline", description="timeline", simulation_contexts=(context,)
        )
    ).simulation_results[0]


def _value(mr: MonthlyResult) -> Decimal:
    return sum(
        (
            holding.units * mr.market_snapshot.index_levels[holding.asset_class]
            for holding in mr.portfolio.holdings
        ),
        Decimal("0"),
    )


def _initial_value(context: SimulationContext) -> Decimal:
    snapshot = context.dataset[0]
    return sum(
        (
            holding.units * snapshot.index_levels[holding.asset_class]
            for holding in context.initial_portfolio.holdings
        ),
        Decimal("0"),
    )


def test_materialize_and_summary_only_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        ExecutionOptions(materialize_timeline=True, summary_only=True)


def test_workbook_timeline_matches_decimal_oracle() -> None:
    horizon = 24
    dataset = _dataset(horizon, Decimal("0.006"), Decimal("0.002"))
    context = _context(dataset, horizon)
    result = _run(context, materialize=True)
    timeline = result.timeline.monthly_results

    # Independent Decimal recurrence: month 0 is pre-retirement (no withdrawal).
    v0 = _initial_value(context)
    c = v0 * Decimal("0.04") / Decimal("12")
    growth = Decimal("0.6") * Decimal("1.006") + Decimal("0.4") * Decimal("1.002")
    expected = [v0]
    value = v0
    for _ in range(horizon - 1):
        value = (value - c) * growth
        expected.append(value)

    assert len(timeline) == horizon
    assert result.statistics.months_simulated == horizon
    for m, expected_value in enumerate(expected):
        assert abs(_value(timeline[m]) - expected_value) < Decimal("0.01")
    assert abs(result.statistics.final_wealth.amount - expected[-1]) < Decimal("0.01")


def test_non_workbook_timeline_matches_decimal_oracle() -> None:
    horizon = 12
    dataset = _dataset(horizon, Decimal("0.006"), Decimal("0.002"))
    context = _context(dataset, horizon, final_value_target=Decimal("0.5"))
    result = _run(context, materialize=True)
    timeline = result.timeline.monthly_results

    v0 = _initial_value(context)
    c = v0 * Decimal("0.04") / Decimal("12")
    growth = Decimal("0.6") * Decimal("1.006") + Decimal("0.4") * Decimal("1.002")

    expected = []
    value = v0
    for m in range(horizon):
        value -= c
        expected.append(value)
        if m < horizon - 1:
            value *= growth

    assert len(timeline) == horizon
    for m, expected_value in enumerate(expected):
        assert abs(_value(timeline[m]) - expected_value) < Decimal("0.01")


def test_buy_and_hold_weights_drift_and_revalue() -> None:
    horizon = 12
    dataset = _dataset(horizon, Decimal("0.01"), Decimal("0.001"))
    context = _context(
        dataset, horizon, allocation_policy=BuyAndHoldAllocationPolicy(Decimal("0.6"))
    )
    result = _run(context, materialize=True)
    timeline = result.timeline.monthly_results

    expected_weight = Decimal("0.6")
    for mr in timeline:
        assert mr.allocation is not None
        assert sum(mr.allocation.weights.values()) == Decimal("1")
        assert mr.allocation_target is not None
        assert mr.allocation_target.weights[EQ] == Decimal("0.6")
        assert abs(mr.allocation.weights[EQ] - expected_weight) < Decimal("0.0001")
        level = mr.market_snapshot.index_levels
        revaluation = sum(
            holding.units * level[holding.asset_class]
            for holding in mr.portfolio.holdings
        )
        assert revaluation == _value(mr)
        expected_weight = (
            expected_weight * Decimal("1.01")
            / (
                expected_weight * Decimal("1.01")
                + (Decimal("1") - expected_weight) * Decimal("1.001")
            )
        )


def test_depleted_timeline_length_equals_months_simulated() -> None:
    horizon = 120
    dataset = _dataset(horizon, Decimal("0"), Decimal("0"))
    context = _context(dataset, horizon)
    context = replace(
        context, withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.5"))
    )
    result = _run(context, materialize=True)

    assert result.statistics.success is False
    assert result.statistics.failure_month is not None
    assert len(result.timeline.monthly_results) == result.statistics.months_simulated


def test_statistics_only_path_is_unchanged() -> None:
    horizon = 36
    dataset = _dataset(horizon, Decimal("0.006"), Decimal("0.002"))
    context = _context(dataset, horizon)

    without = _run(context, materialize=False)
    with_timeline = _run(context, materialize=True)

    assert without.statistics.final_wealth == with_timeline.statistics.final_wealth
    assert without.statistics.success == with_timeline.statistics.success
    assert without.statistics.failure_month == with_timeline.statistics.failure_month
    assert (
        without.statistics.months_simulated
        == with_timeline.statistics.months_simulated
    )
    assert without.timeline.monthly_results == ()


def test_codec_roundtrip_preserves_failure_state_and_debt() -> None:
    snapshot = _dataset(1, Decimal("0"), Decimal("0"))[0]
    monthly = MonthlyResult(
        date=snapshot.date,
        period_index=0,
        market_snapshot=snapshot,
        portfolio=build_initial_portfolio(
            Money(Decimal("1000"), Currency.EUR), _dataset(1, Decimal("0"), Decimal("0"))
        ),
        allocation=None,
        allocation_target=None,
        allocation_drift=None,
        withdrawal_decision=None,
        rebalance_result=None,
        drawdown=0.0,
        cumulative_return=0.0,
        cumulative_inflation=0.0,
        events=(),
        debt_snapshot=DebtSnapshot(
            loan_balance=Decimal("250"),
            cash_balance=Decimal("0"),
            ltv=Decimal("0.25"),
            net_worth=Decimal("750"),
            ltv_enforcement=True,
            is_repayment=True,
        ),
        is_repayment=True,
    )
    result = SimulationResult(
        timeline=SimulationTimeline(monthly_results=(monthly,)),
        statistics=SimulationStatistics(
            final_wealth=Money(Decimal("750"), Currency.EUR),
            max_drawdown=0.0,
            success=False,
            failure_month=0,
            failure_state="depleted",
            months_simulated=0,
        ),
    )

    codec = SimulationResultCodec()
    serialized = codec.dump(result)
    restored = codec.load(
        serialized.statistics_payload_json, serialized.monthly_payloads_json
    )

    assert restored.statistics.failure_state == "depleted"
    restored_monthly = restored.timeline.monthly_results[0]
    assert restored_monthly.is_repayment is True
    assert restored_monthly.debt_snapshot is not None
    assert restored_monthly.debt_snapshot.loan_balance == Decimal("250")
    assert restored_monthly.debt_snapshot.net_worth == Decimal("750")
    assert restored_monthly.debt_snapshot.is_repayment is True
