"""Part 52 coverage layers and FFR provenance.

The workbook ``Distribution of Final Value`` sheet defines 1,739 retirement
labels (1871-02..2015-12), but it is stale relative to the underlying data:
the SWR Toolbox historical returns/CPI end at 2026-06, and the separate FFR
workbook ``Return Data!K`` ends at 2021-12.  These tests pin the distinct
coverage boundaries so they are not conflated with a "full workbook" claim.
They do not replace the research-validation execution suite or its
gross-survival assertions.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from fbf.core.datasets import load_canonical_dataset
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.money import Currency, Money
from fbf.core.study import (
    CohortSpecification,
    StudyConfiguration,
    build_study_plan,
)
from fbf.core.study.builder import build_interest_rate_schedule, load_ffr_rates
from fbf.core.study.internal.cohort.generator import CohortGenerator

DATA_DIR = Path("data/ern")
INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)
MARKET_HISTORY_END = date(2026, 6, 1)
FFR_WORKBOOK_END = date(2021, 12, 1)
FFR_RUNTIME_END = date(2026, 8, 1)
FFR_EXTENSION_START = date(2022, 1, 1)
FORWARD_FILL_START = date(2026, 9, 1)
N_END = date(1954, 6, 1)
M_START = date(1954, 7, 1)

HISTORICAL_MARKET_COVERAGE_COUNT = 1506
FFR_HISTORY_COVERAGE_COUNT = 1453
LEGACY_TERMINAL_2021_12_COUNT = 1452
LEGACY_TERMINAL_OUTSIDE_COUNT = 287
POST_2021_FFR_COUNT = 286
FORWARD_FILLED_COUNT = 230
NO_FORWARD_FILL_COUNT = 1509


def _add_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _month_index(value: date) -> int:
    return value.year * 12 + value.month - 1


def _latest_consumed_ffr_date(cohort: CohortSpecification) -> date:
    return _add_months(cohort.start_date, 359)


def _terminal_snapshot_date(cohort: CohortSpecification) -> date:
    return _add_months(cohort.start_date, 360)


def _is_legacy_terminal_2021_12(cohort: CohortSpecification) -> bool:
    return _terminal_snapshot_date(cohort) <= FFR_WORKBOOK_END


def _has_complete_market_history(cohort: CohortSpecification) -> bool:
    return _terminal_snapshot_date(cohort) <= MARKET_HISTORY_END


def _is_ffr_only_covered(cohort: CohortSpecification) -> bool:
    return _latest_consumed_ffr_date(cohort) <= FFR_WORKBOOK_END


def _last_csv_date(path: Path) -> date:
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return date.fromisoformat(rows[-1]["date"])


def _n_consumed_months(cohort: CohortSpecification) -> int:
    end = min(_latest_consumed_ffr_date(cohort), N_END)
    if cohort.start_date > end:
        return 0
    return _month_index(end) - _month_index(cohort.start_date) + 1


def _part52_config(*, ffr_spread: Decimal | None = None) -> StudyConfiguration:
    values: dict[str, object] = {
        "name": "ERN_Part52_legacy_2021_12_coverage",
        "description": "Legacy Part 52 cohorts with terminal snapshots on or before 2021-12",
        "version": "1.0",
        "allocation_policy_type": "ConstantAllocationPolicy",
        "allocation_policy_values": (Decimal("0.75"),),
        "withdrawal_policy_type": "Part52WithdrawalPolicy",
        "withdrawal_policy_values": (Decimal("0.0358"),),
        "horizon_years": (30,),
        "cohort_horizon_years": 60,
        "debt_ltv_limit": Decimal("0.50"),
        "debt_ltv_enforcement": False,
        "debt_borrow_pct": Decimal("0"),
        "debt_drawdown_threshold": None,
        "ffr_spread": ffr_spread,
    }
    if ffr_spread is None:
        values["debt_interest_rate"] = Decimal("0.015")
    return StudyConfiguration(**values)  # type: ignore[arg-type]


def _load_raw_fedfunds() -> dict[date, Decimal]:
    rates: dict[date, Decimal] = {}
    with (DATA_DIR / "raw" / "FEDFUNDS.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            raw_date = row["observation_date"]
            raw_value = row["FEDFUNDS"]
            assert raw_date is not None
            assert raw_value is not None
            rates[date.fromisoformat(raw_date)] = Decimal(raw_value)
    return rates


@pytest.fixture(scope="module")
def canonical_dataset() -> Dataset:
    return load_canonical_dataset(DATA_DIR)


@pytest.fixture(scope="module")
def full_cohorts(canonical_dataset: Dataset) -> tuple[CohortSpecification, ...]:
    return CohortGenerator.generate_rolling_monthly(canonical_dataset, 721)


@pytest.fixture(scope="module")
def legacy_terminal_cohorts(
    full_cohorts: tuple[CohortSpecification, ...],
) -> tuple[CohortSpecification, ...]:
    return tuple(cohort for cohort in full_cohorts if _is_legacy_terminal_2021_12(cohort))


@pytest.mark.parametrize(
    "ffr_spread",
    [pytest.param(None, id="non_ffr"), pytest.param(Decimal("0.005"), id="ffr")],
)
def test_legacy_2021_12_filter_applies_at_caller(
    canonical_dataset: Dataset,
    ffr_spread: Decimal | None,
) -> None:
    built = build_study_plan(
        _part52_config(ffr_spread=ffr_spread),
        str(DATA_DIR),
        INITIAL_WEALTH,
        dataset=canonical_dataset,
        cohort_filter=_is_legacy_terminal_2021_12,
    )

    assert len(built.cohorts) == LEGACY_TERMINAL_2021_12_COUNT
    assert len(built.plan.units) == LEGACY_TERMINAL_2021_12_COUNT
    assert built.cohorts[0].start_date == date(1871, 1, 31)
    assert built.cohorts[-1].start_date == date(1991, 12, 1)


def test_legacy_2021_12_and_outside_cohort_counts(
    full_cohorts: tuple[CohortSpecification, ...],
    legacy_terminal_cohorts: tuple[CohortSpecification, ...],
) -> None:
    """The full 60-year set maps to the workbook's 1,739 retirement labels.

    Workbook retirement labels 1871-02..2015-12 map to runtime cohort starts
    1871-01..2015-11 because the runtime start is the pre-retirement snapshot.
    """
    assert len(full_cohorts) == 1739
    assert full_cohorts[0].start_date == date(1871, 1, 31)
    assert full_cohorts[-1].start_date == date(2015, 11, 1)
    assert len(legacy_terminal_cohorts) == LEGACY_TERMINAL_2021_12_COUNT
    assert len(full_cohorts) - len(legacy_terminal_cohorts) == LEGACY_TERMINAL_OUTSIDE_COUNT

    post_2021 = tuple(
        cohort
        for cohort in full_cohorts
        if _latest_consumed_ffr_date(cohort) >= FFR_EXTENSION_START
    )
    forward_filled = tuple(
        cohort for cohort in full_cohorts if _latest_consumed_ffr_date(cohort) >= FORWARD_FILL_START
    )

    assert len(post_2021) == POST_2021_FFR_COUNT
    assert len(forward_filled) == FORWARD_FILLED_COUNT
    assert len(full_cohorts) - len(forward_filled) == NO_FORWARD_FILL_COUNT


def test_ffr_only_boundary_excludes_1992_01_terminal_snapshot(
    full_cohorts: tuple[CohortSpecification, ...],
    legacy_terminal_cohorts: tuple[CohortSpecification, ...],
) -> None:
    ffr_only = tuple(cohort for cohort in full_cohorts if _is_ffr_only_covered(cohort))
    boundary = CohortSpecification(date(1992, 1, 1))

    assert len(ffr_only) == FFR_HISTORY_COVERAGE_COUNT
    assert boundary in ffr_only
    assert boundary not in legacy_terminal_cohorts
    assert _latest_consumed_ffr_date(boundary) == date(2021, 12, 1)
    assert _terminal_snapshot_date(boundary) == date(2022, 1, 1)


def test_historical_market_coverage_layers(
    full_cohorts: tuple[CohortSpecification, ...],
    legacy_terminal_cohorts: tuple[CohortSpecification, ...],
) -> None:
    """Historical market/CPI coverage is 1,506 cohorts, not the legacy 1,452.

    The SWR Toolbox historical series end at 2026-06.  The 1,452 subset is a
    one-month-stricter legacy filter tied to the separate FFR workbook end.
    """
    market_covered = tuple(
        cohort for cohort in full_cohorts if _has_complete_market_history(cohort)
    )
    ffr_covered = tuple(cohort for cohort in full_cohorts if _is_ffr_only_covered(cohort))

    assert len(market_covered) == HISTORICAL_MARKET_COVERAGE_COUNT
    assert market_covered[-1].start_date == date(1996, 6, 1)
    assert _terminal_snapshot_date(market_covered[-1]) == MARKET_HISTORY_END
    assert _latest_consumed_ffr_date(market_covered[-1]) < FFR_RUNTIME_END

    assert len(ffr_covered) == FFR_HISTORY_COVERAGE_COUNT
    assert ffr_covered[-1].start_date == date(1992, 1, 1)
    assert _latest_consumed_ffr_date(ffr_covered[-1]) == FFR_WORKBOOK_END

    assert len(legacy_terminal_cohorts) == LEGACY_TERMINAL_2021_12_COUNT
    assert legacy_terminal_cohorts[-1].start_date == date(1991, 12, 1)
    assert _terminal_snapshot_date(legacy_terminal_cohorts[-1]) == FFR_WORKBOOK_END

    assert len(market_covered) - len(legacy_terminal_cohorts) == 54
    assert len(market_covered) - len(ffr_covered) == 53


def test_historical_market_source_end_is_2026_06() -> None:
    assert _last_csv_date(DATA_DIR / "workbook_returns.csv") == MARKET_HISTORY_END
    assert _last_csv_date(DATA_DIR / "cpi.csv") == MARKET_HISTORY_END


def test_legacy_2021_12_n_exposure(
    legacy_terminal_cohorts: tuple[CohortSpecification, ...],
) -> None:
    any_n = tuple(cohort for cohort in legacy_terminal_cohorts if cohort.start_date < M_START)
    only_n = tuple(
        cohort for cohort in legacy_terminal_cohorts if _latest_consumed_ffr_date(cohort) < M_START
    )
    mixed = tuple(cohort for cohort in any_n if cohort not in only_n)

    assert (len(any_n), len(only_n), len(mixed)) == (1002, 643, 359)
    assert sum(_n_consumed_months(cohort) for cohort in legacy_terminal_cohorts) == 296100


def test_a10_a11_loan_rate_schedule_uses_n_for_299_months() -> None:
    start = date(1929, 8, 1)
    source_dates = tuple(_add_months(start, period - 1) for period in range(1, 361))
    assert sum(1 for source in source_dates if source < M_START) == 299

    ffr_rates = load_ffr_rates(str(DATA_DIR))
    schedule = build_interest_rate_schedule(
        ffr_rates,
        Decimal("0.005"),
        start,
        361,
        lag_months=1,
    )
    rate_by_date = dict(ffr_rates)

    assert len(schedule) == 361
    assert schedule[299] == rate_by_date[N_END] + Decimal("0.005")
    assert schedule[300] == rate_by_date[M_START] + Decimal("0.005")


def test_workbook_m_segment_matches_raw_fedfunds_within_tolerance() -> None:
    ffr = dict(load_ffr_rates(str(DATA_DIR)))
    raw = _load_raw_fedfunds()
    segment = tuple(rate_date for rate_date in ffr if M_START <= rate_date <= FFR_WORKBOOK_END)

    assert len(segment) == 810
    differences = [abs(ffr[rate_date] - raw[rate_date] / Decimal("100")) for rate_date in segment]
    assert max(differences) < Decimal("1e-15")


def test_ffr_artifact_is_frozen_and_hash_pinned() -> None:
    artifact = DATA_DIR / "ffr.csv"
    artifact_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert artifact_sha == ("98591457d5d03867bd81992d43b57a6cabc4ce967f3ec9324676216abbf2f5f1")

    provenance = json.loads((DATA_DIR / "ffr.provenance.json").read_text(encoding="utf-8"))
    raw_sha = hashlib.sha256((DATA_DIR / "raw" / "FEDFUNDS.csv").read_bytes()).hexdigest()

    assert provenance["artifact_sha256"] == artifact_sha
    assert provenance["historical"]["source_sha256"] == (
        "e0a0dbea11543809b2f2e8544cc84e21a19e0ca864d8ef3664135b945bbcda38"
    )
    assert provenance["extension"]["source_sha256"] == raw_sha

    rates = load_ffr_rates(str(DATA_DIR))
    assert provenance["observation_count"] == len(rates) == 1868
    assert provenance["historical"]["observation_count"] == 1812
    assert provenance["extension"]["observation_count"] == 56
    assert rates[0][0] == date(1871, 1, 1)
    assert rates[-1][0] == date(2026, 8, 1)
