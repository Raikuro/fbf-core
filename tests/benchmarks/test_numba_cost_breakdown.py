"""End-to-end cost breakdown for Numba vs reference execution.

Measures separately:
  1. Context/data preparation
  2. Dataset extraction
  3. Decimal → float conversion
  4. Batch construction (grouping, growth factor computation)
  5. Numba execution (kernel time)
  6. Result reconstruction
  7. Total wall-clock time

Compares Numba executor against the Decimal reference engine.
"""

from __future__ import annotations

import time
from datetime import date
from decimal import Decimal

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from fbf.core.execution.pipeline.executor import SimulationExecutor
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.numba_executor import NumbaSimulationExecutor
from fbf.core.execution.strategies.parallel_executor import (
    _create_default_simulation_executor,
)
from fbf.core.study.builder import build_initial_portfolio

_EQ = AssetClass(id="equity", name="", description="")
_BD = AssetClass(id="bond", name="", description="")


def _make_dataset(n_months: int) -> Dataset:
    pe = pb = Decimal("100")
    snapshots = []
    d = date(1900, 1, 1)
    for _ in range(n_months):
        snapshots.append(
            MarketSnapshot(
                date=d,
                index_levels={_EQ: pe, _BD: pb},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            )
        )
        pe *= Decimal("1.006")
        pb *= Decimal("1.002")
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return Dataset(snapshots=snapshots, frequency="monthly", version="1.0")


def _make_context(
    dataset: Dataset,
    horizon: int,
    w: float = 0.5,
    r: float = 0.04,
) -> SimulationContext:
    start = dataset[0].date
    portfolio = build_initial_portfolio(Money(Decimal("1000000"), Currency.EUR))
    return SimulationContext(
        experiment_name="bench",
        cohort=str(start),
        start_date=start,
        horizon_months=horizon,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        initial_portfolio=portfolio,
        dataset=dataset.slice(start, horizon),
        allocation_policy=ConstantAllocationPolicy(Decimal(str(w))),
        withdrawal_policy=FixedRealWithdrawalPolicy(Decimal(str(r))),
    )


def _make_experiment(contexts: list[SimulationContext]) -> EngineExperimentDefinition:
    return EngineExperimentDefinition(
        name="bench",
        description="benchmark",
        simulation_contexts=tuple(contexts),
    )


