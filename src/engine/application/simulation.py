"""Execution model objects for the Engine application.

Contains application-layer simulation state, results, and experiment definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Sequence

from engine.application.simulation_context import SimulationContext
from engine.domain.model.allocation import Allocation, AllocationTarget
from engine.domain.model.dataset import Dataset
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.money import Money
from engine.domain.model.portfolio import Portfolio
from engine.domain.policies import AllocationPolicy, WithdrawalPolicy


@dataclass
class SimulationState:
    """Mutable execution state for a single Simulation.

    Portfolio is the canonical source of truth for financial state.
    current_wealth is maintained as a derived cache and should only be
    updated from Domain valuation or service results, not modified independently.
    """

    context: SimulationContext
    current_date: date
    period_index: int
    portfolio: Portfolio
    allocation: Allocation | None = None
    allocation_target: AllocationTarget | None = None
    allocation_drift: object | None = None
    withdrawal_decision: object | None = None
    allocation_decision: object | None = None
    current_withdrawal: Money | None = None
    market_snapshot: MarketSnapshot | None = None
    current_wealth: Money | None = None
    peak_wealth: Money | None = None
    status: str | None = None
    failure_state: str | None = None
    decision_context: DecisionContext | None = None
    monthly_results: list[MonthlyResult] = field(default_factory=list)


@dataclass(frozen=True)
class MonthlyResult:
    """Immutable snapshot of the completed state at the end of one month."""

    date: date
    period_index: int
    market_snapshot: MarketSnapshot
    portfolio: Portfolio
    allocation: Allocation | None
    allocation_target: AllocationTarget | None
    allocation_drift: object | None
    withdrawal_decision: object | None
    rebalance_result: object | None
    drawdown: float
    cumulative_return: float
    cumulative_inflation: float
    events: Sequence[object]


@dataclass(frozen=True)
class SimulationTimeline:
    """Immutable history of all MonthlyResult records."""

    monthly_results: Sequence[MonthlyResult]


@dataclass(frozen=True)
class SimulationStatistics:
    """Derived metrics for a completed Simulation."""

    final_wealth: Money
    max_drawdown: float
    success: bool
    failure_month: int | None
    months_simulated: int
    execution_time_seconds: float


@dataclass(frozen=True)
class SimulationResult:
    """Final result produced by a completed Simulation."""

    timeline: SimulationTimeline
    statistics: SimulationStatistics


@dataclass(frozen=True)
class ExperimentDefinition:
    """Immutable description of an experiment."""

    name: str
    description: str
    dataset: Dataset
    horizon_months: int
    allocation_policy: AllocationPolicy
    withdrawal_policy: WithdrawalPolicy


@dataclass
class ExperimentRun:
    """Execution representation for a single ExperimentDefinition."""

    definition: ExperimentDefinition
    result: SimulationResult | None = None
