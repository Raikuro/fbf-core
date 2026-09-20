"""ERN canonical dataset loader.

Reconstructs the runtime Dataset from canonical CSV sources:

- ``spx_tr_real.csv`` — S&P 500 TR real returns (ISO date format)
- ``bond_10y_tr_real.csv`` — 10-Year Bond Market real returns (ISO date format)
- ``cpi.csv`` — CPI levels (ISO date format, used for interest-rate inflation adjustment)

Source: ERN SWR Toolbox Google Sheet, Asset Returns tab.
  https://docs.google.com/spreadsheets/d/1QGrMm6XSGWBVLI8I_DOAeJV5whoCnSdmaR8toQB2Jz8

The loader owns all CSV-specific details: filenames, forward-projection
rules, and derived market state (ATH, underwater).  The dataset contains
raw ERN market/index data with no fee embedding; the 0.05% p.a. ERN
portfolio fee is applied at the portfolio/study level (expense_ratio).
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

_EQUITY_CSV = "spx_tr_real.csv"
_BOND_CSV = "bond_10y_tr_real.csv"
_CPI_CSV = "cpi.csv"

# ---------------------------------------------------------------------------
# Base snapshot constants (index 0, 1871-01-31)
# ---------------------------------------------------------------------------

_EQUITY_BASE_SNAPSHOT = Decimal("101.169089694984")
_BOND_BASE_SNAPSHOT = Decimal("100.747178470726")

# ---------------------------------------------------------------------------
# First data point constants (index 1, 1871-02-01)
# ---------------------------------------------------------------------------

_EQUITY_BASE = Decimal("100")
_BOND_BASE = Decimal("100")

# ---------------------------------------------------------------------------
# Forward projection constants (ERN canonical — Part 1 §4, Dec 7 2016)
# ---------------------------------------------------------------------------
_EQUITY_FORWARD_ANNUAL = Decimal("0.066")  # 6.6% real p.a.
_BOND_FORWARD_ANNUAL = Decimal("0")  # 0% real p.a. for first 120 months
_BOND_FORWARD_ANNUAL_AFTER = Decimal("0.026")  # 2.6% real p.a. after month 120
_BOND_FORWARD_DELAY_MONTHS = 120  # 10 years = 120 months
_HISTORICAL_END = datetime(2016, 10, 1)  # first forward month
_PROJECTION_END = datetime(2075, 11, 1)


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------


def _load_csv(path: Path) -> list[tuple[str, Decimal]]:
    """Load a canonical date,value CSV.

    Accepts both YYYY-MM-DD and DD-MM-YYYY formats for backward
    compatibility.  Dates are normalised to ``YYYY-MM-DD`` on load.
    """
    rows: list[tuple[str, Decimal]] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        # Accept either header format
        assert header in (
            ["date", "value"],
            ["DD-MM-YYYY", "value"],
        ), f"Unexpected header: {header}"
        for row in reader:
            if len(row) >= 2 and row[1].strip():
                raw_date = row[0].strip()
                # Normalise DD-MM-YYYY → YYYY-MM-DD
                if len(raw_date) == 10 and raw_date[2] == "-" and raw_date[5] == "-":
                    parts = raw_date.split("-")
                    if len(parts[0]) == 2 and len(parts[2]) == 4:
                        raw_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
                rows.append((raw_date, Decimal(row[1].strip())))
    return rows


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_ern_dataset(data_dir: Path) -> Dataset:
    """Load the ERN dataset from canonical CSV sources.

    Reconstructs the runtime Dataset from equity and bond real-return CSVs,
    applying forward projections and ATH/underwater state.  The resulting
    index_levels are raw ERN market data with no fee embedding; the 0.05%
    p.a. ERN portfolio fee is applied at the portfolio/study level.

    Parameters
    ----------
    data_dir:
        Directory containing ``spx_tr_real.csv`` and
        ``bond_10y_tr_real.csv``.

    Returns
    -------
    Dataset
        Immutable market observations ready for study planning and simulation.
    """
    from fbf.core.domain.model.asset import AssetClass
    from fbf.core.domain.model.market_snapshot import MarketSnapshot

    equity_returns = _load_csv(data_dir / _EQUITY_CSV)
    bond_returns = _load_csv(data_dir / _BOND_CSV)
    cpi_returns = _load_csv(data_dir / _CPI_CSV)

    eq_return_map: dict[str, Decimal] = dict(equity_returns)
    bond_return_map: dict[str, Decimal] = dict(bond_returns)
    cpi_map: dict[str, Decimal] = dict(cpi_returns)

    eq_asset = AssetClass(id="equity", name="", description="")
    bond_asset = AssetClass(id="bond", name="", description="")

    snapshots: list[MarketSnapshot] = []

    _ONE = Decimal("1")

    def _append(
        date_str: str,
        eq: Decimal,
        bond: Decimal,
        running_ath_val: Decimal,
        is_ath_val: bool,
        is_uw_val: bool,
    ) -> None:
        cpi_value = cpi_map.get(date_str, Decimal("0"))
        snapshots.append(
            MarketSnapshot(
                date=date.fromisoformat(date_str),
                inflation=Decimal("0"),
                inflation_cumulative=cpi_value,
                is_ath=is_ath_val,
                is_underwater=is_uw_val,
                running_ath=running_ath_val,
                index_levels={
                    eq_asset: eq,
                    bond_asset: bond,
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
        date_key = f"{ret_year:04d}-{ret_month:02d}-01"
        r_eq = eq_return_map.get(date_key, Decimal("0"))
        r_bond = bond_return_map.get(date_key, Decimal("0"))

        eq_level *= (_ONE + r_eq)
        bond_level *= (_ONE + r_bond)

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
    eq_monthly_forward = (_ONE + _EQUITY_FORWARD_ANNUAL) ** (Decimal("1") / Decimal("12")) - _ONE
    bond_monthly_forward = Decimal("0")
    _bd_fwd_exp = (_ONE + _BOND_FORWARD_ANNUAL_AFTER) ** (Decimal("1") / Decimal("12"))
    bond_monthly_forward_after = _bd_fwd_exp - _ONE

    months_into_projection = 0
    while current_date <= _PROJECTION_END:
        eq_level *= (_ONE + eq_monthly_forward)
        if months_into_projection < _BOND_FORWARD_DELAY_MONTHS:
            bond_level *= (_ONE + bond_monthly_forward)
        else:
            bond_level *= (_ONE + bond_monthly_forward_after)

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
