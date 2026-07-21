"""Portfolio valuation service placeholder for the Engine domain."""

from __future__ import annotations

from .portfolio import Portfolio


class PortfolioValuationService:
    """Placeholder service responsible for portfolio valuation."""

    def calculate_value(self, portfolio: Portfolio) -> object:
        raise NotImplementedError
