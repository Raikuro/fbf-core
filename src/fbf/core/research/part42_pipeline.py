"""Part 42 research pipeline — One More Year Syndrome replication.

Implements Experiments A–G from the Part 42 audit specification.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import Portfolio
from fbf.core.execution import ExecutionOptions, execute_study_plan
from fbf.core.research.part3_planner import CohortManifest, load_manifest
from fbf.core.research.part20_aggregation import percentile_swrs
from fbf.core.research.part20_pipeline import (
    BisectionCandidate,
    BisectionEvaluate,
    SearchCache,
    bisect_per_pair,
)
from fbf.core.research.part42_plan import build_part42_study_plan

DEFAULT_DATA_DIR = os.path.join("data", "ern")

__all__ = [
    "PART42_INITIAL_WEALTH",
    "PART42_EQUITY_WEIGHT",
    "PART42_BOND_WEIGHT",
    "PART42_OMY_CONTRIBUTION",
    "PART42_SS_AMOUNT",
    "PART42_SS_START_YEAR",
    "PART42_FV_30Y",
    "PART42_FV_50Y",
    "PART42_SWR_DOMAIN_MIN",
    "PART42_SWR_DOMAIN_MAX",
    "PART42_SWR_PRECISION",
    "Part42ExperimentConfig",
    "Part42FailsafeResult",
    "Part42FixedSWRResult",
    "Part42ExecutionContext",
    "build_part42_context",
    "run_failsafe_search",
    "run_fixed_swr",
    "get_experiment_configs",
]

# Part 42 constants
PART42_INITIAL_WEALTH = Money(Decimal("2000000"), Currency.EUR)
PART42_EQUITY_WEIGHT = Decimal("0.75")
PART42_BOND_WEIGHT = Decimal("0.25")
PART42_OMY_CONTRIBUTION = Money(Decimal("5000"), Currency.EUR)
PART42_SS_AMOUNT = Money(Decimal("3000"), Currency.EUR)
PART42_SS_START_YEAR = 31
PART42_FV_30Y = Decimal("0.25")
PART42_FV_50Y = Decimal("0.0")

# Same precision as Part 20: finer than half of the last displayed digit
PART42_SWR_DOMAIN_MIN = Decimal("0.01")
PART42_SWR_DOMAIN_MAX = Decimal("0.08")
PART42_SWR_PRECISION = Decimal("0.00001")


@dataclass(frozen=True, slots=True)
class Part42ExperimentConfig:
    """Configuration for one Part 42 experiment scenario."""
    id: str
    name: str
    horizon_years: int
    omy: bool
    omy_contribution: Money
    omy_duration_months: int = 12
    social_security: bool = False
    ss_start_year: int = PART42_SS_START_YEAR
    ss_amount: Money = PART42_SS_AMOUNT
    fv_target: Decimal = PART42_FV_30Y
    fixed_swr: Decimal | None = None  # If set, run fixed-SWR instead of failsafe search

    def to_omy_config(self) -> Any:
        """Return self for use by plan builder."""
        return self


@dataclass(frozen=True, slots=True)
class Part42FailsafeResult:
    """Failsafe/percentile SWR result for one Part 42 experiment."""
    experiment_id: str
    horizon_years: int
    fv_target: Decimal
    omy: bool
    omy_contribution: Money
    social_security: bool
    cohort_count: int
    per_cohort_swrs: tuple[Decimal, ...]

    @property
    def percentiles(self) -> dict[Decimal, Decimal]:
        return percentile_swrs(self.per_cohort_swrs)

    @property
    def failsafe(self) -> Decimal:
        return self.percentiles[Decimal("0")]


@dataclass(frozen=True, slots=True)
class Part42FixedSWRResult:
    """Fixed-SWR failure rate result for one Part 42 experiment."""
    experiment_id: str
    horizon_years: int
    fv_target: Decimal
    omy: bool
    omy_contribution: Money
    social_security: bool
    withdrawal_rate: Decimal
    cohort_count: int
    failures: int
    per_cohort_success: tuple[bool, ...] = field(default_factory=tuple)

    @property
    def failure_rate(self) -> Decimal:
        if self.cohort_count == 0:
            return Decimal("0")
        return Decimal(self.failures) / Decimal(self.cohort_count)


@dataclass
class Part42ExecutionContext:
    """Cached planning/execution context for Part 42 audit experiments."""

    manifest: CohortManifest
    trajectory: Dataset
    initial_wealth: Money
    populations: dict[str, list[str]] = field(default_factory=dict)
    _max_horizon: dict[str, int] = field(default_factory=dict)
    _cohort_cache: dict[str, Any] = field(default_factory=dict)
    _dataset_cache: dict[tuple[str, int], Dataset] = field(default_factory=dict)
    _portfolio_cache: dict[tuple[str, int], Portfolio] = field(default_factory=dict)
    _accumulation_cache: dict[str, Portfolio] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        manifest_path: Path,
        trajectory: Dataset,
        initial_wealth: Money = PART42_INITIAL_WEALTH,
    ) -> Part42ExecutionContext:
        manifest = load_manifest(manifest_path)
        all_dates = tuple(
            e.cohort_date for e in manifest.cohorts if e.market_available
        )
        high: list[str] = []
        low: list[str] = []
        cape_available: list[str] = []
        from fbf.core.domain.policies.cape_regime import CapeBinary, classify_cape_binary
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

        populations = {
            "ALL": list(all_dates),
            "HIGH": high,
            "LOW": low,
            "CAPE_AVAILABLE": cape_available,
        }
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

    def effective_horizon(self, cohort_date: str, requested_months: int) -> int:
        max_h = self._max_horizon.get(cohort_date)
        if max_h is None:
            raise KeyError(f"cohort {cohort_date!r} missing from manifest max_horizon lookup")
        return min(requested_months, max_h)

    def cohort_spec(self, cohort_date: str) -> Any:
        from fbf.core.study.internal.cohort.specification import CohortSpecification
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
            from fbf.core.study.builder import build_initial_portfolio
            cached = build_initial_portfolio(self.initial_wealth, dataset)
            self._portfolio_cache[key] = cached
        return cached

    def accumulation_portfolio(self, cohort_date: str, omy_config: Any) -> Portfolio:
        cached = self._accumulation_cache.get(cohort_date)
        if cached is None:
            from fbf.core.domain.model.asset import AssetClass
            from fbf.core.study.internal.accumulation import run_accumulation_phase

            equity_asset = AssetClass(id="equity", name="", description="")
            bond_asset = AssetClass(id="bond", name="", description="")

            acc_months = (
                omy_config.omy_duration_months
                if hasattr(omy_config, 'omy_duration_months')
                else 12
            )
            acc_dataset = self.trajectory.slice(
                date.fromisoformat(cohort_date), acc_months + 1
            )

            target_weights = {equity_asset: PART42_EQUITY_WEIGHT, bond_asset: PART42_BOND_WEIGHT}
            from fbf.core.study.builder import build_initial_portfolio
            initial_portfolio = build_initial_portfolio(self.initial_wealth, acc_dataset)

            result = run_accumulation_phase(
                initial_portfolio=initial_portfolio,
                contribution=(
                    omy_config.omy_contribution
                    if omy_config.omy
                    else Money(Decimal("0"), Currency.EUR)
                ),
                target_weights=target_weights,
                dataset=acc_dataset,
                equity_asset=equity_asset,
                bond_asset=bond_asset,
                months=acc_months,
            )
            cached = result.final_portfolio
            self._accumulation_cache[cohort_date] = cached
        return cached


def build_part42_context(
    manifest_path: Path,
    trajectory: Dataset,
    initial_wealth: Money = PART42_INITIAL_WEALTH,
) -> Part42ExecutionContext:
    return Part42ExecutionContext.create(manifest_path, trajectory, initial_wealth)


def _build_omy_evaluate(
    ctx: Part42ExecutionContext,
    experiment: Part42ExperimentConfig,
    cohort_dates: Sequence[str],
    options: ExecutionOptions,
) -> BisectionEvaluate:
    """Build an evaluate function for batched OMY bisection."""
    n_cohorts = len(cohort_dates)

    def evaluate(candidates: Sequence[BisectionCandidate]) -> Sequence[bool]:
        from collections import defaultdict
        rate_to_candidates: dict[Decimal, list[tuple[int, BisectionCandidate]]] = defaultdict(list)
        for flat_idx, (pair_idx, mid) in enumerate(candidates):
            rate_to_candidates[mid].append((flat_idx, (pair_idx, mid)))

        results: list[bool | None] = [None] * len(candidates)

        for rate, cand_list in rate_to_candidates.items():
            rows = []
            flat_indices = []
            for flat_idx, (pair_idx, _mid) in cand_list:
                cohort_idx = pair_idx
                if cohort_idx >= n_cohorts:
                    raise ValueError(f"cohort_idx {cohort_idx} >= n_cohorts {n_cohorts}")
                cohort_date = cohort_dates[cohort_idx]
                rows.append((cohort_date, rate))
                flat_indices.append(flat_idx)

            # Build and execute plan for this rate
            from fbf.core.study.builder import StudyConfiguration

            base_config = StudyConfiguration(
                name=f"ERN Part 42 — {experiment.name}",
                description=f"Part 42 {experiment.name} replication",
                version="1.0",
                allocation_policy_type="ConstantAllocationPolicy",
                allocation_policy_values=(PART42_EQUITY_WEIGHT,),
                withdrawal_policy_type="FixedRealWithdrawalPolicy",
                withdrawal_policy_values=(rate,),
                horizon_years=(experiment.horizon_years,),
                final_value_target_values=(experiment.fv_target,),
                omy_contribution_amount=(
                    experiment.omy_contribution.amount if experiment.omy else None
                ),
                omy_equity_weight=PART42_EQUITY_WEIGHT if experiment.omy else None,
                omy_bond_weight=PART42_BOND_WEIGHT if experiment.omy else None,
                omy_original_initial_wealth=(
                    PART42_INITIAL_WEALTH.amount if experiment.omy else None
                ),
            )

            omy_config = experiment  # Part42ExperimentConfig has the needed fields

            # Build OMY study plan with SS using the Part 42 plan builder
            built = build_part42_study_plan(
                experiment_id=experiment.id,
                base_config=base_config,
                data_dir=DEFAULT_DATA_DIR,  # Default; callers should override
                # via data_dir parameter
                omy_config=omy_config,
            )

            from fbf.core.execution import execute_study_plan
            result = execute_study_plan(built, options)
            successes = []
            for r in result.experiment_result.simulation_results:
                stats = r.statistics
                successes.append(bool(stats.success) if stats is not None else False)

            for (flat_idx, _), ok in zip(cand_list, successes, strict=True):
                results[flat_idx] = ok

        return tuple(bool(r) for r in results)

    return evaluate


def run_failsafe_search(
    ctx: Part42ExecutionContext,
    experiment: Part42ExperimentConfig,
    cohort_dates: Sequence[str],
    options: ExecutionOptions,
    cache: SearchCache | None = None,
) -> Part42FailsafeResult:
    """Run failsafe SWR search for one Part 42 experiment."""
    if not cohort_dates:
        raise ValueError("cohort_dates must be non-empty")

    n_pairs = len(cohort_dates)
    evaluate = _build_omy_evaluate(ctx, experiment, cohort_dates, options)

    outcome = bisect_per_pair(
        n_pairs,
        evaluate=evaluate,
        domain_min=PART42_SWR_DOMAIN_MIN,
        domain_max=PART42_SWR_DOMAIN_MAX,
        precision=PART42_SWR_PRECISION,
    )

    per_cohort_swrs = tuple(
        b if b is not None else PART42_SWR_DOMAIN_MIN for b in outcome.bests
    )

    return Part42FailsafeResult(
        experiment_id=experiment.id,
        horizon_years=experiment.horizon_years,
        fv_target=experiment.fv_target,
        omy=experiment.omy,
        omy_contribution=experiment.omy_contribution,
        social_security=experiment.social_security,
        cohort_count=n_pairs,
        per_cohort_swrs=per_cohort_swrs,
    )


def run_fixed_swr(
    experiment: Part42ExperimentConfig,
    cohort_dates: Sequence[str],
    data_dir: str,
    options: ExecutionOptions,
) -> Part42FixedSWRResult:
    """Run fixed-SWR experiment for one Part 42 scenario."""
    if experiment.fixed_swr is None:
        raise ValueError("experiment.fixed_swr must be set for fixed-SWR run")

    from fbf.core.study.builder import (
        OmyStudyConfiguration,
        StudyConfiguration,
        build_omy_study_plan,
        build_study_plan,
    )

    base_config = StudyConfiguration(
        name=f"ERN Part 42 — {experiment.name}",
        description=f"Part 42 {experiment.name} replication",
        version="1.0",
        allocation_policy_type="ConstantAllocationPolicy",
        allocation_policy_values=(PART42_EQUITY_WEIGHT,),
        withdrawal_policy_type="FixedRealWithdrawalPolicy",
        withdrawal_policy_values=(experiment.fixed_swr,),
        horizon_years=(experiment.horizon_years,),
        final_value_target_values=(experiment.fv_target,),
        omy_contribution_amount=experiment.omy_contribution.amount if experiment.omy else None,
        omy_equity_weight=PART42_EQUITY_WEIGHT if experiment.omy else None,
        omy_bond_weight=PART42_BOND_WEIGHT if experiment.omy else None,
        omy_original_initial_wealth=PART42_INITIAL_WEALTH.amount if experiment.omy else None,
    )

    if experiment.omy:
        # OMY experiment: use OMY study plan
        omy_study_config = OmyStudyConfiguration(
            base_config=base_config,
            contribution_amount=experiment.omy_contribution,
            equity_weight=PART42_EQUITY_WEIGHT,
            bond_weight=PART42_BOND_WEIGHT,
            original_initial_wealth=PART42_INITIAL_WEALTH,
            fv_target_fraction=experiment.fv_target,
        )
        built = build_omy_study_plan(omy_study_config, data_dir)
    else:
        # Non-OMY experiment: use regular study plan
        built = build_study_plan(base_config, data_dir, PART42_INITIAL_WEALTH)

    result = execute_study_plan(built, options)

    failures = 0
    total = 0
    per_cohort_success = []
    for r in result.experiment_result.simulation_results:
        stats = r.statistics
        if stats is not None:
            total += 1
            success = stats.success
            per_cohort_success.append(success)
            if not success:
                failures += 1

    return Part42FixedSWRResult(
        experiment_id=experiment.id,
        horizon_years=experiment.horizon_years,
        fv_target=experiment.fv_target,
        omy=experiment.omy,
        omy_contribution=experiment.omy_contribution,
        social_security=experiment.social_security,
        withdrawal_rate=experiment.fixed_swr,
        cohort_count=total,
        failures=failures,
        per_cohort_success=tuple(per_cohort_success),
    )


def get_experiment_configs() -> list[Part42ExperimentConfig]:
    # Common fixed SWR for Table 01 (4% withdrawal rate)
    PART42_TABLE01_SWR = Decimal("0.04")

    return [
        Part42ExperimentConfig(
            id="A",
            name="30Y Failsafe Baseline",
            horizon_years=30,
            omy=False,
            omy_contribution=Money(Decimal("0"), Currency.EUR),
            social_security=False,
            fv_target=PART42_FV_30Y,
            fixed_swr=PART42_TABLE01_SWR,
        ),
        Part42ExperimentConfig(
            id="B",
            name="30Y OMY Delay Only",
            horizon_years=30,
            omy=True,
            omy_contribution=Money(Decimal("0"), Currency.EUR),
            social_security=False,
            fv_target=PART42_FV_30Y,
            fixed_swr=PART42_TABLE01_SWR,
        ),
        Part42ExperimentConfig(
            id="C",
            name="30Y OMY + Contributions",
            horizon_years=30,
            omy=True,
            omy_contribution=PART42_OMY_CONTRIBUTION,
            social_security=False,
            fv_target=PART42_FV_30Y,
            fixed_swr=PART42_TABLE01_SWR,
        ),
        Part42ExperimentConfig(
            id="D",
            name="50Y Failsafe Baseline",
            horizon_years=50,
            omy=False,
            omy_contribution=Money(Decimal("0"), Currency.EUR),
            social_security=False,
            fv_target=PART42_FV_50Y,
            fixed_swr=PART42_TABLE01_SWR,
        ),
        Part42ExperimentConfig(
            id="E_delay",
            name="50Y OMY Delay Only",
            horizon_years=50,
            omy=True,
            omy_contribution=Money(Decimal("0"), Currency.EUR),
            social_security=False,
            fv_target=PART42_FV_50Y,
            fixed_swr=PART42_TABLE01_SWR,
        ),
        Part42ExperimentConfig(
            id="E_contrib",
            name="50Y OMY + Contributions",
            horizon_years=50,
            omy=True,
            omy_contribution=PART42_OMY_CONTRIBUTION,
            social_security=False,
            fv_target=PART42_FV_50Y,
            fixed_swr=PART42_TABLE01_SWR,
        ),
        Part42ExperimentConfig(
            id="F_baseline",
            name="50Y + Social Security Baseline",
            horizon_years=50,
            omy=False,
            omy_contribution=Money(Decimal("0"), Currency.EUR),
            social_security=True,
            ss_start_year=PART42_SS_START_YEAR,
            ss_amount=PART42_SS_AMOUNT,
            fv_target=PART42_FV_50Y,
            fixed_swr=PART42_TABLE01_SWR,
        ),
        Part42ExperimentConfig(
            id="F_delay",
            name="50Y + Social Security OMY Delay Only",
            horizon_years=50,
            omy=True,
            omy_contribution=Money(Decimal("0"), Currency.EUR),
            social_security=True,
            ss_start_year=PART42_SS_START_YEAR,
            ss_amount=PART42_SS_AMOUNT,
            fv_target=PART42_FV_50Y,
            fixed_swr=PART42_TABLE01_SWR,
        ),
        Part42ExperimentConfig(
            id="F_contrib",
            name="50Y + Social Security OMY + Contributions",
            horizon_years=50,
            omy=True,
            omy_contribution=PART42_OMY_CONTRIBUTION,
            social_security=True,
            ss_start_year=PART42_SS_START_YEAR,
            ss_amount=PART42_SS_AMOUNT,
            fv_target=PART42_FV_50Y,
            fixed_swr=PART42_TABLE01_SWR,
        ),
        Part42ExperimentConfig(
            id="G_2yr",
            name="2-Year Delay",
            horizon_years=50,
            omy=True,
            omy_duration_months=24,
            omy_contribution=PART42_OMY_CONTRIBUTION,
            social_security=True,
            ss_start_year=PART42_SS_START_YEAR,
            ss_amount=PART42_SS_AMOUNT,
            fv_target=PART42_FV_50Y,
            fixed_swr=PART42_TABLE01_SWR,
        ),
        Part42ExperimentConfig(
            id="G",
            name="Fixed 4% Failure Rates",
            horizon_years=30,
            omy=False,
            omy_contribution=Money(Decimal("0"), Currency.EUR),
            social_security=False,
            fv_target=PART42_FV_30Y,
            fixed_swr=PART42_TABLE01_SWR,
        ),
    ]
