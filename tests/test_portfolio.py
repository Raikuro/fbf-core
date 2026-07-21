from __future__ import annotations

from decimal import Decimal

import pytest

from engine.domain.model.asset import AssetClass
from engine.domain.model.portfolio import AssetHolding, Portfolio


def test_portfolio_holding_units_are_stored() -> None:
    asset = AssetClass(id="acwi", name="ACWI", description="Global equities")
    holdings = [AssetHolding(asset_class=asset, units=Decimal("100.00"))]

    portfolio = Portfolio(holdings=holdings)

    assert portfolio.holdings[0].units == Decimal("100.00")


def test_portfolio_rejects_negative_units() -> None:
    asset = AssetClass(id="acwi", name="ACWI", description="Global equities")

    with pytest.raises(ValueError):
        Portfolio(holdings=[AssetHolding(asset_class=asset, units=Decimal("-100.00"))])


def test_asset_holding_is_immutable() -> None:
    asset = AssetClass(id="acwi", name="ACWI", description="Global equities")
    holding = AssetHolding(asset_class=asset, units=Decimal("100.00"))

    with pytest.raises(AttributeError):
        holding.units = Decimal("200.00")
