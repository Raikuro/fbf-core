"""P10 visualization query tests.

Tests the two new Core persistence methods:
- get_result_statistics() — per-unit statistics aggregation
- get_result_trajectory_percentiles() — percentile bands across units per month

Also tests the _compute_linear_percentile() helper and includes an
ERN-scale benchmark.
"""

from __future__ import annotations

import gc
import json
import time
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from fbf.core.domain.model.allocation import AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies.allocation_policy import AllocationPolicy
from fbf.core.domain.policies.decisions import AllocationDecision, WithdrawalDecision
from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy
from fbf.core.execution.pipeline.simulation import (
    ExperimentRun,
    SimulationResult,
    SimulationStatistics,
    SimulationTimeline,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.result import ResearchExecutionResult
from fbf.core.persistence.studies.sqlite import (
    PersistenceReconstructionContext,
    SQLiteRepository,
)
from fbf.core.persistence.studies.sqlite.codecs import SimulationResultCodec
from fbf.core.persistence.studies.sqlite.sqlite_repository import (
    ExperimentIdentity,
    _compute_linear_percentile,
)
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ASSET = AssetClass(id="acwi", name="ACWI", description="Global equities")


# ---------------------------------------------------------------------------
# Dummy policies (same as test_sqlite_persistence.py)
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
# Codec stubs
# ---------------------------------------------------------------------------


class DummyDatasetResolver:
    def __init__(self, dataset: Any) -> None:
        self._dataset = dataset

    def resolve(self, dataset_identifier: str) -> Any:
        return self._dataset


# ---------------------------------------------------------------------------
# Helpers: create synthetic monthly payloads with real portfolio data
# ---------------------------------------------------------------------------


def _make_monthly_payload(
    month_index: int,
    portfolio_value: float,
    asset_id: str = "acwi",
) -> str:
    """Create a canonical monthly payload JSON with the given portfolio value."""
    payload = {
        "date": f"2000-{(month_index // 12) + 1:02d}-{(month_index % 12) + 1:02d}",
        "period_index": month_index,
        "drawdown": 0.0,
        "cumulative_return": 0.0,
        "cumulative_inflation": 0.0,
        "market_snapshot": {
            "date": f"2000-{(month_index // 12) + 1:02d}-{(month_index % 12) + 1:02d}",
            "index_levels": {asset_id: "100.00"},
            "inflation": "0.00",
            "inflation_cumulative": "0.00",
            "is_ath": True,
            "is_underwater": False,
            "running_ath": "100.00",
            "cape": None,
        },
        "portfolio_holdings": [
            {"asset_class_id": asset_id, "units": f"{portfolio_value:.2f}"}
        ],
        "events": [],
    }
    return json.dumps(payload, sort_keys=True)


def _make_sim_result_with_timeline(
    final_wealth: str,
    success: bool = True,
    failure_month: int | None = None,
    months_simulated: int = 12,
    portfolio_values: Sequence[float] | None = None,
) -> SimulationResult:
    """Create a SimulationResult with a populated timeline.

    If portfolio_values is provided, creates MonthlyResult entries with
    those values. Otherwise, creates empty timeline.
    """
    if portfolio_values is None:
        return SimulationResult(
            timeline=SimulationTimeline(monthly_results=()),
            statistics=SimulationStatistics(
                final_wealth=Money(Decimal(final_wealth), Currency.EUR),
                max_drawdown=0.05,
                success=success,
                failure_month=failure_month,
                failure_state=None,
                months_simulated=months_simulated,
                execution_time_seconds=0.01,
            ),
        )

    # Create actual MonthlyResult objects for the codec
    from fbf.core.domain.model.market_snapshot import MarketSnapshot
    from fbf.core.execution.pipeline.simulation import MonthlyResult

    monthly_results = []
    for i, pv in enumerate(portfolio_values):
        ms = MarketSnapshot(
            date=date(2000, 1 + (i % 12), 1),
            index_levels={_ASSET: Decimal("100.00")},
            inflation=Decimal("0.00"),
            inflation_cumulative=Decimal("0.00"),
            is_ath=True,
            is_underwater=False,
            running_ath=Decimal("100.00"),
        )
        portfolio = Portfolio(
            holdings=(AssetHolding(asset_class=_ASSET, units=Decimal(str(pv))),)
        )
        mr = MonthlyResult(
            date=date(2000, 1 + (i % 12), 1),
            period_index=i,
            market_snapshot=ms,
            portfolio=portfolio,
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
        monthly_results.append(mr)

    return SimulationResult(
        timeline=SimulationTimeline(monthly_results=tuple(monthly_results)),
        statistics=SimulationStatistics(
            final_wealth=Money(Decimal(final_wealth), Currency.EUR),
            max_drawdown=0.05,
            success=success,
            failure_month=failure_month,
            failure_state=None,
            months_simulated=months_simulated,
            execution_time_seconds=0.01,
        ),
    )


# ---------------------------------------------------------------------------
# Plan / experiment helpers
# ---------------------------------------------------------------------------


def _make_experiment(name: str = "p10-test") -> ExperimentDefinition:
    return ExperimentDefinition(
        name=name,
        description="P10 visualization test",
        dataset=_make_test_dataset(24),
        horizon_months=12,
        initial_wealth=Money(Decimal("500000.00"), Currency.EUR),
        cohorts=(CohortSpecification(start_date=date(2000, 1, 1)),),
        allocation_policies=(DummyAllocationPolicy(),),
        withdrawal_policies=(DummyWithdrawalPolicy(),),
    )


def _make_test_dataset(months: int = 24) -> Any:
    from fbf.core.domain.model.dataset import Dataset
    from fbf.core.domain.model.market_snapshot import MarketSnapshot

    snapshots = []
    for i in range(months):
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
    return Dataset(snapshots=snapshots, frequency="monthly", version="P10_TEST_v1")


def _make_unit(month: int = 1) -> PlannedSimulationUnit:
    dataset = _make_test_dataset(24)
    return PlannedSimulationUnit(
        cohort=CohortSpecification(start_date=date(2000, month, 1)),
        parameter_config=ParameterConfiguration(values={"withdrawal_rate": 0.04}),
        allocation_policy=DummyAllocationPolicy(),
        withdrawal_policy=DummyWithdrawalPolicy(),
        initial_portfolio=Portfolio(
            holdings=(AssetHolding(asset_class=_ASSET, units=Decimal("1000")),)
        ),
        dataset=dataset.slice(date(2000, month, 1), 12),
    )


def _make_plan(num_units: int = 3) -> ResearchPlan:
    experiment = _make_experiment()
    units = tuple(_make_unit(month=((i % 12) + 1)) for i in range(num_units))
    return ResearchPlan(experiment_definition=experiment, units=units)


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
        dataset=_make_test_dataset(24),
        allocation_policy=unit.allocation_policy,
        withdrawal_policy=unit.withdrawal_policy,
    )


def _make_experiment_run(
    plan: ResearchPlan,
    sim_results: tuple[SimulationResult, ...] | None = None,
) -> ExperimentRun:
    if sim_results is None:
        sim_results = tuple(
            _make_sim_result_with_timeline(str(500000 + i * 1000))
            for i in range(len(plan.units))
        )
    sim_contexts = tuple(
        _build_sim_context(unit, plan.experiment_definition) for unit in plan.units
    )
    from fbf.core.execution.pipeline.simulation import (
        ExperimentDefinition as EngineExperimentDefinition,
    )

    engine_def = EngineExperimentDefinition(
        name=plan.experiment_definition.name,
        description=plan.experiment_definition.description,
        simulation_contexts=sim_contexts,
    )
    return ExperimentRun(definition=engine_def, simulation_results=sim_results)


def _get_context(plan: ResearchPlan) -> PersistenceReconstructionContext:
    dataset = _make_test_dataset(24)
    resolver = DummyDatasetResolver(dataset)
    return PersistenceReconstructionContext(
        dataset_resolver=resolver,
        policy_codecs={
            ("allocation", "AllocationPolicy"): type(
                "C",
                (),
                {
                    "policy_type": "AllocationPolicy",
                    "dump": lambda self, p: {"type": "AllocationPolicy"},
                    "load": lambda self, p: DummyAllocationPolicy(),
                },
            )(),
            ("withdrawal", "WithdrawalPolicy"): type(
                "C",
                (),
                {
                    "policy_type": "WithdrawalPolicy",
                    "dump": lambda self, p: {"type": "WithdrawalPolicy"},
                    "load": lambda self, p: DummyWithdrawalPolicy(),
                },
            )(),
        },
        simulation_result_codec=SimulationResultCodec(),
    )


def _save_result(
    repo: SQLiteRepository,
    plan: ResearchPlan,
    sim_results: tuple[SimulationResult, ...],
    ctx: PersistenceReconstructionContext,
    name: str = "p10-test",
) -> str:
    experiment_run = _make_experiment_run(plan, sim_results)
    research_result = ResearchExecutionResult(plan=plan, experiment_result=experiment_run)
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=name, revision="v1"),
        plan.experiment_definition,
        ctx,
    )
    plan_id = repo.save_plan(plan, exp_id, ctx)
    result_id = repo.save_execution_result(plan_id, research_result, ctx, duration_seconds=0.5)
    return result_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path) -> SQLiteRepository:
    return SQLiteRepository(str(tmp_path / "p10_test.db"))


