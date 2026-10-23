"""Determinism and parallel-equivalence tests for the Numba engine.

Establishes and validates the execution contracts:

- Repeated sequential execution is bit-exact.
- Process-parallel execution is bit-exact with sequential execution.
"""

from __future__ import annotations

from fbf.core.execution.pipeline.simulation import SimulationResult
from fbf.core.execution.strategies.numba_executor import NumbaSimulationExecutor
from fbf.core.execution.strategies.parallel_executor import (
    ExecutionConfig,
    parallel_execute,
    sequential_execute,
)

from .conftest import make_context, make_dataset, make_engine_def, make_plan


def _assert_result_identical(
    a: SimulationResult,
    b: SimulationResult,
    msg: str,
) -> None:
    """Assert two results are bit-exact identical."""
    assert a.statistics.success == b.statistics.success, f"{msg}: success differs"
    assert a.statistics.failure_month == b.statistics.failure_month, (
        f"{msg}: failure_month differs"
    )
    assert a.statistics.months_simulated == b.statistics.months_simulated, (
        f"{msg}: months_simulated differs"
    )
    assert a.statistics.final_wealth == b.statistics.final_wealth, (
        f"{msg}: final_wealth differs"
    )
    assert len(a.timeline.monthly_results) == len(b.timeline.monthly_results), (
        f"{msg}: timeline length differs"
    )
    for i, (ra, rb) in enumerate(
        zip(a.timeline.monthly_results, b.timeline.monthly_results, strict=True)
    ):
        assert ra == rb, f"{msg}: monthly result {i} differs"


class TestNumbaRepeatability:
    """Plan-level Numba execution is deterministic and parallel-safe."""

    def test_sequential_execute_repeated(self) -> None:
        """Two sequential Numba runs produce identical results."""
        plan = make_plan(cohorts=2, horizons=[361, 720])
        executor = NumbaSimulationExecutor()

        result_a = sequential_execute(plan, simulation_executor=executor)
        result_b = sequential_execute(plan, simulation_executor=executor)

        assert len(result_a.results) == len(result_b.results)
        for i, (a, b) in enumerate(
            zip(result_a.results, result_b.results, strict=True)
        ):
            _assert_result_identical(a, b, f"numba sequential run {i}")

    def test_direct_execute_repeated(self) -> None:
        """Direct Numba execution produces identical results across calls."""
        dataset = make_dataset(721)
        context = make_context(dataset, 720, w=0.5, r=0.04)
        engine_def = make_engine_def([context])
        executor = NumbaSimulationExecutor()

        run_a = executor.execute(engine_def)
        run_b = executor.execute(engine_def)

        for i, (a, b) in enumerate(
            zip(run_a.simulation_results, run_b.simulation_results, strict=True)
        ):
            _assert_result_identical(a, b, f"direct run {i}")

    def test_parallel_matches_sequential(self) -> None:
        """Parallel Numba execution is identical to sequential execution."""
        plan = make_plan(cohorts=2, horizons=[361, 720])
        seq_result = sequential_execute(
            plan, simulation_executor=NumbaSimulationExecutor()
        )
        cfg = ExecutionConfig(use_processes=True, max_workers=2)
        par_result = parallel_execute(
            plan,
            config=cfg,
            simulation_executor=NumbaSimulationExecutor(),
        )

        assert len(seq_result.results) == len(par_result.results)
        for i, (s, p) in enumerate(
            zip(seq_result.results, par_result.results, strict=True)
        ):
            _assert_result_identical(s, p, f"numba parallel unit {i}")
