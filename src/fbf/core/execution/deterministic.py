"""Deterministic execution adapter for single-trajectory case studies.

Supported two-asset deterministic trajectories are executed by a dedicated
Numba kernel that tracks equity and bond units separately.  This preserves
intra-year weight drift while still rebalancing at the configured cadence
(annual by default in Experiment E).  Withdrawals and rebalances occur at the
beginning of a period, after the prior period's growth and fee deduction.

The kernel implements the workbook fee convention:

    fee_t = V_{t-1} * expense_ratio / 12
    V_t   = V_{t-1} * (1 + g_t) - fee_t - W_t

Unsupported configurations with no fee are delegated to the legacy pipeline.
Unsupported configurations with a non-zero fee raise
``UnsupportedConfigurationError`` rather than silently using the legacy
stale-base expense correction.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from fbf.core.domain.model.allocation import AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import AllocationPolicy, WithdrawalPolicy
from fbf.core.domain.policies.concrete import (
    ConstantAllocationPolicy,
    ConstantWithdrawalPolicy,
    FixedRealWithdrawalPolicy,
)
from fbf.core.domain.policies.escalating_withdrawal import EscalatingWithdrawalPolicy
from fbf.core.domain.policies.frequency import WithdrawalFrequency
from fbf.core.domain.policies.glidepath import GlidepathAllocationPolicy, GlidepathCadence
from fbf.core.execution.errors import UnsupportedConfigurationError
from fbf.core.execution.pipeline.schedule import ExecutionSchedule, StepCadence
from fbf.core.execution.strategies.trajectory import build_simulation_timeline

if TYPE_CHECKING:
    from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
    from fbf.core.execution import ExecutionOptions
    from fbf.core.execution.pipeline.simulation import MonthlyResult
    from fbf.core.execution.pipeline.simulation_context import SimulationContext


@dataclass(frozen=True, slots=True)
class DeterministicTrajectory:
    """Configuration for a single deterministic simulation trajectory.

    This is an immutable input specification that contains all parameters
    needed to execute one deterministic trajectory. It does not contain any
    Experiment E-specific fields; it is fully generic and currency-agnostic.

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
    rebalance_cadence:
        Optional rebalance cadence for deterministic execution. When set, it
        takes precedence over the rebalance entry in ``schedule``. Defaults to
        None, which preserves the schedule's rebalance cadence or EVERY_PERIOD.
    schedule:
        Optional ExecutionSchedule to control step cadence (e.g., annual
        rebalance). Retained for Tier 1 compatibility; new callers should use
        ``rebalance_cadence``. Defaults to None (all steps execute every
        period).
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
    rebalance_cadence: StepCadence | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("DeterministicTrajectory.name must be non-empty")
        if self.horizon_months <= 0:
            raise ValueError("DeterministicTrajectory.horizon_months must be positive")
        if self.expense_ratio < 0:
            raise ValueError("DeterministicTrajectory.expense_ratio must be non-negative")
        if self.rebalance_cadence is not None and self.schedule is not None:
            scheduled = self.schedule.explicit_rebalance_cadence()
            if scheduled is not None and scheduled is not self.rebalance_cadence:
                raise ValueError(
                    "rebalance_cadence conflicts with the schedule's explicit "
                    "rebalance cadence"
                )


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


@dataclass(frozen=True, slots=True)
class _KernelInputs:
    """Validated inputs for the dedicated deterministic kernel."""

    equity_class: AssetClass
    equity_prices: NDArray[np.float64]
    bond_prices: NDArray[np.float64]
    target_weights: tuple[Decimal, ...]
    target_weights_float: NDArray[np.float64]
    rebalance_flags: NDArray[np.bool_]
    fixed_withdrawal_amounts: NDArray[np.float64]
    exact_withdrawal_amounts: tuple[Decimal, ...] | None
    use_proportional_withdrawal: bool
    proportional_rate: float
    proportional_annual: bool


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


def _unsupported_schedule_reason(schedule: ExecutionSchedule | None) -> str | None:
    """Return a reason when non-rebalance steps have non-default cadence."""
    if schedule is None:
        return None

    custom = schedule.custom_non_rebalance_cadences()
    if not custom:
        return None

    step_name, cadence = custom[0]
    return f"non-rebalance step {step_name} uses {cadence.value} cadence"


