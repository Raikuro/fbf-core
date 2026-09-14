"""Corrected ERN cash-flow event order (P1.12R timeline remediation).

The engine implements the canonical Part 52 timeline:

* the initial portfolio is established at d_{-1} and NO withdrawal occurs
  at d_{-1} (period_index=0 is the pre-action initial state);
* the first withdrawal is taken at d_0 (period_index=1) using d_{-1}
  prices, BEFORE the first return is applied;
* each retirement month c..c+T-1 then grows the remainder at the month's
  real rebalanced return and withdraws the next monthly installment;
* a T-year retirement produces exactly T return intervals, T+1 withdrawals
  and T+1 observations, the last at d_{c+T-1}.

This is consistent with the canonical Part 52 formula:
    R_{t+1} = (R_t - consumption) * (1 + N_{t+1})
where T=0 is the pre-action initial state.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from fbf.core.execution.pipeline.pipeline import SimulationPipeline
from fbf.core.execution.pipeline.runner import SimulationRunner
from fbf.core.execution.pipeline.simulation import SimulationResult
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.pipeline.steps.allocation_decision_step import AllocationDecisionStep
from fbf.core.execution.pipeline.steps.build_decision_context_step import BuildDecisionContextStep
from fbf.core.execution.pipeline.steps.initialize_allocation_step import InitializeAllocationStep
from fbf.core.execution.pipeline.steps.market_evolution_step import MarketEvolutionStep
from fbf.core.execution.pipeline.steps.monthly_result_builder_step import MonthlyResultBuilderStep
from fbf.core.execution.pipeline.steps.portfolio_rebalance_step import PortfolioRebalanceStep
from fbf.core.execution.pipeline.steps.simulation_state_update_step import SimulationStateUpdateStep
from fbf.core.execution.pipeline.steps.withdrawal_decision_step import WithdrawalDecisionStep
from fbf.core.execution.pipeline.steps.withdrawal_execution_step import WithdrawalExecutionStep

_EQUITY = AssetClass(id="equity", name="", description="")
_BOND = AssetClass(id="bond", name="", description="")


def _snapshot(
    snapshot_date: date,
    equity_level: str,
    bond_level: str,
) -> MarketSnapshot:
    return MarketSnapshot(
        date=snapshot_date,
        index_levels={
            _EQUITY: Decimal(equity_level),
            _BOND: Decimal(bond_level),
        },
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=False,
        is_underwater=False,
        running_ath=Decimal("100"),
    )


def _value_at(portfolio: Portfolio, snapshot: MarketSnapshot) -> Decimal:
    total = Decimal("0")
    for holding in portfolio.holdings:
        total += holding.units * snapshot.index_levels[holding.asset_class]
    return total


def _run(context: SimulationContext) -> tuple[SimulationResult, SimulationRunner]:
    pipeline = SimulationPipeline(
        [
            InitializeAllocationStep(),
            BuildDecisionContextStep(),
            WithdrawalDecisionStep(),
            WithdrawalExecutionStep(),
            AllocationDecisionStep(),
            PortfolioRebalanceStep(),
            MarketEvolutionStep(),
            MonthlyResultBuilderStep(),
            SimulationStateUpdateStep(),
        ]
    )
    runner = SimulationRunner(pipeline)
    return runner.run(context), runner


def _context(dataset: Dataset, rate: str) -> SimulationContext:
    portfolio = Portfolio(
        holdings=(
            AssetHolding(asset_class=_EQUITY, units=Decimal("100")),
            AssetHolding(asset_class=_BOND, units=Decimal("100")),
        )
    )
    return SimulationContext(
        experiment_name="event-order",
        cohort="d_m1",
        start_date=dataset[0].date,
        horizon_months=len(dataset),
        initial_wealth=Money(Decimal("20000"), Currency.EUR),
        initial_portfolio=portfolio,
        dataset=dataset,
        allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.5")),
        withdrawal_policy=FixedRealWithdrawalPolicy(withdrawal_rate=Decimal(rate)),
    )


def _three_month_dataset() -> Dataset:
    """d_{-1}=2000-01-31, d_0=2000-02-29, d_1=2000-03-31 (T=2 retirement months)."""
    return Dataset(
        snapshots=(
            _snapshot(date(2000, 1, 1), "100", "100"),
            _snapshot(date(2000, 2, 1), "101", "100.5"),
            _snapshot(date(2000, 3, 1), "104.02", "100.5"),
        ),
        frequency="monthly",
    )


def test_initial_state_has_withdrawal() -> None:
    """T=0 (d_{-1}) applies the first retirement-month withdrawal."""
    dataset = _three_month_dataset()
    result = _run(_context(dataset, "0.12"))[0]
    monthly = result.timeline.monthly_results

    assert [m.date.isoformat() for m in monthly] == [
        "2000-01-01",
        "2000-02-01",
        "2000-03-01",
    ]

    first = monthly[0]
    assert _value_at(first.portfolio, first.market_snapshot) == Decimal("19800")
    assert first.withdrawal_decision is not None
    assert first.withdrawal_decision.nominal_amount.amount == Decimal("200")


def test_withdrawal_at_each_period() -> None:
    """A withdrawal happens at every period (T=0, T=1)."""
    dataset = _three_month_dataset()
    result = _run(_context(dataset, "0.12"))[0]
    monthly = result.timeline.monthly_results

    first = monthly[0]
    assert first.withdrawal_decision is not None
    assert first.withdrawal_decision.nominal_amount.amount == Decimal("200")

    second = monthly[1]
    assert second.withdrawal_decision is not None
    assert second.withdrawal_decision.nominal_amount.amount == Decimal("200")


def test_grow_then_withdraw_per_retirement_month() -> None:
    """Each retirement month grows the portfolio, then deducts the installment."""
    dataset = _three_month_dataset()
    result = _run(_context(dataset, "0.12"))[0]
    monthly = result.timeline.monthly_results

    # T=0: withdrew 200, then grew by g0
    g0 = Decimal("0.5") * (Decimal("101") / Decimal("100")) + Decimal("0.5") * (
        Decimal("100.5") / Decimal("100")
    )
    # T=0 portfolio after withdrawal: 20000 - 200 = 19800
    # T=1: grew from 19800 by g0, then withdrew 200
    assert _value_at(monthly[1].portfolio, monthly[1].market_snapshot) == (
        (Decimal("20000") - Decimal("200")) * g0 - Decimal("200")
    )

    # Growth d_0->d_1: 0.5*(104.02/101) + 0.5*(100.5/100.5)
    g1 = Decimal("0.5") * (Decimal("104.02") / Decimal("101")) + Decimal("0.5") * (
        Decimal("100.5") / Decimal("100.5")
    )
    after_t1 = (Decimal("20000") - Decimal("200")) * g0 - Decimal("200")
    expected_final = after_t1 * g1 - Decimal("200")
    actual_final = _value_at(monthly[2].portfolio, monthly[2].market_snapshot)
    assert actual_final == pytest.approx(expected_final, abs=Decimal("0.01"))


def test_horizon_is_t_plus_one_observations() -> None:
    """A T-month retirement yields T+1 observations ending at d_{c+T-1}."""
    dataset = _three_month_dataset()  # T = 2 retirement months
    context = _context(dataset, "0.12")
    result = _run(context)[0]

    assert context.horizon_months == 3
    assert len(result.timeline.monthly_results) == 3
    assert result.timeline.monthly_results[-1].date.isoformat() == "2000-03-01"
    assert result.statistics.months_simulated == 3
    assert result.statistics.success is True


def test_depletion_detected_when_withdrawal_exceeds_portfolio() -> None:
    """A withdrawal larger than V_{d_{-1}} is detected at period 0."""
    dataset = _three_month_dataset()
    # w = 20,000 * 12.6/12 = 21,000 — exceeds initial portfolio
    result = _run(_context(dataset, "12.6"))[0]

    assert result.statistics.success is False
    assert result.statistics.failure_month == 0
