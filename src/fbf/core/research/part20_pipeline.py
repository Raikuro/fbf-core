"""Part 20 pipeline — batched SWR search, fixed-SWR grid, and experiment runners.

Bisection is strictly per ``(strategy, cohort)`` pair: each active pair
evaluates its own midpoint, brackets update as ``low = max(success)``,
``high = min(fail)``, ``best = max(success)``, and every active pair in a
step shares one multi-strategy plan execution.  The loop is driven
directly (not via ``SWROptimizer``) because a single-interval optimizer
cannot batch independent pair brackets.

No new domain behavior.  Part 19/20 shared abstraction: DEFERRED (T2.1).

Workload notes (host measurements during T2.1 design):
- static FixedReal plans use the FastPath closed form when eligible;
- glidepath plans fall back to the Decimal reference path;
- batched multi-strategy steps keep pool-creation overhead low.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from fbf.core.execution import ExecutionOptions
from fbf.core.research.part20_aggregation import percentile_swrs
from fbf.core.research.part20_planner import Part20ExecutionContext
from fbf.core.research.part20_strategies import Part20Strategy

__all__ = [
    "PART20_SWR_DOMAIN_MIN",
    "PART20_SWR_DOMAIN_MAX",
    "PART20_SWR_PRECISION",
    "BisectionCandidate",
    "BisectionOutcome",
    "SWRSearchResult",
    "FailureRateCell",
    "SearchCache",
    "bisect_per_pair",
    "default_max_steps",
    "run_percentile_search",
    "run_fixed_swr_grid",
]

# Finer than half of the last displayed digit (0.005% = 0.00005 as fraction).
PART20_SWR_PRECISION = Decimal("0.00001")
PART20_SWR_DOMAIN_MIN = Decimal("0.01")
PART20_SWR_DOMAIN_MAX = Decimal("0.08")

# Search-cache key: (horizon_years, population, final_value_target).
SearchCacheKey = tuple[int, str, Decimal]
SearchCache = dict[SearchCacheKey, dict[str, "SWRSearchResult"]]

# One active pair's candidate: (flat pair index, midpoint).
BisectionCandidate = tuple[int, Decimal]

# evaluate receives candidates for the active pairs and returns one
# success flag per candidate, same order.
BisectionEvaluate = Callable[[Sequence[BisectionCandidate]], Sequence[bool]]


def default_max_steps(
    domain_min: Decimal = PART20_SWR_DOMAIN_MIN,
    domain_max: Decimal = PART20_SWR_DOMAIN_MAX,
    precision: Decimal = PART20_SWR_PRECISION,
) -> int:
    """Bounded step count for the domain: ceil(log2(width/precision)) + 2."""
    width = domain_max - domain_min
    if width <= 0 or precision <= 0:
        raise ValueError("domain width and precision must be positive")
    return math.ceil(math.log2(float(width / precision))) + 2


@dataclass(frozen=True, slots=True)
class BisectionOutcome:
    """Result of one per-pair bisection run."""

    bests: tuple[Decimal | None, ...]
    lows: tuple[Decimal, ...]
    highs: tuple[Decimal, ...]
    steps: int


def bisect_per_pair(
    n_pairs: int,
    *,
    evaluate: BisectionEvaluate,
    domain_min: Decimal = PART20_SWR_DOMAIN_MIN,
    domain_max: Decimal = PART20_SWR_DOMAIN_MAX,
    precision: Decimal = PART20_SWR_PRECISION,
    max_steps: int | None = None,
    on_step: Callable[[int], None] | None = None,
) -> BisectionOutcome:
    """Binary-search break-even thresholds for *n_pairs* independent pairs.

    *evaluate* receives ``(pair_index, midpoint)`` candidates for the
    **active** pairs only and returns a success flag per candidate.
    Per pair: success raises ``low`` to the mid and records it as ``best``;
    failure lowers ``high`` to the mid.  Pairs stop when
    ``high - low <= precision`` or *max_steps* is reached.  A pair that
    never succeeded yields ``best=None`` (caller applies the documented
    domain-floor fallback).

    Each pair's mid lies strictly inside its own bracket — never the
    shared-envelope midpoint that previously straddled diverged brackets
    (T2.1 bisection regression).
    """
    if n_pairs <= 0:
        raise ValueError("n_pairs must be positive")
    if domain_max <= domain_min:
        raise ValueError("domain_max must exceed domain_min")
    steps_bound = (
        max_steps
        if max_steps is not None
        else default_max_steps(domain_min, domain_max, precision)
    )
    lows = [domain_min] * n_pairs
    highs = [domain_max] * n_pairs
    bests: list[Decimal | None] = [None] * n_pairs
    active = list(range(n_pairs))
    steps = 0
    while active and steps < steps_bound:
        candidates: list[BisectionCandidate] = [
            (i, (lows[i] + highs[i]) / Decimal("2")) for i in active
        ]
        successes = evaluate(candidates)
        if len(successes) != len(candidates):
            raise ValueError(
                f"evaluate returned {len(successes)} flags "
                f"for {len(candidates)} candidates"
            )
        still_active: list[int] = []
        for (i, mid), ok in zip(candidates, successes, strict=True):
            if ok:
                lows[i] = mid
                current_best = bests[i]
                if current_best is None or mid > current_best:
                    bests[i] = mid
            else:
                highs[i] = mid
            if (highs[i] - lows[i]) > precision:
                still_active.append(i)
        active = still_active
        steps += 1
        if on_step is not None:
            on_step(steps)
    return BisectionOutcome(
        bests=tuple(bests),
        lows=tuple(lows),
        highs=tuple(highs),
        steps=steps,
    )


@dataclass(frozen=True, slots=True)
class SWRSearchResult:
    """Per-cohort break-even SWRs for one strategy × population cell."""

    strategy_id: str
    horizon_years: int
    final_value_target: Decimal
    cape_regime: str  # HIGH | LOW
    cohort_dates: tuple[str, ...]
    per_cohort_swrs: tuple[Decimal, ...]
    cohort_count: int

    @property
    def percentiles(self) -> dict[Decimal, Decimal]:
        return percentile_swrs(self.per_cohort_swrs)

    @property
    def failsafe(self) -> Decimal:
        return self.percentiles[Decimal("0")]


@dataclass(frozen=True, slots=True)
class FailureRateCell:
    """One Experiment C cell: fixed SWR failure rate over CAPE > 20."""

    strategy_id: str
    horizon_years: int
    withdrawal_rate: Decimal
    failures: int
    total_cohorts: int

    @property
    def failure_rate(self) -> Decimal:
        if self.total_cohorts == 0:
            return Decimal("0")
        return Decimal(self.failures) / Decimal(self.total_cohorts)


def run_percentile_search(
    ctx: Part20ExecutionContext,
    strategies: Sequence[Part20Strategy],
    cohort_dates: Sequence[str],
    *,
    horizon_years: int,
    final_value_target: Decimal,
    cape_regime: str,
    options: ExecutionOptions,
    step_label: str,
    cache: SearchCache | None = None,
    on_step: Callable[[str, int], None] | None = None,
) -> dict[str, SWRSearchResult]:
    """Batched per-pair SWR search across *strategies* × *cohort_dates*.

    With *cache*, strategies already present under
    ``(horizon_years, cape_regime, final_value_target)`` are reused
    (counted in ``ctx.stats.reused_search_cells``) and only missing
    strategies are executed — this is the Experiment A → D FV=0 reuse.
    """
    if not strategies:
        raise ValueError("strategies must be non-empty")
    if not cohort_dates:
        raise ValueError("cohort_dates must be non-empty")
    if cape_regime not in {"HIGH", "LOW", "ALL"}:
        raise ValueError(f"cape_regime must be HIGH|LOW|ALL, got {cape_regime!r}")

    cache_key: SearchCacheKey = (horizon_years, cape_regime, final_value_target)
    results: dict[str, SWRSearchResult] = {}
    to_search: list[Part20Strategy] = []
    cached_table: dict[str, SWRSearchResult] = (
        cache.get(cache_key, {}) if cache is not None else {}
    )
    for strategy in strategies:
        hit = cached_table.get(strategy.id)
        if hit is not None:
            results[strategy.id] = hit
            ctx.stats.reused_search_cells += 1
        else:
            to_search.append(strategy)

    if not to_search:
        return results

    # Strategy-major pairs: one flat index space for the bisection.
    pairs: list[tuple[Part20Strategy, str]] = [
        (strategy, cohort_date)
        for strategy in to_search
        for cohort_date in cohort_dates
    ]
    horizon_months = horizon_years * 12 + 1
    step_counter = {"n": 0}

    def evaluate(candidates: Sequence[BisectionCandidate]) -> Sequence[bool]:
        step_counter["n"] += 1
        rows = [
            (pairs[i][0], pairs[i][1], mid) for i, mid in candidates
        ]
        bundle = ctx.build_units(
            rows=rows,
            horizon_months=horizon_months,
            final_value_target=final_value_target,
            step_label=f"{step_label}_s{step_counter['n']}",
        )
        successes = ctx.execute(bundle, options)
        if on_step is not None:
            on_step(step_label, step_counter["n"])
        return successes

    outcome = bisect_per_pair(len(pairs), evaluate=evaluate)

    n_cohorts = len(cohort_dates)
    new_results: dict[str, SWRSearchResult] = {}
    for s_idx, strategy in enumerate(to_search):
        start = s_idx * n_cohorts
        stop = start + n_cohorts
        segment_bests = outcome.bests[start:stop]
        swrs = tuple(
            b if b is not None else PART20_SWR_DOMAIN_MIN for b in segment_bests
        )
        result = SWRSearchResult(
            strategy_id=strategy.id,
            horizon_years=horizon_years,
            final_value_target=final_value_target,
            cape_regime=cape_regime,
            cohort_dates=tuple(cohort_dates),
            per_cohort_swrs=swrs,
            cohort_count=n_cohorts,
        )
        results[strategy.id] = result
        new_results[strategy.id] = result
    if cache is not None:
        cache.setdefault(cache_key, {}).update(new_results)
    return results


def run_fixed_swr_grid(
    ctx: Part20ExecutionContext,
    strategies: Sequence[Part20Strategy],
    cohort_dates: Sequence[str],
    *,
    horizon_years: int,
    withdrawal_rates: Sequence[Decimal],
    final_value_target: Decimal,
    population: str,
    options: ExecutionOptions,
) -> tuple[FailureRateCell, ...]:
    """Experiment C: fixed-SWR failure rates over the conditioned population."""
    if not withdrawal_rates:
        raise ValueError("withdrawal_rates must be non-empty (pass the audit grid)")
    if population not in {"HIGH", "LOW", "ALL"}:
        raise ValueError(f"population must be HIGH|LOW|ALL, got {population!r}")
    horizon_months = horizon_years * 12 + 1
    n_cohorts = len(cohort_dates)
    cells: list[FailureRateCell] = []
    for rate in withdrawal_rates:
        rows = [
            (strategy, cohort_date, rate)
            for strategy in strategies
            for cohort_date in cohort_dates
        ]
        bundle = ctx.build_units(
            rows=rows,
            horizon_months=horizon_months,
            final_value_target=final_value_target,
            step_label=f"expC_h{horizon_years}_swr_{rate}",
        )
        successes = ctx.execute(bundle, options)
        failure_counts: dict[str, int] = {s.id: 0 for s in strategies}
        totals: dict[str, int] = {s.id: 0 for s in strategies}
        for strategy, ok in zip(bundle.strategies, successes, strict=True):
            totals[strategy.id] += 1
            if not ok:
                failure_counts[strategy.id] += 1
        for strategy in strategies:
            sid = strategy.id
            total = totals[sid]
            if total != n_cohorts:
                raise RuntimeError(
                    f"Exp C {sid} H={horizon_years} rate={rate}: "
                    f"executed {total} cohorts, expected {n_cohorts}"
                )
            cells.append(
                FailureRateCell(
                    strategy_id=sid,
                    horizon_years=horizon_years,
                    withdrawal_rate=rate,
                    failures=failure_counts[sid],
                    total_cohorts=total,
                )
            )
    return tuple(cells)
