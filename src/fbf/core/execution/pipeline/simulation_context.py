"""Application simulation context.

Contains simulation configuration that belongs to the Application layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

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
