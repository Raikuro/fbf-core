"""S5.0 — Part 49 grid & dataset audit.

Verifies:
- 1,739 cohorts methodologically justified
- Grid cardinality: 2 × 9 × 3 = 54 cells
- Dataset sufficient for 30-year horizon
- Cohort coverage correct
"""

from __future__ import annotations

from decimal import Decimal

from fbf.core.domain.model.dataset import Dataset
from fbf.core.study.builder import (
    StudyConfiguration,
    _build_unified_parameter_configs,
)

# ---------------------------------------------------------------------------
# Grid axis values (from S4_ARCHITECTURAL_DESIGN_REVIEW.md C.4)
# ---------------------------------------------------------------------------

EXPECTED_EQUITY_ALLOCATIONS = (Decimal("0.75"), Decimal("1.0"))
EXPECTED_WITHDRAWAL_RATES = tuple(
    Decimal(str(v)) for v in [0.03, 0.0325, 0.035, 0.0375, 0.04, 0.0425, 0.045, 0.0475, 0.05]
)
EXPECTED_INTEREST_RATES = (Decimal("0.0"), Decimal("0.015"), Decimal("0.03"))
EXPECTED_HORIZON_YEARS = (30,)

EXPECTED_CELLS = 2 * 9 * 3  # = 54
EXPECTED_COHORTS = 1739
EXPECTED_UNITS = EXPECTED_CELLS * EXPECTED_COHORTS  # = 93,906


# ---------------------------------------------------------------------------
# Dataset audit
# ---------------------------------------------------------------------------


class TestDatasetAudit:
    """Verify dataset properties and cohort coverage."""

    def test_dataset_has_expected_snapshots(self, ern_dataset: Dataset) -> None:
        """ern_swr_h720.json should have 2,459 snapshots."""
        assert len(ern_dataset.snapshots) == 2459

    def test_dataset_start_date(self, ern_dataset: Dataset) -> None:
        """Dataset should start at 1871-01-31."""
        assert str(ern_dataset.start_date) == "1871-01-31"

    def test_dataset_end_date(self, ern_dataset: Dataset) -> None:
        """Dataset should end at 2075-11-01."""
        assert str(ern_dataset.end_date) == "2075-11-01"

    def test_dataset_has_equity_and_bond(self, ern_dataset: Dataset) -> None:
        """Dataset should contain equity and bond asset classes."""
        first_snapshot = ern_dataset.snapshots[0]
        asset_classes = set(first_snapshot.index_levels.keys())
        # Asset classes may have empty names in the dataset; check by count
        assert len(asset_classes) == 2


# ---------------------------------------------------------------------------
# Cohort audit
# ---------------------------------------------------------------------------


class TestCohortAudit:
    """Verify cohort count is methodologically justified.

    ERN uses a FIXED cohort set of 1,739 across ALL horizons (30y, 40y, 50y, 60y)
    to ensure comparability. The longest horizon (60y = 721 months) determines the
    cohort population: 2,459 snapshots - 721 + 1 = 1,739. This same set is used
    for Part 49 even though it only studies 30-year horizons.

    Source: tools/ern/reference_oracle.py (START_FIRST=1, START_LAST=1739)
    """

    def test_1739_cohorts_for_60yr_horizon(self, ern_dataset: Dataset) -> None:
        """1,739 cohorts = 2,459 snapshots - 721 months + 1 (60yr horizon)."""
        from fbf.core.study.internal.cohort.generator import CohortGenerator

        horizon_months_60y = 60 * 12 + 1  # = 721
        cohorts = CohortGenerator.generate_rolling_monthly(
            ern_dataset, horizon_months_60y
        )
        assert len(cohorts) == 1739

    def test_2099_cohorts_for_30yr_horizon(self, ern_dataset: Dataset) -> None:
        """2,099 cohorts feasible for 30-year horizon (but not used by ERN).

        ERN restricts to 1,739 cohorts for cross-horizon comparability.
        """
        from fbf.core.study.internal.cohort.generator import CohortGenerator

        horizon_months_30y = 30 * 12 + 1  # = 361
        cohorts = CohortGenerator.generate_rolling_monthly(
            ern_dataset, horizon_months_30y
        )
        assert len(cohorts) == 2099

    def test_1739_cohorts_are_ern_standard(self, ern_dataset: Dataset) -> None:
        """1,739 cohorts match ERN's fixed cohort set (Jan 1871 .. Nov 2015).

        This is the canonical ERN cohort population used across ALL studies
        (Parts 19, 20, 42, 49) and ALL horizons. The set is defined by the
        longest horizon (60y) to ensure that success rates are comparable
        across different horizon lengths.
        """
        from fbf.core.study.internal.cohort.generator import CohortGenerator

        horizon_months_60y = 60 * 12 + 1
        cohorts = CohortGenerator.generate_rolling_monthly(
            ern_dataset, horizon_months_60y
        )
        # First cohort is the base snapshot date (1871-01-31)
        assert str(cohorts[0].start_date) == "1871-01-31"
        # Last cohort is the last feasible date for 60yr horizon
        # 2,459 snapshots - 721 months = index 1,738 (0-based) = 2015-11-01
        assert str(cohorts[-1].start_date) == "2015-11-01"


# ---------------------------------------------------------------------------
# Grid cardinality audit
# ---------------------------------------------------------------------------


class TestGridCardinality:
    """Verify grid produces exactly 54 cells."""

    def test_54_parameter_configurations(self, ern_part49_config: StudyConfiguration) -> None:
        """Grid should produce exactly 54 ParameterConfigurations."""
        configs = _build_unified_parameter_configs(ern_part49_config)
        assert len(configs) == EXPECTED_CELLS

    def test_all_equity_values_present(self, ern_part49_config: StudyConfiguration) -> None:
        """Every equity allocation value should appear in the grid."""
        configs = _build_unified_parameter_configs(ern_part49_config)
        equity_values = {Decimal(str(c.get("equity_allocation"))) for c in configs}
        assert equity_values == set(EXPECTED_EQUITY_ALLOCATIONS)

    def test_all_withdrawal_rates_present(self, ern_part49_config: StudyConfiguration) -> None:
        """Every withdrawal rate value should appear in the grid."""
        configs = _build_unified_parameter_configs(ern_part49_config)
        wr_values = {Decimal(str(c.get("withdrawal_rate"))) for c in configs}
        assert wr_values == set(EXPECTED_WITHDRAWAL_RATES)

    def test_no_duplicate_configurations(self, ern_part49_config: StudyConfiguration) -> None:
        """No two ParameterConfigurations should be identical."""
        configs = _build_unified_parameter_configs(ern_part49_config)
        config_tuples = tuple(
            tuple(sorted(c.values.items())) for c in configs
        )
        assert len(set(config_tuples)) == EXPECTED_CELLS

    def test_cartesian_product_structure(self, ern_part49_config: StudyConfiguration) -> None:
        """Grid should be a proper Cartesian product of all axes."""
        configs = _build_unified_parameter_configs(ern_part49_config)
        # Each equity value should pair with each SWR value
        for equity in EXPECTED_EQUITY_ALLOCATIONS:
            for wr in EXPECTED_WITHDRAWAL_RATES:
                matching = [
                    c
                    for c in configs
                    if Decimal(str(c.get("equity_allocation"))) == equity
                    and Decimal(str(c.get("withdrawal_rate"))) == wr
                ]
                assert len(matching) == 3  # one per interest rate
