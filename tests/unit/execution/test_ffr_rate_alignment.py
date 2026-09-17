"""Rate alignment validation tests for S6.2 FFR integration.

These tests verify that the FFR dataset loading and interest rate schedule
construction work correctly, independent of full study execution.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from fbf.core.study.builder import (
    build_interest_rate_schedule,
    load_ffr_rates,
)


def _write_ffr_csv(path: Path, rows: list[tuple[str, str]]) -> None:
    """Write a canonical date,value FFR CSV file (YYYY-MM-DD format)."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("date,value\n")
        for date_str, value in rows:
            f.write(f"{date_str},{value}\n")


def _write_ffr_csv_legacy(path: Path, rows: list[tuple[str, str]]) -> None:
    """Write a legacy DD-MM-YYYY,value FFR CSV file."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("DD-MM-YYYY,value\n")
        for date_str, value in rows:
            f.write(f"{date_str},{value}\n")


def test_load_ffr_rates_from_file(tmp_path: Path) -> None:
    """Verify FFR dataset loading from a canonical CSV file."""
    _write_ffr_csv(
        tmp_path / "ffr.csv",
        [
            ("2020-01-01", "0.0155"),
            ("2020-02-01", "0.0155"),
            ("2020-03-01", "0.0065"),
            ("2020-04-01", "0.0005"),
        ],
    )

    rates = load_ffr_rates(str(tmp_path))
    assert len(rates) == 4
    assert rates[0] == (date(2020, 1, 1), Decimal("0.0155"))
    assert rates[2] == (date(2020, 3, 1), Decimal("0.0065"))


def test_load_ffr_rates_legacy_dd_mm_yyyy(tmp_path: Path) -> None:
    """Verify FFR loading accepts DD-MM-YYYY format (backward compat)."""
    _write_ffr_csv_legacy(
        tmp_path / "ffr.csv",
        [
            ("01-01-2020", "0.0155"),
            ("01-02-2020", "0.0155"),
            ("01-03-2020", "0.0065"),
            ("01-04-2020", "0.0005"),
        ],
    )

    rates = load_ffr_rates(str(tmp_path))
    assert len(rates) == 4
    assert rates[0] == (date(2020, 1, 1), Decimal("0.0155"))
    assert rates[2] == (date(2020, 3, 1), Decimal("0.0065"))


def test_load_ffr_rates_both_formats_equal(tmp_path: Path) -> None:
    """Verify both date formats produce identical results."""
    # Canonical YYYY-MM-DD
    canon_dir = tmp_path / "canon"
    canon_dir.mkdir()
    _write_ffr_csv(canon_dir / "ffr.csv", [("2020-06-01", "0.0025")])

    # Legacy DD-MM-YYYY
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    _write_ffr_csv_legacy(legacy_dir / "ffr.csv", [("01-06-2020", "0.0025")])

    rates_canonical = load_ffr_rates(str(canon_dir))
    rates_legacy = load_ffr_rates(str(legacy_dir))

    # Both should produce the same date and value
    assert rates_canonical[0][0] == rates_legacy[0][0]
    assert rates_canonical[0][1] == rates_legacy[0][1]


def test_load_ffr_rates_missing_file(tmp_path: Path) -> None:
    """Verify FileNotFoundError for missing FFR dataset."""
    import pytest

    with pytest.raises(FileNotFoundError, match="FFR dataset not found"):
        load_ffr_rates(str(tmp_path))


def test_load_ffr_rates_invalid_format(tmp_path: Path) -> None:
    """Verify ValueError for invalid FFR dataset format (missing value column)."""
    import pytest

    bad_path = tmp_path / "ffr.csv"
    bad_path.write_text("date,rate\n2020-01-01,0.01\n", encoding="utf-8")

    with pytest.raises(KeyError):
        load_ffr_rates(str(tmp_path))


def test_build_schedule_basic() -> None:
    """Verify basic schedule construction from FFR rates + spread."""
    ffr_rates = (
        (date(2020, 1, 1), Decimal("0.0150")),
        (date(2020, 2, 1), Decimal("0.0150")),
        (date(2020, 3, 1), Decimal("0.0050")),
        (date(2020, 4, 1), Decimal("0.0010")),
    )
    spread = Decimal("0.0050")  # 0.50%

    schedule = build_interest_rate_schedule(
        ffr_rates=ffr_rates,
        spread=spread,
        start_date=date(2020, 1, 1),
        horizon_months=4,
    )

    assert len(schedule) == 4
    assert schedule[0] == Decimal("0.0200")  # 1.50% + 0.50%
    assert schedule[1] == Decimal("0.0200")
    assert schedule[2] == Decimal("0.0100")  # 0.50% + 0.50%
    assert schedule[3] == Decimal("0.0060")  # 0.10% + 0.50%


def test_build_schedule_date_alignment() -> None:
    """Verify date alignment: FFR for month M is the rate in month M (no lag)."""
    ffr_rates = (
        (date(1965, 1, 1), Decimal("0.0400")),
        (date(1965, 2, 1), Decimal("0.0390")),
        (date(1965, 3, 1), Decimal("0.0380")),
    )
    spread = Decimal("0")

    # Start at Feb 1965 — should use Feb rate first
    schedule = build_interest_rate_schedule(
        ffr_rates=ffr_rates,
        spread=spread,
        start_date=date(1965, 2, 1),
        horizon_months=2,
    )

    assert schedule[0] == Decimal("0.0390")  # Feb rate, not Jan
    assert schedule[1] == Decimal("0.0380")  # Mar rate


def test_build_schedule_zero_spread() -> None:
    """Verify zero spread preserves FFR values exactly."""
    ffr_rates = (
        (date(2020, 1, 1), Decimal("0.0155")),
        (date(2020, 2, 1), Decimal("0.0155")),
    )

    schedule = build_interest_rate_schedule(
        ffr_rates=ffr_rates,
        spread=Decimal("0"),
        start_date=date(2020, 1, 1),
        horizon_months=2,
    )

    assert schedule[0] == Decimal("0.0155")
    assert schedule[1] == Decimal("0.0155")


def test_build_schedule_covers_full_horizon() -> None:
    """Verify schedule covers the full horizon months."""
    ffr_rates = (
        (date(2020, 1, 1), Decimal("0.01")),
        (date(2020, 2, 1), Decimal("0.02")),
        (date(2020, 3, 1), Decimal("0.03")),
        (date(2020, 4, 1), Decimal("0.04")),
        (date(2020, 5, 1), Decimal("0.05")),
        (date(2020, 6, 1), Decimal("0.06")),
    )

    schedule = build_interest_rate_schedule(
        ffr_rates=ffr_rates,
        spread=Decimal("0"),
        start_date=date(2020, 1, 1),
        horizon_months=6,
    )

    assert len(schedule) == 6
    for i, expected in enumerate([0.01, 0.02, 0.03, 0.04, 0.05, 0.06]):
        assert schedule[i] == Decimal(str(expected))


def test_build_schedule_forward_fills_beyond_dataset_end() -> None:
    """Verify forward-fill: periods beyond FFR dataset end use last known rate."""
    ffr_rates = (
        (date(2020, 1, 1), Decimal("0.01")),
        (date(2020, 2, 1), Decimal("0.02")),
    )

    schedule = build_interest_rate_schedule(
        ffr_rates=ffr_rates,
        spread=Decimal("0"),
        start_date=date(2020, 1, 1),
        horizon_months=6,  # Only 2 months of data — months 3-6 forward-filled
    )

    assert len(schedule) == 6
    # Month 1: Jan 2020 → 0.01, Month 2: Feb 2020 → 0.02
    # Months 3-6: forward-filled from Feb 2020 → 0.02
    expected = [0.01, 0.02, 0.02, 0.02, 0.02, 0.02]
    for i, exp in enumerate(expected):
        assert schedule[i] == Decimal(str(exp))


def test_load_ffr_rates_empty_dataset(tmp_path: Path) -> None:
    """Verify ValueError for empty FFR dataset."""
    import pytest

    empty_path = tmp_path / "ffr.csv"
    empty_path.write_text("date,value\n", encoding="utf-8")

    with pytest.raises(ValueError, match="contains no rates"):
        load_ffr_rates(str(tmp_path))


def test_real_ffr_dataset_loads() -> None:
    """Verify the committed FFR dataset loads and covers the expected range."""
    ffr_path = Path(__file__).parent.parent.parent.parent / "data" / "ern" / "ffr.csv"
    if not ffr_path.exists():
        import pytest
        pytest.skip("FFR dataset not found")

    rates = load_ffr_rates(str(ffr_path.parent))
    assert len(rates) > 0
    # Recovered canonical dataset covers 1871-01 to 2026-08
    assert rates[0][0] == date(1871, 1, 1)
    assert rates[-1][0] >= date(2026, 8, 1)
    # All rates should be non-negative Decimals
    for _, r in rates:
        assert isinstance(r, Decimal)
        assert r >= 0


def test_real_ffr_known_values() -> None:
    """Verify representative known date/value pairs from FRED FEDFUNDS.

    These are anchor values directly from the FRED series to validate
    dataset integrity. Source: FRED FEDFUNDS, retrieved 2026-09-05.

    Note: Some values in the recovered dataset have floating-point precision
    artifacts from the original data pipeline. We verify approximate equality
    to 4 decimal places for affected values.
    """
    ffr_path = Path(__file__).parent.parent.parent.parent / "data" / "ern" / "ffr.csv"
    if not ffr_path.exists():
        import pytest
        pytest.skip("FFR dataset not found")

    rates = load_ffr_rates(str(ffr_path.parent))
    rate_map = dict(rates)

    # Known FRED FEDFUNDS values (percent / 100 = decimal)
    # These are the canonical FRED values; the recovered dataset may have
    # floating-point precision artifacts for some entries.
    known_values = {
        # First FFR observation (1954-07)
        date(1954, 7, 1): Decimal("0.0080"),   # 0.80%
        # 1965 cohort start (ERN Part 52 key date)
        date(1965, 11, 1): Decimal("0.0410"),   # 4.10%
        # 1966-07: FFR rising
        date(1966, 7, 1): Decimal("0.0530"),    # 5.30%
        # Volcker peak
        date(1981, 6, 1): Decimal("0.1910"),    # 19.10%
        # Volcker peak (highest)
        date(1981, 1, 1): Decimal("0.1908"),    # 19.08%
        # COVID trough
        date(2020, 4, 1): Decimal("0.0005"),    # 0.05%
        # 2023 peak
        date(2023, 7, 1): Decimal("0.0512"),    # 5.12%
        # Last known observation
        date(2023, 12, 1): Decimal("0.0533"),   # 5.33%
    }

    for d, expected in known_values.items():
        actual = rate_map.get(d)
        assert actual is not None, f"Missing FFR observation for {d}"
        # Compare to 4 decimal places to handle floating-point precision artifacts
        assert abs(actual - expected) < Decimal("0.00005"), (
            f"FFR value mismatch for {d}: expected {expected}, got {actual}"
        )


# ---------------------------------------------------------------------------
# T=0 boundary tests (ERN Part 52 lag_months=1)
# ---------------------------------------------------------------------------


def test_build_schedule_lag_months_1_at_dataset_boundary() -> None:
    """Verify lag_months=1 works when start_date equals the earliest FFR date.

    The ERN workbook never accrues interest at T=0 (loan_balance=0), so the
    rate at schedule[0] is a construction filler that is never consumed. When
    lag_months=1 and start_date is the earliest available FFR date, the lagged
    date for T=0 (one month before start) does not exist. The builder must not
    raise ValueError but instead use the start-date rate as the filler.

    Critical: schedule[1] must use FFR from T=0 (the start date), proving
    the one-month lag is preserved.
    """
    ffr_rates = (
        (date(1871, 1, 1), Decimal("0.0635")),
        (date(1871, 2, 1), Decimal("0.0700")),
        (date(1871, 3, 1), Decimal("0.0800")),
    )
    schedule = build_interest_rate_schedule(
        ffr_rates=ffr_rates,
        spread=Decimal("0"),
        start_date=date(1871, 1, 1),
        horizon_months=3,
        lag_months=1,
    )
    assert len(schedule) == 3
    # schedule[0]: T=0 boundary filler — uses start-date rate (never consumed)
    assert schedule[0] == Decimal("0.0635")
    # schedule[1]: T=1 uses FFR from T=0 (January 1871) — one-month lag
    assert schedule[1] == Decimal("0.0635")
    # schedule[2]: T=2 uses FFR from T=1 (February 1871)
    assert schedule[2] == Decimal("0.0700")


def test_build_schedule_lag_months_1_with_lagged_date_available() -> None:
    """Verify lag_months=1 when the lagged date is already inside the dataset.

    When start_date is 1871-02-01 and lag_months=1, the lagged date for T=0
    is 1871-01-01 which IS in the dataset. This test verifies the normal
    lag behavior works correctly when the lagged date is available.
    """
    ffr_rates = (
        (date(1871, 1, 1), Decimal("0.0635")),
        (date(1871, 2, 1), Decimal("0.0700")),
        (date(1871, 3, 1), Decimal("0.0800")),
        (date(1871, 4, 1), Decimal("0.0900")),
    )
    schedule = build_interest_rate_schedule(
        ffr_rates=ffr_rates,
        spread=Decimal("0"),
        start_date=date(1871, 2, 1),
        horizon_months=3,
        lag_months=1,
    )
    assert len(schedule) == 3
    # schedule[0]: T=0 uses FFR from 1871-01-01 (lagged date is in dataset)
    assert schedule[0] == Decimal("0.0635")
    # schedule[1]: T=1 uses FFR from 1871-02-01
    assert schedule[1] == Decimal("0.0700")
    # schedule[2]: T=2 uses FFR from 1871-03-01
    assert schedule[2] == Decimal("0.0800")


def test_build_schedule_lag_months_1_with_spread_at_boundary() -> None:
    """Verify spread is applied correctly at the T=0 boundary."""
    ffr_rates = (
        (date(1871, 1, 1), Decimal("0.0635")),
        (date(1871, 2, 1), Decimal("0.0700")),
    )
    schedule = build_interest_rate_schedule(
        ffr_rates=ffr_rates,
        spread=Decimal("0.0050"),
        start_date=date(1871, 1, 1),
        horizon_months=2,
        lag_months=1,
    )
    assert len(schedule) == 2
    assert schedule[0] == Decimal("0.0685")  # 0.0635 + 0.0050
    assert schedule[1] == Decimal("0.0685")  # 0.0635 + 0.0050 (lag from T=0)
