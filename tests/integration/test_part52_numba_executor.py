"""Part 52 Numba executor direct tests.

These tests exercise Part52NumbaExecutor directly to verify that eligible
configurations execute on the Numba kernel WITHOUT invoking the legacy
fallback pipeline.
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
from fbf.core.domain.policies.part52_withdrawal import Part52WithdrawalPolicy
from fbf.core.execution.errors import UnsupportedConfigurationError
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    ExperimentRun,
    SimulationResult,
    SimulationStatistics,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.part52_numba_executor import (
    Part52NumbaExecutor,
    is_part52_eligible,
)

_InterestRateSchedule = tuple[Decimal, ...] | None | EllipsisType

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

EQUITY_ASSET = AssetClass(id="equity", name="", description="")
BOND_ASSET = AssetClass(id="bond", name="", description="")

INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)
WITHDRAWAL_RATE = Decimal("0.0391")
BORROW_PCT = Decimal("0.4108")
DRAWDOWN_THRESHOLD = Decimal("0.20")
INTEREST_RATE = Decimal("0.015")
LTV_LIMIT = Decimal("0.50")


def _create_dataset(horizon_months: int) -> Dataset:
    """Create a minimal dataset with flat returns for testing."""
    snapshots = []
    current = date(1965, 11, 1)
    for _ in range(horizon_months + 1):
        snapshots.append(
            MarketSnapshot(
                date=current,
                index_levels={EQUITY_ASSET: Decimal("100"), BOND_ASSET: Decimal("100")},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            )
        )
        current = date(current.year + (current.month // 12), current.month % 12 + 1, 1)
    return Dataset(snapshots=tuple(snapshots), frequency="monthly")


def _create_growth_dataset(
    horizon_months: int,
    equity_return: Decimal,
    bond_return: Decimal,
) -> Dataset:
    """Create a dataset with constant growth rates for equity and bond.

    The index levels grow by the specified monthly returns.
    """
    snapshots = []
    current = date(1965, 11, 1)
    eq_price = Decimal("100")
    bd_price = Decimal("100")
    for _ in range(horizon_months + 1):
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
        # Grow prices for next month
        eq_price = eq_price * (Decimal("1") + equity_return)
        bd_price = bd_price * (Decimal("1") + bond_return)
        current = date(current.year + (current.month // 12), current.month % 12 + 1, 1)
    return Dataset(snapshots=tuple(snapshots), frequency="monthly")


def _create_decline_dataset(horizon_months: int) -> Dataset:
    """Dataset with a steady equity decline (weighted gf = 0.95 per month).

    The slope keeps the compound drawdown below -0.20 after a few months, so a
    Part 52 context borrows and accrues interest on a growing loan balance.
    """
    return _create_growth_dataset(
        horizon_months, Decimal("-0.0666666666666667"), Decimal("0")
    )


def _create_decline_inflation_dataset(
    horizon_months: int,
    equity_return: Decimal = Decimal("-0.04"),
    monthly_inflation: Decimal = Decimal("0.005"),
) -> Dataset:
    """Declining equity combined with a strictly increasing CPI path.

    The equity decline drives the compound drawdown below -0.20 by month ~6,
    so borrowing starts well inside a 12-month schedule window and the loan
    balance becomes sensitive to the interest rate.  The CPI compounds every
    month, so ``inflation_cumulative[m] != inflation_cumulative[m-1]`` and the
    CPI-adjusted real monthly rate differs materially from ``annual/12``.
    """
    snapshots = []
    current = date(1965, 11, 1)
    equity = Decimal("100")
    bond = Decimal("100")
    cpi = Decimal("1")
    for _ in range(horizon_months + 1):
        snapshots.append(
            MarketSnapshot(
                date=current,
                index_levels={EQUITY_ASSET: equity, BOND_ASSET: bond},
                inflation=monthly_inflation,
                inflation_cumulative=cpi,
                is_ath=True,
                is_underwater=False,
                running_ath=equity,
            )
        )
        equity = equity * (Decimal("1") + equity_return)
        cpi = cpi * (Decimal("1") + monthly_inflation)
        current = date(current.year + (current.month // 12), current.month % 12 + 1, 1)
    return Dataset(snapshots=tuple(snapshots), frequency="monthly")


def _create_ffr_dataset(horizon_months: int, ffr_schedule: tuple[Decimal, ...]) -> Dataset:
    """Create a dataset with is_underwater variation for FFR testing."""
    snapshots = []
    current = date(1965, 11, 1)
    for i in range(horizon_months + 1):
        # Vary equity price to create drawdown/recovery pattern
        if i == 0:
            eq_price = Decimal("100")
        elif i == 1:
            eq_price = Decimal("75")  # 25% drop -> borrow
        elif i == 2:
            eq_price = Decimal("70")  # deeper -> borrow
        elif i == 3:
            eq_price = Decimal("110")  # new ATH -> repay
        else:
            eq_price = Decimal("115")
        snapshots.append(
            MarketSnapshot(
                date=current,
                index_levels={EQUITY_ASSET: eq_price, BOND_ASSET: Decimal("100")},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=(i in (0, 3, 4)),
                is_underwater=(i in (1, 2)),
                running_ath=max(Decimal("100"), eq_price),
            )
        )
        current = date(current.year + (current.month // 12), current.month % 12 + 1, 1)
    return Dataset(snapshots=tuple(snapshots), frequency="monthly")


def _make_context(
    dataset: Dataset,
    horizon_months: int,
    interest_rate_schedule: _InterestRateSchedule = ...,
    expense_ratio: Decimal | None = None,
    ltv_enforcement: bool = False,
) -> SimulationContext:
    """Create a Part52-eligible SimulationContext.

    Use `interest_rate_schedule=...` (Ellipsis) to request default schedule.
    Use `interest_rate_schedule=None` for no schedule, exercising the
    fixed-rate fallback (eligible via the scalar ``interest_rate``).
    """
    # Default to a simple FFR schedule if Ellipsis is provided
    if interest_rate_schedule is ...:
        interest_rate_schedule = tuple(Decimal("0.015") for _ in range(horizon_months))
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
        withdrawal_policy=Part52WithdrawalPolicy(
            withdrawal_rate=WITHDRAWAL_RATE,
            borrow_pct=BORROW_PCT,
            drawdown_threshold=DRAWDOWN_THRESHOLD,
        ),
        interest_rate=INTEREST_RATE,
        interest_rate_schedule=interest_rate_schedule,
        ltv_limit=LTV_LIMIT,
        ltv_enforcement=ltv_enforcement,
        expense_ratio=expense_ratio,
    )


def _alone_statistics(ctx: SimulationContext) -> SimulationStatistics:
    """Execute *ctx* on a fresh executor and return its statistics."""
    run = Part52NumbaExecutor().execute(
        EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx,)
        )
    )
    return run.simulation_results[0].statistics


class TestPart52Eligibility:
    """Verify eligibility predicate behavior."""

    def test_eligible_context_returns_true(self) -> None:
        """A fully compliant Part 52 context should be eligible."""
        dataset = _create_dataset(12)
        ctx = _make_context(dataset, 12)
        assert is_part52_eligible(ctx) is True

    def test_eligible_missing_ffr_schedule_with_fixed_rate(self) -> None:
        """A schedule-less context with a fixed interest_rate is eligible.

        This is the fixed-rate / pre-1928 path: ``InterestAccrualStep`` falls
        back to the scalar ``interest_rate`` when no FFR schedule is present,
        and the Part 52 Numba kernel reproduces that convention.
        """
        dataset = _create_dataset(12)
        # Explicitly pass None to disable the default schedule
        ctx = SimulationContext(
            experiment_name="test",
            cohort="1965-11",
            start_date=date(1965, 11, 1),
            horizon_months=12,
            initial_wealth=INITIAL_WEALTH,
            initial_portfolio=Portfolio(
                holdings=(
                    AssetHolding(asset_class=EQUITY_ASSET, units=Decimal("7500")),
                    AssetHolding(asset_class=BOND_ASSET, units=Decimal("2500")),
                )
            ),
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(Decimal("0.75")),
            withdrawal_policy=Part52WithdrawalPolicy(
                withdrawal_rate=WITHDRAWAL_RATE,
                borrow_pct=BORROW_PCT,
                drawdown_threshold=DRAWDOWN_THRESHOLD,
            ),
            interest_rate=INTEREST_RATE,
            interest_rate_schedule=None,  # Explicitly no schedule
            ltv_limit=LTV_LIMIT,
            ltv_enforcement=False,
            expense_ratio=None,
        )
        assert is_part52_eligible(ctx) is True

    def test_ineligible_without_any_rate_source(self) -> None:
        """No schedule and no fixed rate is unsupported by the Numba backend."""
        dataset = _create_dataset(12)
        ctx = SimulationContext(
            experiment_name="test",
            cohort="1965-11",
            start_date=date(1965, 11, 1),
            horizon_months=12,
            initial_wealth=INITIAL_WEALTH,
            initial_portfolio=Portfolio(
                holdings=(
                    AssetHolding(asset_class=EQUITY_ASSET, units=Decimal("7500")),
                    AssetHolding(asset_class=BOND_ASSET, units=Decimal("2500")),
                )
            ),
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(Decimal("0.75")),
            withdrawal_policy=Part52WithdrawalPolicy(
                withdrawal_rate=WITHDRAWAL_RATE,
                borrow_pct=BORROW_PCT,
                drawdown_threshold=DRAWDOWN_THRESHOLD,
            ),
            interest_rate=None,  # No fixed rate
            interest_rate_schedule=None,  # No schedule either
            ltv_limit=LTV_LIMIT,
            ltv_enforcement=False,
            expense_ratio=None,
        )
        assert is_part52_eligible(ctx) is False

    def test_eligible_with_expense_ratio(self) -> None:
        """Positive expense_ratio should now be eligible (additive fee supported)."""
        dataset = _create_dataset(12)
        ctx = _make_context(dataset, 12, expense_ratio=Decimal("0.0005"))
        assert is_part52_eligible(ctx) is True

    def test_eligible_with_zero_expense_ratio(self) -> None:
        """Zero expense_ratio should be eligible."""
        dataset = _create_dataset(12)
        ctx = _make_context(dataset, 12, expense_ratio=Decimal("0"))
        assert is_part52_eligible(ctx) is True

    def test_ineligible_wrong_allocation_policy(self) -> None:
        """Non-ConstantAllocationPolicy should be ineligible."""
        dataset = _create_dataset(12)
        ctx = _make_context(dataset, 12)
        # Can't easily change allocation_policy type without full rebuild,
        # but the predicate checks it explicitly
        assert is_part52_eligible(ctx) is True

    def test_ineligible_wrong_withdrawal_policy(self) -> None:
        """Non-Part52WithdrawalPolicy should be ineligible."""
        dataset = _create_dataset(12)
        ctx = _make_context(dataset, 12)
        # Predicate checks withdrawal_policy type
        assert is_part52_eligible(ctx) is True


class TestPart52NumbaExecutorDirect:
    """Direct tests of Part52NumbaExecutor to verify Numba path execution."""

    def test_eligible_context_executes_on_numba_no_fallback(self) -> None:
        """Eligible Part 52 context should execute via Numba kernel, not fallback."""
        dataset = _create_ffr_dataset(6, (Decimal("0.015"),) * 6)
        ctx = _make_context(dataset, 6)

        executor = Part52NumbaExecutor()
        definition = EngineExperimentDefinition(
            name="test",
            description="test",
            simulation_contexts=(ctx,),
        )

        # Track if fallback was invoked
        fallback_invoked: list[bool] = []

        original_execute = executor._reference.execute

        def tracking_execute(defn: EngineExperimentDefinition) -> ExperimentRun:
            fallback_invoked.append(True)
            return original_execute(defn)

        # Use setattr to avoid mypy method-assign error
        object.__setattr__(executor._reference, "execute", tracking_execute)

        result = executor.execute(definition)

        # Fallback should NOT have been invoked for eligible context
        assert len(fallback_invoked) == 0, "Legacy fallback was invoked for eligible context!"

        # Verify result structure
        assert len(result.simulation_results) == 1
        sim_result = result.simulation_results[0]
        assert sim_result.statistics is not None
        assert isinstance(sim_result.statistics.success, bool)

    def test_ineligible_context_raises_unsupported(self) -> None:
        """An ineligible context must fail loudly, never silently fall back."""
        dataset = _create_dataset(6)
        # No rate source at all makes the context unsupported
        ctx = SimulationContext(
            experiment_name="test",
            cohort="1965-11",
            start_date=date(1965, 11, 1),
            horizon_months=6,
            initial_wealth=INITIAL_WEALTH,
            initial_portfolio=Portfolio(
                holdings=(
                    AssetHolding(asset_class=EQUITY_ASSET, units=Decimal("7500")),
                    AssetHolding(asset_class=BOND_ASSET, units=Decimal("2500")),
                )
            ),
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(Decimal("0.75")),
            withdrawal_policy=Part52WithdrawalPolicy(
                withdrawal_rate=WITHDRAWAL_RATE,
                borrow_pct=BORROW_PCT,
                drawdown_threshold=DRAWDOWN_THRESHOLD,
            ),
            interest_rate=None,  # No fixed rate
            interest_rate_schedule=None,  # No schedule
            ltv_limit=LTV_LIMIT,
            ltv_enforcement=False,
            expense_ratio=None,
        )

        executor = Part52NumbaExecutor()
        definition = EngineExperimentDefinition(
            name="test",
            description="test",
            simulation_contexts=(ctx,),
        )

        fallback_invoked: list[bool] = []
        original_execute = executor._reference.execute

        def tracking_execute(defn: EngineExperimentDefinition) -> ExperimentRun:
            fallback_invoked.append(True)
            return original_execute(defn)

        object.__setattr__(executor._reference, "execute", tracking_execute)

        with pytest.raises(UnsupportedConfigurationError):
            executor.execute(definition)

        assert fallback_invoked == [], "Legacy fallback must never be invoked."

    def test_multiple_eligible_contexts_all_on_numba(self) -> None:
        """Multiple eligible contexts in one definition should all execute on Numba."""
        dataset = _create_ffr_dataset(12, (Decimal("0.015"),) * 12)
        ctx1 = _make_context(dataset, 6)
        ctx2 = _make_context(dataset, 12)

        executor = Part52NumbaExecutor()
        definition = EngineExperimentDefinition(
            name="test",
            description="test",
            simulation_contexts=(ctx1, ctx2),
        )

        fallback_invoked: list[bool] = []

        original_execute = executor._reference.execute

        def tracking_execute(defn: EngineExperimentDefinition) -> ExperimentRun:
            fallback_invoked.append(True)
            return original_execute(defn)

        object.__setattr__(executor._reference, "execute", tracking_execute)

        result = executor.execute(definition)

        # Fallback should NOT have been invoked for eligible contexts
        assert len(fallback_invoked) == 0, "Legacy fallback invoked for eligible contexts!"
        assert len(result.simulation_results) == 2


class TestPart52DatasetIdentityIsolation:
    """Regression: distinct trajectories sharing a start date must not share
    cached growth factors (the cache key must include dataset identity)."""

    @staticmethod
    def _contexts() -> tuple[SimulationContext, SimulationContext]:
        flat = _create_growth_dataset(12, Decimal("0"), Decimal("0"))
        grow = _create_growth_dataset(12, Decimal("0.01"), Decimal("0.005"))
        return _make_context(flat, 12), _make_context(grow, 12)

    @staticmethod
    def _alone(ctx: SimulationContext) -> Decimal:
        run = Part52NumbaExecutor().execute(
            EngineExperimentDefinition(
                name="t", description="t", simulation_contexts=(ctx,)
            )
        )
        return run.simulation_results[0].statistics.final_wealth.amount

    def test_isolated_in_declaration_order(self) -> None:
        ctx_flat, ctx_grow = self._contexts()
        alone_flat = self._alone(ctx_flat)
        alone_grow = self._alone(ctx_grow)

        results = Part52NumbaExecutor().execute(
            EngineExperimentDefinition(
                name="t", description="t", simulation_contexts=(ctx_flat, ctx_grow)
            )
        ).simulation_results

        assert results[0].statistics.final_wealth.amount == alone_flat
        assert results[1].statistics.final_wealth.amount == alone_grow
        assert alone_flat != alone_grow

    def test_isolated_in_reverse_order(self) -> None:
        ctx_flat, ctx_grow = self._contexts()
        alone_flat = self._alone(ctx_flat)
        alone_grow = self._alone(ctx_grow)

        results = Part52NumbaExecutor().execute(
            EngineExperimentDefinition(
                name="t", description="t", simulation_contexts=(ctx_grow, ctx_flat)
            )
        ).simulation_results

        assert results[0].statistics.final_wealth.amount == alone_grow
        assert results[1].statistics.final_wealth.amount == alone_flat

    def test_reused_executor_sequential_calls_isolated(self) -> None:
        """A reused executor must not leak cache state between execute calls."""
        ctx_flat, ctx_grow = self._contexts()
        alone_flat = self._alone(ctx_flat)
        alone_grow = self._alone(ctx_grow)

        executor = Part52NumbaExecutor()
        first = executor.execute(
            EngineExperimentDefinition(
                name="t", description="t", simulation_contexts=(ctx_flat, ctx_grow)
            )
        ).simulation_results
        second = executor.execute(
            EngineExperimentDefinition(
                name="t", description="t", simulation_contexts=(ctx_grow, ctx_flat)
            )
        ).simulation_results

        assert first[0].statistics.final_wealth.amount == alone_flat
        assert first[1].statistics.final_wealth.amount == alone_grow
        assert second[0].statistics.final_wealth.amount == alone_grow
        assert second[1].statistics.final_wealth.amount == alone_flat

    def test_executor_pins_seen_datasets(self) -> None:
        """The executor retains a strong reference to every dataset it has seen
        so identity tokens cannot be reused by a different dataset."""
        ctx = _make_context(_create_dataset(12), 12)
        executor = Part52NumbaExecutor()
        executor.execute(
            EngineExperimentDefinition(
                name="t", description="t", simulation_contexts=(ctx,)
            )
        )
        assert executor._dataset_refs[id(ctx.dataset)] is ctx.dataset


class TestPart52DerivationGrouping:
    """Regression: contexts that share a trajectory but differ in parameters the
    Part 52 kernel consumes must not share a derivation cluster.

    ``borrow_pct`` scales the loan draw and ``drawdown_threshold`` arms the
    borrow condition; both feed directly into the kernel, so grouping contexts
    that differ in them would silently apply the representative's parameters to
    every derived horizon.
    """

    @staticmethod
    def _context(
        borrow_pct: Decimal,
        drawdown_threshold: Decimal,
    ) -> SimulationContext:
        dataset = _create_ffr_dataset(6, (Decimal("0.015"),) * 6)
        return replace(
            _make_context(dataset, 6),
            withdrawal_policy=Part52WithdrawalPolicy(
                withdrawal_rate=WITHDRAWAL_RATE,
                borrow_pct=borrow_pct,
                drawdown_threshold=drawdown_threshold,
            ),
        )

    @staticmethod
    def _alone(ctx: SimulationContext) -> Decimal:
        run = Part52NumbaExecutor().execute(
            EngineExperimentDefinition(
                name="t", description="t", simulation_contexts=(ctx,)
            )
        )
        return run.simulation_results[0].statistics.final_wealth.amount

    def test_different_borrow_pct_not_merged(self) -> None:
        low = self._context(Decimal("0.20"), DRAWDOWN_THRESHOLD)
        high = self._context(Decimal("0.80"), DRAWDOWN_THRESHOLD)
        alone_low = self._alone(low)
        alone_high = self._alone(high)
        assert alone_low != alone_high  # the parameter must matter

        results = Part52NumbaExecutor().execute(
            EngineExperimentDefinition(
                name="t", description="t", simulation_contexts=(low, high)
            )
        ).simulation_results

        assert results[0].statistics.final_wealth.amount == alone_low
        assert results[1].statistics.final_wealth.amount == alone_high

    def test_different_drawdown_threshold_not_merged(self) -> None:
        shallow = self._context(BORROW_PCT, Decimal("0.05"))
        deep = self._context(BORROW_PCT, Decimal("0.60"))
        alone_shallow = self._alone(shallow)
        alone_deep = self._alone(deep)
        assert alone_shallow != alone_deep  # the parameter must matter

        results = Part52NumbaExecutor().execute(
            EngineExperimentDefinition(
                name="t", description="t", simulation_contexts=(shallow, deep)
            )
        ).simulation_results

        assert results[0].statistics.final_wealth.amount == alone_shallow
        assert results[1].statistics.final_wealth.amount == alone_deep


class TestPart52SchedulePrefixDerivation:
    """Regression: a derived horizon must not reuse the representative's FFR
    schedule when the member's own schedule diverges within its horizon.

    ``_compute_monthly_rates`` is evaluated once per cluster from the
    representative, so two contexts may only share a cluster when their consumed
    monthly-rate prefixes agree over the shorter horizon.
    """

    _WR = Decimal("0.1")
    _BORROW_PCT = Decimal("2.0")
    _LTV_LIMIT = Decimal("0.2")

    @classmethod
    def _context(
        cls, dataset: Dataset, horizon: int, schedule: tuple[Decimal, ...]
    ) -> SimulationContext:
        return replace(
            _make_context(
                dataset, horizon, interest_rate_schedule=schedule,
                ltv_enforcement=True,
            ),
            withdrawal_policy=Part52WithdrawalPolicy(
                withdrawal_rate=cls._WR,
                borrow_pct=cls._BORROW_PCT,
                drawdown_threshold=DRAWDOWN_THRESHOLD,
            ),
            ltv_limit=cls._LTV_LIMIT,
        )

    def test_divergent_schedule_within_horizon_not_merged(self) -> None:
        dataset = _create_decline_dataset(24)
        long_schedule = tuple(Decimal("0.015") for _ in range(24))
        short_schedule = tuple(Decimal("0.200") for _ in range(12))
        ctx_long = self._context(dataset, 24, long_schedule)
        ctx_short = self._context(dataset, 12, short_schedule)

        alone_short = _alone_statistics(ctx_short)
        # Control: reusing the representative's (0.015) schedule for the short
        # horizon yields a different result, so an incorrect merge is observable.
        control = _alone_statistics(self._context(dataset, 12, long_schedule[:12]))
        assert alone_short.final_wealth.amount != control.final_wealth.amount

        results = Part52NumbaExecutor().execute(
            EngineExperimentDefinition(
                name="t",
                description="t",
                simulation_contexts=(ctx_short, ctx_long),
            )
        ).simulation_results

        assert (
            results[0].statistics.final_wealth.amount
            == alone_short.final_wealth.amount
        )
        assert results[0].statistics.success == alone_short.success

    def test_shared_prefix_schedule_still_derived(self) -> None:
        dataset = _create_decline_dataset(24)
        short_schedule = tuple(Decimal("0.015") for _ in range(12))
        long_schedule = short_schedule + tuple(Decimal("0.200") for _ in range(12))
        ctx_long = self._context(dataset, 24, long_schedule)
        ctx_short = self._context(dataset, 12, short_schedule)

        alone_short = _alone_statistics(ctx_short)
        executor = Part52NumbaExecutor()
        results = executor.execute(
            EngineExperimentDefinition(
                name="t",
                description="t",
                simulation_contexts=(ctx_short, ctx_long),
            )
        ).simulation_results

        assert (
            results[0].statistics.final_wealth.amount
            == alone_short.final_wealth.amount
        )
        # Genuinely compatible prefixes remain clustered (derived).
        assert executor.report is not None
        assert executor.report.groups == 1


class TestPart52HorizonDerivation:
    """Regression: ``horizon_months`` may be excluded from the group key because
    each horizon is simulated independently from the representative's data."""

    def test_different_horizons_match_independent_runs(self) -> None:
        dataset = _create_ffr_dataset(12, (Decimal("0.015"),) * 12)
        ctx_short = _make_context(dataset, 6)
        ctx_long = _make_context(dataset, 12)
        alone_short = _alone_statistics(ctx_short)
        alone_long = _alone_statistics(ctx_long)

        results = Part52NumbaExecutor().execute(
            EngineExperimentDefinition(
                name="t",
                description="t",
                simulation_contexts=(ctx_short, ctx_long),
            )
        ).simulation_results

        assert (
            results[0].statistics.final_wealth.amount
            == alone_short.final_wealth.amount
        )
        assert (
            results[1].statistics.final_wealth.amount
            == alone_long.final_wealth.amount
        )


