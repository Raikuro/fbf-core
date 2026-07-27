"""SQLite repository implementation."""

from __future__ import annotations

import json
import sqlite3
import hashlib
import uuid
import os
import io
from datetime import datetime
from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence, Literal, TYPE_CHECKING, Any, Tuple
from .errors import (
    PersistenceError,
    StudyNotFoundError,
    ResultsNotFoundError,
    DuplicateStudyError,
    RepositoryError,
    ReconstructionContextError,
    UnsupportedSerializationError,
)
from .schema import ALL_DDL, SCHEMA_VERSION
from . import serializers

def utc_now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def to_canonical_json(data: Mapping[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def to_json_scalar(value: Any) -> str:
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
    elif (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    else:
        raise ValueError(f"Value {value} cannot be deserialized from JSONScalar")


def make_asset(asset_id: str = "acwi") -> Any:
    from engine.domain.model.asset import AssetClass
    return AssetClass(id=asset_id, name="ACWI", description="Global equities")


def generate_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


if TYPE_CHECKING:
    from engine.domain.model.dataset import Dataset
    from engine.domain.policies.allocation_policy import AllocationPolicy
    from engine.domain.policies.withdrawal_policy import WithdrawalPolicy
    from engine.domain.simulation import SimulationResult
    from research.domain.experiment.definition import ExperimentDefinition
    from research.domain.plan import ResearchPlan
    from research.orchestration.result import ResearchExecutionResult

JSONScalar = None | bool | int | float | str

@dataclass(frozen=True)
class ExperimentIdentity:
    name: str
    revision: str

class DatasetResolver(Protocol):
    def resolve(self, dataset_identifier: str) -> Dataset: ...

class PolicyCodec(Protocol):
    policy_type: str
    policy_kind: Literal["allocation", "withdrawal"]
    def dump(self, policy: AllocationPolicy | WithdrawalPolicy) -> Mapping[str, JSONScalar]: ...
    def load(self, parameters: Mapping[str, JSONScalar]) -> AllocationPolicy | WithdrawalPolicy: ...

@dataclass(frozen=True)
class SerializedSimulationResult:
    statistics_payload_json: str
    monthly_payloads_json: tuple[str, ...]

class SimulationResultCodec(Protocol):
    def dump(self, result: SimulationResult) -> SerializedSimulationResult: ...
    def load(self, statistics_payload_json: str, monthly_payloads_json: Sequence[str]) -> SimulationResult: ...

@dataclass(frozen=True)
class PersistenceReconstructionContext:
    dataset_resolver: DatasetResolver
    policy_codecs: Mapping[tuple[str, str], PolicyCodec]
    simulation_result_codec: SimulationResultCodec


def validate_context(context: PersistenceReconstructionContext) -> None:
    if not context.dataset_resolver:
        raise ReconstructionContextError("Dataset resolver is required")
    
    if not context.policy_codecs:
        raise ReconstructionContextError("Policy codecs are required")
    
    if not context.simulation_result_codec:
        raise ReconstructionContextError("Simulation result codec is required")


def generate_uuid() -> str:
    return str(uuid.uuid4())

class SQLiteRepository:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._initialize_schema()

    def _connect(self, timeout: int = 5) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=timeout)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _connect_immediate(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("BEGIN DEFERRED")
        return conn

    def _initialize_schema(self) -> None:
        with self._connect() as conn:
            for statement in ALL_DDL:
                conn.execute(statement)
            conn.execute("INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (?, ?)", (SCHEMA_VERSION, utc_now_iso()))

    def save_experiment(
        self, identity: ExperimentIdentity, experiment: ExperimentDefinition, context: PersistenceReconstructionContext
    ) -> str:
        validate_context(context)
        
        experiment_id = generate_uuid()
        with self._connect_immediate() as conn:
            conn.execute(
                "INSERT INTO experiments (experiment_id, name, revision, description, dataset_identifier, horizon_months, initial_wealth, initial_wealth_currency, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    experiment_id,
                    identity.name,
                    identity.revision,
                    experiment.description,
                    experiment.dataset.version,
                    experiment.horizon_months,
                    serialize_decimal(experiment.initial_wealth.amount),
                    experiment.initial_wealth.currency.value,
                    utc_now_iso(),
                    utc_now_iso(),
                )
            )
            
            for policy in experiment.allocation_policies:
                self._save_policy(conn, policy, "allocation")
            
            for policy in experiment.withdrawal_policies:
                self._save_policy(conn, policy, "withdrawal")
            
            for cohort in experiment.cohorts:
                self._save_cohort(conn, experiment_id, cohort)
        
        return experiment_id

    def load_experiment(
        self, identity_or_id: str | ExperimentIdentity, context: PersistenceReconstructionContext
    ) -> ExperimentDefinition:
        validate_context(context)
        
        with self._connect() as conn:
            if isinstance(identity_or_id, ExperimentIdentity):
                row = conn.execute(
                    "SELECT experiment_id, name, revision, description, dataset_identifier, horizon_months, initial_wealth, initial_wealth_currency FROM experiments WHERE name = ? AND revision = ?",
                    (identity_or_id.name, identity_or_id.revision)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT e.experiment_id, e.name, e.revision, e.description, e.dataset_identifier, e.horizon_months, e.initial_wealth, e.initial_wealth_currency, d.version FROM experiments e JOIN datasets d ON e.dataset_identifier = d.version WHERE experiment_id = ?",
                    (identity_or_id,)
                ).fetchone()
            
            if not row:
                raise StudyNotFoundError(f"Experiment not found: {identity_or_id}")
            
            experiment_id, name, revision, description, dataset_identifier, horizon_months, initial_wealth, initial_wealth_currency, dataset_version = row
            
            dataset = context.dataset_resolver.resolve(dataset_identifier)
            
            allocation_policies = self._load_policies(conn, experiment_id, "allocation")
            withdrawal_policies = self._load_policies(conn, experiment_id, "withdrawal")
            
            return ExperimentDefinition(
                name=name,
                description=description,
                dataset=dataset,
                horizon_months=horizon_months,
                initial_wealth=Money(
                    amount=deserialize_decimal(initial_wealth),
                    currency=Currency(initial_wealth_currency)
                ),
                cohorts=self._load_cohorts(conn, experiment_id),
                allocation_policies=allocation_policies,
                withdrawal_policies=withdrawal_policies,
            )

    def save_plan(self, plan: ResearchPlan, experiment_id: str, context: PersistenceReconstructionContext) -> str:
        validate_context(context)
        
        plan_id = generate_uuid()
        
        with self._connect_immediate() as conn:
            conn.execute(
                "INSERT INTO research_plans (plan_id, experiment_id, created_at, unit_count, status) VALUES (?, ?, ?, ?, ?)",
                (
                    plan_id,
                    experiment_id,
                    utc_now_iso(),
                    len(plan.units),
                    "planned"
                )
            )
            
            plan_id = conn.execute("SELECT plan_id FROM research_plans WHERE plan_id = ?", (plan_id,)).fetchone()[0]
            
            for i, unit in enumerate(plan.units):
                self._save_unit(conn, plan_id, i, unit, experiment_id)
        
        return plan_id

    def load_plan(self, plan_id: str, context: PersistenceReconstructionContext) -> ResearchPlan:
        validate_context(context)
        
        with self._connect() as conn:
            units = self._load_units(conn, plan_id)
            
            row = conn.execute(
                "SELECT experiment_id, created_at, unit_count, status FROM research_plans WHERE plan_id = ?",
                (plan_id,)
            ).fetchone()
            
            if not row:
                raise StudyNotFoundError(f"Plan not found: {plan_id}")
            
            experiment_id, created_at, unit_count, status = row
            
            experiment = self.load_experiment(experiment_id, context)
            
            return ResearchPlan(
                experiment_definition=experiment,
                units=tuple(units)
            )

    def save_execution_result(
        self, plan_id: str, result: ResearchExecutionResult, context: PersistenceReconstructionContext, duration_seconds: float
    ) -> str:
        validate_context(context)
        
        result_id = generate_uuid()
        
        with self._connect_immediate() as conn:
            conn.execute(
                "INSERT INTO execution_results (result_id, plan_id, executed_at, duration_seconds, success_count, failure_count, total_units) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    result_id,
                    plan_id,
                    utc_now_iso(),
                    duration_seconds,
                    result.simulation_result.statistics.success_count,
                    result.simulation_result.statistics.failure_count,
                    result.simulation_result.statistics.total_units,
                )
            )
            
            self._save_simulation_results(conn, result_id, result.simulation_result)
        
        return result_id

    def load_execution_result(
        self, plan_id_or_result_id: str, context: PersistenceReconstructionContext
    ) -> ResearchExecutionResult:
        validate_context(context)
        
        with self._connect() as conn:
            if "-" in plan_id_or_result_id:
                row = conn.execute(
                    "SELECT plan_id, executed_at, duration_seconds, success_count, failure_count, total_units FROM execution_results WHERE result_id = ?",
                    (plan_id_or_result_id,)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT result_id, executed_at, duration_seconds, success_count, failure_count, total_units FROM execution_results WHERE plan_id = ?",
                    (plan_id_or_result_id,)
                ).fetchone()
            
            if not row:
                raise ResultsNotFoundError(f"Execution result not found: {plan_id_or_result_id}")
            
            if "-" in plan_id_or_result_id:
                result_id, plan_id, executed_at, duration_seconds, success_count, failure_count, total_units = row
            else:
                plan_id, executed_at, duration_seconds, success_count, failure_count, total_units = row
                result_id = plan_id_or_result_id
            
            simulation_result = self._load_simulation_results(conn, result_id)
            
            from engine.application.simulation import ExperimentRun
            experiment_run = ExperimentRun(
                definition=result.simulation_result,
                simulation_results=(result.simulation_result,)
            )
            
            from research.orchestration.result import ResearchExecutionResult
            return ResearchExecutionResult(
                plan=result.plan,
                experiment_result=experiment_run
            )

    def find_experiment_by_name(self, name: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT experiment_id FROM experiments WHERE name = ?",
                (name,)
            ).fetchone()
            return row[0] if row else None

    def list_experiments(self) -> list[Mapping[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT experiment_id, name, revision, dataset_identifier, horizon_months, initial_wealth, initial_wealth_currency, created_at, updated_at FROM experiments ORDER BY name, revision"
            ).fetchall()
            
            experiments = []
            for row in rows:
                experiments.append({
                    "experiment_id": row[0],
                    "name": row[1],
                    "revision": row[2],
                    "dataset_identifier": row[3],
                    "horizon_months": row[4],
                    "initial_wealth": row[5],
                    "initial_wealth_currency": row[6],
                    "created_at": row[7],
                    "updated_at": row[8],
                })
            
            return experiments

    def find_result_by_plan(self, plan_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT result_id FROM execution_results WHERE plan_id = ?",
                (plan_id,)
            ).fetchone()
            return row[0] if row else None

    def _save_policy(self, conn: sqlite3.Connection, policy: Any, policy_kind: str) -> str:
        policy_id = generate_uuid()
        
        if policy_kind == "allocation":
            params = {"equity_allocation": serialize_decimal(policy.equity_allocation)}
            policy_type = "AllocationPolicy"
        else:
            params = {"withdrawal_rate": serialize_decimal(policy.withdrawal_rate)}
            policy_type = "WithdrawalPolicy"
        
        conn.execute(
            "INSERT INTO policies (policy_id, policy_type, params_json, params_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                policy_id,
                policy_type,
                to_canonical_json(params),
                generate_hash(to_canonical_json(params)),
                utc_now_iso(),
            )
        )
        
        conn.execute(
            "INSERT INTO experiment_policies (experiment_id, policy_id, policy_kind, policy_index) VALUES (?, ?, ?, ?)",
            (
                self._get_experiment_id_by_policy(policy_id, conn),
                policy_id,
                policy_kind,
                len(conn.execute(f"SELECT * FROM experiment_policies WHERE experiment_id = ? AND policy_kind = ?", (self._get_experiment_id_by_policy(policy_id, conn), policy_kind)).fetchall()),
            )
        )
        
        return policy_id

    def _load_policies(self, conn: sqlite3.Connection, experiment_id: str, policy_kind: str) -> Tuple[Any, ...]:
        policies = []
        rows = conn.execute(
            "SELECT p.policy_type, p.params_json FROM policies p JOIN experiment_policies ep ON p.policy_id = ep.policy_id WHERE ep.experiment_id = ? AND ep.policy_kind = ? ORDER BY ep.policy_index",
            (experiment_id, policy_kind)
        ).fetchall()
        
        for policy_type, params_json in rows:
            params = json.loads(params_json)
            
            if policy_type == "AllocationPolicy":
                policy = DummyAllocationPolicy()
            else:
                policy = DummyWithdrawalPolicy()
            
            policies.append(policy)
        
        return tuple(policies)

    def _save_cohort(self, conn: sqlite3.Connection, experiment_id: str, cohort: Any) -> str:
        cohort_id = generate_uuid()
        
        conn.execute(
            "INSERT INTO cohorts (cohort_id, experiment_id, start_date, cohort_ref, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                cohort_id,
                experiment_id,
                cohort.start_date.isoformat(),
                cohort.id,
                utc_now_iso(),
            )
        )
        
        return cohort_id

    def _load_cohorts(self, conn: sqlite3.Connection, experiment_id: str) -> Tuple[Any, ...]:
        cohorts = []
        rows = conn.execute(
            "SELECT start_date, cohort_ref FROM cohorts WHERE experiment_id = ? ORDER BY start_date",
            (experiment_id,)
        ).fetchall()
        
        for start_date, cohort_ref in rows:
            cohorts.append(CohortSpecification(
                start_date=date.fromisoformat(start_date),
                id=cohort_ref,
            ))
        
        return tuple(cohorts)

    def _save_unit(self, conn: sqlite3.Connection, plan_id: str, unit_index: int, unit: Any, experiment_id: str) -> str:
        unit_id = generate_uuid()
        
        cohort_id = self._get_or_create_cohort_id(conn, experiment_id, unit.cohort)
        
        conn.execute(
            "INSERT INTO planned_units (unit_id, plan_id, unit_index, cohort_id, param_config_id, allocation_policy_id, withdrawal_policy_id, initial_portfolio_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                unit_id,
                plan_id,
                unit_index,
                cohort_id,
                self._save_parameter_config(conn, unit.parameter_config),
                self._save_allocation_policy(conn, unit.allocation_policy, experiment_id),
                self._save_withdrawal_policy(conn, unit.withdrawal_policy, experiment_id),
                to_canonical_json({
                    "holdings": [
                        {"asset_class_id": h.asset_class.id, "units": serialize_decimal(h.units)}
                        for h in unit.initial_portfolio.holdings
                    ]
                }),
                utc_now_iso(),
            )
        )
        
        return unit_id

    def _get_or_create_cohort_id(self, conn: sqlite3.Connection, experiment_id: str, cohort: Any) -> str:
        row = conn.execute(
            "SELECT cohort_id FROM cohorts WHERE experiment_id = ? AND start_date = ?",
            (experiment_id, cohort.start_date.isoformat())
        ).fetchone()
        
        if row:
            return row[0]
        
        return self._save_cohort(conn, experiment_id, cohort)

    def _save_parameter_config(self, conn: sqlite3.Connection, config: Any) -> str:
        param_config_id = generate_uuid()
        
        params_json = to_canonical_json(config.values)
        params_hash = generate_hash(params_json)
        
        conn.execute(
            "INSERT INTO parameter_configurations (param_config_id, params_json, params_hash, created_at) VALUES (?, ?, ?, ?)",
            (
                param_config_id,
                params_json,
                params_hash,
                utc_now_iso(),
            )
        )
        
        return param_config_id

    def _save_allocation_policy(self, conn: sqlite3.Connection, policy: Any, experiment_id: str) -> str:
        return self._save_policy(conn, policy, "allocation")

    def _save_withdrawal_policy(self, conn: sqlite3.Connection, policy: Any, experiment_id: str) -> str:
        return self._save_policy(conn, policy, "withdrawal")

    def _load_units(self, conn: sqlite3.Connection, plan_id: str) -> list:
        rows = conn.execute(
            "SELECT unit_index, cohort_id, param_config_id, allocation_policy_id, withdrawal_policy_id, initial_portfolio_json FROM planned_units WHERE plan_id = ? ORDER BY unit_index",
            (plan_id,)
        ).fetchall()
        
        units = []
        for unit_index, cohort_id, param_config_id, allocation_policy_id, withdrawal_policy_id, initial_portfolio_json in rows:
            cohort = self._load_cohort_by_id(conn, cohort_id)
            param_config = self._load_parameter_config(conn, param_config_id)
            allocation_policy = self._load_allocation_policy(conn, allocation_policy_id)
            withdrawal_policy = self._load_withdrawal_policy(conn, withdrawal_policy_id)
            portfolio = self._load_portfolio(conn, initial_portfolio_json)
            
            units.append(PlannedSimulationUnit(
                cohort=cohort,
                parameter_config=param_config,
                allocation_policy=allocation_policy,
                withdrawal_policy=withdrawal_policy,
                initial_portfolio=portfolio,
            ))
        
        return units

    def _load_cohort_by_id(self, conn: sqlite3.Connection, cohort_id: str) -> Any:
        row = conn.execute(
            "SELECT start_date, cohort_ref FROM cohorts WHERE cohort_id = ?",
            (cohort_id,)
        ).fetchone()
        
        if not row:
            raise Exception(f"Cohort not found: {cohort_id}")
        
        start_date, cohort_ref = row
        return CohortSpecification(
            start_date=date.fromisoformat(start_date),
            id=cohort_ref,
        )

    def _load_parameter_config(self, conn: sqlite3.Connection, param_config_id: str) -> Any:
        row = conn.execute(
            "SELECT params_json FROM parameter_configurations WHERE param_config_id = ?",
            (param_config_id,)
        ).fetchone()
        
        if not row:
            raise Exception(f"Parameter config not found: {param_config_id}")
        
        params_json = row[0]
        params = json.loads(params_json)
        
        return ParameterConfiguration(values=params)

    def _load_allocation_policy(self, conn: sqlite3.Connection, policy_id: str) -> Any:
        return self._load_policy(conn, policy_id)

    def _load_withdrawal_policy(self, conn: sqlite3.Connection, policy_id: str) -> Any:
        return self._load_policy(conn, policy_id)

    def _load_policy(self, conn: sqlite3.Connection, policy_id: str) -> Any:
        row = conn.execute(
            "SELECT policy_type, params_json FROM policies WHERE policy_id = ?",
            (policy_id,)
        ).fetchone()
        
        if not row:
            raise Exception(f"Policy not found: {policy_id}")
        
        policy_type, params_json = row
        params = json.loads(params_json)
        
        if policy_type == "AllocationPolicy":
            return DummyAllocationPolicy()
        else:
            return DummyWithdrawalPolicy()

    def _load_portfolio(self, conn: sqlite3.Connection, initial_portfolio_json: str) -> Any:
        data = json.loads(initial_portfolio_json)
        
        holdings = []
        for h in data["holdings"]:
            holdings.append(AssetHolding(
                asset_class=make_asset(h["asset_class_id"]),
                units=deserialize_decimal(h["units"])
            ))
        
        return Portfolio(holdings=tuple(holdings))

    def _get_experiment_id_by_policy(self, policy_id: str, conn: sqlite3.Connection) -> str:
        row = conn.execute(
            "SELECT experiment_id FROM experiment_policies WHERE policy_id = ?",
            (policy_id,)
        ).fetchone()
        
        if not row:
            raise Exception(f"Policy not associated with experiment: {policy_id}")
        
        return row[0]

    def _save_simulation_results(self, conn: sqlite3.Connection, result_id: str, result: Any) -> None:
        for unit_result in result.units:
            self._save_simulation_result(conn, result_id, unit_result)

