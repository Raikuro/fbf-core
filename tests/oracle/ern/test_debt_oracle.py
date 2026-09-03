"""Tests for the independent Part 49 Debt-Transition Oracle.

These tests validate the oracle's correctness and independently verify
the liquidation equation, unsatisfiable margin call derivation, and
all edge cases defined in the semantic contract.

No imports from fbf.core are permitted in this module.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.oracle.ern.debt_oracle import (
    DebtOracleState,
    ExecutionStatus,
    FailureState,
    check_unsatisfiable_margin_call,
    compute_interest_accrual,
    compute_liquidation_amount,
    compute_margin_call_liquidation,
    execute_month_transition,
    verify_liquidation_equation,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def default_ltv_limit() -> Decimal:
    """Default LTV limit of 75%."""
    return Decimal("0.75")


@pytest.fixture
def default_interest_rate() -> Decimal:
    """Default annual interest rate of 6%."""
    return Decimal("0.06")


# ---------------------------------------------------------------------------
# Test: Liquidation equation derivation
# ---------------------------------------------------------------------------

class TestLiquidationEquationDerivation:
    """Independently derive and verify the liquidation equation."""

    def test_basic_liquidation(self, default_ltv_limit: Decimal) -> None:
        """Test basic liquidation calculation."""
        P = Decimal("100")
        L = Decimal("80")
        ltv_limit = default_ltv_limit

        result = compute_margin_call_liquidation(L, P, ltv_limit)

        # Expected: (80 - 0.75 * 100) / (1 - 0.75) = 20 / 0.25 = 20
        expected_liquidation = Decimal("20")
        assert result.liquidation_amount == expected_liquidation

        # After liquidation: P=80, L=60, LTV=60/80=75%
        assert result.new_portfolio_value == Decimal("80")
        assert result.new_loan_balance == Decimal("60")
        assert result.new_ltv == ltv_limit

    def test_liquidation_equation_independent_derivation(
        self, default_ltv_limit: Decimal
    ) -> None:
        """Independently derive the liquidation equation."""
        P = Decimal("100")
        L = Decimal("80")
        ltv_limit = default_ltv_limit

        # The equation: (L - λP) / (1 - λ)
        numerator = L - ltv_limit * P
        denominator = Decimal("1") - ltv_limit
        expected = numerator / denominator

        actual = compute_liquidation_amount(L, P, ltv_limit)
        assert actual == expected

    def test_liquidation_equation_verification(
        self, default_ltv_limit: Decimal
    ) -> None:
        """Verify the liquidation equation produces correct LTV."""
        P = Decimal("100")
        L = Decimal("80")
        ltv_limit = default_ltv_limit

        result = verify_liquidation_equation(L, P, ltv_limit)

        # After liquidation, LTV should equal the limit
        assert result.new_ltv == ltv_limit

    def test_various_portfolio_values(self, default_ltv_limit: Decimal) -> None:
        """Test liquidation with various portfolio values."""
        ltv_limit = default_ltv_limit
        L = Decimal("75")  # Fixed loan

        for P in [Decimal("100"), Decimal("150"), Decimal("200"), Decimal("500")]:
            if ltv_limit < L / P:
                result = compute_margin_call_liquidation(L, P, ltv_limit)
                assert result.liquidation_amount > 0
                assert result.new_ltv == ltv_limit


# ---------------------------------------------------------------------------
# Test: Unsatisfiable margin call derivation
# ---------------------------------------------------------------------------

class TestUnsatisfiableMarginCallDerivation:
    """Independently derive and verify the unsatisfiable margin call condition."""

    def test_independent_derivation(self) -> None:
        """Independently derive the unsatisfiable condition."""
        # The derivation:
        # liquidation_amount > portfolio_value
        # (L - λP) / (1 - λ) > P
        # L - λP > (1 - λ) * P
        # L - λP > P - λP
        # L > P

        # Therefore: loan_balance > portfolio_value

        # Test cases
        assert check_unsatisfiable_margin_call(Decimal("100"), Decimal("50")) is True
        assert check_unsatisfiable_margin_call(Decimal("50"), Decimal("100")) is False
        assert check_unsatisfiable_margin_call(Decimal("100"), Decimal("100")) is False

    def test_unsatisfiable_liquidation(self, default_ltv_limit: Decimal) -> None:
        """Test unsatisfiable margin call produces correct result."""
        P = Decimal("100")
        L = Decimal("150")  # L > P
        ltv_limit = default_ltv_limit

        result = compute_margin_call_liquidation(L, P, ltv_limit)

        assert result.is_unsatisfiable is True
        assert result.liquidation_amount == P  # Sell entire portfolio
        assert result.new_portfolio_value == Decimal("0")
        assert result.new_loan_balance == Decimal("50")  # Partial repayment

    def test_boundary_case_loan_equals_portfolio(
        self, default_ltv_limit: Decimal
    ) -> None:
        """Test boundary case: loan_balance = portfolio_value."""
        P = Decimal("100")
        L = Decimal("100")
        ltv_limit = default_ltv_limit

        # This is NOT unsatisfiable by the definition L > P
        assert check_unsatisfiable_margin_call(L, P) is False

        # But LTV = 100/100 = 100% > 75%, so margin call triggered
        result = compute_margin_call_liquidation(L, P, ltv_limit)
        assert result.liquidation_amount == P  # Sell entire portfolio
        assert result.new_portfolio_value == Decimal("0")
        assert result.new_loan_balance == Decimal("0")
        assert result.new_ltv == Decimal("0")


# ---------------------------------------------------------------------------
# Test: Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Test all edge cases defined in the semantic contract."""

    def test_zero_portfolio_positive_debt(self, default_ltv_limit: Decimal) -> None:
        """Test edge case: portfolio = 0, debt > 0."""
        P = Decimal("0")
        L = Decimal("50")
        ltv_limit = default_ltv_limit

        result = compute_margin_call_liquidation(L, P, ltv_limit)

        assert result.is_unsatisfiable is True
        assert result.liquidation_amount == Decimal("0")  # Can't sell nothing
        assert result.new_portfolio_value == Decimal("0")
        assert result.new_loan_balance == L  # Debt unchanged

    def test_zero_portfolio_zero_debt(self, default_ltv_limit: Decimal) -> None:
        """Test edge case: portfolio = 0, debt = 0."""
        P = Decimal("0")
        L = Decimal("0")
        ltv_limit = default_ltv_limit

        result = compute_margin_call_liquidation(L, P, ltv_limit)

        assert result.is_unsatisfiable is False
        assert result.liquidation_amount == Decimal("0")

    def test_positive_portfolio_zero_debt(self, default_ltv_limit: Decimal) -> None:
        """Test edge case: portfolio > 0, debt = 0."""
        P = Decimal("100")
        L = Decimal("0")
        ltv_limit = default_ltv_limit

        result = compute_margin_call_liquidation(L, P, ltv_limit)

        assert result.is_unsatisfiable is False
        assert result.liquidation_amount == Decimal("0")
        assert result.new_ltv == Decimal("0")

    def test_loan_equals_portfolio_at_limit(
        self, default_ltv_limit: Decimal
    ) -> None:
        """Test edge case: loan = portfolio, both at limit."""
        P = Decimal("100")
        L = Decimal("75")  # LTV = 75% = limit exactly
        ltv_limit = default_ltv_limit

        result = compute_margin_call_liquidation(L, P, ltv_limit)

        # No margin call triggered (LTV = limit)
        assert result.liquidation_amount == Decimal("0")
        assert result.new_ltv == ltv_limit


