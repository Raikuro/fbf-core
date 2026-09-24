"""Unit tests for EscalatingWithdrawalPolicy.

Verifies the generic currency-agnostic withdrawal policy with annual
escalation, covering multiple years, frequency variants, and
currency preservation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from fbf.core.domain.model.allocation import Allocation, AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.decision_context import DecisionContext
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies.escalating_withdrawal import EscalatingWithdrawalPolicy
from fbf.core.domain.policies.frequency import WithdrawalFrequency

_EQUITY = AssetClass(id="equity", name="", description="")
_BOND = AssetClass(id="bond", name="", description="")


@dataclass(frozen=True)
class SimContext:
    """Minimal simulation context for testing."""

    initial_wealth: Money


def _context(
    period_index: int,
    initial_wealth: Money,
    portfolio_value: Decimal = Decimal("1000000"),
) -> DecisionContext:
    """Create a DecisionContext for testing."""
    portfolio = Portfolio(
        holdings=(
            AssetHolding(asset_class=_EQUITY, units=Decimal("1000")),
            AssetHolding(asset_class=_BOND, units=Decimal("1000")),
        )
    )
    dummy_alloc = Allocation(weights={_EQUITY: Decimal("0.6"), _BOND: Decimal("0.4")})
    dummy_target = AllocationTarget(weights={_EQUITY: Decimal("0.6"), _BOND: Decimal("0.4")})

    from fbf.core.domain.model.dataset import Dataset
    from fbf.core.domain.model.market_snapshot import MarketSnapshot

    snap = MarketSnapshot(
        date=date(1929, 9, 1),
        index_levels={_EQUITY: Decimal("100"), _BOND: Decimal("100")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100"),
    )
    ds = Dataset(snapshots=(snap,), frequency="monthly")

    return DecisionContext(
        date=date(1929, 9, 1),
        period_index=period_index,
        simulation_context=SimContext(initial_wealth=initial_wealth),
        portfolio=portfolio,
        current_allocation=dummy_alloc,
        target_allocation=dummy_target,
        market_snapshot=snap,
        dataset=ds,
    )


class TestEscalatingWithdrawalPolicyInit:
    """Tests for EscalatingWithdrawalPolicy construction."""

    def test_valid_construction_defaults(self) -> None:
        policy = EscalatingWithdrawalPolicy(withdrawal_rate=Decimal("0.035"))
        assert policy.withdrawal_rate == Decimal("0.035")
        assert policy.escalation_rate == Decimal("0.02")
        assert policy.frequency == WithdrawalFrequency.ANNUAL

    def test_valid_construction_custom_escalation(self) -> None:
        policy = EscalatingWithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            escalation_rate=Decimal("0.03"),
            frequency=WithdrawalFrequency.MONTHLY,
        )
        assert policy.withdrawal_rate == Decimal("0.04")
        assert policy.escalation_rate == Decimal("0.03")
        assert policy.frequency == WithdrawalFrequency.MONTHLY

    def test_negative_withdrawal_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="withdrawal_rate must be non-negative"):
            EscalatingWithdrawalPolicy(withdrawal_rate=Decimal("-0.01"))

    def test_negative_escalation_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="escalation_rate must be non-negative"):
            EscalatingWithdrawalPolicy(
                withdrawal_rate=Decimal("0.035"), escalation_rate=Decimal("-0.01")
            )


class TestEscalatingWithdrawalPolicyAnnual:
    """Tests for ANNUAL frequency (Experiment E default)."""

    def test_year_1_withdrawal(self) -> None:
        """Year 1 (period_index 0): 3.5% of $1M = $35,000."""
        policy = EscalatingWithdrawalPolicy(
            withdrawal_rate=Decimal("0.035"),
            escalation_rate=Decimal("0.02"),
            frequency=WithdrawalFrequency.ANNUAL,
        )
        ctx = _context(period_index=0, initial_wealth=Money(Decimal("1000000"), Currency.EUR))
        decision = policy.decide(ctx)

        assert decision.nominal_amount == Money(Decimal("35000"), Currency.EUR)
        assert decision.real_amount == Money(Decimal("35000"), Currency.EUR)

    def test_year_2_withdrawal(self) -> None:
        """Year 2 (period_index 12): 3.5% * 1.02 = 3.57% of $1M = $35,700."""
        policy = EscalatingWithdrawalPolicy(
            withdrawal_rate=Decimal("0.035"),
            escalation_rate=Decimal("0.02"),
            frequency=WithdrawalFrequency.ANNUAL,
        )
        ctx = _context(period_index=12, initial_wealth=Money(Decimal("1000000"), Currency.EUR))
        decision = policy.decide(ctx)

        assert decision.nominal_amount == Money(Decimal("35700"), Currency.EUR)

    def test_year_3_withdrawal(self) -> None:
        """Year 3 (period_index 24): 3.5% * 1.02^2 = 3.6414% of $1M = $36,414."""
        policy = EscalatingWithdrawalPolicy(
            withdrawal_rate=Decimal("0.035"),
            escalation_rate=Decimal("0.02"),
            frequency=WithdrawalFrequency.ANNUAL,
        )
        ctx = _context(period_index=24, initial_wealth=Money(Decimal("1000000"), Currency.EUR))
        decision = policy.decide(ctx)

        expected = Decimal("1000000") * Decimal("0.035") * (Decimal("1.02") ** 2)
        assert decision.nominal_amount == Money(expected, Currency.EUR)

    def test_year_10_withdrawal(self) -> None:
        """Year 10 (period_index 108): matches published $41,828.24."""
        policy = EscalatingWithdrawalPolicy(
            withdrawal_rate=Decimal("0.035"),
            escalation_rate=Decimal("0.02"),
            frequency=WithdrawalFrequency.ANNUAL,
        )
        ctx = _context(period_index=108, initial_wealth=Money(Decimal("1000000"), Currency.EUR))
        decision = policy.decide(ctx)

        expected = Decimal("1000000") * Decimal("0.035") * (Decimal("1.02") ** 9)
        # Published value: $41,828.24
        assert decision.nominal_amount == Money(expected, Currency.EUR)

    def test_non_annual_boundary_returns_zero(self) -> None:
        """Non-annual-boundary periods (period_index % 12 != 0) return zero."""
        policy = EscalatingWithdrawalPolicy(
            withdrawal_rate=Decimal("0.035"),
            escalation_rate=Decimal("0.02"),
            frequency=WithdrawalFrequency.ANNUAL,
        )
        for pi in [1, 2, 11, 13, 23, 25]:
            ctx = _context(period_index=pi, initial_wealth=Money(Decimal("1000000"), Currency.EUR))
            decision = policy.decide(ctx)
            assert decision.nominal_amount == Money(Decimal("0"), Currency.EUR)
            assert decision.reason == "WithdrawalPolicy.frequency_skip"

    def test_total_10_years_matches_published(self) -> None:
        """Sum of 10 annual withdrawals matches published $383,240.12 (within rounding)."""
        policy = EscalatingWithdrawalPolicy(
            withdrawal_rate=Decimal("0.035"),
            escalation_rate=Decimal("0.02"),
            frequency=WithdrawalFrequency.ANNUAL,
        )

        total = Decimal("0")
        for year in range(10):
            wealth = Money(Decimal("1000000"), Currency.EUR)
            ctx = _context(period_index=year * 12, initial_wealth=wealth)
            decision = policy.decide(ctx)
            total += decision.nominal_amount.amount

        # Published total: $383,240.12 (allow tolerance for Decimal compounding precision
        # vs. published rounded values; the formula produces ~383,240.23)
        assert abs(total - Decimal("383240.12")) < Decimal("1.0")


class TestEscalatingWithdrawalPolicyMonthly:
    """Tests for MONTHLY frequency."""

    def test_monthly_divides_annual_by_12(self) -> None:
        policy = EscalatingWithdrawalPolicy(
            withdrawal_rate=Decimal("0.035"),
            escalation_rate=Decimal("0.02"),
            frequency=WithdrawalFrequency.MONTHLY,
        )
        ctx = _context(period_index=0, initial_wealth=Money(Decimal("1000000"), Currency.EUR))
        decision = policy.decide(ctx)

        expected = Decimal("35000") / Decimal("12")
        assert decision.nominal_amount.amount == expected

    def test_monthly_escalation_at_annual_boundaries(self) -> None:
        """Monthly amount escalates at annual boundaries."""
        policy = EscalatingWithdrawalPolicy(
            withdrawal_rate=Decimal("0.035"),
            escalation_rate=Decimal("0.02"),
            frequency=WithdrawalFrequency.MONTHLY,
        )

        # Month 0 (year 1): 35000/12
        ctx0 = _context(period_index=0, initial_wealth=Money(Decimal("1000000"), Currency.EUR))
        dec0 = policy.decide(ctx0)

        # Month 11 (still year 1): same amount
        ctx11 = _context(period_index=11, initial_wealth=Money(Decimal("1000000"), Currency.EUR))
        dec11 = policy.decide(ctx11)
        assert dec11.nominal_amount.amount == dec0.nominal_amount.amount

        # Month 12 (year 2): escalated
        ctx12 = _context(period_index=12, initial_wealth=Money(Decimal("1000000"), Currency.EUR))
        dec12 = policy.decide(ctx12)
        expected = Decimal("35000") * Decimal("1.02") / Decimal("12")
        assert dec12.nominal_amount.amount == expected


class TestEscalatingWithdrawalPolicyCurrency:
    """Tests for currency-agnostic behavior."""

    def test_eur_currency(self) -> None:
        policy = EscalatingWithdrawalPolicy(withdrawal_rate=Decimal("0.035"))
        ctx = _context(period_index=0, initial_wealth=Money(Decimal("1000000"), Currency.EUR))
        decision = policy.decide(ctx)
        assert decision.nominal_amount.currency == Currency.EUR
        assert decision.real_amount.currency == Currency.EUR

    def test_different_initial_wealth_amount(self) -> None:
        """Withdrawal scales with initial wealth."""
        policy = EscalatingWithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            escalation_rate=Decimal("0.02"),
            frequency=WithdrawalFrequency.ANNUAL,
        )
        # $500,000 initial wealth
        ctx = _context(period_index=0, initial_wealth=Money(Decimal("500000"), Currency.EUR))
        decision = policy.decide(ctx)
        assert decision.nominal_amount == Money(Decimal("20000"), Currency.EUR)

    def test_zero_initial_wealth(self) -> None:
        """Zero initial wealth produces zero withdrawal."""
        policy = EscalatingWithdrawalPolicy(
            withdrawal_rate=Decimal("0.035"),
            frequency=WithdrawalFrequency.ANNUAL,
        )
        ctx = _context(period_index=0, initial_wealth=Money(Decimal("0"), Currency.EUR))
        decision = policy.decide(ctx)
        assert decision.nominal_amount == Money(Decimal("0"), Currency.EUR)


class TestEscalatingWithdrawalPolicyEdgeCases:
    """Edge case tests."""

    def test_requires_simulation_context(self) -> None:
        policy = EscalatingWithdrawalPolicy(withdrawal_rate=Decimal("0.035"))

        # Context without simulation_context
        from fbf.core.domain.model.allocation import Allocation, AllocationTarget
        from fbf.core.domain.model.dataset import Dataset
        from fbf.core.domain.model.market_snapshot import MarketSnapshot
        from fbf.core.domain.model.portfolio import AssetHolding, Portfolio

        portfolio = Portfolio(holdings=(AssetHolding(asset_class=_EQUITY, units=Decimal("1000")),))
        dummy_alloc = Allocation(weights={_EQUITY: Decimal("1")})
        dummy_target = AllocationTarget(weights={_EQUITY: Decimal("1")})
        snap = MarketSnapshot(
            date=date(1929, 9, 1),
            index_levels={_EQUITY: Decimal("100")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("0"),
            is_ath=True,
            is_underwater=False,
            running_ath=Decimal("100"),
        )
        ds = Dataset(snapshots=(snap,), frequency="monthly")

        bad_ctx = DecisionContext(
            date=date(1929, 9, 1),
            period_index=0,
            simulation_context=object(),  # No initial_wealth attribute
            portfolio=portfolio,
            current_allocation=dummy_alloc,
            target_allocation=dummy_target,
            market_snapshot=snap,
            dataset=ds,
        )

        with pytest.raises(TypeError, match="requires a DecisionContext with simulation_context"):
            policy.decide(bad_ctx)

    def test_zero_escalation_rate(self) -> None:
        """Zero escalation means constant withdrawal."""
        policy = EscalatingWithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            escalation_rate=Decimal("0"),
            frequency=WithdrawalFrequency.ANNUAL,
        )

        for year in range(5):
            wealth = Money(Decimal("1000000"), Currency.EUR)
            ctx = _context(period_index=year * 12, initial_wealth=wealth)
            decision = policy.decide(ctx)
            assert decision.nominal_amount == Money(Decimal("40000"), Currency.EUR)

    def test_withdrawal_rate_one(self) -> None:
        """100% withdrawal rate (extreme but valid)."""
        policy = EscalatingWithdrawalPolicy(
            withdrawal_rate=Decimal("1"),
            escalation_rate=Decimal("0"),
            frequency=WithdrawalFrequency.ANNUAL,
        )
        ctx = _context(period_index=0, initial_wealth=Money(Decimal("1000000"), Currency.EUR))
        decision = policy.decide(ctx)
        assert decision.nominal_amount == Money(Decimal("1000000"), Currency.EUR)
