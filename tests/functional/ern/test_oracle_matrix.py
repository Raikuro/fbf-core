"""Fast tests for the historical published-ERN oracle matrix.

These verify the pinned published-ERN table at ``data/ern/p49_oracle_table.csv``
and that the published paper anchors hold.  They do not run any simulation.

This is the historical replication target (T+1 terms, multiplicative fee), not
production conformance.  Production uses the workbook-derived oracle at
``data/ern/workbook_oracle_table.csv`` (T terms, additive fee).
"""

from __future__ import annotations

import csv

from tests.support.ern.constants import ANCHOR_CELLS, ORACLE_CSV, load_oracle_table


def test_published_anchors_hold() -> None:
    """The three hard-fail acceptance anchors must match the pinned table."""
    table = load_oracle_table()
    for weight, horizon, rate, expected in ANCHOR_CELLS:
        assert table[(weight, horizon)][rate] == expected, (
            f"anchor {weight}/{horizon}/{rate} should be {expected} but oracle says "
            f"{table[(weight, horizon)][rate]}"
        )


def test_oracle_table_has_expected_shape() -> None:
    """The pinned matrix covers the full 5x4x9 grid."""
    with open(ORACLE_CSV, newline="") as f:
        rows = list(csv.reader(f))
    assert len(rows) == 1 + 20
    assert rows[0][1] == "horizon_years"
    assert len(rows[1]) == 2 + 9