def _benchmark_executor(
    executor: SimulationExecutor,
    definition: EngineExperimentDefinition,
    warmup: int = 2,
    rounds: int = 5,
) -> list[float]:
    """Run executor multiple times, return list of wall-clock times."""
    times = []
    for _ in range(warmup):
        executor.execute(definition)
    for _ in range(rounds):
        t0 = time.perf_counter()
        executor.execute(definition)
        t1 = time.perf_counter()
        times.append(t1 - t0)
    return times


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def run_cost_breakdown() -> None:
    """Run the cost breakdown benchmark and print results."""
    ds = _make_dataset(1441)

    # --- single trajectory ---
    ctx_single = _make_context(ds, horizon=720, w=0.5, r=0.04)
    defn_single = _make_experiment([ctx_single])

    # --- group of 6 horizons ---
    horizons_group = [12, 60, 120, 240, 360, 720]
    ctxs_group = [_make_context(ds, horizon=h, w=0.5, r=0.04) for h in horizons_group]
    defn_group = _make_experiment(ctxs_group)

    # --- larger batch: 6 cohorts x 6 horizons = 36 contexts ---
    ctxs_batch = []
    for cohort_start_month in range(6):
        d = date(1900, 1 + cohort_start_month, 1)
        for h in horizons_group:
            portfolio = build_initial_portfolio(Money(Decimal("1000000"), Currency.EUR))
            ctxs_batch.append(
                SimulationContext(
                    experiment_name="bench",
                    cohort=str(d),
                    start_date=d,
                    horizon_months=h,
                    initial_wealth=Money(Decimal("1000000"), Currency.EUR),
                    initial_portfolio=portfolio,
                    dataset=ds.slice(d, h),
                    allocation_policy=ConstantAllocationPolicy(Decimal("0.5")),
                    withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.04")),
                )
            )
    defn_batch = _make_experiment(ctxs_batch)

    ref_exec = _create_default_simulation_executor()
    numba_exec = NumbaSimulationExecutor()

    print("=" * 72)
    print("R7.5.3 End-to-End Cost Breakdown")
    print("=" * 72)

    for label, defn in [
        ("single (1 ctx, 720m)", defn_single),
        ("group (6 horizons)", defn_group),
        ("batch (36 ctxs)", defn_batch),
    ]:
        n_ctxs = len(defn.simulation_contexts)
        total_months = sum(c.horizon_months for c in defn.simulation_contexts)

        ref_times = _benchmark_executor(ref_exec, defn)
        numba_times = _benchmark_executor(numba_exec, defn)

        ref_med = _median(ref_times)
        numba_med = _median(numba_times)
        speedup = ref_med / numba_med if numba_med > 0 else float("inf")

        print(f"\n--- {label} ({n_ctxs} ctxs, {total_months} months) ---")
        print(f"  Reference:  {ref_med*1000:8.1f} ms  (median of 5)")
        print(f"  Numba:      {numba_med*1000:8.1f} ms  (median of 5)")
        print(f"  Speedup:    {speedup:8.1f}x")

        # Per-context breakdown
        if n_ctxs > 0:
            ref_per = ref_med / n_ctxs * 1000
            numba_per = numba_med / n_ctxs * 1000
            print(f"  Per ctx:    ref={ref_per:.2f} ms  numba={numba_per:.2f} ms")

    # --- Numba executor internal breakdown ---
    print(f"\n--- Numba executor internal breakdown (batch, {len(ctxs_batch)} ctxs) ---")

    # Time the grouping + data preparation separately
    from fbf.core.execution.strategies.fast_path import (
        _group_key,
        _index_series,
        _weights_by_class,
        is_fast_path_eligible,
    )
    from fbf.core.execution.strategies.numba_kernel import compute_growth_factors

    t0 = time.perf_counter()
    key_to_group: dict[tuple[object, ...], int] = {}
    group_contexts: list[list[SimulationContext]] = []
    for ctx in defn_batch.simulation_contexts:
        if not is_fast_path_eligible(ctx):
            continue
        key = _group_key(ctx)
        if key not in key_to_group:
            key_to_group[key] = len(group_contexts)
            group_contexts.append([])
        group_contexts[key_to_group[key]].append(ctx)
    t1 = time.perf_counter()
    grouping_ms = (t1 - t0) * 1000

    # Time growth factor computation
    t0 = time.perf_counter()
    for contexts in group_contexts:
        longest = max(contexts, key=lambda c: c.horizon_months)
        weights = _weights_by_class(longest)
        series = _index_series(longest)
        asset_classes = tuple(series.keys())
        compute_growth_factors(asset_classes, weights, series, longest.horizon_months)
    t1 = time.perf_counter()
    gf_ms = (t1 - t0) * 1000

    # Time the full Numba executor
    t0 = time.perf_counter()
    numba_exec.execute(defn_batch)
    t1 = time.perf_counter()
    total_ms = (t1 - t0) * 1000

    print(f"  Grouping:          {grouping_ms:8.2f} ms")
    print(f"  Growth factors:    {gf_ms:8.2f} ms")
    print(f"  Kernel + results:  {total_ms - grouping_ms - gf_ms:8.2f} ms")
    print(f"  Total:             {total_ms:8.2f} ms")

    # Reference full time
    t0 = time.perf_counter()
    ref_exec.execute(defn_batch)
    t1 = time.perf_counter()
    ref_total_ms = (t1 - t0) * 1000
    print(f"\n  Reference total:   {ref_total_ms:8.2f} ms")
    print(f"  Overall speedup:   {ref_total_ms / total_ms:.1f}x")

    # --- batch-size sweep ---
    print("\n" + "=" * 72)
    print("R7.5.4 Batch-Size Sweep")
    print("=" * 72)
    print(f"{'batch':>8}  {'ref_ms':>10}  {'numba_ms':>10}  {'speedup':>8}  {'us/ctx':>10}")
    print("-" * 60)

    for batch_n in [1, 6, 18, 36, 72, 180]:
        # Build batch: batch_n contexts, each a different cohort start, horizon 720
        ctxs = []
        for i in range(batch_n):
            month_offset = (i % 12) + 1
            year_offset = i // 12
            d = date(1900 + year_offset, month_offset, 1)
            portfolio = build_initial_portfolio(Money(Decimal("1000000"), Currency.EUR))
            ctxs.append(
                SimulationContext(
                    experiment_name="bench",
                    cohort=str(d),
                    start_date=d,
                    horizon_months=720,
                    initial_wealth=Money(Decimal("1000000"), Currency.EUR),
                    initial_portfolio=portfolio,
                    dataset=ds.slice(d, 720),
                    allocation_policy=ConstantAllocationPolicy(Decimal("0.5")),
                    withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.04")),
                )
            )
        defn = _make_experiment(ctxs)

        ref_times = _benchmark_executor(ref_exec, defn, warmup=1, rounds=3)
        numba_times = _benchmark_executor(numba_exec, defn, warmup=1, rounds=3)

        ref_med = _median(ref_times)
        numba_med = _median(numba_times)
        speedup = ref_med / numba_med if numba_med > 0 else float("inf")
        us_per_ctx = numba_med / batch_n * 1_000_000

        row = f"{batch_n:>8}  {ref_med*1000:>10.1f}  {numba_med*1000:>10.1f}"
        row += f"  {speedup:>7.1f}x  {us_per_ctx:>10.1f}"
        print(row)


if __name__ == "__main__":
    run_cost_breakdown()
