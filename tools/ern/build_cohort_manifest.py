#!/usr/bin/env python3
"""Build the canonical Part 3 cohort manifest from workbook-only datasets.

The manifest is derived from the canonical workbook extraction outputs:

- ``cape_shiller.csv``: ``SWR_Toolbox_v2.0.xlsx``, ``Asset Returns!O``
- ``spx_tr_real.csv``: ``SWR_Toolbox_v2.0.xlsx``, ``Asset Returns!Q``
- ``cpi.csv``: ``SWR_Toolbox_v2.0.xlsx``, ``Asset Returns!E``

No external Shiller series, legacy canonical master, or reconstructed market
series is consulted.  Every input must have workbook provenance that identifies
the authorized SWR workbook and the approved source cells.

Projection metadata is read from the production loader constants so the
manifest cannot drift from the actual runtime projection rules.  The builder
does not overwrite an existing manifest unless ``--force`` is supplied.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections.abc import Sequence
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

from fbf.core.datasets import ern as ern_loader
from fbf.core.domain.policies.cape_regime import (
    classify_cape_binary,
    classify_cape_regime,
)

_TOOL_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TOOL_DIR.parents[1]
_DEFAULT_DATA_DIR = _REPO_ROOT / "data" / "ern"

AUTHORIZED_SWR_WORKBOOK_SHA256 = (
    "d393e898a918e179d381768b187c8d5b54f58050500190b9e69403321acdf2c6"
)
_EXPECTED_SOURCE_FILE = "SWR_Toolbox_v2.0.xlsx"
_EXPECTED_SOURCE_SHEET = "Asset Returns"

_FIRST_COHORT = "1871-02-01"
_LAST_COHORT = "2015-12-01"
_BASE_SNAPSHOT_DATE = "1871-01-31"
_FEE = Decimal("0.0005")
_HORIZON_MONTHS = (12, 60, 120, 240, 360, 480, 600, 720)
_CAPE_MANIFEST_QUANTUM = Decimal("0.00000001")

_PROJECTION_START = ern_loader._HISTORICAL_END.date()
_PROJECTION_END = ern_loader._PROJECTION_END.date()


def _parse_month(value: str) -> date:
    parsed = date.fromisoformat(value)
    if parsed.day != 1:
        raise ValueError(f"Expected first-of-month date, got {value!r}")
    return parsed


def _next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def _previous_month(value: date) -> date:
    if value.month == 1:
        return date(value.year - 1, 12, 1)
    return date(value.year, value.month - 1, 1)


def _month_count(start: date, end: date) -> int:
    if end < start:
        raise ValueError(f"End month {end} precedes start month {start}")
    return (end.year - start.year) * 12 + (end.month - start.month) + 1


def _add_months(value: date, months: int) -> date:
    total = value.year * 12 + (value.month - 1) + months
    year, month_index = divmod(total, 12)
    return date(year, month_index + 1, 1)


def _month_range(start: date, end: date) -> tuple[date, ...]:
    return tuple(
        _add_months(start, index) for index in range(_month_count(start, end))
    )


def _validate_contiguous_monthly(
    dates: Sequence[str],
    *,
    label: str,
) -> None:
    if not dates:
        raise ValueError(f"{label} is empty")
    previous = _parse_month(dates[0])
    for raw_date in dates[1:]:
        current = _parse_month(raw_date)
        expected = _next_month(previous)
        if current != expected:
            raise ValueError(
                f"{label} dates must be contiguous monthly dates: "
                f"{previous.isoformat()} -> {current.isoformat()}"
            )
        previous = current


def _load_series(path: Path) -> tuple[tuple[str, Decimal], ...]:
    rows: list[tuple[str, Decimal]] = []
    with open(path, newline="", encoding="utf-8") as source:
        reader = csv.reader(source)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"{path} is empty") from exc
        if header != ["date", "value"]:
            raise ValueError(f"Unexpected header in {path}: {header}")
        for line_number, row in enumerate(reader, start=2):
            if len(row) != 2:
                raise ValueError(f"Malformed row {line_number} in {path}")
            raw_date = row[0].strip()
            raw_value = row[1].strip()
            if not raw_date or not raw_value:
                raise ValueError(f"Blank value at row {line_number} in {path}")
            parsed_date = _parse_month(raw_date)
            if parsed_date.isoformat() != raw_date:
                raise ValueError(
                    f"Date {raw_date!r} at row {line_number} in {path} "
                    "is not canonical YYYY-MM-DD"
                )
            try:
                value = Decimal(raw_value)
            except InvalidOperation as exc:
                raise ValueError(
                    f"Invalid decimal {raw_value!r} at row {line_number} in {path}"
                ) from exc
            rows.append((raw_date, value))
    return tuple(rows)


def _load_provenance(data_dir: Path, csv_name: str) -> dict[str, Any]:
    provenance_path = data_dir / csv_name.replace(".csv", ".provenance.json")
    if not provenance_path.exists():
        raise FileNotFoundError(
            f"Missing workbook provenance for {csv_name}: {provenance_path}"
        )
    payload = json.loads(provenance_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid provenance payload: {provenance_path}")

    if payload.get("source_file") != _EXPECTED_SOURCE_FILE:
        raise ValueError(
            f"{csv_name} provenance source_file must be {_EXPECTED_SOURCE_FILE!r}"
        )
    if payload.get("source_sha256") != AUTHORIZED_SWR_WORKBOOK_SHA256:
        raise ValueError(
            f"{csv_name} provenance does not identify the authorized workbook"
        )
    if payload.get("source_sheet") != _EXPECTED_SOURCE_SHEET:
        raise ValueError(
            f"{csv_name} provenance source_sheet must be {_EXPECTED_SOURCE_SHEET!r}"
        )
    if payload.get("validation_result") != "PASS":
        raise ValueError(f"{csv_name} provenance did not pass validation")
    return cast(dict[str, Any], payload)


def _validate_cape_provenance(provenance: dict[str, Any]) -> None:
    if provenance.get("schema_version") != "1.1":
        raise ValueError("CAPE provenance schema_version must be 1.1")
    if provenance.get("source_field_name") != "CAPE Shiller":
        raise ValueError("CAPE provenance source_field_name must be 'CAPE Shiller'")
    if provenance.get("extraction_tool") != "tools/ern/extract_workbook_returns.py":
        raise ValueError("CAPE provenance must identify the extraction tool")
    version = provenance.get("extraction_tool_version")
    if not isinstance(version, str) or not version:
        raise ValueError("CAPE provenance must identify the extraction tool version")
    transformations = provenance.get("transformations")
    if not isinstance(transformations, list) or not transformations:
        raise ValueError("CAPE provenance must record transformations")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_artifact_hash(
    data_dir: Path,
    csv_name: str,
    provenance: dict[str, Any],
) -> None:
    expected = _sha256(data_dir / csv_name)
    if provenance.get("artifact_sha256") != expected:
        raise ValueError(f"{csv_name} does not match its provenance artifact hash")


def _validate_provenance_series(
    provenance: dict[str, Any],
    rows: Sequence[tuple[str, Decimal]],
    *,
    csv_name: str,
    source_field: str,
    source_cells: str,
) -> None:
    if provenance.get("source_field") != source_field:
        raise ValueError(
            f"{csv_name} provenance source_field must be {source_field!r}"
        )
    if provenance.get("source_cells") != source_cells:
        raise ValueError(
            f"{csv_name} provenance source_cells must be {source_cells!r}"
        )
    if provenance.get("observation_count") != len(rows):
        raise ValueError(
            f"{csv_name} provenance observation_count does not match the CSV"
        )
    expected_range = f"{rows[0][0]} to {rows[-1][0]}"
    if provenance.get("date_range") != expected_range:
        raise ValueError(
            f"{csv_name} provenance date_range must be {expected_range!r}"
        )


def _manifest_cape_number(value: Decimal) -> float:
    return float(value.quantize(_CAPE_MANIFEST_QUANTUM))


def build_manifest(
    *,
    cape_rows: Sequence[tuple[str, Decimal]],
    market_dates: Sequence[str],
    index_dates: Sequence[str],
    cape_source_sha256: str,
    market_source_sha256: str,
    first_cohort: str = _FIRST_COHORT,
    last_cohort: str = _LAST_COHORT,
    projection_start: date = _PROJECTION_START,
    projection_end: date = _PROJECTION_END,
    fee: Decimal = _FEE,
) -> dict[str, Any]:
    """Build the deterministic Part 3 cohort manifest."""
    if cape_source_sha256 != market_source_sha256:
        raise ValueError(
            "CAPE and market inputs must come from the same canonical workbook"
        )
    if cape_source_sha256 != AUTHORIZED_SWR_WORKBOOK_SHA256:
        raise ValueError("Inputs do not come from the authorized SWR workbook")

    cape_dates = [date for date, _value in cape_rows]
    _validate_contiguous_monthly(cape_dates, label="CAPE")
    _validate_contiguous_monthly(market_dates, label="Market")
    _validate_contiguous_monthly(index_dates, label="Index")
    if len(set(cape_dates)) != len(cape_dates):
        raise ValueError("CAPE rows contain duplicate dates")
    if len(set(index_dates)) != len(index_dates):
        raise ValueError("Index rows contain duplicate dates")

    index_date_set = set(index_dates)
    if index_dates[0] != "1871-01-01":
        raise ValueError("Index dates must start at 1871-01-01")
    if len(index_dates) < 2:
        raise ValueError("Index dates must include at least two months")
    if first_cohort != index_dates[1]:
        raise ValueError(
            f"First cohort must be the first return month {index_dates[1]!r}"
        )
    if not set(cape_dates).issubset(index_date_set):
        raise ValueError("CAPE dates must be a subset of canonical index dates")
    if not all(market_date in index_date_set for market_date in market_dates):
        raise ValueError("Market dates must be a subset of canonical index dates")

    last_index = _parse_month(index_dates[-1])
    if projection_start != _next_month(last_index):
        raise ValueError(
            "Projection start must be the month after the last historical index "
            f"date: expected {_next_month(last_index).isoformat()}, "
            f"got {projection_start.isoformat()}"
        )
    projection_months = _month_count(projection_start, projection_end)
    snapshot_count = len(index_dates) + projection_months

    first = _parse_month(first_cohort)
    last = _parse_month(last_cohort)
    if last < first:
        raise ValueError("Last cohort must not precede first cohort")
    cohort_dates = [value.isoformat() for value in _month_range(first, last)]

    index_position = {value: position for position, value in enumerate(index_dates)}
    for cohort_date in cohort_dates:
        if cohort_date not in index_position:
            raise ValueError(f"Cohort date {cohort_date} is not in the index")
        if index_position[cohort_date] == 0:
            raise ValueError(
                f"Cohort date {cohort_date} would start before the first return"
            )

    cape_map = dict(cape_rows)
    market_set = set(market_dates)
    cape_regime_counts = {
        "HIGH": 0,
        "MODERATE": 0,
        "LOW": 0,
        "BELOW_15": 0,
        "EXTREME": 0,
    }
    binary_counts = {"HIGH": 0, "LOW": 0}
    cohorts: list[dict[str, Any]] = []

    for cohort_date in cohort_dates:
        cape_value = cape_map.get(cohort_date)
        cape_available = cape_value is not None
        regime_name: str | None = None
        if cape_value is not None:
            regime = classify_cape_regime(cape_value)
            regime_name = regime.name
            cape_regime_counts[regime_name] += 1

        prior_cape = cape_map.get(_previous_month(_parse_month(cohort_date)).isoformat())
        if prior_cape is None and cohort_date == first_cohort:
            prior_cape = cape_value
        if prior_cape is not None:
            binary = classify_cape_binary(prior_cape)
            binary_counts[binary.value] += 1

        start_month_index = index_position[cohort_date] - 1
        max_horizon_months = snapshot_count - (start_month_index + 1)
        if max_horizon_months < 0:
            raise ValueError(f"Negative horizon for cohort {cohort_date}")

        cohorts.append(
            {
                "cohort_date": cohort_date,
                "market_available": cohort_date in market_set,
                "cape_available": cape_available,
                "cape_value": _manifest_cape_number(cape_value)
                if cape_value is not None
                else None,
                "cape_regime": regime_name,
                "start_month_index": start_month_index,
                "max_horizon_months": max_horizon_months,
            }
        )

    horizon_eligibility = {
        f"h{months}": sum(
            1
            for cohort in cohorts
            if int(cohort["max_horizon_months"]) >= months
        )
        for months in _HORIZON_MONTHS
    }

    return {
        "version": "2.0",
        "description": (
            "Part 3 cohort manifest - workbook-only Shiller CAPE "
            "(Asset Returns!O) and canonical market data"
        ),
        "cohort_range": {
            "first": first_cohort,
            "last": last_cohort,
            "total": len(cohorts),
        },
        "snapshot_count": snapshot_count,
        "market_source": (
            "SWR_Toolbox_v2.0.xlsx Asset Returns!Q (spx_tr_real.csv)"
        ),
        "market_source_sha256": market_source_sha256,
        "cape_source": (
            "SWR_Toolbox_v2.0.xlsx Asset Returns!O (cape_shiller.csv)"
        ),
        "cape_source_sha256": cape_source_sha256,
        "horizon_note": (
            f"Canonical dataset provides {snapshot_count} snapshots "
            f"({_BASE_SNAPSHOT_DATE} to {projection_end.isoformat()}). "
            "Horizon eligibility is computed from each cohort's "
            "max_horizon_months."
        ),
        "fee": float(fee),
        "forward_projection": {
            "equity_annual_months_1_120": str(
                ern_loader._EQUITY_FORWARD_ANNUAL
            ),
            "equity_annual_months_121_plus": str(
                ern_loader._EQUITY_FORWARD_ANNUAL_AFTER
            ),
            "bond_annual_months_1_120": str(ern_loader._BOND_FORWARD_ANNUAL),
            "bond_annual_months_121_plus": str(
                ern_loader._BOND_FORWARD_ANNUAL_AFTER
            ),
            "phase_months": ern_loader._FORWARD_PHASE_MONTHS,
            "historical_end": last_index.isoformat(),
            "projection_start": projection_start.isoformat(),
            "projection_end": projection_end.isoformat(),
            "monthly_formula": "(1 + annual_rate) ** (1 / 12) - 1",
        },
        "statistics": {
            "total_cohorts": len(cohorts),
            "market_available": sum(
                1 for cohort in cohorts if cohort["market_available"]
            ),
            "cape_available": sum(
                1 for cohort in cohorts if cohort["cape_available"]
            ),
            "cape_regimes": cape_regime_counts,
            "horizon_eligibility": horizon_eligibility,
            "binary_cape_regimes": binary_counts,
            "binary_cape_semantics": (
                "CAPE at t-1 > 20; first cohort falls back to its own CAPE"
            ),
        },
        "cohorts": cohorts,
    }


def build_manifest_file(data_dir: Path) -> dict[str, Any]:
    """Load canonical extraction artifacts and build the manifest."""
    cape_rows = _load_series(data_dir / "cape_shiller.csv")
    market_rows = _load_series(data_dir / "spx_tr_real.csv")
    index_rows = _load_series(data_dir / "cpi.csv")

    cape_provenance = _load_provenance(data_dir, "cape_shiller.csv")
    market_provenance = _load_provenance(data_dir, "spx_tr_real.csv")
    index_provenance = _load_provenance(data_dir, "cpi.csv")

    _validate_cape_provenance(cape_provenance)
    _validate_artifact_hash(data_dir, "cape_shiller.csv", cape_provenance)
    _validate_artifact_hash(data_dir, "spx_tr_real.csv", market_provenance)
    _validate_artifact_hash(data_dir, "cpi.csv", index_provenance)

    _validate_provenance_series(
        cape_provenance,
        cape_rows,
        csv_name="cape_shiller.csv",
        source_field="O",
        source_cells="O6:O1871",
    )
    _validate_provenance_series(
        market_provenance,
        market_rows,
        csv_name="spx_tr_real.csv",
        source_field="Q",
        source_cells="Q7:Q1871",
    )
    _validate_provenance_series(
        index_provenance,
        index_rows,
        csv_name="cpi.csv",
        source_field="E",
        source_cells="E6:E1871",
    )

    for field in ("extraction_tool", "extraction_tool_version", "transformations"):
        if field not in cape_provenance:
            raise ValueError(f"CAPE provenance is missing {field!r}")

    source_sha256 = cast(str, cape_provenance["source_sha256"])
    if market_provenance.get("source_sha256") != source_sha256:
        raise ValueError("Market and CAPE provenance identify different workbooks")
    if index_provenance.get("source_sha256") != source_sha256:
        raise ValueError("Index and CAPE provenance identify different workbooks")

    return build_manifest(
        cape_rows=cape_rows,
        market_dates=[date for date, _value in market_rows],
        index_dates=[date for date, _value in index_rows],
        cape_source_sha256=source_sha256,
        market_source_sha256=cast(str, market_provenance["source_sha256"]),
    )


def write_manifest(manifest: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=_DEFAULT_DATA_DIR,
        help="Directory containing canonical workbook extraction CSVs",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the manifest here; omit to print it to stdout",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow replacing an existing --output file",
    )
    args = parser.parse_args(argv)

    manifest = build_manifest_file(args.data_dir)
    if args.output is None:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        return 0

    if args.output.exists() and not args.force:
        parser.error(
            f"{args.output} already exists; pass --force to replace it deliberately"
        )
    write_manifest(manifest, args.output)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
