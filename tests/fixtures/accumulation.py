"""Controlled fixtures for Part 42 accumulation testing.

Provides reproducible datasets, portfolios, and parameters for validating
the accumulation phase implementation against the independent oracle.

All fixtures use the domain model primitives directly. No production
accumulation or execution logic is imported.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio

# Canonical asset classes matching the codebase convention.
EQUITY = AssetClass(id="equity", name="", description="")
BOND = AssetClass(id="bond", name="", description="")


def _snapshot(
    d: date,
    equity_price: Decimal,
    bond_price: Decimal,
) -> MarketSnapshot:
    """Build a minimal MarketSnapshot for testing."""
    return MarketSnapshot(
        date=d,
        index_levels={EQUITY: equity_price, BOND: bond_price},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=True,
        is_underwater=False,
        running_ath=equity_price,
    )


# ---------------------------------------------------------------------------
# Flat dataset: all index levels = 1.0 (zero return)
# ---------------------------------------------------------------------------

_FLAT_DATES = [date(2020, 1, 1 + m) for m in range(13)]
_FLAT_SNAPSHOTS = [_snapshot(d, Decimal("1"), Decimal("1")) for d in _FLAT_DATES]
FLAT_DATASET = Dataset(
    snapshots=_FLAT_SNAPSHOTS,
    frequency="monthly",
    version="test-flat",
    identifier="flat",
)


# ---------------------------------------------------------------------------
# Growth dataset: constant 1% monthly equity return, 0.5% bond return
# ---------------------------------------------------------------------------

_GROWTH_DATES = [date(2020, 1, 1 + m) for m in range(13)]
_GROWTH_EQUITY = [Decimal("100")]
_GROWTH_BOND = [Decimal("50")]
for _ in range(12):
    _GROWTH_EQUITY.append(_GROWTH_EQUITY[-1] * Decimal("1.01"))
    _GROWTH_BOND.append(_GROWTH_BOND[-1] * Decimal("1.005"))
_GROWTH_SNAPSHOTS = [
    _snapshot(d, eq, bd)
    for d, eq, bd in zip(_GROWTH_DATES, _GROWTH_EQUITY, _GROWTH_BOND, strict=True)
]
GROWTH_DATASET = Dataset(
    snapshots=_GROWTH_SNAPSHOTS,
    frequency="monthly",
    version="test-growth",
    identifier="growth",
)


# ---------------------------------------------------------------------------
# Known-answer portfolio: 100 equity units, 200 bond units
# ---------------------------------------------------------------------------

KNOWN_PORTFOLIO = Portfolio(
    holdings=(
        AssetHolding(asset_class=EQUITY, units=Decimal("100")),
        AssetHolding(asset_class=BOND, units=Decimal("200")),
    )
)

# 75/25 target allocation weights (matching Part 42 study configuration)
TARGET_WEIGHTS = {EQUITY: Decimal("0.75"), BOND: Decimal("0.25")}

# Standard contribution amount (constant real, matching S3.1 semantic contract)
CONTRIBUTION = Money(Decimal("5000"), Currency.EUR)


# ---------------------------------------------------------------------------
# ERN-realistic dataset: actual ERN-like price trajectory (13 snapshots)
# ---------------------------------------------------------------------------

_ERN_DATES = [date(1871, 2, 1 + m) for m in range(13)]
_ERN_EQUITY_PRICES = [
    Decimal("100.00"),
    Decimal("102.50"),
    Decimal("98.75"),
    Decimal("105.00"),
    Decimal("103.25"),
    Decimal("108.00"),
    Decimal("112.50"),
    Decimal("110.00"),
    Decimal("115.25"),
    Decimal("118.00"),
    Decimal("116.50"),
    Decimal("120.75"),
    Decimal("125.00"),
]
_ERN_BOND_PRICES = [
    Decimal("50.00"),
    Decimal("50.25"),
    Decimal("50.50"),
    Decimal("50.75"),
    Decimal("51.00"),
    Decimal("51.25"),
    Decimal("51.50"),
    Decimal("51.75"),
    Decimal("52.00"),
    Decimal("52.25"),
    Decimal("52.50"),
    Decimal("52.75"),
    Decimal("53.00"),
]
_ERN_SNAPSHOTS = [
    _snapshot(d, eq, bd)
    for d, eq, bd in zip(
        _ERN_DATES, _ERN_EQUITY_PRICES, _ERN_BOND_PRICES, strict=True
    )
]
ERN_REALISTIC_DATASET = Dataset(
    snapshots=_ERN_SNAPSHOTS,
    frequency="monthly",
    version="test-ern",
    identifier="ern-realistic",
)
