"""Monthly trajectory materialization for the optimized Numba executors.

The optimized executors return trajectory-level statistics
(``SimulationStatistics``) but historically produced empty timelines because
building ``MonthlyResult``/``Portfolio``/``DebtSnapshot`` objects for every
month of every unit dominated the aggregation cost.

When ``ExecutionOptions.materialize_timeline`` is enabled the executors capture
the per-month portfolio value (and, for leveraged / buy-and-hold workloads, the
loan balance, repayment flag and drifting equity weight) into preallocated
``float64`` arrays while the Numba kernel runs, then reconstruct the canonical
domain objects here.

Reconstruction rules:

* ``MonthlyResult[m]`` is dated ``context.dataset[m].date`` and carries the
  exact ``MarketSnapshot`` the kernel valued against.
* ``portfolio`` holds ``AssetHolding`` units that revalue to the captured
  value at the month's own snapshot prices, using canonical asset order
  ``(id, name, description)`` with the residual assigned to the last asset
  (mirroring the workbook SCR model).
* ``allocation`` is the *actual* weight vector (drifting for buy-and-hold);
  ``allocation_target`` is the policy's target vector.
* ``cash_balance`` is zero: withdrawals consume any borrowed cash first, so the
  optimizer never carries a residual cash position between months.
* ``debt_snapshot`` is built only when a loan balance or a non-zero interest
  rate is present, matching ``MonthlyResultBuilderStep``.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import TYPE_CHECKING

from fbf.core.domain.model.allocation import Allocation, AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies.concrete import (
    BuyAndHoldAllocationPolicy,
    ConstantAllocationPolicy,
    resolve_target_weights,
)
from fbf.core.domain.policies.decisions import WithdrawalDecision
from fbf.core.execution.pipeline.simulation import (
    DebtSnapshot,
    MonthlyResult,
    SimulationTimeline,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

_EQUITY_ID = "equity"


def canonical_asset_classes(context: SimulationContext) -> tuple[AssetClass, ...]:
    """Return the dataset's asset classes in canonical ``(id, name, description)`` order."""
    snapshot = context.dataset[0]
    classes = tuple(snapshot.index_levels.keys())
    return tuple(sorted(classes, key=lambda a: (a.id, a.name, a.description)))


def _equity_weights(
    asset_classes: tuple[AssetClass, ...], equity_weight: Decimal
) -> dict[AssetClass, Decimal]:
    """Two-asset equity/bond weights from a single equity allocation."""
    return {
        asset_class: (
            equity_weight
            if asset_class.id == _EQUITY_ID
            else Decimal("1") - equity_weight
        )
        for asset_class in asset_classes
    }


def target_weights_for(
    context: SimulationContext,
    asset_classes: tuple[AssetClass, ...],
    *,
    equity_weight: Decimal | None = None,
) -> dict[AssetClass, Decimal]:
    """Return the policy's target weights aligned to *asset_classes*.

    ``equity_weight`` overrides the policy weight (used for per-month glidepath
    targets and for buy-and-hold's constant target).
    """
    if equity_weight is not None:
        return _equity_weights(asset_classes, equity_weight)
    policy = context.allocation_policy
    if isinstance(policy, ConstantAllocationPolicy):
        weights = resolve_target_weights(policy, asset_classes)
        return dict(zip(asset_classes, weights, strict=True))
    if isinstance(policy, BuyAndHoldAllocationPolicy):
        return _equity_weights(asset_classes, policy.equity_allocation)
    raise TypeError(
        f"materialize_timeline does not support allocation policy {type(policy).__name__}"
    )


def _build_portfolio(
    value: Decimal,
    prices: dict[AssetClass, Decimal],
    weights: dict[AssetClass, Decimal],
    asset_classes: tuple[AssetClass, ...],
) -> Portfolio:
    """Build a portfolio whose holdings revalue to exactly *value* at *prices*."""
    holdings: list[AssetHolding] = []
    allocated = Decimal("0")
    for asset_class in asset_classes[:-1]:
        target = value * weights.get(asset_class, Decimal("0"))
        allocated += target
        holdings.append(AssetHolding(asset_class, target / prices[asset_class]))
    last = asset_classes[-1]
    residual = value - allocated
    if residual < Decimal("0"):
        residual = Decimal("0")
    holdings.append(AssetHolding(last, residual / prices[last]))
    return Portfolio(tuple(holdings))


