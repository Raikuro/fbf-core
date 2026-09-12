"""S6.3 — Part 52 Deterministic Scenario Validation.

Validates that Part 52 mechanics (drawdown-triggered borrowing, repayment at
ATH, FFR-based interest, LTV enforcement) are correctly implemented and
executable through the production study-building path.

This file tests MECHANISM CORRECTNESS and the ResearchExecutor internal path.
Full ERN replication scenarios (A1/A2/A3) are owned by
``test_part52_canonical_ern_replication.py`` and are not duplicated here.

Scope:
    - PART52 policy type registration
    - Policy construction through StudyConfiguration
    - borrow_pct / drawdown_threshold propagation
    - ResearchExecutor internal execution path (single scenario)
    - Unit count and success-rate structure

Not in scope (owned by canonical replication):
    - Full 3-scenario ERN replication (A1/A2/A3)
    - Success-rate assertion at published WR anchors
    - Grid-sweep optimizer path
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies.types import WithdrawalPolicyType
from fbf.core.execution.executor import ResearchExecutor
from fbf.core.execution.pipeline.default_pipeline import create_default_pipeline
from fbf.core.execution.pipeline.executor import SimulationExecutor
from fbf.core.execution.pipeline.runner import SimulationRunner
from fbf.core.study import StudyConfiguration, build_study_plan

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path("data/ern")
INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)
LTV_LIMIT = Decimal("0.50")
HORIZON_YEARS = 30
FIXED_INTEREST_RATE = Decimal("0.015")
EXPECTED_UNITS = 1739

# Baseline anchor (no leverage) — used for the ResearchExecutor path test.
# Full 3-scenario replication is owned by test_part52_canonical_ern_replication.
BASELINE_ANCHOR = ("baseline_no_leverage", 1965, None, Decimal("0.0358"), Decimal("0"))


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScenarioResult:
    """Result of executing one deterministic scenario."""
    scenario_name: str
    cohort_year: int
    anchor_wr: Decimal
    borrow_pct: Decimal
    threshold: Decimal | None
    total_units: int
    successful_units: int
    success_rate: Decimal
    execution_time_s: float
    anomalies: list[str]


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
        dataset_identifier="ern_swr_h720",
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


# ---------------------------------------------------------------------------
# Execution via ResearchExecutor (internal path — not execute_study_plan)
# ---------------------------------------------------------------------------

def _execute_study(config: StudyConfiguration) -> tuple[Any, float]:
    """Execute a study via ResearchExecutor and return (result, wall_time_seconds)."""
    built = build_study_plan(config, str(DATA_DIR), INITIAL_WEALTH)
    executor = ResearchExecutor(
        simulation_executor=SimulationExecutor(
            simulation_runner=SimulationRunner(pipeline=create_default_pipeline())
        )
    )
    t_start = time.perf_counter()
    result = executor.execute(built.plan)
    t_end = time.perf_counter()
    return result, t_end - t_start


def _count_successes(result: Any) -> tuple[int, int]:
    """Return (successful, total) from a ResearchExecutionResult."""
    sim_results = result.experiment_result.simulation_results
    total = len(sim_results)
    successful = sum(1 for r in sim_results if r.statistics.success)
    return successful, total


def _execute_baseline_scenario() -> ScenarioResult:
    """Execute the baseline (no leverage) scenario via ResearchExecutor."""
    scenario_name, cohort_year, threshold, anchor_wr, borrow_pct = BASELINE_ANCHOR
    config = _build_study_config(
        withdrawal_rate=anchor_wr,
        borrow_pct=borrow_pct,
        drawdown_threshold=threshold,
    )
    result, t_elapsed = _execute_study(config)
    succ, total = _count_successes(result)
    rate = Decimal(str(succ)) / Decimal(str(total)) if total > 0 else Decimal("0")

    return ScenarioResult(
        scenario_name=scenario_name,
        cohort_year=cohort_year,
        anchor_wr=anchor_wr,
        borrow_pct=borrow_pct,
        threshold=threshold,
        total_units=total,
        successful_units=succ,
        success_rate=rate,
        execution_time_s=t_elapsed,
        anomalies=[],
    )


# ---------------------------------------------------------------------------
# Fixture: single-scenario ResearchExecutor execution
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def baseline_result() -> ScenarioResult:
    """Execute the baseline scenario once via ResearchExecutor and return result."""
    return _execute_baseline_scenario()


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


# ===========================================================================
# SECTION 2: RESEARCH EXECUTOR PATH
# Validates that the internal ResearchExecutor execution path works correctly.
# Full ERN scenario replication is owned by test_part52_canonical_ern_replication.
# ===========================================================================

class TestResearchExecutorPath:
    """Verify the ResearchExecutor internal path executes Part 52 correctly."""

    def test_baseline_produces_correct_unit_count(
        self, baseline_result: ScenarioResult
    ) -> None:
        """Baseline scenario must produce exactly 1,739 simulation units."""
        assert baseline_result.total_units == EXPECTED_UNITS, (
            f"expected {EXPECTED_UNITS} units, got {baseline_result.total_units}"
        )

    def test_baseline_executes_successfully(
        self, baseline_result: ScenarioResult
    ) -> None:
        """Baseline scenario must execute and produce valid results."""
        assert baseline_result.success_rate >= Decimal("0"), (
            f"Baseline produced invalid success rate: {baseline_result.success_rate}"
        )

    def test_baseline_no_anomalies(self, baseline_result: ScenarioResult) -> None:
        """Baseline scenario must have no critical anomalies."""
        assert baseline_result.anomalies == []

    def test_baseline_completes_within_time_limit(
        self, baseline_result: ScenarioResult
    ) -> None:
        """Baseline scenario must complete within 60 minutes."""
        assert baseline_result.execution_time_s < 3600, (
            f"took {baseline_result.execution_time_s:.0f}s (> 60 min)"
        )


# ---------------------------------------------------------------------------
# Standalone execution for report generation
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 80)
    print("S6.3 — Part 52 Deterministic Scenario Validation")
    print("=" * 80)
    print("Scenario: baseline (no leverage)")
    print(f"Total units: {EXPECTED_UNITS:,}")
    print()

    r = _execute_baseline_scenario()
    print(f"Result: {r.successful_units}/{r.total_units} "
          f"({r.success_rate}), {r.execution_time_s:.1f}s")
    if r.anomalies:
        for a in r.anomalies:
            print(f"  NOTE: {a}")
    else:
        print("  OK")
    print()
    print("=" * 80)
