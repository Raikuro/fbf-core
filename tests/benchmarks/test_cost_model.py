"""Cost model benchmarks for Phase 3 architectural investigation.

Measures the three optimization categories:
  A. Mathematical work reduction (horizon chaining, fast path)
  B. Execution-overhead reduction (process creation, IPC, serialization)
  C. IO/data-access reduction (dataset loading, resolution, slicing)

Uses the real pipeline to measure actual costs, not synthetic executors.
"""

from __future__ import annotations

import pickle
import time
from datetime import date
from decimal import Decimal

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.fast_path import (
    ChainedFastPathSimulationExecutor,
    evaluate_closed_form,
)
from fbf.core.execution.strategies.parallel_executor import (
    parallel_execute,
    sequential_execute,
)
from fbf.core.study.builder import build_initial_portfolio
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan

EQ = AssetClass(id="equity", name="", description="")
BD = AssetClass(id="bond", name="", description="")


def _make_dataset(n_months: int) -> Dataset:
    """Create a synthetic dataset with equity and bond asset classes."""
    import random

    rng = random.Random(42)
    pe = pb = Decimal("100")
    snapshots = []
    d = date(1900, 1, 1)
    for _ in range(n_months):
        snapshots.append(
            MarketSnapshot(
                date=d,
                index_levels={EQ: pe, BD: pb},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            )
        )
        pe *= Decimal(str(1 + rng.gauss(0.006, 0.045)))
        pb *= Decimal(str(1 + rng.gauss(0.002, 0.01)))
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return Dataset(snapshots=snapshots, frequency="monthly", version="1.0")


def _make_context(
    dataset: Dataset,
    start: date,
    horizon: int,
    weight: float = 0.5,
    rate: float = 0.04,
) -> SimulationContext:
    portfolio = build_initial_portfolio(Money(Decimal("1000000"), Currency.EUR))
    return SimulationContext(
        experiment_name="bench",
        cohort=str(start),
        start_date=start,
        horizon_months=horizon,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        initial_portfolio=portfolio,
        dataset=dataset.slice(start, horizon),
        allocation_policy=ConstantAllocationPolicy(Decimal(str(weight))),
        withdrawal_policy=FixedRealWithdrawalPolicy(Decimal(str(rate))),
    )


def _make_engine_def(contexts: list[SimulationContext]) -> EngineExperimentDefinition:
    return EngineExperimentDefinition(
        name="bench",
        description="benchmark",
        simulation_contexts=tuple(contexts),
    )


# ===================================================================
# Category A: Mathematical Work Reduction
# ===================================================================


class TestMathematicalWorkCost:
    """Measure time spent in actual simulation computation."""

    def test_reference_pipeline_per_unit_cost(self) -> None:
        """Time the full 9-step pipeline for a single unit."""
        dataset = _make_dataset(721)
        context = _make_context(dataset, date(1900, 1, 1), 720)
        from fbf.core.execution.strategies.parallel_executor import (
            _create_default_simulation_executor,
        )

        executor = _create_default_simulation_executor()

        # Warm up
        executor.execute(_make_engine_def([context]))

        # Measure
        t0 = time.perf_counter()
        for _ in range(10):
            executor.execute(_make_engine_def([context]))
        elapsed = (time.perf_counter() - t0) / 10

        print(f"\n[COST-A] Reference pipeline per unit (720 months): {elapsed*1000:.1f}ms")
        print(f"[COST-A]   per month: {elapsed/720*1000:.3f}ms")

    def test_fast_path_decimal_per_unit_cost(self) -> None:
        """Time the closed-form fast path (decimal) for a single unit."""
        dataset = _make_dataset(721)
        context = _make_context(dataset, date(1900, 1, 1), 720)

        # Warm up
        evaluate_closed_form(context, "decimal")

        # Measure
        t0 = time.perf_counter()
        for _ in range(100):
            evaluate_closed_form(context, "decimal")
        elapsed = (time.perf_counter() - t0) / 100

        print(f"\n[COST-A] Fast path (decimal) per unit (720 months): {elapsed*1000:.1f}ms")
        print(f"[COST-A]   per month: {elapsed/720*1000:.3f}ms")

    def test_fast_path_float_per_unit_cost(self) -> None:
        """Time the closed-form fast path (float) for a single unit."""
        dataset = _make_dataset(721)
        context = _make_context(dataset, date(1900, 1, 1), 720)

        # Warm up
        evaluate_closed_form(context, "float")

        # Measure
        t0 = time.perf_counter()
        for _ in range(1000):
            evaluate_closed_form(context, "float")
        elapsed = (time.perf_counter() - t0) / 1000

        print(f"\n[COST-A] Fast path (float) per unit (720 months): {elapsed*1000:.1f}ms")
        print(f"[COST-A]   per month: {elapsed/720*1000:.3f}ms")

    def test_horizon_chaining_work_reduction(self) -> None:
        """Measure work reduction from horizon chaining (4 horizons per cohort)."""
        dataset = _make_dataset(721)
        start = date(1900, 1, 1)
        horizons = [361, 481, 601, 721]  # 30, 40, 50, 60 years

        # Without chaining: evaluate each horizon independently
        t0 = time.perf_counter()
        for h in horizons:
            ctx = _make_context(dataset, start, h)
            evaluate_closed_form(ctx, "decimal")
        no_chain_time = time.perf_counter() - t0

        # With chaining: evaluate longest, derive shorter
        contexts = [_make_context(dataset, start, h) for h in horizons]
        engine_def = _make_engine_def(contexts)
        executor = ChainedFastPathSimulationExecutor()

        # Warm up
        executor.execute(engine_def)

        t0 = time.perf_counter()
        for _ in range(10):
            executor.execute(engine_def)
        chain_time = (time.perf_counter() - t0) / 10

        print("\n[COST-A] Horizon chaining (4 horizons per cohort):")
        print(f"[COST-A]   without chaining: {no_chain_time*1000:.1f}ms")
        print(f"[COST-A]   with chaining:    {chain_time*1000:.1f}ms")
        print(f"[COST-A]   reduction:        {(1 - chain_time/no_chain_time)*100:.0f}%")

    def test_grid_work_distribution(self) -> None:
        """Measure work for a grid: 5 weights x 9 rates x 4 horizons = 180 cells."""
        dataset = _make_dataset(721)
        start = date(1900, 1, 1)
        weights = [1.0, 0.75, 0.5, 0.25, 0.0]
        rates = [0.03, 0.0325, 0.035, 0.0375, 0.04, 0.0425, 0.045, 0.0475, 0.05]
        horizons = [361, 481, 601, 721]

        # Create all contexts (1 per cell per cohort, 1 cohort)
        contexts = [
            _make_context(dataset, start, h, w, r)
            for w in weights
            for r in rates
            for h in horizons
        ]
        engine_def = _make_engine_def(contexts)

        # Measure chained fast path
        executor = ChainedFastPathSimulationExecutor()
        executor.execute(engine_def)  # warm up

        t0 = time.perf_counter()
        executor.execute(engine_def)
        elapsed = time.perf_counter() - t0

        print("\n[COST-A] Grid (5x9x4=180 cells, 1 cohort):")
        print(f"[COST-A]   total: {elapsed*1000:.1f}ms")
        print(f"[COST-A]   per cell: {elapsed/180*1000:.3f}ms")


