"""Tests for WithdrawalFrequency enum and frequency-aware withdrawal policies.

Covers:
- WithdrawalFrequency enum values
- Both frequencies for all four withdrawal policies (FixedReal, Constant, Part49, Part52)
- Correct monthly and annual amounts
- Annual event timing (period_index % 12 == 0)
- Zero-amount months in annual mode
- YAML parsing of frequency
- Part52 annual leverage coupling
- Backward compatibility (default MONTHLY)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from fbf.core.domain.model.allocation import Allocation, AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.decision_context import DebtInfo, DecisionContext
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies.concrete import (
    ConstantWithdrawalPolicy,
    FixedRealWithdrawalPolicy,
)
from fbf.core.domain.policies.frequency import WithdrawalFrequency
from fbf.core.domain.policies.part49_withdrawal import Part49WithdrawalPolicy
from fbf.core.domain.policies.part52_withdrawal import Part52WithdrawalPolicy

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def equity_asset() -> AssetClass:
    return AssetClass(id="equity", name="Equity", description="")


@pytest.fixture
def bond_asset() -> AssetClass:
    return AssetClass(id="bond", name="Bond", description="")


@pytest.fixture
def initial_portfolio(
    equity_asset: AssetClass, bond_asset: AssetClass
) -> Portfolio:
    return Portfolio(
        holdings=(
            AssetHolding(asset_class=equity_asset, units=Decimal("500")),
            AssetHolding(asset_class=bond_asset, units=Decimal("500")),
        )
    )


@pytest.fixture
def dataset(
    equity_asset: AssetClass, bond_asset: AssetClass
) -> Dataset:
    return Dataset(
        identifier="test",
        snapshots=(
            MarketSnapshot(
                date=date(1965, 11, 1),
                index_levels={
                    equity_asset: Decimal("100"),
                    bond_asset: Decimal("100"),
                },
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("1"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            ),
        ),
        frequency="monthly",
        version="test",
    )


@dataclass
class MockSimulationContext:
    dataset: Dataset
    initial_portfolio: Portfolio
    loan_draw_rate: Decimal | None = None


def _build_context(
    mock_sim_ctx: MockSimulationContext,
    equity_index: Decimal,
    running_ath: Decimal,
    is_ath: bool,
    period_index: int = 0,
    loan_balance: Decimal = Decimal("0"),
) -> DecisionContext:
    equity_asset = AssetClass(id="equity", name="Equity", description="")
    bond_asset = AssetClass(id="bond", name="Bond", description="")

    market_snapshot = MarketSnapshot(
        date=date(1965, 11, 1),
        index_levels={
            equity_asset: equity_index,
            bond_asset: Decimal("100"),
        },
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("1"),
        is_ath=is_ath,
        is_underwater=not is_ath,
        running_ath=running_ath,
    )

    debt_info = None
    if loan_balance > 0:
        debt_info = DebtInfo(
            loan_balance=loan_balance,
            interest_rate=Decimal("0.015"),
            ltv_limit=Decimal("0.50"),
            portfolio_value=Decimal("100000"),
            ltv_observed=loan_balance / Decimal("100000"),
            ltv_enforcement=True,
        )

    allocation = Allocation(
        weights={equity_asset: Decimal("0.75"), bond_asset: Decimal("0.25")}
    )
    target = AllocationTarget(
        weights={equity_asset: Decimal("0.75"), bond_asset: Decimal("0.25")}
    )

    return DecisionContext(
        date=date(1965, 11, 1),
        period_index=period_index,
        simulation_context=mock_sim_ctx,
        portfolio=Portfolio(holdings=()),
        current_allocation=allocation,
        target_allocation=target,
        market_snapshot=market_snapshot,
        dataset=mock_sim_ctx.dataset,
        debt_info=debt_info,
    )


# ---------------------------------------------------------------------------
# WithdrawalFrequency enum
# ---------------------------------------------------------------------------

class TestWithdrawalFrequency:
    def test_monthly_value(self) -> None:
        assert WithdrawalFrequency.MONTHLY.value == "monthly"

    def test_annual_value(self) -> None:
        assert WithdrawalFrequency.ANNUAL.value == "annual"

    def test_default_is_monthly(self) -> None:
        policy = FixedRealWithdrawalPolicy(
            withdrawal_rate=Decimal("0.04")
        )
        assert policy.frequency is WithdrawalFrequency.MONTHLY


# ---------------------------------------------------------------------------
# FixedRealWithdrawalPolicy — frequency
# ---------------------------------------------------------------------------

class TestFixedRealWithdrawalFrequency:
    def test_monthly_amount(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset, initial_portfolio=initial_portfolio
        )
        policy = FixedRealWithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            frequency=WithdrawalFrequency.MONTHLY,
        )
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("100"),
            running_ath=Decimal("100"),
            is_ath=True,
        )
        decision = policy.decide(context)
        expected = Decimal("100000") * Decimal("0.04") / Decimal("12")
        assert decision.nominal_amount.amount == expected

    def test_annual_amount(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset, initial_portfolio=initial_portfolio
        )
        policy = FixedRealWithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            frequency=WithdrawalFrequency.ANNUAL,
        )
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("100"),
            running_ath=Decimal("100"),
            is_ath=True,
            period_index=0,
        )
        decision = policy.decide(context)
        expected = Decimal("100000") * Decimal("0.04")
        assert decision.nominal_amount.amount == expected

    def test_annual_zero_on_non_withdrawal_month(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset, initial_portfolio=initial_portfolio
        )
        policy = FixedRealWithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            frequency=WithdrawalFrequency.ANNUAL,
        )
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("100"),
            running_ath=Decimal("100"),
            is_ath=True,
            period_index=1,
        )
        decision = policy.decide(context)
        assert decision.nominal_amount == Money.ZERO
        assert decision.real_amount == Money.ZERO

    def test_annual_withdrawal_on_month_12(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset, initial_portfolio=initial_portfolio
        )
        policy = FixedRealWithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            frequency=WithdrawalFrequency.ANNUAL,
        )
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("100"),
            running_ath=Decimal("100"),
            is_ath=True,
            period_index=12,
        )
        decision = policy.decide(context)
        expected = Decimal("100000") * Decimal("0.04")
        assert decision.nominal_amount.amount == expected

    def test_annual_withdrawal_on_month_24(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset, initial_portfolio=initial_portfolio
        )
        policy = FixedRealWithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            frequency=WithdrawalFrequency.ANNUAL,
        )
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("100"),
            running_ath=Decimal("100"),
            is_ath=True,
            period_index=24,
        )
        decision = policy.decide(context)
        expected = Decimal("100000") * Decimal("0.04")
        assert decision.nominal_amount.amount == expected


# ---------------------------------------------------------------------------
# ConstantWithdrawalPolicy — frequency
# ---------------------------------------------------------------------------

class TestConstantWithdrawalFrequency:
    def _make_ctx(
        self,
        equity_asset: AssetClass,
        bond_asset: AssetClass,
        portfolio: Portfolio,
        period_index: int,
    ) -> DecisionContext:
        allocation = Allocation(
            weights={equity_asset: Decimal("0.75"), bond_asset: Decimal("0.25")}
        )
        target = AllocationTarget(
            weights={equity_asset: Decimal("0.75"), bond_asset: Decimal("0.25")}
        )
        snapshot = MarketSnapshot(
            date=date(1965, 11, 1),
            index_levels={
                equity_asset: Decimal("100"),
                bond_asset: Decimal("100"),
            },
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("1"),
            is_ath=True,
            is_underwater=False,
            running_ath=Decimal("100"),
        )
        ds = Dataset(
            identifier="t",
            snapshots=(snapshot,),
            frequency="monthly",
            version="t",
        )
        return DecisionContext(
            date=date(1965, 11, 1),
            period_index=period_index,
            simulation_context=None,
            portfolio=portfolio,
            current_allocation=allocation,
            target_allocation=target,
            market_snapshot=snapshot,
            dataset=ds,
        )

    def test_monthly_amount(
        self, equity_asset: AssetClass, bond_asset: AssetClass
    ) -> None:
        policy = ConstantWithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            frequency=WithdrawalFrequency.MONTHLY,
        )
        portfolio = Portfolio(holdings=(
            AssetHolding(asset_class=equity_asset, units=Decimal("500")),
            AssetHolding(asset_class=bond_asset, units=Decimal("500")),
        ))
        ctx = self._make_ctx(equity_asset, bond_asset, portfolio, 0)
        decision = policy.decide(ctx)
        expected = Decimal("1000") * Decimal("0.04") / Decimal("12")
        assert decision.nominal_amount.amount == expected

    def test_annual_amount(
        self, equity_asset: AssetClass, bond_asset: AssetClass
    ) -> None:
        policy = ConstantWithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            frequency=WithdrawalFrequency.ANNUAL,
        )
        portfolio = Portfolio(holdings=(
            AssetHolding(asset_class=equity_asset, units=Decimal("500")),
            AssetHolding(asset_class=bond_asset, units=Decimal("500")),
        ))
        ctx = self._make_ctx(equity_asset, bond_asset, portfolio, 0)
        decision = policy.decide(ctx)
        expected = Decimal("1000") * Decimal("0.04")
        assert decision.nominal_amount.amount == expected

    def test_annual_zero_on_non_withdrawal_month(
        self, equity_asset: AssetClass, bond_asset: AssetClass
    ) -> None:
        policy = ConstantWithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            frequency=WithdrawalFrequency.ANNUAL,
        )
        portfolio = Portfolio(holdings=(
            AssetHolding(asset_class=equity_asset, units=Decimal("500")),
            AssetHolding(asset_class=bond_asset, units=Decimal("500")),
        ))
        ctx = self._make_ctx(equity_asset, bond_asset, portfolio, 3)
        decision = policy.decide(ctx)
        assert decision.nominal_amount == Money.ZERO


# ---------------------------------------------------------------------------
# Part49WithdrawalPolicy — frequency
# ---------------------------------------------------------------------------

class TestPart49WithdrawalFrequency:
    def test_monthly_amount(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset,
            initial_portfolio=initial_portfolio,
            loan_draw_rate=Decimal("0.10"),
        )
        policy = Part49WithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            frequency=WithdrawalFrequency.MONTHLY,
        )
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("100"),
            running_ath=Decimal("100"),
            is_ath=True,
        )
        decision = policy.decide(context)
        expected_w = Decimal("100000") * Decimal("0.04") / Decimal("12")
        expected_l = Decimal("100000") * Decimal("0.10") / Decimal("12")
        assert decision.nominal_amount.amount == expected_w
        assert decision.loan_draw_amount == expected_l

    def test_annual_amount(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset,
            initial_portfolio=initial_portfolio,
            loan_draw_rate=Decimal("0.10"),
        )
        policy = Part49WithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            frequency=WithdrawalFrequency.ANNUAL,
        )
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("100"),
            running_ath=Decimal("100"),
            is_ath=True,
            period_index=0,
        )
        decision = policy.decide(context)
        expected_w = Decimal("100000") * Decimal("0.04")
        expected_l = Decimal("100000") * Decimal("0.10")
        assert decision.nominal_amount.amount == expected_w
        assert decision.loan_draw_amount == expected_l

    def test_annual_zero_on_non_withdrawal_month(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset,
            initial_portfolio=initial_portfolio,
            loan_draw_rate=Decimal("0.10"),
        )
        policy = Part49WithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            frequency=WithdrawalFrequency.ANNUAL,
        )
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("100"),
            running_ath=Decimal("100"),
            is_ath=True,
            period_index=5,
        )
        decision = policy.decide(context)
        assert decision.nominal_amount == Money.ZERO
        assert decision.loan_draw_amount == Decimal("0")


# ---------------------------------------------------------------------------
# Part52WithdrawalPolicy — frequency
# ---------------------------------------------------------------------------

class TestPart52WithdrawalFrequency:
    def test_monthly_budget(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset, initial_portfolio=initial_portfolio
        )
        policy = Part52WithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            borrow_pct=Decimal("0.25"),
            drawdown_threshold=Decimal("0.20"),
            frequency=WithdrawalFrequency.MONTHLY,
        )
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("100"),
            running_ath=Decimal("100"),
            is_ath=True,
        )
        decision = policy.decide(context)
        expected = Decimal("100000") * Decimal("0.04") / Decimal("12")
        assert decision.nominal_amount.amount == expected

    def test_annual_budget_normal_mode(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset, initial_portfolio=initial_portfolio
        )
        policy = Part52WithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            borrow_pct=Decimal("0.25"),
            drawdown_threshold=Decimal("0.20"),
            frequency=WithdrawalFrequency.ANNUAL,
        )
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("100"),
            running_ath=Decimal("100"),
            is_ath=True,
            period_index=0,
        )
        decision = policy.decide(context)
        expected = Decimal("100000") * Decimal("0.04")
        assert decision.nominal_amount.amount == expected

    def test_annual_borrow_mode(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset, initial_portfolio=initial_portfolio
        )
        policy = Part52WithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            borrow_pct=Decimal("0.25"),
            drawdown_threshold=Decimal("0.20"),
            frequency=WithdrawalFrequency.ANNUAL,
        )
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("75"),
            running_ath=Decimal("100"),
            is_ath=False,
            period_index=0,
        )
        decision = policy.decide(context)
        annual_budget = Decimal("100000") * Decimal("0.04")
        assert decision.loan_draw_amount == annual_budget * Decimal("0.25")
        assert decision.nominal_amount.amount == annual_budget * Decimal("0.75")
        assert decision.is_repayment is False

    def test_annual_repay_mode(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset, initial_portfolio=initial_portfolio
        )
        policy = Part52WithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            borrow_pct=Decimal("0.25"),
            drawdown_threshold=Decimal("0.20"),
            frequency=WithdrawalFrequency.ANNUAL,
        )
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("110"),
            running_ath=Decimal("110"),
            is_ath=True,
            period_index=0,
            loan_balance=Decimal("5000"),
        )
        decision = policy.decide(context)
        annual_budget = Decimal("100000") * Decimal("0.04")
        assert decision.nominal_amount.amount == annual_budget * 2
        assert decision.loan_draw_amount == Decimal("0")
        assert decision.is_repayment is True

    def test_annual_zero_on_non_withdrawal_month(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset, initial_portfolio=initial_portfolio
        )
        policy = Part52WithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            borrow_pct=Decimal("0.25"),
            drawdown_threshold=Decimal("0.20"),
            frequency=WithdrawalFrequency.ANNUAL,
        )
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("75"),
            running_ath=Decimal("100"),
            is_ath=False,
            period_index=3,
        )
        decision = policy.decide(context)
        assert decision.nominal_amount == Money.ZERO
        assert decision.loan_draw_amount == Decimal("0")
        assert decision.is_repayment is False

    def test_annual_borrow_at_month_12(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset, initial_portfolio=initial_portfolio
        )
        policy = Part52WithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            borrow_pct=Decimal("0.25"),
            drawdown_threshold=Decimal("0.20"),
            frequency=WithdrawalFrequency.ANNUAL,
        )
        context = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("75"),
            running_ath=Decimal("100"),
            is_ath=False,
            period_index=12,
        )
        decision = policy.decide(context)
        annual_budget = Decimal("100000") * Decimal("0.04")
        assert decision.loan_draw_amount == annual_budget * Decimal("0.25")

    def test_annual_monthly_budget_ratio(
        self, initial_portfolio: Portfolio, dataset: Dataset
    ) -> None:
        mock_sim_ctx = MockSimulationContext(
            dataset=dataset, initial_portfolio=initial_portfolio
        )
        monthly_policy = Part52WithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            borrow_pct=Decimal("0.25"),
            drawdown_threshold=Decimal("0.20"),
            frequency=WithdrawalFrequency.MONTHLY,
        )
        annual_policy = Part52WithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            borrow_pct=Decimal("0.25"),
            drawdown_threshold=Decimal("0.20"),
            frequency=WithdrawalFrequency.ANNUAL,
        )
        ctx_m = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("100"),
            running_ath=Decimal("100"),
            is_ath=True,
            period_index=0,
        )
        ctx_a = _build_context(
            mock_sim_ctx,
            equity_index=Decimal("100"),
            running_ath=Decimal("100"),
            is_ath=True,
            period_index=0,
        )
        monthly_decision = monthly_policy.decide(ctx_m)
        annual_decision = annual_policy.decide(ctx_a)
        assert (
            annual_decision.nominal_amount.amount
            == monthly_decision.nominal_amount.amount * 12
        )


# ---------------------------------------------------------------------------
# YAML parsing of frequency
# ---------------------------------------------------------------------------

class TestYAMLFrequencyParsing:
    def test_default_frequency_parses_without_error(self) -> None:
        from fbf.core.study.builder import StudyConfiguration

        data = {
            "metadata": {"name": "test"},
            "dataset": {"identifier": "ern_sp500_real"},
            "allocation_policy": {
                "type": "ConstantAllocationPolicy",
                "equity_allocation": [0.75],
            },
            "withdrawal_policy": {
                "type": "FixedRealWithdrawalPolicy",
                "withdrawal_rate": [0.04],
            },
            "cohorts": {"horizon_years": [30]},
        }
        config = StudyConfiguration.from_yaml(data)
        assert config.withdrawal_policy_type == "FixedRealWithdrawalPolicy"

    def test_explicit_annual_frequency_parses_without_error(self) -> None:
        from fbf.core.study.builder import StudyConfiguration

        data = {
            "metadata": {"name": "test"},
            "dataset": {"identifier": "ern_sp500_real"},
            "allocation_policy": {
                "type": "ConstantAllocationPolicy",
                "equity_allocation": [0.75],
            },
            "withdrawal_policy": {
                "type": "FixedRealWithdrawalPolicy",
                "withdrawal_rate": [0.04],
                "frequency": "annual",
            },
            "cohorts": {"horizon_years": [30]},
        }
        config = StudyConfiguration.from_yaml(data)
        assert config.withdrawal_policy_type == "FixedRealWithdrawalPolicy"

    def test_invalid_frequency_raises(self) -> None:
        from fbf.core.study.builder import StudyConfiguration

        data = {
            "metadata": {"name": "test"},
            "dataset": {"identifier": "ern_sp500_real"},
            "allocation_policy": {
                "type": "ConstantAllocationPolicy",
                "equity_allocation": [0.75],
            },
            "withdrawal_policy": {
                "type": "FixedRealWithdrawalPolicy",
                "withdrawal_rate": [0.04],
                "frequency": "weekly",
            },
            "cohorts": {"horizon_years": [30]},
        }
        with pytest.raises(ValueError, match="withdrawal_policy.frequency"):
            StudyConfiguration.from_yaml(data)


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_all_policies_default_to_monthly(self) -> None:
        frp = FixedRealWithdrawalPolicy(withdrawal_rate=Decimal("0.04"))
        cwp = ConstantWithdrawalPolicy(withdrawal_rate=Decimal("0.04"))
        p49 = Part49WithdrawalPolicy(withdrawal_rate=Decimal("0.04"))
        p52 = Part52WithdrawalPolicy(
            withdrawal_rate=Decimal("0.04"),
            borrow_pct=Decimal("0.25"),
            drawdown_threshold=Decimal("0.20"),
        )
        assert frp.frequency is WithdrawalFrequency.MONTHLY
        assert cwp.frequency is WithdrawalFrequency.MONTHLY
        assert p49.frequency is WithdrawalFrequency.MONTHLY
        assert p52.frequency is WithdrawalFrequency.MONTHLY
