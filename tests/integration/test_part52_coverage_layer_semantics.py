"""Part 52 coverage-layer semantics.

The 1,739-row distribution sheet, the 1,506 historical-market layer, the 1,453
workbook-FFR layer, and the 1,452 legacy-terminal subset describe different
data-availability boundaries. They are not interchangeable, and they do not by
themselves establish historical validation or select an eligibility universe.

These tests pin the layer membership, boundaries, and data dependencies so the
1,506/1,453/1,452 decision remains a separate, open methodological choice.
They do not run simulations and do not assert feasibility or acceptance.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest

from fbf.core.datasets import load_canonical_dataset
from fbf.core.study import CohortSpecification
from fbf.core.study.internal.cohort.generator import CohortGenerator

DATA_DIR = Path("data/ern")
COHORT_HORIZON_MONTHS = 60 * 12 + 1
SIMULATION_HORIZON_MONTHS = 30 * 12
MARKET_HISTORY_END = date(2026, 6, 1)
FFR_WORKBOOK_END = date(2021, 12, 1)
FFR_RUNTIME_END = date(2026, 8, 1)

WORKBOOK_NATIVE = "workbook_native"
FRED_EXTENSION = "fred_extension"
FORWARD_FILLED = "forward_filled"
HISTORICAL = "historical"
PROJECTED = "projected"


def _add_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _start_month(cohort: CohortSpecification) -> date:
    return date(cohort.start_date.year, cohort.start_date.month, 1)


def _terminal_snapshot_date(start_date: date) -> date:
    return _add_months(start_date, SIMULATION_HORIZON_MONTHS)


def _latest_consumed_ffr_date(start_date: date) -> date:
    return _add_months(start_date, SIMULATION_HORIZON_MONTHS - 1)


def _classify_market_data(start_date: date) -> str:
    if _terminal_snapshot_date(start_date) <= MARKET_HISTORY_END:
        return HISTORICAL
    return PROJECTED


def _classify_ffr_data(start_date: date) -> str:
    latest = _latest_consumed_ffr_date(start_date)
    if latest <= FFR_WORKBOOK_END:
        return WORKBOOK_NATIVE
    if latest <= FFR_RUNTIME_END:
        return FRED_EXTENSION
    return FORWARD_FILLED


def _counts(
    values: frozenset[date],
    classifier: Callable[[date], str],
) -> dict[str, int]:
    return dict(Counter(classifier(value) for value in values))


@pytest.fixture(scope="module")
def coverage_layers() -> dict[str, frozenset[date]]:
    dataset = load_canonical_dataset(DATA_DIR)
    cohorts = CohortGenerator.generate_rolling_monthly(dataset, COHORT_HORIZON_MONTHS)
    starts = frozenset(_start_month(cohort) for cohort in cohorts)
    return {
        "distribution": starts,
        "historical_market": frozenset(
            start for start in starts if _classify_market_data(start) == HISTORICAL
        ),
        "workbook_ffr": frozenset(
            start for start in starts if _classify_ffr_data(start) == WORKBOOK_NATIVE
        ),
        "legacy_terminal_2021_12": frozenset(
            start
            for start in starts
            if _terminal_snapshot_date(start) <= FFR_WORKBOOK_END
        ),
    }


def test_coverage_layers_are_nested_with_known_sizes(
    coverage_layers: dict[str, frozenset[date]],
) -> None:
    distribution = coverage_layers["distribution"]
    historical_market = coverage_layers["historical_market"]
    workbook_ffr = coverage_layers["workbook_ffr"]
    legacy_terminal = coverage_layers["legacy_terminal_2021_12"]

    assert len(distribution) == 1739
    assert len(historical_market) == 1506
    assert len(workbook_ffr) == 1453
    assert len(legacy_terminal) == 1452

    assert legacy_terminal < workbook_ffr < historical_market < distribution

    assert min(distribution) == date(1871, 1, 1)
    assert max(distribution) == date(2015, 11, 1)
    assert max(historical_market) == date(1996, 6, 1)
    assert max(workbook_ffr) == date(1992, 1, 1)
    assert max(legacy_terminal) == date(1991, 12, 1)


def test_layer_differences_have_precise_date_boundaries(
    coverage_layers: dict[str, frozenset[date]],
) -> None:
    distribution = coverage_layers["distribution"]
    historical_market = coverage_layers["historical_market"]
    workbook_ffr = coverage_layers["workbook_ffr"]
    legacy_terminal = coverage_layers["legacy_terminal_2021_12"]

    assert workbook_ffr - legacy_terminal == {date(1992, 1, 1)}

    market_without_workbook_ffr = historical_market - workbook_ffr
    assert len(market_without_workbook_ffr) == 53
    assert min(market_without_workbook_ffr) == date(1992, 2, 1)
    assert max(market_without_workbook_ffr) == date(1996, 6, 1)

    market_without_legacy = historical_market - legacy_terminal
    assert len(market_without_legacy) == 54
    assert min(market_without_legacy) == date(1992, 1, 1)
    assert max(market_without_legacy) == date(1996, 6, 1)

    projected_asset_cpi = distribution - historical_market
    assert len(projected_asset_cpi) == 233
    assert min(projected_asset_cpi) == date(1996, 7, 1)
    assert max(projected_asset_cpi) == date(2015, 11, 1)


def test_legacy_and_workbook_ffr_layers_are_fully_historical(
    coverage_layers: dict[str, frozenset[date]],
) -> None:
    """Both full-history layers differ only by the legacy terminal boundary.

    The 1,452-cohort layer is one cohort stricter than the 1,453-cohort layer.
    That cohort (1992-01) consumes workbook-native FFR through 2021-12 but has a
    2022-01 terminal snapshot, which is still historical market/CPI data.
    """
    legacy_terminal = coverage_layers["legacy_terminal_2021_12"]
    workbook_ffr = coverage_layers["workbook_ffr"]

    assert _counts(legacy_terminal, _classify_market_data) == {HISTORICAL: 1452}
    assert _counts(legacy_terminal, _classify_ffr_data) == {WORKBOOK_NATIVE: 1452}
    assert _counts(workbook_ffr, _classify_market_data) == {HISTORICAL: 1453}
    assert _counts(workbook_ffr, _classify_ffr_data) == {WORKBOOK_NATIVE: 1453}


def test_historical_market_layer_uses_fred_extension_not_forward_fill(
    coverage_layers: dict[str, frozenset[date]],
) -> None:
    """The 1,506 layer is historical market/CPI but not fully workbook-native FFR.

    Its extra 53 cohorts consume actual FRED FFR through 2026-08, not the
    workbook series through 2021-12. No cohort in this layer requires
    forward-filled FFR after 2026-08.
    """
    historical_market = coverage_layers["historical_market"]

    assert _counts(historical_market, _classify_market_data) == {HISTORICAL: 1506}
    assert _counts(historical_market, _classify_ffr_data) == {
        WORKBOOK_NATIVE: 1453,
        FRED_EXTENSION: 53,
    }


def test_distribution_layer_includes_projection_only_cohorts(
    coverage_layers: dict[str, frozenset[date]],
) -> None:
    """The 1,739 layer is a projection diagnostic, not a historical universe.

    The 233 cohorts outside historical market/CPI coverage require projected
    asset/CPI after 2026-06. Three of them still use actual FFR through 2026-08;
    the other 230 also require forward-filled FFR after 2026-08.
    """
    distribution = coverage_layers["distribution"]
    projected = distribution - coverage_layers["historical_market"]

    assert _counts(distribution, _classify_market_data) == {
        HISTORICAL: 1506,
        PROJECTED: 233,
    }
    assert _counts(distribution, _classify_ffr_data) == {
        WORKBOOK_NATIVE: 1453,
        FRED_EXTENSION: 56,
        FORWARD_FILLED: 230,
    }
    assert _counts(projected, _classify_market_data) == {PROJECTED: 233}
    assert _counts(projected, _classify_ffr_data) == {
        FRED_EXTENSION: 3,
        FORWARD_FILLED: 230,
    }
