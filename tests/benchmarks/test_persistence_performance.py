"""Persistence performance benchmarks.

Measures SQLiteRepository read/write throughput through the public
repository API using deterministic synthetic data.

Execution results are pre-built via ``make_execution_result``
(identical pattern to P4.2 E2E tests), isolating persistence time
from execution time.
"""

from __future__ import annotations

import gc
import time
from pathlib import Path
from typing import Any

from infrastructure.persistence import (
    PersistenceReconstructionContext,
    SQLiteRepository,
)
from infrastructure.persistence.sqlite_repository import ExperimentIdentity
from research.domain.plan import ResearchPlan
from research.orchestration.result import ResearchExecutionResult

from .conftest import (
    make_benchmark_repo,
)
from .helpers import make_execution_result

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _identity(name: str = "perf-test") -> ExperimentIdentity:
    return ExperimentIdentity(name=name, revision="v1")


def _save_all(
    repo: SQLiteRepository,
    plan: ResearchPlan,
    result: ResearchExecutionResult,
    ctx: PersistenceReconstructionContext,
    name: str = "perf-test",
) -> Any:
    exp_id = repo.save_experiment(_identity(name), plan.experiment_definition, ctx)
    plan_id = repo.save_plan(plan, exp_id, ctx)
    repo.save_execution_result(plan_id, result, ctx, duration_seconds=0.5)
    return exp_id


# ===================================================================
# 1. Single-Operation Timing
# ===================================================================


class TestSingleOperationTiming:
    """Time each persistence operation independently."""

    def test_save_experiment_time(
        self,
        bm_small_plan: ResearchPlan,
        bm_persistence_context: PersistenceReconstructionContext,
        tmp_path: Path,
    ) -> None:
        repo = make_benchmark_repo(tmp_path / "save_exp.db")
        ctx = bm_persistence_context

        gc.collect()
        t0 = time.perf_counter()
        exp_id = repo.save_experiment(
            _identity("single-exp"), bm_small_plan.experiment_definition, ctx
        )
        elapsed = time.perf_counter() - t0
        print(f"\n[BENCHMARK] save_experiment: {elapsed:.4f}s")
        assert exp_id is not None

    def test_save_plan_time(
        self,
        bm_small_plan: ResearchPlan,
        bm_persistence_context: PersistenceReconstructionContext,
        tmp_path: Path,
    ) -> None:
        repo = make_benchmark_repo(tmp_path / "save_plan.db")
        ctx = bm_persistence_context
        exp_id = repo.save_experiment(
            _identity("single-plan"), bm_small_plan.experiment_definition, ctx
        )

        gc.collect()
        t0 = time.perf_counter()
        plan_id = repo.save_plan(bm_small_plan, exp_id, ctx)
        elapsed = time.perf_counter() - t0
        print(f"\n[BENCHMARK] save_plan: {elapsed:.4f}s")
        assert plan_id is not None

    def test_save_result_time(
        self,
        bm_small_plan: ResearchPlan,
        bm_persistence_context: PersistenceReconstructionContext,
        tmp_path: Path,
    ) -> None:
        repo = make_benchmark_repo(tmp_path / "save_result.db")
        ctx = bm_persistence_context
        exp_id = repo.save_experiment(
            _identity("single-result"), bm_small_plan.experiment_definition, ctx
        )
        plan_id = repo.save_plan(bm_small_plan, exp_id, ctx)
        result = make_execution_result(bm_small_plan)

        gc.collect()
        t0 = time.perf_counter()
        result_id = repo.save_execution_result(plan_id, result, ctx, duration_seconds=0.5)
        elapsed = time.perf_counter() - t0
        print(f"\n[BENCHMARK] save_execution_result: {elapsed:.4f}s")
        assert result_id is not None

    def test_load_plan_time(
        self,
        bm_small_plan: ResearchPlan,
        bm_persistence_context: PersistenceReconstructionContext,
        tmp_path: Path,
    ) -> None:
        repo = make_benchmark_repo(tmp_path / "load_plan.db")
        ctx = bm_persistence_context
        exp_id = repo.save_experiment(
            _identity("load-plan"), bm_small_plan.experiment_definition, ctx
        )
        plan_id = repo.save_plan(bm_small_plan, exp_id, ctx)

        gc.collect()
        t0 = time.perf_counter()
        loaded = repo.load_plan(plan_id, ctx)
        elapsed = time.perf_counter() - t0
        print(f"\n[BENCHMARK] load_plan: {elapsed:.4f}s")
        assert loaded is not None
        assert len(loaded.units) == len(bm_small_plan.units)


# ===================================================================
# 2. Write Pipeline Timing
# ===================================================================


class TestWritePipelineTiming:
    """Time the full experiment + plan + result write pipeline."""

    def test_write_pipeline_small(
        self,
        bm_small_plan: ResearchPlan,
        bm_persistence_context: PersistenceReconstructionContext,
        tmp_path: Path,
    ) -> None:
        repo = make_benchmark_repo(tmp_path / "pipe_small.db")
        ctx = bm_persistence_context
        result = make_execution_result(bm_small_plan)

        gc.collect()
        t0 = time.perf_counter()
        _save_all(repo, bm_small_plan, result, ctx, name="pipe-small")
        elapsed = time.perf_counter() - t0
        print(f"\n[BENCHMARK] write_pipeline (2 units): {elapsed:.4f}s")

    def test_write_pipeline_medium(
        self,
        bm_medium_plan: ResearchPlan,
        bm_persistence_context: PersistenceReconstructionContext,
        tmp_path: Path,
    ) -> None:
        repo = make_benchmark_repo(tmp_path / "pipe_medium.db")
        ctx = bm_persistence_context
        result = make_execution_result(bm_medium_plan)

        gc.collect()
        t0 = time.perf_counter()
        _save_all(repo, bm_medium_plan, result, ctx, name="pipe-medium")
        elapsed = time.perf_counter() - t0
        print(f"\n[BENCHMARK] write_pipeline (4 units, 60mo): {elapsed:.4f}s")


# ===================================================================
# 3. Persistence Round-Trip Integrity
# ===================================================================


class TestPersistenceRoundTripIntegrity:
    """Save/load round-trip preserves data across all operations."""

    def test_round_trip_preserves_results(
        self,
        bm_small_plan: ResearchPlan,
        bm_persistence_context: PersistenceReconstructionContext,
        tmp_path: Path,
    ) -> None:
        repo = make_benchmark_repo(tmp_path / "rt.db")
        ctx = bm_persistence_context
        original_result = make_execution_result(bm_small_plan)
        _save_all(repo, bm_small_plan, original_result, ctx, name="roundtrip")

        exp_id = repo.find_experiment_by_name("roundtrip")
        assert exp_id is not None
        plan_id = repo.find_plan_by_experiment(exp_id)
        assert plan_id is not None
        loaded_result_id = repo.find_result_by_plan(plan_id)
        assert loaded_result_id is not None

        loaded = repo.load_execution_result(loaded_result_id, ctx)
        assert len(loaded.results) == len(original_result.results)
        for orig, lod in zip(original_result.results, loaded.results, strict=True):
            assert orig.statistics == lod.statistics
