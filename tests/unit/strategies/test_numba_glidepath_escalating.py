"""Glidepath allocation with escalating withdrawals in the general Numba engine.

The combined capability keeps two established contracts separate:

* Escalating withdrawals use the documented non-workbook timing: withdrawal
  before growth, escalation at ``m // 12``, and no growth after the final
  withdrawal.
* Glidepath weights advance according to their own cadence: monthly, or at the
  annual ``m // 12`` boundary.

Expected values below come from an independent Decimal recurrence, not from
the production Numba path.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import cast

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import EscalatingWithdrawalPolicy
from fbf.core.domain.policies.frequency import WithdrawalFrequency
from fbf.core.domain.policies.glidepath import (
    GlidepathAllocationPolicy,
    GlidepathCadence,
)
from fbf.core.execution.errors import UnsupportedConfigurationError
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    SimulationResult,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.numba_executor import (
    NumbaSimulationExecutor,
    _is_glidepath_escalating_eligible,
    is_numba_context_eligible,
)
from fbf.core.study.builder import build_initial_portfolio

_EQ = AssetClass(id="equity", name="", description="")
_BD = AssetClass(id="bond", name="", description="")

_WEALTH = Decimal("1000000")
_TOLERANCE = Decimal("0.01")

ANNUAL = WithdrawalFrequency.ANNUAL
MONTHLY = WithdrawalFrequency.MONTHLY


def _snap(
    d: date,
    equity_price: Decimal,
    bond_price: Decimal,
    *,
    is_underwater: bool,
) -> MarketSnapshot:
    return MarketSnapshot(
        date=d,
        index_levels={_EQ: equity_price, _BD: bond_price},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=not is_underwater,
        is_underwater=is_underwater,
        running_ath=equity_price
        if not is_underwater
        else equity_price * Decimal("1.25"),
    )


def _build_dataset(
    equity_returns: list[Decimal],
    bond_returns: list[Decimal],
    underwater_flags: list[bool],
) -> Dataset:
    """Dataset with ``len(equity_returns) + 1`` monthly snapshots."""
    assert len(equity_returns) == len(bond_returns)
    assert len(underwater_flags) == len(equity_returns) + 1

    equity_price = Decimal("100")
    bond_price = Decimal("100")
    d = date(2000, 1, 1)
    snapshots = [
        _snap(d, equity_price, bond_price, is_underwater=underwater_flags[0])
    ]
    for m, (equity_return, bond_return) in enumerate(
        zip(equity_returns, bond_returns, strict=True)
    ):
        equity_price *= equity_return
        bond_price *= bond_return
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
        snapshots.append(
            _snap(
                d,
                equity_price,
                bond_price,
                is_underwater=underwater_flags[m + 1],
            )
        )
    return Dataset(snapshots=tuple(snapshots), frequency="monthly")


def _context(
    dataset: Dataset,
    policy: GlidepathAllocationPolicy,
    *,
    horizon: int | None = None,
    rate: Decimal = Decimal("0.035"),
    escalation: Decimal = Decimal("0.02"),
    frequency: WithdrawalFrequency = ANNUAL,
    fee: Decimal = Decimal("0"),
    wealth: Decimal = _WEALTH,
) -> SimulationContext:
    horizon = len(dataset.snapshots) if horizon is None else horizon
    start = dataset[0].date
    return SimulationContext(
        experiment_name="glidepath-escalating",
        cohort=f"c-{horizon}",
        start_date=start,
        horizon_months=horizon,
        initial_wealth=Money(wealth, Currency.EUR),
        initial_portfolio=build_initial_portfolio(
            Money(_WEALTH, Currency.EUR), dataset
        ),
        dataset=dataset.slice(start, horizon),
        allocation_policy=policy,
        withdrawal_policy=EscalatingWithdrawalPolicy(
            withdrawal_rate=rate,
            escalation_rate=escalation,
            frequency=frequency,
        ),
        expense_ratio=fee,
    )


def _weights(
    policy: GlidepathAllocationPolicy,
    underwater_flags: list[bool],
    horizon: int,
) -> list[Decimal]:
    weights: list[Decimal] = []
    for m in range(horizon):
        if policy.cadence is GlidepathCadence.ANNUAL:
            advancements = m // 12
        elif policy.mode == "passive":
            advancements = m
        else:
            advancements = sum(1 for flag in underwater_flags[: m + 1] if flag)
        raw = policy.start_equity + policy.slope * advancements
        weights.append(min(raw, policy.end_equity))
    return weights


def _recurrence(
    dataset: Dataset,
    policy: GlidepathAllocationPolicy,
    *,
    rate: Decimal,
    escalation: Decimal,
    frequency: WithdrawalFrequency,
    fee: Decimal,
) -> tuple[Decimal, bool, int | None]:
    """Independent Decimal recurrence for the combined contract."""
    horizon = len(dataset.snapshots)
    underwater_flags = [snap.is_underwater for snap in dataset.snapshots]
    weights = _weights(policy, underwater_flags, horizon)
    annual = frequency is ANNUAL
    fee_monthly = fee / Decimal("12")
    value = _WEALTH
    base = value * rate

    for m in range(horizon):
        escalated = base * (Decimal("1") + escalation) ** (m // 12)
        if annual and m % 12 != 0:
            withdrawal = Decimal("0")
        elif annual:
            withdrawal = escalated
        else:
            withdrawal = escalated / Decimal("12")

        if withdrawal > value:
            return Decimal("0"), False, m

        value -= withdrawal
        if m < horizon - 1:
            equity_return = (
                dataset.snapshots[m + 1].index_levels[_EQ]
                / dataset.snapshots[m].index_levels[_EQ]
            )
            bond_return = (
                dataset.snapshots[m + 1].index_levels[_BD]
                / dataset.snapshots[m].index_levels[_BD]
            )
            growth = (
                weights[m] * equity_return
                + (Decimal("1") - weights[m]) * bond_return
            )
            value *= growth - fee_monthly

    return value, True, None


def _run(
    contexts: list[SimulationContext],
    *,
    materialize_timeline: bool = False,
) -> tuple[NumbaSimulationExecutor, list[SimulationResult]]:
    executor = NumbaSimulationExecutor(
        materialize_timeline=materialize_timeline
    )
    definition = EngineExperimentDefinition(
        name="glidepath-escalating",
        description="combined capability test",
        simulation_contexts=tuple(contexts),
    )
    run = executor.execute(definition)
    return executor, list(run.simulation_results)


def _assert_matches_recurrence(
    context: SimulationContext,
    result: SimulationResult,
) -> None:
    allocation = cast(GlidepathAllocationPolicy, context.allocation_policy)
    withdrawal = cast(EscalatingWithdrawalPolicy, context.withdrawal_policy)
    expected_value, expected_success, expected_failure = _recurrence(
        context.dataset,
        allocation,
        rate=withdrawal.withdrawal_rate,
        escalation=withdrawal.escalation_rate,
        frequency=withdrawal.frequency,
        fee=context.expense_ratio or Decimal("0"),
    )
    statistics = result.statistics
    assert statistics.success is expected_success
    assert statistics.failure_month == expected_failure
    assert (
        abs(statistics.final_wealth.amount - expected_value) < _TOLERANCE
    )


def _policy(
    cadence: GlidepathCadence,
    mode: str = "passive",
) -> GlidepathAllocationPolicy:
    return GlidepathAllocationPolicy(
        start_equity=Decimal("0.60"),
        end_equity=Decimal("0.90"),
        slope=Decimal("0.01"),
        mode=mode,
        cadence=cadence,
    )


def _market(
    horizon: int,
    *,
    underwater_pattern: tuple[int, ...] = (),
) -> Dataset:
    periods = horizon - 1
    equity_returns = [
        Decimal("1.012") if m % 5 else Decimal("0.994") for m in range(periods)
    ]
    bond_returns = [
        Decimal("1.003") if m % 3 else Decimal("1.001") for m in range(periods)
    ]
    underwater_flags = [
        any(m % modulus == 0 for modulus in underwater_pattern)
        for m in range(horizon)
    ]
    return _build_dataset(equity_returns, bond_returns, underwater_flags)


@pytest.mark.parametrize(
    ("cadence", "frequency"),
    [
        (GlidepathCadence.MONTHLY, MONTHLY),
        (GlidepathCadence.MONTHLY, ANNUAL),
        (GlidepathCadence.ANNUAL, MONTHLY),
        (GlidepathCadence.ANNUAL, ANNUAL),
    ],
)
def test_combined_matches_decimal_recurrence(
    cadence: GlidepathCadence,
    frequency: WithdrawalFrequency,
) -> None:
    horizon = 25
    dataset = _market(horizon)
    context = _context(
        dataset,
        _policy(cadence),
        rate=Decimal("0.035"),
        escalation=Decimal("0.02"),
        frequency=frequency,
        fee=Decimal("0.006"),
    )
    _, results = _run([context])
    _assert_matches_recurrence(context, results[0])


def test_active_monthly_glidepath_matches_decimal_recurrence() -> None:
    horizon = 37
    dataset = _market(horizon, underwater_pattern=(2, 5, 7))
    context = _context(
        dataset,
        _policy(GlidepathCadence.MONTHLY, mode="active"),
        frequency=MONTHLY,
        fee=Decimal("0.004"),
    )
    _, results = _run([context])
    _assert_matches_recurrence(context, results[0])


def test_annual_cadence_advances_at_year_boundaries_and_terminal_period() -> None:
    horizon = 25
    dataset = _market(horizon)
    context = _context(
        dataset,
        _policy(GlidepathCadence.ANNUAL),
        horizon=horizon,
    )
    _, results = _run([context], materialize_timeline=True)
    timeline = results[0].timeline

    weights: list[Decimal] = []
    for monthly in timeline.monthly_results:
        target = monthly.allocation_target
        assert target is not None
        weights.append(target.weights[_EQ])
    assert len(weights) == horizon
    assert weights[0] == Decimal("0.60")
    assert weights[11] == Decimal("0.60")
    assert weights[12] == Decimal("0.61")
    assert weights[23] == Decimal("0.61")
    assert weights[24] == Decimal("0.62")

    # The final annual withdrawal closes the trajectory without growth.
    assert timeline.monthly_results[-1].withdrawal_decision is not None
    assert timeline.monthly_results[-1].withdrawal_decision.nominal_amount.amount > 0


@pytest.mark.parametrize(
    ("cadence", "frequency"),
    [
        (GlidepathCadence.MONTHLY, MONTHLY),
        (GlidepathCadence.ANNUAL, ANNUAL),
    ],
)
def test_depletion_matches_decimal_recurrence(
    cadence: GlidepathCadence,
    frequency: WithdrawalFrequency,
) -> None:
    horizon = 25
    dataset = _build_dataset(
        [Decimal("1")] * (horizon - 1),
        [Decimal("1")] * (horizon - 1),
        [False] * horizon,
    )
    context = _context(
        dataset,
        _policy(cadence),
        rate=Decimal("0.60"),
        escalation=Decimal("0"),
        frequency=frequency,
        fee=Decimal("0"),
    )
    _, results = _run([context])
    _assert_matches_recurrence(context, results[0])

    expected_value, expected_success, expected_failure = _recurrence(
        context.dataset,
        cast(GlidepathAllocationPolicy, context.allocation_policy),
        rate=Decimal("0.60"),
        escalation=Decimal("0"),
        frequency=frequency,
        fee=Decimal("0"),
    )
    assert expected_success is False
    assert expected_value == Decimal("0")
    assert expected_failure is not None


def test_cadence_is_part_of_the_trajectory_key() -> None:
    horizon = 25
    dataset = _market(horizon)
    monthly = _context(
        dataset,
        _policy(GlidepathCadence.MONTHLY),
        frequency=MONTHLY,
    )
    annual = _context(
        dataset,
        _policy(GlidepathCadence.ANNUAL),
        frequency=MONTHLY,
    )
    executor, results = _run([monthly, annual])

    report = executor.report
    assert report is not None
    assert report.groups == 2
    _assert_matches_recurrence(monthly, results[0])
    _assert_matches_recurrence(annual, results[1])


def test_expense_ratio_is_part_of_the_trajectory_and_growth_factor_keys() -> None:
    horizon = 25
    dataset = _market(horizon)
    no_fee = _context(
        dataset,
        _policy(GlidepathCadence.ANNUAL),
        frequency=ANNUAL,
        fee=Decimal("0"),
    )
    with_fee = _context(
        dataset,
        _policy(GlidepathCadence.ANNUAL),
        frequency=ANNUAL,
        fee=Decimal("0.006"),
    )
    executor, results = _run([no_fee, with_fee])

    report = executor.report
    assert report is not None
    assert report.groups == 2
    _assert_matches_recurrence(no_fee, results[0])
    _assert_matches_recurrence(with_fee, results[1])
    assert results[0].statistics.final_wealth != results[1].statistics.final_wealth


def test_shared_trajectory_derives_shorter_horizon() -> None:
    long_horizon = 37
    short_horizon = 19
    dataset = _market(long_horizon)
    policy = _policy(GlidepathCadence.ANNUAL)
    long_ctx = _context(dataset, policy, horizon=long_horizon)
    short_ctx = _context(dataset, policy, horizon=short_horizon)

    executor, results = _run([long_ctx, short_ctx])
    report = executor.report
    assert report is not None
    assert report.groups == 1
    _assert_matches_recurrence(long_ctx, results[0])
    _assert_matches_recurrence(short_ctx, results[1])


def test_combined_context_is_admitted_by_generic_numba() -> None:
    dataset = _market(25)
    context = _context(
        dataset,
        _policy(GlidepathCadence.ANNUAL),
        frequency=ANNUAL,
    )
    assert _is_glidepath_escalating_eligible(context) is True
    assert is_numba_context_eligible(context) is True


def test_initial_portfolio_value_mismatch_is_not_eligible() -> None:
    dataset = _market(25)
    context = _context(
        dataset,
        _policy(GlidepathCadence.ANNUAL),
        wealth=Decimal("990000"),
    )
    assert _is_glidepath_escalating_eligible(context) is False

    with pytest.raises(UnsupportedConfigurationError):
        _run([context])
