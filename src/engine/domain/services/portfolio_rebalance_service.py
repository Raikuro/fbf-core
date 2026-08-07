"""Portfolio rebalance service for the Engine domain."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from engine.domain.model.allocation import Allocation, AllocationTarget
from engine.domain.model.asset import AssetClass
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.money import Money
from engine.domain.model.portfolio import AssetHolding, Portfolio
from engine.domain.policies.decisions import AllocationDecision


def _canonical_asset_order(assets: Iterable[AssetClass]) -> list[AssetClass]:
    """Return assets in a canonical, insertion-order-independent sequence.

    ``Decimal`` division truncates to the context precision, so independently
    computed per-asset components cannot be guaranteed to reproduce their
    defining total exactly.  Both valuation services therefore close every
    sum with a deterministic residual assigned to the last canonical asset.

    The canonical order is defined by the stable ``AssetClass`` field triple
    ``(id, name, description)`` and is identical regardless of dictionary
    insertion order, portfolio holding order, or policy construction order.
    """
    return sorted(assets, key=lambda asset: (asset.id, asset.name, asset.description))


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

        current_value = portfolio_value

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
        ordered = _canonical_asset_order(target_weights)
        if not ordered:
            return []

        last_asset = ordered[-1]
        other_assets = ordered[:-1]

        target_amounts: dict[AssetClass, Decimal] = {}
        allocated = Decimal("0")
        for asset_class in other_assets:
            target_amount = portfolio_value.amount * target_weights[asset_class]
            target_amounts[asset_class] = target_amount
            allocated += target_amount
        residual = portfolio_value.amount - allocated
        if residual < Decimal("0"):
            residual = Decimal("0")
        target_amounts[last_asset] = residual

        new_holdings: list[AssetHolding] = []
        for asset_class, target_amount in target_amounts.items():
            price = self._fetch_price(asset_class, market_snapshot)

            if price == Decimal("0"):
                if target_amount != Decimal("0"):
                    raise ValueError(
                        f"Cannot satisfy allocation for asset '{asset_class.id}' with zero price"
                    )
                units = Decimal("0")
            else:
                units = target_amount / price

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

        ordered = _canonical_asset_order(
            {holding.asset_class for holding in portfolio.holdings}
        )
        if not ordered:
            return Allocation(weights=allocation_target.weights)

        values: dict[AssetClass, Decimal] = {}
        for holding in portfolio.holdings:
            price = self._fetch_price(holding.asset_class, market_snapshot)
            values[holding.asset_class] = holding.units * price

        total = sum(values.values())
        if total == Decimal("0"):
            return Allocation(weights=allocation_target.weights)

        weights: dict[AssetClass, Decimal] = {}
        allocated = Decimal("0")
        for asset_class in ordered[:-1]:
            weight = values[asset_class] / total
            weights[asset_class] = weight
            allocated += weight
        weights[ordered[-1]] = Decimal("1") - allocated

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
