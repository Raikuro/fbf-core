"""Optional drawdown projections built on the shared drawdown implementation.

The execution layer records raw net-worth observations.  This adapter is the
single boundary that converts those observations into the optional drawdown
contract used by ``MonthlyResult`` and ``SimulationStatistics``:

* the first observation has no interval, so its drawdown is unavailable;
* one valid observation cannot produce a measurable interval, so the maximum
  drawdown is unavailable;
* invalid or unmeasurable paths are unavailable rather than reported as zero;
* all actual drawdown mathematics remains in :mod:`drawdown`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

import numpy as np
from numpy.typing import NDArray

from fbf.core.execution.strategies.drawdown import (
    ContributionPositiveFlow,
    FlowTiming,
    compute_drawdown,
)

FloatSeries = Sequence[float] | NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class DrawdownResult:
    """Optional per-observation drawdowns and the optional maximum."""

    drawdowns: tuple[float | None, ...]
    max_drawdown: float | None


def withdrawals_as_contribution_flows(
    withdrawal_amounts: Sequence[float | Decimal],
) -> tuple[ContributionPositiveFlow, ...]:
    """Convert positive withdrawal amounts to contribution-positive flows.

    This is the boundary for simulations whose recorded values are already
    post-withdrawal observations (``FlowTiming.END``).  A withdrawal is a
    negative external contribution.
    """
    return tuple(
        ContributionPositiveFlow(-float(amount)) for amount in withdrawal_amounts
    )


def _unavailable(length: int) -> DrawdownResult:
    return DrawdownResult(
        drawdowns=tuple(None for _ in range(length)),
        max_drawdown=None,
    )


def compute_optional_drawdown(
    net_worth: FloatSeries,
    external_cash_flows: Sequence[ContributionPositiveFlow] | None = None,
    *,
    flow_timing: FlowTiming,
) -> DrawdownResult:
    """Return optional drawdowns for an observed net-worth path.

    ``net_worth`` must contain only the observations the execution kernel
    actually recorded.  When the path cannot define a drawdown (no
    observations, a single observation, a non-positive/non-finite initial
    value, or an undefined flow-adjusted return), every value is ``None``.
    """
    values = tuple(float(value) for value in net_worth)
    length = len(values)

    if length < 2:
        return _unavailable(length)
    if not math.isfinite(values[0]) or values[0] <= 0.0:
        return _unavailable(length)
    if not all(math.isfinite(value) for value in values):
        return _unavailable(length)

    try:
        path = compute_drawdown(
            values,
            external_cash_flows,
            flow_timing=flow_timing,
        )
    except ValueError:
        return _unavailable(length)

    drawdowns: tuple[float | None, ...] = (None, *path.drawdowns[1:])
    return DrawdownResult(
        drawdowns=drawdowns,
        max_drawdown=path.max_drawdown,
    )


__all__ = [
    "DrawdownResult",
    "compute_optional_drawdown",
    "withdrawals_as_contribution_flows",
]