# ===================================================================
# Category B: Execution Overhead Reduction
# ===================================================================


class TestExecutionOverheadCost:
    """Measure process creation, IPC, serialization, context creation costs."""

    def test_context_creation_overhead(self) -> None:
        """Time the creation of SimulationContext objects."""
        dataset = _make_dataset(721)
        start = date(1900, 1, 1)
        portfolio = build_initial_portfolio(Money(Decimal("1000000"), Currency.EUR))

        t0 = time.perf_counter()
        for _ in range(1000):
            SimulationContext(
                experiment_name="bench",
                cohort=str(start),
                start_date=start,
                horizon_months=720,
                initial_wealth=Money(Decimal("1000000"), Currency.EUR),
                initial_portfolio=portfolio,
                dataset=dataset.slice(start, 720),
                allocation_policy=ConstantAllocationPolicy(Decimal("0.5")),
                withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.04")),
            )
        elapsed = time.perf_counter() - t0

        print(f"\n[COST-B] Context creation: {elapsed/1000*1000:.3f}ms per context")

    def test_context_serialization_cost(self) -> None:
        """Time pickling of SimulationContext for IPC."""
        dataset = _make_dataset(721)
        context = _make_context(dataset, date(1900, 1, 1), 720)

        # Measure pickle
        t0 = time.perf_counter()
        for _ in range(100):
            pickle.dumps(context)
        elapsed = time.perf_counter() - t0
        size = len(pickle.dumps(context))

        print("\n[COST-B] Context serialization:")
        print(f"[COST-B]   size: {size/1024:.1f}KB")
        print(f"[COST-B]   time: {elapsed/100*1000:.3f}ms per pickle")

    def test_experiment_definition_serialization_cost(self) -> None:
        """Time pickling of full ExperimentDefinition (sent to each worker)."""
        dataset = _make_dataset(840)
        contexts = [
            _make_context(dataset, date(1900, 1, 1), 720)
            for i in range(10)
        ]
        engine_def = _make_engine_def(contexts)

        t0 = time.perf_counter()
        for _ in range(10):
            pickle.dumps(engine_def)
        elapsed = time.perf_counter() - t0
        size = len(pickle.dumps(engine_def))

        print("\n[COST-B] ExperimentDefinition serialization (10 units):")
        print(f"[COST-B]   size: {size/1024:.1f}KB")
        print(f"[COST-B]   time: {elapsed/10*1000:.3f}ms per pickle")

    def test_result_serialization_cost(self) -> None:
        """Time pickling of results (IPC return path)."""
        dataset = _make_dataset(721)
        context = _make_context(dataset, date(1900, 1, 1), 720)
        from fbf.core.execution.strategies.parallel_executor import (
            _create_default_simulation_executor,
        )

        executor = _create_default_simulation_executor()
        result = executor.execute(_make_engine_def([context]))

        # Full result
        t0 = time.perf_counter()
        for _ in range(100):
            pickle.dumps(result)
        elapsed_full = time.perf_counter() - t0
        size_full = len(pickle.dumps(result))

        print("\n[COST-B] Result serialization:")
        print(f"[COST-B]   full: {size_full/1024:.1f}KB, {elapsed_full/100*1000:.3f}ms")

    def test_parallel_dispatch_overhead(self) -> None:
        """Time the overhead of parallel vs sequential dispatch."""
        dataset = _make_dataset(840)
        cohorts = tuple(
            CohortSpecification(start_date=date(1900, 1 + i, 1))
            for i in range(8)
        )
        experiment = ExperimentDefinition(
            name="bench",
            description="benchmark",
            dataset=dataset,
            horizon_months=720,
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            cohorts=cohorts,
            allocation_policies=(ConstantAllocationPolicy(Decimal("0.5")),),
            withdrawal_policies=(FixedRealWithdrawalPolicy(Decimal("0.04")),),
        )
        units = tuple(
            PlannedSimulationUnit(
                cohort=c,
                parameter_config=ParameterConfiguration(values={"rate": 0.04}),
                allocation_policy=ConstantAllocationPolicy(Decimal("0.5")),
                withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.04")),
                initial_portfolio=build_initial_portfolio(Money(Decimal("1000000"), Currency.EUR)),
                dataset=dataset.slice(c.start_date, 720),
            )
            for c in cohorts
        )
        plan = ResearchPlan(experiment_definition=experiment, units=units)

        executor = ChainedFastPathSimulationExecutor()

        # Sequential
        t0 = time.perf_counter()
        sequential_execute(plan, simulation_executor=executor)
        seq_time = time.perf_counter() - t0

        # Parallel (2 workers)
        t0 = time.perf_counter()
        parallel_execute(plan, max_workers=2, simulation_executor=executor)
        par_time = time.perf_counter() - t0

        print("\n[COST-B] Parallel dispatch (8 units, 720 months):")
        print(f"[COST-B]   sequential: {seq_time*1000:.0f}ms")
        print(f"[COST-B]   parallel:   {par_time*1000:.0f}ms")
        print(f"[COST-B]   overhead:   {(par_time/seq_time - 1)*100:.0f}%")