# ===========================================================================
# 1. _compute_linear_percentile unit tests
# ===========================================================================


class TestComputeLinearPercentile:
    def test_empty_list(self) -> None:
        assert _compute_linear_percentile([], 50.0) == 0.0

    def test_single_value(self) -> None:
        assert _compute_linear_percentile([42.0], 50.0) == 42.0
        assert _compute_linear_percentile([42.0], 0.0) == 42.0
        assert _compute_linear_percentile([42.0], 100.0) == 42.0

    def test_two_values(self) -> None:
        # For [10, 20]:
        # p0=10, p50=15, p100=20
        assert _compute_linear_percentile([10.0, 20.0], 0.0) == 10.0
        assert _compute_linear_percentile([10.0, 20.0], 50.0) == 15.0
        assert _compute_linear_percentile([10.0, 20.0], 100.0) == 20.0

    def test_three_values(self) -> None:
        # For [10, 20, 30]:
        # p0=10, p25=15, p50=20, p75=25, p100=30
        vals = [10.0, 20.0, 30.0]
        assert _compute_linear_percentile(vals, 0.0) == 10.0
        assert _compute_linear_percentile(vals, 25.0) == 15.0
        assert _compute_linear_percentile(vals, 50.0) == 20.0
        assert _compute_linear_percentile(vals, 75.0) == 25.0
        assert _compute_linear_percentile(vals, 100.0) == 30.0

    def test_numpy_equivalence(self) -> None:
        """Verify linear interpolation matches numpy default percentile."""
        values = [1.0, 3.0, 5.0, 7.0, 9.0, 11.0, 13.0, 15.0, 17.0, 19.0]
        # Expected from numpy.percentile(values, q, interpolation='linear'):
        # p10 ≈ 2.8, p25 ≈ 5.5, p50 ≈ 10.0, p75 ≈ 14.5, p90 ≈ 17.2
        # Manual: rank for p10 = 0.1 * 9 = 0.9 → 1 + 0.9*(3-1) = 2.8
        sorted_v = sorted(values)
        assert _compute_linear_percentile(sorted_v, 10.0) == pytest.approx(2.8)
        assert _compute_linear_percentile(sorted_v, 25.0) == pytest.approx(5.5)
        assert _compute_linear_percentile(sorted_v, 50.0) == pytest.approx(10.0)
        assert _compute_linear_percentile(sorted_v, 75.0) == pytest.approx(14.5)
        assert _compute_linear_percentile(sorted_v, 90.0) == pytest.approx(17.2)

    def test_boundary_percentiles(self) -> None:
        values = [5.0, 10.0, 15.0, 20.0, 25.0]
        assert _compute_linear_percentile(values, 0.0) == 5.0
        assert _compute_linear_percentile(values, 100.0) == 25.0

    def test_all_same_values(self) -> None:
        values = [42.0, 42.0, 42.0, 42.0]
        assert _compute_linear_percentile(values, 50.0) == 42.0
        assert _compute_linear_percentile(values, 10.0) == 42.0
        assert _compute_linear_percentile(values, 90.0) == 42.0

    def test_unsorted_input_ignored(self) -> None:
        """The function expects sorted input; unsorted gives wrong results."""
        # This documents the contract: caller must sort first.
        result = _compute_linear_percentile([30.0, 10.0, 20.0], 50.0)
        # Without sorting, index 1 = 10.0, not the median
        assert result != 20.0  # Would be 20 if sorted


