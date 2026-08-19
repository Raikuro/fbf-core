"""Test fixtures and parser for ERN per-cell lines."""

from __future__ import annotations

import re
from dataclasses import dataclass

LINE_PATTERN = re.compile(
    r"^equity=(?P<equity>\d+)%\s+"
    r"withdrawal=(?P<withdrawal>[\d.]+)%\s+"
    r"horizon=(?P<horizon>\d+)y\s+"
    r"rate=(?P<rate>[\d.]+)%\s+"
    r"min=(?P<min>[\d.]+)\s+"
    r"max=(?P<max>[\d.]+)\s+"
    r"total=(?P<total>\d+)\s+"
    r"rate_exact=(?P<rate_exact>[\d.]+)\s*$"
)


@dataclass(frozen=True)
class PerCellStats:
    equity: float
    withdrawal: float
    horizon_years: int
    rate_percent: float
    min_multiplier: float
    max_multiplier: float
    total_cohorts: int
    rate_exact: float


def parse_per_cell_line(line: str) -> PerCellStats | None:
    match = LINE_PATTERN.match(line.strip())
    if not match:
        return None
    g = match.groupdict()
    return PerCellStats(
        equity=float(g["equity"]) / 100.0,
        withdrawal=float(g["withdrawal"]) / 100.0,
        horizon_years=int(g["horizon"]),
        rate_percent=float(g["rate"]),
        min_multiplier=float(g["min"]),
        max_multiplier=float(g["max"]),
        total_cohorts=int(g["total"]),
        rate_exact=float(g["rate_exact"]),
    )


def parse_per_cell_lines(lines: list[str]) -> list[PerCellStats]:
    stats = []
    for line in lines:
        s = parse_per_cell_line(line)
        if s is not None:
            stats.append(s)
    return stats
