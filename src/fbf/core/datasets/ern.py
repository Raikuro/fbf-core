"""ERN canonical dataset loader.

Reconstructs the runtime Dataset from canonical CSV sources:

- ``spx_tr_real.csv`` — S&P 500 TR real returns (ISO date format)
- ``spx_tr.csv`` — S&P 500 TR nominal total-return cumulative index (ISO date format)
- ``bond_10y_tr_real.csv`` — 10-Year Bond Market real returns (ISO date format)
- ``cpi.csv`` — CPI levels (ISO date format, used for interest-rate inflation adjustment)

Source: ``SWR_Toolbox_v2.0.xlsx``, ``Asset Returns`` sheet, extracted exactly
by ``tools/ern/extract_workbook_returns.py``. The workbook is the single source
of truth for production ERN data.

The loader owns all CSV-specific details: filenames, forward-projection
rules, and derived market state (ATH, underwater).  The dataset contains
raw ERN market/index data with no fee embedding; the 0.05% p.a. ERN
portfolio fee is applied at the portfolio/study level (expense_ratio).

The ATH/underwater state is computed from the NOMINAL total-return
equity index (spx_tr.csv) per ERN methodology. The real-return equity
levels are used for portfolio simulation returns.
"""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal, localcontext
from pathlib import Path

from fbf.core.domain.model.dataset import Dataset

# ---------------------------------------------------------------------------
# Canonical CSV filenames
# ---------------------------------------------------------------------------

_EQUITY_CSV = "spx_tr_real.csv"
_NOMINAL_EQUITY_CSV = "spx_tr.csv"
_BOND_CSV = "bond_10y_tr_real.csv"
_CPI_CSV = "cpi.csv"

# ---------------------------------------------------------------------------
# First data point constants (index 1, 1871-02-01)
# ---------------------------------------------------------------------------

_EQUITY_BASE = Decimal("100")
_BOND_BASE = Decimal("100")

# The dataset is fee-free; expense ratios are applied by the execution layer.
# The base snapshot level is derived from the first workbook return so the
# first interval reproduces the workbook's February 1871 return exactly.

# ---------------------------------------------------------------------------
# Forward projection constants (SWR Toolbox v2.0 workbook, Parameters B787:B790)
# ---------------------------------------------------------------------------

_EQUITY_FORWARD_ANNUAL = Decimal("0.04")  # 4.0% real p.a. for first 120 months
_EQUITY_FORWARD_ANNUAL_AFTER = Decimal("0.055")  # 5.5% real p.a. after month 120
_BOND_FORWARD_ANNUAL = Decimal("0.025")  # 2.5% real p.a. for first 120 months
_BOND_FORWARD_ANNUAL_AFTER = Decimal("0.0225")  # 2.25% real p.a. after month 120
_FORWARD_PHASE_MONTHS = 120  # 10 years = 120 months
# Historical data boundary: actual observations through 2026-06 (per SWR Toolbox v2.0 workbook).
# Projection begins at 2026-07.
_HISTORICAL_END = datetime(2026, 7, 1)  # first forward month
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


