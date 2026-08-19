"""Persistence protocols and study repositories."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from fbf.core.persistence.studies.sqlite.sqlite_repository import (
    SQLiteRepository,
    SQLiteStudyRepository,
)


class StudyRepository(Protocol):
    """Protocol defining study persistence contract."""
    def save_study(self, study: Any) -> str: ...
    def get_study(self, study_id: str) -> Any | None: ...
    def list_studies(self) -> Sequence[Any]: ...


def create_study_repository(db_path: str = "retirement_simulation.db") -> SQLiteRepository:
    """Factory creating the default SQLite study repository."""
    return SQLiteRepository(db_path=db_path)


__all__ = [
    "StudyRepository",
    "create_study_repository",
    "SQLiteRepository",
    "SQLiteStudyRepository",
]
