"""S5.2 — Research-Plan/Grid Materialization Validation.

Validates that the generic parameter-axis plumbing correctly materializes
the intended Part 49 research grid into executable PlannedSimulationUnit
instances, without yet running the full study.

Tests:
1. exact expected unit count (54 cells × 1,739 cohorts = 93,906)
2. exact Cartesian-product coverage of all parameter axes
3. correct interest-rate propagation
4. no duplicate materialized units
5. deterministic materialization
6. per-cohort initial-portfolio isolation
7. compatibility with the existing execution path
8. regression against existing S4 behavior
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from fbf.core.domain.model.money import Currency, Money
from fbf.core.study import BuiltStudy, StudyConfiguration, build_study_plan

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "ern"
INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)

EXPECTED_EQUITY_ALLOCATIONS = (Decimal("0.75"), Decimal("1.0"))
EXPECTED_WITHDRAWAL_RATES = tuple(
    Decimal(str(v))
    for v in [0.03, 0.0325, 0.035, 0.0375, 0.04, 0.0425, 0.045, 0.0475, 0.05]
)
EXPECTED_INTEREST_RATES = (Decimal("0.0"), Decimal("0.015"), Decimal("0.03"))
EXPECTED_CELLS = 2 * 9 * 3  # = 54
EXPECTED_COHORTS = 1739
EXPECTED_UNITS = EXPECTED_CELLS * EXPECTED_COHORTS  # = 93,906


# ---------------------------------------------------------------------------
# Configuration builder
# ---------------------------------------------------------------------------


def _make_part49_config() -> StudyConfiguration:
    """Full 54-cell Part 49 grid configuration."""
    return StudyConfiguration(
        name="ERN Part 49 -- Using Leverage in Retirement",
        description="Full 54-cell Part 49 grid for S5.2 validation",
        version="2.0",
        dataset_identifier="ern_swr_h720",
        allocation_policy_type="ConstantAllocationPolicy",
        allocation_policy_values=(Decimal("0.75"), Decimal("1.0")),
        withdrawal_policy_type="Part49WithdrawalPolicy",
        withdrawal_policy_values=(
            Decimal("0.03"),
            Decimal("0.0325"),
            Decimal("0.035"),
            Decimal("0.0375"),
            Decimal("0.04"),
            Decimal("0.0425"),
            Decimal("0.045"),
            Decimal("0.0475"),
            Decimal("0.05"),
        ),
        horizon_years=(30,),
        cohort_horizon_years=60,  # ERN uses 60y horizon for cohort generation
        debt_interest_rate_values=(Decimal("0.0"), Decimal("0.015"), Decimal("0.03")),
        debt_ltv_limit=Decimal("0.75"),
        debt_ltv_enforcement=False,
        debt_loan_draw_rate=Decimal("0.01"),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def part49_built_study() -> BuiltStudy:
    """Build the full 54-cell Part 49 study plan (module-scoped for efficiency)."""
    config = _make_part49_config()
    return build_study_plan(config, str(DATA_DIR), INITIAL_WEALTH)


# ---------------------------------------------------------------------------
# Test class 1: Unit count validation
# ---------------------------------------------------------------------------


class TestUnitCount:
    """Verify exact unit count: 54 cells × 1,739 cohorts = 93,906."""

    def test_exact_unit_count(self, part49_built_study: BuiltStudy) -> None:
        """Plan must contain exactly 93,906 PlannedSimulationUnits."""
        assert len(part49_built_study.plan.units) == EXPECTED_UNITS

    def test_exact_cohort_count(self, part49_built_study: BuiltStudy) -> None:
        """Plan must cover exactly 1,739 unique cohorts."""
        cohorts = {u.cohort.start_date for u in part49_built_study.plan.units}
        assert len(cohorts) == EXPECTED_COHORTS

    def test_exact_cell_count(self, part49_built_study: BuiltStudy) -> None:
        """Plan must contain exactly 54 unique parameter configurations."""
        configs = {u.parameter_config for u in part49_built_study.plan.units}
        assert len(configs) == EXPECTED_CELLS


# ---------------------------------------------------------------------------
# Test class 2: Cartesian-product coverage
# ---------------------------------------------------------------------------


class TestCartesianCoverage:
    """Verify every parameter combination is present."""

    def test_all_equity_values_present(self, part49_built_study: BuiltStudy) -> None:
        """Every equity allocation value must appear in the grid."""
        equity_values = {
            Decimal(str(u.parameter_config.get("equity_allocation")))
            for u in part49_built_study.plan.units
        }
        assert equity_values == set(EXPECTED_EQUITY_ALLOCATIONS)

    def test_all_withdrawal_rates_present(self, part49_built_study: BuiltStudy) -> None:
        """Every withdrawal rate value must appear in the grid."""
        wr_values = {
            Decimal(str(u.parameter_config.get("withdrawal_rate")))
            for u in part49_built_study.plan.units
        }
        assert wr_values == set(EXPECTED_WITHDRAWAL_RATES)

    def test_all_interest_rates_present(self, part49_built_study: BuiltStudy) -> None:
        """Every interest rate value must appear in the grid."""
        ir_values = {
            Decimal(str(u.parameter_config.get("interest_rate")))
            for u in part49_built_study.plan.units
        }
        assert ir_values == set(EXPECTED_INTEREST_RATES)

    def test_cartesian_product_structure(self, part49_built_study: BuiltStudy) -> None:
        """Each (equity, SWR, interest_rate) combination must appear exactly 1,739 times."""
        from collections import Counter

        # Count how many times each (equity, SWR, interest_rate) triple appears
        triple_counts: Counter[tuple[Decimal, Decimal, Decimal]] = Counter()
        for u in part49_built_study.plan.units:
            equity = Decimal(str(u.parameter_config.get("equity_allocation")))
            wr = Decimal(str(u.parameter_config.get("withdrawal_rate")))
            ir = Decimal(str(u.parameter_config.get("interest_rate")))
            triple_counts[(equity, wr, ir)] += 1

        # Each triple should appear exactly 1,739 times (once per cohort)
        for triple, count in triple_counts.items():
            assert count == EXPECTED_COHORTS, (
                f"Triple {triple} appears {count} times, expected {EXPECTED_COHORTS}"
            )


# ---------------------------------------------------------------------------
# Test class 3: Interest-rate propagation
# ---------------------------------------------------------------------------


class TestInterestRatePropagation:
    """Verify interest_rate is propagated correctly to PlannedSimulationUnit."""

    def test_interest_rate_on_all_units(self, part49_built_study: BuiltStudy) -> None:
        """Every unit must have a non-None interest_rate."""
        for u in part49_built_study.plan.units:
            assert u.interest_rate is not None, (
                f"Unit {u.cohort.start_date} has None interest_rate"
            )

    def test_interest_rate_matches_config(self, part49_built_study: BuiltStudy) -> None:
        """Unit interest_rate must match its parameter configuration."""
        for u in part49_built_study.plan.units:
            config_rate = Decimal(str(u.parameter_config.get("interest_rate")))
            assert u.interest_rate == config_rate, (
                f"Unit {u.cohort.start_date}: interest_rate {u.interest_rate} "
                f"!= config {config_rate}"
            )

    def test_interest_rate_varies_across_cells(self, part49_built_study: BuiltStudy) -> None:
        """Interest rate must vary across cells (not constant)."""
        rates = {u.interest_rate for u in part49_built_study.plan.units}
        assert len(rates) == 3, f"Expected 3 distinct interest rates, got {len(rates)}"


# ---------------------------------------------------------------------------
# Test class 4: No duplicates
# ---------------------------------------------------------------------------


class TestNoDuplicates:
    """Verify no duplicate materialized units."""

    def test_no_duplicate_units(self, part49_built_study: BuiltStudy) -> None:
        """No two units should share the same (cohort, parameter_config)."""
        seen: set[tuple[Any, ...]] = set()
        for u in part49_built_study.plan.units:
            key = (u.cohort.start_date, u.parameter_config.items())
            assert key not in seen, f"Duplicate unit: {key}"
            seen.add(key)

    def test_plan_uniqueness_enforced(self, part49_built_study: BuiltStudy) -> None:
        """ResearchPlan enforces (cohort, parameter_config) uniqueness."""
        # The ResearchPlan constructor already validates this
        assert len(part49_built_study.plan.units) == EXPECTED_UNITS


# ---------------------------------------------------------------------------
# Test class 5: Deterministic materialization
# ---------------------------------------------------------------------------


class TestDeterministicMaterialization:
    """Verify materialization is deterministic and order-independent."""

    def test_second_build_produces_same_count(self) -> None:
        """Building the same config twice produces the same unit count."""
        config = _make_part49_config()
        first = build_study_plan(config, str(DATA_DIR), INITIAL_WEALTH)
        second = build_study_plan(config, str(DATA_DIR), INITIAL_WEALTH)
        assert len(first.plan.units) == len(second.plan.units)

    def test_second_build_produces_same_units(self) -> None:
        """Building the same config twice produces identical units."""
        config = _make_part49_config()
        first = build_study_plan(config, str(DATA_DIR), INITIAL_WEALTH)
        second = build_study_plan(config, str(DATA_DIR), INITIAL_WEALTH)

        for u1, u2 in zip(first.plan.units, second.plan.units, strict=True):
            assert u1.cohort.start_date == u2.cohort.start_date
            assert u1.parameter_config == u2.parameter_config
            assert u1.interest_rate == u2.interest_rate
            assert u1.horizon_months == u2.horizon_months


# ---------------------------------------------------------------------------
# Test class 6: Per-cohort portfolio isolation
# ---------------------------------------------------------------------------


class TestPortfolioIsolation:
    """Verify per-cohort portfolio construction remains isolated."""

    def test_all_portfolios_have_initial_wealth(self, part49_built_study: BuiltStudy) -> None:
        """Portfolio value at snapshot[0] must equal initial_wealth (within rounding tolerance)."""
        for u in part49_built_study.plan.units:
            dataset = u.dataset
            portfolio = u.initial_portfolio
            # Compute portfolio value at first snapshot
            total = Decimal("0")
            for holding in portfolio.holdings:
                price = dataset.snapshots[0].index_levels.get(holding.asset_class)
                if price is not None:
                    total += holding.units * price
            # Allow tiny rounding tolerance from Decimal multiplication
            diff = abs(total - INITIAL_WEALTH.amount)
            assert diff < Decimal("0.0001"), (
                f"Unit {u.cohort.start_date}: portfolio value {total} "
                f"differs from initial_wealth {INITIAL_WEALTH.amount} by {diff}"
            )

    def test_portfolios_are_distinct_objects(self, part49_built_study: BuiltStudy) -> None:
        """Each unit must have its own Portfolio instance (no sharing)."""
        portfolios = [id(u.initial_portfolio) for u in part49_built_study.plan.units]
        # All portfolio IDs should be distinct
        assert len(set(portfolios)) == EXPECTED_UNITS


# ---------------------------------------------------------------------------
# Test class 7: Fixed Part 49 parameters
# ---------------------------------------------------------------------------


class TestFixedParameters:
    """Verify fixed Part 49 parameters are correctly set on all units."""

    def test_all_units_have_ltv_limit(self, part49_built_study: BuiltStudy) -> None:
        """Every unit must have ltv_limit = 0.75."""
        for u in part49_built_study.plan.units:
            assert u.ltv_limit == Decimal("0.75")

    def test_all_units_have_ltv_enforcement_false(self, part49_built_study: BuiltStudy) -> None:
        """Every unit must have ltv_enforcement = False (ERN behavior)."""
        for u in part49_built_study.plan.units:
            assert u.ltv_enforcement is False

    def test_all_units_have_loan_draw_rate(self, part49_built_study: BuiltStudy) -> None:
        """Every unit must have loan_draw_rate = 0.01."""
        for u in part49_built_study.plan.units:
            assert u.loan_draw_rate == Decimal("0.01")

    def test_all_units_have_horizon_361(self, part49_built_study: BuiltStudy) -> None:
        """Every unit must have horizon_months = 361 (30 years + 1 base)."""
        for u in part49_built_study.plan.units:
            assert u.horizon_months == 361


# ---------------------------------------------------------------------------
# Test class 8: S4 backward compatibility
# ---------------------------------------------------------------------------


class TestS4BackwardCompatibility:
    """Verify existing S4 behavior is not broken."""

    def test_single_cell_config_still_works(self) -> None:
        """The original single-cell Part 49 config must still work."""
        config = StudyConfiguration(
            name="S4 single-cell",
            description="",
            version="",
            dataset_identifier="ern_swr_h720",
            allocation_policy_type="ConstantAllocationPolicy",
            allocation_policy_values=(Decimal("0.75"),),
            withdrawal_policy_type="Part49WithdrawalPolicy",
            withdrawal_policy_values=(Decimal("0.03"),),
            horizon_years=(30,),
            cohort_horizon_years=60,  # ERN uses 60y for cohort generation
            debt_interest_rate=Decimal("0.015"),
            debt_ltv_limit=Decimal("0.75"),
            debt_ltv_enforcement=False,
            debt_loan_draw_rate=Decimal("0.01"),
        )
        built = build_study_plan(config, str(DATA_DIR), INITIAL_WEALTH)
        # Should produce 1,739 units (1 cell × 1,739 cohorts)
        assert len(built.plan.units) == EXPECTED_COHORTS
        # Interest rate should be the scalar value
        for u in built.plan.units:
            assert u.interest_rate == Decimal("0.015")

    def test_no_debt_config_still_works(self) -> None:
        """A config without debt parameters must still work."""
        config = StudyConfiguration(
            name="No debt",
            description="",
            version="",
            dataset_identifier="ern_swr_h720",
            allocation_policy_type="ConstantAllocationPolicy",
            allocation_policy_values=(Decimal("0.75"),),
            withdrawal_policy_type="ConstantWithdrawalPolicy",
            withdrawal_policy_values=(Decimal("0.04"),),
            horizon_years=(30,),
            cohort_horizon_years=60,  # ERN uses 60y for cohort generation
        )
        built = build_study_plan(config, str(DATA_DIR), INITIAL_WEALTH)
        # Should produce 1,739 units
        assert len(built.plan.units) == EXPECTED_COHORTS
        # Interest rate should be None (no debt)
        for u in built.plan.units:
            assert u.interest_rate is None
