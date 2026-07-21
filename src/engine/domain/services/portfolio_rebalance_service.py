"""Portfolio rebalance service for the Engine domain."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from engine.domain.model.asset import AssetClass
from engine.domain.model.allocation import Allocation, AllocationTarget
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.money import Money
from engine.domain.model.portfolio import AssetHolding, Portfolio
from engine.domain.policies.decisions import AllocationDecision


@dataclass(frozen=True)
class PortfolioRebalanceResult:
    portfolio: Portfolio
    allocation: Allocation
    allocation_target: AllocationTarget
    current_value: Money


class PortfolioRebalanceService:
    """Service responsible for executing portfolio rebalances."""

    def execute_rebalance(
        self,
        portfolio: Portfolio,
        allocation_decision: AllocationDecision,
        market_snapshot: MarketSnapshot,
    ) -> PortfolioRebalanceResult:
        if portfolio is None:
            raise ValueError("Portfolio is required")
        if allocation_decision is None:
            raise ValueError("AllocationDecision is required")
        if market_snapshot is None:
            raise ValueError("MarketSnapshot is required")

        allocation_target = allocation_decision.allocation_target
        if allocation_target is None:
            raise ValueError("AllocationDecision.allocation_target is required")

        portfolio_value = self._calculate_portfolio_value(portfolio, market_snapshot)
        if portfolio_value.amount < Decimal("0"):
            raise ValueError("Portfolio value must not be negative")

        target_weights = allocation_target.weights
        new_holdings = self._build_rebalanced_holdings(
            portfolio=portfolio,
            target_weights=target_weights,
            market_snapshot=market_snapshot,
            portfolio_value=portfolio_value,
        )

        rebalanced_portfolio = Portfolio(tuple(new_holdings))
        current_value = self._calculate_portfolio_value(rebalanced_portfolio, market_snapshot)

        if portfolio_value != current_value:
            raise ValueError("Wealth conservation failed after rebalance")

        allocation = self._build_allocation(
            rebalanced_portfolio, current_value, allocation_target, market_snapshot
        )

        return PortfolioRebalanceResult(
            portfolio=rebalanced_portfolio,
            allocation=allocation,
            allocation_target=allocation_target,
            current_value=current_value,
        )

    def _build_rebalanced_holdings(
        self,
        portfolio: Portfolio,
        target_weights: dict[AssetClass, Decimal],
        market_snapshot: MarketSnapshot,
        portfolio_value: Money,
    ) -> list[AssetHolding]:
        target_values: dict[AssetClass, Money] = {}
        for asset_class, weight in target_weights.items():
            target_values[asset_class] = portfolio_value * weight

        new_holdings: list[AssetHolding] = []
        for asset_class, target_value in target_values.items():
            price = self._fetch_price(asset_class, market_snapshot)

            if price == Decimal("0"):
                if target_value.amount != Decimal("0"):
                    raise ValueError(
                        f"Cannot satisfy allocation for asset '{asset_class.id}' with zero price"
                    )
                units = Decimal("0")
            else:
                units = target_value.amount / price

            new_holdings.append(AssetHolding(asset_class=asset_class, units=units))

        return new_holdings

    def _build_allocation(
        self,
        portfolio: Portfolio,
        portfolio_value: Money,
        allocation_target: AllocationTarget,
        market_snapshot: MarketSnapshot,
    ) -> Allocation:
        if portfolio_value == Money.ZERO:
            return Allocation(weights=allocation_target.weights)

        weights: dict[AssetClass, Decimal] = {}
        for holding in portfolio.holdings:
            price = self._fetch_price(holding.asset_class, market_snapshot)
            holding_value = Money(holding.units * price, portfolio_value.currency)
            weights[holding.asset_class] = holding_value.amount / portfolio_value.amount

        return Allocation(weights=weights)

    def _calculate_portfolio_value(
        self, portfolio: Portfolio, market_snapshot: MarketSnapshot
    ) -> Money:
        total = Money.ZERO
        for holding in portfolio.holdings:
            price = self._fetch_price(holding.asset_class, market_snapshot)
            total += Money(holding.units * price, Money.ZERO.currency)
        return total

    def _fetch_price(
        self, asset_class: AssetClass, market_snapshot: MarketSnapshot
    ) -> Decimal:
        if asset_class not in market_snapshot.index_levels:
            raise ValueError(
                f"Missing market price for asset class '{asset_class.id}'"
            )
        return market_snapshot.index_levels[asset_class]
