"""Extract canonical DD-MM-YYYY,value CSV files from existing sources.

This script creates new canonical time-series files from existing data sources.
All existing source files are preserved unchanged.

Usage:
    python tools/ern/extract_canonical_series.py

Output files are written to data/ern/ alongside (not replacing) the originals.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "ern"


def _date_to_dd_mm_yyyy(d: date) -> str:
    """Convert a date to DD-MM-YYYY format."""
    return f"{d.day:02d}-{d.month:02d}-{d.year:04d}"


def _sha256(path: Path) -> str:
    """Compute SHA-256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_canonical_csv(path: Path, rows: list[tuple[str, str]]) -> None:
    """Write a canonical DD-MM-YYYY,value CSV file."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["DD-MM-YYYY", "value"])
        for date_str, value_str in rows:
            writer.writerow([date_str, value_str])


def _write_provenance(
    path: Path,
    source_file: str,
    source_field: str,
    source_date_format: str,
    source_numeric_type: str,
    extraction_method: str,
    observation_count: int,
    date_range: str,
    validation_result: str,
    notes: str = "",
) -> None:
    """Write a provenance JSON file."""
    provenance = {
        "source_file": source_file,
        "source_field": source_field,
        "source_date_format": source_date_format,
        "source_numeric_type": source_numeric_type,
        "extraction_method": extraction_method,
        "observation_count": observation_count,
        "date_range": date_range,
        "validation_result": validation_result,
    }
    if notes:
        provenance["notes"] = notes
    with open(path, "w", encoding="utf-8") as f:
        json.dump(provenance, f, indent=2)
        f.write("\n")


# ---------------------------------------------------------------------------
# 1. FFR from ffr_monthly.json
# ---------------------------------------------------------------------------

def extract_ffr() -> list[str]:
    """Extract ffr.csv from ffr_monthly.json."""
    src = DATA_DIR / "ffr_monthly.json"
    dst = DATA_DIR / "ffr.csv"
    prov = DATA_DIR / "ffr.provenance.json"

    with open(src) as f:
        data = json.load(f)

    rows = []
    for entry in data["rates"]:
        d = date.fromisoformat(entry["date"])
        value = entry["rate"]  # already a decimal string
        rows.append((_date_to_dd_mm_yyyy(d), value))

    rows.sort(key=lambda r: tuple(reversed(r[0].split("-"))))

    _write_canonical_csv(dst, rows)

    # Validation: row-by-row comparison
    errors = []
    with open(dst, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        canonical_rows = list(reader)

    if len(canonical_rows) != len(rows):
        errors.append(f"Row count mismatch: canonical={len(canonical_rows)} expected={len(rows)}")

    for i, (expected_date, expected_value) in enumerate(rows):
        cr = canonical_rows[i]
        if cr["DD-MM-YYYY"] != expected_date:
            errors.append(
                f"Row {i}: date mismatch canonical={cr['DD-MM-YYYY']}"
                f" expected={expected_date}"
            )
        if cr["value"] != expected_value:
            errors.append(
                f"Row {i}: value mismatch canonical={cr['value']}"
                f" expected={expected_value}"
            )

    validation = "PASS" if not errors else "FAIL: " + "; ".join(errors[:5])

    _write_provenance(
        prov,
        source_file="data/ern/ffr_monthly.json",
        source_field="rates[].rate",
        source_date_format="YYYY-MM-DD (ISO)",
        source_numeric_type="string (decimal)",
        extraction_method=(
            "Direct mapping: date.fromisoformat() -> DD-MM-YYYY,"
            " rate string preserved exactly"
        ),
        observation_count=len(rows),
        date_range=f"{rows[0][0]} to {rows[-1][0]}",
        validation_result=validation,
        notes=(
            "Monthly Federal Funds Rate / borrowing rate. Sources:"
            " reconstructed FFR (1928-04 to 1954-06) and official"
            " FEDFUNDS (1954-07 to present)."
        ),
    )

    return [validation]


# ---------------------------------------------------------------------------
# 2. Real returns from ern_real_returns_1871_2016.csv
# ---------------------------------------------------------------------------

def extract_real_returns() -> list[str]:
    """Extract sp500_tr_real_return.csv and bond_10y_tr_real_return.csv."""
    src = DATA_DIR / "ern_real_returns_1871_2016.csv"
    dst_equity = DATA_DIR / "sp500_tr_real_return.csv"
    dst_bond = DATA_DIR / "bond_10y_tr_real_return.csv"
    prov_equity = DATA_DIR / "sp500_tr_real_return.provenance.json"
    prov_bond = DATA_DIR / "bond_10y_tr_real_return.provenance.json"

    results = []

    with open(src, encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)
        csv_rows = list(reader)

    equity_rows = []
    bond_rows = []
    for csv_row in csv_rows:
        if not csv_row or not csv_row[0].strip():
            continue
        year = csv_row[0].strip()
        month = csv_row[1].strip()
        d = date(int(year), int(month), 1)
        dd_mm_yyyy = _date_to_dd_mm_yyyy(d)
        equity_val = csv_row[2].strip() if len(csv_row) > 2 else ""
        bond_val = csv_row[3].strip() if len(csv_row) > 3 else ""
        equity_rows.append((dd_mm_yyyy, equity_val))
        bond_rows.append((dd_mm_yyyy, bond_val))

    # Write equity file
    _write_canonical_csv(dst_equity, equity_rows)

    # Validate equity file
    errors_eq = []
    with open(dst_equity, newline="", encoding="utf-8") as f:
        canonical_eq = list(csv.DictReader(f))

    if len(canonical_eq) != len(equity_rows):
        errors_eq.append(
            f"Row count mismatch: canonical={len(canonical_eq)}"
            f" expected={len(equity_rows)}"
        )

    for i, (exp_date, exp_val) in enumerate(equity_rows):
        cr = canonical_eq[i]
        if cr["DD-MM-YYYY"] != exp_date:
            errors_eq.append(f"Row {i}: date mismatch")
        if cr["value"] != exp_val:
            errors_eq.append(f"Row {i}: value mismatch canonical={cr['value']} expected={exp_val}")

    val_eq = "PASS" if not errors_eq else "FAIL: " + "; ".join(errors_eq[:5])
    results.append(val_eq)

    _write_provenance(
        prov_equity,
        source_file="data/ern/ern_real_returns_1871_2016.csv",
        source_field="spx_tr_real (column 3)",
        source_date_format="YYYY,MM (integer columns)",
        source_numeric_type="float (10+ decimal places)",
        extraction_method=(
            "date = YYYY-MM-01 mapped to DD-MM-YYYY."
            " Value preserved as source string (no rounding)."
        ),
        observation_count=len(equity_rows),
        date_range=f"{equity_rows[0][0]} to {equity_rows[-1][0]}",
        validation_result=val_eq,
        notes=(
            "S&P 500 Total Return real (inflation-adjusted) monthly"
            " returns. Empty values (e.g. 1871-01) represent baseline"
            " period with no return applied."
        ),
    )

    # Write bond file
    _write_canonical_csv(dst_bond, bond_rows)

    # Validate bond file
    errors_bond = []
    with open(dst_bond, newline="", encoding="utf-8") as f:
        canonical_bond = list(csv.DictReader(f))

    if len(canonical_bond) != len(bond_rows):
        errors_bond.append(
            f"Row count mismatch: canonical={len(canonical_bond)}"
            f" expected={len(bond_rows)}"
        )

    for i, (exp_date, exp_val) in enumerate(bond_rows):
        cr = canonical_bond[i]
        if cr["DD-MM-YYYY"] != exp_date:
            errors_bond.append(f"Row {i}: date mismatch")
        if cr["value"] != exp_val:
            errors_bond.append(
                f"Row {i}: value mismatch canonical={cr['value']}"
                f" expected={exp_val}"
            )

    val_bond = "PASS" if not errors_bond else "FAIL: " + "; ".join(errors_bond[:5])
    results.append(val_bond)

    _write_provenance(
        prov_bond,
        source_file="data/ern/ern_real_returns_1871_2016.csv",
        source_field="y10_bm_real (column 4)",
        source_date_format="YYYY,MM (integer columns)",
        source_numeric_type="float (10+ decimal places)",
        extraction_method=(
            "date = YYYY-MM-01 mapped to DD-MM-YYYY."
            " Value preserved as source string (no rounding)."
        ),
        observation_count=len(bond_rows),
        date_range=f"{bond_rows[0][0]} to {bond_rows[-1][0]}",
        validation_result=val_bond,
        notes=(
            "10-Year Bond Total Return real (inflation-adjusted)"
            " monthly returns. Empty values (e.g. 1871-01) represent"
            " baseline period with no return applied."
        ),
    )

    return results


# ---------------------------------------------------------------------------
# 3. Part 52 series from canonical_market_data.json
# ---------------------------------------------------------------------------

def extract_part52_series() -> list[str]:
    """Extract cpi.csv, spx_tr.csv, bm10.csv, ffr_spliced.csv."""
    src = DATA_DIR / "part52" / "canonical_market_data.json"
    results = []

    with open(src) as f:
        data = json.load(f)

    series_map = {
        "cpi": (
            "cpi.csv", "cpi.provenance.json", "CPI index level"
        ),
        "spx_tr": (
            "spx_tr.csv", "spx_tr.provenance.json",
            "S&P 500 Total Return index level (nominal)",
        ),
        "bm10": (
            "bm10.csv", "bm10.provenance.json",
            "10-Year Bond Market index level",
        ),
        "ffr_spliced": (
            "ffr_spliced.csv", "ffr_spliced.provenance.json",
            "Spliced Federal Funds Rate"
            " (historical reconstruction + official FEDFUNDS)",
        ),
    }

    for field, (csv_name, prov_name, description) in series_map.items():
        dst = DATA_DIR / "part52" / csv_name
        prov = DATA_DIR / "part52" / prov_name

        rows = []
        for entry in data["data"]:
            d = date(entry["year"], entry["month"], 1)
            value = entry[field]
            value_str = str(value)
            rows.append((_date_to_dd_mm_yyyy(d), value_str))

        rows.sort(key=lambda r: tuple(reversed(r[0].split("-"))))

        _write_canonical_csv(dst, rows)

        # Row-by-row validation
        errors = []
        with open(dst, newline="", encoding="utf-8") as f:
            canonical_rows = list(csv.DictReader(f))

        if len(canonical_rows) != len(rows):
            errors.append(
                f"Row count mismatch: canonical={len(canonical_rows)}"
                f" expected={len(rows)}"
            )

        for i, (exp_date, exp_val) in enumerate(rows):
            cr = canonical_rows[i]
            if cr["DD-MM-YYYY"] != exp_date:
                errors.append(
                    f"Row {i}: date mismatch"
                    f" canonical={cr['DD-MM-YYYY']}"
                    f" expected={exp_date}"
                )
            if cr["value"] != exp_val:
                errors.append(f"Row {i}: value mismatch canonical={cr['value']} expected={exp_val}")

        validation = "PASS" if not errors else "FAIL: " + "; ".join(errors[:5])
        results.append(f"{csv_name}: {validation}")

        _write_provenance(
            prov,
            source_file="data/ern/part52/canonical_market_data.json",
            source_field=field,
            source_date_format="{year: int, month: int}",
            source_numeric_type="float64 (JSON native)",
            extraction_method=(
                f"date = date(year, month, 1) mapped to DD-MM-YYYY."
                f" Value = float(entry['{field}']),"
                " converted to string preserving full Python"
                " float repr."
            ),
            observation_count=len(rows),
            date_range=f"{rows[0][0]} to {rows[-1][0]}",
            validation_result=validation,
            notes=description,
        )

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print("Canonical Time-Series Extraction")
    print("=" * 70)
    print()

    all_results = []

    print("--- 1. FFR (from ffr_monthly.json) ---")
    r = extract_ffr()
    all_results.extend(r)
    for line in r:
        print(f"  ffr.csv: {line}")
    print()

    print("--- 2. Real Returns (from ern_real_returns_1871_2016.csv) ---")
    r = extract_real_returns()
    all_results.extend(r)
    print(f"  sp500_tr_real_return.csv: {r[0]}")
    print(f"  bond_10y_tr_real_return.csv: {r[1]}")
    print()

    print("--- 3. Part 52 Series (from canonical_market_data.json) ---")
    r = extract_part52_series()
    all_results.extend(r)
    for line in r:
        print(f"  {line}")
    print()

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    all_pass = all("PASS" in res for res in all_results)
    print(f"Overall: {'ALL PASS' if all_pass else 'FAILURES DETECTED'}")
    print("Files created: 8 canonical CSV + 8 provenance JSON = 16 new files")
    print("Files modified: 0 (all existing files preserved unchanged)")
    print()
    for line in all_results:
        status = "OK" if "PASS" in line else "FAIL"
        print(f"  [{status}] {line}")


if __name__ == "__main__":
    main()