def _unsupported_kernel_reason(trajectory: DeterministicTrajectory) -> str | None:
    """Return why *trajectory* cannot use the deterministic Numba kernel.

    ``None`` means the kernel supports the configuration.
    """
    if trajectory.horizon_months > len(trajectory.dataset):
        return "dataset has fewer snapshots than the requested horizon"

    weights = trajectory.initial_allocation.weights
    if len(weights) != 2:
        return "only two-asset deterministic trajectories are supported"

    equity_classes = [asset for asset in weights if asset.id == "equity"]
    if len(equity_classes) != 1:
        return "initial allocation must contain exactly one equity asset"

    equity_class = equity_classes[0]
    bond_classes = [asset for asset in weights if asset is not equity_class]
    if len(bond_classes) != 1:
        return "initial allocation must contain exactly one non-equity asset"

    if equity_class not in trajectory.dataset[0].index_levels:
        return "dataset is missing the equity asset"
    if bond_classes[0] not in trajectory.dataset[0].index_levels:
        return "dataset is missing the bond asset"

    if not isinstance(
        trajectory.allocation_policy,
        (ConstantAllocationPolicy, GlidepathAllocationPolicy),
    ):
        return (
            "unsupported allocation policy "
            f"{type(trajectory.allocation_policy).__name__}"
        )

    if (
        isinstance(trajectory.allocation_policy, ConstantAllocationPolicy)
        and trajectory.allocation_policy.allocations is not None
    ):
        policy_ids = {asset_id for asset_id, _ in trajectory.allocation_policy.allocations}
        if policy_ids != {equity_class.id, bond_classes[0].id}:
            return "explicit allocations must cover exactly the two held assets"

    if not isinstance(
        trajectory.withdrawal_policy,
        (
            ConstantWithdrawalPolicy,
            FixedRealWithdrawalPolicy,
            EscalatingWithdrawalPolicy,
        ),
    ):
        return (
            "unsupported withdrawal policy "
            f"{type(trajectory.withdrawal_policy).__name__}"
        )

    schedule_reason = _unsupported_schedule_reason(trajectory.schedule)
    if schedule_reason is not None:
        return schedule_reason

    if trajectory.initial_wealth.amount < 0:
        raise ValueError("initial_wealth must be non-negative")

    return None


def _select_asset_classes(
    trajectory: DeterministicTrajectory,
) -> tuple[AssetClass, AssetClass]:
    weights = trajectory.initial_allocation.weights
    equity_class = next(asset for asset in weights if asset.id == "equity")
    bond_class = next(asset for asset in weights if asset is not equity_class)
    return equity_class, bond_class


def _target_equity_weight(
    policy: ConstantAllocationPolicy | GlidepathAllocationPolicy,
    dataset: Dataset,
    month: int,
) -> Decimal:
    if isinstance(policy, ConstantAllocationPolicy):
        if policy.allocations is not None:
            return dict(policy.allocations)["equity"]
        if policy.equity_allocation is None:
            raise ValueError("legacy ConstantAllocationPolicy has no equity allocation")
        return policy.equity_allocation

    if policy.cadence is GlidepathCadence.ANNUAL:
        advancement = month // 12
    elif policy.mode == "passive":
        advancement = month
    else:
        advancement = sum(
            1 for index in range(month + 1) if dataset[index].is_underwater
        )
    return min(policy.start_equity + policy.slope * advancement, policy.end_equity)


def _target_equity_weights(
    trajectory: DeterministicTrajectory,
) -> tuple[Decimal, ...]:
    policy = trajectory.allocation_policy
    if not isinstance(policy, (ConstantAllocationPolicy, GlidepathAllocationPolicy)):
        raise TypeError("unsupported allocation policy")
    return tuple(
        _target_equity_weight(policy, trajectory.dataset, month)
        for month in range(trajectory.horizon_months)
    )


def _effective_rebalance_cadence(trajectory: DeterministicTrajectory) -> StepCadence:
    """Resolve the rebalance cadence without importing a pipeline step class."""
    if trajectory.rebalance_cadence is not None:
        return trajectory.rebalance_cadence
    if trajectory.schedule is None:
        return StepCadence.EVERY_PERIOD
    return trajectory.schedule.rebalance_cadence()


def _rebalance_flags(trajectory: DeterministicTrajectory) -> NDArray[np.bool_]:
    horizon = trajectory.horizon_months
    if _effective_rebalance_cadence(trajectory) is StepCadence.ANNUAL:
        return np.array(
            [month % 12 == 0 for month in range(horizon)], dtype=np.bool_
        )
    return np.ones(horizon, dtype=np.bool_)


