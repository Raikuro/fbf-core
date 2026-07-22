"""Execution model objects for the Engine application.

Contains application-layer simulation state, results, and experiment definitions.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from engine.application.simulation_context import SimulationContext
from engine.domain.model.allocation import Allocation, AllocationTarget
from engine.domain.model.decision_context import DecisionContext
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.money import Money
from engine.domain.model.portfolio import Portfolio


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
    failure_state: str | None = None
    status: ExecutionStatus | None = None
    decision_context: DecisionContext | None = None
    monthly_results: list[MonthlyResult] = field(default_factory=list)


class ExecutionStatus(Enum):
    """Enumeration of simulation execution states."""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


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
    """Immutable, ordered request for a scientific experiment."""

    name: str
    description: str
    simulation_contexts: tuple[SimulationContext, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("ExperimentDefinition.name must be non-empty")
        if self.description is None:
            raise ValueError("ExperimentDefinition.description is required")
        if not isinstance(self.simulation_contexts, tuple):
            raise TypeError("ExperimentDefinition.simulation_contexts must be a tuple")
        if any(
            not isinstance(context, SimulationContext)
            for context in self.simulation_contexts
        ):
            raise ValueError(
                "ExperimentDefinition.simulation_contexts must contain SimulationContext values"
            )
        if len({id(context) for context in self.simulation_contexts}) != len(
            self.simulation_contexts
        ):
            raise ValueError(
                "ExperimentDefinition.simulation_contexts must not contain duplicates"
            )


@dataclass(frozen=True)
class ExperimentRun:
    """Immutable aggregate result of a completed ExperimentDefinition."""

    definition: ExperimentDefinition
    simulation_results: tuple[SimulationResult, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.definition, ExperimentDefinition):
            raise TypeError("ExperimentRun.definition must be an ExperimentDefinition")
        if not isinstance(self.simulation_results, tuple):
            raise TypeError("ExperimentRun.simulation_results must be a tuple")
        if len(self.simulation_results) != len(self.definition.simulation_contexts):
            raise ValueError(
                "ExperimentRun.simulation_results must match the definition context count"
            )
        if any(not isinstance(result, SimulationResult) for result in self.simulation_results):
            raise TypeError(
                "ExperimentRun.simulation_results must contain SimulationResult values"
            )
