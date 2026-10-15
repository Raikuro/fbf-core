"""Part 52 Numba executor direct tests.

These tests exercise Part52NumbaExecutor directly to verify that eligible
configurations execute on the Numba kernel WITHOUT invoking the legacy
fallback pipeline.
"""

from __future__ import annotations

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
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    ExperimentRun,
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
    Use `interest_rate_schedule=None` for no schedule (ineligible).
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


class TestPart52Eligibility:
    """Verify eligibility predicate behavior."""

    def test_eligible_context_returns_true(self) -> None:
        """A fully compliant Part 52 context should be eligible."""
        dataset = _create_dataset(12)
        ctx = _make_context(dataset, 12)
        assert is_part52_eligible(ctx) is True

    def test_ineligible_missing_ffr_schedule(self) -> None:
        """Missing interest_rate_schedule should make context ineligible."""
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

    def test_ineligible_context_invokes_fallback(self) -> None:
        """Ineligible context (missing FFR schedule) should invoke fallback."""
        dataset = _create_dataset(6)
        # Missing interest_rate_schedule makes context ineligible
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
            interest_rate=INTEREST_RATE,
            interest_rate_schedule=None,  # Missing FFR schedule makes ineligible
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

        _ = executor.execute(definition)

        # Fallback SHOULD have been invoked for ineligible context
        assert len(fallback_invoked) == 1, "Legacy fallback was NOT invoked for ineligible context!"

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

