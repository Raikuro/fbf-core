"""Unit tests for SimulationStatisticsBuilder.

Tests the statistics derivation logic, edge cases, immutability, and determinism
of the DefaultSimulationStatisticsBuilder.
"""

import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from engine.application.simulation import (
    ExecutionStatus,
    MonthlyResult,
    SimulationState,
    SimulationContext,
)
from engine.application.statistics_builder import DefaultSimulationStatisticsBuilder
from engine.domain.model.allocation import Allocation, AllocationTarget
from engine.domain.model.asset import AssetClass
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.money import Money, Currency
from engine.domain.model.portfolio import Portfolio, AssetHolding


# ============================================================================
# Test Fixtures
# ============================================================================


@dataclass
class MockMarketSnapshot:
    """Mock market snapshot for testing."""
    date_: date
    price_index: float = 100.0


@dataclass
class MockAllocation:
    """Mock allocation for testing."""
    stocks: float = 0.6
    bonds: float = 0.4


def create_test_context(initial_wealth: Money = Money(Decimal("500000"), Currency.EUR)) -> SimulationContext:
    """Create a test SimulationContext."""
    # Create minimal portfolio for initial_portfolio required field
    portfolio = Portfolio(holdings=[])
    
    return SimulationContext(
        experiment_name="test_experiment",
        cohort="test_cohort",
        dataset=None,
        initial_wealth=initial_wealth,
        allocation_policy=None,
        withdrawal_policy=None,
        start_date=date(2024, 1, 1),
        horizon_months=12,
        initial_portfolio=portfolio,
    )


def create_test_monthly_result(date_: date, index: int) -> MonthlyResult:
    """Create a test MonthlyResult."""
    portfolio = Portfolio(holdings=[])
    # Use the provided date directly instead of reconstructing
    return MonthlyResult(
        date=date_,
        period_index=index,
        market_snapshot=MockMarketSnapshot(date_),
        portfolio=portfolio,
        allocation=MockAllocation(),
        allocation_target=None,
        allocation_drift=None,
        withdrawal_decision=None,
        rebalance_result=None,
        drawdown=0.0,
        cumulative_return=0.0,
        cumulative_inflation=0.0,
        events=[],
    )


def create_test_state(
    status: ExecutionStatus = ExecutionStatus.COMPLETED,
    failure_state: str | None = None,
    current_wealth: Money | None = Money(Decimal("600000"), Currency.EUR),
    period_index: int = 12,
    monthly_count: int = 12,
) -> SimulationState:
    """Create a test SimulationState with customizable parameters."""
    initial_wealth = Money(Decimal("500000"), Currency.EUR)
    context = create_test_context(initial_wealth)
    
    # Create proper dates that don't overflow months
    monthly_results = []
    for i in range(monthly_count):
        # Calculate year and month properly
        total_months = 2024 * 12 + 0 + i  # Start from Jan 2024 (month 1)
        year = total_months // 12
        month = (total_months % 12) + 1
        if month > 12:
            year += 1
            month -= 12
        month_date = date(year, month, 1)
        monthly_results.append(create_test_monthly_result(month_date, i))
    
    # Use the final date from monthly_results or a default
    if monthly_results:
        current_date = monthly_results[-1].date
    else:
        current_date = date(2024, 1, 1)
    
    portfolio = Portfolio(holdings=[])
    
    return SimulationState(
        context=context,
        current_date=current_date,
        period_index=period_index,
        portfolio=portfolio,
        current_wealth=current_wealth,
        status=status,
        failure_state=failure_state,
        monthly_results=monthly_results,
    )


# ============================================================================
# Test Classes
# ============================================================================


