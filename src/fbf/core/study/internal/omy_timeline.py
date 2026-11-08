"""Pure OMY timeline arithmetic.

The OMY study keeps the total investment horizon fixed and consumes the first
``omy_months`` periods for accumulation.  This module is the single source of
truth for snapshot and transition counts; date resolution remains in the
planner because it depends on the cohort and dataset.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OmyTimeline:
    """Snapshot and transition counts for a fixed-horizon OMY study."""

    total_snapshots: int
    accumulation_snapshots: int
    accumulation_transitions: int
    retirement_snapshots: int
    retirement_transitions: int


def resolve_omy_timeline(
    *,
    horizon_years: int,
    omy_months: int,
) -> OmyTimeline:
    """Return canonical OMY counts for a fixed total horizon.

    The total horizon is ``horizon_years * 12`` months.  The accumulation phase
    consumes the first ``omy_months`` months, and retirement contains the
    remaining months.  At least one retirement transition must remain.
    """
    if horizon_years < 1:
        raise ValueError("horizon_years must be at least 1")
    if omy_months < 0:
        raise ValueError("omy_months must be non-negative")

    total_months = horizon_years * 12
    if omy_months >= total_months:
        raise ValueError(
            "OMY accumulation must leave at least one retirement transition: "
            f"omy_months={omy_months}, total_months={total_months}"
        )

    total_snapshots = total_months + 1
    accumulation_snapshots = omy_months + 1
    retirement_snapshots = total_months - omy_months + 1
    retirement_transitions = retirement_snapshots - 1

    if retirement_transitions < 1:
        raise ValueError("retirement must contain at least one transition")

    return OmyTimeline(
        total_snapshots=total_snapshots,
        accumulation_snapshots=accumulation_snapshots,
        accumulation_transitions=omy_months,
        retirement_snapshots=retirement_snapshots,
        retirement_transitions=retirement_transitions,
    )
