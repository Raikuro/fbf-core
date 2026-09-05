"""Floating-rate validation tests for S6.2 FFR integration.

Verifies that the FFR-based interest rate schedule is correctly used in the
Part 52 pipeline execution, with interest accrual using per-period rates.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies.concrete import ConstantAllocationPolicy
from fbf.core.domain.policies.part52_withdrawal import Part52WithdrawalPolicy
from fbf.core.execution.pipeline.default_pipeline import create_default_pipeline
from fbf.core.execution.pipeline.simulation import SimulationState
from fbf.core.execution.pipeline.simulation_context import SimulationContext

EQUITY_ASSET = AssetClass(id="equity", name="", description="")
BOND_ASSET = AssetClass(id="bond", name="", description="")

INITIAL_WEALTH = Decimal("1000000")
BUDGET = INITIAL_WEALTH * Decimal("0.0391") / Decimal("12")
WITHDRAWAL_RATE = Decimal("0.0391")
BORROW_PCT = Decimal("0.4108")
DRAWDOWN_THRESHOLD = Decimal("0.20")
LTV_LIMIT = Decimal("0.50")


def _create_dataset() -> Dataset:
    """Create a 6-month dataset with known market conditions."""
    snapshots = [
        MarketSnapshot(
            date=date(1965, 11, 1),
            index_levels={EQUITY_ASSET: Decimal("100"), BOND_ASSET: Decimal("100")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=True,
            is_underwater=False,
            running_ath=Decimal("100"),
        ),
        MarketSnapshot(
            date=date(1965, 12, 1),
            index_levels={EQUITY_ASSET: Decimal("75"), BOND_ASSET: Decimal("100")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=False,
            is_underwater=True,
            running_ath=Decimal("100"),
        ),
        MarketSnapshot(
            date=date(1966, 1, 1),
            index_levels={EQUITY_ASSET: Decimal("70"), BOND_ASSET: Decimal("100")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=False,
            is_underwater=True,
            running_ath=Decimal("100"),
        ),
        MarketSnapshot(
            date=date(1966, 2, 1),
            index_levels={EQUITY_ASSET: Decimal("110"), BOND_ASSET: Decimal("100")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=True,
            is_underwater=False,
            running_ath=Decimal("110"),
        ),
        MarketSnapshot(
            date=date(1966, 3, 1),
            index_levels={EQUITY_ASSET: Decimal("115"), BOND_ASSET: Decimal("100")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=True,
            is_underwater=False,
            running_ath=Decimal("115"),
        ),
        MarketSnapshot(
            date=date(1966, 4, 1),
            index_levels={EQUITY_ASSET: Decimal("120"), BOND_ASSET: Decimal("100")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=True,
            is_underwater=False,
            running_ath=Decimal("120"),
        ),
    ]
    return Dataset(
        identifier="test",
        snapshots=tuple(snapshots),
        frequency="monthly",
        version="test",
    )


def test_ffr_schedule_used_in_interest_accrual() -> None:
    """Verify that InterestAccrualStep uses the FFR schedule correctly."""
    dataset = _create_dataset()
    initial_portfolio = Portfolio(
        holdings=(
            AssetHolding(asset_class=EQUITY_ASSET, units=Decimal("7500")),
            AssetHolding(asset_class=BOND_ASSET, units=Decimal("2500")),
        )
    )

    # FFR schedule: varying rates per month (simulating FFR + spread)
    ffr_schedule = (
        Decimal("0.0400"),  # Month 0: 4.00%
        Decimal("0.0450"),  # Month 1: 4.50%
        Decimal("0.0500"),  # Month 2: 5.00%
        Decimal("0.0450"),  # Month 3: 4.50%
        Decimal("0.0400"),  # Month 4: 4.00%
        Decimal("0.0350"),  # Month 5: 3.50%
    )

    sim_context = SimulationContext(
        experiment_name="test",
        cohort="1965-11",
        start_date=date(1965, 11, 1),
        horizon_months=6,
        initial_wealth=Money(INITIAL_WEALTH, Currency.EUR),
        initial_portfolio=initial_portfolio,
        dataset=dataset,
        allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.75")),
        withdrawal_policy=Part52WithdrawalPolicy(
            withdrawal_rate=WITHDRAWAL_RATE,
            borrow_pct=BORROW_PCT,
            drawdown_threshold=DRAWDOWN_THRESHOLD,
        ),
        interest_rate=None,  # No fixed rate
        interest_rate_schedule=ffr_schedule,
        ltv_limit=LTV_LIMIT,
        ltv_enforcement=False,
    )

    pipeline = create_default_pipeline()
    state = SimulationState(
        context=sim_context,
        current_date=date(1965, 11, 1),
        period_index=0,
        portfolio=initial_portfolio,
        loan_balance=Decimal("0"),
        cash_balance=Decimal("0"),
        interest_rate=Decimal("0"),
        ltv_limit=LTV_LIMIT,
        ltv_enforcement=False,
    )

    # Execute Month 0: Normal (ATH) — no borrowing
    state.market_snapshot = dataset.snapshots[0]
    state = pipeline.execute(state)
    assert state.loan_balance == Decimal("0")

    # Execute Month 1: Drawdown below threshold — borrowing
    state.market_snapshot = dataset.snapshots[1]
    state.period_index = 1
    state.current_date = date(1965, 12, 1)
    state = pipeline.execute(state)
    loan_after_m1 = state.loan_balance
    assert loan_after_m1 > Decimal("0"), "Should have borrowed in Month 1"

    # Execute Month 2: Interest accrues at FFR schedule rate for month 2
    state.market_snapshot = dataset.snapshots[2]
    state.period_index = 2
    state.current_date = date(1966, 1, 1)
    state = pipeline.execute(state)

    # Interest should be: loan_after_m1 * (0.0500 / 12)
    expected_interest_m2 = loan_after_m1 * ffr_schedule[2] / Decimal("12")
    expected_loan_m2 = loan_after_m1 + expected_interest_m2
    assert state.loan_balance == expected_loan_m2, (
        f"Interest accrual should use FFR schedule rate for month 2: "
        f"expected {expected_loan_m2}, got {state.loan_balance}"
    )


def test_ffr_schedule_zero_spread_matches_fixed_rate() -> None:
    """Verify that FFR schedule with zero spread behaves like fixed rate."""
    dataset = _create_dataset()
    initial_portfolio = Portfolio(
        holdings=(
            AssetHolding(asset_class=EQUITY_ASSET, units=Decimal("7500")),
            AssetHolding(asset_class=BOND_ASSET, units=Decimal("2500")),
        )
    )

    fixed_rate = Decimal("0.0400")

    # Create two contexts: one with fixed rate, one with FFR schedule
    def _run_simulation(
        interest_rate: Decimal | None, schedule: tuple[Decimal, ...] | None
    ) -> SimulationState:
        sim_context = SimulationContext(
            experiment_name="test",
            cohort="1965-11",
            start_date=date(1965, 11, 1),
            horizon_months=3,
            initial_wealth=Money(INITIAL_WEALTH, Currency.EUR),
            initial_portfolio=initial_portfolio,
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.75")),
            withdrawal_policy=Part52WithdrawalPolicy(
                withdrawal_rate=WITHDRAWAL_RATE,
                borrow_pct=BORROW_PCT,
                drawdown_threshold=DRAWDOWN_THRESHOLD,
            ),
            interest_rate=interest_rate,
            interest_rate_schedule=schedule,
            ltv_limit=LTV_LIMIT,
            ltv_enforcement=False,
        )
        pipeline = create_default_pipeline()
        state = SimulationState(
            context=sim_context,
            current_date=date(1965, 11, 1),
            period_index=0,
            portfolio=initial_portfolio,
            loan_balance=Decimal("0"),
            cash_balance=Decimal("0"),
            interest_rate=interest_rate or Decimal("0"),
            ltv_limit=LTV_LIMIT,
            ltv_enforcement=False,
        )
        # Execute Month 0: Normal
        state.market_snapshot = dataset.snapshots[0]
        state = pipeline.execute(state)
        # Execute Month 1: Borrow
        state.market_snapshot = dataset.snapshots[1]
        state.period_index = 1
        state.current_date = date(1965, 12, 1)
        state = pipeline.execute(state)
        # Execute Month 2: Interest accrues
        state.market_snapshot = dataset.snapshots[2]
        state.period_index = 2
        state.current_date = date(1966, 1, 1)
        state = pipeline.execute(state)
        return state

    # Fixed rate simulation
    state_fixed = _run_simulation(interest_rate=fixed_rate, schedule=None)

    # FFR schedule with same rate in every month
    ffr_schedule = (fixed_rate, fixed_rate, fixed_rate)
    state_ffr = _run_simulation(interest_rate=None, schedule=ffr_schedule)

    # Loan balances should be identical
    assert state_fixed.loan_balance == state_ffr.loan_balance, (
        f"FFR schedule with constant rate should match fixed rate: "
        f"fixed={state_fixed.loan_balance}, ffr={state_ffr.loan_balance}"
    )


def test_no_schedule_falls_back_to_fixed_rate() -> None:
    """Verify that missing FFR schedule uses fixed interest_rate."""
    dataset = _create_dataset()
    initial_portfolio = Portfolio(
        holdings=(
            AssetHolding(asset_class=EQUITY_ASSET, units=Decimal("7500")),
            AssetHolding(asset_class=BOND_ASSET, units=Decimal("2500")),
        )
    )

    fixed_rate = Decimal("0.0450")

    sim_context = SimulationContext(
        experiment_name="test",
        cohort="1965-11",
        start_date=date(1965, 11, 1),
        horizon_months=3,
        initial_wealth=Money(INITIAL_WEALTH, Currency.EUR),
        initial_portfolio=initial_portfolio,
        dataset=dataset,
        allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.75")),
        withdrawal_policy=Part52WithdrawalPolicy(
            withdrawal_rate=WITHDRAWAL_RATE,
            borrow_pct=BORROW_PCT,
            drawdown_threshold=DRAWDOWN_THRESHOLD,
        ),
        interest_rate=fixed_rate,
        interest_rate_schedule=None,  # No FFR schedule
        ltv_limit=LTV_LIMIT,
        ltv_enforcement=False,
    )

    pipeline = create_default_pipeline()
    state = SimulationState(
        context=sim_context,
        current_date=date(1965, 11, 1),
        period_index=0,
        portfolio=initial_portfolio,
        loan_balance=Decimal("0"),
        cash_balance=Decimal("0"),
        interest_rate=fixed_rate,
        ltv_limit=LTV_LIMIT,
        ltv_enforcement=False,
    )

    # Execute Month 0: Normal
    state.market_snapshot = dataset.snapshots[0]
    state = pipeline.execute(state)
    # Execute Month 1: Borrow
    state.market_snapshot = dataset.snapshots[1]
    state.period_index = 1
    state.current_date = date(1965, 12, 1)
    state = pipeline.execute(state)
    loan_after_m1 = state.loan_balance
    assert loan_after_m1 > Decimal("0")

    # Execute Month 2: Interest accrues at fixed rate
    state.market_snapshot = dataset.snapshots[2]
    state.period_index = 2
    state.current_date = date(1966, 1, 1)
    state = pipeline.execute(state)

    expected_interest = loan_after_m1 * fixed_rate / Decimal("12")
    expected_loan = loan_after_m1 + expected_interest
    assert state.loan_balance == expected_loan
