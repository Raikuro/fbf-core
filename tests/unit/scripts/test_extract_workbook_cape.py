"""Focused tests for workbook CAPE extraction and provenance."""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

import pytest

from tools.ern import extract_workbook_returns as workbook_returns


def _cell(value: str | None) -> workbook_returns._Cell:
    return workbook_returns._Cell(
        value=Decimal(value) if value is not None else None,
        has_formula=False,
    )


def test_parse_cape_reads_cached_column_o_value() -> None:
    cells = {"O6": _cell("11.09725")}

    assert workbook_returns._parse_cape(cells, 6) == Decimal("11.09725")


def test_parse_cape_rejects_missing_or_non_positive_values() -> None:
    with pytest.raises(ValueError, match="Missing Shiller CAPE"):
        workbook_returns._parse_cape({}, 6)

    with pytest.raises(ValueError, match="Invalid Shiller CAPE"):
        workbook_returns._parse_cape({"O6": _cell("0")}, 6)


def test_write_outputs_emits_workbook_only_cape_provenance(tmp_path: Path) -> None:
    data = workbook_returns.WorkbookData(
        index_rows=(
            ("1871-01-01", Decimal("12.0"), Decimal("100.0"), Decimal("100.0")),
            ("1871-02-01", Decimal("12.1"), Decimal("101.0"), Decimal("100.5")),
        ),
        return_rows=(
            workbook_returns.WorkbookRow(
                date="1871-02-01",
                cpi=Decimal("12.1"),
                spx_tr=Decimal("101.0"),
                bm10=Decimal("100.5"),
                equity_real_return=Decimal("0.01"),
                bond_real_return=Decimal("0.005"),
            ),
        ),
        cape_rows=(
            ("1871-01-01", Decimal("11.09725")),
            ("1871-02-01", Decimal("10.91933677")),
        ),
        source_sha256=workbook_returns.AUTHORIZED_SWR_WORKBOOK_SHA256,
    )

    workbook_returns.write_outputs(data, tmp_path)

    with open(tmp_path / "cape_shiller.csv", newline="", encoding="utf-8") as source:
        rows = list(csv.reader(source))
    assert rows == [
        ["date", "value"],
        ["1871-01-01", "11.09725"],
        ["1871-02-01", "10.91933677"],
    ]

    provenance = json.loads(
        (tmp_path / "cape_shiller.provenance.json").read_text(encoding="utf-8")
    )
    assert provenance["source_file"] == "SWR_Toolbox_v2.0.xlsx"
    assert provenance["source_sha256"] == workbook_returns.AUTHORIZED_SWR_WORKBOOK_SHA256
    assert provenance["source_sheet"] == "Asset Returns"
    assert provenance["source_field"] == "O"
    assert provenance["source_cells"] == "O6:O1871"
    assert provenance["observation_count"] == 2
    assert provenance["date_range"] == "1871-01-01 to 1871-02-01"
    assert provenance["extraction_tool"] == "tools/ern/extract_workbook_returns.py"
    assert provenance["extraction_tool_version"] == "1.1.0"
    assert provenance["validation_result"] == "PASS"
    assert any(
        "ie_data.csv" in transformation
        for transformation in provenance["transformations"]
    )


def test_extract_workbook_rejects_unauthorized_sha(tmp_path: Path) -> None:
    workbook = tmp_path / "unauthorized.xlsx"
    workbook.write_bytes(b"not the canonical workbook")

    with pytest.raises(ValueError, match="Unauthorized workbook SHA-256"):
        workbook_returns.extract_workbook(
            workbook,
            expected_sha256=workbook_returns.AUTHORIZED_SWR_WORKBOOK_SHA256,
        )
