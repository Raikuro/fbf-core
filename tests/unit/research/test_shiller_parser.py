"""Tests for the Shiller CSV parser (C2 — deterministic normalization).

Validates that the frozen raw Shiller source is parsed correctly and
produces deterministic, reproducible CAPE and market data extractions.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import OrderedDict
from pathlib import Path

import pytest

_RAW_CSV = Path("data/ern/raw/ie_data.csv")
_EXISTING_CAPE_JSON = Path("data/ern/ern_cape_1871_2016.json")
_EXISTING_RETURNS_CSV = Path("data/ern/ern_real_returns_1871_2016.csv")


def _parse_shiller_raw(path: Path) -> OrderedDict:
    """Parse Shiller CSV. Skip non-padded YYYY,M rows (annual summaries).

    The Shiller CSV contains two row types per January:
    - YYYY,MM format (zero-padded): monthly data point
    - YYYY,M format (non-padded): annual summary/revision

    Both normalize to the same ISO date. The parser keeps only the
    zero-padded monthly rows to avoid annual summaries overwriting
    the monthly January data.
    """
    observations: OrderedDict[str, dict] = OrderedDict()
    with open(path, encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)

    for i, row in enumerate(rows):
        if i < 8:
            continue
        if len(row) < 13:
            continue

        date_str = row[0].strip().strip('"')
        if not date_str or "," not in date_str:
            continue

        parts = date_str.split(",")
        if len(parts) != 2:
            continue
        y_str, m_str = parts

        # Skip non-padded month rows (annual summaries)
        if len(m_str) == 1:
            continue

        try:
            year, month = int(y_str), int(m_str)
            iso_date = f"{year:04d}-{month:02d}-01"
        except ValueError:
            continue

        def parse_val(idx: int, _row: list[str] = row) -> float | None:
            if idx >= len(_row):
                return None
            v = _row[idx].strip().strip('"').replace("\xa0", "").replace(" ", "")
            if not v or v == "NA":
                return None
            v = v.replace(",", ".")
            if v.endswith("%"):
                v = v[:-1]
            try:
                return float(v)
            except ValueError:
                return None

        observations[iso_date] = {
            "date": iso_date,
            "year": year,
            "month": month,
            "nominal_price": parse_val(1),
            "cpi": parse_val(4),
            "rate_gs10": parse_val(6),
            "real_price": parse_val(7),
            "real_dividend": parse_val(8),
            "equity_real_total_return": parse_val(9),
            "cape": parse_val(12),
        }

    return observations


# --- Raw parsing tests ---


class TestRawParsing:
    """Validate raw CSV parsing correctness."""

    @pytest.fixture(scope="class")
    def raw_data(self) -> OrderedDict:
        return _parse_shiller_raw(_RAW_CSV)

    def test_row_count(self, raw_data: OrderedDict) -> None:
        """1681 monthly data rows (152 annual summary rows excluded)."""
        assert len(raw_data) == 1681

    def test_first_date(self, raw_data: OrderedDict) -> None:
        assert list(raw_data.keys())[0] == "1871-01-01"

    def test_last_date(self, raw_data: OrderedDict) -> None:
        assert list(raw_data.keys())[-1] == "2023-09-01"

    def test_no_october_observations(self, raw_data: OrderedDict) -> None:
        """Shiller source has zero October observations."""
        oct_dates = [d for d in raw_data if d.endswith("-10-01")]
        assert len(oct_dates) == 0

    def test_european_decimal_parsing(self, raw_data: OrderedDict) -> None:
        """First equity price (column 9) = 109.05 (parsed from ' 109,05 ')."""
        first = raw_data["1871-01-01"]
        assert first["equity_real_total_return"] == pytest.approx(109.05, abs=0.01)

    def test_cape_column_present(self, raw_data: OrderedDict) -> None:
        """Column 12 exists and is accessible for all rows."""
        for _d, v in raw_data.items():
            assert "cape" in v

    def test_known_cape_value(self, raw_data: OrderedDict) -> None:
        """1881-01 CAPE = 18.47 (first non-NA CAPE from padded monthly row)."""
        assert raw_data["1881-01-01"]["cape"] == pytest.approx(18.47, abs=0.01)

    def test_known_equity_price(self, raw_data: OrderedDict) -> None:
        """1871-02 equity total return price = 107.77."""
        assert raw_data["1871-02-01"]["equity_real_total_return"] == pytest.approx(
            107.77, abs=0.01
        )

    def test_known_gs10_rate(self, raw_data: OrderedDict) -> None:
        """1871-01 GS10 rate = 5.32%."""
        assert raw_data["1871-01-01"]["rate_gs10"] == pytest.approx(5.32, abs=0.01)

    def test_annual_summary_rows_excluded(self, raw_data: OrderedDict) -> None:
        """Non-padded YYYY,M rows are excluded (152 annual summaries)."""
        assert len(raw_data) == 1681


# --- CAPE extraction tests ---


class TestCapeExtraction:
    """Validate CAPE extraction from raw source."""

    @pytest.fixture(scope="class")
    def cape_data(self) -> OrderedDict:
        raw = _parse_shiller_raw(_RAW_CSV)
        return OrderedDict(
            (d, v["cape"]) for d, v in raw.items() if v["cape"] is not None
        )

    def test_cape_count(self, cape_data: OrderedDict) -> None:
        """1571 CAPE observations (1881-01 to 2023-09, excluding October)."""
        assert len(cape_data) == 1571

    def test_first_cape_date(self, cape_data: OrderedDict) -> None:
        assert list(cape_data.keys())[0] == "1881-01-01"

    def test_last_cape_date(self, cape_data: OrderedDict) -> None:
        assert list(cape_data.keys())[-1] == "2023-09-01"

    def test_no_october_cape(self, cape_data: OrderedDict) -> None:
        """No October CAPE observations in Shiller source."""
        oct_cape = [d for d in cape_data if d.endswith("-10-01")]
        assert len(oct_cape) == 0

    def test_negative_cape_not_present(self, cape_data: OrderedDict) -> None:
        """All CAPE values should be positive."""
        for d, c in cape_data.items():
            assert c >= 0, f"Negative CAPE at {d}: {c}"

    def test_cape_decimal_precision(self, cape_data: OrderedDict) -> None:
        """CAPE values are exact floats parsed from European decimal format."""
        assert cape_data["1881-01-01"] == 18.47

    def test_cape_range(self, cape_data: OrderedDict) -> None:
        """CAPE values should be in a reasonable range."""
        values = list(cape_data.values())
        assert min(values) > 4.0
        assert max(values) < 45.0


# --- Determinism tests ---


class TestDeterminism:
    """Verify byte-identical output across runs."""

    def test_raw_file_hash(self) -> None:
        """Raw file SHA-256 is stable (frozen artifact)."""
        h = hashlib.sha256(_RAW_CSV.read_bytes()).hexdigest()
        assert h == "ac5d25734dcd0cc68d05489a019abd5f834bdb4b04f61028a6adbbb6f0004be2"

    def test_parse_determinism(self) -> None:
        """Parsing the same file twice produces identical results."""
        data1 = _parse_shiller_raw(_RAW_CSV)
        data2 = _parse_shiller_raw(_RAW_CSV)
        assert list(data1.keys()) == list(data2.keys())
        for d in data1:
            for k in data1[d]:
                v1 = data1[d][k]
                v2 = data2[d][k]
                if v1 is None:
                    assert v2 is None
                else:
                    assert v1 == v2, f"Mismatch at {d}/{k}: {v1} vs {v2}"


# --- Reconciliation tests ---


class TestCapeReconciliation:
    """Compare extracted CAPE against existing ern_cape_1871_2016.json.

    The existing JSON matches the raw Shiller source exactly when
    annual summary rows (non-padded YYYY,M) are excluded. The previous
    142 January mismatches were caused by annual summary rows overwriting
    monthly January data — resolved in C2.
    """

    @pytest.fixture(scope="class")
    def extracted_cape(self) -> OrderedDict:
        raw = _parse_shiller_raw(_RAW_CSV)
        return OrderedDict(
            (d, v["cape"]) for d, v in raw.items() if v["cape"] is not None
        )

    @pytest.fixture(scope="class")
    def existing_cape(self) -> OrderedDict:
        with open(_EXISTING_CAPE_JSON) as f:
            data = json.load(f)
        return OrderedDict((s["date"], float(s["cape"])) for s in data["snapshots"])

    def test_same_observation_count(
        self, extracted_cape: OrderedDict, existing_cape: OrderedDict
    ) -> None:
        """Both sources have 1571 CAPE observations."""
        assert len(extracted_cape) == len(existing_cape)

    def test_all_months_exact_match(
        self, extracted_cape: OrderedDict, existing_cape: OrderedDict
    ) -> None:
        """All CAPE values match within 0.001 (annual mystery resolved)."""
        mismatches = 0
        for d in extracted_cape:
            if d in existing_cape and abs(extracted_cape[d] - existing_cape[d]) >= 0.001:
                mismatches += 1
        assert mismatches == 0


# --- Market returns lineage tests ---


class TestMarketReturnsLineage:
    """Verify the existing returns CSV is externally sourced (not from Shiller)."""

    def test_existing_csv_has_october_dates(self) -> None:
        """The existing CSV contains October dates not present in Shiller."""
        oct_dates = []
        with open(_EXISTING_RETURNS_CSV) as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            for row in reader:
                if len(row) >= 2 and int(row[1]) == 10:
                    oct_dates.append(f"{int(row[0]):04d}-10")
        assert len(oct_dates) == 145

    def test_existing_csv_row_count(self) -> None:
        """The existing CSV has 1749 rows (including October dates)."""
        with open(_EXISTING_RETURNS_CSV) as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            rows = list(reader)
        assert len(rows) == 1749
