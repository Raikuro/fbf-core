"""Unit tests for Part 19 Experiment B runner logic (no execution)."""

from __future__ import annotations

from decimal import Decimal

from fbf.core.research.part19_pipeline import (
    PART19_EXPERIMENT_B_CAPE_CONDITIONS,
    PART19_EXPERIMENT_B_FV_TARGET,
    PART19_EXPERIMENT_B_HORIZON_YEARS,
    PART19_EXPERIMENT_B_PERCENTILES,
    Part19ExperimentBCell,
)
from fbf.core.research.part20_aggregation import percentile_swrs, swr_at_failure_probability


def test_part19_experiment_b_constants() -> None:
    """Verify Experiment B constants match expectations."""
    assert PART19_EXPERIMENT_B_HORIZON_YEARS == 60
    assert Decimal("0") == PART19_EXPERIMENT_B_FV_TARGET
    assert PART19_EXPERIMENT_B_CAPE_CONDITIONS == ("ALL", "HIGH")

    # Check percentile probabilities
    expected = (Decimal("0"), Decimal("0.01"), Decimal("0.03"),
                Decimal("0.05"), Decimal("0.10"), Decimal("0.25"))
    assert expected == PART19_EXPERIMENT_B_PERCENTILES


def test_percentile_swrs_computation() -> None:
    """Test percentile SWR computation directly."""
    # Sample per-cohort SWRs
    per_cohort_swrs = (
        Decimal("0.02"), Decimal("0.025"), Decimal("0.03"),
        Decimal("0.035"), Decimal("0.04"), Decimal("0.045"),
        Decimal("0.05"), Decimal("0.055"), Decimal("0.06"),
        Decimal("0.065"), Decimal("0.07"),
    )

    percentiles = percentile_swrs(per_cohort_swrs)

    # Check all 6 percentiles present
    expected_probs = (Decimal("0"), Decimal("0.01"), Decimal("0.03"),
                      Decimal("0.05"), Decimal("0.10"), Decimal("0.25"))
    for p in expected_probs:
        assert p in percentiles

    # Check monotonicity
    vals = [percentiles[p] for p in expected_probs]
    for i in range(1, len(vals)):
        assert vals[i] >= vals[i - 1]


def test_swr_at_failure_probability() -> None:
    """Test the core swr_at_failure_probability function."""
    sorted_swrs = tuple(Decimal(str(i)) / Decimal("100") for i in range(2, 12))
    # 0.02, 0.03, 0.04, ..., 0.11

    # failsafe (p=0) should be minimum
    failsafe = swr_at_failure_probability(sorted_swrs, Decimal("0"))
    assert failsafe == Decimal("0.02")

    # p05 (index floor(0.05 * 10) = 0)
    p05 = swr_at_failure_probability(sorted_swrs, Decimal("0.05"))
    assert p05 == Decimal("0.02")

    # p10 (index floor(0.10 * 10) = 1)
    p10 = swr_at_failure_probability(sorted_swrs, Decimal("0.10"))
    assert p10 == Decimal("0.03")

    # p25 (index floor(0.25 * 10) = 2)
    p25 = swr_at_failure_probability(sorted_swrs, Decimal("0.25"))
    assert p25 == Decimal("0.04")


def test_part19_experiment_b_cell_model() -> None:
    """Test the Part19ExperimentBCell model structure."""
    # Create a mock cell with sample data
    per_cohort = tuple(Decimal(str(i)) / Decimal("100") for i in range(2, 12))

    cell = Part19ExperimentBCell(
        strategy_id="static_080",
        horizon_years=60,
        final_value_target=Decimal("0"),
        cape_condition="HIGH",
        cohort_count=383,
        per_cohort_swrs=per_cohort,
    )

    # Check basic properties
    assert cell.strategy_id == "static_080"
    assert cell.horizon_years == 60
    assert cell.final_value_target == Decimal("0")
    assert cell.cape_condition == "HIGH"
    assert cell.cohort_count == 383

    # Check percentile properties
    p = cell.percentiles
    assert cell.failsafe == p[Decimal("0")]
    assert cell.p01 == p[Decimal("0.01")]
    assert cell.p03 == p[Decimal("0.03")]
    assert cell.p05 == p[Decimal("0.05")]
    assert cell.p10 == p[Decimal("0.10")]
    assert cell.p25 == p[Decimal("0.25")]

    # Check monotonicity
    vals = [cell.failsafe, cell.p01, cell.p03, cell.p05, cell.p10, cell.p25]
    for i in range(1, len(vals)):
        assert vals[i] >= vals[i - 1]

    # failsafe should equal p00
    assert cell.failsafe == p[Decimal("0")]


def test_experiment_b_dimension_constants() -> None:
    """Verify Experiment B dimension constants."""

    from fbf.core.research.part19_strategies import (
        PART19_EXPERIMENT_B_STRATEGY_COUNT,
    )

    # Just verify the strategy count matches expected
    assert PART19_EXPERIMENT_B_STRATEGY_COUNT == 45

    # Verify constants
    assert PART19_EXPERIMENT_B_HORIZON_YEARS == 60
    assert Decimal("0") == PART19_EXPERIMENT_B_FV_TARGET
    assert PART19_EXPERIMENT_B_CAPE_CONDITIONS == ("ALL", "HIGH")

    # 90 cells = 45 strategies × 2 CAPE conditions
    assert 45 * 2 == 90

    # 156,510 units = 90 cells × 1,739 cohorts
    assert 90 * 1739 == 156510
