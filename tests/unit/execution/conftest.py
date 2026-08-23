"""Shared test fixtures for execution strategy tests."""

from __future__ import annotations

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
from fbf.core.study.builder import build_initial_portfolio
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan

EQ = AssetClass(id="equity", name="", description="")
BD = AssetClass(id="bond", name="", description="")


def make_dataset(n_months: int) -> Dataset:
    """Create a deterministic synthetic dataset with equity and bond asset classes."""
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
        pe *= Decimal("1.006")
        pb *= Decimal("1.002")
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return Dataset(snapshots=snapshots, frequency="monthly", version="1.0")


def make_context(
    dataset: Dataset,
    horizon: int,
    w: float = 0.5,
    r: float = 0.04,
    start_year: int = 1900,
    start_month: int = 1,
) -> SimulationContext:
    """Create a SimulationContext for testing."""
    start = date(start_year, start_month, 1)
    portfolio = build_initial_portfolio(Money(Decimal("1000000"), Currency.EUR))
    return SimulationContext(
        experiment_name="test",
        cohort=str(start),
        start_date=start,
        horizon_months=horizon,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        initial_portfolio=portfolio,
        dataset=dataset.slice(start, horizon),
        allocation_policy=ConstantAllocationPolicy(Decimal(str(w))),
        withdrawal_policy=FixedRealWithdrawalPolicy(Decimal(str(r))),
    )


def make_engine_def(contexts: list[SimulationContext]) -> EngineExperimentDefinition:
    """Create an EngineExperimentDefinition from a list of contexts."""
    return EngineExperimentDefinition(
        name="test",
        description="test",
        simulation_contexts=tuple(contexts),
    )


def make_plan(
    cohorts: int = 1,
    horizons: list[int] | None = None,
    weights: list[float] | None = None,
    rates: list[float] | None = None,
) -> ResearchPlan:
    """Create a ResearchPlan for testing."""
    if horizons is None:
        horizons = [720]
    if weights is None:
        weights = [0.5]
    if rates is None:
        rates = [0.04]

    dataset = make_dataset(max(horizons) + 1)
    longest_horizon = max(horizons)

    cohort_specs = tuple(
        CohortSpecification(start_date=date(1900, 1 + i, 1))
        for i in range(cohorts)
    )

    experiment = ExperimentDefinition(
        name="test",
        description="test",
        dataset=dataset,
        horizon_months=longest_horizon,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        cohorts=cohort_specs,
        allocation_policies=(ConstantAllocationPolicy(Decimal(str(weights[0]))),),
        withdrawal_policies=(FixedRealWithdrawalPolicy(Decimal(str(rates[0]))),),
    )

    units = []
    for cohort in cohort_specs:
        for w in weights:
            for r in rates:
                for h in horizons:
                    param_config = ParameterConfiguration({
                        "equity_allocation": w,
                        "withdrawal_rate": r,
                        "horizon_years": h // 12,
                    })
                    unit = PlannedSimulationUnit(
                        cohort=cohort,
                        parameter_config=param_config,
                        allocation_policy=ConstantAllocationPolicy(Decimal(str(w))),
                        withdrawal_policy=FixedRealWithdrawalPolicy(Decimal(str(r))),
                        initial_portfolio=build_initial_portfolio(
                            Money(Decimal("1000000"), Currency.EUR)
                        ),
                        dataset=dataset.slice(cohort.start_date, h),
                    )
                    units.append(unit)

    return ResearchPlan(experiment_definition=experiment, units=tuple(units))
