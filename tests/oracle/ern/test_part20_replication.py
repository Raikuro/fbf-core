"""Black-box E2E: the ``sim-retire`` CLI reproduces the ERN Part 20 glidepath grid.

Canonical ERN E2E for Part 20 (More Thoughts on Equity Glidepaths).
Executes the full 320-cell grid (32 glidepaths × 5 SWR × 2 horizons)
through the production CLI and validates at three levels:

1. **Structural coverage** — 320 cells × 1,739 cohorts = 556,480 units
   are represented in the parameter space.

2. **Computational execution** — the 556,480 units are executed through
   the real simulation path and produce real outcomes (success rates,
   failure counts).

3. **Canonical replication** — the resulting behavior is demonstrably
   consistent with the ERN methodology and with traceable ERN results.

No pinned oracle table exists for Part 20 glidepaths.  Result-level
assertions use:

- Internal consistency (every cell runs exactly 1,739 cohorts)
- Success-rate non-triviality (rates vary across the grid; not all 0%
  or 100%)
- Traceable ERN anchor: 60→100% glidepath (slope=0.003, passive)
  at 3.34% SWR with FV=0.0 reports 100% success (rounded), consistent
  with the documented Part 20 observation that 3.34% is a grid-level
  value where ERN would also report 100%
- Determinism: a single-cell reproducibility check confirms identical
  results across two independent CLI invocations

Test execution model:
- ``test_part20_full_grid_replication``: canonical Research E2E (gated
  by ``RUN_ERN_E2E=1``).

Canonical E2E tests are gated behind ``RUN_ERN_E2E=1`` via the centralized
skip hook in ``tests/conftest.py``.  They are NOT part of the normal
``pytest`` invocation.
"""

from __future__ import annotations

import os
import resource
import time
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

import pytest

from tests.oracle.cli_harness import CliHarness

from .constants import (
    COHORTS_PER_CELL,
    DATA_DIR,
    ERN_E2E_MAX_WORKERS,
    ERN_E2E_WORKERS_ENV,
    PART20_ALL_GLIDEPATHS,
    PART20_GLIDEPATH_COUNT,
    PART20_GRID_CELLS,
    PART20_HORIZONS,
    PART20_SWR,
    resolve_e2e_workers,
)
from .fixtures import run_grid_study

_REPO_ROOT = Path(__file__).resolve().parents[3]
PART20_YAML = _REPO_ROOT / "examples" / "studies" / "ern_part20.yaml"

# Expected total units: 320 cells × 1,739 cohorts = 556,480
PART20_TOTAL_UNITS = PART20_GRID_CELLS * COHORTS_PER_CELL

_ROUNDING = ROUND_HALF_EVEN


@pytest.fixture(scope="session")
def data_dir() -> Path:
    path = Path(DATA_DIR).resolve()
    assert path.is_dir(), f"ERN data directory missing: {path}"
    return path


def _resolve_workers_arg() -> str:
    """The ``--workers`` value for a run."""
    value = os.environ.get(ERN_E2E_WORKERS_ENV, "").strip()
    if value == "":
        return str(resolve_e2e_workers(value))
    if value.lower() == ERN_E2E_MAX_WORKERS:
        return ERN_E2E_MAX_WORKERS
    return str(resolve_e2e_workers(value))


def _peak_rss_mb() -> float:
    """Peak RSS in MB (Linux: ru_maxrss is in KB)."""
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return usage.ru_maxrss / 1024


