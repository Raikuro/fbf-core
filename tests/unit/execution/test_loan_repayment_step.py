"""Unit tests for LoanRepaymentStep."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies.decisions import WithdrawalDecision
from fbf.core.execution.pipeline.simulation import SimulationState
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.pipeline.steps.loan_repayment_step import LoanRepaymentStep


@pytest.fixture
def equity_asset() -> AssetClass:
    return AssetClass(id="equity", name="Equity", description="")


@pytest.fixture
def bond_asset() -> AssetClass:
    return AssetClass(id="bond", name="Bond", description="")


@pytest.fixture
def portfolio(equity_asset: AssetClass, bond_asset: AssetClass) -> Portfolio:
    return Portfolio(
        holdings=(
            AssetHolding(asset_class=equity_asset, units=Decimal("500")),
            AssetHolding(asset_class=bond_asset, units=Decimal("500")),
        )
    )


@pytest.fixture
def simulation_context(equity_asset: AssetClass, bond_asset: AssetClass) -> SimulationContext:
    from fbf.core.domain.model.dataset import Dataset
    from fbf.core.domain.model.market_snapshot import MarketSnapshot
    from fbf.core.domain.policies.concrete import (
        ConstantAllocationPolicy,
        FixedRealWithdrawalPolicy,
    )

    dataset = Dataset(
        identifier="test",
        snapshots=(
            MarketSnapshot(
                date=date(1965, 11, 1),
                index_levels={
                    equity_asset: Decimal("100"),
                    bond_asset: Decimal("100"),
                },
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("1"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            ),
        ),
        frequency="monthly",
        version="test",
    )

    return SimulationContext(
        experiment_name="test",
        cohort="1965-11",
        start_date=date(1965, 11, 1),
        horizon_months=360,
        initial_wealth=Money(Decimal("100000"), Currency.EUR),
        initial_portfolio=Portfolio(holdings=()),
        dataset=dataset,
        allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.75")),
        withdrawal_policy=FixedRealWithdrawalPolicy(withdrawal_rate=Decimal("0.04")),
    )


class TestLoanRepaymentStep:
    """Tests for LoanRepaymentStep."""

    def test_repayment_reduces_loan_balance(
        self, portfolio: Portfolio, simulation_context: SimulationContext
    ) -> None:
        """is_repayment=True, loan_balance > 0 → loan_balance decreases."""
        state = SimulationState(
            context=simulation_context,
            current_date=date(1965, 11, 1),
            period_index=0,
            portfolio=portfolio,
            loan_balance=Decimal("5000"),
        )
        state.withdrawal_decision = WithdrawalDecision(
            reason="test",
            nominal_amount=Money(Decimal("1000"), Currency.EUR),
            real_amount=Money(Decimal("1000"), Currency.EUR),
            loan_draw_amount=Decimal("0"),
            is_repayment=True,
        )

        step = LoanRepaymentStep()
        result = step.execute(state)

        # excess = 1000 / 2 = 500
        # repayment = min(500, 5000) = 500
        assert result.loan_balance == Decimal("4500")

    def test_repayment_noop_when_no_loan(
        self, portfolio: Portfolio, simulation_context: SimulationContext
    ) -> None:
        """is_repayment=True, loan_balance = 0 → no change."""
        state = SimulationState(
            context=simulation_context,
            current_date=date(1965, 11, 1),
            period_index=0,
            portfolio=portfolio,
            loan_balance=Decimal("0"),
        )
        state.withdrawal_decision = WithdrawalDecision(
            reason="test",
            nominal_amount=Money(Decimal("1000"), Currency.EUR),
            real_amount=Money(Decimal("1000"), Currency.EUR),
            loan_draw_amount=Decimal("0"),
            is_repayment=True,
        )

        step = LoanRepaymentStep()
        result = step.execute(state)

        assert result.loan_balance == Decimal("0")

    def test_repayment_noop_when_not_repayment(
        self, portfolio: Portfolio, simulation_context: SimulationContext
    ) -> None:
        """is_repayment=False → no change."""
        state = SimulationState(
            context=simulation_context,
            current_date=date(1965, 11, 1),
            period_index=0,
            portfolio=portfolio,
            loan_balance=Decimal("5000"),
        )
        state.withdrawal_decision = WithdrawalDecision(
            reason="test",
            nominal_amount=Money(Decimal("1000"), Currency.EUR),
            real_amount=Money(Decimal("1000"), Currency.EUR),
            loan_draw_amount=Decimal("0"),
            is_repayment=False,
        )

        step = LoanRepaymentStep()
        result = step.execute(state)

        assert result.loan_balance == Decimal("5000")

    def test_repayment_limited_by_loan_balance(
        self, portfolio: Portfolio, simulation_context: SimulationContext
    ) -> None:
        """excess > loan_balance → repay only loan_balance."""
        state = SimulationState(
            context=simulation_context,
            current_date=date(1965, 11, 1),
            period_index=0,
            portfolio=portfolio,
            loan_balance=Decimal("200"),
        )
        state.withdrawal_decision = WithdrawalDecision(
            reason="test",
            nominal_amount=Money(Decimal("1000"), Currency.EUR),
            real_amount=Money(Decimal("1000"), Currency.EUR),
            loan_draw_amount=Decimal("0"),
            is_repayment=True,
        )

        step = LoanRepaymentStep()
        result = step.execute(state)

        # excess = 1000 / 2 = 500
        # repayment = min(500, 200) = 200
        assert result.loan_balance == Decimal("0")

    def test_repayment_preserves_unrelated_state(
        self, portfolio: Portfolio, simulation_context: SimulationContext
    ) -> None:
        """Other state fields unchanged."""
        state = SimulationState(
            context=simulation_context,
            current_date=date(1965, 11, 1),
            period_index=0,
            portfolio=portfolio,
            loan_balance=Decimal("5000"),
            cash_balance=Decimal("1000"),
            interest_rate=Decimal("0.015"),
        )
        state.withdrawal_decision = WithdrawalDecision(
            reason="test",
            nominal_amount=Money(Decimal("1000"), Currency.EUR),
            real_amount=Money(Decimal("1000"), Currency.EUR),
            loan_draw_amount=Decimal("0"),
            is_repayment=True,
        )

        step = LoanRepaymentStep()
        result = step.execute(state)

        assert result.cash_balance == Decimal("1000")
        assert result.interest_rate == Decimal("0.015")
        assert result.portfolio == portfolio
