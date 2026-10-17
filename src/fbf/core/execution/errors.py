"""Research orchestration error hierarchy.

Defines the exception hierarchy for research plan execution failures.

Classes
-------
ResearchExecutionError:
    Base exception for all errors raised during research plan execution.
InvalidResearchPlanError:
    Raised when a ResearchPlan fails structural or translation validation
    before execution begins.
UnsupportedConfigurationError:
    Raised when a workload cannot be executed by the requested backend because
    its configuration is not supported by that backend.
"""

from __future__ import annotations


class ResearchExecutionError(Exception):
    """Base exception for errors during research plan execution."""


class InvalidResearchPlanError(ResearchExecutionError):
    """Raised when a ResearchPlan fails structural or translation validation before execution."""


class UnsupportedConfigurationError(ResearchExecutionError):
    """Raised when a workload cannot be executed by the requested backend.

    Used to make backend routing explicit: an optimized backend must fail
    loudly for a configuration it cannot execute rather than silently
    delegating to a different numerical engine with different conventions.
    """
