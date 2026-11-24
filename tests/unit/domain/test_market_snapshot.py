from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.market_snapshot import MarketSnapshot

_ASSET = AssetClass(id="equity", name="", description="")


def _snapshot(*, cape: Any = None) -> MarketSnapshot:
    return MarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={_ASSET: Decimal("100")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100"),
        cape=cape,
    )


def test_none_cape_is_preserved() -> None:
    assert _snapshot(cape=None).cape is None


def test_valid_decimal_cape_is_preserved_exactly() -> None:
    cape = Decimal("25.12345678901234567890")

    snapshot = _snapshot(cape=cape)

    assert snapshot.cape is cape
    assert snapshot.cape.as_tuple() == cape.as_tuple()


def test_negative_finite_cape_is_accepted() -> None:
    cape = Decimal("-12.5000")

    snapshot = _snapshot(cape=cape)

    assert snapshot.cape is cape
    assert snapshot.cape.as_tuple() == cape.as_tuple()


@pytest.mark.parametrize(
    "cape",
    [25.0, "25.0", 25],
    ids=["float", "str", "int"],
)
def test_non_decimal_cape_is_rejected(cape: Any) -> None:
    with pytest.raises(
        TypeError,
        match="MarketSnapshot cape must be a Decimal or None",
    ):
        _snapshot(cape=cape)


@pytest.mark.parametrize(
    "cape",
    [
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
    ids=["nan", "snan", "infinity", "negative_infinity"],
)
def test_non_finite_cape_is_rejected(cape: Decimal) -> None:
    with pytest.raises(
        ValueError,
        match="MarketSnapshot cape must be finite",
    ):
        _snapshot(cape=cape)
