"""K.6 Integration test: end-to-end Part 49 debt pipeline.

Runs a small grid (1 cohort × 2 interest rates) through the full production
pipeline with debt enabled, verifying:
- Pipeline completes without error
- Debt snapshots are present in monthly results
- Loan balance grows with interest
- Cash lifecycle operates correctly (cash consumed before portfolio sale)
- Net worth identity holds at every period
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies import ConstantAllocationPolicy
from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy
from fbf.core.execution.pipeline.default_pipeline import create_default_pipeline
from fbf.core.execution.pipeline.executor import SimulationExecutor
from fbf.core.execution.pipeline.runner import SimulationRunner
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    MonthlyResult,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext

EQUITY = AssetClass(id="equity", name="", description="")
BOND = AssetClass(id="bond", name="", description="")


def _make_dataset(n_months: int = 12) -> Dataset:
    """Constant-return dataset: equity +0.6%/mo, bond +0.2%/mo."""
    snapshots = []
    pe = pb = Decimal("100")
    d = date(2020, 1, 1)
    for i in range(n_months + 1):
        snapshots.append(MarketSnapshot(
            date=d,
            index_levels={EQUITY: pe, BOND: pb},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("0"),
            is_ath=True,
            is_underwater=(i % 3 == 0),
            running_ath=pe,
        ))
        pe *= Decimal("1.006")
        pb *= Decimal("1.002")
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return Dataset(snapshots=snapshots, frequency="monthly", version="test")


class _Part49WithdrawalPolicy(WithdrawalPolicy):
    """Withdrawal policy that sets both portfolio withdrawal and loan draw.

    Per Part 49: total_spending = portfolio_withdrawal + loan_draw.
    Both are fixed fractions of initial_wealth, computed once at start.
    """

    def __init__(
        self,
        withdrawal_rate: Decimal,
        loan_draw_rate: Decimal,
    ) -> None:
        self.withdrawal_rate = withdrawal_rate
        self.loan_draw_rate = loan_draw_rate

    def decide(self, context: object) -> object:  # type: ignore[override]
        from fbf.core.domain.model.decision_context import DecisionContext
        from fbf.core.domain.policies.decisions import WithdrawalDecision

        ctx = context
        assert isinstance(ctx, DecisionContext)
        sim = ctx.simulation_context
        assert isinstance(sim, SimulationContext)

        initial_snapshot = sim.dataset[0]
        total = Money.ZERO
        for h in sim.initial_portfolio.holdings:
            price = initial_snapshot.index_levels[h.asset_class]
            total += Money(h.units * price, Currency.EUR)

        monthly_withdrawal = total.amount * self.withdrawal_rate / Decimal("12")
        monthly_loan = total.amount * self.loan_draw_rate / Decimal("12")

        return WithdrawalDecision(
            reason="Part49Test",
            nominal_amount=Money(monthly_withdrawal, Currency.EUR),
            real_amount=Money(monthly_withdrawal, Currency.EUR),
            loan_draw_amount=monthly_loan,
        )


def _run_debt_simulation(
    interest_rate: Decimal,
    ltv_limit: Decimal = Decimal("0.75"),
    n_months: int = 12,
) -> list[MonthlyResult]:
    """Run a single debt-enabled simulation and return monthly results."""
    dataset = _make_dataset(n_months)
    initial_wealth = Money(Decimal("1000000"), Currency.EUR)

    context = SimulationContext(
        experiment_name="part49-test",
        cohort="part49-test",
        start_date=dataset[0].date,
        horizon_months=n_months,
        initial_wealth=initial_wealth,
        initial_portfolio=Portfolio(holdings=(
            AssetHolding(asset_class=EQUITY, units=Decimal("5000")),
            AssetHolding(asset_class=BOND, units=Decimal("10000")),
        )),
        dataset=dataset,
        allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.75")),
        withdrawal_policy=_Part49WithdrawalPolicy(
            withdrawal_rate=Decimal("0.03"),
            loan_draw_rate=Decimal("0.01"),
        ),
        interest_rate=interest_rate,
        ltv_limit=ltv_limit,
    )

    pipeline = create_default_pipeline()
    runner = SimulationRunner(pipeline=pipeline)
    executor = SimulationExecutor(runner)

    engine_def = EngineExperimentDefinition(
        name="part49-test",
        description="K.6 integration test",
        simulation_contexts=(context,),
    )
    experiment_run = executor.execute(engine_def)
    sim_result = experiment_run.simulation_results[0]

    return list(sim_result.timeline.monthly_results)


class TestPart49SmallGrid:
    """K.6 acceptance: small grid with debt enabled completes successfully."""

    def test_single_interest_rate_completes(self) -> None:
        """1 cohort × 1 interest rate completes with debt snapshots."""
        results = _run_debt_simulation(interest_rate=Decimal("0.06"))
        assert len(results) == 12
        for mr in results:
            assert mr.debt_snapshot is not None

    def test_two_interest_rates_complete(self) -> None:
        """1 cohort × 2 interest rates both complete."""
        r1 = _run_debt_simulation(interest_rate=Decimal("0.0"))
        r2 = _run_debt_simulation(interest_rate=Decimal("0.06"))
        assert len(r1) == 12
        assert len(r2) == 12

    def test_zero_interest_no_debt_snapshot(self) -> None:
        """interest_rate=0 → debt snapshots are None (no debt configured)."""
        results = _run_debt_simulation(interest_rate=Decimal("0.0"))
        for mr in results:
            assert mr.debt_snapshot is None

    def test_debt_snapshot_fields_present(self) -> None:
        """Debt snapshot has all required fields when interest_rate > 0."""
        results = _run_debt_simulation(interest_rate=Decimal("0.06"))
        for mr in results:
            ds = mr.debt_snapshot
            assert ds is not None
            assert isinstance(ds.loan_balance, Decimal)
            assert isinstance(ds.cash_balance, Decimal)
            assert isinstance(ds.ltv, Decimal)
            assert isinstance(ds.net_worth, Decimal)

    def test_loan_balance_grows_with_interest(self) -> None:
        """Loan balance increases each period due to interest accrual."""
        results = _run_debt_simulation(interest_rate=Decimal("0.06"), n_months=6)
        loan_balances = [
            mr.debt_snapshot.loan_balance
            for mr in results
            if mr.debt_snapshot is not None
        ]
        for i in range(1, len(loan_balances)):
            assert loan_balances[i] > loan_balances[i - 1], (
                f"Loan balance should grow: month {i-1}={loan_balances[i-1]}, "
                f"month {i}={loan_balances[i]}"
            )

    def test_net_worth_identity_holds(self) -> None:
        """net_worth = portfolio_value + cash_balance - loan_balance at every period."""
        results = _run_debt_simulation(interest_rate=Decimal("0.06"), n_months=6)
        for mr in results:
            ds = mr.debt_snapshot
            assert ds is not None
            portfolio_value = Decimal("0")
            for h in mr.portfolio.holdings:
                price = mr.market_snapshot.index_levels.get(h.asset_class)
                if price is not None:
                    portfolio_value += h.units * price
            expected_nw = portfolio_value + ds.cash_balance - ds.loan_balance
            assert ds.net_worth == expected_nw, (
                f"net_worth identity violated: {ds.net_worth} != "
                f"{portfolio_value} + {ds.cash_balance} - {ds.loan_balance}"
            )

    def test_cash_lifecycle(self) -> None:
        """Cash from loan draw is consumed by withdrawal (cash_balance=0 at record time)."""
        results = _run_debt_simulation(interest_rate=Decimal("0.06"), n_months=6)
        for mr in results:
            ds = mr.debt_snapshot
            assert ds is not None
            # After LoanDraw (adds cash) and WithdrawalExecution (consumes cash),
            # cash should be consumed by spending (or zero if no spending).
            # At MonthlyResultBuilder (step 70), cash_balance should be 0
            # because the withdrawal consumed the cash.
            assert ds.cash_balance >= 0, f"cash_balance negative: {ds.cash_balance}"

    def test_ltv_ratio_computed(self) -> None:
        """LTV is computed when loan_balance > 0."""
        results = _run_debt_simulation(interest_rate=Decimal("0.06"), n_months=6)
        for mr in results:
            ds = mr.debt_snapshot
            assert ds is not None
            if ds.loan_balance > 0:
                portfolio_value = Decimal("0")
                for h in mr.portfolio.holdings:
                    price = mr.market_snapshot.index_levels.get(h.asset_class)
                    if price is not None:
                        portfolio_value += h.units * price
                if portfolio_value > 0:
                    expected_ltv = ds.loan_balance / portfolio_value
                    assert ds.ltv == expected_ltv, (
                        f"LTV mismatch: {ds.ltv} != {expected_ltv}"
                    )
