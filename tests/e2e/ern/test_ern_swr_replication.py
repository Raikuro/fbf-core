"""Black-box E2E: the ``sim-retire`` CLI reproduces the ERN SWR Part 1 oracle.

Acceptance criterion (P4.9): running the public ``sim-retire`` CLI on the
committed ERN datasets yields success rates that agree with the independent
ERN oracle matrix (``data/ern/p49_oracle_table.csv``) within +/-1 percentage
point, with the three published anchors (95 / 65 / 97) as hard-fail checks.

The test exercises ONLY the public CLI as an external subprocess:
  dataset/config/study -> ``sim-retire run --no-persist --summary-only``
  -> observable summary -> success rate -> oracle assertion.

Each cell runs in non-persistent, summary-only mode: no SQLite study database
is created and per-month timelines are never materialized or transferred, so
the acceptance run performs no multi-GB persistence/IO. The aggregate success
statistics are identical to the persisted path (semantics are unchanged).
Enable with ``RUN_ERN_E2E=1``; the full 180-cell grid also needs
``RUN_ERN_E2E_FULL=1``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from tests.e2e.cli_harness import CliHarness

from .constants import (
    ANCHOR_CELLS,
    DATA_DIR,
    HORIZON_YEARS,
    RATES,
    SMOKE_CELLS,
    WEIGHTS,
    OracleTable,
    cell_name,
    load_oracle_table,
)
from .fixtures import cell_success_rate, write_study_yaml

RUN_ERN_E2E = os.environ.get("RUN_ERN_E2E") == "1"
RUN_ERN_E2E_FULL = RUN_ERN_E2E and os.environ.get("RUN_ERN_E2E_FULL") == "1"
# Worker scaling is host-dependent and sub-linear. Measured benchmark on the
# development host (30y cell, --no-persist --summary-only): 1->48.3s, 2->30.3s,
# 4->22.3s, 8->22.2s (~2.2x at 8 workers; 8 adds little over 4). Results are
# identical across worker counts. 8 is the default, never exceeding the host
# core count; use ERN_E2E_WORKERS to override for a different host.
DEFAULT_WORKERS = min(int(os.environ.get("ERN_E2E_WORKERS", "8")), os.cpu_count() or 8)

pytestmark = [
    pytest.mark.ern_e2e,
    pytest.mark.skipif(
        not RUN_ERN_E2E,
        reason="set RUN_ERN_E2E=1 to run the slow black-box ERN E2E",
    ),
]

TOLERANCE_PP = 1


@pytest.fixture(scope="session")
def oracle() -> OracleTable:
    return load_oracle_table()


@pytest.fixture(scope="session")
def data_dir() -> Path:
    path = Path(DATA_DIR).resolve()
    assert path.is_dir(), f"ERN data directory missing: {path}"
    return path


def _run_cell(
    data_dir: Path,
    run_dir: Path,
    weight: float,
    horizon: int,
    rate: float,
    workers: int,
) -> tuple[float, int]:
    """Run one grid cell with an isolated HOME; return (success_pct, units_run)."""
    home = run_dir / f"home_{cell_name(weight, horizon, rate)}"
    home.mkdir()
    harness = CliHarness(data_dir=data_dir, home_dir=home)
    study_yaml = run_dir / f"{cell_name(weight, horizon, rate)}.yaml"
    write_study_yaml(study_yaml, weight, horizon, rate)
    try:
        return cell_success_rate(harness, study_yaml, workers=workers)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def _assert_cell_matches(
    oracle: OracleTable,
    weight: float,
    horizon: int,
    rate: float,
    got: float,
) -> None:
    expected = oracle[(weight, horizon)][rate]
    diff = abs(round(got) - expected)
    assert diff <= TOLERANCE_PP, (
        f"cell {int(weight * 100)}/{horizon}y/{rate * 100:.2f}%: CLI "
        f"{got:.2f}% ({round(got)}) vs oracle {expected}% (diff {diff}pp > {TOLERANCE_PP}pp)"
    )


def test_anchor_cells_reproduce_paper(data_dir: Path, tmp_path: Path, oracle: OracleTable) -> None:
    """Hard-fail anchors: 50/50 30y 4% = 95, 50/50 60y 4% = 65, 75/25 60y 3.5% = 97."""
    for weight, horizon, rate, expected in ANCHOR_CELLS:
        got, _ = _run_cell(data_dir, tmp_path, weight, horizon, rate, DEFAULT_WORKERS)
        assert round(got) == expected, (
            f"anchor {int(weight * 100)}/{horizon}y/{rate * 100:.2f}%: CLI {got:.2f}% "
            f"({round(got)}) vs published {expected}%"
        )


def test_smoke_grid_matches_oracle(data_dir: Path, tmp_path: Path, oracle: OracleTable) -> None:
    """A representative slice of Table 1 must agree with the oracle within +/-1pp."""
    for weight, horizon, rate, _ in SMOKE_CELLS:
        got, _ = _run_cell(data_dir, tmp_path, weight, horizon, rate, DEFAULT_WORKERS)
        _assert_cell_matches(oracle, weight, horizon, rate, got)


FAST_PATH_ENABLED = os.environ.get("ERN_E2E_FAST_PATH") == "1"


@pytest.mark.skipif(
    not FAST_PATH_ENABLED,
    reason="set ERN_E2E_FAST_PATH=1 to run the fast-path acceptance cells",
)
def test_fast_path_reproduces_reference_success_rates() -> None:
    """The closed-form fast path must reproduce the reference engine's success
    rates exactly on the smoke cells (same units, same result count)."""
    data_dir = Path(DATA_DIR).resolve()
    run_dir = Path("/tmp") / "ern_fast_path_acceptance"
    run_dir.mkdir(exist_ok=True)
    for weight, horizon, rate, _ in SMOKE_CELLS:
        home = run_dir / f"home_{cell_name(weight, horizon, rate)}"
        home.mkdir()
        harness = CliHarness(data_dir=data_dir, home_dir=home)
        study_yaml = run_dir / f"{cell_name(weight, horizon, rate)}.yaml"
        write_study_yaml(study_yaml, weight, horizon, rate)
        try:
            ref_rate, units = cell_success_rate(harness, study_yaml, DEFAULT_WORKERS)
            fast_rate, _ = cell_success_rate(harness, study_yaml, DEFAULT_WORKERS, fast_path=True)
            assert ref_rate == fast_rate, (
                f"cell {int(weight * 100)}/{horizon}y/{rate * 100:.2f}%: reference "
                f"{ref_rate:.2f}% vs fast path {fast_rate:.2f}% over {units} units"
            )
        finally:
            shutil.rmtree(home, ignore_errors=True)


@pytest.mark.skipif(
    not RUN_ERN_E2E_FULL,
    reason="set RUN_ERN_E2E_FULL=1 for the full 180-cell acceptance run",
)
def test_full_grid_matches_oracle(data_dir: Path, tmp_path: Path, oracle: OracleTable) -> None:
    """Full Table 1 grid (5 weights x 4 horizons x 9 rates = 180 cells).

    Emits an acceptance report: wall time, worker count, per-cell deviations
    (min/max), total simulation units, observed throughput, the hard-fail
    anchors, and any cell outside the +/-1 pp tolerance.
    """
    import time

    workers = DEFAULT_WORKERS
    start = time.perf_counter()
    deviations: list[tuple[int, float, int, float, int]] = []
    total_units = 0
    anchor_results: dict[str, tuple[float, int]] = {}
    outside = []

    for weight in WEIGHTS:
        for horizon in HORIZON_YEARS:
            for rate in RATES:
                got, units = _run_cell(data_dir, tmp_path, weight, horizon, rate, workers)
                total_units += units
                expected = oracle[(weight, horizon)][rate]
                dev = round(got) - expected
                deviations.append((abs(dev), weight, horizon, rate, round(got)))
                if abs(dev) > TOLERANCE_PP:
                    outside.append((weight, horizon, rate, round(got), expected))
                for aw, ah, ar, aexp in ANCHOR_CELLS:
                    if (weight, horizon, rate) == (aw, ah, ar):
                        anchor_results[f"{int(weight*100)}/{horizon}y/{ar*100:.2f}%"] = (
                            round(got),
                            aexp,
                        )
                _assert_cell_matches(oracle, weight, horizon, rate, got)

    elapsed = time.perf_counter() - start
    deviations_sorted = sorted(deviations)
    worst_diff, ww, wh, wr, wgot = deviations_sorted[-1]
    min_diff = deviations_sorted[0][0]
    max_diff = worst_diff
    print("\n" + "=" * 62)
    print("P4.9 FULL-GRID ACCEPTANCE REPORT")
    print("=" * 62)
    print(f"Cells run:          {len(deviations)}/180")
    print(f"Workers:            {workers}")
    print(
        f"Wall time:          {elapsed:.0f}s "
        f"({time.strftime('%H:%M:%S', time.gmtime(elapsed))})"
    )
    print(f"Total units:        {total_units:,}")
    print(
        f"Throughput:         {total_units / elapsed:.0f} units/s "
        f"({elapsed / total_units:.5f} s/unit)"
    )
    print(f"Abs deviation min:  {min_diff} pp")
    print(
        f"Abs deviation max:  {max_diff} pp "
        f"(cell {int(ww*100)}/{wh}y/{wr*100:.2f}%: CLI {wgot}% vs oracle "
        f"{oracle[(ww, wh)][wr]}%)"
    )
    print("Anchors (hard-fail):")
    for name, (got, exp) in anchor_results.items():
        print(f"  {name}: CLI={got}% oracle={exp}% " f"({'PASS' if got == exp else 'FAIL'})")
    if outside:
        print(f"Cells outside +/-{TOLERANCE_PP} pp: {len(outside)}")
        for cell in outside:
            print(f"  {cell}")
    else:
        print(f"Cells outside +/-{TOLERANCE_PP} pp: 0")
    print("=" * 62)
    assert len(deviations) == 180
    assert worst_diff <= TOLERANCE_PP, f"worst cell: {deviations_sorted[-1]}"
