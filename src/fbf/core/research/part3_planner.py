"""Part 3 research planner — deterministic cohort manifest integration.

Consumes the canonical cohort manifest and market trajectory to produce
a ``ResearchPlan`` whose units respect per-cohort horizon constraints
and whose CAPE metadata is available for regime-based aggregation.

This module belongs to the Research layer.  It does not modify the
simulation engine, the generic planning primitives, or the canonical
datasets.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.money import Money
from fbf.core.study.builder import (
    build_allocation_policy,
    build_initial_portfolio,
    build_withdrawal_policy,
)
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.parameter.axis import ParameterAxis
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.internal.parameter.engine import ParameterSweepEngine
from fbf.core.study.plan import ResearchPlan

# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CohortManifestEntry:
    """A single cohort entry from the canonical manifest."""

    cohort_date: str
    market_available: bool
    cape_available: bool
    cape_value: Decimal | None
    cape_regime: str | None
    start_month_index: int
    max_horizon_months: int


@dataclass(frozen=True)
class CohortManifest:
    """The canonical Part 3 cohort manifest."""

    version: str
    description: str
    market_source: str
    cape_source: str
    fee: float
    statistics: dict[str, Any]
    cohorts: tuple[CohortManifestEntry, ...]


def load_manifest(path: Path) -> CohortManifest:
    """Load the canonical cohort manifest from a JSON file.

    The manifest is the authoritative deterministic research artifact
    defining the cohort universe, CAPE values, regimes, and horizon
    constraints.  It is loaded once and treated as immutable.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    cohorts = tuple(
        CohortManifestEntry(
            cohort_date=c["cohort_date"],
            market_available=c["market_available"],
            cape_available=c["cape_available"],
            cape_value=Decimal(str(c["cape_value"])) if c["cape_value"] is not None else None,
            cape_regime=c["cape_regime"],
            start_month_index=c["start_month_index"],
            max_horizon_months=c["max_horizon_months"],
        )
        for c in raw["cohorts"]
    )
    return CohortManifest(
        version=raw["version"],
        description=raw["description"],
        market_source=raw["market_source"],
        cape_source=raw["cape_source"],
        fee=raw["fee"],
        statistics=raw["statistics"],
        cohorts=cohorts,
    )


# ---------------------------------------------------------------------------
# CAPE metadata registry
# ---------------------------------------------------------------------------

CapeMetadata = tuple[Decimal | None, str | None]


def build_cape_registry(
    manifest: CohortManifest,
) -> Callable[[CohortSpecification], CapeMetadata]:
    """Build a deterministic CAPE lookup from the manifest.

    Returns a callable that maps a ``CohortSpecification`` to its
    ``(cape_value, cape_regime)`` pair from the manifest.  Cohorts
    not present in the manifest return ``(None, None)``.

    The registry resolves CAPE once at construction time.  Subsequent
    lookups are pure dictionary accesses — no repeated CAPE computation.
    """
    lookup: dict[str, CapeMetadata] = {}
    for entry in manifest.cohorts:
        lookup[entry.cohort_date] = (entry.cape_value, entry.cape_regime)

    def get_cape_metadata(cohort: CohortSpecification) -> CapeMetadata:
        key = cohort.start_date.isoformat()
        return lookup.get(key, (None, None))

    return get_cape_metadata


# ---------------------------------------------------------------------------
# Part 3 Research Planner
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Part3PlannerConfig:
    """Configuration for the Part 3 research planner."""

    equity_allocations: tuple[Decimal, ...]
    withdrawal_rates: tuple[Decimal, ...]
    horizon_years: tuple[int, ...]
    final_value_targets: tuple[Decimal, ...] | None
    allocation_policy_type: str
    withdrawal_policy_type: str


@dataclass(frozen=True)
class Part3PlanResult:
    """Result of Part 3 research plan materialization."""

    plan: ResearchPlan
    get_cape_metadata: Callable[[CohortSpecification], CapeMetadata]
    cohorts: tuple[CohortSpecification, ...]
    param_configs: tuple[ParameterConfiguration, ...]


