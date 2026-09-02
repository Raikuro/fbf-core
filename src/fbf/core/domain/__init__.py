"""Domain models, entities, and financial valuation services."""

from __future__ import annotations

from fbf.core.domain.model.allocation import Allocation, AllocationTarget
from fbf.core.domain.model.asset import AssetClass, AssetSeries
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.model.simulation import (
    MonthlyResult,
    SimulationResult,
    SimulationState,
    SimulationStatistics,
    SimulationTimeline,
)
from fbf.core.domain.policies.allocation_policy import AllocationPolicy
from fbf.core.domain.policies.concrete import (
    ConstantAllocationPolicy,
    ConstantWithdrawalPolicy,
    FixedRealWithdrawalPolicy,
)
from fbf.core.domain.policies.decisions import AllocationDecision, WithdrawalDecision
from fbf.core.domain.policies.glidepath import GlidepathAllocationPolicy
from fbf.core.domain.policies.policy import Policy
from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy

__all__ = [
    "Money",
    "Currency",
    "Portfolio",
    "AssetHolding",
    "AssetClass",
    "AssetSeries",
    "Dataset",
    "MarketSnapshot",
    "Allocation",
    "AllocationTarget",
    "SimulationTimeline",
    "SimulationResult",
    "SimulationStatistics",
    "MonthlyResult",
    "SimulationState",
    "Policy",
    "AllocationPolicy",
    "WithdrawalPolicy",
    "AllocationDecision",
    "WithdrawalDecision",
    "ConstantAllocationPolicy",
    "ConstantWithdrawalPolicy",
    "FixedRealWithdrawalPolicy",
    "GlidepathAllocationPolicy",
]
