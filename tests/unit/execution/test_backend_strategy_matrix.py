"""Execution backend and strategy routing tests.

Numba is the only execution engine.  AUTO and explicit FAST resolve to the same
fail-closed Numba selection; parallel execution is rejected.
"""

from __future__ import annotations

from typing import Any

import pytest

from fbf.core.execution import (
    ExecutionBackend,
    ExecutionOptions,
    ExecutionStrategy,
    execute_study_plan,
)
from fbf.core.study.builder import BuiltStudy
from tests.unit.execution.conftest import make_plan


def _make_built_study(
    cohorts: int = 1, horizons: list[int] | None = None
) -> BuiltStudy:
    """Create a BuiltStudy suitable for execute_study_plan."""
    plan = make_plan(cohorts=cohorts, horizons=horizons)
    return BuiltStudy(
        plan=plan,
        experiment_definition=plan.experiment_definition,
        cohorts=plan.experiment_definition.cohorts,
        param_configs=(),
    )


class TestFastBackendStrategy:
    """FAST backend × strategy combinations."""

    def test_fast_auto_resolves_to_sequential(self) -> None:
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
        built = _make_built_study(cohorts=1, horizons=[720])
        options = ExecutionOptions(
            backend=ExecutionBackend.FAST,
            strategy=ExecutionStrategy.SEQUENTIAL,
            summary_only=True,
        )
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None

    def test_fast_parallel_raises_explicit_error(self) -> None:
        built = _make_built_study(cohorts=1, horizons=[720])
        options = ExecutionOptions(
            backend=ExecutionBackend.FAST,
            strategy=ExecutionStrategy.PARALLEL,
        )
        with pytest.raises(ValueError, match="Numba backend does not support parallel"):
            execute_study_plan(built, options)


class TestMissingDependency:
    """Execution without the optional Numba dependency."""

    def test_missing_numba_raises_clear_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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


class TestExecutionOptionsDefaults:
    """Verify ExecutionOptions default values."""

    def test_default_backend_is_none(self) -> None:
        assert ExecutionOptions().backend is None

    def test_default_strategy_is_auto(self) -> None:
        assert ExecutionOptions().strategy == ExecutionStrategy.AUTO

    def test_workers_default_is_none(self) -> None:
        assert ExecutionOptions().workers is None

    def test_summary_only_default_is_false(self) -> None:
        assert ExecutionOptions().summary_only is False


class TestAutoBackendDispatch:
    """AUTO dispatch selects a Numba executor for supported workloads."""

    def test_auto_dispatch_executes_fixed_real(self) -> None:
        built = _make_built_study(cohorts=1, horizons=[720])
        options = ExecutionOptions(
            strategy=ExecutionStrategy.AUTO,
            workers=None,
            summary_only=True,
        )
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None

    def test_explicit_fast_matches_auto(self) -> None:
        built = _make_built_study(cohorts=1, horizons=[720])
        auto = execute_study_plan(
            built, ExecutionOptions(strategy=ExecutionStrategy.AUTO)
        )
        explicit = execute_study_plan(
            built,
            ExecutionOptions(backend=ExecutionBackend.FAST),
        )
        assert auto.results == explicit.results

    def test_auto_parallel_raises_for_numba(self) -> None:
        built = _make_built_study(cohorts=1, horizons=[720])
        options = ExecutionOptions(
            strategy=ExecutionStrategy.PARALLEL,
            workers=2,
        )
        with pytest.raises(ValueError, match="Numba backend does not support parallel"):
            execute_study_plan(built, options)

    def test_auto_sequential_for_numba(self) -> None:
        built = _make_built_study(cohorts=1, horizons=[720])
        options = ExecutionOptions(
            strategy=ExecutionStrategy.SEQUENTIAL,
            summary_only=True,
        )
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None
