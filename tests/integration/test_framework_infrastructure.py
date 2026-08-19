"""Smoke tests for the integration test framework.

These tests validate that the shared fixtures and helpers defined
in conftest.py and helpers.py initialise correctly and compose
as expected.  They are the foundation on which P4.2–P4.5 build.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from cli.error_handling import ExitCode
from cli.main import main

from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.money import Currency
from fbf.core.execution.result import ResearchExecutionResult
from fbf.core.persistence.studies.sqlite import (
    PersistenceReconstructionContext,
    SQLiteRepository,
)
from fbf.core.persistence.studies.sqlite.codecs import DefaultDatasetResolver
from fbf.core.persistence.studies.sqlite.sqlite_repository import (
    ExperimentIdentity,
)
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.plan import ResearchPlan

from .helpers import (
    assert_study_exists,
    assert_study_not_exists,
    create_study_yaml,
    make_dataset,
    make_execution_result,
    make_experiment,
    make_plan,
    make_simulation_result,
)

# ---------------------------------------------------------------------------
# Conftest fixture smoke tests
# ---------------------------------------------------------------------------


class TestConftestFixtures:
    def test_integration_db_path_creates_file(self, integration_db_path: Path) -> None:
        assert isinstance(integration_db_path, Path)
        assert integration_db_path.name == "integration_test.db"

    def test_integration_repo_initialises(self, integration_repo: SQLiteRepository) -> None:
        assert isinstance(integration_repo, SQLiteRepository)
        assert integration_repo.db_path is not None

    def test_persistence_context_created(
        self, persistence_context: PersistenceReconstructionContext
    ) -> None:
        assert persistence_context.dataset_resolver is not None
        assert persistence_context.policy_codecs is not None
        assert persistence_context.simulation_result_codec is not None

    def test_persistence_context_has_all_codecs(
        self, persistence_context: PersistenceReconstructionContext
    ) -> None:
        assert ("allocation", "AllocationPolicy") in persistence_context.policy_codecs
        assert ("withdrawal", "WithdrawalPolicy") in persistence_context.policy_codecs

    def test_sample_dataset_created(self, sample_dataset: Dataset) -> None:
        assert isinstance(sample_dataset, Dataset)
        assert len(sample_dataset.snapshots) == 500

    def test_sample_experiment_created(
        self, sample_experiment: ExperimentDefinition
    ) -> None:
        assert sample_experiment.name == "integration-test-experiment"
        assert sample_experiment.horizon_months == 120
        assert sample_experiment.initial_wealth.amount == Decimal("1000000")
        assert sample_experiment.initial_wealth.currency == Currency.EUR

    def test_sample_plan_created(self, sample_plan: ResearchPlan) -> None:
        assert isinstance(sample_plan, ResearchPlan)
        assert len(sample_plan.units) == 2

    def test_study_yaml_path_created(self, study_yaml_path: Path) -> None:
        assert study_yaml_path.exists()
        content = study_yaml_path.read_text(encoding="utf-8")
        assert "Integration Test Study" in content
        assert "metadata" in content

    def test_invoke_cli_is_callable(self, invoke_cli: Any) -> None:
        assert callable(invoke_cli)


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    def test_make_dataset_default(self) -> None:
        ds = make_dataset()
        assert isinstance(ds, Dataset)
        assert len(ds.snapshots) == 500

    def test_make_dataset_custom_size(self) -> None:
        ds = make_dataset(num_months=100)
        assert len(ds.snapshots) == 100

    def test_make_experiment_default(self) -> None:
        exp = make_experiment()
        assert exp.name == "helper-experiment"
        assert exp.horizon_months == 120

    def test_make_experiment_custom(self) -> None:
        exp = make_experiment(name="custom-study")
        assert exp.name == "custom-study"

    def test_make_plan_default(self) -> None:
        plan = make_plan()
        assert isinstance(plan, ResearchPlan)
        assert len(plan.units) == 3

    def test_make_plan_custom_units(self) -> None:
        plan = make_plan(num_units=5)
        assert len(plan.units) == 5

    def test_make_simulation_result_default(self) -> None:
        result = make_simulation_result()
        assert result.statistics.final_wealth.amount == Decimal("500000.00")
        assert result.statistics.success is True

    def test_make_simulation_result_failed(self) -> None:
        result = make_simulation_result(success=False, failure_month=12)
        assert result.statistics.success is False
        assert result.statistics.failure_month == 12

    def test_make_execution_result(self) -> None:
        plan = make_plan(num_units=2)
        exec_result = make_execution_result(plan)
        assert isinstance(exec_result, ResearchExecutionResult)
        assert len(exec_result.results) == 2

    def test_make_execution_result_default(self) -> None:
        exec_result = make_execution_result()
        assert isinstance(exec_result, ResearchExecutionResult)

    def test_create_study_yaml(self, tmp_path: Path) -> None:
        path = create_study_yaml(tmp_path / "test.yaml")
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "Integration Test Study" in content

    def test_create_study_yaml_custom(self, tmp_path: Path) -> None:
        path = create_study_yaml(
            tmp_path / "custom.yaml",
            name="Custom Study",
            withdrawal_rate=0.05,
            equity_values="0.60",
        )
        content = path.read_text(encoding="utf-8")
        assert "Custom Study" in content
        assert "0.05" in content
        assert "equity_allocation: [0.60]" in content


# ---------------------------------------------------------------------------
# Assertion utility tests
# ---------------------------------------------------------------------------


class TestAssertionUtilities:
    def test_assert_study_exists_passes(
        self,
        integration_repo: SQLiteRepository,
        persistence_context: PersistenceReconstructionContext,
        sample_experiment: ExperimentDefinition,
    ) -> None:
        integration_repo.save_experiment(
            ExperimentIdentity(name="test-study", revision="v1"),
            sample_experiment,
            persistence_context,
        )
        assert_study_exists(integration_repo, "test-study")

    def test_assert_study_not_exists_passes(
        self, integration_repo: SQLiteRepository
    ) -> None:
        assert_study_not_exists(integration_repo, "nonexistent-study")

    def test_assert_study_not_exists_after_save(
        self,
        integration_repo: SQLiteRepository,
        persistence_context: PersistenceReconstructionContext,
        sample_experiment: ExperimentDefinition,
    ) -> None:
        assert_study_not_exists(integration_repo, "brand-new-study")
        integration_repo.save_experiment(
            ExperimentIdentity(name="brand-new-study", revision="v1"),
            sample_experiment,
            persistence_context,
        )
        assert_study_exists(integration_repo, "brand-new-study")


# ---------------------------------------------------------------------------
# Persistence round-trip verification (framework-level)
# ---------------------------------------------------------------------------


class TestFrameworkPersistenceRoundTrip:
    def test_experiment_save_and_find(
        self,
        integration_repo: SQLiteRepository,
        persistence_context: PersistenceReconstructionContext,
        sample_experiment: ExperimentDefinition,
    ) -> None:
        exp_id = integration_repo.save_experiment(
            ExperimentIdentity(name="round-trip-test", revision="v1"),
            sample_experiment,
            persistence_context,
        )
        found_id = integration_repo.find_experiment_by_name("round-trip-test")
        assert found_id == exp_id

    def test_plan_save_and_load(
        self,
        integration_repo: SQLiteRepository,
        persistence_context_with_dataset: PersistenceReconstructionContext,
        sample_experiment: ExperimentDefinition,
    ) -> None:
        exp_id = integration_repo.save_experiment(
            ExperimentIdentity(name="plan-round-trip", revision="v1"),
            sample_experiment,
            persistence_context_with_dataset,
        )
        plan = make_plan(sample_experiment, num_units=4)
        plan_id = integration_repo.save_plan(plan, exp_id, persistence_context_with_dataset)
        loaded_plan = integration_repo.load_plan(plan_id, persistence_context_with_dataset)
        assert len(loaded_plan.units) == 4

    def test_execution_result_save_and_load(
        self,
        integration_repo: SQLiteRepository,
        persistence_context_with_dataset: PersistenceReconstructionContext,
        sample_experiment: ExperimentDefinition,
    ) -> None:
        exp_id = integration_repo.save_experiment(
            ExperimentIdentity(name="result-round-trip", revision="v1"),
            sample_experiment,
            persistence_context_with_dataset,
        )
        plan = make_plan(sample_experiment, num_units=3)
        plan_id = integration_repo.save_plan(plan, exp_id, persistence_context_with_dataset)
        exec_result = make_execution_result(plan)
        result_id = integration_repo.save_execution_result(
            plan_id, exec_result, persistence_context_with_dataset, duration_seconds=2.0
        )
        loaded = integration_repo.load_execution_result(result_id, persistence_context_with_dataset)
        assert len(loaded.results) == 3

    def test_duplicate_study_detected(
        self,
        integration_repo: SQLiteRepository,
        persistence_context: PersistenceReconstructionContext,
        sample_experiment: ExperimentDefinition,
    ) -> None:
        from fbf.core.persistence.studies.sqlite import DuplicateStudyError
        integration_repo.save_experiment(
            ExperimentIdentity(name="unique-study", revision="v1"),
            sample_experiment,
            persistence_context,
        )
        with pytest.raises(DuplicateStudyError):
            integration_repo.save_experiment(
                ExperimentIdentity(name="unique-study", revision="v1"),
                sample_experiment,
                persistence_context,
            )


# ---------------------------------------------------------------------------
# CLI smoke test (framework-level only — not full E2E, which is P4.2)
# ---------------------------------------------------------------------------


class TestFrameworkConfigIntegration:
    def test_config_validate_minimal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text(
            "database:\n  path: test.db\noutput:\n  default_format: csv\n"
            "execution:\n  default_workers: 4\nlogging:\n  level: INFO\n",
            encoding="utf-8",
        )
        with monkeypatch.context() as m:
            m.setattr(DefaultDatasetResolver, "resolve", lambda self, id: make_dataset(120))
            rc = main(["--config", str(config_yaml), "validate", str(tmp_path / "study.yaml")])
        # file-not-found → validation error (expected; no study yaml provided)
        assert rc == ExitCode.VALIDATION_ERROR


# ---------------------------------------------------------------------------
# Repository integration (framework-level)
# ---------------------------------------------------------------------------


class TestFrameworkRepositoryIntegration:
    def test_repository_schema_tables(
        self, integration_db_path: Path
    ) -> None:
        SQLiteRepository(str(integration_db_path))
        expected_tables = {
            "schema_version", "experiments", "cohorts",
            "parameter_configurations", "policies",
            "research_plans", "planned_units",
            "execution_results", "simulation_results",
        }
        import sqlite3
        with sqlite3.connect(str(integration_db_path)) as conn:
            tables = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert expected_tables.issubset(tables)

    def test_repository_list_experiments(
        self,
        integration_repo: SQLiteRepository,
        persistence_context: PersistenceReconstructionContext,
        sample_experiment: ExperimentDefinition,
    ) -> None:
        integration_repo.save_experiment(
            ExperimentIdentity(name="list-test-a", revision="v1"),
            sample_experiment,
            persistence_context,
        )
        integration_repo.save_experiment(
            ExperimentIdentity(name="list-test-b", revision="v1"),
            sample_experiment,
            persistence_context,
        )
        experiments = integration_repo.list_experiments()
        names = {e["name"] for e in experiments}
        assert "list-test-a" in names
        assert "list-test-b" in names
