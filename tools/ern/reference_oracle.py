#!/usr/bin/env python3
"""Standalone ERN SWR reference oracle (SSRN 2920322).

This is the independent reference tool for the P4.9 black-box E2E replication.
It is a pure data-processing utility: it imports NO framework modules and is
NEVER called by the E2E test.  The E2E asserts against the pinned oracle matrix
``data/ern/p49_oracle_table.csv`` that this tool regenerates.

Inputs (source, from ERN's public SWR Toolbox Google Sheet "Asset Returns" tab,
spreadsheet id 1QGrMm6XSGWBVLI8I_DOAeJV5whoCnSdmaR8toQB2Jz8):
    data/ern/ern_real_returns_1871_2016.csv
        columns: year, month, spx_tr_real, y10_bm_real
        rows: Jan 1871 (base, empty) .. Sep 2016 (1749 months)
        spx_tr_real = S&P 500 total-return monthly REAL return
        y10_bm_real  = 10Y Treasury total-return monthly REAL return

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
from pathlib import Path

_TOOL_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TOOL_DIR.parents[1]
_DATA_DIR = _REPO_ROOT / "data" / "ern"

FEE = 0.0005
R_EQ_FWD = (1.066) ** (1 / 12) - 1.0
R_BD_FWD0 = 0.0
R_BD_FWD = (1.026) ** (1 / 12) - 1.0
START_FIRST = 1
START_LAST = 1739
REALIZED_N = 1749
MAX_INDEX = 1739 + 720 - 1
N = MAX_INDEX + 1

RATES = [0.030, 0.0325, 0.035, 0.0375, 0.040, 0.0425, 0.045, 0.0475, 0.050]
HORIZONS = {30: 360, 40: 480, 50: 600, 60: 720}
WEIGHTS = [1.0, 0.75, 0.5, 0.25, 0.0]


def load_real_returns(path: Path) -> tuple[list[float], list[float]]:
    with open(path) as f:
        rows = list(csv.reader(f))
    data = rows[1:]
    assert len(data) == 1749, len(data)
    r_eq = [float(r[2]) if r[2] else 0.0 for r in data]
    r_bd = [float(r[3]) if r[3] else 0.0 for r in data]
    r_eq[0] = r_eq[1]
    r_bd[0] = r_bd[1]
    return r_eq, r_bd


def build_extended(r_eq: list[float], r_bd: list[float]) -> tuple[list[float], list[float]]:
    eq = r_eq + [R_EQ_FWD] * (N - REALIZED_N)
    bd = r_bd + [R_BD_FWD0 if k < REALIZED_N + 120 else R_BD_FWD for k in range(REALIZED_N, N)]
    return eq, bd


def prefix_tables(eq: list[float], bd: list[float], w_eq: float) -> tuple[list[float], list[float]]:
    net = [
        (1.0 + w_eq * e + (1.0 - w_eq) * b) * (1.0 - FEE / 12.0) - 1.0
        for e, b in zip(eq, bd, strict=True)
    ]
    P = [1.0] * (N + 1)
    for k in range(N):
        P[k + 1] = P[k] * (1.0 + net[k])
    inv = [1.0 / P[k] for k in range(N + 1)]
    pre = [0.0] * (N + 2)
    for k in range(N + 1):
        pre[k + 1] = pre[k] + inv[k]
    return P, pre


def cohort_annual_swr(P: list[float], pre: list[float], start: int, T: int) -> float:
    return 12.0 / (P[start - 1] * (pre[start + T] - pre[start - 1]))


def success_rate(P: list[float], pre: list[float], T: int, x: float) -> int:
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
        ["equity_weight", "horizon_years", *[f"{r:g}" for r in RATES]]
    ]
    for w in WEIGHTS:
        P, pre = prefix_tables(eq, bd, w)
        for h in (30, 40, 50, 60):
            vals = [success_rate(P, pre, HORIZONS[h], x) for x in RATES]
            rows.append([w, h, *vals])
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=_DATA_DIR / "ern_real_returns_1871_2016.csv",
        help="Path to the extracted ERN real-returns CSV",
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
