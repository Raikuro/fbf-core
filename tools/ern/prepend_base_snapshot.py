"""Prepend the ERN base snapshot (d_{-1} = 1871-01-31) to the runtime JSON datasets.

The ERN timeline requires the retiree's initial withdrawal at the *previous*
month's closing price — i.e. at d_{c-1} — before the first retirement month's
return is applied.  The first cohort (retirement beginning in Feb-1871) therefore
needs a market snapshot dated 1871-01-31 that is not present in the original
datasets.

The base levels are implied from the Feb-1871 gross real returns plus the
canonical 5 bps p.a. fee drag:

    level_d_{-1} = level_Feb-1871 / ((1 + r_Feb) * (1 - fee/12))

so that the rebalanced growth d_{-1} -> d_0 reproduces the oracle's net
Feb-1871 return exactly (see tools/ern/reference_oracle.py: FEE, prefix_tables).

This is a data remediation: it must be run once, after which the four runtime
datasets expose d_{-1} for every cohort.  The oracle (reference_oracle.py) and
the pinned acceptance matrix (tests/oracle/ern/) are NOT modified.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

FEE = 0.0005
BASE_DATE = "1871-01-31"
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "ern"
CSV_PATH = DATA_DIR / "ern_real_returns_1871_2016.csv"
DATASETS = (
    "ern_swr_h360.json",
    "ern_swr_h480.json",
    "ern_swr_h600.json",
    "ern_swr_h720.json",
)


def load_february_returns() -> tuple[float, float]:
    """Feb-1871 gross real returns (equity, bond) from the canonical CSV."""
    with open(CSV_PATH, newline="") as f:
        rows = list(csv.reader(f))
    data = rows[1:]
    feb = next(r for r in data if int(r[0]) == 1871 and int(r[1]) == 2)
    return float(feb[2]), float(feb[3])


def implied_base_levels() -> tuple[float, float]:
    """Levels at d_{-1} implied from the Feb-1871 net returns (see module doc)."""
    r_eq, r_bd = load_february_returns()
    return 100.0 / ((1.0 + r_eq) * (1.0 - FEE / 12.0)), 100.0 / (
        (1.0 + r_bd) * (1.0 - FEE / 12.0)
    )


def build_base_snapshot(eq_base: float, bd_base: float) -> dict[str, object]:
    """The d_{-1} snapshot; auxiliary fields mirror the original first snapshot."""
    return {
        "date": BASE_DATE,
        "index_levels": {
            "equity": f"{eq_base:.12f}",
            "bond": f"{bd_base:.12f}",
        },
        "inflation": 0,
        "inflation_cumulative": 0,
        "is_ath": False,
        "is_underwater": True,
        "running_ath": "100.000000000000",
    }


def prepend_base(path: Path, base: dict[str, object]) -> None:
    """Prepend *base* to one dataset file (idempotent, refuses double-application)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    snapshots = raw["snapshots"]
    if snapshots[0]["date"] == BASE_DATE:
        print(f"  {path.name}: already has base snapshot, skipping")
        return
    if snapshots[0]["date"] != "1871-02-01":
        raise RuntimeError(f"Unexpected first date {snapshots[0]['date']!r} in {path.name}")
    raw["snapshots"] = [base, *snapshots]
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    print(f"  {path.name}: prepended base snapshot ({len(snapshots)} -> {len(snapshots) + 1})")


def main() -> int:
    eq_base, bd_base = implied_base_levels()
    base = build_base_snapshot(eq_base, bd_base)
    print(f"base levels: equity={eq_base:.12f} bond={bd_base:.12f}")
    for name in DATASETS:
        prepend_base(DATA_DIR / name, base)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
