#!/usr/bin/env python3
"""Extract exact production data from the SWR Toolbox v2.0 workbook.

The workbook is the single source of truth for production ERN data.  This tool
reads the cached values of the ``Asset Returns`` sheet and writes the canonical
CSV files consumed by ``fbf.core.datasets.ern`` plus the combined exact-return
fixture used by ``tools.ern.workbook_oracle``.

Extracted columns (``Asset Returns``):

- ``A``/``B``: month and year (the workbook's date key)
- ``E``: CPI level
- ``F``: S&P 500 total-return nominal index
- ``G``: 10-year bond market cumulative nominal index
- ``O``: Shiller CAPE (authoritative canonical CAPE)
- ``Q``: S&P 500 total-return real return
- ``R``: 10-year bond market total-return real return

Only workbook cached values are used.  No formula is re-evaluated, rounded, or
reconstructed, so the extracted values are exactly the values Excel computed.
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
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree

_TOOL_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TOOL_DIR.parents[1]
_DEFAULT_OUTPUT_DIR = _REPO_ROOT / "data" / "outputs" / "ern-extraction"

_ASSET_RETURNS = "Asset Returns"
_FIRST_INDEX_ROW = 6  # 1871-01
_FIRST_RETURN_ROW = 7  # 1871-02
_LAST_RETURN_ROW = 1871  # 2026-06

AUTHORIZED_SWR_WORKBOOK_SHA256 = (
    "d393e898a918e179d381768b187c8d5b54f58050500190b9e69403321acdf2c6"
)
EXTRACTION_TOOL = "tools/ern/extract_workbook_returns.py"
EXTRACTION_TOOL_VERSION = "1.1.0"


@dataclass(frozen=True)
class WorkbookRow:
    """One row of exact workbook production data."""

    date: str
    cpi: Decimal
    spx_tr: Decimal
    bm10: Decimal
    equity_real_return: Decimal
    bond_real_return: Decimal


@dataclass(frozen=True)
class WorkbookData:
    """Extracted index rows, return rows, CAPE rows, and source identity."""

    index_rows: tuple[tuple[str, Decimal, Decimal, Decimal], ...]
    return_rows: tuple[WorkbookRow, ...]
    cape_rows: tuple[tuple[str, Decimal], ...]
    source_sha256: str


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _worksheet_path(workbook: zipfile.ZipFile, sheet_name: str) -> str:
    """Resolve a worksheet name to its package path."""
    workbook_root = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
    rels_root = ElementTree.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))

    rel_targets: dict[str, str] = {}
    for rel in rels_root.iter():
        if _local_name(rel.tag) == "Relationship":
            rel_id = rel.get("Id")
            target = rel.get("Target")
            if rel_id is not None and target is not None:
                rel_targets[rel_id] = target.lstrip("/")

    for node in workbook_root.iter():
        if _local_name(node.tag) == "sheet" and node.get("name") == sheet_name:
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


@dataclass(frozen=True)
class _Cell:
    value: Decimal | None
    has_formula: bool


def _collect_cells(root: ElementTree.Element) -> dict[str, _Cell]:
    cells: dict[str, _Cell] = {}
    for cell in root.iter():
        if _local_name(cell.tag) != "c":
            continue
        ref = cell.get("r")
        if ref is None:
            continue
        raw_value: str | None = None
        has_formula = False
        for child in cell:
            name = _local_name(child.tag)
            if name == "v":
                raw_value = child.text
            elif name == "f":
                has_formula = True
        numeric_value: Decimal | None = None
        if raw_value is not None:
            try:
                numeric_value = Decimal(raw_value)
            except InvalidOperation:
                numeric_value = None
        cells[ref] = _Cell(value=numeric_value, has_formula=has_formula)
    return cells


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _month_date(year: int, month: int) -> str:
    if not 1 <= month <= 12:
        raise ValueError(f"Invalid month {month} for year {year}")
    return f"{year:04d}-{month:02d}-01"


def _next_month(date: str) -> str:
    year, month, _day = (int(part) for part in date.split("-"))
    if month == 12:
        return _month_date(year + 1, 1)
    return _month_date(year, month + 1)


def _parse_cape(cells: dict[str, _Cell], row_number: int) -> Decimal:
    """Return the positive cached CAPE value for one workbook row."""
    cell = cells.get(f"O{row_number}")
    if cell is None or cell.value is None:
        raise ValueError(f"Missing Shiller CAPE value at O{row_number}")
    if cell.value <= 0:
        raise ValueError(f"Invalid Shiller CAPE value at O{row_number}: {cell.value}")
    return cell.value


def extract_workbook(
    workbook_path: Path,
    *,
    expected_sha256: str | None = AUTHORIZED_SWR_WORKBOOK_SHA256,
) -> WorkbookData:
    """Extract and validate all production rows from the workbook.

    ``expected_sha256`` defaults to the authorized SWR workbook identity.  Pass
    ``None`` only for synthetic test workbooks; production extraction must never
    disable identity verification.
    """
    source_sha256 = _sha256(workbook_path)
    if expected_sha256 is not None and source_sha256 != expected_sha256:
        raise ValueError(
            f"Unauthorized workbook SHA-256: {source_sha256}; "
            f"expected {expected_sha256}"
        )

    with zipfile.ZipFile(workbook_path) as workbook:
        sheet_path = _worksheet_path(workbook, _ASSET_RETURNS)
        sheet_root = ElementTree.fromstring(workbook.read(sheet_path))
    cells = _collect_cells(sheet_root)

    def value(ref: str) -> Decimal | None:
        cell = cells.get(ref)
        return cell.value if cell is not None else None

    def has_formula(ref: str) -> bool:
        cell = cells.get(ref)
        return cell.has_formula if cell is not None else False

    index_rows: list[tuple[str, Decimal, Decimal, Decimal]] = []
    cape_rows: list[tuple[str, Decimal]] = []
    rows: list[WorkbookRow] = []
    previous_date: str | None = None
    for row_number in range(_FIRST_INDEX_ROW, _LAST_RETURN_ROW + 1):
        year_value = value(f"B{row_number}")
        month_value = value(f"A{row_number}")
        cpi = value(f"E{row_number}")
        spx_tr = value(f"F{row_number}")
        bm10 = value(f"G{row_number}")
        if year_value is None or month_value is None:
            raise ValueError(f"Missing date key at row {row_number}")
        if cpi is None or spx_tr is None or bm10 is None:
            raise ValueError(f"Missing CPI/SPX-TR/BM10 value at row {row_number}")

        date = _month_date(int(year_value), int(month_value))
        if previous_date is not None and date != _next_month(previous_date):
            raise ValueError(
                f"Non-contiguous workbook dates at row {row_number}: "
                f"{previous_date} -> {date}"
            )
        previous_date = date

        index_rows.append((date, cpi, spx_tr, bm10))
        cape_rows.append((date, _parse_cape(cells, row_number)))
        if row_number < _FIRST_RETURN_ROW:
            continue

        for column in ("Q", "R"):
            if not has_formula(f"{column}{row_number}"):
                raise ValueError(
                    f"Expected formula in {column}{row_number}; "
                    "refusing to extract a non-workbook return"
                )

        equity_return = value(f"Q{row_number}")
        bond_return = value(f"R{row_number}")
        if equity_return is None or bond_return is None:
            raise ValueError(f"Missing real return at row {row_number}")

        rows.append(
            WorkbookRow(
                date=date,
                cpi=cpi,
                spx_tr=spx_tr,
                bm10=bm10,
                equity_real_return=equity_return,
                bond_real_return=bond_return,
            )
        )

    if not rows:
        raise ValueError("No production rows extracted from workbook")
    if index_rows[0][0] != "1871-01-01":
        raise ValueError(f"Unexpected first index date: {index_rows[0][0]}")
    if rows[0].date != "1871-02-01":
        raise ValueError(f"Unexpected first production date: {rows[0].date}")
    if rows[-1].date != "2026-06-01":
        raise ValueError(f"Unexpected last production date: {rows[-1].date}")
    if len(cape_rows) != len(index_rows):
        raise ValueError(
            f"CAPE row count {len(cape_rows)} does not match "
            f"index row count {len(index_rows)}"
        )
    if cape_rows[0][0] != "1871-01-01":
        raise ValueError(f"Unexpected first CAPE date: {cape_rows[0][0]}")
    if cape_rows[-1][0] != "2026-06-01":
        raise ValueError(f"Unexpected last CAPE date: {cape_rows[-1][0]}")
    return WorkbookData(
        index_rows=tuple(index_rows),
        return_rows=tuple(rows),
        cape_rows=tuple(cape_rows),
        source_sha256=source_sha256,
    )


def _csv_text(header: list[str], rows: list[list[str]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()


def _write_csv(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _provenance(
    *,
    artifact_sha256: str,
    source_sha256: str,
    source_field: str,
    source_sheet: str,
    source_cells: str,
    observation_count: int,
    date_range: str,
    notes: str,
) -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "source_file": "SWR_Toolbox_v2.0.xlsx",
            "source_sha256": source_sha256,
            "source_sheet": source_sheet,
            "source_field": source_field,
            "source_cells": source_cells,
            "source_date_format": "year (column B), month (column A)",
            "source_numeric_type": "cached Excel value (preserved exactly)",
            "extraction_method": (
                "Direct cached-value extraction; no formula re-evaluation, "
                "rounding, or normalization."
            ),
            "observation_count": observation_count,
            "date_range": date_range,
            "artifact_sha256": artifact_sha256,
            "validation_result": "PASS",
            "notes": notes,
        },
        indent=2,
    ) + "\n"


def _cape_provenance(
    *,
    artifact_sha256: str,
    source_sha256: str,
    observation_count: int,
    date_range: str,
) -> str:
    """Build the workbook-only CAPE provenance record."""
    return json.dumps(
        {
            "schema_version": "1.1",
            "source_file": "SWR_Toolbox_v2.0.xlsx",
            "source_sha256": source_sha256,
            "source_sheet": _ASSET_RETURNS,
            "source_field": "O",
            "source_field_name": "CAPE Shiller",
            "source_cells": "O6:O1871",
            "source_date_format": "year (column B), month (column A)",
            "source_numeric_type": "cached Excel value (preserved exactly)",
            "extraction_tool": EXTRACTION_TOOL,
            "extraction_tool_version": EXTRACTION_TOOL_VERSION,
            "extraction_method": (
                "Direct cached-value extraction; no formula re-evaluation, "
                "rounding, normalization, interpolation, or date extension."
            ),
            "transformations": [
                "Read Asset Returns!O cached values for rows 6-1871.",
                "No merge with ie_data.csv, Shiller JSON, "
                "canonical/ern_asset_returns.csv, or external observations.",
                "No gap filling, rounding, or coverage extension.",
            ],
            "observation_count": observation_count,
            "date_range": date_range,
            "artifact_sha256": artifact_sha256,
            "validation_result": "PASS",
            "notes": (
                "Authoritative Shiller CAPE series for canonical ERN research; "
                "workbook column O only."
            ),
        },
        indent=2,
    ) + "\n"


def write_outputs(data: WorkbookData, output_dir: Path) -> list[Path]:
    """Write canonical production CSVs and the exact oracle fixture."""
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    rows = data.return_rows
    return_rows = [
        [row.date, str(row.equity_real_return), str(row.bond_real_return)]
        for row in rows
    ]
    index_rows = [[date, str(cpi)] for date, cpi, _spx, _bm10 in data.index_rows]
    spx_rows = [[date, str(spx)] for date, _cpi, spx, _bm10 in data.index_rows]
    bm10_rows = [[date, str(bm10)] for date, _cpi, _spx, bm10 in data.index_rows]
    equity_rows = [[row.date, str(row.equity_real_return)] for row in rows]
    bond_rows = [[row.date, str(row.bond_real_return)] for row in rows]
    cape_rows = [[date, str(cape)] for date, cape in data.cape_rows]

    targets = {
        "workbook_returns.csv": _csv_text(
            ["date", "equity_real_return", "bond_real_return"], return_rows
        ),
        "spx_tr_real.csv": _csv_text(["date", "value"], equity_rows),
        "bond_10y_tr_real.csv": _csv_text(["date", "value"], bond_rows),
        "spx_tr.csv": _csv_text(["date", "value"], spx_rows),
        "bm10.csv": _csv_text(["date", "value"], bm10_rows),
        "cpi.csv": _csv_text(["date", "value"], index_rows),
        "cape_shiller.csv": _csv_text(["date", "value"], cape_rows),
    }
    for name, text in targets.items():
        path = output_dir / name
        _write_csv(path, text)
        written.append(path)

    date_range = f"{rows[0].date} to {rows[-1].date}"
    provenance_targets = {
        "workbook_returns.provenance.json": _provenance(
            artifact_sha256=hashlib.sha256(
                targets["workbook_returns.csv"].encode("utf-8")
            ).hexdigest(),
            source_sha256=data.source_sha256,
            source_field="Q (equity real return), R (bond real return)",
            source_sheet=_ASSET_RETURNS,
            source_cells="Q7:Q1871, R7:R1871",
            observation_count=len(rows),
            date_range=date_range,
            notes="Exact combined oracle fixture for tools/ern/workbook_oracle.py",
        ),
        "spx_tr_real.provenance.json": _provenance(
            artifact_sha256=hashlib.sha256(
                targets["spx_tr_real.csv"].encode("utf-8")
            ).hexdigest(),
            source_sha256=data.source_sha256,
            source_field="Q",
            source_sheet=_ASSET_RETURNS,
            source_cells="Q7:Q1871",
            observation_count=len(rows),
            date_range=date_range,
            notes="S&P 500 total-return monthly real returns",
        ),
        "bond_10y_tr_real.provenance.json": _provenance(
            artifact_sha256=hashlib.sha256(
                targets["bond_10y_tr_real.csv"].encode("utf-8")
            ).hexdigest(),
            source_sha256=data.source_sha256,
            source_field="R",
            source_sheet=_ASSET_RETURNS,
            source_cells="R7:R1871",
            observation_count=len(rows),
            date_range=date_range,
            notes="10-year bond market total-return monthly real returns",
        ),
        "spx_tr.provenance.json": _provenance(
            artifact_sha256=hashlib.sha256(
                targets["spx_tr.csv"].encode("utf-8")
            ).hexdigest(),
            source_sha256=data.source_sha256,
            source_field="F",
            source_sheet=_ASSET_RETURNS,
            source_cells="F6:F1871",
            observation_count=len(data.index_rows),
            date_range=f"{data.index_rows[0][0]} to {data.index_rows[-1][0]}",
            notes="S&P 500 total-return nominal index",
        ),
        "bm10.provenance.json": _provenance(
            artifact_sha256=hashlib.sha256(
                targets["bm10.csv"].encode("utf-8")
            ).hexdigest(),
            source_sha256=data.source_sha256,
            source_field="G",
            source_sheet=_ASSET_RETURNS,
            source_cells="G6:G1871",
            observation_count=len(data.index_rows),
            date_range=f"{data.index_rows[0][0]} to {data.index_rows[-1][0]}",
            notes="10-year bond market cumulative nominal index",
        ),
        "cpi.provenance.json": _provenance(
            artifact_sha256=hashlib.sha256(
                targets["cpi.csv"].encode("utf-8")
            ).hexdigest(),
            source_sha256=data.source_sha256,
            source_field="E",
            source_sheet=_ASSET_RETURNS,
            source_cells="E6:E1871",
            observation_count=len(data.index_rows),
            date_range=f"{data.index_rows[0][0]} to {data.index_rows[-1][0]}",
            notes="CPI level",
        ),
        "cape_shiller.provenance.json": _cape_provenance(
            artifact_sha256=hashlib.sha256(
                targets["cape_shiller.csv"].encode("utf-8")
            ).hexdigest(),
            source_sha256=data.source_sha256,
            observation_count=len(data.cape_rows),
            date_range=f"{data.cape_rows[0][0]} to {data.cape_rows[-1][0]}",
        ),
    }
    for name, text in provenance_targets.items():
        path = output_dir / name
        _write_csv(path, text)
        written.append(path)

    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workbook",
        type=Path,
        required=True,
        help="Path to SWR_Toolbox_v2.0.xlsx",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_DEFAULT_OUTPUT_DIR,
        help=(
            "Directory for the extracted review bundle "
            "(default: data/outputs/ern-extraction)"
        ),
    )
    args = parser.parse_args(argv)

    data = extract_workbook(args.workbook)
    written = write_outputs(data, args.output_dir)
    rows = data.return_rows
    print(
        f"Extracted {len(rows)} monthly return rows "
        f"({rows[0].date} to {rows[-1].date}), "
        f"{len(data.index_rows)} monthly index rows, and "
        f"{len(data.cape_rows)} monthly CAPE rows"
    )
    for path in written:
        print(f"  wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
