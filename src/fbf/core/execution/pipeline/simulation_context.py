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
    loan_draw_rate: Decimal | None = None
    interest_rate: Decimal | None = None
    ltv_limit: Decimal | None = None
