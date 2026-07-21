"""Portfolio withdrawal execution service for the Engine domain."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from engine.domain.model.asset import AssetClass
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.money import Money
from engine.domain.model.portfolio import AssetHolding, Portfolio
from engine.domain.policies.decisions import WithdrawalDecision


@dataclass(frozen=True)
class WithdrawalExecutionResult:
    requested_withdrawal: WithdrawalDecision
    portfolio: Portfolio
    depleted: bool
    shortfall: Money | None
    remaining_value: Money


class PortfolioWithdrawalService:
    """Service responsible for executing withdrawals against a portfolio."""

    def execute_withdrawal(
        self,
        portfolio: Portfolio,
        requested_withdrawal: WithdrawalDecision,
        market_snapshot: MarketSnapshot,
    ) -> WithdrawalExecutionResult:
        if portfolio is None:
            raise ValueError("Portfolio is required")
        if requested_withdrawal is None:
            raise ValueError("Requested withdrawal is required")
        if market_snapshot is None:
            raise ValueError("MarketSnapshot is required")
        if requested_withdrawal.nominal_amount.amount < Decimal("0"):
            raise ValueError("Requested withdrawal must not be negative")

        portfolio_value = self._calculate_portfolio_value(portfolio, market_snapshot)
        if requested_withdrawal.nominal_amount == Money.ZERO:
            return WithdrawalExecutionResult(
                requested_withdrawal=requested_withdrawal,
                portfolio=Portfolio(tuple(portfolio.holdings)),
                depleted=False,
                shortfall=None,
                remaining_value=portfolio_value,
            )

        if portfolio_value == Money.ZERO:
            return WithdrawalExecutionResult(
                requested_withdrawal=requested_withdrawal,
                portfolio=Portfolio(tuple(portfolio.holdings)),
                depleted=True,
                shortfall=requested_withdrawal.nominal_amount,
                remaining_value=Money.ZERO,
            )

        if requested_withdrawal.nominal_amount > portfolio_value:
            withdrawal_value = portfolio_value
            depleted = True
            shortfall = requested_withdrawal.nominal_amount - portfolio_value
        else:
            withdrawal_value = requested_withdrawal.nominal_amount
            depleted = False
            shortfall = None

        ratio = withdrawal_value.amount / portfolio_value.amount
        new_holdings: list[AssetHolding] = []
        for holding in portfolio.holdings:
            price = self._fetch_price(holding.asset_class, market_snapshot)
            holding_value = Money(holding.units * price, Money.ZERO.currency)

            if holding_value == Money.ZERO:
                new_holdings.append(holding)
                continue

            holding_withdrawal_value = Money(holding_value.amount * ratio, Money.ZERO.currency)
            units_sold = holding_withdrawal_value.amount / price
            remaining_units = holding.units - units_sold
            if remaining_units < Decimal("0"):
                remaining_units = Decimal("0")

            new_holdings.append(
                AssetHolding(asset_class=holding.asset_class, units=remaining_units)
            )

        new_portfolio = Portfolio(tuple(new_holdings))
        remaining_value = self._calculate_portfolio_value(new_portfolio, market_snapshot)

        return WithdrawalExecutionResult(
            requested_withdrawal=requested_withdrawal,
            portfolio=new_portfolio,
            depleted=depleted,
            shortfall=shortfall,
            remaining_value=remaining_value,
        )

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
