"""Decision context placeholder for the Engine domain.

Contains the placeholder DecisionContext used by Policies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .allocation import Allocation, AllocationTarget
from .dataset import Dataset
from .market_snapshot import MarketSnapshot
from .portfolio import Portfolio


@dataclass(frozen=True)
class DebtInfo:
    """Immutable debt information for policy decisions.

    This is a snapshot of the debt state at the beginning of the period.
    Policies observe this to make allocation decisions.
    Policies never mutate debt state.

    Authoritative net-worth identity:
        net_worth = portfolio_value + cash_balance - loan_balance

    This identity holds because cash_balance represents borrowed funds
    that are available for spending but not yet consumed.
    """

    loan_balance: Decimal
    interest_rate: Decimal
    ltv_limit: Decimal
    portfolio_value: Decimal
    cash_balance: Decimal = Decimal("0")

    @property
    def net_worth(self) -> Decimal:
        """Derived net worth: portfolio + cash - loan.

        Authoritative identity: net_worth = portfolio_value + cash_balance - loan_balance
        """
        return self.portfolio_value + self.cash_balance - self.loan_balance


@dataclass(frozen=True)
class DecisionContext:
    """Immutable decision context used by Policies."""

    date: date
    period_index: int
    simulation_context: object
    portfolio: Portfolio
    current_allocation: Allocation
    target_allocation: AllocationTarget
    market_snapshot: MarketSnapshot
    dataset: Dataset
    debt_info: DebtInfo | None = None
