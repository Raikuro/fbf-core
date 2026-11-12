"""Focused tests for the runtime effective Part 3 manifest builder."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from tools.ern import (
    build_cohort_manifest as manifest_builder,
    extract_workbook_returns as workbook_returns,
)

_AUTHORIZED_SHA = manifest_builder.AUTHORIZED_SWR_WORKBOOK_SHA256


def _months(start: date, count: int) -> list[str]:
    values: list[str] = []
    total = start.year * 12 + (start.month - 1)
    for offset in range(count):
        year, month_index = divmod(total + offset, 12)
        values.append(date(year, month_index + 1, 1).isoformat())
    return values


def _write_series(path: Path, rows: list[tuple[str, str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as target:
        writer = csv.writer(target, lineterminator="\n")
        writer.writerow(["date", "value"])
        writer.writerows(rows)


def _write_provenance(
    path: Path,
    *,
    source_field: str,
    source_cells: str,
    rows: list[tuple[str, str]],
    source_sha256: str = _AUTHORIZED_SHA,
    include_tool_identity: bool = False,
) -> None:
    csv_path = path.with_name(path.name.replace(".provenance.json", ".csv"))
    payload: dict[str, Any] = {
        "schema_version": "1.1" if include_tool_identity else "1.0",
        "source_file": "SWR_Toolbox_v2.0.xlsx",
        "source_sha256": source_sha256,
        "source_sheet": "Asset Returns",
        "source_field": source_field,
        "source_cells": source_cells,
        "observation_count": len(rows),
        "date_range": f"{rows[0][0]} to {rows[-1][0]}",
        "artifact_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "validation_result": "PASS",
    }
    if include_tool_identity:
        payload["source_field_name"] = "CAPE Shiller"
        payload["extraction_tool"] = "tools/ern/extract_workbook_returns.py"
        payload["extraction_tool_version"] = "1.1.0"
        payload["transformations"] = ["workbook cached values only"]
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_canonical_inputs(tmp_path: Path) -> None:
    index_dates = _months(date(1871, 1, 1), 1866)
    cape_rows = [
        (value, str(Decimal(10) + Decimal(index % 30)))
        for index, value in enumerate(index_dates)
    ]
    market_rows = cape_rows[1:]
    _write_series(tmp_path / "cpi.csv", cape_rows)
    _write_series(tmp_path / "cape_shiller.csv", cape_rows)
    _write_series(tmp_path / "spx_tr_real.csv", market_rows)
    _write_series(tmp_path / "bond_10y_tr_real.csv", market_rows)
    _write_provenance(
        tmp_path / "cpi.provenance.json",
        source_field="E",
        source_cells="E6:E1871",
        rows=cape_rows,
    )
    _write_provenance(
        tmp_path / "cape_shiller.provenance.json",
        source_field="O",
        source_cells="O6:O1871",
        rows=cape_rows,
        include_tool_identity=True,
    )
    _write_provenance(
        tmp_path / "spx_tr_real.provenance.json",
        source_field="Q",
        source_cells="Q7:Q1871",
        rows=market_rows,
    )


def test_authorized_workbook_hash_matches_extractor() -> None:
    assert (
        manifest_builder.AUTHORIZED_SWR_WORKBOOK_SHA256
        == workbook_returns.AUTHORIZED_SWR_WORKBOOK_SHA256
    )


def test_build_manifest_file_builds_effective_manifest(tmp_path: Path) -> None:
    _write_canonical_inputs(tmp_path)

    manifest = manifest_builder.build_manifest_file(tmp_path)

    assert manifest["version"] == "2.0"
    assert manifest["cohort_range"]["total"] == 1739
    assert manifest["snapshot_count"] == 2460
    assert manifest["statistics"]["market_available"] == 1739
    assert manifest["statistics"]["cape_available"] == 1739
    assert manifest["statistics"]["horizon_eligibility"]["h720"] == 1739
    assert manifest["cohorts"][0]["cohort_date"] == "1871-02-01"
    assert manifest["cohorts"][-1]["cohort_date"] == "2015-12-01"
    assert manifest["cohorts"][-1]["max_horizon_months"] == 721
    assert manifest["forward_projection"]["historical_end"] == "2026-06-01"
    assert manifest["forward_projection"]["projection_start"] == "2026-07-01"
    assert manifest["forward_projection"]["projection_end"] == "2075-12-01"


def test_manifest_output_is_deterministic() -> None:
    first = manifest_builder.build_manifest_file(Path("data/inputs/ern"))
    second = manifest_builder.build_manifest_file(Path("data/inputs/ern"))
    assert first == second


def test_validate_cape_provenance_requires_tool_identity() -> None:
    payload: dict[str, Any] = {
        "schema_version": "1.1",
        "source_field_name": "CAPE Shiller",
        "extraction_tool": "tools/ern/extract_workbook_returns.py",
        "extraction_tool_version": "1.1.0",
        "transformations": ["workbook cached values only"],
    }
    manifest_builder._validate_cape_provenance(payload)

    payload.pop("transformations")
    with pytest.raises(ValueError, match="transformations"):
        manifest_builder._validate_cape_provenance(payload)


def test_validate_artifact_hash_rejects_tampering(tmp_path: Path) -> None:
    artifact = tmp_path / "cape_shiller.csv"
    artifact.write_text("date,value\n1871-01-01,10\n", encoding="utf-8")

    with pytest.raises(ValueError, match="artifact hash"):
        manifest_builder._validate_artifact_hash(
            tmp_path,
            "cape_shiller.csv",
            {"artifact_sha256": "not-the-file-hash"},
        )


def test_build_manifest_file_rejects_missing_provenance(tmp_path: Path) -> None:
    index_dates = _months(date(1871, 1, 1), 1866)
    cape_rows = [(value, "10") for value in index_dates]
    _write_series(tmp_path / "cpi.csv", cape_rows)
    _write_series(tmp_path / "cape_shiller.csv", cape_rows)
    _write_series(tmp_path / "spx_tr_real.csv", cape_rows[1:])
    _write_series(tmp_path / "bond_10y_tr_real.csv", cape_rows[1:])

    with pytest.raises(FileNotFoundError, match="Missing workbook provenance"):
        manifest_builder.build_manifest_file(tmp_path)


def test_build_manifest_file_rejects_unauthorized_provenance(
    tmp_path: Path,
) -> None:
    _write_canonical_inputs(tmp_path)
    provenance_path = tmp_path / "cape_shiller.provenance.json"
    payload = json.loads(provenance_path.read_text(encoding="utf-8"))
    payload["source_sha256"] = "not-the-authorized-workbook"
    provenance_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="authorized workbook"):
        manifest_builder.build_manifest_file(tmp_path)


def test_real_workbook_pipeline_reports_canonical_migration_counts(
    tmp_path: Path,
) -> None:
    raw_workbook = os.environ.get("ERN_SWR_WORKBOOK")
    if not raw_workbook:
        pytest.skip("ERN_SWR_WORKBOOK is not set; workbook validation skipped")
    workbook = Path(raw_workbook)
    if not workbook.exists():
        pytest.skip(f"ERN_SWR_WORKBOOK does not exist: {workbook}")

    data = workbook_returns.extract_workbook(workbook)
    workbook_returns.write_outputs(data, tmp_path)
    manifest = manifest_builder.build_manifest_file(tmp_path)

    assert manifest["snapshot_count"] == 2460
    assert manifest["statistics"]["total_cohorts"] == 1739
    assert manifest["statistics"]["cape_available"] == 1739
    assert manifest["statistics"]["cape_regimes"] == {
        "HIGH": 359,
        "MODERATE": 520,
        "LOW": 0,
        "BELOW_15": 802,
        "EXTREME": 58,
    }
    assert manifest["statistics"]["binary_cape_regimes"] == {
        "HIGH": 416,
        "LOW": 1323,
    }
    assert manifest["cohorts"][0]["cape_value"] == 10.91933677
    assert manifest["cohorts"][-1]["cape_value"] == 25.69555241
    assert manifest["cape_source_sha256"] == (
        workbook_returns.AUTHORIZED_SWR_WORKBOOK_SHA256
    )
