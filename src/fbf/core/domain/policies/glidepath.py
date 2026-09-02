"""Glidepath allocation policy — dynamic equity weight over time.

Implements both passive and active glidepath modes as described in
ERN Part 19.  The policy is stateless: the equity weight at any period
is a deterministic function of the period index and the historical
market state available through the DecisionContext.
"""

from __future__ import annotations

from decimal import Decimal

from fbf.core.domain.model.allocation import AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.decision_context import DecisionContext
from fbf.core.domain.policies.allocation_policy import AllocationPolicy
from fbf.core.domain.policies.decisions import AllocationDecision


class GlidepathAllocationPolicy(AllocationPolicy):
    """Period-indexed glidepath allocation policy.

    The equity weight increases from *start_equity* toward *end_equity*
    at a rate of *slope* percentage points per qualifying month.

    Passive mode: every month qualifies.
    Active mode: only months where ``dataset[period_index].is_underwater``
    qualifies.

    Parameters
    ----------
    start_equity:
        Initial equity weight (0.0–1.0).
    end_equity:
        Target equity weight (0.0–1.0).  The weight never exceeds this value.
    slope:
        Monthly increase as a **fraction** (e.g. ``Decimal("0.005")``
        for 0.5 percentage points per qualifying month).  The YAML/builder
        layer converts percentage-point values to fractions.
    mode:
        ``"passive"`` — advancement every month.
        ``"active"`` — advancement only when the S&P 500 is below its
        all-time high (``is_underwater == True``).
    """

    _EQUITY = AssetClass(id="equity", name="", description="")
    _BOND = AssetClass(id="bond", name="", description="")

    def __init__(
        self,
        start_equity: Decimal,
        end_equity: Decimal,
        slope: Decimal,
        mode: str,
    ) -> None:
        if mode not in ("passive", "active"):
            raise ValueError(
                f"GlidepathAllocationPolicy mode must be 'passive' or 'active', got {mode!r}"
            )
        if slope < 0:
            raise ValueError(
                f"GlidepathAllocationPolicy slope must be non-negative, got {slope}"
            )
        self.start_equity = start_equity
        self.end_equity = end_equity
        self.slope = slope
        self.mode = mode

    def decide(self, context: DecisionContext) -> AllocationDecision:
        advancement_count = self._count_advancements(context)
        raw = self.start_equity + self.slope * advancement_count
        equity = min(raw, self.end_equity)
        return AllocationDecision(
            reason="GlidepathAllocationPolicy",
            allocation_target=AllocationTarget(weights={
                self._EQUITY: equity,
                self._BOND: Decimal("1") - equity,
            }),
        )

    def _count_advancements(self, context: DecisionContext) -> int:
        if self.mode == "passive":
            return context.period_index
        return self._count_underwater_periods(context)

    def _count_underwater_periods(self, context: DecisionContext) -> int:
        snapshots = context.dataset.snapshots
        limit = min(context.period_index + 1, len(snapshots))
        return sum(1 for i in range(limit) if snapshots[i].is_underwater)
