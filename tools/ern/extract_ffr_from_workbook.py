"""Extract the canonical FFR runtime series from the ERN workbook.

The historical segment is extracted from ``Timing-Leverage-Calc.xlsx``,
sheet ``Return Data``, column ``K`` (``K4:K1815``). The workbook's ``K``
column is the spliced series ``IF(ISNUMBER(M), M, N)``: Federal Funds Rate
where available, otherwise the short-term yield.

The post-2021 extension is derived from FRED ``FEDFUNDS`` and is recorded
separately in the provenance file. It is not part of the original workbook.

Usage:
    python tools/ern/extract_ffr_from_workbook.py \
        --workbook /path/to/Timing-Leverage-Calc.xlsx

    python tools/ern/extract_ffr_from_workbook.py --validate-only \
        [--workbook /path/to/Timing-Leverage-Calc.xlsx]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import zipfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree

_WORKBOOK_SHEET = "Return Data"
_HISTORY_CELL_RANGE = "K4:K1815"
_HISTORY_FORMULA = "=IF(ISNUMBER(M4),M4,N4)"
_HISTORY_START = date(1871, 1, 1)
_HISTORY_END = date(2021, 12, 1)
_HISTORY_ROWS = 1812
EXTENSION_START = date(2022, 1, 1)
EXTENSION_END = date(2026, 8, 1)
_DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "ern"
_DEFAULT_EXTENSION_SOURCE = _DEFAULT_OUTPUT_DIR / "raw" / "FEDFUNDS.csv"
_FALLBACK_METADATA: dict[str, str] = {
    "source_column": "N",
    "header": "Short-term Yield (p.a.)",
    "date_range": "1871-01-01 to 1954-06-01",
    "upstream_source": "not documented in workbook",
    "vintage": "not documented in workbook",
}
_LIMITATIONS: tuple[str, ...] = (
    "FRED extension acquisition metadata (download date, request URL/query, "
    "retrieval tool) is not recorded in the repository.",
    "The workbook does not document the upstream source or vintage of column N.",
)


@dataclass(frozen=True)
class _Cell:
    value: Decimal | None
    formula: str | None
    formula_type: str | None
    shared_index: str | None


@dataclass(frozen=True)
class HistoryExtraction:
    rows: tuple[tuple[date, str], ...]
    workbook_sha256: str


@dataclass(frozen=True)
class ExtensionExtraction:
    rows: tuple[tuple[date, str], ...]
    source_sha256: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _worksheet_path(workbook: zipfile.ZipFile, sheet_name: str) -> str:
    workbook_root = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
    rels_root = ElementTree.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))

    rel_targets: dict[str, str] = {}
    for rel in rels_root.iter():
        if _local_name(rel.tag) != "Relationship":
            continue
        rel_id = rel.get("Id")
        target = rel.get("Target")
        if rel_id is not None and target is not None:
            rel_targets[rel_id] = target.lstrip("/")

    for node in workbook_root.iter():
        if _local_name(node.tag) != "sheet" or node.get("name") != sheet_name:
            continue
        rel_id = node.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        )
        if rel_id is None or rel_id not in rel_targets:
            raise ValueError(f"Cannot resolve worksheet {sheet_name!r}")
        target = rel_targets[rel_id]
        if not target.startswith("xl/"):
            target = f"xl/{target}"
        return target

    raise ValueError(f"Worksheet {sheet_name!r} not found in workbook")


def _collect_cells(root: ElementTree.Element) -> dict[str, _Cell]:
    cells: dict[str, _Cell] = {}
    for cell in root.iter():
        if _local_name(cell.tag) != "c":
            continue
        ref = cell.get("r")
        if ref is None:
            continue
        raw_value: str | None = None
        formula: str | None = None
        formula_type: str | None = None
        shared_index: str | None = None
        for child in cell:
            name = _local_name(child.tag)
            if name == "v":
                raw_value = child.text
            elif name == "f":
                formula = child.text
                formula_type = child.get("t")
                shared_index = child.get("si")
        numeric_value: Decimal | None = None
        if raw_value is not None:
            try:
                numeric_value = Decimal(raw_value)
            except InvalidOperation:
                numeric_value = None
        cells[ref] = _Cell(
            value=numeric_value,
            formula=formula,
            formula_type=formula_type,
            shared_index=shared_index,
        )
    return cells


def _next_month(day: date) -> date:
    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)


def _month_count(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month + 1


def _validate_contiguous(rows: list[tuple[date, str]], label: str) -> None:
    if not rows:
        raise ValueError(f"{label} contains no rows")
    for (previous, _), (current, _) in zip(rows, rows[1:], strict=False):
        if current != _next_month(previous):
            raise ValueError(
                f"{label} is not contiguous: {previous.isoformat()} -> {current.isoformat()}"
            )


def _validate_bounds(
    rows: list[tuple[date, str]],
    start: date,
    end: date,
    count: int,
    label: str,
) -> None:
    if len(rows) != count:
        raise ValueError(f"{label} has {len(rows)} rows, expected {count}")
    if rows[0][0] != start or rows[-1][0] != end:
        raise ValueError(
            f"{label} spans {rows[0][0].isoformat()}..{rows[-1][0].isoformat()}, "
            f"expected {start.isoformat()}..{end.isoformat()}"
        )


def _parse_artifact_date(raw: str) -> date:
    if len(raw) == 10 and raw[2] == "-" and raw[5] == "-":
        return date(int(raw[6:10]), int(raw[3:5]), int(raw[0:2]))
    return date.fromisoformat(raw)


def extract_history(workbook_path: Path) -> HistoryExtraction:
    """Extract the 1871-01..2021-12 segment from workbook column K."""
    with zipfile.ZipFile(workbook_path) as workbook:
        sheet_path = _worksheet_path(workbook, _WORKBOOK_SHEET)
        sheet_root = ElementTree.fromstring(workbook.read(sheet_path))

    cells = _collect_cells(sheet_root)
    rows: list[tuple[date, str]] = []
    shared_masters: dict[str, int] = {}
    for row_number in range(4, 1816):
        year_cell = cells.get(f"A{row_number}")
        month_cell = cells.get(f"B{row_number}")
        rate_cell = cells.get(f"K{row_number}")
        if (
            year_cell is None
            or month_cell is None
            or rate_cell is None
            or year_cell.value is None
            or month_cell.value is None
            or rate_cell.value is None
        ):
            raise ValueError(f"Missing workbook value at row {row_number}")
        if rate_cell.formula is None:
            if rate_cell.formula_type != "shared" or rate_cell.shared_index is None:
                raise ValueError(f"Missing formula in K{row_number}")
        else:
            expected_formula = (
                f"IF(ISNUMBER(M{row_number}),M{row_number},N{row_number})"
            )
            actual_formula = rate_cell.formula.removeprefix("=")
            if actual_formula != expected_formula:
                raise ValueError(
                    f"Unexpected formula in K{row_number}: "
                    f"{rate_cell.formula!r}; expected {expected_formula!r}"
                )
            if rate_cell.formula_type == "shared":
                if rate_cell.shared_index is None:
                    raise ValueError(
                        f"Shared formula in K{row_number} has no shared index"
                    )
                shared_masters[rate_cell.shared_index] = row_number
            elif rate_cell.formula_type not in (None, ""):
                raise ValueError(
                    f"Unexpected formula type in K{row_number}: "
                    f"{rate_cell.formula_type!r}"
                )
        day = date(int(year_cell.value), int(month_cell.value), 1)
        rows.append((day, str(float(rate_cell.value))))

    for row_number in range(4, 1816):
        rate_cell = cells[f"K{row_number}"]
        if rate_cell.formula is not None:
            continue
        if rate_cell.shared_index not in shared_masters:
            raise ValueError(
                f"Shared formula in K{row_number} has no validated master"
            )

    _validate_contiguous(rows, "workbook history")
    _validate_bounds(rows, _HISTORY_START, _HISTORY_END, _HISTORY_ROWS, "workbook history")
    return HistoryExtraction(rows=tuple(rows), workbook_sha256=_sha256(workbook_path))


def extract_extension(
    source_path: Path,
    start: date = EXTENSION_START,
    end: date = EXTENSION_END,
) -> ExtensionExtraction:
    """Extract the FRED FEDFUNDS extension and convert percent to decimal."""
    rows: list[tuple[date, str]] = []
    with open(source_path, newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if (
            reader.fieldnames is None
            or "observation_date" not in reader.fieldnames
            or "FEDFUNDS" not in reader.fieldnames
        ):
            raise ValueError(
                f"{source_path} must contain observation_date and FEDFUNDS columns"
            )
        for row in reader:
            raw_date = row.get("observation_date")
            raw_value = row.get("FEDFUNDS")
            if raw_date is None or raw_value is None:
                raise ValueError(f"Missing FEDFUNDS row in {source_path}")
            day = date.fromisoformat(raw_date)
            if day < start or day > end:
                continue
            value = Decimal(raw_value) / Decimal(100)
            rows.append((day, format(value, ".4f")))

    _validate_contiguous(rows, "FEDFUNDS extension")
    _validate_bounds(rows, start, end, _month_count(start, end), "FEDFUNDS extension")
    return ExtensionExtraction(rows=tuple(rows), source_sha256=_sha256(source_path))


def read_artifact(path: Path) -> tuple[tuple[date, str], ...]:
    """Read a canonical FFR CSV in either supported date format."""
    with open(path, newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no header")
        date_key = "DD-MM-YYYY" if "DD-MM-YYYY" in reader.fieldnames else "date"
        if date_key not in reader.fieldnames or "value" not in reader.fieldnames:
            raise ValueError(f"{path} must contain date and value columns")
        rows: list[tuple[date, str]] = []
        for row in reader:
            raw_date = row.get(date_key)
            raw_value = row.get("value")
            if raw_date is None or raw_value is None:
                raise ValueError(f"Missing date/value row in {path}")
            rows.append((_parse_artifact_date(raw_date), raw_value))

    _validate_contiguous(rows, "FFR artifact")
    return tuple(rows)


def render_artifact(
    history: tuple[tuple[date, str], ...],
    extension: tuple[tuple[date, str], ...],
) -> str:
    """Render the canonical DD-MM-YYYY CSV content."""
    rows = list(history) + list(extension)
    rows.sort(key=lambda row: row[0])
    _validate_contiguous(rows, "FFR artifact")

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(["DD-MM-YYYY", "value"])
    for day, value in rows:
        writer.writerow([day.strftime("%d-%m-%Y"), value])
    return buffer.getvalue()


def validate_artifact(
    path: Path,
    history: tuple[tuple[date, str], ...],
    extension: tuple[tuple[date, str], ...],
) -> list[str]:
    """Compare a written artifact with the expected historical and extension rows."""
    actual = read_artifact(path)
    expected = tuple(sorted(history + extension, key=lambda row: row[0]))
    errors: list[str] = []
    if len(actual) != len(expected):
        errors.append(f"artifact has {len(actual)} rows, expected {len(expected)}")
    for (actual_day, actual_value), (expected_day, expected_value) in zip(
        actual, expected, strict=False
    ):
        if actual_day != expected_day:
            errors.append(
                f"date mismatch: artifact={actual_day.isoformat()} "
                f"expected={expected_day.isoformat()}"
            )
        if actual_value != expected_value:
            errors.append(
                f"value mismatch at {expected_day.isoformat()}: "
                f"artifact={actual_value} expected={expected_value}"
            )
    return errors


def _date_range(rows: tuple[tuple[date, str], ...]) -> str:
    if not rows:
        return ""
    return f"{rows[0][0].isoformat()} to {rows[-1][0].isoformat()}"


def build_provenance(
    history: HistoryExtraction,
    extension: ExtensionExtraction | None,
    artifact_sha256: str,
) -> dict[str, object]:
    """Build provenance with separate historical and extension segments."""
    combined = history.rows + (extension.rows if extension is not None else ())
    provenance: dict[str, object] = {
        "artifact": "ffr.csv",
        "artifact_sha256": artifact_sha256,
        "schema_version": "2.0",
        "historical": {
            "source_file": "Timing-Leverage-Calc.xlsx",
            "source_url": (
                "https://earlyretirementnow.com/wp-content/uploads/2022/03/"
                "Timing-Leverage-Calc.xlsx"
            ),
            "source_sha256": history.workbook_sha256,
            "source_created": "2022-03-12T17:11:40Z",
            "source_modified": "2022-03-21T20:16:41Z",
            "source_sheet": _WORKBOOK_SHEET,
            "source_cells": _HISTORY_CELL_RANGE,
            "source_formula": _HISTORY_FORMULA,
            "source_date_format": "year (column A), month (column B)",
            "source_numeric_type": (
                "cached Excel value, rendered as Python float shortest "
                "round-trip decimal"
            ),
            "extraction_method": (
                "Direct cached-value extraction; the workbook XML value is "
                "parsed as Decimal and rendered with Python float "
                "shortest round-trip representation. K formulas are "
                "validated, including shared-formula masters. No formula "
                "re-evaluation or financial reconstruction."
            ),
            "observation_count": len(history.rows),
            "date_range": _date_range(history.rows),
            "fallback": dict(_FALLBACK_METADATA),
            "validation_result": "PASS",
        },
        "observation_count": len(combined),
        "date_range": _date_range(combined),
        "validation_result": "PASS",
        "notes": (
            "Historical segment is the workbook's spliced FFR/3M-yield series. "
            "The post-2021 extension is FRED FEDFUNDS and is not part of the "
            "original workbook."
        ),
        "limitations": list(_LIMITATIONS),
    }
    if extension is not None:
        provenance["extension"] = {
            "source_file": "data/ern/raw/FEDFUNDS.csv",
            "source_series_id": "FEDFUNDS",
            "source_url": "https://fred.stlouisfed.org/series/FEDFUNDS",
            "source_field": "FEDFUNDS",
            "source_sha256": extension.source_sha256,
            "source_observation_count": 866,
            "source_date_range": "1954-07-01 to 2026-08-01",
            "source_units": "percent per annum",
            "output_units": "decimal per annum",
            "source_revision_status": (
                "FRED series is subject to revision; this artifact uses a "
                "frozen local snapshot pinned by SHA-256"
            ),
            "transformation": "value / 100, formatted to 4 decimal places",
            "observation_count": len(extension.rows),
            "date_range": _date_range(extension.rows),
            "validation_result": "PASS",
        }
    return provenance


def _write_provenance(path: Path, provenance: dict[str, object]) -> None:
    path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")


def _validate_only(
    artifact_path: Path,
    workbook_path: Path | None,
    extension_source: Path,
    no_extension: bool,
) -> int:
    if not artifact_path.exists():
        print(f"artifact validation: FAIL (missing {artifact_path})")
        return 1

    try:
        artifact_rows = read_artifact(artifact_path)
    except ValueError as error:
        print(f"artifact validation: FAIL ({error})")
        return 1
    print(f"artifact structure: PASS ({len(artifact_rows)} rows)")

    errors: list[str] = []
    validated_segments = 0
    history_rows: tuple[tuple[date, str], ...] | None = None
    extension_rows: tuple[tuple[date, str], ...] | None = None

    if workbook_path is None:
        print("historical validation: SKIPPED (workbook unavailable)")
    elif not workbook_path.exists():
        print(f"historical validation: SKIPPED (workbook not found: {workbook_path})")
    else:
        try:
            history = extract_history(workbook_path)
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            print(f"historical validation: FAIL ({error})")
            errors.append(str(error))
        else:
            history_rows = history.rows
            actual = artifact_rows[: len(history.rows)]
            if actual == history.rows:
                print(
                    f"historical validation: PASS ({len(history.rows)} rows, "
                    f"{_date_range(history.rows)})"
                )
                validated_segments += 1
            else:
                message = "artifact historical segment does not match workbook K"
                print(f"historical validation: FAIL ({message})")
                errors.append(message)

    if no_extension:
        print("extension validation: SKIPPED (--no-extension)")
    elif not extension_source.exists():
        print(f"extension validation: SKIPPED (source not found: {extension_source})")
    else:
        try:
            extension = extract_extension(extension_source)
        except (OSError, ValueError) as error:
            print(f"extension validation: FAIL ({error})")
            errors.append(str(error))
        else:
            extension_rows = extension.rows
            actual = artifact_rows[-len(extension.rows) :]
            if actual == extension.rows:
                print(
                    f"extension validation: PASS ({len(extension.rows)} rows, "
                    f"{_date_range(extension.rows)})"
                )
                validated_segments += 1
            else:
                message = "artifact extension does not match raw FEDFUNDS"
                print(f"extension validation: FAIL ({message})")
                errors.append(message)

    if history_rows is not None and extension_rows is not None:
        expected_count = len(history_rows) + len(extension_rows)
        if len(artifact_rows) != expected_count:
            errors.append(
                f"artifact has {len(artifact_rows)} rows, expected {expected_count}"
            )

    if errors:
        print("overall: FAIL")
        return 1
    if validated_segments == 0:
        print("overall: PASS (structure only; requested validations were skipped)")
    else:
        print("overall: PASS (available checks)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workbook",
        type=Path,
        help="Path to Timing-Leverage-Calc.xlsx",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_DEFAULT_OUTPUT_DIR,
        help="Directory containing ffr.csv and ffr.provenance.json",
    )
    parser.add_argument(
        "--extension-source",
        type=Path,
        default=_DEFAULT_EXTENSION_SOURCE,
        help="FRED FEDFUNDS CSV used for the post-2021 extension",
    )
    parser.add_argument(
        "--no-extension",
        action="store_true",
        help="Write only the 1871-01..2021-12 workbook segment",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the existing artifact without writing anything",
    )
    args = parser.parse_args(argv)

    artifact_path = args.output_dir / "ffr.csv"
    provenance_path = args.output_dir / "ffr.provenance.json"

    if args.validate_only:
        return _validate_only(
            artifact_path,
            args.workbook,
            args.extension_source,
            args.no_extension,
        )

    if args.workbook is None:
        parser.error("--workbook is required unless --validate-only is used")
    if not args.workbook.exists():
        parser.error(f"workbook not found: {args.workbook}")

    try:
        history = extract_history(args.workbook)
        extension = None
        if not args.no_extension:
            if not args.extension_source.exists():
                parser.error(f"extension source not found: {args.extension_source}")
            extension = extract_extension(args.extension_source)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"extraction: FAIL ({error})")
        return 1

    extension_rows = extension.rows if extension is not None else ()
    content = render_artifact(history.rows, extension_rows)
    artifact_bytes = content.encode("utf-8")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    previous = artifact_path.read_bytes() if artifact_path.exists() else None
    if previous != artifact_bytes:
        artifact_path.write_text(content, encoding="utf-8", newline="")

    errors = validate_artifact(artifact_path, history.rows, extension_rows)
    if errors:
        if previous is None:
            artifact_path.unlink(missing_ok=True)
        else:
            artifact_path.write_bytes(previous)
        print("artifact validation: FAIL")
        for message in errors:
            print(f"  {message}")
        return 1

    artifact_sha256 = _sha256(artifact_path)
    _write_provenance(
        provenance_path,
        build_provenance(history, extension, artifact_sha256),
    )

    print(
        f"historical: {len(history.rows)} rows ({_date_range(history.rows)}) PASS"
    )
    if extension is not None:
        print(
            f"extension: {len(extension.rows)} rows "
            f"({_date_range(extension.rows)}) PASS"
        )
    else:
        print("extension: SKIPPED (--no-extension)")
    print(
        f"artifact: {len(history.rows) + len(extension_rows)} rows "
        f"({_date_range(history.rows + extension_rows)}) PASS"
    )
    state = "unchanged" if previous == content.encode("utf-8") else "updated"
    print(f"wrote {artifact_path} ({state})")
    print(f"wrote {provenance_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
