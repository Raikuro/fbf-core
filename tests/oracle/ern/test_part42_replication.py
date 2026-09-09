"""Part 42 research validation — structural constants and grid dimensions.

Grid dimensions:
  5 equity_weights × 9 SWR × 1 horizon (30y) = 45 cells
  Each cell runs over rolling cohorts (1739 cohorts for ern_swr_h720).
  Total: 45 × 1739 = 78,255 simulation units.

Published anchors (from ERN Part 42, §A.3):
  - 30-year baseline failsafe (no OMY): ~3.6%
  - OMY improvement: +7.8%

These are research references, not hard gates. Discrepancies are documented
as research findings, not implementation defects.

The full grid execution (78,255 units) is not yet implemented. This module
currently contains only structural validation of grid constants and anchors.
"""

from __future__ import annotations

from tests.oracle.ern.constants import (
    PART42_ANCHOR_BASELINE_FAILSAFE,
    PART42_ANCHOR_OMY_IMPROVEMENT,
    PART42_GRID_CELLS,
    PART42_HORIZON_COUNT,
    PART42_SWR_COUNT,
    PART42_WEIGHT_COUNT,
)


class TestPart42GridStructure:
    """Part 42 grid structural constants — runs by default."""

    def test_grid_dimensions(self) -> None:
        """Verify grid dimensions match expected values."""
        assert PART42_WEIGHT_COUNT == 5
        assert PART42_SWR_COUNT == 9
        assert PART42_HORIZON_COUNT == 1
        assert PART42_GRID_CELLS == 45

    def test_published_anchors_documented(self) -> None:
        """Published anchors must be available for comparison."""
        assert PART42_ANCHOR_BASELINE_FAILSAFE == 0.036
        assert PART42_ANCHOR_OMY_IMPROVEMENT == 0.078
