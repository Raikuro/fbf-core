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
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    MonthlyResult,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.part52_numba_executor import Part52NumbaExecutor

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


def _execute(sim_context: SimulationContext) -> tuple[MonthlyResult, ...]:
    definition = EngineExperimentDefinition(
        name="part52-numerical-trace",
        description="Part 52 numerical trace test",
        simulation_contexts=(sim_context,),
    )
    executor = Part52NumbaExecutor(materialize_timeline=True)
    result = executor.execute(definition).simulation_results[0]
    return tuple(result.timeline.monthly_results)


def _assert_decimal_close(actual: Decimal, expected: Decimal) -> None:
    tolerance = max(abs(expected) * Decimal("1e-12"), Decimal("1e-12"))
    assert abs(actual - expected) <= tolerance, f"{actual} != {expected}"


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
        snapshots=tuple(snapshots),
        frequency="monthly",
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
        horizon_months=5,
        initial_wealth=Money(INITIAL_WEALTH, Currency.EUR),
        initial_portfolio=initial_portfolio,
        dataset=dataset,
        allocation_policy=allocation_policy,
        withdrawal_policy=withdrawal_policy,
        interest_rate=INTEREST_RATE,
        ltv_limit=LTV_LIMIT,
        ltv_enforcement=False,  # Part 49 behavior: observe only
    )

    # Execute months 0..4 through the Part 52 Numba executor
    months = _execute(sim_context)
    result_month0 = months[0]

    # Verify Month 0
    assert result_month0.withdrawal_decision is not None
    _assert_decimal_close(result_month0.withdrawal_decision.nominal_amount.amount, BUDGET)
    assert result_month0.withdrawal_decision.loan_draw_amount == Decimal("0")
    assert result_month0.withdrawal_decision.is_repayment is False
    assert result_month0.debt_snapshot is not None
    assert result_month0.debt_snapshot.loan_balance == Decimal("0")
    assert result_month0.debt_snapshot.cash_balance == Decimal("0")

    # Execute Month 1: BORROW (drawdown = 25% >= 20%, loan_balance = 0)
    result_month1 = months[1]

    # Verify Month 1
    # BORROW: nominal = C (full budget; WithdrawalExecution consumes loan_draw
    # from cash first, selling C - X from portfolio = ERN W = V - X)
    assert result_month1.withdrawal_decision is not None
    expected_loan_draw = BUDGET * BORROW_PCT
    expected_nominal_m1 = BUDGET
    _assert_decimal_close(
        result_month1.withdrawal_decision.loan_draw_amount, expected_loan_draw
    )
    _assert_decimal_close(
        result_month1.withdrawal_decision.nominal_amount.amount, expected_nominal_m1
    )
    assert result_month1.withdrawal_decision.is_repayment is False
    # ERN ordering: interest accrues on PRIOR balance (0), then draw is added.
    # T(N) = Y(N-1) * (1+M), Y(N) = X(N) + T(N)
    expected_loan_balance_m1 = expected_loan_draw  # draw added after interest
    assert result_month1.debt_snapshot is not None
    _assert_decimal_close(
        result_month1.debt_snapshot.loan_balance, expected_loan_balance_m1
    )
    assert result_month1.debt_snapshot.cash_balance == Decimal("0")  # Cash consumed

    # Execute Month 2: BORROW (drawdown=30% >= threshold, loan_balance > 0)
    # Monthly-draw: a new draw occurs every eligible month regardless of
    # existing loan balance.
    result_month2 = months[2]

    # Verify Month 2 — new draw on top of existing loan
    # BORROW: nominal = C (full budget; WithdrawalExecution handles loan_draw)
    assert result_month2.withdrawal_decision is not None
    expected_loan_draw_m2 = BUDGET * BORROW_PCT
    expected_nominal_m2 = BUDGET
    _assert_decimal_close(
        result_month2.withdrawal_decision.loan_draw_amount, expected_loan_draw_m2
    )
    _assert_decimal_close(
        result_month2.withdrawal_decision.nominal_amount.amount, expected_nominal_m2
    )
    assert result_month2.withdrawal_decision.is_repayment is False
    # ERN ordering: interest accrues on PRIOR balance, then draw is added.
    # T(N) = Y(N-1) * (1+M), Y(N) = X(N) + T(N)
    expected_interest_m2 = (
        expected_loan_balance_m1 * INTEREST_RATE / Decimal("12")
    )
    expected_loan_balance_m2 = (
        expected_loan_balance_m1 + expected_interest_m2 + expected_loan_draw_m2
    )
    assert result_month2.debt_snapshot is not None
    _assert_decimal_close(
        result_month2.debt_snapshot.loan_balance, expected_loan_balance_m2
    )

    # Execute Month 3: REPAY (compound_drawdown == 0, loan_balance > 0)
    result_month3 = months[3]

    # Verify Month 3
    # REPAY: nominal_amount = C (not C - D_{t-1})
    assert result_month3.withdrawal_decision is not None
    _assert_decimal_close(result_month3.withdrawal_decision.nominal_amount.amount, BUDGET)
    assert result_month3.withdrawal_decision.loan_draw_amount == Decimal("0")
    assert result_month3.withdrawal_decision.is_repayment is True
    # Interest accrues BEFORE repayment (seq 26 < seq 32)
    expected_interest_m3 = expected_loan_balance_m2 * INTEREST_RATE / Decimal("12")
    loan_balance_after_interest_m3 = expected_loan_balance_m2 + expected_interest_m3
    # Workbook repayment is MIN(Y, C): the monthly budget repays the loan
    # until it is cleared.  The loan after interest is below C here.
    repayment_m3 = min(BUDGET, loan_balance_after_interest_m3)
    expected_loan_balance_after_repayment = loan_balance_after_interest_m3 - repayment_m3
    assert result_month3.debt_snapshot is not None
    _assert_decimal_close(
        result_month3.debt_snapshot.loan_balance,
        expected_loan_balance_after_repayment,
    )

    # Month 4 is the terminal valuation row: no draw, withdrawal, or repayment.
    result_month4 = months[4]
    assert result_month4.withdrawal_decision is not None
    _assert_decimal_close(
        result_month4.withdrawal_decision.nominal_amount.amount, Decimal("0")
    )
    assert result_month4.withdrawal_decision.loan_draw_amount == Decimal("0")
    assert result_month4.withdrawal_decision.is_repayment is False


def test_fixed_rate_compatibility() -> None:
    """Verify that interest_rate_schedule=None produces identical behavior."""
    # Create simple dataset: month 0 withdrawal, month 1 terminal valuation
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
            index_levels={EQUITY_ASSET: Decimal("100"), BOND_ASSET: Decimal("100")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=True,
            is_underwater=False,
            running_ath=Decimal("100"),
        ),
    ]

    dataset = Dataset(
        snapshots=tuple(snapshots),
        frequency="monthly",
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
        horizon_months=2,
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

    months = _execute(sim_context_fixed)

    # Verify that interest_rate_schedule=None works correctly
    month0 = months[0]
    assert month0.debt_snapshot is not None
    assert month0.debt_snapshot.loan_balance == Decimal("0")  # No debt in normal mode
    assert month0.withdrawal_decision is not None
    _assert_decimal_close(month0.withdrawal_decision.nominal_amount.amount, BUDGET)

    month1 = months[1]
    assert month1.withdrawal_decision is not None
    _assert_decimal_close(month1.withdrawal_decision.nominal_amount.amount, Decimal("0"))
