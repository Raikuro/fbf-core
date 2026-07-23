"""Research orchestration error hierarchy.

Defines the exception hierarchy for research plan execution failures.

Classes
-------
ResearchExecutionError:
    Base exception for all errors raised during research plan execution.
InvalidResearchPlanError:
    Raised when a ResearchPlan fails structural or translation validation
    before execution begins.
"""

from __future__ import annotations


class ResearchExecutionError(Exception):
    """Base exception for errors during research plan execution."""


class InvalidResearchPlanError(ResearchExecutionError):
    """Raised when a ResearchPlan fails structural or translation validation before execution."""
