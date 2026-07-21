"""Decision context placeholder for the Engine domain.

Contains the placeholder DecisionContext used by Policies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from .allocation import Allocation, AllocationTarget
from .dataset import Dataset
from .market_snapshot import MarketSnapshot
from .portfolio import Portfolio


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
