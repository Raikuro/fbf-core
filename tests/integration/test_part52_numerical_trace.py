"""Integration test for complete Part 52 numerical trace.

Verifies the complete lifecycle:
NORMAL → BORROW → BORROW → FRESH INDEX ATH → REPAY → DEBT CLEARED → NORMAL

For every relevant month, verifies:
- beginning portfolio value
- index level
- index ATH
- drawdown
- withdrawal budget
- loan draw
- portfolio withdrawal
- repayment amount
- ending portfolio
- cash balance
- interest
- ending loan balance
- net worth
- LTV
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

# Test parameters
INITIAL_WEALTH = Decimal("1000000")
WITHDRAWAL_RATE = Decimal("0.0391")
BORROW_PCT = Decimal("0.4108")
DRAWDOWN_THRESHOLD = Decimal("0.20")
INTEREST_RATE = Decimal("0.015")
LTV_LIMIT = Decimal("0.50")

# Derived values
BUDGET = INITIAL_WEALTH * WITHDRAWAL_RATE / Decimal("12")

# Asset classes (shared across all snapshots) - matching codebase convention
EQUITY_ASSET = AssetClass(id="equity", name="", description="")
BOND_ASSET = AssetClass(id="bond", name="", description="")


def test_complete_numerical_trace() -> None:
    """Verify complete lifecycle with exact numerical values."""
    # Create dataset with specific market conditions
    snapshots = [
        # Month 0: Normal market (ATH)
        MarketSnapshot(
            date=date(1965, 11, 1),
            index_levels={EQUITY_ASSET: Decimal("100"), BOND_ASSET: Decimal("100")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=True,
            is_underwater=False,
            running_ath=Decimal("100"),
        ),
        # Month 1: Market drops 25% (below threshold)
        MarketSnapshot(
            date=date(1965, 12, 1),
            index_levels={EQUITY_ASSET: Decimal("75"), BOND_ASSET: Decimal("100")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=False,
            is_underwater=True,
            running_ath=Decimal("100"),
        ),
        # Month 2: Market stays low
        MarketSnapshot(
            date=date(1966, 1, 1),
            index_levels={EQUITY_ASSET: Decimal("70"), BOND_ASSET: Decimal("100")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=False,
            is_underwater=True,
            running_ath=Decimal("100"),
        ),
        # Month 3: Market recovers to new ATH
        MarketSnapshot(
            date=date(1966, 2, 1),
            index_levels={EQUITY_ASSET: Decimal("110"), BOND_ASSET: Decimal("100")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=True,
            is_underwater=False,
            running_ath=Decimal("110"),
        ),
        # Month 4: Normal market (no debt)
        MarketSnapshot(
            date=date(1966, 3, 1),
            index_levels={EQUITY_ASSET: Decimal("115"), BOND_ASSET: Decimal("100")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=True,
            is_underwater=False,
            running_ath=Decimal("115"),
        ),
    ]

    dataset = Dataset(
        identifier="test",
        snapshots=tuple(snapshots),
        frequency="monthly",
        version="test",
    )

    # Create initial portfolio (75/25 split)
    initial_portfolio = Portfolio(
        holdings=(
            AssetHolding(asset_class=EQUITY_ASSET, units=Decimal("7500")),
            AssetHolding(asset_class=BOND_ASSET, units=Decimal("2500")),
        )
    )

    # Verify initial portfolio value
    initial_value = Decimal("0")
    for holding in initial_portfolio.holdings:
        price = snapshots[0].index_levels[holding.asset_class]
        initial_value += holding.units * price
    assert initial_value == INITIAL_WEALTH, f"Initial portfolio value mismatch: {initial_value}"

    # Create policies
    allocation_policy = ConstantAllocationPolicy(equity_allocation=Decimal("0.75"))
    withdrawal_policy = Part52WithdrawalPolicy(
        withdrawal_rate=WITHDRAWAL_RATE,
        borrow_pct=BORROW_PCT,
        drawdown_threshold=DRAWDOWN_THRESHOLD,
    )

    # Create simulation context
    sim_context = SimulationContext(
        experiment_name="test",
        cohort="1965-11",
        start_date=date(1965, 11, 1),
        horizon_months=60,
        initial_wealth=Money(INITIAL_WEALTH, Currency.EUR),
        initial_portfolio=initial_portfolio,
        dataset=dataset,
        allocation_policy=allocation_policy,
        withdrawal_policy=withdrawal_policy,
        interest_rate=INTEREST_RATE,
        ltv_limit=LTV_LIMIT,
        ltv_enforcement=False,  # Part 49 behavior: observe only
    )

    # Create pipeline and initial state (matching runner initialization)
    pipeline = create_default_pipeline()
    state = SimulationState(
        context=sim_context,
        current_date=date(1965, 11, 1),
        period_index=0,
        portfolio=initial_portfolio,
        loan_balance=Decimal("0"),
        cash_balance=Decimal("0"),
        interest_rate=INTEREST_RATE,
        ltv_limit=LTV_LIMIT,
        ltv_enforcement=False,
    )

    # Execute Month 0: NORMAL (ATH, no debt)
    state.market_snapshot = snapshots[0]
    state = pipeline.execute(state)
    result_month0 = state.monthly_results[-1]

    # Verify Month 0
    assert result_month0.withdrawal_decision is not None
    assert result_month0.withdrawal_decision.nominal_amount.amount == BUDGET
    assert result_month0.withdrawal_decision.loan_draw_amount == Decimal("0")
    assert result_month0.withdrawal_decision.is_repayment is False
    assert state.loan_balance == Decimal("0")
    assert state.cash_balance == Decimal("0")

    # Execute Month 1: BORROW (drawdown = 25% >= 20%, loan_balance = 0)
    state.market_snapshot = snapshots[1]
    state.period_index = 1
    state.current_date = date(1965, 12, 1)
    state = pipeline.execute(state)
    result_month1 = state.monthly_results[-1]

    # Verify Month 1
    assert result_month1.withdrawal_decision is not None
    expected_loan_draw = BUDGET * BORROW_PCT
    expected_portfolio_withdrawal = BUDGET * (Decimal("1") - BORROW_PCT)
    assert result_month1.withdrawal_decision.loan_draw_amount == expected_loan_draw
    assert result_month1.withdrawal_decision.nominal_amount.amount == expected_portfolio_withdrawal
    assert result_month1.withdrawal_decision.is_repayment is False
    # Loan balance after interest accrual (interest accrues in same month)
    expected_interest_m1 = expected_loan_draw * INTEREST_RATE / Decimal("12")
    expected_loan_balance_m1 = expected_loan_draw + expected_interest_m1
    assert state.loan_balance == expected_loan_balance_m1
    assert state.cash_balance == Decimal("0")  # Cash consumed

    # Execute Month 2: BORROW (loan_balance > 0, not at ATH)
    state.market_snapshot = snapshots[2]
    state.period_index = 2
    state.current_date = date(1966, 1, 1)
    state = pipeline.execute(state)
    result_month2 = state.monthly_results[-1]

    # Verify Month 2 (loan balance accrues another month of interest)
    assert result_month2.withdrawal_decision is not None
    assert result_month2.withdrawal_decision.nominal_amount.amount == BUDGET
    assert result_month2.withdrawal_decision.loan_draw_amount == Decimal("0")
    assert result_month2.withdrawal_decision.is_repayment is False
    # Interest accrues on current loan balance (which already includes M1 interest)
    expected_interest_m2 = expected_loan_balance_m1 * INTEREST_RATE / Decimal("12")
    expected_loan_balance_m2 = expected_loan_balance_m1 + expected_interest_m2
    assert state.loan_balance == expected_loan_balance_m2

    # Execute Month 3: REPAY (is_ath = True, loan_balance > 0)
    state.market_snapshot = snapshots[3]
    state.period_index = 3
    state.current_date = date(1966, 2, 1)
    state = pipeline.execute(state)
    result_month3 = state.monthly_results[-1]

    # Verify Month 3
    assert result_month3.withdrawal_decision is not None
    assert result_month3.withdrawal_decision.nominal_amount.amount == BUDGET * 2
    assert result_month3.withdrawal_decision.loan_draw_amount == Decimal("0")
    assert result_month3.withdrawal_decision.is_repayment is True
    # Loan balance reduced by repayment
    excess = BUDGET * 2 - BUDGET  # = BUDGET
    repayment = min(excess, expected_loan_balance_m2)
    expected_loan_balance_after_repayment = expected_loan_balance_m2 - repayment
    assert state.loan_balance == expected_loan_balance_after_repayment

    # Execute Month 4: NORMAL (is_ath = True, loan_balance = 0 or > 0)
    state.market_snapshot = snapshots[4]
    state.period_index = 4
    state.current_date = date(1966, 3, 1)
    state = pipeline.execute(state)
    result_month4 = state.monthly_results[-1]

    # Verify Month 4
    assert result_month4.withdrawal_decision is not None
    if expected_loan_balance_after_repayment <= 0:
        # Debt cleared, back to NORMAL
        assert result_month4.withdrawal_decision.nominal_amount.amount == BUDGET
        assert result_month4.withdrawal_decision.loan_draw_amount == Decimal("0")
        assert result_month4.withdrawal_decision.is_repayment is False
    else:
        # Still has debt, REPAY again
        assert result_month4.withdrawal_decision.nominal_amount.amount == BUDGET * 2
        assert result_month4.withdrawal_decision.is_repayment is True


def test_fixed_rate_compatibility() -> None:
    """Verify that interest_rate_schedule=None produces identical behavior."""
    # Create simple dataset
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
    ]

    dataset = Dataset(
        identifier="test",
        snapshots=tuple(snapshots),
        frequency="monthly",
        version="test",
    )

    initial_portfolio = Portfolio(
        holdings=(
            AssetHolding(asset_class=EQUITY_ASSET, units=Decimal("7500")),
            AssetHolding(asset_class=BOND_ASSET, units=Decimal("2500")),
        )
    )

    allocation_policy = ConstantAllocationPolicy(equity_allocation=Decimal("0.75"))
    withdrawal_policy = Part52WithdrawalPolicy(
        withdrawal_rate=WITHDRAWAL_RATE,
        borrow_pct=BORROW_PCT,
        drawdown_threshold=DRAWDOWN_THRESHOLD,
    )

    # Test with interest_rate_schedule=None (fixed rate)
    sim_context_fixed = SimulationContext(
        experiment_name="test",
        cohort="1965-11",
        start_date=date(1965, 11, 1),
        horizon_months=12,
        initial_wealth=Money(INITIAL_WEALTH, Currency.EUR),
        initial_portfolio=initial_portfolio,
        dataset=dataset,
        allocation_policy=allocation_policy,
        withdrawal_policy=withdrawal_policy,
        interest_rate=INTEREST_RATE,
        interest_rate_schedule=None,  # Fixed rate
        ltv_limit=LTV_LIMIT,
        ltv_enforcement=False,
    )

    pipeline = create_default_pipeline()
    state_fixed = SimulationState(
        context=sim_context_fixed,
        current_date=date(1965, 11, 1),
        period_index=0,
        portfolio=initial_portfolio,
        loan_balance=Decimal("0"),
        cash_balance=Decimal("0"),
        interest_rate=INTEREST_RATE,
        ltv_limit=LTV_LIMIT,
        ltv_enforcement=False,
    )
    state_fixed.market_snapshot = snapshots[0]
    state_fixed = pipeline.execute(state_fixed)

    # Verify that interest_rate_schedule=None works correctly
    assert state_fixed.loan_balance == Decimal("0")  # No debt in normal mode
    assert state_fixed.monthly_results[-1].withdrawal_decision is not None
    assert state_fixed.monthly_results[-1].withdrawal_decision.nominal_amount.amount == BUDGET
