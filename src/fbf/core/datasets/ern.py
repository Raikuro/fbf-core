"""ERN canonical dataset loader.

Reconstructs the runtime Dataset from canonical CSV sources:

- ``sp500_tr_real_return.csv`` — S&P 500 TR real returns
- ``bond_10y_tr_real_return.csv`` — 10-Year Bond Market real returns

The loader owns all CSV-specific details: filenames, fee rules,
forward-projection rules, and derived market state (ATH, underwater).
The study builder does not know these details.
"""

from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from fbf.core.domain.model.dataset import Dataset

# ---------------------------------------------------------------------------
# Canonical CSV filenames
# ---------------------------------------------------------------------------

_EQUITY_CSV = "sp500_tr_real_return.csv"
_BOND_CSV = "bond_10y_tr_real_return.csv"

# ---------------------------------------------------------------------------
# Fee constants
# ---------------------------------------------------------------------------

_FEE_ANNUAL = Decimal("0.0005")
_FEE_MONTHLY = _FEE_ANNUAL / Decimal("12")

# ---------------------------------------------------------------------------
# Base snapshot constants (index 0, 1871-01-31)
# ---------------------------------------------------------------------------

_EQUITY_BASE_SNAPSHOT = 101.169089694984
_BOND_BASE_SNAPSHOT = 100.747178470726

# ---------------------------------------------------------------------------
# First data point constants (index 1, 1871-02-01)
# ---------------------------------------------------------------------------

_EQUITY_BASE = 100.0
_BOND_BASE = 100.0

# ---------------------------------------------------------------------------
# Forward projection constants
# ---------------------------------------------------------------------------

_EQUITY_FORWARD_ANNUAL = 0.065467
_BOND_FORWARD_ANNUAL = 0.0
_BOND_FORWARD_ANNUAL_AFTER = 0.025487
_BOND_FORWARD_DELAY_MONTHS = 121
_HISTORICAL_END = datetime(2016, 10, 1)
_PROJECTION_END = datetime(2075, 11, 1)


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------


def _load_csv(path: Path) -> list[tuple[str, float]]:
    """Load a canonical DD-MM-YYYY,value CSV."""
    rows: list[tuple[str, float]] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        assert header == ["DD-MM-YYYY", "value"], f"Unexpected header: {header}"
        for row in reader:
            if len(row) >= 2 and row[1].strip():
                rows.append((row[0].strip(), float(row[1].strip())))
    return rows


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_ern_dataset(data_dir: Path) -> Dataset:
    """Load the ERN dataset from canonical CSV sources.

    Reconstructs the runtime Dataset from equity and bond real-return CSVs,
    applying fee deductions, forward projections, and ATH/underwater state.

    Parameters
    ----------
    data_dir:
        Directory containing ``sp500_tr_real_return.csv`` and
        ``bond_10y_tr_real_return.csv``.

    Returns
    -------
    Dataset
        Immutable market observations ready for study planning and simulation.
    """
    from fbf.core.domain.model.asset import AssetClass
    from fbf.core.domain.model.market_snapshot import MarketSnapshot

    equity_returns = _load_csv(data_dir / _EQUITY_CSV)
    bond_returns = _load_csv(data_dir / _BOND_CSV)

    eq_return_map: dict[str, float] = dict(equity_returns)
    bond_return_map: dict[str, float] = dict(bond_returns)

    eq_asset = AssetClass(id="equity", name="", description="")
    bond_asset = AssetClass(id="bond", name="", description="")

    snapshots: list[MarketSnapshot] = []

    def _append(
        date_str: str,
        eq: float,
        bond: float,
        running_ath_val: float,
        is_ath_val: bool,
        is_uw_val: bool,
    ) -> None:
        snapshots.append(
            MarketSnapshot(
                date=date.fromisoformat(date_str),
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=is_ath_val,
                is_underwater=is_uw_val,
                running_ath=Decimal(str(running_ath_val)),
                index_levels={
                    eq_asset: Decimal(str(eq)),
                    bond_asset: Decimal(str(bond)),
                },
            )
        )

    # Base snapshot (index 0, 1871-01-31)
    _append(
        "1871-01-31",
        _EQUITY_BASE_SNAPSHOT,
        _BOND_BASE_SNAPSHOT,
        _EQUITY_BASE_SNAPSHOT,
        False,
        True,
    )

    # First data point (index 1, 1871-02-01)
    eq_level = _EQUITY_BASE
    bond_level = _BOND_BASE
    running_ath = eq_level
    _append("1871-02-01", eq_level, bond_level, running_ath, True, False)

    # Historical period (1871-03 through 2016-09)
    current_date = datetime(1871, 3, 1)
    while current_date < _HISTORICAL_END:
        ret_month = current_date.month - 1 if current_date.month > 1 else 12
        ret_year = (
            current_date.year if current_date.month > 1 else current_date.year - 1
        )
        date_key = f"01-{ret_month:02d}-{ret_year}"
        r_eq = eq_return_map.get(date_key, 0.0)
        r_bond = bond_return_map.get(date_key, 0.0)

        eq_level *= (1 + r_eq) * (1 - float(_FEE_MONTHLY))
        bond_level *= (1 + r_bond) * (1 - float(_FEE_MONTHLY))

        running_ath = max(running_ath, eq_level)
        is_ath = eq_level >= running_ath
        is_underwater = eq_level < running_ath

        _append(
            current_date.strftime("%Y-%m-%d"),
            eq_level,
            bond_level,
            running_ath,
            is_ath,
            is_underwater,
        )

        if current_date.month == 12:
            current_date = current_date.replace(year=current_date.year + 1, month=1)
        else:
            current_date = current_date.replace(month=current_date.month + 1)

    # Forward projection (2016-10 through 2075-11)
    eq_monthly_forward = (1 + _EQUITY_FORWARD_ANNUAL) ** (1 / 12) - 1
    bond_monthly_forward = -float(_FEE_MONTHLY)
    bond_monthly_forward_after = (1 + _BOND_FORWARD_ANNUAL_AFTER) ** (1 / 12) - 1

    months_into_projection = 0
    while current_date <= _PROJECTION_END:
        if months_into_projection == 0:
            r_eq = eq_return_map.get("01-09-2016", 0.0)
            r_bond = bond_return_map.get("01-09-2016", 0.0)
            eq_level *= (1 + r_eq) * (1 - float(_FEE_MONTHLY))
            bond_level *= (1 + r_bond) * (1 - float(_FEE_MONTHLY))
        else:
            eq_level *= (1 + eq_monthly_forward)
            if months_into_projection < _BOND_FORWARD_DELAY_MONTHS:
                bond_level *= (1 + bond_monthly_forward)
            else:
                bond_level *= (1 + bond_monthly_forward_after)

        running_ath = max(running_ath, eq_level)
        is_ath = eq_level >= running_ath
        is_underwater = eq_level < running_ath

        _append(
            current_date.strftime("%Y-%m-%d"),
            eq_level,
            bond_level,
            running_ath,
            is_ath,
            is_underwater,
        )

        months_into_projection += 1
        if current_date.month == 12:
            current_date = current_date.replace(year=current_date.year + 1, month=1)
        else:
            current_date = current_date.replace(month=current_date.month + 1)

    return Dataset(snapshots=tuple(snapshots), frequency="monthly")
