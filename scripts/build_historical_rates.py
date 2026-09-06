#!/usr/bin/env python3
"""Build the merged historical monthly borrowing-rate artifact.

Source chain:
    1928-04 through 1954-06: Reconstructed FFR (Anbil et al. 2020)
    1954-07 onward: Official FEDFUNDS

Raw inputs: data/ern/raw/*.csv
Output: data/ern/ffr_monthly.json

Methodology:
    Source-derived (Anbil et al.):
        - Newspaper midpoints from HIGH/LOW
        - Average both newspapers when both available
    FBF framework decisions:
        - Single-endpoint fallback
        - Daily-to-monthly arithmetic mean
        - Partial-month aggregation (no blending across sources)

Reproducibility:
    Run this script from committed raw inputs without network access.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, NamedTuple

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class DailyObs(NamedTuple):
    """A single daily observation from one newspaper."""
    date: date
    high: Decimal | None
    low: Decimal | None


class MonthlyRate(NamedTuple):
    """A completed monthly rate observation."""
    date: date
    rate: Decimal


# ---------------------------------------------------------------------------
# Source-derived transformations (Anbil et al. 2020)
# ---------------------------------------------------------------------------

def newspaper_midpoint(high: Decimal | None, low: Decimal | None) -> Decimal | None:
    """Calculate midpoint from a single newspaper's HIGH and LOW.

    Source-derived rule: (high + low) / 2 when both exist.
    FBF framework rule: use the single endpoint when only one exists.
    """
    if high is not None and low is not None:
        return (high + low) / 2
    if high is not None:
        return high
    if low is not None:
        return low
    return None


def daily_rate_from_newspapers(
    ht_high: Decimal | None,
    ht_low: Decimal | None,
    wsj_high: Decimal | None,
    wsj_low: Decimal | None,
) -> Decimal | None:
    """Calculate the daily federal funds rate from newspaper observations.

    Source-derived rules (Anbil et al.):
        - Average both newspapers' midpoints when both available
        - Use single newspaper when only one reports
    FBF framework rules:
        - When a newspaper reports only one endpoint, use that value
        - When no observations available, return None
    """
    midpoints: list[Decimal] = []

    ht_mid = newspaper_midpoint(ht_high, ht_low)
    if ht_mid is not None:
        midpoints.append(ht_mid)

    wsj_mid = newspaper_midpoint(wsj_high, wsj_low)
    if wsj_mid is not None:
        midpoints.append(wsj_mid)

    if not midpoints:
        return None
    total = Decimal("0")
    for m in midpoints:
        total += m
    return total / Decimal(str(len(midpoints)))


# ---------------------------------------------------------------------------
# Source path selection (monthly-output granularity)
# ---------------------------------------------------------------------------

def select_reconstructed_source(year: int, month: int) -> str:
    """Select the source path for a given output month.

    Returns one of:
        "HT_ONLY"        - 1928-04 through 1932-05
        "HT_PLUS_WSJ"    - 1932-06 through 1937-08
        "HT_LOW_PLUS_WSJ" - 1937-09 through 1938-02
        "WSJ_ONLY"        - 1938-03 through 1954-06
        "FEDFUNDS"        - 1954-07 onward
    """
    d = date(year, month, 1)
    if d < date(1928, 4, 1):
        return "BEFORE_RECONSTRUCTION"
    if d < date(1932, 6, 1):
        return "HT_ONLY"
    if d < date(1937, 9, 1):
        return "HT_PLUS_WSJ"
    if d < date(1938, 3, 1):
        return "HT_LOW_PLUS_WSJ"
    if d < date(1954, 7, 1):
        return "WSJ_ONLY"
    return "FEDFUNDS"


# ---------------------------------------------------------------------------
# FBF framework transformations
# ---------------------------------------------------------------------------

def aggregate_daily_to_monthly(daily_rates: list[Decimal]) -> Decimal:
    """Arithmetic mean of available daily observations.

    FBF framework decision, matched to FEDFUNDS methodology.

    Raises ValueError if no valid observations.
    """
    valid = [r for r in daily_rates if r is not None]
    if not valid:
        raise ValueError("No observations available for this month")
    total = Decimal("0")
    for v in valid:
        total += v
    return total / Decimal(str(len(valid)))


# ---------------------------------------------------------------------------
# Raw CSV parsing
# ---------------------------------------------------------------------------

def parse_fred_csv(filepath: Path) -> dict[date, Decimal | None]:
    """Parse a FRED CSV file into {date: value_or_None}.

    Handles missing values (empty strings after the date).
    """
    result: dict[date, Decimal | None] = {}
    with filepath.open(encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        if "observation_date" not in header[0]:
            raise ValueError(f"Expected 'observation_date' header, got {header}")

        for row in reader:
            if len(row) < 2:
                continue
            d = date.fromisoformat(row[0])
            val_str = row[1].strip()
            if val_str:
                result[d] = Decimal(val_str)
            else:
                result[d] = None
    return result


def parse_fedfunds_csv(filepath: Path) -> dict[date, Decimal]:
    """Parse the FEDFUNDS CSV into {date: percent_value}."""
    result: dict[date, Decimal] = {}
    with filepath.open(encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        if "observation_date" not in header[0]:
            raise ValueError(f"Expected 'observation_date' header, got {header}")

        for row in reader:
            if len(row) < 2:
                continue
            d = date.fromisoformat(row[0])
            val_str = row[1].strip()
            if val_str:
                result[d] = Decimal(val_str)
    return result


# ---------------------------------------------------------------------------
# Reconstructed FFR: daily rate construction
# ---------------------------------------------------------------------------

def build_daily_reconstructed_ffr(
    ht_high: dict[date, Decimal | None],
    ht_low: dict[date, Decimal | None],
    wsj_high: dict[date, Decimal | None],
    wsj_low: dict[date, Decimal | None],
) -> dict[date, Decimal]:
    """Build daily reconstructed FFR from four newspaper series.

    For each date, calculates the daily rate using the approved methodology.
    """
    all_dates = sorted(set(ht_high) | set(ht_low) | set(wsj_high) | set(wsj_low))
    result: dict[date, Decimal] = {}
    for d in all_dates:
        rate = daily_rate_from_newspapers(
            ht_high.get(d),
            ht_low.get(d),
            wsj_high.get(d),
            wsj_low.get(d),
        )
        if rate is not None:
            result[d] = rate
    return result


# ---------------------------------------------------------------------------
# Monthly aggregation of reconstructed FFR
# ---------------------------------------------------------------------------

def aggregate_reconstructed_to_monthly(
    daily_ffr: dict[date, Decimal],
) -> dict[tuple[int, int], Decimal]:
    """Aggregate daily reconstructed FFR to monthly observations.

    Groups by (year, month), takes arithmetic mean.
    Only includes months where at least one observation exists.
    """
    by_month: dict[tuple[int, int], list[Decimal]] = defaultdict(list)
    for d, rate in daily_ffr.items():
        by_month[(d.year, d.month)].append(rate)

    result: dict[tuple[int, int], Decimal] = {}
    for ym in sorted(by_month):
        result[ym] = aggregate_daily_to_monthly(by_month[ym])
    return result


# ---------------------------------------------------------------------------
# Merge reconstructed and official FEDFUNDS
# ---------------------------------------------------------------------------

def merge_series(
    reconstructed: dict[tuple[int, int], Decimal],
    fedfunds: dict[date, Decimal],
) -> list[MonthlyRate]:
    """Merge reconstructed FFR and official FEDFUNDS into a single series.

    Handoff: 1954-06 uses reconstructed, 1954-07 uses FEDFUNDS.
    """
    rates: list[MonthlyRate] = []

    # Reconstructed FFR: 1928-04 through 1954-06
    for (y, m), rate in sorted(reconstructed.items()):
        if date(y, m, 1) >= date(1954, 7, 1):
            break
        # Convert percent to decimal fraction (same as FEDFUNDS)
        decimal_rate = (rate / Decimal("100")).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        rates.append(MonthlyRate(date=date(y, m, 1), rate=decimal_rate))

    # Official FEDFUNDS: 1954-07 onward
    for d in sorted(fedfunds.keys()):
        if d < date(1954, 7, 1):
            continue
        # Convert percent to decimal fraction
        decimal_rate = (fedfunds[d] / Decimal("100")).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        rates.append(MonthlyRate(date=d, rate=decimal_rate))

    return rates


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_monthly_coverage(rates: list[MonthlyRate]) -> list[str]:
    """Check for gaps, duplicates, and ordering issues."""
    errors: list[str] = []
    if not rates:
        errors.append("No monthly observations")
        return errors

    seen_months: set[tuple[int, int]] = set()
    prev_date: date | None = None

    for mr in rates:
        ym = (mr.date.year, mr.date.month)
        if ym in seen_months:
            errors.append(f"Duplicate month: {mr.date.isoformat()}")
        seen_months.add(ym)

        if prev_date is not None and mr.date <= prev_date:
            errors.append(
                f"Out of order: {mr.date.isoformat()} <= {prev_date.isoformat()}"
            )
        prev_date = mr.date

    # Check for missing months between first and last
    if rates:
        first = rates[0].date
        last = rates[-1].date
        current = date(first.year, first.month, 1)
        last_month = date(last.year, last.month, 1)
        while current <= last_month:
            if (current.year, current.month) not in seen_months:
                errors.append(f"Missing month: {current.isoformat()}")
            # Advance to next month
            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, current.month + 1, 1)

    return errors


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def build_artifact(
    rates: list[MonthlyRate],
) -> dict[str, Any]:
    """Build the JSON-serializable artifact dict."""
    return {
        "schema_version": "2.0",
        "methodology_version": "1.0",
        "series_name": "Historical Monthly Borrowing Rate for ERN Part 52",
        "data_frequency": "monthly",
        "units": "decimal (e.g. 0.0410 = 4.10% per annum)",
        "seasonal_adjustment": "not seasonally adjusted",
        "coverage_start": rates[0].date.isoformat() if rates else "unknown",
        "coverage_end": rates[-1].date.isoformat() if rates else "unknown",
        "sources": {
            "reconstructed_ffr": {
                "description": (
                    "Reconstructed daily FFR from newspaper reports"
                    " (Anbil et al. 2020)"
                ),
                "series_ids": [
                    "FFHTHIGH", "FFHTLOW", "FFWSJHIGH", "FFWSJLOW"
                ],
                "coverage": "1928-04-04 to 1954-06-30",
                "url": "https://fred.stlouisfed.org/categories/33951",
                "daily_methodology": (
                    "Average both newspapers' midpoints when both "
                    "available; use single newspaper when only one "
                    "reports (Anbil et al.)"
                ),
                "monthly_methodology": (
                    "Arithmetic mean of available daily observations"
                    " (FBF framework decision)"
                ),
            },
            "fedfunds": {
                "description": (
                    "Federal Funds Effective Rate"
                    " (Board of Governors)"
                ),
                "series_id": "FEDFUNDS",
                "coverage": "1954-07 to present",
                "url": "https://fred.stlouisfed.org/series/FEDFUNDS",
                "monthly_methodology": (
                    "FRED monthly averages of daily figures"
                ),
            },
        },
        "boundary_rules": [
            {
                "output_month": "1928-04",
                "rule": (
                    "Reconstructed FFR begins; HT-only; partial month"
                ),
            },
            {"output_month": "1932-06", "rule": "HT + WSJ overlap begins"},
            {
                "output_month": "1937-09",
                "rule": "HT HIGH ended; HT LOW + WSJ path",
            },
            {"output_month": "1938-03", "rule": "HT LOW ended; WSJ-only path"},
            {"output_month": "1954-07", "rule": "Switch to official FEDFUNDS"},
        ],
        "rates": [
            {"date": mr.date.isoformat(), "rate": str(mr.rate)}
            for mr in rates
        ],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build(raw_dir: Path, output_path: Path) -> dict[str, Any]:
    """Execute the full build pipeline. Returns the artifact dict."""
    # Parse raw CSVs
    ht_high = parse_fred_csv(raw_dir / "FFHTHIGH.csv")
    ht_low = parse_fred_csv(raw_dir / "FFHTLOW.csv")
    wsj_high = parse_fred_csv(raw_dir / "FFWSJHIGH.csv")
    wsj_low = parse_fred_csv(raw_dir / "FFWSJLOW.csv")
    fedfunds = parse_fedfunds_csv(raw_dir / "FEDFUNDS.csv")

    # Build daily reconstructed FFR
    daily_ffr = build_daily_reconstructed_ffr(ht_high, ht_low, wsj_high, wsj_low)

    # Aggregate to monthly
    reconstructed_monthly = aggregate_reconstructed_to_monthly(daily_ffr)

    # Merge with official FEDFUNDS
    merged = merge_series(reconstructed_monthly, fedfunds)

    # Validate
    errors = validate_monthly_coverage(merged)
    if errors:
        raise ValueError("Validation errors:\n" + "\n".join(errors))

    # Build and write artifact
    artifact = build_artifact(merged)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(artifact, indent=2) + "\n",
        encoding="utf-8",
    )

    return artifact


def main() -> None:
    script_dir = Path(__file__).parent
    raw_dir = script_dir.parent / "data" / "ern" / "raw"
    output_path = script_dir.parent / "data" / "ern" / "ffr_monthly.json"

    artifact = build(raw_dir, output_path)

    obs = artifact["rates"]
    print(f"Generated {output_path}")
    print(f"Coverage: {artifact['coverage_start']} to {artifact['coverage_end']}")
    print(f"Rates: {len(obs)}")
    print(f"First: {obs[0]}")
    print(f"Last: {obs[-1]}")

    # Print key anchor values
    rate_map = {o["date"]: o["rate"] for o in obs}
    anchors = {
        "1928-04-01": "First reconstructed month",
        "1929-01-01": "ERN 1929 cohort start",
        "1932-06-01": "HT+WSJ overlap begins",
        "1937-09-01": "HT HIGH ended",
        "1938-03-01": "HT LOW ended; WSJ only",
        "1954-06-01": "Last reconstructed month",
        "1954-07-01": "First FEDFUNDS",
        "1965-11-01": "ERN 1965 cohort start",
    }
    for d, label in anchors.items():
        val = rate_map.get(d, "NOT FOUND")
        print(f"  {d}: {val} ({label})")


if __name__ == "__main__":
    main()