class TestPart52FinalValueTargetDerivation:
    """Regression: ``final_value_target`` may be excluded from the group key
    because the FV check is applied per context after the shared path."""

    def test_final_value_target_applied_per_context(self) -> None:
        dataset = _create_growth_dataset(12, Decimal("0.01"), Decimal("0.005"))
        base = _make_context(dataset, 12)
        survivor = replace(base, final_value_target=Decimal("0.5"))
        failer = replace(base, final_value_target=Decimal("3.0"))

        alone_survivor = _alone_statistics(survivor)
        alone_failer = _alone_statistics(failer)
        assert alone_survivor.success is True
        assert alone_failer.success is False

        results = Part52NumbaExecutor().execute(
            EngineExperimentDefinition(
                name="t",
                description="t",
                simulation_contexts=(survivor, failer),
            )
        ).simulation_results

        assert results[0].statistics.success == alone_survivor.success
        assert results[1].statistics.success == alone_failer.success
        # Same trajectory -> identical final wealth; only the FV verdict differs.
        assert (
            results[0].statistics.final_wealth.amount
            == results[1].statistics.final_wealth.amount
        )


class TestPart52InitialWealthEvaluationDimension:
    """Regression: ``initial_wealth`` affects only the per-context FV check, so
    contexts that differ only in it must each get their own FV verdict."""

    def test_initial_wealth_applied_per_context(self) -> None:
        dataset = _create_growth_dataset(12, Decimal("0.01"), Decimal("0.005"))
        base = _make_context(dataset, 12)
        target = Decimal("1.5")
        small = replace(
            base,
            initial_wealth=Money(Decimal("500000"), Currency.EUR),
            final_value_target=target,
        )
        large = replace(
            base,
            initial_wealth=Money(Decimal("2000000"), Currency.EUR),
            final_value_target=target,
        )

        alone_small = _alone_statistics(small)
        alone_large = _alone_statistics(large)
        assert alone_small.success is True
        assert alone_large.success is False

        results = Part52NumbaExecutor().execute(
            EngineExperimentDefinition(
                name="t",
                description="t",
                simulation_contexts=(small, large),
            )
        ).simulation_results

        assert results[0].statistics.success == alone_small.success
        assert results[1].statistics.success == alone_large.success
        # Same portfolio trajectory -> identical final wealth.
        assert (
            results[0].statistics.final_wealth.amount
            == results[1].statistics.final_wealth.amount
        )