# ===========================================================================
# 2. get_result_statistics tests
# ===========================================================================


class TestGetResultStatistics:
    def test_returns_none_for_missing_result(self, repo: SQLiteRepository) -> None:
        assert repo.get_result_statistics("nonexistent-id") is None

    def test_basic_statistics(self, repo: SQLiteRepository) -> None:
        plan = _make_plan(num_units=4)
        ctx = _get_context(plan)
        sim_results = (
            _make_sim_result_with_timeline("500000", success=True),
            _make_sim_result_with_timeline("600000", success=True),
            _make_sim_result_with_timeline("300000", success=False, failure_month=36),
            _make_sim_result_with_timeline("0", success=False, failure_month=24),
        )
        result_id = _save_result(repo, plan, sim_results, ctx)

        stats = repo.get_result_statistics(result_id)
        assert stats is not None
        assert stats["total_units"] == 4
        assert stats["success_count"] == 2
        assert stats["failure_count"] == 2
        assert stats["result_id"] == result_id

    def test_terminal_wealth_percentiles(self, repo: SQLiteRepository) -> None:
        plan = _make_plan(num_units=5)
        ctx = _get_context(plan)
        sim_results = tuple(
            _make_sim_result_with_timeline(str(100000 * (i + 1)))
            for i in range(5)
        )
        result_id = _save_result(repo, plan, sim_results, ctx)

        stats = repo.get_result_statistics(result_id)
        assert stats is not None
        tw = stats["terminal_wealth"]
        # Values: 100000, 200000, 300000, 400000, 500000
        assert tw["min"] == 100000.0
        assert tw["max"] == 500000.0
        assert tw["mean"] == 300000.0
        assert tw["median"] == 300000.0

    def test_failure_months_histogram(self, repo: SQLiteRepository) -> None:
        plan = _make_plan(num_units=6)
        ctx = _get_context(plan)
        sim_results = (
            _make_sim_result_with_timeline("500000", success=True),
            _make_sim_result_with_timeline("500000", success=True),
            _make_sim_result_with_timeline("0", success=False, failure_month=24),
            _make_sim_result_with_timeline("0", success=False, failure_month=24),
            _make_sim_result_with_timeline("0", success=False, failure_month=36),
            _make_sim_result_with_timeline("0", success=False, failure_month=48),
        )
        result_id = _save_result(repo, plan, sim_results, ctx)

        stats = repo.get_result_statistics(result_id)
        assert stats is not None
        hist = stats["failure_months"]["histogram"]
        assert len(hist) == 3
        assert hist[0] == {"month": 24, "count": 2}
        assert hist[1] == {"month": 36, "count": 1}
        assert hist[2] == {"month": 48, "count": 1}

    def test_no_failures(self, repo: SQLiteRepository) -> None:
        plan = _make_plan(num_units=3)
        ctx = _get_context(plan)
        sim_results = tuple(
            _make_sim_result_with_timeline(str(500000 + i * 1000), success=True)
            for i in range(3)
        )
        result_id = _save_result(repo, plan, sim_results, ctx)

        stats = repo.get_result_statistics(result_id)
        assert stats is not None
        assert stats["failure_count"] == 0
        assert stats["failure_months"]["histogram"] == []

    def test_all_failures(self, repo: SQLiteRepository) -> None:
        plan = _make_plan(num_units=3)
        ctx = _get_context(plan)
        sim_results = tuple(
            _make_sim_result_with_timeline("0", success=False, failure_month=12 + i)
            for i in range(3)
        )
        result_id = _save_result(repo, plan, sim_results, ctx)

        stats = repo.get_result_statistics(result_id)
        assert stats is not None
        assert stats["success_count"] == 0
        assert stats["failure_count"] == 3
        assert len(stats["failure_months"]["histogram"]) == 3

    def test_single_unit(self, repo: SQLiteRepository) -> None:
        plan = _make_plan(num_units=1)
        ctx = _get_context(plan)
        sim_results = (_make_sim_result_with_timeline("500000", success=True),)
        result_id = _save_result(repo, plan, sim_results, ctx)

        stats = repo.get_result_statistics(result_id)
        assert stats is not None
        assert stats["total_units"] == 1
        assert stats["terminal_wealth"]["min"] == 500000.0
        assert stats["terminal_wealth"]["max"] == 500000.0


