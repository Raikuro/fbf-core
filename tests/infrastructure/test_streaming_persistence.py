"""Integration tests for incremental (streamed) execution persistence."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

import pytest

from fbf.core.persistence.studies.sqlite import (
    CorruptedDatabaseError,
    ExecutionAttempt,
    ExecutionInProgressError,
    PersistenceError,
    ResultsNotFoundError,
    SQLiteRepository,
    StaleExecutionAttemptError,
)
from fbf.core.persistence.studies.sqlite.sqlite_repository import ExperimentIdentity
from tests.infrastructure.test_sqlite_persistence import (
    get_dummy_context,
    make_experiment,
    make_plan,
    make_sim_result,
)


def _new_plan(repo: SQLiteRepository, ctx: Any, units: int = 4) -> tuple[Any, str]:
    experiment = make_experiment("Streaming Study")
    exp_id = repo.save_experiment(
        ExperimentIdentity(name="Streaming Study", revision="v1"),
        experiment,
        ctx,
    )
    plan = make_plan(units)
    plan_id = repo.save_plan(plan, exp_id, ctx)
    return plan, plan_id


def _unit_signature(plan: Any) -> tuple[Any, ...]:
    return tuple(
        (
            unit.cohort.start_date,
            dict(unit.parameter_config.values),
            unit.initial_portfolio,
        )
        for unit in plan.units
    )


def _statistics(results: Any) -> tuple[Any, ...]:
    return tuple(result.statistics for result in results)


def _results(count: int, *, success_from: int = 0) -> tuple[Any, ...]:
    return tuple(
        make_sim_result(
            final_wealth=str(500000 + i * 100),
            success=i >= success_from,
        )
        for i in range(count)
    )


def test_slice_roundtrip_matches_complete_result(tmp_path: Path) -> None:
    repo = SQLiteRepository(str(tmp_path / "stream.db"))
    ctx = get_dummy_context()
    plan, plan_id = _new_plan(repo, ctx)
    results = _results(len(plan.units))

    attempt = repo.begin_execution(plan_id, len(plan.units), ctx)
    assert attempt.completed_units == 0
    assert repo.find_result_by_plan(plan_id) is None

    attempt = repo.append_execution_slice(
        attempt.result_id, attempt.attempt_id, 0, results[:2], ctx
    )
    assert attempt.completed_units == 2
    assert attempt.success_count == 2
    assert repo.find_result_by_plan(plan_id) is None
    assert repo.get_execution_result_metadata(plan_id) is None
    assert repo.get_result_statistics(attempt.result_id) is None
    assert repo.get_available_parameters(attempt.result_id) is None
    with pytest.raises(ResultsNotFoundError):
        repo.load_execution_result(plan_id, ctx)
    with pytest.raises(ResultsNotFoundError):
        repo.load_execution_result(attempt.result_id, ctx)

    attempt = repo.append_execution_slice(
        attempt.result_id, attempt.attempt_id, 2, results[2:], ctx
    )
    assert attempt.completed_units == 4
    completed = repo.complete_execution(
        attempt.result_id, attempt.attempt_id, duration_seconds=1.25
    )
    assert completed.status == "completed"
    assert repo.list_incomplete_executions() == []

    loaded = repo.load_execution_result(plan_id, ctx)
    assert _unit_signature(loaded.plan) == _unit_signature(plan)
    assert _statistics(loaded.results) == _statistics(results)
    assert repo.find_result_by_plan(plan_id) == attempt.result_id
    assert repo.find_plan_by_result(attempt.result_id) == plan_id
    metadata = repo.get_execution_result_metadata(plan_id)
    assert metadata is not None
    assert metadata["success_count"] == 4
    assert repo.get_execution_attempt(attempt.result_id) == completed


def test_append_is_idempotent_and_contiguous(tmp_path: Path) -> None:
    repo = SQLiteRepository(str(tmp_path / "idempotent.db"))
    ctx = get_dummy_context()
    plan, plan_id = _new_plan(repo, ctx)
    results = _results(len(plan.units))
    attempt = repo.begin_execution(plan_id, len(plan.units), ctx)

    first = repo.append_execution_slice(
        attempt.result_id, attempt.attempt_id, 0, results[:2], ctx
    )
    retried = repo.append_execution_slice(
        attempt.result_id, attempt.attempt_id, 0, results[:2], ctx
    )
    assert retried.completed_units == first.completed_units == 2
    assert retried.success_count == first.success_count == 2
    assert retried.failure_count == first.failure_count == 0

    with pytest.raises(PersistenceError, match="contiguously"):
        repo.append_execution_slice(
            attempt.result_id, attempt.attempt_id, 3, results[3:], ctx
        )
    with pytest.raises(PersistenceError, match="exceeds expected"):
        repo.append_execution_slice(
            attempt.result_id, attempt.attempt_id, 2, _results(3), ctx
        )
    with pytest.raises(ValueError):
        repo.append_execution_slice(
            attempt.result_id, attempt.attempt_id, 2, (), ctx
        )

    repo.append_execution_slice(
        attempt.result_id, attempt.attempt_id, 2, results[2:], ctx
    )
    repo.complete_execution(attempt.result_id, attempt.attempt_id, 0.5)
    with pytest.raises(PersistenceError, match="not executing"):
        repo.append_execution_slice(
            attempt.result_id, attempt.attempt_id, 4, _results(1), ctx
        )


def test_stale_attempt_and_concurrent_begin_rejected(tmp_path: Path) -> None:
    repo = SQLiteRepository(str(tmp_path / "stale.db"))
    ctx = get_dummy_context()
    plan, plan_id = _new_plan(repo, ctx)
    attempt = repo.begin_execution(plan_id, len(plan.units), ctx)

    with pytest.raises(ExecutionInProgressError):
        repo.begin_execution(plan_id, len(plan.units), ctx)
    with pytest.raises(StaleExecutionAttemptError):
        repo.append_execution_slice(
            attempt.result_id, "not-the-current-token", 0, _results(1), ctx
        )
    with pytest.raises(StaleExecutionAttemptError):
        repo.complete_execution(attempt.result_id, "not-the-current-token", 0.1)

    repo.append_execution_slice(
        attempt.result_id, attempt.attempt_id, 0, _results(1), ctx
    )
    repo.abandon_execution(attempt.result_id, attempt.attempt_id, "test cleanup")
    with pytest.raises(PersistenceError, match="not executing"):
        repo.append_execution_slice(
            attempt.result_id, attempt.attempt_id, 1, _results(1), ctx
        )


def test_failed_attempt_retries_with_new_identity(tmp_path: Path) -> None:
    repo = SQLiteRepository(str(tmp_path / "retry.db"))
    ctx = get_dummy_context()
    plan, plan_id = _new_plan(repo, ctx)
    results = _results(len(plan.units), success_from=2)

    first = repo.begin_execution(plan_id, len(plan.units), ctx)
    repo.append_execution_slice(
        first.result_id, first.attempt_id, 0, results[:2], ctx
    )
    failed = repo.fail_execution(
        first.result_id, first.attempt_id, "boom", duration_seconds=0.1
    )
    assert failed.status == "failed"
    assert repo.list_incomplete_executions() == []
    with pytest.raises(ResultsNotFoundError):
        repo.load_execution_result(plan_id, ctx)

    second = repo.begin_execution(plan_id, len(plan.units), ctx)
    assert second.result_id == first.result_id
    assert second.attempt_id != first.attempt_id
    assert second.completed_units == 0
    with pytest.raises(StaleExecutionAttemptError):
        repo.append_execution_slice(
            first.result_id, first.attempt_id, 0, results[:2], ctx
        )

    repo.append_execution_slice(
        second.result_id, second.attempt_id, 0, results[:2], ctx
    )
    repo.append_execution_slice(
        second.result_id, second.attempt_id, 2, results[2:], ctx
    )
    repo.complete_execution(second.result_id, second.attempt_id, 0.2)
    loaded = repo.load_execution_result(plan_id, ctx)
    assert _statistics(loaded.results) == _statistics(results)


def test_interrupted_attempt_requires_explicit_recovery(tmp_path: Path) -> None:
    db_path = tmp_path / "recover.db"
    repo = SQLiteRepository(str(db_path))
    ctx = get_dummy_context()
    plan, plan_id = _new_plan(repo, ctx)
    attempt = repo.begin_execution(plan_id, len(plan.units), ctx)
    repo.append_execution_slice(
        attempt.result_id, attempt.attempt_id, 0, _results(1), ctx
    )

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "UPDATE execution_results SET updated_at = ? WHERE result_id = ?",
            ("2000-01-01T00:00:00Z", attempt.result_id),
        )
        conn.commit()

    reopened = SQLiteRepository(str(db_path))
    incomplete = reopened.list_incomplete_executions()
    assert [item.result_id for item in incomplete] == [attempt.result_id]
    assert incomplete[0].attempt_id == attempt.attempt_id
    assert incomplete[0].status == "executing"

    with pytest.raises(ExecutionInProgressError):
        reopened.begin_execution(plan_id, len(plan.units), ctx)

    abandoned = reopened.abandon_execution(
        attempt.result_id, attempt.attempt_id, "operator confirmed process exit"
    )
    assert abandoned.status == "failed"
    assert "operator confirmed process exit" in (abandoned.error or "")
    assert reopened.list_incomplete_executions() == []

    retry = reopened.begin_execution(plan_id, len(plan.units), ctx)
    assert retry.attempt_id != attempt.attempt_id


def test_concurrent_begin_allows_only_one_attempt(tmp_path: Path) -> None:
    db_path = tmp_path / "concurrent_begin.db"
    repo = SQLiteRepository(str(db_path))
    ctx = get_dummy_context()
    plan, plan_id = _new_plan(repo, ctx)
    barrier = threading.Barrier(2)
    outcomes: list[Any] = []
    lock = threading.Lock()

    def starter() -> None:
        local = SQLiteRepository(str(db_path))
        try:
            barrier.wait(timeout=5)
            attempt = local.begin_execution(plan_id, len(plan.units), ctx)
            with lock:
                outcomes.append(attempt)
        except BaseException as exc:
            with lock:
                outcomes.append(exc)

    threads = [threading.Thread(target=starter) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    attempts = [item for item in outcomes if isinstance(item, ExecutionAttempt)]
    errors = [item for item in outcomes if isinstance(item, BaseException)]
    assert len(attempts) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], ExecutionInProgressError)
    assert len(repo.list_incomplete_executions()) == 1


def test_completion_verifies_full_result_coverage(tmp_path: Path) -> None:
    repo = SQLiteRepository(str(tmp_path / "verify.db"))
    ctx = get_dummy_context()
    plan, plan_id = _new_plan(repo, ctx)
    attempt = repo.begin_execution(plan_id, len(plan.units), ctx)
    repo.append_execution_slice(
        attempt.result_id, attempt.attempt_id, 0, _results(2), ctx
    )
    with pytest.raises(PersistenceError, match="before all units"):
        repo.complete_execution(attempt.result_id, attempt.attempt_id, 0.1)

    # Corrupt the persisted rows directly: remove one unit's final row and
    # clear its counter, then completion must reject the inconsistent state.
    with sqlite3.connect(str(tmp_path / "verify.db")) as conn:
        conn.execute(
            "DELETE FROM simulation_results "
            "WHERE execution_result_id = ? AND unit_index = 1",
            (attempt.result_id,),
        )
        conn.execute(
            "UPDATE execution_results SET completed_units = 4, "
            "success_count = 4, failure_count = 0 WHERE result_id = ?",
            (attempt.result_id,),
        )
        conn.commit()
    with pytest.raises(PersistenceError, match="incomplete or inconsistent"):
        repo.complete_execution(attempt.result_id, attempt.attempt_id, 0.1)


def test_concurrent_append_of_same_slice_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "concurrent.db"
    repo = SQLiteRepository(str(db_path))
    ctx = get_dummy_context()
    plan, plan_id = _new_plan(repo, ctx)
    results = _results(len(plan.units))
    attempt = repo.begin_execution(plan_id, len(plan.units), ctx)
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def writer() -> None:
        local = SQLiteRepository(str(db_path))
        try:
            barrier.wait(timeout=5)
            local.append_execution_slice(
                attempt.result_id, attempt.attempt_id, 0, results[:2], ctx
            )
        except BaseException as exc:  # pragma: no cover - diagnostic path
            errors.append(exc)

    threads = [threading.Thread(target=writer) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not errors
    snapshot = repo.get_execution_attempt(attempt.result_id)
    assert snapshot is not None
    assert snapshot.completed_units == 2
    assert snapshot.success_count == 2


def test_legacy_completed_execution_is_rejected(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_v3.db"
    repo = SQLiteRepository(str(db_path))
    ctx = get_dummy_context()
    plan, plan_id = _new_plan(repo, ctx)
    results = _results(len(plan.units))
    from fbf.core.execution.pipeline.simulation import (
        ExperimentDefinition as EngineExperimentDefinition,
        ExperimentRun,
    )
    from fbf.core.execution.pipeline.simulation_context import SimulationContext
    from fbf.core.execution.result import ResearchExecutionResult

    sim_contexts = tuple(
        SimulationContext(
            experiment_name=plan.experiment_definition.name,
            cohort=unit.cohort.start_date.isoformat(),
            start_date=unit.cohort.start_date,
            horizon_months=plan.experiment_definition.horizon_months,
            initial_wealth=plan.experiment_definition.initial_wealth,
            initial_portfolio=unit.initial_portfolio,
            dataset=plan.experiment_definition.dataset,
            allocation_policy=unit.allocation_policy,
            withdrawal_policy=unit.withdrawal_policy,
        )
        for unit in plan.units
    )
    engine = EngineExperimentDefinition(
        name=plan.experiment_definition.name,
        description=plan.experiment_definition.description,
        simulation_contexts=sim_contexts,
    )
    result = ResearchExecutionResult(
        plan=plan,
        experiment_result=ExperimentRun(
            definition=engine, simulation_results=results
        ),
    )
    repo.save_execution_result(plan_id, result, ctx, 1.0)

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("DROP INDEX IF EXISTS idx_results_status")
        for column in (
            "attempt_id",
            "status",
            "updated_at",
            "completed_at",
            "completed_units",
            "error",
        ):
            conn.execute(f"ALTER TABLE execution_results DROP COLUMN {column}")
        conn.execute("DELETE FROM schema_version")
        conn.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (3, ?)",
            ("2024-01-01T00:00:00Z",),
        )
        conn.commit()

    with pytest.raises(CorruptedDatabaseError, match="version 3"):
        SQLiteRepository(str(db_path))
