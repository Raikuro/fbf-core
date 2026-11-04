"""S6.6B Stage 2 — Canonical ERN Part 52 Replication.

Executes 11 canonical Part 52 scenarios and reports gross-survival counts.

Scenario provenance:
- A1, A2, A3, A9, A10 use published WR and Borrow% values.
- A4-A8 and A11 use published WR with BF-discovered Borrow% values.

FFR use:
- A1 and A9 are non-FFR baselines.
- A2-A8 and A10-A11 use the runtime FFR series with lag_months=1
  (month T uses FFR from month T-1).

The A2, A3, and A10 published-parameter anchors also evaluate the workbook's
three-constraint feasibility result through `evaluate_part52_feasibility()`,
using the same built plan and the production Part 52 kernel.
`statistics.success` remains gross portfolio survival; each anchor asserts
every feasibility condition independently and records the diagnostic metrics.
Full-universe feasibility, LTV enforcement, and the final-value target are not
applied to every scenario (`debt_ltv_enforcement=False`). Full-universe
gross-survival counts are diagnostic, not canonical acceptance targets.

The FFR conversion formula is resolved (see
docs/research/ern_part52_replication.md §3.2 and §27.8). Open questions are
FFR data fidelity (vintage, post-2021 handling, end-bound/cohort eligibility,
stale provenance metadata) and validation semantics, not the conversion formula.

Canonical Configuration Matrix (from ERN Part 52 primary source):

Category A: Validation scenarios (published WR; Borrow% provenance noted)
    A1: 1965-11, no threshold, no FFR, WR=3.58%, B%=0%, no repayment
    A2: 1965-11, no threshold, FFR+0.50%, WR=3.78%, B%=10.76%, no repayment
    A3: 1965-11, 20% threshold, FFR+0.50%, WR=3.91%, B%=41.08%, repayment
    A4: 1965-11, 25% threshold, FFR+0.50%, WR=3.92%, B%=BF-discovered (10%), repayment
    A5: 1965-11, 25% threshold, FFR+1.25%, WR=3.87%, B%=BF-discovered (5%), repayment
    A6: 1965-11, 25% threshold, FFR+2.75%, WR=3.75%, B%=BF-discovered (0%), repayment
    A7: 1965-11, 30% threshold, FFR+0.50%, WR=3.94%, B%=BF-discovered (10%), repayment
    A8: 1965-11, 35% threshold, FFR+0.50%, WR=3.83%, B%=BF-discovered (0%), repayment
    A9: 1929-09, no threshold, no FFR, WR=3.61%, B%=0%, no repayment
    A10: 1929-09, no threshold, FFR+0.50%, WR=4.39%, B%=31.86%, no repayment
    A11: 1929-09, 35% threshold, FFR+0.50%, WR=4.93%, B%=BF-discovered (50%), repayment

Classification key:
    A — Published Borrow%; gross survival 100% in this test
    B — BF-discovered Borrow%; gross survival 100% in this test
    C — Gross survival <100%; not a feasibility classification
    D — Explainable methodology/data difference

Parameters:
    Horizon: 30 years (360 months)
    Allocation: 75/25 stocks/bonds
    Initial portfolio: $1,000,000
    Cohorts: 1,739 units from the full dataset; not filtered to FFR coverage
    LTV limit: 50% (observed by the feasibility helper; enforcement disabled)
    Final value target: $250,000 (feasibility helper default; not configured in the study)
    Success metric: statistics.success = gross survival
    Feasibility metric: A2/A3 1965-11 and A10 1929-09 anchors, via
        evaluate_part52_feasibility()
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from fbf.core.domain.model.money import Currency, Money
from fbf.core.execution import (
    ExecutionOptions,
    ExecutionStrategy,
    _extract_simulation_contexts,
    execute_study_plan,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.part52_numba_executor import (
    Part52FeasibilityMetrics,
    evaluate_part52_feasibility,
)
from fbf.core.study import (
    BuiltStudy,
    PlannedSimulationUnit,
    ResearchPlan,
    StudyConfiguration,
    build_study_plan,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path("data/ern")
INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)
FINAL_VALUE_TARGET = Decimal("0.25")  # $250K terminal net-worth
LTV_LIMIT = Decimal("0.50")
HORIZON_YEARS = 30
COHORT_HORIZON_YEARS = 60
EXPECTED_UNITS = 1739
FFR_DATASET = "ffr"
FEASIBILITY_ANCHOR_SCENARIO_IDS = frozenset({"A2", "A3", "A10"})
MIN_NET_WORTH_TARGET = Decimal("1000")
FINAL_NET_WORTH_TARGET = Decimal("250000")

# ---------------------------------------------------------------------------
# Canonical ERN Configuration Matrix
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CanonicalScenario:
    """One canonical ERN scenario with full provenance."""
    scenario_id: str
    cohort_year: int
    cohort_month: int
    threshold: Decimal | None
    ffr_spread: Decimal | None
    repayment_enabled: bool
    published_wr: Decimal
    published_borrow_pct: Decimal | None
    wr_provenance: str  # "published", "methodology-derived"
    borrow_provenance: str  # "published", "BF-discovered"


CANONICAL_SCENARIOS: tuple[CanonicalScenario, ...] = (
    # A1: Baseline no leverage
    CanonicalScenario(
        scenario_id="A1",
        cohort_year=1965, cohort_month=11,
        threshold=None, ffr_spread=None, repayment_enabled=False,
        published_wr=Decimal("0.0358"), published_borrow_pct=Decimal("0"),
        wr_provenance="published", borrow_provenance="published",
    ),
    # A2: No timing, leverage, FFR+0.50%
    CanonicalScenario(
        scenario_id="A2",
        cohort_year=1965, cohort_month=11,
        threshold=None, ffr_spread=Decimal("0.005"), repayment_enabled=False,
        published_wr=Decimal("0.0378"), published_borrow_pct=Decimal("0.1076"),
        wr_provenance="published", borrow_provenance="published",
    ),
    # A3: 20% threshold, FFR+0.50%, repayment
    CanonicalScenario(
        scenario_id="A3",
        cohort_year=1965, cohort_month=11,
        threshold=Decimal("0.20"), ffr_spread=Decimal("0.005"), repayment_enabled=True,
        published_wr=Decimal("0.0391"), published_borrow_pct=Decimal("0.4108"),
        wr_provenance="published", borrow_provenance="published",
    ),
    # A4: 25% threshold, FFR+0.50%, repayment — B%=10% (BF-discovered)
    CanonicalScenario(
        scenario_id="A4",
        cohort_year=1965, cohort_month=11,
        threshold=Decimal("0.25"), ffr_spread=Decimal("0.005"), repayment_enabled=True,
        published_wr=Decimal("0.0392"), published_borrow_pct=Decimal("0.10"),
        wr_provenance="published", borrow_provenance="BF-discovered",
    ),
    # A5: 25% threshold, FFR+1.25%, repayment — B%=5% (BF-discovered)
    CanonicalScenario(
        scenario_id="A5",
        cohort_year=1965, cohort_month=11,
        threshold=Decimal("0.25"), ffr_spread=Decimal("0.0125"), repayment_enabled=True,
        published_wr=Decimal("0.0387"), published_borrow_pct=Decimal("0.05"),
        wr_provenance="published", borrow_provenance="BF-discovered",
    ),
    # A6: 25% threshold, FFR+2.75%, repayment — B%=0% (BF-discovered)
    CanonicalScenario(
        scenario_id="A6",
        cohort_year=1965, cohort_month=11,
        threshold=Decimal("0.25"), ffr_spread=Decimal("0.0275"), repayment_enabled=True,
        published_wr=Decimal("0.0375"), published_borrow_pct=Decimal("0"),
        wr_provenance="published", borrow_provenance="BF-discovered",
    ),
    # A7: 30% threshold, FFR+0.50%, repayment — B%=10% (BF-discovered)
    CanonicalScenario(
        scenario_id="A7",
        cohort_year=1965, cohort_month=11,
        threshold=Decimal("0.30"), ffr_spread=Decimal("0.005"), repayment_enabled=True,
        published_wr=Decimal("0.0394"), published_borrow_pct=Decimal("0.10"),
        wr_provenance="published", borrow_provenance="BF-discovered",
    ),
    # A8: 35% threshold, FFR+0.50%, repayment — B%=0% (BF-discovered)
    CanonicalScenario(
        scenario_id="A8",
        cohort_year=1965, cohort_month=11,
        threshold=Decimal("0.35"), ffr_spread=Decimal("0.005"), repayment_enabled=True,
        published_wr=Decimal("0.0383"), published_borrow_pct=Decimal("0"),
        wr_provenance="published", borrow_provenance="BF-discovered",
    ),
    # A9: 1929 baseline no leverage
    CanonicalScenario(
        scenario_id="A9",
        cohort_year=1929, cohort_month=9,
        threshold=None, ffr_spread=None, repayment_enabled=False,
        published_wr=Decimal("0.0361"), published_borrow_pct=Decimal("0"),
        wr_provenance="published", borrow_provenance="published",
    ),
    # A10: 1929 no timing, leverage, FFR+0.50%
    CanonicalScenario(
        scenario_id="A10",
        cohort_year=1929, cohort_month=9,
        threshold=None, ffr_spread=Decimal("0.005"), repayment_enabled=False,
        published_wr=Decimal("0.0439"), published_borrow_pct=Decimal("0.3186"),
        wr_provenance="published", borrow_provenance="published",
    ),
    # A11: 1929 35% threshold, FFR+0.50%, repayment — B%=50% (BF-discovered, best effort)
    CanonicalScenario(
        scenario_id="A11",
        cohort_year=1929, cohort_month=9,
        threshold=Decimal("0.35"), ffr_spread=Decimal("0.005"), repayment_enabled=True,
        published_wr=Decimal("0.0493"), published_borrow_pct=Decimal("0.50"),
        wr_provenance="published", borrow_provenance="BF-discovered",
    ),
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExecutionResult:
    """Result of executing one canonical scenario."""
    scenario: CanonicalScenario
    borrow_pct_used: Decimal
    total_units: int
    successful_units: int
    success_rate: Decimal
    max_ltv: Decimal
    terminal_net_worth_median: Decimal | None
    execution_time_s: float
    classification: str  # A, B, C, D, or E
    anchor_feasibility: Part52FeasibilityMetrics | None = None
    anchor_gross_survival: bool | None = None
    anchor_cohort_start: date | None = None


# ---------------------------------------------------------------------------
# Configuration builder
# ---------------------------------------------------------------------------

def _build_study_config(
    scenario: CanonicalScenario,
    borrow_pct: Decimal,
) -> StudyConfiguration:
    """Build a StudyConfiguration for one canonical scenario.

    For FFR scenarios: use the runtime FFR series plus spread via ffr_spread.
    The builder deliberately retains the full 1,739-cohort distribution for this
    diagnostic execution. Full-universe eligibility is resolved separately:
    historical-market (1,506) is primary, workbook-FFR (1,453) is sensitivity,
    distribution (1,739) is projection-only, and legacy terminal (1,452) is
    retired. Canonical acceptance is the A2/A3/A10 published-anchor surface.

    For non-FFR scenarios: use the full cohort set with no FFR.
    """
    if scenario.ffr_spread is not None:
        # Use runtime FFR + spread; no cohort filtering by FFR coverage.
        return StudyConfiguration(
            name=f"ERN_Part52_{scenario.scenario_id}",
            description=f"S6.6B canonical ERN replication: {scenario.scenario_id}",
            version="1.0",
            allocation_policy_type="ConstantAllocationPolicy",
            allocation_policy_values=(Decimal("0.75"),),
            withdrawal_policy_type="Part52WithdrawalPolicy",
            withdrawal_policy_values=(scenario.published_wr,),
            horizon_years=(HORIZON_YEARS,),
            cohort_horizon_years=COHORT_HORIZON_YEARS,
            ffr_spread=scenario.ffr_spread,
            debt_ltv_limit=LTV_LIMIT,
            debt_ltv_enforcement=False,
            debt_borrow_pct=borrow_pct,
            debt_drawdown_threshold=scenario.threshold,
        )

    return StudyConfiguration(
        name=f"ERN_Part52_{scenario.scenario_id}",
        description=f"S6.6B canonical ERN replication: {scenario.scenario_id}",
        version="1.0",
        allocation_policy_type="ConstantAllocationPolicy",
        allocation_policy_values=(Decimal("0.75"),),
        withdrawal_policy_type="Part52WithdrawalPolicy",
        withdrawal_policy_values=(scenario.published_wr,),
        horizon_years=(HORIZON_YEARS,),
        cohort_horizon_years=COHORT_HORIZON_YEARS,
        debt_interest_rate=Decimal("0.015"),
        debt_ltv_limit=LTV_LIMIT,
        debt_ltv_enforcement=False,
        debt_borrow_pct=borrow_pct,
        debt_drawdown_threshold=scenario.threshold,
    )


# ---------------------------------------------------------------------------
# Execution helpers
# ---------------------------------------------------------------------------

def _execute_study(config: StudyConfiguration) -> tuple[Any, float, BuiltStudy]:
    """Execute a study and return (result, wall_time_seconds, built_plan)."""
    t_start = time.perf_counter()
    built = build_study_plan(config, str(DATA_DIR), INITIAL_WEALTH)
    result = execute_study_plan(
        built,
        options=ExecutionOptions(
            strategy=ExecutionStrategy.AUTO,
            workers=None,  # Auto-detect
        ),
    )
    t_end = time.perf_counter()
    return result, t_end - t_start, built


def _anchor_unit_index(built: BuiltStudy, start_date: date) -> int:
    """Return the plan index of the scenario's feasibility anchor cohort."""
    for index, unit in enumerate(built.plan.units):
        if unit.cohort.start_date == start_date:
            return index
    raise AssertionError(
        f"Feasibility anchor cohort {start_date} not found in study plan"
    )


