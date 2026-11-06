"""Focused tests for the canonical Part 3 cohort manifest builder."""

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

from fbf.core.datasets import ern as ern_loader
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


def _small_inputs() -> tuple[list[tuple[str, Decimal]], list[str], list[str]]:
    index_dates = _months(date(1871, 1, 1), 6)
    cape_rows = [
        ("1871-01-01", Decimal("10")),
        ("1871-02-01", Decimal("25")),
        ("1871-03-01", Decimal("12")),
        ("1871-04-01", Decimal("20")),
        ("1871-05-01", Decimal("30")),
        ("1871-06-01", Decimal("15")),
    ]
    return cape_rows, index_dates[1:], index_dates


def test_authorized_workbook_hash_matches_extractor() -> None:
    assert (
        manifest_builder.AUTHORIZED_SWR_WORKBOOK_SHA256
        == workbook_returns.AUTHORIZED_SWR_WORKBOOK_SHA256
    )


def test_build_manifest_derives_lagged_binary_regimes_and_horizons() -> None:
    cape_rows, market_dates, index_dates = _small_inputs()

    manifest = manifest_builder.build_manifest(
        cape_rows=cape_rows,
        market_dates=market_dates,
        index_dates=index_dates,
        cape_source_sha256=_AUTHORIZED_SHA,
        market_source_sha256=_AUTHORIZED_SHA,
        first_cohort="1871-02-01",
        last_cohort="1871-05-01",
        projection_start=date(1871, 7, 1),
        projection_end=date(1871, 9, 1),
    )

    assert manifest["version"] == "2.0"
    assert manifest["snapshot_count"] == 9
    assert manifest["cohort_range"] == {
        "first": "1871-02-01",
        "last": "1871-05-01",
        "total": 4,
    }
    assert manifest["statistics"]["cape_regimes"] == {
        "HIGH": 2,
        "MODERATE": 0,
        "LOW": 0,
        "BELOW_15": 1,
        "EXTREME": 1,
    }
    assert manifest["statistics"]["binary_cape_regimes"] == {
        "HIGH": 1,
        "LOW": 3,
    }
    assert manifest["statistics"]["binary_cape_semantics"].startswith(
        "CAPE at t-1 > 20"
    )
    assert manifest["statistics"]["horizon_eligibility"]["h12"] == 0
    assert manifest["statistics"]["horizon_eligibility"]["h60"] == 0

    first = manifest["cohorts"][0]
    assert first == {
        "cohort_date": "1871-02-01",
        "market_available": True,
        "cape_available": True,
        "cape_value": 25.0,
        "cape_regime": "HIGH",
        "start_month_index": 0,
        "max_horizon_months": 8,
    }
    assert manifest["cohorts"][-1]["start_month_index"] == 3
    assert manifest["cohorts"][-1]["max_horizon_months"] == 5


def test_build_manifest_first_cohort_uses_own_cape_when_prior_missing() -> None:
    cape_rows, market_dates, index_dates = _small_inputs()
    cape_rows = cape_rows[1:]

    manifest = manifest_builder.build_manifest(
        cape_rows=cape_rows,
        market_dates=market_dates,
        index_dates=index_dates,
        cape_source_sha256=_AUTHORIZED_SHA,
        market_source_sha256=_AUTHORIZED_SHA,
        first_cohort="1871-02-01",
        last_cohort="1871-02-01",
        projection_start=date(1871, 7, 1),
        projection_end=date(1871, 9, 1),
    )

    assert manifest["statistics"]["binary_cape_regimes"] == {
        "HIGH": 1,
        "LOW": 0,
    }


def test_build_manifest_rejects_non_contiguous_or_mismatched_sources() -> None:
    cape_rows, market_dates, index_dates = _small_inputs()

    with pytest.raises(ValueError, match="contiguous"):
        manifest_builder.build_manifest(
            cape_rows=cape_rows,
            market_dates=market_dates,
            index_dates=["1871-01-01", "1871-03-01"],
            cape_source_sha256=_AUTHORIZED_SHA,
            market_source_sha256=_AUTHORIZED_SHA,
            first_cohort="1871-02-01",
            last_cohort="1871-02-01",
            projection_start=date(1871, 4, 1),
            projection_end=date(1871, 9, 1),
        )

    with pytest.raises(ValueError, match="same canonical workbook"):
        manifest_builder.build_manifest(
            cape_rows=cape_rows,
            market_dates=market_dates,
            index_dates=index_dates,
            cape_source_sha256=_AUTHORIZED_SHA,
            market_source_sha256="different",
            first_cohort="1871-02-01",
            last_cohort="1871-02-01",
            projection_start=date(1871, 7, 1),
            projection_end=date(1871, 9, 1),
        )

    with pytest.raises(ValueError, match="Projection start"):
        manifest_builder.build_manifest(
            cape_rows=cape_rows,
            market_dates=market_dates,
            index_dates=index_dates,
            cape_source_sha256=_AUTHORIZED_SHA,
            market_source_sha256=_AUTHORIZED_SHA,
            first_cohort="1871-02-01",
            last_cohort="1871-02-01",
            projection_start=date(1871, 8, 1),
            projection_end=date(1871, 9, 1),
        )