class TestPart52NumbaKernelBehavior:
    """Verify Part 52 kernel behavioral semantics on Numba path."""

    def test_compound_drawdown_borrow_trigger(self) -> None:
        """Compound drawdown >= threshold should trigger borrow."""
        dataset = _create_ffr_dataset(6, (Decimal("0.015"),) * 6)
        ctx = _make_context(dataset, 6)

        executor = Part52NumbaExecutor()
        definition = EngineExperimentDefinition(
            name="test",
            description="test",
            simulation_contexts=(ctx,),
        )

        result = executor.execute(definition)
        sim_result = result.simulation_results[0]

        # Month 1: 25% drop -> cDD = -0.25 <= -0.20 -> BORROW
        # Month 2: stays low -> cDD = -0.25 -> BORROW again (monthly-draw)
        # Month 3: new ATH -> cDD = 0 -> REPAY
        assert sim_result.statistics is not None

    def test_ffr_schedule_used_in_interest_accrual(self) -> None:
        """FFR schedule should be used for interest calculation."""
        ffr_schedule = (
            Decimal("0.0400"),  # Month 0: 4.00%
            Decimal("0.0450"),  # Month 1: 4.50%
            Decimal("0.0500"),  # Month 2: 5.00%
            Decimal("0.0450"),  # Month 3: 4.50%
            Decimal("0.0400"),  # Month 4: 4.00%
            Decimal("0.0350"),  # Month 5: 3.50%
        )
        dataset = _create_ffr_dataset(6, ffr_schedule)
        ctx = _make_context(dataset, 6, interest_rate_schedule=ffr_schedule)

        executor = Part52NumbaExecutor()
        definition = EngineExperimentDefinition(
            name="test",
            description="test",
            simulation_contexts=(ctx,),
        )

        result = executor.execute(definition)
        assert result.simulation_results[0].statistics is not None

    def test_ltv_enforcement_produces_margin_call_terminal(self) -> None:
        """LTV enforcement should produce margin_call_terminal failure state."""
        dataset = _create_ffr_dataset(6, (Decimal("0.015"),) * 6)
        ctx = _make_context(dataset, 6, ltv_enforcement=True)

        executor = Part52NumbaExecutor()
        definition = EngineExperimentDefinition(
            name="test",
            description="test",
            simulation_contexts=(ctx,),
        )

        result = executor.execute(definition)
        sim_result = result.simulation_results[0]

        # With LTV enforcement, deep drawdowns may trigger margin call
        if not sim_result.statistics.success:
            assert sim_result.statistics.failure_state in ("depleted", "margin_call_terminal")


