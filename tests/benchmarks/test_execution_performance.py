"""Execution performance benchmarks.

Measures executor framework overhead — plan translation, result
aggregation, and parallel dispatch — through the public executor API.

Uses a fast synthetic executor (same pattern as P4.2 E2E tests) to
isolate framework costs from pipeline execution time.
"""

from __future__ import annotations

import gc
import time
from pathlib import Path
from typing import Any

import pytest

from fbf.core.execution.pipeline.executor import SimulationExecutor
from fbf.core.execution.pipeline.simulation import ExperimentRun
from fbf.core.execution.result import ResearchExecutionResult
from fbf.core.execution.strategies import ExecutionConfig
from fbf.core.execution.strategies.parallel_executor import (
    parallel_execute,
    sequential_execute,
)
from fbf.core.persistence.studies.sqlite.sqlite_repository import ExperimentIdentity
from fbf.core.study.plan import ResearchPlan

from .conftest import (
    make_benchmark_plan,
    make_benchmark_repo,
    make_persistence_context,
)
from .helpers import make_simulation_result

# ---------------------------------------------------------------------------
# Fast synthetic executor for framework benchmarking
# ---------------------------------------------------------------------------


class BenchmarkSimulationExecutor(SimulationExecutor):
    """Executor that returns pre-built results instantly.

    Measures ResearchExecutor translation + aggregation overhead
    without running the real pipeline (which requires state fields
    not set in the initial state).
    """

    def __init__(self) -> None:
        pass  # skip SimulationExecutor.__init__

    def execute(self, definition: Any) -> ExperimentRun:
        contexts = definition.simulation_contexts
        results = tuple(make_simulation_result() for _ in contexts)
        return ExperimentRun(definition=definition, simulation_results=results)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def bench_executor() -> BenchmarkSimulationExecutor:
    return BenchmarkSimulationExecutor()


# ===================================================================
# 1. Execution Determinism
# ===================================================================


class TestExecutionDeterminism:
    """Repeated execution through the executor framework is deterministic."""

    def test_sequential_execution_is_deterministic(
        self, bm_small_plan: ResearchPlan, bench_executor: BenchmarkSimulationExecutor
    ) -> None:
        result_a = sequential_execute(bm_small_plan, simulation_executor=bench_executor)
        result_b = sequential_execute(bm_small_plan, simulation_executor=bench_executor)

        assert len(result_a.results) == len(result_b.results)
        for a, b in zip(result_a.results, result_b.results, strict=True):
            assert a.statistics == b.statistics

    def test_parallel_execution_is_deterministic(
        self, bm_small_plan: ResearchPlan, bench_executor: BenchmarkSimulationExecutor
    ) -> None:
        cfg = ExecutionConfig(use_processes=False, max_workers=2)
        result_a = parallel_execute(bm_small_plan, config=cfg, simulation_executor=bench_executor)
        result_b = parallel_execute(bm_small_plan, config=cfg, simulation_executor=bench_executor)

        assert len(result_a.results) == len(result_b.results)
        for a, b in zip(result_a.results, result_b.results, strict=True):
            assert a.statistics == b.statistics


# ===================================================================
# 2. Parallel Correctness
# ===================================================================


class TestParallelCorrectness:
    """Parallel execution produces identical results to sequential."""

    def test_parallel_matches_sequential(
        self, bm_small_plan: ResearchPlan, bench_executor: BenchmarkSimulationExecutor
    ) -> None:
        seq_result = sequential_execute(bm_small_plan, simulation_executor=bench_executor)
        cfg = ExecutionConfig(use_processes=False, max_workers=2)
        par_result = parallel_execute(bm_small_plan, config=cfg, simulation_executor=bench_executor)

        assert len(par_result.results) == len(seq_result.results)
        for i, (s, p) in enumerate(zip(seq_result.results, par_result.results, strict=True)):
            assert s.statistics == p.statistics, f"Unit {i} statistics differ"

    def test_different_worker_counts_produce_same_results(
        self, bm_medium_plan: ResearchPlan, bench_executor: BenchmarkSimulationExecutor
    ) -> None:
        seq_result = sequential_execute(bm_medium_plan, simulation_executor=bench_executor)
        for workers in [1, 2, 4]:
            cfg = ExecutionConfig(use_processes=False, max_workers=workers)
            par_result = parallel_execute(
                bm_medium_plan, config=cfg, simulation_executor=bench_executor,
            )
            for i, (s, p) in enumerate(zip(seq_result.results, par_result.results, strict=True)):
                assert s.statistics == p.statistics, f"Unit {i} mismatch at workers={workers}"


# ===================================================================
# 3. Plan Translation Overhead
# ===================================================================


