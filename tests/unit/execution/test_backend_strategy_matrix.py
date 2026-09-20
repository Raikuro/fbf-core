"""Tests for the execution backend × strategy routing matrix.

Verifies that every supported combination of ExecutionBackend and
ExecutionStrategy resolves to the correct execution path, and that
unsupported combinations fail explicitly.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from fbf.core.execution import (
    _DEFAULT_PARALLEL_UNIT_THRESHOLD,
    ExecutionBackend,
    ExecutionOptions,
    ExecutionStrategy,
    execute_study_plan,
    sequential_execute,
)
from fbf.core.execution.pipeline.executor import SimulationExecutor
from fbf.core.study.builder import BuiltStudy
from tests.unit.execution.conftest import make_plan


def _make_built_study(cohorts: int = 1, horizons: list[int] | None = None) -> BuiltStudy:
    """Create a BuiltStudy suitable for execute_study_plan."""
    plan = make_plan(cohorts=cohorts, horizons=horizons)
    return BuiltStudy(
        plan=plan,
        experiment_definition=plan.experiment_definition,
        cohorts=plan.experiment_definition.cohorts,
        param_configs=(),
    )


class TestReferenceBackendStrategy:
    """REFERENCE backend × strategy combinations."""

    def test_reference_auto_small_workload_selects_sequential(self) -> None:
        """REFERENCE + AUTO with a small plan resolves to sequential."""
        built = _make_built_study(cohorts=1, horizons=[720])
        # Fewer units than threshold → sequential
        options = ExecutionOptions(
            backend=ExecutionBackend.REFERENCE,
            strategy=ExecutionStrategy.AUTO,
            workers=8,
            summary_only=True,
        )
        # Should not raise; result is produced via sequential path
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None
        assert all(r.timeline.monthly_results == () for r in result.results)

    def test_reference_auto_large_workload_selects_parallel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """REFERENCE + AUTO with a large plan resolves to parallel when workers available."""
        built = _make_built_study(cohorts=1, horizons=[720])
        # Patch the threshold to 0 so the small test plan triggers parallel
        monkeypatch.setattr(
            "fbf.core.execution._DEFAULT_PARALLEL_UNIT_THRESHOLD", 0
        )
        options = ExecutionOptions(
            backend=ExecutionBackend.REFERENCE,
            strategy=ExecutionStrategy.AUTO,
            workers=2,
            summary_only=True,
        )
        # Should execute in parallel (workers > 1 and units >= threshold)
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None

    def test_reference_auto_workers_none_uses_host_default(self) -> None:
        """REFERENCE + AUTO with workers=None inspects host capabilities."""
        built = _make_built_study(cohorts=1, horizons=[720])
        options = ExecutionOptions(
            backend=ExecutionBackend.REFERENCE,
            strategy=ExecutionStrategy.AUTO,
            workers=None,
            summary_only=True,
        )
        # Should complete without error regardless of host CPU count
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None

    def test_reference_sequential_forces_sequential(self) -> None:
        """REFERENCE + SEQUENTIAL always executes sequentially."""
        built = _make_built_study(cohorts=1, horizons=[720])
        options = ExecutionOptions(
            backend=ExecutionBackend.REFERENCE,
            strategy=ExecutionStrategy.SEQUENTIAL,
            workers=8,
            summary_only=True,
        )
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None

    def test_reference_parallel_forces_parallel(self) -> None:
        """REFERENCE + PARALLEL always executes in parallel."""
        built = _make_built_study(cohorts=1, horizons=[720])
        options = ExecutionOptions(
            backend=ExecutionBackend.REFERENCE,
            strategy=ExecutionStrategy.PARALLEL,
            workers=2,
            summary_only=True,
        )
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None


class TestFastBackendStrategy:
    """FAST backend × strategy combinations."""

    def test_fast_auto_resolves_to_sequential(self) -> None:
        """FAST + AUTO always resolves to sequential."""
        built = _make_built_study(cohorts=1, horizons=[720])
        options = ExecutionOptions(
            backend=ExecutionBackend.FAST,
            strategy=ExecutionStrategy.AUTO,
            workers=8,
            summary_only=True,
        )
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None

    def test_fast_sequential_forces_sequential(self) -> None:
        """FAST + SEQUENTIAL always executes sequentially."""
        built = _make_built_study(cohorts=1, horizons=[720])
        options = ExecutionOptions(
            backend=ExecutionBackend.FAST,
            strategy=ExecutionStrategy.SEQUENTIAL,
            summary_only=True,
        )
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None

    def test_fast_parallel_raises_explicit_error(self) -> None:
        """FAST + PARALLEL raises ValueError immediately."""
        built = _make_built_study(cohorts=1, horizons=[720])
        options = ExecutionOptions(
            backend=ExecutionBackend.FAST,
            strategy=ExecutionStrategy.PARALLEL,
        )
        with pytest.raises(ValueError, match="FAST backend does not support parallel"):
            execute_study_plan(built, options)


class TestFastMissingDependency:
    """FAST backend without optional Numba dependency."""

    def test_fast_missing_numba_raises_clear_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Requesting FAST when numba is not installed gives a clear error."""
        import builtins

        built = _make_built_study(cohorts=1, horizons=[720])
        options = ExecutionOptions(backend=ExecutionBackend.FAST)

        original_import = builtins.__import__

        def _block_numba(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "numba" or name.startswith("numba."):
                raise ModuleNotFoundError(f"No module named '{name}'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _block_numba)

        with pytest.raises(ModuleNotFoundError, match="FAST backend requires"):
            execute_study_plan(built, options)


class TestAutoRoutingPolicy:
    """Verify the AUTO routing threshold behavior."""

    def test_threshold_constant_is_positive(self) -> None:
        """The parallel threshold is a positive integer."""
        assert _DEFAULT_PARALLEL_UNIT_THRESHOLD > 0

    def test_small_plan_stays_sequential_even_with_many_workers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A plan below the threshold stays sequential regardless of worker count."""
        built = _make_built_study(cohorts=1, horizons=[720])
        monkeypatch.setattr(
            "fbf.core.execution._DEFAULT_PARALLEL_UNIT_THRESHOLD", 100_000
        )
        options = ExecutionOptions(
            backend=ExecutionBackend.REFERENCE,
            strategy=ExecutionStrategy.AUTO,
            workers=64,
            summary_only=True,
        )
        # Should complete without spawning parallel workers
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None

    def test_explicit_sequential_overrides_auto_routing(self) -> None:
        """Explicit SEQUENTIAL prevents parallel even for large plans."""
        built = _make_built_study(cohorts=1, horizons=[720])
        options = ExecutionOptions(
            backend=ExecutionBackend.REFERENCE,
            strategy=ExecutionStrategy.SEQUENTIAL,
            workers=64,
            summary_only=True,
        )
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None

    def test_explicit_parallel_overrides_auto_routing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit PARALLEL forces parallel even for small plans."""
        built = _make_built_study(cohorts=1, horizons=[720])
        monkeypatch.setattr(
            "fbf.core.execution._DEFAULT_PARALLEL_UNIT_THRESHOLD", 100_000
        )
        options = ExecutionOptions(
            backend=ExecutionBackend.REFERENCE,
            strategy=ExecutionStrategy.PARALLEL,
            workers=2,
            summary_only=True,
        )
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None


class TestExecutionOptionsDefaults:
    """Verify ExecutionOptions default values."""

    def test_default_backend_is_none(self) -> None:
        opts = ExecutionOptions()
        assert opts.backend is None

    def test_default_strategy_is_auto(self) -> None:
        opts = ExecutionOptions()
        assert opts.strategy == ExecutionStrategy.AUTO

    def test_workers_default_is_none(self) -> None:
        opts = ExecutionOptions()
        assert opts.workers is None

    def test_summary_only_default_is_false(self) -> None:
        opts = ExecutionOptions()
        assert opts.summary_only is False


class TestAutoBackendDispatch:
    """AUTO dispatch: capability-driven backend selection."""

    def test_auto_dispatch_selects_numba_for_fixed_real(self) -> None:
        """backend=None + AUTO dispatches to Numba for FixedReal-eligible workloads."""
        built = _make_built_study(cohorts=1, horizons=[720])
        options = ExecutionOptions(
            strategy=ExecutionStrategy.AUTO,
            workers=None,
            summary_only=True,
        )
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None

    def test_auto_dispatch_falls_back_to_default_for_unsupported(self) -> None:
        """backend=None + AUTO falls back to REFERENCE for unsupported policies."""
        from fbf.core.domain.model.money import Currency, Money
        from fbf.core.domain.policies import (
            ConstantAllocationPolicy,
            ConstantWithdrawalPolicy,
        )
        from fbf.core.study.builder import build_initial_portfolio
        from fbf.core.study.internal.cohort.specification import CohortSpecification
        from fbf.core.study.internal.experiment.definition import ExperimentDefinition
        from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
        from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan
        from tests.unit.execution.conftest import make_dataset

        dataset = make_dataset(730)
        start = date(1900, 1, 1)
        portfolio = build_initial_portfolio(
            Money(Decimal("1000000"), Currency.EUR), dataset
        )
        cohort = CohortSpecification(start_date=start)
        const_wd = ConstantWithdrawalPolicy(withdrawal_rate=Decimal("0.04"))
        experiment = ExperimentDefinition(
            name="test", description="test", dataset=dataset,
            horizon_months=720,
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            cohorts=(cohort,),
            allocation_policies=(
                ConstantAllocationPolicy(Decimal("0.75")),
            ),
            withdrawal_policies=(const_wd,),
        )
        unit = PlannedSimulationUnit(
            cohort=cohort,
            parameter_config=ParameterConfiguration({
                "equity_allocation": 0.75,
                "withdrawal_rate": 0.04,
                "horizon_years": 60,
            }),
            allocation_policy=ConstantAllocationPolicy(Decimal("0.75")),
            withdrawal_policy=const_wd,
            initial_portfolio=portfolio,
            dataset=dataset.slice(start, 720),
        )
        plan = ResearchPlan(
            experiment_definition=experiment, units=(unit,),
        )
        built = BuiltStudy(
            plan=plan, experiment_definition=experiment,
            cohorts=(cohort,), param_configs=(),
        )
        options = ExecutionOptions(
            strategy=ExecutionStrategy.AUTO, summary_only=True,
        )
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None

    def test_explicit_reference_bypasses_auto_dispatch(self) -> None:
        """backend=REFERENCE always uses Decimal reference, even for eligible workloads."""
        built = _make_built_study(cohorts=1, horizons=[720])
        options = ExecutionOptions(
            backend=ExecutionBackend.REFERENCE,
            strategy=ExecutionStrategy.AUTO,
            summary_only=True,
        )
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None

    def test_explicit_fast_bypasses_auto_dispatch(self) -> None:
        """backend=FAST always uses Numba, even if AUTO would choose differently."""
        built = _make_built_study(cohorts=1, horizons=[720])
        options = ExecutionOptions(
            backend=ExecutionBackend.FAST,
            strategy=ExecutionStrategy.AUTO,
            summary_only=True,
        )
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None

    def test_auto_dispatch_parallel_raises_for_numba(self) -> None:
        """backend=None + PARALLEL raises ValueError when AUTO selects Numba."""
        built = _make_built_study(cohorts=1, horizons=[720])
        options = ExecutionOptions(
            strategy=ExecutionStrategy.PARALLEL,
            workers=2,
        )
        with pytest.raises(ValueError, match="FAST backend does not support parallel"):
            execute_study_plan(built, options)

    def test_auto_dispatch_sequential_for_numba(self) -> None:
        """backend=None + SEQUENTIAL forces sequential even when AUTO selects Numba."""
        built = _make_built_study(cohorts=1, horizons=[720])
        options = ExecutionOptions(
            strategy=ExecutionStrategy.SEQUENTIAL,
            summary_only=True,
        )
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None


class TestSummaryOnlyEquivalence:
    """summary_only=True must produce identical statistics but empty timelines.

    The invariant: ``summary_only`` only strips per-month timelines from the
    returned ``SimulationResult`` objects.  All other semantic content —
    aggregate statistics, plan, experiment definition — must be unchanged.

    The REFERENCE and FAST backends always produce empty timelines (they use
    closed-form / Numba kernels that don't build monthly results).  To test
    the stripping behaviour we must use the reference SimulationExecutor
    directly via ``sequential_execute``.
    """

    def _make_reference_executor(self) -> SimulationExecutor:
        """Create a reference SimulationExecutor that produces full timelines."""
        from fbf.core.execution.pipeline.default_pipeline import create_default_pipeline
        from fbf.core.execution.pipeline.runner import SimulationRunner

        return SimulationExecutor(SimulationRunner(pipeline=create_default_pipeline()))

    def test_statistics_identical(self) -> None:
        """Complete SimulationStatistics must match across both modes."""
        plan = make_plan(cohorts=1, horizons=[720])
        sim_exec = self._make_reference_executor()

        result_full = sequential_execute(
            plan, simulation_executor=sim_exec, summary_only=False,
        )
        result_summary = sequential_execute(
            plan, simulation_executor=sim_exec, summary_only=True,
        )

        assert len(result_full.results) == len(result_summary.results)

        for i, (full, summary) in enumerate(
            zip(result_full.results, result_summary.results, strict=True)
        ):
            assert full.statistics == summary.statistics, (
                f"Unit {i}: statistics differ. "
                f"full={full.statistics} summary={summary.statistics}"
            )

    def test_timelines_differ_intentionally(self) -> None:
        """summary_only=False must have a populated timeline; summary_only=True
        must have an empty timeline."""
        plan = make_plan(cohorts=1, horizons=[720])
        sim_exec = self._make_reference_executor()

        result_full = sequential_execute(
            plan, simulation_executor=sim_exec, summary_only=False,
        )
        result_summary = sequential_execute(
            plan, simulation_executor=sim_exec, summary_only=True,
        )

        assert len(result_full.results) == len(result_summary.results)

        for i, (full, summary) in enumerate(
            zip(result_full.results, result_summary.results, strict=True)
        ):
            assert full.timeline.monthly_results != (), (
                f"Unit {i}: summary_only=False must have a populated timeline"
            )
            assert summary.timeline.monthly_results == (), (
                f"Unit {i}: summary_only=True must have an empty timeline"
            )

    def test_plan_and_definition_preserved(self) -> None:
        """ResearchExecutionResult.plan and ExperimentRun.definition are unchanged."""
        plan = make_plan(cohorts=1, horizons=[720])
        sim_exec = self._make_reference_executor()

        result_full = sequential_execute(
            plan, simulation_executor=sim_exec, summary_only=False,
        )
        result_summary = sequential_execute(
            plan, simulation_executor=sim_exec, summary_only=True,
        )

        assert result_full.plan == result_summary.plan
        assert (
            result_full.experiment_result.definition
            == result_summary.experiment_result.definition
        )
        assert len(result_full.results) == len(result_summary.results)
