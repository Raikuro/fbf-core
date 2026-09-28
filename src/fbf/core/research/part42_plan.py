"""Part 42 study plan builder with Social Security support.

Extends the OMY study plan builder to wire Social Security cash flows
and SupplementalCashFlowStep into the execution pipeline.
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
from fbf.core.execution.pipeline.default_pipeline import create_default_pipeline
from fbf.core.execution.pipeline.pipeline import SimulationPipeline
from fbf.core.execution.pipeline.steps.supplemental_cash_flow_step import SupplementalCashFlowStep
from fbf.core.study.builder import (
    BuiltStudy,
    StudyConfiguration,
    build_initial_portfolio,
)
from fbf.core.study.internal.accumulation import run_accumulation_phase
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
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
    """Build a Part 42 study plan with OMY accumulation and Social Security.

    This extends build_omy_study_plan to:
    1. Handle 24-month OMY (G_2yr experiment)
    2. Wire Social Security cash flow via SupplementalCashFlowStep
    3. Use the correct withdrawal policy with initial_wealth = $2M pre-OMY

    If `cohorts` is provided, uses those specific cohorts instead of generating
    all cohorts from the dataset. This is used by the bisection evaluate function
    to run only specific cohort/rate pairs.
    """
    from fbf.core.study.builder import (
        _make_policy_resolver,
        _make_target_resolver,
    )

    equity_asset = AssetClass(id="equity", name="", description="")
    bond_asset = AssetClass(id="bond", name="", description="")

    dataset = load_canonical_dataset(Path(data_dir))

    retirement_horizon_years = base_config.horizon_years[0]
    omy_months = (
        omy_config.omy_duration_months
        if hasattr(omy_config, 'omy_duration_months')
        else 12
    )
    total_horizon_months = omy_months + retirement_horizon_years * 12 + 1

    if cohorts is None:
        cohorts = build_cohort_specs(dataset, total_horizon_months)
    if not cohorts:
        raise ValueError(f"Dataset too small for {retirement_horizon_years + 1}-year OMY horizon")

    param_configs = _build_unified_parameter_configs(base_config)

    # Determine SS start period (period_index when SS begins)
    # SS starts at year 31 of retirement = 360 months into retirement
    ss_start_period = omy_months + 360  # 0-indexed period_index
    ss_active = omy_config.social_security if hasattr(omy_config, 'social_security') else False
    ss_amount = omy_config.ss_amount if hasattr(omy_config, 'ss_amount') else Decimal("3000")

    # Accumulation: once per cohort, cached by start_date
    accumulation_cache: dict[date, Portfolio] = {}

    target_weights = {equity_asset: Decimal("0.75"), bond_asset: Decimal("0.25")}
    initial_portfolio = build_initial_portfolio(Money(Decimal("2000000"), Currency.EUR), dataset)

    for cohort in cohorts:
        start = cohort.start_date
        if start not in accumulation_cache:
            acc_dataset = dataset.slice(start, omy_months + 1)
            result = run_accumulation_phase(
                initial_portfolio=initial_portfolio,
                contribution=(
                    Money(omy_config.omy_contribution.amount, Currency.EUR)
                    if omy_config.omy
                    else Money(Decimal("0"), Currency.EUR)
                ),
                target_weights=target_weights,
                dataset=acc_dataset,
                equity_asset=equity_asset,
                bond_asset=bond_asset,
                months=omy_months,
            )
            accumulation_cache[start] = result.final_portfolio

    # Build retirement plan using accumulated portfolios
    retirement_horizon_months = retirement_horizon_years * 12 + 1

    representative_allocation = ConstantAllocationPolicy(equity_allocation=Decimal("0.75"))
    representative_withdrawal = FixedRealWithdrawalPolicy(withdrawal_rate=Decimal("0.04"))

    experiment_def = ExperimentDefinition(
        name=base_config.name,
        description=base_config.description or base_config.name,
        dataset=dataset,
        horizon_months=retirement_horizon_months,
        initial_wealth=Money(
            Decimal("2000000"), Currency.EUR
        ),  # Pre-OMY wealth for withdrawal calculation
        cohorts=cohorts,
        allocation_policies=(representative_allocation,),
        withdrawal_policies=(representative_withdrawal,),
    )

    # Create pipeline with SupplementalCashFlowStep for SS
    create_part42_pipeline(
        ss_active=ss_active, ss_amount=ss_amount, ss_start_period=ss_start_period
    )

    dataset_cache: dict[tuple[date, int], Dataset] = {}
    units: list[PlannedSimulationUnit] = []
    for cohort in cohorts:
        acc_portfolio = accumulation_cache[cohort.start_date]
        for param_config in param_configs:
            horizon_months = retirement_horizon_months
            alloc_policy, withdrawal_policy = _make_policy_resolver(base_config)(param_config)
            final_value_target = _make_target_resolver(base_config)(param_config)
            cache_key = (cohort.start_date, horizon_months)
            if cache_key not in dataset_cache:
                dataset_cache[cache_key] = dataset.slice(
                    cohort.start_date, horizon_months
                )
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
                )
            )

    plan = ResearchPlan(experiment_definition=experiment_def, units=tuple(units))
    return BuiltStudy(
        plan=plan,
        experiment_definition=experiment_def,
        cohorts=cohorts,
        param_configs=param_configs,
    )


def create_part42_pipeline(
    ss_active: bool = False,
    ss_amount: Decimal = Decimal("3000"),
    ss_start_period: int = 360,
) -> SimulationPipeline:
    """Create a pipeline with SupplementalCashFlowStep for Part 42.

    The default pipeline already includes a SupplementalCashFlowStep (inactive by default).
    This function configures the existing step with Part 42-specific parameters.
    """

    default = create_default_pipeline()
    steps = list(default.steps)

    # Find and configure the existing SupplementalCashFlowStep
    for step in steps:
        if isinstance(step, SupplementalCashFlowStep):
            # Replace with configured step
            configured_step = SupplementalCashFlowStep(
                ss_amount=ss_amount,
                ss_start_period=ss_start_period,
                ss_active=ss_active,
            )
            idx = steps.index(step)
            steps[idx] = configured_step
            break

    return SimulationPipeline(steps=steps)


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