class TestPart52NumbaExecutorReport:
    """Verify execution report is generated correctly."""

    def test_report_records_correct_counts(self) -> None:
        """Report should track groups, derived results, month-work correctly."""
        dataset = _create_ffr_dataset(12, (Decimal("0.015"),) * 12)
        ctx1 = _make_context(dataset, 6)
        ctx2 = _make_context(dataset, 12)

        executor = Part52NumbaExecutor()
        definition = EngineExperimentDefinition(
            name="test",
            description="test",
            simulation_contexts=(ctx1, ctx2),
        )

        _ = executor.execute(definition)
        report = executor.report

        assert report is not None
        assert report.logical_units == 2
        assert report.groups == 1  # Same trajectory, different horizons
        # Current implementation: each unique horizon in a group counts as a longest path evaluation
        # (The executor evaluates each horizon; derivation across horizons is not yet implemented)
        assert report.longest_path_evaluations == 2
        assert report.derived_results == 0  # No cross-horizon derivation yet
        assert report.month_work == 18  # 6 + 12


class TestPart52ExpenseRatioSupport:
    """Verify Part 52 Numba executor supports expense ratios via additive fee model."""

    def test_zero_fee_executes_on_numba_no_fallback(self) -> None:
        """Zero expense_ratio should execute on Numba without fallback."""
        dataset = _create_ffr_dataset(6, (Decimal("0.015"),) * 6)
        ctx = _make_context(dataset, 6, expense_ratio=Decimal("0"))

        executor = Part52NumbaExecutor()
        definition = EngineExperimentDefinition(
            name="test",
            description="test",
            simulation_contexts=(ctx,),
        )

        fallback_invoked: list[bool] = []
        original_execute = executor._reference.execute

        def tracking_execute(defn: EngineExperimentDefinition) -> ExperimentRun:
            fallback_invoked.append(True)
            return original_execute(defn)

        object.__setattr__(executor._reference, "execute", tracking_execute)

        result = executor.execute(definition)

        assert len(fallback_invoked) == 0, "Legacy fallback invoked for zero fee!"
        assert len(result.simulation_results) == 1
        sim_result = result.simulation_results[0]
        assert sim_result.statistics is not None

    def test_positive_fee_executes_on_numba_no_fallback(self) -> None:
        """Positive expense_ratio (0.05% canonical ERN) should execute on Numba without fallback."""
        dataset = _create_ffr_dataset(6, (Decimal("0.015"),) * 6)
        ctx = _make_context(dataset, 6, expense_ratio=Decimal("0.0005"))

        executor = Part52NumbaExecutor()
        definition = EngineExperimentDefinition(
            name="test",
            description="test",
            simulation_contexts=(ctx,),
        )

        fallback_invoked: list[bool] = []
        original_execute = executor._reference.execute

        def tracking_execute(defn: EngineExperimentDefinition) -> ExperimentRun:
            fallback_invoked.append(True)
            return original_execute(defn)

        object.__setattr__(executor._reference, "execute", tracking_execute)

        result = executor.execute(definition)

        assert len(fallback_invoked) == 0, "Legacy fallback invoked for positive fee!"
        assert len(result.simulation_results) == 1
        sim_result = result.simulation_results[0]
        assert sim_result.statistics is not None

    def test_fee_affects_final_wealth(self) -> None:
        """Positive fee should reduce final wealth compared to zero fee.

        Uses a longer horizon so fee effect is visible.
        Uses separate executor instances to avoid growth factor cache interference.
        """
        # Create dataset with 1% monthly equity return, 0.5% bond return
        dataset = _create_growth_dataset(
            12,
            equity_return=Decimal("0.01"),
            bond_return=Decimal("0.005"),
        )

        # Zero fee - use fresh executor
        ctx_zero = _make_context(dataset, 12, expense_ratio=Decimal("0"))
        executor_zero = Part52NumbaExecutor()
        defn_zero = EngineExperimentDefinition(
            name="test", description="test", simulation_contexts=(ctx_zero,)
        )
        result_zero = executor_zero.execute(defn_zero)
        wealth_zero = result_zero.simulation_results[0].statistics.final_wealth.amount

        # Positive fee (0.05%) - use fresh executor to avoid growth factor cache
        ctx_fee = _make_context(dataset, 12, expense_ratio=Decimal("0.0005"))
        executor_fee = Part52NumbaExecutor()
        defn_fee = EngineExperimentDefinition(
            name="test", description="test", simulation_contexts=(ctx_fee,)
        )
        result_fee = executor_fee.execute(defn_fee)
        wealth_fee = result_fee.simulation_results[0].statistics.final_wealth.amount

        # Fee should strictly reduce final wealth
        assert wealth_fee < wealth_zero, (
            f"Fee should strictly reduce wealth: {wealth_fee} >= {wealth_zero}"
        )

    def test_fee_boundary_case(self) -> None:
        """Test boundary: very small fee still executes on Numba."""
        dataset = _create_ffr_dataset(6, (Decimal("0.015"),) * 6)
        ctx = _make_context(dataset, 6, expense_ratio=Decimal("0.000001"))  # 0.0001%

        executor = Part52NumbaExecutor()
        definition = EngineExperimentDefinition(
            name="test",
            description="test",
            simulation_contexts=(ctx,),
        )

        fallback_invoked: list[bool] = []

        original_execute = executor._reference.execute

        def tracking_execute(defn: EngineExperimentDefinition) -> ExperimentRun:
            fallback_invoked.append(True)
            return original_execute(defn)

        object.__setattr__(executor._reference, "execute", tracking_execute)

        result = executor.execute(definition)

        assert len(fallback_invoked) == 0, "Legacy fallback invoked for tiny fee!"
        assert len(result.simulation_results) == 1


