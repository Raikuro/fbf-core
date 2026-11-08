"""Canonical OMY timeline semantics."""

from __future__ import annotations

import pytest

from fbf.core.study.internal.omy_timeline import resolve_omy_timeline


@pytest.mark.parametrize(
    ("horizon_years", "omy_months", "total", "accumulation", "retirement", "transitions"),
    [
        (30, 12, 361, 13, 349, 348),
        (50, 12, 601, 13, 589, 588),
        (50, 24, 601, 25, 577, 576),
    ],
)
def test_canonical_timeline_counts(
    horizon_years: int,
    omy_months: int,
    total: int,
    accumulation: int,
    retirement: int,
    transitions: int,
) -> None:
    timeline = resolve_omy_timeline(
        horizon_years=horizon_years,
        omy_months=omy_months,
    )
    assert timeline.total_snapshots == total
    assert timeline.accumulation_snapshots == accumulation
    assert timeline.retirement_snapshots == retirement
    assert timeline.retirement_transitions == transitions


def test_timeline_rejects_omy_consuming_entire_horizon() -> None:
    with pytest.raises(ValueError, match="at least one retirement transition"):
        resolve_omy_timeline(horizon_years=1, omy_months=12)
