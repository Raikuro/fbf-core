"""Tests for workbook-aligned Part 52 fixed-parameter feasibility metrics."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies import ConstantAllocationPolicy
from fbf.core.domain.policies.part52_withdrawal import Part52WithdrawalPolicy
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.part52_numba_executor import (
    evaluate_part52_feasibility,
)

EQUITY = AssetClass(id="equity", name="", description="")
BOND = AssetClass(id="bond", name="", description="")
INITIAL_WEALTH = Decimal("1000000")


def _context(
    *,
    equity_path: tuple[Decimal, ...],
    horizon: int,
    withdrawal_rate: Decimal = Decimal("0.0391"),
    borrow_pct: Decimal = Decimal("0.4108"),
) -> SimulationContext:
    base = date(1965, 11, 1)
    snapshots = tuple(
        MarketSnapshot(
            date=date(
                base.year + (base.month - 1 + i) // 12,
                (base.month - 1 + i) % 12 + 1,
                1,
            ),
            index_levels={EQUITY: price, BOND: Decimal("100")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=price >= max(equity_path[: i + 1]),
            is_underwater=price < max(equity_path[: i + 1]),
            running_ath=max(equity_path[: i + 1]),
        )
        for i, price in enumerate(equity_path)
    )
    return SimulationContext(
        experiment_name="part52-feasibility",
        cohort="1965-11",
        start_date=date(1965, 11, 1),
        horizon_months=horizon,
        initial_wealth=Money(INITIAL_WEALTH, Currency.EUR),
        initial_portfolio=Portfolio(
            holdings=(
                AssetHolding(asset_class=EQUITY, units=Decimal("7500")),
                AssetHolding(asset_class=BOND, units=Decimal("2500")),
            )
        ),
        dataset=Dataset(snapshots=snapshots, frequency="monthly"),
        allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.75")),
        withdrawal_policy=Part52WithdrawalPolicy(
            withdrawal_rate=withdrawal_rate,
            borrow_pct=borrow_pct,
            drawdown_threshold=Decimal("0.20"),
        ),
        interest_rate=Decimal("0.015"),
        ltv_limit=Decimal("0.50"),
        ltv_enforcement=False,
    )


def test_flat_market_without_debt_is_feasible() -> None:
    metrics = evaluate_part52_feasibility(
        _context(
            equity_path=(Decimal("100"),) * 4,
            horizon=4,
        )
    )

    assert metrics.gross_survival is True
    assert metrics.min_net_worth_ok is True
    assert metrics.final_net_worth_ok is True
    assert metrics.max_loan_to_portfolio_ok is True
    assert metrics.feasible is True
    assert metrics.withdrawal_months == 3
    assert abs(metrics.min_net_worth - Decimal("990225")) < Decimal("0.01")
    assert abs(metrics.final_net_worth - Decimal("990225")) < Decimal("0.01")
    assert metrics.max_loan_to_portfolio == Decimal("0.0")


def test_final_target_override_can_reject() -> None:
    metrics = evaluate_part52_feasibility(
        _context(
            equity_path=(Decimal("100"),) * 4,
            horizon=4,
        ),
        final_net_worth_target=Decimal("1000000"),
    )

    assert metrics.gross_survival is True
    assert metrics.final_net_worth_ok is False
    assert metrics.feasible is False


def test_depletion_is_not_feasible_despite_initial_net_worth() -> None:
    metrics = evaluate_part52_feasibility(
        _context(
            equity_path=(Decimal("100"),) * 4,
            horizon=4,
            withdrawal_rate=Decimal("6.0"),
        )
    )

    assert metrics.gross_survival is False
    assert metrics.min_net_worth_ok is True
    assert metrics.feasible is False
    assert metrics.final_portfolio_value == Decimal("0.0")
    assert metrics.max_loan_to_portfolio > Decimal("0.5")
    assert metrics.withdrawal_months == 2


def test_gross_survival_can_be_separate_from_feasibility() -> None:
    metrics = evaluate_part52_feasibility(
        _context(
            equity_path=(Decimal("100"), Decimal("75"), Decimal("75")),
            horizon=3,
            withdrawal_rate=Decimal("6.0"),
            borrow_pct=Decimal("1.0"),
        )
    )

    assert metrics.gross_survival is True
    assert metrics.max_loan_to_portfolio_ok is False
    assert metrics.feasible is False
    assert metrics.max_loan_to_portfolio > Decimal("0.5")
