"""Unit tests for DebtInfo cash_balance fix."""

from __future__ import annotations

from decimal import Decimal

from fbf.core.domain.model.decision_context import DebtInfo


class TestDebtInfoCashBalance:
    """Tests for DebtInfo.cash_balance correctness."""

    def test_debt_info_cash_balance_net_worth(self) -> None:
        """DebtInfo with non-zero cash → net_worth = portfolio + cash - loan."""
        debt_info = DebtInfo(
            loan_balance=Decimal("5000"),
            interest_rate=Decimal("0.015"),
            ltv_limit=Decimal("0.50"),
            portfolio_value=Decimal("100000"),
            cash_balance=Decimal("1000"),
            ltv_observed=Decimal("0.05"),
            ltv_enforcement=True,
        )
        # net_worth = portfolio_value + cash_balance - loan_balance
        # net_worth = 100000 + 1000 - 5000 = 96000
        assert debt_info.net_worth == Decimal("96000")

    def test_debt_info_zero_cash(self) -> None:
        """DebtInfo with zero cash → net_worth = portfolio - loan."""
        debt_info = DebtInfo(
            loan_balance=Decimal("5000"),
            interest_rate=Decimal("0.015"),
            ltv_limit=Decimal("0.50"),
            portfolio_value=Decimal("100000"),
            cash_balance=Decimal("0"),
            ltv_observed=Decimal("0.05"),
            ltv_enforcement=True,
        )
        # net_worth = 100000 + 0 - 5000 = 95000
        assert debt_info.net_worth == Decimal("95000")

    def test_debt_info_default_cash(self) -> None:
        """DebtInfo with default cash → net_worth = portfolio - loan."""
        debt_info = DebtInfo(
            loan_balance=Decimal("5000"),
            interest_rate=Decimal("0.015"),
            ltv_limit=Decimal("0.50"),
            portfolio_value=Decimal("100000"),
            ltv_observed=Decimal("0.05"),
            ltv_enforcement=True,
        )
        # Default cash_balance is Decimal("0")
        assert debt_info.cash_balance == Decimal("0")
        # net_worth = 100000 + 0 - 5000 = 95000
        assert debt_info.net_worth == Decimal("95000")
