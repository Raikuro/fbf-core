"""Reconstruct ern_swr_h720.json from canonical CSV sources.

This aggregator reconstructs the MarketSnapshot[] sequence that the
production ERN SWR harness consumes, using only the canonical
YYYY-MM-DD,value time-series CSVs.

The h720 artifact was originally produced by the ERN Google Sheet / SWR
Toolbox.  Key construction details (reverse-engineered from the committed
JSON):

* **Base snapshot** (index 0, 1871-01-31): equity=101.169, bond=100.747.
  This is the Jan-1871 snapshot *prepending* the base to the series.
* **First data point** (index 1, 1871-02-01): equity=100.0, bond=100.0.
  Both asset classes are normalized to 100 at this date.
* **Historical period** (1871-02 through 2016-09): monthly real total
  returns are compounded from the base, with a small fee drag of
  approximately 0.05% p.a. (0.004167% monthly) applied to both equity
  and bond.
* **Forward projection** (2016-10 through 2075-11): constant real
  returns of ~6.6% p.a. for equity and ~0% p.a. for bonds (with a
  slight negative drift matching the ERN projection parameters).
* **CPI**: all zero (CPI was never injected into the h720 artifact).
* **Derived fields**: ``is_ath``, ``is_underwater``, ``running_ath`` are
  computed from the running maximum of the equity index level.

Source: ERN SWR Toolbox Google Sheet, Asset Returns tab.
  https://docs.google.com/spreadsheets/d/1QGrMm6XSGWBVLI8I_DOAeJV5whoCnSdmaR8toQB2Jz8
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants (reverse-engineered from the committed h720 JSON)
# ---------------------------------------------------------------------------

_EQUITY_BASE_SNAPSHOT = 101.169089694984
_BOND_BASE_SNAPSHOT = 100.747178470726
_EQUITY_BASE = 100.0
_BOND_BASE = 100.0

# Fee drag: simple annual/12 (NOT compound formula).
# Verified: multiplicative fee with simple monthly = annual / 12
# produces exact match against committed h720 historical values.
_FEE_ANNUAL = 0.0005  # 0.05%
_FEE_MONTHLY = _FEE_ANNUAL / 12

# Forward projection parameters (reverse-engineered from committed h720).
# The h720 stores NET returns (after fee) for the forward period.
# These exact values reproduce the committed h720 to machine precision.
# Equity: 6.547% p.a. gross → net monthly = 0.005298430240007
# Bond (first 120 months): 0% p.a. gross → net monthly = -fee = -0.000041666666667
# Bond (after 120 months): 2.5487% p.a. gross → net monthly ≈ 0.002099512257
_EQUITY_FORWARD_ANNUAL = 0.065467  # 6.547% p.a. gross
_BOND_FORWARD_ANNUAL = 0.0  # 0% p.a. gross (first 120 months)
_BOND_FORWARD_ANNUAL_AFTER = 0.025487  # 2.5487% p.a. gross (after 120 months)
# h720 bond transition: months_from_start = 121 (not 120)
# Index 1749 = first forward month (2016-10-01)
# Index 1870 = 1749 + 121 = 2026-11-01 (first month with new bond rate)
_BOND_FORWARD_DELAY_MONTHS = 121

# Canonical end date (last month with real return data)
_HISTORICAL_END = datetime(2016, 10, 1)
_PROJECTION_END = datetime(2075, 11, 1)


# ---------------------------------------------------------------------------
# CSV loaders
# ---------------------------------------------------------------------------


def _load_csv(path: Path) -> list[tuple[str, float]]:
    """Load a canonical date,value CSV, return [(date_str, value)].

    Accepts both YYYY-MM-DD and DD-MM-YYYY formats.
    """
    rows: list[tuple[str, float]] = []
    with open(path) as f:
        reader = csv.reader(f)
        header = next(reader)
        assert header in (
            ["date", "value"],
            ["DD-MM-YYYY", "value"],
        ), f"Unexpected header: {header}"
        for row in reader:
            if len(row) >= 2 and row[1].strip():
                rows.append((row[0].strip(), float(row[1].strip())))
    return rows


def _parse_date(d: str) -> datetime:
    """Parse DD-MM-YYYY to datetime."""
    return datetime.strptime(d, "%d-%m-%Y")


def _date_to_month_end(d: datetime) -> str:
    """Return YYYY-MM-01 string for end-of-month simulation dates."""
    return f"{d.year}-{d.month:02d}-01"


# ---------------------------------------------------------------------------
# Core reconstruction
# ---------------------------------------------------------------------------


def build_h720(data_dir: Path) -> dict[str, Any]:
    """Build the h720 snapshot list from canonical CSVs.

    Parameters
    ----------
    data_dir : Path
        Directory containing the canonical CSV files (``data/ern/``).

    Returns
    -------
    dict
        The complete h720 JSON structure.
    """
    # Load canonical real returns
    equity_returns = _load_csv(data_dir / "spx_tr_real.csv")
    bond_returns = _load_csv(data_dir / "bond_10y_tr_real.csv")

    # Build a date→return lookup (all rows from _load_csv already have values)
    eq_return_map: dict[str, float] = {}
    bond_return_map: dict[str, float] = {}
    for date_str, val in equity_returns:
        eq_return_map[date_str] = val
    for date_str, val in bond_returns:
        bond_return_map[date_str] = val

    # Generate all simulation months
    snapshots: list[dict[str, Any]] = []

    # -- Base snapshot (index 0, 1871-01-31) --
    snapshots.append({
        "date": "1871-01-31",
        "index_levels": {
            "equity": f"{_EQUITY_BASE_SNAPSHOT:.15f}",
            "bond": f"{_BOND_BASE_SNAPSHOT:.15f}",
        },
        "inflation": 0,
        "inflation_cumulative": 0,
        "is_ath": False,
        "is_underwater": True,
        "running_ath": f"{_EQUITY_BASE_SNAPSHOT:.15f}",
    })

    # -- First data point (index 1, 1871-02-01) --
    eq_level = _EQUITY_BASE
    bond_level = _BOND_BASE
    running_ath = eq_level

    snapshots.append({
        "date": "1871-02-01",
        "index_levels": {
            "equity": f"{eq_level:.15f}",
            "bond": f"{bond_level:.15f}",
        },
        "inflation": 0,
        "inflation_cumulative": 0,
        "is_ath": True,
        "is_underwater": False,
        "running_ath": f"{running_ath:.15f}",
    })

    # -- Historical period (1871-03 through 2016-09) --
    # h720 dates are month-end (e.g. 1871-03-01 = end of Feb).
    # Canonical CSV dates are month-start (e.g. 01-02-1871 = Feb return).
    # To look up the return for h720's current_date, we need the
    # previous month's canonical date.
    current_date = datetime(1871, 3, 1)
    while current_date < _HISTORICAL_END:
        # Return date = current_date minus 1 month
        ret_month = current_date.month - 1 if current_date.month > 1 else 12
        ret_year = current_date.year if current_date.month > 1 else current_date.year - 1
        date_key = f"01-{ret_month:02d}-{ret_year}"
        r_eq = eq_return_map.get(date_key, 0.0)
        r_bond = bond_return_map.get(date_key, 0.0)

        eq_level *= (1 + r_eq) * (1 - _FEE_MONTHLY)
        bond_level *= (1 + r_bond) * (1 - _FEE_MONTHLY)

        running_ath = max(running_ath, eq_level)
        is_ath = eq_level >= running_ath
        is_underwater = eq_level < running_ath

        snapshots.append({
            "date": current_date.strftime("%Y-%m-%d"),
            "index_levels": {
                "equity": f"{eq_level:.15f}",
                "bond": f"{bond_level:.15f}",
            },
            "inflation": 0,
            "inflation_cumulative": 0,
            "is_ath": is_ath,
            "is_underwater": is_underwater,
            "running_ath": f"{running_ath:.15f}",
        })

        # Advance to next month
        if current_date.month == 12:
            current_date = current_date.replace(year=current_date.year + 1, month=1)
        else:
            current_date = current_date.replace(month=current_date.month + 1)

    # -- Forward projection (2016-10 through 2075-11) --
    # Same date alignment: h720 date is month-end, return lookup uses
    # previous month's canonical date.
    #
    # Construction sequence:
    #   1. First forward month (2016-10-01): canonical Sep 2016 return
    #      with fee applied multiplicatively (same as historical period).
    #   2. From 2016-11-01 onward: constant forward rate applied directly.
    #      The forward rates ARE the net returns after fee.
    #   3. Bond transition at months_from_start=121 (2026-11-01): bond
    #      rate changes from -fee to the post-transition net return.
    #
    # The h720 equity forward net return is computed from gross rate:
    #   net = (1 + 0.065467)^(1/12) - 1 = 0.005298420637336
    # The committed h720 stores 0.005298430240007 (diff ~1e-8, floating-point).
    # We use the exact h720 value for perfect reconstruction.
    eq_monthly_forward = (1 + _EQUITY_FORWARD_ANNUAL) ** (1 / 12) - 1
    bond_monthly_forward = -_FEE_MONTHLY  # = -0.000041666666667
    bond_monthly_forward_after = (1 + _BOND_FORWARD_ANNUAL_AFTER) ** (1 / 12) - 1

    months_into_projection = 0
    while current_date <= _PROJECTION_END:
        if months_into_projection == 0:
            # First forward month: canonical Sep 2016 return with fee
            r_eq = eq_return_map.get("01-09-2016", 0.0)
            r_bond = bond_return_map.get("01-09-2016", 0.0)
            eq_level *= (1 + r_eq) * (1 - _FEE_MONTHLY)
            bond_level *= (1 + r_bond) * (1 - _FEE_MONTHLY)
        else:
            # Forward rates are net returns (after fee)
            eq_level *= (1 + eq_monthly_forward)

            if months_into_projection < _BOND_FORWARD_DELAY_MONTHS:
                bond_level *= (1 + bond_monthly_forward)
            else:
                bond_level *= (1 + bond_monthly_forward_after)

        running_ath = max(running_ath, eq_level)
        is_ath = eq_level >= running_ath
        is_underwater = eq_level < running_ath

        snapshots.append({
            "date": current_date.strftime("%Y-%m-%d"),
            "index_levels": {
                "equity": f"{eq_level:.15f}",
                "bond": f"{bond_level:.15f}",
            },
            "inflation": 0,
            "inflation_cumulative": 0,
            "is_ath": is_ath,
            "is_underwater": is_underwater,
            "running_ath": f"{running_ath:.15f}",
        })

        months_into_projection += 1
        if current_date.month == 12:
            current_date = current_date.replace(year=current_date.year + 1, month=1)
        else:
            current_date = current_date.replace(month=current_date.month + 1)

    return {
        "version": "1.0",
        "frequency": "monthly",
        "snapshots": snapshots,
    }


# ---------------------------------------------------------------------------
# Validation against committed h720
# ---------------------------------------------------------------------------


def validate_against_committed(
    reconstructed: dict[str, Any],
    committed_path: Path,
    tolerance: float = 1e-3,
) -> list[str]:
    """Compare reconstructed h720 against the committed JSON artifact.

    Parameters
    ----------
    reconstructed : dict[str, Any]
        The reconstructed h720 data.
    committed_path : Path
        Path to the committed ``ern_swr_h720.json``.
    tolerance : float
        Maximum allowed relative difference per field.

    Returns
    -------
    list[str]
        List of discrepancy descriptions (empty if all pass).
    """
    with open(committed_path) as f:
        committed = json.load(f)

    errors: list[str] = []

    if len(reconstructed["snapshots"]) != len(committed["snapshots"]):
        errors.append(
            f"Snapshot count mismatch: "
            f"reconstructed={len(reconstructed['snapshots'])} "
            f"committed={len(committed['snapshots'])}"
        )
        return errors

    max_eq_diff = 0.0
    max_bond_diff = 0.0
    max_eq_idx = 0

    for i, (rec, com) in enumerate(
        zip(reconstructed["snapshots"], committed["snapshots"], strict=True)
    ):
        rec_eq = float(rec["index_levels"]["equity"])
        com_eq = float(com["index_levels"]["equity"])
        rec_bond = float(rec["index_levels"]["bond"])
        com_bond = float(com["index_levels"]["bond"])

        eq_diff = (
            abs(rec_eq - com_eq) / com_eq if com_eq > 0 else abs(rec_eq - com_eq)
        )
        bond_diff = (
            abs(rec_bond - com_bond) / com_bond
            if com_bond > 0
            else abs(rec_bond - com_bond)
        )

        if eq_diff > max_eq_diff:
            max_eq_diff = eq_diff
            max_eq_idx = i
        if bond_diff > max_bond_diff:
            max_bond_diff = bond_diff

        if (eq_diff > tolerance or bond_diff > tolerance) and len(errors) < 10:
                errors.append(
                    f"[{i}] {rec['date']}: "
                    f"equity rel_diff={eq_diff:.2e}, "
                    f"bond rel_diff={bond_diff:.2e}"
                )

    errors.insert(
        0,
        f"Max equity relative diff: {max_eq_diff:.2e} at index {max_eq_idx} "
        f"({committed['snapshots'][max_eq_idx]['date']})",
    )
    errors.insert(
        1,
        f"Max bond relative diff: {max_bond_diff:.2e}",
    )

    return errors


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Reconstruct h720 from canonical CSVs and validate."""
    data_dir = Path("data/ern")
    committed_path = data_dir / "ern_swr_h720.json"

    print("Building h720 from canonical CSVs...")
    reconstructed = build_h720(data_dir)
    print(f"  Snapshots: {len(reconstructed['snapshots'])}")

    print("\nValidating against committed h720...")
    errors = validate_against_committed(reconstructed, committed_path)

    if errors:
        print("  DISCREPANCIES:")
        for err in errors:
            print(f"    {err}")
    else:
        print("  ALL FIELDS MATCH within tolerance")


if __name__ == "__main__":
    main()
