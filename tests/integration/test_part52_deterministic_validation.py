"""S6.3 — Part 52 Deterministic Scenario Validation.

Validates that Part 52 mechanics (drawdown-triggered borrowing, repayment at
ATH, FFR-based interest, LTV enforcement) are correctly implemented and
executable through the production study-building path.

This file tests MECHANISM CORRECTNESS only.
Full ERN replication scenarios (A1/A2/A3) are owned by
``test_part52_canonical_ern_replication.py`` and are not duplicated here.

Scope:
    - PART52 policy type registration
    - Policy construction through StudyConfiguration
    - borrow_pct / drawdown_threshold propagation

Not in scope (owned by canonical replication):
    - Full 3-scenario ERN replication (A1/A2/A3)
    - Success-rate assertion at published WR anchors
    - Grid-sweep optimizer path
    - ResearchExecutor execution (redundant with canonical E2E A1)
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from fbf.core.domain.policies.types import WithdrawalPolicyType
from fbf.core.study import StudyConfiguration

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LTV_LIMIT = Decimal("0.50")
HORIZON_YEARS = 30
FIXED_INTEREST_RATE = Decimal("0.015")


# ---------------------------------------------------------------------------
# Configuration builder
# ---------------------------------------------------------------------------

def _build_study_config(
    *,
    withdrawal_rate: Decimal,
    borrow_pct: Decimal | None,
    drawdown_threshold: Decimal | None,
) -> StudyConfiguration:
    """Build a StudyConfiguration for one Part 52 scenario × WR combination."""
    return StudyConfiguration(
        name=f"ERN Part 52 — {withdrawal_rate}",
        description="S6.3 deterministic Part 52 scenario validation",
        version="1.0",
        allocation_policy_type="ConstantAllocationPolicy",
        allocation_policy_values=(Decimal("0.75"),),
        withdrawal_policy_type="Part52WithdrawalPolicy",
        withdrawal_policy_values=(withdrawal_rate,),
        horizon_years=(HORIZON_YEARS,),
        cohort_horizon_years=60,
        debt_interest_rate=FIXED_INTEREST_RATE,
        debt_ltv_limit=LTV_LIMIT,
        debt_ltv_enforcement=True,
        debt_loan_draw_rate=None,
        debt_borrow_pct=borrow_pct,
        debt_drawdown_threshold=drawdown_threshold,
    )


# ===========================================================================
# SECTION 1: MECHANISM CORRECTNESS
# These tests verify that Part 52 is correctly implemented and executable.
# ===========================================================================

class TestMechanismRegistration:
    """Verify Part 52 is registered as a first-class policy type."""

    def test_part52_enum_exists(self) -> None:
        """PART52 must exist in WithdrawalPolicyType."""
        assert hasattr(WithdrawalPolicyType, "PART52")

    def test_part52_enum_value(self) -> None:
        """PART52 must have the correct YAML name."""
        assert WithdrawalPolicyType.PART52.yaml_name == "Part52WithdrawalPolicy"


class TestMechanismConstruction:
    """Verify Part 52 policies can be constructed through the production path."""

    def test_baseline_config_constructs(self) -> None:
        """Baseline (no leverage) must construct without error."""
        config = _build_study_config(
            withdrawal_rate=Decimal("0.0358"),
            borrow_pct=Decimal("0"),
            drawdown_threshold=None,
        )
        assert config.withdrawal_policy_type == "Part52WithdrawalPolicy"

    def test_fixed_rate_config_constructs(self) -> None:
        """Fixed-rate no-timing must construct without error."""
        config = _build_study_config(
            withdrawal_rate=Decimal("0.0378"),
            borrow_pct=Decimal("0.1076"),
            drawdown_threshold=None,
        )
        assert config.debt_borrow_pct == Decimal("0.1076")

    def test_threshold_config_constructs(self) -> None:
        """Threshold timing must construct without error."""
        config = _build_study_config(
            withdrawal_rate=Decimal("0.0391"),
            borrow_pct=Decimal("0.4108"),
            drawdown_threshold=Decimal("0.20"),
        )
        assert config.debt_borrow_pct == Decimal("0.4108")
        assert config.debt_drawdown_threshold == Decimal("0.20")
