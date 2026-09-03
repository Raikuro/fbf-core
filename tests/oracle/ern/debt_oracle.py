"""Independent Part 49 Debt-Transition Oracle.

This module implements the Part 49 debt operations from first principles.
It is completely independent from the production fbf.core implementation.
No imports from fbf.core are permitted.

The oracle validates:
1. Liquidation equation correctness
2. Unsatisfiable margin call derivation
3. All edge cases defined in the semantic contract
4. Interest accrual mechanics
5. Net worth calculations

All calculations use Decimal arithmetic for exactness.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class FailureState(Enum):
    """Simulation failure states."""

    NONE = "none"
    DEPLETED = "depleted"
    MARGIN_CALL_IMPOSSIBLE = "margin_call_impossible"


class ExecutionStatus(Enum):
    """Execution status."""

    RUNNING = "running"
    FAILED = "failed"
    COMPLETED = "completed"


@dataclass(frozen=True)
class DebtOracleState:
    """Immutable state snapshot for debt oracle calculations.

    This is the independent oracle's representation of the debt state.
    It does not depend on any production code.
    """

    portfolio_value: Decimal
    loan_balance: Decimal
    annual_interest_rate: Decimal
    ltv_limit: Decimal
    month_index: int

    @property
    def ltv(self) -> Decimal:
        """Compute LTV (loan-to-value ratio).

        Returns 0 if loan_balance is 0.
        """
        if self.loan_balance <= 0:
            return Decimal("0")
        if self.portfolio_value <= 0:
            return Decimal("999999")  # Effectively infinite
        return self.loan_balance / self.portfolio_value


@dataclass(frozen=True)
class LiquidationResult:
    """Result of a liquidation calculation."""

    liquidation_amount: Decimal
    new_portfolio_value: Decimal
    new_loan_balance: Decimal
    new_ltv: Decimal
    is_unsatisfiable: bool


@dataclass(frozen=True)
class MonthTransitionResult:
    """Result of a single month transition."""

    portfolio_value: Decimal
    loan_balance: Decimal
    interest_accrued: Decimal
    liquidation: LiquidationResult | None
    net_worth: Decimal
    failure_state: FailureState
    status: ExecutionStatus


def compute_liquidation_amount(
    loan_balance: Decimal,
    portfolio_value: Decimal,
    ltv_limit: Decimal,
) -> Decimal:
    """Compute the liquidation amount required to restore LTV to the limit.

    This is the independent derivation of the liquidation equation:
        liquidation_amount = (loan_balance - ltv_limit × portfolio_value) / (1 - ltv_limit)

    The derivation assumes:
    - After selling assets worth x and repaying the loan:
      - New portfolio value = P - x
      - New loan balance = L - x
      - LTV constraint: (L - x) / (P - x) ≤ λ
      - Solving for x: x ≥ (L - λP) / (1 - λ)

    Parameters
    ----------
    loan_balance
        Outstanding loan balance.
    portfolio_value
        Current portfolio value.
    ltv_limit
        Maximum allowed LTV (e.g., 0.75 for 75%).

    Returns
    -------
    Decimal
        The minimum liquidation amount required to restore LTV to the limit.
    """
    numerator = loan_balance - ltv_limit * portfolio_value
    denominator = Decimal("1") - ltv_limit

    if denominator <= 0:
        # ltv_limit >= 1.0 is invalid; return the full portfolio
        return portfolio_value

    return numerator / denominator


def check_unsatisfiable_margin_call(
    loan_balance: Decimal,
    portfolio_value: Decimal,
) -> bool:
    """Check if a margin call is unsatisfiable.

    A margin call is unsatisfiable if and only if loan_balance > portfolio_value.

    This is derived from the liquidation equation:
        liquidation_amount > portfolio_value
        (loan_balance - ltv_limit × portfolio_value) / (1 - ltv_limit) > portfolio_value
        loan_balance - ltv_limit × portfolio_value > (1 - ltv_limit) × portfolio_value
        loan_balance > portfolio_value

    Parameters
    ----------
    loan_balance
        Outstanding loan balance.
    portfolio_value
        Current portfolio value.

    Returns
    -------
    bool
        True if the margin call is unsatisfiable.
    """
    return loan_balance > portfolio_value


def compute_margin_call_liquidation(
    loan_balance: Decimal,
    portfolio_value: Decimal,
    ltv_limit: Decimal,
) -> LiquidationResult:
    """Compute the liquidation result for a margin call.

    Parameters
    ----------
    loan_balance
        Outstanding loan balance.
    portfolio_value
        Current portfolio value.
    ltv_limit
        Maximum allowed LTV.

    Returns
    -------
    LiquidationResult
        The result of the liquidation calculation.
    """
    if loan_balance <= 0:
        # No loan, no liquidation needed
        return LiquidationResult(
            liquidation_amount=Decimal("0"),
            new_portfolio_value=portfolio_value,
            new_loan_balance=loan_balance,
            new_ltv=Decimal("0"),
            is_unsatisfiable=False,
        )

    ltv = loan_balance / portfolio_value if portfolio_value > 0 else Decimal("999999")

    if ltv <= ltv_limit:
        # No margin call
        return LiquidationResult(
            liquidation_amount=Decimal("0"),
            new_portfolio_value=portfolio_value,
            new_loan_balance=loan_balance,
            new_ltv=ltv,
            is_unsatisfiable=False,
        )

    # Margin call triggered
    if check_unsatisfiable_margin_call(loan_balance, portfolio_value):
        # Unsatisfiable: sell entire portfolio
        liquidation_amount = portfolio_value
        new_portfolio = Decimal("0")
        new_loan = loan_balance - liquidation_amount
    else:
        # Computable: use the liquidation equation
        liquidation_amount = compute_liquidation_amount(
            loan_balance, portfolio_value, ltv_limit
        )
        new_portfolio = portfolio_value - liquidation_amount
        new_loan = loan_balance - liquidation_amount

    # Compute new LTV
    new_ltv = (
        new_loan / new_portfolio
        if new_portfolio > 0
        else (Decimal("999999") if new_loan > 0 else Decimal("0"))
    )

    return LiquidationResult(
        liquidation_amount=liquidation_amount,
        new_portfolio_value=new_portfolio,
        new_loan_balance=new_loan,
        new_ltv=new_ltv,
        is_unsatisfiable=check_unsatisfiable_margin_call(loan_balance, portfolio_value),
    )


def compute_interest_accrual(
    loan_balance: Decimal,
    annual_interest_rate: Decimal,
) -> tuple[Decimal, Decimal]:
    """Compute monthly interest accrual.

    Parameters
    ----------
    loan_balance
        Current loan balance.
    annual_interest_rate
        Annual interest rate (e.g., 0.06 for 6%).

    Returns
    -------
    tuple[Decimal, Decimal]
        (interest_amount, new_loan_balance)
    """
    monthly_rate = annual_interest_rate / Decimal("12")
    interest = loan_balance * monthly_rate
    new_balance = loan_balance + interest
    return interest, new_balance


def execute_month_transition(
    state: DebtOracleState,
    market_return: Decimal,
) -> MonthTransitionResult:
    """Execute a single month transition using the oracle.

    This follows the 10-step ordering from the semantic contract.

    Parameters
    ----------
    state
        Beginning-of-period state.
    market_return
        Market return for the period (e.g., 0.01 for 1% gain).

    Returns
    -------
    MonthTransitionResult
        The result of the month transition.
    """
    # Step 6: Market Evolution
    portfolio_value_after_market = state.portfolio_value * (Decimal("1") + market_return)

    # Step 7: Interest Accrual
    interest, loan_balance_after_interest = compute_interest_accrual(
        state.loan_balance, state.annual_interest_rate
    )

    # Step 8: LTV Evaluation
    ltv_after = (
        loan_balance_after_interest / portfolio_value_after_market
        if portfolio_value_after_market > 0
        else Decimal("999999")
    )

    liquidation = None
    portfolio_value_final = portfolio_value_after_market
    loan_balance_final = loan_balance_after_interest

    if ltv_after > state.ltv_limit and loan_balance_after_interest > 0:
        # Margin call triggered
        liquidation = compute_margin_call_liquidation(
            loan_balance_after_interest,
            portfolio_value_after_market,
            state.ltv_limit,
        )
        portfolio_value_final = liquidation.new_portfolio_value
        loan_balance_final = liquidation.new_loan_balance

    # Step 9: Net Worth Calculation
    net_worth = portfolio_value_final - loan_balance_final

    # Step 10: Failure Detection
    failure_state = FailureState.NONE
    status = ExecutionStatus.RUNNING

    if portfolio_value_final <= 0:
        failure_state = FailureState.DEPLETED
        status = ExecutionStatus.FAILED
    elif loan_balance_final > portfolio_value_final and loan_balance_final > 0:
        failure_state = FailureState.MARGIN_CALL_IMPOSSIBLE
        status = ExecutionStatus.FAILED

    return MonthTransitionResult(
        portfolio_value=portfolio_value_final,
        loan_balance=loan_balance_final,
        interest_accrued=interest,
        liquidation=liquidation,
        net_worth=net_worth,
        failure_state=failure_state,
        status=status,
    )


def verify_liquidation_equation(
    loan_balance: Decimal,
    portfolio_value: Decimal,
    ltv_limit: Decimal,
) -> LiquidationResult:
    """Verify the liquidation equation produces correct results.

    This function independently derives and verifies the liquidation equation
    by checking that after liquidation, the LTV equals the limit.

    Parameters
    ----------
    loan_balance
        Outstanding loan balance.
    portfolio_value
        Current portfolio value.
    ltv_limit
        Maximum allowed LTV.

    Returns
    -------
    LiquidationResult
        The verified liquidation result.
    """
    result = compute_margin_call_liquidation(loan_balance, portfolio_value, ltv_limit)

    # Verify the equation
    if result.liquidation_amount > 0 and not result.is_unsatisfiable:
        # After liquidation: (L - x) / (P - x) should equal λ
        expected_new_loan = loan_balance - result.liquidation_amount
        expected_new_portfolio = portfolio_value - result.liquidation_amount
        expected_ltv = (
            expected_new_loan / expected_new_portfolio
            if expected_new_portfolio > 0
            else Decimal("0")
        )

        # Allow small tolerance for rounding
        tolerance = Decimal("0.0000000001")
        if abs(expected_ltv - ltv_limit) > tolerance:
            raise ValueError(
                f"Liquidation equation verification failed: "
                f"expected LTV {expected_ltv}, got {ltv_limit}"
            )

    return result
