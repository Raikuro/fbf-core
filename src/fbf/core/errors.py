"""Core exception hierarchy for the FIRE Backtesting Framework (FBF)."""

from __future__ import annotations


class CoreError(Exception):
    """Base exception for all Core errors."""


class StudyConfigurationError(CoreError):
    """Raised when a study configuration is invalid or malformed."""


class DatasetNotFoundError(CoreError):
    """Raised when a referenced historical dataset cannot be resolved."""


class ExecutionError(CoreError):
    """Raised when an unrecoverable error occurs during simulation execution."""


class PersistenceError(CoreError):
    """Raised when an error occurs during study storage or retrieval."""


class DuplicateStudyError(PersistenceError):
    """Raised when attempting to persist a study with an existing ID without overwrite."""


class OptimizationError(CoreError):
    """Raised when SWR optimization fails or diverges."""
