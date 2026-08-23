"""Grid per-cell summary parser for the ERN oracle tests.

Each machine-parseable ``cell: ...`` line printed by the CLI is keyed by
``(equity_allocation, withdrawal_rate, horizon_years)`` and parsed into
a ``PerCellStats`` aggregate.

``run_grid_study`` is retained here as the black-box bridge used by the
optional canonical engine-to-oracle acceptance suite.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tests.oracle.cli_harness import CliHarness, CliResult

_CELL_LINE_RE = re.compile(r"^cell: (.*)$", re.MULTILINE)

_CELL_HEADER = "Per-Cell Results (grid):"

_CELL_FIELDS = (
    "equity_allocation",
    "withdrawal_rate",
    "horizon_years",
    "units_run",
    "units_failed",
    "success_rate",
)


@dataclass(frozen=True)
class PerCellStats:
    """Aggregate statistics for one grid cell, parsed from the CLI summary."""

    units_run: int
    units_failed: int
    success_rate: float

    @property
    def success_percent(self) -> float:
        return self.success_rate * 100


def parse_per_cell_lines(
    stdout: str,
) -> dict[tuple[float, float, int], PerCellStats]:
    """Parse the CLI's machine-parseable per-cell summary lines.

    Each line has the stable layout
    ``cell: equity_allocation=<w> withdrawal_rate=<r> horizon_years=<h>
    units_run=<n> units_failed=<m> success_rate=<s>`` and is keyed by
    ``(equity_allocation, withdrawal_rate, horizon_years)``.

    Raises
    ------
    ValueError
        If any cell line is malformed, missing a required field, or duplicated.
    """
    parsed: dict[tuple[float, float, int], PerCellStats] = {}
    for match in _CELL_LINE_RE.finditer(stdout):
        fields: dict[str, str] = {}
        for token in match.group(1).split():
            name, sep, value = token.partition("=")
            if not sep or not name or not value:
                raise ValueError(f"Malformed per-cell token: {token!r}")
            if name in fields:
                raise ValueError(f"Duplicate field {name!r} in cell line")
            fields[name] = value
        missing = [name for name in _CELL_FIELDS if name not in fields]
        if missing:
            raise ValueError(f"Cell line missing fields {missing}: {match.group(1)!r}")
        key = (
            float(fields["equity_allocation"]),
            float(fields["withdrawal_rate"]),
            int(fields["horizon_years"]),
        )
        if key in parsed:
            raise ValueError(f"Duplicate cell {key!r}")
        parsed[key] = PerCellStats(
            units_run=int(fields["units_run"]),
            units_failed=int(fields["units_failed"]),
            success_rate=float(fields["success_rate"]),
        )
    return parsed


def run_grid_study(
    harness: CliHarness,
    study_yaml: Path,
    workers: int | str,
    timeout: int = 3600,
    fast_path: bool = False,
    reference: bool = False,
) -> tuple[CliResult, dict[tuple[float, float, int], PerCellStats]]:
    """Run one grid through the public CLI and return validated cell output."""
    if fast_path and reference:
        raise ValueError("fast_path and reference are mutually exclusive")
    args = ["run", str(study_yaml), "--workers", str(workers), "--no-persist", "--summary-only"]
    if fast_path:
        args.append("--fast-path")
    elif reference:
        args.append("--reference")
    result = harness.run(args, timeout=timeout)
    if result.exit_code != 0:
        raise RuntimeError(
            f"sim-retire run failed (exit={result.exit_code}): {result.stderr or result.stdout}"
        )
    if _CELL_HEADER not in result.stdout:
        raise RuntimeError(f"sim-retire run printed no '{_CELL_HEADER}' section in its summary.")
    cells = parse_per_cell_lines(result.stdout)
    if not cells:
        raise RuntimeError(
            f"No per-cell lines parsed from sim-retire run (exit={result.exit_code})."
        )
    for key, stats in cells.items():
        expected_rate = 1 - stats.units_failed / stats.units_run
        if abs(stats.success_rate - expected_rate) > 1e-4:
            raise RuntimeError(
                f"cell {key}: success_rate={stats.success_rate} inconsistent with "
                f"units_failed/units_run={expected_rate:.6f}"
            )
    return result, cells
