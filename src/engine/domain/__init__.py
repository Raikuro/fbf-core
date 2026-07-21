"""Engine domain package.

Contains pure domain abstractions, value objects, entities and domain services.
"""

from .model.allocation import Allocation, AllocationTarget
from .model.asset import AssetClass, AssetSeries
from .model.dataset import Dataset
from .model.market_snapshot import MarketSnapshot
from .model.money import Money
from .model.portfolio import AssetHolding, Portfolio
from .model.simulation import (
    ExperimentDefinition,
    ExperimentRun,
    MonthlyResult,
    SimulationResult,
    SimulationState,
    SimulationStatistics,
    SimulationTimeline,
)
from .optimizer.optimizer import Optimizer, OptimizationResult
from .policies.allocation_policy import AllocationPolicy
from .policies.policy import Policy
from .policies.decisions import AllocationDecision, PolicyDecision, WithdrawalDecision
from .policies.withdrawal_policy import WithdrawalPolicy
from .validation.validation import ValidationResult

__all__ = [
    "AssetClass",
    "AssetSeries",
    "Dataset",
    "MarketSnapshot",
    "Money",
    "Allocation",
    "AllocationTarget",
    "AssetHolding",
    "Portfolio",
    "SimulationState",
    "SimulationStatistics",
    "SimulationTimeline",
    "MonthlyResult",
    "SimulationResult",
    "ExperimentDefinition",
    "ExperimentRun",
    "Optimizer",
    "OptimizationResult",
    "Policy",
    "PolicyDecision",
    "AllocationPolicy",
    "WithdrawalPolicy",
    "AllocationDecision",
    "WithdrawalDecision",
    "ValidationResult",
]
