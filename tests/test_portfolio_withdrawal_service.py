from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from engine.domain.model.asset import AssetClass
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.money import Money
from engine.domain.model.portfolio import AssetHolding, Portfolio
from engine.domain.policies.decisions import WithdrawalDecision
from engine.domain.services.portfolio_withdrawal_service import (
    PortfolioWithdrawalService,
    WithdrawalExecutionResult,
)


class DummyAssetClass(AssetClass):
    pass


class DummyMarketSnapshot(MarketSnapshot):
    pass


def make_portfolio() -> Portfolio:
    asset_a = AssetClass(id="a", name="Asset A", description="A")
    asset_b = AssetClass(id="b", name="Asset B", description="B")
    return Portfolio(
        (
            AssetHolding(asset_class=asset_a, units=Decimal("10")),
            AssetHolding(asset_class=asset_b, units=Decimal("5")),
        )
    )


def make_snapshot(asset_a: AssetClass, asset_b: AssetClass) -> MarketSnapshot:
    return DummyMarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={asset_a: Decimal("2"), asset_b: Decimal("4")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=False,
        is_underwater=False,
        running_ath=Decimal("4"),
    )


def test_portfolio_withdrawal_service_executes_proportional_withdrawal() -> None:
    portfolio = make_portfolio()
    asset_a, asset_b = [holding.asset_class for holding in portfolio.holdings]
    snapshot = make_snapshot(asset_a, asset_b)
    service = PortfolioWithdrawalService()

    decision = WithdrawalDecision(
        reason="test",
        nominal_amount=Money(Decimal("10"), Money.ZERO.currency),
        real_amount=Money(Decimal("10"), Money.ZERO.currency),
    )

    result = service.execute_withdrawal(portfolio, decision, snapshot)

    assert result.requested_withdrawal is decision
    assert result.depleted is False
    assert result.shortfall is None
    assert result.remaining_value.amount == Decimal("30")
    assert result.portfolio is not portfolio
    assert result.portfolio.holdings[0].units < portfolio.holdings[0].units
    assert result.portfolio.holdings[1].units < portfolio.holdings[1].units


def test_portfolio_withdrawal_service_returns_new_portfolio_for_zero_withdrawal() -> None:
    portfolio = make_portfolio()
    asset_a, asset_b = [holding.asset_class for holding in portfolio.holdings]
    snapshot = make_snapshot(asset_a, asset_b)
    service = PortfolioWithdrawalService()

    decision = WithdrawalDecision(
        reason="test",
        nominal_amount=Money.ZERO,
        real_amount=Money.ZERO,
    )

    result = service.execute_withdrawal(portfolio, decision, snapshot)

    assert result.depleted is False
    assert result.shortfall is None
    assert result.remaining_value == Money(Decimal("40"), Money.ZERO.currency)
    assert result.portfolio is not portfolio
    assert result.portfolio.holdings == portfolio.holdings


def test_portfolio_withdrawal_service_handles_empty_portfolio() -> None:
    snapshot = DummyMarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=False,
        is_underwater=False,
        running_ath=Decimal("0"),
    )
    service = PortfolioWithdrawalService()
    decision = WithdrawalDecision(
        reason="test",
        nominal_amount=Money(Decimal("1"), Money.ZERO.currency),
        real_amount=Money(Decimal("1"), Money.ZERO.currency),
    )

    result = service.execute_withdrawal(Portfolio(()), decision, snapshot)

    assert result.depleted is True
    assert result.shortfall == Money(Decimal("1"), Money.ZERO.currency)
    assert result.remaining_value == Money.ZERO
    assert result.portfolio.holdings == ()


def test_portfolio_withdrawal_service_rejects_negative_withdrawal() -> None:
    portfolio = make_portfolio()
    asset_a, asset_b = [holding.asset_class for holding in portfolio.holdings]
    snapshot = make_snapshot(asset_a, asset_b)
    service = PortfolioWithdrawalService()

    decision = WithdrawalDecision(
        reason="test",
        nominal_amount=Money(Decimal("-1"), Money.ZERO.currency),
        real_amount=Money(Decimal("-1"), Money.ZERO.currency),
    )

    with pytest.raises(ValueError, match="must not be negative"):
        service.execute_withdrawal(portfolio, decision, snapshot)


def test_portfolio_withdrawal_service_rejects_missing_price() -> None:
    portfolio = make_portfolio()
    asset_a, asset_b = [holding.asset_class for holding in portfolio.holdings]
    snapshot = DummyMarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={asset_a: Decimal("2")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=False,
        is_underwater=False,
        running_ath=Decimal("2"),
    )
    service = PortfolioWithdrawalService()
    decision = WithdrawalDecision(
        reason="test",
        nominal_amount=Money(Decimal("1"), Money.ZERO.currency),
        real_amount=Money(Decimal("1"), Money.ZERO.currency),
    )

    with pytest.raises(ValueError, match="Missing market price"):
        service.execute_withdrawal(portfolio, decision, snapshot)


def test_portfolio_withdrawal_service_conserves_portfolio_value_when_not_depleted() -> None:
    portfolio = make_portfolio()
    asset_a, asset_b = [holding.asset_class for holding in portfolio.holdings]
    snapshot = make_snapshot(asset_a, asset_b)
    service = PortfolioWithdrawalService()
    decision = WithdrawalDecision(
        reason="test",
        nominal_amount=Money(Decimal("10"), Money.ZERO.currency),
        real_amount=Money(Decimal("10"), Money.ZERO.currency),
    )

    before_value = Money.ZERO
    for holding in portfolio.holdings:
        before_value += Money(holding.units * snapshot.index_levels[holding.asset_class], Money.ZERO.currency)

    result = service.execute_withdrawal(portfolio, decision, snapshot)

    assert result.depleted is False
    assert before_value - decision.nominal_amount == result.remaining_value


def test_portfolio_withdrawal_service_is_deterministic() -> None:
    portfolio = make_portfolio()
    asset_a, asset_b = [holding.asset_class for holding in portfolio.holdings]
    snapshot = make_snapshot(asset_a, asset_b)
    service = PortfolioWithdrawalService()
    decision = WithdrawalDecision(
        reason="test",
        nominal_amount=Money(Decimal("10"), Money.ZERO.currency),
        real_amount=Money(Decimal("10"), Money.ZERO.currency),
    )

    first = service.execute_withdrawal(portfolio, decision, snapshot)
    second = service.execute_withdrawal(portfolio, decision, snapshot)

    assert first == second
