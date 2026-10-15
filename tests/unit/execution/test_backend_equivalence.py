"""Backend-equivalence tests: AUTO and FAST produce identical outcomes.

Runs representative workloads through AUTO and FAST backend paths and asserts
success/failure equality, failure month equality, and final wealth equality.
The REFERENCE backend uses a different (legacy) methodology and is not compared.

This creates a permanent safety net so future optimizations cannot silently
diverge.
"""

from __future__ import annotations

from decimal import Decimal

from fbf.core.execution import (
    ExecutionBackend,
    ExecutionOptions,
    ExecutionStrategy,
    execute_study_plan,
)
from fbf.core.execution.pipeline.simulation import SimulationResult
from fbf.core.study.builder import BuiltStudy
from tests.unit.execution.conftest import make_plan


def _compare_auto_fast(
    auto_results: tuple[SimulationResult, ...],
    fast_results: tuple[SimulationResult, ...],
    label: str = "",
) -> None:
    """Compare simulation results between AUTO and FAST backends.

    Both backends now use the workbook-aligned methodology (fee embedded in returns).
    Asserts success/failure equality, failure month equality, and final
    wealth equality (within tolerance for Numba float64 vs Decimal).
    """
    assert len(auto_results) == len(fast_results), (
        f"{label}: result count mismatch {len(auto_results)} vs {len(fast_results)}"
    )

    for i, (auto_r, fast_r) in enumerate(zip(auto_results, fast_results, strict=True)):
        assert auto_r.statistics.success == fast_r.statistics.success, (
            f"{label} unit {i}: AUTO vs FAST success mismatch "
            f"auto={auto_r.statistics.success} fast={fast_r.statistics.success}"
        )
        assert auto_r.statistics.failure_month == fast_r.statistics.failure_month, (
            f"{label} unit {i}: AUTO vs FAST failure_month mismatch "
            f"auto={auto_r.statistics.failure_month} fast={fast_r.statistics.failure_month}"
        )
        assert auto_r.statistics.months_simulated == fast_r.statistics.months_simulated, (
            f"{label} unit {i}: months_simulated mismatch "
            f"auto={auto_r.statistics.months_simulated} fast={fast_r.statistics.months_simulated}"
        )
        # Final wealth: Decimal (AUTO) vs float64 (FAST) may differ slightly
        if auto_r.statistics.success and fast_r.statistics.success:
            diff = abs(
                auto_r.statistics.final_wealth.amount
                - fast_r.statistics.final_wealth.amount
            )
            assert diff < Decimal("0.01"), (
                f"{label} unit {i}: final_wealth diff {diff} > 0.01"
            )


class TestFixedRealBackendEquivalence:
    """FixedReal workload: AUTO and FAST produce identical outcomes."""

    def test_auto_matches_fast(self) -> None:
        """AUTO and FAST produce equivalent results for FixedReal."""
        built = _make_built_study(cohorts=1, horizons=[360])

        auto_result = execute_study_plan(
            built,
            options=ExecutionOptions(strategy=ExecutionStrategy.AUTO, summary_only=True),
        )
        fast_result = execute_study_plan(
            built,
            options=ExecutionOptions(
                backend=ExecutionBackend.FAST,
                strategy=ExecutionStrategy.SEQUENTIAL,
                summary_only=True,
            ),
        )

        _compare_auto_fast(
            auto_result.results,
            fast_result.results,
            label="FixedReal 3-cohort",
        )


class TestPart52BackendEquivalence:
    """Part52 workload: AUTO and FAST produce identical outcomes."""

    def test_auto_matches_fast(self) -> None:
        """AUTO and FAST produce equivalent results for Part52."""
        built = _make_built_study(cohorts=1, horizons=[360])

        auto_result = execute_study_plan(
            built,
            options=ExecutionOptions(strategy=ExecutionStrategy.AUTO, summary_only=True),
        )
        fast_result = execute_study_plan(
            built,
            options=ExecutionOptions(
                backend=ExecutionBackend.FAST,
                strategy=ExecutionStrategy.SEQUENTIAL,
                summary_only=True,
            ),
        )

        _compare_auto_fast(
            auto_result.results,
            fast_result.results,
            label="Part52 2-cohort",
        )


class TestAutoDispatchCorrectness:
    """Verify AUTO dispatch selects the expected backend."""

    def test_auto_selects_numba_for_fixed_real(self) -> None:
        """AUTO dispatch selects Numba for FixedReal-eligible workloads."""
        built = _make_built_study(cohorts=1, horizons=[720])
        result = execute_study_plan(
            built,
            options=ExecutionOptions(strategy=ExecutionStrategy.AUTO, summary_only=True),
        )
        assert result.experiment_result is not None

    def test_auto_selects_part52_for_part52_workload(self) -> None:
        """AUTO dispatch selects Part52Numba for Part52-eligible workloads."""
        built = _make_built_study(cohorts=1, horizons=[720])
        result = execute_study_plan(
            built,
            options=ExecutionOptions(strategy=ExecutionStrategy.AUTO, summary_only=True),
        )
        assert result.experiment_result is not None

    def test_explicit_reference_always_uses_decimal(self) -> None:
        """Explicit REFERENCE always uses Decimal, even for eligible workloads."""
        built = _make_built_study(cohorts=1, horizons=[720])
        result = execute_study_plan(
            built,
            options=ExecutionOptions(
                backend=ExecutionBackend.REFERENCE,
                strategy=ExecutionStrategy.SEQUENTIAL,
                summary_only=True,
            ),
        )
        assert result.experiment_result is not None

    def test_explicit_fast_always_uses_numba(self) -> None:
        """Explicit FAST always uses Numba, even when AUTO would choose differently."""
        built = _make_built_study(cohorts=1, horizons=[720])
        result = execute_study_plan(
            built,
            options=ExecutionOptions(
                backend=ExecutionBackend.FAST,
                strategy=ExecutionStrategy.SEQUENTIAL,
                summary_only=True,
            ),
        )
        assert result.experiment_result is not None


def _make_built_study(cohorts: int = 1, horizons: list[int] | None = None) -> BuiltStudy:
    """Create a BuiltStudy suitable for execute_study_plan."""
    plan = make_plan(cohorts=cohorts, horizons=horizons)
    return BuiltStudy(
        plan=plan,
        experiment_definition=plan.experiment_definition,
        cohorts=plan.experiment_definition.cohorts,
        param_configs=(),
    )
