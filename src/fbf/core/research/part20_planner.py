"""Part 20 research planner — cohort populations and plan materialization.

Consumes the canonical Part 3 cohort manifest (shared ERN retirement-start
universe) and the canonical trajectory to build ``ResearchPlan`` units for
the Part 20 baseline audit.

CAPE conditioning is applied at the research boundary: populations are
selected from manifest metadata before units are built.  No CAPE data
enters the engine.  Part 20 uses the prior month's Shiller CAPE
(``CAPE_{t-1} > 20``), matching the workbook's one-month-lag convention.

Per-cohort horizons are clamped to the manifest ``max_horizon_months``,
which counts *return months*.  Because the first return of a cohort is
the cohort month itself, each sliced dataset starts at the prior month's
snapshot and therefore contains ``effective_return_months + 1`` snapshots
(the base snapshot plus one snapshot per return).  This mirrors the
workbook, where the final cohort (2015-12, 720 returns) needs the
2015-11 base snapshot.

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
    iter_execute_study_plan,
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
    "extract_successes",
    "load_part20_manifest",
    "PART20_EXPENSE_RATIO",
    "PART20_INITIAL_WEALTH",
]

PART20_INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)

# Workbook ``Parameters & Main Results!B32`` (0.05% annual, applied monthly).
PART20_EXPENSE_RATIO = Decimal("0.0005")


def _previous_month(value: date) -> date:
    """Return the first day of the month preceding *value*."""
    if value.month == 1:
        return date(value.year - 1, 12, 1)
    return date(value.year, value.month - 1, 1)


def load_part20_manifest(path: Path) -> CohortManifest:
    """Load the canonical cohort manifest used by the Part 20 audit."""
    return load_manifest(path)


@dataclass(frozen=True, slots=True)
class Part20CohortPopulations:
    """CAPE-conditioned cohort populations for Part 20.

    Populations are cohort start-date strings (ISO).  Cohorts lacking a
    prior-month CAPE observation are excluded from both binary regimes.
    """

    all_dates: tuple[str, ...]
    cape_available_dates: tuple[str, ...]
    high_dates: tuple[str, ...]  # prior-month CAPE > 20
    low_dates: tuple[str, ...]  # prior-month CAPE <= 20

    @property
    def excluded_no_cape(self) -> int:
        return len(self.all_dates) - len(self.cape_available_dates)


def build_cohort_populations(manifest: CohortManifest) -> Part20CohortPopulations:
    """Derive Part 20 cohort populations from manifest metadata.

    Filtering rules (frozen audit methodology):
    - market-available cohorts form the executable universe (1,739);
    - CAPE conditioning uses the prior month's CAPE value
      (``CAPE_{t-1}``), matching the workbook's one-month lag;
    - cohorts without prior-month CAPE are excluded from both panels;
    - ``classify_cape_binary`` implements CAPE > 20 vs CAPE <= 20.

    The earliest cohort has no prior cohort in the manifest universe, so
    its own CAPE value is used as the documented boundary fallback.  This
    does not affect its LOW classification, but keeps the universe intact.
    """
    all_dates = tuple(
        e.cohort_date for e in manifest.cohorts if e.market_available
    )
    by_date = {
        date.fromisoformat(e.cohort_date): e
        for e in manifest.cohorts
        if e.market_available
    }
    first_date = min(by_date) if by_date else None
    high: list[str] = []
    low: list[str] = []
    cape_available: list[str] = []
    for entry in manifest.cohorts:
        if not entry.market_available:
            continue
        cohort_date = date.fromisoformat(entry.cohort_date)
        prior = by_date.get(_previous_month(cohort_date))
        if prior is None and cohort_date == first_date:
            prior = entry
        if (
            prior is None
            or prior.cape_value is None
            or not prior.cape_available
        ):
            continue
        cape_available.append(entry.cohort_date)
        regime = classify_cape_binary(prior.cape_value)
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
    expense_ratio: Decimal = PART20_EXPENSE_RATIO
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
        """Clamp a requested snapshot count to the cohort's return capacity.

        ``requested_months`` is the number of snapshots in the requested
        horizon (``horizon_years * 12 + 1``).  The manifest limit counts
        return months, so the clamp operates on ``requested_months - 1``.
        The returned value is still a snapshot count and therefore includes
        the base snapshot.
        """
        if requested_months < 1:
            raise ValueError("requested_months must be positive")
        max_returns = self._max_horizon.get(cohort_date)
        if max_returns is None:
            raise KeyError(
                f"cohort {cohort_date!r} missing from manifest max_horizon lookup"
            )
        return min(requested_months - 1, max_returns) + 1

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
        """Return the cohort slice whose first snapshot is the prior month.

        ``horizon_months`` counts snapshots, including the base snapshot.
        The cohort month's return therefore uses the transition from the
        base snapshot to the first cohort-month snapshot, matching the
        workbook's return indexing.
        """
        key = (cohort_date, horizon_months)
        cached = self._dataset_cache.get(key)
        if cached is None:
            cohort = date.fromisoformat(cohort_date)
            start_idx: int | None = None
            for idx, snapshot in enumerate(self.trajectory.snapshots):
                if snapshot.date == cohort:
                    start_idx = idx
                    break
            if start_idx is None:
                raise ValueError(
                    f"cohort {cohort_date!r} not found in trajectory"
                )
            if start_idx == 0:
                raise ValueError(
                    f"cohort {cohort_date!r} has no prior-month base snapshot"
                )
            base_date = self.trajectory.snapshots[start_idx - 1].date
            cached = self.trajectory.slice(base_date, horizon_months)
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
        carries the requested (longest) horizon.  Every unit receives the
        workbook annual expense ratio exactly once.
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
                    expense_ratio=self.expense_ratio,
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

    def _execute_bundle(
        self,
        bundle: Part20PlanBundle,
        options: ExecutionOptions,
    ) -> tuple[bool, ...]:
        """Execute one bundle through the Numba path in bounded slices."""
        effective = replace(
            options,
            strategy=ExecutionStrategy.AUTO,
            summary_only=True,
            glidepath_gf_cache=self.glidepath_gf_cache,
        )
        built = BuiltStudy(
            plan=bundle.plan,
            experiment_definition=bundle.plan.experiment_definition,
            cohorts=bundle.cohorts,
            param_configs=bundle.param_configs,
        )
        successes: list[bool] = []
        for chunk in iter_execute_study_plan(built, effective):
            if chunk.start_index != len(successes):
                raise RuntimeError(
                    "streamed execution slices are not contiguous in plan order"
                )
            successes.extend(extract_successes(chunk.result.results))
            del chunk
        return tuple(successes)

    def execute(
        self,
        bundle: Part20PlanBundle,
        options: ExecutionOptions,
    ) -> tuple[bool, ...]:
        """Execute *bundle* and return per-unit success flags in plan order.

        Every unit is executed through the Numba path, which may mix generic
        policy families in one plan.  The caller's strategy is overridden with
        AUTO because production parallel execution is unsupported.

        Result order matches ``bundle.plan.units``.  Stats count one logical
        execution and the full logical unit count per call.
        """
        successes = self._execute_bundle(bundle, options)
        self.stats.executions += 1
        self.stats.units_executed += len(bundle.plan.units)
        return successes
