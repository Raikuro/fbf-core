"""Differential tests for the dedicated deterministic two-asset kernel."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from fbf.core.domain.model.allocation import AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import (
    BuyAndHoldAllocationPolicy,
    ConstantAllocationPolicy,
    ConstantWithdrawalPolicy,
    EscalatingWithdrawalPolicy,
    FixedRealWithdrawalPolicy,
)
from fbf.core.domain.policies.frequency import WithdrawalFrequency
from fbf.core.domain.policies.glidepath import GlidepathAllocationPolicy, GlidepathCadence
from fbf.core.execution import (
    DeterministicTrajectory,
    UnsupportedConfigurationError,
    execute_deterministic_trajectory,
)
from fbf.core.execution.pipeline.schedule import ExecutionSchedule, StepCadence
from fbf.core.execution.pipeline.simulation import MonthlyResult
from fbf.core.execution.pipeline.steps.portfolio_rebalance_step import (
    PortfolioRebalanceStep,
)

from .deterministic_reference import ReferenceResult, simulate_reference

_EQUITY = AssetClass(id="equity", name="", description="")
_BOND = AssetClass(id="bond", name="", description="")
_FEE = Decimal("0.0005")


def _make_dataset(horizon: int, *, pattern: str = "volatile") -> Dataset:
    snapshots: list[MarketSnapshot] = []
    current_date = date(1929, 9, 1)
    equity = Decimal("100")
    bond = Decimal("100")
    running_ath = equity

    for month in range(horizon):
        if pattern == "flat":
            pass
        elif pattern == "volatile":
            if month % 3 == 0:
                equity *= Decimal("1.06")
            elif month % 3 == 1:
                equity *= Decimal("0.98")
            else:
                equity *= Decimal("1.03")
            bond *= Decimal("1.004") if month % 2 == 0 else Decimal("1.001")
        elif pattern == "jump":
            if month == 1:
                equity *= Decimal("1.10")
        else:
            raise ValueError(pattern)

        running_ath = max(running_ath, equity)
        snapshots.append(
            MarketSnapshot(
                date=current_date,
                index_levels={_EQUITY: equity, _BOND: bond},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=equity >= running_ath,
                is_underwater=equity < running_ath,
                running_ath=running_ath,
            )
        )
        if current_date.month == 12:
            current_date = current_date.replace(year=current_date.year + 1, month=1)
        else:
            current_date = current_date.replace(month=current_date.month + 1)

    return Dataset(snapshots=tuple(snapshots), frequency="monthly")


def _annual_schedule() -> ExecutionSchedule:
    return ExecutionSchedule({PortfolioRebalanceStep: StepCadence.ANNUAL})


def _trajectory(
    dataset: Dataset,
    allocation_policy: (
        ConstantAllocationPolicy
        | GlidepathAllocationPolicy
        | BuyAndHoldAllocationPolicy
    ),
    withdrawal_policy: (
        ConstantWithdrawalPolicy
        | FixedRealWithdrawalPolicy
        | EscalatingWithdrawalPolicy
    ),
    *,
    initial_equity: Decimal,
    horizon: int | None = None,
    fee: Decimal = _FEE,
    schedule: ExecutionSchedule | None = None,
    rebalance_cadence: StepCadence | None = None,
) -> DeterministicTrajectory:
    return DeterministicTrajectory(
        name="test",
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        initial_allocation=AllocationTarget(
            weights={_EQUITY: initial_equity, _BOND: Decimal("1") - initial_equity}
        ),
        dataset=dataset,
        allocation_policy=allocation_policy,
        withdrawal_policy=withdrawal_policy,
        horizon_months=horizon if horizon is not None else len(dataset),
        expense_ratio=fee,
        schedule=schedule,
        rebalance_cadence=rebalance_cadence,
    )


def _target_weights(trajectory: DeterministicTrajectory) -> tuple[Decimal, ...]:
    policy = trajectory.allocation_policy
    if isinstance(policy, ConstantAllocationPolicy):
        if policy.allocations is not None:
            weight = dict(policy.allocations)["equity"]
        else:
            assert policy.equity_allocation is not None
            weight = policy.equity_allocation
        return tuple(weight for _ in range(trajectory.horizon_months))

    assert isinstance(policy, GlidepathAllocationPolicy)
    result: list[Decimal] = []
    for month in range(trajectory.horizon_months):
        if policy.cadence is GlidepathCadence.ANNUAL:
            advancement = month // 12
        elif policy.mode == "passive":
            advancement = month
        else:
            advancement = sum(
                1
                for index in range(month + 1)
                if trajectory.dataset[index].is_underwater
            )
        result.append(
            min(policy.start_equity + policy.slope * advancement, policy.end_equity)
        )
    return tuple(result)


def _withdrawal_inputs(
    trajectory: DeterministicTrajectory,
) -> tuple[tuple[Decimal, ...] | None, Decimal | None, bool]:
    policy = trajectory.withdrawal_policy
    if isinstance(policy, ConstantWithdrawalPolicy):
        return (
            None,
            policy.withdrawal_rate,
            policy.frequency is WithdrawalFrequency.ANNUAL,
        )

    annual = policy.frequency is WithdrawalFrequency.ANNUAL
    base = trajectory.initial_wealth.amount
    amounts: list[Decimal] = []
    if isinstance(policy, FixedRealWithdrawalPolicy):
        amount = base * policy.withdrawal_rate
        if not annual:
            amount /= Decimal("12")
        for month in range(trajectory.horizon_months):
            amounts.append(amount if not annual or month % 12 == 0 else Decimal("0"))
    else:
        assert isinstance(policy, EscalatingWithdrawalPolicy)
        for month in range(trajectory.horizon_months):
            escalated = (
                base
                * policy.withdrawal_rate
                * (Decimal("1") + policy.escalation_rate) ** (month // 12)
            )
            if annual:
                amounts.append(
                    escalated if month % 12 == 0 else Decimal("0")
                )
            else:
                amounts.append(escalated / Decimal("12"))
    return tuple(amounts), None, annual


def _reference_for(trajectory: DeterministicTrajectory) -> ReferenceResult:
    equity_prices = tuple(
        trajectory.dataset[month].index_levels[_EQUITY]
        for month in range(trajectory.horizon_months)
    )
    bond_prices = tuple(
        trajectory.dataset[month].index_levels[_BOND]
        for month in range(trajectory.horizon_months)
    )
    targets = _target_weights(trajectory)
    fixed, rate, annual = _withdrawal_inputs(trajectory)

    if trajectory.rebalance_cadence is not None:
        cadence = trajectory.rebalance_cadence
    elif trajectory.schedule is not None:
        cadence = trajectory.schedule.rebalance_cadence()
    else:
        cadence = StepCadence.EVERY_PERIOD
    rebalance_flags = tuple(
        month % 12 == 0 if cadence is StepCadence.ANNUAL else True
        for month in range(trajectory.horizon_months)
    )

    return simulate_reference(
        equity_prices,
        bond_prices,
        targets,
        rebalance_flags,
        fixed_withdrawal_amounts=fixed,
        proportional_rate=rate,
        proportional_annual=annual,
        fee_annual=trajectory.expense_ratio,
        initial_wealth=trajectory.initial_wealth.amount,
        initial_equity_weight=trajectory.initial_allocation.weights[_EQUITY],
        horizon=trajectory.horizon_months,
    )


def _assert_close(actual: Decimal, expected: Decimal, tolerance: Decimal) -> None:
    assert abs(actual - expected) <= tolerance, (actual, expected)


def _actual_equity_weight(checkpoint: MonthlyResult) -> Decimal:
    assert checkpoint.allocation is not None
    return checkpoint.allocation.weights[_EQUITY]


def _withdrawal_amount(checkpoint: MonthlyResult) -> Decimal:
    assert checkpoint.withdrawal_decision is not None
    return checkpoint.withdrawal_decision.nominal_amount.amount


def _assert_matches_reference(
    result: object,
    reference: ReferenceResult,
) -> None:
    from fbf.core.execution import DeterministicResult

    assert isinstance(result, DeterministicResult)
    assert result.success is reference.success
    assert result.failure_period == reference.failure_month
    assert len(result.timeline) == len(reference.values)

    value_tolerance = Decimal("0.000001")
    weight_tolerance = Decimal("0.000000001")

    for month, expected in enumerate(reference.values):
        checkpoint = result.checkpoints[month]
        assert checkpoint.allocation is not None
        assert checkpoint.allocation_target is not None
        value = sum(
            (
                holding.units
                * checkpoint.market_snapshot.index_levels[holding.asset_class]
                for holding in checkpoint.portfolio.holdings
            ),
            Decimal("0"),
        )
        _assert_close(value, expected, value_tolerance)
        _assert_close(
            checkpoint.allocation.weights[_EQUITY],
            reference.actual_equity_weights[month],
            weight_tolerance,
        )
        _assert_close(
            checkpoint.allocation_target.weights[_EQUITY],
            reference.target_equity_weights[month],
            weight_tolerance,
        )
        assert checkpoint.withdrawal_decision is not None
        _assert_close(
            checkpoint.withdrawal_decision.nominal_amount.amount,
            reference.withdrawals[month],
            value_tolerance,
        )


class TestKernelReferenceEquivalence:
    def test_static_annual_rebalance_with_fee_and_drift(self) -> None:
        dataset = _make_dataset(36)
        trajectory = _trajectory(
            dataset,
            ConstantAllocationPolicy(equity_allocation=Decimal("0.80")),
            EscalatingWithdrawalPolicy(
                withdrawal_rate=Decimal("0.035"),
                escalation_rate=Decimal("0.02"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            initial_equity=Decimal("0.80"),
            schedule=_annual_schedule(),
        )

        _assert_matches_reference(
            execute_deterministic_trajectory(trajectory),
            _reference_for(trajectory),
        )

    def test_static_annual_rebalance_uses_explicit_cadence(self) -> None:
        dataset = _make_dataset(36)
        trajectory = _trajectory(
            dataset,
            ConstantAllocationPolicy(equity_allocation=Decimal("0.80")),
            EscalatingWithdrawalPolicy(
                withdrawal_rate=Decimal("0.035"),
                escalation_rate=Decimal("0.02"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            initial_equity=Decimal("0.80"),
            rebalance_cadence=StepCadence.ANNUAL,
        )

        _assert_matches_reference(
            execute_deterministic_trajectory(trajectory),
            _reference_for(trajectory),
        )

    def test_monthly_rebalance_with_fee(self) -> None:
        dataset = _make_dataset(24)
        trajectory = _trajectory(
            dataset,
            ConstantAllocationPolicy(equity_allocation=Decimal("0.60")),
            FixedRealWithdrawalPolicy(
                withdrawal_rate=Decimal("0.04"),
                frequency=WithdrawalFrequency.MONTHLY,
            ),
            initial_equity=Decimal("0.60"),
            schedule=None,
        )

        _assert_matches_reference(
            execute_deterministic_trajectory(trajectory),
            _reference_for(trajectory),
        )

    def test_annual_glidepath_with_fee(self) -> None:
        dataset = _make_dataset(36)
        trajectory = _trajectory(
            dataset,
            GlidepathAllocationPolicy(
                start_equity=Decimal("0.70"),
                end_equity=Decimal("0.90"),
                slope=Decimal("0.02"),
                mode="passive",
                cadence=GlidepathCadence.ANNUAL,
            ),
            FixedRealWithdrawalPolicy(
                withdrawal_rate=Decimal("0.035"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            initial_equity=Decimal("0.70"),
            schedule=_annual_schedule(),
        )

        _assert_matches_reference(
            execute_deterministic_trajectory(trajectory),
            _reference_for(trajectory),
        )


class TestFeeConvention:
    def test_fee_is_charged_additively_on_beginning_value(self) -> None:
        dataset = _make_dataset(3, pattern="jump")
        trajectory = _trajectory(
            dataset,
            ConstantAllocationPolicy(equity_allocation=Decimal("1")),
            ConstantWithdrawalPolicy(
                withdrawal_rate=Decimal("0"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            initial_equity=Decimal("1"),
            schedule=_annual_schedule(),
        )

        result = execute_deterministic_trajectory(trajectory)
        fee_monthly = _FEE / Decimal("12")
        expected_p1 = (
            Decimal("1000000")
            * (Decimal("1.10") - fee_monthly)
        )
        wrong_multiplicative = (
            Decimal("1000000")
            * Decimal("1.10")
            * (Decimal("1") - fee_monthly)
        )

        checkpoint = result.checkpoints[1]
        actual_p1 = sum(
            (
                holding.units
                * checkpoint.market_snapshot.index_levels[holding.asset_class]
                for holding in checkpoint.portfolio.holdings
            ),
            Decimal("0"),
        )
        _assert_close(actual_p1, expected_p1, Decimal("0.000001"))
        assert abs(actual_p1 - wrong_multiplicative) > Decimal("4")

    def test_no_fee_at_initial_withdrawal(self) -> None:
        dataset = _make_dataset(1, pattern="flat")
        trajectory = _trajectory(
            dataset,
            ConstantAllocationPolicy(equity_allocation=Decimal("0.60")),
            FixedRealWithdrawalPolicy(
                withdrawal_rate=Decimal("0.035"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            initial_equity=Decimal("0.60"),
            horizon=1,
            schedule=_annual_schedule(),
        )

        result = execute_deterministic_trajectory(trajectory)
        checkpoint = result.checkpoints[0]
        value = sum(
            (
                holding.units
                * checkpoint.market_snapshot.index_levels[holding.asset_class]
                for holding in checkpoint.portfolio.holdings
            ),
            Decimal("0"),
        )
        assert value == Decimal("965000")
        assert checkpoint.withdrawal_decision is not None
        assert checkpoint.withdrawal_decision.nominal_amount.amount == Decimal("35000")


class TestRebalanceCadence:
    def test_annual_rebalance_resets_weights_once_per_year(self) -> None:
        dataset = _make_dataset(36)
        trajectory = _trajectory(
            dataset,
            ConstantAllocationPolicy(equity_allocation=Decimal("0.80")),
            FixedRealWithdrawalPolicy(
                withdrawal_rate=Decimal("0"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            initial_equity=Decimal("0.80"),
            fee=Decimal("0"),
            schedule=_annual_schedule(),
        )

        result = execute_deterministic_trajectory(trajectory)
        assert _actual_equity_weight(result.checkpoints[1]) != Decimal("0.80")
        _assert_close(
            _actual_equity_weight(result.checkpoints[12]),
            Decimal("0.80"),
            Decimal("1e-12"),
        )
        assert _actual_equity_weight(result.checkpoints[13]) != Decimal("0.80")
        _assert_close(
            _actual_equity_weight(result.checkpoints[24]),
            Decimal("0.80"),
            Decimal("1e-12"),
        )

    def test_monthly_rebalance_pins_weights_every_month(self) -> None:
        dataset = _make_dataset(24)
        trajectory = _trajectory(
            dataset,
            ConstantAllocationPolicy(equity_allocation=Decimal("0.80")),
            FixedRealWithdrawalPolicy(
                withdrawal_rate=Decimal("0"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            initial_equity=Decimal("0.80"),
            fee=Decimal("0"),
            schedule=None,
        )

        result = execute_deterministic_trajectory(trajectory)
        for month in (1, 11, 12, 13, 23):
            _assert_close(
                _actual_equity_weight(result.checkpoints[month]),
                Decimal("0.80"),
                Decimal("1e-12"),
            )


class TestWithdrawalAndFailureSemantics:
    def test_annual_escalating_withdrawal_boundaries(self) -> None:
        dataset = _make_dataset(120)
        trajectory = _trajectory(
            dataset,
            ConstantAllocationPolicy(equity_allocation=Decimal("0.80")),
            EscalatingWithdrawalPolicy(
                withdrawal_rate=Decimal("0.035"),
                escalation_rate=Decimal("0.02"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            initial_equity=Decimal("0.80"),
            schedule=_annual_schedule(),
        )

        result = execute_deterministic_trajectory(trajectory)
        for month in (1, 11, 13, 23):
            assert _withdrawal_amount(result.checkpoints[month]) == Decimal("0")
        assert _withdrawal_amount(result.checkpoints[0]) == Decimal("35000")
        assert _withdrawal_amount(result.checkpoints[12]) == Decimal("35700")
        expected_year_10 = Decimal("35000") * (Decimal("1.02") ** 9)
        assert _withdrawal_amount(result.checkpoints[108]) == expected_year_10
        assert _withdrawal_amount(result.checkpoints[119]) == Decimal("0")

    def test_depletion_stops_at_failure_month(self) -> None:
        dataset = _make_dataset(24, pattern="flat")
        trajectory = DeterministicTrajectory(
            name="depletion",
            initial_wealth=Money(Decimal("1000"), Currency.EUR),
            initial_allocation=AllocationTarget(
                weights={_EQUITY: Decimal("0.60"), _BOND: Decimal("0.40")}
            ),
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(
                equity_allocation=Decimal("0.60")
            ),
            withdrawal_policy=FixedRealWithdrawalPolicy(
                withdrawal_rate=Decimal("0.60"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            horizon_months=24,
            expense_ratio=Decimal("0"),
            schedule=_annual_schedule(),
        )

        result = execute_deterministic_trajectory(trajectory)
        assert result.success is False
        assert result.failure_period == 12
        assert result.failure_state == "depleted"
        assert result.final_wealth.amount == Decimal("0")
        assert len(result.timeline) == 12
        assert 12 not in result.checkpoints

    def test_exact_boundary_withdrawal_succeeds_with_zero(self) -> None:
        dataset = _make_dataset(1, pattern="flat")
        trajectory = DeterministicTrajectory(
            name="exact-boundary",
            initial_wealth=Money(Decimal("1000"), Currency.EUR),
            initial_allocation=AllocationTarget(
                weights={_EQUITY: Decimal("0.60"), _BOND: Decimal("0.40")}
            ),
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(
                equity_allocation=Decimal("0.60")
            ),
            withdrawal_policy=FixedRealWithdrawalPolicy(
                withdrawal_rate=Decimal("1"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            horizon_months=1,
            expense_ratio=Decimal("0"),
            schedule=_annual_schedule(),
        )

        result = execute_deterministic_trajectory(trajectory)
        assert result.success is True
        assert result.final_wealth.amount == Decimal("0")
        assert len(result.timeline) == 1
        assert _actual_equity_weight(result.checkpoints[0]) == Decimal("0.60")

    def test_zero_valued_asset_position_is_supported(self) -> None:
        dataset = _make_dataset(12)
        trajectory = _trajectory(
            dataset,
            ConstantAllocationPolicy(equity_allocation=Decimal("1")),
            FixedRealWithdrawalPolicy(
                withdrawal_rate=Decimal("0.035"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            initial_equity=Decimal("1"),
            schedule=_annual_schedule(),
        )

        result = execute_deterministic_trajectory(trajectory)
        assert result.success is True
        for checkpoint in result.timeline:
            assert checkpoint.allocation is not None
            assert checkpoint.allocation.weights[_BOND] == Decimal("0")
            assert checkpoint.allocation.weights[_EQUITY] == Decimal("1")


class TestFallbackPolicy:
    def test_fee_free_unsupported_configuration_uses_legacy_pipeline(self) -> None:
        dataset = _make_dataset(12)
        trajectory = _trajectory(
            dataset,
            BuyAndHoldAllocationPolicy(equity_allocation=Decimal("0.60")),
            FixedRealWithdrawalPolicy(
                withdrawal_rate=Decimal("0.04"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            initial_equity=Decimal("0.60"),
            fee=Decimal("0"),
            schedule=_annual_schedule(),
        )

        result = execute_deterministic_trajectory(trajectory)
        assert result.success is True
        assert len(result.timeline) == 12

    def test_nonzero_fee_unsupported_configuration_raises(self) -> None:
        dataset = _make_dataset(12)
        trajectory = _trajectory(
            dataset,
            BuyAndHoldAllocationPolicy(equity_allocation=Decimal("0.60")),
            FixedRealWithdrawalPolicy(
                withdrawal_rate=Decimal("0.04"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            initial_equity=Decimal("0.60"),
            fee=_FEE,
            schedule=_annual_schedule(),
        )

        with pytest.raises(
            UnsupportedConfigurationError,
            match="non-zero expense ratio",
        ):
            execute_deterministic_trajectory(trajectory)
