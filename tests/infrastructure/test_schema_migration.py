"""Migration regression tests for legacy (v1) SQLite databases.

Schema version 2 adds the ``deleted_at`` soft-delete columns on ``experiments``
and ``research_plans`` together with the ``idx_experiments_deleted`` and
``idx_plans_deleted`` indexes. A v1 database created by the original persistence
layer lacks all of these.

These tests construct an *isolated* legacy v1 database (never touching
``~/.sim-retire/``), open it through the current persistence layer, and verify:

- migrations execute on open without error;
- the migrated schema matches the current schema;
- the deleted-at indexes can be created after migration;
- existing v1 records remain readable;
- subsequent persistence operations work correctly;
- migration is idempotent across repeated opens;
- a brand-new (empty) database initializes correctly without legacy migration.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fbf.core.persistence.studies.sqlite.schema import SCHEMA_VERSION
from fbf.core.persistence.studies.sqlite.sqlite_repository import (
    ExperimentIdentity,
    SQLiteRepository,
)
from tests.infrastructure.test_sqlite_persistence import (
    get_dummy_context,
    make_experiment,
    make_plan,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _table_columns(db_path: Path) -> dict[str, set[str]]:
    """Return {table -> set(column)} for every user table in the database."""
    conn = sqlite3.connect(str(db_path))
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
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


def _indexes(db_path: Path) -> dict[str, str]:
    """Return {index_name -> index_sql} for all explicitly created indexes."""
    conn = sqlite3.connect(str(db_path))
    try:
        return {
            row[0]: row[2]
            for row in conn.execute(
                "SELECT name, tbl_name, sql FROM sqlite_master "
                "WHERE type='index' AND sql IS NOT NULL"
            ).fetchall()
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


def _make_v1_database(db_path: Path) -> tuple[str, str]:
    """Create a realistic database populated through the real write path, then
    demote it to v1 format: drop the soft-delete columns and indexes and record
    schema version 1. The returned values are the persisted experiment/plan ids.
    """
    ctx = get_dummy_context()
    repo = SQLiteRepository(str(db_path))
    experiment = make_experiment("Legacy Study")
    exp_id = repo.save_experiment(
        ExperimentIdentity(name="Legacy Study", revision="v1"), experiment, ctx
    )
    plan = make_plan(3)
    plan_id = repo.save_plan(plan, exp_id, ctx)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("DROP INDEX IF EXISTS idx_experiments_deleted")
        conn.execute("DROP INDEX IF EXISTS idx_plans_deleted")
        conn.execute("ALTER TABLE experiments DROP COLUMN deleted_at")
        conn.execute("ALTER TABLE research_plans DROP COLUMN deleted_at")
        conn.execute("DELETE FROM schema_version")
        conn.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (1, ?)",
            ("2024-01-01T00:00:00Z",),
        )
        conn.commit()
    finally:
        conn.close()
    return exp_id, plan_id


def _assert_current_schema(db_path: Path) -> None:
    """Assert the schema at ``db_path`` matches the current (v2) schema."""
    columns = _table_columns(db_path)
    assert "deleted_at" in columns["experiments"]
    assert "deleted_at" in columns["research_plans"]

    indexes = _indexes(db_path)
    assert "idx_experiments_deleted" in indexes
    assert "idx_plans_deleted" in indexes
    # No duplicate indexes (sqlite_master stores exactly one row per index).
    assert list(indexes).count("idx_experiments_deleted") == 1
    assert list(indexes).count("idx_plans_deleted") == 1

    assert _schema_version(db_path) == SCHEMA_VERSION


# ---------------------------------------------------------------------------
# v1 -> current migration
# ---------------------------------------------------------------------------


def test_legacy_v1_database_migrates_on_open(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_v1.db"
    exp_id, plan_id = _make_v1_database(db_path)

    # Sanity: the fixture really is v1 format (no soft-delete columns).
    columns = _table_columns(db_path)
    assert "deleted_at" not in columns["experiments"]
    assert "deleted_at" not in columns["research_plans"]
    assert _schema_version(db_path) == 1

    # Opening through the current persistence layer must run the migration.
    ctx = get_dummy_context()
    repo = SQLiteRepository(str(db_path))
    _assert_current_schema(db_path)

    # Existing v1 records remain readable after migration.
    loaded = repo.load_experiment(exp_id, ctx)
    assert loaded.name == "Legacy Study"
    loaded_plan = repo.load_plan(plan_id, ctx)
    assert len(loaded_plan.units) == 3
    listed = repo.list_experiments()
    assert any(row["experiment_id"] == exp_id for row in listed)

    # Subsequent persistence operations work correctly after migration.
    second_id = repo.save_experiment(
        ExperimentIdentity(name="Post Migration", revision="v1"),
        make_experiment("Post Migration"),
        ctx,
    )
    assert second_id != exp_id
    assert repo.load_experiment(second_id, ctx).name == "Post Migration"

    new_plan_id = repo.save_plan(make_plan(2), second_id, ctx)
    assert len(repo.load_plan(new_plan_id, ctx).units) == 2


# ---------------------------------------------------------------------------
# Migration idempotency
# ---------------------------------------------------------------------------


def test_migration_is_idempotent_across_repeated_opens(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_v1_idempotent.db"
    exp_id, plan_id = _make_v1_database(db_path)

    ctx = get_dummy_context()
    SQLiteRepository(str(db_path))
    _assert_current_schema(db_path)
    schema_after_first = (_table_columns(db_path), _indexes(db_path))

    # Reopen several times (migration must be a no-op and must not duplicate
    # indexes or corrupt records).
    for _ in range(3):
        repo = SQLiteRepository(str(db_path))
        _assert_current_schema(db_path)

    schema_after_repeated = (_table_columns(db_path), _indexes(db_path))
    assert schema_after_repeated == schema_after_first
    assert _schema_version(db_path) == SCHEMA_VERSION

    # Existing records still intact after repeated migrations.
    assert repo.load_experiment(exp_id, ctx).name == "Legacy Study"
    assert len(repo.load_plan(plan_id, ctx).units) == 3


# ---------------------------------------------------------------------------
# Fresh / empty database
# ---------------------------------------------------------------------------


def test_fresh_database_initializes_current_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.db"
    assert not db_path.exists()

    repo = SQLiteRepository(str(db_path))
    _assert_current_schema(db_path)

    # Fresh database supports normal persistence immediately.
    ctx = get_dummy_context()
    exp_id = repo.save_experiment(
        ExperimentIdentity(name="Fresh Start", revision="v1"),
        make_experiment("Fresh Start"),
        ctx,
    )
    assert repo.load_experiment(exp_id, ctx).name == "Fresh Start"

    # Reopening a fresh database is also idempotent.
    schema_before = (_table_columns(db_path), _indexes(db_path))
    SQLiteRepository(str(db_path))
    assert (_table_columns(db_path), _indexes(db_path)) == schema_before
