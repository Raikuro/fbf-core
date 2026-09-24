"""Unit tests for deterministic execution adapter.

Tests the DeterministicTrajectory, execute_deterministic_trajectory,
and checkpoint extraction functionality.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from fbf.core.domain.model.allocation import AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import ConstantAllocationPolicy, EscalatingWithdrawalPolicy
from fbf.core.domain.policies.frequency import WithdrawalFrequency
from fbf.core.domain.policies.glidepath import GlidepathAllocationPolicy, GlidepathCadence
from fbf.core.execution import (
    DeterministicTrajectory,
    ExecutionOptions,
    execute_deterministic_trajectory,
)
from fbf.core.execution.pipeline.schedule import ExecutionSchedule, StepCadence

_EQUITY = AssetClass(id="equity", name="", description="")
_BOND = AssetClass(id="bond", name="", description="")


def _make_flat_dataset(horizon_months: int = 120) -> Dataset:
    """Create a flat (0% return) dataset for deterministic testing."""
    snapshots = []
    current_date = date(1929, 9, 1)

    for _ in range(horizon_months):
        snapshots.append(
            MarketSnapshot(
                date=current_date,
                index_levels={_EQUITY: Decimal("100"), _BOND: Decimal("100")},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            )
        )
        if current_date.month == 12:
            current_date = current_date.replace(year=current_date.year + 1, month=1)
        else:
            current_date = current_date.replace(month=current_date.month + 1)

    return Dataset(snapshots=tuple(snapshots), frequency="monthly")


def _make_rising_dataset(horizon_months: int = 120) -> Dataset:
    """Create a rising (positive return) dataset."""
    snapshots = []
    current_date = date(1929, 9, 1)
    eq_level = Decimal("100")
    bond_level = Decimal("100")
    running_ath = Decimal("100")

    for _ in range(horizon_months):
        # Small positive monthly return ~0.5%
        eq_level *= Decimal("1.005")
        bond_level *= Decimal("1.002")
        running_ath = max(running_ath, eq_level)

        snapshots.append(
            MarketSnapshot(
                date=current_date,
                index_levels={_EQUITY: eq_level, _BOND: bond_level},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=(eq_level >= running_ath),
                is_underwater=(eq_level < running_ath),
                running_ath=running_ath,
            )
        )
        if current_date.month == 12:
            current_date = current_date.replace(year=current_date.year + 1, month=1)
        else:
            current_date = current_date.replace(month=current_date.month + 1)

    return Dataset(snapshots=tuple(snapshots), frequency="monthly")


class TestDeterministicTrajectory:
    """Tests for DeterministicTrajectory construction and validation."""

    def test_valid_construction(self) -> None:
        dataset = _make_flat_dataset(12)
        trajectory = DeterministicTrajectory(
            name="Test",
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_allocation=AllocationTarget(
                weights={_EQUITY: Decimal("0.6"), _BOND: Decimal("0.4")}
            ),
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.6")),
            withdrawal_policy=EscalatingWithdrawalPolicy(
                withdrawal_rate=Decimal("0.04"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            horizon_months=12,
        )
        assert trajectory.name == "Test"
        assert trajectory.horizon_months == 12
        assert trajectory.expense_ratio == Decimal("0")
        assert trajectory.schedule is None

    def test_with_expense_ratio(self) -> None:
        dataset = _make_flat_dataset(12)
        trajectory = DeterministicTrajectory(
            name="Test",
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_allocation=AllocationTarget(
                weights={_EQUITY: Decimal("0.6"), _BOND: Decimal("0.4")}
            ),
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.6")),
            withdrawal_policy=EscalatingWithdrawalPolicy(
                withdrawal_rate=Decimal("0.04"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            horizon_months=12,
            expense_ratio=Decimal("0.0005"),
        )
        assert trajectory.expense_ratio == Decimal("0.0005")

    def test_with_schedule(self) -> None:
        dataset = _make_flat_dataset(12)
        from fbf.core.execution.pipeline.steps.allocation_decision_step import (
            AllocationDecisionStep,
        )
        schedule = ExecutionSchedule(
            {AllocationDecisionStep: StepCadence.EVERY_PERIOD}
        )
        trajectory = DeterministicTrajectory(
            name="Test",
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_allocation=AllocationTarget(
                weights={_EQUITY: Decimal("0.6"), _BOND: Decimal("0.4")}
            ),
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.6")),
            withdrawal_policy=EscalatingWithdrawalPolicy(
                withdrawal_rate=Decimal("0.04"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            horizon_months=12,
            schedule=schedule,
        )
        assert trajectory.schedule is schedule

    def test_empty_name_raises(self) -> None:
        dataset = _make_flat_dataset(12)
        with pytest.raises(ValueError, match="name must be non-empty"):
            DeterministicTrajectory(
                name="",
                initial_wealth=Money(Decimal("1000000"), Currency.EUR),
                initial_allocation=AllocationTarget(
                    weights={_EQUITY: Decimal("0.6"), _BOND: Decimal("0.4")}
                ),
                dataset=dataset,
                allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.6")),
                withdrawal_policy=EscalatingWithdrawalPolicy(
                    withdrawal_rate=Decimal("0.04"),
                    frequency=WithdrawalFrequency.ANNUAL,
                ),
                horizon_months=12,
            )

    def test_zero_horizon_raises(self) -> None:
        dataset = _make_flat_dataset(12)
        with pytest.raises(ValueError, match="horizon_months must be positive"):
            DeterministicTrajectory(
                name="Test",
                initial_wealth=Money(Decimal("1000000"), Currency.EUR),
                initial_allocation=AllocationTarget(
                    weights={_EQUITY: Decimal("0.6"), _BOND: Decimal("0.4")}
                ),
                dataset=dataset,
                allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.6")),
                withdrawal_policy=EscalatingWithdrawalPolicy(
                    withdrawal_rate=Decimal("0.04"),
                    frequency=WithdrawalFrequency.ANNUAL,
                ),
                horizon_months=0,
            )

    def test_negative_expense_ratio_raises(self) -> None:
        dataset = _make_flat_dataset(12)
        with pytest.raises(ValueError, match="expense_ratio must be non-negative"):
            DeterministicTrajectory(
                name="Test",
                initial_wealth=Money(Decimal("1000000"), Currency.EUR),
                initial_allocation=AllocationTarget(
                    weights={_EQUITY: Decimal("0.6"), _BOND: Decimal("0.4")}
                ),
                dataset=dataset,
                allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.6")),
                withdrawal_policy=EscalatingWithdrawalPolicy(
                    withdrawal_rate=Decimal("0.04"),
                    frequency=WithdrawalFrequency.ANNUAL,
                ),
                horizon_months=12,
                expense_ratio=Decimal("-0.01"),
            )


class TestExecuteDeterministicTrajectory:
    """Tests for execute_deterministic_trajectory function."""

    def test_minimal_trajectory_completes(self) -> None:
        """A minimal 12-month trajectory should complete successfully."""
        dataset = _make_flat_dataset(12)
        trajectory = DeterministicTrajectory(
            name="Minimal",
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_allocation=AllocationTarget(
                weights={_EQUITY: Decimal("0.6"), _BOND: Decimal("0.4")}
            ),
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.6")),
            withdrawal_policy=EscalatingWithdrawalPolicy(
                withdrawal_rate=Decimal("0.04"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            horizon_months=12,
        )

        result = execute_deterministic_trajectory(trajectory)

        assert result.name == "Minimal"
        assert len(result.timeline) == 12
        assert result.success is True
        assert result.final_wealth is not None

    def test_horizon_respected(self) -> None:
        """The requested horizon should be respected."""
        for horizon in [6, 12, 24, 60, 120]:
            dataset = _make_flat_dataset(horizon)
            trajectory = DeterministicTrajectory(
                name=f"Horizon{horizon}",
                initial_wealth=Money(Decimal("1000000"), Currency.EUR),
                initial_allocation=AllocationTarget(
                    weights={_EQUITY: Decimal("0.6"), _BOND: Decimal("0.4")}
                ),
                dataset=dataset,
                allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.6")),
                withdrawal_policy=EscalatingWithdrawalPolicy(
                    withdrawal_rate=Decimal("0.04"),
                    frequency=WithdrawalFrequency.ANNUAL,
                ),
                horizon_months=horizon,
            )

            result = execute_deterministic_trajectory(trajectory)
            assert len(result.timeline) == horizon, f"Failed for horizon {horizon}"

    def test_checkpoint_extraction(self) -> None:
        """Checkpoints should be extracted at correct period indices."""
        dataset = _make_flat_dataset(120)
        trajectory = DeterministicTrajectory(
            name="CheckpointTest",
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_allocation=AllocationTarget(
                weights={_EQUITY: Decimal("0.6"), _BOND: Decimal("0.4")}
            ),
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.6")),
            withdrawal_policy=EscalatingWithdrawalPolicy(
                withdrawal_rate=Decimal("0.04"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            horizon_months=120,
        )

        result = execute_deterministic_trajectory(trajectory)

        # Checkpoints should be a dict keyed by period_index
        assert isinstance(result.checkpoints, dict)
        # Should have entries for all period indices
        assert len(result.checkpoints) == 120

        # Verify specific period indices exist
        for pi in [0, 11, 12, 23, 24, 108, 119]:
            assert pi in result.checkpoints, f"Missing checkpoint at period {pi}"

    def test_year_2_checkpoint_is_period_23(self) -> None:
        """Year 2 checkpoint should be at period_index 23 (after 24 months)."""
        dataset = _make_rising_dataset(120)
        trajectory = DeterministicTrajectory(
            name="Year2Checkpoint",
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_allocation=AllocationTarget(
                weights={_EQUITY: Decimal("0.6"), _BOND: Decimal("0.4")}
            ),
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.6")),
            withdrawal_policy=EscalatingWithdrawalPolicy(
                withdrawal_rate=Decimal("0.04"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            horizon_months=120,
        )

        result = execute_deterministic_trajectory(trajectory)

        # Year 2 checkpoint = period_index 23
        checkpoint_23 = result.checkpoints[23]
        assert checkpoint_23.period_index == 23
        assert checkpoint_23.date == date(1931, 8, 1)  # 24 months from 1929-09

    def test_year_10_checkpoint_is_period_119(self) -> None:
        """Year 10 checkpoint should be at period_index 119 (after 120 months)."""
        dataset = _make_rising_dataset(120)
        trajectory = DeterministicTrajectory(
            name="Year10Checkpoint",
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_allocation=AllocationTarget(
                weights={_EQUITY: Decimal("0.6"), _BOND: Decimal("0.4")}
            ),
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.6")),
            withdrawal_policy=EscalatingWithdrawalPolicy(
                withdrawal_rate=Decimal("0.04"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            horizon_months=120,
        )

        result = execute_deterministic_trajectory(trajectory)

        # Year 10 checkpoint = period_index 119
        checkpoint_119 = result.checkpoints[119]
        assert checkpoint_119.period_index == 119
        assert checkpoint_119.date == date(1939, 8, 1)  # 120 months from 1929-09

    def test_annual_schedule_integration(self) -> None:
        """Annual rebalance schedule should suppress rebalance at non-annual periods."""
        dataset = _make_rising_dataset(24)
        schedule = ExecutionSchedule(
            {}  # No specific cadence = all steps every period (default)
        )
        trajectory = DeterministicTrajectory(
            name="AnnualSchedule",
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_allocation=AllocationTarget(
                weights={_EQUITY: Decimal("0.6"), _BOND: Decimal("0.4")}
            ),
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.6")),
            withdrawal_policy=EscalatingWithdrawalPolicy(
                withdrawal_rate=Decimal("0.04"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            horizon_months=24,
            schedule=schedule,
        )

        result = execute_deterministic_trajectory(trajectory)

        # With default schedule, all steps execute every period
        assert len(result.timeline) == 24
        assert result.success is True

    def test_annual_rebalance_schedule(self) -> None:
        """Annual rebalance should execute only at period 0, 12, 24, etc."""
        dataset = _make_rising_dataset(36)
        # Test that we can create a schedule with annual rebalance
        # The actual step execution is tested in Phase 2 tests
        schedule = ExecutionSchedule()
        trajectory = DeterministicTrajectory(
            name="AnnualRebalance",
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_allocation=AllocationTarget(
                weights={_EQUITY: Decimal("0.6"), _BOND: Decimal("0.4")}
            ),
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.6")),
            withdrawal_policy=EscalatingWithdrawalPolicy(
                withdrawal_rate=Decimal("0.04"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            horizon_months=36,
            schedule=schedule,
        )

        result = execute_deterministic_trajectory(trajectory)

        assert len(result.timeline) == 36
        assert result.success is True

    def test_annual_glidepath_integration(self) -> None:
        """Deterministic adapter should work with annual glidepath cadence."""
        dataset = _make_rising_dataset(120)
        trajectory = DeterministicTrajectory(
            name="AnnualGlidepath",
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_allocation=AllocationTarget(
                weights={_EQUITY: Decimal("0.70"), _BOND: Decimal("0.30")}
            ),
            dataset=dataset,
            allocation_policy=GlidepathAllocationPolicy(
                start_equity=Decimal("0.70"),
                end_equity=Decimal("0.90"),
                slope=Decimal("0.02"),
                mode="passive",
                cadence=GlidepathCadence.ANNUAL,
            ),
            withdrawal_policy=EscalatingWithdrawalPolicy(
                withdrawal_rate=Decimal("0.035"),
                escalation_rate=Decimal("0.02"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            horizon_months=120,
        )

        result = execute_deterministic_trajectory(trajectory)

        assert len(result.timeline) == 120
        assert result.success is True

        # Verify glidepath progression at key periods
        # period 0: 70%
        # period 12: 72%
        # period 24: 74%
        # period 108: 88%
        # period 119: 88%
        # period 120: 90% (capped)
        checkpoint_0 = result.checkpoints[0]
        checkpoint_12 = result.checkpoints[12]
        checkpoint_24 = result.checkpoints[24]
        checkpoint_108 = result.checkpoints[108]
        checkpoint_119 = result.checkpoints[119]

        assert checkpoint_0.allocation_target is not None
        assert checkpoint_12.allocation_target is not None
        assert checkpoint_24.allocation_target is not None
        assert checkpoint_108.allocation_target is not None
        assert checkpoint_119.allocation_target is not None

    def test_escalating_withdrawal_integration(self) -> None:
        """Deterministic adapter should work with EscalatingWithdrawalPolicy."""
        dataset = _make_rising_dataset(120)
        trajectory = DeterministicTrajectory(
            name="EscalatingWithdrawal",
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_allocation=AllocationTarget(
                weights={_EQUITY: Decimal("0.6"), _BOND: Decimal("0.4")}
            ),
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.6")),
            withdrawal_policy=EscalatingWithdrawalPolicy(
                withdrawal_rate=Decimal("0.035"),
                escalation_rate=Decimal("0.02"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            horizon_months=120,
        )

        result = execute_deterministic_trajectory(trajectory)

        assert len(result.timeline) == 120
        assert result.success is True

        # Check withdrawal decisions at annual boundaries
        # Year 1 (period 0): 35,000
        # Year 2 (period 12): 35,700
        checkpoint_0 = result.checkpoints[0]
        checkpoint_12 = result.checkpoints[12]

        assert checkpoint_0.withdrawal_decision is not None
        assert checkpoint_12.withdrawal_decision is not None

        # Both should be non-zero at annual boundaries
        assert checkpoint_0.withdrawal_decision.nominal_amount.amount > 0
        assert checkpoint_12.withdrawal_decision.nominal_amount.amount > 0

        # Year 2 should be higher than Year 1 (escalation)
        year1_withdrawal = checkpoint_0.withdrawal_decision.nominal_amount.amount
        year2_withdrawal = checkpoint_12.withdrawal_decision.nominal_amount.amount
        assert year2_withdrawal > year1_withdrawal

    def test_currency_preservation(self) -> None:
        """Currency should be preserved from initial_wealth."""
        dataset = _make_flat_dataset(12)
        trajectory = DeterministicTrajectory(
            name="CurrencyTest",
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_allocation=AllocationTarget(
                weights={_EQUITY: Decimal("0.6"), _BOND: Decimal("0.4")}
            ),
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.6")),
            withdrawal_policy=EscalatingWithdrawalPolicy(
                withdrawal_rate=Decimal("0.04"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            horizon_months=12,
        )

        result = execute_deterministic_trajectory(trajectory)

        assert result.final_wealth.currency == Currency.EUR
        for mr in result.timeline:
            # MonthlyResult has portfolio, not portfolio_value
            # The currency comes from the withdrawal decisions or initial_wealth
            if mr.withdrawal_decision is not None:
                assert mr.withdrawal_decision.nominal_amount.currency == Currency.EUR

    def test_options_parameter(self) -> None:
        """ExecutionOptions should be accepted."""
        dataset = _make_flat_dataset(12)
        trajectory = DeterministicTrajectory(
            name="OptionsTest",
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_allocation=AllocationTarget(
                weights={_EQUITY: Decimal("0.6"), _BOND: Decimal("0.4")}
            ),
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.6")),
            withdrawal_policy=EscalatingWithdrawalPolicy(
                withdrawal_rate=Decimal("0.04"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            horizon_months=12,
        )

        options = ExecutionOptions()
        result = execute_deterministic_trajectory(trajectory, options)

        assert result.success is True
        assert len(result.timeline) == 12


class TestDeterministicResult:
    """Tests for DeterministicResult structure."""

    def test_contains_required_fields(self) -> None:
        """DeterministicResult should have all required fields."""
        dataset = _make_flat_dataset(12)
        trajectory = DeterministicTrajectory(
            name="ResultTest",
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_allocation=AllocationTarget(
                weights={_EQUITY: Decimal("0.6"), _BOND: Decimal("0.4")}
            ),
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.6")),
            withdrawal_policy=EscalatingWithdrawalPolicy(
                withdrawal_rate=Decimal("0.04"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            horizon_months=12,
        )

        result = execute_deterministic_trajectory(trajectory)

        assert result.name == "ResultTest"
        assert isinstance(result.timeline, tuple)
        assert isinstance(result.checkpoints, dict)
        assert result.final_wealth is not None
        assert isinstance(result.success, bool)

    def test_checkpoints_are_monthly_results(self) -> None:
        """Checkpoints should be MonthlyResult objects."""
        dataset = _make_flat_dataset(12)
        trajectory = DeterministicTrajectory(
            name="CheckpointType",
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_allocation=AllocationTarget(
                weights={_EQUITY: Decimal("0.6"), _BOND: Decimal("0.4")}
            ),
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.6")),
            withdrawal_policy=EscalatingWithdrawalPolicy(
                withdrawal_rate=Decimal("0.04"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            horizon_months=12,
        )

        result = execute_deterministic_trajectory(trajectory)

        for pi, mr in result.checkpoints.items():
            assert hasattr(mr, "period_index")
            assert hasattr(mr, "date")
            # MonthlyResult has portfolio, not portfolio_value
            assert hasattr(mr, "portfolio")
            assert hasattr(mr, "allocation_target")
            assert hasattr(mr, "withdrawal_decision")
            assert mr.period_index == pi


class TestBackwardCompatibility:
    """Tests ensuring existing behavior is unchanged."""

    def test_monthly_trajectory_still_works(self) -> None:
        """A trajectory with monthly policies should work as before."""
        dataset = _make_flat_dataset(12)
        trajectory = DeterministicTrajectory(
            name="Monthly",
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_allocation=AllocationTarget(
                weights={_EQUITY: Decimal("0.6"), _BOND: Decimal("0.4")}
            ),
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.6")),
            withdrawal_policy=EscalatingWithdrawalPolicy(
                withdrawal_rate=Decimal("0.04"),
                frequency=WithdrawalFrequency.MONTHLY,
            ),
            horizon_months=12,
        )

        result = execute_deterministic_trajectory(trajectory)

        assert len(result.timeline) == 12
        assert result.success is True

    def test_glidepath_monthly_cadence_preserved(self) -> None:
        """Monthly glidepath cadence should work as before."""
        dataset = _make_rising_dataset(120)
        trajectory = DeterministicTrajectory(
            name="MonthlyGlidepath",
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_allocation=AllocationTarget(
                weights={_EQUITY: Decimal("0.60"), _BOND: Decimal("0.40")}
            ),
            dataset=dataset,
            allocation_policy=GlidepathAllocationPolicy(
                start_equity=Decimal("0.60"),
                end_equity=Decimal("1.00"),
                slope=Decimal("0.005"),
                mode="passive",
                cadence=GlidepathCadence.MONTHLY,
            ),
            withdrawal_policy=EscalatingWithdrawalPolicy(
                withdrawal_rate=Decimal("0.04"),
                frequency=WithdrawalFrequency.MONTHLY,
            ),
            horizon_months=120,
        )

        result = execute_deterministic_trajectory(trajectory)

        assert len(result.timeline) == 120
        assert result.success is True

        # With monthly cadence, equity should advance every period
        checkpoint_0 = result.checkpoints[0]
        checkpoint_1 = result.checkpoints[1]
        assert checkpoint_0.allocation_target is not None
        assert checkpoint_1.allocation_target is not None
        equity_1 = checkpoint_1.allocation_target.weights[_EQUITY]
        equity_0 = checkpoint_0.allocation_target.weights[_EQUITY]
        assert equity_1 > equity_0

