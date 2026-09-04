"""C4 — Performance Benchmark: Part 49 Debt Pipeline Cost.

Measures the real execution cost of the debt-aware Part 49 pipeline relative
to the equivalent non-debt baseline. This is a measurement and validation
phase — no optimization is performed.

Three scenarios are compared:
  A. Non-debt baseline — standard simulation path (no debt parameters)
  B. Debt-capable pipeline, debt inactive — debt configured but interest_rate=0
  C. Active Part 49 debt — active borrowing, interest accrual, LTV observation

The S4 design review acceptance criterion is:
  Debt-aware execution <= 2x non-debt baseline

Environment is documented inline. All timings use time.perf_counter() with
multiple repetitions and median as the robust central metric.
"""

from __future__ import annotations

import gc
import os
import platform
import statistics
import sys
import time
from collections.abc import Callable
from datetime import date
from decimal import Decimal

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies import ConstantAllocationPolicy
from fbf.core.domain.policies.part49_withdrawal import Part49WithdrawalPolicy
from fbf.core.execution.pipeline.executor import SimulationExecutor
from fbf.core.execution.strategies.parallel_executor import (
    _create_default_simulation_executor,
    sequential_execute,
)
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import ResearchPlan, materialize_research_plan

# ---------------------------------------------------------------------------
# Asset classes
# ---------------------------------------------------------------------------

EQUITY = AssetClass(id="equity", name="", description="")
BOND = AssetClass(id="bond", name="", description="")


# ---------------------------------------------------------------------------
# Dataset construction
# ---------------------------------------------------------------------------

def _make_dataset(n_months: int = 600, start_year: int = 1970) -> Dataset:
    """Create a synthetic dataset with varying equity and bond prices.

    Deterministic: prices follow a simple drift pattern, no randomness.
    """
    snapshots = []
    pe = Decimal("100")
    pb = Decimal("50")
    d = date(start_year, 1, 1)
    for i in range(n_months):
        snapshots.append(
            MarketSnapshot(
                date=d,
                index_levels={EQUITY: pe, BOND: pb},
                inflation=Decimal("0.002"),
                inflation_cumulative=Decimal(str(round(i * 0.002, 6))),
                is_ath=(i == 0),
                is_underwater=False,
                running_ath=pe,
            )
        )
        # Deterministic drift
        pe += Decimal("0.5")
        pb += Decimal("0.1")
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return Dataset(snapshots=snapshots, frequency="monthly", version="C4_bench")


# ---------------------------------------------------------------------------
# Plan construction helpers
# ---------------------------------------------------------------------------

INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)
HORIZON_YEARS = 30
HORIZON_MONTHS = HORIZON_YEARS * 12 + 1  # 361

# Part 49 debt parameters
INTEREST_RATE = Decimal("0.015")
LTV_LIMIT = Decimal("0.75")
LOAN_DRAW_RATE = Decimal("0.01")
WITHDRAWAL_RATE = Decimal("0.03")
EQUITY_ALLOCATION = Decimal("0.75")


def _make_cohorts(n_cohorts: int) -> tuple[CohortSpecification, ...]:
    """Generate n_cohorts rolling monthly cohorts starting Jan 1970."""
    cohorts = []
    for i in range(n_cohorts):
        m = i + 1
        year = 1970 + (m - 1) // 12
        month = ((m - 1) % 12) + 1
        cohorts.append(CohortSpecification(start_date=date(year, month, 1)))
    return tuple(cohorts)