def _build_debt_snapshot(
    context: SimulationContext,
    value: Decimal,
    loan_balance: Decimal,
    is_repayment: bool,
) -> DebtSnapshot | None:
    interest_rate = context.interest_rate or Decimal("0")
    if loan_balance <= Decimal("0") and interest_rate <= Decimal("0"):
        return None
    ltv = Decimal("0")
    if value > Decimal("0") and loan_balance > Decimal("0"):
        ltv = loan_balance / value
    net_worth = value - loan_balance
    return DebtSnapshot(
        loan_balance=loan_balance,
        cash_balance=Decimal("0"),
        ltv=ltv,
        net_worth=net_worth,
        ltv_enforcement=context.ltv_enforcement,
        is_repayment=is_repayment,
    )


def _float_to_decimal(value: float) -> Decimal:
    return Decimal(str(value))


def build_simulation_timeline(
    context: SimulationContext,
    values: NDArray[np.float64] | Sequence[float],
    *,
    n_months: int,
    withdrawal_reason: str,
    withdrawal_amounts: Sequence[Decimal] | None = None,
    net_cash_flows: Sequence[Money | None] | None = None,
    loan_draw_amount: Decimal = Decimal("0"),
    loan_draw_amounts: Sequence[Decimal] | None = None,
    is_repayment_default: bool = False,
    actual_equity_weights: NDArray[np.float64] | Sequence[float] | None = None,
    target_equity_weights: Sequence[Decimal] | None = None,
    loan_balances: NDArray[np.float64] | None = None,
    is_repayments: NDArray[np.bool_] | None = None,
) -> SimulationTimeline:
    """Reconstruct a ``SimulationTimeline`` from captured kernel arrays.

    ``values[m]`` is the portfolio value at ``context.dataset[m]`` (the point
    the kernel records: post-withdrawal, pre-growth).  Only the first
    ``n_months`` entries are consumed, which is exactly the number of months the
    kernel simulated (``months_simulated``).
    """
    asset_classes = canonical_asset_classes(context)
    monthly_results: list[MonthlyResult] = []

    for m in range(n_months):
        snapshot = context.dataset[m]
        prices = snapshot.index_levels
        value = _float_to_decimal(float(values[m]))

        if target_equity_weights is not None:
            target_weights = _equity_weights(
                asset_classes, target_equity_weights[m]
            )
        else:
            target_weights = target_weights_for(context, asset_classes)

        if actual_equity_weights is not None:
            actual_weights = _equity_weights(
                asset_classes, _float_to_decimal(float(actual_equity_weights[m]))
            )
        else:
            actual_weights = target_weights

        portfolio = _build_portfolio(value, prices, actual_weights, asset_classes)

        is_repayment = is_repayment_default
        if is_repayments is not None:
            is_repayment = bool(is_repayments[m])

        if withdrawal_amounts is not None:
            nominal = withdrawal_amounts[m]
            draw_amount = (
                loan_draw_amounts[m]
                if loan_draw_amounts is not None
                else loan_draw_amount
            )
            withdrawal_decision = WithdrawalDecision(
                reason=withdrawal_reason,
                nominal_amount=Money(nominal, Currency.EUR),
                real_amount=Money(nominal, Currency.EUR),
                loan_draw_amount=draw_amount,
                is_repayment=is_repayment,
                spending_budget=nominal,
            )
        else:
            withdrawal_decision = None

        debt_snapshot = None
        if loan_balances is not None:
            debt_snapshot = _build_debt_snapshot(
                context, value, _float_to_decimal(float(loan_balances[m])), is_repayment
            )

        monthly_results.append(
            MonthlyResult(
                date=snapshot.date,
                period_index=m,
                market_snapshot=snapshot,
                portfolio=portfolio,
                allocation=Allocation(actual_weights),
                allocation_target=AllocationTarget(target_weights),
                allocation_drift=None,
                withdrawal_decision=withdrawal_decision,
                rebalance_result=None,
                drawdown=0.0,
                cumulative_return=0.0,
                cumulative_inflation=0.0,
                events=(),
                debt_snapshot=debt_snapshot,
                is_repayment=is_repayment,
                net_cash_flow=(
                    net_cash_flows[m] if net_cash_flows is not None else None
                ),
            )
        )

    return SimulationTimeline(monthly_results=tuple(monthly_results))


__all__ = [
    "build_simulation_timeline",
    "canonical_asset_classes",
    "target_weights_for",
]
