"""Application simulation context.

Contains simulation configuration that belongs to the Application layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fbf.core.domain.model.cash_flow import ExternalCashFlowSchedule
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.money import Money
from fbf.core.domain.model.portfolio import Portfolio
from fbf.core.domain.policies import AllocationPolicy, WithdrawalPolicy


@dataclass(frozen=True)
class SimulationContext:
    experiment_name: str
    cohort: str
    start_date: date
    horizon_months: int
    initial_wealth: Money
    initial_portfolio: Portfolio
    dataset: Dataset
    allocation_policy: AllocationPolicy
    withdrawal_policy: WithdrawalPolicy
    final_value_target: Decimal | None = None
    withdrawal_base: Money | None = None
    external_cash_flow_schedule: ExternalCashFlowSchedule | None = None
    loan_draw_rate: Decimal | None = None
    interest_rate: Decimal | None = None
    interest_rate_schedule: tuple[Decimal, ...] | None = None
    ltv_limit: Decimal | None = None
    ltv_enforcement: bool = True
    expense_ratio: Decimal | None = None
    debt_interest_rate_is_real: bool = False

    def __post_init__(self) -> None:
        if self.withdrawal_base is not None:
            if not isinstance(self.withdrawal_base, Money):
                raise TypeError(
                    "SimulationContext.withdrawal_base must be a Money instance or None"
                )
            if self.withdrawal_base.amount <= 0:
                raise ValueError("SimulationContext.withdrawal_base must be positive")
            if self.withdrawal_base.currency != self.initial_wealth.currency:
                raise ValueError(
                    "SimulationContext.withdrawal_base currency must match initial_wealth"
                )
        if self.external_cash_flow_schedule is not None:
            if not isinstance(
                self.external_cash_flow_schedule, ExternalCashFlowSchedule
            ):
                raise TypeError(
                    "SimulationContext.external_cash_flow_schedule must be an "
                    "ExternalCashFlowSchedule instance or None"
                )
            if (
                self.external_cash_flow_schedule.monthly_amount.currency
                != self.initial_wealth.currency
            ):
                raise ValueError(
                    "SimulationContext.external_cash_flow_schedule currency must "
                    "match initial_wealth"
                )
            effective_horizon = self.horizon_months - 1
            if self.external_cash_flow_schedule.end_period > effective_horizon:
                raise ValueError(
                    "SimulationContext.external_cash_flow_schedule.end_period must "
                    "not exceed horizon_months - 1"
                )
            scheduled_horizon = self.external_cash_flow_schedule.horizon_transitions
            if scheduled_horizon is not None and scheduled_horizon != effective_horizon:
                raise ValueError(
                    "SimulationContext.external_cash_flow_schedule horizon_transitions "
                    "must match horizon_months - 1"
                )
