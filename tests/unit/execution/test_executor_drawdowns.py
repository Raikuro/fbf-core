"""Integration tests for drawdowns produced by the execution paths."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from fbf.core.domain.model.allocation import AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.cash_flow import ExternalCashFlowSchedule
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import (
    BuyAndHoldAllocationPolicy,
    ConstantAllocationPolicy,
    ConstantWithdrawalPolicy,
    EscalatingWithdrawalPolicy,
    FixedRealWithdrawalPolicy,
    WithdrawalPolicy,
)
from fbf.core.domain.policies.allocation_policy import AllocationPolicy
from fbf.core.domain.policies.frequency import WithdrawalFrequency
from fbf.core.domain.policies.glidepath import GlidepathAllocationPolicy
from fbf.core.domain.policies.part49_withdrawal import Part49WithdrawalPolicy
from fbf.core.domain.policies.part52_withdrawal import Part52WithdrawalPolicy
from fbf.core.execution import (
    DeterministicTrajectory,
    execute_deterministic_trajectory,
)
from fbf.core.execution.pipeline.executor import SimulationExecutor
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition,
    SimulationResult,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.drawdown import FlowTiming
from fbf.core.execution.strategies.drawdown_adapter import (
    compute_optional_drawdown,
    withdrawals_as_contribution_flows,
)
from fbf.core.execution.strategies.numba_executor import NumbaSimulationExecutor
from fbf.core.execution.strategies.part49_buy_and_hold_numba_executor import (
    Part49BuyAndHoldNumbaExecutor,
)
from fbf.core.execution.strategies.part49_numba_executor import Part49NumbaExecutor
from fbf.core.execution.strategies.part52_numba_executor import Part52NumbaExecutor

EQ = AssetClass(id="equity", name="", description="")
BD = AssetClass(id="bond", name="", description="")


def _dataset(returns: list[Decimal]) -> Dataset:
    eq_price = Decimal("100")
    bd_price = Decimal("100")
    current = date(1900, 1, 1)
    snapshots = [
        MarketSnapshot(
            date=current,
            index_levels={EQ: eq_price, BD: bd_price},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("0"),
            is_ath=True,
            is_underwater=False,
            running_ath=eq_price,
        )
    ]
    for change in returns:
        eq_price *= Decimal("1") + change
        bd_price *= Decimal("1") + change
        current = date(
            current.year + (current.month // 12),
            current.month % 12 + 1,
            1,
        )
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
    return Dataset(snapshots=tuple(snapshots), frequency="monthly")


def _context(
    dataset: Dataset,
    horizon: int,
    *,
    allocation_policy: AllocationPolicy,
    withdrawal_policy: WithdrawalPolicy,
    external_cash_flow_schedule: ExternalCashFlowSchedule | None = None,
    loan_draw_rate: Decimal | None = None,
    interest_rate: Decimal | None = None,
    ltv_limit: Decimal | None = None,
    ltv_enforcement: bool = True,
) -> SimulationContext:
    wealth = Money(Decimal("1000000"), Currency.EUR)
    from fbf.core.study.builder import build_initial_portfolio

    return SimulationContext(
        experiment_name="drawdown",
        cohort="c",
        start_date=dataset[0].date,
        horizon_months=horizon,
        initial_wealth=wealth,
        initial_portfolio=build_initial_portfolio(wealth, dataset),
        dataset=dataset.slice(dataset[0].date, horizon),
        allocation_policy=allocation_policy,
        withdrawal_policy=withdrawal_policy,
        external_cash_flow_schedule=external_cash_flow_schedule,
        loan_draw_rate=loan_draw_rate,
        interest_rate=interest_rate,
        ltv_limit=ltv_limit,
        ltv_enforcement=ltv_enforcement,
    )


def _run(context: SimulationContext, *, materialize: bool) -> SimulationResult:
    executor = NumbaSimulationExecutor(materialize_timeline=materialize)
    return executor.execute(
        ExperimentDefinition(
            name="drawdown",
            description="drawdown",
            simulation_contexts=(context,),
        )
    ).simulation_results[0]


def _assert_neutralized_withdrawals(
    context: SimulationContext,
) -> None:
    summary = _run(context, materialize=False)
    materialized = _run(context, materialize=True)
    months = materialized.timeline.monthly_results

    assert summary.statistics.max_drawdown == pytest.approx(0.0, abs=1e-12)
    assert materialized.statistics.max_drawdown == pytest.approx(0.0, abs=1e-12)
    assert summary.statistics.max_drawdown == materialized.statistics.max_drawdown
    assert months[0].drawdown is None
    assert all(
        month.drawdown == pytest.approx(0.0, abs=1e-12) for month in months[1:]
    )


@pytest.mark.parametrize(
    "allocation_policy",
    [
        ConstantAllocationPolicy(Decimal("0.6")),
        BuyAndHoldAllocationPolicy(Decimal("0.6")),
        GlidepathAllocationPolicy(
            Decimal("0.6"), Decimal("0.8"), Decimal("0.01"), "passive"
        ),
    ],
    ids=["constant", "buy-and-hold", "glidepath"],
)
def test_fixed_real_family_neutralizes_withdrawals(
    allocation_policy: AllocationPolicy,
) -> None:
    horizon = 24
    context = _context(
        _dataset([Decimal("0")] * horizon),
        horizon,
        allocation_policy=allocation_policy,
        withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.04")),
    )

    _assert_neutralized_withdrawals(context)


@pytest.mark.parametrize(
    ("allocation_policy", "frequency"),
    [
        (ConstantAllocationPolicy(Decimal("0.6")), WithdrawalFrequency.MONTHLY),
        (ConstantAllocationPolicy(Decimal("0.6")), WithdrawalFrequency.ANNUAL),
        (GlidepathAllocationPolicy(
            Decimal("0.6"), Decimal("0.8"), Decimal("0.01"), "passive"
        ), WithdrawalFrequency.MONTHLY),
    ],
    ids=["constant-monthly", "constant-annual", "glidepath-monthly"],
)
def test_escalating_family_neutralizes_withdrawals(
    allocation_policy: AllocationPolicy,
    frequency: WithdrawalFrequency,
) -> None:
    horizon = 24
    context = _context(
        _dataset([Decimal("0")] * horizon),
        horizon,
        allocation_policy=allocation_policy,
        withdrawal_policy=EscalatingWithdrawalPolicy(
            Decimal("0.04"),
            Decimal("0.02"),
            frequency=frequency,
        ),
    )

    _assert_neutralized_withdrawals(context)


def test_constant_nominal_family_neutralizes_withdrawals() -> None:
    horizon = 24
    context = _context(
        _dataset([Decimal("0")] * horizon),
        horizon,
        allocation_policy=ConstantAllocationPolicy(Decimal("0.6")),
        withdrawal_policy=ConstantWithdrawalPolicy(Decimal("0.04")),
    )

    _assert_neutralized_withdrawals(context)


def test_workbook_drawdown_tracks_flow_adjusted_loss() -> None:
    horizon = 12
    returns = [
        Decimal("0.10"),
        Decimal("-0.20"),
        Decimal("0.05"),
        Decimal("0.03"),
        Decimal("-0.10"),
        Decimal("0.04"),
        Decimal("0.02"),
        Decimal("-0.15"),
        Decimal("0.06"),
        Decimal("0.01"),
        Decimal("0.00"),
        Decimal("0.00"),
    ]
    dataset = _dataset(returns)
    context = _context(
        dataset,
        horizon,
        allocation_policy=ConstantAllocationPolicy(Decimal("0.6")),
        withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.04")),
    )

    result = _run(context, materialize=True)
    index = Decimal("1")
    peak = Decimal("1")
    expected: list[float] = [0.0]
    for change in returns[: horizon - 1]:
        index *= Decimal("1") + change
        peak = max(peak, index)
        expected.append(float(max(Decimal("0"), Decimal("1") - index / peak)))

    actual = result.timeline.monthly_results
    assert actual[0].drawdown is None
    for month, expected_drawdown in zip(actual[1:], expected[1:], strict=True):
        assert month.drawdown == pytest.approx(expected_drawdown, abs=1e-12)
    assert result.statistics.max_drawdown == pytest.approx(max(expected), abs=1e-12)


def test_constant_nominal_drawdown_tracks_flow_adjusted_loss() -> None:
    horizon = 12
    returns = [
        Decimal("0.08"),
        Decimal("-0.25"),
        Decimal("0.03"),
        Decimal("0.01"),
        Decimal("-0.12"),
        Decimal("0.04"),
        Decimal("0.02"),
        Decimal("0.00"),
        Decimal("0.01"),
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.00"),
    ]
    dataset = _dataset(returns)
    context = _context(
        dataset,
        horizon,
        allocation_policy=ConstantAllocationPolicy(Decimal("0.6")),
        withdrawal_policy=ConstantWithdrawalPolicy(Decimal("0.04")),
    )

    result = _run(context, materialize=True)
    index = Decimal("1")
    peak = Decimal("1")
    expected: list[float] = [0.0]
    for change in returns[: horizon - 1]:
        index *= Decimal("1") + change
        peak = max(peak, index)
        expected.append(float(max(Decimal("0"), Decimal("1") - index / peak)))

    actual = result.timeline.monthly_results
    assert actual[0].drawdown is None
    for month, expected_drawdown in zip(actual[1:], expected[1:], strict=True):
        assert month.drawdown == pytest.approx(expected_drawdown, abs=1e-12)
    assert result.statistics.max_drawdown == pytest.approx(max(expected), abs=1e-12)


def test_deterministic_drawdowns_are_flow_adjusted() -> None:
    horizon = 24
    dataset = _dataset([Decimal("0")] * horizon)
    trajectory = DeterministicTrajectory(
        name="deterministic",
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        initial_allocation=AllocationTarget(
            weights={EQ: Decimal("0.6"), BD: Decimal("0.4")}
        ),
        dataset=dataset,
        allocation_policy=ConstantAllocationPolicy(Decimal("0.6")),
        withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.04")),
        horizon_months=horizon,
    )

    result = execute_deterministic_trajectory(trajectory)

    assert result.timeline[0].drawdown is None
    assert all(
        month.drawdown == pytest.approx(0.0, abs=1e-12)
        for month in result.timeline[1:]
    )

def test_workbook_external_cash_flows_are_neutralized() -> None:
    horizon = 12
    returns = [
        Decimal("0.05"),
        Decimal("-0.10"),
        Decimal("0.04"),
        Decimal("0.03"),
        Decimal("-0.08"),
        Decimal("0.02"),
        Decimal("0.01"),
        Decimal("-0.06"),
        Decimal("0.03"),
        Decimal("0.02"),
        Decimal("0.00"),
        Decimal("0.00"),
    ]
    dataset = _dataset(returns)
    context = _context(
        dataset,
        horizon,
        allocation_policy=ConstantAllocationPolicy(Decimal("0.6")),
        withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.04")),
        external_cash_flow_schedule=ExternalCashFlowSchedule(
            start_period=2,
            end_period=7,
            monthly_amount=Money(Decimal("5000"), Currency.EUR),
            horizon_transitions=horizon - 1,
        ),
    )

    result = _run(context, materialize=True)
    index = Decimal("1")
    peak = Decimal("1")
    expected: list[float] = [0.0]
    for change in returns[: horizon - 1]:
        index *= Decimal("1") + change
        peak = max(peak, index)
        expected.append(float(max(Decimal("0"), Decimal("1") - index / peak)))

    actual = result.timeline.monthly_results
    assert actual[0].drawdown is None
    for month, expected_drawdown in zip(actual[1:], expected[1:], strict=True):
        assert month.drawdown == pytest.approx(expected_drawdown, abs=1e-12)
    assert result.statistics.max_drawdown == pytest.approx(max(expected), abs=1e-12)

def _run_executor(
    executor: SimulationExecutor, context: SimulationContext
) -> SimulationResult:
    return executor.execute(
        ExperimentDefinition(
            name="drawdown",
            description="drawdown",
            simulation_contexts=(context,),
        )
    ).simulation_results[0]


def _observed_net_worth(result: SimulationResult) -> list[float]:
    values: list[float] = []
    for month in result.timeline.monthly_results:
        if month.debt_snapshot is not None:
            values.append(float(month.debt_snapshot.net_worth))
        else:
            values.append(float(sum(
                holding.units * month.market_snapshot.index_levels[holding.asset_class]
                for holding in month.portfolio.holdings
            )))
    return values


def test_part49_drawdowns_use_net_worth_and_total_spending() -> None:
    horizon = 24
    returns = [
        Decimal("0.04"),
        Decimal("-0.15"),
        Decimal("0.03"),
        Decimal("0.02"),
        Decimal("-0.08"),
        Decimal("0.05"),
        Decimal("0.01"),
        Decimal("-0.04"),
        Decimal("0.02"),
        Decimal("0.01"),
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.03"),
        Decimal("-0.10"),
        Decimal("0.02"),
        Decimal("0.01"),
        Decimal("-0.05"),
        Decimal("0.04"),
        Decimal("0.02"),
        Decimal("0.00"),
        Decimal("0.01"),
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.00"),
    ]
    context = _context(
        _dataset(returns),
        horizon,
        allocation_policy=ConstantAllocationPolicy(Decimal("0.6")),
        withdrawal_policy=Part49WithdrawalPolicy(Decimal("0.04")),
        loan_draw_rate=Decimal("0.02"),
        interest_rate=Decimal("0"),
        ltv_enforcement=False,
    )

    summary_executor = Part49NumbaExecutor(materialize_timeline=False)
    timeline_executor = Part49NumbaExecutor(materialize_timeline=True)
    summary = _run_executor(summary_executor, context)
    materialized = _run_executor(timeline_executor, context)
    net_worth = _observed_net_worth(materialized)
    total_spending = (
        Decimal("1000000") * Decimal("0.04") / Decimal("12")
        + Decimal("1000000") * Decimal("0.02") / Decimal("12")
    )
    expected = compute_optional_drawdown(
        net_worth,
        withdrawals_as_contribution_flows([total_spending] * len(net_worth)),
        flow_timing=FlowTiming.END,
    )

    for month, expected_drawdown in zip(
        materialized.timeline.monthly_results,
        expected.drawdowns,
        strict=True,
    ):
        if expected_drawdown is None:
            assert month.drawdown is None
        else:
            assert month.drawdown == pytest.approx(expected_drawdown, abs=1e-15)
    assert materialized.statistics.max_drawdown == pytest.approx(
        expected.max_drawdown, abs=1e-15
    )
    assert summary.statistics.max_drawdown == pytest.approx(
        expected.max_drawdown, abs=1e-15
    )
    assert materialized.timeline.monthly_results[0].drawdown is None


def test_part49_buy_and_hold_drawdowns_use_net_worth() -> None:
    horizon = 18
    returns = [
        Decimal("0.03"),
        Decimal("-0.12"),
        Decimal("0.02"),
        Decimal("0.01"),
        Decimal("-0.06"),
        Decimal("0.04"),
        Decimal("0.01"),
        Decimal("-0.03"),
        Decimal("0.02"),
        Decimal("0.01"),
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.03"),
        Decimal("-0.08"),
        Decimal("0.02"),
        Decimal("0.01"),
        Decimal("-0.04"),
        Decimal("0.03"),
    ]
    context = _context(
        _dataset(returns),
        horizon,
        allocation_policy=BuyAndHoldAllocationPolicy(Decimal("0.6")),
        withdrawal_policy=Part49WithdrawalPolicy(Decimal("0.04")),
        loan_draw_rate=Decimal("0.02"),
        interest_rate=Decimal("0"),
        ltv_enforcement=False,
    )

    materialized = _run_executor(
        Part49BuyAndHoldNumbaExecutor(materialize_timeline=True), context
    )
    net_worth = _observed_net_worth(materialized)
    total_spending = (
        Decimal("1000000") * Decimal("0.04") / Decimal("12")
        + Decimal("1000000") * Decimal("0.02") / Decimal("12")
    )
    expected = compute_optional_drawdown(
        net_worth,
        withdrawals_as_contribution_flows([total_spending] * len(net_worth)),
        flow_timing=FlowTiming.END,
    )

    for month, expected_drawdown in zip(
        materialized.timeline.monthly_results,
        expected.drawdowns,
        strict=True,
    ):
        if expected_drawdown is None:
            assert month.drawdown is None
        else:
            assert month.drawdown == pytest.approx(expected_drawdown, abs=1e-15)
    assert materialized.statistics.max_drawdown == pytest.approx(
        expected.max_drawdown, abs=1e-15
    )


def test_part52_drawdowns_use_net_worth_and_consumption() -> None:
    horizon = 24
    returns = [
        Decimal("0.02"),
        Decimal("-0.12"),
        Decimal("0.03"),
        Decimal("0.01"),
        Decimal("-0.07"),
        Decimal("0.05"),
        Decimal("0.01"),
        Decimal("-0.03"),
        Decimal("0.02"),
        Decimal("0.01"),
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.03"),
        Decimal("-0.09"),
        Decimal("0.02"),
        Decimal("0.01"),
        Decimal("-0.04"),
        Decimal("0.03"),
        Decimal("0.02"),
        Decimal("0.00"),
        Decimal("0.01"),
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.00"),
    ]
    context = _context(
        _dataset(returns),
        horizon,
        allocation_policy=ConstantAllocationPolicy(Decimal("0.6")),
        withdrawal_policy=Part52WithdrawalPolicy(
            Decimal("0.04"),
            Decimal("0.5"),
            Decimal("0"),
        ),
        interest_rate=Decimal("0"),
        ltv_enforcement=False,
    )

    summary = _run_executor(Part52NumbaExecutor(materialize_timeline=False), context)
    materialized = _run_executor(
        Part52NumbaExecutor(materialize_timeline=True), context
    )
    net_worth = _observed_net_worth(materialized)
    withdrawal = Decimal("1000000") * Decimal("0.04") / Decimal("12")
    withdrawal_amounts = [withdrawal] * len(net_worth)
    if materialized.statistics.success:
        withdrawal_amounts[-1] = Decimal("0")
    expected = compute_optional_drawdown(
        net_worth,
        withdrawals_as_contribution_flows(withdrawal_amounts),
        flow_timing=FlowTiming.END,
    )

    for month, expected_drawdown in zip(
        materialized.timeline.monthly_results,
        expected.drawdowns,
        strict=True,
    ):
        if expected_drawdown is None:
            assert month.drawdown is None
        else:
            assert month.drawdown == pytest.approx(expected_drawdown, abs=1e-15)
    assert materialized.statistics.max_drawdown == pytest.approx(
        expected.max_drawdown, abs=1e-15
    )
    assert summary.statistics.max_drawdown == pytest.approx(
        expected.max_drawdown, abs=1e-15
    )
    assert materialized.timeline.monthly_results[0].drawdown is None
