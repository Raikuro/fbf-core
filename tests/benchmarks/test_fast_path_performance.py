"""Performance benchmarks for the closed-form fast path and horizon derivation.

Measures, on a synthetic random-walk dataset:
  1. reference pipeline vs float closed form (per-cohort throughput),
  2. multi-horizon execution (wall time + outcome equivalence
     vs direct closed-form evaluation).

These are informational timing benchmarks (they print and assert equivalence,
not strict wall-clock thresholds).
"""

from __future__ import annotations

import random
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
    FastPathSimulationExecutor,
    evaluate_closed_form,
)
from fbf.core.execution.strategies.parallel_executor import sequential_execute
from fbf.core.study.builder import build_initial_portfolio

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
    from fbf.core.study.builder import build_initial_portfolio
    from fbf.core.study.internal.cohort.generator import CohortGenerator
    from fbf.core.study.internal.experiment.definition import ExperimentDefinition
    from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
    from fbf.core.study.plan import materialize_research_plan

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
    plan = materialize_research_plan(
        experiment_def=experiment_def,
        canonical_trajectory=dataset,
        cohorts=cohorts,
        param_configs=(ParameterConfiguration({"equity_allocation": 0.5}),),
        initial_portfolio=build_initial_portfolio(experiment_def.initial_wealth),
        horizon_resolver=lambda c: 120,
        policy_resolver=lambda c: (alloc, withdraw),
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
        assert ref.statistics.months_simulated == got.statistics.months_simulated

    n = len(plan.units)
    print(
        f"fast path: reference {t_reference / n * 1000:.1f}ms/cohort vs "
        f"closed-form {t_fast / n * 1000:.3f}ms/cohort "
        f"({t_reference / t_fast:.0f}x, {n} cohorts)"
    )


def test_decimal_fast_path_vs_reference_throughput() -> None:
    """Decimal closed form is bit-exact with reference and faster."""
    dataset = _synthetic_dataset(260)
    from fbf.core.study.builder import build_initial_portfolio
    from fbf.core.study.internal.cohort.generator import CohortGenerator
    from fbf.core.study.internal.experiment.definition import ExperimentDefinition
    from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
    from fbf.core.study.plan import materialize_research_plan

    cohorts = CohortGenerator.generate_rolling_monthly(dataset, 120)
    alloc = ConstantAllocationPolicy(Decimal("0.5"))
    withdraw = FixedRealWithdrawalPolicy(Decimal("0.04"))
    experiment_def = ExperimentDefinition(
        name="bench-dec",
        description="bench-dec",
        dataset=dataset,
        horizon_months=120,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        cohorts=cohorts,
        allocation_policies=(alloc,),
        withdrawal_policies=(withdraw,),
    )
    plan = materialize_research_plan(
        experiment_def=experiment_def,
        canonical_trajectory=dataset,
        cohorts=cohorts,
        param_configs=(ParameterConfiguration({"equity_allocation": 0.5}),),
        initial_portfolio=build_initial_portfolio(experiment_def.initial_wealth),
        horizon_resolver=lambda c: 120,
        policy_resolver=lambda c: (alloc, withdraw),
    )

    t0 = time.perf_counter()
    reference = sequential_execute(plan, summary_only=True)
    t_reference = time.perf_counter() - t0

    t0 = time.perf_counter()
    decimal_path = sequential_execute(
        plan,
        simulation_executor=FastPathSimulationExecutor(precision="decimal"),
        summary_only=True,
    )
    t_decimal = time.perf_counter() - t0

    for ref, got in zip(reference.results, decimal_path.results, strict=True):
        assert ref.statistics.success == got.statistics.success
        assert ref.statistics.failure_month == got.statistics.failure_month
        assert ref.statistics.months_simulated == got.statistics.months_simulated
        assert ref.statistics.final_wealth == got.statistics.final_wealth

    n = len(plan.units)
    print(
        f"decimal fast path: reference {t_reference / n * 1000:.1f}ms/cohort vs "
        f"decimal closed-form {t_decimal / n * 1000:.3f}ms/cohort "
        f"({t_reference / t_decimal:.0f}x, {n} cohorts)"
    )


def test_horizon_derivation_matches_direct_closed_form() -> None:
    """Multi-horizon execution is outcome-equivalent to direct closed-form."""
    dataset = _synthetic_dataset(320)
    start = date(1900, 1, 1)
    contexts = _contexts(dataset, start, [120, 240])
    definition = EngineExperimentDefinition(
        name="bench", description="bench", simulation_contexts=tuple(contexts)
    )

    direct = tuple(
        evaluate_closed_form(ctx, "float") for ctx in contexts
    )
    executor = FastPathSimulationExecutor(precision="float")

    t0 = time.perf_counter()
    executor_run = executor.execute(definition)
    t_executor = time.perf_counter() - t0

    for a, b in zip(direct, executor_run.simulation_results, strict=True):
        assert a.statistics.success == b.statistics.success
        assert a.statistics.failure_month == b.statistics.failure_month
        assert a.statistics.months_simulated == b.statistics.months_simulated
        assert a.statistics.final_wealth == b.statistics.final_wealth

    print(
        f"horizon derivation: {t_executor * 1000:.1f}ms "
        f"({len(contexts)} contexts)"
    )


def test_grid_plan_horizon_derivation_report() -> None:
    """A full synthetic grid's month-work is cut exactly by the family factor."""
    from fbf.core.execution.strategies.fast_path import (
        expected_report,
        reference_month_work,
    )
    from fbf.core.study.builder import build_initial_portfolio
    from fbf.core.study.internal.cohort.generator import CohortGenerator
    from fbf.core.study.internal.experiment.definition import ExperimentDefinition
    from fbf.core.study.internal.parameter.axis import ParameterAxis
    from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
    from fbf.core.study.internal.parameter.engine import ParameterSweepEngine
    from fbf.core.study.plan import materialize_research_plan

    dataset = _synthetic_dataset(780)
    horizons = (30, 40, 50, 60)
    cohorts = CohortGenerator.generate_rolling_monthly(dataset, max(horizons) * 12)
    configs = ParameterSweepEngine.cartesian_product(
        [
            ParameterAxis(name="equity_allocation", values=(1.0, 0.75, 0.5, 0.25, 0.0)),
            ParameterAxis(name="withdrawal_rate", values=(0.03, 0.035, 0.04, 0.045, 0.05)),
            ParameterAxis(name="horizon_years", values=horizons),
        ]
    )
    alloc = ConstantAllocationPolicy(Decimal("0.75"))
    withdraw = FixedRealWithdrawalPolicy(Decimal("0.04"))
    exp_def = ExperimentDefinition(
        name="grid-bench",
        description="grid-bench",
        dataset=dataset,
        horizon_months=max(horizons) * 12,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        cohorts=cohorts,
        allocation_policies=(alloc,),
        withdrawal_policies=(withdraw,),
    )
    _alloc_by_weight: dict[Decimal, ConstantAllocationPolicy] = {}
    _withdraw_by_rate: dict[Decimal, FixedRealWithdrawalPolicy] = {}

    def _resolve_policies(
        config: ParameterConfiguration,
    ) -> tuple[ConstantAllocationPolicy, FixedRealWithdrawalPolicy]:
        weight = Decimal(str(config.get("equity_allocation")))
        resolved_alloc = _alloc_by_weight.get(weight)
        if resolved_alloc is None:
            resolved_alloc = ConstantAllocationPolicy(equity_allocation=weight)
            _alloc_by_weight[weight] = resolved_alloc
        rate = Decimal(str(config.get("withdrawal_rate")))
        resolved_withd = _withdraw_by_rate.get(rate)
        if resolved_withd is None:
            resolved_withd = FixedRealWithdrawalPolicy(withdrawal_rate=rate)
            _withdraw_by_rate[rate] = resolved_withd
        return resolved_alloc, resolved_withd

    plan = materialize_research_plan(
        experiment_def=exp_def,
        canonical_trajectory=dataset,
        cohorts=cohorts,
        param_configs=configs,
        initial_portfolio=build_initial_portfolio(exp_def.initial_wealth),
        horizon_resolver=lambda c: int(c.get("horizon_years")) * 12,
        policy_resolver=_resolve_policies,
    )

    report = expected_report(plan)
    ref_work = reference_month_work(plan)
    ratio = ref_work / report.month_work

    assert report.groups == len(cohorts) * len(configs) // len(horizons)
    assert report.derived_results == len(plan.units) - report.groups
    assert report.independent_evaluations == 0

    t0 = time.perf_counter()
    result = sequential_execute(
        plan,
        simulation_executor=FastPathSimulationExecutor(precision="float"),
        summary_only=True,
    )
    t_result = time.perf_counter() - t0
    assert len(result.results) == len(plan.units)
    print(
        f"grid horizon derivation: {len(plan.units):,} units -> {report.groups:,} "
        f"families, month-work {report.month_work:,}/{ref_work:,} "
        f"({ratio:.1f}x reduction), ran in {t_result * 1000:.1f}ms"
    )
