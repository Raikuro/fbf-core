"""Part 20 research planner — cohort populations and plan materialization.

Consumes the canonical Part 3 cohort manifest (shared ERN retirement-start
universe) and the canonical trajectory to build ``ResearchPlan`` units for
the Part 20 baseline audit.

CAPE conditioning is applied at the research boundary: populations are
selected from manifest metadata before units are built.  No CAPE data
enters the engine.

Per-cohort horizons are clamped to the manifest ``max_horizon_months``
(``min(requested, max_h)``), mirroring ``materialize_part3_plan`` — the
established convention for manifest-driven plans.  Without the clamp the
final cohort (2015-12, max 720 months) cannot slice a 721-month horizon.

Part 19/20 shared abstraction: DEFERRED (T2.1 architecture decision).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import Portfolio
from fbf.core.domain.policies.allocation_policy import AllocationPolicy
from fbf.core.domain.policies.cape_regime import CapeBinary, classify_cape_binary
from fbf.core.domain.policies.concrete import FixedRealWithdrawalPolicy
from fbf.core.execution import (
    ExecutionOptions,
    ExecutionStrategy,
    ResearchExecutionResult,
    execute_study_plan,
)
from fbf.core.execution.pipeline.simulation import SimulationResult
from fbf.core.execution.strategies.numba_executor import (
    GlidepathGFKey,
)
from fbf.core.research.part3_planner import CohortManifest, load_manifest
from fbf.core.research.part20_strategies import Part20Strategy
from fbf.core.study.builder import BuiltStudy, build_initial_portfolio
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan

__all__ = [
    "Part20CohortPopulations",
    "Part20ExecutionContext",
    "Part20PlanBundle",
    "Part20RunStats",
    "choose_execution_strategy",
    "extract_successes",
    "load_part20_manifest",
    "PART20_INITIAL_WEALTH",
    "PART20_PARALLEL_UNIT_THRESHOLD",
    "PART20_PARALLEL_CHUNK_UNITS",
]

PART20_INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)


def _is_glidepath_strategy(strategy: Part20Strategy) -> bool:
    """Check if a Part20Strategy is a glidepath (eligible for Numba glidepath path)."""
    return strategy.kind == "glidepath"

# Minimum batch size at which mixed (glidepath) plans use PARALLEL.
PART20_PARALLEL_UNIT_THRESHOLD = 500

# Max units per PARALLEL execute_study_plan call for glidepath partitions.
# Host probe: 12,800 units OK; 19,200+ raised BrokenProcessPool (worker
# death during long Decimal batches).  12,000 is a proven-safe bound.
PART20_PARALLEL_CHUNK_UNITS = 12_000


def load_part20_manifest(path: Path) -> CohortManifest:
    """Load the canonical cohort manifest used by the Part 20 audit."""
    return load_manifest(path)


@dataclass(frozen=True, slots=True)
class Part20CohortPopulations:
    """CAPE-conditioned cohort populations for Part 20.

    Populations are cohort start-date strings (ISO).  Pre-1881 cohorts
    without CAPE are excluded from both binary regimes.
    """

    all_dates: tuple[str, ...]
    cape_available_dates: tuple[str, ...]
    high_dates: tuple[str, ...]  # CAPE > 20
    low_dates: tuple[str, ...]  # CAPE <= 20

    @property
    def excluded_no_cape(self) -> int:
        return len(self.all_dates) - len(self.cape_available_dates)


def build_cohort_populations(manifest: CohortManifest) -> Part20CohortPopulations:
    """Derive Part 20 cohort populations from manifest metadata.

    Filtering rules (frozen audit methodology):
    - market-available cohorts form the executable universe (1,739);
    - CAPE conditioning uses the retirement-start CAPE value;
    - cohorts without CAPE are excluded from both binary panels;
    - ``classify_cape_binary`` implements CAPE > 20 vs CAPE <= 20.
    """
    all_dates = tuple(
        e.cohort_date for e in manifest.cohorts if e.market_available
    )
    high: list[str] = []
    low: list[str] = []
    cape_available: list[str] = []
    for entry in manifest.cohorts:
        if not entry.market_available:
            continue
        if entry.cape_value is None or not entry.cape_available:
            continue
        cape_available.append(entry.cohort_date)
        regime = classify_cape_binary(entry.cape_value)
        if regime is CapeBinary.HIGH:
            high.append(entry.cohort_date)
        else:
            low.append(entry.cohort_date)
    return Part20CohortPopulations(
        all_dates=all_dates,
        cape_available_dates=tuple(cape_available),
        high_dates=tuple(high),
        low_dates=tuple(low),
    )


@dataclass(frozen=True, slots=True)
class Part20PlanBundle:
    """One materialized multi-strategy plan ready for execution.

    ``strategies`` is parallel to ``plan.units`` (one strategy identity
    per unit, strategy-major order).  ``cohorts`` and ``param_configs``
    feed ``BuiltStudy`` (unique cohorts; one parameter config per unit).
    """

    plan: ResearchPlan
    param_configs: tuple[ParameterConfiguration, ...]
    cohorts: tuple[CohortSpecification, ...]
    strategies: tuple[Part20Strategy, ...]


@dataclass(slots=True)
class Part20RunStats:
    """Genuine-execution accounting for the audit run."""

    executions: int = 0
    units_executed: int = 0
    reused_search_cells: int = 0


def choose_execution_strategy(
    unit_count: int,
    *,
    all_static: bool,
    all_glidepath_numba: bool = False,
) -> ExecutionStrategy:
    """Select the execution strategy for one audit batch.

    All-static batches (ConstantAllocationPolicy + FixedRealWithdrawalPolicy)
    use AUTO so the execution layer picks the fastest validated backend
    (Numba closed form when available).

    All-glidepath batches that are Numba-eligible use AUTO so the execution
    layer picks the Numba backend (which runs sequentially).

    Other mixed/glidepath batches use PARALLEL at
    ``PART20_PARALLEL_UNIT_THRESHOLD`` units; smaller mixed batches use AUTO.
    """
    if all_static or all_glidepath_numba:
        return ExecutionStrategy.AUTO
    if unit_count >= PART20_PARALLEL_UNIT_THRESHOLD:
        return ExecutionStrategy.PARALLEL
    return ExecutionStrategy.AUTO


def extract_successes(results: tuple[SimulationResult, ...]) -> tuple[bool, ...]:
    """Map simulation results to success flags."""
    flags: list[bool] = []
    for r in results:
        stats = r.statistics
        flags.append(bool(stats.success) if stats is not None else False)
    return tuple(flags)


@dataclass
class Part20ExecutionContext:
    """Cached planning/execution context for Part 20 audit experiments.

    Holds the immutable manifest/trajectory plus per-cohort dataset,
    portfolio, and policy caches so bisection steps rebuild only the
    parameter configurations and withdrawal policies, not market slices.
    """

    manifest: CohortManifest
    trajectory: Dataset
    initial_wealth: Money
    populations: Part20CohortPopulations
    stats: Part20RunStats = field(default_factory=Part20RunStats)
    _max_horizon: dict[str, int] = field(default_factory=dict)
    _cohort_cache: dict[str, CohortSpecification] = field(default_factory=dict)
    _dataset_cache: dict[tuple[str, int], Dataset] = field(default_factory=dict)
    _portfolio_cache: dict[tuple[str, int], Portfolio] = field(default_factory=dict)
    _policy_cache: dict[str, AllocationPolicy] = field(default_factory=dict)
    # Persistent glidepath growth-factor cache shared across bisection steps.
    # Key: GlidepathGFKey, Value: NDArray of growth factors.
    glidepath_gf_cache: dict[GlidepathGFKey, NDArray[np.float64]] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        manifest_path: Path,
        trajectory: Dataset,
        initial_wealth: Money = PART20_INITIAL_WEALTH,
    ) -> Part20ExecutionContext:
        manifest = load_part20_manifest(manifest_path)
        populations = build_cohort_populations(manifest)
        max_horizon = {
            e.cohort_date: e.max_horizon_months
            for e in manifest.cohorts
            if e.market_available
        }
        return cls(
            manifest=manifest,
            trajectory=trajectory,
            initial_wealth=initial_wealth,
            populations=populations,
            _max_horizon=max_horizon,
        )

    # -- horizon clamping --------------------------------------------------

    def effective_horizon(self, cohort_date: str, requested_months: int) -> int:
        """Clamp *requested_months* to the manifest max for *cohort_date*.

        Mirrors Part 3's ``cohort_aware_horizon_resolver``:
        ``min(requested, cohort_max_horizon)``.
        """
        max_h = self._max_horizon.get(cohort_date)
        if max_h is None:
            raise KeyError(
                f"cohort {cohort_date!r} missing from manifest max_horizon lookup"
            )
        return min(requested_months, max_h)

    # -- caches ------------------------------------------------------------

    def cohort_spec(self, cohort_date: str) -> CohortSpecification:
        cached = self._cohort_cache.get(cohort_date)
        if cached is None:
            cached = CohortSpecification(
                start_date=date.fromisoformat(cohort_date),
                id=cohort_date,
            )
            self._cohort_cache[cohort_date] = cached
        return cached

    def dataset_for(self, cohort_date: str, horizon_months: int) -> Dataset:
        key = (cohort_date, horizon_months)
        cached = self._dataset_cache.get(key)
        if cached is None:
            cached = self.trajectory.slice(
                date.fromisoformat(cohort_date), horizon_months
            )
            self._dataset_cache[key] = cached
        return cached

    def portfolio_for(self, cohort_date: str, horizon_months: int) -> Portfolio:
        key = (cohort_date, horizon_months)
        cached = self._portfolio_cache.get(key)
        if cached is None:
            dataset = self.dataset_for(cohort_date, horizon_months)
            cached = build_initial_portfolio(self.initial_wealth, dataset)
            self._portfolio_cache[key] = cached
        return cached

    def allocation_policy(self, strategy: Part20Strategy) -> AllocationPolicy:
        cached = self._policy_cache.get(strategy.id)
        if cached is None:
            cached = strategy.build_allocation_policy()
            self._policy_cache[strategy.id] = cached
        return cached

    # -- unit construction ---------------------------------------------------

    def build_units(
        self,
        *,
        rows: Sequence[tuple[Part20Strategy, str, Decimal]],
        horizon_months: int,
        final_value_target: Decimal,
        step_label: str,
    ) -> Part20PlanBundle:
        """Build one multi-strategy plan from explicit unit rows.

        Each row is ``(strategy, cohort_date, withdrawal_rate)``.  Rows are
        ordered strategy-major by the caller.  Per-cohort horizons are
        clamped via :meth:`effective_horizon`; the ``ExperimentDefinition``
        carries the requested (longest) horizon.
        """
        if not rows:
            raise ValueError("rows must be non-empty")

        units: list[PlannedSimulationUnit] = []
        unit_strategies: list[Part20Strategy] = []
        unique_cohorts: dict[str, CohortSpecification] = {}
        first_alloc: AllocationPolicy | None = None
        first_withdrawal: FixedRealWithdrawalPolicy | None = None

        for idx, (strategy, cohort_date, rate) in enumerate(rows):
            effective = self.effective_horizon(cohort_date, horizon_months)
            cohort = self.cohort_spec(cohort_date)
            unit_dataset = self.dataset_for(cohort_date, effective)
            portfolio = self.portfolio_for(cohort_date, effective)
            alloc = self.allocation_policy(strategy)
            withdrawal = FixedRealWithdrawalPolicy(withdrawal_rate=rate)
            if first_alloc is None:
                first_alloc = alloc
                first_withdrawal = withdrawal
            pc = ParameterConfiguration(
                values={
                    "strategy_id": strategy.id,
                    "withdrawal_rate": float(rate),
                    "horizon_months": float(effective),
                    "requested_horizon_months": float(horizon_months),
                    "final_value_target": float(final_value_target),
                    "step": step_label,
                    "unit_index": float(idx),
                }
            )
            units.append(
                PlannedSimulationUnit(
                    cohort=cohort,
                    parameter_config=pc,
                    allocation_policy=alloc,
                    withdrawal_policy=withdrawal,
                    initial_portfolio=portfolio,
                    dataset=unit_dataset,
                    horizon_months=effective,
                    final_value_target=final_value_target,
                )
            )
            unit_strategies.append(strategy)
            unique_cohorts.setdefault(cohort_date, cohort)

        assert first_alloc is not None and first_withdrawal is not None
        unique = tuple(unique_cohorts.values())
        experiment_def = ExperimentDefinition(
            name=f"ERN Part 20 T2.1 {step_label}",
            description="Part 20 baseline audit (T2.1)",
            dataset=self.trajectory,
            horizon_months=horizon_months,
            initial_wealth=self.initial_wealth,
            cohorts=unique,
            allocation_policies=(first_alloc,),
            withdrawal_policies=(first_withdrawal,),
        )
        plan = ResearchPlan(
            experiment_definition=experiment_def,
            units=tuple(units),
        )
        return Part20PlanBundle(
            plan=plan,
            param_configs=tuple(u.parameter_config for u in units),
            cohorts=unique,
            strategies=tuple(unit_strategies),
        )

    # -- execution -----------------------------------------------------------

    def _sub_bundle(
        self,
        bundle: Part20PlanBundle,
        indices: Sequence[int],
    ) -> Part20PlanBundle:
        """Materialize a sub-plan for *indices* (order preserved)."""
        units = tuple(bundle.plan.units[i] for i in indices)
        strategies = tuple(bundle.strategies[i] for i in indices)
        param_configs = tuple(bundle.param_configs[i] for i in indices)
        seen: dict[str, CohortSpecification] = {}
        for unit in units:
            key = unit.cohort.start_date.isoformat()
            seen.setdefault(key, unit.cohort)
        plan = ResearchPlan(
            experiment_definition=bundle.plan.experiment_definition,
            units=units,
        )
        return Part20PlanBundle(
            plan=plan,
            param_configs=param_configs,
            cohorts=tuple(seen.values()),
            strategies=strategies,
        )

    def _execute_bundle(
        self,
        bundle: Part20PlanBundle,
        options: ExecutionOptions,
        *,
        all_static: bool,
    ) -> tuple[bool, ...]:
        """Run one homogeneous bundle through the chosen execution path.

        Large PARALLEL glidepath plans are split into
        ``PART20_PARALLEL_CHUNK_UNITS``-sized consecutive chunks so each
        ``execute_study_plan`` call stays within the host's proven-safe
        worker-pool size.  Chunks preserve unit order; results are merged
        positionally.  SEQUENTIAL (static) plans are never chunked.

        All-glidepath Numba-eligible bundles use AUTO (Numba sequential).
        Other large mixed/glidepath bundles use PARALLEL.
        """
        n_units = len(bundle.plan.units)
        # Check if all strategies in this bundle are glidepath and Numba-eligible
        has_strategies = bool(bundle.strategies)
        all_non_static = all(not s.is_static for s in bundle.strategies)
        all_glidepath = all(_is_glidepath_strategy(s) for s in bundle.strategies)
        all_glidepath_numba: bool = (
            not all_static
            and has_strategies
            and all_non_static
            and all_glidepath
        )
        strategy = choose_execution_strategy(
            n_units, all_static=all_static, all_glidepath_numba=all_glidepath_numba
        )

        if (
            strategy is ExecutionStrategy.PARALLEL
            and n_units > PART20_PARALLEL_CHUNK_UNITS
        ):
            merged: list[bool | None] = [None] * n_units
            for start in range(0, n_units, PART20_PARALLEL_CHUNK_UNITS):
                stop = min(start + PART20_PARALLEL_CHUNK_UNITS, n_units)
                chunk = self._sub_bundle(bundle, list(range(start, stop)))
                chunk_successes = self._execute_bundle_uncached(
                    chunk, options, strategy=strategy
                )
                for offset, ok in enumerate(chunk_successes):
                    merged[start + offset] = ok
            return tuple(bool(flag) for flag in merged)

        return self._execute_bundle_uncached(bundle, options, strategy=strategy)

    def _execute_bundle_uncached(
        self,
        bundle: Part20PlanBundle,
        options: ExecutionOptions,
        *,
        strategy: ExecutionStrategy,
    ) -> tuple[bool, ...]:
        """Single ``execute_study_plan`` call for *bundle*."""
        effective = replace(
            options,
            strategy=strategy,
            summary_only=True,
            glidepath_gf_cache=self.glidepath_gf_cache,
        )
        built = BuiltStudy(
            plan=bundle.plan,
            experiment_definition=bundle.plan.experiment_definition,
            cohorts=bundle.cohorts,
            param_configs=bundle.param_configs,
        )
        result: ResearchExecutionResult = execute_study_plan(built, effective)
        return extract_successes(result.results)

    def execute(
        self,
        bundle: Part20PlanBundle,
        options: ExecutionOptions,
    ) -> tuple[bool, ...]:
        """Execute *bundle* and return per-unit success flags in plan order.

        Mixed batches (static + glidepath strategies) are partitioned so
        static/FixedReal units regain the FastPath/Numba closed-form path
        while glidepath units use the parallel/reference path.  This is an
        execution-path optimization only: cohorts, strategies, rates,
        horizons, targets, datasets, and logical unit count are unchanged.
        Result order matches ``bundle.plan.units``.  Stats count one logical
        execution and the full logical unit count per call.
        """
        n_units = len(bundle.plan.units)
        static_idx = [i for i, s in enumerate(bundle.strategies) if s.is_static]
        glide_idx = [i for i, s in enumerate(bundle.strategies) if not s.is_static]

        if not glide_idx or not static_idx:
            # Homogeneous: single path (unchanged behaviour).
            all_static = not glide_idx
            successes = self._execute_bundle(
                bundle, options, all_static=all_static
            )
            self.stats.executions += 1
            self.stats.units_executed += n_units
            return successes

        # Mixed: partition, execute each subset, merge by original index.
        merged: list[bool | None] = [None] * n_units
        for indices, all_static in (
            (static_idx, True),
            (glide_idx, False),
        ):
            sub = self._sub_bundle(bundle, indices)
            sub_successes = self._execute_bundle(
                sub, options, all_static=all_static
            )
            for orig_i, ok in zip(indices, sub_successes, strict=True):
                merged[orig_i] = ok

        self.stats.executions += 1
        self.stats.units_executed += n_units
        return tuple(bool(flag) for flag in merged)