def _build_ern_dataset(
    equity_returns: Sequence[tuple[str, Decimal]],
    bond_returns: Sequence[tuple[str, Decimal]],
    *,
    historical_end: datetime,
    projection_end: datetime,
    equity_forward_annual: Decimal,
    equity_forward_annual_after: Decimal,
    bond_forward_annual: Decimal,
    bond_forward_annual_after: Decimal,
    forward_phase_months: int,
    nominal_equity_levels: Mapping[str, Decimal] | None = None,
    cpi_levels: Mapping[str, Decimal] | None = None,
) -> Dataset:
    """Build an ERN dataset from historical return rows and projection rules.

    The first return row must be February 1871.  The base snapshot
    (1871-01-31) is derived from that return, so the first interval reproduces
    the workbook value exactly.  Historical returns are consumed through the
    month before ``historical_end``; projection begins at ``historical_end``.
    """
    from fbf.core.domain.model.asset import AssetClass
    from fbf.core.domain.model.market_snapshot import MarketSnapshot

    if len(equity_returns) != len(bond_returns):
        raise ValueError("Equity and bond return series must have equal length")
    if not equity_returns:
        raise ValueError("At least one historical return is required")
    if equity_returns[0][0] != "1871-02-01":
        raise ValueError(
            f"First historical return must be 1871-02-01, got {equity_returns[0][0]}"
        )

    eq_return_map: dict[str, Decimal] = dict(equity_returns)
    bond_return_map: dict[str, Decimal] = dict(bond_returns)
    nominal_equity_map: Mapping[str, Decimal] = nominal_equity_levels or {}
    cpi_map: Mapping[str, Decimal] = cpi_levels or {}

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

    # Base snapshot (index 0, 1871-01-31), implied by the first workbook return.
    with localcontext() as base_context:
        base_context.prec = 50
        equity_base_snapshot = _EQUITY_BASE / (_ONE + equity_returns[0][1])
        bond_base_snapshot = _BOND_BASE / (_ONE + bond_returns[0][1])

    _append(
        "1871-01-31",
        equity_base_snapshot,
        bond_base_snapshot,
        equity_base_snapshot,
        False,
        True,
    )

    # First data point (index 1, 1871-02-01)
    eq_level = _EQUITY_BASE
    bond_level = _BOND_BASE
    running_ath = eq_level
    _append("1871-02-01", eq_level, bond_level, running_ath, True, False)

    # Initialize nominal ATH tracking (once, before the monthly loop)
    nominal_running_ath = Decimal("0")

    # Historical period (1871-03 through the month before historical_end).
    # Each snapshot interval uses the return dated the same month as the
    # workbook row (e.g. the 1871-03-01 snapshot uses the 1871-03-01 return).
    current_date = datetime(1871, 3, 1)
    while current_date < historical_end:
        date_key = current_date.strftime("%Y-%m-%d")
        try:
            r_eq = eq_return_map[date_key]
            r_bond = bond_return_map[date_key]
        except KeyError as exc:
            raise ValueError(f"Missing ERN return for {date_key}") from exc

        eq_level *= (_ONE + r_eq)
        bond_level *= (_ONE + r_bond)

        running_ath = max(running_ath, eq_level)

        # Nominal equity level for ATH/underwater (ERN methodology: nominal total-return index)
        nominal_eq_level = nominal_equity_map.get(date_key, eq_level)
        nominal_running_ath = max(nominal_running_ath, nominal_eq_level)
        is_ath = nominal_eq_level >= nominal_running_ath
        is_underwater = nominal_eq_level < nominal_running_ath

        _append(
            date_key,
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

    # Forward projection.  Use the same extended precision as the workbook
    # oracle so the two implementations agree.
    with localcontext() as _projection_context:
        _projection_context.prec = 50
        eq_monthly_forward = (
            (_ONE + equity_forward_annual) ** (Decimal("1") / Decimal("12")) - _ONE
        )
        eq_monthly_forward_after = (
            (_ONE + equity_forward_annual_after) ** (Decimal("1") / Decimal("12")) - _ONE
        )
        bond_monthly_forward = (
            (_ONE + bond_forward_annual) ** (Decimal("1") / Decimal("12")) - _ONE
        )
        bond_monthly_forward_after = (
            (_ONE + bond_forward_annual_after) ** (Decimal("1") / Decimal("12")) - _ONE
        )

    months_into_projection = 0
    while current_date <= projection_end:
        if months_into_projection < forward_phase_months:
            eq_level *= (_ONE + eq_monthly_forward)
            bond_level *= (_ONE + bond_monthly_forward)
        else:
            eq_level *= (_ONE + eq_monthly_forward_after)
            bond_level *= (_ONE + bond_monthly_forward_after)

        running_ath = max(running_ath, eq_level)

        # Forward projection: use real eq_level as proxy for nominal level
        # (no separate nominal data available for forward months)
        nominal_eq_level = eq_level
        nominal_running_ath = max(nominal_running_ath, nominal_eq_level)
        is_ath = nominal_eq_level >= nominal_running_ath
        is_underwater = nominal_eq_level < nominal_running_ath

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


def load_ern_dataset(data_dir: Path) -> Dataset:
    """Load the ERN dataset from canonical CSV sources.

    Reconstructs the runtime Dataset from equity and bond real-return CSVs,
    applying forward projections and ATH/underwater state. The resulting
    index_levels are raw ERN market data with no fee embedding; the 0.05%
    p.a. ERN portfolio fee is applied at the portfolio/study level.

    The ATH/underwater state is computed from the NOMINAL total-return
    equity index (spx_tr.csv) per ERN methodology. The real-return equity
    levels are used for portfolio simulation returns.

    Parameters
    ----------
    data_dir:
        Directory containing ``spx_tr_real.csv``, ``spx_tr.csv``,
        ``bond_10y_tr_real.csv``, and ``cpi.csv``.

    Returns
    -------
    Dataset
        Immutable market observations ready for study planning and simulation.
    """
    equity_returns = _load_csv(data_dir / _EQUITY_CSV)
    nominal_equity_levels = _load_csv(data_dir / _NOMINAL_EQUITY_CSV)
    bond_returns = _load_csv(data_dir / _BOND_CSV)
    cpi_levels = _load_csv(data_dir / _CPI_CSV)

    return _build_ern_dataset(
        equity_returns,
        bond_returns,
        historical_end=_HISTORICAL_END,
        projection_end=_PROJECTION_END,
        equity_forward_annual=_EQUITY_FORWARD_ANNUAL,
        equity_forward_annual_after=_EQUITY_FORWARD_ANNUAL_AFTER,
        bond_forward_annual=_BOND_FORWARD_ANNUAL,
        bond_forward_annual_after=_BOND_FORWARD_ANNUAL_AFTER,
        forward_phase_months=_FORWARD_PHASE_MONTHS,
        nominal_equity_levels=dict(nominal_equity_levels),
        cpi_levels=dict(cpi_levels),
    )
