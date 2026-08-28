"""Determinism and cross-strategy equivalence tests.

Establishes and validates the execution contracts:

- Reference repeatability: bit-exact across runs
- Decimal Fast Path repeatability: bit-exact across runs
- Reference ↔ Decimal Fast Path equivalence: bit-exact where eligible

The Fast Path eligibility contract requires:
- ConstantAllocationPolicy
- FixedRealWithdrawalPolicy
- horizon_months >= 1
- Dataset covers full horizon
- Exactly 2 holdings (1 equity, 1 bond)
- All holdings in dataset index levels
"""

from __future__ import annotations

from fbf.core.execution.pipeline.simulation import SimulationResult
from fbf.core.execution.strategies.fast_path import (
    FastPathSimulationExecutor,
    evaluate_closed_form,
)
from fbf.core.execution.strategies.parallel_executor import (
    ExecutionConfig,
    _create_default_simulation_executor,
    parallel_execute,
    sequential_execute,
)
from fbf.core.execution.strategies.reference import (
    ReferenceSimulationExecutor,
)

from .conftest import make_context, make_dataset, make_engine_def, make_plan

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_reference_result_identical(
    a: SimulationResult,
    b: SimulationResult,
    msg: str,
) -> None:
    """Assert two Reference results are bit-exact identical."""
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


def _assert_decimal_fast_path_exact(
    ref: SimulationResult,
    fp: SimulationResult,
    msg: str,
) -> None:
    """Assert Decimal Fast Path is bit-exact with Reference."""
    assert ref.statistics.success == fp.statistics.success, f"{msg}: success differs"
    assert ref.statistics.failure_month == fp.statistics.failure_month, (
        f"{msg}: failure_month differs"
    )
    assert ref.statistics.months_simulated == fp.statistics.months_simulated, (
        f"{msg}: months_simulated differs"
    )
    assert ref.statistics.final_wealth == fp.statistics.final_wealth, (
        f"{msg}: final_wealth differs (Decimal should be bit-exact)"
    )



# ---------------------------------------------------------------------------
# Reference Repeatability
# ---------------------------------------------------------------------------


class TestReferenceRepeatability:
    """Repeated Reference execution produces bit-exact results."""

    def test_sequential_repeated_execution(self) -> None:
        """Two sequential Reference runs produce identical results."""
        dataset = make_dataset(721)
        contexts = [make_context(dataset, 720, w=0.5, r=0.04)]
        engine_def = make_engine_def(contexts)
        executor = _create_default_simulation_executor()

        run_a = executor.execute(engine_def)
        run_b = executor.execute(engine_def)

        assert len(run_a.simulation_results) == len(run_b.simulation_results)
        for i, (a, b) in enumerate(
            zip(run_a.simulation_results, run_b.simulation_results, strict=True)
        ):
            _assert_reference_result_identical(a, b, f"sequential run {i}")

    def test_sequential_execute_repeated(self) -> None:
        """sequential_execute() produces identical results across calls."""
        plan = make_plan(cohorts=1, horizons=[720])
        result_a = sequential_execute(plan)
        result_b = sequential_execute(plan)

        assert len(result_a.results) == len(result_b.results)
        for i, (a, b) in enumerate(
            zip(result_a.results, result_b.results, strict=True)
        ):
            _assert_reference_result_identical(a, b, f"sequential_execute run {i}")

    def test_parallel_matches_sequential(self) -> None:
        """Parallel Reference execution is bit-for-bit identical to sequential."""
        plan = make_plan(cohorts=2, horizons=[720])
        seq_result = sequential_execute(plan)
        cfg = ExecutionConfig(use_processes=False, max_workers=2)
        par_result = parallel_execute(plan, config=cfg)

        assert len(seq_result.results) == len(par_result.results)
        for i, (s, p) in enumerate(
            zip(seq_result.results, par_result.results, strict=True)
        ):
            _assert_reference_result_identical(s, p, f"parallel vs sequential unit {i}")


