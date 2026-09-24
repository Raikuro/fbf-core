"""Deterministic execution adapter for single-trajectory case studies.

This module provides a thin composition layer around the existing
SimulationRunner to execute deterministic trajectories. It reuses the
existing engine, pipeline, and result structures without duplicating
any simulation logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
    from fbf.core.execution import ExecutionOptions
    from fbf.core.execution.pipeline.simulation import MonthlyResult

from fbf.core.domain.model.allocation import AllocationTarget
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import AllocationPolicy, WithdrawalPolicy
from fbf.core.execution.pipeline.schedule import ExecutionSchedule


@dataclass(frozen=True, slots=True)
class DeterministicTrajectory:
    """Configuration for a single deterministic simulation trajectory.

    This is an immutable input specification that contains all parameters
    needed to execute one deterministic trajectory using the existing
    simulation engine. It does not contain any Experiment E-specific
    fields; it is fully generic and currency-agnostic.

    Parameters
    ----------
    name:
        Identifier for the trajectory (used in results).
    initial_wealth:
        Initial portfolio wealth (currency comes from this Money object).
    initial_allocation:
        Target allocation for period 0.
    dataset:
        Prescribed dataset with monthly market snapshots.
    allocation_policy:
        Allocation policy (e.g., glidepath with annual cadence).
    withdrawal_policy:
        Withdrawal policy (e.g., escalating with annual frequency).
    horizon_months:
        Number of monthly periods to simulate.
    expense_ratio:
        Annual expense ratio as a Decimal fraction (e.g., 0.0005 for 0.05%).
        Defaults to 0 (no expenses).
    schedule:
        Optional ExecutionSchedule to control step cadence (e.g., annual rebalance).
        Defaults to None (all steps execute every period).
    """

    name: str
    initial_wealth: Money
    initial_allocation: AllocationTarget
    dataset: Dataset
    allocation_policy: AllocationPolicy
    withdrawal_policy: WithdrawalPolicy
    horizon_months: int
    expense_ratio: Decimal = Decimal("0")
    schedule: ExecutionSchedule | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("DeterministicTrajectory.name must be non-empty")
        if self.horizon_months <= 0:
            raise ValueError("DeterministicTrajectory.horizon_months must be positive")
        if self.expense_ratio < 0:
            raise ValueError("DeterministicTrajectory.expense_ratio must be non-negative")


@dataclass(frozen=True, slots=True)
class DeterministicResult:
    """Result of a deterministic trajectory execution.

    Contains the full simulation result plus extracted checkpoints at
    requested period indices. Reuses existing MonthlyResult structures.
    """

    name: str
    timeline: tuple[MonthlyResult, ...]
    checkpoints: dict[int, MonthlyResult]
    final_wealth: Money
    success: bool
    failure_period: int | None = None
    failure_state: str | None = None


def _build_initial_portfolio(
    initial_wealth: Money,
    initial_allocation: AllocationTarget,
    dataset: Dataset,
) -> tuple[Portfolio, list[AssetHolding]]:
    """Build initial portfolio matching the initial_allocation weights.

    Computes holdings such that the portfolio value at the first dataset
    snapshot equals initial_wealth with the specified allocation weights.

    Returns
    -------
    tuple
        (Portfolio, list of AssetHolding) for the constructed portfolio.
    """
    from fbf.core.domain.model.portfolio import AssetHolding, Portfolio

    initial_snapshot = dataset[0]
    holdings = []

    for asset_class, weight in initial_allocation.weights.items():
        price = initial_snapshot.index_levels.get(asset_class)
        if price is None:
            raise ValueError(
                f"Dataset initial snapshot missing price for {asset_class}"
            )
        if price == 0:
            raise ValueError(f"Initial price for {asset_class} is zero")

        units = (initial_wealth.amount * weight) / price
        holdings.append(AssetHolding(asset_class=asset_class, units=units))

    return Portfolio(holdings=tuple(holdings)), holdings


def execute_deterministic_trajectory(
    trajectory: DeterministicTrajectory,
    options: ExecutionOptions | None = None,
) -> DeterministicResult:
    """Execute a deterministic trajectory using the existing engine.

    This is a thin adapter that:
    1. Constructs a SimulationContext from the trajectory
    2. Creates a SimulationRunner with the default pipeline
    3. Runs the runner with the configured ExecutionSchedule
    4. Extracts checkpoints from the existing MonthlyResult timeline
    5. Returns a DeterministicResult with checkpoints

    Does NOT introduce a second simulation engine. Uses the existing
    SimulationRunner and SimulationPipeline.

    Parameters
    ----------
    trajectory:
        The deterministic trajectory configuration.
    options:
        Optional ExecutionOptions for the runner. Defaults to default options.

    Returns
    -------
    DeterministicResult
        Result containing full timeline and requested checkpoints.
    """
    from fbf.core.execution import ExecutionOptions
    from fbf.core.execution.pipeline.default_pipeline import create_default_pipeline
    from fbf.core.execution.pipeline.runner import SimulationRunner
    from fbf.core.execution.pipeline.simulation import SimulationResult
    from fbf.core.execution.pipeline.simulation_context import SimulationContext

    _ = options or ExecutionOptions()

    # Build initial portfolio matching the initial allocation
    initial_portfolio, _ = _build_initial_portfolio(
        trajectory.initial_wealth,
        trajectory.initial_allocation,
        trajectory.dataset,
    )

    # Create simulation context
    context = SimulationContext(
        experiment_name=trajectory.name,
        cohort=trajectory.name,  # Use trajectory name as cohort ID
        start_date=trajectory.dataset.start_date,
        horizon_months=trajectory.horizon_months,
        initial_wealth=trajectory.initial_wealth,
        initial_portfolio=initial_portfolio,
        dataset=trajectory.dataset,
        allocation_policy=trajectory.allocation_policy,
        withdrawal_policy=trajectory.withdrawal_policy,
        expense_ratio=trajectory.expense_ratio if trajectory.expense_ratio > 0 else None,
    )

    # Create runner with default pipeline
    pipeline = create_default_pipeline()
    runner = SimulationRunner(pipeline=pipeline)

    # Execute with optional schedule
    result: SimulationResult = runner.run(context, schedule=trajectory.schedule)

    # Extract checkpoints from monthly results
    # Note: The design specifies checkpoints at specific period indices
    # For Experiment E: Year 2 = period_index 23, Year 10 = period_index 119
    # The trajectory doesn't specify checkpoints; we extract all monthly results
    # and the research layer can filter as needed.
    monthly_results = tuple(result.timeline.monthly_results)

    # Build checkpoints dict (all monthly results indexed by period_index)
    # The research layer can filter for specific periods (e.g., 23, 119)
    checkpoints = {mr.period_index: mr for mr in monthly_results}

    def _portfolio_value(monthly_result: MonthlyResult, currency: Currency) -> Money:
        """Compute portfolio value from MonthlyResult portfolio and market snapshot."""
        from fbf.core.domain.model.money import Money

        total = Decimal("0")
        for holding in monthly_result.portfolio.holdings:
            price = monthly_result.market_snapshot.index_levels.get(holding.asset_class)
            if price is not None:
                total += holding.units * price
        return Money(total, currency)

    # Get final wealth from the last monthly result
    final_wealth = trajectory.initial_wealth  # fallback
    if monthly_results:
        final_wealth = _portfolio_value(monthly_results[-1], trajectory.initial_wealth.currency)

    return DeterministicResult(
        name=trajectory.name,
        timeline=monthly_results,
        checkpoints=checkpoints,
        final_wealth=final_wealth,
        success=result.statistics.success,
        failure_period=result.statistics.failure_month,
        failure_state=result.statistics.failure_state,
    )


__all__ = [
    "DeterministicTrajectory",
    "DeterministicResult",
    "execute_deterministic_trajectory",
]