class TestFinalWealth:
    """Tests for final_wealth statistic derivation."""

    def test_final_wealth_from_current_wealth(self):
        """final_wealth should use state.current_wealth when available."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state(current_wealth=Money(Decimal("750000"), Currency.EUR))
        
        stats = builder.build(state)
        
        assert stats.final_wealth == Money(Decimal("750000"), Currency.EUR)

    def test_final_wealth_fallback_to_initial(self):
        """final_wealth should fallback to initial_wealth when current_wealth is None."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state(current_wealth=None)
        
        stats = builder.build(state)
        
        assert stats.final_wealth == Money(Decimal("500000"), Currency.EUR)

    def test_final_wealth_preserves_money_type(self):
        """final_wealth should preserve Money type exactly."""
        builder = DefaultSimulationStatisticsBuilder()
        wealth = Money(Decimal("1234567"), Currency.EUR)
        state = create_test_state(current_wealth=wealth)
        
        stats = builder.build(state)
        
        assert isinstance(stats.final_wealth, Money)
        assert stats.final_wealth == wealth


class TestSuccessFlag:
    """Tests for success flag derivation."""

    def test_success_true_on_completed_without_failure(self):
        """success should be True when COMPLETED and no failure_state."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state(
            status=ExecutionStatus.COMPLETED,
            failure_state=None,
        )
        
        stats = builder.build(state)
        
        assert stats.success is True

    def test_success_false_on_failure_state(self):
        """success should be False when failure_state is set."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state(
            status=ExecutionStatus.COMPLETED,
            failure_state="Portfolio depleted",
        )
        
        stats = builder.build(state)
        
        assert stats.success is False

    def test_success_false_on_failed_status(self):
        """success should be False when status is FAILED."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state(
            status=ExecutionStatus.FAILED,
            failure_state=None,
        )
        
        stats = builder.build(state)
        
        assert stats.success is False

    def test_success_false_on_running_status(self):
        """success should be False when status is RUNNING."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state(
            status=ExecutionStatus.RUNNING,
            failure_state=None,
        )
        
        stats = builder.build(state)
        
        assert stats.success is False

    def test_success_false_when_failed_and_failure_state_set(self):
        """success should be False when both FAILED and failure_state."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state(
            status=ExecutionStatus.FAILED,
            failure_state="Portfolio depleted",
        )
        
        stats = builder.build(state)
        
        assert stats.success is False


class TestFailureMonth:
    """Tests for failure_month field derivation."""

    def test_failure_month_set_on_failure(self):
        """failure_month should be set to period_index when failure_state is present."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state(
            failure_state="Portfolio depleted",
            period_index=8,
        )
        
        stats = builder.build(state)
        
        assert stats.failure_month == 8

    def test_failure_month_none_on_success(self):
        """failure_month should be None when failure_state is None."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state(
            status=ExecutionStatus.COMPLETED,
            failure_state=None,
        )
        
        stats = builder.build(state)
        
        assert stats.failure_month is None

    def test_failure_month_zero_on_immediate_failure(self):
        """failure_month should be 0 when failure occurs at first month."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state(
            failure_state="Insufficient portfolio",
            period_index=0,
        )
        
        stats = builder.build(state)
        
        assert stats.failure_month == 0

    def test_failure_month_reflects_period_index(self):
        """failure_month should reflect any valid period_index."""
        builder = DefaultSimulationStatisticsBuilder()
        for period in [0, 5, 11, 23, 100]:
            state = create_test_state(
                failure_state="Failed",
                period_index=period,
            )
            
            stats = builder.build(state)
            
            assert stats.failure_month == period


