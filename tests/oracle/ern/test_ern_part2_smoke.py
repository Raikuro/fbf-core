"""R4 smoke E2E: final-value target semantics through the public CLI.

Exercises the newly implemented ``final_value_target`` criterion end-to-end
via the ``sim-retire`` CLI, proving that the configuration → planning →
execution → CLI output path works correctly for the final-value success
criterion.

Acceptance criteria:
1. FV=0% cell matches the existing ERN Part 1 oracle (control anchor: 95%).
2. FV=100 cell has a strictly lower success rate (exercising the new criterion).
3. Structural invariants: correct unit count, cell count, and per-cell field
   layout.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tests.oracle.cli_harness import CliHarness

from .constants import DATA_DIR

_PART2_SMOKE_YAML = Path(__file__).resolve().parent / "ern_part2_smoke.yaml"

# ---------------------------------------------------------------------------
# Per-cell parser (handles final_value_target as an optional axis)
# ---------------------------------------------------------------------------

_CELL_LINE_RE = re.compile(r"^cell: (.*)$", re.MULTILINE)
_CELL_HEADER = "Per-Cell Results (grid):"


@dataclass(frozen=True)
class Part2CellStats:
    """Aggregate statistics for one grid cell, including final_value_target."""

    equity_allocation: float
    withdrawal_rate: float
    horizon_years: int
    final_value_target: float | None
    units_run: int
    units_failed: int
    success_rate: float

    @property
    def success_percent(self) -> float:
        return self.success_rate * 100


def _parse_part2_cells(stdout: str) -> dict[tuple[float, float, int, float | None], Part2CellStats]:
    """Parse CLI per-cell lines, including optional final_value_target axis."""
    cells: dict[tuple[float, float, int, float | None], Part2CellStats] = {}
    for match in _CELL_LINE_RE.finditer(stdout):
        fields: dict[str, str] = {}
        for token in match.group(1).split():
            name, sep, value = token.partition("=")
            if not sep or not name or not value:
                raise ValueError(f"Malformed per-cell token: {token!r}")
            fields[name] = value

        key = (
            float(fields["equity_allocation"]),
            float(fields["withdrawal_rate"]),
            int(fields["horizon_years"]),
            float(fields["final_value_target"]) if "final_value_target" in fields else None,
        )
        if key in cells:
            raise ValueError(f"Duplicate cell {key!r}")

        cells[key] = Part2CellStats(
            equity_allocation=float(fields["equity_allocation"]),
            withdrawal_rate=float(fields["withdrawal_rate"]),
            horizon_years=int(fields["horizon_years"]),
            final_value_target=(
                float(fields["final_value_target"])
                if "final_value_target" in fields
                else None
            ),
            units_run=int(fields["units_run"]),
            units_failed=int(fields["units_failed"]),
            success_rate=float(fields["success_rate"]),
        )
    return cells


# ---------------------------------------------------------------------------
# Anchors
# ---------------------------------------------------------------------------

# FV=0% control: the ERN Part 1 oracle for 50/50 30y 4% is 95%.
# With the full h720 dataset (2099 cohorts for 30y), the engine should
# reproduce this within the standard +/-1pp tolerance.
FV0_CONTROL_EXPECTED = 95
FV0_TOLERANCE_PP = 1  # percentage points

# FV=100 structural invariant: the new criterion must produce a strictly
# lower success rate than FV=0% for at least one cell, proving the criterion
# is actually evaluated.
FV100_MUST_BE_LOWER_THAN_FV0 = True


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPart2SmokeE2E:
    """R4 black-box E2E: final-value target through the public CLI."""

    def test_part2_smoke_matches_oracle_and_exercises_fv_criterion(
        self, tmp_path: Path
    ) -> None:
        """The Part 2 smoke grid reproduces the FV=0% oracle and exercises FV=100.

        Runs the ``sim-retire`` CLI on the committed Part 2 smoke YAML and
        validates:
        1. FV=0% cell matches the ERN Part 1 oracle anchor (95% +/- 1pp).
        2. FV=100 cell has a strictly lower success rate (proving the new
           final-value criterion is active).
        3. Structural invariants: correct unit count, cell count, per-cell
           field layout including ``final_value_target``.
        """
        harness = CliHarness(data_dir=Path(DATA_DIR), home_dir=tmp_path / "home")
        result = harness.run(
            [
                "run",
                str(_PART2_SMOKE_YAML),
                "--workers",
                "4",
                "--no-persist",
                "--summary-only",
            ],
            timeout=600,
        )

        assert result.exit_code == 0, (
            f"sim-retire run failed (exit={result.exit_code}): "
            f"{result.stderr or result.stdout}"
        )
        assert _CELL_HEADER in result.stdout, (
            f"CLI output missing '{_CELL_HEADER}' section"
        )

        cells = _parse_part2_cells(result.stdout)
        assert len(cells) == 2, (
            f"Expected 2 cells (FV=0 + FV=100), got {len(cells)}: {list(cells.keys())}"
        )

        # --- Structural invariants ---
        total_units = sum(c.units_run for c in cells.values())
        assert total_units > 0, "No units were executed"

        # --- FV=0% control anchor ---
        fv0_key = (0.5, 0.04, 30, 0.0)
        assert fv0_key in cells, (
            f"FV=0% cell {fv0_key} missing from output; "
            f"available keys: {list(cells.keys())}"
        )
        fv0 = cells[fv0_key]
        assert fv0.units_run > 0
        fv0_pct = round(fv0.success_percent)
        assert abs(fv0_pct - FV0_CONTROL_EXPECTED) <= FV0_TOLERANCE_PP, (
            f"FV=0% cell: got {fv0_pct}%, expected {FV0_CONTROL_EXPECTED}% "
            f"+/- {FV0_TOLERANCE_PP}pp"
        )

        # --- FV=100 exercises the new criterion ---
        fv100_key = (0.5, 0.04, 30, 100.0)
        assert fv100_key in cells, (
            f"FV=100 cell {fv100_key} missing from output; "
            f"available keys: {list(cells.keys())}"
        )
        fv100 = cells[fv100_key]
        assert fv100.units_run == fv0.units_run, (
            f"FV=100 units_run ({fv100.units_run}) != "
            f"FV=0 units_run ({fv0.units_run})"
        )
        if FV100_MUST_BE_LOWER_THAN_FV0:
            assert fv100.success_rate < fv0.success_rate, (
                f"FV=100 success_rate ({fv100.success_rate:.4f}) must be "
                f"strictly lower than FV=0 ({fv0.success_rate:.4f}) to prove "
                f"the final-value criterion is active"
            )

        # --- Per-cell field layout includes final_value_target ---
        assert "final_value_target" in result.stdout, (
            "CLI output does not include final_value_target in cell lines"
        )
