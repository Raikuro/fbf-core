"""Fast tests for the independent ERN oracle matrix (runs by default).

These verify the pinned oracle table at ``data/ern/p49_oracle_table.csv`` is
regenerated identically by the standalone reference tool and that the published
paper anchors hold.  They do not run any simulation.
"""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

from .constants import ANCHOR_CELLS, ORACLE_CSV, load_oracle_table

REPO_ROOT = Path(__file__).resolve().parents[3]
REFERENCE_TOOL = REPO_ROOT / "tools" / "ern" / "reference_oracle.py"


def _regenerate_oracle(out: Path) -> Path:
    proc = subprocess.run(
        [sys.executable, str(REFERENCE_TOOL), "--output", str(out)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"reference_oracle failed: {proc.stderr}")
    return out


def test_pinned_oracle_matrix_matches_reference_tool(tmp_path: Path) -> None:
    """The committed oracle matrix must be exactly what the tool regenerates."""
    generated = _regenerate_oracle(tmp_path / "generated_oracle_table.csv")
    assert generated.read_text(encoding="utf-8") == ORACLE_CSV.read_text(
        encoding="utf-8"
    ), "pinned p49_oracle_table.csv is out of sync with tools/ern/reference_oracle.py"


def test_published_anchors_hold() -> None:
    """The three hard-fail acceptance anchors must match the pinned table."""
    table = load_oracle_table()
    for weight, horizon, rate, expected in ANCHOR_CELLS:
        assert table[(weight, horizon)][rate] == expected, (
            f"anchor {weight}/{horizon}/{rate} should be {expected} but oracle says "
            f"{table[(weight, horizon)][rate]}"
        )


def test_oracle_table_has_expected_shape() -> None:
    """The pinned matrix covers the full 5x4x9 grid."""
    with open(ORACLE_CSV, newline="") as f:
        rows = list(csv.reader(f))
    assert len(rows) == 1 + 20
    assert rows[0][1] == "horizon_years"
    assert len(rows[1]) == 2 + 9
