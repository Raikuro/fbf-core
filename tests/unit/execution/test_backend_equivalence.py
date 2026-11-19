"""Numba dispatch stability tests.

Every study plan executes through the single Numba dispatch path.  These tests
assert that option variations and repeated executions do not alter results.
"""

from __future__ import annotations

from fbf.core.execution import ExecutionOptions, execute_study_plan
from fbf.core.execution.pipeline.simulation import SimulationResult
from fbf.core.study.builder import BuiltStudy
from tests.unit.execution.conftest import make_plan


def _assert_results_identical(
    first_results: tuple[SimulationResult, ...],
    second_results: tuple[SimulationResult, ...],
    label: str = "",
) -> None:
    assert len(first_results) == len(second_results), (
        f"{label}: result count mismatch {len(first_results)} vs "
        f"{len(second_results)}"
    )

    for i, (first, second) in enumerate(
        zip(first_results, second_results, strict=True)
    ):
        assert first.statistics.success == second.statistics.success, (
            f"{label} unit {i}: success mismatch"
        )
        assert first.statistics.failure_month == second.statistics.failure_month, (
            f"{label} unit {i}: failure_month mismatch"
        )
        assert (
            first.statistics.months_simulated == second.statistics.months_simulated
        ), f"{label} unit {i}: months_simulated mismatch"
        assert first.statistics.final_wealth == second.statistics.final_wealth, (
            f"{label} unit {i}: final_wealth mismatch"
        )


class TestNumbaDispatchStability:
    """The single Numba path produces stable results across option variations."""

    def test_default_and_summary_only_match(self) -> None:
        built = _make_built_study(cohorts=1, horizons=[360])

        full_result = execute_study_plan(built, ExecutionOptions())
        summary_result = execute_study_plan(
            built,
            ExecutionOptions(summary_only=True),
        )

        _assert_results_identical(
            full_result.results,
            summary_result.results,
            label="FixedReal",
        )

    def test_repeated_dispatch_is_stable(self) -> None:
        built = _make_built_study(cohorts=2, horizons=[361, 720])

        first_result = execute_study_plan(
            built,
            ExecutionOptions(summary_only=True),
        )
        second_result = execute_study_plan(
            built,
            ExecutionOptions(summary_only=True),
        )

        _assert_results_identical(
            first_result.results,
            second_result.results,
            label="repeated dispatch",
        )


def _make_built_study(cohorts: int = 1, horizons: list[int] | None = None) -> BuiltStudy:
    """Create a BuiltStudy suitable for execute_study_plan."""
    plan = make_plan(cohorts=cohorts, horizons=horizons)
    return BuiltStudy(
        plan=plan,
        experiment_definition=plan.experiment_definition,
        cohorts=plan.experiment_definition.cohorts,
        param_configs=(),
    )
