"""Contract tests for canonical ERN data provenance.

These tests enforce artifact-level reproducibility: every canonical CSV is
pinned by SHA-256, market/CPI provenance identifies the SWR workbook and source
cells, and FFR provenance identifies the workbook and FRED segments separately.
They do not regenerate production data. Optional workbook checks run only when
the corresponding environment variable is set.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest

from fbf.core.datasets.ern import load_cape_rows, prepare_ern_dataset
from fbf.core.research.cohort_manifest import build_effective_manifest
from tools.ern import extract_workbook_returns as workbook_returns

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _REPO_ROOT / "data" / "inputs" / "ern"
_EXTRACTION_DIR = _DATA_DIR / "extraction"
_FIXTURE_DIR = _REPO_ROOT / "data" / "ern"

_EXTRACTION_CSVS = frozenset({"spx_tr.csv", "bm10.csv"})
_FIXTURE_CSVS = frozenset({"workbook_returns.csv"})


def _csv_path(csv_name: str) -> Path:
    if csv_name in _EXTRACTION_CSVS:
        return _EXTRACTION_DIR / csv_name
    if csv_name in _FIXTURE_CSVS:
        return _FIXTURE_DIR / csv_name
    return _DATA_DIR / csv_name
_SWR_WORKBOOK_SHA256 = (
    "d393e898a918e179d381768b187c8d5b54f58050500190b9e69403321acdf2c6"
)
_MARKET_PROVENANCE: dict[str, tuple[str, str, int]] = {
    "cpi.csv": ("E", "E6:E1871", 1866),
    "spx_tr.csv": ("F", "F6:F1871", 1866),
    "bm10.csv": ("G", "G6:G1871", 1866),
    "spx_tr_real.csv": ("Q", "Q7:Q1871", 1865),
    "bond_10y_tr_real.csv": ("R", "R7:R1871", 1865),
    "workbook_returns.csv": (
        "Q (equity real return), R (bond real return)",
        "Q7:Q1871, R7:R1871",
        1865,
    ),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_provenance(csv_name: str) -> dict[str, Any]:
    path = _csv_path(csv_name).with_suffix(".provenance.json")
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def _read_ffr_rows(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no header")
        date_key = (
            "DD-MM-YYYY" if "DD-MM-YYYY" in reader.fieldnames else "date"
        )
        rows: list[dict[str, str]] = []
        for row in reader:
            raw_date = row[date_key] or ""
            if date_key == "DD-MM-YYYY":
                day, month, year = raw_date.split("-")
                raw_date = f"{year}-{month}-{day}"
            rows.append({"date": raw_date, "value": row["value"] or ""})
        return rows


def _read_raw_fedfunds() -> list[dict[str, str]]:
    with open(
        _EXTRACTION_DIR / "FEDFUNDS.csv", newline="", encoding="utf-8"
    ) as source:
        return list(csv.DictReader(source))


def test_market_provenance_pins_artifact_and_workbook() -> None:
    for csv_name, (source_field, source_cells, observation_count) in (
        _MARKET_PROVENANCE.items()
    ):
        artifact = _csv_path(csv_name)
        provenance = _load_provenance(csv_name)
        rows = _read_csv_rows(artifact)

        assert provenance["schema_version"] == "1.0"
        assert provenance["source_file"] == "SWR_Toolbox_v2.0.xlsx"
        assert provenance["source_sha256"] == _SWR_WORKBOOK_SHA256
        assert provenance["source_sheet"] == "Asset Returns"
        assert provenance["source_field"] == source_field
        assert provenance["source_cells"] == source_cells
        assert provenance["artifact_sha256"] == _sha256(artifact)
        assert provenance["observation_count"] == observation_count == len(rows)
        assert provenance["date_range"] == f"{rows[0]['date']} to {rows[-1]['date']}"
        assert provenance["validation_result"] == "PASS"


def test_market_artifacts_match_workbook_extraction(tmp_path: Path) -> None:
    raw_workbook = os.environ.get("ERN_SWR_WORKBOOK")
    if not raw_workbook:
        pytest.skip("ERN_SWR_WORKBOOK is not set; workbook validation skipped")
    workbook = Path(raw_workbook)
    if not workbook.exists():
        pytest.skip(f"ERN_SWR_WORKBOOK does not exist: {workbook}")

    data = workbook_returns.extract_workbook(workbook)
    assert data.source_sha256 == _SWR_WORKBOOK_SHA256
    workbook_returns.write_outputs(data, tmp_path)

    for csv_name in _MARKET_PROVENANCE:
        assert (tmp_path / csv_name).read_bytes() == _csv_path(csv_name).read_bytes()
        generated = json.loads(
            (tmp_path / csv_name.replace(".csv", ".provenance.json")).read_text(
                encoding="utf-8"
            )
        )
        assert generated == _load_provenance(csv_name)


def test_cape_provenance_is_workbook_only() -> None:
    artifact = _DATA_DIR / "cape_shiller.csv"
    provenance_path = _DATA_DIR / "cape_shiller.provenance.json"
    if not provenance_path.exists():
        pytest.skip("cape_shiller.csv has not yet been migrated to workbook provenance")

    provenance = _load_provenance("cape_shiller.csv")
    rows = _read_csv_rows(artifact)

    assert provenance["schema_version"] == "1.1"
    assert provenance["source_file"] == "SWR_Toolbox_v2.0.xlsx"
    assert provenance["source_sha256"] == _SWR_WORKBOOK_SHA256
    assert provenance["source_sheet"] == "Asset Returns"
    assert provenance["source_field"] == "O"
    assert provenance["source_field_name"] == "CAPE Shiller"
    assert provenance["source_cells"] == "O6:O1871"
    assert provenance["artifact_sha256"] == _sha256(artifact)
    assert provenance["observation_count"] == 1866 == len(rows)
    assert provenance["date_range"] == "1871-01-01 to 2026-06-01"
    assert provenance["extraction_tool"] == (
        "tools/ern/extract_workbook_returns.py"
    )
    assert provenance["extraction_tool_version"]
    assert provenance["validation_result"] == "PASS"
    assert any(
        "ie_data.csv" in transformation
        for transformation in provenance["transformations"]
    )

    assert rows[0] == {"date": "1871-01-01", "value": "11.09725"}
    assert rows[6] == {"date": "1871-07-01", "value": "12.28616144"}
    assert rows[-1] == {"date": "2026-06-01", "value": "40.62325499"}
    assert next(
        row for row in rows if row["date"] == "1881-01-01"
    )["value"] == "18.48021972"


def test_cape_artifact_matches_workbook_extraction(tmp_path: Path) -> None:
    raw_workbook = os.environ.get("ERN_SWR_WORKBOOK")
    if not raw_workbook:
        pytest.skip("ERN_SWR_WORKBOOK is not set; workbook validation skipped")
    workbook = Path(raw_workbook)
    if not workbook.exists():
        pytest.skip(f"ERN_SWR_WORKBOOK does not exist: {workbook}")

    data = workbook_returns.extract_workbook(workbook)
    assert data.source_sha256 == _SWR_WORKBOOK_SHA256
    workbook_returns.write_outputs(data, tmp_path)

    generated_rows = _read_csv_rows(tmp_path / "cape_shiller.csv")
    expected_rows = [
        {"date": date_value, "value": str(value)}
        for date_value, value in data.cape_rows
    ]
    assert generated_rows == expected_rows

    generated_provenance = json.loads(
        (tmp_path / "cape_shiller.provenance.json").read_text(encoding="utf-8")
    )
    assert generated_provenance["source_sha256"] == _SWR_WORKBOOK_SHA256
    assert generated_provenance["source_field"] == "O"
    assert generated_provenance["source_cells"] == "O6:O1871"
    assert generated_provenance["observation_count"] == 1866
    assert generated_provenance["artifact_sha256"] == _sha256(
        tmp_path / "cape_shiller.csv"
    )

    committed_provenance = _DATA_DIR / "cape_shiller.provenance.json"
    if committed_provenance.exists():
        assert generated_provenance == json.loads(
            committed_provenance.read_text(encoding="utf-8")
        )


def test_extract_workbook_rejects_wrong_expected_sha() -> None:
    raw_workbook = os.environ.get("ERN_SWR_WORKBOOK")
    if not raw_workbook:
        pytest.skip("ERN_SWR_WORKBOOK is not set; workbook validation skipped")
    workbook = Path(raw_workbook)
    if not workbook.exists():
        pytest.skip(f"ERN_SWR_WORKBOOK does not exist: {workbook}")

    with pytest.raises(ValueError, match="Unauthorized workbook SHA-256"):
        workbook_returns.extract_workbook(workbook, expected_sha256="0" * 64)


def test_ffr_provenance_defines_separate_segments() -> None:
    artifact = _DATA_DIR / "ffr.csv"
    provenance = _load_provenance("ffr.csv")
    historical = provenance["historical"]
    extension = provenance["extension"]

    assert isinstance(historical, dict)
    assert isinstance(extension, dict)
    assert provenance["schema_version"] == "2.0"
    assert provenance["artifact_sha256"] == _sha256(artifact)

    assert historical["source_file"] == "Timing-Leverage-Calc.xlsx"
    assert historical["source_sha256"] == (
        "e0a0dbea11543809b2f2e8544cc84e21a19e0ca864d8ef3664135b945bbcda38"
    )
    assert historical["source_created"] == "2022-03-12T17:11:40Z"
    assert historical["source_modified"] == "2022-03-21T20:16:41Z"
    assert historical["source_cells"] == "K4:K1815"
    assert historical["fallback"]["source_column"] == "N"

    raw_rows = _read_raw_fedfunds()
    raw_path = _EXTRACTION_DIR / "FEDFUNDS.csv"
    assert extension["source_series_id"] == "FEDFUNDS"
    assert extension["source_url"] == "https://fred.stlouisfed.org/series/FEDFUNDS"
    assert extension["source_sha256"] == _sha256(raw_path)
    assert extension["source_observation_count"] == len(raw_rows)
    assert extension["source_date_range"] == (
        f"{raw_rows[0]['observation_date']} to {raw_rows[-1]['observation_date']}"
    )
    assert extension["source_revision_status"]

    history_count = int(historical["observation_count"])
    extension_count = int(extension["observation_count"])
    rows = _read_ffr_rows(artifact)
    assert history_count + extension_count == provenance["observation_count"]
    assert provenance["observation_count"] == len(rows)
    assert rows[history_count - 1]["date"] == "2021-12-01"
    assert rows[history_count]["date"] == "2022-01-01"
    assert provenance["date_range"] == f"{rows[0]['date']} to {rows[-1]['date']}"


def test_part3_effective_metadata_retains_all_source_fingerprints() -> None:
    prepared = prepare_ern_dataset(_DATA_DIR)
    fingerprints = dict(prepared.metadata.source_sha256)
    expected = {
        "spx_tr_real.csv",
        "bond_10y_tr_real.csv",
        "cpi.csv",
        "cape_shiller.csv",
        "ffr.csv",
    }

    assert set(fingerprints) == expected
    for source_name in expected:
        assert fingerprints[source_name] == _sha256(_DATA_DIR / source_name)

    manifest = build_effective_manifest(
        dataset=prepared.dataset,
        metadata=prepared.metadata,
        cape_rows=load_cape_rows(_DATA_DIR),
        cohort_start=date(1871, 2, 1),
        cohort_end=date(2015, 12, 1),
        require_cape=True,
    )

    source_metadata = manifest.statistics["source_metadata"]
    assert source_metadata["source_sha256"] == fingerprints
    assert source_metadata["historical_data_cutoff"] == "2026-06-01"
    assert source_metadata["projection_end"] == "2075-12-01"
