"""Tests for concrete persistence codec implementations (Package P3.1).

Covers:
- Reconstruction context creation with concrete codecs
- Dataset resolution: valid → Dataset, unknown → RepositoryError
- AllocationPolicy round-trip (dump → load)
- WithdrawalPolicy round-trip (dump → load)
- SimulationResult round-trip (dump → load with identical fields)
- Decimal precision lossless preservation
- Month ordering preservation
- SQLiteRepository integration with production codecs
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from engine.application.simulation import (
    SimulationResult,
    SimulationStatistics,
    SimulationTimeline,
)
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
    AllocationPolicyCodec,
    DefaultDatasetResolver,
    PersistenceReconstructionContext,
    RepositoryError,
    SimulationResultCodec,
    StudyNotFoundError,
    WithdrawalPolicyCodec,
)
from infrastructure.persistence.codecs import (
    _ConcreteAllocationPolicy,
    _ConcreteWithdrawalPolicy,
)
from infrastructure.persistence.sqlite_repository import PolicyKind

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

_ASSET = AssetClass(id="acwi", name="ACWI", description="Global equities")


def _make_shared_dataset() -> Dataset:
    snapshot = MarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={_ASSET: Decimal("100.00")},
        inflation=Decimal("0.00"),
        inflation_cumulative=Decimal("0.00"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100.00"),
    )
    return Dataset(snapshots=[snapshot], frequency="monthly", version="TEST_v1")


_TEST_DATASET: Dataset = _make_shared_dataset()


# ---------------------------------------------------------------------------
# Test policies
# ---------------------------------------------------------------------------


class _TestAllocationPolicy(AllocationPolicy):
    """Allocation policy with a configurable equity_allocation."""

    def __init__(self, equity_allocation: str = "0.75") -> None:
        self.equity_allocation = equity_allocation

    def decide(self, context: object) -> AllocationDecision:
        return AllocationDecision(
            reason="test",
            allocation_target=AllocationTarget(weights={}),
        )


class _TestWithdrawalPolicy(WithdrawalPolicy):
    """Withdrawal policy with a configurable withdrawal_rate."""

    def __init__(self, withdrawal_rate: str = "0.04") -> None:
        self.withdrawal_rate = withdrawal_rate

    def decide(self, context: object) -> WithdrawalDecision:
        return WithdrawalDecision(
            reason="test",
            nominal_amount=Money(Decimal("1000"), Currency.EUR),
            real_amount=Money(Decimal("1000"), Currency.EUR),
        )


# ---------------------------------------------------------------------------
# Reconstruction context
# ---------------------------------------------------------------------------


def test_reconstruction_context_creates_with_concrete_codecs() -> None:
    resolver = DefaultDatasetResolver(datasets={"TEST": _TEST_DATASET})
    alloc_codec = AllocationPolicyCodec()
    withd_codec = WithdrawalPolicyCodec()
    sim_codec = SimulationResultCodec()

    ctx = PersistenceReconstructionContext(
        dataset_resolver=resolver,
        policy_codecs={
            ("allocation", "AllocationPolicy"): alloc_codec,
            ("withdrawal", "WithdrawalPolicy"): withd_codec,
        },
        simulation_result_codec=sim_codec,
    )
    assert ctx.dataset_resolver is resolver
    assert ctx.simulation_result_codec is sim_codec
    assert len(ctx.policy_codecs) == 2


# ---------------------------------------------------------------------------
# DatasetResolver tests
# ---------------------------------------------------------------------------


class TestDefaultDatasetResolver:
    def test_resolve_valid_identifier(self) -> None:
        resolver = DefaultDatasetResolver(datasets={"ACWI_2024": _TEST_DATASET})
        result = resolver.resolve("ACWI_2024")
        assert result is _TEST_DATASET
        assert result.version == "TEST_v1"

    def test_resolve_unknown_identifier_raises(self) -> None:
        resolver = DefaultDatasetResolver(datasets={"KNOWN": _TEST_DATASET})
        with pytest.raises(StudyNotFoundError) as exc:
            resolver.resolve("UNKNOWN")
        assert "Dataset not found" in str(exc.value)

    def test_resolve_unknown_identifier_is_repository_error(self) -> None:
        resolver = DefaultDatasetResolver(datasets={})
        with pytest.raises(RepositoryError):
            resolver.resolve("anything")

    def test_resolve_empty_registry(self) -> None:
        resolver = DefaultDatasetResolver()
        with pytest.raises(StudyNotFoundError):
            resolver.resolve("anything")


# ---------------------------------------------------------------------------
# PolicyCodec round-trip tests
# ---------------------------------------------------------------------------


class TestAllocationPolicyCodec:
    def test_codec_has_required_attributes(self) -> None:
        codec = AllocationPolicyCodec()
        assert codec.policy_type == "AllocationPolicy"
        assert codec.policy_kind == PolicyKind.ALLOCATION

    def test_dump_returns_mapping_with_equity_allocation(self) -> None:
        codec = AllocationPolicyCodec()
        policy = _TestAllocationPolicy(equity_allocation="0.75")
        result = codec.dump(policy)
        assert isinstance(result, Mapping)
        assert result["equity_allocation"] == "0.75"

    def test_dump_default_equity_when_missing(self) -> None:
        codec = AllocationPolicyCodec()

        class MinimalPolicy:
            pass

        result = codec.dump(MinimalPolicy())
        assert result["equity_allocation"] == "1.0"

    def test_load_returns_concrete_policy(self) -> None:
        codec = AllocationPolicyCodec()
        policy = codec.load({"equity_allocation": "0.60"})
        assert isinstance(policy, _ConcreteAllocationPolicy)
        assert policy.equity_allocation == "0.60"

    def test_load_default_equity_when_missing(self) -> None:
        codec = AllocationPolicyCodec()
        policy = codec.load({})
        assert policy.equity_allocation == "1.0"

    def test_round_trip_preserves_equity_allocation(self) -> None:
        codec = AllocationPolicyCodec()
        original = _TestAllocationPolicy(equity_allocation="0.85")
        dumped = codec.dump(original)
        loaded = codec.load(dumped)
        assert loaded.equity_allocation == "0.85"

    def test_round_trip_produces_isinstance_equivalent(self) -> None:
        codec = AllocationPolicyCodec()
        original = _TestAllocationPolicy()
        dumped = codec.dump(original)
        loaded = codec.load(dumped)
        assert isinstance(loaded, _ConcreteAllocationPolicy)


class TestWithdrawalPolicyCodec:
    def test_codec_has_required_attributes(self) -> None:
        codec = WithdrawalPolicyCodec()
        assert codec.policy_type == "WithdrawalPolicy"
        assert codec.policy_kind == PolicyKind.WITHDRAWAL

    def test_dump_returns_mapping_with_withdrawal_rate(self) -> None:
        codec = WithdrawalPolicyCodec()
        policy = _TestWithdrawalPolicy(withdrawal_rate="0.03")
        result = codec.dump(policy)
        assert isinstance(result, Mapping)
        assert result["withdrawal_rate"] == "0.03"

    def test_dump_default_rate_when_missing(self) -> None:
        codec = WithdrawalPolicyCodec()

        class MinimalPolicy:
            pass

        result = codec.dump(MinimalPolicy())
        assert result["withdrawal_rate"] == "0.04"

    def test_load_returns_concrete_policy(self) -> None:
        codec = WithdrawalPolicyCodec()
        policy = codec.load({"withdrawal_rate": "0.05"})
        assert isinstance(policy, _ConcreteWithdrawalPolicy)
        assert policy.withdrawal_rate == "0.05"

    def test_load_default_rate_when_missing(self) -> None:
        codec = WithdrawalPolicyCodec()
        policy = codec.load({})
        assert policy.withdrawal_rate == "0.04"

    def test_round_trip_preserves_withdrawal_rate(self) -> None:
        codec = WithdrawalPolicyCodec()
        original = _TestWithdrawalPolicy(withdrawal_rate="0.035")
        dumped = codec.dump(original)
        loaded = codec.load(dumped)
        assert loaded.withdrawal_rate == "0.035"

    def test_round_trip_produces_isinstance_equivalent(self) -> None:
        codec = WithdrawalPolicyCodec()
        original = _TestWithdrawalPolicy()
        dumped = codec.dump(original)
        loaded = codec.load(dumped)
        assert isinstance(loaded, _ConcreteWithdrawalPolicy)


# ---------------------------------------------------------------------------
# SimulationResult round-trip tests
# ---------------------------------------------------------------------------


class TestSimulationResultCodec:
    def make_sim_result(
        self,
        final_wealth: str = "500000.00",
        success: bool = True,
        months_simulated: int = 120,
    ) -> SimulationResult:
        return SimulationResult(
            timeline=SimulationTimeline(monthly_results=()),
            statistics=SimulationStatistics(
                final_wealth=Money(Decimal(final_wealth), Currency.EUR),
                max_drawdown=0.05,
                success=success,
                failure_month=None if success else 36,
                months_simulated=months_simulated,
                execution_time_seconds=0.01,
            ),
        )

    def test_dump_returns_serialized_simulation_result(self) -> None:
        codec = SimulationResultCodec()
        result = self.make_sim_result()
        serialized = codec.dump(result)
        assert isinstance(serialized.statistics_payload_json, str)
        assert isinstance(serialized.monthly_payloads_json, tuple)

    def test_round_trip_statistics(self) -> None:
        codec = SimulationResultCodec()
        original = self.make_sim_result(
            final_wealth="750000.00",
            months_simulated=360,
        )
        serialized = codec.dump(original)
        loaded = codec.load(
            serialized.statistics_payload_json,
            serialized.monthly_payloads_json,
        )
        assert loaded.statistics.final_wealth.amount == Decimal("750000.00")
        assert loaded.statistics.final_wealth.currency == Currency.EUR
        assert loaded.statistics.months_simulated == 360
        assert loaded.statistics.execution_time_seconds == 0.01

    def test_round_trip_success_flag(self) -> None:
        codec = SimulationResultCodec()
        original = self.make_sim_result(success=True)
        serialized = codec.dump(original)
        loaded = codec.load(
            serialized.statistics_payload_json,
            serialized.monthly_payloads_json,
        )
        assert loaded.statistics.success is True
        assert loaded.statistics.failure_month is None

    def test_round_trip_failure_state(self) -> None:
        codec = SimulationResultCodec()
        original = self.make_sim_result(success=False)
        serialized = codec.dump(original)
        loaded = codec.load(
            serialized.statistics_payload_json,
            serialized.monthly_payloads_json,
        )
        assert loaded.statistics.success is False
        assert loaded.statistics.failure_month == 36

    def test_round_trip_max_drawdown(self) -> None:
        codec = SimulationResultCodec()
        original = self.make_sim_result()
        serialized = codec.dump(original)
        loaded = codec.load(
            serialized.statistics_payload_json,
            serialized.monthly_payloads_json,
        )
        assert loaded.statistics.max_drawdown == 0.05

    def test_decimal_precision_preserved(self) -> None:
        codec = SimulationResultCodec()
        precise = "123456789.987654321"
        original = self.make_sim_result(final_wealth=precise)
        serialized = codec.dump(original)
        loaded = codec.load(
            serialized.statistics_payload_json,
            serialized.monthly_payloads_json,
        )
        assert loaded.statistics.final_wealth.amount == Decimal(precise)

    def test_round_trip_empty_timeline(self) -> None:
        codec = SimulationResultCodec()
        original = self.make_sim_result()
        serialized = codec.dump(original)
        loaded = codec.load(
            serialized.statistics_payload_json,
            serialized.monthly_payloads_json,
        )
        assert len(loaded.timeline.monthly_results) == 0

    def test_monthly_order_preserved(self) -> None:
        codec = SimulationResultCodec()

        def _make_monthly(date_str: str, value: str) -> Any:
            snap = MarketSnapshot(
                date=date.fromisoformat(date_str),
                index_levels={_ASSET: Decimal("100.00")},
                inflation=Decimal("0.00"),
                inflation_cumulative=Decimal("0.00"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100.00"),
            )
            from engine.application.simulation import MonthlyResult
            return MonthlyResult(
                date=date.fromisoformat(date_str),
                period_index=0,
                market_snapshot=snap,
                portfolio=Portfolio(
                    holdings=(
                        AssetHolding(
                            asset_class=_ASSET,
                            units=Decimal(value),
                        ),
                    )
                ),
                allocation=None,
                allocation_target=None,
                allocation_drift=None,
                withdrawal_decision=None,
                rebalance_result=None,
                drawdown=0.0,
                cumulative_return=0.0,
                cumulative_inflation=0.0,
                events=(),
            )

        monthly = (
            _make_monthly("2000-01-01", "500000"),
            _make_monthly("2000-02-01", "510000"),
            _make_monthly("2000-03-01", "520000"),
        )
        original = SimulationResult(
            timeline=SimulationTimeline(monthly_results=monthly),
            statistics=SimulationStatistics(
                final_wealth=Money(Decimal("520000"), Currency.EUR),
                max_drawdown=0.0,
                success=True,
                failure_month=None,
                months_simulated=3,
                execution_time_seconds=0.01,
            ),
        )

        serialized = codec.dump(original)
        loaded = codec.load(
            serialized.statistics_payload_json,
            serialized.monthly_payloads_json,
        )

        assert len(loaded.timeline.monthly_results) == 3
        expected_dates = [
            date(2000, 1, 1),
            date(2000, 2, 1),
            date(2000, 3, 1),
        ]
        actual_dates = [
            mr.date for mr in loaded.timeline.monthly_results
        ]
        assert actual_dates == expected_dates

    def test_monthly_portfolio_value_preserved(self) -> None:
        codec = SimulationResultCodec()
        from engine.application.simulation import MonthlyResult

        snap = MarketSnapshot(
            date=date(2000, 1, 1),
            index_levels={_ASSET: Decimal("100.00")},
            inflation=Decimal("0.00"),
            inflation_cumulative=Decimal("0.00"),
            is_ath=True,
            is_underwater=False,
            running_ath=Decimal("100.00"),
        )
        mr = MonthlyResult(
            date=date(2000, 1, 1),
            period_index=0,
            market_snapshot=snap,
            portfolio=Portfolio(
                holdings=(
                    AssetHolding(
                        asset_class=_ASSET,
                        units=Decimal("98765.4321"),
                    ),
                )
            ),
            allocation=None,
            allocation_target=None,
            allocation_drift=None,
            withdrawal_decision=None,
            rebalance_result=None,
            drawdown=0.05,
            cumulative_return=0.10,
            cumulative_inflation=0.02,
            events=(),
        )
        original = SimulationResult(
            timeline=SimulationTimeline(monthly_results=(mr,)),
            statistics=SimulationStatistics(
                final_wealth=Money(Decimal("500000"), Currency.EUR),
                max_drawdown=0.05,
                success=True,
                failure_month=None,
                months_simulated=1,
                execution_time_seconds=0.01,
            ),
        )

        serialized = codec.dump(original)
        loaded = codec.load(
            serialized.statistics_payload_json,
            serialized.monthly_payloads_json,
        )

        loaded_mr = loaded.timeline.monthly_results[0]
        assert loaded_mr.portfolio.holdings[0].units == Decimal("98765.4321")
        assert loaded_mr.drawdown == 0.05
        assert loaded_mr.cumulative_return == 0.10
        assert loaded_mr.cumulative_inflation == 0.02

    def test_multiple_serializations_are_independent(self) -> None:
        codec = SimulationResultCodec()
        r1 = self.make_sim_result(final_wealth="100000.00")
        r2 = self.make_sim_result(final_wealth="200000.00")

        s1 = codec.dump(r1)
        s2 = codec.dump(r2)

        l1 = codec.load(s1.statistics_payload_json, s1.monthly_payloads_json)
        l2 = codec.load(s2.statistics_payload_json, s2.monthly_payloads_json)

        assert l1.statistics.final_wealth.amount == Decimal("100000.00")
        assert l2.statistics.final_wealth.amount == Decimal("200000.00")


# ---------------------------------------------------------------------------
# SQLiteRepository integration test with concrete codecs
# ---------------------------------------------------------------------------


def _make_experiment(dataset: Dataset, name: str = "codec-test-exp") -> Any:
    from research.domain.cohort.specification import CohortSpecification
    from research.domain.experiment.definition import ExperimentDefinition

    return ExperimentDefinition(
        name=name,
        description="Integration test with concrete codecs",
        dataset=dataset,
        horizon_months=120,
        initial_wealth=Money(Decimal("500000.00"), Currency.EUR),
        cohorts=(
            CohortSpecification(start_date=date(2000, 1, 1)),
        ),
        allocation_policies=(_TestAllocationPolicy(),),
        withdrawal_policies=(_TestWithdrawalPolicy(),),
    )


def _make_plan(experiment: Any, num_units: int = 2) -> Any:
    from research.domain.cohort.specification import CohortSpecification
    from research.domain.parameter.configuration import (
        ParameterConfiguration,
    )
    from research.domain.plan import PlannedSimulationUnit, ResearchPlan

    units = tuple(
        PlannedSimulationUnit(
            cohort=CohortSpecification(
                start_date=date(2000, month, 1)
            ),
            parameter_config=ParameterConfiguration(
                values={"rate": 0.04}
            ),
            allocation_policy=_TestAllocationPolicy(),
            withdrawal_policy=_TestWithdrawalPolicy(),
            initial_portfolio=Portfolio(
                holdings=(
                    AssetHolding(
                        asset_class=_ASSET, units=Decimal("1000.00")
                    ),
                )
            ),
        )
        for month in range(1, num_units + 1)
    )
    return ResearchPlan(
        experiment_definition=experiment, units=units
    )


def test_sqlite_repository_integration_with_concrete_codecs(
    tmp_path: Path,
) -> None:
    from infrastructure.persistence import SQLiteRepository
    from infrastructure.persistence.sqlite_repository import (
        ExperimentIdentity,
    )

    resolver = DefaultDatasetResolver(
        datasets={"TEST_v1": _TEST_DATASET}
    )
    ctx = PersistenceReconstructionContext(
        dataset_resolver=resolver,
        policy_codecs={
            ("allocation", "AllocationPolicy"): AllocationPolicyCodec(),
            ("withdrawal", "WithdrawalPolicy"): WithdrawalPolicyCodec(),
        },
        simulation_result_codec=SimulationResultCodec(),
    )

    db_file = tmp_path / "integration_test.db"
    repo = SQLiteRepository(str(db_file))

    experiment = _make_experiment(_TEST_DATASET)
    exp_id = repo.save_experiment(
        ExperimentIdentity(
            name=experiment.name, revision="v1"
        ),
        experiment,
        ctx,
    )
    loaded_exp = repo.load_experiment(exp_id, ctx)
    assert loaded_exp.name == experiment.name
    assert loaded_exp.horizon_months == 120
    assert loaded_exp.initial_wealth.amount == Decimal("500000.00")

    plan = _make_plan(experiment, num_units=2)
    plan_id = repo.save_plan(plan, exp_id, ctx)
    loaded_plan = repo.load_plan(plan_id, ctx)
    assert len(loaded_plan.units) == 2

    sim_result = SimulationResult(
        timeline=SimulationTimeline(monthly_results=()),
        statistics=SimulationStatistics(
            final_wealth=Money(Decimal("550000.00"), Currency.EUR),
            max_drawdown=0.10,
            success=True,
            failure_month=None,
            months_simulated=120,
            execution_time_seconds=0.05,
        ),
    )
    sim_contexts = tuple(
        _build_sim_context(unit, experiment)
        for unit in plan.units
    )
    from engine.application.simulation import (
        ExperimentDefinition as EngineExperimentDefinition,
        ExperimentRun,
    )
    from research.orchestration.result import ResearchExecutionResult

    engine_def = EngineExperimentDefinition(
        name=experiment.name,
        description=experiment.description,
        simulation_contexts=sim_contexts,
    )
    experiment_run = ExperimentRun(
        definition=engine_def,
        simulation_results=(sim_result, sim_result),
    )
    research_result = ResearchExecutionResult(
        plan=plan, experiment_result=experiment_run
    )

    result_id = repo.save_execution_result(
        plan_id, research_result, ctx, duration_seconds=1.0
    )
    loaded_result = repo.load_execution_result(result_id, ctx)
    assert len(loaded_result.results) == 2
    assert (
        loaded_result.results[0].statistics.final_wealth.amount
        == Decimal("550000.00")
    )


def _build_sim_context(
    unit: Any, experiment: Any
) -> Any:
    from engine.application.simulation_context import (
        SimulationContext,
    )

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
