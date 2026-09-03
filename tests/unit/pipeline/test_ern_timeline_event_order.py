"""Corrected ERN cash-flow event order (P1.12R timeline remediation).

The engine must implement the literal ERN timeline:

* the initial portfolio is established at the pre-retirement month-end d_{c-1};
* the INITIAL withdrawal is taken at d_{c-1} at the previous month's closing
  price, BEFORE the first return is applied;
* each retirement month c..c+T-1 then grows the remainder at the month's real
  rebalanced return and withdraws the next monthly installment at the month-end;
* a T-year retirement produces exactly T return intervals, T+1 withdrawals and
  T+1 observations, the last at d_{c+T-1}.

This test pins that event order on the reference pipeline with the real ERN
data (whose first snapshot is the d_{-1} base at 1871-01-31).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

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
        version="1.0",
    )


def test_initial_withdrawal_happens_at_pre_retirement_snapshot() -> None:
    """The first recorded observation is the post-withdrawal value at d_{-1}."""
    dataset = _three_month_dataset()
    result = _run(_context(dataset, "0.12"))[0]
    monthly = result.timeline.monthly_results

    assert [m.date.isoformat() for m in monthly] == [
        "2000-01-01",
        "2000-02-01",
        "2000-03-01",
    ]

    # Withdrawal anchored at dataset[0] = d_{-1}: w = V_{d_{-1}} * 0.12 / 12.
    # V_{d_{-1}} = 100*100 + 100*100 = 20,000 -> w = 200.
    first = monthly[0]
    assert _value_at(first.portfolio, first.market_snapshot) == Decimal("19800")
    assert first.withdrawal_decision is not None
    assert first.withdrawal_decision.nominal_amount.amount == Decimal("200")


def test_grow_then_withdraw_per_retirement_month() -> None:
    """Each retirement month applies the return, then the installment."""
    dataset = _three_month_dataset()
    result = _run(_context(dataset, "0.12"))[0]
    monthly = result.timeline.monthly_results

    # Growth d_{-1}->d_0: 0.5*(101/100) + 0.5*(100.5/100) = 1.0075
    g0 = Decimal("0.5") * (Decimal("101") / Decimal("100")) + Decimal("0.5") * (
        Decimal("100.5") / Decimal("100")
    )
    assert _value_at(monthly[1].portfolio, monthly[1].market_snapshot) == (
        Decimal("19800") * g0 - Decimal("200")
    )

    # Growth d_0->d_1: 0.5*(104.02/101) + 0.5*(100.5/100.5)
    g1 = Decimal("0.5") * (Decimal("104.02") / Decimal("101")) + Decimal("0.5") * (
        Decimal("100.5") / Decimal("100.5")
    )
    expected_final = (Decimal("19800") * g0 - Decimal("200")) * g1 - Decimal("200")
    assert _value_at(monthly[2].portfolio, monthly[2].market_snapshot) == expected_final


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


def test_depletion_at_initial_withdrawal_is_detected() -> None:
    """A withdrawal larger than V_{d_{-1}} fails immediately at d_{-1}."""
    dataset = _three_month_dataset()
    result = _run(_context(dataset, "12.6"))[0]  # w = 20,000 * 12.6/12 = 21,000

    assert result.statistics.success is False
    assert result.statistics.failure_month == 0
