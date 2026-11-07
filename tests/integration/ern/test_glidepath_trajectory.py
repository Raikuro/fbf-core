"""Controlled-trajectory integration test for GlidepathAllocationPolicy.

Builds a synthetic dataset with a deliberately controlled underwater pattern,
runs it through the Part 52 Numba glidepath executor, and verifies that the allocation
path matches the independently computed expected path.

This validates:
- Pipeline step ordering (glidepath at Step 40, before market at Step 60)
- Dataset slicing (cohort gets correct slice)
- Policy receives correct period_index and market_snapshot
- Rebalancing applies the glidepath target correctly
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies import FixedRealWithdrawalPolicy
from fbf.core.domain.policies.glidepath import GlidepathAllocationPolicy
from fbf.core.execution.strategies.numba_executor import NumbaSimulationExecutor
from fbf.core.execution.strategies.parallel_executor import sequential_execute
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan

_EQUITY = AssetClass(id="equity", name="", description="")
_BOND = AssetClass(id="bond", name="", description="")

# Slope: 0.5 percentage points = 0.005 fraction per month
_SLOPE = Decimal("0.005")


def _snap(equity_price: str, is_underwater: bool, d: date) -> MarketSnapshot:
    return MarketSnapshot(
        date=d,
        index_levels={
            _EQUITY: Decimal(equity_price),
            _BOND: Decimal("50.00"),
        },
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=not is_underwater,
        is_underwater=is_underwater,
        running_ath=Decimal(equity_price) if not is_underwater else Decimal("100"),
    )


def _build_plan(mode: str, underwater_flags: list[bool]) -> tuple[Dataset, ResearchPlan]:
    """Build a single-cohort plan with the given underwater pattern."""
    base = date(2000, 1, 1)
    prices = ["80" if uw else "100" for uw in underwater_flags]
    snapshots = [
        _snap(prices[i], underwater_flags[i], date(2000 + (i // 12), (i % 12) + 1, 1))
        for i in range(len(underwater_flags))
    ]
    dataset = Dataset(snapshots=snapshots, frequency="monthly")

    policy = GlidepathAllocationPolicy(
        start_equity=Decimal("0.6"),
        end_equity=Decimal("1.0"),
        slope=_SLOPE,
        mode=mode,
    )
    withdrawal = FixedRealWithdrawalPolicy(withdrawal_rate=Decimal("0"))

    horizon_months = len(underwater_flags)
    experiment = ExperimentDefinition(
        name=f"glidepath-trajectory-{mode}",
        description=f"Controlled trajectory test for {mode} glidepath",
        dataset=dataset,
        horizon_months=horizon_months,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        cohorts=(CohortSpecification(start_date=base),),
        allocation_policies=(policy,),
        withdrawal_policies=(withdrawal,),
    )

    # Initial prices are 80 (equity) and 50 (bond); the holdings must value
    # exactly to the initial wealth so the Numba admission check can run.
    portfolio = Portfolio(holdings=(
        AssetHolding(asset_class=_EQUITY, units=Decimal("6250")),
        AssetHolding(asset_class=_BOND, units=Decimal("10000")),
    ))

    sliced = dataset.slice(base, horizon_months)
    unit = PlannedSimulationUnit(
        cohort=CohortSpecification(start_date=base),
        parameter_config=ParameterConfiguration(values={"test": 1}),
        allocation_policy=policy,
        withdrawal_policy=withdrawal,
        initial_portfolio=portfolio,
        dataset=sliced,
        horizon_months=horizon_months,
    )
    plan = ResearchPlan(experiment_definition=experiment, units=(unit,))
    return dataset, plan


def _compute_expected_equity_weights(
    underwater_flags: list[bool],
    start_equity: Decimal,
    slope: Decimal,
) -> list[Decimal]:
    """Independently compute expected equity weights for the active glidepath."""
    weights = []
    advancement = 0
    for uw in underwater_flags:
        if uw:
            advancement += 1
        raw = start_equity + slope * advancement
        weights.append(min(raw, Decimal("1")))
    return weights


def test_active_glidepath_controlled_trajectory() -> None:
    """Run active glidepath through full pipeline and verify allocation path."""
    uw = [True, False, False, True, False, False, True, False, False, True, False, False]
    _dataset, plan = _build_plan("active", uw)

    result = sequential_execute(
        plan,
        summary_only=False,
        simulation_executor=NumbaSimulationExecutor(materialize_timeline=True),
    )

    assert len(result.results) == 1
    timeline = result.results[0].timeline

    expected_weights = _compute_expected_equity_weights(
        uw, Decimal("0.6"), _SLOPE
    )
    assert len(timeline.monthly_results) == len(uw)

    # Month 0 is the pre-retirement base row.  The weight applied to the
    # return from month j-1 to month j is shown at month j.
    expected_timeline = [expected_weights[0]] + expected_weights[: len(uw) - 1]
    for i, monthly in enumerate(timeline.monthly_results):
        if monthly.allocation_target is not None:
            actual = monthly.allocation_target.weights.get(_EQUITY)
            assert actual is not None, f"Period {i}: no equity"
            assert actual == expected_timeline[i], (
                f"Period {i}: expected={expected_timeline[i]}, got={actual}"
            )


def test_passive_glidepath_controlled_trajectory() -> None:
    """Run passive glidepath through full pipeline and verify allocation path."""
    uw = [True, False, False, True, False, False, True, False, False, True, False, False]
    _dataset, plan = _build_plan("passive", uw)

    result = sequential_execute(
        plan,
        summary_only=False,
        simulation_executor=NumbaSimulationExecutor(materialize_timeline=True),
    )

    assert len(result.results) == 1
    timeline = result.results[0].timeline
    assert len(timeline.monthly_results) == len(uw)

    for i, monthly in enumerate(timeline.monthly_results):
        if monthly.allocation_target is not None:
            actual = monthly.allocation_target.weights.get(_EQUITY)
            assert actual is not None, f"Period {i}: no equity"
            # Month 0 is the base row; month i >= 1 applies the (i - 1)-th
            # step of the passive glidepath.
            expected = min(
                Decimal("0.6") + _SLOPE * max(i - 1, 0), Decimal("1")
            )
            assert actual == expected, (
                f"Period {i}: expected={expected}, got={actual}"
            )
