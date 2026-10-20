#!/usr/bin/env python3
"""Standalone workbook-conformance SCR oracle.

This tool implements the SWR Toolbox v2.0 workbook methodology for an
independent workbook-conformance oracle. It is intentionally distinct from
``tools/ern/reference_oracle.py``, which preserves the frozen published-ERN
replication methodology and is not re-baselined by this tool.

It imports NO framework modules and is NEVER called by production code.
Focused unit tests exercise it directly as a standalone data-processing utility.

Workbook Methodology (SWR_Toolbox_v2.0.xlsx, "Asset Returns" and "SCR time series" sheets):

1. Historical real returns through June 2026, then forward projection from
   July 2026. Monthly forward rates use the workbook formula
   ``(1 + annual_return) ** (1 / 12) - 1``:
   - equity: 4.0% for projection months 1-120, then 5.5%
   - bonds:  2.5% for projection months 1-120, then 2.25%

2. Monthly portfolio returns with the additive expense ratio applied to the
   weighted monthly return before cumulative growth:
   AF_t = w_eq * equity_real_t + w_bd * bond_real_t - fee_annual/12

3. Forward cumulative growth factors (mathematically equivalent to workbook's
   backward AG column):
   P[0] = 1
   P[t] = P[t-1] * (1 + AF_{t-1})  for t = 1..T

4. SCR formula (from SCR time series E8):
   SCR = (AH + AJ - FV) / AI * 12
   Where:
   - AH = growth_T = P[T] (workbook's AG7/AG607)
   - AI = Sum_{t=1..T} growth_t_T = growth_T * Sum_{t=0..T-1} 1/P[t]
   - AJ = Sum(CtPt) / growth_T = 0 for basic ERN
   - FV = Final Value Target = 0 for basic ERN

   For basic ERN (Ct=1, CtPt=0, FV=0):
   SCR = AH / AI * 12 = 1 / (Sum_{t=0..T-1} 1/P[t]) * 12

5. Final wealth trajectory (from SCR time series F8):
   FV = growth_T - AI * (WR/12)
   = growth_T * (1 - (WR/12) * Sum_{t=0..T-1} 1/P[t])

This matches month-by-month simulation with additive-fee returns.
"""

from __future__ import annotations

import argparse
import csv
import sys
from decimal import Decimal, localcontext
from pathlib import Path

_TOOL_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TOOL_DIR.parents[1]
_DATA_DIR = _REPO_ROOT / "data" / "ern"

# Workbook constants (matching SWR_Toolbox_v2.0.xlsx default config)
FEE_ANNUAL = Decimal("0.0005")  # 0.05% annual expense ratio
START_FIRST = 1
START_LAST = 1739
HORIZONS = {30: 360, 40: 480, 50: 600, 60: 720}
WEIGHTS = [Decimal("1.0"), Decimal("0.75"), Decimal("0.5"), Decimal("0.25"), Decimal("0.0")]
RATES = [
    Decimal("0.030"), Decimal("0.0325"), Decimal("0.035"), Decimal("0.0375"),
    Decimal("0.040"), Decimal("0.0425"), Decimal("0.045"), Decimal("0.0475"),
    Decimal("0.050"),
]

# Workbook forward projection constants (Parameters & Main Results B787:B790)
# Historical observations end June 2026; July 2026 is projection month 1.
_HISTORICAL_END = "2026-07-01"
_PROJECTION_END = "2075-11-01"
_EXPECTED_SNAPSHOT_COUNT = 2459

_EQUITY_FORWARD_ANNUAL = Decimal("0.04")
_EQUITY_FORWARD_ANNUAL_AFTER = Decimal("0.055")
_BOND_FORWARD_ANNUAL = Decimal("0.025")
_BOND_FORWARD_ANNUAL_AFTER = Decimal("0.0225")
_FORWARD_PHASE_MONTHS = 120

# 1,739 workbook cohorts are indexed 0..1,738; the longest horizon needs 720
# monthly returns. N is the return-series length (snapshot count minus one).
N = (START_LAST - 1) + max(HORIZONS.values())

_ONE = Decimal("1")
_ZERO = Decimal("0")
_TWELVE = Decimal("12")


def _monthly_return(annual_return: Decimal) -> Decimal:
    """Convert an annual rate to the workbook monthly rate."""
    with localcontext() as ctx:
        ctx.prec = 50
        return (_ONE + annual_return) ** (_ONE / _TWELVE) - _ONE