def materialize_part3_plan(
    manifest: CohortManifest,
    canonical_trajectory: Dataset,
    config: Part3PlannerConfig,
    initial_wealth: Money,
) -> Part3PlanResult:
    """Build a Part 3 ResearchPlan from the canonical manifest and trajectory.

    The planner:

    1. Filters the manifest to market-available cohorts.
    2. Creates ``CohortSpecification`` objects for each eligible cohort.
    3. Generates the Cartesian parameter space.
    4. Applies per-cohort horizon constraints from the manifest.
    5. Produces a ``ResearchPlan`` via the generic ``materialize_research_plan``.
    6. Returns a CAPE metadata registry for downstream aggregation.

    No CAPE information enters the ``PlannedSimulationUnit`` or the engine.
    The engine receives only simulation-relevant state: market trajectory,
    policies, and horizon.
    """
    # Step 1: Filter to market-available cohorts
    market_cohorts = tuple(
        entry for entry in manifest.cohorts if entry.market_available
    )
    if not market_cohorts:
        raise ValueError("No market-available cohorts in manifest")

    # Step 2: Create CohortSpecification objects
    cohort_specs = tuple(
        CohortSpecification(
            start_date=date.fromisoformat(entry.cohort_date),
            id=entry.cohort_date,
        )
        for entry in market_cohorts
    )

    # Step 3: Build per-cohort max horizon lookup
    cohort_max_horizon: dict[str, int] = {
        entry.cohort_date: entry.max_horizon_months
        for entry in market_cohorts
    }

    # Step 4: Generate parameter configurations
    axes = [
        ParameterAxis(
            name="equity_allocation",
            values=tuple(float(v) for v in config.equity_allocations),
        ),
        ParameterAxis(
            name="withdrawal_rate",
            values=tuple(float(v) for v in config.withdrawal_rates),
        ),
        ParameterAxis(
            name="horizon_years",
            values=tuple(int(v) for v in config.horizon_years),
        ),
    ]
    if config.final_value_targets is not None:
        axes.append(
            ParameterAxis(
                name="final_value_target",
                values=tuple(float(v) for v in config.final_value_targets),
            )
        )
    param_configs = ParameterSweepEngine.cartesian_product(axes)

    # Step 5: Build the initial portfolio (shared across all units)
    initial_portfolio = build_initial_portfolio(initial_wealth)

    # Step 6: Build resolvers
    def horizon_resolver(param_config: ParameterConfiguration) -> int:
        return int(param_config.get("horizon_years")) * 12 + 1

    def policy_resolver(
        param_config: ParameterConfiguration,
    ) -> tuple[Any, Any]:
        alloc = build_allocation_policy(
            config.allocation_policy_type,
            Decimal(str(param_config.get("equity_allocation"))),
        )
        withdraw = build_withdrawal_policy(
            config.withdrawal_policy_type,
            Decimal(str(param_config.get("withdrawal_rate"))),
        )
        return alloc, withdraw

    def target_resolver(param_config: ParameterConfiguration) -> Decimal | None:
        raw = param_config.get("final_value_target")
        if raw is None:
            return None
        return Decimal(str(raw))

    # Step 7: Build a horizon resolver that respects per-cohort constraints.
    # For each cohort, the effective horizon is:
    #   min(requested_horizon, cohort_max_horizon)
    # This ensures cohorts with insufficient forward data are not
    # assigned an impossible horizon.
    def cohort_aware_horizon_resolver(
        param_config: ParameterConfiguration,
        cohort: CohortSpecification,
    ) -> int:
        requested = horizon_resolver(param_config)
        max_h = cohort_max_horizon.get(cohort.start_date.isoformat(), 0)
        return min(requested, max_h)

    # Step 8: Materialize the plan using per-cohorizon-aware slicing.
    # We cannot use the generic materialize_research_plan directly because
    # it applies a uniform horizon to all cohorts.  Instead, we build
    # units manually with per-cohort horizon constraints.
    dataset_cache: dict[tuple[str, int], Dataset] = {}
    units: list[Any] = []
    for cohort in cohort_specs:
        for param_config in param_configs:
            effective_horizon = cohort_aware_horizon_resolver(param_config, cohort)
            alloc_policy, withdrawal_policy = policy_resolver(param_config)
            final_value_target = (
                target_resolver(param_config)
                if config.final_value_targets is not None
                else None
            )
            cache_key = (cohort.start_date.isoformat(), effective_horizon)
            if cache_key not in dataset_cache:
                dataset_cache[cache_key] = canonical_trajectory.slice(
                    cohort.start_date, effective_horizon
                )
            from fbf.core.study.plan import PlannedSimulationUnit

            units.append(
                PlannedSimulationUnit(
                    cohort=cohort,
                    parameter_config=param_config,
                    allocation_policy=alloc_policy,
                    withdrawal_policy=withdrawal_policy,
                    initial_portfolio=initial_portfolio,
                    dataset=dataset_cache[cache_key],
                    horizon_months=effective_horizon,
                    final_value_target=final_value_target,
                )
            )

    # Build the ExperimentDefinition for the plan
    from fbf.core.study.internal.experiment.definition import ExperimentDefinition

    longest_horizon = max(config.horizon_years) * 12 + 1
    representative_alloc = build_allocation_policy(
        config.allocation_policy_type, config.equity_allocations[0]
    )
    representative_withdraw = build_withdrawal_policy(
        config.withdrawal_policy_type, config.withdrawal_rates[0]
    )
    experiment_def = ExperimentDefinition(
        name="ERN Part 3",
        description="Early Retirement Now Part 3 replication",
        dataset=canonical_trajectory,
        horizon_months=longest_horizon,
        initial_wealth=initial_wealth,
        cohorts=cohort_specs,
        allocation_policies=(representative_alloc,),
        withdrawal_policies=(representative_withdraw,),
    )

    plan = ResearchPlan(experiment_definition=experiment_def, units=tuple(units))

    # Step 9: Build CAPE metadata registry
    get_cape_metadata = build_cape_registry(manifest)

    return Part3PlanResult(
        plan=plan,
        get_cape_metadata=get_cape_metadata,
        cohorts=cohort_specs,
        param_configs=param_configs,
    )
