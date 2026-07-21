from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from engine.domain.model.asset import AssetClass
from engine.domain.model.allocation import Allocation
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.money import Money
from engine.domain.model.portfolio import AssetHolding, Portfolio
from engine.domain.services.portfolio_market_evolution_service import (
    PortfolioMarketEvolutionService,
)


class DummyMarketSnapshot(MarketSnapshot):
    pass


def make_portfolio() -> Portfolio:
    asset_a = AssetClass(id="a", name="Equity", description="Equity")
    asset_b = AssetClass(id="b", name="Bond", description="Bond")
    return Portfolio(
        (
            AssetHolding(asset_class=asset_a, units=Decimal("10")),
            AssetHolding(asset_class=asset_b, units=Decimal("20")),
        )
    )


def make_snapshot(asset_a: AssetClass, asset_b: AssetClass, price_a: Decimal, price_b: Decimal) -> MarketSnapshot:
    return DummyMarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={asset_a: price_a, asset_b: price_b},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=False,
        is_underwater=False,
        running_ath=max(price_a, price_b),
    )


def test_market_evolution_preserves_units_and_returns_new_portfolio() -> None:
    portfolio = make_portfolio()
    asset_a, asset_b = [holding.asset_class for holding in portfolio.holdings]
    snapshot = make_snapshot(asset_a, asset_b, Decimal("100"), Decimal("200"))
    service = PortfolioMarketEvolutionService()

    result = service.apply_market_evolution(portfolio, snapshot)

    assert result.portfolio is not portfolio
    assert [holding.units for holding in result.portfolio.holdings] == [Decimal("10"), Decimal("20")]
    assert [holding.asset_class for holding in result.portfolio.holdings] == [asset_a, asset_b]
    assert result.current_value == Money(Decimal("5000"), Money.ZERO.currency)
    assert result.allocation == Allocation(weights={asset_a: Decimal("0.2"), asset_b: Decimal("0.8")})


def test_market_evolution_handles_negative_returns() -> None:
    portfolio = make_portfolio()
    asset_a, asset_b = [holding.asset_class for holding in portfolio.holdings]
    snapshot = make_snapshot(asset_a, asset_b, Decimal("50"), Decimal("100"))
    service = PortfolioMarketEvolutionService()

    result = service.apply_market_evolution(portfolio, snapshot)

    assert result.current_value == Money(Decimal("2500"), Money.ZERO.currency)
    assert result.allocation == Allocation(weights={asset_a: Decimal("0.2"), asset_b: Decimal("0.8")})


def test_market_evolution_handles_zero_returns() -> None:
    portfolio = make_portfolio()
    asset_a, asset_b = [holding.asset_class for holding in portfolio.holdings]
    snapshot = make_snapshot(asset_a, asset_b, Decimal("0"), Decimal("0"))
    service = PortfolioMarketEvolutionService()

    result = service.apply_market_evolution(portfolio, snapshot)

    assert result.current_value == Money(Decimal("0"), Money.ZERO.currency)
    assert result.allocation == Allocation(weights={asset_a: Decimal("0.3333333333333333333333333333"), asset_b: Decimal("0.6666666666666666666666666667")})


def test_market_evolution_preserves_allocation_when_returns_are_identical() -> None:
    portfolio = make_portfolio()
    asset_a, asset_b = [holding.asset_class for holding in portfolio.holdings]
    snapshot = make_snapshot(asset_a, asset_b, Decimal("200"), Decimal("200"))
    service = PortfolioMarketEvolutionService()

    result = service.apply_market_evolution(portfolio, snapshot)

    assert result.allocation == Allocation(weights={asset_a: Decimal("0.3333333333333333333333333333"), asset_b: Decimal("0.6666666666666666666666666667")})


def test_market_evolution_is_deterministic() -> None:
    portfolio = make_portfolio()
    asset_a, asset_b = [holding.asset_class for holding in portfolio.holdings]
    snapshot = make_snapshot(asset_a, asset_b, Decimal("100"), Decimal("200"))
    service = PortfolioMarketEvolutionService()

    first = service.apply_market_evolution(portfolio, snapshot)
    second = service.apply_market_evolution(portfolio, snapshot)

    assert first.portfolio == second.portfolio
    assert first.allocation == second.allocation
    assert first.current_value == second.current_value


def test_market_evolution_recalculates_allocation_when_returns_differ() -> None:
    portfolio = make_portfolio()
    asset_a, asset_b = [holding.asset_class for holding in portfolio.holdings]
    snapshot = make_snapshot(asset_a, asset_b, Decimal("300"), Decimal("100"))
    service = PortfolioMarketEvolutionService()

    result = service.apply_market_evolution(portfolio, snapshot)

    assert result.allocation == Allocation(weights={asset_a: Decimal("0.6"), asset_b: Decimal("0.4")})


def test_market_evolution_raises_when_price_missing() -> None:
    portfolio = make_portfolio()
    asset_a = portfolio.holdings[0].asset_class
    snapshot = DummyMarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={asset_a: Decimal("100")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=False,
        is_underwater=False,
        running_ath=Decimal("100"),
    )
    service = PortfolioMarketEvolutionService()

    with pytest.raises(ValueError, match="Missing market price"):
        service.apply_market_evolution(portfolio, snapshot)
