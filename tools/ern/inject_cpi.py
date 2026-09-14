"""Inject canonical CPI data into FBF ERN datasets.

The canonical ERN interest rate formula requires CPI data:
    M41 = (1 + FFR_prev/12 + Spread/12) * (CPI_prev/CPI_curr) - 1

The FBF datasets currently have `inflation_cumulative = 0` everywhere,
which makes this CPI adjustment a no-op. This script populates the
`inflation_cumulative` field with canonical CPI values from
``data/ern/part52/cpi.csv``.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "ern"
CPI_CSV = DATA_DIR / "part52" / "cpi.csv"
DATASETS = ("ern_swr_h720.json",)


def load_canonical_cpi() -> dict[str, float]:
    """Load canonical CPI values indexed by YYYY-MM from DD-MM-YYYY,value CSV."""
    cpi_map: dict[str, float] = {}
    with open(CPI_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dd, mm, yyyy = row["DD-MM-YYYY"].split("-")
            key = f"{yyyy}-{mm}"
            cpi_map[key] = float(row["value"])
    return cpi_map


def inject_cpi(path: Path, cpi_map: dict[str, float]) -> None:
    """Inject CPI data into one dataset file."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    snapshots = raw["snapshots"]
    injected = 0
    for snap in snapshots:
        ym = snap["date"][:7]  # "YYYY-MM"
        if ym in cpi_map:
            cpi_val = cpi_map[ym]
            old_val = snap.get("inflation_cumulative", "0")
            if old_val == "0" or old_val == 0:
                snap["inflation_cumulative"] = str(cpi_val)
                injected += 1
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    print(f"  {path.name}: injected CPI into {injected}/{len(snapshots)} snapshots")


def main() -> int:
    print("Loading canonical CPI data...")
    cpi_map = load_canonical_cpi()
    print(f"  {len(cpi_map)} CPI values loaded ({min(cpi_map.keys())} to {max(cpi_map.keys())})")

    print("Injecting CPI into datasets...")
    for name in DATASETS:
        inject_cpi(DATA_DIR / name, cpi_map)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
