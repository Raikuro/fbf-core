"""Unit and integration tests for parallel execution engine (v0.4 Phase 1).

Verifies the behavioral specification PARALLEL_EXECUTION_SPECIFICATION.md:
- Determinism: parallel execution ≡ sequential execution
- Work distribution: deterministic work batching
- Ordering preservation: exact 1-to-1 plan unit to result mapping
- Progress tracking: callback invocation
- Error isolation: safe worker execution
"""

from __future__ import annotations

import random
from datetime import date
from decimal import Decimal
from unittest.mock import Mock

import pytest

from fbf.core.domain.model.allocation import AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from fbf.core.domain.policies.allocation_policy import AllocationPolicy
from fbf.core.domain.policies.decisions import AllocationDecision, WithdrawalDecision
from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    ExperimentRun,
    SimulationResult,
    SimulationStatistics,
    SimulationTimeline,
)
from fbf.core.execution.strategies.parallel_executor import (
    ExecutionConfig,
    ParallelExecutor,
    _worker_execute_batch_safe,
    create_work_batches,
    default_max_workers,
    parallel_execute,
    sequential_execute,
)
from fbf.core.study.builder import build_initial_portfolio
from fbf.core.study.internal.cohort.generator import CohortGenerator
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.axis import ParameterAxis
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.internal.parameter.engine import ParameterSweepEngine
from fbf.core.study.plan import (
    PlannedSimulationUnit,
    ResearchPlan,
    materialize_research_plan,
)

# ---------------------------------------------------------------------------
# Test doubles & helpers
# ---------------------------------------------------------------------------


class DummyAllocationPolicy(AllocationPolicy):
    def decide(self, context: object) -> AllocationDecision:
        portfolio = getattr(context, "portfolio", None)
        asset = (
            portfolio.holdings[0].asset_class if portfolio and portfolio.holdings else make_asset()
        )
        return AllocationDecision(
            reason="dummy",
            allocation_target=AllocationTarget(weights={asset: Decimal("1.0")}),
        )


class DummyWithdrawalPolicy(WithdrawalPolicy):
    def decide(self, context: object) -> WithdrawalDecision:
        return WithdrawalDecision(
            reason="dummy",
            nominal_amount=Money(Decimal("100"), Currency.EUR),
            real_amount=Money(Decimal("100"), Currency.EUR),
        )


def make_asset() -> AssetClass:
    return AssetClass(id="acwi", name="ACWI", description="Global equities")