def _withdrawal_plan(
    trajectory: DeterministicTrajectory,
) -> tuple[
    bool,
    float,
    bool,
    NDArray[np.float64],
    tuple[Decimal, ...] | None,
]:
    """Return (proportional, rate, annual, fixed_amounts, exact_amounts)."""
    horizon = trajectory.horizon_months
    policy = trajectory.withdrawal_policy
    fixed = np.zeros(horizon, dtype=np.float64)

    if isinstance(policy, ConstantWithdrawalPolicy):
        return (
            True,
            float(policy.withdrawal_rate),
            policy.frequency is WithdrawalFrequency.ANNUAL,
            fixed,
            None,
        )

    annual = policy.frequency is WithdrawalFrequency.ANNUAL
    base = trajectory.initial_wealth.amount
    exact: list[Decimal] = []

    if isinstance(policy, FixedRealWithdrawalPolicy):
        amount = base * policy.withdrawal_rate
        if not annual:
            amount /= Decimal("12")
        for month in range(horizon):
            current = amount if not annual or month % 12 == 0 else Decimal("0")
            exact.append(current)
            fixed[month] = float(current)
        return False, 0.0, False, fixed, tuple(exact)

    if isinstance(policy, EscalatingWithdrawalPolicy):
        for month in range(horizon):
            escalated = (
                base
                * policy.withdrawal_rate
                * (Decimal("1") + policy.escalation_rate) ** (month // 12)
            )
            if annual:
                current = escalated if month % 12 == 0 else Decimal("0")
            else:
                current = escalated / Decimal("12")
            exact.append(current)
            fixed[month] = float(current)
        return False, 0.0, False, fixed, tuple(exact)

    raise TypeError(f"unsupported withdrawal policy {type(policy).__name__}")


def _prepare_kernel_inputs(trajectory: DeterministicTrajectory) -> _KernelInputs:
    equity_class, bond_class = _select_asset_classes(trajectory)
    horizon = trajectory.horizon_months
    equity_prices: list[float] = []
    bond_prices: list[float] = []

    for month in range(horizon):
        snapshot = trajectory.dataset[month]
        equity_price = snapshot.index_levels.get(equity_class)
        bond_price = snapshot.index_levels.get(bond_class)
        if equity_price is None or bond_price is None:
            raise ValueError("dataset is missing a required asset price")
        if equity_price <= 0 or bond_price <= 0:
            raise ValueError("deterministic execution requires positive asset prices")
        equity_prices.append(float(equity_price))
        bond_prices.append(float(bond_price))

    target_weights = _target_equity_weights(trajectory)
    use_proportional, rate, proportional_annual, fixed, exact = _withdrawal_plan(trajectory)

    return _KernelInputs(
        equity_class=equity_class,
        equity_prices=np.array(equity_prices, dtype=np.float64),
        bond_prices=np.array(bond_prices, dtype=np.float64),
        target_weights=target_weights,
        target_weights_float=np.array(
            [float(weight) for weight in target_weights], dtype=np.float64
        ),
        rebalance_flags=_rebalance_flags(trajectory),
        fixed_withdrawal_amounts=fixed,
        exact_withdrawal_amounts=exact,
        use_proportional_withdrawal=use_proportional,
        proportional_rate=rate,
        proportional_annual=proportional_annual,
    )


def _build_context(trajectory: DeterministicTrajectory) -> SimulationContext:
    from fbf.core.execution.pipeline.simulation_context import SimulationContext

    initial_portfolio, _ = _build_initial_portfolio(
        trajectory.initial_wealth,
        trajectory.initial_allocation,
        trajectory.dataset,
    )
    return SimulationContext(
        experiment_name=trajectory.name,
        cohort=trajectory.name,
        start_date=trajectory.dataset.start_date,
        horizon_months=trajectory.horizon_months,
        initial_wealth=trajectory.initial_wealth,
        initial_portfolio=initial_portfolio,
        dataset=trajectory.dataset,
        allocation_policy=trajectory.allocation_policy,
        withdrawal_policy=trajectory.withdrawal_policy,
        expense_ratio=trajectory.expense_ratio if trajectory.expense_ratio > 0 else None,
    )


def _execute_deterministic_kernel(
    trajectory: DeterministicTrajectory,
) -> DeterministicResult:
    from fbf.core.execution.strategies.deterministic_kernel import (
        simulate_deterministic_two_asset,
    )

    inputs = _prepare_kernel_inputs(trajectory)
    horizon = trajectory.horizon_months
    out_values = np.empty(horizon, dtype=np.float64)
    out_actual_weights = np.empty(horizon, dtype=np.float64)
    out_target_weights = np.empty(horizon, dtype=np.float64)
    out_withdrawals = np.empty(horizon, dtype=np.float64)

    initial_equity_weight = float(
        trajectory.initial_allocation.weights[inputs.equity_class]
    )
    final_value, success, failure_month, months_simulated = (
        simulate_deterministic_two_asset(
            inputs.equity_prices,
            inputs.bond_prices,
            inputs.target_weights_float,
            inputs.rebalance_flags,
            inputs.fixed_withdrawal_amounts,
            inputs.use_proportional_withdrawal,
            inputs.proportional_rate,
            inputs.proportional_annual,
            float(trajectory.expense_ratio),
            float(trajectory.initial_wealth.amount),
            initial_equity_weight,
            horizon,
            out_values,
            out_actual_weights,
            out_target_weights,
            out_withdrawals,
        )
    )

    currency = trajectory.initial_wealth.currency
    if success:
        final_wealth = Money(Decimal(str(final_value)), currency)
        failure_period = None
        failure_state = None
    else:
        final_wealth = Money(Decimal("0"), currency)
        failure_period = failure_month
        failure_state = "depleted"

    context = _build_context(trajectory)
    if inputs.exact_withdrawal_amounts is not None:
        withdrawal_amounts = inputs.exact_withdrawal_amounts[:months_simulated]
    else:
        withdrawal_amounts = tuple(
            Decimal(str(float(out_withdrawals[month])))
            for month in range(months_simulated)
        )

    timeline = build_simulation_timeline(
        context,
        out_values,
        n_months=months_simulated,
        withdrawal_reason=type(trajectory.withdrawal_policy).__name__,
        withdrawal_amounts=withdrawal_amounts,
        actual_equity_weights=out_actual_weights,
        target_equity_weights=inputs.target_weights,
    )
    monthly_results = tuple(timeline.monthly_results)
    checkpoints = {result.period_index: result for result in monthly_results}

    return DeterministicResult(
        name=trajectory.name,
        timeline=monthly_results,
        checkpoints=checkpoints,
        final_wealth=final_wealth,
        success=success,
        failure_period=failure_period,
        failure_state=failure_state,
    )


def _execute_legacy_deterministic(
    trajectory: DeterministicTrajectory,
    options: ExecutionOptions | None = None,
) -> DeterministicResult:
    """Execute through the legacy Decimal pipeline (fee-free fallback only)."""
    from fbf.core.execution import ExecutionOptions
    from fbf.core.execution.pipeline.default_pipeline import create_default_pipeline
    from fbf.core.execution.pipeline.runner import SimulationRunner
    from fbf.core.execution.pipeline.simulation import SimulationResult

    _ = options or ExecutionOptions()

    context = _build_context(trajectory)
    pipeline = create_default_pipeline()
    runner = SimulationRunner(pipeline=pipeline)
    schedule = trajectory.schedule
    if trajectory.rebalance_cadence is not None:
        schedule = (schedule or ExecutionSchedule()).with_rebalance_cadence(
            trajectory.rebalance_cadence
        )
    result: SimulationResult = runner.run(context, schedule=schedule)

    monthly_results = tuple(result.timeline.monthly_results)
    checkpoints = {mr.period_index: mr for mr in monthly_results}

    def _portfolio_value(monthly_result: MonthlyResult, currency: Currency) -> Money:
        from fbf.core.domain.model.money import Money

        total = Decimal("0")
        for holding in monthly_result.portfolio.holdings:
            price = monthly_result.market_snapshot.index_levels.get(holding.asset_class)
            if price is not None:
                total += holding.units * price
        return Money(total, currency)

    final_wealth = trajectory.initial_wealth
    if monthly_results:
        final_wealth = _portfolio_value(
            monthly_results[-1], trajectory.initial_wealth.currency
        )

    return DeterministicResult(
        name=trajectory.name,
        timeline=monthly_results,
        checkpoints=checkpoints,
        final_wealth=final_wealth,
        success=result.statistics.success,
        failure_period=result.statistics.failure_month,
        failure_state=result.statistics.failure_state,
    )


def execute_deterministic_trajectory(
    trajectory: DeterministicTrajectory,
    options: ExecutionOptions | None = None,
) -> DeterministicResult:
    """Execute a deterministic trajectory.

    Two-asset configurations with supported allocation/withdrawal policies are
    executed by the dedicated Numba kernel.  Unsupported fee-free
    configurations fall back to the legacy Decimal pipeline.  Unsupported
    configurations with a non-zero fee raise ``UnsupportedConfigurationError``.

    Parameters
    ----------
    trajectory:
        The deterministic trajectory configuration.
    options:
        Optional ExecutionOptions for the legacy fallback.  The kernel path
        always materializes the full monthly timeline.

    Returns
    -------
    DeterministicResult
        Result containing the full timeline and checkpoints.
    """
    reason = _unsupported_kernel_reason(trajectory)
    if reason is None:
        return _execute_deterministic_kernel(trajectory)

    if trajectory.expense_ratio > 0:
        raise UnsupportedConfigurationError(
            "deterministic Numba execution does not support this configuration "
            f"with a non-zero expense ratio: {reason}"
        )

    return _execute_legacy_deterministic(trajectory, options)


__all__ = [
    "DeterministicTrajectory",
    "DeterministicResult",
    "execute_deterministic_trajectory",
]