def _make_plan_scenario_a(
    dataset: Dataset,
    cohorts: tuple[CohortSpecification, ...],
) -> ResearchPlan:
    """Scenario A: Non-debt baseline — no debt parameters."""
    param_config = ParameterConfiguration(
        {"withdrawal_rate": 0.03, "horizon_years": 30}
    )

    exp_def = ExperimentDefinition(
        name="c4-bench-A",
        description="C4 baseline (no debt)",
        dataset=dataset,
        horizon_months=HORIZON_MONTHS,
        initial_wealth=INITIAL_WEALTH,
        cohorts=cohorts,
        allocation_policies=(ConstantAllocationPolicy(equity_allocation=EQUITY_ALLOCATION),),
        withdrawal_policies=(Part49WithdrawalPolicy(withdrawal_rate=WITHDRAWAL_RATE),),
    )

    placeholder_portfolio = Portfolio(
        holdings=(
            AssetHolding(asset_class=EQUITY, units=Decimal("1")),
            AssetHolding(asset_class=BOND, units=Decimal("1")),
        )
    )

    return materialize_research_plan(
        experiment_def=exp_def,
        canonical_trajectory=dataset,
        cohorts=cohorts,
        param_configs=(param_config,),
        initial_portfolio=placeholder_portfolio,
        horizon_resolver=lambda pc: HORIZON_MONTHS,
        policy_resolver=lambda pc: (
            ConstantAllocationPolicy(equity_allocation=EQUITY_ALLOCATION),
            Part49WithdrawalPolicy(withdrawal_rate=WITHDRAWAL_RATE),
        ),
        # NO debt parameters
    )


def _make_plan_scenario_b(
    dataset: Dataset,
    cohorts: tuple[CohortSpecification, ...],
) -> ResearchPlan:
    """Scenario B: Debt-capable pipeline, debt inactive (interest_rate=0).

    Pipeline steps are present but interest_rate=0 makes them no-ops.
    """
    param_config = ParameterConfiguration(
        {"withdrawal_rate": 0.03, "horizon_years": 30}
    )

    exp_def = ExperimentDefinition(
        name="c4-bench-B",
        description="C4 debt-capable inactive",
        dataset=dataset,
        horizon_months=HORIZON_MONTHS,
        initial_wealth=INITIAL_WEALTH,
        cohorts=cohorts,
        allocation_policies=(ConstantAllocationPolicy(equity_allocation=EQUITY_ALLOCATION),),
        withdrawal_policies=(Part49WithdrawalPolicy(withdrawal_rate=WITHDRAWAL_RATE),),
    )

    placeholder_portfolio = Portfolio(
        holdings=(
            AssetHolding(asset_class=EQUITY, units=Decimal("1")),
            AssetHolding(asset_class=BOND, units=Decimal("1")),
        )
    )

    return materialize_research_plan(
        experiment_def=exp_def,
        canonical_trajectory=dataset,
        cohorts=cohorts,
        param_configs=(param_config,),
        initial_portfolio=placeholder_portfolio,
        horizon_resolver=lambda pc: HORIZON_MONTHS,
        policy_resolver=lambda pc: (
            ConstantAllocationPolicy(equity_allocation=EQUITY_ALLOCATION),
            Part49WithdrawalPolicy(withdrawal_rate=WITHDRAWAL_RATE),
        ),
        interest_rate=Decimal("0"),  # debt configured but inactive
        ltv_limit=LTV_LIMIT,
        ltv_enforcement=False,
        loan_draw_rate=Decimal("0"),
    )


def _make_plan_scenario_c(
    dataset: Dataset,
    cohorts: tuple[CohortSpecification, ...],
) -> ResearchPlan:
    """Scenario C: Active Part 49 debt — full borrowing, interest, LTV."""
    param_config = ParameterConfiguration(
        {"withdrawal_rate": 0.03, "horizon_years": 30}
    )

    exp_def = ExperimentDefinition(
        name="c4-bench-C",
        description="C4 active Part 49 debt",
        dataset=dataset,
        horizon_months=HORIZON_MONTHS,
        initial_wealth=INITIAL_WEALTH,
        cohorts=cohorts,
        allocation_policies=(ConstantAllocationPolicy(equity_allocation=EQUITY_ALLOCATION),),
        withdrawal_policies=(Part49WithdrawalPolicy(withdrawal_rate=WITHDRAWAL_RATE),),
    )

    placeholder_portfolio = Portfolio(
        holdings=(
            AssetHolding(asset_class=EQUITY, units=Decimal("1")),
            AssetHolding(asset_class=BOND, units=Decimal("1")),
        )
    )

    return materialize_research_plan(
        experiment_def=exp_def,
        canonical_trajectory=dataset,
        cohorts=cohorts,
        param_configs=(param_config,),
        initial_portfolio=placeholder_portfolio,
        horizon_resolver=lambda pc: HORIZON_MONTHS,
        policy_resolver=lambda pc: (
            ConstantAllocationPolicy(equity_allocation=EQUITY_ALLOCATION),
            Part49WithdrawalPolicy(withdrawal_rate=WITHDRAWAL_RATE),
        ),
        interest_rate=INTEREST_RATE,
        ltv_limit=LTV_LIMIT,
        ltv_enforcement=False,
        loan_draw_rate=LOAN_DRAW_RATE,
    )