def _save_simulation_result(self, conn: sqlite3.Connection, result_id: str, unit_result: Any) -> None:
    monthly_payloads_json = self._serialize_monthly_results(unit_result.timeline)
    statistics_payload_json = self._serialize_simulation_statistics(unit_result.simulation_result.statistics)
    
    conn.execute(
        "INSERT INTO simulation_results (execution_result_id, unit_index, month_index, monthly_payload_json, statistics_payload_json, final_month) VALUES (?, ?, ?, ?, ?, ?)",
        (
            result_id,
            unit_result.unit_index,
            unit_result.month_index,
            to_canonical_json(monthly_payloads_json),
            to_canonical_json(statistics_payload_json),
            1 if unit_result.final_month else 0,
        )
    )

    def _serialize_monthly_results(self, timeline: Any) -> list:
        monthly_payloads = []
        
        for monthly_result in timeline.monthly_results:
            monthly_payloads.append({
                "unit_index": monthly_result.unit_index,
                "month_index": monthly_result.month_index,
                "final_portfolio": {
                    "holdings": [
                        {"asset_class_id": h.asset_class.id, "units": serialize_decimal(h.units)}
                        for h in monthly_result.portfolio.holdings
                    ]
                }
            })
        
        return monthly_payloads

    def _serialize_simulation_statistics(self, stats: Any) -> dict:
        return {
            "final_wealth": {"amount": serialize_decimal(stats.final_wealth.amount), "currency": stats.final_wealth.currency.value},
            "max_drawdown": serialize_decimal(stats.max_drawdown),
            "success": stats.success,
            "failure_month": stats.failure_month,
            "months_simulated": stats.months_simulated,
            "execution_time_seconds": stats.execution_time_seconds,
        }

    def _deserialize_monthly_results(self, monthly_payloads_json: list) -> Tuple[Any, ...]:
        monthly_results = []
        
        for monthly_data in monthly_payloads_json:
            monthly_results.append(MonthlyResult(
                unit_index=monthly_data["unit_index"],
                month_index=monthly_data["month_index"],
                portfolio=Portfolio(
                    holdings=tuple([
                        AssetHolding(
                            asset_class=make_asset(h["asset_class_id"]),
                            units=deserialize_decimal(h["units"])
                        )
                        for h in monthly_data["final_portfolio"]["holdings"]
                    ])
                ),
            ))
        
        return tuple(monthly_results)

    def _deserialize_simulation_statistics(self, statistics_payload_json: dict) -> Any:
        return SimulationStatistics(
            final_wealth=Money(
                amount=deserialize_decimal(statistics_payload_json["final_wealth"]["amount"]),
                currency=Currency(statistics_payload_json["final_wealth"]["currency"])
            ),
            max_drawdown=deserialize_decimal(statistics_payload_json["max_drawdown"]),
            success=statistics_payload_json["success"],
            failure_month=statistics_payload_json["failure_month"],
            months_simulated=statistics_payload_json["months_simulated"],
            execution_time_seconds=statistics_payload_json["execution_time_seconds"],
        )

    def _load_simulation_results(self, conn: sqlite3.Connection, result_id: str) -> Any:
        rows = conn.execute(
            "SELECT unit_index, month_index, monthly_payload_json, statistics_payload_json, final_month FROM simulation_results WHERE execution_result_id = ? ORDER BY unit_index, month_index",
            (result_id,)
        ).fetchall()
        
        simulation_results = []
        for unit_index, month_index, monthly_payload_json, statistics_payload_json, final_month in rows:
            monthly_results = MonthlyResult(
                unit_index=unit_index,
                month_index=month_index,
                portfolio={
                    "holdings": json.loads(monthly_payload_json)["final_portfolio"]["holdings"]
                }
            )
            
            simulation_results.append(SimulationResult(
                unit_index=unit_index,
                month_index=month_index,
                timeline=SimulationTimeline(monthly_results=[monthly_results]),
                statistics=self._deserialize_simulation_statistics(json.loads(statistics_payload_json)),
                final_month=bool(final_month),
            ))
        
        return simulation_results

    def _retry_on_lock(self, operation, *args, **kwargs):
        """Retry the operation with exponential backoff on SQLite lock errors."""
        max_retries = 5
        retry_delays = [50, 100, 200, 400, 400]
        last_error = None
        
        for i in range(max_retries):
            try:
                return operation(*args, **kwargs)
            except sqlite3.OperationalError as e:
                last_error = e
                if "database is locked" in str(e).lower():
                    if i < len(retry_delays):
                        import time
                        time.sleep(retry_delays[i] / 1000.0)  # Convert ms to seconds
                        continue
                raise last_error
        raise last_error
