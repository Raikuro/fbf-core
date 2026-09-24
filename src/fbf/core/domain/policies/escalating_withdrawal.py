"""Escalating withdrawal policy for deterministic case studies.

This module provides the EscalatingWithdrawalPolicy — a generic,
currency-agnostic withdrawal policy that escalates the withdrawal amount
annually at a fixed rate.

The policy computes withdrawal amounts according to the frozen semantics:

    initial_wealth * withdrawal_rate * (1 + escalation_rate) ** years_elapsed

where years_elapsed = period_index // 12 (annual boundaries at period_index % 12 == 0).

This policy is designed for Experiment E (ERN Part 20) but is fully
general-purpose and currency-agnostic — the currency comes from the
simulation's initial wealth.
"""

from __future__ import annotations

from decimal import Decimal

from fbf.core.domain.model.decision_context import DecisionContext
from fbf.core.domain.model.money import Money
from fbf.core.domain.policies.decisions import WithdrawalDecision
from fbf.core.domain.policies.frequency import WithdrawalFrequency
from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy

__all__ = ["EscalatingWithdrawalPolicy"]


class EscalatingWithdrawalPolicy(WithdrawalPolicy):
    """Withdrawal policy with annual escalation.

    The withdrawal amount starts at initial_wealth * withdrawal_rate and
    escalates by escalation_rate each year (compounded annually).

    Parameters
    ----------
    withdrawal_rate:
        Initial withdrawal rate as a Decimal fraction (e.g., Decimal("0.035") for 3.5%).
    escalation_rate:
        Annual escalation rate as a Decimal fraction (e.g., Decimal("0.02") for 2%).
        Defaults to 2% per year.
    frequency:
        Withdrawal cadence. ANNUAL produces one withdrawal per year at
        period_index % 12 == 0. MONTHLY divides the annual amount by 12.
        Defaults to ANNUAL for Experiment E compatibility.

    Notes
    -----
    - Currency is derived from simulation_context.initial_wealth (currency-agnostic).
    - Escalation applies at each annual boundary (period_index // 12 years elapsed).
    - Existing monthly withdrawal behavior (FixedRealWithdrawalPolicy) is unchanged.
    """

    def __init__(
        self,
        withdrawal_rate: Decimal,
        escalation_rate: Decimal = Decimal("0.02"),
        *,
        frequency: WithdrawalFrequency = WithdrawalFrequency.ANNUAL,
    ) -> None:
        super().__init__(frequency=frequency)
        if withdrawal_rate < 0:
            raise ValueError(f"withdrawal_rate must be non-negative, got {withdrawal_rate}")
        if escalation_rate < 0:
            raise ValueError(f"escalation_rate must be non-negative, got {escalation_rate}")
        self.withdrawal_rate = withdrawal_rate
        self.escalation_rate = escalation_rate

    def _decide_active(self, context: DecisionContext) -> WithdrawalDecision:
        sim_context = getattr(context, "simulation_context", None)
        if sim_context is None or not hasattr(sim_context, "initial_wealth"):
            raise TypeError(
                "EscalatingWithdrawalPolicy requires a DecisionContext "
                "with simulation_context.initial_wealth"
            )
        initial_wealth: Money = sim_context.initial_wealth

        years_elapsed = context.period_index // 12
        current_rate = self.withdrawal_rate * (Decimal("1") + self.escalation_rate) ** years_elapsed

        if self.frequency is WithdrawalFrequency.ANNUAL:
            amount = initial_wealth.amount * current_rate
        else:
            amount = initial_wealth.amount * current_rate / Decimal("12")

        return WithdrawalDecision(
            reason="EscalatingWithdrawalPolicy",
            nominal_amount=Money(amount, initial_wealth.currency),
            real_amount=Money(amount, initial_wealth.currency),
        )
