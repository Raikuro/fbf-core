"""Canonical ERN Part 19 E2E replication — Experiment A: Fixed 3.5% SWR Failure Rates.

Executes the Part 19 Experiment A grid (27 strategies × 3 FV targets × 2 CAPE conditions)
and validates against structural, computational, and cross-validation criteria.

Validation levels:
1. Structural: 162 cells × 1,739 cohorts executed
2. Computational: Real failure rates in [0,1], variation across grid, determinism
3. Cross-validation: 27 overlapping cells match Part 20 Experiment C (3.5% SWR, 60Y, FV=0, CAPE>20)
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
    PART19_EXPERIMENT_A_FV_TARGETS,
    PART19_EXPERIMENT_A_HORIZON_YEARS,
    PART19_EXPERIMENT_A_SWR,
    Part19ExperimentACell,
    run_experiment_a,
)
from fbf.core.research.part19_strategies import (
    PART19_EXPERIMENT_A_GLIDEPATH_IDS,
    PART19_EXPERIMENT_A_STATIC_IDS,
    PART19_EXPERIMENT_A_STRATEGY_COUNT,
    part19_experiment_a_strategies,
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
    """Load the Part 19 Experiment A audit spec YAML."""
    import yaml

    spec_path = Path("tests/fixtures/ern_part19_experiment_a_e2e_audit.yaml")
    with open(spec_path) as f:
        return yaml.safe_load(f)  # type: ignore[no-any-return]


def _build_cross_validation_map() -> dict[str, Decimal]:
    """Build expected failure rates from Part 20 Experiment C anchors."""
    spec = _load_audit_spec()
    anchors = spec.get("cross_validation_anchors", [])
    result: dict[str, Decimal] = {}
    for a in anchors:
        key = f"{a['strategy']}_{a['horizon_years']}Y_fv{a['final_value_target']}_HIGH"
        result[key] = Decimal(str(a["published_failure_rate"]))
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.ern_e2e
@pytest.mark.skipif(
    not MANIFEST_PATH.is_file(), reason="Canonical manifest not present"
)
class TestPart19ExperimentA:
    """Canonical ERN Part 19 Experiment A replication."""

    @pytest.fixture(scope="class")
    def ctx(self) -> Part20ExecutionContext:
        """Build the Part 20 execution context (shared canonical cohort populations)."""
        trajectory = load_canonical_dataset(DATA_DIR)
        return Part20ExecutionContext.create(MANIFEST_PATH, trajectory)

    @pytest.fixture(scope="class")
    def experiment_a_cells(self, ctx: Part20ExecutionContext) -> tuple[Part19ExperimentACell, ...]:
        """Execute Part 19 Experiment A once for all tests."""
        options = ExecutionOptions(summary_only=True)
        return run_experiment_a(ctx, options=options)

    @pytest.fixture(scope="class")
    def part20_experiment_c_cells(self, ctx: Part20ExecutionContext) -> dict[str, Any]:
        """Load Part 20 Experiment C results for cross-validation (3.5% SWR, 60Y, FV=0, HIGH)."""
        # Reuse the Part 20 fixed-SWR grid runner for the specific overlapping cells
        from fbf.core.research.part19_strategies import part19_experiment_a_strategies
        from fbf.core.research.part20_pipeline import run_fixed_swr_grid

        options = ExecutionOptions(summary_only=True)
        strategies = part19_experiment_a_strategies()
        high_dates = ctx.populations.high_dates

        cells = run_fixed_swr_grid(
            ctx=ctx,
            strategies=strategies,
            cohort_dates=high_dates,
            horizon_years=60,
            withdrawal_rates=(PART19_EXPERIMENT_A_SWR,),
            final_value_target=Decimal("0"),
            population="HIGH",
            options=options,
        )

        # Index by strategy_id for easy lookup
        return {c.strategy_id: c for c in cells}

    # -----------------------------------------------------------------------
    # Structural validation
    # -----------------------------------------------------------------------

    def test_strategy_universe_correct(self) -> None:
        """Verify the exact 27 strategies are selected."""
        strategies = part19_experiment_a_strategies()
        assert len(strategies) == PART19_EXPERIMENT_A_STRATEGY_COUNT

        static_ids = [s.id for s in strategies if s.kind == "static"]
        glidepath_ids = [s.id for s in strategies if s.kind == "glidepath"]

        assert static_ids == list(PART19_EXPERIMENT_A_STATIC_IDS)
        assert glidepath_ids == list(PART19_EXPERIMENT_A_GLIDEPATH_IDS)

    def test_strategies_are_subset_of_part20(self) -> None:
        """All Part 19 Experiment A strategies exist in Part 20 universe."""
        part19_strategies = part19_experiment_a_strategies()
        part20_universe = part20_strategy_universe()
        part20_ids = {s.id for s in part20_universe}

        for s in part19_strategies:
            assert s.id in part20_ids, f"Part 19 strategy {s.id} not in Part 20 universe"

    def test_cell_count(self, experiment_a_cells: tuple[Part19ExperimentACell, ...]) -> None:
        """Exactly 162 cells (27 strategies × 3 FV × 2 CAPE)."""
        assert len(experiment_a_cells) == 162

    def test_cell_dimensions(self, experiment_a_cells: tuple[Part19ExperimentACell, ...]) -> None:
        """Every cell has correct dimension values."""
        strategies_seen = set()
        fv_targets_seen = set()
        cape_conditions_seen = set()
        horizons_seen = set()
        swrs_seen = set()

        for cell in experiment_a_cells:
            strategies_seen.add(cell.strategy_id)
            fv_targets_seen.add(cell.final_value_target)
            cape_conditions_seen.add(cell.cape_condition)
            horizons_seen.add(cell.horizon_years)
            swrs_seen.add(cell.withdrawal_rate)

        assert len(strategies_seen) == 27
        assert fv_targets_seen == {Decimal("0"), Decimal("0.5"), Decimal("1")}
        assert cape_conditions_seen == {"ALL", "HIGH"}
        assert horizons_seen == {60}
        assert swrs_seen == {Decimal("0.035")}

    def test_cohort_counts(self, experiment_a_cells: tuple[Part19ExperimentACell, ...]) -> None:
        """ALL CAPE condition uses 1,739 cohorts; HIGH uses 383."""
        for cell in experiment_a_cells:
            if cell.cape_condition == "ALL":
                expected = 1739
                assert cell.total_cohorts == expected, (
                    f"{cell.strategy_id}: ALL CAPE should have {expected} cohorts, "
                    f"got {cell.total_cohorts}"
                )
            elif cell.cape_condition == "HIGH":
                expected = 383
                assert cell.total_cohorts == expected, (
                    f"{cell.strategy_id}: HIGH CAPE should have {expected} cohorts, "
                    f"got {cell.total_cohorts}"
                )

    def test_all_strategies_present_per_cell(
        self, experiment_a_cells: tuple[Part19ExperimentACell, ...]
    ) -> None:
        """Every strategy appears exactly once per FV×CAPE combination."""
        by_combo: dict[tuple[Decimal, str], set[str]] = defaultdict(set)
        for cell in experiment_a_cells:
            by_combo[(cell.final_value_target, cell.cape_condition)].add(cell.strategy_id)

        for combo, strategies in by_combo.items():
            assert len(strategies) == 27, (
                f"Combo {combo}: {len(strategies)} strategies, expected 27"
            )

    # -----------------------------------------------------------------------
    # Computational validation
    # -----------------------------------------------------------------------

    def test_failure_rates_valid_range(
        self, experiment_a_cells: tuple[Part19ExperimentACell, ...]
    ) -> None:
        """All failure rates are valid probabilities in [0, 1]."""
        for cell in experiment_a_cells:
            rate = cell.failure_rate
            assert Decimal("0") <= rate <= Decimal("1"), (
                f"{cell.strategy_id}: failure_rate={rate} not in [0,1]"
            )

    def test_failure_rates_vary(
        self, experiment_a_cells: tuple[Part19ExperimentACell, ...]
    ) -> None:
        """Failure rates vary across the grid (not all identical)."""
        rates = [cell.failure_rate for cell in experiment_a_cells]
        unique_rates = set(rates)
        assert len(unique_rates) > 1, (
            f"All {len(experiment_a_cells)} cells have identical failure rate"
        )

    def test_not_all_pass_or_fail(
        self, experiment_a_cells: tuple[Part19ExperimentACell, ...]
    ) -> None:
        """Not trivially all-pass (rate=0) or all-fail (rate=1)."""
        rates = [cell.failure_rate for cell in experiment_a_cells]
        min_rate = min(rates)
        max_rate = max(rates)
        assert min_rate < Decimal("1"), "All cells have failure_rate=1 (all fail)"
        assert max_rate > Decimal("0"), "All cells have failure_rate=0 (all pass)"

    def test_determinism_spot_check(self, ctx: Part20ExecutionContext) -> None:
        """Single-cell determinism: re-run one cell and verify identical results."""
        from fbf.core.research.part19_strategies import part19_experiment_a_strategies
        from fbf.core.research.part20_pipeline import run_fixed_swr_grid

        options = ExecutionOptions(summary_only=True)
        strategies = part19_experiment_a_strategies()
        probe_strategy = next(s for s in strategies if s.id == "static_080")
        all_dates = ctx.populations.all_dates

        # Run twice
        cells1 = run_fixed_swr_grid(
            ctx=ctx,
            strategies=(probe_strategy,),
            cohort_dates=all_dates,
            horizon_years=PART19_EXPERIMENT_A_HORIZON_YEARS,
            withdrawal_rates=(PART19_EXPERIMENT_A_SWR,),
            final_value_target=Decimal("0"),
            population="ALL",
            options=options,
        )
        cells2 = run_fixed_swr_grid(
            ctx=ctx,
            strategies=(probe_strategy,),
            cohort_dates=all_dates,
            horizon_years=PART19_EXPERIMENT_A_HORIZON_YEARS,
            withdrawal_rates=(PART19_EXPERIMENT_A_SWR,),
            final_value_target=Decimal("0"),
            population="ALL",
            options=options,
        )

        assert cells1[0].failures == cells2[0].failures
        assert cells1[0].total_cohorts == cells2[0].total_cohorts

    # -----------------------------------------------------------------------
    # Cross-validation with Part 20 Experiment C
    # -----------------------------------------------------------------------

    def test_cross_validation_part20_experiment_c(
        self,
        experiment_a_cells: tuple[Part19ExperimentACell, ...],
        part20_experiment_c_cells: dict[str, Any],
    ) -> None:
        """Part 19 Experiment A cells at FV=0, CAPE>20 match Part 20 Experiment C at 3.5% SWR.

        Overlap: 27 Part 19 strategies at 60Y, FV=0, CAPE>20, 3.5% SWR.
        """
        # Filter Part 19 cells to the overlapping condition
        overlap_cells = {
            cell.strategy_id: cell
            for cell in experiment_a_cells
            if cell.final_value_target == Decimal("0") and cell.cape_condition == "HIGH"
        }

        assert len(overlap_cells) == 27, f"Expected 27 overlap cells, got {len(overlap_cells)}"

        mismatches = []
        for strategy_id, part19_cell in overlap_cells.items():
            part20_cell = part20_experiment_c_cells.get(strategy_id)
            if part20_cell is None:
                mismatches.append(f"{strategy_id}: missing from Part 20 Experiment C")
                continue

            # Compare failure rates (should be exactly equal since same computation)
            if part19_cell.failures != part20_cell.failures:
                mismatches.append(
                    f"{strategy_id}: Part19 failures={part19_cell.failures} "
                    f"!= Part20 failures={part20_cell.failures}"
                )

        assert not mismatches, "Cross-validation mismatches:\n" + "\n".join(mismatches)

    def test_cross_validation_published_anchors(
        self,
        experiment_a_cells: tuple[Part19ExperimentACell, ...],
    ) -> None:
        """Compare overlapping cells against Part 20 Experiment C published anchors."""
        spec = _load_audit_spec()
        anchors = spec.get("cross_validation_anchors", [])

        overlap_cells = {
            f"{cell.strategy_id}_{cell.horizon_years}Y_fv"
            f"{cell.final_value_target}_{cell.cape_condition}": cell
            for cell in experiment_a_cells
            if cell.final_value_target == Decimal("0") and cell.cape_condition == "HIGH"
        }

        for anchor in anchors:
            key = (
                f"{anchor['strategy']}_{anchor['horizon_years']}Y_fv"
                f"{anchor['final_value_target']}_HIGH"
            )
            part19_cell = overlap_cells.get(key)
            if part19_cell is None:
                pytest.skip(f"Overlap cell {key} not found in Part 19 results")

            # Compute Part 19 failure rate as percentage with 1 decimal place
            part19_rate_pct = part19_cell.failure_rate * Decimal("100")
            # Round to 1 decimal place (matching Part 20 published precision)
            part19_rate_display = (
                part19_rate_pct * Decimal("10")
            ).quantize(Decimal("1")) / Decimal("10")
            expected = Decimal(str(anchor["published_failure_rate"]))

            # Allow 1 ULP (0.1 percentage point) tolerance for display rounding
            diff = abs(part19_rate_display - expected)
            assert diff <= Decimal("0.1"), (
                f"{key}: Part19 failure rate {part19_rate_display}% != published {expected}% "
                f"(raw: {part19_rate_pct:.4f}%)"
            )

    # -----------------------------------------------------------------------
    # Qualitative validation (informational)
    # -----------------------------------------------------------------------

    def test_qualitative_60_to_100_glidepaths_best_cape_high(
        self, experiment_a_cells: tuple[Part19ExperimentACell, ...]
    ) -> None:
        """60→100% glidepaths should be among best performers in CAPE > 20 (FV=0).

        Article (Bullet 2): "The 80% to 100% and 60% to 100% glidepaths
        deliver consistently lowest failure rates, regardless of the final value target."
        Article (Bullet 7): "The consistently best performers are the 60 to 100%
        glidepaths..."

        This test verifies that at least one 60→100% glidepath has a lower
        failure rate than the two static allocations shown in the failure-rate
        charts (static 80% and static 100%). This is a minimal check consistent
        with the article's qualitative "consistently best performers" observation.
        """
        # Filter to CAPE HIGH, FV=0
        cape_high_fv0 = [
            c for c in experiment_a_cells
            if c.cape_condition == "HIGH" and c.final_value_target == Decimal("0")
        ]

        # Get failure rates for 60→100% glidepaths (4 strategies)
        gp_60_100_rates = {
            c.strategy_id: c.failure_rate
            for c in cape_high_fv0
            if c.strategy_id.startswith("gp_060_100_")
        }

        # Get failure rates for static 80% and 100% (the two shown in charts)
        static_080_rate = next(
            c.failure_rate for c in cape_high_fv0 if c.strategy_id == "static_080"
        )
        static_100_rate = next(
            c.failure_rate for c in cape_high_fv0 if c.strategy_id == "static_100"
        )

        # At least one 60→100% glidepath should have lower failure rate
        # than static_080 and static_100
        best_gp_rate = min(gp_60_100_rates.values())
        assert best_gp_rate <= static_080_rate, (
            f"Best 60→100% glidepath failure rate {best_gp_rate} "
            f"not <= static_080 {static_080_rate}"
        )
        assert best_gp_rate <= static_100_rate, (
            f"Best 60→100% glidepath failure rate {best_gp_rate} "
            f"not <= static_100 {static_100_rate}"
        )

    def test_qualitative_active_better_than_passive(
        self, experiment_a_cells: tuple[Part19ExperimentACell, ...]
    ) -> None:
        """Active glidepaths should perform better than passive glidepaths as a group.

        Article (Bullet 7): "The consistently best performers are the 60 to 100%
        glidepaths and the active glidepaths perform slightly better than the
        passive ones."

        This is a group-level qualitative observation from the article's charts.
        The test verifies that the mean failure rate of active glidepaths is
        lower than the mean failure rate of passive glidepaths (CAPE > 20, FV=0).
        This captures the article's general pattern without imposing a universal
        pairwise inequality that the qualitative source does not support.
        """
        cape_high_fv0 = [
            c for c in experiment_a_cells
            if c.cape_condition == "HIGH" and c.final_value_target == Decimal("0")
        ]

        active_rates = []
        passive_rates = []
        for cell in cape_high_fv0:
            if cell.strategy_id.startswith("gp_"):
                # Parse: gp_060_080_0.002_passive
                parts = cell.strategy_id.split("_")
                mode = parts[4]  # passive or active
                if mode == "active":
                    active_rates.append(cell.failure_rate)
                elif mode == "passive":
                    passive_rates.append(cell.failure_rate)

        assert active_rates, "No active glidepaths found"
        assert passive_rates, "No passive glidepaths found"

        mean_active = sum(active_rates) / len(active_rates)
        mean_passive = sum(passive_rates) / len(passive_rates)

        # Active glidepaths as a group should have lower mean failure rate
        assert mean_active < mean_passive, (
            f"Mean active failure rate {mean_active:.4f} not < mean passive {mean_passive:.4f}"
        )

    def test_qualitative_20_to_80_inferior(
        self, experiment_a_cells: tuple[Part19ExperimentACell, ...]
    ) -> None:
        """20→80% glidepaths should be inferior to static 80% and 100% allocations.

        Article (Bullet 5): "The 20 to 80% glidepaths are even inferior to the
        static 80% and 100% allocations."

        This test verifies that all 20→80% glidepaths have higher failure rates
        than both static_080 and static_100 (CAPE > 20, FV=0).
        """
        cape_high_fv0 = [
            c for c in experiment_a_cells
            if c.cape_condition == "HIGH" and c.final_value_target == Decimal("0")
        ]

        gp_20_80_rates = [
            c.failure_rate for c in cape_high_fv0 if c.strategy_id.startswith("gp_020_080_")
        ]
        static_080_rate = next(
            c.failure_rate for c in cape_high_fv0 if c.strategy_id == "static_080"
        )
        static_100_rate = next(
            c.failure_rate for c in cape_high_fv0 if c.strategy_id == "static_100"
        )

        # All 20→80% glidepaths should have higher failure rates than BOTH
        # static 80% and static 100% (article: "inferior to the static 80% and 100% allocations")
        for rate in gp_20_80_rates:
            assert rate > static_080_rate, (
                f"20→80% failure rate {rate:.4f} not > static_080 {static_080_rate:.4f}"
            )
            assert rate > static_100_rate, (
                f"20→80% failure rate {rate:.4f} not > static_100 {static_100_rate:.4f}"
            )

    # -----------------------------------------------------------------------
    # Reporting
    # -----------------------------------------------------------------------

    def test_print_summary(self, experiment_a_cells: tuple[Part19ExperimentACell, ...]) -> None:
        """Print summary statistics for manual inspection."""
        print("\n" + "=" * 70)
        print("PART 19 EXPERIMENT A SUMMARY")
        print("=" * 70)
        print(f"Total cells: {len(experiment_a_cells)}")
        print("Strategies: 27 (3 static + 24 glidepath)")
        print(f"FV targets: {[str(fv) for fv in PART19_EXPERIMENT_A_FV_TARGETS]}")
        print("CAPE conditions: ALL (1739), HIGH (383)")
        print(f"Horizon: {PART19_EXPERIMENT_A_HORIZON_YEARS}Y")
        print(f"SWR: {PART19_EXPERIMENT_A_SWR}")

        # Per FV target, CAPE condition summary
        for fv in PART19_EXPERIMENT_A_FV_TARGETS:
            for cape in ("ALL", "HIGH"):
                subset = [
                    c
                    for c in experiment_a_cells
                    if c.final_value_target == fv and c.cape_condition == cape
                ]
                rates = [c.failure_rate for c in subset]
                print(f"\n  FV={fv}, CAPE={cape}:")
                print(f"    min failure rate: {min(rates)*100:.2f}%")
                print(f"    max failure rate: {max(rates)*100:.2f}%")
                print(f"    mean failure rate: {sum(rates)/len(rates)*100:.2f}%")

        print("=" * 70)