# ---------------------------------------------------------------------------
# Timing helper
# ---------------------------------------------------------------------------

def _bench(
    func: Callable[[], object],
    warmup: int = 2,
    repetitions: int = 5,
) -> tuple[float, float]:
    """Run func (warmup + repetitions), return (median, stdev) in seconds."""
    for _ in range(warmup):
        func()
    times = []
    for _ in range(repetitions):
        gc.collect()
        t0 = time.perf_counter()
        func()
        times.append(time.perf_counter() - t0)
    return statistics.median(times), statistics.stdev(times) if len(times) > 1 else 0.0


# ---------------------------------------------------------------------------
# Benchmark tests
# ---------------------------------------------------------------------------


class TestPart49PipelineCost:
    """Measure the cost of the Part 49 debt pipeline across scenarios."""

    def test_single_cohort_scenarios(self) -> None:
        """Compare A/B/C for a single cohort (30-year horizon)."""
        dataset = _make_dataset()
        cohorts = _make_cohorts(1)
        executor = _create_default_simulation_executor()

        plan_a = _make_plan_scenario_a(dataset, cohorts)
        plan_b = _make_plan_scenario_b(dataset, cohorts)
        plan_c = _make_plan_scenario_c(dataset, cohorts)

        time_a, std_a = _bench(lambda: sequential_execute(plan_a, simulation_executor=executor))
        time_b, std_b = _bench(lambda: sequential_execute(plan_b, simulation_executor=executor))
        time_c, std_c = _bench(lambda: sequential_execute(plan_c, simulation_executor=executor))

        ratio_b = time_b / time_a if time_a > 0 else 0
        ratio_c = time_c / time_a if time_a > 0 else 0

        print("\n[C4] Single cohort (1 cohort x 361 months):")
        print(f"[C4]   A (baseline):      {time_a*1000:8.1f}ms  (+/- {std_a*1000:.1f}ms)")
        rb = f"  ratio={ratio_b:.3f}x"
        rc = f"  ratio={ratio_c:.3f}x"
        print(f"[C4]   B (debt inactive): {time_b*1000:8.1f}ms  (+/- {std_b*1000:.1f}ms){rb}")
        print(f"[C4]   C (active debt):   {time_c*1000:8.1f}ms  (+/- {std_c*1000:.1f}ms){rc}")
        acc = "PASS" if ratio_c <= 2.0 else "FAIL"
        print(f"[C4]   Acceptance (<=2x): {acc}")

    def test_multi_cohort_scenarios(self) -> None:
        """Compare A/B/C for 10 cohorts (30-year horizon each)."""
        dataset = _make_dataset()
        cohorts = _make_cohorts(10)
        executor = _create_default_simulation_executor()

        plan_a = _make_plan_scenario_a(dataset, cohorts)
        plan_b = _make_plan_scenario_b(dataset, cohorts)
        plan_c = _make_plan_scenario_c(dataset, cohorts)

        time_a, std_a = _bench(lambda: sequential_execute(plan_a, simulation_executor=executor))
        time_b, std_b = _bench(lambda: sequential_execute(plan_b, simulation_executor=executor))
        time_c, std_c = _bench(lambda: sequential_execute(plan_c, simulation_executor=executor))

        ratio_b = time_b / time_a if time_a > 0 else 0
        ratio_c = time_c / time_a if time_a > 0 else 0

        print("\n[C4] Multi-cohort (10 cohorts x 361 months):")
        print(f"[C4]   A (baseline):      {time_a*1000:8.1f}ms  (+/- {std_a*1000:.1f}ms)")
        rb = f"  ratio={ratio_b:.3f}x"
        rc = f"  ratio={ratio_c:.3f}x"
        print(f"[C4]   B (debt inactive): {time_b*1000:8.1f}ms  (+/- {std_b*1000:.1f}ms){rb}")
        print(f"[C4]   C (active debt):   {time_c*1000:8.1f}ms  (+/- {std_c*1000:.1f}ms){rc}")
        acc = "PASS" if ratio_c <= 2.0 else "FAIL"
        print(f"[C4]   Acceptance (<=2x): {acc}")

    def test_scaling_with_cohort_count(self) -> None:
        """Measure how cost scales with cohort count for scenario C."""
        dataset = _make_dataset()
        executor = _create_default_simulation_executor()

        print("\n[C4] Scaling (active debt, 30-year horizon):")
        print(f"[C4]   {'Cohorts':>8}  {'Time':>10}  {'Per-cohort':>12}  {'Stdev':>8}")
        print(f"[C4]   {'-------':>8}  {'----':>10}  {'----------':>12}  {'-----':>8}")

        for n_cohorts in [1, 5, 10, 15]:
            cohorts = _make_cohorts(n_cohorts)
            plan = _make_plan_scenario_c(dataset, cohorts)

            def _run_plan(
                p: ResearchPlan = plan,
                e: SimulationExecutor = executor,
            ) -> object:
                return sequential_execute(p, simulation_executor=e)

            time_med, time_std = _bench(_run_plan, warmup=2, repetitions=5)
            per_cohort = time_med / n_cohorts
            print(
                f"[C4]   {n_cohorts:>8}  {time_med*1000:>9.1f}ms  "
                f"{per_cohort*1000:>11.2f}ms  {time_std*1000:>7.1f}ms"
            )


