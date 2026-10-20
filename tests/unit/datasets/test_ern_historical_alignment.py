"""ERN historical interval alignment against the SWR Toolbox v2.0 workbook.

These tests pin the loader's monthly indexing:

* the synthetic base snapshot is the raw fee-free ``d_{-1}`` level implied by
  the February 1871 gross return;
* each historical snapshot interval uses the return dated the same month as
  the workbook row;
* June 2026 is the last historical return and July 2026 is the first
  projection month;
* the first workbook cohort's SCR agrees with ``tools/ern/workbook_oracle.py``.
"""

from __future__ import annotations

from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from fbf.core.datasets.ern import load_ern_dataset
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from tools.ern import workbook_oracle as wo

_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "ern"
_DEFAULT_TOLERANCE = Decimal("1e-24")
_FEE_ANNUAL = Decimal("0.0005")
_HORIZON_MONTHS = 360
_FEBRUARY_EQUITY_RETURN = Decimal("-0.0115146124")
_FEBRUARY_BOND_RETURN = Decimal("-0.007375011804")


def _monthly_return(annual_return: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 50
        return (Decimal("1") + annual_return) ** (
            Decimal("1") / Decimal("12")
        ) - Decimal("1")


def _asset_level(snapshot: MarketSnapshot, asset_id: str) -> Decimal:
    for asset_class, level in snapshot.index_levels.items():
        if asset_class.id == asset_id:
            return level
    raise AssertionError(f"No {asset_id!r} level in snapshot {snapshot.date}")


def _snapshot(dataset: Dataset, iso_date: str) -> MarketSnapshot:
    for snapshot in dataset.snapshots:
        if snapshot.date.isoformat() == iso_date:
            return snapshot
    raise AssertionError(f"No snapshot for {iso_date}")


def _interval_return(
    dataset: Dataset, start_date: str, end_date: str, asset_id: str
) -> Decimal:
    start = _asset_level(_snapshot(dataset, start_date), asset_id)
    end = _asset_level(_snapshot(dataset, end_date), asset_id)
    return end / start - Decimal("1")


def _assert_close(
    actual: Decimal, expected: Decimal, tolerance: Decimal = _DEFAULT_TOLERANCE
) -> None:
    assert abs(actual - expected) <= tolerance, f"{actual} != {expected}"


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return load_ern_dataset(_DATA_DIR)


def test_base_snapshot_is_raw_february_implied_level(dataset: Dataset) -> None:
    """d_{-1} is implied from February gross returns with no fee embedded."""
    base = dataset.snapshots[0]
    _assert_close(
        _asset_level(base, "equity"),
        Decimal("100") / (Decimal("1") + _FEBRUARY_EQUITY_RETURN),
    )
    _assert_close(
        _asset_level(base, "bond"),
        Decimal("100") / (Decimal("1") + _FEBRUARY_BOND_RETURN),
    )

    _assert_close(
        _interval_return(dataset, "1871-01-31", "1871-02-01", "equity"),
        _FEBRUARY_EQUITY_RETURN,
    )
    _assert_close(
        _interval_return(dataset, "1871-01-31", "1871-02-01", "bond"),
        _FEBRUARY_BOND_RETURN,
    )


def test_first_historical_intervals_use_same_month_returns(dataset: Dataset) -> None:
    """The February return is not duplicated into the March interval."""
    _assert_close(
        _interval_return(dataset, "1871-02-01", "1871-03-01", "equity"),
        Decimal("0.0144157692"),
    )
    _assert_close(
        _interval_return(dataset, "1871-02-01", "1871-03-01", "bond"),
        Decimal("-0.003552413693"),
    )
    _assert_close(
        _interval_return(dataset, "1871-03-01", "1871-04-01", "equity"),
        Decimal("0.07330801661"),
    )
    _assert_close(
        _interval_return(dataset, "1871-03-01", "1871-04-01", "bond"),
        Decimal("0.05404830716"),
    )

    assert _asset_level(dataset.snapshots[2], "equity") == Decimal("101.44157692")
    assert _asset_level(dataset.snapshots[3], "equity") == Decimal("108.878057725795952641200")
    assert _asset_level(dataset.snapshots[2], "bond") == Decimal("99.644758630700")
    assert _asset_level(dataset.snapshots[3], "bond") == Decimal("105.03038915205613460581200")


def test_may_june_july_2026_transition(dataset: Dataset) -> None:
    """June 2026 is the last historical return; July 2026 starts projection."""
    _assert_close(
        _interval_return(dataset, "2026-04-01", "2026-05-01", "equity"),
        Decimal("0.04767843451"),
    )
    _assert_close(
        _interval_return(dataset, "2026-05-01", "2026-06-01", "equity"),
        Decimal("-0.005320897265"),
    )
    _assert_close(
        _interval_return(dataset, "2026-05-01", "2026-06-01", "bond"),
        Decimal("0.007513216583"),
    )
    _assert_close(
        _interval_return(dataset, "2026-06-01", "2026-07-01", "equity"),
        _monthly_return(Decimal("0.04")),
    )
    _assert_close(
        _interval_return(dataset, "2026-06-01", "2026-07-01", "bond"),
        _monthly_return(Decimal("0.025")),
    )


@pytest.mark.parametrize("weight", [Decimal("0"), Decimal("0.5"), Decimal("1")])
def test_first_cohort_scr_matches_workbook_oracle(
    dataset: Dataset, weight: Decimal
) -> None:
    """First-cohort 30y SCR agrees with the standalone workbook oracle."""
    loader_eq = [
        _asset_level(dataset.snapshots[m + 1], "equity")
        / _asset_level(dataset.snapshots[m], "equity")
        - Decimal("1")
        for m in range(_HORIZON_MONTHS)
    ]
    loader_bd = [
        _asset_level(dataset.snapshots[m + 1], "bond")
        / _asset_level(dataset.snapshots[m], "bond")
        - Decimal("1")
        for m in range(_HORIZON_MONTHS)
    ]

    r_eq, r_bd = wo.load_real_returns(_DATA_DIR)
    workbook_eq, workbook_bd = wo.build_extended(r_eq, r_bd)

    actual = wo.compute_workbook_scr(
        loader_eq, loader_bd, weight, 0, _HORIZON_MONTHS, _FEE_ANNUAL
    )
    expected = wo.compute_workbook_scr(
        workbook_eq, workbook_bd, weight, 0, _HORIZON_MONTHS, _FEE_ANNUAL
    )
    _assert_close(actual, expected)
