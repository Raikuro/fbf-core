"""Lazy, cohort-aligned slicing of research plans.

The slice limit is a memory-control target, not an absolute bound: a cohort is
never split, so a slice whose first cohort alone exceeds the limit is still
emitted intact.  Consumers that need a hard bound must account for the largest
cohort size and for retained executor/aggregation state.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan


def iter_cohort_slices(
    plan: ResearchPlan,
    *,
    max_units_per_slice: int,
) -> Iterator[tuple[PlannedSimulationUnit, ...]]:
    """Yield contiguous, cohort-aligned slices of ``plan.units``.

    Units retain their original order.  Consecutive units sharing a cohort
    ``start_date`` form a group that is never split, even when the group exceeds
    ``max_units_per_slice``.  A new slice is started only at a cohort boundary
    once the accumulated slice has reached the target.

    The iterator holds at most one slice in memory and does not build the full
    list of slices.
    """
    if max_units_per_slice <= 0:
        raise ValueError(
            f"max_units_per_slice must be positive, got {max_units_per_slice}"
        )

    buffer: list[PlannedSimulationUnit] = []
    last_start: date | None = None
    for unit in plan.units:
        start_date = unit.cohort.start_date
        if (
            buffer
            and start_date != last_start
            and len(buffer) >= max_units_per_slice
        ):
            yield tuple(buffer)
            buffer = []
        last_start = start_date
        buffer.append(unit)

    if buffer:
        yield tuple(buffer)


__all__ = ["iter_cohort_slices"]
