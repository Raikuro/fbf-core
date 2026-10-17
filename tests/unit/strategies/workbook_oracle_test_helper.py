"""Workbook oracle helper for tests.

Computes expected workbook SCR results for validation against production code.
This is independent of production execution and implements the exact workbook formulas.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.study.builder import build_initial_portfolio


@dataclass(frozen=True)
class WorkbookOracleResult:
    """Expected result from workbook methodology."""
    success: bool
    failure_month: int | None
    final_wealth: Decimal
    months_simulated: int
    scr: Decimal


def compute_workbook_oracle_result(context: SimulationContext) -> WorkbookOracleResult:
    """Compute expected workbook result for a context.

    The workbook convention (``SWR_Toolbox_v2.0.xlsx`` ``Case Study``) counts
    ``horizon_months - 1`` return / withdrawal periods because
    ``context.horizon_months`` includes the pre-retirement snapshot.  Each
    period withdraws before growing, and the final period's return is
    compounded.

    Requires context.dataset to have at least ``horizon_months`` snapshots.
    """
    horizon = context.horizon_months
    periods = horizon - 1
    if len(context.dataset.snapshots) < periods + 1:
        raise ValueError(
            f"Dataset has {len(context.dataset.snapshots)} snapshots, "
            f"need {periods + 1}"
        )

    # Extract returns from dataset
    allocation = context.allocation_policy
    if not isinstance(allocation, ConstantAllocationPolicy):
        raise ValueError("Only ConstantAllocationPolicy supported")
    withdrawal = context.withdrawal_policy
    if not isinstance(withdrawal, FixedRealWithdrawalPolicy):
        raise ValueError("Only FixedRealWithdrawalPolicy supported")

    w_eq = allocation.equity_allocation
    fee_annual = context.expense_ratio or Decimal("0")
    fee_monthly = fee_annual / Decimal("12")
    target_rate = withdrawal.withdrawal_rate

    # Build monthly returns from dataset snapshots (fee embedded)
    eq_returns: list[Decimal] = []
    bd_returns: list[Decimal] = []
    snapshots = context.dataset.snapshots

    eq_class = AssetClass(id="equity", name="", description="")
    bd_class = AssetClass(id="bond", name="", description="")

    for m in range(periods):
        idx_m = snapshots[m].index_levels
        idx_m1 = snapshots[m + 1].index_levels
        eq_ret = idx_m1[eq_class] / idx_m[eq_class] - Decimal("1")
        bd_ret = idx_m1[bd_class] / idx_m[bd_class] - Decimal("1")
        eq_returns.append(eq_ret)
        bd_returns.append(bd_ret)

    # Compute workbook SCR
    scr = _compute_workbook_scr_from_returns(eq_returns, bd_returns, w_eq, fee_monthly)

    success = scr >= target_rate

    # Compute workbook trajectory for final wealth
    initial_value = _compute_initial_value(context)
    monthly_withdrawal = initial_value * target_rate / Decimal("12")

    final_wealth, _failure = _simulate_workbook_trajectory(
        eq_returns, bd_returns, w_eq, fee_monthly, initial_value,
        monthly_withdrawal, periods,
    )
    # Match the canonical Decimal fast path: success is decided by the SCR and
    # failure is reported at the horizon (the workbook model has no notion of a
    # trajectory depletion month).
    failure_month = None if success else horizon
    months_simulated = horizon

    return WorkbookOracleResult(
        success=success,
        failure_month=failure_month,
        final_wealth=final_wealth,
        months_simulated=months_simulated,
        scr=scr,
    )


def _compute_workbook_scr_from_returns(
    eq_returns: Sequence[Decimal],
    bd_returns: Sequence[Decimal],
    w_eq: Decimal,
    fee_monthly: Decimal,
) -> Decimal:
    """Compute workbook SCR from return sequences.

    SCR = 1 / (Sum_{t=0..T-1} 1/P[t]) * 12

    Where P[t] = cumulative growth factor with fee embedded:
    P[0] = 1
    P[t] = P[t-1] * (1 + w_eq*eq_ret + w_bd*bd_ret - fee_monthly)
    """
    w_bd = Decimal("1") - w_eq
    horizon = len(eq_returns)

    # Build cumulative growth factors P with fee embedded
    P = [Decimal("1")]
    for m in range(horizon):
        r = w_eq * eq_returns[m] + w_bd * bd_returns[m] - fee_monthly
        P.append(P[-1] * (Decimal("1") + r))

    # SCR = 1 / (Sum_{t=0..T-1} 1/P[t]) * 12
    sum_inv_P = sum(Decimal("1") / P[t] for t in range(horizon))
    scr = Decimal("1") / sum_inv_P * Decimal("12")
    return scr


def _compute_initial_value(context: SimulationContext) -> Decimal:
    """Compute initial portfolio value from context."""
    initial_value = Decimal("0")
    for holding in context.initial_portfolio.holdings:
        initial_value += (
            holding.units * context.dataset.snapshots[0].index_levels[holding.asset_class]
        )
    return initial_value


def _simulate_workbook_trajectory(
    eq_returns: Sequence[Decimal],
    bd_returns: Sequence[Decimal],
    w_eq: Decimal,
    fee_monthly: Decimal,
    initial_value: Decimal,
    monthly_withdrawal: Decimal,
    horizon: int,
) -> tuple[Decimal, int | None]:
    """Simulate the workbook trajectory (withdraw first, then grow).

    Returns ``(final_wealth, failure_month)`` where ``failure_month`` is the
    0-based month of depletion or ``None`` if the withdrawal is sustainable for
    the whole horizon.
    """
    w_bd = Decimal("1") - w_eq
    V = initial_value

    for m in range(horizon):
        if monthly_withdrawal > V:
            return Decimal("0"), m
        V = V - monthly_withdrawal  # Withdraw first (beginning-of-period)
        r = w_eq * eq_returns[m] + w_bd * bd_returns[m] - fee_monthly
        V = V * (Decimal("1") + r)  # Then grow (with fee embedded)

    return V, None


def make_workbook_test_context(
    horizon: int,
    w: float = 0.5,
    r: float = 0.04,
    equity_return: float = 0.006,
    bond_return: float = 0.002,
    fee_annual: float = 0.0005,
) -> SimulationContext:
    """Create a test context with horizon+1 snapshots for workbook validation.

    Snapshot index levels are gross market levels (``equity_return`` /
    ``bond_return``), matching production datasets.  The annual ``fee_annual``
    is carried by ``expense_ratio`` and applied exactly once by the strategy;
    it is deliberately not embedded in the prices as well.
    """
    from datetime import date

    _EQ = AssetClass(id="equity", name="", description="")
    _BD = AssetClass(id="bond", name="", description="")

    pe = pb = Decimal("100")
    snapshots = []
    d = date(1900, 1, 1)
    equity_return_dec = Decimal(str(equity_return))
    bond_return_dec = Decimal(str(bond_return))

    for _ in range(horizon + 1):  # horizon+1 snapshots for workbook
        snapshots.append(
            MarketSnapshot(
                date=d,
                index_levels={_EQ: pe, _BD: pb},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            )
        )
        pe *= (Decimal("1") + equity_return_dec)
        pb *= (Decimal("1") + bond_return_dec)
        d = date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)

    dataset = Dataset(snapshots=snapshots, frequency="monthly")
    start = dataset[0].date

    portfolio = build_initial_portfolio(Money(Decimal("1000000"), Currency.EUR), dataset)

    return SimulationContext(
        experiment_name="test",
        cohort=str(start),
        start_date=start,
        horizon_months=horizon,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        initial_portfolio=portfolio,
        dataset=dataset,  # Full dataset with horizon+1 snapshots
        allocation_policy=ConstantAllocationPolicy(Decimal(str(w))),
        withdrawal_policy=FixedRealWithdrawalPolicy(Decimal(str(r))),
        expense_ratio=Decimal(str(fee_annual)),
    )
