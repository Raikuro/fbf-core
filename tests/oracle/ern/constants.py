"""ERN SWR replication: constants and oracle-table access.

Source data lives in the repository under ``data/ern/`` (see the P4.9
investigation report, docs/continuity/P4_9_E2E_REPLICATION_INVESTIGATION.md):

- ``ern_real_returns_1871_2016.csv``  extracted monthly real returns (source).
- ``ern_swr_h{360,480,600,720}.json`` per-horizon datasets (derived).
- ``p49_oracle_table.csv``            pinned ERN oracle matrix (derived).

Provenance of every file is documented in Section 4 of that report.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = _REPO_ROOT / "data" / "ern"
ORACLE_CSV = DATA_DIR / "p49_oracle_table.csv"
RETURNS_CSV = DATA_DIR / "ern_real_returns_1871_2016.csv"

# ---------------------------------------------------------------------------
# E2E worker selection
# ---------------------------------------------------------------------------
# The ERN E2E runs the whole grid as ONE ``sim-retire run --workers <N>``
# subprocess.  The CLI itself supports ``--workers max`` (every available
# logical CPU) since P4.11; ``ERN_E2E_WORKERS`` remains an optional override
# for hosts that want a pinned count:
#
# - ``ERN_E2E_WORKERS`` unset       -> conservative default min(8, cpu_count())
# - ``ERN_E2E_WORKERS=N``           -> pass exactly N workers (capped to host CPUs)
# - ``ERN_E2E_WORKERS=max``         -> pass ``--workers max`` (every logical CPU)

ERN_E2E_WORKERS_ENV = "ERN_E2E_WORKERS"
ERN_E2E_MAX_WORKERS = "max"
ERN_E2E_WORKERS_BASELINE = 8


def resolve_e2e_workers(
    value: str | None = None,
    host_cpu_count: int | None = None,
) -> int:
    """Resolve the ERN E2E worker count from the ``ERN_E2E_WORKERS`` value.

    The default path (``None`` or empty) selects the conservative baseline
    ``min(ERN_E2E_WORKERS_BASELINE, cpu_count())``; the literal ``"max"``
    selects every available logical CPU (passed through to the CLI); a
    positive integer selects exactly that count (capped to host CPUs).

    Parameters
    ----------
    value:
        Raw environment value (``os.environ.get("ERN_E2E_WORKERS")``).
        ``None`` or empty selects the conservative baseline (8).  The literal
        ``"max"`` (case-insensitive) selects every available logical CPU.
        A positive integer selects exactly that many workers.
    host_cpu_count:
        Override of the host CPU count (used by unit tests for determinism).
        Defaults to ``os.cpu_count()`` with a fallback of 8 when it is None.

    Returns
    -------
    int
        The worker count for the ``ERN_E2E_WORKERS`` value.

    Raises
    ------
    ValueError
        If *value* is neither empty, ``"max"`` nor a positive integer.
    """
    cpu_count = host_cpu_count or os.cpu_count() or ERN_E2E_WORKERS_BASELINE
    if value is None:
        value = ""
    value = str(value).strip()
    if value == "":
        return min(ERN_E2E_WORKERS_BASELINE, cpu_count)
    if value.lower() == ERN_E2E_MAX_WORKERS:
        return cpu_count
    try:
        requested = int(value)
    except ValueError:
        raise ValueError(
            f"{ERN_E2E_WORKERS_ENV} must be a positive integer or "
            f"'{ERN_E2E_MAX_WORKERS}', got {value!r}"
        ) from None
    if requested <= 0:
        raise ValueError(
            f"{ERN_E2E_WORKERS_ENV} must be a positive integer or "
            f"'{ERN_E2E_MAX_WORKERS}', got {value!r}"
        )
    return min(requested, cpu_count)


# Pinned oracle matrix: {(weight, horizon_years): {rate: success_pct}}.
type OracleTable = dict[tuple[float, int], dict[float, int]]

WEIGHTS = [1.0, 0.75, 0.5, 0.25, 0.0]
HORIZON_YEARS = [30, 40, 50, 60]
RATES = [0.03, 0.0325, 0.035, 0.0375, 0.04, 0.0425, 0.045, 0.0475, 0.05]

# Full grid dimensions: 5 weights x 9 rates x 4 horizons = 180 cells.
FULL_GRID_CELLS = len(WEIGHTS) * len(RATES) * len(HORIZON_YEARS)
# Every grid cell runs over the full rolling-cohort set (1739 cohorts), so the
# full grid totals 180 x 1739 = 313,020 simulation units.
COHORTS_PER_CELL = 1739
FULL_GRID_UNITS = FULL_GRID_CELLS * COHORTS_PER_CELL

# The minimal parameter space of the ERN smoke-grid fixture
# (tests/oracle/ern/ern_smoke.yaml):
# 1 weight x 1 rate x 1 horizon (30y) x 1 target (FV=0.0)
# x 2099 cohorts = 2,099 units.
SMOKE_WEIGHTS: list[float] = [0.5]
SMOKE_RATES: list[float] = [0.04]
SMOKE_HORIZONS: list[int] = [30]
SMOKE_FV_TARGETS: list[float] = [0.0]
SMOKE_GRID_CELLS = (
    len(SMOKE_WEIGHTS) * len(SMOKE_RATES) * len(SMOKE_HORIZONS) * len(SMOKE_FV_TARGETS)
)
SMOKE_GRID_COHORTS = 2099
SMOKE_GRID_UNITS = SMOKE_GRID_CELLS * SMOKE_GRID_COHORTS

# Hard-fail acceptance anchors from the ERN paper Table 1 (Section 5.2).
ANCHOR_CELLS = [
    (0.5, 30, 0.04, 95),
    (0.5, 60, 0.04, 65),
    (0.75, 60, 0.035, 97),
]

# ---------------------------------------------------------------------------
# Part 20 — More Thoughts on Equity Glidepaths
# ---------------------------------------------------------------------------
# Extends Part 19 with 8 additional glidepaths (passive only) and
# 30-year horizons.  The full grid is:
#   32 glidepaths x 5 SWR x 2 horizons = 320 cells

# Part 19 glidepaths: (start_equity, end_equity, slope, mode)
PART19_GLIDEPATHS: list[tuple[float, float, float, str]] = [
    # 60% -> 80%
    (0.6, 0.8, 0.002, "passive"),
    (0.6, 0.8, 0.003, "passive"),
    (0.6, 0.8, 0.002, "active"),
    (0.6, 0.8, 0.003, "active"),
    # 40% -> 80%
    (0.4, 0.8, 0.003, "passive"),
    (0.4, 0.8, 0.004, "passive"),
    (0.4, 0.8, 0.003, "active"),
    (0.4, 0.8, 0.004, "active"),
    # 20% -> 80%
    (0.2, 0.8, 0.004, "passive"),
    (0.2, 0.8, 0.005, "passive"),
    (0.2, 0.8, 0.004, "active"),
    (0.2, 0.8, 0.005, "active"),
    # 80% -> 100%
    (0.8, 1.0, 0.002, "passive"),
    (0.8, 1.0, 0.003, "passive"),
    (0.8, 1.0, 0.002, "active"),
    (0.8, 1.0, 0.003, "active"),
    # 60% -> 100%
    (0.6, 1.0, 0.003, "passive"),
    (0.6, 1.0, 0.004, "passive"),
    (0.6, 1.0, 0.003, "active"),
    (0.6, 1.0, 0.004, "active"),
    # 40% -> 100%
    (0.4, 1.0, 0.004, "passive"),
    (0.4, 1.0, 0.005, "passive"),
    (0.4, 1.0, 0.004, "active"),
    (0.4, 1.0, 0.005, "active"),
]

# Part 20 additions: 8 glidepaths (passive only)
PART20_GLIDEPATHS: list[tuple[float, float, float, str]] = [
    # 30% -> 70% (Kitces/Pfau-inspired)
    (0.3, 0.7, 0.00111, "passive"),
    (0.3, 0.7, 0.002, "passive"),
    (0.3, 0.7, 0.003, "passive"),
    (0.3, 0.7, 0.004, "passive"),
    # 20% -> 60% (Low-equity variant)
    (0.2, 0.6, 0.00111, "passive"),
    (0.2, 0.6, 0.002, "passive"),
    (0.2, 0.6, 0.003, "passive"),
    (0.2, 0.6, 0.004, "passive"),
]

# Combined: Part 19 + Part 20 = 32 glidepaths
PART20_ALL_GLIDEPATHS = PART19_GLIDEPATHS + PART20_GLIDEPATHS

# Part 20 SWR values: 3.0% to 4.0% in 0.25% steps
PART20_SWR: list[float] = [0.03, 0.0325, 0.035, 0.0375, 0.04]

# Part 20 horizons
PART20_HORIZONS: list[int] = [30, 60]

# Part 20 final value target
PART20_FV_TARGET: float = 0.0

# Full Part 20 grid dimensions
PART20_GLIDEPATH_COUNT = len(PART20_ALL_GLIDEPATHS)  # 32
PART20_SWR_COUNT = len(PART20_SWR)  # 5
PART20_HORIZON_COUNT = len(PART20_HORIZONS)  # 2
PART20_GRID_CELLS = (
    PART20_GLIDEPATH_COUNT * PART20_SWR_COUNT * PART20_HORIZON_COUNT
)  # 320


def load_oracle_table(path: Path = ORACLE_CSV) -> OracleTable:
    """Load the pinned oracle matrix as ``{(weight, horizon_years): {rate: percent}}``."""
    table: OracleTable = {}
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        weight = float(row["equity_weight"])
        horizon = int(row["horizon_years"])
        table[(weight, horizon)] = {rate: int(row[f"{rate:g}"]) for rate in RATES}
    return table
