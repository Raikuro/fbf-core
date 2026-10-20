"""Focused tests for the standalone workbook-conformance oracle tool."""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

import pytest

from tools.ern import workbook_oracle as wo

_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "ern"


def _write_returns(path: Path, rows: list[tuple[str, str, str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "equity_real_return", "bond_real_return"])
        writer.writerows(rows)


def test_load_real_returns_stops_after_june_2026(tmp_path: Path) -> None:
    """Historical loading includes June 2026 and excludes later rows."""
    _write_returns(
        tmp_path / "workbook_returns.csv",
        [
            ("2026-05-01", "0.01", "0.05"),
            ("2026-06-01", "0.02", "0.06"),
            ("2026-07-01", "0.03", "0.07"),
            ("2026-08-01", "0.04", "0.08"),
        ],
    )

    r_eq, r_bd = wo.load_real_returns(tmp_path)

    assert r_eq == [Decimal("0.01"), Decimal("0.02")]
    assert r_bd == [Decimal("0.05"), Decimal("0.06")]


def test_projection_matches_workbook_phase_boundary_and_end() -> None:
    """Projection starts July 2026, switches after month 120, and ends Nov 2075."""
    r_eq, r_bd = wo.load_real_returns(_DATA_DIR)
    eq, bd = wo.build_extended(r_eq, r_bd)

    with open(_DATA_DIR / "workbook_returns.csv", newline="", encoding="utf-8") as f:
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


def test_workbook_fixture_matches_canonical_production_columns() -> None:
    """The combined fixture and the production real-return CSVs stay in sync."""
    with open(_DATA_DIR / "workbook_returns.csv", newline="", encoding="utf-8") as f:
        combined = list(csv.DictReader(f))
    with open(_DATA_DIR / "spx_tr_real.csv", newline="", encoding="utf-8") as f:
        equity = list(csv.DictReader(f))
    with open(_DATA_DIR / "bond_10y_tr_real.csv", newline="", encoding="utf-8") as f:
        bond = list(csv.DictReader(f))

    assert [row["date"] for row in combined] == [row["date"] for row in equity]
    assert [row["date"] for row in combined] == [row["date"] for row in bond]
    assert [row["equity_real_return"] for row in combined] == [
        row["value"] for row in equity
    ]
    assert [row["bond_real_return"] for row in combined] == [
        row["value"] for row in bond
    ]
    assert combined[0]["date"] == "1871-02-01"
    assert combined[-1]["date"] == "2026-06-01"
    assert len(combined) == 1865


def test_first_cohort_scr_matches_workbook_scr_time_series() -> None:
    """First cohort (75/25, 50y) matches the workbook's cached SCR value."""
    r_eq, r_bd = wo.load_real_returns(_DATA_DIR)
    eq, bd = wo.build_extended(r_eq, r_bd)
    scr = wo.compute_workbook_scr(eq, bd, Decimal("0.75"), 0, 600)
    assert scr.quantize(Decimal("0.0000000001")) == Decimal("0.0778554756")


def test_boundary_cell_matches_workbook_exact_returns() -> None:
    """0% equity / 30y / 3.25% is 77% with exact workbook returns."""
    r_eq, r_bd = wo.load_real_returns(_DATA_DIR)
    eq, bd = wo.build_extended(r_eq, r_bd)
    assert wo.success_rate(eq, bd, Decimal("0"), 360, Decimal("0.0325")) == 77


def test_committed_workbook_oracle_table_uses_exact_fixture() -> None:
    """The pinned workbook matrix reflects the exact workbook returns."""
    with open(
        _DATA_DIR / "workbook_oracle_table.csv", newline="", encoding="utf-8"
    ) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 20

    zero_thirty = next(
        row for row in rows
        if float(row["equity_weight"]) == 0.0 and int(row["horizon_years"]) == 30
    )
    assert [int(zero_thirty[f"{float(rate):g}"]) for rate in wo.RATES] == [
        89, 77, 64, 56, 49, 45, 41, 38, 32
    ]

    full_forty = next(
        row for row in rows
        if float(row["equity_weight"]) == 1.0 and int(row["horizon_years"]) == 40
    )
    assert int(full_forty["0.045"]) == 84