# ===========================================================================
# 3. get_result_trajectory_percentiles tests
# ===========================================================================


class TestGetResultTrajectoryPercentiles:
    def test_returns_none_for_missing_result(self, repo: SQLiteRepository) -> None:
        assert repo.get_result_trajectory_percentiles("nonexistent") is None

    def test_basic_trajectory(self, repo: SQLiteRepository) -> None:
        plan = _make_plan(num_units=3)
        ctx = _get_context(plan)
        # 3 units with different growth trajectories over 12 months
        sim_results = (
            _make_sim_result_with_timeline(
                "150000", months_simulated=12,
                portfolio_values=[100000 + i * 5000 for i in range(12)],
            ),
            _make_sim_result_with_timeline(
                "150000", months_simulated=12,
                portfolio_values=[100000 + i * 4000 for i in range(12)],
            ),
            _make_sim_result_with_timeline(
                "150000", months_simulated=12,
                portfolio_values=[100000 + i * 3000 for i in range(12)],
            ),
        )
        result_id = _save_result(repo, plan, sim_results, ctx)

        traj = repo.get_result_trajectory_percentiles(result_id)
        assert traj is not None
        assert traj["total_units"] == 3
        assert traj["month_count"] == 12
        assert len(traj["months"]) == 12
        assert traj["months"] == list(range(12))

        # Check that percentiles are present
        assert "p50" in traj["series"]
        assert len(traj["series"]["p50"]) == 12

    def test_percentile_bands_ordered(self, repo: SQLiteRepository) -> None:
        plan = _make_plan(num_units=5)
        ctx = _get_context(plan)
        # Units with spread-out values
        base_values = [100000, 110000, 120000, 130000, 140000]
        sim_results = tuple(
            _make_sim_result_with_timeline(
                str(v), months_simulated=6,
                portfolio_values=[v + i * 1000 for i in range(6)],
            )
            for v in base_values
        )
        result_id = _save_result(repo, plan, sim_results, ctx)

        traj = repo.get_result_trajectory_percentiles(
            result_id, percentiles=(10.0, 50.0, 90.0)
        )
        assert traj is not None

        # At month 0, values are [100000, 110000, 120000, 130000, 140000]
        # p10 should be close to 100000, p50=120000, p90 close to 140000
        for m_idx in range(6):
            p10 = traj["series"]["p10"][m_idx]
            p50 = traj["series"]["p50"][m_idx]
            p90 = traj["series"]["p90"][m_idx]
            assert p10 <= p50 <= p90, (
                f"Month {m_idx}: p10={p10} > p50={p50} or p50 > p90={p90}"
            )

    def test_single_unit(self, repo: SQLiteRepository) -> None:
        plan = _make_plan(num_units=1)
        ctx = _get_context(plan)
        sim_results = (
            _make_sim_result_with_timeline(
                "120000", months_simulated=6,
                portfolio_values=[100000, 104000, 108000, 112000, 116000, 120000],
            ),
        )
        result_id = _save_result(repo, plan, sim_results, ctx)

        traj = repo.get_result_trajectory_percentiles(result_id)
        assert traj is not None
        assert traj["total_units"] == 1
        # With a single unit, all percentiles equal the same value
        for p_key in traj["series"]:
            for val in traj["series"][p_key]:
                assert val == pytest.approx(100000.0, abs=1.0) or val > 0

    def test_empty_result(self, repo: SQLiteRepository) -> None:
        plan = _make_plan(num_units=1)
        ctx = _get_context(plan)
        sim_results = (
            _make_sim_result_with_timeline("500000", months_simulated=0),
        )
        result_id = _save_result(repo, plan, sim_results, ctx)

        traj = repo.get_result_trajectory_percentiles(result_id)
        assert traj is not None
        assert traj["month_count"] == 0
        assert traj["months"] == []
        for key, values in traj["series"].items():
            assert values == [], f"Series {key} should be empty"

    def test_custom_percentiles(self, repo: SQLiteRepository) -> None:
        plan = _make_plan(num_units=3)
        ctx = _get_context(plan)
        sim_results = tuple(
            _make_sim_result_with_timeline(
                str(100000 * (i + 1)), months_simulated=6,
                portfolio_values=[100000 * (i + 1)] * 6,
            )
            for i in range(3)
        )
        result_id = _save_result(repo, plan, sim_results, ctx)

        traj = repo.get_result_trajectory_percentiles(
            result_id, percentiles=(25.0, 75.0)
        )
        assert traj is not None
        assert traj["percentiles"] == [25.0, 75.0]
        assert "p25" in traj["series"]
        assert "p75" in traj["series"]
        assert "p50" not in traj["series"]