def load_real_returns(data_dir: Path) -> tuple[list[Decimal], list[Decimal]]:
    """Load historical real equity and bond returns from canonical CSVs.

    Only rows before July 2026 are loaded. The canonical CSVs also contain
    pre-existing projected rows; those are intentionally ignored so the
    workbook-conformance projection can be appended by :func:`build_extended`.
    """

    def _load_canonical(csv_path: Path) -> list[Decimal]:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [
                Decimal(row["value"])
                for row in reader
                if row["date"] < _HISTORICAL_END
            ]

    r_eq = _load_canonical(data_dir / "spx_tr_real.csv")
    r_bd = _load_canonical(data_dir / "bond_10y_tr_real.csv")
    return r_eq, r_bd


def build_extended(
    r_eq: list[Decimal], r_bd: list[Decimal]
) -> tuple[list[Decimal], list[Decimal]]:
    """Append the workbook's two-phase forward projections to historical returns.

    Projection month 1 is July 2026. Months 1-120 use 4.0% equity / 2.5%
    bonds; month 121 onward uses 5.5% / 2.25%. Monthly rates are converted with
    ``(1 + annual_return) ** (1 / 12) - 1``.
    """
    realized_n = len(r_eq)
    projection_months = N - realized_n
    if projection_months < 0:
        raise ValueError(
            f"Historical return series has {realized_n} observations, "
            f"but the workbook oracle needs at most {N}"
        )

    eq_first = _monthly_return(_EQUITY_FORWARD_ANNUAL)
    eq_after = _monthly_return(_EQUITY_FORWARD_ANNUAL_AFTER)
    bd_first = _monthly_return(_BOND_FORWARD_ANNUAL)
    bd_after = _monthly_return(_BOND_FORWARD_ANNUAL_AFTER)

    eq_forward = [
        eq_first if month < _FORWARD_PHASE_MONTHS else eq_after
        for month in range(projection_months)
    ]
    bd_forward = [
        bd_first if month < _FORWARD_PHASE_MONTHS else bd_after
        for month in range(projection_months)
    ]
    return r_eq + eq_forward, r_bd + bd_forward


def compute_workbook_scr(
    eq_returns: list[Decimal],
    bd_returns: list[Decimal],
    w_eq: Decimal,
    start: int,  # 0-based start index
    T: int,      # horizon in months
    fee_annual: Decimal = FEE_ANNUAL,
) -> Decimal:
    """Compute workbook SCR for a single cohort.

    This implements the EXACT workbook formula:
    SCR = 1 / (Sum_{t=0..T-1} 1/P[t]) * 12

    Where P[t] = cumulative growth factor with the additive monthly fee applied
    to the weighted monthly return before growth:
    P[0] = 1
    P[t] = P[t-1] * (1 + w_eq*eq_ret + w_bd*bd_ret - fee_annual/12)
    """
    w_bd = _ONE - w_eq
    fee_monthly = fee_annual / _TWELVE

    # Build cumulative growth factors P with the additive monthly fee
    P = [_ONE]  # P[0] = 1
    for m in range(T):
        r = w_eq * eq_returns[start + m] + w_bd * bd_returns[start + m] - fee_monthly
        P.append(P[-1] * (_ONE + r))

    # SCR = 1 / (Sum_{t=0..T-1} 1/P[t]) * 12
    sum_inv_P = sum(_ONE / P[t] for t in range(T))
    scr = _ONE / sum_inv_P * _TWELVE
    return scr


def simulate_workbook_trajectory(
    eq_returns: list[Decimal],
    bd_returns: list[Decimal],
    w_eq: Decimal,
    start: int,
    T: int,
    initial_value: Decimal,
    withdrawal_rate: Decimal,
    fee_annual: Decimal = FEE_ANNUAL,
) -> tuple[bool, Decimal]:
    """Simulate the workbook trajectory for final wealth.

    The workbook (``Case Study`` sheet, note in row 6) withdraws *before*
    growing every month::

        P(t) = (P(t-1) - W(t)) * (1 + R(t))

    so the withdrawal is taken at the beginning of the period and the return is
    compounded at the end, for all ``T`` periods including the final one. The
    additive monthly fee is applied to the weighted monthly return before growth.

    Returns (success, final_wealth).
    """
    w_bd = _ONE - w_eq
    fee_monthly = fee_annual / _TWELVE
    C = initial_value * withdrawal_rate / _TWELVE
    V = initial_value

    for m in range(T):
        r = w_eq * eq_returns[start + m] + w_bd * bd_returns[start + m] - fee_monthly
        if V < C:
            return False, _ZERO
        V = V - C  # Withdraw first (workbook: P(t-1) - W(t))
        V = V * (_ONE + r)  # Then grow (workbook: * (1 + R(t)))

    return True, V


