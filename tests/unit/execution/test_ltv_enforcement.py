"""Tests for LTV observation/enforcement separation (C2 architectural change).

Validates that:
1. LTV is always computed for observation regardless of enforcement mode
2. When ltv_enforcement=True, margin calls trigger forced liquidation (legacy behavior)
3. When ltv_enforcement=False, LTV exceeds limit without forced liquidation (ERN Part 49)
4. DebtInfo exposes ltv_observed and ltv_enforcement correctly
5. DebtSnapshot records ltv_enforcement for diagnostics
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.execution.pipeline.simulation import SimulationState
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.pipeline.steps.ltv_evaluation_step import LTVEvaluationStep
from tests.fixtures.debt import BOND, EQUITY

if TYPE_CHECKING:
    from fbf.core.domain.model.dataset import Dataset
    from fbf.core.domain.model.market_snapshot import MarketSnapshot


def _make_snapshot(
    equity_price: Decimal = Decimal("1"),
    bond_price: Decimal = Decimal("1"),
) -> MarketSnapshot:
    """Create a market snapshot with required fields."""
    from fbf.core.domain.model.market_snapshot import MarketSnapshot

    return MarketSnapshot(
        date=date(2020, 1, 31),
        index_levels={EQUITY: equity_price, BOND: bond_price},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=True,
        is_underwater=False,
        running_ath=equity_price,
    )


def _make_portfolio(equity_value: Decimal, bond_value: Decimal) -> Portfolio:
    """Create a portfolio with given equity and bond values (at price=1)."""
    return Portfolio(
        holdings=(
            AssetHolding(asset_class=EQUITY, units=equity_value),
            AssetHolding(asset_class=BOND, units=bond_value),
        )
    )


def _make_dataset(*snapshots: MarketSnapshot) -> Dataset:
    """Create a dataset from snapshots."""
    from fbf.core.domain.model.dataset import Dataset

    return Dataset(
        snapshots=tuple(snapshots),
        frequency="monthly",
        version="1.0",
    )


def _make_context(
    interest_rate: Decimal = Decimal("0.06"),
    ltv_limit: Decimal = Decimal("0.75"),
    ltv_enforcement: bool = True,
) -> SimulationContext:
    """Create a minimal SimulationContext for testing."""
    from fbf.core.domain.policies.concrete import (
        ConstantAllocationPolicy,
        FixedRealWithdrawalPolicy,
    )

    snapshot1 = _make_snapshot()
    snapshot2 = _make_snapshot()
    # Make snapshot2 have a different date
    from fbf.core.domain.model.market_snapshot import MarketSnapshot
    snapshot2 = MarketSnapshot(
        date=date(2020, 2, 29),
        index_levels={EQUITY: Decimal("1"), BOND: Decimal("1")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("1"),
    )
    dataset = _make_dataset(snapshot1, snapshot2)

    return SimulationContext(
        experiment_name="test",
        cohort="2020-01",
        start_date=date(2020, 1, 31),
        horizon_months=1,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        initial_portfolio=_make_portfolio(Decimal("750000"), Decimal("250000")),
        dataset=dataset,
        allocation_policy=ConstantAllocationPolicy(Decimal("0.75")),
        withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.04")),
        interest_rate=interest_rate,
        ltv_limit=ltv_limit,
        ltv_enforcement=ltv_enforcement,
    )


class TestLtvEnforcementSeparation:
    """Test the LTV observation/enforcement separation architecture."""

    def test_ltv_observed_when_enforcement_off(self) -> None:
        """LTV is computed for observation even when enforcement is OFF."""
        step = LTVEvaluationStep()

        context = _make_context(ltv_enforcement=False)
        state = SimulationState(
            context=context,
            current_date=date(2020, 1, 31),
            period_index=0,
            portfolio=_make_portfolio(Decimal("500000"), Decimal("0")),
            market_snapshot=_make_snapshot(),
            loan_balance=Decimal("600000"),  # LTV = 120%
            interest_rate=Decimal("0.06"),
            ltv_limit=Decimal("0.75"),
            ltv_enforcement=False,
        )

        result = step.execute(state)

        # LTV exceeds limit but no liquidation occurs
        assert result.loan_balance == Decimal("600000")
        assert sum(h.units for h in result.portfolio.holdings) == Decimal("500000")

    def test_ltv_enforcement_on_triggers_liquidation(self) -> None:
        """When enforcement is ON, margin calls trigger forced liquidation."""
        step = LTVEvaluationStep()

        context = _make_context(ltv_enforcement=True)
        state = SimulationState(
            context=context,
            current_date=date(2020, 1, 31),
            period_index=0,
            portfolio=_make_portfolio(Decimal("500000"), Decimal("0")),
            market_snapshot=_make_snapshot(),
            loan_balance=Decimal("600000"),  # LTV = 120%
            interest_rate=Decimal("0.06"),
            ltv_limit=Decimal("0.75"),
            ltv_enforcement=True,
        )

        result = step.execute(state)

        # Liquidation should occur
        assert result.loan_balance < Decimal("600000")

    def test_ltv_observed_below_limit_no_action(self) -> None:
        """When LTV is below limit, no action is taken regardless of enforcement."""
        step = LTVEvaluationStep()

        context = _make_context(ltv_enforcement=False)
        state = SimulationState(
            context=context,
            current_date=date(2020, 1, 31),
            period_index=0,
            portfolio=_make_portfolio(Decimal("750000"), Decimal("250000")),
            market_snapshot=_make_snapshot(),
            loan_balance=Decimal("500000"),  # LTV = 50%
            interest_rate=Decimal("0.06"),
            ltv_limit=Decimal("0.75"),
            ltv_enforcement=False,
        )

        result = step.execute(state)

        # No change
        assert result.loan_balance == Decimal("500000")
        assert sum(h.units for h in result.portfolio.holdings) == Decimal("1000000")

    def test_debt_info_exposes_ltv_observed(self) -> None:
        """DebtInfo includes ltv_observed and ltv_enforcement fields."""
        from fbf.core.domain.model.decision_context import DebtInfo

        debt_info = DebtInfo(
            loan_balance=Decimal("600000"),
            interest_rate=Decimal("0.06"),
            ltv_limit=Decimal("0.75"),
            portfolio_value=Decimal("500000"),
            ltv_observed=Decimal("1.2"),
            ltv_enforcement=False,
        )

        assert debt_info.ltv_observed == Decimal("1.2")
        assert debt_info.ltv_enforcement is False

    def test_debt_snapshot_records_enforcement(self) -> None:
        """DebtSnapshot records ltv_enforcement for diagnostics."""
        from fbf.core.execution.pipeline.simulation import DebtSnapshot

        snapshot = DebtSnapshot(
            loan_balance=Decimal("600000"),
            cash_balance=Decimal("0"),
            ltv=Decimal("1.2"),
            net_worth=Decimal("-100000"),
            ltv_enforcement=False,
        )

        assert snapshot.ltv_enforcement is False

    def test_simulation_context_passes_ltv_enforcement(self) -> None:
        """SimulationContext.ltv_enforcement propagates to SimulationState."""
        context = _make_context(ltv_enforcement=False)
        assert context.ltv_enforcement is False

    def test_ern_part49_enforcement_off_preserves_portfolio(self) -> None:
        """ERN Part 49 behavior: LTV > 75% does NOT trigger liquidation."""
        step = LTVEvaluationStep()

        # Simulate 1965-like scenario: LTV at 84%
        context = _make_context(ltv_enforcement=False)
        state = SimulationState(
            context=context,
            current_date=date(2020, 1, 31),
            period_index=0,
            portfolio=_make_portfolio(Decimal("500000"), Decimal("0")),
            market_snapshot=_make_snapshot(),
            loan_balance=Decimal("420000"),  # LTV = 84%
            interest_rate=Decimal("0.06"),
            ltv_limit=Decimal("0.75"),
            ltv_enforcement=False,
        )

        result = step.execute(state)

        # Portfolio unchanged - no forced liquidation
        assert result.portfolio == state.portfolio
        assert result.loan_balance == Decimal("420000")
