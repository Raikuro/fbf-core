"""Application simulation context.

Contains simulation configuration that belongs to the Application layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

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