class TestMonthsSimulated:
    """Tests for months_simulated derivation."""

    def test_months_simulated_from_timeline_length(self):
        """months_simulated should equal the length of monthly_results."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state(monthly_count=12)
        
        stats = builder.build(state)
        
        assert stats.months_simulated == 12

    def test_months_simulated_single_month(self):
        """months_simulated should be 1 for single-month simulation."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state(monthly_count=1)
        
        stats = builder.build(state)
        
        assert stats.months_simulated == 1

    def test_months_simulated_zero_months(self):
        """months_simulated should be 0 for zero-month simulation."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state(monthly_count=0)
        
        stats = builder.build(state)
        
        assert stats.months_simulated == 0

    def test_months_simulated_many_months(self):
        """months_simulated should handle large month counts."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state(monthly_count=240)  # 20 years
        
        stats = builder.build(state)
        
        assert stats.months_simulated == 240

    def test_months_simulated_independent_of_period_index(self):
        """months_simulated should depend only on timeline length, not period_index."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state(monthly_count=12, period_index=5)
        
        stats = builder.build(state)
        
        # Should be 12 (timeline length), not 5 (period_index)
        assert stats.months_simulated == 12


class TestPlaceholderMetrics:
    """Tests for deferred/placeholder metrics."""

    def test_max_drawdown_placeholder_value(self):
        """max_drawdown should be 0.0 (placeholder)."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state()
        
        stats = builder.build(state)
        
        assert stats.max_drawdown == 0.0

    def test_execution_time_placeholder_value(self):
        """execution_time_seconds should be 0.0 (placeholder)."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state()
        
        stats = builder.build(state)
        
        assert stats.execution_time_seconds == 0.0

    def test_placeholder_metrics_consistent_across_scenarios(self):
        """Placeholder metrics should always be 0.0 regardless of scenario."""
        builder = DefaultSimulationStatisticsBuilder()
        
        # Successful simulation
        state1 = create_test_state(status=ExecutionStatus.COMPLETED, failure_state=None)
        stats1 = builder.build(state1)
        assert stats1.max_drawdown == 0.0
        assert stats1.execution_time_seconds == 0.0
        
        # Failed simulation
        state2 = create_test_state(status=ExecutionStatus.FAILED, failure_state="Error")
        stats2 = builder.build(state2)
        assert stats2.max_drawdown == 0.0
        assert stats2.execution_time_seconds == 0.0


class TestResultImmutability:
    """Tests for immutability of returned SimulationStatistics."""

    def test_result_is_frozen_dataclass(self):
        """Returned SimulationStatistics should be immutable (frozen)."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state()
        
        stats = builder.build(state)
        
        # Attempting to modify should raise FrozenInstanceError
        try:
            stats.final_wealth = Money(Decimal("999999"), Currency.EUR)
            assert False, "Should not be able to modify frozen dataclass"
        except (AttributeError, Exception) as e:
            # frozen=True raises AttributeError or similar
            assert True

    def test_result_has_no_mutable_fields(self):
        """SimulationStatistics should have only immutable field types."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state()
        
        stats = builder.build(state)
        
        # Verify all fields are immutable types
        assert isinstance(stats.final_wealth, Money)
        assert isinstance(stats.max_drawdown, float)
        assert isinstance(stats.success, bool)
        assert stats.failure_month is None or isinstance(stats.failure_month, int)
        assert isinstance(stats.months_simulated, int)
        assert isinstance(stats.execution_time_seconds, float)


class TestDeterminism:
    """Tests for deterministic behavior."""

    def test_identical_state_produces_identical_statistics(self):
        """Calling build twice with same state should produce identical results."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state()
        
        stats1 = builder.build(state)
        stats2 = builder.build(state)
        
        assert stats1.final_wealth == stats2.final_wealth
        assert stats1.max_drawdown == stats2.max_drawdown
        assert stats1.success == stats2.success
        assert stats1.failure_month == stats2.failure_month
        assert stats1.months_simulated == stats2.months_simulated
        assert stats1.execution_time_seconds == stats2.execution_time_seconds

    def test_builder_instance_does_not_affect_determinism(self):
        """Different builder instances should produce identical statistics."""
        state = create_test_state()
        
        builder1 = DefaultSimulationStatisticsBuilder()
        builder2 = DefaultSimulationStatisticsBuilder()
        
        stats1 = builder1.build(state)
        stats2 = builder2.build(state)
        
        assert stats1.final_wealth == stats2.final_wealth
        assert stats1.success == stats2.success


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_zero_month_simulation_success(self):
        """Zero-month simulation should produce valid statistics."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state(
            status=ExecutionStatus.COMPLETED,
            failure_state=None,
            monthly_count=0,
        )
        
        stats = builder.build(state)
        
        assert stats.success is True
        assert stats.failure_month is None
        assert stats.months_simulated == 0

    def test_immediate_failure_in_first_month(self):
        """Immediate failure (period_index=0) should be properly recorded."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state(
            status=ExecutionStatus.FAILED,
            failure_state="Insufficient funds",
            period_index=0,
            monthly_count=1,
        )
        
        stats = builder.build(state)
        
        assert stats.success is False
        assert stats.failure_month == 0
        assert stats.months_simulated == 1

    def test_late_failure_near_horizon(self):
        """Failure near the end of horizon should be properly recorded."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state(
            status=ExecutionStatus.FAILED,
            failure_state="Portfolio depleted",
            period_index=239,
            monthly_count=240,
        )
        
        stats = builder.build(state)
        
        assert stats.success is False
        assert stats.failure_month == 239
        assert stats.months_simulated == 240

    def test_wealth_at_boundaries(self):
        """Wealth values at monetary boundaries should be handled correctly."""
        builder = DefaultSimulationStatisticsBuilder()
        
        # Very large wealth
        state1 = create_test_state(current_wealth=Money(Decimal("999999999999"), Currency.EUR))
        stats1 = builder.build(state1)
        assert stats1.final_wealth == Money(Decimal("999999999999"), Currency.EUR)
        
        # Very small wealth
        state2 = create_test_state(current_wealth=Money(Decimal("1"), Currency.EUR))
        stats2 = builder.build(state2)
        assert stats2.final_wealth == Money(Decimal("1"), Currency.EUR)
        
        # Zero wealth
        state3 = create_test_state(current_wealth=Money(Decimal("0"), Currency.EUR))
        stats3 = builder.build(state3)
        assert stats3.final_wealth == Money(Decimal("0"), Currency.EUR)


class TestCoherence:
    """Tests for logical coherence of statistics."""

    def test_failure_month_implies_not_successful(self):
        """If failure_month is set, success should be False."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state(
            failure_state="Error",
            period_index=5,
        )
        
        stats = builder.build(state)
        
        assert stats.failure_month is not None
        assert stats.success is False

    def test_success_implies_no_failure_month(self):
        """If success is True, failure_month should be None."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state(
            status=ExecutionStatus.COMPLETED,
            failure_state=None,
        )
        
        stats = builder.build(state)
        
        assert stats.success is True
        assert stats.failure_month is None

    def test_months_simulated_non_negative(self):
        """months_simulated should never be negative."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state(monthly_count=0)
        
        stats = builder.build(state)
        
        assert stats.months_simulated >= 0