def success_rate(
    eq_returns: list[Decimal],
    bd_returns: list[Decimal],
    w_eq: Decimal,
    T: int,
    x: Decimal,
    fee_annual: Decimal = FEE_ANNUAL,
) -> int:
    """Compute success rate across the workbook's 1,739 cohorts.

    Cohort return-window starts are 0-based indices 0..1,738.
    """
    ok = 0
    for s in range(START_FIRST - 1, START_LAST):  # 0-based
        scr = compute_workbook_scr(eq_returns, bd_returns, w_eq, s, T, fee_annual)
        if scr >= x:
            ok += 1
    return round(100 * ok / (START_LAST - START_FIRST + 1))


def build_workbook_oracle_table(
    csv_path: Path,
) -> list[list[object]]:
    """Build the workbook-conformance matrix using workbook SCR methodology.

    This is independent of the production loader and of the frozen published-ERN
    replication oracle in ``tools/ern/reference_oracle.py``.
    """
    r_eq, r_bd = load_real_returns(csv_path)
    eq, bd = build_extended(r_eq, r_bd)

    rows: list[list[object]] = [
        ["equity_weight", "horizon_years", *[f"{float(r):g}" for r in RATES]]
    ]

    for w in WEIGHTS:
        for h in (30, 40, 50, 60):
            vals = [success_rate(eq, bd, w, HORIZONS[h], x) for x in RATES]
            rows.append([float(w), h, *vals])

    return rows


def validate_hand_cases() -> list[tuple[str, bool, str]]:
    """Validate against hand-verifiable cases.

    Returns list of (case_name, passed, details).
    """
    r_eq, r_bd = load_real_returns(_DATA_DIR)
    eq, bd = build_extended(r_eq, r_bd)

    results = []

    # Case 1: Simple flat returns - hand verifiable
    # Equity 0.5%/mo, Bond 0.2%/mo, 50/50, fee=0, 12 months, 4% WR
    eq_flat = [Decimal("0.005")] * 12
    bd_flat = [Decimal("0.002")] * 12
    _ = compute_workbook_scr(eq_flat, bd_flat, Decimal("0.5"), 0, 12, Decimal("0"))
    # Portfolio return = 0.5*0.005 + 0.5*0.002 = 0.0035/mo = 4.2%/yr
    # P[0]=1, P[1]=1.0035, ..., P[12]=1.0035^12
    # SCR = 1 / Sum_{t=0..11} 1/P[t] * 12
    success, fv = simulate_workbook_trajectory(
        eq_flat, bd_flat, Decimal("0.5"), 0, 12,
        Decimal("1000000"), Decimal("0.04"), Decimal("0")
    )
    results.append(("flat_returns_success", success, f"final_wealth={fv}"))

    # Case 2: Depletion case - high withdrawal over long horizon
    eq_flat_long = [Decimal("0.005")] * 120
    bd_flat_long = [Decimal("0.002")] * 120
    success, fv = simulate_workbook_trajectory(
        eq_flat_long, bd_flat_long, Decimal("0.5"), 0, 120,
        Decimal("1000000"), Decimal("0.20"), Decimal("0")
    )
    results.append(("flat_returns_depletion", not success, f"final_wealth={fv}"))

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=_DATA_DIR,
        help="Directory containing canonical real-return CSV files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_DATA_DIR / "workbook_oracle_table.csv",
        help="Output path for the workbook oracle matrix CSV",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run hand-verifiable validation cases",
    )
    args = parser.parse_args(argv)

    if args.validate:
        print("Running hand-verifiable validation cases...")
        cases = validate_hand_cases()
        all_pass = True
        for name, passed, details in cases:
            status = "PASS" if passed else "FAIL"
            print(f"  {name}: {status} ({details})")
            if not passed:
                all_pass = False
        if all_pass:
            print("All hand-verifiable cases passed.")
        else:
            print("Some validation cases FAILED.")
        return 0 if all_pass else 1

    print(f"Building workbook oracle table from {args.source}...")
    rows = build_workbook_oracle_table(args.source)
    with open(args.output, "w", newline="") as f:
        csv.writer(f).writerows(rows)
    print(f"Wrote workbook oracle matrix ({len(rows) - 1} cells) to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

