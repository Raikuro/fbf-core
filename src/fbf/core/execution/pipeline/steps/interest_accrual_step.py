"""Pipeline step that accrues interest on the loan balance (Part 49/52).

ERN Part 52 interest model:
- Annual rate = FFR + spread (e.g., FFR + 0.50%)
- Monthly real rate = (1 + annual_rate/12) × (CPI_prev / CPI_curr) - 1
- Interest = prior_loan_balance × monthly_real_rate
- Interest accrues on the PRIOR balance only (before new draw)

Pipeline ordering (ERN spreadsheet):
    T(N) = Y(N-1) × (1 + M(N))    [interest on prior balance]
    Y(N) = X(N) + T(N)             [draw added after interest]

This means InterestAccrualStep MUST run before LoanDrawStep.
"""

from __future__ import annotations

from decimal import Decimal

from fbf.core.execution.pipeline.pipeline import PipelineStep
from fbf.core.execution.pipeline.simulation import SimulationState


class InterestAccrualStep(PipelineStep):
    """PipelineStep that accrues interest on the loan balance.

    Implements the ERN Part 52 CPI-adjusted real interest rate:
        monthly_rate = (1 + annual_rate/12) * (CPI_prev / CPI_curr) - 1

    When CPI data is zero (real-terms dataset), this simplifies to:
        monthly_rate = annual_rate / 12

    Interest accrues on the PRIOR balance only, matching ERN's ordering
    where the new draw is added AFTER interest computation.
    """

    sequence_order = 26

    def execute(self, state: SimulationState) -> SimulationState:
        self._validate_state(state)

        # If no loan balance, no interest to accrue
        if state.loan_balance <= 0:
            return state

        # Determine annual rate for this period
        schedule = state.context.interest_rate_schedule
        if schedule is not None and state.period_index < len(schedule):
            annual_rate = schedule[state.period_index]
        else:
            annual_rate = state.interest_rate

        # Compute CPI-adjusted real monthly rate
        monthly_rate = self._compute_real_monthly_rate(annual_rate, state)

        # Interest on PRIOR balance only (before new draw)
        interest = state.loan_balance * monthly_rate

        # Capitalize interest (add to loan balance)
        state.loan_balance += interest

        return state

    def _compute_real_monthly_rate(
        self, annual_rate: Decimal, state: SimulationState
    ) -> Decimal:
        """Compute CPI-adjusted real monthly interest rate.

        Formula: (1 + annual_rate/12) * (CPI_prev / CPI_curr) - 1

        For real-terms datasets where CPI is zero, CPI_prev/CPI_curr = 1,
        so this simplifies to annual_rate / 12.
        """
        snapshot = state.market_snapshot
        if snapshot is None:
            return annual_rate / Decimal("12")

        cpi_curr = snapshot.inflation_cumulative
        prev_idx = state.period_index - 1
        if prev_idx >= 0 and prev_idx < len(state.context.dataset):
            cpi_prev = state.context.dataset[prev_idx].inflation_cumulative
        else:
            cpi_prev = cpi_curr

        # For real-terms datasets: CPI values are 0, ratio = 1
        if cpi_curr == 0 or cpi_prev == 0:
            return annual_rate / Decimal("12")

        cpi_ratio = cpi_prev / cpi_curr
        nominal_monthly = annual_rate / Decimal("12")
        real_monthly = (Decimal("1") + nominal_monthly) * cpi_ratio - Decimal("1")
        return real_monthly

    def _validate_state(self, state: SimulationState) -> None:
        if state.portfolio is None:
            raise ValueError("SimulationState.portfolio is required")
        if state.market_snapshot is None:
            raise ValueError("SimulationState.market_snapshot is required")
