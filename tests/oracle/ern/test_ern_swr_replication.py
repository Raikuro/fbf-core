"""Black-box E2E: the ``sim-retire`` CLI reproduces the ERN SWR Part 1 oracle.

Acceptance criterion (P4.9, extended by P4.11): running the public ``sim-retire``
CLI on the committed ERN datasets yields success rates that agree with the
independent ERN oracle matrix (``data/ern/p49_oracle_table.csv``) within +/-1
percentage point, with the three published anchors (95 / 65 / 97) as hard-fail
checks.

The test exercises ONLY the public CLI as an external subprocess, exactly as a
user would:

  ``sim-retire --data-dir data/ern run <grid.yaml> --workers max
  --no-persist --summary-only``

The whole ERN SWR grid is a SINGLE study: one YAML, one ResearchPlan of
313,020 units, one subprocess, one observable summary with one
machine-parseable ``cell:`` line per parameter configuration.  The test parses
those lines, maps each to ``(equity_allocation, withdrawal_rate, horizon_years)``
and compares every cell against the pinned oracle.

The grid runs in non-persistent, summary-only mode: no SQLite study database is
created and per-month timelines are never materialized or transferred.

Enable with ``RUN_ERN_E2E=1``; the full 180-cell grid also needs
``RUN_ERN_E2E_FULL=1``.  The fast-path acceptance check needs
``ERN_E2E_FAST_PATH=1``.  Reference Chained is the sole reference execution
strategy (the no-flag default and ``--reference-chained`` are identical).
The default worker selection when ``ERN_E2E_WORKERS`` is unset is the
conservative ``min(8, cpu_count)``;
``ERN_E2E_WORKERS=N`` pins an exact override count and ``ERN_E2E_WORKERS=max``
requests every available logical CPU.
"""

from __future__ import annotations

import os
import time
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path

import pytest

from tests.oracle.cli_harness import CliHarness

from .constants import (
    ANCHOR_CELLS,
    COHORTS_PER_CELL,
    DATA_DIR,
    ERN_E2E_MAX_WORKERS,
    ERN_E2E_WORKERS_ENV,
    FULL_GRID_CELLS,
    FULL_GRID_UNITS,
    HORIZON_YEARS,
    RATES,
    SMOKE_GRID_CELLS,
    SMOKE_GRID_UNITS,
    SMOKE_HORIZONS,
    SMOKE_RATES,
    SMOKE_WEIGHTS,
    WEIGHTS,
    OracleTable,
    load_oracle_table,
    resolve_e2e_workers,
)
from .fixtures import PerCellStats, run_grid_study

RUN_ERN_E2E = os.environ.get("RUN_ERN_E2E") == "1"
RUN_ERN_E2E_FULL = RUN_ERN_E2E and os.environ.get("RUN_ERN_E2E_FULL") == "1"
FAST_PATH_ENABLED = os.environ.get("ERN_E2E_FAST_PATH") == "1"

pytestmark = [
    pytest.mark.ern_e2e,
    pytest.mark.skipif(
        not RUN_ERN_E2E,
        reason="set RUN_ERN_E2E=1 to run the slow black-box ERN E2E",
    ),
]

GRID_YAML = Path("examples/studies/ern_grid.yaml").resolve()
SMOKE_GRID_YAML = Path(__file__).resolve().parent / "ern_grid_smoke.yaml"

_PERCENT_SCALE = Decimal("1")
_ROUNDING = ROUND_HALF_EVEN


def _resolve_workers_arg() -> str:
    """The ``--workers`` value for a run.

    ``ERN_E2E_WORKERS`` unset → the conservative default ``min(8, cpu_count)``;
    ``ERN_E2E_WORKERS=N`` pins an exact count (capped to host CPUs);
    ``ERN_E2E_WORKERS=max`` requests every available logical CPU.
    """
    value = os.environ.get(ERN_E2E_WORKERS_ENV, "").strip()
    if value == "":
        return str(resolve_e2e_workers(value))
    if value.lower() == ERN_E2E_MAX_WORKERS:
        return ERN_E2E_MAX_WORKERS
    return str(resolve_e2e_workers(value))


def _expected_cell_keys(
    weights: list[float],
    rates: list[float],
    horizons: list[int],
) -> set[tuple[float, float, int]]:
    """The exact parameter space a grid run must report as cell keys."""
    return {(float(w), float(r), int(h)) for w in weights for r in rates for h in horizons}


@pytest.fixture(scope="session")
def oracle() -> OracleTable:
    return load_oracle_table()


@pytest.fixture(scope="session")
def data_dir() -> Path:
    path = Path(DATA_DIR).resolve()
    assert path.is_dir(), f"ERN data directory missing: {path}"
    return path


