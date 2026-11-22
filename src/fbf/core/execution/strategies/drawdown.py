"""Flow-adjusted drawdown calculations for optimized simulation paths."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import NewType

import numpy as np
from numpy.typing import NDArray

from fbf.core.domain.model.money import Money

FloatSeries = Sequence[float] | NDArray[np.float64]
ContributionPositiveFlow = NewType("ContributionPositiveFlow", float)


class FlowTiming(Enum):
    """Timing of an external cash flow relative to an interval's return."""

    BEGINNING = "beginning"
    END = "end"


@dataclass(frozen=True, slots=True)
class DrawdownPath:
    """Flow-adjusted investment index and its drawdown path."""

    investment_index: tuple[float, ...]
    drawdowns: tuple[float, ...]
    max_drawdown: float


def flows_from_timeline_net_cash_flows(
    net_cash_flows: Sequence[Money | None],
) -> tuple[ContributionPositiveFlow, ...]:
    """Convert timeline cash flows to the contribution-positive convention.

    ``MonthlyResult.net_cash_flow`` is positive for withdrawals and negative
    for contributions.  This conversion inverts that sign and represents
    ``None`` as a zero flow.  Use this boundary before calling
    :func:`compute_drawdown` with values taken from a simulation timeline.
    """
    return tuple(
        ContributionPositiveFlow(-float(flow.amount))
        if flow is not None
        else ContributionPositiveFlow(0.0)
        for flow in net_cash_flows
    )


def _growth_factor(
    previous: float,
    current: float,
    external_cash_flow: ContributionPositiveFlow,
    flow_timing: FlowTiming,
) -> float:
    flow = float(external_cash_flow)
    if flow_timing is FlowTiming.BEGINNING:
        invested_capital = previous + flow
        adjusted_wealth = current
    elif flow_timing is FlowTiming.END:
        invested_capital = previous
        adjusted_wealth = current - flow
    else:
        raise ValueError("unsupported flow timing")

    if not math.isfinite(invested_capital):
        raise ValueError("invested capital is not finite")
    if invested_capital < 0.0:
        raise ValueError(
            "investment return is undefined because invested capital is "
            "negative"
        )
    if invested_capital == 0.0:
        if adjusted_wealth == 0.0:
            return 1.0
        raise ValueError(
            "investment return is undefined because flow-adjusted invested "
            "capital is zero"
        )

    growth_factor = adjusted_wealth / invested_capital
    if not math.isfinite(growth_factor):
        raise ValueError("investment return is not a finite growth factor")
    return growth_factor


def compute_drawdown(
    net_worth: FloatSeries,
    external_cash_flows: Sequence[ContributionPositiveFlow] | None = None,
    *,
    flow_timing: FlowTiming,
) -> DrawdownPath:
    """Compute a flow-adjusted investment index and its drawdown path.

    ``net_worth[t]`` is the observed net worth at observation ``t``.
    ``external_cash_flows[t]`` is the signed net external flow assigned to the
    interval ending at observation ``t``.  It uses the contribution-positive
    convention: positive is a contribution and negative is a withdrawal.
    Timeline values must be converted with
    :func:`flows_from_timeline_net_cash_flows`.  The first observation
    establishes the base, so its flow entry is ignored.

    ``FlowTiming.BEGINNING`` applies the flow before the interval return::

        W_t = (W_{t-1} + F_t) * G_t

    ``FlowTiming.END`` applies the flow after the interval return::

        W_t = W_{t-1} * G_t + F_t

    ``G_t`` is a growth factor, not a return rate.  Fees remain embedded in
    ``G_t`` because only external flows are added back.

    Flow-adjusted wealth is ``W_t - F_t`` for end-timed flows and ``W_t`` for
    beginning-timed flows.  Positive adjusted wealth produces a normal growth
    factor.  Zero adjusted wealth produces a zero growth factor, so the index
    reaches zero and drawdown reaches 100%.  Negative adjusted wealth produces
    a negative growth factor; the index may become negative and drawdown may
    exceed 100%.  Drawdown is not capped at 100%.

    Negative invested capital raises ``ValueError`` because a percentage
    return relative to negative capital is undefined.

    When beginning-timed invested capital is exactly zero and ending wealth is
    also zero, no capital remained exposed to market performance and the
    previous investment index is preserved.  Zero invested capital with
    non-zero adjusted wealth raises ``ValueError`` because the investment
    return cannot be inferred.

    Returns positive drawdowns as loss magnitudes, starting with zero at the
    base observation.
    """
    if not isinstance(flow_timing, FlowTiming):
        raise ValueError("unsupported flow timing")

    worth = tuple(float(value) for value in net_worth)
    if not worth:
        raise ValueError("net_worth must contain at least one observation")
    if not math.isfinite(worth[0]) or worth[0] <= 0.0:
        raise ValueError("net_worth[0] must be a positive finite value")
    if not all(math.isfinite(value) for value in worth):
        raise ValueError("net_worth must contain only finite values")

    if external_cash_flows is None:
        flows = tuple(ContributionPositiveFlow(0.0) for _ in worth)
    else:
        flows = tuple(
            ContributionPositiveFlow(float(flow)) for flow in external_cash_flows
        )
        if len(flows) != len(worth):
            raise ValueError("external_cash_flows must match net_worth length")
        if not all(math.isfinite(float(flow)) for flow in flows):
            raise ValueError(
                "external_cash_flows must contain only finite values"
            )

    investment_index = [1.0]
    drawdowns = [0.0]
    peak = 1.0
    max_drawdown = 0.0

    for period in range(1, len(worth)):
        growth_factor = _growth_factor(
            worth[period - 1],
            worth[period],
            flows[period],
            flow_timing,
        )
        index_value = investment_index[-1] * growth_factor
        if not math.isfinite(index_value):
            raise ValueError("investment index is not finite")
        investment_index.append(index_value)

        peak = max(peak, index_value)
        drawdown = max(0.0, 1.0 - index_value / peak)
        drawdowns.append(drawdown)
        max_drawdown = max(max_drawdown, drawdown)

    return DrawdownPath(
        investment_index=tuple(investment_index),
        drawdowns=tuple(drawdowns),
        max_drawdown=max_drawdown,
    )


__all__ = [
    "ContributionPositiveFlow",
    "DrawdownPath",
    "FlowTiming",
    "compute_drawdown",
    "flows_from_timeline_net_cash_flows",
]
