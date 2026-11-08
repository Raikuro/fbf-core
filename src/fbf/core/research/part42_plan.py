"""Part 42 study plan builder.

Extends the OMY study plan builder with the accumulation phase. Supplemental
cash flows are not part of the optimized execution model.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from fbf.core.datasets import load_canonical_dataset
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import Portfolio
from fbf.core.domain.policies.concrete import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from fbf.core.execution.errors import UnsupportedConfigurationError
from fbf.core.study.builder import (
    BuiltStudy,
    StudyConfiguration,
    build_initial_portfolio,
)
from fbf.core.study.internal.accumulation import run_accumulation_phase
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.omy_timeline import resolve_omy_timeline
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan


def build_part42_study_plan(
    experiment_id: str,
    base_config: StudyConfiguration,
    data_dir: str,
    omy_config: Any,  # Part42ExperimentConfig
    ss_config: dict[str, Any] | None = None,
    cohorts: tuple[CohortSpecification, ...] | None = None,
) -> BuiltStudy:
    """Build a Part 42 study plan with OMY accumulation.

    This extends build_omy_study_plan to:
    1. Handle 12- and 24-month OMY (G_2yr experiment)
    2. Use original pre-OMY wealth as the fixed-real withdrawal base

    If `cohorts` is provided, uses those specific cohorts instead of generating
    all cohorts from the dataset. This is used by the bisection evaluate function
    to run only specific cohort/rate pairs.
    """
    from fbf.core.study.builder import (
        _make_policy_resolver,
        _make_target_resolver,
    )

    if ss_config is not None or getattr(omy_config, "social_security", False):
        raise UnsupportedConfigurationError(
            "Part 42 Social Security configuration is unsupported in Phase 1"
        )

    if len(base_config.horizon_years) != 1:
        raise ValueError(
            "Part 42 requires exactly one configured horizon year, got "
            f"{base_config.horizon_years!r}"
        )

    equity_asset = AssetClass(id="equity", name="", description="")
    bond_asset = AssetClass(id="bond", name="", description="")

    dataset = load_canonical_dataset(Path(data_dir))

    horizon_years = base_config.horizon_years[0]
    omy_months = (
        omy_config.omy_duration_months
        if hasattr(omy_config, "omy_duration_months")
        else 12
    )
    if omy_months < 1:
        raise ValueError("Part 42 OMY duration must be positive")
    timeline = resolve_omy_timeline(
        horizon_years=horizon_years,
        omy_months=omy_months,
    )

    if cohorts is None:
        cohorts = build_cohort_specs(dataset, timeline.total_snapshots)
    if not cohorts:
        raise ValueError(
            f"Dataset too small for {horizon_years}-year OMY horizon"
        )

    param_configs = _build_unified_parameter_configs(base_config)
    original_wealth = Money(Decimal("2000000"), Currency.EUR)

    # Accumulation: once per cohort, cached by start_date.
    accumulation_cache: dict[date, Portfolio] = {}
    retirement_start_by_cohort: dict[date, date] = {}

    target_weights = {equity_asset: Decimal("0.75"), bond_asset: Decimal("0.25")}

    for cohort in cohorts:
        start = cohort.start_date
        if start not in accumulation_cache:
            acc_dataset = dataset.slice(start, timeline.accumulation_snapshots)
            if len(acc_dataset) != timeline.accumulation_snapshots:
                raise ValueError(
                    "Dataset is too small for Part 42 accumulation: "
                    f"cohort={start.isoformat()}, "
                    f"required={timeline.accumulation_snapshots}, "
                    f"got={len(acc_dataset)}"
                )
            cohort_initial_portfolio = build_initial_portfolio(
                original_wealth, acc_dataset
            )
            result = run_accumulation_phase(
                initial_portfolio=cohort_initial_portfolio,
                contribution=(
                    Money(omy_config.omy_contribution.amount, Currency.EUR)
                    if omy_config.omy
                    else Money(Decimal("0"), Currency.EUR)
                ),
                target_weights=target_weights,
                dataset=acc_dataset,
                equity_asset=equity_asset,
                bond_asset=bond_asset,
                months=timeline.accumulation_transitions,
            )
            accumulation_cache[start] = result.final_portfolio
            retirement_start_by_cohort[start] = acc_dataset.snapshots[-1].date

    retirement_horizon_months = timeline.retirement_snapshots

    representative_allocation = ConstantAllocationPolicy(equity_allocation=Decimal("0.75"))
    representative_withdrawal = FixedRealWithdrawalPolicy(withdrawal_rate=Decimal("0.04"))

    experiment_def = ExperimentDefinition(
        name=base_config.name,
        description=base_config.description or base_config.name,
        dataset=dataset,
        horizon_months=retirement_horizon_months,
        initial_wealth=original_wealth,
        cohorts=cohorts,
        allocation_policies=(representative_allocation,),
        withdrawal_policies=(representative_withdrawal,),
    )

    dataset_cache: dict[tuple[date, int], Dataset] = {}
    units: list[PlannedSimulationUnit] = []
    for cohort in cohorts:
        acc_portfolio = accumulation_cache[cohort.start_date]
        retirement_start = retirement_start_by_cohort[cohort.start_date]
        for param_config in param_configs:
            horizon_months = retirement_horizon_months
            alloc_policy, withdrawal_policy = _make_policy_resolver(base_config)(param_config)
            final_value_target = _make_target_resolver(base_config)(param_config)
            cache_key = (retirement_start, horizon_months)
            if cache_key not in dataset_cache:
                retirement_dataset = dataset.slice(
                    retirement_start, horizon_months
                )
                if len(retirement_dataset) != horizon_months:
                    raise ValueError(
                        "Dataset is too small for Part 42 retirement: "
                        f"cohort={cohort.start_date.isoformat()}, "
                        f"required={horizon_months}, "
                        f"got={len(retirement_dataset)}"
                    )
                dataset_cache[cache_key] = retirement_dataset
            units.append(
                PlannedSimulationUnit(
                    cohort=cohort,
                    parameter_config=param_config,
                    allocation_policy=alloc_policy,
                    withdrawal_policy=withdrawal_policy,
                    initial_portfolio=acc_portfolio,
                    dataset=dataset_cache[cache_key],
                    horizon_months=horizon_months,
                    final_value_target=final_value_target,
                    withdrawal_base=original_wealth,
                )
            )

    plan = ResearchPlan(experiment_definition=experiment_def, units=tuple(units))
    return BuiltStudy(
        plan=plan,
        experiment_definition=experiment_def,
        cohorts=cohorts,
        param_configs=param_configs,
    )


def build_cohort_specs(
    dataset: Dataset, min_horizon_months: int
) -> tuple[CohortSpecification, ...]:
    """Build cohort specifications from dataset."""
    from fbf.core.study.internal.cohort.generator import CohortGenerator
    return CohortGenerator.generate_rolling_monthly(dataset, min_horizon_months)


def _build_unified_parameter_configs(
    config: StudyConfiguration,
) -> tuple[ParameterConfiguration, ...]:
    """Build parameter configurations from study configuration."""
    from fbf.core.study.internal.parameter.axis import ParameterAxis
    from fbf.core.study.internal.parameter.engine import ParameterSweepEngine

    axes: list[ParameterAxis] = []

    if config.allocation_policy_values:
        axes.append(ParameterAxis(
            name="equity_allocation",
            values=tuple(float(v) for v in config.allocation_policy_values),
        ))
    if config.withdrawal_policy_values:
        axes.append(ParameterAxis(
            name="withdrawal_rate",
            values=tuple(float(v) for v in config.withdrawal_policy_values),
        ))
    if config.horizon_years:
        axes.append(ParameterAxis(
            name="horizon_years",
            values=tuple(int(v) for v in config.horizon_years),
        ))
    if config.final_value_target_values:
        axes.append(ParameterAxis(
            name="final_value_target",
            values=tuple(float(v) for v in config.final_value_target_values),
        ))

    return ParameterSweepEngine.cartesian_product(axes)