class TestPlanTranslationOverhead:
    """Time spent translating ResearchPlan units into SimulationContexts."""

    def test_translation_overhead_small(
        self, bm_small_plan: ResearchPlan, bench_executor: BenchmarkSimulationExecutor
    ) -> None:
        gc.collect()
        t0 = time.perf_counter()
        result = sequential_execute(bm_small_plan, simulation_executor=bench_executor)
        elapsed = time.perf_counter() - t0
        units = len(bm_small_plan.units)
        print(
            f"\n[BENCHMARK] translate + exec (2 units): {elapsed:.6f}s"
            f"  ({elapsed / units:.6f}s/unit)"
        )
        assert isinstance(result, ResearchExecutionResult)
        assert len(result.results) == units

    def test_translation_scales_with_units(
        self, bm_dataset_small: Any, bench_executor: BenchmarkSimulationExecutor
    ) -> None:
        for num_units in [2, 4, 8]:
            plan = make_benchmark_plan(
                num_units=num_units, horizon_months=24, dataset=bm_dataset_small,
            )
            gc.collect()
            t0 = time.perf_counter()
            sequential_execute(plan, simulation_executor=bench_executor)
            elapsed = time.perf_counter() - t0
            print(
                f"\n[BENCHMARK] translate + exec ({num_units} units):"
                f" {elapsed:.6f}s  ({elapsed / num_units:.6f}s/unit)"
            )


# ===================================================================
# 4. Parallel Framework Overhead
# ===================================================================


class TestParallelFrameworkOverhead:
    """Time cost of the parallel dispatch framework itself."""

    def test_parallel_dispatch_time(
        self, bm_medium_plan: ResearchPlan, bench_executor: BenchmarkSimulationExecutor
    ) -> None:
        gc.collect()
        t0 = time.perf_counter()
        sequential_execute(bm_medium_plan, simulation_executor=bench_executor)
        seq_time = time.perf_counter() - t0

        gc.collect()
        cfg = ExecutionConfig(use_processes=False, max_workers=2)
        t0 = time.perf_counter()
        parallel_execute(bm_medium_plan, config=cfg, simulation_executor=bench_executor)
        par_time = time.perf_counter() - t0

        ratio = par_time / seq_time if seq_time > 0 else 0
        print(
            f"\n[BENCHMARK] Dispatch overhead (4 units): "
            f"seq={seq_time:.6f}s par={par_time:.6f}s "
            f"par/seq={ratio:.2f}x"
        )

    def test_parallel_with_large_plan_overhead(
        self, bm_plan_8_units: ResearchPlan, bench_executor: BenchmarkSimulationExecutor
    ) -> None:
        cfg2 = ExecutionConfig(use_processes=False, max_workers=2)
        cfg4 = ExecutionConfig(use_processes=False, max_workers=4)

        gc.collect()
        t0 = time.perf_counter()
        parallel_execute(bm_plan_8_units, config=cfg2, simulation_executor=bench_executor)
        t2 = time.perf_counter() - t0

        gc.collect()
        t0 = time.perf_counter()
        parallel_execute(bm_plan_8_units, config=cfg4, simulation_executor=bench_executor)
        t4 = time.perf_counter() - t0

        print(
            f"\n[BENCHMARK] Parallel dispatch (8 units): "
            f"workers=2 -> {t2:.6f}s  workers=4 -> {t4:.6f}s"
        )


# ===================================================================
# 5. Persistence + Execution Integration
# ===================================================================


class TestExecutionWithPersistence:
    """Time the full execute + persist workflow."""

    def test_execute_and_persist(
        self,
        bm_small_plan: ResearchPlan,
        bm_dataset_small: Any,
        bench_executor: BenchmarkSimulationExecutor,
        tmp_path: Path,
    ) -> None:
        ctx = make_persistence_context(bm_dataset_small)
        repo = make_benchmark_repo(tmp_path / "exec_persist.db")

        gc.collect()
        t0 = time.perf_counter()
        result = sequential_execute(bm_small_plan, simulation_executor=bench_executor)
        exp_id = repo.save_experiment(
            ExperimentIdentity(name="exec-persist", revision="v1"),
            bm_small_plan.experiment_definition,
            ctx,
        )
        plan_id = repo.save_plan(bm_small_plan, exp_id, ctx)
        repo.save_execution_result(plan_id, result, ctx, duration_seconds=0.5)
        elapsed = time.perf_counter() - t0
        print(f"\n[BENCHMARK] execute + persist (2 units): {elapsed:.6f}s")


# ===================================================================
# 6. summary_only payload reduction
# ===================================================================


class TestSummaryOnlyOverhead:
    """summary_only keeps aggregate statistics while dropping timelines."""

    def test_summary_only_reduces_transfer_payload(
        self, bm_medium_plan: ResearchPlan, bench_executor: BenchmarkSimulationExecutor
    ) -> None:
        import pickle

        full = sequential_execute(bm_medium_plan, simulation_executor=bench_executor)
        summary = sequential_execute(
            bm_medium_plan, simulation_executor=bench_executor, summary_only=True
        )

        full_bytes = len(pickle.dumps(full.results[0]))
        summary_bytes = len(pickle.dumps(summary.results[0]))
        print(
            f"\n[BENCHMARK] payload per result: full={full_bytes}B "
            f"summary={summary_bytes}B  ratio={full_bytes / max(summary_bytes, 1):.0f}x"
        )
        assert summary_bytes <= full_bytes
        for full_result, summary_result in zip(full.results, summary.results, strict=True):
            assert summary_result.timeline.monthly_results == ()
            assert summary_result.statistics == full_result.statistics
