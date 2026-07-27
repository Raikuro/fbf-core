"""Infrastructure persistence package (v0.4).

Public API for the SQLite persistence layer.
"""

from .errors import (
    CorruptedDatabaseError,
    DuplicateStudyError,
    PersistenceError,
    RepositoryError,
    ResultsNotFoundError,
    StudyNotFoundError,
)
from .sqlite_repository import SQLiteRepository

__all__ = [
    "SQLiteRepository",
    "RepositoryError",
    "StudyNotFoundError",
    "ResultsNotFoundError",
    "DuplicateStudyError",
    "PersistenceError",
    "CorruptedDatabaseError",
]
