"""Simulation execution strategies.

The optimized Numba executors are the only simulation engines.  Shared
eligibility and trajectory-grouping helpers live in :mod:`.eligibility`.
"""

from .parallel_executor import (
    ExecutionConfig,
    ParallelExecutor,
    create_work_batches,
    parallel_execute,
    sequential_execute,
)

__all__ = [
    "ExecutionConfig",
    "ParallelExecutor",
    "create_work_batches",
    "parallel_execute",
    "sequential_execute",
]
