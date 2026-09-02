"""Production accumulation phase implementation for Part 42 OMY.

Implements the 12-month accumulation phase using domain primitives only.
No engine, pipeline, or execution logic is imported.

This module produces the retirement starting portfolio from the initial
portfolio by applying monthly contributions, rebalancing, and market
evolution over 12 accumulation months.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.money import Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio


@dataclass(frozen=True)
class AccumulationResult:
    """Result of the accumulation phase."""

    final_portfolio: Portfolio
    month_by_month: tuple[Portfolio, ...]


def _find_holding(portfolio: Portfolio, asset: AssetClass) -> Decimal:
    """Return units for asset in portfolio, or 0 if absent."""
    for h in portfolio.holdings:
        if h.asset_class == asset:
            return h.units
    return Decimal("0")


def _build_portfolio(holdings: dict[AssetClass, Decimal]) -> Portfolio:
    """Build a Portfolio from a dict of asset→units."""
    return Portfolio(
        holdings=tuple(
            AssetHolding(asset_class=a, units=u) for a, u in holdings.items()
        )
    )


def run_accumulation_phase(
    *,
    initial_portfolio: Portfolio,
    contribution: Money,
    target_weights: dict[AssetClass, Decimal],
    dataset: Dataset,
    equity_asset: AssetClass,
    bond_asset: AssetClass,
) -> AccumulationResult:
    """Run 12-month accumulation phase.

    Parameters
    ----------
    initial_portfolio :
        Starting portfolio (snapshot[0] prices).
    contribution :
        Monthly contribution amount (constant real).
    target_weights :
        Target allocation weights (must sum to 1).
    dataset :
        Dataset with exactly 13 snapshots (indices 0..12).
    equity_asset :
        Equity AssetClass identifier.
    bond_asset :
        Bond AssetClass identifier.

    Returns
    -------
    AccumulationResult
        Final portfolio and month-by-month snapshots.

    Raises
    ------
    ValueError
        If dataset does not contain exactly 13 snapshots.
    """
    if len(dataset.snapshots) != 13:
        raise ValueError(
            f"Accumulation requires 13 snapshots, got {len(dataset.snapshots)}"
        )

    eq_units = _find_holding(initial_portfolio, equity_asset)
    bd_units = _find_holding(initial_portfolio, bond_asset)

    contribution_amount = contribution.amount

    month_portfolios: list[Portfolio] = []

    for m in range(12):
        eq_price_m = dataset.snapshots[m].index_levels[equity_asset]
        bd_price_m = dataset.snapshots[m].index_levels[bond_asset]

        # 1. Contribution
        eq_contrib = contribution_amount * target_weights[equity_asset] / eq_price_m
        bd_contrib = contribution_amount * target_weights[bond_asset] / bd_price_m
        eq_units += eq_contrib
        bd_units += bd_contrib

        # 2. Rebalance
        total_value = eq_units * eq_price_m + bd_units * bd_price_m
        eq_units = total_value * target_weights[equity_asset] / eq_price_m
        bd_units = total_value * target_weights[bond_asset] / bd_price_m

        # 3. Market evolution (current snapshot → next snapshot)
        eq_price_next = dataset.snapshots[m + 1].index_levels[equity_asset]
        bd_price_next = dataset.snapshots[m + 1].index_levels[bond_asset]
        eq_units *= eq_price_next / eq_price_m
        bd_units *= bd_price_next / bd_price_m

        month_portfolios.append(
            _build_portfolio({equity_asset: eq_units, bond_asset: bd_units})
        )

    final = _build_portfolio({equity_asset: eq_units, bond_asset: bd_units})
    return AccumulationResult(
        final_portfolio=final,
        month_by_month=tuple(month_portfolios),
    )