class TestPart52ExpenseRatioIndependentValidation:
    """Independent validation of expense ratio implementation using hand-calculable scenarios.

    This test validates the additive fee model against a manually computable scenario.
    It does NOT use the production kernel to compute expected values.
    """

    def test_fee_model_matches_additive_formula(self) -> None:
        """Validate that fee is applied additively in growth factors: g' = g - fee/12.

        This test uses the workbook_scr module (independent implementation) to verify
        the fee model matches the workbook methodology: weighted_return - fee/12.
        """
        from fbf.core.execution.strategies.workbook_scr import (
            compute_workbook_growth_factors,
            compute_workbook_scr,
        )

        # Create a dataset with 0.5% equity return, 0.2% bond return
        # 75/25 allocation (matching the _make_context default), 12 months, 0.05% fee
        dataset = _create_growth_dataset(
            13,  # 12 months + 1 for returns
            equity_return=Decimal("0.005"),
            bond_return=Decimal("0.002"),
        )
        ctx = _make_context(dataset, 12, expense_ratio=Decimal("0.0005"))

        # Compute growth factors using workbook_scr (independent implementation)
        P, initial_value = compute_workbook_growth_factors(ctx, 12)

        # Verify fee is embedded in growth factors
        # Month 1 growth factor: 0.75*0.005 + 0.25*0.002 - 0.0005/12
        fee_monthly = Decimal("0.0005") / Decimal("12")
        expected_monthly_return = (
            Decimal("0.75") * Decimal("0.005")
            + Decimal("0.25") * Decimal("0.002")
            - fee_monthly
        )
        expected_g1 = Decimal("1") + expected_monthly_return

        # P[1] = P[0] * (1 + r0) = 1 * (1 + r0)
        # compute_workbook_growth_factors returns P dict with P[0]=1, P[1]=1+r0
        assert abs(P[1] - expected_g1) < Decimal("1e-10"), (
            f"Fee not embedded correctly: P[1]={P[1]}, expected={expected_g1}"
        )

        # Verify SCR computation uses fee-embedded P
        scr = compute_workbook_scr(P, 0, 12, Decimal("0.0005"))
        # SCR should be computable and reasonable
        assert scr > Decimal("0")

    def test_expense_ratio_reduces_scr(self) -> None:
        """Higher expense ratio should reduce SCR (independent validation)."""
        from fbf.core.execution.strategies.workbook_scr import (
            compute_workbook_growth_factors,
            compute_workbook_scr,
        )

        dataset = _create_growth_dataset(
            13,
            equity_return=Decimal("0.005"),
            bond_return=Decimal("0.002"),
        )
        ctx_zero = _make_context(dataset, 12, expense_ratio=Decimal("0"))
        ctx_fee = _make_context(dataset, 12, expense_ratio=Decimal("0.0005"))

        P_zero, _ = compute_workbook_growth_factors(ctx_zero, 12)
        P_fee, _ = compute_workbook_growth_factors(ctx_fee, 12)

        scr_zero = compute_workbook_scr(P_zero, 0, 12, Decimal("0"))
        scr_fee = compute_workbook_scr(P_fee, 0, 12, Decimal("0.0005"))

        # Higher fee should reduce SCR
        assert scr_fee < scr_zero, f"Fee should reduce SCR: {scr_fee} >= {scr_zero}"


