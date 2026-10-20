"""Focused tests for the standalone workbook-conformance oracle tool."""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

import pytest

from tools.ern import workbook_oracle as wo

_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "ern"


def _write_returns(path: Path, rows: list[tuple[str, str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "value"])
        writer.writerows(rows)


def test_load_real_returns_stops_after_june_2026(tmp_path: Path) -> None:
    """Historical loading includes June 2026 and excludes projected rows."""
    eq_rows = [
        ("2026-05-01", "0.01"),
        ("2026-06-01", "0.02"),
        ("2026-07-01", "0.03"),
        ("2026-08-01", "0.04"),
    ]
    bd_rows = [
        ("2026-05-01", "0.05"),
        ("2026-06-01", "0.06"),
        ("2026-07-01", "0.07"),
        ("2026-08-01", "0.08"),
    ]
    _write_returns(tmp_path / "spx_tr_real.csv", eq_rows)
    _write_returns(tmp_path / "bond_10y_tr_real.csv", bd_rows)

    r_eq, r_bd = wo.load_real_returns(tmp_path)

    assert r_eq == [Decimal("0.01"), Decimal("0.02")]
    assert r_bd == [Decimal("0.05"), Decimal("0.06")]


def test_projection_matches_workbook_phase_boundary_and_end() -> None:
    """Projection starts July 2026, switches after month 120, and ends Nov 2075."""
    r_eq, r_bd = wo.load_real_returns(_DATA_DIR)
    eq, bd = wo.build_extended(r_eq, r_bd)

    with open(_DATA_DIR / "spx_tr_real.csv", newline="", encoding="utf-8") as f:
        historical_dates = [
            row["date"] for row in csv.DictReader(f) if row["date"] < wo._HISTORICAL_END
        ]
    historical_n = len(historical_dates)

    assert historical_dates[-1] == "2026-06-01"
    assert len(r_eq) == historical_n
    assert len(eq) == len(bd) == wo.N
    assert wo.N + 1 == wo._EXPECTED_SNAPSHOT_COUNT

    eq_first = wo._monthly_return(wo._EQUITY_FORWARD_ANNUAL)
    eq_after = wo._monthly_return(wo._EQUITY_FORWARD_ANNUAL_AFTER)
    bd_first = wo._monthly_return(wo._BOND_FORWARD_ANNUAL)
    bd_after = wo._monthly_return(wo._BOND_FORWARD_ANNUAL_AFTER)

    first_projection = historical_n
    last_first_phase = first_projection + wo._FORWARD_PHASE_MONTHS - 1
    first_second_phase = first_projection + wo._FORWARD_PHASE_MONTHS

    assert eq[first_projection] == eq_first
    assert eq[last_first_phase] == eq_first
    assert eq[first_second_phase] == eq_after
    assert bd[first_projection] == bd_first
    assert bd[last_first_phase] == bd_first
    assert bd[first_second_phase] == bd_after
    assert eq[-1] == eq_after
    assert bd[-1] == bd_after

    ending_offset = wo.N - 1 - historical_n
    total_months = 2026 * 12 + 6 + ending_offset  # July 2026 = month offset 0
    year, month_index = divmod(total_months, 12)
    assert f"{year:04d}-{month_index + 1:02d}-01" == wo._PROJECTION_END


@pytest.mark.parametrize(
    ("annual_return", "expected_monthly"),
    [
        ("0.04", "0.003273739782"),
        ("0.055", "0.004471698917"),
        ("0.025", "0.002059836270"),
        ("0.0225", "0.001855937535"),
    ],
)
def test_monthly_conversion_matches_workbook_cached_values(
    annual_return: str, expected_monthly: str
) -> None:
    """Annual-to-monthly conversion matches the workbook's cached formulas."""
    monthly = wo._monthly_return(Decimal(annual_return))
    assert monthly.quantize(Decimal("0.000000000001")) == Decimal(expected_monthly)


def test_expense_ratio_is_additive_to_weighted_monthly_return() -> None:
    """The annual fee is subtracted from the weighted monthly return before growth."""
    eq_returns = [Decimal("0.01"), Decimal("0.01")]
    bd_returns = [Decimal("0.005"), Decimal("0.005")]
    weight = Decimal("0.5")
    fee = Decimal("0.0005")

    net = weight * eq_returns[0] + (Decimal("1") - weight) * bd_returns[0] - fee / Decimal("12")
    p1 = Decimal("1") + net
    expected = Decimal("1") / (Decimal("1") + Decimal("1") / p1) * Decimal("12")

    actual = wo.compute_workbook_scr(eq_returns, bd_returns, weight, 0, 2, fee)
    zero_fee = wo.compute_workbook_scr(eq_returns, bd_returns, weight, 0, 2, Decimal("0"))

    assert actual == expected
    assert actual < zero_fee
