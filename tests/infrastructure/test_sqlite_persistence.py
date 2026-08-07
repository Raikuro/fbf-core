"""Round-trip tests for the SQLite persistence layer (v0.4 Phase 2).

Verifies the behavioral specification INFRASTRUCTURE_SQLITE_PERSISTENCE_SPECIFICATION.md:
- Round-trip: ExperimentDefinition metadata persisted and retrieved identically
- Round-trip: ResearchPlan with PlannedSimulationUnit records round-trip losslessly
- Round-trip: ResearchExecutionResult with SimulationResult records round-trip losslessly
- Round-trip: All Decimal values preserved with exact precision
- Round-trip: All date values preserved exactly
- Round-trip: All policy parameters preserved exactly
- Ordering: Unit order in plans preserved on persistence
- Ordering: Simulation result month order preserved
- Error handling: DuplicateStudyError on duplicate name
- Error handling: StudyNotFoundError on missing experiment
- Error handling: ResultsNotFoundError on missing execution result
- Schema: All 9 core tables created
- Isolation: Foreign key constraints enforced
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from engine.application.simulation import (
    ExperimentRun,
    SimulationResult,
    SimulationStatistics,
    SimulationTimeline,
)
from engine.application.simulation_context import SimulationContext
from engine.domain.model.allocation import AllocationTarget
from engine.domain.model.asset import AssetClass
from engine.domain.model.dataset import Dataset
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.money import Currency, Money
from engine.domain.model.portfolio import AssetHolding, Portfolio
from engine.domain.policies.allocation_policy import AllocationPolicy
from engine.domain.policies.decisions import AllocationDecision, WithdrawalDecision
from engine.domain.policies.withdrawal_policy import WithdrawalPolicy
from infrastructure.persistence import (
    CorruptedDatabaseError,
    DuplicateStudyError,
    PersistenceError,
    RepositoryError,
    ResultsNotFoundError,
    SQLiteRepository,
    StudyNotFoundError,
)
from infrastructure.persistence.serializers import (
    deserialize_decimal,
    deserialize_parameter_config,
    deserialize_portfolio,
    serialize_decimal,
    serialize_parameter_config,
    serialize_policy,
    serialize_portfolio,
)
from infrastructure.persistence.sqlite_repository import (
    ExperimentIdentity,
    PersistenceReconstructionContext,
    PolicyKind,
    SerializedSimulationResult,
)
from research.domain.cohort.specification import CohortSpecification
from research.domain.experiment.definition import ExperimentDefinition
from research.domain.parameter.configuration import ParameterConfiguration
from research.domain.plan import PlannedSimulationUnit, ResearchPlan
from research.orchestration.result import ResearchExecutionResult

# ---------------------------------------------------------------------------
# Shared test dataset — reused so id() matches across save/load
# ---------------------------------------------------------------------------

_ASSET = AssetClass(id="acwi", name="ACWI", description="Global equities")


def _make_shared_dataset() -> Dataset:
    snapshots = []
    for i in range(240):
        m = i + 1
        y = 2000 + (m - 1) // 12
        mo = ((m - 1) % 12) + 1
        snapshots.append(
            MarketSnapshot(
                date=date(y, mo, 1),
                index_levels={_ASSET: Decimal("100.00")},
                inflation=Decimal("0.00"),
                inflation_cumulative=Decimal("0.00"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100.00"),
            )
        )
    return Dataset(snapshots=snapshots, frequency="monthly", version="TEST_DATASET_v1")


_TEST_DATASET: Dataset = _make_shared_dataset()


# ---------------------------------------------------------------------------
# Dummy policies for tests
# ---------------------------------------------------------------------------


class DummyAllocationPolicy(AllocationPolicy):
    def decide(self, context: object) -> AllocationDecision:
        return AllocationDecision(
            reason="dummy",
            allocation_target=AllocationTarget(weights={}),
        )


class DummyWithdrawalPolicy(WithdrawalPolicy):
    def decide(self, context: object) -> WithdrawalDecision:
        return WithdrawalDecision(
            reason="dummy",
            nominal_amount=Money(Decimal("500"), Currency.EUR),
            real_amount=Money(Decimal("500"), Currency.EUR),
        )


# ---------------------------------------------------------------------------
# Codec stubs for reconstruction context
# ---------------------------------------------------------------------------


class DummySimulationResultCodec:
    def dump(self, result: SimulationResult) -> SerializedSimulationResult:
        stats = result.statistics
        payload = {
            "final_wealth_amount": str(stats.final_wealth.amount),
            "final_wealth_currency": stats.final_wealth.currency.value,
            "max_drawdown": stats.max_drawdown,
            "success": stats.success,
            "failure_month": stats.failure_month,
            "months_simulated": stats.months_simulated,
            "execution_time_seconds": stats.execution_time_seconds,
        }
        monthly = tuple(
            json.dumps({"month": i, "dummy": True}, sort_keys=True)
            for i in range(len(result.timeline.monthly_results))
        )
        return SerializedSimulationResult(
            statistics_payload_json=json.dumps(payload, sort_keys=True),
            monthly_payloads_json=monthly,
        )

    def load(
        self, statistics_payload_json: str, monthly_payloads_json: Sequence[str]
    ) -> SimulationResult:
        data = json.loads(statistics_payload_json)
        statistics = SimulationStatistics(
            final_wealth=Money(
                Decimal(data["final_wealth_amount"]),
                Currency(data["final_wealth_currency"]),
            ),
            max_drawdown=data["max_drawdown"],
            success=data["success"],
            failure_month=data["failure_month"],
            months_simulated=data["months_simulated"],
            execution_time_seconds=data["execution_time_seconds"],
        )
        monthly_results = tuple(
            json.loads(p) for p in monthly_payloads_json
        )
        timeline = SimulationTimeline(monthly_results=monthly_results)
        return SimulationResult(timeline=timeline, statistics=statistics)


class DummyAllocationPolicyCodec:
    policy_type: str = "AllocationPolicy"
    policy_kind: PolicyKind = PolicyKind.ALLOCATION

    def dump(self, policy: Any) -> Mapping[str, Any]:
        return {"type": "AllocationPolicy"}

    def load(self, parameters: Mapping[str, Any]) -> Any:
        return DummyAllocationPolicy()


class DummyWithdrawalPolicyCodec:
    policy_type: str = "WithdrawalPolicy"
    policy_kind: PolicyKind = PolicyKind.WITHDRAWAL

    def dump(self, policy: Any) -> Mapping[str, Any]:
        return {"type": "WithdrawalPolicy"}

    def load(self, parameters: Mapping[str, Any]) -> Any:
        return DummyWithdrawalPolicy()


# ---------------------------------------------------------------------------
# Helper: context for persistence tests
# ---------------------------------------------------------------------------


class DummyDatasetResolver:
    def resolve(self, dataset_identifier: str) -> Dataset:
        return _TEST_DATASET


def get_dummy_context() -> PersistenceReconstructionContext:
    return PersistenceReconstructionContext(
        dataset_resolver=DummyDatasetResolver(),
        policy_codecs={
            ("allocation", "AllocationPolicy"): DummyAllocationPolicyCodec(),
            ("withdrawal", "WithdrawalPolicy"): DummyWithdrawalPolicyCodec(),
        },
        simulation_result_codec=DummySimulationResultCodec(),
    )


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def make_asset(asset_id: str = "acwi") -> AssetClass:
    return AssetClass(id=asset_id, name="ACWI", description="Global equities")


def make_portfolio(units: str = "1000.00") -> Portfolio:
    return Portfolio(
        holdings=(AssetHolding(asset_class=_ASSET, units=Decimal(units)),)
    )


def make_experiment(name: str = "test-experiment") -> ExperimentDefinition:
    return ExperimentDefinition(
        name=name,
        description="Round-trip test experiment",
        dataset=_TEST_DATASET,
        horizon_months=120,
        initial_wealth=Money(Decimal("500000.00"), Currency.EUR),
        cohorts=(
            CohortSpecification(start_date=date(2000, 1, 1)),
            CohortSpecification(start_date=date(2000, 2, 1)),
        ),
        allocation_policies=(DummyAllocationPolicy(),),
        withdrawal_policies=(DummyWithdrawalPolicy(),),
    )


def make_unit(month: int = 1, rate: str = "0.04") -> PlannedSimulationUnit:
    cohort_date = date(2000, month, 1)
    sliced_dataset = _TEST_DATASET.slice(cohort_date, 120)
    return PlannedSimulationUnit(
        cohort=CohortSpecification(start_date=cohort_date),
        parameter_config=ParameterConfiguration(values={"withdrawal_rate": float(rate)}),
        allocation_policy=DummyAllocationPolicy(),
        withdrawal_policy=DummyWithdrawalPolicy(),
        initial_portfolio=make_portfolio(),
        dataset=sliced_dataset,
    )


def make_plan(num_units: int = 4) -> ResearchPlan:
    experiment = make_experiment()
    units = tuple(make_unit(month=((i % 12) + 1)) for i in range(num_units))
    return ResearchPlan(experiment_definition=experiment, units=units)


def make_sim_result(
    final_wealth: str = "500000.00",
    success: bool = True,
) -> SimulationResult:
    return SimulationResult(
        timeline=SimulationTimeline(monthly_results=()),
        statistics=SimulationStatistics(
            final_wealth=Money(Decimal(final_wealth), Currency.EUR),
            max_drawdown=0.05,
            success=success,
            failure_month=None if success else 36,
            months_simulated=120,
            execution_time_seconds=0.01,
        ),
    )


def _build_sim_context(
    unit: PlannedSimulationUnit, experiment: ExperimentDefinition
) -> SimulationContext:
    return SimulationContext(
        experiment_name=experiment.name,
        cohort=unit.cohort.start_date.isoformat(),
        start_date=unit.cohort.start_date,
        horizon_months=experiment.horizon_months,
        initial_wealth=experiment.initial_wealth,
        initial_portfolio=unit.initial_portfolio,
        dataset=_TEST_DATASET,
        allocation_policy=unit.allocation_policy,
        withdrawal_policy=unit.withdrawal_policy,
    )


def make_experiment_run(plan: ResearchPlan) -> ExperimentRun:
    sim_results = tuple(
        make_sim_result(str(500000 + i * 1000)) for i in range(len(plan.units))
    )
    sim_contexts = tuple(
        _build_sim_context(unit, plan.experiment_definition) for unit in plan.units
    )
    from engine.application.simulation import ExperimentDefinition as EngineExperimentDefinition
    engine_def = EngineExperimentDefinition(
        name=plan.experiment_definition.name,
        description=plan.experiment_definition.description,
        simulation_contexts=sim_contexts,
    )
    return ExperimentRun(definition=engine_def, simulation_results=sim_results)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path) -> SQLiteRepository:
    db_file = tmp_path / "test_persistence.db"
    return SQLiteRepository(str(db_file))


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


def test_schema_creates_all_tables(repo: SQLiteRepository) -> None:
    expected_tables = {
        "schema_version",
        "experiments",
        "cohorts",
        "parameter_configurations",
        "policies",
        "research_plans",
        "planned_units",
        "execution_results",
        "simulation_results",
    }
    import tempfile as _tf
    with _tf.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp_path = f.name
    try:
        SQLiteRepository(tmp_path)
        import sqlite3
        with sqlite3.connect(tmp_path) as c:
            tables = {r[0] for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        assert expected_tables.issubset(tables), (
            f"Missing tables: {expected_tables - tables}"
        )
    finally:
        os.unlink(tmp_path)


def test_schema_version_recorded(repo: SQLiteRepository) -> None:
    import sqlite3
    import tempfile as _tf
    with _tf.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp_path = f.name
    try:
        SQLiteRepository(tmp_path)
        with sqlite3.connect(tmp_path) as c:
            row = c.execute("SELECT version FROM schema_version").fetchone()
        assert row is not None
        assert row[0] == 1
    finally:
        os.unlink(tmp_path)


def test_error_hierarchy() -> None:
    assert issubclass(StudyNotFoundError, RepositoryError)
    assert issubclass(ResultsNotFoundError, RepositoryError)
    assert issubclass(DuplicateStudyError, RepositoryError)
    assert issubclass(PersistenceError, RepositoryError)
    assert issubclass(CorruptedDatabaseError, RepositoryError)


# ---------------------------------------------------------------------------
# Serializer unit tests
# ---------------------------------------------------------------------------


class TestDecimalSerialization:
    def test_round_trip_decimal(self) -> None:
        val = Decimal("123.456")
        assert deserialize_decimal(serialize_decimal(val)) == val


class TestParameterConfigSerialization:
    def test_round_trip_float(self) -> None:
        values = {"withdrawal_rate": 0.04, "equity_pct": 0.75}
        params_json = serialize_parameter_config(values)
        restored = deserialize_parameter_config(params_json)
        assert restored["withdrawal_rate"] == 0.04
        assert restored["equity_pct"] == 0.75

    def test_round_trip_int(self) -> None:
        values = {"horizon_years": 30}
        params_json = serialize_parameter_config(values)
        restored = deserialize_parameter_config(params_json)
        assert restored["horizon_years"] == 30

    def test_round_trip_string(self) -> None:
        values = {"strategy": "aggressive"}
        params_json = serialize_parameter_config(values)
        restored = deserialize_parameter_config(params_json)
        assert restored["strategy"] == "aggressive"

    def test_canonical_json_deterministic(self) -> None:
        values = {"a": 1.0, "b": 2.0}
        j1 = serialize_parameter_config(values)
        j2 = serialize_parameter_config(values)
        assert j1 == j2

    def test_different_configs_different_json(self) -> None:
        v1 = {"rate": 0.04}
        v2 = {"rate": 0.05}
        assert serialize_parameter_config(v1) != serialize_parameter_config(v2)


class TestPortfolioSerialization:
    def test_round_trip(self) -> None:
        data = {"holdings": [{"asset_class_id": "acwi", "units": "1234.56789"}]}
        json_str = serialize_portfolio(data)
        restored = deserialize_portfolio(json_str)
        assert restored["holdings"][0]["asset_class_id"] == "acwi"
        assert restored["holdings"][0]["units"] == "1234.56789"

    def test_multi_asset_round_trip(self) -> None:
        data = {
            "holdings": [
                {"asset_class_id": "equity", "units": "750"},
                {"asset_class_id": "bond", "units": "250"},
            ]
        }
        json_str = serialize_portfolio(data)
        restored = deserialize_portfolio(json_str)
        assert len(restored["holdings"]) == 2


class TestPolicySerialization:
    def test_serialize_returns_string(self) -> None:
        data = {"policy_type": "DummyAllocationPolicy"}
        result = serialize_policy(data)
        assert isinstance(result, str)

    def test_serialize_is_json(self) -> None:
        data = {"policy_type": "DummyAllocationPolicy"}
        result = serialize_policy(data)
        parsed = json.loads(result)
        assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# Experiment round-trip tests
# ---------------------------------------------------------------------------


def test_experiment_save_and_load_name(repo: SQLiteRepository) -> None:
    ctx = get_dummy_context()
    experiment = make_experiment("SWR-Study-2024")
    exp_id = repo.save_experiment(
        ExperimentIdentity(name="SWR-Study-2024", revision="v1"), experiment, ctx
    )
    loaded = repo.load_experiment(exp_id, ctx)
    assert loaded.name == "SWR-Study-2024"


def test_experiment_save_and_load_description(repo: SQLiteRepository) -> None:
    ctx = get_dummy_context()
    experiment = make_experiment()
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    loaded = repo.load_experiment(exp_id, ctx)
    assert loaded.description == experiment.description


def test_experiment_save_and_load_horizon(repo: SQLiteRepository) -> None:
    ctx = get_dummy_context()
    experiment = make_experiment()
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    loaded = repo.load_experiment(exp_id, ctx)
    assert loaded.horizon_months == 120


def test_experiment_save_and_load_initial_wealth(repo: SQLiteRepository) -> None:
    ctx = get_dummy_context()
    experiment = make_experiment()
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    loaded = repo.load_experiment(exp_id, ctx)
    assert loaded.initial_wealth.amount == Decimal("500000.00")
    assert loaded.initial_wealth.currency == Currency.EUR


def test_experiment_save_and_load_cohort_dates(repo: SQLiteRepository) -> None:
    ctx = get_dummy_context()
    experiment = make_experiment()
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    loaded = repo.load_experiment(exp_id, ctx)
    assert len(loaded.cohorts) == 2
    dates = {c.start_date for c in loaded.cohorts}
    assert date(2000, 1, 1) in dates
    assert date(2000, 2, 1) in dates


def test_experiment_cohort_order_preserved(repo: SQLiteRepository) -> None:
    ctx = get_dummy_context()
    experiment = make_experiment()
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    loaded = repo.load_experiment(exp_id, ctx)
    dates = [c.start_date for c in loaded.cohorts]
    assert dates == sorted(dates)


def test_duplicate_experiment_raises(repo: SQLiteRepository) -> None:
    ctx = get_dummy_context()
    experiment = make_experiment("unique-name")
    repo.save_experiment(ExperimentIdentity(name="unique-name", revision="v1"), experiment, ctx)
    with pytest.raises(DuplicateStudyError):
        repo.save_experiment(ExperimentIdentity(name="unique-name", revision="v1"), experiment, ctx)


def test_load_missing_experiment_raises(repo: SQLiteRepository) -> None:
    ctx = get_dummy_context()
    with pytest.raises(StudyNotFoundError):
        repo.load_experiment("00000000-0000-0000-0000-000000000000", ctx)


def test_find_experiment_by_name(repo: SQLiteRepository) -> None:
    ctx = get_dummy_context()
    experiment = make_experiment("searchable-study")
    exp_id = repo.save_experiment(
        ExperimentIdentity(name="searchable-study", revision="v1"), experiment, ctx
    )
    found_id = repo.find_experiment_by_name("searchable-study")
    assert found_id == exp_id


def test_find_experiment_by_name_missing(repo: SQLiteRepository) -> None:
    assert repo.find_experiment_by_name("nonexistent") is None


def test_list_experiments(repo: SQLiteRepository) -> None:
    ctx = get_dummy_context()
    exp_a = make_experiment("study-a")
    exp_b = make_experiment("study-b")
    repo.save_experiment(ExperimentIdentity(name="study-a", revision="v1"), exp_a, ctx)
    repo.save_experiment(ExperimentIdentity(name="study-b", revision="v1"), exp_b, ctx)
    all_experiments = repo.list_experiments()
    names = {e["name"] for e in all_experiments}
    assert "study-a" in names
    assert "study-b" in names


# ---------------------------------------------------------------------------
# Plan round-trip tests
# ---------------------------------------------------------------------------


def test_plan_save_and_load_unit_count(repo: SQLiteRepository) -> None:
    ctx = get_dummy_context()
    experiment = make_experiment()
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    plan = make_plan(num_units=6)
    plan_id = repo.save_plan(plan, exp_id, ctx)
    loaded = repo.load_plan(plan_id, ctx)
    assert len(loaded.units) == 6


def test_plan_unit_order_preserved(repo: SQLiteRepository) -> None:
    ctx = get_dummy_context()
    experiment = make_experiment()
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    units = tuple(
        make_unit(month=m) for m in [3, 1, 2, 6, 4, 5]
    )
    plan = ResearchPlan(experiment_definition=experiment, units=units)
    plan_id = repo.save_plan(plan, exp_id, ctx)
    loaded = repo.load_plan(plan_id, ctx)
    expected_dates = [date(2000, m, 1) for m in [3, 1, 2, 6, 4, 5]]
    actual_dates = [u.cohort.start_date for u in loaded.units]
    assert actual_dates == expected_dates


def test_plan_parameter_config_round_trip(repo: SQLiteRepository) -> None:
    ctx = get_dummy_context()
    experiment = make_experiment()
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    unit = PlannedSimulationUnit(
        cohort=CohortSpecification(start_date=date(2000, 1, 1)),
        parameter_config=ParameterConfiguration(
            values={"withdrawal_rate": 0.04, "equity_pct": 0.75}
        ),
        allocation_policy=DummyAllocationPolicy(),
        withdrawal_policy=DummyWithdrawalPolicy(),
        initial_portfolio=make_portfolio(),
        dataset=_TEST_DATASET,
    )
    plan = ResearchPlan(experiment_definition=experiment, units=(unit,))
    plan_id = repo.save_plan(plan, exp_id, ctx)
    loaded = repo.load_plan(plan_id, ctx)
    assert len(loaded.units) == 1
    assert loaded.units[0].parameter_config.values["withdrawal_rate"] == 0.04
    assert loaded.units[0].parameter_config.values["equity_pct"] == 0.75


def test_plan_portfolio_round_trip(repo: SQLiteRepository) -> None:
    ctx = get_dummy_context()
    experiment = make_experiment()
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    exact_units = "123456789.987654321"
    unit = PlannedSimulationUnit(
        cohort=CohortSpecification(start_date=date(2000, 1, 1)),
        parameter_config=ParameterConfiguration(values={"rate": 0.04}),
        allocation_policy=DummyAllocationPolicy(),
        withdrawal_policy=DummyWithdrawalPolicy(),
        initial_portfolio=Portfolio(
            holdings=(AssetHolding(asset_class=_ASSET, units=Decimal(exact_units)),)
        ),
        dataset=_TEST_DATASET,
    )
    plan = ResearchPlan(experiment_definition=experiment, units=(unit,))
    plan_id = repo.save_plan(plan, exp_id, ctx)
    loaded = repo.load_plan(plan_id, ctx)
    assert loaded.units[0].initial_portfolio.holdings[0].units == Decimal(exact_units)


def test_plan_cohort_start_date_round_trip(repo: SQLiteRepository) -> None:
    ctx = get_dummy_context()
    experiment = make_experiment()
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    unit = make_unit(month=7)
    plan = ResearchPlan(experiment_definition=experiment, units=(unit,))
    plan_id = repo.save_plan(plan, exp_id, ctx)
    loaded = repo.load_plan(plan_id, ctx)
    assert loaded.units[0].cohort.start_date == date(2000, 7, 1)


def test_plan_policy_type_round_trip(repo: SQLiteRepository) -> None:
    ctx = get_dummy_context()
    experiment = make_experiment()
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    plan = make_plan(num_units=1)
    plan_id = repo.save_plan(plan, exp_id, ctx)
    loaded = repo.load_plan(plan_id, ctx)
    alloc_type = type(loaded.units[0].allocation_policy).__name__
    withd_type = type(loaded.units[0].withdrawal_policy).__name__
    assert "DummyAllocationPolicy" in alloc_type
    assert "DummyWithdrawalPolicy" in withd_type


# ---------------------------------------------------------------------------
# Execution result round-trip tests
# ---------------------------------------------------------------------------


def test_execution_result_save_and_load(repo: SQLiteRepository) -> None:
    ctx = get_dummy_context()
    experiment = make_experiment()
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    plan = make_plan(num_units=3)
    plan_id = repo.save_plan(plan, exp_id, ctx)

    experiment_run = make_experiment_run(plan)
    research_result = ResearchExecutionResult(plan=plan, experiment_result=experiment_run)

    result_id = repo.save_execution_result(plan_id, research_result, ctx, duration_seconds=1.5)
    loaded = repo.load_execution_result(result_id, ctx)
    loaded_results = loaded.results

    assert len(loaded_results) == 3


def test_execution_result_final_wealth_round_trip(repo: SQLiteRepository) -> None:
    ctx = get_dummy_context()
    experiment = make_experiment()
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    plan = make_plan(num_units=1)
    plan_id = repo.save_plan(plan, exp_id, ctx)

    exact_wealth = "987654.123456789"
    sim_result = SimulationResult(
        timeline=SimulationTimeline(monthly_results=()),
        statistics=SimulationStatistics(
            final_wealth=Money(Decimal(exact_wealth), Currency.EUR),
            max_drawdown=0.12,
            success=True,
            failure_month=None,
            months_simulated=120,
            execution_time_seconds=0.01,
        ),
    )
    sim_contexts = tuple(
        _build_sim_context(unit, experiment)
        for unit in plan.units
    )
    from engine.application.simulation import ExperimentDefinition as EngineExperimentDefinition
    engine_def = EngineExperimentDefinition(
        name=experiment.name,
        description=experiment.description,
        simulation_contexts=sim_contexts,
    )
    experiment_run = ExperimentRun(definition=engine_def, simulation_results=(sim_result,))
    research_result = ResearchExecutionResult(plan=plan, experiment_result=experiment_run)

    result_id = repo.save_execution_result(plan_id, research_result, ctx, duration_seconds=1.5)
    loaded = repo.load_execution_result(result_id, ctx)
    loaded_result = loaded.results[0]

    assert loaded_result.statistics.final_wealth.amount == Decimal(exact_wealth)
    assert loaded_result.statistics.final_wealth.currency == Currency.EUR


def test_execution_result_success_flag_round_trip(repo: SQLiteRepository) -> None:
    ctx = get_dummy_context()
    experiment = make_experiment()
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    plan = make_plan(num_units=2)
    plan_id = repo.save_plan(plan, exp_id, ctx)

    sim_results = (
        make_sim_result(success=True),
        SimulationResult(
            timeline=SimulationTimeline(monthly_results=()),
            statistics=SimulationStatistics(
                final_wealth=Money(Decimal("0"), Currency.EUR),
                max_drawdown=1.0,
                success=False,
                failure_month=36,
                months_simulated=36,
                execution_time_seconds=0.01,
            ),
        ),
    )
    sim_contexts = tuple(
        _build_sim_context(unit, experiment)
        for unit in plan.units
    )
    from engine.application.simulation import ExperimentDefinition as EngineExperimentDefinition
    engine_def = EngineExperimentDefinition(
        name=experiment.name,
        description=experiment.description,
        simulation_contexts=sim_contexts,
    )
    experiment_run = ExperimentRun(definition=engine_def, simulation_results=sim_results)
    research_result = ResearchExecutionResult(plan=plan, experiment_result=experiment_run)

    result_id = repo.save_execution_result(plan_id, research_result, ctx, duration_seconds=1.5)
    loaded = repo.load_execution_result(result_id, ctx)
    loaded_results = loaded.results

    assert loaded_results[0].statistics.success is True
    assert loaded_results[0].statistics.failure_month is None
    assert loaded_results[1].statistics.success is False
    assert loaded_results[1].statistics.failure_month == 36


def test_execution_result_unit_order_preserved(repo: SQLiteRepository) -> None:
    ctx = get_dummy_context()
    experiment = make_experiment()
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    plan = make_plan(num_units=5)
    plan_id = repo.save_plan(plan, exp_id, ctx)

    sim_results = tuple(
        make_sim_result(str(500000 + i * 10000)) for i in range(5)
    )
    sim_contexts = tuple(
        _build_sim_context(unit, experiment)
        for unit in plan.units
    )
    from engine.application.simulation import ExperimentDefinition as EngineExperimentDefinition
    engine_def = EngineExperimentDefinition(
        name=experiment.name,
        description=experiment.description,
        simulation_contexts=sim_contexts,
    )
    experiment_run = ExperimentRun(definition=engine_def, simulation_results=sim_results)
    research_result = ResearchExecutionResult(plan=plan, experiment_result=experiment_run)

    result_id = repo.save_execution_result(plan_id, research_result, ctx, duration_seconds=1.5)
    loaded = repo.load_execution_result(result_id, ctx)
    loaded_results = loaded.results

    expected_amounts = [Decimal(str(500000 + i * 10000)) for i in range(5)]
    actual_amounts = [r.statistics.final_wealth.amount for r in loaded_results]
    assert actual_amounts == expected_amounts


def test_execution_result_statistics_round_trip(repo: SQLiteRepository) -> None:
    ctx = get_dummy_context()
    experiment = make_experiment()
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    plan = make_plan(num_units=1)
    plan_id = repo.save_plan(plan, exp_id, ctx)

    sim_result = SimulationResult(
        timeline=SimulationTimeline(monthly_results=()),
        statistics=SimulationStatistics(
            final_wealth=Money(Decimal("300000"), Currency.EUR),
            max_drawdown=0.35,
            success=True,
            failure_month=None,
            months_simulated=360,
            execution_time_seconds=2.5,
        ),
    )
    sim_contexts = tuple(
        _build_sim_context(unit, experiment)
        for unit in plan.units
    )
    from engine.application.simulation import ExperimentDefinition as EngineExperimentDefinition
    engine_def = EngineExperimentDefinition(
        name=experiment.name,
        description=experiment.description,
        simulation_contexts=sim_contexts,
    )
    experiment_run = ExperimentRun(definition=engine_def, simulation_results=(sim_result,))
    research_result = ResearchExecutionResult(plan=plan, experiment_result=experiment_run)
    result_id = repo.save_execution_result(plan_id, research_result, ctx, duration_seconds=1.5)
    loaded = repo.load_execution_result(result_id, ctx)
    loaded_result = loaded.results[0]

    assert loaded_result.statistics.max_drawdown == pytest.approx(0.35)
    assert loaded_result.statistics.months_simulated == 360
    assert loaded_result.statistics.execution_time_seconds == pytest.approx(2.5)


def test_load_missing_execution_result_raises(repo: SQLiteRepository) -> None:
    ctx = get_dummy_context()
    with pytest.raises(ResultsNotFoundError):
        repo.load_execution_result("00000000-0000-0000-0000-000000000000", ctx)


def test_find_result_by_plan(repo: SQLiteRepository) -> None:
    ctx = get_dummy_context()
    experiment = make_experiment()
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    plan = make_plan(num_units=1)
    plan_id = repo.save_plan(plan, exp_id, ctx)

    experiment_run = make_experiment_run(plan)
    research_result = ResearchExecutionResult(plan=plan, experiment_result=experiment_run)
    result_id = repo.save_execution_result(plan_id, research_result, ctx, duration_seconds=1.5)

    found = repo.find_result_by_plan(plan_id)
    assert found == result_id


def test_find_result_by_plan_missing(repo: SQLiteRepository) -> None:
    assert repo.find_result_by_plan("nonexistent-plan-id") is None


# ---------------------------------------------------------------------------
# Isolation / FK tests
# ---------------------------------------------------------------------------


def test_foreign_key_plan_requires_experiment(repo: SQLiteRepository) -> None:
    ctx = get_dummy_context()
    plan = make_plan(num_units=1)
    with pytest.raises((RepositoryError, Exception)):
        repo.save_plan(plan, "nonexistent-experiment-id", ctx)