# ===================================================================
# Category C: IO/Data-Access Reduction
# ===================================================================


class TestIODataAccessCost:
    """Measure dataset loading, resolution, slicing costs."""

    def test_dataset_slicing_cost(self) -> None:
        """Time creating sliced datasets for cohorts."""
        dataset = _make_dataset(840)

        t0 = time.perf_counter()
        for _i in range(100):
            dataset.slice(date(1900, 1, 1), 720)
        elapsed = time.perf_counter() - t0

        print("\n[COST-C] Dataset slicing (720 months):")
        print(f"[COST-C]   time: {elapsed/100*1000:.3f}ms per slice")

    def test_dataset_memory_sharing(self) -> None:
        """Verify that sliced datasets share MarketSnapshot objects."""
        dataset = _make_dataset(840)
        sliced = dataset.slice(date(1900, 1, 1), 360)

        # Check identity sharing
        shared = all(
            dataset.snapshots[i] is sliced.snapshots[i]
            for i in range(len(sliced.snapshots))
        )
        print(f"\n[COST-C] Memory sharing in sliced datasets: {shared}")
        print(f"[COST-C]   parent snapshots: {len(dataset.snapshots)}")
        print(f"[COST-C]   sliced snapshots: {len(sliced.snapshots)}")


# ===================================================================
# Combined Cost Model
# ===================================================================


class TestCombinedCostModel:
    """End-to-end cost breakdown for a realistic workload."""

    def test_ern_smoke_grid_cost_breakdown(self) -> None:
        """Break down costs for the ERN smoke grid (2x2x2=8 cells, 1 cohort)."""
        dataset = _make_dataset(721)
        start = date(1900, 1, 1)
        weights = [0.5, 0.0]
        rates = [0.04, 0.05]
        horizons = [361, 721]

        # Create all contexts
        contexts = [
            _make_context(dataset, start, h, w, r)
            for w in weights
            for r in rates
            for h in horizons
        ]
        engine_def = _make_engine_def(contexts)

        # Measure chained fast path
        executor = ChainedFastPathSimulationExecutor()
        executor.execute(engine_def)  # warm up
        t0 = time.perf_counter()
        executor.execute(engine_def)
        fast_time = time.perf_counter() - t0

        # Measure reference pipeline (no chaining)
        from fbf.core.execution.strategies.parallel_executor import (
            _create_default_simulation_executor,
        )

        ref_executor = _create_default_simulation_executor()
        ref_executor.execute(engine_def)  # warm up
        t0 = time.perf_counter()
        ref_executor.execute(engine_def)
        ref_time = time.perf_counter() - t0

        print("\n[COST] ERN smoke grid (8 cells, 1 cohort):")
        print(f"[COST]   reference (no chaining): {ref_time*1000:.1f}ms")
        print(f"[COST]   chained fast path:       {fast_time*1000:.1f}ms")
        print(f"[COST]   speedup:                 {ref_time/fast_time:.1f}x")
