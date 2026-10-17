"""Tests for explicit N-asset ConstantAllocationPolicy semantics.

Covers the explicit (N >= 2) allocation form, the single weight resolver, and
the canonical allocation identity used for cache/group keys.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from fbf.core.domain.model.allocation import Allocation, AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.decision_context import DecisionContext
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies import (
    ConstantAllocationPolicy,
    allocation_identity,
    resolve_target_weights,
)

_EQ = AssetClass(id="equity", name="", description="")
_BD = AssetClass(id="bond", name="", description="")
_GD = AssetClass(id="gold", name="", description="")

_WEIGHTS = {"equity": Decimal("0.5"), "bond": Decimal("0.3"), "gold": Decimal("0.2")}


class TestExplicitConstruction:
    def test_canonical_sorted_storage(self) -> None:
        policy = ConstantAllocationPolicy(allocations=dict(_WEIGHTS))
        assert policy.allocations == (
            ("bond", Decimal("0.3")),
            ("equity", Decimal("0.5")),
            ("gold", Decimal("0.2")),
        )
        assert policy.equity_allocation is None

    def test_legacy_form_preserved(self) -> None:
        policy = ConstantAllocationPolicy(Decimal("0.6"))
        assert policy.equity_allocation == Decimal("0.6")
        assert policy.allocations is None

    def test_neither_form_rejected(self) -> None:
        with pytest.raises(ValueError):
            ConstantAllocationPolicy()

    def test_both_forms_rejected(self) -> None:
        with pytest.raises(ValueError):
            ConstantAllocationPolicy(Decimal("0.5"), allocations=dict(_WEIGHTS))

    def test_fewer_than_two_assets_rejected(self) -> None:
        with pytest.raises(ValueError):
            ConstantAllocationPolicy(allocations={"equity": Decimal("1")})

    def test_empty_key_rejected(self) -> None:
        with pytest.raises(ValueError):
            ConstantAllocationPolicy(
                allocations={"": Decimal("0.5"), "bond": Decimal("0.5")}
            )

    def test_non_decimal_weight_rejected(self) -> None:
        with pytest.raises(TypeError):
            ConstantAllocationPolicy(
                allocations={"equity": 0.5, "bond": Decimal("0.5")}  # type: ignore[dict-item]
            )

    def test_out_of_range_weight_rejected(self) -> None:
        with pytest.raises(ValueError):
            ConstantAllocationPolicy(
                allocations={"equity": Decimal("1.5"), "bond": Decimal("-0.5")}
            )

    def test_sum_not_one_rejected(self) -> None:
        with pytest.raises(ValueError):
            ConstantAllocationPolicy(
                allocations={"equity": Decimal("0.5"), "bond": Decimal("0.4")}
            )

    def test_zero_weight_held_asset_allowed(self) -> None:
        policy = ConstantAllocationPolicy(
            allocations={"equity": Decimal("1"), "bond": Decimal("0")}
        )
        assert policy.allocations == (
            ("bond", Decimal("0")),
            ("equity", Decimal("1")),
        )


class TestResolver:
    def test_explicit_aligns_to_given_order(self) -> None:
        policy = ConstantAllocationPolicy(allocations=dict(_WEIGHTS))
        weights = resolve_target_weights(policy, (_GD, _EQ, _BD))
        assert weights == (Decimal("0.2"), Decimal("0.5"), Decimal("0.3"))

    def test_explicit_missing_asset_rejected(self) -> None:
        policy = ConstantAllocationPolicy(allocations=dict(_WEIGHTS))
        with pytest.raises(ValueError):
            resolve_target_weights(policy, (_EQ, _BD))

    def test_explicit_extra_asset_rejected(self) -> None:
        policy = ConstantAllocationPolicy(
            allocations={"equity": Decimal("0.5"), "bond": Decimal("0.5")}
        )
        with pytest.raises(ValueError):
            resolve_target_weights(policy, (_EQ, _BD, _GD))

    def test_duplicate_held_ids_rejected(self) -> None:
        policy = ConstantAllocationPolicy(
            allocations={"equity": Decimal("0.5"), "bond": Decimal("0.5")}
        )
        with pytest.raises(ValueError):
            resolve_target_weights(policy, (_EQ, _EQ))

    def test_legacy_mirrors_equity_and_rest(self) -> None:
        policy = ConstantAllocationPolicy(Decimal("0.6"))
        assert resolve_target_weights(policy, (_EQ, _BD)) == (
            Decimal("0.6"),
            Decimal("0.4"),
        )
        assert resolve_target_weights(policy, (_BD, _EQ)) == (
            Decimal("0.4"),
            Decimal("0.6"),
        )

    def test_legacy_lenient_for_unknown_order(self) -> None:
        policy = ConstantAllocationPolicy(Decimal("0.6"))
        weights = resolve_target_weights(policy, (_GD, _EQ))
        assert weights == (Decimal("0.4"), Decimal("0.6"))


class TestAllocationIdentity:
    def test_order_insensitive(self) -> None:
        a = ConstantAllocationPolicy(
            allocations={"equity": Decimal("0.5"), "bond": Decimal("0.5")}
        )
        b = ConstantAllocationPolicy(
            allocations={"bond": Decimal("0.5"), "equity": Decimal("0.5")}
        )
        assert allocation_identity(a, (_EQ, _BD)) == allocation_identity(b, (_BD, _EQ))

    def test_distinct_weights_distinct_identity(self) -> None:
        a = ConstantAllocationPolicy(
            allocations={"equity": Decimal("0.5"), "bond": Decimal("0.5")}
        )
        b = ConstantAllocationPolicy(
            allocations={"equity": Decimal("0.4"), "bond": Decimal("0.6")}
        )
        assert allocation_identity(a, (_EQ, _BD)) != allocation_identity(b, (_EQ, _BD))

    def test_legacy_identity(self) -> None:
        policy = ConstantAllocationPolicy(Decimal("0.6"))
        assert allocation_identity(policy, (_EQ, _BD)) == (
            ("bond", Decimal("0.4")),
            ("equity", Decimal("0.6")),
        )


def _make_context(holdings: tuple[AssetHolding, ...]) -> DecisionContext:
    portfolio = Portfolio(holdings=holdings)
    index_levels = {h.asset_class: Decimal("1") for h in holdings}
    snapshot = MarketSnapshot(
        date=date(2020, 1, 1),
        index_levels=index_levels,
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100"),
    )
    dummy = AssetClass(id="dummy", name="Dummy", description="")
    return DecisionContext(
        date=date(2020, 1, 1),
        period_index=0,
        simulation_context=object(),
        portfolio=portfolio,
        current_allocation=Allocation(weights={dummy: Decimal("1")}),
        target_allocation=AllocationTarget(weights={dummy: Decimal("1")}),
        market_snapshot=snapshot,
        dataset=Dataset(snapshots=(snapshot,), frequency="monthly"),
    )


class TestExplicitDecide:
    def test_maps_ids_to_held_classes(self) -> None:
        policy = ConstantAllocationPolicy(allocations=dict(_WEIGHTS))
        context = _make_context(
            (
                AssetHolding(asset_class=_EQ, units=Decimal("1")),
                AssetHolding(asset_class=_BD, units=Decimal("1")),
                AssetHolding(asset_class=_GD, units=Decimal("1")),
            )
        )
        decision = policy.decide(context)
        assert decision.allocation_target.weights == {
            _EQ: Decimal("0.5"),
            _BD: Decimal("0.3"),
            _GD: Decimal("0.2"),
        }

    def test_unknown_asset_id_rejected(self) -> None:
        policy = ConstantAllocationPolicy(allocations=dict(_WEIGHTS))
        context = _make_context(
            (
                AssetHolding(asset_class=_EQ, units=Decimal("1")),
                AssetHolding(asset_class=_BD, units=Decimal("1")),
            )
        )
        with pytest.raises(ValueError):
            policy.decide(context)

    def test_missing_held_asset_rejected(self) -> None:
        policy = ConstantAllocationPolicy(
            allocations={"equity": Decimal("0.5"), "bond": Decimal("0.5")}
        )
        context = _make_context(
            (
                AssetHolding(asset_class=_EQ, units=Decimal("1")),
                AssetHolding(asset_class=_BD, units=Decimal("1")),
                AssetHolding(asset_class=_GD, units=Decimal("1")),
            )
        )
        with pytest.raises(ValueError):
            policy.decide(context)
