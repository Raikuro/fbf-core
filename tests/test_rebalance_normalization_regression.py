"""Rebalance normalization regression (deterministic residual compensation).

Reproduces the pre-fix defect where, under non-round ``Decimal`` valuations,
independent per-asset division made:

- the rebalanced portfolio's revalued total drift from ``portfolio_value``
  ("Wealth conservation failed after rebalance"), and
- the derived ``Allocation`` weights sum to ``0.9999999999999999999999999999``
  instead of exactly ``Decimal("1")``.

Both symptoms share one root cause: ``Decimal`` division truncates to the
context precision, so independently derived per-asset components do not
guarantee to reproduce their defining total.  The fix assigns a deterministic
residual to the last canonical asset so that the strict domain invariants hold
exactly (sum of weights == 1; rebalance preserves wealth).  No tolerance or
global monetary quantum is involved.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from cli.builders import build_initial_portfolio
from cli.policies import ConstantAllocationPolicy
from engine.domain.model.allocation import Allocation, AllocationTarget
from engine.domain.model.asset import AssetClass
from engine.domain.model.dataset import Dataset
from engine.domain.model.decision_context import DecisionContext
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.money import Money
from engine.domain.model.portfolio import AssetHolding, Portfolio
from engine.domain.policies.decisions import AllocationDecision
from engine.domain.services.portfolio_market_evolution_service import (
    PortfolioMarketEvolutionService,
)
from engine.domain.services.portfolio_rebalance_service import PortfolioRebalanceService

EQUITY = AssetClass(id="equity", name="", description="")
BOND = AssetClass(id="bond", name="", description="")


def snap() -> MarketSnapshot:
    return MarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={EQUITY: Decimal("1.1"), BOND: Decimal("1.7")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("1.1"),
    )


def make_decision() -> AllocationDecision:
    return AllocationDecision(
        reason="test",
        allocation_target=AllocationTarget(
            weights={EQUITY: Decimal("0.75"), BOND: Decimal("0.25")}
        ),
    )


def _non_round_portfolio() -> Portfolio:
    """Valuation whose OLD rebalance raised the wealth-conservation failure.

    Equity price 1.1 / bond price 1.7 around a non-round ``777.13`` target: the
    per-asset division round-trips do not reproduce the portfolio total, so the
    pre-fix ``execute_rebalance`` failed at the exact wealth check.
    """
    target = Decimal("777.13")
    equity = AssetHolding(
        asset_class=EQUITY, units=target * Decimal("0.75") / Decimal("1.1")
    )
    bond = AssetHolding(
        asset_class=BOND, units=target * Decimal("0.25") / Decimal("1.7")
    )
    return Portfolio((equity, bond))


def _allocation_sum_failure_portfolio() -> Portfolio:
    """Valuation whose pre-fix derived allocation summed to 0.999...9 (captured).

    With these prices/units the wealth check passed but the independently
    divided ``Allocation`` weights were ``0.7499999999999999999999999999 +
    0.25 == 0.9999999999999999999999999999``.
    """
    return Portfolio(
        (
            AssetHolding(asset_class=EQUITY, units=Decimal("897030.1")),
            AssetHolding(asset_class=BOND, units=Decimal("9192638.3")),
        )
    )


def _allocation_sum_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={EQUITY: Decimal("656.1"), BOND: Decimal("47.67")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("656.1"),
    )


def _pre_fix_allocation_weights(
    portfolio: Portfolio, market: MarketSnapshot
) -> list[Decimal]:
    """Reproduce the pre-fix target->units->division derivation that leaked.

    Returns the independently divided equity and bond weights.
    """
    values = {
        holding.asset_class: holding.units
        * market.index_levels[holding.asset_class]
        for holding in portfolio.holdings
    }
    total = Decimal("0")
    for value in values.values():
        total += value
    target_units = {
        EQUITY: total * Decimal("0.75") / market.index_levels[EQUITY],
        BOND: total * Decimal("0.25") / market.index_levels[BOND],
    }

    def revalue(asset: AssetClass) -> Decimal:
        return target_units[asset] * market.index_levels[asset]

    rebuilt_total = revalue(EQUITY) + revalue(BOND)
    equity = revalue(EQUITY) / rebuilt_total
    bond = revalue(BOND) / rebuilt_total
    return [equity, bond]


def _value_of(portfolio: Portfolio, market: MarketSnapshot) -> Decimal:
    total = Decimal("0")
    for holding in portfolio.holdings:
        total += holding.units * market.index_levels[holding.asset_class]
    return total


def test_rebalance_preserves_wealth_exactly_under_non_round_valuations() -> None:
    market = snap()
    portfolio = _non_round_portfolio()
    before = _value_of(portfolio, market)

    result = PortfolioRebalanceService().execute_rebalance(
        portfolio, make_decision(), market
    )

    assert result.current_value == Money(before, Money.ZERO.currency)


def test_rebalance_allocation_sums_to_one_under_non_round_valuations() -> None:
    market = _allocation_sum_snapshot()
    portfolio = _allocation_sum_failure_portfolio()

    pre_fix = _pre_fix_allocation_weights(portfolio, market)
    captured_sum = pre_fix[0] + pre_fix[1]
    assert pre_fix[0] == Decimal("0.7499999999999999999999999999")
    assert pre_fix[1] == Decimal("0.25")
    assert captured_sum == Decimal("0.9999999999999999999999999999")

    result = PortfolioRebalanceService().execute_rebalance(
        portfolio, make_decision(), market
    )

    assert sum(result.allocation.weights.values()) == Decimal("1")
    assert all(value >= Decimal("0") for value in result.allocation.weights.values())


def test_evolution_services_derive_valid_allocation_under_non_round_valuations() -> None:
    market = snap()
    portfolio = _non_round_portfolio()
    service = PortfolioMarketEvolutionService()

    derived = service.derive_allocation(portfolio, market)
    assert sum(derived.weights.values()) == Decimal("1")
    assert all(value >= Decimal("0") for value in derived.weights.values())

    evolved = service.apply_market_evolution(portfolio, market)
    assert sum(evolved.allocation.weights.values()) == Decimal("1")
    assert all(value >= Decimal("0") for value in evolved.allocation.weights.values())


def test_rebalance_is_order_independent() -> None:
    market = snap()
    equity_first = _non_round_portfolio()
    bond_first = Portfolio(tuple(reversed(equity_first.holdings)))

    service = PortfolioRebalanceService()
    result_a = service.execute_rebalance(equity_first, make_decision(), market)
    result_b = service.execute_rebalance(bond_first, make_decision(), market)

    assert result_a.portfolio == result_b.portfolio
    assert result_a.allocation == result_b.allocation
    assert result_a.current_value == result_b.current_value


def test_rebalance_is_idempotent() -> None:
    market = snap()
    portfolio = _non_round_portfolio()
    service = PortfolioRebalanceService()
    decision = make_decision()

    first = service.execute_rebalance(portfolio, decision, market)
    second = service.execute_rebalance(first.portfolio, decision, market)

    assert first.portfolio == second.portfolio
    assert first.allocation == second.allocation


class TestConfiguredAllocationIsAuthoritative:
    """The user-configured ``equity_ratio`` must drive the target allocation.

    ``build_initial_portfolio`` only funds the initial capital into equity/bond
    bootstrap holdings so the engine has priced holdings at month 0.  That 50/50
    bootstrap must NOT be the user-facing asset allocation: the actual target
    comes from ``ConstantAllocationPolicy(equity_allocation=ratio)`` and the
    rebalance normalization must preserve it instead of forcing 50/50.
    """

    PRICES = {EQUITY: Decimal("2"), BOND: Decimal("1")}

    @staticmethod
    def _snapshot() -> MarketSnapshot:
        return MarketSnapshot(
            date=date(2000, 1, 1),
            index_levels=TestConfiguredAllocationIsAuthoritative.PRICES,
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("0"),
            is_ath=True,
            is_underwater=False,
            running_ath=Decimal("2"),
        )

    @staticmethod
    def _context(portfolio: Portfolio, market: MarketSnapshot) -> DecisionContext:
        dataset = Dataset(snapshots=(market,), frequency="monthly", version="v1")
        bootstrap_allocation = Allocation(weights={EQUITY: Decimal("1")})
        bootstrap_target = AllocationTarget(weights={EQUITY: Decimal("1")})
        return DecisionContext(
            date=market.date,
            period_index=0,
            simulation_context=object(),
            portfolio=portfolio,
            current_allocation=bootstrap_allocation,
            target_allocation=bootstrap_target,
            market_snapshot=market,
            dataset=dataset,
        )

    @pytest.mark.parametrize(
        ("ratio", "expected_equity", "expected_bond"),
        [
            (Decimal("0.80"), Decimal("0.80"), Decimal("0.20")),
            (Decimal("0.30"), Decimal("0.30"), Decimal("0.70")),
        ],
    )
    def test_configured_equity_ratio_survives_end_to_end(
        self,
        ratio: Decimal,
        expected_equity: Decimal,
        expected_bond: Decimal,
    ) -> None:
        wealth = Money(Decimal("1000000"), Money.ZERO.currency)
        market = self._snapshot()

        bootstrap = build_initial_portfolio(wealth)
        assert [h.asset_class for h in bootstrap.holdings] == [EQUITY, BOND]
        assert bootstrap.holdings[0].units == wealth.amount * Decimal("0.5")
        assert bootstrap.holdings[1].units == wealth.amount * Decimal("0.5")

        policy = ConstantAllocationPolicy(equity_allocation=ratio)
        target = policy.decide(self._context(bootstrap, market)).allocation_target
        assert target.weights == {EQUITY: expected_equity, BOND: expected_bond}
        assert sum(target.weights.values()) == Decimal("1")

        result = PortfolioRebalanceService().execute_rebalance(
            bootstrap, AllocationDecision(reason="test", allocation_target=target), market
        )

        assert result.allocation.weights[EQUITY] == expected_equity
        assert result.allocation.weights[BOND] == expected_bond
        assert sum(result.allocation.weights.values()) == Decimal("1")
        before = Decimal("0")
        for holding in bootstrap.holdings:
            before += holding.units * market.index_levels[holding.asset_class]
        assert result.current_value == Money(before, Money.ZERO.currency)