def test_projection_metadata_matches_production_loader() -> None:
    cape_rows, market_dates, index_dates = _small_inputs()

    manifest = manifest_builder.build_manifest(
        cape_rows=cape_rows,
        market_dates=market_dates,
        index_dates=index_dates,
        cape_source_sha256=_AUTHORIZED_SHA,
        market_source_sha256=_AUTHORIZED_SHA,
        first_cohort="1871-02-01",
        last_cohort="1871-02-01",
        projection_start=date(1871, 7, 1),
        projection_end=date(1871, 9, 1),
    )

    projection = manifest["forward_projection"]
    assert projection["equity_annual_months_1_120"] == str(
        ern_loader._EQUITY_FORWARD_ANNUAL
    )
    assert projection["equity_annual_months_121_plus"] == str(
        ern_loader._EQUITY_FORWARD_ANNUAL_AFTER
    )
    assert projection["bond_annual_months_1_120"] == str(
        ern_loader._BOND_FORWARD_ANNUAL
    )
    assert projection["bond_annual_months_121_plus"] == str(
        ern_loader._BOND_FORWARD_ANNUAL_AFTER
    )
    assert projection["phase_months"] == ern_loader._FORWARD_PHASE_MONTHS


def test_build_manifest_file_reads_only_workbook_provenance(tmp_path: Path) -> None:
    index_dates = _months(date(1871, 1, 1), 1866)
    cape_rows = [
        (value, str(Decimal(10) + Decimal(index % 30)))
        for index, value in enumerate(index_dates)
    ]
    market_rows = cape_rows[1:]
    _write_series(tmp_path / "cpi.csv", cape_rows)
    _write_series(tmp_path / "cape_shiller.csv", cape_rows)
    _write_series(tmp_path / "spx_tr_real.csv", market_rows)
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

    manifest = manifest_builder.build_manifest_file(tmp_path)

    assert manifest["cohort_range"]["total"] == 1739
    assert manifest["snapshot_count"] == 2459
    assert manifest["statistics"]["market_available"] == 1739
    assert manifest["statistics"]["cape_available"] == 1739
    assert manifest["cohorts"][0]["cohort_date"] == "1871-02-01"
    assert manifest["cohorts"][-1]["cohort_date"] == "2015-12-01"
    assert manifest["forward_projection"]["historical_end"] == "2026-06-01"
    assert manifest["forward_projection"]["projection_start"] == "2026-07-01"
    assert manifest["forward_projection"]["projection_end"] == "2075-11-01"


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

    with pytest.raises(FileNotFoundError, match="Missing workbook provenance"):
        manifest_builder.build_manifest_file(tmp_path)


def test_build_manifest_file_rejects_unauthorized_provenance(
    tmp_path: Path,
) -> None:
    index_dates = _months(date(1871, 1, 1), 1866)
    cape_rows = [(value, "10") for value in index_dates]
    market_rows = cape_rows[1:]
    _write_series(tmp_path / "cpi.csv", cape_rows)
    _write_series(tmp_path / "cape_shiller.csv", cape_rows)
    _write_series(tmp_path / "spx_tr_real.csv", market_rows)
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
        source_sha256="not-the-authorized-workbook",
        include_tool_identity=True,
    )
    _write_provenance(
        tmp_path / "spx_tr_real.provenance.json",
        source_field="Q",
        source_cells="Q7:Q1871",
        rows=market_rows,
    )

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

    assert manifest["snapshot_count"] == 2459
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


def test_manifest_output_is_deterministic() -> None:
    cape_rows, market_dates, index_dates = _small_inputs()
    kwargs: dict[str, object] = {
        "cape_rows": cape_rows,
        "market_dates": market_dates,
        "index_dates": index_dates,
        "cape_source_sha256": _AUTHORIZED_SHA,
        "market_source_sha256": _AUTHORIZED_SHA,
        "first_cohort": "1871-02-01",
        "last_cohort": "1871-05-01",
        "projection_start": date(1871, 7, 1),
        "projection_end": date(1871, 9, 1),
    }

    first = manifest_builder.build_manifest(**kwargs)  # type: ignore[arg-type]
    second = manifest_builder.build_manifest(**kwargs)  # type: ignore[arg-type]

    assert first == second
