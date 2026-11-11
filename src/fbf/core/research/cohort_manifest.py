"""Runtime construction of the effective Part 3 cohort manifest.

The manifest is derived from historical CAPE observations and a prepared
market dataset.  It is never persisted with projection-dependent horizons.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from itertools import pairwise
from typing import Any

from fbf.core.datasets.ern import PreparedDatasetMetadata
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.policies.cape_regime import (
    classify_cape_binary,
    classify_cape_regime,
)
from fbf.core.research.part3_planner import CohortManifest, CohortManifestEntry

_HORIZON_MONTHS = (12, 60, 120, 240, 360, 480, 600, 720)
_CAPE_QUANTUM = Decimal("0.00000001")


def _next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def _previous_month(value: date) -> date:
    if value.month == 1:
        return date(value.year - 1, 12, 1)
    return date(value.year, value.month - 1, 1)


def _month_count(start: date, end: date) -> int:
    if end < start:
        raise ValueError(f"End month {end} precedes start month {start}")
    return (end.year - start.year) * 12 + (end.month - start.month) + 1


def _add_months(value: date, months: int) -> date:
    total = value.year * 12 + (value.month - 1) + months
    year, month_index = divmod(total, 12)
    return date(year, month_index + 1, 1)


def _month_range(start: date, end: date) -> tuple[date, ...]:
    return tuple(_add_months(start, index) for index in range(_month_count(start, end)))


def _validate_contiguous(dates: Sequence[date], *, label: str) -> None:
    if not dates:
        raise ValueError(f"{label} is empty")
    for previous, current in pairwise(dates):
        if current != _next_month(previous):
            raise ValueError(
                f"{label} dates must be contiguous monthly dates: "
                f"{previous.isoformat()} -> {current.isoformat()}"
            )


def build_effective_manifest(
    *,
    dataset: Dataset,
    metadata: PreparedDatasetMetadata,
    cape_rows: Sequence[tuple[str, Decimal]],
    cohort_start: date,
    cohort_end: date,
    fee: Decimal = Decimal("0.0005"),
    require_cape: bool = False,
) -> CohortManifest:
    """Build the effective runtime manifest for a prepared dataset.

    CAPE is historical-only.  Cohorts after the historical cutoff may be
    present only when ``require_cape`` is false; callers that condition on
    CAPE must pass ``require_cape=True`` and fail if any cohort lacks CAPE.
    """
    cutoff = metadata.historical_data_cutoff
    historical_dates = tuple(
        snapshot.date for snapshot in dataset if snapshot.date <= cutoff
    )
    _validate_contiguous(historical_dates, label="Historical index")

    cape_map: dict[date, Decimal] = {
        date.fromisoformat(raw_date): value
        for raw_date, value in cape_rows
        if date.fromisoformat(raw_date) <= cutoff
    }
    _validate_contiguous(sorted(cape_map), label="CAPE")

    if cohort_end < cohort_start:
        raise ValueError("cohort_end must not precede cohort_start")
    cohort_dates = _month_range(cohort_start, cohort_end)
    snapshot_position = {
        snapshot.date: index for index, snapshot in enumerate(dataset)
    }
    snapshot_count = len(dataset)

    cape_regime_counts = {
        "HIGH": 0,
        "MODERATE": 0,
        "LOW": 0,
        "BELOW_15": 0,
        "EXTREME": 0,
    }
    binary_counts = {"HIGH": 0, "LOW": 0}
    entries: list[CohortManifestEntry] = []
    missing_cape: list[date] = []

    for cohort_date in cohort_dates:
        if cohort_date not in snapshot_position:
            if cohort_date <= cutoff:
                raise ValueError(
                    f"Cohort date {cohort_date.isoformat()} is not a historical "
                    f"observation at or before cutoff {cutoff.isoformat()}"
                )
            raise ValueError(
                f"Cohort date {cohort_date.isoformat()} is not a prepared "
                "dataset observation"
            )
        cape_value = cape_map.get(cohort_date)
        if cape_value is None:
            missing_cape.append(cohort_date)
        cape_available = cape_value is not None
        regime_name: str | None = None
        if cape_value is not None:
            regime = classify_cape_regime(cape_value)
            regime_name = regime.name
            cape_regime_counts[regime_name] += 1

        prior_cape = cape_map.get(_previous_month(cohort_date))
        if prior_cape is None and cohort_date == cohort_dates[0]:
            prior_cape = cape_value
        if prior_cape is not None:
            binary_counts[classify_cape_binary(prior_cape).value] += 1

        position = snapshot_position[cohort_date]
        if position == 0:
            raise ValueError(
                f"Cohort date {cohort_date.isoformat()} would start before the "
                "first return"
            )
        start_month_index = position - 1
        max_horizon_months = snapshot_count - (start_month_index + 1)
        if max_horizon_months < 0:
            raise ValueError(f"Negative horizon for cohort {cohort_date.isoformat()}")

        entries.append(
            CohortManifestEntry(
                cohort_date=cohort_date.isoformat(),
                market_available=True,
                cape_available=cape_available,
                cape_value=(
                    cape_value.quantize(_CAPE_QUANTUM)
                    if cape_value is not None
                    else None
                ),
                cape_regime=regime_name,
                start_month_index=start_month_index,
                max_horizon_months=max_horizon_months,
            )
        )

    if require_cape and missing_cape:
        first_missing = missing_cape[0]
        raise ValueError(
            "CAPE conditioning requires a historical CAPE observation for every "
            f"included cohort; first missing cohort={first_missing.isoformat()}"
        )

    horizon_eligibility = {
        f"h{months}": sum(
            1 for entry in entries if entry.max_horizon_months >= months
        )
        for months in _HORIZON_MONTHS
    }
    cape_available_count = sum(1 for entry in entries if entry.cape_available)
    source_metadata = metadata.as_dict()
    return CohortManifest(
        version="2.0",
        description=(
            "Runtime effective Part 3 cohort manifest - historical-only CAPE "
            "and runtime projection metadata"
        ),
        market_source=(
            "SWR_Toolbox_v2.0.xlsx Asset Returns!Q (spx_tr_real.csv)"
        ),
        cape_source="cape_shiller.csv",
        fee=float(fee),
        statistics={
            "total_cohorts": len(entries),
            "market_available": len(entries),
            "cape_available": cape_available_count,
            "cape_regimes": cape_regime_counts,
            "horizon_eligibility": horizon_eligibility,
            "binary_cape_regimes": binary_counts,
            "binary_cape_semantics": (
                "CAPE at t-1 > 20; first cohort falls back to its own CAPE"
            ),
            "historical_data_cutoff": cutoff.isoformat(),
            "projection_start": metadata.projection_start.isoformat(),
            "projection_end": metadata.projection_end.isoformat(),
            "snapshot_count": snapshot_count,
            "source_metadata": source_metadata,
        },
        cohorts=tuple(entries),
    )



def manifest_to_dict(manifest: CohortManifest) -> dict[str, Any]:
    """Serialize an effective manifest to the public JSON-compatible shape."""
    return {
        "version": manifest.version,
        "description": manifest.description,
        "market_source": manifest.market_source,
        "cape_source": manifest.cape_source,
        "fee": manifest.fee,
        "statistics": manifest.statistics,
        "cohorts": [
            {
                "cohort_date": entry.cohort_date,
                "market_available": entry.market_available,
                "cape_available": entry.cape_available,
                "cape_value": (
                    float(entry.cape_value)
                    if entry.cape_value is not None
                    else None
                ),
                "cape_regime": entry.cape_regime,
                "start_month_index": entry.start_month_index,
                "max_horizon_months": entry.max_horizon_months,
            }
            for entry in manifest.cohorts
        ],
    }
