"""Grid per-cell summary parser for the ERN oracle tests.

Each machine-parseable ``cell: ...`` line printed by the CLI is keyed by
``(equity_allocation, withdrawal_rate, horizon_years)`` and parsed into
a ``PerCellStats`` aggregate.

``run_grid_study`` (which requires a CLI harness) lives in ``fbf-cli``'s
``tests/oracle/ern/fixtures.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_CELL_LINE_RE = re.compile(r"^cell: (.*)$", re.MULTILINE)

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