# ---------------------------------------------------------------------------
# Test: Interest accrual
# ---------------------------------------------------------------------------

class TestInterestAccrual:
    """Test interest accrual mechanics."""

    def test_basic_interest(self, default_interest_rate: Decimal) -> None:
        """Test basic interest accrual."""
        L = Decimal("1000")
        rate = default_interest_rate

        interest, new_balance = compute_interest_accrual(L, rate)

        # Monthly rate = 6% / 12 = 0.5%
        expected_interest = L * rate / Decimal("12")
        assert interest == expected_interest
        assert new_balance == L + interest

    def test_compound_interest(self, default_interest_rate: Decimal) -> None:
        """Test compound interest over multiple periods."""
        L = Decimal("1000")
        rate = default_interest_rate
        monthly_rate = rate / Decimal("12")

        balance = L
        for _ in range(12):
            interest, balance = compute_interest_accrual(balance, rate)

        # After 12 months, balance should be L * (1 + monthly_rate)^12
        expected = L * (Decimal("1") + monthly_rate) ** 12
        # Allow small tolerance for rounding in iterative computation
        tolerance = Decimal("0.000000000001")
        assert abs(balance - expected) < tolerance


# ---------------------------------------------------------------------------
# Test: Month transition
# ---------------------------------------------------------------------------

