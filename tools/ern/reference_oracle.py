#!/usr/bin/env python3
"""Standalone ERN SWR reference oracle (SSRN 2920322).

This is the independent reference tool for the P4.9 black-box E2E replication.
It is a pure data-processing utility: it imports NO framework modules and is
NEVER called by the E2E test.  The E2E asserts against the pinned oracle matrix
``data/ern/p49_oracle_table.csv`` that this tool regenerates.

Inputs (source, from ERN's public SWR Toolbox Google Sheet "Asset Returns" tab,
    spreadsheet id 1QGrMm6XSGWBVLI8I_DOAeJV5whoCnSdmaR8toQB2Jz8):
    data/ern/spx_tr_real.csv           (canonical YYYY-MM-DD,value)
        S&P 500 total-return monthly REAL return
    data/ern/bond_10y_tr_real.csv      (canonical YYYY-MM-DD,value)
        10Y Treasury total-return monthly REAL return

Methodology (ERN "Safe Withdrawal Rates"):
    - Working entirely in REAL terms, initial portfolio normalized to 1.
    - Cohorts: 1,739 monthly start dates Feb 1871 .. Dec 2015 inclusive.
    - Horizon T months; monthly rebalanced portfolio real return
          r_t = w_eq*r_eq,t + (1-w_eq)*r_bond,t
    - 0.05% p.a. fee drag applied monthly.
    - Forward extrapolation beyond Sep 2016:
          equity: (1.066)^(1/12)-1 every month (6.6% real p.a., no volatility)
          bonds : 0% real for the first 120 months, then (1.026)^(1/12)-1
    - Cumulative opportunity-cost factors (Part 8): C_t = prod_{tau=t..T}(1+r_tau)
    - Withdrawal at the BEGINNING of each month (final value at END of final month).
    - Depletion target (FV=0): monthly real withdrawal w = C_1 / sum_t C_t ; annual SWR = 12*w.
    - Success rate for rate x = share of the 1,739 cohorts with 12*w >= x.

Validated anchors (match the published Table 1 within +/-1pp):
    50/50 30y 4% = 95% ; 50/50 60y 4% = 65% ; 75/25 60y 3.5% = 97% ;
    100/0 30y 4% = 97% ; 25/75 30y 4% = 80% ; 0/100 30y 4% = 55%.
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

FEE = Decimal("0.0005")
_R_EQ_FWD_ANNUAL = Decimal("1.066")
_R_BD_FWD_ANNUAL = Decimal("1.026")
_R_BD_FWD0 = Decimal("0")
START_FIRST = 1
START_LAST = 1739
# Historical returns end Sep 2016; only the historical portion of the canonical
# CSV is loaded.  Forward projections use the constant ERN Part 1 §4 rates.
_HISTORICAL_END = "2016-10-01"
# N must cover all cohorts (1..1739) + max horizon (720 months)
MAX_INDEX = max(1739 + 720 - 1, 0)
N = MAX_INDEX + 1

RATES = [
    Decimal("0.030"), Decimal("0.0325"), Decimal("0.035"), Decimal("0.0375"),
    Decimal("0.040"), Decimal("0.0425"), Decimal("0.045"), Decimal("0.0475"),
    Decimal("0.050"),
]
HORIZONS = {30: 360, 40: 480, 50: 600, 60: 720}
WEIGHTS = [Decimal("1.0"), Decimal("0.75"), Decimal("0.5"), Decimal("0.25"), Decimal("0.0")]

_ONE = Decimal("1")
_ZERO = Decimal("0")
_TWELVE = Decimal("12")


def load_real_returns(data_dir: Path) -> tuple[list[Decimal], list[Decimal]]:
    """Load historical real equity and bond returns from canonical CSVs.

    Only rows with dates before the historical cutoff (Oct 2016) are loaded.
    Forward projections are appended separately by :func:`build_extended`.

    Parameters
    ----------
    data_dir:
        Directory containing ``spx_tr_real.csv`` and
        ``bond_10y_tr_real.csv``.
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
    with localcontext() as ctx:
        ctx.prec = 50
        realized_n = len(r_eq)
        r_eq_fwd = _R_EQ_FWD_ANNUAL ** (_ONE / _TWELVE) - _ONE
        r_bd_fwd = _R_BD_FWD_ANNUAL ** (_ONE / _TWELVE) - _ONE
    eq = r_eq + [r_eq_fwd] * (N - realized_n)
    bd = r_bd + [
        _R_BD_FWD0 if k < realized_n + 120 else r_bd_fwd
        for k in range(realized_n, N)
    ]
    return eq, bd


def prefix_tables(
    eq: list[Decimal], bd: list[Decimal], w_eq: Decimal
) -> tuple[list[Decimal], list[Decimal]]:
    with localcontext() as ctx:
        ctx.prec = 50
        w_bd = _ONE - w_eq
        fee_adj = _ONE - FEE / _TWELVE
        net = [
            (_ONE + w_eq * e + w_bd * b) * fee_adj - _ONE
            for e, b in zip(eq, bd, strict=True)
        ]
        P = [_ONE] * (N + 1)
        for k in range(N):
            P[k + 1] = P[k] * (_ONE + net[k])
        inv = [_ONE / P[k] for k in range(N + 1)]
        pre = [_ZERO] * (N + 2)
        for k in range(N + 1):
            pre[k + 1] = pre[k] + inv[k]
    return P, pre


def cohort_annual_swr(P: list[Decimal], pre: list[Decimal], start: int, T: int) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 50
        return _TWELVE / (P[start - 1] * (pre[start + T] - pre[start - 1]))


def success_rate(P: list[Decimal], pre: list[Decimal], T: int, x: Decimal) -> int:
    n = 0
    ok = 0
    for s in range(START_FIRST, START_LAST + 1):
        if cohort_annual_swr(P, pre, s, T) >= x:
            ok += 1
        n += 1
    return round(100 * ok / n)


def build_oracle_table(
    csv_path: Path,
) -> list[list[object]]:
    r_eq, r_bd = load_real_returns(csv_path)
    eq, bd = build_extended(r_eq, r_bd)
    rows: list[list[object]] = [
        ["equity_weight", "horizon_years", *[f"{float(r):g}" for r in RATES]]
    ]
    for w in WEIGHTS:
        P, pre = prefix_tables(eq, bd, w)
        for h in (30, 40, 50, 60):
            vals = [success_rate(P, pre, HORIZONS[h], x) for x in RATES]
            rows.append([float(w), h, *vals])
    return rows


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
        default=_DATA_DIR / "p49_oracle_table.csv",
        help="Output path for the oracle matrix CSV",
    )
    args = parser.parse_args(argv)

    rows = build_oracle_table(args.source)
    with open(args.output, "w", newline="") as f:
        csv.writer(f).writerows(rows)
    print(f"Wrote oracle matrix ({len(rows) - 1} cells) to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
