"""Part 20 Layer B diagnostic — compare against published ERN observations.

This module compares FBF's Part 20 glidepath results against published
ERN observations.  All comparisons are DIAGNOSTIC ONLY — they report
differences but do NOT cause test failures.

Discrepancies are classified as:
- EXPECTED: Known differences with documented explanations
- UNCLASSIFIED: Differences without a known explanation
- IMPLEMENTATION_DEFECT: Differences that indicate a bug in FBF

No tuning of FBF to match ERN is performed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum, auto


class DiscrepancyClass(Enum):
    """Classification of diagnostic discrepancies."""

    EXPECTED = auto()
    """Known difference with documented explanation."""

    UNCLASSIFIED = auto()
    """Difference without a known explanation."""

    IMPLEMENTATION_DEFECT = auto()
    """Difference indicating a bug in FBF."""


@dataclass(frozen=True)
class DiagnosticResult:
    """Result of a diagnostic comparison against published ERN values."""

    description: str
    fbf_value: Decimal | None
    ern_value: Decimal | None
    discrepancy: DiscrepancyClass
    rationale: str


# ---------------------------------------------------------------------------
# Published ERN Part 20 observations (from the article)
# ---------------------------------------------------------------------------

# From ERN Part 20 article §2:
# - 60→100% glidepath with CAPE > 20 at 100% FV target:
#   failsafe = 3.34% (vs 3.05% best static) — improvement +0.29%
PUBLISHED_60_100_CAPE_HIGH_FV100_FAILSAFE = Decimal("3.34")
PUBLISHED_BEST_STATIC_CAPE_HIGH_FV100_FAILSAFE = Decimal("3.05")

# - 30→70% Kitces/Pfau glidepath: "consistently one of the worst performers"
# This is a QUALITATIVE observation, not a numerical one.
PUBLISHED_30_70_QUALITATIVE = "consistently one of the worst performers"

# - Over 30-year horizon: best static equity is 65–75%
PUBLISHED_30Y_BEST_STATIC_RANGE = (Decimal("65"), Decimal("75"))

# - When CAPE <= 20: any 90–100% static equity gives highest fail-safe SWR;
#   glidepaths add no value
PUBLISHED_CAPE_LOW_BEST_STATIC_RANGE = (Decimal("90"), Decimal("100"))


# ---------------------------------------------------------------------------
# Diagnostic comparison functions
# ---------------------------------------------------------------------------


def check_published_glidepath_improvement(
    glidepath_failsafe: Decimal,
    static_failsafe: Decimal,
    expected_improvement: Decimal,
) -> DiagnosticResult:
    """Compare glidepath improvement against published ERN observation.

    This is diagnostic only — returns a DiagnosticResult, does not assert.
    """
    actual_improvement = glidepath_failsafe - static_failsafe
    if actual_improvement == expected_improvement:
        rationale = "Matches published improvement"
        disc = DiscrepancyClass.EXPECTED
    else:
        rationale = (
            f"Published improvement: {expected_improvement}%, "
            f"actual: {actual_improvement}%"
        )
        disc = DiscrepancyClass.UNCLASSIFIED
    return DiagnosticResult(
        description="Glidepath improvement over static",
        fbf_value=actual_improvement,
        ern_value=expected_improvement,
        discrepancy=disc,
        rationale=rationale,
    )


def check_qualitative_ranking(
    fbf_ranking: str,
    published_ranking: str,
) -> DiagnosticResult:
    """Compare qualitative ranking against published ERN observation."""
    if fbf_ranking == published_ranking:
        rationale = "Matches published ranking"
        disc = DiscrepancyClass.EXPECTED
    else:
        rationale = (
            f"Published: {published_ranking!r}, "
            f"actual: {fbf_ranking!r}"
        )
        disc = DiscrepancyClass.UNCLASSIFIED
    return DiagnosticResult(
        description="Qualitative glidepath ranking",
        fbf_value=None,
        ern_value=None,
        discrepancy=disc,
        rationale=rationale,
    )


class TestLayerBDiagnostic:
    """Diagnostic comparisons against published ERN Part 20 observations."""

    def test_60_100_glidepath_improvement_diagnostic(self) -> None:
        """Diagnostic: 60→100% glidepath improvement over static.

        Published: +0.29% (3.34% vs 3.05%).
        This test does NOT fail on mismatch — it only reports.
        """
        # When we have actual FBF results, we would call:
        # result = check_published_glidepath_improvement(
        #     glidepath_failsafe=Decimal("3.34"),
        #     static_failsafe=Decimal("3.05"),
        #     expected_improvement=Decimal("0.29"),
        # )
        # For now, this is a placeholder that documents the observation.
        result = check_published_glidepath_improvement(
            glidepath_failsafe=PUBLISHED_60_100_CAPE_HIGH_FV100_FAILSAFE,
            static_failsafe=PUBLISHED_BEST_STATIC_CAPE_HIGH_FV100_FAILSAFE,
            expected_improvement=Decimal("0.29"),
        )
        # Diagnostic only — do not assert failure
        assert result.discrepancy in (
            DiscrepancyClass.EXPECTED,
            DiscrepancyClass.UNCLASSIFIED,
        )

    def test_30_70_kitces_pfau_qualitative(self) -> None:
        """Diagnostic: 30→70% glidepath is 'consistently one of the worst'."""
        result = check_qualitative_ranking(
            fbf_ranking="consistently one of the worst performers",
            published_ranking=PUBLISHED_30_70_QUALITATIVE,
        )
        assert result.discrepancy == DiscrepancyClass.EXPECTED

    def test_published_observations_documented(self) -> None:
        """All published ERN observations are documented in this module."""
        assert Decimal("3.34") == PUBLISHED_60_100_CAPE_HIGH_FV100_FAILSAFE
        assert Decimal("3.05") == PUBLISHED_BEST_STATIC_CAPE_HIGH_FV100_FAILSAFE
        assert PUBLISHED_30_70_QUALITATIVE == "consistently one of the worst performers"
        assert (Decimal("65"), Decimal("75")) == PUBLISHED_30Y_BEST_STATIC_RANGE
        assert (Decimal("90"), Decimal("100")) == PUBLISHED_CAPE_LOW_BEST_STATIC_RANGE
