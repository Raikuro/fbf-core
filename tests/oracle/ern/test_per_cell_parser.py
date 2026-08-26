"""Fast tests for the grid per-cell summary parser (runs by default)."""

from __future__ import annotations

import pytest

from .fixtures import parse_per_cell_lines

_CELL = (
    "cell: equity_allocation=0.75 withdrawal_rate=0.04 horizon_years=60 "
    "units_run=1739 units_failed=264 success_rate=0.8482"
)
_CELL2 = (
    "cell: equity_allocation=0.5 withdrawal_rate=0.05 horizon_years=30 "
    "units_run=1739 units_failed=85 success_rate=0.9511"
)


_CELL_FV = (
    "cell: equity_allocation=0.5 withdrawal_rate=0.04 horizon_years=30 "
    "final_value_target=100.0 units_run=1739 units_failed=105 success_rate=0.9396"
)


def test_parses_cells_into_parameter_keyed_stats() -> None:
    cells = parse_per_cell_lines(f"{_CELL}\n{_CELL2}\n{_CELL_FV}\n")
    assert set(cells) == {
        (0.75, 0.04, 60, None),
        (0.5, 0.05, 30, None),
        (0.5, 0.04, 30, 100.0),
    }
    stats = cells[(0.75, 0.04, 60, None)]
    assert stats.units_run == 1739
    assert stats.units_failed == 264
    assert stats.success_rate == pytest.approx(0.8482)
    assert stats.success_percent == pytest.approx(84.82)
    assert stats.final_value_target is None

    stats_fv = cells[(0.5, 0.04, 30, 100.0)]
    assert stats_fv.final_value_target == 100.0


def test_empty_output_parses_to_empty() -> None:
    assert parse_per_cell_lines("") == {}
    assert parse_per_cell_lines("Status: SUCCESS\n") == {}


def test_malformed_token_raises() -> None:
    with pytest.raises(ValueError, match="Malformed per-cell token"):
        parse_per_cell_lines("cell: equity_allocation units_run=1739\n")


def test_missing_field_raises() -> None:
    with pytest.raises(ValueError, match="missing fields"):
        parse_per_cell_lines("cell: equity_allocation=0.5 units_run=1739\n")


def test_duplicate_cell_raises() -> None:
    with pytest.raises(ValueError, match="Duplicate cell"):
        parse_per_cell_lines(f"{_CELL}\n{_CELL}\n")


def test_duplicate_field_in_one_line_raises() -> None:
    with pytest.raises(ValueError, match="Duplicate field"):
        parse_per_cell_lines(
            "cell: equity_allocation=0.5 equity_allocation=0.5 "
            "withdrawal_rate=0.04 horizon_years=60 units_run=1739 "
            "units_failed=1 success_rate=0.9994\n"
        )
