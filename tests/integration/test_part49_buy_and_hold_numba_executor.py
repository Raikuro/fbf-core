"""Leveraged buy-and-hold (Part 49 + BuyAndHoldAllocationPolicy) Numba tests.

Covers eligibility, direct Numba execution (no silent fallback), correctness
against an *independent* Decimal unit-tracking debt recurrence, differential
agreement with the legacy buy-and-hold pipeline (fee = 0), LTV/enforcement
invariants, failure states, and the AUTO/FAST/REFERENCE dispatch contract —
including the routing fix that guarantees an unsupported buy-and-hold workload
is never silently simulated by the periodically rebalancing default pipeline.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from decimal import Decimal
from types import EllipsisType
from typing import cast

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies import (
    BuyAndHoldAllocationPolicy,
    ConstantAllocationPolicy,
    FixedRealWithdrawalPolicy,
)
from fbf.core.domain.policies.frequency import WithdrawalFrequency
from fbf.core.domain.policies.part49_withdrawal import Part49WithdrawalPolicy
from fbf.core.execution import (
    ExecutionBackend,
    ExecutionOptions,
    ExecutionStrategy,
    NoOpProfiler,
    UnsupportedConfigurationError,
    _auto_select_backend,
    _extract_simulation_contexts,
    execute_study_plan,
)
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    SimulationResult,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.part49_buy_and_hold_numba_executor import (
    Part49BuyAndHoldNumbaExecutor,
    is_part49_buy_and_hold_eligible,
)
from fbf.core.study.builder import BuiltStudy
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan
from tests.unit.execution.debt_recurrence_reference import compute_monthly_rates

EQUITY_ASSET = AssetClass(id="equity", name="", description="")
BOND_ASSET = AssetClass(id="bond", name="", description="")

INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)
EQUITY_ALLOCATION = Decimal("0.75")
WITHDRAWAL_RATE = Decimal("0.03")
LOAN_DRAW_RATE = Decimal("0.01")
INTEREST_RATE = Decimal("0.015")
LTV_LIMIT = Decimal("0.75")

_InterestRateSchedule = tuple[Decimal, ...] | None | EllipsisType

_WEALTH_TOLERANCE = Decimal("0.01")


# ---------------------------------------------------------------------------
# Datasets and contexts
# ---------------------------------------------------------------------------


def _create_growth_dataset(
    horizon_months: int,
    equity_return: Decimal,
    bond_return: Decimal,
    monthly_inflation: Decimal = Decimal("0"),
) -> Dataset:
    """Dataset with constant monthly returns and optional compounding CPI."""
    snapshots = []
    current = date(1965, 11, 1)
    eq_price = Decimal("100")
    bd_price = Decimal("100")
    cpi = Decimal("1")
    for _ in range(horizon_months + 1):
        snapshots.append(
            MarketSnapshot(
                date=current,
                index_levels={EQUITY_ASSET: eq_price, BOND_ASSET: bd_price},
                inflation=monthly_inflation,
                inflation_cumulative=cpi,
                is_ath=True,
                is_underwater=False,
                running_ath=eq_price,
            )
        )
        eq_price = eq_price * (Decimal("1") + equity_return)
        bd_price = bd_price * (Decimal("1") + bond_return)
        if monthly_inflation != 0:
            cpi = cpi * (Decimal("1") + monthly_inflation)
        current = date(current.year + (current.month // 12), current.month % 12 + 1, 1)
    return Dataset(snapshots=tuple(snapshots), frequency="monthly")


def _create_flat_dataset(horizon_months: int) -> Dataset:
    return _create_growth_dataset(horizon_months, Decimal("0"), Decimal("0"))


def _create_trend_dataset(horizon_months: int) -> Dataset:
    """Strong equity trend so buy-and-hold drift differs materially from rebalancing."""
    return _create_growth_dataset(
        horizon_months, Decimal("0.01"), Decimal("0")
    )


def _create_varying_dataset(horizon_months: int) -> Dataset:
    """Deterministic varying returns (alternating up/down months)."""
    snapshots = []
    current = date(1965, 11, 1)
    eq_price = Decimal("100")
    bd_price = Decimal("100")
    for i in range(horizon_months + 1):
        snapshots.append(
            MarketSnapshot(
                date=current,
                index_levels={EQUITY_ASSET: eq_price, BOND_ASSET: bd_price},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=eq_price,
            )
        )
        eq_return = Decimal("0.01") if i % 2 == 0 else Decimal("-0.008")
        bd_return = Decimal("0.002") if i % 3 == 0 else Decimal("0.001")
        eq_price = eq_price * (Decimal("1") + eq_return)
        bd_price = bd_price * (Decimal("1") + bd_return)
        current = date(current.year + (current.month // 12), current.month % 12 + 1, 1)
    return Dataset(snapshots=tuple(snapshots), frequency="monthly")


def _create_decline_dataset(horizon_months: int) -> Dataset:
    """Steady equity decline so leverage grows the loan and LTV rises."""
    return _create_growth_dataset(
        horizon_months, Decimal("-0.0666666666666667"), Decimal("0")
    )


def _make_context(
    dataset: Dataset,
    horizon_months: int,
    *,
    equity_weight: Decimal = EQUITY_ALLOCATION,
    withdrawal_rate: Decimal = WITHDRAWAL_RATE,
    loan_draw_rate: Decimal | None = LOAN_DRAW_RATE,
    interest_rate: Decimal | None = INTEREST_RATE,
    interest_rate_schedule: _InterestRateSchedule = ...,
    ltv_limit: Decimal | None = LTV_LIMIT,
    ltv_enforcement: bool = False,
    debt_interest_rate_is_real: bool = True,
    expense_ratio: Decimal | None = None,
    final_value_target: Decimal | None = None,
    frequency: WithdrawalFrequency = WithdrawalFrequency.MONTHLY,
    equity_units: Decimal = Decimal("7500"),
    bond_units: Decimal = Decimal("2500"),
) -> SimulationContext:
    if interest_rate_schedule is ...:
        interest_rate_schedule = None
    return SimulationContext(
        experiment_name="test",
        cohort="1965-11",
        start_date=dataset[0].date,
        horizon_months=horizon_months,
        initial_wealth=INITIAL_WEALTH,
        initial_portfolio=Portfolio(
            holdings=(
                AssetHolding(asset_class=EQUITY_ASSET, units=equity_units),
                AssetHolding(asset_class=BOND_ASSET, units=bond_units),
            )
        ),
        dataset=dataset.slice(dataset[0].date, horizon_months),
        allocation_policy=BuyAndHoldAllocationPolicy(equity_weight),
        withdrawal_policy=Part49WithdrawalPolicy(
            withdrawal_rate=withdrawal_rate,
            frequency=frequency,
        ),
        interest_rate=interest_rate,
        interest_rate_schedule=interest_rate_schedule,
        ltv_limit=ltv_limit,
        ltv_enforcement=ltv_enforcement,
        expense_ratio=expense_ratio,
        loan_draw_rate=loan_draw_rate,
        debt_interest_rate_is_real=debt_interest_rate_is_real,
        final_value_target=final_value_target,
    )


def _numba_result(ctx: SimulationContext) -> SimulationResult:
    run = Part49BuyAndHoldNumbaExecutor().execute(
        EngineExperimentDefinition(name="numba", description="numba", simulation_contexts=(ctx,))
    )
    return run.simulation_results[0]


# ---------------------------------------------------------------------------
# Independent Decimal unit-tracking debt recurrence (primary oracle)
# ---------------------------------------------------------------------------


def _part49_buy_and_hold_reference(
    dataset: Dataset,
    horizon_months: int,
    initial_value: Decimal,
    equity_weight: Decimal,
    withdrawal_rate: Decimal,
    loan_draw_rate: Decimal,
    monthly_rates: Sequence[Decimal],
    ltv_limit: Decimal,
    ltv_enforcement: bool,
) -> tuple[Decimal, bool, int | None, str | None, Decimal]:
    """Independent Decimal recurrence for leveraged buy-and-hold.

    The target equity/bond split is applied once to *initial_value* at the month
    0 prices, then tracked as per-asset *units* (not as a drifting weight):
    portfolio value is recomputed from units × index levels every month, and the
    Part 49 loan balance is carried explicitly.  Withdrawals sell both holdings
    pro rata (preserving the current weights); growth is implicit in the index
    levels as the month advances.

    Returns ``(final_value, success, failure_month, failure_state, final_loan)``.
    """
    one = Decimal("1")
    snap0 = dataset[0]
    price0_eq = snap0.index_levels[EQUITY_ASSET]
    price0_bd = snap0.index_levels[BOND_ASSET]
    portfolio_withdrawal = initial_value * withdrawal_rate / Decimal("12")
    loan_draw = initial_value * loan_draw_rate / Decimal("12")

    eq_units = initial_value * equity_weight / price0_eq
    bd_units = initial_value * (one - equity_weight) / price0_bd
    loan = Decimal("0")

    for m in range(horizon_months):
        snapshot = dataset[m]
        value = (
            eq_units * snapshot.index_levels[EQUITY_ASSET]
            + bd_units * snapshot.index_levels[BOND_ASSET]
        )

        if loan > 0:
            loan += loan * monthly_rates[m]
        loan += loan_draw

        if portfolio_withdrawal >= value:
            return Decimal("0"), False, m, "depleted", loan

        # Pro-rata sale preserves the (drifting) equity/bond split.
        sell_fraction = portfolio_withdrawal / value
        eq_units = eq_units * (one - sell_fraction)
        bd_units = bd_units * (one - sell_fraction)
        value_after = value - portfolio_withdrawal

        if ltv_enforcement and loan > 0 and value_after > 0:
            ltv = loan / value_after
            if ltv > ltv_limit:
                liquidation = (loan - ltv_limit * value_after) / (one - ltv_limit)
                if liquidation > value_after:
                    loan -= value_after
                    value_after = Decimal("0")
                else:
                    return (
                        value_after - liquidation,
                        False,
                        m,
                        "margin_call_terminal",
                        loan - liquidation,
                    )

        if value_after <= 0:
            return Decimal("0"), False, m, "depleted", loan
        if ltv_enforcement and loan > value_after and loan > 0:
            return value_after, False, m, "margin_call_impossible", loan

    final_snapshot = dataset[horizon_months - 1]
    final_value = (
        eq_units * final_snapshot.index_levels[EQUITY_ASSET]
        + bd_units * final_snapshot.index_levels[BOND_ASSET]
    )
    return final_value, True, None, None, loan


def _reference_from_context(
    ctx: SimulationContext,
) -> tuple[Decimal, bool, int | None, str | None, Decimal]:
    withdrawal = ctx.withdrawal_policy
    assert isinstance(withdrawal, Part49WithdrawalPolicy)
    assert isinstance(ctx.allocation_policy, BuyAndHoldAllocationPolicy)
    assert ctx.interest_rate is not None or ctx.interest_rate_schedule is not None
    snapshot0 = ctx.dataset[0]
    initial_value = sum(
        (
            holding.units * snapshot0.index_levels[holding.asset_class]
            for holding in ctx.initial_portfolio.holdings
        ),
        Decimal("0"),
    )
    monthly_rates = compute_monthly_rates(
        tuple(snapshot.inflation_cumulative for snapshot in ctx.dataset.snapshots),
        ctx.horizon_months,
        annual_rate_schedule=ctx.interest_rate_schedule,
        fixed_annual_rate=ctx.interest_rate,
        real_rate=ctx.debt_interest_rate_is_real,
    )
    final_value, success, failure_month, failure_state, final_loan = (
        _part49_buy_and_hold_reference(
            ctx.dataset,
            ctx.horizon_months,
            initial_value,
            ctx.allocation_policy.equity_allocation,
            withdrawal.withdrawal_rate,
            ctx.loan_draw_rate or Decimal("0"),
            monthly_rates,
            ctx.ltv_limit or Decimal("0.5"),
            ctx.ltv_enforcement,
        )
    )
    if success and ctx.final_value_target is not None:
        success = (
            final_value
            >= ctx.final_value_target * ctx.initial_wealth.amount
        )
    return final_value, success, failure_month, failure_state, final_loan


class TestPart49BuyAndHoldKernelHandCalculated:
    def test_flat_market_no_leverage_drains_linearly(self) -> None:
        import numpy as np

        from fbf.core.execution.strategies.numba_kernel import (
            _simulate_part49_buy_and_hold,
        )

        horizon = 60
        ones = np.ones(horizon, dtype=np.float64)
        withdrawal = 1_000_000.0 * 0.03 / 12.0
        final, ok, fm, _loan, reason = _simulate_part49_buy_and_hold(
            ones, ones, np.zeros(horizon), 1_000_000.0, 0.75, withdrawal, 0.0, 0.75,
            horizon, False,
        )
        assert ok is True
        assert fm == -1
        assert reason == 0
        assert abs(final - (1_000_000.0 - horizon * withdrawal)) < 1e-6

    def test_flat_market_with_draw_portfolio_unaffected_without_enforcement(self) -> None:
        import numpy as np

        from fbf.core.execution.strategies.numba_kernel import (
            _simulate_part49_buy_and_hold,
        )

        horizon = 60
        ones = np.ones(horizon, dtype=np.float64)
        withdrawal = 1_000_000.0 * 0.03 / 12.0
        loan_draw = 1_000_000.0 * 0.01 / 12.0
        loan_rate = np.array([0.015 / 12.0] * horizon, dtype=np.float64)
        final, ok, _, loan, _ = _simulate_part49_buy_and_hold(
            ones, ones, loan_rate, 1_000_000.0, 0.75, withdrawal, loan_draw, 0.75,
            horizon, False,
        )
        assert ok is True
        assert abs(final - (1_000_000.0 - horizon * withdrawal)) < 1e-6
        assert loan > 0.0

    @pytest.mark.parametrize("weight", [0.0, 1.0])
    def test_full_allocation_matches_single_asset(self, weight: float) -> None:
        import numpy as np

        from fbf.core.execution.strategies.numba_kernel import (
            _simulate_part49_buy_and_hold,
        )

        horizon = 24
        eq = np.array([1.01] * (horizon - 1), dtype=np.float64)
        bd = np.array([1.001] * (horizon - 1), dtype=np.float64)
        withdrawal = 1_000_000.0 * 0.03 / 12.0
        final, ok, _, _, _ = _simulate_part49_buy_and_hold(
            eq, bd, np.zeros(horizon), 1_000_000.0, weight, withdrawal, 0.0, 0.75,
            horizon, False,
        )
        growth = 1.01 if weight == 1.0 else 1.001
        value = 1_000_000.0
        for m in range(horizon):
            value -= withdrawal
            if m < horizon - 1:
                value *= growth
        assert ok is True
        assert abs(final - value) < 1e-9


class TestPart49BuyAndHoldIndependentReference:
    """Differential against the independent Decimal unit-tracking recurrence."""

    @staticmethod
    def _assert_matches(ctx: SimulationContext, numba: SimulationResult) -> None:
        exp_value, exp_ok, exp_fm, exp_state, _loan = _reference_from_context(ctx)
        stats = numba.statistics
        assert stats.success is exp_ok
        assert stats.failure_state == exp_state
        assert stats.failure_month == exp_fm
        expected_months = exp_fm if exp_fm is not None else ctx.horizon_months
        assert stats.months_simulated == expected_months
        diff = abs(stats.final_wealth.amount - exp_value)
        assert diff < _WEALTH_TOLERANCE, (
            f"final wealth diff {diff} exceeds tolerance {_WEALTH_TOLERANCE}: "
            f"numba={stats.final_wealth.amount}, reference={exp_value}"
        )

    @pytest.mark.parametrize(
        ("weight", "equity_return", "bond_return"),
        [
            ("0.0", "0.006", "0.002"),
            ("0.25", "0.006", "0.002"),
            ("0.5", "-0.002", "0.001"),
            ("0.75", "0.006", "0.002"),
            ("1.0", "0.006", "0.002"),
        ],
    )
    def test_constant_growth_matches_reference(
        self, weight: str, equity_return: str, bond_return: str
    ) -> None:
        horizon = 120
        ctx = _make_context(
            _create_growth_dataset(
                horizon, Decimal(equity_return), Decimal(bond_return)
            ),
            horizon,
            equity_weight=Decimal(weight),
        )
        self._assert_matches(ctx, _numba_result(ctx))

    def test_constant_growth_legacy_returns_match_reference(self) -> None:
        horizon = 120
        ctx = _make_context(
            _create_growth_dataset(horizon, Decimal("0.006"), Decimal("0.002")),
            horizon,
            equity_weight=Decimal("0.5"),
        )
        self._assert_matches(ctx, _numba_result(ctx))

    def test_varying_returns_match_reference(self) -> None:
        horizon = 96
        ctx = _make_context(_create_varying_dataset(horizon), horizon)
        self._assert_matches(ctx, _numba_result(ctx))

    def test_cpi_adjusted_rate_matches_reference(self) -> None:
        horizon = 60
        ctx = _make_context(
            _create_growth_dataset(
                horizon,
                Decimal("-0.01"),
                Decimal("0"),
                monthly_inflation=Decimal("0.003"),
            ),
            horizon,
            debt_interest_rate_is_real=False,
            interest_rate=Decimal("0.02"),
        )
        self._assert_matches(ctx, _numba_result(ctx))

    def test_zero_loan_draw_matches_reference(self) -> None:
        horizon = 60
        ctx = _make_context(
            _create_growth_dataset(horizon, Decimal("0.004"), Decimal("0.001")),
            horizon,
            loan_draw_rate=Decimal("0"),
        )
        self._assert_matches(ctx, _numba_result(ctx))

    def test_flat_market_no_leverage_matches_hand_calculation(self) -> None:
        horizon = 60
        ctx = _make_context(
            _create_flat_dataset(horizon),
            horizon,
            loan_draw_rate=Decimal("0"),
        )
        result = _numba_result(ctx)
        self._assert_matches(ctx, result)

        withdrawal = INITIAL_WEALTH.amount * WITHDRAWAL_RATE / Decimal("12")
        expected = INITIAL_WEALTH.amount - horizon * withdrawal
        assert abs(result.statistics.final_wealth.amount - expected) < _WEALTH_TOLERANCE

    def test_depletion_matches_reference(self) -> None:
        horizon = 120
        ctx = _make_context(
            _create_decline_dataset(horizon), horizon, withdrawal_rate=Decimal("0.6")
        )
        result = _numba_result(ctx)
        self._assert_matches(ctx, result)
        assert result.statistics.success is False
        assert result.statistics.failure_state == "depleted"
        assert result.statistics.final_wealth.amount == Decimal("0")

    def test_ltv_terminal_matches_reference(self) -> None:
        horizon = 120
        ctx = _make_context(
            _create_decline_dataset(horizon), horizon, ltv_enforcement=True
        )
        result = _numba_result(ctx)
        self._assert_matches(ctx, result)
        assert result.statistics.success is False
        assert result.statistics.failure_state == "margin_call_terminal"

    def test_enforcement_off_matches_reference(self) -> None:
        horizon = 120
        ctx = _make_context(
            _create_decline_dataset(horizon), horizon, ltv_enforcement=False
        )
        self._assert_matches(ctx, _numba_result(ctx))

    def test_final_value_target_pass_and_fail_match_reference(self) -> None:
        horizon = 60
        dataset = _create_growth_dataset(horizon, Decimal("0.004"), Decimal("0.001"))

        passing = _make_context(dataset, horizon, final_value_target=Decimal("0.5"))
        passing_result = _numba_result(passing)
        self._assert_matches(passing, passing_result)
        assert passing_result.statistics.success is True

        failing = _make_context(dataset, horizon, final_value_target=Decimal("10"))
        failing_result = _numba_result(failing)
        self._assert_matches(failing, failing_result)
        assert failing_result.statistics.success is False
        assert failing_result.statistics.failure_month is None
        assert failing_result.statistics.failure_state is None

    def test_terminal_loan_matches_reference_on_survivor(self) -> None:
        horizon = 60
        ctx = _make_context(
            _create_varying_dataset(horizon), horizon
        )
        result = _numba_result(ctx)
        assert result.statistics.success is True

        import numpy as np

        from fbf.core.execution.strategies.eligibility import _index_series
        from fbf.core.execution.strategies.numba_kernel import (
            _materialize_price_float,
            _simulate_part49_buy_and_hold,
        )

        series = _index_series(ctx)
        asset_classes = tuple(series.keys())
        prices = _materialize_price_float(asset_classes, series)
        equity_row = next(
            i for i, ac in enumerate(asset_classes) if cast(AssetClass, ac).id == "equity"
        )
        bond_row = next(
            i for i, ac in enumerate(asset_classes) if cast(AssetClass, ac).id == "bond"
        )
        equity_growth = prices[equity_row][1:] / prices[equity_row][:-1]
        bond_growth = prices[bond_row][1:] / prices[bond_row][:-1]

        snapshot0 = ctx.dataset[0]
        v0 = float(
            sum(
                h.units * snapshot0.index_levels[h.asset_class]
                for h in ctx.initial_portfolio.holdings
            )
        )
        withdrawal = ctx.withdrawal_policy
        assert isinstance(withdrawal, Part49WithdrawalPolicy)
        assert ctx.interest_rate is not None
        monthly_rate = float(ctx.interest_rate / Decimal("12"))
        rates = np.array([monthly_rate] * horizon, dtype=np.float64)
        kernel_loan = _simulate_part49_buy_and_hold(
            equity_growth[:horizon],
            bond_growth[:horizon],
            rates,
            v0,
            float(EQUITY_ALLOCATION),
            v0 * float(withdrawal.withdrawal_rate) / 12.0,
            v0 * float(LOAN_DRAW_RATE) / 12.0,
            float(LTV_LIMIT),
            horizon,
            False,
        )[3]

        _value, _ok, _fm, _state, ref_loan = _reference_from_context(ctx)
        assert abs(Decimal(str(kernel_loan)) - ref_loan) < _WEALTH_TOLERANCE


class TestPart49BuyAndHoldExecutor:
    def test_does_not_invoke_reference_executor(self) -> None:
        ctx = _make_context(_create_decline_dataset(24), 24)
        executor = Part49BuyAndHoldNumbaExecutor()

        assert not hasattr(executor, "_reference")
        run = executor.execute(
            EngineExperimentDefinition(name="t", description="t", simulation_contexts=(ctx,))
        )
        assert len(run.simulation_results) == 1

    def test_report_counts_logical_units(self) -> None:
        dataset = _create_decline_dataset(24)
        contexts = (
            _make_context(dataset, 12),
            _make_context(dataset, 24),
        )
        executor = Part49BuyAndHoldNumbaExecutor()
        run = executor.execute(
            EngineExperimentDefinition(
                name="t", description="t", simulation_contexts=contexts
            )
        )
        assert len(run.simulation_results) == 2
        report = executor.report
        assert report is not None
        assert report.logical_units == 2
        assert report.month_work == 12 + 24

    def test_ineligible_context_raises(self) -> None:
        ctx = _make_context(
            _create_flat_dataset(12), 12, expense_ratio=Decimal("0.005")
        )
        with pytest.raises(UnsupportedConfigurationError):
            Part49BuyAndHoldNumbaExecutor().execute(
                EngineExperimentDefinition(
                    name="t", description="t", simulation_contexts=(ctx,)
                )
            )

    def test_shared_trajectory_is_one_cluster(self) -> None:
        base = _create_growth_dataset(121, Decimal("0.006"), Decimal("0.002"))
        long_ctx = _make_context(base, 120)
        short_ctx = _make_context(base, 60)
        executor = Part49BuyAndHoldNumbaExecutor()
        executor.execute(
            EngineExperimentDefinition(
                name="t", description="t", simulation_contexts=(long_ctx, short_ctx)
            )
        )
        report = executor.report
        assert report is not None
        assert report.groups == 1

    def test_different_allocations_are_separate_groups(self) -> None:
        base = _create_growth_dataset(61, Decimal("0.006"), Decimal("0.002"))
        a = _make_context(base, 60, equity_weight=Decimal("0.25"))
        b = _make_context(base, 60, equity_weight=Decimal("0.75"))
        executor = Part49BuyAndHoldNumbaExecutor()
        executor.execute(
            EngineExperimentDefinition(
                name="t", description="t", simulation_contexts=(a, b)
            )
        )
        report = executor.report
        assert report is not None
        assert report.groups == 2


class TestPart49BuyAndHoldEligibility:
    def test_eligible_context_returns_true(self) -> None:
        assert is_part49_buy_and_hold_eligible(
            _make_context(_create_flat_dataset(12), 12)
        )

    def test_constant_allocation_ineligible(self) -> None:
        ctx = replace(
            _make_context(_create_flat_dataset(12), 12),
            allocation_policy=ConstantAllocationPolicy(Decimal("0.75")),
        )
        assert is_part49_buy_and_hold_eligible(ctx) is False

    def test_non_part49_withdrawal_ineligible(self) -> None:
        ctx = replace(
            _make_context(_create_flat_dataset(12), 12),
            withdrawal_policy=FixedRealWithdrawalPolicy(
                withdrawal_rate=Decimal("0.04")
            ),
        )
        assert is_part49_buy_and_hold_eligible(ctx) is False

    def test_annual_frequency_ineligible(self) -> None:
        ctx = _make_context(
            _create_flat_dataset(12),
            12,
            frequency=WithdrawalFrequency.ANNUAL,
        )
        assert is_part49_buy_and_hold_eligible(ctx) is False

    def test_nonzero_expense_ratio_ineligible(self) -> None:
        ctx = _make_context(
            _create_flat_dataset(12), 12, expense_ratio=Decimal("0.005")
        )
        assert is_part49_buy_and_hold_eligible(ctx) is False

    def test_no_rate_source_ineligible(self) -> None:
        ctx = replace(
            _make_context(_create_flat_dataset(12), 12),
            interest_rate=None,
            interest_rate_schedule=None,
        )
        assert is_part49_buy_and_hold_eligible(ctx) is False

    def test_schedule_covering_horizon_eligible(self) -> None:
        ctx = _make_context(
            _create_flat_dataset(12),
            12,
            interest_rate_schedule=tuple(Decimal("0.02") for _ in range(12)),
        )
        assert is_part49_buy_and_hold_eligible(ctx) is True

    def test_single_holding_ineligible(self) -> None:
        ctx = replace(
            _make_context(_create_flat_dataset(12), 12),
            initial_portfolio=Portfolio(
                holdings=(
                    AssetHolding(asset_class=EQUITY_ASSET, units=Decimal("10000")),
                )
            ),
        )
        assert is_part49_buy_and_hold_eligible(ctx) is False

    def test_dataset_too_short_ineligible(self) -> None:
        ctx = replace(
            _make_context(_create_flat_dataset(6), 6),
            horizon_months=12,
        )
        assert is_part49_buy_and_hold_eligible(ctx) is False


# ---------------------------------------------------------------------------
# Dispatch contract
# ---------------------------------------------------------------------------


def _bh_unit(
    cohort_date: date,
    horizon_months: int,
    dataset: Dataset,
    *,
    equity_weight: Decimal = EQUITY_ALLOCATION,
    withdrawal_rate: Decimal = WITHDRAWAL_RATE,
    loan_draw_rate: Decimal | None = LOAN_DRAW_RATE,
    rate: Decimal | None = INTEREST_RATE,
    schedule: _InterestRateSchedule = ...,
    ltv_limit: Decimal = LTV_LIMIT,
    ltv_enforcement: bool = False,
    debt_interest_rate_is_real: bool = True,
    expense_ratio: Decimal | None = None,
) -> PlannedSimulationUnit:
    if schedule is ...:
        schedule = (
            tuple(rate for _ in range(horizon_months)) if rate is not None else None
        )
    return PlannedSimulationUnit(
        cohort=CohortSpecification(start_date=cohort_date),
        parameter_config=ParameterConfiguration(values={"withdrawal_rate": 0.03}),
        allocation_policy=BuyAndHoldAllocationPolicy(equity_weight),
        withdrawal_policy=Part49WithdrawalPolicy(
            withdrawal_rate=withdrawal_rate, frequency=WithdrawalFrequency.MONTHLY
        ),
        initial_portfolio=Portfolio(
            holdings=(
                AssetHolding(asset_class=EQUITY_ASSET, units=Decimal("7500")),
                AssetHolding(asset_class=BOND_ASSET, units=Decimal("2500")),
            )
        ),
        dataset=dataset,
        horizon_months=horizon_months,
        interest_rate=rate,
        interest_rate_schedule=schedule,
        ltv_limit=ltv_limit,
        ltv_enforcement=ltv_enforcement,
        expense_ratio=expense_ratio,
        loan_draw_rate=loan_draw_rate,
        debt_interest_rate_is_real=debt_interest_rate_is_real,
    )


def _built_plan(
    units: tuple[PlannedSimulationUnit, ...], horizon_months: int = 12
) -> BuiltStudy:
    experiment = ExperimentDefinition(
        name="Part49 buy-and-hold dispatch contract",
        description="Part 49 buy-and-hold dispatch contract",
        dataset=units[0].dataset,
        horizon_months=horizon_months,
        initial_wealth=INITIAL_WEALTH,
        cohorts=tuple(unit.cohort for unit in units),
        allocation_policies=tuple(unit.allocation_policy for unit in units),
        withdrawal_policies=tuple(unit.withdrawal_policy for unit in units),
    )
    plan = ResearchPlan(experiment_definition=experiment, units=units)
    return BuiltStudy(
        plan=plan,
        experiment_definition=experiment,
        cohorts=tuple(unit.cohort for unit in units),
        param_configs=tuple(unit.parameter_config for unit in units),
    )


class TestPart49BuyAndHoldDispatchContract:
    def test_auto_routes_part49_buy_and_hold_to_numba(self) -> None:
        dataset = _create_flat_dataset(12)
        unit = _bh_unit(date(1965, 11, 1), 12, dataset)
        built = _built_plan((unit,))
        assert isinstance(
            _auto_select_backend(built, NoOpProfiler()), Part49BuyAndHoldNumbaExecutor
        )

    def test_fast_runs_part49_buy_and_hold_through_study_plan(self) -> None:
        dataset = _create_growth_dataset(12, Decimal("0.005"), Decimal("0.002"))
        unit = _bh_unit(date(1965, 11, 1), 12, dataset)
        built = _built_plan((unit,))

        fast = execute_study_plan(
            built,
            ExecutionOptions(
                backend=ExecutionBackend.FAST, strategy=ExecutionStrategy.SEQUENTIAL
            ),
        )
        stats = fast.experiment_result.simulation_results[0].statistics
        assert stats.success is True
        assert stats.months_simulated == 12

    def test_fast_rejects_unsupported_part49_buy_and_hold(self) -> None:
        dataset = _create_flat_dataset(12)
        unit = _bh_unit(
            date(1965, 11, 1), 12, dataset, expense_ratio=Decimal("0.005")
        )
        built = _built_plan((unit,))
        with pytest.raises(UnsupportedConfigurationError):
            execute_study_plan(
                built,
                ExecutionOptions(
                    backend=ExecutionBackend.FAST,
                    strategy=ExecutionStrategy.SEQUENTIAL,
                ),
            )

    def test_auto_unsupported_buy_and_hold_fails_explicitly(self) -> None:
        horizon = 120
        dataset = _create_trend_dataset(horizon)
        unit = _bh_unit(
            date(1965, 11, 1),
            horizon,
            dataset.slice(dataset[0].date, horizon),
            expense_ratio=Decimal("0.005"),
        )
        built = _built_plan((unit,), horizon_months=horizon)

        with pytest.raises(UnsupportedConfigurationError):
            execute_study_plan(
                built,
                ExecutionOptions(
                    backend=None, strategy=ExecutionStrategy.SEQUENTIAL
                ),
            )

    def test_auto_mixed_plan_fails_explicitly(self) -> None:
        dataset = _create_flat_dataset(12)
        bh_unit = _bh_unit(date(1965, 11, 1), 12, dataset)
        constant_unit = PlannedSimulationUnit(
            cohort=CohortSpecification(start_date=date(1966, 1, 1)),
            parameter_config=ParameterConfiguration(values={"withdrawal_rate": 0.04}),
            allocation_policy=ConstantAllocationPolicy(Decimal("0.6")),
            withdrawal_policy=FixedRealWithdrawalPolicy(
                withdrawal_rate=Decimal("0.04")
            ),
            initial_portfolio=Portfolio(
                holdings=(
                    AssetHolding(asset_class=EQUITY_ASSET, units=Decimal("6000")),
                    AssetHolding(asset_class=BOND_ASSET, units=Decimal("4000")),
                )
            ),
            dataset=dataset,
            horizon_months=12,
        )
        built = _built_plan((bh_unit, constant_unit))
        contexts = _extract_simulation_contexts(built.plan)
        assert not all(is_part49_buy_and_hold_eligible(ctx) for ctx in contexts)
        with pytest.raises(UnsupportedConfigurationError):
            _auto_select_backend(built, NoOpProfiler())


class TestPart49BuyAndHoldTimelineSpendingReporting:
    def test_timeline_reports_total_spending_without_changing_cash_flows(self) -> None:
        ctx = _make_context(_create_flat_dataset(12), 12)
        run = Part49BuyAndHoldNumbaExecutor(materialize_timeline=True).execute(
            EngineExperimentDefinition(
                name="timeline", description="timeline", simulation_contexts=(ctx,)
            )
        )
        result = run.simulation_results[0]
        assert result.timeline is not None
        month0 = result.timeline.monthly_results[0]
        assert month0.withdrawal_decision is not None

        annual = INITIAL_WEALTH.amount
        portfolio_withdrawal = Decimal(
            str(float(annual) * float(WITHDRAWAL_RATE) / 12.0)
        )
        loan_draw = Decimal(str(float(annual) * float(LOAN_DRAW_RATE) / 12.0))
        total_spending = Decimal(
            str(float(annual) * (float(WITHDRAWAL_RATE) + float(LOAN_DRAW_RATE)) / 12.0)
        )

        decision = month0.withdrawal_decision
        assert decision.nominal_amount.amount == total_spending
        assert decision.spending_budget == total_spending
        assert decision.loan_draw_amount == loan_draw

        portfolio_value = sum(
            (
                holding.units
                * month0.market_snapshot.index_levels[holding.asset_class]
                for holding in month0.portfolio.holdings
            ),
            Decimal("0"),
        )
        assert abs(portfolio_value - (annual - portfolio_withdrawal)) < Decimal("0.01")
        assert month0.debt_snapshot is not None
        assert month0.debt_snapshot.loan_balance == loan_draw

        baseline = Part49BuyAndHoldNumbaExecutor(materialize_timeline=False).execute(
            EngineExperimentDefinition(
                name="baseline", description="baseline", simulation_contexts=(ctx,)
            )
        )
        baseline_stats = baseline.simulation_results[0].statistics
        assert result.statistics.final_wealth == baseline_stats.final_wealth


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
