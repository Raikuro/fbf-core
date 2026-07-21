"""Domain optimizer package.

Contains optimizer abstractions for finding safe withdrawal rates and related search results.
"""

from .optimizer import Optimizer, OptimizationResult

__all__ = ["Optimizer", "OptimizationResult"]
