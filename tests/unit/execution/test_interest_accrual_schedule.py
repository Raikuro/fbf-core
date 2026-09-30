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


class TestInterestAccrualRealRate:
    """Tests for GAP-2: real-rate semantics with non-zero inflation."""

    def test_real_rate_no_cpi_adjustment_with_inflation(self) -> None:
        """When debt_interest_rate_is_real=True, rate is applied without CPI adjustment."""
        # Create context with debt_interest_rate_is_real=True and non-zero inflation
        from datetime import date
        from decimal import Decimal

        from fbf.core.domain.model.asset import AssetClass
        from fbf.core.domain.model.dataset import Dataset
        from fbf.core.domain.model.market_snapshot import MarketSnapshot
        from fbf.core.domain.model.money import Currency, Money
        from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
        from fbf.core.execution.pipeline.simulation_context import SimulationContext
        from fbf.core.execution.pipeline.steps.interest_accrual_step import InterestAccrualStep

        equity_asset = AssetClass(id="equity", name="Equity", description="")
        bond_asset = AssetClass(id="bond", name="Bond", description="")

        # Dataset with non-zero inflation_cumulative (simulating ~5% annual inflation)
        dataset = Dataset(
            snapshots=(
                MarketSnapshot(
                    date=date(1965, 11, 1),
                    index_levels={equity_asset: Decimal("100"), bond_asset: Decimal("100")},
                    inflation=Decimal("0"),
                    inflation_cumulative=Decimal("1.0"),  # Base
                    is_ath=True,
                    is_underwater=False,
                    running_ath=Decimal("100"),
                ),
                MarketSnapshot(
                    date=date(1965, 12, 1),
                    index_levels={equity_asset: Decimal("100"), bond_asset: Decimal("100")},
                    inflation=Decimal("0"),
                    inflation_cumulative=Decimal("1.0041667"),  # ~5% annual / 12
                    is_ath=True,
                    is_underwater=False,
                    running_ath=Decimal("100"),
                ),
            ),
            frequency="monthly",
        )

        context = SimulationContext(
            experiment_name="test",
            cohort="1965-11",
            start_date=date(1965, 11, 1),
            horizon_months=12,
            initial_wealth=Money(Decimal("100000"), Currency.EUR),
            initial_portfolio=Portfolio(holdings=(
                AssetHolding(asset_class=equity_asset, units=Decimal("500")),
                AssetHolding(asset_class=bond_asset, units=Decimal("500")),
            )),
            dataset=dataset,
            allocation_policy=None,  # type: ignore[arg-type]  # Not needed for this step
            withdrawal_policy=None,  # type: ignore[arg-type]  # Not needed for this step
            interest_rate=Decimal("0.03"),  # 3% annual real rate
            interest_rate_schedule=None,
            ltv_limit=Decimal("0.75"),
            ltv_enforcement=False,
            loan_draw_rate=Decimal("0.01"),
            expense_ratio=None,
            debt_interest_rate_is_real=True,  # GAP-2: real rate flag
        )

        state = SimulationState(
            context=context,
            current_date=date(1965, 11, 1),
            period_index=0,
            portfolio=Portfolio(holdings=(
                AssetHolding(asset_class=equity_asset, units=Decimal("500")),
                AssetHolding(asset_class=bond_asset, units=Decimal("500")),
            )),
            loan_balance=Decimal("100000"),
            interest_rate=Decimal("0.03"),
            market_snapshot=dataset[0],
        )

        step = InterestAccrualStep()
        result = step.execute(state)

        # With real rate: monthly rate = 0.03 / 12 = 0.0025
        # Interest = 100000 * 0.0025 = 250
        expected_interest = Decimal("100000") * Decimal("0.03") / Decimal("12")
        assert result.loan_balance == Decimal("100000") + expected_interest

    def test_nominal_rate_with_cpi_adjustment_with_inflation(self) -> None:
        """With debt_interest_rate_is_real=False (default), CPI adjustment is applied."""
        from datetime import date
        from decimal import Decimal

        from fbf.core.domain.model.asset import AssetClass
        from fbf.core.domain.model.dataset import Dataset
        from fbf.core.domain.model.market_snapshot import MarketSnapshot
        from fbf.core.domain.model.money import Currency, Money
        from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
        from fbf.core.execution.pipeline.simulation_context import SimulationContext
        from fbf.core.execution.pipeline.steps.interest_accrual_step import InterestAccrualStep

        equity_asset = AssetClass(id="equity", name="Equity", description="")
        bond_asset = AssetClass(id="bond", name="Bond", description="")

        # Dataset with non-zero inflation_cumulative (simulating 5% annual inflation)
        dataset = Dataset(
            snapshots=(
                MarketSnapshot(
                    date=date(1965, 11, 1),
                    index_levels={equity_asset: Decimal("100"), bond_asset: Decimal("100")},
                    inflation=Decimal("0"),
                    inflation_cumulative=Decimal("1.0"),  # Base
                    is_ath=True,
                    is_underwater=False,
                    running_ath=Decimal("100"),
                ),
                MarketSnapshot(
                    date=date(1965, 12, 1),
                    index_levels={equity_asset: Decimal("100"), bond_asset: Decimal("100")},
                    inflation=Decimal("0"),
                    inflation_cumulative=Decimal("1.0041667"),  # ~5% annual / 12
                    is_ath=True,
                    is_underwater=False,
                    running_ath=Decimal("100"),
                ),
            ),
            frequency="monthly",
        )

        context = SimulationContext(
            experiment_name="test",
            cohort="1965-11",
            start_date=date(1965, 11, 1),
            horizon_months=12,
            initial_wealth=Money(Decimal("100000"), Currency.EUR),
            initial_portfolio=Portfolio(holdings=(
                AssetHolding(asset_class=equity_asset, units=Decimal("500")),
                AssetHolding(asset_class=bond_asset, units=Decimal("500")),
            )),
            dataset=dataset,
            allocation_policy=None,  # type: ignore[arg-type]  # Not needed for this step
            withdrawal_policy=None,  # type: ignore[arg-type]  # Not needed for this step
            interest_rate=Decimal("0.03"),  # 3% nominal annual rate
            interest_rate_schedule=None,
            ltv_limit=Decimal("0.75"),
            ltv_enforcement=False,
            loan_draw_rate=Decimal("0.01"),
            expense_ratio=None,
            debt_interest_rate_is_real=False,  # Default: nominal rate with CPI adjustment
        )

        state = SimulationState(
            context=context,
            current_date=date(1965, 12, 1),  # Second month (December 1965)
            period_index=1,  # Second month (index 1) to test CPI adjustment between period 0 and 1
            portfolio=Portfolio(holdings=(
                AssetHolding(asset_class=equity_asset, units=Decimal("500")),
                AssetHolding(asset_class=bond_asset, units=Decimal("500")),
            )),
            loan_balance=Decimal("100000"),
            interest_rate=Decimal("0.03"),
            market_snapshot=dataset[1],  # Second month snapshot with higher CPI
        )

        step = InterestAccrualStep()
        result = step.execute(state)

        # With nominal rate and CPI adjustment:
        # CPI ratio = 1.0 / 1.0041667 = 0.99585
        # nominal_monthly = 0.03 / 12 = 0.0025
        # real_monthly = (1 + 0.0025) * 0.99585 - 1 = -0.00414...
        # This should NOT equal 100000 * 0.03 / 12 = 250
        # It should be DIFFERENT (and smaller due to CPI deflation)
        expected_interest_nominal = Decimal("100000") * Decimal("0.03") / Decimal("12")
        assert result.loan_balance != Decimal("100000") + expected_interest_nominal
        # The interest should be smaller due to CPI deflation
        assert result.loan_balance < Decimal("100000") + expected_interest_nominal