def make_dataset(start_date: date = date(2000, 1, 1)) -> Dataset:
    asset = make_asset()
    snapshot = MarketSnapshot(
        date=start_date,
        index_levels={asset: Decimal("100.00")},
        inflation=Decimal("0.00"),
        inflation_cumulative=Decimal("0.00"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100.00"),
    )
    return Dataset(snapshots=[snapshot], frequency="monthly", version="1.0")


def make_minimal_dataset(year: int = 2000, month: int = 1) -> Dataset:
    """Minimal single-snapshot Dataset aligned to a cohort start date."""
    return make_dataset(start_date=date(year, month, 1))


def make_experiment_def() -> ExperimentDefinition:
    return ExperimentDefinition(
        name="parallel-test-experiment",
        description="Experiment for parallel execution tests",
        dataset=make_dataset(),
        horizon_months=12,
        initial_wealth=Money(Decimal("100000"), Currency.EUR),
        cohorts=(CohortSpecification(start_date=date(2000, 1, 1)),),
        allocation_policies=(DummyAllocationPolicy(),),
        withdrawal_policies=(DummyWithdrawalPolicy(),),
    )


def make_unit(month: int = 1, withdrawal_rate: float = 0.04) -> PlannedSimulationUnit:
    asset = make_asset()
    portfolio = Portfolio(holdings=(AssetHolding(asset_class=asset, units=Decimal("1000")),))
    return PlannedSimulationUnit(
        cohort=CohortSpecification(start_date=date(2000, month, 1)),
        parameter_config=ParameterConfiguration(values={"withdrawal_rate": withdrawal_rate}),
        allocation_policy=DummyAllocationPolicy(),
        withdrawal_policy=DummyWithdrawalPolicy(),
        initial_portfolio=portfolio,
        dataset=make_minimal_dataset(year=2000, month=month),
    )


def make_simulation_result(unit_idx: int) -> SimulationResult:
    return SimulationResult(
        timeline=SimulationTimeline(monthly_results=()),
        statistics=SimulationStatistics(
            final_wealth=Money(Decimal(100000 + unit_idx * 1000), Currency.EUR),
            max_drawdown=0.0,
            success=True,
            failure_month=None,
            failure_state=None,
            months_simulated=12,
            execution_time_seconds=0.01,
        ),
    )


def make_test_plan(num_units: int = 12) -> ResearchPlan:
    exp_def = make_experiment_def()
    units = tuple(
        make_unit(month=((i % 12) + 1), withdrawal_rate=0.03 + (i * 0.001))
        for i in range(num_units)
    )
    return ResearchPlan(experiment_definition=exp_def, units=units)


def make_mock_simulation_executor(num_units: int) -> Mock:
    """Return a mock SimulationExecutor whose results are deterministic per-context.

    Result index is derived from the SimulationContext's start_date month so that
    the same unit always yields the same SimulationResult regardless of which batch
    it lands in (needed for parallel-vs-sequential determinism assertions).
    """
    mock_exec = Mock()

    def mock_execute(engine_def: EngineExperimentDefinition) -> ExperimentRun:
        sim_results = tuple(
            make_simulation_result(ctx.start_date.month + ctx.start_date.year * 12)
            for ctx in engine_def.simulation_contexts
        )
        return ExperimentRun(definition=engine_def, simulation_results=sim_results)

    mock_exec.execute.side_effect = mock_execute
    return mock_exec


# ---------------------------------------------------------------------------
# Tests for Work Batching
# ---------------------------------------------------------------------------


def test_create_work_batches_distribution() -> None:
    """Verify units are split deterministically across workers."""
    plan = make_test_plan(num_units=10)

    # 4 workers: ceil(10/4) = 3 per batch -> 3, 3, 3, 1
    batches = create_work_batches(plan, max_workers=4)
    assert len(batches) == 4
    assert len(batches[0]) == 3
    assert len(batches[1]) == 3
    assert len(batches[2]) == 3
    assert len(batches[3]) == 1

    # Verify unit order preservation
    all_batched_units = [unit for batch in batches for unit in batch]
    assert tuple(all_batched_units) == plan.units


def test_create_work_batches_invalid_workers() -> None:
    """Verify ValueError when max_workers <= 0."""
    plan = make_test_plan(num_units=5)
    with pytest.raises(ValueError, match="max_workers must be positive"):
        create_work_batches(plan, max_workers=0)


def test_create_work_batches_empty_plan() -> None:
    """Verify empty plan produces empty batches."""
    batches = create_work_batches(Mock(units=()), max_workers=4)
    assert batches == []


# ---------------------------------------------------------------------------
# Default worker selection (conservative cap)
# ---------------------------------------------------------------------------


def test_default_max_workers_caps_at_8_on_large_hosts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No explicit override + more than 8 logical CPUs resolves to 8 workers."""
    monkeypatch.setattr("os.cpu_count", lambda: 32)
    assert default_max_workers() == 8


def test_default_max_workers_uses_host_cpus_below_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No explicit override + fewer than 8 logical CPUs resolves to host count."""
    monkeypatch.setattr("os.cpu_count", lambda: 4)
    assert default_max_workers() == 4


def test_default_max_workers_fallback_when_cpu_count_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No explicit override + no CPU count resolves to a safe floor of 1."""
    monkeypatch.setattr("os.cpu_count", lambda: None)
    assert default_max_workers() == 1


def test_default_max_workers_preserves_explicit_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit positive worker counts bypass the conservative default entirely."""
    monkeypatch.setattr("os.cpu_count", lambda: 32)
    config = ExecutionConfig(max_workers=16, use_processes=False)
    plan = make_test_plan(num_units=8)
    result = parallel_execute(
        plan,
        config=config,
        simulation_executor=make_mock_simulation_executor(8),
    )
    assert len(result.results) == 8


# ---------------------------------------------------------------------------
# Tests for Parallel Execution Determinism & Equivalence
# ---------------------------------------------------------------------------


def test_parallel_determinism_sequential_equivalence() -> None:
    """Verify parallel execution output is identical to sequential execution."""
    plan = make_test_plan(num_units=12)
    mock_sim_exec = make_mock_simulation_executor(12)

    seq_res = sequential_execute(plan, simulation_executor=mock_sim_exec)

    config = ExecutionConfig(max_workers=3, use_processes=False)
    par_res = parallel_execute(plan, config=config, simulation_executor=mock_sim_exec)

    assert len(seq_res.results) == len(par_res.results) == 12
    assert seq_res.plan == par_res.plan
    assert seq_res.results == par_res.results


def test_parallel_determinism_across_runs() -> None:
    """Verify parallel execution produces identical results across multiple runs.

    Uses two independent mock executors with the same deterministic logic to confirm
    that worker-count differences don't affect output ordering or values.
    """
    plan = make_test_plan(num_units=8)

    config1 = ExecutionConfig(max_workers=2, use_processes=False)
    config2 = ExecutionConfig(max_workers=4, use_processes=False)

    run1 = parallel_execute(
        plan, config=config1, simulation_executor=make_mock_simulation_executor(8)
    )
    run2 = parallel_execute(
        plan, config=config2, simulation_executor=make_mock_simulation_executor(8)
    )

    assert run1.results == run2.results


def _make_real_engine_plan() -> ResearchPlan:
    """Build a small multi-cohort, multi-config plan for the real Decimal fbf.core."""
    rng = random.Random(11)
    equity = AssetClass(id="equity", name="", description="")
    bond = AssetClass(id="bond", name="", description="")
    pe = pb = Decimal("100")
    snapshots = []
    d = date(2000, 1, 1)
    for _ in range(60):
        snapshots.append(
            MarketSnapshot(
                date=d,
                index_levels={equity: pe, bond: pb},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            )
        )
        pe *= Decimal(str(1 + rng.gauss(0.006, 0.04)))
        pb *= Decimal(str(1 + rng.gauss(0.002, 0.01)))
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    dataset = Dataset(snapshots=snapshots, frequency="monthly", version="1.0")

    cohorts = CohortGenerator.generate_rolling_monthly(dataset, 36)
    alloc = ConstantAllocationPolicy(Decimal("0.6"))
    withdraw = FixedRealWithdrawalPolicy(Decimal("0.04"))
    configs = ParameterSweepEngine.cartesian_product(
        [
            ParameterAxis(name="equity_allocation", values=(0.6, 0.4)),
            ParameterAxis(name="withdrawal_rate", values=(0.03, 0.04)),
        ]
    )
    exp_def = ExperimentDefinition(
        name="real-determinism",
        description="real-engine parallel determinism",
        dataset=dataset,
        horizon_months=36,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        cohorts=cohorts,
        allocation_policies=(alloc,),
        withdrawal_policies=(withdraw,),
    )
    return materialize_research_plan(
        experiment_def=exp_def,
        canonical_trajectory=dataset,
        cohorts=cohorts,
        param_configs=configs,
        initial_portfolio=build_initial_portfolio(exp_def.initial_wealth),
        horizon_resolver=lambda c: 36,
        policy_resolver=lambda c: (alloc, withdraw),
    )


def test_real_engine_parallel_matches_sequential() -> None:
    """Parallel execution through the real Decimal engine is bit-for-bit equal
    to sequential execution (result and per-month timeline)."""
    plan = _make_real_engine_plan()

    seq_result = sequential_execute(plan)
    par_result = parallel_execute(plan, max_workers=2)

    assert len(par_result.results) == len(seq_result.results)
    for seq, par in zip(seq_result.results, par_result.results, strict=True):
        assert seq == par


def test_parallel_executor_class_wrapper() -> None:
    """Verify ParallelExecutor wrapper delegates correctly."""
    plan = make_test_plan(num_units=6)
    mock_sim_exec = make_mock_simulation_executor(6)

    config = ExecutionConfig(max_workers=2, use_processes=False)
    executor = ParallelExecutor(config=config, simulation_executor=mock_sim_exec)

    res = executor.execute_plan(plan)
    assert len(res.results) == 6


# ---------------------------------------------------------------------------
# Tests for Progress Reporting & Error Handling
# ---------------------------------------------------------------------------


def test_progress_callback() -> None:
    """Verify progress callback receives intermediate progress updates."""
    plan = make_test_plan(num_units=8)
    mock_sim_exec = make_mock_simulation_executor(8)

    progress_reports: list[tuple[int, int]] = []

    def callback(completed: int, total: int) -> None:
        progress_reports.append((completed, total))

    config = ExecutionConfig(max_workers=2, use_processes=False)
    parallel_execute(
        plan,
        config=config,
        simulation_executor=mock_sim_exec,
        progress_callback=callback,
    )

    assert len(progress_reports) > 0
    assert progress_reports[-1] == (8, 8)


def test_sequential_execute_progress_callback_per_unit() -> None:
    """Verify sequential execution fires progress once per completed unit."""
    plan = make_test_plan(num_units=8)
    mock_sim_exec = make_mock_simulation_executor(8)

    progress_reports: list[tuple[int, int]] = []

    def callback(completed: int, total: int) -> None:
        progress_reports.append((completed, total))

    res = sequential_execute(
        plan,
        simulation_executor=mock_sim_exec,
        progress_callback=callback,
    )

    assert progress_reports == [(i, 8) for i in range(1, 9)]
    assert len(res.results) == 8


def test_sequential_execute_summary_only_strips_timelines() -> None:
    """Verify summary_only drops timelines but preserves aggregate statistics."""
    plan = make_test_plan(num_units=6)
    mock_sim_exec = make_mock_simulation_executor(6)

    full = sequential_execute(plan, simulation_executor=mock_sim_exec)
    summary = sequential_execute(plan, simulation_executor=mock_sim_exec, summary_only=True)

    assert len(summary.results) == len(full.results) == 6
    for summary_result, full_result in zip(summary.results, full.results, strict=True):
        assert summary_result.timeline.monthly_results == ()
        assert summary_result.statistics == full_result.statistics


def test_parallel_execute_summary_only_strips_timelines() -> None:
    """Verify summary_only strips timelines in the parallel path too."""
    plan = make_test_plan(num_units=6)
    mock_sim_exec = make_mock_simulation_executor(6)

    config = ExecutionConfig(max_workers=3, use_processes=False)
    full = parallel_execute(plan, config=config, simulation_executor=mock_sim_exec)
    summary = parallel_execute(
        plan,
        config=config,
        simulation_executor=mock_sim_exec,
        summary_only=True,
    )

    assert len(summary.results) == len(full.results) == 6
    for summary_result, full_result in zip(summary.results, full.results, strict=True):
        assert summary_result.timeline.monthly_results == ()
        assert summary_result.statistics == full_result.statistics


def test_parallel_execute_summary_only_single_worker() -> None:
    """Verify summary_only works when the plan delegates to sequential_execute."""
    plan = make_test_plan(num_units=4)
    mock_sim_exec = make_mock_simulation_executor(4)

    config = ExecutionConfig(max_workers=1, use_processes=False)
    summary = parallel_execute(
        plan,
        config=config,
        simulation_executor=mock_sim_exec,
        summary_only=True,
    )

    assert len(summary.results) == 4
    assert all(r.timeline.monthly_results == () for r in summary.results)


class ExplodingAllocationPolicy(AllocationPolicy):
    """Allocation policy that raises RuntimeError at execution time."""

    def decide(self, context: object) -> AllocationDecision:
        raise RuntimeError("Deliberate execution-time failure for error isolation test")


def _make_selective_mock_executor() -> Mock:
    """Mock SimulationExecutor that succeeds for normal units and raises for
    ExplodingAllocationPolicy."""
    mock_exec = Mock()

    def selective_execute(engine_def: EngineExperimentDefinition) -> ExperimentRun:
        # Raise if any context uses ExplodingAllocationPolicy
        for ctx in engine_def.simulation_contexts:
            if isinstance(ctx.allocation_policy, ExplodingAllocationPolicy):
                raise RuntimeError("Deliberate execution-time failure for error isolation test")
        sim_results = tuple(
            make_simulation_result(ctx.start_date.month) for ctx in engine_def.simulation_contexts
        )
        return ExperimentRun(definition=engine_def, simulation_results=sim_results)

    mock_exec.execute.side_effect = selective_execute
    return mock_exec


def test_worker_execute_batch_safe_error_isolation() -> None:
    """Verify _worker_execute_batch_safe captures exceptions without halting.

    A well-formed unit whose allocation policy raises at *execution* time is used
    to trigger an in-worker exception, confirming the safe wrapper captures it
    without aborting the remaining units in the batch.
    """
    exp_def = make_experiment_def()
    unit1 = make_unit(month=1)

    # Unit 2 is fully constructed but its policy triggers a RuntimeError during execution
    unit_bad = PlannedSimulationUnit(
        cohort=CohortSpecification(start_date=date(2000, 3, 1)),
        parameter_config=ParameterConfiguration(values={"withdrawal_rate": 0.04}),
        allocation_policy=ExplodingAllocationPolicy(),
        withdrawal_policy=DummyWithdrawalPolicy(),
        initial_portfolio=make_unit().initial_portfolio,
        dataset=make_minimal_dataset(year=2000, month=3),
    )

    selective_mock = _make_selective_mock_executor()
    batch_res = _worker_execute_batch_safe(
        exp_def, [unit1, unit_bad], simulation_executor=selective_mock
    )
    assert len(batch_res) == 2

    # Unit 1 succeeded
    assert batch_res[0][0] is not None
    assert batch_res[0][1] is None

    # Unit 2 failed safely with the execution-time error captured
    assert batch_res[1][0] is None
    assert isinstance(batch_res[1][1], Exception)
