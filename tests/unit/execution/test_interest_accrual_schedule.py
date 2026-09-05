"""Unit tests for InterestAccrualStep schedule support."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.execution.pipeline.simulation import SimulationState
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.pipeline.steps.interest_accrual_step import InterestAccrualStep


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


class TestInterestAccrualStepSchedule:
    """Tests for InterestAccrualStep schedule support."""

    def test_schedule_rate_used_when_present(
        self, portfolio: Portfolio, simulation_context: SimulationContext
    ) -> None:
        """interest_rate_schedule set → uses schedule[period_index]."""
        schedule = (Decimal("0.05"), Decimal("0.10"), Decimal("0.15"))
        context_with_schedule = SimulationContext(
            experiment_name="test",
            cohort="1965-11",
            start_date=date(1965, 11, 1),
            horizon_months=360,
            initial_wealth=Money(Decimal("100000"), Currency.EUR),
            initial_portfolio=Portfolio(holdings=()),
            dataset=simulation_context.dataset,
            allocation_policy=simulation_context.allocation_policy,
            withdrawal_policy=simulation_context.withdrawal_policy,
            interest_rate=Decimal("0.015"),
            interest_rate_schedule=schedule,
        )

        equity_asset = AssetClass(id="equity", name="Equity", description="")
        bond_asset = AssetClass(id="bond", name="Bond", description="")
        market_snapshot = MarketSnapshot(
            date=date(1965, 11, 1),
            index_levels={equity_asset: Decimal("100"), bond_asset: Decimal("100")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=True,
            is_underwater=False,
            running_ath=Decimal("100"),
        )

        state = SimulationState(
            context=context_with_schedule,
            current_date=date(1965, 11, 1),
            period_index=0,
            portfolio=portfolio,
            loan_balance=Decimal("10000"),
            interest_rate=Decimal("0.015"),
            market_snapshot=market_snapshot,
        )

        step = InterestAccrualStep()
        result = step.execute(state)

        # Schedule rate at index 0 = 0.05
        # Monthly rate = 0.05 / 12 = 0.0041666...
        # Interest = 10000 * 0.0041666... = 41.666...
        expected_interest = Decimal("10000") * Decimal("0.05") / Decimal("12")
        assert result.loan_balance == Decimal("10000") + expected_interest

    def test_fallback_to_fixed_rate(
        self, portfolio: Portfolio, simulation_context: SimulationContext
    ) -> None:
        """No schedule → uses interest_rate."""
        equity_asset = AssetClass(id="equity", name="Equity", description="")
        bond_asset = AssetClass(id="bond", name="Bond", description="")
        market_snapshot = MarketSnapshot(
            date=date(1965, 11, 1),
            index_levels={equity_asset: Decimal("100"), bond_asset: Decimal("100")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=True,
            is_underwater=False,
            running_ath=Decimal("100"),
        )

        state = SimulationState(
            context=simulation_context,
            current_date=date(1965, 11, 1),
            period_index=0,
            portfolio=portfolio,
            loan_balance=Decimal("10000"),
            interest_rate=Decimal("0.015"),
            market_snapshot=market_snapshot,
        )

        step = InterestAccrualStep()
        result = step.execute(state)

        # Fixed rate = 0.015
        # Monthly rate = 0.015 / 12 = 0.00125
        # Interest = 10000 * 0.00125 = 12.5
        expected_interest = Decimal("10000") * Decimal("0.015") / Decimal("12")
        assert result.loan_balance == Decimal("10000") + expected_interest

    def test_schedule_out_of_bounds_fallback(
        self, portfolio: Portfolio, simulation_context: SimulationContext
    ) -> None:
        """period_index >= len(schedule) → uses interest_rate."""
        schedule = (Decimal("0.05"),)  # Only 1 element
        context_with_schedule = SimulationContext(
            experiment_name="test",
            cohort="1965-11",
            start_date=date(1965, 11, 1),
            horizon_months=360,
            initial_wealth=Money(Decimal("100000"), Currency.EUR),
            initial_portfolio=Portfolio(holdings=()),
            dataset=simulation_context.dataset,
            allocation_policy=simulation_context.allocation_policy,
            withdrawal_policy=simulation_context.withdrawal_policy,
            interest_rate=Decimal("0.015"),
            interest_rate_schedule=schedule,
        )

        equity_asset = AssetClass(id="equity", name="Equity", description="")
        bond_asset = AssetClass(id="bond", name="Bond", description="")
        market_snapshot = MarketSnapshot(
            date=date(1965, 11, 1),
            index_levels={equity_asset: Decimal("100"), bond_asset: Decimal("100")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=True,
            is_underwater=False,
            running_ath=Decimal("100"),
        )

        state = SimulationState(
            context=context_with_schedule,
            current_date=date(1965, 11, 1),
            period_index=5,  # Out of bounds
            portfolio=portfolio,
            loan_balance=Decimal("10000"),
            interest_rate=Decimal("0.015"),
            market_snapshot=market_snapshot,
        )

        step = InterestAccrualStep()
        result = step.execute(state)

        # Falls back to fixed rate = 0.015
        expected_interest = Decimal("10000") * Decimal("0.015") / Decimal("12")
        assert result.loan_balance == Decimal("10000") + expected_interest
