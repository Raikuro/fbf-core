"""Tests for shared CLI policy implementations.

Verifies that ConstantAllocationPolicy and ConstantWithdrawalPolicy
produce correct decisions for nominal and edge-case inputs.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from cli.policies import ConstantAllocationPolicy, ConstantWithdrawalPolicy
from engine.domain.model.allocation import Allocation, AllocationTarget
from engine.domain.model.asset import AssetClass
from engine.domain.model.dataset import Dataset
from engine.domain.model.decision_context import DecisionContext
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.portfolio import AssetHolding, Portfolio


def _make_dataset() -> Dataset:
    asset = AssetClass(id="acwi", name="ACWI", description="")
    snap = MarketSnapshot(
        date=date(2020, 1, 1),
        index_levels={asset: Decimal("100")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100"),
    )
    return Dataset(snapshots=(snap,), frequency="monthly", version="1.0")


def _make_portfolio(total: Decimal) -> Portfolio:
    asset = AssetClass(id="initial", name="Initial", description="")
    return Portfolio(holdings=(AssetHolding(asset_class=asset, units=total),))


def _make_context(portfolio: Portfolio) -> DecisionContext:
    asset = AssetClass(id="acwi", name="ACWI", description="")
    snapshot = MarketSnapshot(
        date=date(2020, 1, 1),
        index_levels={asset: Decimal("100")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100"),
    )
    dummy_asset = AssetClass(id="dummy", name="Dummy", description="")
    dummy_alloc = Allocation(weights={dummy_asset: Decimal("1")})
    dummy_target = AllocationTarget(weights={dummy_asset: Decimal("1")})
    return DecisionContext(
        date=date(2020, 1, 1),
        period_index=0,
        simulation_context=object(),
        portfolio=portfolio,
        current_allocation=dummy_alloc,
        target_allocation=dummy_target,
        market_snapshot=snapshot,
        dataset=_make_dataset(),
    )


class TestConstantAllocationPolicy:
    def test_equity_075(self) -> None:
        policy = ConstantAllocationPolicy(equity_allocation=Decimal("0.75"))
        ctx = _make_context(_make_portfolio(Decimal("1000000")))
        decision = policy.decide(ctx)

        equity = AssetClass(id="equity", name="Equity", description="")
        bond = AssetClass(id="bond", name="Bond", description="")

        assert decision.allocation_target.weights[equity] == Decimal("0.75")
        assert decision.allocation_target.weights[bond] == Decimal("0.25")

    def test_equity_100(self) -> None:
        policy = ConstantAllocationPolicy(equity_allocation=Decimal("1.0"))
        ctx = _make_context(_make_portfolio(Decimal("1000000")))
        decision = policy.decide(ctx)

        equity = AssetClass(id="equity", name="Equity", description="")
        bond = AssetClass(id="bond", name="Bond", description="")

        assert decision.allocation_target.weights[equity] == Decimal("1.0")
        assert decision.allocation_target.weights[bond] == Decimal("0.0")

    def test_equity_000(self) -> None:
        policy = ConstantAllocationPolicy(equity_allocation=Decimal("0.0"))
        ctx = _make_context(_make_portfolio(Decimal("1000000")))
        decision = policy.decide(ctx)

        equity = AssetClass(id="equity", name="Equity", description="")
        bond = AssetClass(id="bond", name="Bond", description="")

        assert decision.allocation_target.weights[equity] == Decimal("0.0")
        assert decision.allocation_target.weights[bond] == Decimal("1.0")

    def test_weights_sum_to_one(self) -> None:
        for ratio in [
            Decimal("0.0"),
            Decimal("0.25"),
            Decimal("0.5"),
            Decimal("0.75"),
            Decimal("1.0"),
        ]:
            policy = ConstantAllocationPolicy(equity_allocation=ratio)
            ctx = _make_context(_make_portfolio(Decimal("1000000")))
            decision = policy.decide(ctx)
            total = sum(decision.allocation_target.weights.values())
            assert total == Decimal("1.0"), f"Weights sum to {total} for ratio={ratio}"


class TestConstantWithdrawalPolicy:
    def test_nominal_rate(self) -> None:
        policy = ConstantWithdrawalPolicy(withdrawal_rate=Decimal("0.04"))
        portfolio = _make_portfolio(Decimal("1000000"))
        ctx = _make_context(portfolio)
        decision = policy.decide(ctx)

        expected = Decimal("1000000") * Decimal("0.04") / Decimal("12")
        assert decision.nominal_amount.amount == expected
        assert decision.real_amount.amount == expected

    def test_zero_rate(self) -> None:
        policy = ConstantWithdrawalPolicy(withdrawal_rate=Decimal("0"))
        portfolio = _make_portfolio(Decimal("1000000"))
        ctx = _make_context(portfolio)
        decision = policy.decide(ctx)

        assert decision.nominal_amount.amount == Decimal("0")
        assert decision.real_amount.amount == Decimal("0")

    def test_preserves_decimal_precision(self) -> None:
        rate = Decimal("0.0715")
        policy = ConstantWithdrawalPolicy(withdrawal_rate=rate)
        portfolio = _make_portfolio(Decimal("1000000"))
        ctx = _make_context(portfolio)
        decision = policy.decide(ctx)

        expected = Decimal("1000000") * rate / Decimal("12")
        assert decision.nominal_amount.amount == expected
        assert isinstance(decision.nominal_amount.amount, Decimal)

    def test_works_with_real_context(self) -> None:
        policy = ConstantWithdrawalPolicy(withdrawal_rate=Decimal("0.04"))
        portfolio = _make_portfolio(Decimal("500000"))
        ctx = _make_context(portfolio)
        decision = policy.decide(ctx)

        assert decision.nominal_amount.amount > Decimal("0")
        assert decision.reason == "ConstantWithdrawalPolicy"
