"""Part 49 Numba executor tests.

Covers eligibility, direct Numba execution (no silent fallback), differential
agreement with an independent Decimal debt recurrence, the
``debt_interest_rate_is_real`` CPI bypass, failure states, and the AUTO/FAST
dispatch contract.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from types import EllipsisType

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies import ConstantAllocationPolicy
from fbf.core.domain.policies.concrete import ConstantWithdrawalPolicy
from fbf.core.domain.policies.frequency import WithdrawalFrequency
from fbf.core.domain.policies.part49_withdrawal import Part49WithdrawalPolicy
from fbf.core.execution import (
    ExecutionBackend,
    ExecutionOptions,
    NoOpProfiler,
    UnsupportedConfigurationError,
    _auto_select_backend,
    _extract_simulation_contexts,
    execute_study_plan,
)
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    SimulationResult,
    SimulationStatistics,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.part49_numba_executor import (
    Part49NumbaExecutor,
    _compute_part49_monthly_rates,
    is_part49_context,
    is_part49_eligible,
)
from fbf.core.study.builder import BuiltStudy
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan
from tests.unit.execution.debt_recurrence_reference import (
    DebtReferenceResult,
    compute_monthly_rates,
    simulate_part49_reference,
)

EQUITY_ASSET = AssetClass(id="equity", name="", description="")
BOND_ASSET = AssetClass(id="bond", name="", description="")

INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)
WITHDRAWAL_RATE = Decimal("0.03")
LOAN_DRAW_RATE = Decimal("0.01")
INTEREST_RATE = Decimal("0.015")
LTV_LIMIT = Decimal("0.75")

_InterestRateSchedule = tuple[Decimal, ...] | None | EllipsisType

_WEALTH_TOLERANCE = Decimal("0.01")


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


def _create_growth_positive_dataset(horizon_months: int) -> Dataset:
    return _create_growth_dataset(horizon_months, Decimal("0.005"), Decimal("0.003"))


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
    interest_rate_schedule: _InterestRateSchedule = ...,
    *,
    loan_draw_rate: Decimal | None = LOAN_DRAW_RATE,
    debt_interest_rate_is_real: bool = False,
    withdrawal_rate: Decimal = WITHDRAWAL_RATE,
    ltv_enforcement: bool = False,
    expense_ratio: Decimal | None = None,
    final_value_target: Decimal | None = None,
    frequency: WithdrawalFrequency = WithdrawalFrequency.MONTHLY,
) -> SimulationContext:
    if interest_rate_schedule is ...:
        interest_rate_schedule = None
    return SimulationContext(
        experiment_name="test",
        cohort="1965-11",
        start_date=date(1965, 11, 1),
        horizon_months=horizon_months,
        initial_wealth=INITIAL_WEALTH,
        initial_portfolio=Portfolio(
            holdings=(
                AssetHolding(asset_class=EQUITY_ASSET, units=Decimal("7500")),
                AssetHolding(asset_class=BOND_ASSET, units=Decimal("2500")),
            )
        ),
        dataset=dataset,
        allocation_policy=ConstantAllocationPolicy(Decimal("0.75")),
        withdrawal_policy=Part49WithdrawalPolicy(
            withdrawal_rate=withdrawal_rate,
            frequency=frequency,
        ),
        interest_rate=INTEREST_RATE,
        interest_rate_schedule=interest_rate_schedule,
        ltv_limit=LTV_LIMIT,
        ltv_enforcement=ltv_enforcement,
        expense_ratio=expense_ratio,
        loan_draw_rate=loan_draw_rate,
        debt_interest_rate_is_real=debt_interest_rate_is_real,
        final_value_target=final_value_target,
    )


def _alone_statistics(ctx: SimulationContext) -> SimulationStatistics:
    run = Part49NumbaExecutor().execute(
        EngineExperimentDefinition(name="t", description="t", simulation_contexts=(ctx,))
    )
    return run.simulation_results[0].statistics


def _numba_result(ctx: SimulationContext) -> SimulationResult:
    run = Part49NumbaExecutor().execute(
        EngineExperimentDefinition(name="numba", description="numba", simulation_contexts=(ctx,))
    )
    return run.simulation_results[0]


def _independent_result(ctx: SimulationContext) -> DebtReferenceResult:
    """Run the independent Decimal Part 49 debt recurrence for *ctx*."""
    allocation = ctx.allocation_policy
    assert isinstance(allocation, ConstantAllocationPolicy)
    assert allocation.equity_allocation is not None
    withdrawal = ctx.withdrawal_policy
    assert isinstance(withdrawal, Part49WithdrawalPolicy)

    snapshot0 = ctx.dataset[0]
    initial_value = sum(
        (
            holding.units * snapshot0.index_levels[holding.asset_class]
            for holding in ctx.initial_portfolio.holdings
        ),
        Decimal("0"),
    )
    equity_prices = tuple(
        snapshot.index_levels[EQUITY_ASSET] for snapshot in ctx.dataset
    )
    bond_prices = tuple(snapshot.index_levels[BOND_ASSET] for snapshot in ctx.dataset)
    monthly_rates = compute_monthly_rates(
        tuple(snapshot.inflation_cumulative for snapshot in ctx.dataset),
        ctx.horizon_months,
        annual_rate_schedule=ctx.interest_rate_schedule,
        fixed_annual_rate=ctx.interest_rate,
        real_rate=ctx.debt_interest_rate_is_real,
    )
    return simulate_part49_reference(
        equity_prices,
        bond_prices,
        initial_value=initial_value,
        equity_weight=allocation.equity_allocation,
        withdrawal_rate=withdrawal.withdrawal_rate,
        loan_draw_rate=ctx.loan_draw_rate or Decimal("0"),
        monthly_rates=monthly_rates,
        ltv_limit=ctx.ltv_limit or Decimal("0.5"),
        ltv_enforcement=ctx.ltv_enforcement,
        horizon=ctx.horizon_months,
        final_value_target=ctx.final_value_target,
        initial_wealth=ctx.initial_wealth.amount,
    )


def _kernel_terminal_loan(ctx: SimulationContext, horizon: int) -> Decimal:
    """Terminal loan carried by the production Part 49 kernel inputs.

    Inputs are produced by the shared precompute helpers (the same ones the
    executor uses); the result is only ever compared against the independent
    Decimal reference.
    """
    import numpy as np

    from fbf.core.execution.strategies.eligibility import (
        _index_series,
        _weights_by_class,
    )
    from fbf.core.execution.strategies.numba_kernel import (
        _compute_growth_factors_numpy,
        _materialize_price_float,
        _simulate_part49,
    )

    weights = _weights_by_class(ctx)
    series = _index_series(ctx)
    asset_classes = tuple(series.keys())
    prices_f = _materialize_price_float(asset_classes, series)
    weights_f = np.array([float(weights[ac]) for ac in asset_classes], dtype=np.float64)
    gf = _compute_growth_factors_numpy(weights_f, prices_f, horizon, 0.0)

    initial_snapshot = ctx.dataset[0]
    v0 = float(
        sum(
            holding.units * initial_snapshot.index_levels[holding.asset_class]
            for holding in ctx.initial_portfolio.holdings
        )
    )
    withdrawal = ctx.withdrawal_policy
    assert isinstance(withdrawal, Part49WithdrawalPolicy)
    pw = v0 * float(withdrawal.withdrawal_rate) / 12.0
    ld = v0 * float(ctx.loan_draw_rate or Decimal("0")) / 12.0
    rates = np.array(
        [float(r) for r in _compute_part49_monthly_rates(ctx, horizon)], dtype=np.float64
    )
    final_loan = _simulate_part49(
        gf,
        rates,
        v0,
        pw,
        ld,
        float(ctx.ltv_limit) if ctx.ltv_limit else 0.5,
        horizon,
        ctx.ltv_enforcement,
    )[3]
    return Decimal(str(final_loan))


class TestPart49Eligibility:
    def test_eligible_context_returns_true(self) -> None:
        ctx = _make_context(_create_flat_dataset(12), 12)
        assert is_part49_context(ctx) is True
        assert is_part49_eligible(ctx) is True

    def test_zero_loan_draw_still_eligible(self) -> None:
        ctx = _make_context(_create_flat_dataset(12), 12, loan_draw_rate=Decimal("0"))
        assert is_part49_eligible(ctx) is True

    def test_none_loan_draw_still_eligible(self) -> None:
        ctx = _make_context(_create_flat_dataset(12), 12, loan_draw_rate=None)
        assert is_part49_eligible(ctx) is True

    def test_annual_frequency_ineligible(self) -> None:
        ctx = _make_context(
            _create_flat_dataset(12), 12, frequency=WithdrawalFrequency.ANNUAL
        )
        assert is_part49_eligible(ctx) is False

    def test_nonzero_expense_ratio_ineligible(self) -> None:
        ctx = _make_context(_create_flat_dataset(12), 12, expense_ratio=Decimal("0.005"))
        assert is_part49_eligible(ctx) is False

    def test_zero_expense_ratio_eligible(self) -> None:
        ctx = _make_context(_create_flat_dataset(12), 12, expense_ratio=Decimal("0"))
        assert is_part49_eligible(ctx) is True

    def test_no_rate_source_ineligible(self) -> None:
        ctx = replace(
            _make_context(_create_flat_dataset(12), 12),
            interest_rate=None,
            interest_rate_schedule=None,
        )
        assert is_part49_eligible(ctx) is False

    def test_explicit_allocations_ineligible(self) -> None:
        ctx = replace(
            _make_context(_create_flat_dataset(12), 12),
            allocation_policy=ConstantAllocationPolicy(
                allocations={"equity": Decimal("0.75"), "bond": Decimal("0.25")},
            ),
        )
        assert is_part49_eligible(ctx) is False

    def test_single_holding_ineligible(self) -> None:
        ctx = replace(
            _make_context(_create_flat_dataset(12), 12),
            initial_portfolio=Portfolio(
                holdings=(AssetHolding(asset_class=EQUITY_ASSET, units=Decimal("10000")),)
            ),
        )
        assert is_part49_eligible(ctx) is False

    def test_dataset_too_short_ineligible(self) -> None:
        ctx = _make_context(_create_flat_dataset(6), 12)
        assert is_part49_eligible(ctx) is False

    def test_non_part49_policy_not_context(self) -> None:
        ctx = replace(
            _make_context(_create_flat_dataset(12), 12),
            withdrawal_policy=ConstantWithdrawalPolicy(Decimal("0.04")),
        )
        assert is_part49_context(ctx) is False
        assert is_part49_eligible(ctx) is False

    def test_schedule_covering_horizon_eligible(self) -> None:
        ctx = _make_context(
            _create_flat_dataset(12), 12, interest_rate_schedule=tuple(
                Decimal("0.02") for _ in range(12)
            )
        )
        assert is_part49_eligible(ctx) is True


class TestPart49NumbaExecutorDirect:
    def test_does_not_invoke_reference_executor(self) -> None:
        dataset = _create_decline_dataset(24)
        ctx = _make_context(dataset, 24)
        executor = Part49NumbaExecutor()

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
        executor = Part49NumbaExecutor()
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
        ctx = _make_context(_create_flat_dataset(12), 12, expense_ratio=Decimal("0.005"))
        with pytest.raises(UnsupportedConfigurationError):
            Part49NumbaExecutor().execute(
                EngineExperimentDefinition(
                    name="t", description="t", simulation_contexts=(ctx,)
                )
            )


class TestPart49IndependentDebtReference:
    """Differential against the independent Decimal Part 49 debt recurrence.

    Coverage matrix (retired legacy differential case -> independent case):

    - flat growth -> ``test_flat_growth_matches_independent_reference``
    - constant growth, zero draw -> ``test_constant_growth_zero_loan_draw_matches``
    - constant growth, positive draw -> ``test_constant_growth_positive_loan_draw_matches``
    - varying returns -> ``test_varying_returns_match_independent_reference``
    - real-rate CPI bypass -> ``test_real_rate_bypasses_cpi_and_matches``
    - CPI-adjusted rate -> ``test_cpi_adjusted_rate_matches_independent_reference``
    - depletion -> ``test_depleted_matches_independent_reference``
    - terminal margin call -> ``test_margin_call_terminal_matches_independent_reference``
    - final-value target -> ``test_final_value_target_pass_and_fail``
    - enforcement off -> ``test_enforcement_off_matches_independent_reference``
    """

    @staticmethod
    def _assert_matches(
        ctx: SimulationContext, numba: SimulationResult
    ) -> DebtReferenceResult:
        reference = _independent_result(ctx)
        ns = numba.statistics
        assert ns.success is reference.success
        assert ns.failure_state == reference.failure_state
        assert ns.failure_month == reference.failure_month
        assert ns.months_simulated == reference.months_simulated
        diff = abs(ns.final_wealth.amount - reference.final_value)
        assert diff < _WEALTH_TOLERANCE, (
            f"final_wealth diff {diff} exceeds tolerance {_WEALTH_TOLERANCE}: "
            f"numba={ns.final_wealth.amount}, reference={reference.final_value}"
        )
        return reference

    @staticmethod
    def _assert_terminal_loan_matches(
        ctx: SimulationContext, reference: DebtReferenceResult
    ) -> None:
        kernel_loan = _kernel_terminal_loan(ctx, ctx.horizon_months)
        diff = abs(kernel_loan - reference.final_loan)
        assert diff < _WEALTH_TOLERANCE, (
            f"terminal loan diff {diff} exceeds tolerance {_WEALTH_TOLERANCE}: "
            f"numba={kernel_loan}, reference={reference.final_loan}"
        )

    def test_flat_market_without_leverage_is_hand_calculated(self) -> None:
        horizon = 24
        ctx = _make_context(
            _create_flat_dataset(horizon), horizon, loan_draw_rate=Decimal("0")
        )
        reference = _independent_result(ctx)
        expected = INITIAL_WEALTH.amount - horizon * (
            INITIAL_WEALTH.amount * WITHDRAWAL_RATE / Decimal("12")
        )
        assert reference.final_value == expected
        assert reference.final_loan == Decimal("0")
        self._assert_matches(ctx, _numba_result(ctx))

    def test_flat_growth_matches_independent_reference(self) -> None:
        ctx = _make_context(_create_flat_dataset(24), 24)
        self._assert_matches(ctx, _numba_result(ctx))

    def test_constant_growth_zero_loan_draw_matches(self) -> None:
        ctx = _make_context(
            _create_growth_positive_dataset(24), 24, loan_draw_rate=Decimal("0")
        )
        self._assert_matches(ctx, _numba_result(ctx))

    def test_constant_growth_positive_loan_draw_matches(self) -> None:
        horizon = 24
        ctx = _make_context(_create_growth_positive_dataset(horizon), horizon)
        reference = self._assert_matches(ctx, _numba_result(ctx))
        self._assert_terminal_loan_matches(ctx, reference)

    def test_varying_returns_match_independent_reference(self) -> None:
        horizon = 36
        ctx = _make_context(_create_varying_dataset(horizon), horizon)
        reference = self._assert_matches(ctx, _numba_result(ctx))
        self._assert_terminal_loan_matches(ctx, reference)

    def test_real_rate_bypasses_cpi_and_matches(self) -> None:
        horizon = 24
        dataset = _create_growth_dataset(
            horizon, Decimal("-0.04"), Decimal("0"), monthly_inflation=Decimal("0.005")
        )
        ctx = _make_context(dataset, horizon, debt_interest_rate_is_real=True)
        reference = self._assert_matches(ctx, _numba_result(ctx))
        self._assert_terminal_loan_matches(ctx, reference)

        cpi_reference = _independent_result(
            replace(ctx, debt_interest_rate_is_real=False)
        )
        assert reference.final_loan != cpi_reference.final_loan

    def test_cpi_adjusted_rate_matches_independent_reference(self) -> None:
        horizon = 24
        dataset = _create_growth_dataset(
            horizon, Decimal("-0.04"), Decimal("0"), monthly_inflation=Decimal("0.005")
        )
        ctx = _make_context(dataset, horizon, debt_interest_rate_is_real=False)
        reference = self._assert_matches(ctx, _numba_result(ctx))
        self._assert_terminal_loan_matches(ctx, reference)

    def test_depleted_matches_independent_reference(self) -> None:
        horizon = 24
        ctx = _make_context(
            _create_decline_dataset(horizon), horizon, withdrawal_rate=Decimal("0.6")
        )
        numba = _numba_result(ctx)
        reference = self._assert_matches(ctx, numba)
        assert reference.success is False
        assert reference.failure_state == "depleted"
        assert reference.failure_month is not None
        assert reference.final_value == Decimal("0")
        assert numba.statistics.final_wealth.amount == Decimal("0")

    def test_margin_call_terminal_matches_independent_reference(self) -> None:
        horizon = 60
        ctx = _make_context(_create_decline_dataset(horizon), horizon, ltv_enforcement=True)
        reference = self._assert_matches(ctx, _numba_result(ctx))
        assert reference.success is False
        assert reference.failure_state == "margin_call_terminal"
        assert reference.failure_month is not None
        assert reference.final_value > Decimal("0")

    def test_final_value_target_pass_and_fail(self) -> None:
        horizon = 24
        dataset = _create_growth_positive_dataset(horizon)

        passing = _make_context(dataset, horizon, final_value_target=Decimal("0.5"))
        passing_reference = self._assert_matches(passing, _numba_result(passing))
        assert passing_reference.success is True

        failing = _make_context(dataset, horizon, final_value_target=Decimal("10"))
        failing_reference = self._assert_matches(failing, _numba_result(failing))
        assert failing_reference.success is False
        assert failing_reference.failure_month is None
        assert failing_reference.failure_state is None

    def test_enforcement_off_matches_independent_reference(self) -> None:
        horizon = 60
        ctx = _make_context(_create_decline_dataset(horizon), horizon, ltv_enforcement=False)
        self._assert_matches(ctx, _numba_result(ctx))


def _make_dataset(months: int) -> Dataset:
    return _create_flat_dataset(months)


def _part49_unit(
    cohort_date: date,
    horizon_months: int | None,
    dataset: Dataset,
    *,
    schedule: _InterestRateSchedule = ...,
    rate: Decimal | None = INTEREST_RATE,
    frequency: WithdrawalFrequency = WithdrawalFrequency.MONTHLY,
    expense_ratio: Decimal | None = None,
) -> PlannedSimulationUnit:
    if schedule is ...:
        schedule = (
            tuple(INTEREST_RATE for _ in range(horizon_months)) if horizon_months else None
        )
    return PlannedSimulationUnit(
        cohort=CohortSpecification(start_date=cohort_date),
        parameter_config=ParameterConfiguration(values={"withdrawal_rate": 0.03}),
        allocation_policy=ConstantAllocationPolicy(Decimal("0.75")),
        withdrawal_policy=Part49WithdrawalPolicy(
            withdrawal_rate=WITHDRAWAL_RATE, frequency=frequency
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
        ltv_limit=LTV_LIMIT,
        ltv_enforcement=False,
        expense_ratio=expense_ratio,
        loan_draw_rate=LOAN_DRAW_RATE,
        debt_interest_rate_is_real=True,
    )


def _non_part49_unit(cohort_date: date, dataset: Dataset) -> PlannedSimulationUnit:
    return PlannedSimulationUnit(
        cohort=CohortSpecification(start_date=cohort_date),
        parameter_config=ParameterConfiguration(values={"withdrawal_rate": 0.04}),
        allocation_policy=ConstantAllocationPolicy(Decimal("0.60")),
        withdrawal_policy=ConstantWithdrawalPolicy(Decimal("0.04")),
        initial_portfolio=Portfolio(
            holdings=(AssetHolding(asset_class=EQUITY_ASSET, units=Decimal("10000")),)
        ),
        dataset=dataset,
        horizon_months=12,
    )


def _built_plan(
    units: tuple[PlannedSimulationUnit, ...], horizon_months: int = 12
) -> BuiltStudy:
    experiment = ExperimentDefinition(
        name="Part49 dispatch contract",
        description="Part 49 dispatch contract",
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


class TestPart49DispatchContract:
    def test_auto_routes_part49_to_numba(self) -> None:
        dataset = _make_dataset(12)
        unit = _part49_unit(date(1965, 11, 1), 12, dataset)
        built = _built_plan((unit,))
        assert isinstance(
            _auto_select_backend(built, NoOpProfiler()), Part49NumbaExecutor
        )

    def test_fast_runs_part49_through_study_plan(self) -> None:
        dataset = _create_growth_positive_dataset(12)
        unit = _part49_unit(date(1965, 11, 1), 12, dataset)
        built = _built_plan((unit,))

        fast = execute_study_plan(built, ExecutionOptions(backend=ExecutionBackend.FAST))
        stats = fast.experiment_result.simulation_results[0].statistics
        assert stats.success is True
        assert stats.months_simulated == 12

    def test_fast_rejects_annual_frequency(self) -> None:
        dataset = _make_dataset(12)
        unit = _part49_unit(
            date(1965, 11, 1),
            12,
            dataset,
            frequency=WithdrawalFrequency.ANNUAL,
        )
        built = _built_plan((unit,))
        with pytest.raises(UnsupportedConfigurationError):
            execute_study_plan(built, ExecutionOptions(backend=ExecutionBackend.FAST))

    def test_fast_rejects_nonzero_expense_ratio(self) -> None:
        dataset = _make_dataset(12)
        unit = _part49_unit(
            date(1965, 11, 1), 12, dataset, expense_ratio=Decimal("0.005")
        )
        built = _built_plan((unit,))
        with pytest.raises(UnsupportedConfigurationError):
            execute_study_plan(built, ExecutionOptions(backend=ExecutionBackend.FAST))

    def test_fast_rejects_no_rate_source(self) -> None:
        dataset = _make_dataset(12)
        unit = _part49_unit(
            date(1965, 11, 1), 12, dataset, schedule=None, rate=None
        )
        built = _built_plan((unit,))
        with pytest.raises(UnsupportedConfigurationError):
            execute_study_plan(built, ExecutionOptions(backend=ExecutionBackend.FAST))

    def test_fast_rejects_mixed_plan(self) -> None:
        dataset = _make_dataset(12)
        units = (
            _part49_unit(date(1965, 11, 1), 12, dataset),
            _non_part49_unit(date(1966, 1, 1), dataset),
        )
        built = _built_plan(units)
        with pytest.raises(UnsupportedConfigurationError):
            execute_study_plan(built, ExecutionOptions(backend=ExecutionBackend.FAST))

    def test_auto_mixed_plan_fails_explicitly(self) -> None:
        dataset = _make_dataset(12)
        units = (
            _part49_unit(date(1965, 11, 1), 12, dataset),
            _non_part49_unit(date(1966, 1, 1), dataset),
        )
        built = _built_plan(units)
        contexts = _extract_simulation_contexts(built.plan)
        assert not all(is_part49_eligible(ctx) for ctx in contexts)
        with pytest.raises(UnsupportedConfigurationError):
            _auto_select_backend(built, NoOpProfiler())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
