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
        """Drawdown >= threshold AND loan_balance = 0 → BORROW mode."""
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
            equity_index=Decimal("75"),  # drawdown = 25%
            running_ath=Decimal("100"),
            is_ath=False,
        )
        decision = policy.decide(context)
        # budget = 100000 * 0.04 / 12 = 333.333...
        budget = Decimal("100000") * Decimal("0.04") / Decimal("12")
        assert decision.loan_draw_amount == budget * Decimal("0.25")
        assert decision.nominal_amount.amount == budget * Decimal("0.75")
        assert decision.is_repayment is False

    def test_repay_when_at_ath_with_loan(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        """is_ath = True AND loan_balance > 0 → REPAY mode."""
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
            loan_balance=Decimal("5000"),
        )
        decision = policy.decide(context)
        budget = Decimal("100000") * Decimal("0.04") / Decimal("12")
        assert decision.nominal_amount.amount == budget * 2
        assert decision.loan_draw_amount == Decimal("0")
        assert decision.is_repayment is True

    def test_no_repay_when_no_loan(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        """is_ath = True AND loan_balance = 0 → NORMAL mode."""
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
        """Verify portfolio_withdrawal = budget * (1 - borrow_pct) in BORROW mode."""
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
        )
        decision = policy.decide(context)
        budget = Decimal("100000") * Decimal("0.0391") / Decimal("12")
        assert decision.nominal_amount.amount == budget * (1 - borrow_pct)
        assert decision.loan_draw_amount == budget * borrow_pct

    def test_repayment_doubles_withdrawal(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        """Verify portfolio_withdrawal = budget * 2 in REPAY mode."""
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
        )
        decision = policy.decide(context)
        budget = Decimal("100000") * Decimal("0.0391") / Decimal("12")
        assert decision.nominal_amount.amount == budget * 2

    def test_drawdown_computation(self) -> None:
        """Verify drawdown = 1 - (equity_index / running_ath)."""
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

        # drawdown = 1 - (80/100) = 0.20
        equity_index = market_snapshot.index_levels[equity_asset]
        running_ath = market_snapshot.running_ath
        drawdown = Decimal("1") - (equity_index / running_ath)
        assert drawdown == Decimal("0.20")
