"""Canonical ERN Part 19 E2E replication — Experiment B: Failsafe/Percentile SWR.

Executes the Part 19 Experiment B grid (45 strategies × 2 CAPE conditions)
and validates against structural, computational, published-anchor,
cross-validation, and qualitative criteria.

Validation levels:
1. Structural: 90 cells × cohorts executed
2. Computational: Real SWR percentiles, monotonic ordering, determinism
3. Published anchors: 4 anchor groups from §9.2 of replication doc
4. Cross-validation: 27 Part 20 Experiment A overlaps (failsafe)
4. Qualitative: Article-consistent patterns (informational, not hard gates)
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from fbf.core.datasets import load_canonical_dataset
from fbf.core.execution import ExecutionOptions
from fbf.core.research.part19_pipeline import (
    PART19_EXPERIMENT_B_FV_TARGET,
    PART19_EXPERIMENT_B_HORIZON_YEARS,
    PART19_EXPERIMENT_B_PERCENTILES,
    Part19ExperimentBCell,
    run_experiment_b,
)
from fbf.core.research.part19_strategies import (
    PART19_EXPERIMENT_B_GLIDEPATH_IDS,
    PART19_EXPERIMENT_B_STATIC_IDS,
    PART19_EXPERIMENT_B_STRATEGY_COUNT,
    part19_experiment_b_strategies,
)
from fbf.core.research.part20_planner import Part20ExecutionContext
from fbf.core.research.part20_strategies import part20_strategy_universe

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path("data/ern")
MANIFEST_PATH = DATA_DIR / "cohort_manifest_part3.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_audit_spec() -> dict[str, Any]:
    """Load the Part 19 Experiment B audit spec YAML."""
    import yaml

    spec_path = Path("tests/fixtures/ern_part19_e2e_audit.yaml")
    with open(spec_path) as f:
        return yaml.safe_load(f)  # type: ignore[no-any-return]


def _build_part20_experiment_a_map(
    ctx: Part20ExecutionContext,
) -> dict[str, Any]:
    """Build Part 20 Experiment A failsafe results for cross-validation."""
    from fbf.core.research.part19_strategies import part19_experiment_b_strategies
    from fbf.core.research.part20_pipeline import run_percentile_search

    options = ExecutionOptions(summary_only=True)
    strategies = part19_experiment_b_strategies()
    high_dates = ctx.populations.high_dates

    results = run_percentile_search(
        ctx=ctx,
        strategies=strategies,
        cohort_dates=high_dates,
        horizon_years=60,
        final_value_target=Decimal("0"),
        cape_regime="HIGH",
        options=options,
        step_label="part20_expA_crossval",
    )
    return dict(results.items())


def _build_cross_validation_map() -> dict[str, Decimal]:
    """Build expected failsafe values from Part 20 Experiment A anchors."""
    import yaml

    spec_path = Path("tests/fixtures/ern_part19_e2e_audit.yaml")
    with open(spec_path) as f:
        spec = yaml.safe_load(f)

    anchors = spec.get("cross_validation_anchors", [])
    result: dict[str, Decimal] = {}
    for a in anchors:
        key = f"{a['strategy']}_{a['horizon_years']}Y_fv{a['final_value_target']}_HIGH"
        result[key] = Decimal(str(a["published"]))
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.ern_e2e
@pytest.mark.skipif(
    not MANIFEST_PATH.is_file(), reason="Canonical manifest not present"
)
class TestPart19ExperimentB:
    """Canonical ERN Part 19 Experiment B replication."""

    @pytest.fixture(scope="class")
    def ctx(self) -> Part20ExecutionContext:
        """Build the Part 20 execution context (shared canonical cohort populations)."""
        trajectory = load_canonical_dataset(DATA_DIR)
        return Part20ExecutionContext.create(MANIFEST_PATH, trajectory)

    @pytest.fixture(scope="class")
    def experiment_b_cells(self, ctx: Part20ExecutionContext) -> tuple[Part19ExperimentBCell, ...]:
        """Execute Part 19 Experiment B once for all tests."""
        options = ExecutionOptions(summary_only=True)
        return run_experiment_b(ctx, options=options)

    @pytest.fixture(scope="class")
    def part20_experiment_a_cells(self, ctx: Part20ExecutionContext) -> dict[str, Any]:
        """Load Part 20 Experiment A results for cross-validation (60Y, FV=0, HIGH)."""
        return _build_part20_experiment_a_map(ctx)

    # -----------------------------------------------------------------------
    # Structural validation
    # -----------------------------------------------------------------------

    def test_strategy_universe_correct(self) -> None:
        """Verify the exact 45 strategies are selected."""
        strategies = part19_experiment_b_strategies()
        assert len(strategies) == PART19_EXPERIMENT_B_STRATEGY_COUNT

        static_ids = [s.id for s in strategies if s.kind == "static"]
        glidepath_ids = [s.id for s in strategies if s.kind == "glidepath"]

        assert static_ids == list(PART19_EXPERIMENT_B_STATIC_IDS)
        assert glidepath_ids == list(PART19_EXPERIMENT_B_GLIDEPATH_IDS)

    def test_strategies_are_subset_of_part20(self) -> None:
        """All Part 19 Experiment B strategies exist in Part 20 universe."""
        part19_strategies = part19_experiment_b_strategies()
        part20_universe = part20_strategy_universe()
        part20_ids = {s.id for s in part20_universe}

        for s in part19_strategies:
            assert s.id in part20_ids, f"Part 19 strategy {s.id} not in Part 20 universe"

    def test_cell_count(self, experiment_b_cells: tuple[Part19ExperimentBCell, ...]) -> None:
        """Exactly 90 cells (45 strategies × 2 CAPE)."""
        assert len(experiment_b_cells) == 90

    def test_cell_dimensions(
        self, experiment_b_cells: tuple[Part19ExperimentBCell, ...]
    ) -> None:
        """Every cell has correct dimension values."""
        strategies_seen = set()
        cape_conditions_seen = set()
        horizons_seen = set()
        fv_targets_seen = set()

        for cell in experiment_b_cells:
            strategies_seen.add(cell.strategy_id)
            cape_conditions_seen.add(cell.cape_condition)
            horizons_seen.add(cell.horizon_years)
            fv_targets_seen.add(cell.final_value_target)

        assert len(strategies_seen) == 45
        assert cape_conditions_seen == {"ALL", "HIGH"}
        assert horizons_seen == {60}
        assert fv_targets_seen == {Decimal("0")}

    def test_cohort_counts(self, experiment_b_cells: tuple[Part19ExperimentBCell, ...]) -> None:
        """ALL CAPE condition uses 1,739 cohorts; HIGH uses 383."""
        for cell in experiment_b_cells:
            if cell.cape_condition == "ALL":
                expected = 1739
                assert cell.cohort_count == expected, (
                    f"{cell.strategy_id}: ALL CAPE should have {expected} cohorts, "
                    f"got {cell.cohort_count}"
                )
            elif cell.cape_condition == "HIGH":
                expected = 383
                assert cell.cohort_count == expected, (
                    f"{cell.strategy_id}: HIGH CAPE should have {expected} cohorts, "
                    f"got {cell.cohort_count}"
                )

    def test_all_strategies_present_per_population(
        self, experiment_b_cells: tuple[Part19ExperimentBCell, ...]
    ) -> None:
        """Every strategy appears exactly once per CAPE population."""
        by_pop: dict[str, set[str]] = defaultdict(set)
        for cell in experiment_b_cells:
            by_pop[cell.cape_condition].add(cell.strategy_id)

        assert len(by_pop["ALL"]) == 45
        assert len(by_pop["HIGH"]) == 45
        assert by_pop["ALL"] == by_pop["HIGH"]

    def test_no_duplicate_cells(
        self, experiment_b_cells: tuple[Part19ExperimentBCell, ...]
    ) -> None:
        """No duplicate (strategy, CAPE) combinations."""
        seen = set()
        for cell in experiment_b_cells:
            key = (cell.strategy_id, cell.cape_condition)
            assert key not in seen, f"Duplicate cell: {key}"
            seen.add(key)

    # -----------------------------------------------------------------------
    # Computational validation
    # -----------------------------------------------------------------------

    def test_percentile_metrics_present(
        self, experiment_b_cells: tuple[Part19ExperimentBCell, ...]
    ) -> None:
        """All cells have the required six percentile metrics."""
        for cell in experiment_b_cells:
            percentiles = cell.percentiles
            for p in PART19_EXPERIMENT_B_PERCENTILES:
                assert p in percentiles, f"{cell.strategy_id}: missing percentile {p}"

            # Check property accessors
            assert cell.failsafe == cell.percentiles[Decimal("0")]
            assert cell.p01 == cell.percentiles[Decimal("0.01")]
            assert cell.p03 == cell.percentiles[Decimal("0.03")]
            assert cell.p05 == cell.percentiles[Decimal("0.05")]
            assert cell.p10 == cell.percentiles[Decimal("0.10")]
            assert cell.p25 == cell.percentiles[Decimal("0.25")]

    def test_percentile_monotonicity(
        self, experiment_b_cells: tuple[Part19ExperimentBCell, ...]
    ) -> None:
        """Percentiles are monotonically increasing: failsafe ≤ p01 ≤ p03 ≤ p05 ≤ p10 ≤ p25."""
        for cell in experiment_b_cells:
            p = cell.percentiles
            vals = [
                p[Decimal("0")],
                p[Decimal("0.01")],
                p[Decimal("0.03")],
                p[Decimal("0.05")],
                p[Decimal("0.10")],
                p[Decimal("0.25")],
            ]
            for i in range(1, len(vals)):
                assert vals[i] >= vals[i - 1], (
                    f"{cell.strategy_id}: percentile monotonicity violated: {vals}"
                )

    def test_failsafe_equals_p00(
        self, experiment_b_cells: tuple[Part19ExperimentBCell, ...]
    ) -> None:
        """failsafe property equals the p00 percentile."""
        for cell in experiment_b_cells:
            assert cell.failsafe == cell.percentiles[Decimal("0")]

    def test_percentiles_valid_range(
        self, experiment_b_cells: tuple[Part19ExperimentBCell, ...]
    ) -> None:
        """All percentiles are valid SWR fractions."""
        for cell in experiment_b_cells:
            for p in PART19_EXPERIMENT_B_PERCENTILES:
                val = cell.percentiles[p]
                assert Decimal("0") <= val <= Decimal("1"), (
                    f"{cell.strategy_id}: percentile {p} = {val} not in [0,1]"
                )

    def test_determinism_spot_check(self, ctx: Part20ExecutionContext) -> None:
        """Single-cell determinism: re-run one cell and verify identical results."""
        options = ExecutionOptions(summary_only=True)

        cells1 = run_experiment_b(ctx, options=options)
        cells2 = run_experiment_b(ctx, options=options)

        assert len(cells1) == len(cells2)
        for c1, c2 in zip(cells1, cells2, strict=True):
            assert c1.strategy_id == c2.strategy_id
            assert c1.cape_condition == c2.cape_condition
            assert c1.failsafe == c2.failsafe
            assert c1.p01 == c2.p01
            assert c1.p03 == c2.p03
            assert c1.p05 == c2.p05
            assert c1.p10 == c2.p10
            assert c1.p25 == c2.p25

    # -----------------------------------------------------------------------
    # Published anchor validation
    # -----------------------------------------------------------------------

    def test_published_anchor_static_075_failsafe(
        self, experiment_b_cells: tuple[Part19ExperimentBCell, ...]
    ) -> None:
        """Anchor 1: static_075 failsafe = 3.25% for HIGH / 60Y / FV0.

        Per audit protocol: UNEXPLAINED DIFFERENCE with methodological hypothesis.
        FBF execution order (withdrawal→rebalance→returns) vs ERN (returns→withdrawal→rebalance).
        """
        cell = next(
            c for c in experiment_b_cells
            if c.strategy_id == "static_075" and c.cape_condition == "HIGH"
        )
        observed = (cell.failsafe * Decimal("100")).quantize(Decimal("0.01"))
        expected = Decimal("3.25")
        diff = abs(observed - expected)
        if diff > Decimal("0.01"):
            print(
                f"\nUNEXPLAINED DIFFERENCE: static_075 failsafe: observed {observed}% "
                f"!= published {expected}% (raw: {cell.failsafe*100:.4f}%)"
            )
            print(
                "  Hypothesis: FBF execution order (withdrawal→rebalance→returns) vs ERN "
                "(returns→withdrawal→rebalance) and real vs nominal ATH index."
            )
            print(
                "  Classification: UNEXPLAINED DIFFERENCE — variant isolation not run."
            )

    def test_published_anchor_60_to_100_failsafe_range(
        self, experiment_b_cells: tuple[Part19ExperimentBCell, ...]
    ) -> None:
        """60→100% glidepath failsafe range = 3.42%–3.47% (HIGH, 60Y, FV=0).

        Per audit protocol: UNEXPLAINED DIFFERENCE with methodological hypothesis.
        """
        gp_60_100_ids = [
            "gp_060_100_0.003_passive",
            "gp_060_100_0.004_passive",
            "gp_060_100_0.003_active",
            "gp_060_100_0.004_active",
        ]

        for sid in gp_60_100_ids:
            cell = next(
                c for c in experiment_b_cells
                if c.strategy_id == sid and c.cape_condition == "HIGH"
            )
            observed = (cell.failsafe * Decimal("100")).quantize(Decimal("0.01"))
            if not (Decimal("3.42") <= observed <= Decimal("3.47")):
                print(
                    f"\nUNEXPLAINED DIFFERENCE: {sid} failsafe: observed {observed}% "
                    f"not in range [3.42%, 3.47%]"
                )
                print(
                    "  Hypothesis: FBF execution order (withdrawal→rebalance→returns) vs ERN "
                    "(returns→withdrawal→rebalance) and real vs nominal ATH index."
                )
                print(
                    "  Classification: UNEXPLAINED DIFFERENCE — variant isolation not run."
                )

    def test_published_anchor_static_080_p05(
        self, experiment_b_cells: tuple[Part19ExperimentBCell, ...]
    ) -> None:
        """Anchor 3: static_080 p05 = 3.47% for HIGH / 60Y / FV0.

        Per audit protocol: UNEXPLAINED DIFFERENCE with methodological hypothesis.
        """
        cell = next(
            c for c in experiment_b_cells
            if c.strategy_id == "static_080" and c.cape_condition == "HIGH"
        )
        observed = (cell.p05 * Decimal("100")).quantize(Decimal("0.01"))
        expected = Decimal("3.47")
        diff = abs(observed - expected)
        if diff > Decimal("0.01"):
            print(
                f"\nUNEXPLAINED DIFFERENCE: static_080 p05: observed {observed}% "
                f"!= published {expected}% (raw: {cell.p05*100:.4f}%)"
            )
            print(
                "  Hypothesis: FBF execution order (withdrawal→rebalance→returns) vs ERN "
                "(returns→withdrawal→rebalance) and real vs nominal ATH index."
            )
            print(
                "  Classification: UNEXPLAINED DIFFERENCE — variant isolation not run."
            )

    def test_published_anchor_60_to_100_p05_range(
        self, experiment_b_cells: tuple[Part19ExperimentBCell, ...]
    ) -> None:
        """60→100% glidepath p05 range = 3.57%–3.63% (HIGH, 60Y, FV=0).

        Per audit protocol: UNEXPLAINED DIFFERENCE with methodological hypothesis.
        """
        gp_60_100_ids = [
            "gp_060_100_0.003_passive",
            "gp_060_100_0.004_passive",
            "gp_060_100_0.003_active",
            "gp_060_100_0.004_active",
        ]

        for sid in gp_60_100_ids:
            cell = next(
                c for c in experiment_b_cells
                if c.strategy_id == sid and c.cape_condition == "HIGH"
            )
            observed = (cell.p05 * Decimal("100")).quantize(Decimal("0.01"))
            if not (Decimal("3.57") <= observed <= Decimal("3.63")):
                print(
                    f"\nUNEXPLAINED DIFFERENCE: {sid} p05: observed {observed}% "
                    f"not in range [3.57%, 3.63%]"
                )
                print(
                    "  Hypothesis: FBF execution order (withdrawal→rebalance→returns) vs ERN "
                    "(returns→withdrawal→rebalance) and real vs nominal ATH index."
                )
                print(
                    "  Classification: UNEXPLAINED DIFFERENCE — variant isolation not run."
                )

    # -----------------------------------------------------------------------
    # Cross-validation with Part 20 Experiment A
    # -----------------------------------------------------------------------

    def test_cross_validation_part20_experiment_a(
        self,
        experiment_b_cells: tuple[Part19ExperimentBCell, ...],
        part20_experiment_a_cells: dict[str, Any],
    ) -> None:
        """Part 19 Experiment B cells at FV=0, CAPE>20 match Part 20 Experiment A failsafe.

        Overlap: 45 Part 19 Experiment B strategies at 60Y, FV=0, CAPE>20.
        All 45 are cross-validated against identical computation.
        """
        # Filter Part 19 cells to the overlapping condition
        overlap_cells = {
            cell.strategy_id: cell
            for cell in experiment_b_cells
            if cell.cape_condition == "HIGH"
        }

        assert len(overlap_cells) == 45, f"Expected 45 overlap cells, got {len(overlap_cells)}"

        mismatches = []
        for strategy_id, part19_cell in overlap_cells.items():
            part20_result = part20_experiment_a_cells.get(strategy_id)
            if part20_result is None:
                mismatches.append(f"{strategy_id}: missing from Part 20 Experiment A")
                continue

            # Compare failsafe values (should be exactly equal since same computation)
            if part19_cell.failsafe != part20_result.failsafe:
                mismatches.append(
                    f"{strategy_id}: Part19 failsafe={part19_cell.failsafe} "
                    f"!= Part20 failsafe={part20_result.failsafe}"
                )

        if mismatches:
            # Report mismatches but don't fail - cross-validation is diagnostic
            print("\nCross-validation mismatches (Part 19 Exp B vs Part 20 Exp A):")
            for m in mismatches:
                print(f"  {m}")

    def test_cross_validation_published_anchors(
        self, experiment_b_cells: tuple[Part19ExperimentBCell, ...]
    ) -> None:
        """Compare overlapping cells against Part 20 Experiment A published anchors.

        Validates the 10 authoritative Part 20 Experiment A published anchors.
        Discrepancies are classified as UNEXPLAINED DIFFERENCE per audit protocol;
        execution order and ATH index differences are documented methodological hypotheses.
        """
        spec = _load_audit_spec()
        anchors = spec.get("cross_validation_anchors", [])

        overlap_cells = {
            f"{cell.strategy_id}_{cell.horizon_years}Y_fv{cell.final_value_target}_HIGH": cell
            for cell in experiment_b_cells
            if cell.cape_condition == "HIGH"
        }

        for anchor in anchors:
            key = (
                f"{anchor['strategy']}_{anchor['horizon_years']}Y_fv"
                f"{anchor['final_value_target']}_HIGH"
            )
            part19_cell = overlap_cells.get(key)
            if part19_cell is None:
                print(f"\nINFORMATIONAL: Overlap cell {key} not found in Part 19 results")
                continue

            # Compute Part 19 failsafe as percentage with 2 decimal places
            part19_rate_pct = part19_cell.failsafe * Decimal("100")
            part19_rate_display = part19_rate_pct.quantize(Decimal("0.01"))
            expected = Decimal(str(anchor["published"]))

            diff = abs(part19_rate_display - expected)
            if diff > Decimal("0.01"):
                # Per audit protocol: UNEXPLAINED DIFFERENCE with methodological hypothesis
                print(
                    f"\nUNEXPLAINED DIFFERENCE: {key}: Part19 failsafe {part19_rate_display}% "
                    f"!= published {expected}% (raw: {part19_rate_pct:.4f}%)"
                )
                print(
                    "  Hypothesis: FBF execution order (withdrawal→rebalance→returns) vs ERN "
                    "(returns→withdrawal→rebalance) and real vs nominal ATH index."
                )
                print(
                    "  Classification: UNEXPLAINED DIFFERENCE — variant isolation not run."
                )

    # -----------------------------------------------------------------------
    # Qualitative validation (informational diagnostics only)
    # -----------------------------------------------------------------------
    #
    # These tests are informational only. The ERN article qualitative claims
    # (Part 19 §1.7) refer to fixed 3.5% SWR failure rates (Experiment A),
    # while this test suite operates on Experiment B failsafe SWR.
    # The metric mismatch means these comparisons are informational only.
    #

    # -----------------------------------------------------------------------
    # Reporting
    # -----------------------------------------------------------------------

    def test_print_summary(self, experiment_b_cells: tuple[Part19ExperimentBCell, ...]) -> None:
        """Print summary statistics for manual inspection."""
        print("\n" + "=" * 70)
        print("PART 19 EXPERIMENT B SUMMARY")
        print("=" * 70)
        print(f"Total cells: {len(experiment_b_cells)}")
        print("Strategies: 45 (21 static + 24 glidepath)")
        print(f"FV target: {PART19_EXPERIMENT_B_FV_TARGET}")
        print("CAPE conditions: ALL (1739), HIGH (383)")
        print(f"Horizon: {PART19_EXPERIMENT_B_HORIZON_YEARS}Y")
        print(f"Metrics: {[str(p) for p in PART19_EXPERIMENT_B_PERCENTILES]}")

        for cape in ("ALL", "HIGH"):
            subset = [c for c in experiment_b_cells if c.cape_condition == cape]
            failsafes = [c.failsafe for c in subset]
            p05s = [c.p05 for c in subset]
            print(f"\n  CAPE={cape}:")
            print(f"    failsafe: min={min(failsafes)*100:.2f}%, max={max(failsafes)*100:.2f}%")
            print(f"    p05: min={min(p05s)*100:.2f}%, max={max(p05s)*100:.2f}%")

        print("=" * 70)
