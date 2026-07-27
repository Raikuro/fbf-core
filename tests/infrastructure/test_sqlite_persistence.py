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

import os
import tempfile
from datetime import date
from decimal import Decimal

import pytest

from engine.application.simulation import (
    ExperimentRun,
    SimulationResult,
    SimulationStatistics,
    SimulationTimeline,
)
from engine.domain.model.asset import AssetClass
from engine.domain.model.dataset import Dataset
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.money import Currency, Money
from engine.domain.model.portfolio import AssetHolding, Portfolio
from engine.domain.policies.allocation_policy import AllocationPolicy
from engine.domain.policies.decisions import AllocationDecision, WithdrawalDecision
from engine.domain.policies.withdrawal_policy import WithdrawalPolicy
from engine.domain.model.allocation import AllocationTarget
from infrastructure.persistence import (
    CorruptedDatabaseError,
    DuplicateStudyError,
    PersistenceError,
    RepositoryError,
    ResultsNotFoundError,
    SQLiteRepository,
    StudyNotFoundError,
)
from infrastructure.persistence.sqlite_repository import (
    ExperimentIdentity,
    PersistenceReconstructionContext,
    SQLiteRepository,
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
from research.domain.cohort.specification import CohortSpecification
from research.domain.experiment.definition import ExperimentDefinition
from research.domain.parameter.configuration import ParameterConfiguration
from research.domain.plan import PlannedSimulationUnit, ResearchPlan
from research.orchestration.result import ResearchExecutionResult

# Helper to create a dummy context for persistence tests
class DummyDatasetResolver:
    def resolve(self, dataset_identifier: str) -> Dataset:
        return make_dataset(dataset_identifier)


def get_dummy_context() -> PersistenceReconstructionContext:
    # Minimal stub context
    return PersistenceReconstructionContext(
        dataset_resolver=DummyDatasetResolver(),
        policy_codecs={},
        simulation_result_codec=None,  # type: ignore
    )


class DummyAllocationPolicy(AllocationPolicy):
    """Deterministic allocation policy for tests."""

    def decide(self, context: object) -> AllocationDecision:
        return AllocationDecision(
            reason="dummy",
            allocation_target=AllocationTarget(weights={}),
        )


class DummyWithdrawalPolicy(WithdrawalPolicy):
    """Deterministic withdrawal policy for tests."""

    def decide(self, context: object) -> WithdrawalDecision:
        return WithdrawalDecision(
            reason="dummy",
            nominal_amount=Money(Decimal("500"), Currency.EUR),
            real_amount=Money(Decimal("500"), Currency.EUR),
        )


def make_asset(asset_id: str = "acwi") -> AssetClass:
    return AssetClass(id=asset_id, name="ACWI", description="Global equities")


def make_dataset(version: str = "TEST_DATASET_v1") -> Dataset:
    """Return a minimal single-snapshot Dataset for use in ExperimentDefinition."""
    asset = make_asset()
    snapshot = MarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={asset: Decimal("100.00")},
        inflation=Decimal("0.00"),
        inflation_cumulative=Decimal("0.00"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100.00"),
    )
    return Dataset(snapshots=[snapshot], frequency="monthly", version=version)


def make_portfolio(units: str = "1000.00") -> Portfolio:
    return Portfolio(
        holdings=(AssetHolding(asset_class=make_asset(), units=Decimal(units)),)
    )


def make_experiment(name: str = "test-experiment") -> ExperimentDefinition:
    return ExperimentDefinition(
        name=name,
        description="Round-trip test experiment",
        dataset=make_dataset(),
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
    return PlannedSimulationUnit(
        cohort=CohortSpecification(start_date=date(2000, month, 1)),
        parameter_config=ParameterConfiguration(values={"withdrawal_rate": float(rate)}),
        allocation_policy=DummyAllocationPolicy(),
        withdrawal_policy=DummyWithdrawalPolicy(),
        initial_portfolio=make_portfolio(),
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


@pytest.fixture
def repo(tmp_path) -> SQLiteRepository:
    """File-based SQLite repository — isolated per test via pytest tmp_path."""
    db_file = tmp_path / "test_persistence.db"
    return SQLiteRepository(str(db_file))


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


def test_schema_creates_all_tables(repo: SQLiteRepository) -> None:
    """Verify all 9 core tables and schema_version table are created."""
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
    import sqlite3
    conn = sqlite3.connect(":memory:")
    # Re-initialise on a fresh conn (schema already created by fixture above)
    repo2 = SQLiteRepository(":memory:")
    with sqlite3.connect(":memory:") as raw_conn:
        repo3 = SQLiteRepository.__new__(SQLiteRepository)
        repo3.db_path = ":memory:"
        repo3._initialize_schema()
        rows = raw_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    # Verify via the fixture's in-memory DB instead
    import sqlite3 as _sqlite3
    _conn = _sqlite3.connect(":memory:")
    _repo = SQLiteRepository(":memory:")
    # The repo already initialised tables — just trust the save/load tests
    # as an indirect schema verification; here we check via a direct query.
    # Use a different approach: open a temp file db and inspect tables.
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp_path = f.name
    try:
        tmp_repo = SQLiteRepository(tmp_path)
        with _sqlite3.connect(tmp_path) as c:
            tables = {r[0] for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        assert expected_tables.issubset(tables), (
            f"Missing tables: {expected_tables - tables}"
        )
    finally:
        os.unlink(tmp_path)


def test_schema_version_recorded(repo: SQLiteRepository) -> None:
    """Verify schema version is recorded after initialisation."""
    import sqlite3, tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp_path = f.name
    try:
        SQLiteRepository(tmp_path)
        with sqlite3.connect(tmp_path) as c:
            row = c.execute("SELECT version FROM schema_version").fetchone()
        assert row is not None
        assert row[0] == 1
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Serializer unit tests (pure — no I/O)
# ---------------------------------------------------------------------------


class TestDecimalSerialization:
    def test_round_trip_decimal(self) -> None:
        val = Decimal("123.456")
        assert deserialize_decimal(serialize_decimal(val)) == val


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

def test_save_load_experiment_metadata(repo: SQLiteRepository) -> None:
    identity = ExperimentIdentity(name="test-exp", revision="1.0")
    experiment = make_experiment(name=identity.name)
    ctx = get_dummy_context()
    
    experiment_id = repo.save_experiment(identity, experiment, ctx)
    # Metadata is retrieved via query helper or load_experiment
    # Verify it exists by querying name
    assert repo.find_experiment_by_name(identity.name) == experiment_id


class TestParameterConfigSerialization:
    def test_round_trip_float(self) -> None:
        config = ParameterConfiguration(values={"withdrawal_rate": 0.04, "equity_pct": 0.75})
        params_json, params_hash = serialize_parameter_config(config)
        restored = deserialize_parameter_config(params_json)
        assert restored == config

    def test_round_trip_int(self) -> None:
        config = ParameterConfiguration(values={"horizon_years": 30})
        params_json, _ = serialize_parameter_config(config)
        restored = deserialize_parameter_config(params_json)
        assert restored.get("horizon_years") == 30

    def test_round_trip_string(self) -> None:
        config = ParameterConfiguration(values={"strategy": "aggressive"})
        params_json, _ = serialize_parameter_config(config)
        restored = deserialize_parameter_config(params_json)
        assert restored.get("strategy") == "aggressive"

    def test_hash_deterministic(self) -> None:
        config = ParameterConfiguration(values={"a": 1.0, "b": 2.0})
        _, hash1 = serialize_parameter_config(config)
        _, hash2 = serialize_parameter_config(config)
        assert hash1 == hash2

    def test_different_configs_different_hashes(self) -> None:
        c1 = ParameterConfiguration(values={"rate": 0.04})
        c2 = ParameterConfiguration(values={"rate": 0.05})
        _, h1 = serialize_parameter_config(c1)
        _, h2 = serialize_parameter_config(c2)
        assert h1 != h2


class TestPortfolioSerialization:
    def test_round_trip(self) -> None:
        portfolio = make_portfolio("1234.56789")
        json_str = serialize_portfolio(portfolio)
        restored = deserialize_portfolio(json_str)
        assert len(restored.holdings) == 1
        assert restored.holdings[0].asset_class.id == "acwi"
        assert restored.holdings[0].units == Decimal("1234.56789")

    def test_multi_asset_round_trip(self) -> None:
        asset1 = AssetClass(id="equity", name="Equity", description="Stocks")
        asset2 = AssetClass(id="bond", name="Bond", description="Bonds")
        portfolio = Portfolio(
            holdings=(
                AssetHolding(asset_class=asset1, units=Decimal("750")),
                AssetHolding(asset_class=asset2, units=Decimal("250")),
            )
        )
        json_str = serialize_portfolio(portfolio)
        restored = deserialize_portfolio(json_str)
        assert len(restored.holdings) == 2
        assert restored.holdings[0].asset_class.id == "equity"
        assert restored.holdings[0].units == Decimal("750")
        assert restored.holdings[1].asset_class.id == "bond"
        assert restored.holdings[1].units == Decimal("250")


class TestPolicySerialization:
    def test_policy_type_recorded(self) -> None:
        policy = DummyAllocationPolicy()
        policy_type, params_json, params_hash = serialize_policy(policy)
        assert "DummyAllocationPolicy" in policy_type

    def test_hash_deterministic(self) -> None:
        policy = DummyAllocationPolicy()
        _, _, h1 = serialize_policy(policy)
        _, _, h2 = serialize_policy(policy)
        assert h1 == h2


# ---------------------------------------------------------------------------
# Experiment round-trip tests
# ---------------------------------------------------------------------------


def test_experiment_save_and_load_name(repo: SQLiteRepository) -> None:
    """Experiment name round-trips correctly."""
    experiment = make_experiment("SWR-Study-2024")
    experiment_id = repo.save_experiment(ExperimentIdentity(name=experiment.name, revision="v1"), experiment, get_dummy_context())
    loaded = repo.load_experiment(experiment_id)
    assert loaded.name == "SWR-Study-2024"


def test_experiment_save_and_load_description(repo: SQLiteRepository) -> None:
    """Experiment description round-trips correctly."""
    experiment = make_experiment()
    experiment_id = repo.save_experiment(ExperimentIdentity(name=experiment.name, revision="v1"), experiment, get_dummy_context())
    loaded = repo.load_experiment(experiment_id)
    assert loaded.description == experiment.description


def test_experiment_save_and_load_horizon(repo: SQLiteRepository) -> None:
    """Experiment horizon_months round-trips correctly."""
    experiment = make_experiment()
    experiment_id = repo.save_experiment(ExperimentIdentity(name=experiment.name, revision="v1"), experiment, get_dummy_context())
    loaded = repo.load_experiment(experiment_id)
    assert loaded.horizon_months == 120


def test_experiment_save_and_load_initial_wealth(repo: SQLiteRepository) -> None:
    """Initial wealth Decimal value round-trips with exact precision."""
    experiment = make_experiment()
    experiment_id = repo.save_experiment(ExperimentIdentity(name=experiment.name, revision="v1"), experiment, get_dummy_context())
    loaded = repo.load_experiment(experiment_id)
    assert loaded.initial_wealth.amount == Decimal("500000.00")
    assert loaded.initial_wealth.currency == Currency.EUR


def test_experiment_save_and_load_cohort_dates(repo: SQLiteRepository) -> None:
    """Cohort start dates round-trip exactly as ISO 8601."""
    experiment = make_experiment()
    experiment_id = repo.save_experiment(ExperimentIdentity(name=experiment.name, revision="v1"), experiment, get_dummy_context())
    loaded = repo.load_experiment(experiment_id)
    assert len(loaded.cohorts) == 2
    dates = {c.start_date for c in loaded.cohorts}
    assert date(2000, 1, 1) in dates
    assert date(2000, 2, 1) in dates


def test_experiment_cohort_order_preserved(repo: SQLiteRepository) -> None:
    """Cohorts are returned ordered by start_date ascending."""
    experiment = make_experiment()
    experiment_id = repo.save_experiment(ExperimentIdentity(name=experiment.name, revision="v1"), experiment, get_dummy_context())
    loaded = repo.load_experiment(experiment_id)
    dates = [c.start_date for c in loaded.cohorts]
    assert dates == sorted(dates)


def test_duplicate_experiment_raises(repo: SQLiteRepository) -> None:
    """Saving two experiments with the same name raises DuplicateStudyError."""
    experiment = make_experiment("unique-name")
    repo.save_experiment(ExperimentIdentity(name=experiment.name, revision="v1"), experiment, get_dummy_context())
    with pytest.raises(DuplicateStudyError):
        repo.save_experiment(ExperimentIdentity(name=experiment.name, revision="v1"), experiment, get_dummy_context())


def test_load_missing_experiment_raises(repo: SQLiteRepository) -> None:
    """Loading a non-existent experiment_id raises StudyNotFoundError."""
    with pytest.raises(StudyNotFoundError):
        repo.load_experiment("00000000-0000-0000-0000-000000000000")


def test_find_experiment_by_name(repo: SQLiteRepository) -> None:
    """find_experiment_by_name returns correct experiment_id."""
    experiment = make_experiment("searchable-study")
    experiment_id = repo.save_experiment(ExperimentIdentity(name=experiment.name, revision="v1"), experiment, get_dummy_context())
    found_id = repo.find_experiment_by_name("searchable-study")
    assert found_id == experiment_id


def test_find_experiment_by_name_missing(repo: SQLiteRepository) -> None:
    """find_experiment_by_name returns None for unknown names."""
    assert repo.find_experiment_by_name("nonexistent") is None


def test_list_experiments(repo: SQLiteRepository) -> None:
    """list_experiments returns all saved experiments."""
    repo.save_experiment(make_experiment("study-a"))
    repo.save_experiment(make_experiment("study-b"))
    all_experiments = repo.list_experiments()
    names = {e["name"] for e in all_experiments}
    assert "study-a" in names
    assert "study-b" in names


# ---------------------------------------------------------------------------
# Plan round-trip tests
# ---------------------------------------------------------------------------


def test_plan_save_and_load_unit_count(repo: SQLiteRepository) -> None:
    """Plan unit count round-trips correctly."""
    experiment = make_experiment()
    experiment_id = repo.save_experiment(ExperimentIdentity(name=experiment.name, revision="v1"), experiment, get_dummy_context())
    plan = make_plan(num_units=6)
    plan_id = repo.save_plan(plan, experiment_id)
    units = repo.load_plan_units(plan_id)
    assert len(units) == 6


def test_plan_unit_order_preserved(repo: SQLiteRepository) -> None:
    """Units are returned in their original order (by unit_index)."""
    experiment = make_experiment()
    experiment_id = repo.save_experiment(ExperimentIdentity(name=experiment.name, revision="v1"), experiment, get_dummy_context())
    units = tuple(
        make_unit(month=m) for m in [3, 1, 2, 6, 4, 5]
    )
    plan = ResearchPlan(experiment_definition=experiment, units=units)
    plan_id = repo.save_plan(plan, experiment_id)
    loaded_units = repo.load_plan_units(plan_id)
    # The units were inserted in month order [3,1,2,6,4,5]; verify dates preserved
    expected_dates = [date(2000, m, 1).isoformat() for m in [3, 1, 2, 6, 4, 5]]
    actual_dates = [u[0] for u in loaded_units]
    assert actual_dates == expected_dates


def test_plan_parameter_config_round_trip(repo: SQLiteRepository) -> None:
    """ParameterConfiguration values round-trip without precision loss."""
    experiment = make_experiment()
    experiment_id = repo.save_experiment(ExperimentIdentity(name=experiment.name, revision="v1"), experiment, get_dummy_context())
    unit = PlannedSimulationUnit(
        cohort=CohortSpecification(start_date=date(2000, 1, 1)),
        parameter_config=ParameterConfiguration(values={"withdrawal_rate": 0.04, "equity_pct": 0.75}),
        allocation_policy=DummyAllocationPolicy(),
        withdrawal_policy=DummyWithdrawalPolicy(),
        initial_portfolio=make_portfolio(),
    )
    plan = ResearchPlan(experiment_definition=experiment, units=(unit,))
    plan_id = repo.save_plan(plan, experiment_id)
    loaded = repo.load_plan_units(plan_id)
    assert len(loaded) == 1
    restored_config = deserialize_parameter_config(loaded[0][2])
    assert restored_config.get("withdrawal_rate") == 0.04
    assert restored_config.get("equity_pct") == 0.75


def test_plan_portfolio_round_trip(repo: SQLiteRepository) -> None:
    """Initial portfolio persists with exact Decimal precision."""
    experiment = make_experiment()
    experiment_id = repo.save_experiment(ExperimentIdentity(name=experiment.name, revision="v1"), experiment, get_dummy_context())
    exact_units = "123456789.987654321"
    unit = PlannedSimulationUnit(
        cohort=CohortSpecification(start_date=date(2000, 1, 1)),
        parameter_config=ParameterConfiguration(values={"rate": 0.04}),
        allocation_policy=DummyAllocationPolicy(),
        withdrawal_policy=DummyWithdrawalPolicy(),
        initial_portfolio=Portfolio(
            holdings=(AssetHolding(asset_class=make_asset(), units=Decimal(exact_units)),)
        ),
    )
    plan = ResearchPlan(experiment_definition=experiment, units=(unit,))
    plan_id = repo.save_plan(plan, experiment_id)
    loaded = repo.load_plan_units(plan_id)
    restored_portfolio = deserialize_portfolio(loaded[0][7])
    assert restored_portfolio.holdings[0].units == Decimal(exact_units)


def test_plan_cohort_start_date_round_trip(repo: SQLiteRepository) -> None:
    """Cohort start_date persists and retrieves as exact ISO date."""
    experiment = make_experiment()
    experiment_id = repo.save_experiment(ExperimentIdentity(name=experiment.name, revision="v1"), experiment, get_dummy_context())
    unit = make_unit(month=7)
    plan = ResearchPlan(experiment_definition=experiment, units=(unit,))
    plan_id = repo.save_plan(plan, experiment_id)
    loaded = repo.load_plan_units(plan_id)
    assert loaded[0][0] == "2000-07-01"


def test_plan_policy_type_round_trip(repo: SQLiteRepository) -> None:
    """Policy type names are preserved on persistence."""
    experiment = make_experiment()
    experiment_id = repo.save_experiment(ExperimentIdentity(name=experiment.name, revision="v1"), experiment, get_dummy_context())
    plan = make_plan(num_units=1)
    plan_id = repo.save_plan(plan, experiment_id)
    loaded = repo.load_plan_units(plan_id)
    alloc_type = loaded[0][3]
    withd_type = loaded[0][5]
    assert "DummyAllocationPolicy" in alloc_type
    assert "DummyWithdrawalPolicy" in withd_type


# ---------------------------------------------------------------------------
# Execution result round-trip tests
# ---------------------------------------------------------------------------


def test_execution_result_save_and_load(repo: SQLiteRepository) -> None:
    """Execution result round-trips with correct unit count."""
    experiment = make_experiment()
    experiment_id = repo.save_experiment(ExperimentIdentity(name=experiment.name, revision="v1"), experiment, get_dummy_context())
    plan = make_plan(num_units=3)
    plan_id = repo.save_plan(plan, experiment_id)

    engine_def = _make_engine_def(plan)
    sim_results = tuple(make_sim_result(f"{500000 + i * 1000}") for i in range(3))
    experiment_run = ExperimentRun(definition=engine_def, simulation_results=sim_results)
    research_result = ResearchExecutionResult(plan=plan, experiment_result=experiment_run)

    result_id = repo.save_execution_result(research_result, plan_id, duration_seconds=1.5)
    loaded_results = repo.load_simulation_results(result_id)

    assert len(loaded_results) == 3


def test_execution_result_final_wealth_round_trip(repo: SQLiteRepository) -> None:
    """SimulationResult final_wealth Decimal value round-trips exactly."""
    experiment = make_experiment()
    experiment_id = repo.save_experiment(ExperimentIdentity(name=experiment.name, revision="v1"), experiment, get_dummy_context())
    plan = make_plan(num_units=1)
    plan_id = repo.save_plan(plan, experiment_id)

    exact_wealth = "987654.123456789"
    engine_def = _make_engine_def(plan)
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
    experiment_run = ExperimentRun(definition=engine_def, simulation_results=(sim_result,))
    research_result = ResearchExecutionResult(plan=plan, experiment_result=experiment_run)

    result_id = repo.save_execution_result(research_result, plan_id)
    loaded = repo.load_simulation_results(result_id)

    assert loaded[0].statistics.final_wealth.amount == Decimal(exact_wealth)
    assert loaded[0].statistics.final_wealth.currency == Currency.EUR


def test_execution_result_success_flag_round_trip(repo: SQLiteRepository) -> None:
    """SimulationResult success flag and failure_month round-trip exactly."""
    experiment = make_experiment()
    experiment_id = repo.save_experiment(ExperimentIdentity(name=experiment.name, revision="v1"), experiment, get_dummy_context())
    plan = make_plan(num_units=2)
    plan_id = repo.save_plan(plan, experiment_id)

    engine_def = _make_engine_def(plan)
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
    experiment_run = ExperimentRun(definition=engine_def, simulation_results=sim_results)
    research_result = ResearchExecutionResult(plan=plan, experiment_result=experiment_run)

    result_id = repo.save_execution_result(research_result, plan_id)
    loaded = repo.load_simulation_results(result_id)

    assert loaded[0].statistics.success is True
    assert loaded[0].statistics.failure_month is None
    assert loaded[1].statistics.success is False
    assert loaded[1].statistics.failure_month == 36


def test_execution_result_unit_order_preserved(repo: SQLiteRepository) -> None:
    """Simulation results are returned in unit_index order."""
    experiment = make_experiment()
    experiment_id = repo.save_experiment(ExperimentIdentity(name=experiment.name, revision="v1"), experiment, get_dummy_context())
    plan = make_plan(num_units=5)
    plan_id = repo.save_plan(plan, experiment_id)

    engine_def = _make_engine_def(plan)
    sim_results = tuple(
        make_sim_result(str(500000 + i * 10000)) for i in range(5)
    )
    experiment_run = ExperimentRun(definition=engine_def, simulation_results=sim_results)
    research_result = ResearchExecutionResult(plan=plan, experiment_result=experiment_run)

    result_id = repo.save_execution_result(research_result, plan_id)
    loaded = repo.load_simulation_results(result_id)

    expected_amounts = [Decimal(str(500000 + i * 10000)) for i in range(5)]
    actual_amounts = [r.statistics.final_wealth.amount for r in loaded]
    assert actual_amounts == expected_amounts


def test_execution_result_statistics_round_trip(repo: SQLiteRepository) -> None:
    """SimulationStatistics fields (max_drawdown, months_simulated) round-trip."""
    experiment = make_experiment()
    experiment_id = repo.save_experiment(ExperimentIdentity(name=experiment.name, revision="v1"), experiment, get_dummy_context())
    plan = make_plan(num_units=1)
    plan_id = repo.save_plan(plan, experiment_id)

    engine_def = _make_engine_def(plan)
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
    experiment_run = ExperimentRun(definition=engine_def, simulation_results=(sim_result,))
    research_result = ResearchExecutionResult(plan=plan, experiment_result=experiment_run)
    result_id = repo.save_execution_result(research_result, plan_id)
    loaded = repo.load_simulation_results(result_id)

    assert loaded[0].statistics.max_drawdown == pytest.approx(0.35)
    assert loaded[0].statistics.months_simulated == 360
    assert loaded[0].statistics.execution_time_seconds == pytest.approx(2.5)


def test_load_missing_execution_result_raises(repo: SQLiteRepository) -> None:
    """Loading a non-existent result_id raises ResultsNotFoundError."""
    with pytest.raises(ResultsNotFoundError):
        repo.load_execution_result("00000000-0000-0000-0000-000000000000")


def test_find_result_by_plan(repo: SQLiteRepository) -> None:
    """find_result_by_plan returns correct result_id after saving."""
    experiment = make_experiment()
    experiment_id = repo.save_experiment(ExperimentIdentity(name=experiment.name, revision="v1"), experiment, get_dummy_context())
    plan = make_plan(num_units=1)
    plan_id = repo.save_plan(plan, experiment_id)

    engine_def = _make_engine_def(plan)
    sim_results = (make_sim_result(),)
    experiment_run = ExperimentRun(definition=engine_def, simulation_results=sim_results)
    research_result = ResearchExecutionResult(plan=plan, experiment_result=experiment_run)
    result_id = repo.save_execution_result(research_result, plan_id)

    found = repo.find_result_by_plan(plan_id)
    assert found == result_id


def test_find_result_by_plan_missing(repo: SQLiteRepository) -> None:
    """find_result_by_plan returns None for unexecuted plans."""
    assert repo.find_result_by_plan("nonexistent-plan-id") is None


# ---------------------------------------------------------------------------
# Error hierarchy tests
# ---------------------------------------------------------------------------


def test_error_hierarchy() -> None:
    """Verify all custom exceptions inherit from RepositoryError."""
    assert issubclass(StudyNotFoundError, RepositoryError)
    assert issubclass(ResultsNotFoundError, RepositoryError)
    assert issubclass(DuplicateStudyError, RepositoryError)
    assert issubclass(PersistenceError, RepositoryError)
    assert issubclass(CorruptedDatabaseError, RepositoryError)


# ---------------------------------------------------------------------------
# Isolation / FK tests
# ---------------------------------------------------------------------------


def test_foreign_key_plan_requires_experiment(repo: SQLiteRepository) -> None:
    """Saving a plan with a nonexistent experiment_id raises an error."""
    plan = make_plan(num_units=1)
    with pytest.raises((RepositoryError, Exception)):
        repo.save_plan(plan, "nonexistent-experiment-id")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_engine_def(plan: ResearchPlan):
    """Build a minimal engine ExperimentDefinition stub for test ExperimentRun."""
    from engine.application.simulation import ExperimentDefinition as EngineExperimentDefinition
    from engine.application.simulation_context import SimulationContext
    # Create minimal contexts matching unit count
    contexts = []
    for unit in plan.units:
        from engine.domain.model.dataset import Dataset
        from engine.domain.model.market_snapshot import MarketSnapshot
        from engine.domain.model.asset import AssetClass as _A
        asset = _A(id="acwi", name="ACWI", description="Global equities")
        from decimal import Decimal as D
        snap = MarketSnapshot(
            date=unit.cohort.start_date,
            index_levels={asset: D("100")},
            inflation=D("0"),
            inflation_cumulative=D("0"),
            is_ath=True,
            is_underwater=False,
            running_ath=D("100"),
        )
        dataset = Dataset(snapshots=[snap], frequency="monthly", version="v1")
        ctx = SimulationContext(
            start_date=unit.cohort.start_date,
            horizon_months=plan.experiment_definition.horizon_months,
            initial_portfolio=unit.initial_portfolio,
            dataset=dataset,
            allocation_policy=unit.allocation_policy,
            withdrawal_policy=unit.withdrawal_policy,
        )
        contexts.append(ctx)
    return EngineExperimentDefinition(
        name=plan.experiment_definition.name,
        description=plan.experiment_definition.description,
        simulation_contexts=tuple(contexts),
    )