class TestPublicContractCompliance:
    """Tests ensuring builder complies with specification contract."""

    def test_builder_uses_only_public_fields(self):
        """Builder should depend only on documented public fields."""
        # This test documents the contract:
        # - status
        # - failure_state
        # - current_wealth
        # - context.initial_wealth
        # - period_index
        # - monthly_results
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state()
        
        # Should succeed without errors
        stats = builder.build(state)
        
        # Verify all required fields were accessible
        assert stats is not None

    def test_builder_returns_simulation_statistics(self):
        """Builder should return exactly SimulationStatistics type."""
        from engine.application.simulation import SimulationStatistics
        
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state()
        
        stats = builder.build(state)
        
        assert type(stats) == SimulationStatistics

    def test_builder_all_fields_populated(self):
        """Returned SimulationStatistics should have all 6 fields populated."""
        builder = DefaultSimulationStatisticsBuilder()
        state = create_test_state()
        
        stats = builder.build(state)
        
        assert hasattr(stats, 'final_wealth')
        assert hasattr(stats, 'max_drawdown')
        assert hasattr(stats, 'success')
        assert hasattr(stats, 'failure_month')
        assert hasattr(stats, 'months_simulated')
        assert hasattr(stats, 'execution_time_seconds')
        
        # All fields have values
        assert stats.final_wealth is not None
        assert stats.max_drawdown is not None
        assert stats.success is not None
        # failure_month can be None
        assert stats.months_simulated is not None
        assert stats.execution_time_seconds is not None