def _assert_anchors(
    oracle: OracleTable, cells: dict[tuple[float, float, int], PerCellStats]
) -> None:
    """Hard-fail on any anchor present in the grid summary.

    Anchors not in the reported cell set are skipped: the full grid's structural
    assertion already requires every 5x9x4 combination (so the 75/60/3.5%
    anchor cannot be missing there), while reduced smoke grids cover a subset.
    """
    for weight, horizon, rate, expected in ANCHOR_CELLS:
        stats = cells.get((weight, rate, horizon))
        if stats is None:
            continue
        got = round(stats.success_percent)
        assert got == expected, (
            f"anchor {int(weight * 100)}/{horizon}y/{rate * 100:.2f}%: "
            f"CLI {got}% vs published {expected}%"
        )


def _assert_cell_matches(
    oracle: OracleTable, key: tuple[float, float, int], stats: PerCellStats
) -> None:
    weight, rate, horizon = key
    expected = oracle[(weight, horizon)][rate]
    # The canonical matrix serializes whole percentage points using Python's
    # half-even rounding. Derive that serialized value from integer engine
    # outcomes using Decimal only; no binary float or tolerance is involved.
    actual = (
        Decimal(stats.units_run - stats.units_failed)
        * Decimal("100")
        / Decimal(stats.units_run)
    ).quantize(_PERCENT_SCALE, rounding=_ROUNDING)
    assert actual == Decimal(expected), (
        f"cell {int(weight * 100)}/{horizon}y/{rate * 100:.2f}%: engine "
        f"{actual}%, canonical oracle {expected}%"
    )


def test_smoke_grid_matches_oracle(data_dir: Path, tmp_path: Path, oracle: OracleTable) -> None:
    """The reduced single-plan smoke grid reproduces the oracle.

    Exercises the same one-subprocess / one-plan / per-cell-summary architecture
    as the full grid at a fraction of the chained-Reference wall time.  The two
    smoke anchors hard-fail; every other smoke cell is held to the +/-1pp
    tolerance.
    """
    harness = CliHarness(data_dir=data_dir, home_dir=tmp_path / "home")
    workers = _resolve_workers_arg()
    result, cells = run_grid_study(harness, SMOKE_GRID_YAML, workers, timeout=900)

    assert result.units_run == SMOKE_GRID_UNITS, (
        f"smoke grid ran {result.units_run:,} units, expected {SMOKE_GRID_UNITS:,}"
    )
    expected_keys = _expected_cell_keys(SMOKE_WEIGHTS, SMOKE_RATES, SMOKE_HORIZONS)
    assert set(cells) == expected_keys, (
        f"smoke grid reported {len(cells)} cells; expected {SMOKE_GRID_CELLS} "
        f"matching the declared parameter space"
    )
    assert all(stats.units_run == COHORTS_PER_CELL for stats in cells.values())

    _assert_anchors(oracle, cells)
    for key, stats in cells.items():
        _assert_cell_matches(oracle, key, stats)


@pytest.mark.skipif(
    not RUN_ERN_E2E_FULL,
    reason="set RUN_ERN_E2E_FULL=1 for the full 180-cell acceptance run",
)
def test_full_grid_matches_oracle(data_dir: Path, tmp_path: Path, oracle: OracleTable) -> None:
    """Full Table 1 grid (5 weights x 9 rates x 4 horizons = 180 cells).

    The whole grid is ONE CLI subprocess: one plan, one summary, 180 per-cell
    lines.  Emits an acceptance report: wall time, worker count, per-cell
    deviations (min/max), total simulation units, observed throughput, the
    hard-fail anchors, and any cell outside the +/-1 pp tolerance.
    """
    harness = CliHarness(data_dir=data_dir, home_dir=tmp_path / "home")
    workers = _resolve_workers_arg()
    start = time.perf_counter()
    result, cells = run_grid_study(harness, GRID_YAML, workers, timeout=3600)
    elapsed = time.perf_counter() - start

    # --- Structural invariants -------------------------------------------
    assert result.units_run == FULL_GRID_UNITS, (
        f"full grid ran {result.units_run:,} units, expected {FULL_GRID_UNITS:,}"
    )
    expected_keys = _expected_cell_keys(WEIGHTS, RATES, HORIZON_YEARS)
    assert set(cells) == expected_keys, (
        f"full grid reported {len(cells)} cells; expected exactly "
        f"{FULL_GRID_CELLS} covering the 5x9x4 parameter space (missing, "
        f"unexpected or duplicated cells fail here)"
    )
    assert len(cells) == FULL_GRID_CELLS
    # Every declared weight, rate and horizon must be represented.
    assert {key[0] for key in cells} == {float(w) for w in WEIGHTS}
    assert {key[1] for key in cells} == {float(r) for r in RATES}
    assert {key[2] for key in cells} == set(HORIZON_YEARS)
    assert all(stats.units_run == COHORTS_PER_CELL for stats in cells.values())

    # --- Oracle comparison --------------------------------------------------
    deviations: list[Decimal] = []
    outside: list[tuple[float, int, float, Decimal, int]] = []
    anchor_results: dict[str, tuple[int, int]] = {}
    for key, stats in sorted(cells.items()):
        weight, rate, horizon = key
        expected = oracle[(weight, horizon)][rate]
        actual = (
            Decimal(stats.units_run - stats.units_failed)
            * Decimal("100")
            / Decimal(stats.units_run)
        ).quantize(_PERCENT_SCALE, rounding=_ROUNDING)
        dev = abs(actual - Decimal(expected))
        deviations.append(dev)
        if dev != 0:
            outside.append((weight, horizon, rate, actual, expected))
        for aw, ah, ar, aexp in ANCHOR_CELLS:
            if (weight, rate, horizon) == (aw, ar, ah):
                anchor_results[f"{int(weight * 100)}/{horizon}y/{ar * 100:.2f}%"] = (
                    round(stats.success_percent),
                    aexp,
                )
        _assert_cell_matches(oracle, key, stats)

    _assert_anchors(oracle, cells)
    worst_diff = max(deviations)
    min_diff = min(deviations)

    print("\n" + "=" * 62)
    print("P4.9/P4.11 FULL-GRID ACCEPTANCE REPORT (single plan)")
    print("=" * 62)
    print(f"Cells reported:     {len(cells)}/{FULL_GRID_CELLS}")
    print(f"Workers:            {workers} (resolved by CLI: --workers {workers})")
    print(f"Wall time:          {elapsed:.0f}s ({time.strftime('%H:%M:%S', time.gmtime(elapsed))})")
    print(f"Total units:        {result.units_run:,}")
    print(
        f"Throughput:         {result.units_run / elapsed:.0f} units/s "
        f"({elapsed / result.units_run:.5f} s/unit)"
    )
    print("Subprocesses:       1")
    print(f"Abs deviation min:  {min_diff} pp")
    print(f"Abs deviation max:  {worst_diff} pp")
    print("Anchors (hard-fail):")
    for name, (got, exp) in anchor_results.items():
        print(f"  {name}: CLI={got}% oracle={exp}% ({'PASS' if got == exp else 'FAIL'})")
    if outside:
        print(f"Cells outside exact Decimal equality: {len(outside)}")
        for cell in outside:
            print(f"  {cell}")
    else:
        print("Cells outside exact Decimal equality: 0")
    print("=" * 62)
    assert len(cells) == FULL_GRID_CELLS
    assert worst_diff == 0, f"mismatched cells: {sorted(outside, reverse=True)}"


