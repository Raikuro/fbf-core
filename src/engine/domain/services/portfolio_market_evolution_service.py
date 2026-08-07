"""Portfolio market evolution service for the Engine domain."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from engine.domain.model.allocation import Allocation
from engine.domain.model.asset import AssetClass
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.money import Money
from engine.domain.model.portfolio import AssetHolding, Portfolio
from engine.domain.services.portfolio_rebalance_service import _canonical_asset_order


@dataclass(frozen=True)
class PortfolioMarketEvolutionResult:
    portfolio: Portfolio
    allocation: Allocation
    current_value: Money


class PortfolioMarketEvolutionService:
    """Service responsible for applying market evolution to a portfolio."""

    def derive_allocation(
        self,
        portfolio: Portfolio,
        market_snapshot: MarketSnapshot,
    ) -> Allocation:
        """Derive the value-weighted allocation of a portfolio at a snapshot.

        This is the same valuation derivation used by market evolution, exposed so
        the application layer can materialise the initial allocation before the
        monthly pipeline's decision context is built.
        """
        if portfolio is None:
            raise ValueError("Portfolio is required")
        if market_snapshot is None:
            raise ValueError("MarketSnapshot is required")
        value = self._calculate_portfolio_value(portfolio, market_snapshot)
        return self._build_allocation(portfolio, value, market_snapshot)

    def apply_market_evolution(
        self,
        portfolio: Portfolio,
        market_snapshot: MarketSnapshot,
    ) -> PortfolioMarketEvolutionResult:
        if portfolio is None:
            raise ValueError("Portfolio is required")
        if market_snapshot is None:
            raise ValueError("MarketSnapshot is required")

        new_holdings = self._evolve_holdings(portfolio, market_snapshot)
        evolved_portfolio = Portfolio(tuple(new_holdings))
        current_value = self._calculate_portfolio_value(evolved_portfolio, market_snapshot)
        allocation = self._build_allocation(evolved_portfolio, current_value, market_snapshot)

        return PortfolioMarketEvolutionResult(
            portfolio=evolved_portfolio,
            allocation=allocation,
            current_value=current_value,
        )

    def _evolve_holdings(
        self,
        portfolio: Portfolio,
        market_snapshot: MarketSnapshot,
    ) -> list[AssetHolding]:
        holdings: list[AssetHolding] = []

        for holding in portfolio.holdings:
            price = self._fetch_price(holding.asset_class, market_snapshot)
            if price < Decimal("0"):
                raise ValueError(
                    f"Invalid market price for asset class '{holding.asset_class.id}'"
                )
            holdings.append(
                AssetHolding(asset_class=holding.asset_class, units=holding.units)
            )

        return holdings

    def _calculate_portfolio_value(
        self, portfolio: Portfolio, market_snapshot: MarketSnapshot
    ) -> Money:
        total = Money.ZERO
        for holding in portfolio.holdings:
            price = self._fetch_price(holding.asset_class, market_snapshot)
            total += Money(holding.units * price, Money.ZERO.currency)
        return total

    def _build_allocation(
        self,
        portfolio: Portfolio,
        portfolio_value: Money,
        market_snapshot: MarketSnapshot,
    ) -> Allocation:
        ordered = _canonical_asset_order(
            {holding.asset_class for holding in portfolio.holdings}
        )
        if not ordered:
            raise ValueError("Cannot derive allocation for empty portfolio")

        if portfolio_value == Money.ZERO:
            total_units = sum(holding.units for holding in portfolio.holdings)
            if total_units == Decimal("0"):
                raise ValueError("Cannot derive allocation for zero-value portfolio")
            units_by_asset = {
                holding.asset_class: holding.units for holding in portfolio.holdings
            }
            weights: dict[AssetClass, Decimal] = {}
            allocated = Decimal("0")
            for asset_class in ordered[:-1]:
                weight = units_by_asset[asset_class] / total_units
                weights[asset_class] = weight
                allocated += weight
            weights[ordered[-1]] = Decimal("1") - allocated
            return Allocation(weights=weights)

        values: dict[AssetClass, Decimal] = {}
        for holding in portfolio.holdings:
            price = self._fetch_price(holding.asset_class, market_snapshot)
            values[holding.asset_class] = holding.units * price

        weights = {}
        allocated = Decimal("0")
        for asset_class in ordered[:-1]:
            weight = values[asset_class] / portfolio_value.amount
            weights[asset_class] = weight
            allocated += weight
        weights[ordered[-1]] = Decimal("1") - allocated
        return Allocation(weights=weights)

    def _fetch_price(
        self, asset_class: AssetClass, market_snapshot: MarketSnapshot
    ) -> Decimal:
        if asset_class not in market_snapshot.index_levels:
            raise ValueError(
                f"Missing market price for asset class '{asset_class.id}'"
            )
        return market_snapshot.index_levels[asset_class]