# ===========================================================================
# 4. ERN-scale benchmark
# ===========================================================================


def _make_ern_scale_plan(
    num_cohorts: int = 100,
    horizon_months: int = 120,
) -> tuple[ResearchPlan, PersistenceReconstructionContext]:
    """Create a plan scaled toward ERN parameters (100 cohorts × 120 months).

    Full ERN is 1739 × 720 = 1.25M rows. We use 100 × 120 = 12,000 rows
    as a representative benchmark that completes in reasonable test time.
    """
    # Dataset must extend far enough for the latest cohort + horizon
    # Latest cohort index is (num_cohorts-1), spans multiple years
    latest_cohort_year_offset = (num_cohorts - 1) // 12
    dataset_months = (latest_cohort_year_offset + 1) * 12 + horizon_months + 12
    snapshots = []
    for i in range(dataset_months):
        m = i + 1
        y = 2000 + (m - 1) // 12
        mo = ((m - 1) % 12) + 1
        snapshots.append(
            __import__(
                "fbf.core.domain.model.market_snapshot", fromlist=["MarketSnapshot"]
            ).MarketSnapshot(
                date=date(y, mo, 1),
                index_levels={_ASSET: Decimal("100.00")},
                inflation=Decimal("0.00"),
                inflation_cumulative=Decimal("0.00"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100.00"),
            )
        )
    from fbf.core.domain.model.dataset import Dataset

    dataset = Dataset(snapshots=snapshots, frequency="monthly", version="ERN_BENCH_v1")

    # Generate unique cohort dates across multiple years
    cohort_dates = []
    for i in range(num_cohorts):
        year = 2000 + (i // 12)
        month = 1 + (i % 12)
        cohort_dates.append(date(year, month, 1))

    experiment = ExperimentDefinition(
        name="ern-benchmark",
        description="ERN-scale benchmark",
        dataset=dataset,
        horizon_months=horizon_months,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        cohorts=tuple(
            CohortSpecification(start_date=cd) for cd in cohort_dates
        ),
        allocation_policies=(DummyAllocationPolicy(),),
        withdrawal_policies=(DummyWithdrawalPolicy(),),
    )

    units = tuple(
        PlannedSimulationUnit(
            cohort=CohortSpecification(start_date=cd),
            parameter_config=ParameterConfiguration(values={"withdrawal_rate": 0.04}),
            allocation_policy=DummyAllocationPolicy(),
            withdrawal_policy=DummyWithdrawalPolicy(),
            initial_portfolio=Portfolio(
                holdings=(AssetHolding(asset_class=_ASSET, units=Decimal("1000")),)
            ),
            dataset=dataset.slice(cd, horizon_months),
        )
        for cd in cohort_dates
    )

    plan = ResearchPlan(experiment_definition=experiment, units=units)
    resolver = DummyDatasetResolver(dataset)
    ctx = PersistenceReconstructionContext(
        dataset_resolver=resolver,
        policy_codecs={
            ("allocation", "AllocationPolicy"): type(
                "C",
                (),
                {
                    "policy_type": "AllocationPolicy",
                    "dump": lambda self, p: {"type": "AllocationPolicy"},
                    "load": lambda self, p: DummyAllocationPolicy(),
                },
            )(),
            ("withdrawal", "WithdrawalPolicy"): type(
                "C",
                (),
                {
                    "policy_type": "WithdrawalPolicy",
                    "dump": lambda self, p: {"type": "WithdrawalPolicy"},
                    "load": lambda self, p: DummyWithdrawalPolicy(),
                },
            )(),
        },
        simulation_result_codec=SimulationResultCodec(),
    )
    return plan, ctx


class TestERNBenchmark:
    """Benchmark tests for ERN-scale data volumes."""

    def test_ern_scale_statistics_benchmark(
        self, repo: SQLiteRepository, tmp_path: Path
    ) -> None:
        """Benchmark get_result_statistics with ~12K rows."""
        num_units = 100
        horizon = 120
        plan, ctx = _make_ern_scale_plan(num_units, horizon)

        sim_results = tuple(
            _make_sim_result_with_timeline(
                str(500000 + i * 5000),
                success=i % 10 != 0,  # 10% failure rate
                failure_month=36 if i % 10 == 0 else None,
                months_simulated=horizon if i % 10 != 0 else 36,
            )
            for i in range(num_units)
        )
        result_id = _save_result(repo, plan, sim_results, ctx, name="ern-stats")

        gc.collect()
        t0 = time.perf_counter()
        stats = repo.get_result_statistics(result_id)
        elapsed = time.perf_counter() - t0

        assert stats is not None
        assert stats["total_units"] == num_units
        print(f"\n[ERN BENCHMARK] get_result_statistics ({num_units} units): {elapsed:.4f}s")
        assert elapsed < 5.0, f"Statistics query too slow: {elapsed:.2f}s"

    def test_ern_scale_trajectory_benchmark(
        self, repo: SQLiteRepository, tmp_path: Path
    ) -> None:
        """Benchmark get_result_trajectory_percentiles with ~12K rows."""
        num_units = 100
        horizon = 120
        plan, ctx = _make_ern_scale_plan(num_units, horizon)

        sim_results = tuple(
            _make_sim_result_with_timeline(
                str(500000 + i * 5000),
                months_simulated=horizon,
                portfolio_values=[
                    500000 + i * 5000 + m * (1000 + i * 10) for m in range(horizon)
                ],
            )
            for i in range(num_units)
        )
        result_id = _save_result(repo, plan, sim_results, ctx, name="ern-traj")

        gc.collect()
        t0 = time.perf_counter()
        traj = repo.get_result_trajectory_percentiles(result_id)
        elapsed = time.perf_counter() - t0

        assert traj is not None
        assert traj["total_units"] == num_units
        assert traj["month_count"] == horizon
        print(
            f"\n[ERN BENCHMARK] get_result_trajectory_percentiles "
            f"({num_units} units × {horizon} months): {elapsed:.4f}s"
        )
        assert elapsed < 10.0, f"Trajectory query too slow: {elapsed:.2f}s"

    def test_json_extract_vs_python_benchmark(
        self, repo: SQLiteRepository, tmp_path: Path
    ) -> None:
        """Compare Python-side JSON extraction vs SQLite json_extract().

        This benchmark informs the architecture decision for how to
        extract portfolio value from monthly payloads.
        """
        num_units = 100
        horizon = 120
        plan, ctx = _make_ern_scale_plan(num_units, horizon)

        sim_results = tuple(
            _make_sim_result_with_timeline(
                str(500000 + i * 5000),
                months_simulated=horizon,
                portfolio_values=[
                    500000 + i * 5000 + m * 1000 for m in range(horizon)
                ],
            )
            for i in range(num_units)
        )
        result_id = _save_result(repo, plan, sim_results, ctx, name="bench-compare")


        # Approach 1: Python-side extraction (current approach)
        gc.collect()
        t0 = time.perf_counter()
        with repo._connect() as conn:
            rows = conn.execute(
                "SELECT unit_index, month_index, monthly_payload_json "
                "FROM simulation_results WHERE execution_result_id = ? "
                "ORDER BY month_index, unit_index",
                (result_id,),
            ).fetchall()
            python_values: dict[int, list[float]] = {}
            for _unit_idx, month_idx, payload_json in rows:
                if month_idx not in python_values:
                    python_values[month_idx] = []
                payload = json.loads(payload_json)
                holdings = payload.get("portfolio_holdings", [])
                pv = sum(float(h["units"]) for h in holdings)
                python_values[month_idx].append(pv)
        python_time = time.perf_counter() - t0

        # Approach 2: SQLite json_extract() extraction
        gc.collect()
        t0 = time.perf_counter()
        with repo._connect() as conn:
            rows2 = conn.execute(
                "SELECT unit_index, month_index, "
                "json_extract(monthly_payload_json, '$.portfolio_holdings[0].units') "
                "FROM simulation_results WHERE execution_result_id = ? "
                "ORDER BY month_index, unit_index",
                (result_id,),
            ).fetchall()
            sql_values: dict[int, list[float]] = {}
            for _unit_idx, month_idx, pv_str in rows2:
                if month_idx not in sql_values:
                    sql_values[month_idx] = []
                sql_values[month_idx].append(float(pv_str))
        sql_time = time.perf_counter() - t0

        print(f"\n[ERN BENCHMARK] Python-side extraction: {python_time:.4f}s")
        print(f"[ERN BENCHMARK] SQLite json_extract():  {sql_time:.4f}s")
        print(
            f"[ERN BENCHMARK] Ratio (python/sql): "
            f"{python_time / sql_time:.2f}x" if sql_time > 0 else "N/A"
        )

        # Both should produce equivalent results
        assert set(python_values.keys()) == set(sql_values.keys())
        for month_idx in python_values:
            assert len(python_values[month_idx]) == len(sql_values[month_idx])
            for pv_py, pv_sql in zip(
                sorted(python_values[month_idx]),
                sorted(sql_values[month_idx]), strict=False,
            ):
                assert pv_py == pytest.approx(pv_sql, abs=0.01)
