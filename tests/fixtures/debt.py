"""Controlled fixtures for Part 49 debt-transition testing.

Provides deterministic scenarios, parameters, and expected results for
validating the debt engine implementation against the independent oracle.

All fixtures use domain model primitives directly. No production
debt or execution logic is imported.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import NamedTuple

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.money import Currency, Money

# Canonical asset classes matching the codebase convention.
EQUITY = AssetClass(id="equity", name="", description="")
BOND = AssetClass(id="bond", name="", description="")


# ---------------------------------------------------------------------------
# Parameter fixtures
# ---------------------------------------------------------------------------

# Standard Part 49 parameters
STANDARD_INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)
STANDARD_WITHDRAWAL_RATE = Decimal("0.04")
STANDARD_LOAN_DRAW_RATE = Decimal("0.01")
STANDARD_ANNUAL_INTEREST_RATE = Decimal("0.06")
STANDARD_LTV_LIMIT = Decimal("0.75")
STANDARD_HORIZON_MONTHS = 360


# ---------------------------------------------------------------------------
# Oracle reference results
# ---------------------------------------------------------------------------

class OracleMonthResult(NamedTuple):
    """Expected result from the oracle for a single month transition."""

    portfolio_value: Decimal
    loan_balance: Decimal
    ltv: Decimal
    interest_accrued: Decimal
    liquidation_amount: Decimal
    net_worth: Decimal
    is_margin_call: bool
    is_unsatisfiable: bool
    is_failure: bool


@dataclass(frozen=True)
class DebtScenario:
    """A complete debt scenario with input state and expected results."""

    name: str
    description: str
    initial_portfolio_value: Decimal
    initial_loan_balance: Decimal
    annual_interest_rate: Decimal
    ltv_limit: Decimal
    market_return: Decimal
    expected: OracleMonthResult


# ---------------------------------------------------------------------------
# Scenario 1: Basic borrowing (no margin call)
# ---------------------------------------------------------------------------

SCENARIO_BASIC_BORROWING = DebtScenario(
    name="basic_borrowing",
    description="Basic borrowing with no margin call",
    initial_portfolio_value=Decimal("1000000"),
    initial_loan_balance=Decimal("100000"),
    annual_interest_rate=Decimal("0.06"),
    ltv_limit=Decimal("0.75"),
    market_return=Decimal("0.01"),  # 1% gain
    expected=OracleMonthResult(
        portfolio_value=Decimal("1010000"),  # 1M * 1.01
        loan_balance=Decimal("100500"),  # 100K + 500 interest
        ltv=Decimal("0.09950495049504950495049504950"),
        interest_accrued=Decimal("500"),
        liquidation_amount=Decimal("0"),
        net_worth=Decimal("909500"),
        is_margin_call=False,
        is_unsatisfiable=False,
        is_failure=False,
    ),
)


# ---------------------------------------------------------------------------
# Scenario 2: Market loss triggering margin call
# ---------------------------------------------------------------------------

SCENARIO_MARGIN_CALL = DebtScenario(
    name="margin_call",
    description="Market loss triggering margin call",
    initial_portfolio_value=Decimal("1000000"),
    initial_loan_balance=Decimal("800000"),
    annual_interest_rate=Decimal("0.06"),
    ltv_limit=Decimal("0.75"),
    market_return=Decimal("-0.20"),  # 20% loss
    expected=OracleMonthResult(
        # Portfolio after 20% loss: 1M * 0.8 = 800K
        # Loan after interest: 800K + 4K = 804K
        # LTV: 804K / 800K = 1.005 > 0.75 → margin call
        # Liquidation: (804K - 0.75 * 800K) / (1 - 0.75) = 204K / 0.25 = 816K
        # But 816K > 800K (portfolio) → unsatisfiable
        # Result: sell entire portfolio, partial repayment
        portfolio_value=Decimal("0"),
        loan_balance=Decimal("4000"),  # 804K - 800K
        ltv=Decimal("0"),  # No portfolio
        interest_accrued=Decimal("4000"),
        liquidation_amount=Decimal("800000"),  # Sell entire portfolio
        net_worth=Decimal("-4000"),
        is_margin_call=True,
        is_unsatisfiable=True,
        is_failure=True,
    ),
)


# ---------------------------------------------------------------------------
# Scenario 3: Margin call with proportional liquidation
# ---------------------------------------------------------------------------

SCENARIO_PROPORTIONAL_LIQUIDATION = DebtScenario(
    name="proportional_liquidation",
    description="Margin call with proportional liquidation restoring LTV",
    initial_portfolio_value=Decimal("1000000"),
    initial_loan_balance=Decimal("800000"),
    annual_interest_rate=Decimal("0.06"),
    ltv_limit=Decimal("0.75"),
    market_return=Decimal("-0.10"),  # 10% loss
    expected=OracleMonthResult(
        # Portfolio after 10% loss: 1M * 0.9 = 900K
        # Loan after interest: 800K + 4K = 804K
        # LTV: 804K / 900K = 0.8933 > 0.75 → margin call
        # Liquidation: (804K - 0.75 * 900K) / (1 - 0.75) = 129K / 0.25 = 516K
        # After: P = 900K - 516K = 384K, L = 804K - 516K = 288K
        # LTV: 288K / 384K = 0.75 ✓
        portfolio_value=Decimal("384000"),
        loan_balance=Decimal("288000"),
        ltv=Decimal("0.75"),
        interest_accrued=Decimal("4000"),
        liquidation_amount=Decimal("516000"),
        net_worth=Decimal("96000"),
        is_margin_call=True,
        is_unsatisfiable=False,
        is_failure=False,
    ),
)


# ---------------------------------------------------------------------------
# Scenario 4: Zero-debt scenario
# ---------------------------------------------------------------------------

SCENARIO_ZERO_DEBT = DebtScenario(
    name="zero_debt",
    description="No debt, standard market return",
    initial_portfolio_value=Decimal("1000000"),
    initial_loan_balance=Decimal("0"),
    annual_interest_rate=Decimal("0.06"),
    ltv_limit=Decimal("0.75"),
    market_return=Decimal("0.01"),  # 1% gain
    expected=OracleMonthResult(
        portfolio_value=Decimal("1010000"),
        loan_balance=Decimal("0"),
        ltv=Decimal("0"),
        interest_accrued=Decimal("0"),
        liquidation_amount=Decimal("0"),
        net_worth=Decimal("1010000"),
        is_margin_call=False,
        is_unsatisfiable=False,
        is_failure=False,
    ),
)


# ---------------------------------------------------------------------------
# Scenario 5: Zero-portfolio boundary
# ---------------------------------------------------------------------------

SCENARIO_ZERO_PORTFOLIO = DebtScenario(
    name="zero_portfolio",
    description="Zero portfolio with positive debt",
    initial_portfolio_value=Decimal("0"),
    initial_loan_balance=Decimal("100000"),
    annual_interest_rate=Decimal("0.06"),
    ltv_limit=Decimal("0.75"),
    market_return=Decimal("0"),  # No return
    expected=OracleMonthResult(
        portfolio_value=Decimal("0"),
        loan_balance=Decimal("100500"),  # 100K + 500 interest
        ltv=Decimal("999999"),  # Effectively infinite
        interest_accrued=Decimal("500"),
        liquidation_amount=Decimal("0"),  # Can't sell nothing
        net_worth=Decimal("-100500"),
        is_margin_call=True,
        is_unsatisfiable=True,
        is_failure=True,
    ),
)


# ---------------------------------------------------------------------------
# Scenario 6: Loan equals portfolio (boundary)
# ---------------------------------------------------------------------------

SCENARIO_LOAN_EQUALS_PORTFOLIO = DebtScenario(
    name="loan_equals_portfolio",
    description="Loan balance equals portfolio value",
    initial_portfolio_value=Decimal("1000000"),
    initial_loan_balance=Decimal("1000000"),
    annual_interest_rate=Decimal("0.06"),
    ltv_limit=Decimal("0.75"),
    market_return=Decimal("0"),  # No return
    expected=OracleMonthResult(
        # LTV: 1M / 1M = 1.0 > 0.75 → margin call
        # Interest: 1M * 0.06 / 12 = 5000
        # Loan after interest: 1,005,000
        # Liquidation: (1,005,000 - 0.75 * 1M) / (1 - 0.75) = 255,000 / 0.25 = 1,020,000
        # But 1,020,000 > 1M (portfolio) → unsatisfiable
        # Sell entire portfolio, repay loan
        portfolio_value=Decimal("0"),
        loan_balance=Decimal("5000"),  # 1,005,000 - 1,000,000
        ltv=Decimal("0"),
        interest_accrued=Decimal("5000"),
        liquidation_amount=Decimal("1000000"),  # Sell entire portfolio
        net_worth=Decimal("-5000"),
        is_margin_call=True,
        is_unsatisfiable=True,
        is_failure=True,
    ),
)


# ---------------------------------------------------------------------------
# Scenario 7: Interest accrual verification
# ---------------------------------------------------------------------------

SCENARIO_INTEREST_ACCRUAL = DebtScenario(
    name="interest_accrual",
    description="Verify interest accrual mechanics",
    initial_portfolio_value=Decimal("1000000"),
    initial_loan_balance=Decimal("100000"),
    annual_interest_rate=Decimal("0.12"),  # 12% for easy calculation
    ltv_limit=Decimal("0.75"),
    market_return=Decimal("0"),  # No return
    expected=OracleMonthResult(
        portfolio_value=Decimal("1000000"),
        loan_balance=Decimal("101000"),  # 100K + 1K interest (1% monthly)
        ltv=Decimal("0.101"),
        interest_accrued=Decimal("1000"),
        liquidation_amount=Decimal("0"),
        net_worth=Decimal("899000"),
        is_margin_call=False,
        is_unsatisfiable=False,
        is_failure=False,
    ),
)


# ---------------------------------------------------------------------------
# Scenario 8: LTV exactly at limit (no margin call)
# ---------------------------------------------------------------------------

SCENARIO_LTV_AT_LIMIT = DebtScenario(
    name="ltv_at_limit",
    description="LTV exactly at limit before interest, margin call after",
    initial_portfolio_value=Decimal("1000000"),
    initial_loan_balance=Decimal("750000"),  # 75% LTV
    annual_interest_rate=Decimal("0.06"),
    ltv_limit=Decimal("0.75"),
    market_return=Decimal("0"),  # No return
    expected=OracleMonthResult(
        # Before interest: LTV = 750K / 1M = 0.75 = limit
        # After interest: Loan = 750K + 3750 = 753750
        # LTV: 753750 / 1M = 0.75375 > 0.75 → margin call
        # Liquidation: (753750 - 0.75 * 1M) / (1 - 0.75) = 3750 / 0.25 = 15000
        # After: P = 1M - 15K = 985K, L = 753750 - 15K = 738750
        # LTV: 738750 / 985K = 0.75
        portfolio_value=Decimal("985000"),
        loan_balance=Decimal("738750"),
        ltv=Decimal("0.75"),
        interest_accrued=Decimal("3750"),
        liquidation_amount=Decimal("15000"),
        net_worth=Decimal("246250"),
        is_margin_call=True,
        is_unsatisfiable=False,
        is_failure=False,
    ),
)


# ---------------------------------------------------------------------------
# Scenario 9: Large market gain with debt
# ---------------------------------------------------------------------------

SCENARIO_LARGE_GAIN = DebtScenario(
    name="large_gain",
    description="Large market gain with debt",
    initial_portfolio_value=Decimal("1000000"),
    initial_loan_balance=Decimal("500000"),
    annual_interest_rate=Decimal("0.06"),
    ltv_limit=Decimal("0.75"),
    market_return=Decimal("0.50"),  # 50% gain
    expected=OracleMonthResult(
        # Portfolio after 50% gain: 1M * 1.5 = 1.5M
        # Loan after interest: 500K + 2500 = 502500
        # LTV: 502500 / 1.5M = 0.335 < 0.75 → no margin call
        portfolio_value=Decimal("1500000"),
        loan_balance=Decimal("502500"),
        ltv=Decimal("0.335"),
        interest_accrued=Decimal("2500"),
        liquidation_amount=Decimal("0"),
        net_worth=Decimal("997500"),
        is_margin_call=False,
        is_unsatisfiable=False,
        is_failure=False,
    ),
)


# ---------------------------------------------------------------------------
# Scenario 10: Multi-month transition sequence
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MultiMonthScenario:
    """A multi-month transition scenario with sequence of market returns."""

    name: str
    description: str
    initial_portfolio_value: Decimal
    initial_loan_balance: Decimal
    annual_interest_rate: Decimal
    ltv_limit: Decimal
    monthly_returns: list[Decimal]
    expected_final: OracleMonthResult


SCENARIO_MULTI_MONTH = MultiMonthScenario(
    name="multi_month",
    description="3-month sequence: gain, loss, recovery",
    initial_portfolio_value=Decimal("1000000"),
    initial_loan_balance=Decimal("600000"),
    annual_interest_rate=Decimal("0.06"),
    ltv_limit=Decimal("0.75"),
    monthly_returns=[Decimal("0.02"), Decimal("-0.15"), Decimal("0.10")],
    expected_final=OracleMonthResult(
        # Month 1: P = 1M * 1.02 = 1.02M, L = 600K + 3K = 603K
        # Month 2: P = 1.02M * 0.85 = 867K, L = 603K + 3015 = 606015
        # Month 3: P = 867K * 1.10 = 953700, L = 606015 + 3030.075 = 609045.075
        portfolio_value=Decimal("953700"),
        loan_balance=Decimal("609045.075"),
        ltv=Decimal("0.638599"),
        interest_accrued=Decimal("3030.075"),
        liquidation_amount=Decimal("0"),
        net_worth=Decimal("344654.925"),
        is_margin_call=False,
        is_unsatisfiable=False,
        is_failure=False,
    ),
)


# ---------------------------------------------------------------------------
# All scenarios for parameterized testing
# ---------------------------------------------------------------------------

ALL_SCENARIOS: list[DebtScenario] = [
    SCENARIO_BASIC_BORROWING,
    SCENARIO_MARGIN_CALL,
    SCENARIO_PROPORTIONAL_LIQUIDATION,
    SCENARIO_ZERO_DEBT,
    SCENARIO_ZERO_PORTFOLIO,
    SCENARIO_LOAN_EQUALS_PORTFOLIO,
    SCENARIO_INTEREST_ACCRUAL,
    SCENARIO_LTV_AT_LIMIT,
    SCENARIO_LARGE_GAIN,
]

SCENARIO_NAMES: list[str] = [s.name for s in ALL_SCENARIOS]


# ---------------------------------------------------------------------------
# Liquidation equation verification cases
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LiquidationTestCase:
    """A test case for liquidation equation verification."""

    name: str
    loan_balance: Decimal
    portfolio_value: Decimal
    ltv_limit: Decimal
    expected_liquidation: Decimal
    expected_new_ltv: Decimal
    is_unsatisfiable: bool


LIQUIDATION_TEST_CASES: list[LiquidationTestCase] = [
    LiquidationTestCase(
        name="basic_case",
        loan_balance=Decimal("800000"),
        portfolio_value=Decimal("1000000"),
        ltv_limit=Decimal("0.75"),
        expected_liquidation=Decimal("200000"),
        expected_new_ltv=Decimal("0.75"),
        is_unsatisfiable=False,
    ),
    LiquidationTestCase(
        name="high_ltv",
        loan_balance=Decimal("900000"),
        portfolio_value=Decimal("1000000"),
        ltv_limit=Decimal("0.75"),
        expected_liquidation=Decimal("600000"),
        expected_new_ltv=Decimal("0.75"),
        is_unsatisfiable=False,
    ),
    LiquidationTestCase(
        name="unsatisfiable",
        loan_balance=Decimal("1500000"),
        portfolio_value=Decimal("1000000"),
        ltv_limit=Decimal("0.75"),
        expected_liquidation=Decimal("1000000"),  # Sell entire portfolio
        expected_new_ltv=Decimal("0"),  # No portfolio
        is_unsatisfiable=True,
    ),
    LiquidationTestCase(
        name="boundary_loan_equals_portfolio",
        loan_balance=Decimal("1000000"),
        portfolio_value=Decimal("1000000"),
        ltv_limit=Decimal("0.75"),
        expected_liquidation=Decimal("1000000"),  # Sell entire portfolio
        expected_new_ltv=Decimal("0"),  # No portfolio
        is_unsatisfiable=False,
    ),
]


# ---------------------------------------------------------------------------
# Unsatisfiable margin call boundary cases
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UnsatisfiableTestCase:
    """A test case for unsatisfiable margin call boundary."""

    name: str
    loan_balance: Decimal
    portfolio_value: Decimal
    is_unsatisfiable: bool


UNSATISFIABLE_TEST_CASES: list[UnsatisfiableTestCase] = [
    UnsatisfiableTestCase(
        name="loan_less_than_portfolio",
        loan_balance=Decimal("500000"),
        portfolio_value=Decimal("1000000"),
        is_unsatisfiable=False,
    ),
    UnsatisfiableTestCase(
        name="loan_equals_portfolio",
        loan_balance=Decimal("1000000"),
        portfolio_value=Decimal("1000000"),
        is_unsatisfiable=False,
    ),
    UnsatisfiableTestCase(
        name="loan_greater_than_portfolio",
        loan_balance=Decimal("1500000"),
        portfolio_value=Decimal("1000000"),
        is_unsatisfiable=True,
    ),
    UnsatisfiableTestCase(
        name="zero_portfolio_positive_loan",
        loan_balance=Decimal("100000"),
        portfolio_value=Decimal("0"),
        is_unsatisfiable=True,
    ),
    UnsatisfiableTestCase(
        name="both_zero",
        loan_balance=Decimal("0"),
        portfolio_value=Decimal("0"),
        is_unsatisfiable=False,
    ),
]
