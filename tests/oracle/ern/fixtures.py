"""Grid per-cell summary parser for the ERN oracle tests.

Each machine-parseable ``cell: ...`` line printed by the CLI is keyed by
all parameter fields present in the line (excluding result fields) and parsed
into a ``PerCellStats`` aggregate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_CELL_LINE_RE = re.compile(r"^cell: (.*)$", re.MULTILINE)

_CELL_HEADER = "Per-Cell Results (grid):"

# Fields that are result metrics, not parameter identifiers
_RESULT_FIELDS = (
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
    # Store all parameter fields for flexible keying
    params: dict[str, float | int | bool]
    # Backward compatibility fields
    final_value_target: float | None = None

    @property
    def success_percent(self) -> float:
        return self.success_rate * 100

    def __post_init__(self) -> None:
        # Extract final_value_target from params if not explicitly set
        if self.final_value_target is None and "final_value_target" in self.params:
            object.__setattr__(self, "final_value_target", self.params["final_value_target"])


# Type alias for the flexible cell key (sorted tuple of parameter name-value pairs)
CellKey = tuple[tuple[str, float | int | bool], ...]


def parse_per_cell_lines(
    stdout: str,
) -> dict[CellKey, PerCellStats]:
    """Parse the CLI's machine-parseable per-cell summary lines.

    Each line has the layout
    ``cell: param1=<v1> param2=<v2> ... units_run=<n> units_failed=<m> success_rate=``
    and is keyed by a sorted tuple of all non-result parameter fields.

    Raises
    ------
    ValueError
        If any cell line is malformed, missing a required field, or duplicated.
    """
    parsed: dict[tuple[tuple[str, float | int], ...], PerCellStats] = {}
    for match in _CELL_LINE_RE.finditer(stdout):
        fields: dict[str, str] = {}
        for token in match.group(1).split():
            name, sep, value = token.partition("=")
            if not sep or not name or not value:
                raise ValueError(f"Malformed per-cell token: {token!r}")
            if name in fields:
                raise ValueError(f"Duplicate field {name!r} in cell line")
            fields[name] = value
        missing = [name for name in _RESULT_FIELDS if name not in fields]
        if missing:
            raise ValueError(f"Cell line missing fields {missing}: {match.group(1)!r}")
        # Separate parameter fields from result fields
        params: dict[str, float | int | bool] = {}
        for name, value in fields.items():
            if name in _RESULT_FIELDS:
                continue
            # Try to parse as bool, int, then float
            if value.lower() == "true":
                params[name] = True
            elif value.lower() == "false":
                params[name] = False
            else:
                try:
                    params[name] = int(value)
                except ValueError:
                    params[name] = float(value)
        # Create a stable key from sorted parameter items
        key = tuple(sorted(params.items()))
        if key in parsed:
            raise ValueError(f"Duplicate cell {key!r}")
        parsed[key] = PerCellStats(
            units_run=int(fields["units_run"]),
            units_failed=int(fields["units_failed"]),
            success_rate=float(fields["success_rate"]),
            params=params,
        )
    return parsed