@pytest.mark.skipif(
    not (RUN_ERN_E2E_FULL and FAST_PATH_ENABLED),
    reason="set RUN_ERN_E2E_FULL=1 and ERN_E2E_FAST_PATH=1 for the full-grid "
    "fast-path equivalence check",
)
def test_full_grid_fast_path_reproduces_reference_success_rates(
    data_dir: Path, tmp_path: Path
) -> None:
    """Full-grid reference vs fast-path equivalence across all 180 cells.

    The complete 180-cell grid is executed twice through the public CLI
    (the default Reference Chained path, which is bit-exact with the canonical
    engine, then ``--fast-path`` with horizon chaining) and every per-cell
    statistic is compared.  This extends the smoke-level fast-path equivalence
    check to the full parameter space; oracle comparison stays on the
    reference-path tests.
    """
    harness = CliHarness(data_dir=data_dir, home_dir=tmp_path / "home_fast_full")
    workers = _resolve_workers_arg()
    ref_result, ref_cells = run_grid_study(harness, GRID_YAML, workers, timeout=3600)
    fast_result, fast_cells = run_grid_study(
        harness, GRID_YAML, workers, timeout=3600, fast_path=True
    )

    assert ref_result.units_run == fast_result.units_run == FULL_GRID_UNITS
    assert set(ref_cells) == set(fast_cells)
    assert len(ref_cells) == FULL_GRID_CELLS
    for key in sorted(ref_cells):
        assert ref_cells[key] == fast_cells[key], (
            f"cell {key}: reference {ref_cells[key].success_percent:.2f}% vs "
            f"fast path {fast_cells[key].success_percent:.2f}%"
        )


@pytest.mark.skipif(
    not FAST_PATH_ENABLED,
    reason="set ERN_E2E_FAST_PATH=1 to run the fast-path acceptance cells",
)
def test_fast_path_reproduces_reference_success_rates(data_dir: Path, tmp_path: Path) -> None:
    """The closed-form fast path must reproduce the reference engine exactly.

    Runs the smoke grid twice through the public CLI (reference then
    ``--fast-path``) and asserts every per-cell statistic is identical.  This is
    a pure optimization-equivalence check; oracle comparison stays on the
    reference-path tests above.
    """
    harness = CliHarness(data_dir=data_dir, home_dir=tmp_path / "home_fast")
    workers = _resolve_workers_arg()
    ref_result, ref_cells = run_grid_study(harness, SMOKE_GRID_YAML, workers, timeout=900)
    fast_result, fast_cells = run_grid_study(
        harness, SMOKE_GRID_YAML, workers, timeout=900, fast_path=True
    )

    assert ref_result.units_run == fast_result.units_run == SMOKE_GRID_UNITS
    assert set(ref_cells) == set(fast_cells)
    for key in ref_cells:
        assert ref_cells[key] == fast_cells[key], (
            f"cell {key}: reference {ref_cells[key].success_percent:.2f}% vs "
            f"fast path {fast_cells[key].success_percent:.2f}%"
        )
