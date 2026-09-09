"""Withdrawal policy abstractions for the Engine domain."""

from __future__ import annotations

from ..model.decision_context import DecisionContext
from .decisions import WithdrawalDecision
from .frequency import WithdrawalFrequency
from .policy import Policy


class WithdrawalPolicy(Policy):
    """Policy that decides the withdrawal amount for a simulation.

    Parameters
    ----------
    frequency:
        Cadence at which the policy produces non-zero amounts.
        ``MONTHLY`` (default) preserves existing behaviour exactly.
        ``ANNUAL`` produces one event per year (``period_index % 12 == 0``);
        all other months return zero-amount decisions that are safe
        no-ops for every downstream pipeline step.
    """

    def __init__(self, *, frequency: WithdrawalFrequency = WithdrawalFrequency.MONTHLY) -> None:
        self.frequency = frequency

    def decide(self, context: DecisionContext) -> WithdrawalDecision:
        if self.frequency is WithdrawalFrequency.ANNUAL and context.period_index % 12 != 0:
            from fbf.core.domain.model.money import Money

            return WithdrawalDecision(
                reason="WithdrawalPolicy.frequency_skip",
                nominal_amount=Money.ZERO,
                real_amount=Money.ZERO,
            )
        return self._decide_active(context)

    def _decide_active(self, context: DecisionContext) -> WithdrawalDecision:
        raise NotImplementedError
