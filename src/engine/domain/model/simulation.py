"""Simulation model objects for the Engine domain.

Contains simulation context, state, results, and related value objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from .dataset import Dataset
from .allocation import Allocation, AllocationTarget
from .money import Money


@dataclass
class SimulationState:
    """Mutable state that evolves during a Simulation."""

    current_date: date
    period_index: int
    portfolio: object | None = None
    allocation: Allocation | None = None
    allocation_target: AllocationTarget | None = None
    allocation_drift: object | None = None
    withdrawal_decision: object | None = None
    market_snapshot: object | None = None
    current_wealth: Money | None = None
    peak_wealth: Money | None = None


@dataclass(frozen=True)
class SimulationStatistics:
    """Immutable aggregated metrics for a Simulation."""

    months_simulated: int
    withdrawals_count: int
    rebalances_count: int
    buy_trades_count: int
    sell_trades_count: int
    capital_withdrawn: Money
    capital_traded: Money
    peak_wealth: Money
    min_wealth: Money
    max_drawdown: float
    cagr: float
    execution_time_seconds: float


@dataclass(frozen=True)
class MonthlyResult:
    """Immutable snapshot of a Simulation at the end of one month."""

    date: date
    period_index: int
    market_snapshot: object
    portfolio_value: Money
    allocation: Allocation
    allocation_target: AllocationTarget
    allocation_drift: object
    withdrawal_decision: object
    rebalance_result: object | None
    drawdown: float
    cumulative_return: float
    cumulative_inflation: float
    events: Sequence[object]


@dataclass(frozen=True)
class SimulationTimeline:
    """Immutable chronological record of MonthlyResult records."""

    monthly_results: Sequence[MonthlyResult]


@dataclass(frozen=True)
class Summary:
    """Immutable summary metadata for a completed Simulation."""

    strategy_name: str
    cohort: str
    start_date: date
    end_date: date
    final_wealth: Money
    objective_reached: bool
    final_state: str


@dataclass(frozen=True)
class Diagnostics:
    """Immutable diagnostic information for a completed Simulation."""

    construction_time_seconds: float
    simulation_time_seconds: float
    iterations: int
    engine_version: str
    dataset_version: str


@dataclass(frozen=True)
class SimulationResult:
    """Immutable result produced by a completed Simulation."""

    context: object
    statistics: SimulationStatistics
    timeline: SimulationTimeline
    summary: Summary
    diagnostics: Diagnostics


@dataclass(frozen=True)
class ExperimentDefinition:
    """Immutable definition of a scientific experiment."""

    name: str
    description: str
    dataset: Dataset
    horizon_months: int
    cohorts: Sequence[str]
    allocation_policies: Sequence[object]
    withdrawal_policies: Sequence[object]


@dataclass
class ExperimentRun:
    """Runtime representation of an ExperimentDefinition execution."""

    definition: ExperimentDefinition
    run_id: str
    execution_date: date
    state: str
    configuration: dict[str, object]