class TestMonthTransition:
    """Test single month transition execution."""

    def test_basic_transition(self, default_interest_rate: Decimal) -> None:
        """Test basic month transition."""
        state = DebtOracleState(
            portfolio_value=Decimal("1000"),
            loan_balance=Decimal("500"),
            annual_interest_rate=default_interest_rate,
            ltv_limit=Decimal("0.75"),
            month_index=0,
        )
        market_return = Decimal("0.01")  # 1% gain

        result = execute_month_transition(state, market_return)

        assert result.status == ExecutionStatus.RUNNING
        assert result.failure_state == FailureState.NONE
        assert result.portfolio_value > Decimal("0")
        assert result.loan_balance > Decimal("500")  # Interest accrued

    def test_market_loss_triggers_margin_call(
        self, default_interest_rate: Decimal
    ) -> None:
        """Test that market losses can trigger margin call."""
        state = DebtOracleState(
            portfolio_value=Decimal("1000"),
            loan_balance=Decimal("800"),
            annual_interest_rate=default_interest_rate,
            ltv_limit=Decimal("0.75"),
            month_index=0,
        )
        # 20% market loss
        market_return = Decimal("-0.20")

        result = execute_month_transition(state, market_return)

        # LTV after market loss: 800 / 800 = 100% > 75%
        assert result.liquidation is not None
        assert result.liquidation.liquidation_amount > 0

    def test_no_margin_call_when_within_limit(
        self, default_interest_rate: Decimal
    ) -> None:
        """Test no margin call when LTV within limit."""
        state = DebtOracleState(
            portfolio_value=Decimal("1000"),
            loan_balance=Decimal("500"),
            annual_interest_rate=default_interest_rate,
            ltv_limit=Decimal("0.75"),
            month_index=0,
        )
        # Small market gain
        market_return = Decimal("0.01")

        result = execute_month_transition(state, market_return)

        assert result.liquidation is None


# ---------------------------------------------------------------------------
# Test: Invariants
# ---------------------------------------------------------------------------

