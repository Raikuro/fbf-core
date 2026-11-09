"""Schema compatibility tests for the SQLite persistence layer.

Schema version 6 persists each planned unit's dataset start and effective
horizon. Databases created by older schema versions are rejected rather than
migrated because the missing unit provenance cannot be reconstructed safely.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fbf.core.persistence.studies.sqlite import CorruptedDatabaseError, SQLiteRepository
from fbf.core.persistence.studies.sqlite.schema import SCHEMA_VERSION


def _table_columns(db_path: Path) -> dict[str, set[str]]:
    conn = sqlite3.connect(str(db_path))
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        return {
            table: {
                row[1]
                for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            for table in tables
        }
    finally:
        conn.close()


def _schema_version(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        assert row is not None
        return int(row[0])
    finally:
        conn.close()


def _make_v5_database(db_path: Path) -> None:
    SQLiteRepository(str(db_path))
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("ALTER TABLE planned_units DROP COLUMN horizon_months")
        conn.execute("ALTER TABLE planned_units DROP COLUMN dataset_start_date")
        conn.execute("DELETE FROM schema_version")
        conn.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (5, ?)",
            ("2024-01-01T00:00:00Z",),
        )
        conn.commit()
    finally:
        conn.close()


def test_v5_database_is_rejected(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_v5.db"
    _make_v5_database(db_path)
    assert _schema_version(db_path) == 5

    with pytest.raises(CorruptedDatabaseError, match="version 5"):
        SQLiteRepository(str(db_path))


def test_database_without_schema_version_is_rejected(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_unversioned.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE experiments (experiment_id TEXT PRIMARY KEY)")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(CorruptedDatabaseError, match="missing schema_version"):
        SQLiteRepository(str(db_path))


def test_fresh_database_initializes_current_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.db"
    assert not db_path.exists()

    SQLiteRepository(str(db_path))

    columns = _table_columns(db_path)
    assert "dataset_start_date" in columns["planned_units"]
    assert "horizon_months" in columns["planned_units"]
    assert _schema_version(db_path) == SCHEMA_VERSION


def test_current_schema_reopens_idempotently(tmp_path: Path) -> None:
    db_path = tmp_path / "current.db"
    SQLiteRepository(str(db_path))
    before = (_table_columns(db_path), _schema_version(db_path))

    for _ in range(3):
        SQLiteRepository(str(db_path))

    after = (_table_columns(db_path), _schema_version(db_path))
    assert after == before
