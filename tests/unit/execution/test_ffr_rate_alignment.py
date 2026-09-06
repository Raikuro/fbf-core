"""Rate alignment validation tests for S6.2 FFR integration.

These tests verify that the FFR dataset loading and interest rate schedule
construction work correctly, independent of full study execution.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from fbf.core.study.builder import (
    build_interest_rate_schedule,
    load_ffr_rates,
)


def test_load_ffr_rates_from_file(tmp_path: Path) -> None:
    """Verify FFR dataset loading from a JSON file."""
    ffr_data = {
        "version": "1.0",
        "type": "ffr",
        "rates": [
            {"date": "2020-01-01", "rate": "0.0155"},
            {"date": "2020-02-01", "rate": "0.0155"},
            {"date": "2020-03-01", "rate": "0.0065"},
            {"date": "2020-04-01", "rate": "0.0005"},
        ],
    }
    ffr_path = tmp_path / "test_ffr.json"
    ffr_path.write_text(json.dumps(ffr_data), encoding="utf-8")

    rates = load_ffr_rates("test_ffr", str(tmp_path))
    assert len(rates) == 4
    assert rates[0] == (date(2020, 1, 1), Decimal("0.0155"))
    assert rates[2] == (date(2020, 3, 1), Decimal("0.0065"))


def test_load_ffr_rates_missing_file(tmp_path: Path) -> None:
    """Verify FileNotFoundError for missing FFR dataset."""
    import pytest

    with pytest.raises(FileNotFoundError, match="FFR dataset not found"):
        load_ffr_rates("nonexistent", str(tmp_path))


def test_load_ffr_rates_invalid_format(tmp_path: Path) -> None:
    """Verify ValueError for invalid FFR dataset format."""
    import pytest

    bad_data = {"version": "1.0", "rates": "not_a_list"}
    bad_path = tmp_path / "bad_ffr.json"
    bad_path.write_text(json.dumps(bad_data), encoding="utf-8")

    with pytest.raises(ValueError, match="must be a list"):
        load_ffr_rates("bad_ffr", str(tmp_path))


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


def test_build_schedule_out_of_range_raises() -> None:
    """Verify explicit failure when FFR dataset doesn't cover full horizon."""
    import pytest

    ffr_rates = (
        (date(2020, 1, 1), Decimal("0.01")),
        (date(2020, 2, 1), Decimal("0.02")),
    )

    with pytest.raises(ValueError, match="No FFR rate available"):
        build_interest_rate_schedule(
            ffr_rates=ffr_rates,
            spread=Decimal("0"),
            start_date=date(2020, 1, 1),
            horizon_months=6,  # Only 2 months of data — must fail
        )


def test_load_ffr_rates_empty_dataset(tmp_path: Path) -> None:
    """Verify ValueError for empty FFR dataset."""
    import pytest

    empty_data = {"version": "1.0", "type": "ffr", "rates": []}
    empty_path = tmp_path / "empty_ffr.json"
    empty_path.write_text(json.dumps(empty_data), encoding="utf-8")

    with pytest.raises(ValueError, match="contains no rates"):
        load_ffr_rates("empty_ffr", str(tmp_path))


def test_real_ffr_dataset_loads() -> None:
    """Verify the committed FFR dataset loads and covers the expected range."""
    ffr_path = Path(__file__).parent.parent.parent.parent / "data" / "ern" / "ffr_monthly.json"
    if not ffr_path.exists():
        import pytest
        pytest.skip("FFR dataset not found")

    rates = load_ffr_rates("ffr_monthly", str(ffr_path.parent))
    assert len(rates) > 0
    # Historical FFR covers 1928-04 to present
    assert rates[0][0] == date(1928, 4, 1)
    assert rates[-1][0] >= date(2023, 12, 1)
    # All rates should be non-negative Decimals
    for _, r in rates:
        assert isinstance(r, Decimal)
        assert r >= 0


def test_real_ffr_known_values() -> None:
    """Verify representative known date/value pairs from FRED FEDFUNDS.

    These are anchor values directly from the FRED series to validate
    dataset integrity. Source: FRED FEDFUNDS, retrieved 2026-09-05.
    """
    ffr_path = Path(__file__).parent.parent.parent.parent / "data" / "ern" / "ffr_monthly.json"
    if not ffr_path.exists():
        import pytest
        pytest.skip("FFR dataset not found")

    rates = load_ffr_rates("ffr_monthly", str(ffr_path.parent))
    rate_map = dict(rates)

    # Known FRED FEDFUNDS values (percent / 100 = decimal)
    known_values = {
        # First observation
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
        # Last observation
        date(2023, 12, 1): Decimal("0.0533"),   # 5.33%
    }

    for d, expected in known_values.items():
        actual = rate_map.get(d)
        assert actual is not None, f"Missing FFR observation for {d}"
        assert actual == expected, (
            f"FFR value mismatch for {d}: expected {expected}, got {actual}"
        )
