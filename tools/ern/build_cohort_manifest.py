#!/usr/bin/env python3
"""Build the canonical Part 3 cohort manifest from workbook-only datasets.

The manifest is derived from the canonical workbook extraction outputs:

- ``cape_shiller.csv``: ``SWR_Toolbox_v2.0.xlsx``, ``Asset Returns!O``
- ``spx_tr_real.csv``: ``SWR_Toolbox_v2.0.xlsx``, ``Asset Returns!Q``
- ``cpi.csv``: ``SWR_Toolbox_v2.0.xlsx``, ``Asset Returns!E``

No external Shiller series, legacy canonical master, or reconstructed market
series is consulted.  Every input must have workbook provenance that identifies
the authorized SWR workbook and the approved source cells.

The manifest is built through the same runtime preparation and effective
manifest pipeline as production studies.  It is projection-dependent and must
not be committed as canonical dataset data.  The builder does not overwrite an
existing file unless ``--force`` is supplied.
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
from fbf.core.research.cohort_manifest import (
    build_effective_manifest,
    manifest_to_dict,
)

_TOOL_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TOOL_DIR.parents[1]
_DEFAULT_DATA_DIR = _REPO_ROOT / "data" / "inputs" / "ern"

AUTHORIZED_SWR_WORKBOOK_SHA256 = (
    "d393e898a918e179d381768b187c8d5b54f58050500190b9e69403321acdf2c6"
)
_EXPECTED_SOURCE_FILE = "SWR_Toolbox_v2.0.xlsx"
_EXPECTED_SOURCE_SHEET = "Asset Returns"

_FIRST_COHORT = "1871-02-01"
_LAST_COHORT = "2015-12-01"
_BASE_SNAPSHOT_DATE = "1871-01-31"
_FEE = Decimal("0.0005")


def _parse_month(value: str) -> date:
    parsed = date.fromisoformat(value)
    if parsed.day != 1:
        raise ValueError(f"Expected first-of-month date, got {value!r}")
    return parsed


def _add_months(value: date, months: int) -> date:
    total = value.year * 12 + (value.month - 1) + months
    year, month_index = divmod(total, 12)
    return date(year, month_index + 1, 1)


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


def _effective_manifest_payload(data_dir: Path) -> dict[str, Any]:
    """Build the runtime effective manifest and compatible top-level fields."""
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

    historical_cutoff = _parse_month(index_rows[-1][0])
    prepared = ern_loader.prepare_ern_dataset(
        data_dir,
        config=ern_loader.ProjectionConfig(
            historical_data_cutoff=historical_cutoff
        ),
        required_through=_add_months(_parse_month(_LAST_COHORT), 60 * 12),
    )
    manifest = build_effective_manifest(
        dataset=prepared.dataset,
        metadata=prepared.metadata,
        cape_rows=cape_rows,
        cohort_start=_parse_month(_FIRST_COHORT),
        cohort_end=_parse_month(_LAST_COHORT),
        fee=_FEE,
        require_cape=True,
    )
    payload = manifest_to_dict(manifest)
    payload["cohort_range"] = {
        "first": _FIRST_COHORT,
        "last": _LAST_COHORT,
        "total": len(manifest.cohorts),
    }
    payload["snapshot_count"] = prepared.metadata.snapshot_count
    payload["market_source_sha256"] = cast(
        str, market_provenance["source_sha256"]
    )
    payload["cape_source_sha256"] = source_sha256
    payload["horizon_note"] = (
        f"Runtime projection provides {prepared.metadata.snapshot_count} "
        f"snapshots ({_BASE_SNAPSHOT_DATE} to "
        f"{prepared.metadata.projection_end.isoformat()})."
    )
    payload["forward_projection"] = {
        "equity_annual_months_1_120": str(prepared.metadata.equity_annual),
        "equity_annual_months_121_plus": str(
            prepared.metadata.equity_annual_after
        ),
        "bond_annual_months_1_120": str(prepared.metadata.bond_annual),
        "bond_annual_months_121_plus": str(prepared.metadata.bond_annual_after),
        "phase_months": prepared.metadata.phase_months,
        "historical_end": prepared.metadata.historical_data_cutoff.isoformat(),
        "projection_start": prepared.metadata.projection_start.isoformat(),
        "projection_end": prepared.metadata.projection_end.isoformat(),
        "monthly_formula": "(1 + annual_rate) ** (1 / 12) - 1",
    }
    return payload


def build_manifest_file(data_dir: Path) -> dict[str, Any]:
    """Load canonical formats and return the runtime effective manifest."""
    return _effective_manifest_payload(data_dir)


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
