"""Unit tests for the final-value success criterion.

Verifies the externally observable contract:

    success =
        survived (intrinsic)
        AND
        (final_value_target is None
         OR final_wealth >= target_fraction * initial_wealth)

Six test cases:
1. No target configured -> survival only (existing behavior).
2. Positive target + final wealth below target -> failure.
3. Positive target + temporary dip below target + final wealth above target -> success.
4. Final wealth exactly equal to target -> success.
5. Final wealth one cent below target -> failure.
6. Depletion before the final period -> failure regardless of target.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fbf.core.domain.model.allocation import Allocation, AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import Portfolio
from fbf.core.domain.policies import AllocationPolicy, WithdrawalPolicy
from fbf.core.domain.policies.decisions import AllocationDecision, WithdrawalDecision
from fbf.core.execution.pipeline.simulation import (
    ExecutionStatus,
    MonthlyResult,
    SimulationState,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.pipeline.statistics_builder import DefaultSimulationStatisticsBuilder

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_market_snapshot(date_: date) -> MarketSnapshot:
    asset = AssetClass(id="test", name="Test", description="")
    return MarketSnapshot(
        date=date_,
        index_levels={asset: Decimal("100")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100"),
    )


def _make_test_dataset() -> Dataset:
    return Dataset(
        snapshots=[_make_market_snapshot(date(2024, 1, 1))],
        frequency="monthly",
        version="1.0",
    )


class _NoopAllocationPolicy(AllocationPolicy):
    def decide(self, context: object) -> AllocationDecision:
        asset = AssetClass(id="noop", name="Noop", description="")
        return AllocationDecision(
            reason="noop",
            allocation_target=AllocationTarget(weights={asset: Decimal("1")}),
        )


class _NoopWithdrawalPolicy(WithdrawalPolicy):
    def decide(self, context: object) -> WithdrawalDecision:
        return WithdrawalDecision(
            reason="noop",
            nominal_amount=Money(Decimal("0"), Currency.EUR),
            real_amount=Money(Decimal("0"), Currency.EUR),
        )


def _make_context(
    initial_wealth: Money,
    final_value_target: Decimal | None = None,
) -> SimulationContext:
    return SimulationContext(
        experiment_name="test",
        cohort="test_cohort",
        start_date=date(2024, 1, 1),
        horizon_months=3,
        initial_wealth=initial_wealth,
        initial_portfolio=Portfolio(holdings=[]),
        dataset=_make_test_dataset(),
        allocation_policy=_NoopAllocationPolicy(),
        withdrawal_policy=_NoopWithdrawalPolicy(),
        final_value_target=final_value_target,
    )


def _make_monthly_result(date_: date, index: int) -> MonthlyResult:
    asset = AssetClass(id="test", name="Test", description="")
    return MonthlyResult(
        date=date_,
        period_index=index,
        market_snapshot=_make_market_snapshot(date_),
        portfolio=Portfolio(holdings=[]),
        allocation=Allocation(weights={asset: Decimal("1")}),
        allocation_target=None,
        allocation_drift=None,
        withdrawal_decision=None,
        rebalance_result=None,
        drawdown=0.0,
        cumulative_return=0.0,
        cumulative_inflation=0.0,
        events=[],
    )


def _make_state(
    context: SimulationContext,
    status: ExecutionStatus = ExecutionStatus.COMPLETED,
    failure_state: str | None = None,
    current_wealth: Money | None = None,
    period_index: int = 2,
) -> SimulationState:
    monthly_results = [
        _make_monthly_result(date(2024, 1 + i, 1), i) for i in range(3)
    ]
    return SimulationState(
        context=context,
        current_date=date(2024, 3, 1),
        period_index=period_index,
        portfolio=Portfolio(holdings=[]),
        current_wealth=current_wealth,
        status=status,
        failure_state=failure_state,
        monthly_results=monthly_results,
    )


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

INITIAL_WEALTH = Money(Decimal("100"), Currency.EUR)
BUILDER = DefaultSimulationStatisticsBuilder()


class TestFinalValueSuccessSemantics:
    """The six deterministic success-semantic test cases."""

    def test_case1_no_target_survival_only(self):
        """No target configured -> success if survived, regardless of final wealth."""
        ctx = _make_context(INITIAL_WEALTH, final_value_target=None)
        state = _make_state(
            ctx,
            current_wealth=Money(Decimal("83.45"), Currency.EUR),
        )
        stats = BUILDER.build(state)
        assert stats.success is True

    def test_case2_positive_target_below(self):
        """Final wealth below target -> failure."""
        ctx = _make_context(INITIAL_WEALTH, final_value_target=Decimal("0.90"))
        state = _make_state(
            ctx,
            current_wealth=Money(Decimal("83.45"), Currency.EUR),
        )
        stats = BUILDER.build(state)
        assert stats.success is False

    def test_case3_temporary_dip_but_recovers(self):
        """Portfolio temporarily falls below target but finishes above it -> success.

        The final-value criterion is evaluated only at the final period.
        Intermediate values below the target do not cause failure.

        Scenario:
            Initial wealth: $100
            Target: 85% -> $85

            Month 0: $100 -> $95
            Month 1: $95 -> $32.50  (below $85)
            Month 2: $32.50 -> $180  (above $85)
        """
        ctx = _make_context(INITIAL_WEALTH, final_value_target=Decimal("0.85"))
        state = _make_state(
            ctx,
            current_wealth=Money(Decimal("180"), Currency.EUR),
        )
        stats = BUILDER.build(state)
        assert stats.success is True

    def test_case4_exact_equality(self):
        """Final wealth exactly equal to target -> success."""
        ctx = _make_context(INITIAL_WEALTH, final_value_target=Decimal("0.8345"))
        state = _make_state(
            ctx,
            current_wealth=Money(Decimal("83.45"), Currency.EUR),
        )
        stats = BUILDER.build(state)
        assert stats.success is True

    def test_case5_one_cent_below(self):
        """Final wealth one cent below target -> failure."""
        ctx = _make_context(INITIAL_WEALTH, final_value_target=Decimal("0.8346"))
        state = _make_state(
            ctx,
            current_wealth=Money(Decimal("83.45"), Currency.EUR),
        )
        stats = BUILDER.build(state)
        assert stats.success is False

    def test_case6_depletion_before_final_period(self):
        """Depletion before the final period -> failure regardless of target.

        Even with a trivially satisfiable target (0%), a depleted portfolio
        is always unsuccessful.
        """
        ctx = _make_context(INITIAL_WEALTH, final_value_target=Decimal("0.00"))
        state = _make_state(
            ctx,
            status=ExecutionStatus.FAILED,
            failure_state="depleted",
            current_wealth=Money(Decimal("0"), Currency.EUR),
            period_index=1,
        )
        stats = BUILDER.build(state)
        assert stats.success is False
        assert stats.failure_month == 1

    def test_target_zero_reproduces_depletion_semantics(self):
        """target=0.00 with a surviving portfolio -> success (trivially satisfied)."""
        ctx = _make_context(INITIAL_WEALTH, final_value_target=Decimal("0.00"))
        state = _make_state(
            ctx,
            current_wealth=Money(Decimal("1"), Currency.EUR),
        )
        stats = BUILDER.build(state)
        assert stats.success is True

    def test_survived_but_zero_wealth_with_positive_target(self):
        """Survived with zero final wealth + positive target -> failure."""
        ctx = _make_context(INITIAL_WEALTH, final_value_target=Decimal("0.01"))
        state = _make_state(
            ctx,
            current_wealth=Money(Decimal("0"), Currency.EUR),
        )
        stats = BUILDER.build(state)
        assert stats.success is False
