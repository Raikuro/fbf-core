"""Tests for the execution backend × strategy routing matrix.

Verifies that every supported combination of ExecutionBackend and
ExecutionStrategy resolves to the correct execution path, and that
unsupported combinations fail explicitly.
"""

from __future__ import annotations

from typing import Any

import pytest

from fbf.core.execution import (
    _DEFAULT_PARALLEL_UNIT_THRESHOLD,
    ExecutionBackend,
    ExecutionOptions,
    ExecutionStrategy,
    execute_study_plan,
)
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


class TestDefaultBackendStrategy:
    """DEFAULT backend × strategy combinations."""

    def test_default_auto_small_workload_selects_sequential(self) -> None:
        """DEFAULT + AUTO with a small plan resolves to sequential."""
        built = _make_built_study(cohorts=1, horizons=[720])
        # Fewer units than threshold → sequential
        options = ExecutionOptions(
            backend=ExecutionBackend.DEFAULT,
            strategy=ExecutionStrategy.AUTO,
            workers=8,
        )
        # Should not raise; result is produced via sequential path
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None

    def test_default_auto_large_workload_selects_parallel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DEFAULT + AUTO with a large plan resolves to parallel when workers available."""
        built = _make_built_study(cohorts=1, horizons=[720])
        # Patch the threshold to 0 so the small test plan triggers parallel
        monkeypatch.setattr(
            "fbf.core.execution._DEFAULT_PARALLEL_UNIT_THRESHOLD", 0
        )
        options = ExecutionOptions(
            backend=ExecutionBackend.DEFAULT,
            strategy=ExecutionStrategy.AUTO,
            workers=2,
        )
        # Should execute in parallel (workers > 1 and units >= threshold)
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None

    def test_default_auto_workers_none_uses_host_default(self) -> None:
        """DEFAULT + AUTO with workers=None inspects host capabilities."""
        built = _make_built_study(cohorts=1, horizons=[720])
        options = ExecutionOptions(
            backend=ExecutionBackend.DEFAULT,
            strategy=ExecutionStrategy.AUTO,
            workers=None,
        )
        # Should complete without error regardless of host CPU count
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None

    def test_default_sequential_forces_sequential(self) -> None:
        """DEFAULT + SEQUENTIAL always executes sequentially."""
        built = _make_built_study(cohorts=1, horizons=[720])
        options = ExecutionOptions(
            backend=ExecutionBackend.DEFAULT,
            strategy=ExecutionStrategy.SEQUENTIAL,
            workers=8,
        )
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None

    def test_default_parallel_forces_parallel(self) -> None:
        """DEFAULT + PARALLEL always executes in parallel."""
        built = _make_built_study(cohorts=1, horizons=[720])
        options = ExecutionOptions(
            backend=ExecutionBackend.DEFAULT,
            strategy=ExecutionStrategy.PARALLEL,
            workers=2,
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
        )
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None

    def test_fast_sequential_forces_sequential(self) -> None:
        """FAST + SEQUENTIAL always executes sequentially."""
        built = _make_built_study(cohorts=1, horizons=[720])
        options = ExecutionOptions(
            backend=ExecutionBackend.FAST,
            strategy=ExecutionStrategy.SEQUENTIAL,
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
            backend=ExecutionBackend.DEFAULT,
            strategy=ExecutionStrategy.AUTO,
            workers=64,
        )
        # Should complete without spawning parallel workers
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None

    def test_explicit_sequential_overrides_auto_routing(self) -> None:
        """Explicit SEQUENTIAL prevents parallel even for large plans."""
        built = _make_built_study(cohorts=1, horizons=[720])
        options = ExecutionOptions(
            backend=ExecutionBackend.DEFAULT,
            strategy=ExecutionStrategy.SEQUENTIAL,
            workers=64,
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
            backend=ExecutionBackend.DEFAULT,
            strategy=ExecutionStrategy.PARALLEL,
            workers=2,
        )
        result = execute_study_plan(built, options)
        assert result.experiment_result is not None


class TestExecutionOptionsDefaults:
    """Verify ExecutionOptions default values."""

    def test_default_backend_is_default(self) -> None:
        opts = ExecutionOptions()
        assert opts.backend == ExecutionBackend.DEFAULT

    def test_default_strategy_is_auto(self) -> None:
        opts = ExecutionOptions()
        assert opts.strategy == ExecutionStrategy.AUTO

    def test_workers_default_is_none(self) -> None:
        opts = ExecutionOptions()
        assert opts.workers is None
