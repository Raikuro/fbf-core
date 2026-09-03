"""Oracle equivalence tests for debt engine integration (K.4).

These tests verify that the production engine reproduces the K.1/K.2 semantics
by comparing production state transitions against the independent oracle
using the K.3 fixtures.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.pipeline.steps.interest_accrual_step import InterestAccrualStep
from fbf.core.execution.pipeline.steps.ltv_evaluation_step import LTVEvaluationStep
from tests.fixtures.debt import (
    ALL_SCENARIOS,
    SCENARIO_BASIC_BORROWING,
    SCENARIO_INTEREST_ACCRUAL,
    SCENARIO_MARGIN_CALL,
    SCENARIO_PROPORTIONAL_LIQUIDATION,
    DebtScenario,
)
from tests.oracle.ern.debt_oracle import DebtOracleState, execute_month_transition

# Canonical asset classes
EQUITY = AssetClass(id="equity", name="Equity", description="")
BOND = AssetClass(id="bond", name="Bond", description="")


def _create_dataset(snapshots: list[MarketSnapshot]) -> Dataset:
    """Create a dataset from snapshots."""
    return Dataset(
        snapshots=snapshots,
        frequency="monthly",
        version="test",
        identifier="test-dataset",
    )


def _create_snapshot(
    equity_price: Decimal,
    bond_price: Decimal,
    period: int = 0,
) -> MarketSnapshot:
    """Create a market snapshot."""
    from datetime import date

    return MarketSnapshot(
        date=date(2020, 1, 1 + period),
        index_levels={EQUITY: equity_price, BOND: bond_price},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=True,
        is_underwater=False,
        running_ath=equity_price,
    )


class TestOracleEquivalence:
    """Verify that production engine reproduces oracle semantics."""

    def _run_full_month_transition(
        self,
        initial_portfolio_value: Decimal,
        initial_loan_balance: Decimal,
        annual_interest_rate: Decimal,
        ltv_limit: Decimal,
        market_return: Decimal,
    ) -> tuple[Decimal, Decimal, bool]:
        """Run full month transition and return results.

        Executes: interest accrual + LTV evaluation + failure detection.
        """
        from datetime import date

        from fbf.core.execution.pipeline.simulation import ExecutionStatus, SimulationState
        from fbf.core.execution.pipeline.steps.failure_detection_step import FailureDetectionStep

        interest_step = InterestAccrualStep()
        ltv_step = LTVEvaluationStep()
        failure_step = FailureDetectionStep()

        # Create dataset with price that gives us the desired portfolio value
        # Portfolio has 100 equity units, so price = initial_portfolio_value / 100
        equity_price = initial_portfolio_value / Decimal("100")

        # Apply market return to get end-of-period price
        end_equity_price = equity_price * (Decimal("1") + market_return)

        dataset = _create_dataset([
            _create_snapshot(equity_price, Decimal("50"), 0),
            _create_snapshot(end_equity_price, Decimal("50"), 1),
        ])

        context = SimulationContext(
            experiment_name="test",
            cohort="test",
            start_date=date(2020, 1, 1),
            horizon_months=2,
            initial_wealth=Money(Decimal("10000"), Currency.EUR),
            initial_portfolio=Portfolio(holdings=(
                AssetHolding(asset_class=EQUITY, units=Decimal("100")),
            )),
            dataset=dataset,
            allocation_policy=None,  # type: ignore
            withdrawal_policy=None,  # type: ignore
        )

        state = SimulationState(
            context=context,
            current_date=date(2020, 1, 1),
            period_index=0,
            portfolio=context.initial_portfolio,
            market_snapshot=dataset[0],
            current_wealth=context.initial_wealth,
            peak_wealth=context.initial_wealth,
            status=ExecutionStatus.RUNNING,
            loan_balance=initial_loan_balance,
            interest_rate=annual_interest_rate,
            ltv_limit=ltv_limit,
        )

        # Simulate market evolution: update portfolio to end-of-period prices
        # This simulates what MarketEvolutionStep would do
        state.market_snapshot = dataset[1]

        # Step 7: Interest accrual
        state = interest_step.execute(state)

        # Step 8: LTV evaluation
        state = ltv_step.execute(state)

        # Step 10: Failure detection
        state = failure_step.execute(state)

        # Calculate final portfolio value
        portfolio_value = Decimal("0")
        for holding in state.portfolio.holdings:
            price = state.market_snapshot.index_levels.get(holding.asset_class)
            if price is not None:
                portfolio_value += holding.units * price

        is_failure = state.failure_state is not None

        return portfolio_value, state.loan_balance, is_failure

    def test_interest_accrual_oracle_equivalence(self) -> None:
        """Verify interest accrual matches oracle."""
        scenario = SCENARIO_INTEREST_ACCRUAL

        # Run production engine
        prod_portfolio, prod_loan, _ = self._run_full_month_transition(
            scenario.initial_portfolio_value,
            scenario.initial_loan_balance,
            scenario.annual_interest_rate,
            scenario.ltv_limit,
            scenario.market_return,
        )

        # Run oracle
        oracle_state = DebtOracleState(
            portfolio_value=scenario.initial_portfolio_value,
            loan_balance=scenario.initial_loan_balance,
            annual_interest_rate=scenario.annual_interest_rate,
            ltv_limit=scenario.ltv_limit,
            month_index=0,
        )
        oracle_result = execute_month_transition(oracle_state, scenario.market_return)

        # Compare (portfolio unchanged, loan balance matches)
        assert prod_portfolio == scenario.initial_portfolio_value
        assert prod_loan == oracle_result.loan_balance

    def test_ltv_evaluation_no_margin_call(self) -> None:
        """Verify LTV evaluation with no margin call matches oracle."""
        scenario = SCENARIO_BASIC_BORROWING

        # Run production engine
        prod_portfolio, prod_loan, is_failure = self._run_full_month_transition(
            scenario.initial_portfolio_value,
            scenario.initial_loan_balance,
            scenario.annual_interest_rate,
            scenario.ltv_limit,
            scenario.market_return,
        )

        # Run oracle
        oracle_state = DebtOracleState(
            portfolio_value=scenario.initial_portfolio_value,
            loan_balance=scenario.initial_loan_balance,
            annual_interest_rate=scenario.annual_interest_rate,
            ltv_limit=scenario.ltv_limit,
            month_index=0,
        )
        oracle_result = execute_month_transition(oracle_state, scenario.market_return)

        # Compare
        assert prod_portfolio == oracle_result.portfolio_value
        assert prod_loan == oracle_result.loan_balance
        assert is_failure == (oracle_result.failure_state.value != "none")

    def test_ltv_evaluation_margin_call(self) -> None:
        """Verify LTV evaluation with margin call matches oracle."""
        scenario = SCENARIO_PROPORTIONAL_LIQUIDATION

        # Run production engine
        prod_portfolio, prod_loan, is_failure = self._run_full_month_transition(
            scenario.initial_portfolio_value,
            scenario.initial_loan_balance,
            scenario.annual_interest_rate,
            scenario.ltv_limit,
            scenario.market_return,
        )

        # Run oracle
        oracle_state = DebtOracleState(
            portfolio_value=scenario.initial_portfolio_value,
            loan_balance=scenario.initial_loan_balance,
            annual_interest_rate=scenario.annual_interest_rate,
            ltv_limit=scenario.ltv_limit,
            month_index=0,
        )
        oracle_result = execute_month_transition(oracle_state, scenario.market_return)

        # Compare
        assert prod_portfolio == oracle_result.portfolio_value
        assert prod_loan == oracle_result.loan_balance
        assert is_failure == (oracle_result.failure_state.value != "none")

    def test_ltv_evaluation_unsatisfiable_margin_call(self) -> None:
        """Verify LTV evaluation with unsatisfiable margin call matches oracle."""
        scenario = SCENARIO_MARGIN_CALL

        # Run production engine
        prod_portfolio, prod_loan, is_failure = self._run_full_month_transition(
            scenario.initial_portfolio_value,
            scenario.initial_loan_balance,
            scenario.annual_interest_rate,
            scenario.ltv_limit,
            scenario.market_return,
        )

        # Run oracle
        oracle_state = DebtOracleState(
            portfolio_value=scenario.initial_portfolio_value,
            loan_balance=scenario.initial_loan_balance,
            annual_interest_rate=scenario.annual_interest_rate,
            ltv_limit=scenario.ltv_limit,
            month_index=0,
        )
        oracle_result = execute_month_transition(oracle_state, scenario.market_return)

        # Compare
        assert prod_portfolio == oracle_result.portfolio_value
        assert prod_loan == oracle_result.loan_balance
        assert is_failure == (oracle_result.failure_state.value != "none")

    @pytest.mark.parametrize(
        "scenario",
        ALL_SCENARIOS,
        ids=[s.name for s in ALL_SCENARIOS],
    )
    def test_scenario_oracle_equivalence(self, scenario: DebtScenario) -> None:
        """Verify all scenarios produce oracle-equivalent results."""
        # Run production engine
        prod_portfolio, prod_loan, is_failure = self._run_full_month_transition(
            scenario.initial_portfolio_value,
            scenario.initial_loan_balance,
            scenario.annual_interest_rate,
            scenario.ltv_limit,
            scenario.market_return,
        )

        # Run oracle
        oracle_state = DebtOracleState(
            portfolio_value=scenario.initial_portfolio_value,
            loan_balance=scenario.initial_loan_balance,
            annual_interest_rate=scenario.annual_interest_rate,
            ltv_limit=scenario.ltv_limit,
            month_index=0,
        )
        oracle_result = execute_month_transition(oracle_state, scenario.market_return)

        # Compare
        assert prod_portfolio == oracle_result.portfolio_value, (
            f"Portfolio mismatch for {scenario.name}: "
            f"got {prod_portfolio}, expected {oracle_result.portfolio_value}"
        )
        assert prod_loan == oracle_result.loan_balance, (
            f"Loan mismatch for {scenario.name}: "
            f"got {prod_loan}, expected {oracle_result.loan_balance}"
        )
        assert is_failure == (oracle_result.failure_state.value != "none"), (
            f"Failure mismatch for {scenario.name}: "
            f"got {is_failure}, expected {oracle_result.failure_state.value != 'none'}"
        )
