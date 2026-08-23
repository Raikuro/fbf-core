"""Parallel execution module for FIRE Backtesting Framework (v0.4)."""

from .parallel_executor import (
    ExecutionConfig,
    ParallelExecutor,
    create_work_batches,
    parallel_execute,
    sequential_execute,
)
from .reference import ReferenceSimulationExecutor

__all__ = [
    "ExecutionConfig",
    "ParallelExecutor",
    "create_work_batches",
    "parallel_execute",
    "sequential_execute",
    "ReferenceSimulationExecutor",
]
