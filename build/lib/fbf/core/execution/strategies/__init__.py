"""Parallel execution module for FIRE Backtesting Framework (v0.4)."""

from .parallel_executor import (
    ExecutionConfig,
    ParallelExecutor,
    create_work_batches,
    parallel_execute,
    sequential_execute,
)
from .reference_chaining import ChainedReferenceSimulationExecutor

__all__ = [
    "ExecutionConfig",
    "ParallelExecutor",
    "create_work_batches",
    "parallel_execute",
    "sequential_execute",
    "ChainedReferenceSimulationExecutor",
]