# ---------------------------------------------------------------------------
# Decimal Fast Path Repeatability
# ---------------------------------------------------------------------------


class TestDecimalFastPathRepeatability:
    """Repeated Decimal Fast Path execution produces bit-exact results."""

    def test_decimal_fast_path_repeated_execution(self) -> None:
        """Two Decimal Fast Path runs produce identical results."""
        dataset = make_dataset(721)
        contexts = [make_context(dataset, 720, w=0.5, r=0.04)]
        engine_def = make_engine_def(contexts)
        executor = FastPathSimulationExecutor()

        run_a = executor.execute(engine_def)
        run_b = executor.execute(engine_def)

        assert len(run_a.simulation_results) == len(run_b.simulation_results)
        for i, (a, b) in enumerate(
            zip(run_a.simulation_results, run_b.simulation_results, strict=True)
        ):
            _assert_reference_result_identical(a, b, f"decimal fast path run {i}")

    def test_decimal_closed_form_repeated(self) -> None:
        """evaluate_closed_form() produces identical results across calls."""
        dataset = make_dataset(721)
        context = make_context(dataset, 720, w=0.5, r=0.04)

        result_a = evaluate_closed_form(context)
        result_b = evaluate_closed_form(context)

        _assert_reference_result_identical(result_a, result_b, "decimal closed form")


# ---------------------------------------------------------------------------
# Reference ↔ Decimal Fast Path Equivalence
# ---------------------------------------------------------------------------


class TestReferenceDecimalEquivalence:
    """Decimal Fast Path is bit-exact with Reference where eligible."""

    def test_decimal_matches_reference_single_context(self) -> None:
        """Decimal Fast Path matches Reference for a single eligible context."""
        dataset = make_dataset(721)
        context = make_context(dataset, 720, w=0.5, r=0.04)
        engine_def = make_engine_def([context])

        ref_executor = _create_default_simulation_executor()
        fp_executor = FastPathSimulationExecutor()

        ref_run = ref_executor.execute(engine_def)
        fp_run = fp_executor.execute(engine_def)

        assert len(ref_run.simulation_results) == len(fp_run.simulation_results)
        for i, (r, f) in enumerate(
            zip(ref_run.simulation_results, fp_run.simulation_results, strict=True)
        ):
            _assert_decimal_fast_path_exact(r, f, f"decimal vs reference unit {i}")

    def test_decimal_matches_reference_grid(self) -> None:
        """Decimal Fast Path matches Reference across a parameter grid."""
        dataset = make_dataset(721)
        weights = [0.5, 0.25, 0.0]
        rates = [0.04, 0.05]
        horizons = [361, 720]

        contexts = [
            make_context(dataset, h, w, r)
            for w in weights
            for r in rates
            for h in horizons
        ]
        engine_def = make_engine_def(contexts)

        ref_executor = _create_default_simulation_executor()
        fp_executor = FastPathSimulationExecutor()

        ref_run = ref_executor.execute(engine_def)
        fp_run = fp_executor.execute(engine_def)

        assert len(ref_run.simulation_results) == len(fp_run.simulation_results)
        for i, (r, f) in enumerate(
            zip(ref_run.simulation_results, fp_run.simulation_results, strict=True)
        ):
            _assert_decimal_fast_path_exact(r, f, f"grid unit {i}")

    def test_reference_matches_reference_engine(self) -> None:
        """ReferenceSimulationExecutor matches reference engine."""
        plan = make_plan(cohorts=2, horizons=[361, 720])
        seq_result = sequential_execute(plan)
        reference_executor = ReferenceSimulationExecutor()
        reference_result = sequential_execute(plan, simulation_executor=reference_executor)

        assert len(seq_result.results) == len(reference_result.results)
        for i, (s, c) in enumerate(
            zip(seq_result.results, reference_result.results, strict=True)
        ):
            _assert_reference_result_identical(s, c, f"reference vs reference unit {i}")

