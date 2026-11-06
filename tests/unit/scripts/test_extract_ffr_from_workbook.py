"""Focused tests for the workbook-derived FFR extraction tool."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from tools.ern import extract_ffr_from_workbook as ffr

_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "ern"
_ARTIFACT = _DATA_DIR / "ffr.csv"
_PROVENANCE = _DATA_DIR / "ffr.provenance.json"
_EXTENSION_SOURCE = _DATA_DIR / "raw" / "FEDFUNDS.csv"


def _months(start: date, end: date) -> list[date]:
    result: list[date] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        result.append(date(year, month, 1))
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
    return result


def _write_minimal_workbook(
    path: Path,
    rows: list[tuple[date, str]],
    formula_template: str = "IF(ISNUMBER(M{row}),M{row},N{row})",
    shared_formulas: bool = False,
) -> None:
    sheet_rows: list[str] = []
    for row_number, (day, value) in enumerate(rows, start=4):
        formula = formula_template.format(row=row_number)
        if shared_formulas and row_number == 4:
            formula_xml = (
                f'<f t="shared" ref="K4:K1815" si="0">{formula}</f>'
            )
        elif shared_formulas:
            formula_xml = '<f t="shared" si="0"/>'
        else:
            formula_xml = f"<f>{formula}</f>"
        sheet_rows.append(
            f'<row r="{row_number}">'
            f'<c r="A{row_number}"><v>{day.year}</v></c>'
            f'<c r="B{row_number}"><v>{day.month}</v></c>'
            f'<c r="K{row_number}">'
            f"{formula_xml}"
            f"<v>{value}</v></c></row>"
        )
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Return Data" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    with zipfile.ZipFile(path, "w") as workbook:
        workbook.writestr("xl/workbook.xml", workbook_xml)
        workbook.writestr("xl/_rels/workbook.xml.rels", rels_xml)
        workbook.writestr("xl/worksheets/sheet1.xml", sheet_xml)


def _write_extension_source(path: Path) -> None:
    days = _months(ffr.EXTENSION_START, ffr.EXTENSION_END)
    with open(path, "w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["observation_date", "FEDFUNDS"])
        for index, day in enumerate(days):
            value = Decimal("0.08") + Decimal(index) / Decimal(100)
            writer.writerow([day.isoformat(), format(value, ".2f")])


def test_extract_history_from_synthetic_workbook(tmp_path: Path) -> None:
    days = _months(date(1871, 1, 1), date(2021, 12, 1))
    rows = [(day, f"0.{index:04d}") for index, day in enumerate(days)]
    workbook = tmp_path / "workbook.xlsx"
    _write_minimal_workbook(workbook, rows)

    result = ffr.extract_history(workbook)

    assert len(result.rows) == 1812
    assert result.rows[0] == (date(1871, 1, 1), "0.0")
    assert result.rows[-1] == (date(2021, 12, 1), "0.1811")
    assert result.workbook_sha256 == hashlib.sha256(workbook.read_bytes()).hexdigest()


def test_extract_history_accepts_shared_formulas(tmp_path: Path) -> None:
    days = _months(date(1871, 1, 1), date(2021, 12, 1))
    rows = [(day, "0.0100") for day in days]
    workbook = tmp_path / "workbook.xlsx"
    _write_minimal_workbook(workbook, rows, shared_formulas=True)

    result = ffr.extract_history(workbook)

    assert len(result.rows) == 1812
    assert result.rows[0] == (date(1871, 1, 1), "0.01")
    assert result.rows[-1] == (date(2021, 12, 1), "0.01")


def test_extract_history_rejects_wrong_formula(tmp_path: Path) -> None:
    days = _months(date(1871, 1, 1), date(2021, 12, 1))
    rows = [(day, "0.0100") for day in days]
    workbook = tmp_path / "workbook.xlsx"
    _write_minimal_workbook(workbook, rows, formula_template="M{row}")

    with pytest.raises(ValueError, match="Unexpected formula in K4"):
        ffr.extract_history(workbook)


def test_extract_history_rejects_wrong_date_boundary(tmp_path: Path) -> None:
    days = _months(date(1870, 12, 1), date(2021, 11, 1))
    rows = [(day, "0.0100") for day in days]
    workbook = tmp_path / "workbook.xlsx"
    _write_minimal_workbook(workbook, rows)

    with pytest.raises(ValueError, match="expected 1871-01-01..2021-12-01"):
        ffr.extract_history(workbook)


def test_extract_extension_from_raw_fedfunds(tmp_path: Path) -> None:
    days = _months(ffr.EXTENSION_START, ffr.EXTENSION_END)
    source = tmp_path / "FEDFUNDS.csv"
    with open(source, "w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["observation_date", "FEDFUNDS"])
        for index, day in enumerate(days):
            value = Decimal("0.08") + Decimal(index) / Decimal(100)
            writer.writerow([day.isoformat(), format(value, ".2f")])

    result = ffr.extract_extension(source)

    assert len(result.rows) == 56
    assert result.rows[0] == (date(2022, 1, 1), "0.0008")
    assert result.rows[2] == (date(2022, 3, 1), "0.0010")
    assert result.rows[-1] == (date(2026, 8, 1), "0.0063")


def test_extract_extension_rejects_missing_range(tmp_path: Path) -> None:
    source = tmp_path / "FEDFUNDS.csv"
    source.write_text(
        "observation_date,FEDFUNDS\n2022-01-01,0.08\n2022-02-01,0.08\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="has 2 rows, expected 56"):
        ffr.extract_extension(source)


def test_committed_artifact_boundaries() -> None:
    rows = ffr.read_artifact(_ARTIFACT)

    assert len(rows) == 1868
    assert rows[0][0] == date(1871, 1, 1)
    assert rows[1811][0] == date(2021, 12, 1)
    assert rows[1812][0] == date(2022, 1, 1)
    assert rows[-1][0] == date(2026, 8, 1)


def test_committed_extension_matches_raw_fedfunds() -> None:
    extension = ffr.extract_extension(_EXTENSION_SOURCE)
    artifact = dict(ffr.read_artifact(_ARTIFACT))

    for day, value in extension.rows:
        assert artifact[day] == value


def test_committed_artifact_matches_workbook_when_available() -> None:
    raw_workbook = os.environ.get("ERN_TIMING_WORKBOOK")
    if not raw_workbook:
        pytest.skip("ERN_TIMING_WORKBOOK is not set; workbook validation skipped")
    workbook = Path(raw_workbook)
    if not workbook.exists():
        pytest.skip(f"ERN_TIMING_WORKBOOK does not exist: {workbook}")

    history = ffr.extract_history(workbook)
    extension = ffr.extract_extension(_EXTENSION_SOURCE)
    artifact = ffr.read_artifact(_ARTIFACT)

    assert artifact[: len(history.rows)] == history.rows
    assert artifact[-len(extension.rows) :] == extension.rows
    assert ffr.render_artifact(history.rows, extension.rows).encode("utf-8") == (
        _ARTIFACT.read_bytes()
    )


def test_committed_provenance_matches_build_provenance() -> None:
    rows = ffr.read_artifact(_ARTIFACT)
    approved = json.loads(_PROVENANCE.read_text(encoding="utf-8"))
    history_count = approved["historical"]["observation_count"]
    history = ffr.HistoryExtraction(
        rows=rows[:history_count],
        workbook_sha256=approved["historical"]["source_sha256"],
    )
    extension = ffr.ExtensionExtraction(
        rows=rows[history_count:],
        source_sha256=approved["extension"]["source_sha256"],
    )

    generated = ffr.build_provenance(
        history,
        extension,
        approved["artifact_sha256"],
    )

    assert generated == approved


def test_main_generates_provenance_without_rewriting_unchanged_artifact(
    tmp_path: Path,
) -> None:
    days = _months(date(1871, 1, 1), date(2021, 12, 1))
    rows = [(day, f"0.{index:04d}") for index, day in enumerate(days)]
    workbook = tmp_path / "workbook.xlsx"
    _write_minimal_workbook(workbook, rows)
    extension_source = tmp_path / "FEDFUNDS.csv"
    _write_extension_source(extension_source)
    output_dir = tmp_path / "output"
    args = [
        "--workbook",
        str(workbook),
        "--output-dir",
        str(output_dir),
        "--extension-source",
        str(extension_source),
    ]

    assert ffr.main(args) == 0

    artifact = output_dir / "ffr.csv"
    provenance_path = output_dir / "ffr.provenance.json"
    artifact_bytes = artifact.read_bytes()
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))

    assert provenance["artifact_sha256"] == hashlib.sha256(artifact_bytes).hexdigest()
    assert provenance["historical"]["fallback"]["source_column"] == "N"
    assert provenance["limitations"]
    assert not (output_dir / "ffr_monthly.json").exists()

    fixed_ns = 1_000_000_000_000_000_000
    os.utime(artifact, ns=(fixed_ns, fixed_ns))
    before_mtime = artifact.stat().st_mtime_ns

    assert ffr.main(args) == 0
    assert artifact.read_bytes() == artifact_bytes
    assert artifact.stat().st_mtime_ns == before_mtime
