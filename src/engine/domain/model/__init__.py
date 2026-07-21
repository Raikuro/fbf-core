"""Domain model package.

Contains core domain concepts and value objects such as assets, allocations, portfolios, and money.
"""

from .allocation import Allocation, AllocationTarget
from .asset import AssetClass, AssetSeries
from .dataset import Dataset
from .market_snapshot import MarketSnapshot
from .money import Money
from .portfolio import AssetHolding, Portfolio
from .decision_context import DecisionContext
from .simulation import (
    ExperimentDefinition,
    ExperimentRun,
    MonthlyResult,
    SimulationResult,
    SimulationState,
    SimulationStatistics,
    SimulationTimeline,
)

__all__ = [
    "Allocation",
    "AllocationTarget",
    "AssetClass",
    "AssetSeries",
    "Dataset",
    "MarketSnapshot",
    "Money",
    "AssetHolding",
    "Portfolio",
    "DecisionContext",
    "ExperimentDefinition",
    "ExperimentRun",
    "SimulationState",
    "SimulationStatistics",
    "SimulationTimeline",
    "MonthlyResult",
    "SimulationResult",
]
