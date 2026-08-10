"""Black-box E2E: the ``sim-retire`` CLI reproduces the ERN SWR Part 1 oracle.

Acceptance criterion (P4.9): running the public ``sim-retire`` CLI on the
committed ERN datasets yields success rates that agree with the independent
ERN oracle matrix (``data/ern/p49_oracle_table.csv``) within +/-1 percentage
point, with the three published anchors (95 / 65 / 97) as hard-fail checks.

The test exercises ONLY the public CLI as an external subprocess:
  dataset/config/study -> ``sim-retire run`` -> observable summary
  -> ``sim-retire list`` / ``export`` -> success rate -> oracle assertion.

Runtime: one study cell is ~1,739 cohort simulations (~60-120s at 4 workers)
and writes a SQLite database (~700MB) to an isolated temp HOME that is removed
after each cell.  Enable with ``RUN_ERN_E2E=1``; the full 180-cell grid also
needs ``RUN_ERN_E2E_FULL=1``.
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
    cell_name,
    load_oracle_table,
)
from .fixtures import cell_success_rate, write_study_yaml

RUN_ERN_E2E = os.environ.get("RUN_ERN_E2E") == "1"
RUN_ERN_E2E_FULL = RUN_ERN_E2E and os.environ.get("RUN_ERN_E2E_FULL") == "1"
DEFAULT_WORKERS = int(os.environ.get("ERN_E2E_WORKERS", "4"))

pytestmark = [
    pytest.mark.ern_e2e,
    pytest.mark.skipif(
        not RUN_ERN_E2E,
        reason="set RUN_ERN_E2E=1 to run the slow black-box ERN E2E",
    ),
]

TOLERANCE_PP = 1


@pytest.fixture(scope="session")
def oracle() -> dict:
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
) -> float:
    """Run one grid cell with an isolated HOME and return the success percent."""
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
    oracle: dict,
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


def test_anchor_cells_reproduce_paper(
    data_dir: Path, tmp_path: Path, oracle: dict
) -> None:
    """Hard-fail anchors: 50/50 30y 4% = 95, 50/50 60y 4% = 65, 75/25 60y 3.5% = 97."""
    for weight, horizon, rate, expected in ANCHOR_CELLS:
        got = _run_cell(data_dir, tmp_path, weight, horizon, rate, DEFAULT_WORKERS)
        assert round(got) == expected, (
            f"anchor {int(weight * 100)}/{horizon}y/{rate * 100:.2f}%: CLI {got:.2f}% "
            f"({round(got)}) vs published {expected}%"
        )


def test_smoke_grid_matches_oracle(
    data_dir: Path, tmp_path: Path, oracle: dict
) -> None:
    """A representative slice of Table 1 must agree with the oracle within +/-1pp."""
    for weight, horizon, rate, _ in SMOKE_CELLS:
        got = _run_cell(data_dir, tmp_path, weight, horizon, rate, DEFAULT_WORKERS)
        _assert_cell_matches(oracle, weight, horizon, rate, got)


@pytest.mark.skipif(
    not RUN_ERN_E2E_FULL,
    reason="set RUN_ERN_E2E_FULL=1 for the full 180-cell acceptance run",
)
def test_full_grid_matches_oracle(
    data_dir: Path, tmp_path: Path, oracle: dict
) -> None:
    """Full Table 1 grid (5 weights x 4 horizons x 9 rates = 180 cells)."""
    worst_diff = 0
    worst_cell = None
    for weight in WEIGHTS:
        for horizon in HORIZON_YEARS:
            for rate in RATES:
                got = _run_cell(data_dir, tmp_path, weight, horizon, rate, DEFAULT_WORKERS)
                expected = oracle[(weight, horizon)][rate]
                diff = abs(round(got) - expected)
                if diff > worst_diff:
                    worst_diff = diff
                    worst_cell = (weight, horizon, rate, round(got), expected)
                _assert_cell_matches(oracle, weight, horizon, rate, got)
    assert worst_diff <= TOLERANCE_PP, f"worst cell: {worst_cell}"
