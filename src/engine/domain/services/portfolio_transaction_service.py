"""Portfolio transaction service placeholder for the Engine domain."""

from __future__ import annotations

from .portfolio import Portfolio


class PortfolioTransactionService:
    """Placeholder service responsible for portfolio transactions."""

    def execute_transaction(self, portfolio: Portfolio, amount: object) -> object:
        raise NotImplementedError
