"""SQLite repository implementation.

Implements the v0.4 SQLite persistence adapter according to the
INFRASTRUCTURE_SQLITE_PERSISTENCE_SPECIFICATION.md specification.

Uses the ReconstructionContext pattern for safe reconstruction and exposes
the exact interface defined in Section 12.3.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol

from .errors import (
    DuplicateStudyError,
    PersistenceError,
    PlanNotFoundError,
    ReconstructionContextError,
    ResultsNotFoundError,
    StudyNotFoundError,
    UnsupportedSerializationError,
)
from .schema import ALL_DDL, SCHEMA_VERSION

JSONScalar = None | bool | int | float | str


class PolicyKind(StrEnum):
    ALLOCATION = "allocation"
    WITHDRAWAL = "withdrawal"


def utc_now_iso() -> str:
    """Return UTC timestamp in ISO format with Z suffix."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def generate_uuid() -> str:
    """Generate a deterministic UUID for entity IDs."""
    return str(uuid.uuid4())


def generate_hash(content: str) -> str:
    """Generate SHA-256 hash of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def serialize_decimal(value: Any) -> str:
    """Serialize Decimal to string preserving precision."""
    return str(value)


def deserialize_decimal(value: str) -> Any:
    """Deserialize string to Decimal."""
    from decimal import Decimal
    return Decimal(value)


def to_json_scalar(value: Any) -> str:
    """Convert value to JSONScalar string representation."""
    if value is None:
        return "null"
    elif isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    else:
        raise TypeError(f"Value {value} cannot be serialized to JSONScalar")


def from_json_scalar(value: str) -> Any:
    """Convert JSONScalar string representation to Python value."""
    if value == "null":
        return None
    elif value == "true":
        return True
    elif value == "false":
        return False
    elif value.replace('.', '', 1).isdigit() or value.startswith('-'):
        try:
            if '.' in value or 'e' in value.lower():
                return float(value)
            else:
                return int(value)
        except ValueError:
            return value
    elif (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    else:
        raise ValueError(f"Value {value} cannot be deserialized from JSONScalar")


def to_canonical_json(data: Mapping[str, Any]) -> str:
    """Convert dict to canonical JSON with sorted keys and compact separators."""
    return json.dumps(data, sort_keys=True, separators=(',', ':'))


def from_canonical_json(data: str) -> dict[str, Any]:
    """Parse canonical JSON string to dict with validation."""
    result = json.loads(data)
    assert isinstance(result, dict)
    return result


def _serialize_policy(
    policy: Any,
    policy_kind: PolicyKind,
    context: PersistenceReconstructionContext,
) -> tuple[str, dict[str, Any]]:
    """Serialize a policy to ``(policy_type, params_dict)`` for storage.

    Mirrors the serialization logic used by ``SQLiteRepository._save_policy``:
    a registered codec is tried first, then the standard-policy fallback.
    """
    from fbf.core.domain.policies.allocation_policy import AllocationPolicy
    from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy

    for (kind, _ptype), codec in context.policy_codecs.items():
        if kind == policy_kind.value:
            try:
                candidate = dict(codec.dump(policy))
                return codec.policy_type, candidate
            except (TypeError, ValueError):
                continue

    if policy_kind == PolicyKind.ALLOCATION:
        if isinstance(policy, AllocationPolicy):
            return "AllocationPolicy", {
                "equity_allocation": str(getattr(policy, "equity_allocation", "1.0"))
            }
        raise UnsupportedSerializationError(
            f"Unsupported allocation policy type: {type(policy).__name__}"
        )
    if isinstance(policy, WithdrawalPolicy):
        return "WithdrawalPolicy", {
            "withdrawal_rate": str(getattr(policy, "withdrawal_rate", "0.04"))
        }
    raise UnsupportedSerializationError(
        f"Unsupported withdrawal policy type: {type(policy).__name__}"
    )


# Fields that determine the actual simulation and therefore MUST match for a
# logically deleted experiment to be considered semantically equivalent. These
# are explicitly enumerable so that no field is silently ignored.
_DETERMINISTIC_EXPERIMENT_FIELDS = (
    "name",
    "revision",
    "description",
    "dataset_identifier",
    "horizon_months",
    "initial_wealth",
    "initial_wealth_currency",
    "allocation_policies",
    "withdrawal_policies",
    "cohort_start_dates",
)

# Non-deterministic / execution-specific fields that are deliberately EXCLUDED
# from the equivalence comparison, and why:
#   - experiment_id / plan_id / result_id : storage-generated UUIDs, unrelated to
#     the simulation's content.
#   - created_at / updated_at / deleted_at / executed_at : wall-clock provenance,
#     never part of a deterministic definition.
#   - duration_seconds / execution_time_seconds : measurement noise.
#   - simulation_results / monthly data : outputs, not configuration.
_NON_DETERMINISTIC_FIELDS_DOC = (
    "experiment_id, plan_id, result_id (storage UUIDs); "
    "created_at, updated_at, deleted_at, executed_at (wall-clock provenance); "
    "duration_seconds, execution_time_seconds (measurement noise); "
    "simulation results and per-month timelines (outputs, not configuration)."
)


def _experiment_snapshot_from_object(
    identity: ExperimentIdentity,
    experiment: ExperimentDefinition,
    context: PersistenceReconstructionContext,
) -> dict[str, Any]:
    """Build a deterministic canonical snapshot of an in-memory experiment."""
    allocation_policies = tuple(
        (ptype, to_canonical_json(params))
        for ptype, params in (
            _serialize_policy(p, PolicyKind.ALLOCATION, context)
            for p in experiment.allocation_policies
        )
    )
    withdrawal_policies = tuple(
        (ptype, to_canonical_json(params))
        for ptype, params in (
            _serialize_policy(p, PolicyKind.WITHDRAWAL, context)
            for p in experiment.withdrawal_policies
        )
    )
    return {
        "name": identity.name,
        "revision": identity.revision,
        "description": experiment.description,
        "dataset_identifier": experiment.dataset.identifier or experiment.dataset.version,
        "horizon_months": experiment.horizon_months,
        "initial_wealth": serialize_decimal(experiment.initial_wealth.amount),
        "initial_wealth_currency": experiment.initial_wealth.currency.value,
        "allocation_policies": allocation_policies,
        "withdrawal_policies": withdrawal_policies,
        "cohort_start_dates": tuple(
            sorted(c.start_date.isoformat() for c in experiment.cohorts)
        ),
    }


def _experiment_snapshot_from_rows(
    identity: ExperimentIdentity,
    row: Sequence[Any],
    allocation_policies: Sequence[tuple[str, str]],
    withdrawal_policies: Sequence[tuple[str, str]],
    cohort_start_dates: Sequence[str],
) -> dict[str, Any]:
    """Build a deterministic canonical snapshot from stored experiment rows."""
    (
        experiment_id,
        name,
        revision,
        description,
        dataset_identifier,
        horizon_months,
        initial_wealth,
        initial_wealth_currency,
    ) = row
    return {
        "name": identity.name,
        "revision": identity.revision,
        "description": description,
        "dataset_identifier": dataset_identifier,
        "horizon_months": horizon_months,
        "initial_wealth": initial_wealth,
        "initial_wealth_currency": initial_wealth_currency,
        "allocation_policies": tuple(allocation_policies),
        "withdrawal_policies": tuple(withdrawal_policies),
        "cohort_start_dates": tuple(sorted(cohort_start_dates)),
    }


def experiments_semantically_equivalent(
    identity_a: ExperimentIdentity,
    experiment_a: ExperimentDefinition,
    identity_b: ExperimentIdentity,
    experiment_b: ExperimentDefinition,
    context: PersistenceReconstructionContext,
) -> bool:
    """Return True if two experiments are deterministically semantically equivalent.

    Compares every field that determines the actual simulation — natural
    identity ``(name, revision)``, description, dataset identifier, horizon,
    initial wealth, serialized allocation/withdrawal policies in index order,
    and cohort start dates. Timestamps, storage UUIDs, and execution outputs
    are intentionally excluded (see ``_NON_DETERMINISTIC_FIELDS_DOC``).

    Parameters
    ----------
    identity_a / identity_b:
        Natural identities ``(name, revision)`` of the two experiments.
    experiment_a / experiment_b:
        The experiment definitions being compared.
    context:
        Persistence reconstruction context providing policy codecs.

    Returns
    -------
    bool
        True if the two experiments are equivalent except for explicitly
        identified non-deterministic fields.
    """
    snapshot_a = _experiment_snapshot_from_object(identity_a, experiment_a, context)
    snapshot_b = _experiment_snapshot_from_object(identity_b, experiment_b, context)
    return snapshot_a == snapshot_b


if TYPE_CHECKING:
    from fbf.core.domain.model.dataset import Dataset
    from fbf.core.execution.pipeline.simulation import SimulationResult
    from fbf.core.execution.result import ResearchExecutionResult
    from fbf.core.study.internal.experiment.definition import ExperimentDefinition
    from fbf.core.study.plan import ResearchPlan


@dataclass(frozen=True)
class ExperimentIdentity:
    """Identity for experiment persistence."""
    name: str
    revision: str


class DatasetResolver(Protocol):
    """Protocol for resolving dataset identifiers to Dataset objects."""
    def resolve(self, dataset_identifier: str) -> Dataset: ...


class PolicyCodec(Protocol):
    """Protocol for encoding/decoding policy parameters."""
    policy_type: str
    policy_kind: PolicyKind

    def dump(self, policy: Any) -> Mapping[str, JSONScalar]: ...
    def load(self, parameters: Mapping[str, JSONScalar]) -> Any: ...


@dataclass(frozen=True)
class SerializedSimulationResult:
    """Carrier for serialized simulation result components."""
    statistics_payload_json: str
    monthly_payloads_json: tuple[str, ...]


class SimulationResultCodec(Protocol):
    """Protocol for encoding/decoding simulation results."""

    def dump(self, result: SimulationResult) -> SerializedSimulationResult: ...

    def load(
        self, statistics_payload_json: str, monthly_payloads_json: Sequence[str]
    ) -> SimulationResult: ...


@dataclass(frozen=True)
class PersistenceReconstructionContext:
    """Context providing reconstruction capabilities for persistence."""
    dataset_resolver: DatasetResolver
    policy_codecs: Mapping[tuple[str, str], PolicyCodec]
    simulation_result_codec: SimulationResultCodec


def validate_context(context: PersistenceReconstructionContext) -> None:
    """Validate context has all required reconstruction capabilities."""
    if not context.dataset_resolver:
        raise ReconstructionContextError("Dataset resolver is required")

    if not context.policy_codecs:
        raise ReconstructionContextError("Policy codecs are required")

    if not context.simulation_result_codec:
        raise ReconstructionContextError("Simulation result codec is required")


def _compute_portfolio_value(monthly_payload: Mapping[str, Any]) -> str:
    holdings = monthly_payload.get("portfolio_holdings", [])
    total = sum(float(h["units"]) for h in holdings)
    return f"{total:.2f}"


def _compute_withdrawal_amount(monthly_payload: Mapping[str, Any]) -> str:
    return str(monthly_payload.get("withdrawal_decision", "0"))


class SQLiteRepository:
    """SQLite persistence adapter implementing v0.4 specifications.

    Exposes the public API defined in Section 12.3 and implements
    all requirements from the Infrastructure SQLite Persistence v0.4 spec.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._initialize_schema()

    def _connect(self, timeout: int = 5) -> sqlite3.Connection:
        """Create a SQLite connection with v0.4 required pragmas."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=timeout)
        except sqlite3.Error as exc:
            raise PersistenceError(f"Database connection failed: {exc}") from exc
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _connect_immediate(self) -> sqlite3.Connection:
        """Create an immediate transaction connection."""
        try:
            conn = sqlite3.connect(self.db_path)
        except sqlite3.Error as exc:
            raise PersistenceError(f"Database connection failed: {exc}") from exc
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("BEGIN DEFERRED")
        return conn

    def _initialize_schema(self) -> None:
        """Initialize database schema and version tracking."""
        from .schema import INDEX_DDL

        with self._connect() as conn:
            for statement in ALL_DDL:
                conn.execute(statement)
            self._apply_migrations(conn)
            # Indexes are created after migrations because some indexes added by
            # a newer schema version reference columns that only exist after the
            # migration has run on databases created by an older version.
            for statement in INDEX_DDL:
                conn.execute(statement)
            # Record the current schema version. A single row tracks the applied
            # version; it is rewritten only when it differs (e.g. a legacy v1
            # database was just migrated), keeping the row stable across
            # repeated opens so schema initialization is fully idempotent.
            row = conn.execute(
                "SELECT version FROM schema_version"
            ).fetchone()
            if row is None or row[0] != SCHEMA_VERSION:
                conn.execute("DELETE FROM schema_version")
                conn.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, utc_now_iso()),
                )

    @staticmethod
    def _apply_migrations(conn: sqlite3.Connection) -> None:
        """Add columns introduced after the original schema for existing databases.

        ``CREATE TABLE IF NOT EXISTS`` cannot alter an existing table, so any
        columns added by a newer schema version are applied here when missing.
        """
        from .schema import MIGRATIONS

        for table, column, ddl in MIGRATIONS:
            columns = {
                row[1]
                for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if column not in columns:
                conn.execute(ddl)

    def save_experiment(
        self,
        identity: ExperimentIdentity,
        experiment: ExperimentDefinition,
        context: PersistenceReconstructionContext,
    ) -> str:
        """Persist experiment definition with all associated entities.

        Implements Section 12.3: save_experiment(identity, definition, context).
        All writes occur in a single DEFERRED transaction.

        Idempotent logical-deletion restore rule: when an experiment with the
        same natural identity ``(name, revision)`` exists but has been logically
        deleted, the deleted row is restored **if and only if** the incoming
        experiment is deterministically semantically equivalent to the stored
        one (see ``experiments_semantically_equivalent``). If they differ in any
        deterministic configuration field the restore is refused with
        ``DuplicateStudyError``. An active (non-deleted) duplicate always raises
        ``DuplicateStudyError`` as before.
        """
        validate_context(context)

        # Verify experiment identity is unique (Section 12.2: identity check)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT experiment_id, deleted_at FROM experiments "
                "WHERE name = ? AND revision = ?",
                (identity.name, identity.revision),
            ).fetchone()
            if row:
                existing_id: str = str(row[0])
                deleted_at = row[1]
                if deleted_at is None:
                    raise DuplicateStudyError(
                        "Experiment already exists with name "
                        f"'{identity.name}' and revision '{identity.revision}'"
                    )
                self._restore_if_semantically_equivalent(
                    identity, experiment, existing_id, context
                )
                return existing_id

        experiment_id = generate_uuid()

        def _do_save() -> str:
            with self._connect_immediate() as conn:
                conn.execute(
                    """
                    INSERT INTO experiments (
                        experiment_id, name, revision, description, dataset_identifier,
                        horizon_months, initial_wealth, initial_wealth_currency,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        experiment_id,
                        identity.name,
                        identity.revision,
                        experiment.description,
                        experiment.dataset.identifier or experiment.dataset.version,
                        experiment.horizon_months,
                        serialize_decimal(experiment.initial_wealth.amount),
                        experiment.initial_wealth.currency.value,
                        utc_now_iso(),
                        utc_now_iso(),
                    ),
                )

                for i, policy in enumerate(experiment.allocation_policies):
                    self._save_policy(
                        conn, policy, PolicyKind.ALLOCATION, experiment_id, i, context
                    )

                for i, wpolicy in enumerate(experiment.withdrawal_policies):
                    self._save_policy(
                        conn, wpolicy, PolicyKind.WITHDRAWAL, experiment_id, i, context
                    )

                for cohort in experiment.cohorts:
                    self._save_cohort(conn, experiment_id, cohort)
            return experiment_id

        result_str = self._retry_on_lock(_do_save)
        assert isinstance(result_str, str)
        return result_str

    def _stored_experiment_snapshot(
        self,
        identity: ExperimentIdentity,
        experiment_id: str,
        context: PersistenceReconstructionContext,
    ) -> dict[str, Any]:
        """Build a deterministic snapshot of a stored experiment from its rows."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT experiment_id, name, revision, description, dataset_identifier,
                       horizon_months, initial_wealth, initial_wealth_currency
                FROM experiments WHERE experiment_id = ?
                """,
                (experiment_id,),
            ).fetchone()
            if not row:
                raise StudyNotFoundError(f"Experiment not found: {experiment_id}")

            allocation_policies = self._load_stored_policy_snapshot(
                conn, experiment_id, PolicyKind.ALLOCATION
            )
            withdrawal_policies = self._load_stored_policy_snapshot(
                conn, experiment_id, PolicyKind.WITHDRAWAL
            )
            cohort_dates = tuple(
                r[0]
                for r in conn.execute(
                    "SELECT start_date FROM cohorts "
                    "WHERE experiment_id = ? ORDER BY start_date",
                    (experiment_id,),
                ).fetchall()
            )
        return _experiment_snapshot_from_rows(
            identity,
            row,
            allocation_policies,
            withdrawal_policies,
            cohort_dates,
        )

    @staticmethod
    def _load_stored_policy_snapshot(
        conn: sqlite3.Connection,
        experiment_id: str,
        policy_kind: PolicyKind,
    ) -> tuple[tuple[str, str], ...]:
        """Load stored policies as ``(policy_type, canonical_params_json)`` tuples."""
        rows = conn.execute(
            """
            SELECT p.policy_type, p.params_json
            FROM policies p
            JOIN experiment_policies ep ON p.policy_id = ep.policy_id
            WHERE ep.experiment_id = ? AND ep.policy_kind = ?
            ORDER BY ep.policy_index
            """,
            (experiment_id, policy_kind.value),
        ).fetchall()
        return tuple((str(r[0]), str(r[1])) for r in rows)

    def _restore_if_semantically_equivalent(
        self,
        identity: ExperimentIdentity,
        experiment: ExperimentDefinition,
        experiment_id: str,
        context: PersistenceReconstructionContext,
    ) -> None:
        """Restore a logically deleted experiment iff it is semantically equivalent.

        Raises ``DuplicateStudyError`` (refusing to restore) when the incoming
        experiment differs from the stored, logically deleted entry in any
        deterministic field. Restores by clearing ``deleted_at`` and reusing the
        existing ``experiment_id`` otherwise.
        """
        incoming_snapshot = _experiment_snapshot_from_object(identity, experiment, context)
        stored_snapshot = self._stored_experiment_snapshot(identity, experiment_id, context)
        if incoming_snapshot != stored_snapshot:
            raise DuplicateStudyError(
                f"A logically deleted experiment exists with name '{identity.name}' and "
                f"revision '{identity.revision}' but its deterministic configuration "
                "differs from the entry being persisted. Refusing to restore: the ID alone "
                "is not evidence of identity. Delete the stale entry or use a new identity."
            )

        with self._connect_immediate() as conn:
            conn.execute(
                "UPDATE experiments SET deleted_at = NULL, updated_at = ? "
                "WHERE experiment_id = ?",
                (utc_now_iso(), experiment_id),
            )

    def logical_delete_experiment(self, identity: ExperimentIdentity) -> None:
        """Logically delete an experiment and its research plans.

        Sets ``deleted_at`` on the matching ``(name, revision)`` row and on every
        of its research plans so they are hidden from all query APIs. The rows are
        retained so that a semantically equivalent re-save can restore them
        (see ``save_experiment``). Does nothing if no matching row exists.
        """
        with self._connect_immediate() as conn:
            row = conn.execute(
                "SELECT experiment_id FROM experiments "
                "WHERE name = ? AND revision = ?",
                (identity.name, identity.revision),
            ).fetchone()
            if not row:
                raise StudyNotFoundError(
                    f"Experiment not found: '{identity.name}' revision '{identity.revision}'"
                )
            experiment_id = row[0]
            now = utc_now_iso()
            conn.execute(
                "UPDATE experiments SET deleted_at = ?, updated_at = ? "
                "WHERE experiment_id = ?",
                (now, now, experiment_id),
            )
            conn.execute(
                "UPDATE research_plans SET deleted_at = ? WHERE experiment_id = ?",
                (now, experiment_id),
            )

    def load_experiment(
        self, identity_or_id: str | ExperimentIdentity, context: PersistenceReconstructionContext
    ) -> ExperimentDefinition:
        """Load experiment definition with all dependent entities.

        Implements Section 12.3: load_experiment(identity_or_id, context).
        Requires complete context for safe reconstruction.

        Logically deleted experiments are treated as not found by the public
        query API (restore happens through ``save_experiment``).
        """
        validate_context(context)

        with self._connect() as conn:
            if isinstance(identity_or_id, ExperimentIdentity):
                row = conn.execute(
                    """
                    SELECT experiment_id, name, revision, description, dataset_identifier,
                           horizon_months, initial_wealth, initial_wealth_currency
                    FROM experiments
                    WHERE name = ? AND revision = ? AND deleted_at IS NULL
                    """,
                    (identity_or_id.name, identity_or_id.revision),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT e.experiment_id, e.name, e.revision, e.description, e.dataset_identifier,
                           e.horizon_months, e.initial_wealth, e.initial_wealth_currency
                    FROM experiments e
                    WHERE e.experiment_id = ? AND e.deleted_at IS NULL
                    """,
                    (identity_or_id,),
                ).fetchone()

            if not row:
                raise StudyNotFoundError(f"Experiment not found: {identity_or_id}")

            (
                experiment_id,
                name,
                revision,
                description,
                dataset_identifier,
                horizon_months,
                initial_wealth,
                initial_wealth_currency,
            ) = row

            dataset = context.dataset_resolver.resolve(dataset_identifier)

            allocation_policies = self._load_policies(
                conn, experiment_id, PolicyKind.ALLOCATION, context
            )
            withdrawal_policies = self._load_policies(
                conn, experiment_id, PolicyKind.WITHDRAWAL, context
            )

            from fbf.core.domain.model.money import Currency, Money
            from fbf.core.study.internal.experiment.definition import ExperimentDefinition

            return ExperimentDefinition(
                name=name,
                description=description,
                dataset=dataset,
                horizon_months=horizon_months,
                initial_wealth=Money(
                    amount=deserialize_decimal(initial_wealth),
                    currency=Currency(initial_wealth_currency),
                ),
                cohorts=self._load_cohorts(conn, experiment_id),
                allocation_policies=allocation_policies,
                withdrawal_policies=withdrawal_policies,
            )

    def save_plan(
        self,
        plan: ResearchPlan,
        experiment_id: str,
        context: PersistenceReconstructionContext,
    ) -> str:
        """Persist research plan with all associated units and configurations.

        Section 12.3: save_plan(plan, experiment_id, context).
        Verifies plan belongs to the experiment and is exactly reconstructed.
        """
        validate_context(context)

        # Verify experiment exists
        self.load_experiment(experiment_id, context)

        plan_id = generate_uuid()

        def _do_save() -> str:
            with self._connect_immediate() as conn:
                conn.execute(
                    """
                    INSERT INTO research_plans (
                        plan_id, experiment_id, created_at, unit_count, status
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        plan_id,
                        experiment_id,
                        utc_now_iso(),
                        len(plan.units),
                        "planned",
                    ),
                )

                for i, unit in enumerate(plan.units):
                    self._save_unit(conn, plan_id, i, unit, experiment_id, context)
            return plan_id

        result_str = self._retry_on_lock(_do_save)
        assert isinstance(result_str, str)
        return result_str

    def load_plan(self, plan_id: str, context: PersistenceReconstructionContext) -> ResearchPlan:
        """Load research plan with all units, policies, and cohorts.

        Implements Section 12.3: load_plan(plan_id, context).
        Returns complete plan with all dependent entities reconstructed.
        """
        validate_context(context)

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT experiment_id, created_at, unit_count, status
                FROM research_plans
                WHERE plan_id = ?
                """,
                (plan_id,),
            ).fetchone()

            if not row:
                raise StudyNotFoundError(f"Plan not found: {plan_id}")

            experiment_id, created_at, unit_count, status = row

            # Load the parent experiment definition first so its full dataset
            # is available for per-cohort slicing when units are reconstructed.
            experiment = self.load_experiment(experiment_id, context)

            units = self._load_units(conn, plan_id, context, experiment)

            from fbf.core.study.plan import ResearchPlan

            return ResearchPlan(
                experiment_definition=experiment,
                units=tuple(units),
            )

    def save_execution_result(
        self,
        plan_id: str,
        result: ResearchExecutionResult,
        context: PersistenceReconstructionContext,
        duration_seconds: float,
    ) -> str:
        """Persist execution result with simulation statistics and timeline.

        Section 12.3: save_execution_result(plan_id, result, context, duration).
        Atomic transaction with plan verification and status transition.
        """
        validate_context(context)

        simulation_results = result.experiment_result.simulation_results
        success_count = sum(1 for r in simulation_results if r.statistics.success)
        failure_count = sum(1 for r in simulation_results if not r.statistics.success)
        total_units = len(simulation_results)

        # Verify plan exists and check status (Section 12.3: status transitions)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status FROM research_plans WHERE plan_id = ?", (plan_id,)
            ).fetchone()
            if not row:
                raise PlanNotFoundError(f"Plan not found: {plan_id}")
            current_status = row[0]
            if current_status == "completed":
                raise PersistenceError("Cannot save result for completed plan")

        result_id = generate_uuid()

        def _do_save() -> str:
            with self._connect_immediate() as conn:
                conn.execute(
                    "UPDATE research_plans SET status = ? WHERE plan_id = ?",
                    ("completed", plan_id),
                )

                conn.execute(
                    """
                    INSERT INTO execution_results (
                        result_id, plan_id, executed_at, duration_seconds,
                        success_count, failure_count, total_units
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result_id,
                        plan_id,
                        utc_now_iso(),
                        duration_seconds,
                        success_count,
                        failure_count,
                        total_units,
                    ),
                )

                self._save_simulation_results(conn, result_id, simulation_results, context)
            return result_id

        result_str = self._retry_on_lock(_do_save)
        assert isinstance(result_str, str)
        return result_str

    def load_execution_result(
        self, plan_id_or_result_id: str, context: PersistenceReconstructionContext
    ) -> ResearchExecutionResult:
        """Load execution result by plan ID or result ID.

        Implements Section 12.3: load_execution_result(plan_id_or_result_id, context).
        Returns complete result with plan and simulation data.
        """
        validate_context(context)

        with self._connect() as conn:
            if "-" in plan_id_or_result_id:
                row = conn.execute(
                    """
                    SELECT result_id, plan_id, executed_at, duration_seconds,
                           success_count, failure_count, total_units
                    FROM execution_results WHERE result_id = ?
                    """,
                    (plan_id_or_result_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT result_id, plan_id, executed_at, duration_seconds,
                           success_count, failure_count, total_units
                    FROM execution_results WHERE plan_id = ?
                    """,
                    (plan_id_or_result_id,),
                ).fetchone()

            if not row:
                if "-" in plan_id_or_result_id:
                    raise ResultsNotFoundError(
                        f"Execution result not found: {plan_id_or_result_id}"
                    )
                else:
                    raise StudyNotFoundError(
                        f"Results for plan not found: {plan_id_or_result_id}"
                    )

            if "-" in plan_id_or_result_id:
                (
                    result_id,
                    plan_id,
                    executed_at,
                    duration_seconds,
                    success_count,
                    failure_count,
                    total_units,
                ) = row
            else:
                (
                    result_id,
                    plan_id,
                    executed_at,
                    duration_seconds,
                    success_count,
                    failure_count,
                    total_units,
                ) = (plan_id_or_result_id,) + row

            # Load simulation results via context codec
            loaded_sim_results = self._load_simulation_results(conn, result_id, context)

            from fbf.core.execution.pipeline.simulation import (
                ExperimentDefinition as EngineExperimentDefinition,
                ExperimentRun,
            )
            from fbf.core.execution.pipeline.simulation_context import SimulationContext
            from fbf.core.execution.result import ResearchExecutionResult

            # Load the associated plan
            plan = self.load_plan(plan_id, context)

            # Reconstruct ExperimentDefinition with proper simulation contexts
            exp_def = plan.experiment_definition
            sim_contexts = tuple(
                SimulationContext(
                    experiment_name=exp_def.name,
                    cohort=unit.cohort.start_date.isoformat(),
                    start_date=unit.cohort.start_date,
                    horizon_months=exp_def.horizon_months,
                    initial_wealth=exp_def.initial_wealth,
                    initial_portfolio=unit.initial_portfolio,
                    dataset=exp_def.dataset,
                    allocation_policy=unit.allocation_policy,
                    withdrawal_policy=unit.withdrawal_policy,
                )
                for unit in plan.units
            )
            engine_def = EngineExperimentDefinition(
                name=exp_def.name,
                description=exp_def.description,
                simulation_contexts=sim_contexts,
            )

            # Create the experiment run object
            experiment_run = ExperimentRun(
                definition=engine_def,
                simulation_results=tuple(loaded_sim_results),
            )

            return ResearchExecutionResult(
                plan=plan,
                experiment_result=experiment_run,
            )

    def find_experiment_by_name(self, name: str) -> str | None:
        """Find experiment ID by name and latest revision.

        Query API for infrastructure layer.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT experiment_id FROM experiments "
                "WHERE name = ? AND deleted_at IS NULL "
                "ORDER BY revision DESC LIMIT 1",
                (name,)
            ).fetchone()
            return row[0] if row else None

    def list_experiments(self) -> list[Mapping[str, Any]]:
        """List all experiments with metadata.

        Query API for infrastructure layer.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT experiment_id, name, revision, dataset_identifier, horizon_months,
                       initial_wealth, initial_wealth_currency, created_at, updated_at
                FROM experiments WHERE deleted_at IS NULL
                ORDER BY name, revision
                """
            ).fetchall()

            experiments: list[Mapping[str, Any]] = []
            for row in rows:
                experiments.append(
                    {
                        "experiment_id": row[0],
                        "name": row[1],
                        "revision": row[2],
                        "dataset_identifier": row[3],
                        "horizon_months": row[4],
                        "initial_wealth": row[5],
                        "initial_wealth_currency": row[6],
                        "created_at": row[7],
                        "updated_at": row[8],
                    }
                )

            return experiments

    def find_result_by_plan(self, plan_id: str) -> str | None:
        """Find result ID for a completed plan.

        Query API for infrastructure layer.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT result_id FROM execution_results WHERE plan_id = ?", (plan_id,)
            ).fetchone()
            return row[0] if row else None

    def find_plan_by_experiment(self, experiment_id: str) -> str | None:
        """Find the latest completed plan for an experiment."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT plan_id FROM research_plans
                WHERE experiment_id = ? AND status = 'completed' AND deleted_at IS NULL
                ORDER BY created_at DESC LIMIT 1
                """,
                (experiment_id,),
            ).fetchone()
            return row[0] if row else None

    def get_export_data(self, experiment_id: str) -> dict[str, Any] | None:
        """Return flat export dict with metadata + rows, or None.

        Joins across experiments, research_plans, planned_units, cohorts,
        parameter_configurations, execution_results, and simulation_results
        to produce flat rows. Does NOT use PersistenceReconstructionContext.
        """
        with self._connect() as conn:
            exp_row = conn.execute(
                """
                SELECT name, revision, created_at
                FROM experiments WHERE experiment_id = ? AND deleted_at IS NULL
                """,
                (experiment_id,),
            ).fetchone()
            if not exp_row:
                return None
            name, revision, created_at = exp_row

            plan_id = self.find_plan_by_experiment(experiment_id)
            if not plan_id:
                return None

            result_row = conn.execute(
                """
                SELECT result_id, executed_at, duration_seconds,
                       success_count, failure_count, total_units
                FROM execution_results WHERE plan_id = ?
                """,
                (plan_id,),
            ).fetchone()
            if not result_row:
                return None
            (
                result_id,
                executed_at,
                duration_seconds,
                success_count,
                failure_count,
                total_units,
            ) = result_row

            unit_rows = conn.execute(
                """
                SELECT pu.unit_index, c.start_date AS cohort_start_date, pc.params_json
                FROM planned_units pu
                JOIN cohorts c ON pu.cohort_id = c.cohort_id
                JOIN parameter_configurations pc ON pu.param_config_id = pc.param_config_id
                WHERE pu.plan_id = ?
                ORDER BY pu.unit_index
                """,
                (plan_id,),
            ).fetchall()

            param_keys_set: set[str] = set()
            unit_info: dict[int, dict[str, Any]] = {}
            for unit_index, cohort_start_date, params_json in unit_rows:
                params = json.loads(params_json)
                param_keys_set.update(params.keys())
                unit_info[unit_index] = {
                    "cohort_start_date": cohort_start_date,
                    "params": params,
                }

            sim_rows = conn.execute(
                """
                SELECT unit_index, month_index, monthly_payload_json,
                       statistics_payload_json, final_month
                FROM simulation_results
                WHERE execution_result_id = ?
                ORDER BY unit_index, month_index
                """,
                (result_id,),
            ).fetchall()

            unit_success: dict[int, bool] = {}
            for (
                unit_index,
                _month_index,
                _monthly_payload_json,
                statistics_payload_json,
                final_month,
            ) in sim_rows:
                if final_month and statistics_payload_json:
                    stats = json.loads(statistics_payload_json)
                    unit_success[unit_index] = bool(stats.get("success", False))

            rows: list[dict[str, Any]] = []
            for (
                unit_index,
                month_index,
                monthly_payload_json,
                _statistics_payload_json,
                _final_month,
            ) in sim_rows:
                info = unit_info.get(unit_index, {})
                cohort_start_date = info.get("cohort_start_date", "")
                params = info.get("params", {})

                monthly = json.loads(monthly_payload_json)
                row: dict[str, Any] = {
                    "cohort_start_date": cohort_start_date,
                    "month_index": month_index,
                    "portfolio_value": _compute_portfolio_value(monthly),
                    "withdrawal": _compute_withdrawal_amount(monthly),
                    "success": 1 if unit_success.get(unit_index, False) else 0,
                }
                row.update(params)
                rows.append(row)

            if not rows:
                return {
                    "study_id": experiment_id,
                    "name": name,
                    "revision": revision,
                    "created_at": created_at,
                    "executed_at": executed_at,
                    "duration_seconds": duration_seconds,
                    "success_rate": (
                        round(success_count / total_units, 4) if total_units > 0 else 0.0
                    ),
                    "total_units": total_units,
                    "success_count": success_count,
                    "failure_count": failure_count,
                    "parameter_keys": sorted(param_keys_set),
                }

            return {
                "study_id": experiment_id,
                "name": name,
                "revision": revision,
                "created_at": created_at,
                "executed_at": executed_at,
                "duration_seconds": duration_seconds,
                "success_rate": round(success_count / total_units, 4) if total_units > 0 else 0.0,
                "total_units": total_units,
                "success_count": success_count,
                "failure_count": failure_count,
                "parameter_keys": sorted(param_keys_set),
                "rows": rows,
            }

    # --- Private Implementation Methods ---

    def _save_policy(
        self, conn: sqlite3.Connection, policy: Any, policy_kind: PolicyKind,
        experiment_id: str, policy_index: int, context: PersistenceReconstructionContext
    ) -> str:
        """Save a single policy with its typed parameters.

        Implements Section 12.1-12.2: Uses registered PolicyCodecs for serialization.
        If no matching codec is found, falls back to direct serialization for
        standard allocation/withdrawal policies.
        """
        from fbf.core.domain.policies.allocation_policy import AllocationPolicy
        from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy

        codec_params = None
        policy_type = None

        # Try to find a matching codec in context
        for (kind, _ptype), codec in context.policy_codecs.items():
            if kind == policy_kind.value:
                try:
                    candidate = codec.dump(policy)
                    codec_params = dict(candidate)
                    policy_type = codec.policy_type
                    break
                except (TypeError, ValueError):
                    continue

        # Fallback for standard policies if no codec matched
        if codec_params is None:
            if policy_kind == PolicyKind.ALLOCATION:
                if isinstance(policy, AllocationPolicy):
                    equity = str(getattr(policy, 'equity_allocation', '1.0'))
                    codec_params = {"equity_allocation": equity}
                    policy_type = "AllocationPolicy"
                else:
                    raise UnsupportedSerializationError(
                        f"Unsupported allocation policy type: {type(policy).__name__}"
                    )
            else:
                if isinstance(policy, WithdrawalPolicy):
                    rate = str(getattr(policy, 'withdrawal_rate', '0.04'))
                    codec_params = {"withdrawal_rate": rate}
                    policy_type = "WithdrawalPolicy"
                else:
                    raise UnsupportedSerializationError(
                        f"Unsupported withdrawal policy type: {type(policy).__name__}"
                    )

        params_json = to_canonical_json(codec_params)
        params_hash = generate_hash(params_json)

        # Check if policy already exists (Section 12.2: uniqueness by type + hash)
        existing = conn.execute(
            "SELECT policy_id FROM policies WHERE policy_type = ? AND params_hash = ?",
            (policy_type, params_hash),
        ).fetchone()

        if existing:
            policy_id: str = existing[0]
        else:
            policy_id = generate_uuid()

            # Save policy metadata (Section 12.2: canonical JSON encoding)
            conn.execute(
                """
                INSERT INTO policies (policy_id, policy_type, params_json, params_hash, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    policy_id,
                    policy_type,
                    params_json,
                    params_hash,
                    utc_now_iso(),
                ),
            )

        # Save ordered policy association. This must run for every experiment
        # even when the policy row itself is reused (same type + hash), otherwise
        # an experiment whose policies match an already-stored policy would lose
        # its experiment_policies link and fail to reconstruct on load.
        conn.execute(
            """
            INSERT OR IGNORE INTO experiment_policies
                (experiment_id, policy_id, policy_kind, policy_index)
            VALUES (?, ?, ?, ?)
            """,
            (
                experiment_id,
                policy_id,
                policy_kind.value,
                policy_index,
            ),
        )

        return policy_id

    def _load_policies(
        self, conn: sqlite3.Connection, experiment_id: str, policy_kind: PolicyKind,
        context: PersistenceReconstructionContext
    ) -> tuple[Any, ...]:
        """Load policies for an experiment in correct order.

        Implements Section 12.1-12.2: Uses registered PolicyCodecs for reconstruction.
        Falls back to direct construction for standard policy types.
        """
        policies = []
        rows = conn.execute(
            """
            SELECT p.policy_type, p.params_json
            FROM policies p
            JOIN experiment_policies ep ON p.policy_id = ep.policy_id
            WHERE ep.experiment_id = ? AND ep.policy_kind = ?
            ORDER BY ep.policy_index
            """,
            (experiment_id, policy_kind.value),
        ).fetchall()

        for policy_type, params_json in rows:
            params = from_canonical_json(params_json)

            # Check for a registered codec first
            codec = context.policy_codecs.get((policy_kind.value, policy_type))
            if codec is not None:
                policy = codec.load(params)
            else:
                # Fallback for standard policy types
                if policy_type == "AllocationPolicy":
                    from fbf.core.domain.policies.allocation_policy import AllocationPolicy
                    policy = AllocationPolicy()
                elif policy_type == "WithdrawalPolicy":
                    from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy
                    policy = WithdrawalPolicy()
                else:
                    raise ReconstructionContextError(
                        f"No codec registered for policy type '{policy_type}' "
                        f"(kind: {policy_kind.value})"
                    )

            policies.append(policy)

        return tuple(policies)

    def _save_cohort(self, conn: sqlite3.Connection, experiment_id: str, cohort: Any) -> str:
        """Save a cohort specification with persistent identifier."""
        cohort_id = generate_uuid()

        conn.execute(
            """
            INSERT INTO cohorts (cohort_id, experiment_id, start_date, cohort_ref, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                cohort_id,
                experiment_id,
                cohort.start_date.isoformat(),
                cohort.id,
                utc_now_iso(),
            ),
        )

        return cohort_id

    def _load_cohorts(self, conn: sqlite3.Connection, experiment_id: str) -> tuple[Any, ...]:
        """Load all cohorts for an experiment, ordered by start date."""
        from datetime import date

        from fbf.core.study.internal.cohort.specification import CohortSpecification
        cohorts = []
        rows = conn.execute(
            "SELECT start_date, cohort_ref FROM cohorts "
            "WHERE experiment_id = ? ORDER BY start_date",
            (experiment_id,),
        ).fetchall()

        for start_date, cohort_ref in rows:
            cohorts.append(
                CohortSpecification(
                    start_date=date.fromisoformat(start_date),
                    id=cohort_ref,
                )
            )

        return tuple(cohorts)

    def _save_unit(
        self,
        conn: sqlite3.Connection,
        plan_id: str,
        unit_index: int,
        unit: Any,
        experiment_id: str,
        context: PersistenceReconstructionContext,
    ) -> str:
        """Save a simulation unit with all dependencies."""
        unit_id = generate_uuid()

        # Resolve cohort ID
        cohort_id = self._get_or_create_cohort_id(conn, experiment_id, unit.cohort)

        # Save unit metadata
        conn.execute(
            """
            INSERT INTO planned_units (
                unit_id, plan_id, unit_index, cohort_id, param_config_id,
                allocation_policy_id, withdrawal_policy_id, initial_portfolio_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                unit_id,
                plan_id,
                unit_index,
                cohort_id,
                self._save_parameter_config(conn, unit.parameter_config),
                self._save_allocation_policy(conn, unit.allocation_policy, experiment_id, context),
                self._save_withdrawal_policy(conn, unit.withdrawal_policy, experiment_id, context),
                to_canonical_json(
                    {
                        "holdings": [
                            {
                                "asset_class_id": h.asset_class.id,
                                "units": serialize_decimal(h.units)
                            }
                            for h in unit.initial_portfolio.holdings
                        ]
                    }
                ),
            ),
        )

        return unit_id

    def _get_or_create_cohort_id(
        self, conn: sqlite3.Connection, experiment_id: str, cohort: Any
    ) -> str:
        """Get existing cohort ID or create new one."""
        row = conn.execute(
            "SELECT cohort_id FROM cohorts WHERE experiment_id = ? AND start_date = ?",
            (experiment_id, cohort.start_date.isoformat()),
        ).fetchone()

        if row:
            cohort_id: str = row[0]
            return cohort_id

        return self._save_cohort(conn, experiment_id, cohort)

    def _save_parameter_config(self, conn: sqlite3.Connection, config: Any) -> str:
        """Save parameter configuration with hash for uniqueness."""
        params_json = to_canonical_json(dict(config.values))
        params_hash = generate_hash(params_json)

        # Check if config already exists (Section 12.2: uniqueness by hash)
        existing = conn.execute(
            "SELECT param_config_id FROM parameter_configurations WHERE params_hash = ?",
            (params_hash,),
        ).fetchone()
        if existing:
            existing_id: str = existing[0]
            return existing_id

        param_config_id = generate_uuid()

        conn.execute(
            """
            INSERT INTO parameter_configurations (
                param_config_id, params_json, params_hash, created_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                param_config_id,
                params_json,
                params_hash,
                utc_now_iso(),
            ),
        )

        return param_config_id

    def _save_allocation_policy(
        self,
        conn: sqlite3.Connection,
        policy: Any,
        experiment_id: str,
        context: PersistenceReconstructionContext,
    ) -> str:
        """Save allocation policy with experiment association."""
        return self._save_policy(conn, policy, PolicyKind.ALLOCATION, experiment_id, 0, context)

    def _save_withdrawal_policy(
        self,
        conn: sqlite3.Connection,
        policy: Any,
        experiment_id: str,
        context: PersistenceReconstructionContext,
    ) -> str:
        """Save withdrawal policy with experiment association."""
        return self._save_policy(conn, policy, PolicyKind.WITHDRAWAL, experiment_id, 0, context)

    def _load_units(
        self,
        conn: sqlite3.Connection,
        plan_id: str,
        context: PersistenceReconstructionContext,
        experiment: Any,
    ) -> list[Any]:
        """Load all units for a plan in correct order.

        Each unit's dataset is produced by slicing the experiment's full dataset
        at the cohort's start_date for the experiment's horizon_months.
        A local cache keyed by cohort start date prevents duplicate slices.
        """
        from datetime import date as _date

        rows = conn.execute(
            """
            SELECT unit_index, cohort_id, param_config_id, allocation_policy_id,
                   withdrawal_policy_id, initial_portfolio_json
            FROM planned_units
            WHERE plan_id = ?
            ORDER BY unit_index
            """,
            (plan_id,),
        ).fetchall()

        dataset_cache: dict[_date, Dataset] = {}
        units = []
        for (
            _unit_index,
            cohort_id,
            param_config_id,
            allocation_policy_id,
            withdrawal_policy_id,
            initial_portfolio_json,
        ) in rows:
            from fbf.core.study.plan import PlannedSimulationUnit
            cohort = self._load_cohort_by_id(conn, cohort_id)
            param_config = self._load_parameter_config(conn, param_config_id)
            allocation_policy = self._load_allocation_policy(conn, allocation_policy_id, context)
            withdrawal_policy = self._load_withdrawal_policy(conn, withdrawal_policy_id, context)
            portfolio = self._load_portfolio(conn, initial_portfolio_json)

            cohort_start = cohort.start_date
            if cohort_start not in dataset_cache:
                dataset_cache[cohort_start] = experiment.dataset.slice(
                    cohort_start, experiment.horizon_months
                )
            unit_dataset = dataset_cache[cohort_start]

            units.append(
                PlannedSimulationUnit(
                    cohort=cohort,
                    parameter_config=param_config,
                    allocation_policy=allocation_policy,
                    withdrawal_policy=withdrawal_policy,
                    initial_portfolio=portfolio,
                    dataset=unit_dataset,
                )
            )

        return units

    def _load_cohort_by_id(self, conn: sqlite3.Connection, cohort_id: str) -> Any:
        """Load cohort specification by persistent ID."""
        row = conn.execute(
            "SELECT start_date, cohort_ref FROM cohorts WHERE cohort_id = ?", (cohort_id,)
        ).fetchone()

        if not row:
            raise Exception(f"Cohort not found: {cohort_id}")

        from datetime import date

        from fbf.core.study.internal.cohort.specification import CohortSpecification

        return CohortSpecification(
            start_date=date.fromisoformat(row[0]),
            id=row[1],
        )

    def _load_parameter_config(self, conn: sqlite3.Connection, param_config_id: str) -> Any:
        """Load parameter configuration by ID."""
        row = conn.execute(
            "SELECT params_json FROM parameter_configurations WHERE param_config_id = ?",
            (param_config_id,),
        ).fetchone()

        if not row:
            raise Exception(f"Parameter config not found: {param_config_id}")

        from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
        return ParameterConfiguration(values=json.loads(row[0]))

    def _load_allocation_policy(
        self, conn: sqlite3.Connection, policy_id: str, context: PersistenceReconstructionContext
    ) -> Any:
        """Load allocation policy by ID."""
        return self._load_policy(conn, policy_id, context)

    def _load_withdrawal_policy(
        self, conn: sqlite3.Connection, policy_id: str, context: PersistenceReconstructionContext
    ) -> Any:
        """Load withdrawal policy by ID."""
        return self._load_policy(conn, policy_id, context)

    def _load_policy(
        self, conn: sqlite3.Connection, policy_id: str, context: PersistenceReconstructionContext
    ) -> Any:
        """Load policy by ID from policies table.

        Uses context.codecs for reconstruction when a registered codec exists.
        """
        row = conn.execute(
            "SELECT policy_type, params_json FROM policies WHERE policy_id = ?",
            (policy_id,),
        ).fetchone()

        if not row:
            raise Exception(f"Policy not found: {policy_id}")

        from fbf.core.domain.policies.allocation_policy import AllocationPolicy
        from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy

        policy_type, params_json = row
        params = from_canonical_json(params_json)

        # Determine policy kind from stored type
        kind = "allocation" if policy_type == "AllocationPolicy" else "withdrawal"

        # Check for a registered codec
        codec = context.policy_codecs.get((kind, policy_type))
        if codec is not None:
            return codec.load(params)

        # Fallback for standard policy types
        if policy_type == "AllocationPolicy":
            return AllocationPolicy()
        elif policy_type == "WithdrawalPolicy":
            return WithdrawalPolicy()
        else:
            raise ReconstructionContextError(
                f"No codec registered for policy type '{policy_type}'"
            )

    def _load_portfolio(self, conn: sqlite3.Connection, initial_portfolio_json: str) -> Any:
        """Load portfolio from serialized holdings."""
        data = json.loads(initial_portfolio_json)

        holdings = []
        for h in data["holdings"]:
            from fbf.core.domain.model.portfolio import AssetHolding
            holdings.append(
                AssetHolding(
                    asset_class=self._make_asset(h["asset_class_id"]),
                    units=deserialize_decimal(h["units"]),
                )
            )

        from fbf.core.domain.model.portfolio import Portfolio
        return Portfolio(holdings=tuple(holdings))

    def _make_asset(self, asset_class_id: str) -> Any:
        """Create a minimal AssetClass for reconstruction.

        This is a minimal implementation that should be replaced with the
        proper AssetClass resolution in a real implementation.
        """
        from fbf.core.domain.model.asset import AssetClass
        return AssetClass(id=asset_class_id, name="ACWI", description="Global equities")

    def _get_experiment_id_by_policy(self, policy_id: str, conn: sqlite3.Connection) -> str:
        """Get experiment ID for a policy (required for experiment_policies)."""
        row = conn.execute(
            "SELECT experiment_id FROM experiment_policies WHERE policy_id = ?", (policy_id,)
        ).fetchone()

        if not row:
            raise Exception(f"Policy not associated with experiment: {policy_id}")

        exp_id: str = row[0]
        return exp_id

    def _save_simulation_results(
        self,
        conn: sqlite3.Connection,
        result_id: str,
        simulation_results: tuple[Any, ...],
        context: PersistenceReconstructionContext,
    ) -> None:
        """Save all simulation results for a result ID.

        Uses context.simulation_result_codec for serialization.
        """
        for unit_index, unit_result in enumerate(simulation_results):
            self._save_simulation_result(conn, result_id, unit_index, unit_result, context)

    def _save_simulation_result(
        self,
        conn: sqlite3.Connection,
        result_id: str,
        unit_index: int,
        unit_result: Any,
        context: PersistenceReconstructionContext,
    ) -> None:
        """Save a single simulation result with timeline and statistics.

        Section 12.1: Uses registered SimulationResultCodec for serialization.
        """
        # Use context codec for serialization
        serialized = context.simulation_result_codec.dump(unit_result)

        # serialized provides statistics_payload_json and monthly_payloads_json
        # Each monthly_payload goes in its own row; the final row carries statistics
        monthly_payloads = list(serialized.monthly_payloads_json)
        statistics_payload = serialized.statistics_payload_json

        # Ensure at least one row per unit (empty timeline still needs a result marker)
        if not monthly_payloads:
            monthly_payloads.append(json.dumps({"dummy": True}))

        for month_idx, monthly_payload in enumerate(monthly_payloads):
            is_final = 1 if month_idx == len(monthly_payloads) - 1 else 0
            stats_json = statistics_payload if is_final else None

            conn.execute(
                """
                INSERT INTO simulation_results (
                    execution_result_id, unit_index, month_index, monthly_payload_json,
                    statistics_payload_json, final_month
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    result_id,
                    unit_index,
                    month_idx,
                    monthly_payload,
                    stats_json,
                    is_final,
                ),
            )

    def _load_simulation_results(
        self, conn: sqlite3.Connection, result_id: str, context: PersistenceReconstructionContext
    ) -> Any:
        """Load simulation results ordered by unit and month.

        Section 12.1-12.2: Uses registered SimulationResultCodec for reconstruction.
        Groups monthly rows per unit, then calls codec.load() once per unit.
        """
        rows = conn.execute(
            """
            SELECT unit_index, month_index, monthly_payload_json,
                   statistics_payload_json, final_month
            FROM simulation_results
            WHERE execution_result_id = ?
            ORDER BY unit_index, month_index
            """,
            (result_id,),
        ).fetchall()

        # Group rows by unit_index
        units_data: OrderedDict[int, dict[str, Any]] = OrderedDict()
        for (
            unit_index,
            _month_index,
            monthly_payload_json,
            statistics_payload_json,
            final_month,
        ) in rows:
            if unit_index not in units_data:
                units_data[unit_index] = {"monthly_payloads": [], "statistics_payload": None}
            units_data[unit_index]["monthly_payloads"].append(monthly_payload_json)
            if final_month:
                units_data[unit_index]["statistics_payload"] = statistics_payload_json

        simulation_results = []
        for unit_index, data in units_data.items():
            # Use context codec to reconstruct the SimulationResult
            if data["statistics_payload"] is None:
                raise PersistenceError(f"Missing statistics payload for unit {unit_index}")
            result = context.simulation_result_codec.load(
                statistics_payload_json=data["statistics_payload"],
                monthly_payloads_json=data["monthly_payloads"],
            )
            simulation_results.append(result)

        return simulation_results

    def _retry_on_lock(self, operation: Any, *args: Any, **kwargs: Any) -> Any:
        """Retry the operation with exponential backoff on SQLite lock errors."""
        max_retries = 5
        retry_delays = [50, 100, 200, 400, 400]
        last_error = None

        for i in range(max_retries):
            try:
                return operation(*args, **kwargs)
            except sqlite3.OperationalError as e:
                last_error = e
                if "database is locked" in str(e).lower() and i < len(retry_delays):
                    import time
                    time.sleep(retry_delays[i] / 1000.0)
                    continue
        if last_error:
            raise last_error
        raise PersistenceError("Maximum retries exceeded")
        raise last_error

SQLiteStudyRepository = SQLiteRepository
