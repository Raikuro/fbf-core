"""Floating-rate validation tests for S6.2 FFR integration.

Verifies that the FFR-based interest rate schedule is correctly used in the
Part 52 Numba execution, with interest accrual using per-period rates.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies.concrete import ConstantAllocationPolicy
from fbf.core.domain.policies.part52_withdrawal import Part52WithdrawalPolicy
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    SimulationResult,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.part52_numba_executor import Part52NumbaExecutor

EQUITY_ASSET = AssetClass(id="equity", name="", description="")
BOND_ASSET = AssetClass(id="bond", name="", description="")

INITIAL_WEALTH = Decimal("1000000")
BUDGET = INITIAL_WEALTH * Decimal("0.0391") / Decimal("12")
WITHDRAWAL_RATE = Decimal("0.0391")
BORROW_PCT = Decimal("0.4108")
DRAWDOWN_THRESHOLD = Decimal("0.20")
LTV_LIMIT = Decimal("0.50")


def _execute(sim_context: SimulationContext) -> SimulationResult:
    definition = EngineExperimentDefinition(
        name="part52-ffr",
        description="FFR integration test",
        simulation_contexts=(sim_context,),
    )
    executor = Part52NumbaExecutor(materialize_timeline=True)
    return executor.execute(definition).simulation_results[0]


def _assert_decimal_close(actual: Decimal, expected: Decimal) -> None:
    tolerance = max(abs(expected) * Decimal("1e-12"), Decimal("1e-12"))
    assert abs(actual - expected) <= tolerance, f"{actual} != {expected}"


def _create_dataset() -> Dataset:
    """Create a 6-month dataset with known market conditions."""
    snapshots = [
        MarketSnapshot(
            date=date(1965, 11, 1),
            index_levels={EQUITY_ASSET: Decimal("100"), BOND_ASSET: Decimal("100")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=True,
            is_underwater=False,
            running_ath=Decimal("100"),
        ),
        MarketSnapshot(
            date=date(1965, 12, 1),
            index_levels={EQUITY_ASSET: Decimal("75"), BOND_ASSET: Decimal("100")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=False,
            is_underwater=True,
            running_ath=Decimal("100"),
        ),
        MarketSnapshot(
            date=date(1966, 1, 1),
            index_levels={EQUITY_ASSET: Decimal("70"), BOND_ASSET: Decimal("100")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=False,
            is_underwater=True,
            running_ath=Decimal("100"),
        ),
        MarketSnapshot(
            date=date(1966, 2, 1),
            index_levels={EQUITY_ASSET: Decimal("110"), BOND_ASSET: Decimal("100")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=True,
            is_underwater=False,
            running_ath=Decimal("110"),
        ),
        MarketSnapshot(
            date=date(1966, 3, 1),
            index_levels={EQUITY_ASSET: Decimal("115"), BOND_ASSET: Decimal("100")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=True,
            is_underwater=False,
            running_ath=Decimal("115"),
        ),
        MarketSnapshot(
            date=date(1966, 4, 1),
            index_levels={EQUITY_ASSET: Decimal("120"), BOND_ASSET: Decimal("100")},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=True,
            is_underwater=False,
            running_ath=Decimal("120"),
        ),
    ]
    return Dataset(
        snapshots=tuple(snapshots),
        frequency="monthly",
    )


def test_ffr_schedule_used_in_interest_accrual() -> None:
    """Verify that InterestAccrualStep uses the FFR schedule correctly."""
    dataset = _create_dataset()
    initial_portfolio = Portfolio(
        holdings=(
            AssetHolding(asset_class=EQUITY_ASSET, units=Decimal("7500")),
            AssetHolding(asset_class=BOND_ASSET, units=Decimal("2500")),
        )
    )

    # FFR schedule: varying rates per month (simulating FFR + spread)
    ffr_schedule = (
        Decimal("0.0400"),  # Month 0: 4.00%
        Decimal("0.0450"),  # Month 1: 4.50%
        Decimal("0.0500"),  # Month 2: 5.00%
        Decimal("0.0450"),  # Month 3: 4.50%
        Decimal("0.0400"),  # Month 4: 4.00%
        Decimal("0.0350"),  # Month 5: 3.50%
    )

    sim_context = SimulationContext(
        experiment_name="test",
        cohort="1965-11",
        start_date=date(1965, 11, 1),
        horizon_months=6,
        initial_wealth=Money(INITIAL_WEALTH, Currency.EUR),
        initial_portfolio=initial_portfolio,
        dataset=dataset,
        allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.75")),
        withdrawal_policy=Part52WithdrawalPolicy(
            withdrawal_rate=WITHDRAWAL_RATE,
            borrow_pct=BORROW_PCT,
            drawdown_threshold=DRAWDOWN_THRESHOLD,
        ),
        interest_rate=None,  # No fixed rate
        interest_rate_schedule=ffr_schedule,
        ltv_limit=LTV_LIMIT,
        ltv_enforcement=False,
    )

    months = _execute(sim_context).timeline.monthly_results

    # Execute Month 0: Normal (ATH) — no borrowing
    assert months[0].debt_snapshot is None

    # Execute Month 1: Drawdown below threshold — borrowing
    assert months[1].debt_snapshot is not None
    loan_after_m1 = months[1].debt_snapshot.loan_balance
    assert loan_after_m1 > Decimal("0"), "Should have borrowed in Month 1"

    # Execute Month 2: Drawdown still >= threshold → new draw + interest at FFR[2]
    # Monthly-draw: interest on PRIOR balance, then draw is added (ERN order)
    assert months[2].debt_snapshot is not None
    new_draw_m2 = BUDGET * BORROW_PCT
    expected_interest_m2 = loan_after_m1 * ffr_schedule[2] / Decimal("12")
    expected_loan_m2 = loan_after_m1 + expected_interest_m2 + new_draw_m2
    _assert_decimal_close(months[2].debt_snapshot.loan_balance, expected_loan_m2)
    assert months[2].withdrawal_decision is not None
    assert months[2].withdrawal_decision.loan_draw_amount > Decimal("0")


def test_ffr_schedule_zero_spread_matches_fixed_rate() -> None:
    """Verify that FFR schedule with zero spread behaves like fixed rate."""
    dataset = _create_dataset()
    initial_portfolio = Portfolio(
        holdings=(
            AssetHolding(asset_class=EQUITY_ASSET, units=Decimal("7500")),
            AssetHolding(asset_class=BOND_ASSET, units=Decimal("2500")),
        )
    )

    fixed_rate = Decimal("0.0400")

    # Create two contexts: one with fixed rate, one with FFR schedule
    def _run_simulation(
        interest_rate: Decimal | None, schedule: tuple[Decimal, ...] | None
    ) -> Decimal:
        sim_context = SimulationContext(
            experiment_name="test",
            cohort="1965-11",
            start_date=date(1965, 11, 1),
            horizon_months=3,
            initial_wealth=Money(INITIAL_WEALTH, Currency.EUR),
            initial_portfolio=initial_portfolio,
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.75")),
            withdrawal_policy=Part52WithdrawalPolicy(
                withdrawal_rate=WITHDRAWAL_RATE,
                borrow_pct=BORROW_PCT,
                drawdown_threshold=DRAWDOWN_THRESHOLD,
            ),
            interest_rate=interest_rate,
            interest_rate_schedule=schedule,
            ltv_limit=LTV_LIMIT,
            ltv_enforcement=False,
        )
        final_month = _execute(sim_context).timeline.monthly_results[-1]
        assert final_month.debt_snapshot is not None
        return final_month.debt_snapshot.loan_balance

    # Fixed rate simulation
    loan_fixed = _run_simulation(interest_rate=fixed_rate, schedule=None)

    # FFR schedule with same rate in every month
    ffr_schedule = (fixed_rate, fixed_rate, fixed_rate)
    loan_ffr = _run_simulation(interest_rate=None, schedule=ffr_schedule)

    # Loan balances should be identical
    assert loan_fixed == loan_ffr, (
        f"FFR schedule with constant rate should match fixed rate: "
        f"fixed={loan_fixed}, ffr={loan_ffr}"
    )


def test_no_schedule_falls_back_to_fixed_rate() -> None:
    """Verify that missing FFR schedule uses fixed interest_rate."""
    dataset = _create_dataset()
    initial_portfolio = Portfolio(
        holdings=(
            AssetHolding(asset_class=EQUITY_ASSET, units=Decimal("7500")),
            AssetHolding(asset_class=BOND_ASSET, units=Decimal("2500")),
        )
    )

    fixed_rate = Decimal("0.0450")

    sim_context = SimulationContext(
        experiment_name="test",
        cohort="1965-11",
        start_date=date(1965, 11, 1),
        horizon_months=3,
        initial_wealth=Money(INITIAL_WEALTH, Currency.EUR),
        initial_portfolio=initial_portfolio,
        dataset=dataset,
        allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.75")),
        withdrawal_policy=Part52WithdrawalPolicy(
            withdrawal_rate=WITHDRAWAL_RATE,
            borrow_pct=BORROW_PCT,
            drawdown_threshold=DRAWDOWN_THRESHOLD,
        ),
        interest_rate=fixed_rate,
        interest_rate_schedule=None,  # No FFR schedule
        ltv_limit=LTV_LIMIT,
        ltv_enforcement=False,
    )

    months = _execute(sim_context).timeline.monthly_results

    # Execute Month 0: Normal
    assert months[0].debt_snapshot is not None
    assert months[0].debt_snapshot.loan_balance == Decimal("0")

    # Execute Month 1: Borrow
    assert months[1].debt_snapshot is not None
    loan_after_m1 = months[1].debt_snapshot.loan_balance
    assert loan_after_m1 > Decimal("0")

    # Execute Month 2: Drawdown still >= threshold → new draw + interest at fixed rate
    # ERN ordering: interest on PRIOR balance, then draw is added
    assert months[2].debt_snapshot is not None
    new_draw_m2 = BUDGET * BORROW_PCT
    expected_interest = loan_after_m1 * fixed_rate / Decimal("12")
    expected_loan = loan_after_m1 + expected_interest + new_draw_m2
    _assert_decimal_close(months[2].debt_snapshot.loan_balance, expected_loan)