def _context_for_unit(
    built: BuiltStudy,
    unit: PlannedSimulationUnit,
) -> SimulationContext:
    """Build the production SimulationContext for one planned unit."""
    contexts = _extract_simulation_contexts(
        ResearchPlan(
            experiment_definition=built.plan.experiment_definition,
            units=(unit,),
        )
    )
    assert len(contexts) == 1
    return contexts[0]


def _extract_metrics(result: Any) -> tuple[int, int, Decimal, Decimal | None]:
    """Extract (successful, total, max_ltv, median_terminal_nw) from result."""
    sim_results = result.experiment_result.simulation_results
    total = len(sim_results)
    successful = sum(1 for r in sim_results if r.statistics.success)

    max_ltv = Decimal("0")
    terminal_nws: list[Decimal] = []
    for r in sim_results:
        for mr in r.timeline.monthly_results:
            if mr.debt_snapshot and mr.debt_snapshot.ltv > max_ltv:
                max_ltv = mr.debt_snapshot.ltv
        if r.timeline.monthly_results:
            last = r.timeline.monthly_results[-1]
            if last.debt_snapshot:
                terminal_nws.append(last.debt_snapshot.net_worth)
            else:
                # No debt: net worth = portfolio value
                portfolio_value = sum(
                    h.units * last.market_snapshot.index_levels.get(h.asset_class, Decimal("0"))
                    for h in last.portfolio.holdings
                )
                terminal_nws.append(portfolio_value)

    median_nw = None
    if terminal_nws:
        terminal_nws.sort()
        mid = len(terminal_nws) // 2
        median_nw = terminal_nws[mid]

    return successful, total, max_ltv, median_nw