class TestInvariants:
    """Test that invariants are preserved."""

    def test_invariant_debt_non_negative(self, default_interest_rate: Decimal) -> None:
        """Invariant: loan_balance >= 0 at all times."""
        state = DebtOracleState(
            portfolio_value=Decimal("1000"),
            loan_balance=Decimal("500"),
            annual_interest_rate=default_interest_rate,
            ltv_limit=Decimal("0.75"),
            month_index=0,
        )
        market_return = Decimal("-0.30")  # Large loss

        result = execute_month_transition(state, market_return)

        assert result.loan_balance >= Decimal("0")

    def test_invariant_portfolio_non_negative(
        self, default_interest_rate: Decimal
    ) -> None:
        """Invariant: portfolio_value >= 0 at all times."""
        state = DebtOracleState(
            portfolio_value=Decimal("1000"),
            loan_balance=Decimal("800"),
            annual_interest_rate=default_interest_rate,
            ltv_limit=Decimal("0.75"),
            month_index=0,
        )
        market_return = Decimal("-0.30")

        result = execute_month_transition(state, market_return)

        assert result.portfolio_value >= Decimal("0")

    def test_invariant_net_worth_identity(
        self, default_interest_rate: Decimal
    ) -> None:
        """Invariant: net_worth = portfolio_value - loan_balance."""
        state = DebtOracleState(
            portfolio_value=Decimal("1000"),
            loan_balance=Decimal("500"),
            annual_interest_rate=default_interest_rate,
            ltv_limit=Decimal("0.75"),
            month_index=0,
        )
        market_return = Decimal("0.05")

        result = execute_month_transition(state, market_return)

        expected_net_worth = result.portfolio_value - result.loan_balance
        assert result.net_worth == expected_net_worth

    def test_invariant_liquidation_reduces_both_equally(
        self, default_interest_rate: Decimal
    ) -> None:
        """Invariant: liquidation reduces portfolio and debt by same amount."""
        state = DebtOracleState(
            portfolio_value=Decimal("1000"),
            loan_balance=Decimal("800"),
            annual_interest_rate=default_interest_rate,
            ltv_limit=Decimal("0.75"),
            month_index=0,
        )
        market_return = Decimal("-0.20")

        result = execute_month_transition(state, market_return)

        if result.liquidation is not None and result.liquidation.liquidation_amount > 0:
            # Portfolio decreased by liquidation_amount
            # Debt decreased by liquidation_amount
            expected_loan = (
                state.loan_balance
                * (Decimal("1") + state.annual_interest_rate / Decimal("12"))
                - result.liquidation.liquidation_amount
            )
            assert result.loan_balance == expected_loan

    def test_invariant_ltv_restored_after_liquidation(
        self, default_interest_rate: Decimal
    ) -> None:
        """Invariant: LTV restored to limit after liquidation."""
        state = DebtOracleState(
            portfolio_value=Decimal("1000"),
            loan_balance=Decimal("800"),
            annual_interest_rate=default_interest_rate,
            ltv_limit=Decimal("0.75"),
            month_index=0,
        )
        market_return = Decimal("-0.20")

        result = execute_month_transition(state, market_return)

        if result.liquidation is not None and not result.liquidation.is_unsatisfiable:
            # After liquidation, LTV should equal the limit
            assert result.liquidation.new_ltv == state.ltv_limit


# ---------------------------------------------------------------------------
# Test: Verification of documentation assertions
# ---------------------------------------------------------------------------

class TestDocumentationAssertions:
    """Verify assertions from the semantic contract documentation."""

    def test_verification_example_from_documentation(
        self, default_ltv_limit: Decimal
    ) -> None:
        """Test the verification example from the documentation."""
        P = Decimal("100")
        L = Decimal("80")
        ltv_limit = default_ltv_limit

        result = compute_margin_call_liquidation(L, P, ltv_limit)

        # Expected: liquidation_amount = 20
        assert result.liquidation_amount == Decimal("20")
        # After: P=80, L=60, LTV=75%
        assert result.new_portfolio_value == Decimal("80")
        assert result.new_loan_balance == Decimal("60")
        assert result.new_ltv == ltv_limit

    def test_numerator_insufficient(self, default_ltv_limit: Decimal) -> None:
        """Test that numerator alone is insufficient."""
        P = Decimal("100")
        L = Decimal("80")
        ltv_limit = default_ltv_limit

        # Numerator alone: 80 - 0.75 * 100 = 5
        numerator = L - ltv_limit * P
        assert numerator == Decimal("5")

        # But correct liquidation is 20, not 5
        result = compute_margin_call_liquidation(L, P, ltv_limit)
        assert result.liquidation_amount == Decimal("20")

    def test_unsatisfiable_condition_derived(
        self, default_ltv_limit: Decimal
    ) -> None:
        """Test that unsatisfiable condition is correctly derived."""
        # From documentation:
        # liquidation_amount > portfolio_value
        # (loan_balance - ltv_limit × portfolio_value) / (1 - ltv_limit) > portfolio_value
        # loan_balance > portfolio_value

        # Test case 1: L > P (unsatisfiable)
        assert check_unsatisfiable_margin_call(Decimal("150"), Decimal("100")) is True

        # Test case 2: L < P (satisfiable)
        assert check_unsatisfiable_margin_call(Decimal("50"), Decimal("100")) is False

        # Test case 3: L = P (boundary)
        assert check_unsatisfiable_margin_call(Decimal("100"), Decimal("100")) is False
