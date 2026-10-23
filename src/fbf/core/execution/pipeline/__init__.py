"""Simulation contracts shared by every execution strategy.

This package contains immutable simulation inputs and outputs plus the
``SimulationExecutor`` abstraction.  It has no execution engine of its own.
"""

from .executor import SimulationExecutor
from .simulation import (
    ExperimentDefinition,
    ExperimentRun,
    MonthlyResult,
    SimulationResult,
    SimulationState,
    SimulationStatistics,
    SimulationTimeline,
)
from .simulation_context import SimulationContext

__all__ = [
    "SimulationContext",
    "SimulationState",
    "MonthlyResult",
    "SimulationResult",
    "SimulationStatistics",
    "SimulationTimeline",
    "ExperimentDefinition",
    "ExperimentRun",
    "SimulationExecutor",
]
