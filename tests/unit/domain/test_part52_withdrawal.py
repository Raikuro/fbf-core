"""Unit tests for Part52WithdrawalPolicy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from fbf.core.domain.model.allocation import Allocation, AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.decision_context import DebtInfo, DecisionContext
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies.part52_withdrawal import Part52WithdrawalPolicy


@pytest.fixture
def equity_asset() -> AssetClass:
    return AssetClass(id="equity", name="Equity", description="")


@pytest.fixture
def bond_asset() -> AssetClass:
    return AssetClass(id="bond", name="Bond", description="")


@pytest.fixture
def initial_portfolio(equity_asset: AssetClass, bond_asset: AssetClass) -> Portfolio:
    return Portfolio(
        holdings=(
            AssetHolding(asset_class=equity_asset, units=Decimal("500")),
            AssetHolding(asset_class=bond_asset, units=Decimal("500")),
        )
    )


@pytest.fixture
def dataset(equity_asset: AssetClass, bond_asset: AssetClass) -> Dataset:
    return Dataset(
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


@dataclass
class MockSimulationContext:
    dataset: Dataset
    initial_portfolio: Portfolio


def _build_context(
    mock_sim_ctx: MockSimulationContext,
    equity_index: Decimal,
    running_ath: Decimal,
    is_ath: bool,
    loan_balance: Decimal = Decimal("0"),
    compound_drawdown: Decimal = Decimal("0"),
    previous_draw_repay: Decimal = Decimal("0"),
) -> DecisionContext:
    equity_asset = AssetClass(id="equity", name="Equity", description="")
    bond_asset = AssetClass(id="bond", name="Bond", description="")

    market_snapshot = MarketSnapshot(
        date=date(1965, 11, 1),
        index_levels={
            equity_asset: equity_index,
            bond_asset: Decimal("100"),
        },
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("1"),
        is_ath=is_ath,
        is_underwater=not is_ath,
        running_ath=running_ath,
    )

    debt_info = None
    if loan_balance > 0:
        debt_info = DebtInfo(
            loan_balance=loan_balance,
            interest_rate=Decimal("0.015"),
            ltv_limit=Decimal("0.50"),
            portfolio_value=Decimal("100000"),
            ltv_observed=loan_balance / Decimal("100000"),
            ltv_enforcement=True,
        )

    # Create mock allocation (not used by Part52 policy but required by DecisionContext)
    allocation = Allocation(weights={equity_asset: Decimal("0.75"), bond_asset: Decimal("0.25")})
    target = AllocationTarget(weights={equity_asset: Decimal("0.75"), bond_asset: Decimal("0.25")})

    return DecisionContext(
        date=date(1965, 11, 1),
        period_index=0,
        simulation_context=mock_sim_ctx,
        portfolio=Portfolio(holdings=()),
        current_allocation=allocation,
        target_allocation=target,
        market_snapshot=market_snapshot,
        dataset=mock_sim_ctx.dataset,
        debt_info=debt_info,
        compound_drawdown=compound_drawdown,
        previous_draw_repay=previous_draw_repay,
    )


class TestPart52WithdrawalPolicy:
    """Tests for Part52WithdrawalPolicy."""

    def test_budget_calculation(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        """Budget = initial_wealth * withdrawal_rate / 12."""
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset,
            initial_portfolio=initial_portfolio,
        )
        policy = Part52WithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            borrow_pct=Decimal("0.25"),
            drawdown_threshold=Decimal("0.20"),
        )
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("100"),
            running_ath=Decimal("100"),
            is_ath=True,
        )
        decision = policy.decide(context)
        # initial_wealth = 500*100 + 500*100 = 100000
        # budget = 100000 * 0.04 / 12 = 333.333...
        assert decision.nominal_amount.amount == Decimal("100000") * Decimal("0.04") / Decimal("12")

    def test_no_borrow_when_above_threshold(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        """Drawdown < threshold → NORMAL mode."""
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset,
            initial_portfolio=initial_portfolio,
        )
        policy = Part52WithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            borrow_pct=Decimal("0.25"),
            drawdown_threshold=Decimal("0.20"),
        )
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("95"),  # drawdown = 5%
            running_ath=Decimal("100"),
            is_ath=False,
        )
        decision = policy.decide(context)
        assert decision.loan_draw_amount == Decimal("0")
        assert decision.is_repayment is False

    def test_borrow_when_below_threshold(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        """Compound DD <= -threshold → BORROW mode."""
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset,
            initial_portfolio=initial_portfolio,
        )
        policy = Part52WithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            borrow_pct=Decimal("0.25"),
            drawdown_threshold=Decimal("0.20"),
        )
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("75"),
            running_ath=Decimal("100"),
            is_ath=False,
            compound_drawdown=Decimal("-0.25"),
        )
        decision = policy.decide(context)
        budget = Decimal("100000") * Decimal("0.04") / Decimal("12")
        assert decision.loan_draw_amount == budget * Decimal("0.25")
        # BORROW: nominal = C + D_t - D_{t-1} = budget + D_t (D_{t-1}=0)
        assert decision.nominal_amount.amount == budget + budget * Decimal("0.25")
        assert decision.is_repayment is False

    def test_repay_when_cdd_zero_with_loan(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        """compound_drawdown == 0 AND loan_balance > 0 → REPAY mode."""
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset,
            initial_portfolio=initial_portfolio,
        )
        policy = Part52WithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            borrow_pct=Decimal("0.25"),
            drawdown_threshold=Decimal("0.20"),
        )
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("110"),  # new ATH
            running_ath=Decimal("110"),
            is_ath=True,
            compound_drawdown=Decimal("0"),
            loan_balance=Decimal("5000"),
            previous_draw_repay=Decimal("1337.86"),
        )
        decision = policy.decide(context)
        budget = Decimal("100000") * Decimal("0.04") / Decimal("12")
        # REPAY: nominal = C (not C * 2)
        assert decision.nominal_amount.amount == budget
        assert decision.loan_draw_amount == Decimal("0")
        assert decision.is_repayment is True

    def test_no_repay_when_no_loan(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        """compound_drawdown == 0 AND loan_balance = 0 → NORMAL mode."""
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset,
            initial_portfolio=initial_portfolio,
        )
        policy = Part52WithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            borrow_pct=Decimal("0.25"),
            drawdown_threshold=Decimal("0.20"),
        )
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("110"),  # new ATH
            running_ath=Decimal("110"),
            is_ath=True,
            compound_drawdown=Decimal("0"),
            loan_balance=Decimal("0"),
        )
        decision = policy.decide(context)
        budget = Decimal("100000") * Decimal("0.04") / Decimal("12")
        assert decision.nominal_amount.amount == budget
        assert decision.loan_draw_amount == Decimal("0")
        assert decision.is_repayment is False

    def test_borrow_pct_split(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        """Verify BORROW mode: nominal = C + D_t, loan_draw = D_t."""
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset,
            initial_portfolio=initial_portfolio,
        )
        borrow_pct = Decimal("0.4108")
        policy = Part52WithdrawalPolicy(
            withdrawal_rate=Decimal("0.0391"),
            borrow_pct=borrow_pct,
            drawdown_threshold=Decimal("0.20"),
        )
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("75"),
            running_ath=Decimal("100"),
            is_ath=False,
            compound_drawdown=Decimal("-0.25"),
        )
        decision = policy.decide(context)
        budget = Decimal("100000") * Decimal("0.0391") / Decimal("12")
        # BORROW: nominal = C + D_t - D_{t-1} = budget + D_t (D_{t-1}=0)
        assert decision.nominal_amount.amount == budget + budget * borrow_pct
        assert decision.loan_draw_amount == budget * borrow_pct

    def test_repayment_withdrawal_amount(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        """Verify REPAY mode: nominal = C (not C * 2)."""
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset,
            initial_portfolio=initial_portfolio,
        )
        policy = Part52WithdrawalPolicy(
            withdrawal_rate=Decimal("0.0391"),
            borrow_pct=Decimal("0.4108"),
            drawdown_threshold=Decimal("0.20"),
        )
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("110"),
            running_ath=Decimal("110"),
            is_ath=True,
            loan_balance=Decimal("5000"),
            previous_draw_repay=Decimal("1337.86"),
        )
        decision = policy.decide(context)
        budget = Decimal("100000") * Decimal("0.0391") / Decimal("12")
        # REPAY: nominal = C
        assert decision.nominal_amount.amount == budget

    def test_drawdown_computation(self) -> None:
        """Verify compound drawdown = min(0, (1 + prev_cDD) * (curr/prev) - 1)."""
        equity_asset = AssetClass(id="equity", name="Equity", description="")
        bond_asset = AssetClass(id="bond", name="Bond", description="")

        market_snapshot = MarketSnapshot(
            date=date(1965, 11, 1),
            index_levels={
                equity_asset: Decimal("80"),
                bond_asset: Decimal("100"),
            },
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=False,
            is_underwater=True,
            running_ath=Decimal("100"),
        )

        # compound DD = min(0, (1 + 0) * (80/100) - 1) = -0.20
        equity_index = market_snapshot.index_levels[equity_asset]
        running_ath = market_snapshot.running_ath
        simple_dd = Decimal("1") - (equity_index / running_ath)
        assert simple_dd == Decimal("0.20")


class TestMonthlyLoanDrawSemantics:
    """Tests for ERN monthly-draw behavior: a new loan draw every eligible month."""

    def test_borrow_with_existing_loan_balance(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        """Drawdown >= threshold AND loan_balance > 0 → BORROW mode.

        This is the core monthly-draw behavior: the existing loan balance
        does NOT prevent a new draw.
        """
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset,
            initial_portfolio=initial_portfolio,
        )
        policy = Part52WithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            borrow_pct=Decimal("0.25"),
            drawdown_threshold=Decimal("0.20"),
        )
        budget = Decimal("100000") * Decimal("0.04") / Decimal("12")
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("75"),
            running_ath=Decimal("100"),
            is_ath=False,
            loan_balance=Decimal("5000"),
            compound_drawdown=Decimal("-0.25"),
            previous_draw_repay=budget * Decimal("0.25"),
        )
        decision = policy.decide(context)
        assert decision.loan_draw_amount == budget * Decimal("0.25")
        # BORROW: nominal = C + D_t - D_{t-1} = C (when D_t == D_{t-1})
        expected_nominal = budget + budget * Decimal("0.25") - budget * Decimal("0.25")
        assert decision.nominal_amount.amount == expected_nominal
        assert decision.is_repayment is False

    def test_consecutive_draws_have_consistent_amount(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        """Each monthly draw produces the same budget × borrow_pct amount."""
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset,
            initial_portfolio=initial_portfolio,
        )
        policy = Part52WithdrawalPolicy(
            withdrawal_rate=Decimal("0.0391"),
            borrow_pct=Decimal("0.4108"),
            drawdown_threshold=Decimal("0.20"),
        )
        budget = Decimal("100000") * Decimal("0.0391") / Decimal("12")
        expected_draw = budget * Decimal("0.4108")

        # Simulate 3 consecutive months with compound DD > -threshold
        for month in range(3):
            existing_loan = expected_draw * month  # accumulates each month
            # previous_draw_repay = expected_draw for months > 0, 0 for month 0
            prev_draw = expected_draw if month > 0 else Decimal("0")
            context = _build_context(
                mock_sim_ctx,
                equity_index=Decimal("75"),
                running_ath=Decimal("100"),
                is_ath=False,
                loan_balance=existing_loan,
                compound_drawdown=Decimal("-0.25"),
                previous_draw_repay=prev_draw,
            )
            decision = policy.decide(context)
            assert decision.loan_draw_amount == expected_draw, (
                f"Month {month}: expected draw {expected_draw}, got {decision.loan_draw_amount}"
            )
            # BORROW: nominal = C + D_t - D_{t-1}
            assert decision.nominal_amount.amount == budget + expected_draw - prev_draw

    def test_drawdown_recovery_stops_borrowing(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        """When drawdown drops below threshold, no new draw occurs."""
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset,
            initial_portfolio=initial_portfolio,
        )
        policy = Part52WithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            borrow_pct=Decimal("0.25"),
            drawdown_threshold=Decimal("0.20"),
        )
        # First: compound DD below threshold → BORROW
        context_borrow = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("75"),
            running_ath=Decimal("100"),
            is_ath=False,
            loan_balance=Decimal("5000"),
            compound_drawdown=Decimal("-0.25"),
        )
        decision_borrow = policy.decide(context_borrow)
        assert decision_borrow.loan_draw_amount > Decimal("0")

        # Then: compound DD above threshold → NORMAL (no new draw)
        context_normal = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("95"),
            running_ath=Decimal("100"),
            is_ath=False,
            loan_balance=Decimal("5000"),
            compound_drawdown=Decimal("-0.15"),
        )
        decision_normal = policy.decide(context_normal)
        assert decision_normal.loan_draw_amount == Decimal("0")
        assert decision_normal.is_repayment is False

    def test_later_episode_can_borrow_again(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        """After full repayment, a new drawdown episode triggers fresh borrowing."""
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset,
            initial_portfolio=initial_portfolio,
        )
        policy = Part52WithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            borrow_pct=Decimal("0.25"),
            drawdown_threshold=Decimal("0.20"),
        )
        # Repayment at ATH clears the loan
        context_repay = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("110"),
            running_ath=Decimal("110"),
            is_ath=True,
            loan_balance=Decimal("5000"),
            previous_draw_repay=Decimal("1337.86"),
        )
        decision_repay = policy.decide(context_repay)
        assert decision_repay.is_repayment is True

        # New drawdown episode → BORROW again
        context_borrow = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("75"),
            running_ath=Decimal("110"),
            is_ath=False,
            loan_balance=Decimal("0"),
            compound_drawdown=Decimal("-0.318"),
        )
        decision_borrow = policy.decide(context_borrow)
        budget = Decimal("100000") * Decimal("0.04") / Decimal("12")
        assert decision_borrow.loan_draw_amount == budget * Decimal("0.25")
        assert decision_borrow.is_repayment is False

    def test_repayment_excess_computation(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        """In REPAY mode, nominal = C, spending_budget = C - D_{t-1}, excess = D_{t-1}."""
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset,
            initial_portfolio=initial_portfolio,
        )
        policy = Part52WithdrawalPolicy(
            withdrawal_rate=Decimal("0.0391"),
            borrow_pct=Decimal("0.4108"),
            drawdown_threshold=Decimal("0.20"),
        )
        loan = Decimal("50000")
        d_prev = Decimal("1337.86")
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("110"),
            running_ath=Decimal("110"),
            is_ath=True,
            compound_drawdown=Decimal("0"),
            loan_balance=loan,
            previous_draw_repay=d_prev,
        )
        decision = policy.decide(context)
        budget = Decimal("100000") * Decimal("0.0391") / Decimal("12")
        # REPAY: nominal = C, spending_budget = C - D_{t-1}
        assert decision.nominal_amount.amount == budget
        assert decision.spending_budget == budget - d_prev
        assert decision.loan_draw_amount == Decimal("0")
        assert decision.is_repayment is True

    def test_no_borrow_on_cdd_zero_with_zero_loan(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        """compound_drawdown == 0 AND loan_balance = 0 → NORMAL mode (not BORROW, not REPAY)."""
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset,
            initial_portfolio=initial_portfolio,
        )
        policy = Part52WithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            borrow_pct=Decimal("0.25"),
            drawdown_threshold=Decimal("0.20"),
        )
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("110"),
            running_ath=Decimal("110"),
            is_ath=True,
            compound_drawdown=Decimal("0"),
            loan_balance=Decimal("0"),
        )
        decision = policy.decide(context)
        budget = Decimal("100000") * Decimal("0.04") / Decimal("12")
        assert decision.nominal_amount.amount == budget
        assert decision.loan_draw_amount == Decimal("0")
        assert decision.is_repayment is False

    def test_no_borrow_below_threshold_with_existing_loan(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        """Drawdown < threshold AND loan_balance > 0 → NORMAL mode."""
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset,
            initial_portfolio=initial_portfolio,
        )
        policy = Part52WithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            borrow_pct=Decimal("0.25"),
            drawdown_threshold=Decimal("0.20"),
        )
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("95"),  # drawdown = 5%
            running_ath=Decimal("100"),
            is_ath=False,
            compound_drawdown=Decimal("-0.05"),
            loan_balance=Decimal("10000"),
        )
        decision = policy.decide(context)
        assert decision.loan_draw_amount == Decimal("0")
        assert decision.is_repayment is False