@pytest.mark.ern_e2e
def test_part20_full_grid_replication(data_dir: Path, tmp_path: Path) -> None:
    """Full Part 20 grid (32 glidepaths × 5 SWR × 2 horizons = 320 cells).

    Executes 556,480 simulation units through the production CLI and
    validates at three levels:

    **Level 1 — Structural coverage:**
    - 320 cells reported (32 glidepaths × 5 SWR × 2 horizons)
    - Every cell runs exactly 1,739 cohorts
    - All horizons, SWR values, and start_equity values represented

    **Level 2 — Computational execution:**
    - Every cell has a real success_rate in [0.0, 1.0]
    - Success rates vary across the grid (not all identical)
    - At least one cell has success_rate < 1.0 (not trivially all-pass)
    - At least one cell has success_rate > 0.0 (not trivially all-fail)

    **Level 3 — Canonical replication:**
    - 60→100% glidepath (slope=0.003, passive) at 3.34% SWR with FV=0.0:
      success_rate rounds to 100%, consistent with the traceable Part 20
      observation that 3.34% is a grid-level value where ERN reports 100%
    - 60→100% glidepath (slope=0.003, passive) at 4.0% SWR with FV=0.0:
      success_rate < 1.0 (higher withdrawal rate must reduce success)
    - 60-year horizon cells have lower success rates than 30-year cells
      for the same glidepath and SWR (longer horizon = harder)
    """
    harness = CliHarness(data_dir=data_dir, home_dir=tmp_path / "home")
    workers = _resolve_workers_arg()
    start = time.perf_counter()
    result, cells = run_grid_study(harness, PART20_YAML, workers, timeout=7200)
    elapsed = time.perf_counter() - start
    peak_rss = _peak_rss_mb()

    # =====================================================================
    # Level 1: Structural coverage
    # =====================================================================
    assert result.units_run == PART20_TOTAL_UNITS, (
        f"Part 20 grid ran {result.units_run:,} units, expected {PART20_TOTAL_UNITS:,}"
    )
    assert len(cells) == PART20_GRID_CELLS, (
        f"Part 20 grid reported {len(cells)} cells; expected {PART20_GRID_CELLS} "
        f"(32 glidepaths × 5 SWR × 2 horizons)"
    )

    for key, stats in cells.items():
        assert stats.units_run == COHORTS_PER_CELL, (
            f"cell {key}: ran {stats.units_run} units, expected {COHORTS_PER_CELL}"
        )

    observed_horizons = {key[2] for key in cells}
    assert observed_horizons == set(PART20_HORIZONS), (
        f"horizons: observed {observed_horizons}, expected {set(PART20_HORIZONS)}"
    )

    observed_rates = {key[1] for key in cells}
    assert observed_rates == set(PART20_SWR), (
        f"SWR values: observed {observed_rates}, expected {set(PART20_SWR)}"
    )

    observed_start_equities = {key[0] for key in cells}
    expected_start_equities = {gp[0] for gp in PART20_ALL_GLIDEPATHS}
    assert observed_start_equities == expected_start_equities, (
        f"start_equity values: observed {observed_start_equities}, "
        f"expected {expected_start_equities}"
    )

    # =====================================================================
    # Level 2: Computational execution — real outcomes produced
    # =====================================================================
    success_rates = [stats.success_rate for stats in cells.values()]

    # Every success_rate is a real float in [0.0, 1.0]
    for key, stats in cells.items():
        assert 0.0 <= stats.success_rate <= 1.0, (
            f"cell {key}: success_rate={stats.success_rate} out of [0.0, 1.0]"
        )
        # units_failed must be consistent with success_rate
        expected_rate = 1.0 - stats.units_failed / stats.units_run
        assert abs(stats.success_rate - expected_rate) < 1e-6, (
            f"cell {key}: success_rate={stats.success_rate} inconsistent with "
            f"units_failed/units_run={expected_rate:.6f}"
        )

    # Success rates vary across the grid (not all identical)
    unique_rates = set(success_rates)
    assert len(unique_rates) > 1, (
        f"all {len(cells)} cells have identical success_rate={success_rates[0]}; "
        f"expected variation across glidepaths/SWR/horizons"
    )

    # Not trivially all-pass or all-fail
    min_rate = min(success_rates)
    max_rate = max(success_rates)
    assert min_rate > 0.0, (
        "all cells have success_rate=0.0; simulation produced no successes"
    )
    assert max_rate < 1.0, (
        "all cells have success_rate=1.0; simulation produced no failures"
    )

    # =====================================================================
    # Level 3: Canonical replication — traceable ERN anchors
    # =====================================================================

    # Anchor 1: 60→100% glidepath (slope=0.003, passive) at 3.34% SWR
    # With FV=0.0 (depletion), this should report 100% success.
    # The 3.34% value is a traceable Part 20 grid-level observation
    # (not a precise mathematical failsafe).
    anchor_key: tuple[float, float, int, float] = (0.6, 0.0334, 60, 0.0)
    if anchor_key in cells:
        anchor_stats = cells[anchor_key]
        anchor_pct = Decimal(str(anchor_stats.units_run - anchor_stats.units_failed)) * Decimal(
            "100"
        ) / Decimal(str(anchor_stats.units_run))
        anchor_rounded = int(anchor_pct.quantize(Decimal("1"), rounding=_ROUNDING))
        assert anchor_rounded == 100, (
            f"60→100% slope=0.003 at 3.34% SWR (FV=0.0): "
            f"{anchor_stats.units_run - anchor_stats.units_failed}/{anchor_stats.units_run} "
            f"= {anchor_pct:.2f}% -> {anchor_rounded}%, expected 100%"
        )

    # Anchor 2: same glidepath at 4.0% must have lower success than at 3.34%
    high_rate_key: tuple[float, float, int, float] = (0.6, 0.04, 60, 0.0)
    if anchor_key in cells and high_rate_key in cells:
        rate_334 = cells[anchor_key].success_rate
        rate_400 = cells[high_rate_key].success_rate
        assert rate_400 < rate_334, (
            f"60→100% slope=0.003: 4.0% rate ({rate_400:.4f}) should be "
            f"lower than 3.34% rate ({rate_334:.4f})"
        )

    # Anchor 3: 60-year horizon has lower success than 30-year for same config
    key_60y: tuple[float, float, int, float] = (0.6, 0.035, 60, 0.0)
    key_30y: tuple[float, float, int, float] = (0.6, 0.035, 30, 0.0)
    if key_60y in cells and key_30y in cells:
        rate_60y = cells[key_60y].success_rate
        rate_30y = cells[key_30y].success_rate
        assert rate_60y < rate_30y, (
            f"60→100% slope=0.003 at 3.5%: 60y rate ({rate_60y:.4f}) should be "
            f"lower than 30y rate ({rate_30y:.4f})"
        )

    # =====================================================================
    # Acceptance report
    # =====================================================================
    print("\n" + "=" * 62)
    print("PART 20 FULL-GRID CANONICAL E2E ACCEPTANCE REPORT")
    print("=" * 62)
    print(f"Cells reported:     {len(cells)}/{PART20_GRID_CELLS}")
    print(f"Workers:            {workers}")
    print(f"Wall time:          {elapsed:.0f}s ({time.strftime('%H:%M:%S', time.gmtime(elapsed))})")
    print(f"Total units:        {result.units_run:,}")
    if elapsed > 0:
        print(
            f"Throughput:         {result.units_run / elapsed:.0f} units/s "
            f"({elapsed / result.units_run:.5f} s/unit)"
        )
    print(f"Peak RSS (children): {peak_rss:.0f} MB")
    print(f"Success rate min:   {min_rate * 100:.2f}%")
    print(f"Success rate max:   {max_rate * 100:.2f}%")
    print(f"Unique rates:       {len(unique_rates)}")
    print(f"Glidepaths:         {PART20_GLIDEPATH_COUNT}")
    print(f"SWR values:         {len(PART20_SWR)}")
    print(f"Horizons:           {PART20_HORIZONS}")
    if anchor_key in cells:
        a = cells[anchor_key]
        print(
            f"Anchor 60→100%/3.34%/60y: "
            f"{a.units_run - a.units_failed}/{a.units_run} = "
            f"{a.success_rate * 100:.2f}%"
        )
    print("=" * 62)


@pytest.mark.ern_e2e
def test_part20_determinism(data_dir: Path, tmp_path: Path) -> None:
    """Single-cell determinism check: two independent CLI invocations
    of the same glidepath/SWR/horizon produce identical results.

    This verifies that the simulation is deterministic and reproducible,
    which is a prerequisite for canonical replication.
    """
    harness = CliHarness(data_dir=data_dir, home_dir=tmp_path / "home")
    workers = _resolve_workers_arg()

    # Run the smoke YAML (single cell) twice
    smoke_yaml = Path(__file__).resolve().parent / "ern_smoke.yaml"
    _result1, cells1 = run_grid_study(harness, smoke_yaml, workers, timeout=900)
    _result2, cells2 = run_grid_study(harness, smoke_yaml, workers, timeout=900)

    assert cells1 == cells2, (
        f"determinism check failed: first run {cells1} != second run {cells2}"
    )
    assert len(cells1) >= 1, "smoke YAML produced no cells"
    for key, stats in cells1.items():
        assert stats.units_run == COHORTS_PER_CELL, (
            f"smoke cell {key}: ran {stats.units_run}, expected {COHORTS_PER_CELL}"
        )
