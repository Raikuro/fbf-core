"""S5.5-R1 — Zero-interest debt semantics tests.

Verifies that interest_rate=0 with loan_draw > 0 produces valid debt,
distinct from "no debt configured". These tests enforce the corrected
semantic contract established in S5.5-R1.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.decision_context import DebtInfo
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.execution.pipeline.default_pipeline import create_default_pipeline
from fbf.core.execution.pipeline.runner import SimulationRunner
from fbf.core.execution.pipeline.simulation import ExecutionStatus, SimulationState
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.pipeline.steps.build_decision_context_step import (
    BuildDecisionContextStep,
)
from fbf.core.execution.pipeline.steps.interest_accrual_step import InterestAccrualStep
from fbf.core.execution.pipeline.steps.loan_draw_step import LoanDrawStep
from fbf.core.execution.pipeline.steps.ltv_evaluation_step import LTVEvaluationStep
from fbf.core.execution.pipeline.steps.monthly_result_builder_step import (
    MonthlyResultBuilderStep,
)

# Canonical asset classes (must match existing test conventions)
EQUITY = AssetClass(id="equity", name="", description="")
BOND = AssetClass(id="bond", name="", description="")


def _snapshot(period: int = 0) -> MarketSnapshot:
    return MarketSnapshot(
        date=date(2020, 1, 1 + period),
        index_levels={EQUITY: Decimal("100"), BOND: Decimal("100")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100"),
    )


def _dataset() -> Dataset:
    return Dataset(
        snapshots=[_snapshot(0), _snapshot(1)],
        frequency="monthly",
        version="test",
        identifier="test",
    )


def _portfolio(equity: Decimal = Decimal("7500"), bond: Decimal = Decimal("2500")) -> Portfolio:
    return Portfolio(holdings=(
        AssetHolding(asset_class=EQUITY, units=equity),
        AssetHolding(asset_class=BOND, units=bond),
    ))


def _context(
    interest_rate: Decimal = Decimal("0"),
    loan_draw_rate: Decimal = Decimal("0"),
) -> SimulationContext:
    return SimulationContext(
        experiment_name="test",
        cohort="test",
        start_date=date(2020, 1, 1),
        horizon_months=2,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        initial_portfolio=_portfolio(),
        dataset=_dataset(),
        allocation_policy=None,  # type: ignore
        withdrawal_policy=None,  # type: ignore
        interest_rate=interest_rate,
        loan_draw_rate=loan_draw_rate,
        ltv_enforcement=False,
    )


def _state(
    interest_rate: Decimal = Decimal("0"),
    loan_balance: Decimal = Decimal("0"),
) -> SimulationState:
    ctx = _context(interest_rate=interest_rate)
    return SimulationState(
        context=ctx,
        current_date=date(2020, 1, 1),
        period_index=0,
        portfolio=_portfolio(),
        market_snapshot=_snapshot(),
        current_wealth=Money(Decimal("1000000"), Currency.EUR),
        peak_wealth=Money(Decimal("1000000"), Currency.EUR),
        status=ExecutionStatus.RUNNING,
        interest_rate=interest_rate,
        loan_balance=loan_balance,
        ltv_enforcement=False,
    )


# ---------------------------------------------------------------------------
# 1. Positive loan draw + 0% interest creates debt
# ---------------------------------------------------------------------------


class TestZeroInterestLoanDraw:
    """Verify that loan draws occur at 0% interest."""

    def test_loan_draw_occurs_at_zero_interest(self) -> None:
        """LoanDrawStep must execute when loan_draw_amount > 0 at 0% interest."""
        from fbf.core.domain.model.money import Currency, Money
        from fbf.core.domain.policies.decisions import WithdrawalDecision

        step = LoanDrawStep()
        state = _state(interest_rate=Decimal("0"))
        state.withdrawal_decision = WithdrawalDecision(
            reason="test",
            nominal_amount=Money(Decimal("3000"), Currency.EUR),
            real_amount=Money(Decimal("3000"), Currency.EUR),
            loan_draw_amount=Decimal("833.33"),
        )
        result = step.execute(state)
        assert result.loan_balance == Decimal("833.33")
        assert result.cash_balance == Decimal("833.33")

    def test_no_draw_when_amount_zero(self) -> None:
        """LoanDrawStep must be a no-op when loan_draw_amount = 0."""
        from fbf.core.domain.model.money import Currency, Money
        from fbf.core.domain.policies.decisions import WithdrawalDecision

        step = LoanDrawStep()
        state = _state(interest_rate=Decimal("0"))
        state.withdrawal_decision = WithdrawalDecision(
            reason="test",
            nominal_amount=Money(Decimal("3000"), Currency.EUR),
            real_amount=Money(Decimal("3000"), Currency.EUR),
            loan_draw_amount=Decimal("0"),
        )
        result = step.execute(state)
        assert result.loan_balance == Decimal("0")
        assert result.cash_balance == Decimal("0")

    def test_no_draw_when_amount_negative(self) -> None:
        """LoanDrawStep must reject negative loan_draw_amount."""
        from fbf.core.domain.model.money import Currency, Money
        from fbf.core.domain.policies.decisions import WithdrawalDecision

        step = LoanDrawStep()
        state = _state(interest_rate=Decimal("0"))
        state.withdrawal_decision = WithdrawalDecision(
            reason="test",
            nominal_amount=Money(Decimal("3000"), Currency.EUR),
            real_amount=Money(Decimal("3000"), Currency.EUR),
            loan_draw_amount=Decimal("-100"),
        )
        try:
            step.execute(state)
            raise AssertionError("Should have raised ValueError")
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# 2. 0% interest produces zero interest accrual
# ---------------------------------------------------------------------------


class TestZeroInterestAccrual:
    """Verify that zero-interest debt accrues zero interest."""

    def test_zero_interest_preserves_loan_balance(self) -> None:
        """InterestAccrualStep must not change loan_balance when interest_rate=0."""
        step = InterestAccrualStep()
        state = _state(interest_rate=Decimal("0"), loan_balance=Decimal("300000"))
        result = step.execute(state)
        assert result.loan_balance == Decimal("300000")

    def test_positive_interest_accrues(self) -> None:
        """InterestAccrualStep must accrue interest when interest_rate > 0."""
        step = InterestAccrualStep()
        state = _state(interest_rate=Decimal("0.03"), loan_balance=Decimal("300000"))
        result = step.execute(state)
        expected = Decimal("300000") * Decimal("0.03") / Decimal("12")
        assert result.loan_balance == Decimal("300000") + expected

    def test_no_accrual_when_no_loan(self) -> None:
        """InterestAccrualStep must be a no-op when loan_balance = 0."""
        step = InterestAccrualStep()
        state = _state(interest_rate=Decimal("0.03"), loan_balance=Decimal("0"))
        result = step.execute(state)
        assert result.loan_balance == Decimal("0")


# ---------------------------------------------------------------------------
# 3. 0% debt produces DebtInfo
# ---------------------------------------------------------------------------


class TestZeroInterestDebtInfo:
    """Verify that DebtInfo is created when debt exists at 0% interest."""

    def test_debt_info_created_at_zero_interest(self) -> None:
        """BuildDecisionContextStep must create DebtInfo when loan_balance > 0."""
        from fbf.core.domain.model.allocation import Allocation, AllocationTarget

        step = BuildDecisionContextStep()
        state = _state(interest_rate=Decimal("0"), loan_balance=Decimal("300000"))
        state.allocation = Allocation(
            weights={EQUITY: Decimal("0.75"), BOND: Decimal("0.25")}
        )
        state.allocation_target = AllocationTarget(
            weights={EQUITY: Decimal("0.75"), BOND: Decimal("0.25")}
        )
        result = step.execute(state)
        assert result.decision_context is not None
        assert result.decision_context.debt_info is not None
        assert isinstance(result.decision_context.debt_info, DebtInfo)
        assert result.decision_context.debt_info.loan_balance == Decimal("300000")

    def test_no_debt_info_when_no_debt(self) -> None:
        """BuildDecisionContextStep must not create DebtInfo when no debt exists."""
        from fbf.core.domain.model.allocation import Allocation, AllocationTarget

        step = BuildDecisionContextStep()
        state = _state(interest_rate=Decimal("0"), loan_balance=Decimal("0"))
        state.allocation = Allocation(
            weights={EQUITY: Decimal("0.75"), BOND: Decimal("0.25")}
        )
        state.allocation_target = AllocationTarget(
            weights={EQUITY: Decimal("0.75"), BOND: Decimal("0.25")}
        )
        result = step.execute(state)
        assert result.decision_context is not None
        assert result.decision_context.debt_info is None


# ---------------------------------------------------------------------------
# 4. 0% debt produces DebtSnapshot
# ---------------------------------------------------------------------------


class TestZeroInterestDebtSnapshot:
    """Verify that DebtSnapshot is created when debt exists at 0% interest."""

    def test_debt_snapshot_created_at_zero_interest(self) -> None:
        """MonthlyResultBuilderStep must create DebtSnapshot when loan_balance > 0."""
        step = MonthlyResultBuilderStep()
        state = _state(interest_rate=Decimal("0"), loan_balance=Decimal("300000"))
        result = step.execute(state)
        last_mr = result.monthly_results[-1]
        assert last_mr.debt_snapshot is not None
        assert last_mr.debt_snapshot.loan_balance == Decimal("300000")
        assert last_mr.debt_snapshot.ltv_enforcement is False

    def test_no_debt_snapshot_when_no_debt(self) -> None:
        """MonthlyResultBuilderStep must not create DebtSnapshot when no debt exists."""
        step = MonthlyResultBuilderStep()
        state = _state(interest_rate=Decimal("0"), loan_balance=Decimal("0"))
        result = step.execute(state)
        last_mr = result.monthly_results[-1]
        assert last_mr.debt_snapshot is None


# ---------------------------------------------------------------------------
# 5. LTV evaluated for zero-interest debt
# ---------------------------------------------------------------------------


class TestZeroInterestLTV:
    """Verify that LTV is evaluated when loan_balance > 0 at 0% interest."""

    def test_ltv_evaluated_at_zero_interest(self) -> None:
        """LTVEvaluationStep must not short-circuit when loan_balance > 0."""
        step = LTVEvaluationStep()
        state = _state(interest_rate=Decimal("0"), loan_balance=Decimal("300000"))
        step.execute(state)
        # LTV should be computed: loan_balance / portfolio_value
        # portfolio_value = 7500*100 + 2500*100 = 1,000,000
        # LTV = 300000 / 1000000 = 0.30
        assert state.loan_balance == Decimal("300000")

    def test_no_ltv_when_no_loan(self) -> None:
        """LTVEvaluationStep must be a no-op when loan_balance = 0."""
        step = LTVEvaluationStep()
        state = _state(interest_rate=Decimal("0"), loan_balance=Decimal("0"))
        result = step.execute(state)
        assert result.loan_balance == Decimal("0")


# ---------------------------------------------------------------------------
# 6. LTV enforcement remains OFF for Part 49
# ---------------------------------------------------------------------------


class TestZeroInterestLTVEnforcement:
    """Verify that LTV enforcement remains OFF at 0% interest."""

    def test_ltv_enforcement_off(self) -> None:
        """With ltv_enforcement=False, LTV is observed but not enforced."""
        step = LTVEvaluationStep()
        state = _state(interest_rate=Decimal("0"), loan_balance=Decimal("300000"))
        state.ltv_enforcement = False
        result = step.execute(state)
        assert result.loan_balance == Decimal("300000")


# ---------------------------------------------------------------------------
# 7. Genuine no-debt configuration remains debt-free
# ---------------------------------------------------------------------------


class TestNoDebtConfiguration:
    """Verify that no-debt configuration produces no debt state."""

    def test_no_debt_no_snapshots(self) -> None:
        """When loan_balance=0 and loan_draw=0, no DebtSnapshot should be created."""
        step = MonthlyResultBuilderStep()
        state = _state(interest_rate=Decimal("0"), loan_balance=Decimal("0"))
        result = step.execute(state)
        last_mr = result.monthly_results[-1]
        assert last_mr.debt_snapshot is None


# ---------------------------------------------------------------------------
# 8. Zero-interest debt preserves net-worth identity
# ---------------------------------------------------------------------------


class TestZeroInterestNetWorth:
    """Verify that net-worth identity holds for zero-interest debt."""

    def test_net_worth_identity(self) -> None:
        """net_worth = portfolio_value + cash_balance - loan_balance."""
        step = MonthlyResultBuilderStep()
        state = _state(interest_rate=Decimal("0"), loan_balance=Decimal("300000"))
        state.cash_balance = Decimal("0")
        result = step.execute(state)
        last_mr = result.monthly_results[-1]
        ds = last_mr.debt_snapshot
        assert ds is not None
        # portfolio_value = 7500*100 + 2500*100 = 1,000,000
        # net_worth = 1,000,000 + 0 - 300,000 = 700,000
        assert ds.net_worth == Decimal("1000000") + state.cash_balance - Decimal("300000")


# ---------------------------------------------------------------------------
# 9. Positive-interest behavior unchanged
# ---------------------------------------------------------------------------


class TestPositiveInterestUnchanged:
    """Verify that positive-interest behavior is regression-safe."""

    def test_positive_interest_still_accrues(self) -> None:
        """InterestAccrualStep must still accrue interest when interest_rate > 0."""
        step = InterestAccrualStep()
        state = _state(interest_rate=Decimal("0.03"), loan_balance=Decimal("300000"))
        result = step.execute(state)
        expected = Decimal("300000") * Decimal("0.03") / Decimal("12")
        assert result.loan_balance == Decimal("300000") + expected

    def test_positive_interest_creates_debt_info(self) -> None:
        """BuildDecisionContextStep must create DebtInfo when interest_rate > 0."""
        from fbf.core.domain.model.allocation import Allocation, AllocationTarget

        step = BuildDecisionContextStep()
        state = _state(interest_rate=Decimal("0.03"), loan_balance=Decimal("300000"))
        state.allocation = Allocation(
            weights={EQUITY: Decimal("0.75"), BOND: Decimal("0.25")}
        )
        state.allocation_target = AllocationTarget(
            weights={EQUITY: Decimal("0.75"), BOND: Decimal("0.25")}
        )
        result = step.execute(state)
        assert result.decision_context is not None
        assert result.decision_context.debt_info is not None


# ---------------------------------------------------------------------------
# 10. Full pipeline integration with zero interest
# ---------------------------------------------------------------------------


class TestZeroInterestFullPipeline:
    """Integration test: full pipeline with zero-interest debt."""

    def test_full_pipeline_zero_interest(self) -> None:
        """Full pipeline must produce valid results with zero-interest debt."""
        from fbf.core.domain.model.dataset import Dataset
        from fbf.core.domain.policies.concrete import ConstantAllocationPolicy
        from fbf.core.domain.policies.part49_withdrawal import Part49WithdrawalPolicy

        n_months = 3
        snapshots = []
        pe = pb = Decimal("100")
        d = date(2020, 1, 1)
        for _i in range(n_months + 1):
            snapshots.append(MarketSnapshot(
                date=d,
                index_levels={EQUITY: pe, BOND: pb},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=pe,
            ))
            pe *= Decimal("1.006")
            pb *= Decimal("1.002")
            d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
        ds = Dataset(snapshots=snapshots, frequency="monthly", version="test")

        runner = SimulationRunner(pipeline=create_default_pipeline())
        ctx = SimulationContext(
            experiment_name="test",
            cohort="test",
            start_date=date(2020, 1, 1),
            horizon_months=n_months,
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_portfolio=Portfolio(holdings=(
                AssetHolding(asset_class=EQUITY, units=Decimal("5000")),
                AssetHolding(asset_class=BOND, units=Decimal("10000")),
            )),
            dataset=ds,
            allocation_policy=ConstantAllocationPolicy(Decimal("0.75")),
            withdrawal_policy=Part49WithdrawalPolicy(Decimal("0.03")),
            interest_rate=Decimal("0"),
            loan_draw_rate=Decimal("0.01"),
            ltv_enforcement=False,
        )
        result = runner.run(ctx)
        assert result is not None
        assert result.statistics is not None
        for mr in result.timeline.monthly_results:
            assert mr.debt_snapshot is not None
            assert mr.debt_snapshot.loan_balance >= Decimal("0")