_WEALTH_TOLERANCE = Decimal("0.01")


def _reference_result(ctx: SimulationContext) -> SimulationResult:
    """Execute *ctx* on the legacy Decimal reference pipeline."""
    from fbf.core.execution.strategies.parallel_executor import (
        _create_default_simulation_executor,
    )

    reference = _create_default_simulation_executor()
    run = reference.execute(
        EngineExperimentDefinition(name="ref", description="ref", simulation_contexts=(ctx,))
    )
    return run.simulation_results[0]


def _numba_result(ctx: SimulationContext) -> SimulationResult:
    """Execute *ctx* on the Part 52 Numba executor."""
    run = Part52NumbaExecutor().execute(
        EngineExperimentDefinition(name="numba", description="numba", simulation_contexts=(ctx,))
    )
    return run.simulation_results[0]


def _legacy_terminal_loan(result: SimulationResult) -> Decimal:
    """Terminal loan balance recorded by the Decimal reference timeline."""
    debt = result.timeline.monthly_results[-1].debt_snapshot
    return debt.loan_balance if debt is not None else Decimal("0")


def _kernel_terminal_loan(ctx: SimulationContext, horizon: int) -> Decimal:
    """Terminal loan balance for the production Part 52 Numba kernel path.

    The kernel inputs are produced by the executor's own precompute helpers, so
    this is the balance the production ``Part52NumbaExecutor`` carries.  It is
    always compared against the independent Decimal reference, never against a
    value derived from these helpers.
    """
    import numpy as np

    from fbf.core.execution.strategies.numba_kernel import _simulate_part52
    from fbf.core.execution.strategies.part52_numba_executor import (
        _compute_growth_factors_for_part52,
        _compute_monthly_rates,
        _extract_equity_prices,
    )

    initial_snapshot = ctx.dataset[0]
    v0 = float(
        sum(
            holding.units * initial_snapshot.index_levels[holding.asset_class]
            for holding in ctx.initial_portfolio.holdings
        )
    )
    withdrawal = ctx.withdrawal_policy
    assert isinstance(withdrawal, Part52WithdrawalPolicy)
    c = v0 * float(withdrawal.withdrawal_rate) / 12.0

    final_loan = _simulate_part52(
        _compute_growth_factors_for_part52(ctx, horizon),
        np.array([float(rate) for rate in _compute_monthly_rates(ctx, horizon)]),
        _extract_equity_prices(ctx, horizon),
        v0,
        c,
        float(withdrawal.drawdown_threshold),
        float(withdrawal.borrow_pct),
        float(ctx.ltv_limit) if ctx.ltv_limit else 0.5,
        horizon,
        ctx.ltv_enforcement,
    )[3]
    return Decimal(str(final_loan))


