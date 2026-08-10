"""Performance benchmarks for the closed-form fast path and horizon chaining.

Measures, on a synthetic random-walk dataset:
  1. reference pipeline vs float closed form (per-cohort throughput),
  2. non-chained vs chained multi-horizon execution (wall time + outcome
     equivalence).

These are informational timing benchmarks (they print and assert equivalence,
not strict wall-clock thresholds).
"""

from __future__ import annotations

import random
import time
from datetime import date
from decimal import Decimal

from cli.builders import build_initial_portfolio
from cli.fast_path import ChainedFastPathSimulationExecutor, FastPathSimulationExecutor
from cli.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from engine.application.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
)
from engine.application.simulation_context import SimulationContext
from engine.domain.model.asset import AssetClass
from engine.domain.model.dataset import Dataset
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.money import Currency, Money
from infrastructure.execution.parallel_executor import sequential_execute

EQ = AssetClass(id="equity", name="", description="")
BD = AssetClass(id="bond", name="", description="")


def _synthetic_dataset(n_months: int, seed: int = 7) -> Dataset:
    rng = random.Random(seed)
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


def _contexts(dataset: Dataset, start: date, horizons: list[int]) -> list[SimulationContext]:
    portfolio = build_initial_portfolio(Money(Decimal("1000000"), Currency.EUR))
    return [
        SimulationContext(
            experiment_name="bench",
            cohort=str(start),
            start_date=start,
            horizon_months=h,
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_portfolio=portfolio,
            dataset=dataset.slice(start, h),
            allocation_policy=ConstantAllocationPolicy(Decimal("0.5")),
            withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.04")),
        )
        for h in horizons
    ]


def test_fast_path_vs_reference_throughput() -> None:
    """Float closed form is orders of magnitude faster and outcome-equivalent."""
    dataset = _synthetic_dataset(260)
    from cli.builders import build_parameter_configs, build_research_plan
    from research.domain.cohort.generator import CohortGenerator
    from research.domain.experiment.definition import ExperimentDefinition

    cohorts = CohortGenerator.generate_rolling_monthly(dataset, 120)
    alloc = ConstantAllocationPolicy(Decimal("0.5"))
    withdraw = FixedRealWithdrawalPolicy(Decimal("0.04"))
    experiment_def = ExperimentDefinition(
        name="bench",
        description="bench",
        dataset=dataset,
        horizon_months=120,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        cohorts=cohorts,
        allocation_policies=(alloc,),
        withdrawal_policies=(withdraw,),
    )
    plan = build_research_plan(
        experiment_def,
        cohorts,
        build_parameter_configs({"equity_allocation": [0.5]}),
        alloc,
        withdraw,
    )

    t0 = time.perf_counter()
    reference = sequential_execute(plan, summary_only=True)
    t_reference = time.perf_counter() - t0

    t0 = time.perf_counter()
    fast = sequential_execute(
        plan,
        simulation_executor=FastPathSimulationExecutor(precision="float"),
        summary_only=True,
    )
    t_fast = time.perf_counter() - t0

    for ref, got in zip(reference.results, fast.results, strict=True):
        assert ref.statistics.success == got.statistics.success
        assert ref.statistics.failure_month == got.statistics.failure_month

    n = len(plan.units)
    print(
        f"fast path: reference {t_reference/n*1000:.1f}ms/cohort vs "
        f"closed-form {t_fast/n*1000:.3f}ms/cohort "
        f"({t_reference/t_fast:.0f}x, {n} cohorts)"
    )


def test_chained_vs_non_chained() -> None:
    """Chained multi-horizon execution is faster and outcome-equivalent."""
    dataset = _synthetic_dataset(320)
    start = date(1900, 1, 1)
    contexts = _contexts(dataset, start, [120, 240])
    definition = EngineExperimentDefinition(
        name="bench", description="bench", simulation_contexts=tuple(contexts)
    )

    plain = FastPathSimulationExecutor(precision="float")
    chained = ChainedFastPathSimulationExecutor(precision="float")

    t0 = time.perf_counter()
    non_chained = plain.execute(definition)
    t_non = time.perf_counter() - t0

    t0 = time.perf_counter()
    chained_run = chained.execute(definition)
    t_chained = time.perf_counter() - t0

    for a, b in zip(
        non_chained.simulation_results, chained_run.simulation_results, strict=True
    ):
        assert a.statistics.success == b.statistics.success
        assert a.statistics.failure_month == b.statistics.failure_month

    print(
        f"chaining: non-chained {t_non*1000:.1f}ms vs chained {t_chained*1000:.1f}ms "
        f"({t_non/t_chained:.1f}x, {len(contexts)} contexts)"
    )
