"""Comprehensive accounting tests for K.5.1 — Debt Accounting Closure.

These tests verify:
1. Net-worth identity: net_worth = portfolio_value + cash_balance - loan_balance
2. Cash lifecycle: LoanDrawStep → WithdrawalExecutionStep → cash_balance = 0
3. Partial/full cash funding of withdrawals
4. Cash cannot go negative
5. Numerical month-level regression
"""

from __future__ import annotations

from decimal import Decimal

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies.decisions import WithdrawalDecision
from fbf.core.execution.pipeline.simulation import ExecutionStatus, SimulationState
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.pipeline.steps.interest_accrual_step import InterestAccrualStep
from fbf.core.execution.pipeline.steps.loan_draw_step import LoanDrawStep
from fbf.core.execution.pipeline.steps.withdrawal_execution_step import (
    WithdrawalExecutionStep,
)

EQUITY = AssetClass(id="equity", name="Equity", description="")
BOND = AssetClass(id="bond", name="Bond", description="")


def _snapshot(equity_price: str, period: int = 0) -> MarketSnapshot:
    return MarketSnapshot(
        date=__import__("datetime").date(2020, 1, 1 + period),
        index_levels={EQUITY: Decimal(equity_price), BOND: Decimal("50")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal(equity_price),
    )


def _context(
    equity_price: str = "100",
    initial_units: str = "100",
) -> SimulationContext:
    dataset = Dataset(
        snapshots=[_snapshot(equity_price, 0), _snapshot(equity_price, 1)],
        frequency="monthly",
        version="test",
        identifier="test",
    )
    return SimulationContext(
        experiment_name="test",
        cohort="test",
        start_date=__import__("datetime").date(2020, 1, 1),
        horizon_months=2,
        initial_wealth=Money(Decimal("10000"), Currency.EUR),
        initial_portfolio=Portfolio(holdings=(
            AssetHolding(asset_class=EQUITY, units=Decimal(initial_units)),
        )),
        dataset=dataset,
        allocation_policy=None,  # type: ignore
        withdrawal_policy=None,  # type: ignore
    )


def _state(
    ctx: SimulationContext,
    *,
    loan_balance: str = "0",
    cash_balance: str = "0",
    interest_rate: str = "0",
    ltv_limit: str = "0.75",
    withdrawal_amount: str = "0",
    loan_draw_amount: str = "0",
) -> SimulationState:
    return SimulationState(
        context=ctx,
        current_date=__import__("datetime").date(2020, 1, 1),
        period_index=0,
        portfolio=ctx.initial_portfolio,
        market_snapshot=ctx.dataset[0],
        current_wealth=ctx.initial_wealth,
        peak_wealth=ctx.initial_wealth,
        status=ExecutionStatus.RUNNING,
        loan_balance=Decimal(loan_balance),
        cash_balance=Decimal(cash_balance),
        interest_rate=Decimal(interest_rate),
        ltv_limit=Decimal(ltv_limit),
        withdrawal_decision=WithdrawalDecision(
            reason="test",
            nominal_amount=Money(Decimal(withdrawal_amount), Currency.EUR),
            real_amount=Money(Decimal(withdrawal_amount), Currency.EUR),
            loan_draw_amount=Decimal(loan_draw_amount),
        ),
    )


def _portfolio_value(state: SimulationState) -> Decimal:
    assert state.market_snapshot is not None
    total = Decimal("0")
    for h in state.portfolio.holdings:
        price = state.market_snapshot.index_levels.get(h.asset_class)
        if price is not None:
            total += h.units * price
    return total


def _net_worth(state: SimulationState) -> Decimal:
    return _portfolio_value(state) + state.cash_balance - state.loan_balance


# ── Net-worth identity ──────────────────────────────────────────────


class TestNetWorthIdentity:
    """net_worth = portfolio_value + cash_balance - loan_balance"""

    def test_no_debt(self) -> None:
        ctx = _context(equity_price="100", initial_units="100")
        s = _state(ctx)
        assert _net_worth(s) == Decimal("10000")
        assert s.cash_balance == Decimal("0")
        assert s.loan_balance == Decimal("0")

    def test_with_debt_no_cash(self) -> None:
        ctx = _context(equity_price="100", initial_units="100")
        s = _state(ctx, loan_balance="5000")
        # 10000 - 5000 = 5000
        assert _net_worth(s) == Decimal("5000")

    def test_with_debt_and_cash(self) -> None:
        ctx = _context(equity_price="100", initial_units="100")
        s = _state(ctx, loan_balance="5000", cash_balance="2000")
        # 10000 + 2000 - 5000 = 7000
        assert _net_worth(s) == Decimal("7000")

    def test_cash_equals_loan(self) -> None:
        ctx = _context(equity_price="100", initial_units="100")
        s = _state(ctx, loan_balance="3000", cash_balance="3000")
        # Cash cancels loan in net worth
        assert _net_worth(s) == Decimal("10000")


# ── Cash lifecycle: LoanDraw → WithdrawalExecution ─────────────────


class TestCashLifecycle:
    """LoanDrawStep adds cash, WithdrawalExecutionStep consumes it."""

    def test_loan_draw_then_full_consumption(self) -> None:
        """Cash from loan draw is fully consumed by withdrawal."""
        ctx = _context(equity_price="100", initial_units="100")
        # LoanDraw: cash += 83.33
        s = _state(ctx, interest_rate="0.06", withdrawal_amount="250", loan_draw_amount="83.33")

        loan_step = LoanDrawStep()
        s = loan_step.execute(s)
        assert s.cash_balance == Decimal("83.33")
        assert s.loan_balance == Decimal("83.33")

        # WithdrawalExecution: consume 83.33 cash + sell 166.67 portfolio
        withdraw_step = WithdrawalExecutionStep()
        s = withdraw_step.execute(s)
        assert s.cash_balance == Decimal("0")

    def test_loan_draw_partial_consumption(self) -> None:
        """Cash partially covers withdrawal; remaining from portfolio."""
        ctx = _context(equity_price="100", initial_units="100")
        s = _state(ctx, interest_rate="0.06", withdrawal_amount="500", loan_draw_amount="83.33")

        s = LoanDrawStep().execute(s)
        assert s.cash_balance == Decimal("83.33")

        s = WithdrawalExecutionStep().execute(s)
        assert s.cash_balance == Decimal("0")
        # Portfolio should have sold 500 - 83.33 = 416.67
        assert _portfolio_value(s) == Decimal("10000") - Decimal("416.67")

    def test_zero_cash_withdrawal_from_portfolio(self) -> None:
        """No loan draw → entire withdrawal from portfolio."""
        ctx = _context(equity_price="100", initial_units="100")
        s = _state(ctx, interest_rate="0", withdrawal_amount="250", loan_draw_amount="0")

        # LoanDraw is no-op when interest_rate <= 0
        s = LoanDrawStep().execute(s)
        assert s.cash_balance == Decimal("0")

        s = WithdrawalExecutionStep().execute(s)
        assert s.cash_balance == Decimal("0")
        assert _portfolio_value(s) == Decimal("10000") - Decimal("250")

    def test_zero_withdrawal_is_noop(self) -> None:
        """Zero spending returns state unchanged."""
        ctx = _context(equity_price="100", initial_units="100")
        s = _state(ctx, interest_rate="0.06", withdrawal_amount="0", loan_draw_amount="83.33")

        s = LoanDrawStep().execute(s)
        assert s.cash_balance == Decimal("83.33")

        s = WithdrawalExecutionStep().execute(s)
        # Cash remains unconsumed (no spending to consume it)
        assert s.cash_balance == Decimal("83.33")
        assert _portfolio_value(s) == Decimal("10000")

    def test_cash_funded_withdrawal_preserves_portfolio(self) -> None:
        """When cash fully covers spending, portfolio is untouched."""
        ctx = _context(equity_price="100", initial_units="100")
        s = _state(ctx, interest_rate="0.06", withdrawal_amount="83.33", loan_draw_amount="83.33")

        s = LoanDrawStep().execute(s)
        s = WithdrawalExecutionStep().execute(s)

        assert s.cash_balance == Decimal("0")
        # Portfolio completely untouched
        assert _portfolio_value(s) == Decimal("10000")


# ── Cash cannot go negative ────────────────────────────────────────


class TestCashNonNegative:
    """cash_balance must never go negative after any step."""

    def test_cash_non_negative_after_loan_draw(self) -> None:
        ctx = _context()
        s = _state(ctx, interest_rate="0.06", loan_draw_amount="83.33")
        s = LoanDrawStep().execute(s)
        assert s.cash_balance >= 0

    def test_cash_non_negative_after_withdrawal(self) -> None:
        ctx = _context(equity_price="100", initial_units="100")
        s = _state(ctx, interest_rate="0.06", withdrawal_amount="250", loan_draw_amount="83.33")
        s = LoanDrawStep().execute(s)
        s = WithdrawalExecutionStep().execute(s)
        assert s.cash_balance >= 0


# ── Numerical month-level regression ───────────────────────────────


class TestNumericalMonthRegression:
    """Single-period numerical trace with explicit accounting check."""

    def test_single_period_full_trace(self) -> None:
        """Full single-period trace with borrowing:
        - Initial: portfolio=100×$100=$10,000, loan=0, cash=0
        - loan_draw_amount=83.33, total_spending=250
        - After LoanDrawStep: loan=83.33, cash=83.33
        - After WithdrawalExecution: cash consumed, portfolio sold 166.67
        - Portfolio remaining: 10000 - 166.67 = 9833.33
        - After interest (6% annual → 0.5% monthly): loan = 83.33 × 1.005 = 83.747
        """
        ctx = _context(equity_price="100", initial_units="100")
        s = _state(ctx, interest_rate="0.06", withdrawal_amount="250", loan_draw_amount="83.33")

        # Step 1: LoanDraw
        s = LoanDrawStep().execute(s)
        assert s.loan_balance == Decimal("83.33")
        assert s.cash_balance == Decimal("83.33")
        assert _portfolio_value(s) == Decimal("10000")
        assert _net_worth(s) == Decimal("10000") + Decimal("83.33") - Decimal("83.33")

        # Step 2: WithdrawalExecution
        s = WithdrawalExecutionStep().execute(s)
        assert s.cash_balance == Decimal("0")
        assert _portfolio_value(s) == Decimal("10000") - Decimal("166.67")
        assert _net_worth(s) == Decimal("9833.33") + Decimal("0") - Decimal("83.33")

        # Step 3: InterestAccrual (monthly: 0.06/12 = 0.005)
        s = InterestAccrualStep().execute(s)
        expected_loan = Decimal("83.33") * (1 + Decimal("0.06") / Decimal("12"))
        assert s.loan_balance == expected_loan
        assert s.cash_balance == Decimal("0")
        assert _portfolio_value(s) == Decimal("9833.33")
        assert _net_worth(s) == Decimal("9833.33") - expected_loan


# ── DebtInfo net-worth identity (domain boundary) ──────────────────


class TestDebtInfoNetWorth:
    """DebtInfo.net_worth identity at domain boundary."""

    def test_debt_info_identity(self) -> None:
        from fbf.core.domain.model.decision_context import DebtInfo

        info = DebtInfo(
            loan_balance=Decimal("5000"),
            interest_rate=Decimal("0.06"),
            ltv_limit=Decimal("0.75"),
            portfolio_value=Decimal("10000"),
            cash_balance=Decimal("2000"),
        )
        # 10000 + 2000 - 5000 = 7000
        assert info.net_worth == Decimal("7000")

    def test_debt_info_no_cash(self) -> None:
        from fbf.core.domain.model.decision_context import DebtInfo

        info = DebtInfo(
            loan_balance=Decimal("5000"),
            interest_rate=Decimal("0.06"),
            ltv_limit=Decimal("0.75"),
            portfolio_value=Decimal("10000"),
        )
        assert info.net_worth == Decimal("5000")

    def test_debt_info_zero_portfolio(self) -> None:
        from fbf.core.domain.model.decision_context import DebtInfo

        info = DebtInfo(
            loan_balance=Decimal("5000"),
            interest_rate=Decimal("0.06"),
            ltv_limit=Decimal("0.75"),
            portfolio_value=Decimal("0"),
            cash_balance=Decimal("1000"),
        )
        # 0 + 1000 - 5000 = -4000
        assert info.net_worth == Decimal("-4000")


# ── DebtSnapshot net-worth identity (MonthlyResult) ────────────────


class TestDebtSnapshotNetWorth:
    """DebtSnapshot.net_worth computed correctly by MonthlyResultBuilderStep."""

    def test_debt_snapshot_in_monthly_result(self) -> None:
        from fbf.core.execution.pipeline.steps.monthly_result_builder_step import (
            MonthlyResultBuilderStep,
        )

        ctx = _context(equity_price="100", initial_units="100")
        s = _state(ctx, interest_rate="0.06", loan_balance="5000", cash_balance="2000")

        step = MonthlyResultBuilderStep()
        s = step.execute(s)

        assert len(s.monthly_results) == 1
        ds = s.monthly_results[0].debt_snapshot
        assert ds is not None
        assert ds.loan_balance == Decimal("5000")
        assert ds.cash_balance == Decimal("2000")
        # 10000 + 2000 - 5000 = 7000
        assert ds.net_worth == Decimal("7000")

    def test_debt_snapshot_no_debt(self) -> None:
        from fbf.core.execution.pipeline.steps.monthly_result_builder_step import (
            MonthlyResultBuilderStep,
        )

        ctx = _context(equity_price="100", initial_units="100")
        s = _state(ctx)

        step = MonthlyResultBuilderStep()
        s = step.execute(s)

        assert s.monthly_results[0].debt_snapshot is None