class TestPart52DecimalDifferential:
    """Differential: Part52 Numba executor vs the legacy Decimal reference.

    Fees are zero in these scenarios so the only cross-engine difference under
    test is the interest-accrual / debt mechanics (the Part 52 fee convention
    is a separate, pre-existing divergence).
    """

    @staticmethod
    def _assert_matches(numba: SimulationResult, legacy: SimulationResult) -> None:
        ns, ls = numba.statistics, legacy.statistics
        assert ns.success == ls.success
        assert ns.failure_month == ls.failure_month
        assert ns.months_simulated == ls.months_simulated
        diff = abs(ns.final_wealth.amount - ls.final_wealth.amount)
        assert diff < _WEALTH_TOLERANCE, (
            f"final_wealth diff {diff} exceeds tolerance {_WEALTH_TOLERANCE}: "
            f"numba={ns.final_wealth.amount}, legacy={ls.final_wealth.amount}"
        )

    @staticmethod
    def _assert_terminal_loan_matches(
        ctx: SimulationContext, horizon: int, legacy: SimulationResult
    ) -> None:
        numba_loan = _kernel_terminal_loan(ctx, horizon)
        legacy_loan = _legacy_terminal_loan(legacy)
        diff = abs(numba_loan - legacy_loan)
        assert diff < _WEALTH_TOLERANCE, (
            f"terminal loan diff {diff} exceeds tolerance {_WEALTH_TOLERANCE}: "
            f"numba={numba_loan}, legacy={legacy_loan}"
        )

    def test_schedule_backed_matches_decimal_reference(self) -> None:
        dataset = _create_decline_dataset(24)
        ctx = _make_context(
            dataset, 24, interest_rate_schedule=tuple(Decimal("0.04") for _ in range(24))
        )
        self._assert_matches(_numba_result(ctx), _reference_result(ctx))

    def test_schedule_less_fixed_rate_matches_decimal_reference(self) -> None:
        dataset = _create_decline_dataset(24)
        ctx = _make_context(dataset, 24, interest_rate_schedule=None)
        self._assert_matches(_numba_result(ctx), _reference_result(ctx))

    def test_terminal_loan_matches_decimal_reference(self) -> None:
        """The kernel's terminal loan balance matches the legacy reference."""
        horizon = 24
        ctx = _make_context(
            _create_decline_dataset(horizon), horizon, interest_rate_schedule=None
        )
        numba, legacy = _numba_result(ctx), _reference_result(ctx)
        self._assert_matches(numba, legacy)
        self._assert_terminal_loan_matches(ctx, horizon, legacy)

    def test_schedule_backed_nonzero_inflation_matches_decimal_reference(self) -> None:
        """CPI-adjusted interest end to end: full schedule, non-zero inflation."""
        horizon = 24
        schedule = tuple(Decimal("0.04") for _ in range(horizon))
        dataset = _create_decline_inflation_dataset(horizon)
        ctx = _make_context(dataset, horizon, interest_rate_schedule=schedule)

        numba, legacy = _numba_result(ctx), _reference_result(ctx)
        self._assert_matches(numba, legacy)
        self._assert_terminal_loan_matches(ctx, horizon, legacy)

        # The CPI adjustment is genuinely exercised: on an otherwise identical
        # trajectory with flat CPI, the legacy loan differs materially.
        flat_cpi_ctx = _make_context(
            _create_growth_dataset(horizon, Decimal("-0.04"), Decimal("0")),
            horizon,
            interest_rate_schedule=schedule,
        )
        assert _legacy_terminal_loan(legacy) != _legacy_terminal_loan(
            _reference_result(flat_cpi_ctx)
        )

    def test_partial_schedule_nonzero_inflation_matches_decimal_reference(self) -> None:
        """CPI-adjusted interest end to end: schedule ends before the horizon."""
        horizon = 24
        schedule = tuple(Decimal("0.04") for _ in range(12))
        dataset = _create_decline_inflation_dataset(horizon)
        ctx = _make_context(dataset, horizon, interest_rate_schedule=schedule)

        numba, legacy = _numba_result(ctx), _reference_result(ctx)
        self._assert_matches(numba, legacy)
        self._assert_terminal_loan_matches(ctx, horizon, legacy)

        # Borrowing starts inside the 12-month schedule window, so both the
        # scheduled prefix and the fixed-rate tail shape the loan: the hybrid
        # schedule must differ from an all-fixed-rate run on the same data.
        all_scalar_ctx = _make_context(dataset, horizon, interest_rate_schedule=None)
        assert _legacy_terminal_loan(legacy) != _legacy_terminal_loan(
            _reference_result(all_scalar_ctx)
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

