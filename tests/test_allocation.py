from __future__ import annotations

from decimal import Decimal

import pytest

from engine.domain.model.allocation import Allocation, AllocationTarget
from engine.domain.model.asset import AssetClass


@pytest.fixture
def asset_classes() -> list[AssetClass]:
    return [
        AssetClass(id="acwi", name="ACWI", description="Global equities"),
        AssetClass(id="bonds", name="Bonds", description="Government bonds"),
        AssetClass(id="cash", name="Cash", description="Money market"),
    ]


def test_allocation_sums_to_one(asset_classes: list[AssetClass]) -> None:
    allocation = Allocation(
        weights={
            asset_classes[0]: Decimal("0.60"),
            asset_classes[1]: Decimal("0.30"),
            asset_classes[2]: Decimal("0.10"),
        }
    )

    assert allocation[asset_classes[0]] == Decimal("0.60")
    assert allocation[asset_classes[1]] == Decimal("0.30")
    assert allocation[asset_classes[2]] == Decimal("0.10")


def test_allocation_rejects_negative_weights(asset_classes: list[AssetClass]) -> None:
    with pytest.raises(ValueError):
        Allocation(
            weights={
                asset_classes[0]: Decimal("0.60"),
                asset_classes[1]: Decimal("-0.10"),
                asset_classes[2]: Decimal("0.50"),
            }
        )


def test_allocation_rejects_non_unit_total(asset_classes: list[AssetClass]) -> None:
    with pytest.raises(ValueError):
        Allocation(
            weights={
                asset_classes[0]: Decimal("0.50"),
                asset_classes[1]: Decimal("0.30"),
                asset_classes[2]: Decimal("0.10"),
            }
        )


def test_allocation_target_equivalence(asset_classes: list[AssetClass]) -> None:
    target = AllocationTarget(
        weights={
            asset_classes[0]: Decimal("0.70"),
            asset_classes[1]: Decimal("0.20"),
            asset_classes[2]: Decimal("0.10"),
        }
    )

    assert target[asset_classes[0]] == Decimal("0.70")
    assert target[asset_classes[1]] == Decimal("0.20")
    assert target[asset_classes[2]] == Decimal("0.10")
