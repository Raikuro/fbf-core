"""Extract canonical date,value CSV files from the canonical master.

This script creates runtime CSVs from ``canonical/ern_asset_returns.csv``.
The FFR series is not extracted here; use
``tools/ern/extract_ffr_from_workbook.py`` for the workbook-derived FFR series.

Usage:
    python tools/ern/extract_canonical_series.py

Output files are written to data/ern/ alongside (not replacing) the originals.
"""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "ern"


def _date_to_yyyy_mm_dd(d: date) -> str:
    """Convert a date to YYYY-MM-DD format."""
    return f"{d.year:04d}-{d.month:02d}-{d.day:02d}"


def _write_canonical_csv(path: Path, rows: list[tuple[str, str]]) -> None:
    """Write a canonical date,value CSV file."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "value"])
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
# Direct extraction from canonical/ern_asset_returns.csv
# ---------------------------------------------------------------------------

MASTER_CSV = Path(__file__).resolve().parent.parent.parent / "canonical" / "ern_asset_returns.csv"

# Columns to extract: (master_column, runtime_filename, description)
MASTER_SERIES = [
    ("spx_tr_real", "spx_tr_real.csv", "S&P 500 TR real returns (monthly)"),
    ("y10_bm_real", "bond_10y_tr_real.csv", "10-Year Bond Market real returns (monthly)"),
    ("cpi", "cpi.csv", "CPI index level"),
    ("spx_tr_cum", "spx_tr.csv", "S&P 500 TR cumulative nominal return index"),
    ("y10_bm_cum", "bm10.csv", "10-Year Bond Market cumulative nominal return index"),
]


def extract_from_master() -> list[str]:
    """Extract runtime CSVs directly from canonical/ern_asset_returns.csv.

    Direct column extraction: no reconstruction, no renormalization, no
    financial calculations.  Values are preserved exactly as they appear
    in the master dataset.
    """
    results = []

    # Read master CSV
    master_rows = []
    with open(MASTER_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            master_rows.append(row)

    print(f"  Master: {len(master_rows)} rows"
          f" ({master_rows[0]['year']}-{master_rows[0]['month']}"
          f" to {master_rows[-1]['year']}-{master_rows[-1]['month']})")

    for column, csv_name, description in MASTER_SERIES:
        dst = DATA_DIR / csv_name
        prov = DATA_DIR / csv_name.replace(".csv", ".provenance.json")

        # Extract rows: preserve exact values from master
        extracted_rows = []
        for row in master_rows:
            year = row["year"].strip()
            month = row["month"].strip()
            if not year or not month:
                continue
            d = date(int(year), int(month), 1)
            value = row[column].strip() if row.get(column) else ""
            extracted_rows.append((_date_to_yyyy_mm_dd(d), value))

        # Filter out empty values (e.g., 1871-01 has no real returns)
        extracted_rows = [(d, v) for d, v in extracted_rows if v]

        # Write runtime CSV
        _write_canonical_csv(dst, extracted_rows)

        # Validate: exact match against master column
        errors = []
        with open(dst, newline="", encoding="utf-8") as f:
            canonical_rows = list(csv.DictReader(f))

        if len(canonical_rows) != len(extracted_rows):
            errors.append(
                f"Row count mismatch: canonical={len(canonical_rows)}"
                f" expected={len(extracted_rows)}"
            )

        for i, (exp_date, exp_val) in enumerate(extracted_rows):
            cr = canonical_rows[i]
            if cr["date"] != exp_date:
                errors.append(f"Row {i}: date mismatch")
            if cr["value"] != exp_val:
                errors.append(
                    f"Row {i}: value mismatch canonical={cr['value']}"
                    f" expected={exp_val}"
                )

        validation = "PASS" if not errors else "FAIL: " + "; ".join(errors[:5])
        results.append(f"{csv_name}: {validation}")

        # Write provenance
        _write_provenance(
            prov,
            source_file="canonical/ern_asset_returns.csv",
            source_field=column,
            source_date_format="year,month (integer columns)",
            source_numeric_type="string (preserved exactly)",
            extraction_method=(
                "Direct column extraction. date = YYYY-MM-01 mapped to"
                " YYYY-MM-DD. Value preserved as source string (no"
                " rounding, no normalization)."
            ),
            observation_count=len(extracted_rows),
            date_range=f"{extracted_rows[0][0]} to {extracted_rows[-1][0]}",
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

    print("--- Direct Extraction from Master (canonical/ern_asset_returns.csv) ---")
    all_results = extract_from_master()
    for line in all_results:
        print(f"  {line}")
    print()

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    all_pass = all("PASS" in res for res in all_results)
    print(f"Overall: {'ALL PASS' if all_pass else 'FAILURES DETECTED'}")
    print()
    for line in all_results:
        status = "OK" if "PASS" in line else "FAIL"
        print(f"  [{status}] {line}")


if __name__ == "__main__":
    main()
