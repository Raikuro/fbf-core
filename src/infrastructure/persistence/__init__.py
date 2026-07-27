"""Infrastructure persistence package (v0.4).

Public API for the SQLite persistence layer.
"""

from .errors import (
    CorruptedDatabaseError,
    DuplicateStudyError,
    PersistenceError,
    PlanNotFoundError,
    ReconstructionContextError,
    RepositoryError,
    ResultsNotFoundError,
    StudyNotFoundError,
    UnsupportedSerializationError,
)
from .sqlite_repository import (
    ExperimentIdentity,
    PersistenceReconstructionContext,
    SQLiteRepository,
)

__all__ = [
    "CorruptedDatabaseError",
    "DuplicateStudyError",
    "ExperimentIdentity",
    "PersistenceError",
    "PersistenceReconstructionContext",
    "PlanNotFoundError",
    "ReconstructionContextError",
    "RepositoryError",
    "ResultsNotFoundError",
    "SQLiteRepository",
    "StudyNotFoundError",
    "UnsupportedSerializationError",
]