class TestDebtOverheadBreakdown:
    """Break down where the debt pipeline overhead comes from."""

    def test_pipeline_step_count_comparison(self) -> None:
        """Report pipeline step counts for each scenario."""
        from fbf.core.execution.pipeline.default_pipeline import create_default_pipeline

        pipeline = create_default_pipeline()
        step_names = [type(s).__name__ for s in pipeline.steps]

        print(f"\n[C4] Pipeline steps ({len(step_names)} total):")
        for i, name in enumerate(step_names):
            print(f"[C4]   {i+1:>2}. {name}")

    def test_debt_snapshot_construction_cost(self) -> None:
        """Measure the cost of DebtSnapshot construction per month."""
        from fbf.core.execution.pipeline.simulation import DebtSnapshot

        n_iterations = 10000
        loan = Decimal("500000")
        cash = Decimal("10000")
        ltv = Decimal("0.65")
        net_worth = Decimal("510000")

        gc.collect()
        t0 = time.perf_counter()
        for _ in range(n_iterations):
            DebtSnapshot(
                loan_balance=loan,
                cash_balance=cash,
                ltv=ltv,
                net_worth=net_worth,
                ltv_enforcement=False,
            )
        elapsed = time.perf_counter() - t0

        per_snapshot = elapsed / n_iterations
        # 361 months per cohort
        per_cohort = per_snapshot * 361

        print("\n[C4] DebtSnapshot construction:")
        print(f"[C4]   per snapshot: {per_snapshot*1e6:.1f}us")
        print(f"[C4]   per cohort (361 months): {per_cohort*1000:.2f}ms")

    def test_interest_accrual_step_cost(self) -> None:
        """Measure the cost of the interest accrual pipeline step."""
        from fbf.core.execution.pipeline.simulation import ExecutionStatus, SimulationState
        from fbf.core.execution.pipeline.simulation_context import SimulationContext
        from fbf.core.execution.pipeline.steps.interest_accrual_step import InterestAccrualStep

        step = InterestAccrualStep()

        # Create a minimal state with debt
        dataset = _make_dataset(2)
        portfolio = Portfolio(holdings=(
            AssetHolding(asset_class=EQUITY, units=Decimal("5000")),
            AssetHolding(asset_class=BOND, units=Decimal("5000")),
        ))
        context = SimulationContext(
            experiment_name="bench",
            cohort="bench",
            start_date=date(1970, 1, 1),
            horizon_months=2,
            initial_wealth=INITIAL_WEALTH,
            initial_portfolio=portfolio,
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.75")),
            withdrawal_policy=Part49WithdrawalPolicy(withdrawal_rate=Decimal("0.03")),
            interest_rate=INTEREST_RATE,
            ltv_limit=LTV_LIMIT,
            ltv_enforcement=False,
            loan_draw_rate=LOAN_DRAW_RATE,
        )
        state = SimulationState(
            context=context,
            current_date=date(1970, 1, 1),
            period_index=0,
            portfolio=portfolio,
            market_snapshot=dataset[0],
            current_wealth=INITIAL_WEALTH,
            peak_wealth=INITIAL_WEALTH,
            status=ExecutionStatus.RUNNING,
            loan_balance=Decimal("10000"),
            interest_rate=INTEREST_RATE,
            ltv_limit=LTV_LIMIT,
            ltv_enforcement=False,
        )

        n_iterations = 10000
        gc.collect()
        t0 = time.perf_counter()
        for _ in range(n_iterations):
            step.execute(state)
        elapsed = time.perf_counter() - t0

        per_call = elapsed / n_iterations
        per_cohort = per_call * 361

        print("\n[C4] InterestAccrualStep:")
        print(f"[C4]   per call: {per_call*1e6:.1f}us")
        print(f"[C4]   per cohort (361 months): {per_cohort*1000:.2f}ms")

    def test_ltv_evaluation_step_cost(self) -> None:
        """Measure the cost of the LTV evaluation pipeline step."""
        from fbf.core.execution.pipeline.simulation import ExecutionStatus, SimulationState
        from fbf.core.execution.pipeline.simulation_context import SimulationContext
        from fbf.core.execution.pipeline.steps.ltv_evaluation_step import LTVEvaluationStep

        step = LTVEvaluationStep()

        dataset = _make_dataset(2)
        portfolio = Portfolio(holdings=(
            AssetHolding(asset_class=EQUITY, units=Decimal("5000")),
            AssetHolding(asset_class=BOND, units=Decimal("5000")),
        ))
        context = SimulationContext(
            experiment_name="bench",
            cohort="bench",
            start_date=date(1970, 1, 1),
            horizon_months=2,
            initial_wealth=INITIAL_WEALTH,
            initial_portfolio=portfolio,
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.75")),
            withdrawal_policy=Part49WithdrawalPolicy(withdrawal_rate=Decimal("0.03")),
            interest_rate=INTEREST_RATE,
            ltv_limit=LTV_LIMIT,
            ltv_enforcement=False,
            loan_draw_rate=LOAN_DRAW_RATE,
        )
        state = SimulationState(
            context=context,
            current_date=date(1970, 1, 1),
            period_index=0,
            portfolio=portfolio,
            market_snapshot=dataset[0],
            current_wealth=INITIAL_WEALTH,
            peak_wealth=INITIAL_WEALTH,
            status=ExecutionStatus.RUNNING,
            loan_balance=Decimal("10000"),
            interest_rate=INTEREST_RATE,
            ltv_limit=LTV_LIMIT,
            ltv_enforcement=False,
        )

        n_iterations = 10000
        gc.collect()
        t0 = time.perf_counter()
        for _ in range(n_iterations):
            step.execute(state)
        elapsed = time.perf_counter() - t0

        per_call = elapsed / n_iterations
        per_cohort = per_call * 361

        print("\n[C4] LTVEvaluationStep:")
        print(f"[C4]   per call: {per_call*1e6:.1f}us")
        print(f"[C4]   per cohort (361 months): {per_cohort*1000:.2f}ms")


class TestEnvironmentDocumentation:
    """Document the benchmark environment for reproducibility."""

    def test_report_environment(self) -> None:
        """Print environment details."""
        print("\n[C4] Environment:")
        print(f"[C4]   Python: {sys.version}")
        print(f"[C4]   Platform: {platform.platform()}")
        print(f"[C4]   Processor: {platform.processor()}")
        print(f"[C4]   CPU count: {os.cpu_count()}")
        print("[C4]   fbf-core: from source (development install)")