# ---------------------------------------------------------------------------
# Scenario execution
# ---------------------------------------------------------------------------

def _execute_scenario(scenario: CanonicalScenario) -> ExecutionResult:
    """Execute one canonical scenario and return results."""
    # Use published borrow_pct (hardcoded with BF-discovered values)
    borrow_pct = scenario.published_borrow_pct
    assert borrow_pct is not None, f"Scenario {scenario.scenario_id} missing borrow_pct"

    # Build and execute study
    config = _build_study_config(scenario, borrow_pct)
    result, t_elapsed, built = _execute_study(config)
    successful, total, max_ltv, median_nw = _extract_metrics(result)
    success_rate = Decimal(str(successful)) / Decimal(str(total)) if total > 0 else Decimal("0")

    anchor_feasibility: Part52FeasibilityMetrics | None = None
    anchor_gross_survival: bool | None = None
    anchor_cohort_start: date | None = None
    if scenario.scenario_id in FEASIBILITY_ANCHOR_SCENARIO_IDS:
        anchor_cohort_start = date(scenario.cohort_year, scenario.cohort_month, 1)
        index = _anchor_unit_index(built, anchor_cohort_start)
        context = _context_for_unit(built, built.plan.units[index])
        anchor_feasibility = evaluate_part52_feasibility(context)
        anchor_gross_survival = (
            result.experiment_result.simulation_results[index].statistics.success
        )

    # Classify result
    # A: Published Borrow%; gross survival 100% in this test
    # B: BF-discovered Borrow%; gross survival 100% in this test
    # C: Gross survival <100%; not a feasibility classification
    # D: Explainable methodology/data difference
    if success_rate == Decimal("1"):
        classification = "A" if scenario.borrow_provenance == "published" else "B"
    else:
        classification = "C"  # Gross survival <100%; not a feasibility classification

    return ExecutionResult(
        scenario=scenario,
        borrow_pct_used=borrow_pct,
        total_units=total,
        successful_units=successful,
        success_rate=success_rate,
        max_ltv=max_ltv,
        terminal_net_worth_median=median_nw,
        execution_time_s=t_elapsed,
        classification=classification,
        anchor_feasibility=anchor_feasibility,
        anchor_gross_survival=anchor_gross_survival,
        anchor_cohort_start=anchor_cohort_start,
    )


