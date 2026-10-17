"""Regression tests for the no-codec allocation-policy serialization fallback.

The production persistence context always registers ``AllocationPolicyCodec``,
but the repository also exposes a fallback that serializes a policy directly
when no codec matches. That fallback must not write an explicit multi-asset
policy's ``equity_allocation=None`` as the string ``"None"``.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from fbf.core.domain.policies import ConstantAllocationPolicy
from fbf.core.persistence.studies.sqlite import SQLiteRepository
from fbf.core.persistence.studies.sqlite.sqlite_repository import (
    PersistenceReconstructionContext,
    PolicyKind,
    _fallback_allocation_params,
    _serialize_policy,
)

_EXPLICIT = ConstantAllocationPolicy(
    allocations={
        "equity": Decimal("0.5"),
        "bond": Decimal("0.3"),
        "gold": Decimal("0.2"),
    }
)
_EXPLICIT_PARAMS = {"allocations": {"bond": "0.3", "equity": "0.5", "gold": "0.2"}}


def _no_codec_context() -> PersistenceReconstructionContext:
    """A context with no registered policy codecs (forces the fallback)."""
    return PersistenceReconstructionContext(
        dataset_loader=cast(Any, object()),
        policy_codecs={},
        simulation_result_codec=cast(Any, object()),
    )


class TestFallbackAllocationParams:
    def test_explicit_tuple_allocations(self) -> None:
        assert _fallback_allocation_params(_EXPLICIT) == _EXPLICIT_PARAMS

    def test_explicit_mapping_allocations(self) -> None:
        class _Policy:
            allocations = {"equity": "0.6", "bond": "0.4"}
            equity_allocation = None

        assert _fallback_allocation_params(_Policy()) == {
            "allocations": {"equity": "0.6", "bond": "0.4"}
        }

    def test_legacy_scalar(self) -> None:
        legacy = ConstantAllocationPolicy(Decimal("0.7"))
        assert _fallback_allocation_params(legacy) == {"equity_allocation": "0.7"}

    def test_missing_attributes_defaults(self) -> None:
        class _Policy:
            pass

        assert _fallback_allocation_params(_Policy()) == {
            "equity_allocation": "1.0"
        }


class TestSerializePolicyWithoutCodec:
    def test_explicit_never_emits_none(self) -> None:
        policy_type, params = _serialize_policy(
            _EXPLICIT, PolicyKind.ALLOCATION, _no_codec_context()
        )
        assert policy_type == "AllocationPolicy"
        assert params == _EXPLICIT_PARAMS
        assert "equity_allocation" not in params

    def test_legacy_emits_equity_allocation(self) -> None:
        policy_type, params = _serialize_policy(
            ConstantAllocationPolicy(Decimal("0.7")),
            PolicyKind.ALLOCATION,
            _no_codec_context(),
        )
        assert policy_type == "AllocationPolicy"
        assert params == {"equity_allocation": "0.7"}


def _insert_experiment(conn: sqlite3.Connection) -> str:
    experiment_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO experiments (experiment_id, name, revision, description, "
        "dataset_identifier, horizon_months, initial_wealth, "
        "initial_wealth_currency, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            experiment_id, "fallback-test", "v1", "fallback serialization",
            "test", 721, "1000000", "EUR", "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z",
        ),
    )
    return experiment_id


class TestSavePolicyFallbackPersistence:
    def _save(self, tmp_path: Path, policy: Any) -> tuple[str, dict[str, Any]]:
        repo = SQLiteRepository(str(tmp_path / "fallback.db"))
        with sqlite3.connect(repo.db_path) as conn:
            experiment_id = _insert_experiment(conn)
            policy_id = repo._save_policy(
                conn, policy, PolicyKind.ALLOCATION, experiment_id, 0,
                _no_codec_context(),
            )
            row = conn.execute(
                "SELECT policy_type, params_json FROM policies WHERE policy_id = ?",
                (policy_id,),
            ).fetchone()
            conn.commit()
        return row[0], json.loads(row[1])

    def test_explicit_persisted_as_allocations(self, tmp_path: Path) -> None:
        policy_type, params = self._save(tmp_path, _EXPLICIT)
        assert policy_type == "AllocationPolicy"
        assert params == _EXPLICIT_PARAMS
        assert "equity_allocation" not in params

    def test_legacy_persisted_unchanged(self, tmp_path: Path) -> None:
        policy_type, params = self._save(
            tmp_path, ConstantAllocationPolicy(Decimal("0.7"))
        )
        assert policy_type == "AllocationPolicy"
        assert params == {"equity_allocation": "0.7"}
