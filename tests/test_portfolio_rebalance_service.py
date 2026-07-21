from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from engine.domain.model.asset import AssetClass
from engine.domain.model.allocation import Allocation, AllocationTarget
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.money import Money
from engine.domain.model.portfolio import AssetHolding, Portfolio
from engine.domain.policies.decisions import AllocationDecision
from engine.domain.services.portfolio_rebalance_service import (
    PortfolioRebalanceResult,
    PortfolioRebalanceService,
)


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


def test_portfolio_rebalance_service_executes_proportional_multi_asset_rebalance() -> None:
    portfolio = make_portfolio()
    asset_a, asset_b = [holding.asset_class for holding in portfolio.holdings]
    snapshot = make_snapshot(asset_a, asset_b)
    service = PortfolioRebalanceService()

    decision = AllocationDecision(
        reason="test",
        allocation_target=AllocationTarget(weights={asset_a: Decimal("0.6"), asset_b: Decimal("0.4")}),
    )

    result = service.execute_rebalance(portfolio, decision, snapshot)

    assert isinstance(result, PortfolioRebalanceResult)
    assert result.portfolio is not portfolio
    assert result.current_value == Money(Decimal("40"), Money.ZERO.currency)
    assert result.allocation == Allocation(weights={asset_a: Decimal("0.6"), asset_b: Decimal("0.4")})
    assert result.allocation_target is decision.allocation_target


def test_portfolio_rebalance_service_preserves_wealth_exactly() -> None:
    portfolio = make_portfolio()
    asset_a, asset_b = [holding.asset_class for holding in portfolio.holdings]
    snapshot = make_snapshot(asset_a, asset_b)
    service = PortfolioRebalanceService()
    decision = AllocationDecision(
        reason="test",
        allocation_target=AllocationTarget(weights={asset_a: Decimal("0.6"), asset_b: Decimal("0.4")}),
    )

    before_value = Money.ZERO
    for holding in portfolio.holdings:
        before_value += Money(holding.units * snapshot.index_levels[holding.asset_class], Money.ZERO.currency)

    result = service.execute_rebalance(portfolio, decision, snapshot)

    after_value = Money.ZERO
    for holding in result.portfolio.holdings:
        after_value += Money(holding.units * snapshot.index_levels[holding.asset_class], Money.ZERO.currency)

    assert before_value == after_value
    assert before_value == result.current_value


def test_portfolio_rebalance_service_preserves_trade_value() -> None:
    portfolio = make_portfolio()
    asset_a, asset_b = [holding.asset_class for holding in portfolio.holdings]
    snapshot = make_snapshot(asset_a, asset_b)
    service = PortfolioRebalanceService()
    decision = AllocationDecision(
        reason="test",
        allocation_target=AllocationTarget(weights={asset_a: Decimal("0.6"), asset_b: Decimal("0.4")}),
    )

    result = service.execute_rebalance(portfolio, decision, snapshot)

    buy_value = Money.ZERO
    sell_value = Money.ZERO
    for before, after in zip(portfolio.holdings, result.portfolio.holdings):
        before_value = Money(before.units * snapshot.index_levels[before.asset_class], Money.ZERO.currency)
        after_value = Money(after.units * snapshot.index_levels[after.asset_class], Money.ZERO.currency)
        diff = after_value - before_value
        if diff.amount > 0:
            buy_value += diff
        else:
            sell_value += Money(-diff.amount, diff.currency)

    assert buy_value == sell_value


def test_portfolio_rebalance_service_is_idempotent() -> None:
    portfolio = make_portfolio()
    asset_a, asset_b = [holding.asset_class for holding in portfolio.holdings]
    snapshot = make_snapshot(asset_a, asset_b)
    service = PortfolioRebalanceService()
    decision = AllocationDecision(
        reason="test",
        allocation_target=AllocationTarget(weights={asset_a: Decimal("0.6"), asset_b: Decimal("0.4")}),
    )

    first = service.execute_rebalance(portfolio, decision, snapshot)
    second = service.execute_rebalance(first.portfolio, decision, snapshot)

    assert first.portfolio == second.portfolio
    assert first.allocation == second.allocation
    assert first.current_value == second.current_value


def test_portfolio_rebalance_service_is_order_independent() -> None:
    asset_a = AssetClass(id="a", name="Asset A", description="A")
    asset_b = AssetClass(id="b", name="Asset B", description="B")
    portfolio_one = Portfolio(
        (
            AssetHolding(asset_class=asset_a, units=Decimal("10")),
            AssetHolding(asset_class=asset_b, units=Decimal("5")),
        )
    )
    portfolio_two = Portfolio(
        (
            AssetHolding(asset_class=asset_b, units=Decimal("5")),
            AssetHolding(asset_class=asset_a, units=Decimal("10")),
        )
    )
    snapshot = make_snapshot(asset_a, asset_b)
    service = PortfolioRebalanceService()
    decision = AllocationDecision(
        reason="test",
        allocation_target=AllocationTarget(weights={asset_a: Decimal("0.5"), asset_b: Decimal("0.5")}),
    )

    first = service.execute_rebalance(portfolio_one, decision, snapshot)
    second = service.execute_rebalance(portfolio_two, decision, snapshot)

    assert first.portfolio == second.portfolio
    assert first.allocation == second.allocation
    assert first.current_value == second.current_value


def test_portfolio_rebalance_service_returns_new_portfolio_for_already_balanced_portfolio() -> None:
    asset_a, asset_b = AssetClass(id="a", name="Asset A", description="A"), AssetClass(
        id="b", name="Asset B", description="B"
    )
    portfolio = Portfolio(
        (
            AssetHolding(asset_class=asset_a, units=Decimal("10")),
            AssetHolding(asset_class=asset_b, units=Decimal("5")),
        )
    )
    snapshot = make_snapshot(asset_a, asset_b)
    service = PortfolioRebalanceService()
    decision = AllocationDecision(
        reason="test",
        allocation_target=AllocationTarget(weights={asset_a: Decimal("0.5"), asset_b: Decimal("0.5")}),
    )

    result = service.execute_rebalance(portfolio, decision, snapshot)

    assert result.portfolio is not portfolio
    assert result.portfolio.holdings == portfolio.holdings
    assert result.current_value == Money(Decimal("40"), Money.ZERO.currency)
    assert result.allocation == Allocation(weights={asset_a: Decimal("0.5"), asset_b: Decimal("0.5")})