def _assert_anchor_feasibility(
    result: ExecutionResult,
    expected_start: date,
) -> None:
    """Assert fixed-parameter feasibility for one published anchor cohort."""
    scenario_id = result.scenario.scenario_id
    assert result.anchor_cohort_start == expected_start, (
        f"{scenario_id} anchor start mismatch: "
        f"expected {expected_start}, got {result.anchor_cohort_start}"
    )
    metrics = result.anchor_feasibility
    assert metrics is not None, f"{scenario_id} feasibility anchor was not evaluated"
    assert result.anchor_gross_survival is not None
    assert metrics.gross_survival is result.anchor_gross_survival, (
        f"{scenario_id} feasibility helper and oracle disagree on gross survival: "
        f"helper={metrics.gross_survival}, oracle={result.anchor_gross_survival}"
    )
    assert metrics.gross_survival is True, (
        f"{scenario_id} anchor gross survival failed: {metrics}"
    )
    assert metrics.min_net_worth_ok is True, (
        f"{scenario_id} min net worth {metrics.min_net_worth} "
        f"is below {metrics.min_net_worth_target}"
    )
    assert metrics.final_net_worth_ok is True, (
        f"{scenario_id} final net worth {metrics.final_net_worth} "
        f"is below {metrics.final_net_worth_target}"
    )
    assert metrics.max_loan_to_portfolio_ok is True, (
        f"{scenario_id} max loan-to-portfolio {metrics.max_loan_to_portfolio} "
        f"exceeds {metrics.max_loan_to_portfolio_limit}"
    )
    assert metrics.feasible == (
        metrics.min_net_worth_ok
        and metrics.final_net_worth_ok
        and metrics.max_loan_to_portfolio_ok
    )
    assert metrics.feasible is True, (
        f"{scenario_id} three-constraint feasibility failed: {metrics}"
    )
    assert metrics.min_net_worth_target == MIN_NET_WORTH_TARGET
    assert metrics.final_net_worth_target == FINAL_NET_WORTH_TARGET
    assert metrics.max_loan_to_portfolio_limit == LTV_LIMIT


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.research_validation
class TestCanonicalERNReplication:
    """Execute and validate all 11 canonical ERN scenarios."""

    @pytest.fixture(scope="class")
    def all_results(self) -> list[ExecutionResult]:
        """Execute all canonical scenarios."""
        results = []
        for scenario in CANONICAL_SCENARIOS:
            result = _execute_scenario(scenario)
            results.append(result)
        return results

    def test_all_scenarios_execute(self, all_results: list[ExecutionResult]) -> None:
        """All 11 scenarios must produce results."""
        assert len(all_results) == len(CANONICAL_SCENARIOS)

    def test_correct_unit_count(self, all_results: list[ExecutionResult]) -> None:
        """All scenarios must produce exactly 1,739 simulation units."""
        for r in all_results:
            assert r.total_units == EXPECTED_UNITS, (
                f"{r.scenario.scenario_id}: expected {EXPECTED_UNITS} units, "
                f"got {r.total_units}"
            )

    def test_a1_baseline_reproduces(self, all_results: list[ExecutionResult]) -> None:
        """A1: 1965 baseline, WR=3.58%, no leverage → all cohorts succeed."""
        r = next(x for x in all_results if x.scenario.scenario_id == "A1")
        assert r.success_rate == Decimal("1"), (
            f"A1 REPLICATION DISCREPANCY: WR={r.scenario.published_wr}, "
            f"expected 1739/1739, got {r.successful_units}/{r.total_units}"
        )

    def test_a2_full_universe_gross_survival_diagnostic(
        self, all_results: list[ExecutionResult]
    ) -> None:
        """A2 full-universe gross survival at fixed published parameters.

        All 1,739 distribution units survive grossly. This is not
        three-constraint feasibility and not a canonical acceptance target; the
        1965-11 anchor is the acceptance surface. A failure here indicates
        cohort-level depletion on the current dataset vintage, not a failure of
        the published 1965 Solver result.
        """
        r = next(x for x in all_results if x.scenario.scenario_id == "A2")
        assert r.success_rate == Decimal("1"), (
            f"A2 gross-survival diagnostic: WR={r.scenario.published_wr}, "
            f"B%={r.borrow_pct_used}, expected 1739/1739, "
            f"got {r.successful_units}/{r.total_units}"
        )

    def test_a2_anchor_feasibility(self, all_results: list[ExecutionResult]) -> None:
        """A2 1965-11: gross survival and all three fixed-parameter constraints.

        This validates the production path at the published WR/B values. It is
        not a Solver replication and does not confirm the published optimized
        values; Solver reproduction remains deferred. Metric values are
        current-vintage diagnostics, not published acceptance constants.
        """
        r = next(x for x in all_results if x.scenario.scenario_id == "A2")
        _assert_anchor_feasibility(r, date(1965, 11, 1))

    def test_a3_full_universe_gross_survival_diagnostic(
        self, all_results: list[ExecutionResult]
    ) -> None:
        """A3 full-universe gross survival at fixed published parameters.

        All 1,739 distribution units survive grossly. This is not
        three-constraint feasibility and not a canonical acceptance target; the
        1965-11 anchor is the acceptance surface. A failure here indicates
        cohort-level depletion on the current dataset vintage, not a failure of
        the published 1965 Solver result.
        """
        r = next(x for x in all_results if x.scenario.scenario_id == "A3")
        assert r.success_rate == Decimal("1"), (
            f"A3 gross-survival diagnostic: WR={r.scenario.published_wr}, "
            f"B%={r.borrow_pct_used}, expected 1739/1739, "
            f"got {r.successful_units}/{r.total_units}"
        )

    def test_a3_anchor_feasibility(self, all_results: list[ExecutionResult]) -> None:
        """A3 1965-11: gross survival and all three fixed-parameter constraints.

        This validates the production path at the published WR/B values. It is
        not a Solver replication and does not confirm the published optimized
        values; Solver reproduction remains deferred. Metric values are
        current-vintage diagnostics, not published acceptance constants.
        """
        r = next(x for x in all_results if x.scenario.scenario_id == "A3")
        _assert_anchor_feasibility(r, date(1965, 11, 1))

    def test_a9_1929_baseline_reproduces(self, all_results: list[ExecutionResult]) -> None:
        """A9: 1929 baseline, WR=3.61%, no leverage → all cohorts succeed."""
        r = next(x for x in all_results if x.scenario.scenario_id == "A9")
        assert r.success_rate == Decimal("1"), (
            f"A9 REPLICATION DISCREPANCY: WR={r.scenario.published_wr}, "
            f"expected 1739/1739, got {r.successful_units}/{r.total_units}"
        )

    def test_a10_full_universe_gross_survival_diagnostic(
        self, all_results: list[ExecutionResult]
    ) -> None:
        """A10 full-universe gross survival at fixed published parameters.

        All 1,739 distribution units survive grossly. This is not
        three-constraint feasibility and not a canonical acceptance target; the
        1929-09 anchor is the acceptance surface. At fixed A10 parameters the
        current-vintage all-three diagnostic is 1323/1739.
        """
        r = next(x for x in all_results if x.scenario.scenario_id == "A10")
        assert r.success_rate == Decimal("1"), (
            f"A10 gross-survival diagnostic: WR={r.scenario.published_wr}, "
            f"B%={r.borrow_pct_used}, expected 1739/1739, "
            f"got {r.successful_units}/{r.total_units}"
        )

    def test_a10_anchor_feasibility(self, all_results: list[ExecutionResult]) -> None:
        """A10 1929-09: gross survival and all three fixed-parameter constraints.

        This validates the production path at the published WR/B values. It is
        not a Solver replication and does not confirm the published optimized
        values; Solver reproduction remains deferred. Metric values are
        current-vintage diagnostics, not published acceptance constants.
        """
        r = next(x for x in all_results if x.scenario.scenario_id == "A10")
        _assert_anchor_feasibility(r, date(1929, 9, 1))

    def test_bf_discovered_scenarios_produce_results(
        self, all_results: list[ExecutionResult]
    ) -> None:
        """Guard for scenarios without a recorded Borrow%; none currently exist."""
        bf_scenarios = [r for r in all_results if r.scenario.published_borrow_pct is None]
        for r in bf_scenarios:
            assert r.success_rate >= Decimal("0"), (
                f"{r.scenario.scenario_id}: invalid success rate {r.success_rate}"
            )

    def test_optimizer_provenance_recorded(
        self, all_results: list[ExecutionResult]
    ) -> None:
        """All BF-discovered scenarios must have a valid classification."""
        bf_scenarios = [r for r in all_results if r.scenario.borrow_provenance == "BF-discovered"]
        for r in bf_scenarios:
            assert r.classification in ("A", "B", "C"), (
                f"{r.scenario.scenario_id}: invalid classification {r.classification}"
            )

    def test_classification_recorded(self, all_results: list[ExecutionResult]) -> None:
        """All scenarios must have a valid classification."""
        valid_classifications = {"A", "B", "C", "D", "E"}
        for r in all_results:
            assert r.classification in valid_classifications, (
                f"{r.scenario.scenario_id}: invalid classification {r.classification}"
            )


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(results: list[ExecutionResult]) -> str:
    """Generate a canonical execution report."""
    lines = [
        "=" * 80,
        "S6.6B Stage 2 — Canonical ERN Part 52 Replication Report",
        "=" * 80,
        "",
        "EXECUTION MATRIX",
        "-" * 80,
        f"{'ID':<4} {'Cohort':<10} {'Threshold':<10} {'FFR':<8} {'WR':<8} "
        f"{'B%':<8} {'Repay':<6} {'Gross':<12} {'Class':<6} {'Time':<8}",
        "-" * 80,
    ]

    for r in results:
        s = r.scenario
        threshold_str = f"{s.threshold*100:.0f}%" if s.threshold else "none"
        ffr_str = f"+{s.ffr_spread*100:.2f}%" if s.ffr_spread else "none"
        repay_str = "ON" if s.repayment_enabled else "OFF"
        success_str = f"{r.successful_units}/{r.total_units}"
        time_str = f"{r.execution_time_s:.1f}s"

        lines.append(
            f"{s.scenario_id:<4} {s.cohort_year}-{s.cohort_month:02d:<6} "
            f"{threshold_str:<10} {ffr_str:<8} {s.published_wr*100:.2f}%{'':<2} "
            f"{r.borrow_pct_used*100:.2f}%{'':<2} {repay_str:<6} "
            f"{success_str:<12} {r.classification:<6} {time_str:<8}"
        )

    lines.extend(["", "COMPARISON SUMMARY", "-" * 80])

    for r in results:
        s = r.scenario
        lines.append(f"\n{s.scenario_id}: {s.cohort_year} cohort, threshold={s.threshold}")
        lines.append(f"  Published WR: {s.published_wr*100:.2f}% ({s.wr_provenance})")
        lines.append(f"  Borrow% used: {r.borrow_pct_used*100:.2f}% ({s.borrow_provenance})")
        lines.append(
            f"  Gross survival: {r.successful_units}/{r.total_units} ({r.success_rate})"
        )
        lines.append(f"  Max LTV: {r.max_ltv*100:.2f}%")
        lines.append(f"  Classification: {r.classification}")

    total_time = sum(r.execution_time_s for r in results)
    lines.extend([
        "",
        "=" * 80,
        f"Total execution time: {total_time:.1f}s ({total_time/60:.1f} min)",
        f"Scenarios executed: {len(results)}",
        f"Total simulation units: {sum(r.total_units for r in results):,}",
        "=" * 80,
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Standalone execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("S6.6B Stage 2 — Canonical ERN Part 52 Replication")
    print(f"Scenarios: {len(CANONICAL_SCENARIOS)}")
    print(f"Total units per scenario: {EXPECTED_UNITS:,}")
    print()

    results = []
    for scenario in CANONICAL_SCENARIOS:
        print(f"--- {scenario.scenario_id}: {scenario.cohort_year} cohort ---")
        r = _execute_scenario(scenario)
        results.append(r)
        print(f"  Borrow%: {r.borrow_pct_used*100:.2f}% ({scenario.borrow_provenance})")
        print(f"  Result: {r.successful_units}/{r.total_units} ({r.success_rate})")
        print(f"  Max LTV: {r.max_ltv*100:.2f}%")
        print(f"  Classification: {r.classification}")
        print()

    print(generate_report(results))
