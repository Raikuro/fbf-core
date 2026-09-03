"""Tests for controlled debt fixtures.

Validates that the fixtures produce correct expected results when processed
by the independent oracle. This ensures the fixtures are self-consistent
and can be used by K.4 to verify the production engine.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.fixtures.debt import (
    ALL_SCENARIOS,
    LIQUIDATION_TEST_CASES,
    SCENARIO_BASIC_BORROWING,
    SCENARIO_MARGIN_CALL,
    SCENARIO_MULTI_MONTH,
    UNSATISFIABLE_TEST_CASES,
    DebtScenario,
    LiquidationTestCase,
    UnsatisfiableTestCase,
)
from tests.oracle.ern.debt_oracle import (
    DebtOracleState,
    FailureState,
    check_unsatisfiable_margin_call,
    compute_margin_call_liquidation,
    execute_month_transition,
)

# ---------------------------------------------------------------------------
# Test: Scenario oracle correspondence
# ---------------------------------------------------------------------------

class TestScenarioOracleCorrespondence:
    """Verify that fixtures produce correct oracle results."""

    @pytest.mark.parametrize(
        "scenario",
        ALL_SCENARIOS,
        ids=[s.name for s in ALL_SCENARIOS],
    )
    def test_single_month_scenario(self, scenario: DebtScenario) -> None:
        """Test single-month scenario against oracle."""
        state = DebtOracleState(
            portfolio_value=scenario.initial_portfolio_value,
            loan_balance=scenario.initial_loan_balance,
            annual_interest_rate=scenario.annual_interest_rate,
            ltv_limit=scenario.ltv_limit,
            month_index=0,
        )

        result = execute_month_transition(state, scenario.market_return)

        expected = scenario.expected

        # Portfolio value
        assert result.portfolio_value == expected.portfolio_value, (
            f"Portfolio value mismatch: got {result.portfolio_value}, "
            f"expected {expected.portfolio_value}"
        )

        # Loan balance
        assert result.loan_balance == expected.loan_balance, (
            f"Loan balance mismatch: got {result.loan_balance}, "
            f"expected {expected.loan_balance}"
        )

        # Interest accrued
        assert result.interest_accrued == expected.interest_accrued, (
            f"Interest accrued mismatch: got {result.interest_accrued}, "
            f"expected {expected.interest_accrued}"
        )

        # Liquidation amount
        liquidation = result.liquidation
        liquidation_amount = (
            liquidation.liquidation_amount if liquidation is not None
            else Decimal("0")
        )
        assert liquidation_amount == expected.liquidation_amount, (
            f"Liquidation amount mismatch: got {liquidation_amount}, "
            f"expected {expected.liquidation_amount}"
        )

        # Net worth
        assert result.net_worth == expected.net_worth, (
            f"Net worth mismatch: got {result.net_worth}, "
            f"expected {expected.net_worth}"
        )

        # Failure state
        is_failed = result.failure_state != FailureState.NONE
        assert is_failed == expected.is_failure, (
            f"Failure state mismatch: got {is_failed}, "
            f"expected {expected.is_failure}"
        )


# ---------------------------------------------------------------------------
# Test: Liquidation test cases
# ---------------------------------------------------------------------------

class TestLiquidationTestCases:
    """Verify liquidation test cases against oracle."""

    @pytest.mark.parametrize(
        "case",
        LIQUIDATION_TEST_CASES,
        ids=[c.name for c in LIQUIDATION_TEST_CASES],
    )
    def test_liquidation_case(self, case: LiquidationTestCase) -> None:
        """Test liquidation case against oracle."""
        result = compute_margin_call_liquidation(
            case.loan_balance,
            case.portfolio_value,
            case.ltv_limit,
        )

        assert result.liquidation_amount == case.expected_liquidation, (
            f"Liquidation amount mismatch: got {result.liquidation_amount}, "
            f"expected {case.expected_liquidation}"
        )

        assert result.is_unsatisfiable == case.is_unsatisfiable, (
            f"Unsatisfiable mismatch: got {result.is_unsatisfiable}, "
            f"expected {case.is_unsatisfiable}"
        )

        if not case.is_unsatisfiable:
            assert result.new_ltv == case.expected_new_ltv, (
                f"LTV mismatch: got {result.new_ltv}, "
                f"expected {case.expected_new_ltv}"
            )


# ---------------------------------------------------------------------------
# Test: Unsatisfiable margin call boundary cases
# ---------------------------------------------------------------------------

class TestUnsatisfiableBoundaryCases:
    """Verify unsatisfiable margin call boundary cases."""

    @pytest.mark.parametrize(
        "case",
        UNSATISFIABLE_TEST_CASES,
        ids=[c.name for c in UNSATISFIABLE_TEST_CASES],
    )
    def test_unsatisfiable_case(self, case: UnsatisfiableTestCase) -> None:
        """Test unsatisfiable margin call boundary."""
        result = check_unsatisfiable_margin_call(
            case.loan_balance,
            case.portfolio_value,
        )

        assert result == case.is_unsatisfiable, (
            f"Unsatisfiable mismatch: got {result}, "
            f"expected {case.is_unsatisfiable}"
        )


# ---------------------------------------------------------------------------
# Test: Multi-month scenario
# ---------------------------------------------------------------------------

class TestMultiMonthScenario:
    """Verify multi-month scenario against oracle."""

    def test_multi_month_sequence(self) -> None:
        """Test multi-month sequence against oracle."""
        scenario = SCENARIO_MULTI_MONTH

        state = DebtOracleState(
            portfolio_value=scenario.initial_portfolio_value,
            loan_balance=scenario.initial_loan_balance,
            annual_interest_rate=scenario.annual_interest_rate,
            ltv_limit=scenario.ltv_limit,
            month_index=0,
        )

        # Execute each month
        for month_idx, market_return in enumerate(scenario.monthly_returns):
            result = execute_month_transition(state, market_return)

            # Update state for next month
            state = DebtOracleState(
                portfolio_value=result.portfolio_value,
                loan_balance=result.loan_balance,
                annual_interest_rate=scenario.annual_interest_rate,
                ltv_limit=scenario.ltv_limit,
                month_index=month_idx + 1,
            )

        # Verify final state
        expected = scenario.expected_final

        assert result.portfolio_value == expected.portfolio_value, (
            f"Final portfolio value mismatch: got {result.portfolio_value}, "
            f"expected {expected.portfolio_value}"
        )

        assert result.loan_balance == expected.loan_balance, (
            f"Final loan balance mismatch: got {result.loan_balance}, "
            f"expected {expected.loan_balance}"
        )

        assert result.net_worth == expected.net_worth, (
            f"Final net worth mismatch: got {result.net_worth}, "
            f"expected {expected.net_worth}"
        )


# ---------------------------------------------------------------------------
# Test: Fixture consistency
# ---------------------------------------------------------------------------

class TestFixtureConsistency:
    """Verify that fixtures are internally consistent."""

    def test_all_scenarios_have_expected_results(self) -> None:
        """Test that all scenarios have non-None expected results."""
        for scenario in ALL_SCENARIOS:
            assert scenario.expected is not None, (
                f"Scenario {scenario.name} has no expected results"
            )

    def test_liquidation_cases_have_expected_values(self) -> None:
        """Test that all liquidation cases have expected values."""
        for case in LIQUIDATION_TEST_CASES:
            assert case.expected_liquidation >= 0, (
                f"Liquidation case {case.name} has negative expected liquidation"
            )

    def test_unsatisfiable_cases_are_valid(self) -> None:
        """Test that unsatisfiable cases are valid."""
        for case in UNSATISFIABLE_TEST_CASES:
            if case.is_unsatisfiable:
                # If unsatisfiable, loan must be > portfolio
                assert case.loan_balance > case.portfolio_value, (
                    f"Unsatisfiable case {case.name} has loan <= portfolio"
                )


# ---------------------------------------------------------------------------
# Test: Invariant verification through fixtures
# ---------------------------------------------------------------------------

class TestInvariantVerification:
    """Verify invariants are preserved through fixtures."""

    def test_invariant_debt_non_negative(self) -> None:
        """Invariant: loan_balance >= 0 at all times."""
        scenario = SCENARIO_MARGIN_CALL

        state = DebtOracleState(
            portfolio_value=scenario.initial_portfolio_value,
            loan_balance=scenario.initial_loan_balance,
            annual_interest_rate=scenario.annual_interest_rate,
            ltv_limit=scenario.ltv_limit,
            month_index=0,
        )

        result = execute_month_transition(state, scenario.market_return)

        assert result.loan_balance >= 0, (
            f"Invariant violated: loan_balance = {result.loan_balance}"
        )

    def test_invariant_portfolio_non_negative(self) -> None:
        """Invariant: portfolio_value >= 0 at all times."""
        scenario = SCENARIO_MARGIN_CALL

        state = DebtOracleState(
            portfolio_value=scenario.initial_portfolio_value,
            loan_balance=scenario.initial_loan_balance,
            annual_interest_rate=scenario.annual_interest_rate,
            ltv_limit=scenario.ltv_limit,
            month_index=0,
        )

        result = execute_month_transition(state, scenario.market_return)

        assert result.portfolio_value >= 0, (
            f"Invariant violated: portfolio_value = {result.portfolio_value}"
        )

    def test_invariant_net_worth_identity(self) -> None:
        """Invariant: net_worth = portfolio_value - loan_balance."""
        scenario = SCENARIO_BASIC_BORROWING

        state = DebtOracleState(
            portfolio_value=scenario.initial_portfolio_value,
            loan_balance=scenario.initial_loan_balance,
            annual_interest_rate=scenario.annual_interest_rate,
            ltv_limit=scenario.ltv_limit,
            month_index=0,
        )

        result = execute_month_transition(state, scenario.market_return)

        expected_net_worth = result.portfolio_value - result.loan_balance
        assert result.net_worth == expected_net_worth, (
            f"Invariant violated: net_worth = {result.net_worth}, "
            f"expected {expected_net_worth}"
        )
