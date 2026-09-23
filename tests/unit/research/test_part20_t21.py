"""T2.1 unit tests — Part 20 strategy universe, populations, percentiles, bisection, classification.

These tests run in the normal suite (no RUN_ERN_E2E) and cover pure
functions and structural helpers without executing the full audit grid.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

import pytest

from fbf.core.execution import ExecutionStrategy
from fbf.core.research.part20_aggregation import (
    PART20_FAILURE_PROBABILITIES,
    classify_displayed_value,
    percentile_swrs,
    swr_at_failure_probability,
    to_displayed_failure_percent,
    to_displayed_percent,
)
from fbf.core.research.part20_anchors import compare_anchor, structural_checks
from fbf.core.research.part20_audit_spec import (
    AuditAnchor,
    FixedSWRSpec,
    PercentileSearchSpec,
    UnsupportedSpec,
    load_part20_audit_spec,
)
from fbf.core.research.part20_pipeline import (
    PART20_SWR_DOMAIN_MIN,
    PART20_SWR_PRECISION,
    bisect_per_pair,
    default_max_steps,
)
from fbf.core.research.part20_planner import (
    PART20_PARALLEL_CHUNK_UNITS,
    build_cohort_populations,
    choose_execution_strategy,
    load_part20_manifest,
)
from fbf.core.research.part20_strategies import (
    PART20_GLIDEPATH_COUNT,
    PART20_STATIC_COUNT,
    PART20_STRATEGY_COUNT,
    part20_strategy_universe,
)

MANIFEST_PATH = Path("data/ern/cohort_manifest_part3.json")
AUDIT_SPEC_PATH = Path("tests/fixtures/ern_part20_e2e_audit.yaml")


class TestStrategyUniverse:
    def test_counts(self) -> None:
        universe = part20_strategy_universe()
        assert len(universe) == 53
        assert PART20_STATIC_COUNT == 21
        assert PART20_GLIDEPATH_COUNT == 32
        assert PART20_STRATEGY_COUNT == 53

    def test_unique_ids(self) -> None:
        ids = [s.id for s in part20_strategy_universe()]
        assert len(set(ids)) == 53

    def test_static_equity_steps(self) -> None:
        statics = [s for s in part20_strategy_universe() if s.is_static]
        equities = sorted(
            s.equity_allocation for s in statics if s.equity_allocation is not None
        )
        expected = [Decimal(i) / Decimal("100") for i in range(0, 105, 5)]
        assert equities == expected

    def test_kitces_0111_present(self) -> None:
        ids = {s.id for s in part20_strategy_universe()}
        assert "gp_030_070_0.00111_passive" in ids
        assert "gp_020_060_0.00111_passive" in ids

    def test_active_count(self) -> None:
        actives = [s for s in part20_strategy_universe() if s.is_active]
        # 6 start/end combos × 2 slopes × 1 active mode = 12
        assert len(actives) == 12


class TestAuditSpec:
    def test_loads_fixture(self) -> None:
        spec = load_part20_audit_spec(AUDIT_SPEC_PATH)
        assert sorted(exp.id for exp in spec.experiments) == ["A", "B", "C", "D", "E"]
        assert spec.structural_counts.total_cohorts == 1739
        assert spec.structural_counts.cape_high == 383
        assert spec.structural_counts.strategy_count == 53

    def test_anchor_counts(self) -> None:
        spec = load_part20_audit_spec(AUDIT_SPEC_PATH)
        assert len(spec.anchors_for("A")) == 10
        assert len(spec.anchors_for("B")) == 11
        assert len(spec.anchors_for("C")) == 42
        assert len(spec.anchors_for("D")) == 6
        assert len(spec.anchors_for("E")) == 8
        assert len(spec.anchors) == 77

    def test_experiment_kinds(self) -> None:
        spec = load_part20_audit_spec(AUDIT_SPEC_PATH)
        assert isinstance(spec.experiment("A"), PercentileSearchSpec)
        assert isinstance(spec.experiment("B"), PercentileSearchSpec)
        assert isinstance(spec.experiment("C"), FixedSWRSpec)
        assert isinstance(spec.experiment("D"), PercentileSearchSpec)
        assert isinstance(spec.experiment("E"), UnsupportedSpec)

    def test_c_fixed_swrs(self) -> None:
        spec = load_part20_audit_spec(AUDIT_SPEC_PATH)
        exp_c = spec.experiment("C")
        assert isinstance(exp_c, FixedSWRSpec)
        assert exp_c.fixed_swrs == (
            Decimal("0.03"),
            Decimal("0.0325"),
            Decimal("0.035"),
            Decimal("0.0375"),
            Decimal("0.04"),
        )
        assert exp_c.horizons_years == (60, 30)

    def test_d_reuse_from_a(self) -> None:
        spec = load_part20_audit_spec(AUDIT_SPEC_PATH)
        exp_d = spec.experiment("D")
        assert isinstance(exp_d, PercentileSearchSpec)
        assert exp_d.reuse_from == "A"
        assert exp_d.fv_targets == (Decimal("0"), Decimal("0.5"), Decimal("1"))

    def test_e_cases_and_gaps(self) -> None:
        spec = load_part20_audit_spec(AUDIT_SPEC_PATH)
        exp_e = spec.experiment("E")
        assert isinstance(exp_e, UnsupportedSpec)
        assert len(exp_e.cases) == 4
        assert len(exp_e.capability_gaps) >= 3
        strategies = {case.strategy for case in exp_e.cases}
        assert strategies == {"gp_070_090_annual", "static_080"}

    def test_invalid_unit_rejected(self) -> None:
        with pytest.raises(ValueError, match="invalid unit"):
            AuditAnchor(
                experiment="A",
                strategy="static_075",
                metric="failsafe",
                horizon_years=60,
                final_value_target=Decimal("0"),
                cape_regime="HIGH",
                published=Decimal("3.25"),
                unit="basis_points",
            )


@pytest.mark.skipif(not MANIFEST_PATH.is_file(), reason="manifest not present")
class TestCohortPopulations:
    def test_counts(self) -> None:
        spec = load_part20_audit_spec(AUDIT_SPEC_PATH)
        manifest = load_part20_manifest(MANIFEST_PATH)
        pops = build_cohort_populations(manifest)
        counts = spec.structural_counts
        assert len(pops.all_dates) == counts.total_cohorts
        assert len(pops.cape_available_dates) == counts.cape_available
        assert len(pops.high_dates) == counts.cape_high
        assert len(pops.low_dates) == counts.cape_available - counts.cape_high
        assert (
            pops.excluded_no_cape
            == counts.total_cohorts - counts.cape_available
        )

    def test_high_and_low_partition(self) -> None:
        manifest = load_part20_manifest(MANIFEST_PATH)
        pops = build_cohort_populations(manifest)
        combined = set(pops.high_dates) | set(pops.low_dates)
        assert len(combined) == len(pops.high_dates) + len(pops.low_dates)
        assert combined == set(pops.cape_available_dates)

    def test_effective_horizon_clamps_last_cohort(self) -> None:
        """2015-12 has max_horizon_months=720; a 721 request must clamp."""
        from datetime import date

        from fbf.core.datasets import load_canonical_dataset

        trajectory = load_canonical_dataset(Path("data/ern"))
        from fbf.core.research.part20_planner import Part20ExecutionContext

        ctx = Part20ExecutionContext.create(MANIFEST_PATH, trajectory)
        assert ctx.effective_horizon("2015-12-01", 721) == 720
        assert ctx.effective_horizon("2015-11-01", 721) == 721
        assert ctx.effective_horizon("1871-02-01", 721) == 721
        assert ctx.effective_horizon("2015-12-01", 361) == 361
        # Slice with the clamped horizon must succeed.
        dataset = ctx.dataset_for("2015-12-01", ctx.effective_horizon("2015-12-01", 721))
        assert len(dataset.snapshots) == 720
        assert dataset.snapshots[0].date == date(2015, 12, 1)


class TestPercentiles:
    def test_failsafe_is_min(self) -> None:
        swrs = [Decimal("0.03"), Decimal("0.04"), Decimal("0.02")]
        p = percentile_swrs(swrs, (Decimal("0"),))
        assert p[Decimal("0")] == Decimal("0.02")

    def test_order_statistic_definition(self) -> None:
        # n=100, p=0.05 → index floor(5) = 5 (0-based) = 6th smallest
        swrs = [Decimal(i) / Decimal("100") for i in range(1, 101)]
        ordered = sorted(swrs)
        got = swr_at_failure_probability(ordered, Decimal("0.05"))
        assert got == ordered[5]
        assert got == Decimal("0.06")

    def test_p1_n100(self) -> None:
        ordered = [Decimal(i) for i in range(100)]
        assert swr_at_failure_probability(ordered, Decimal("0.01")) == ordered[1]

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            swr_at_failure_probability([], Decimal("0"))

    def test_invalid_p_raises(self) -> None:
        with pytest.raises(ValueError, match="in \\[0, 1\\]"):
            swr_at_failure_probability([Decimal("1")], Decimal("1.5"))

    def test_displayed_percent_rounding(self) -> None:
        assert to_displayed_percent(Decimal("0.0325")) == Decimal("3.25")
        assert to_displayed_percent(Decimal("0.03145")) == Decimal("3.14")  # ROUND_HALF_EVEN
        assert to_displayed_percent(Decimal("0.03144")) == Decimal("3.14")

    def test_failure_percent_rounding(self) -> None:
        assert to_displayed_failure_percent(Decimal("0.058")) == Decimal("5.8")
        assert to_displayed_failure_percent(Decimal("0.0335")) == Decimal("3.4")

    def test_probabilities_include_failsafe_and_p05(self) -> None:
        assert Decimal("0") in PART20_FAILURE_PROBABILITIES
        assert Decimal("0.05") in PART20_FAILURE_PROBABILITIES


class TestBisectionPerPair:
    def test_default_max_steps(self) -> None:
        # width 0.07 / precision 1e-5 = 7000 → ceil(log2)=13 → +2 = 15
        assert default_max_steps() == 15

    def test_converges_each_pair_to_its_threshold(self) -> None:
        thresholds = [Decimal("0.040"), Decimal("0.020"), Decimal("0.055")]

        def evaluate(candidates: Sequence[tuple[int, Decimal]]) -> Sequence[bool]:
            return [mid <= thresholds[i] for i, mid in candidates]

        outcome = bisect_per_pair(len(thresholds), evaluate=evaluate)
        assert outcome.steps <= default_max_steps()
        assert outcome.steps >= 13  # width requires 13 halvings
        for i, threshold in enumerate(thresholds):
            best = outcome.bests[i]
            assert best is not None
            assert abs(best - threshold) <= PART20_SWR_PRECISION * 2

    def test_mids_stay_inside_each_pair_bracket(self) -> None:
        thresholds = [Decimal("0.050"), Decimal("0.040")]
        seen: list[list[tuple[int, Decimal]]] = []

        def evaluate(candidates: Sequence[tuple[int, Decimal]]) -> Sequence[bool]:
            seen.append(list(candidates))
            return [mid <= thresholds[i] for i, mid in candidates]

        # Track brackets independently to assert mid ∈ [low, high].
        lows = [PART20_SWR_DOMAIN_MIN] * len(thresholds)
        highs = [Decimal("0.08")] * len(thresholds)
        # Re-run with bracket assertion via wrapper.
        lows = [PART20_SWR_DOMAIN_MIN] * len(thresholds)
        highs = [Decimal("0.08")] * len(thresholds)

        def evaluate_checked(
            candidates: Sequence[tuple[int, Decimal]],
        ) -> Sequence[bool]:
            for i, mid in candidates:
                assert lows[i] < mid < highs[i], (
                    f"pair {i}: mid {mid} outside [{lows[i]}, {highs[i]}]"
                )
            flags = []
            for i, mid in candidates:
                ok = mid <= thresholds[i]
                if ok:
                    lows[i] = mid
                else:
                    highs[i] = mid
                flags.append(ok)
            return flags

        outcome = bisect_per_pair(len(thresholds), evaluate=evaluate_checked)
        # Straddling regression: pair thresholds differ; both must converge.
        assert outcome.bests[0] is not None and outcome.bests[1] is not None
        assert outcome.bests[0] > outcome.bests[1]

    def test_straddling_midpoint_regression(self) -> None:
        """Shared-envelope midpoint would stall diverged pairs; per-pair does not.

        After step 1, pair0 succeeds at 0.045 (threshold 0.050) and pair1
        fails (threshold 0.040).  The old shared mid
        (min(lows)+max(highs))/2 stays at 0.045 forever: pair0's low is
        already 0.045 (success leaves bracket unchanged) and pair1's high
        is already 0.045.  Per-pair mids (0.0625 and 0.0275) both progress.
        """
        thresholds = [Decimal("0.050"), Decimal("0.040")]
        call_mids: list[list[tuple[int, Decimal]]] = []

        def evaluate(candidates: Sequence[tuple[int, Decimal]]) -> Sequence[bool]:
            call_mids.append(list(candidates))
            return [mid <= thresholds[i] for i, mid in candidates]

        outcome = bisect_per_pair(2, evaluate=evaluate)

        # Both pairs found their true break-even within a tight tolerance.
        assert outcome.bests[0] is not None
        assert outcome.bests[1] is not None
        assert abs(outcome.bests[0] - thresholds[0]) <= PART20_SWR_PRECISION * 2
        assert abs(outcome.bests[1] - thresholds[1]) <= PART20_SWR_PRECISION * 2
        # Pair1 never collapsed to the domain floor (old failure mode).
        assert outcome.bests[1] > PART20_SWR_DOMAIN_MIN
        # Second step must evaluate pair-specific mids, not the shared 0.045.
        assert len(call_mids) >= 2
        second = dict(call_mids[1])
        assert second[0] != Decimal("0.045")
        assert second[1] != Decimal("0.045")

    def test_never_succeeded_yields_none(self) -> None:
        def evaluate(candidates: Sequence[tuple[int, Decimal]]) -> Sequence[bool]:
            return [False] * len(candidates)

        outcome = bisect_per_pair(3, evaluate=evaluate)
        assert outcome.bests == (None, None, None)
        # Documented fallback applies at the call site:
        assert Decimal("0.01") == PART20_SWR_DOMAIN_MIN

    def test_empty_pairs_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            bisect_per_pair(0, evaluate=lambda c: [])

    def test_misaligned_flags_raise(self) -> None:
        def evaluate(candidates: Sequence[tuple[int, Decimal]]) -> Sequence[bool]:
            return [True]  # wrong length

        with pytest.raises(ValueError, match="flags"):
            bisect_per_pair(2, evaluate=evaluate)


class TestClassification:
    def test_exact_match_reproduced(self) -> None:
        c = classify_displayed_value(
            Decimal("3.25"),
            Decimal("3.25"),
            unit="percent",
            strategy_kind="static",
            strategy_is_active=False,
            calculation_path="test",
        )
        assert c.kind == "REPRODUCED"

    def test_one_ulp_explained(self) -> None:
        c = classify_displayed_value(
            Decimal("3.24"),
            Decimal("3.25"),
            unit="percent",
            strategy_kind="static",
            strategy_is_active=False,
            calculation_path="test",
        )
        assert c.kind == "EXPLAINED DIFFERENCE"
        assert "1,739" in c.evidence or "1739" in c.evidence
        assert "one display ULP" in c.evidence

    def test_two_ulp_unexplained(self) -> None:
        c = classify_displayed_value(
            Decimal("3.23"),
            Decimal("3.25"),
            unit="percent",
            strategy_kind="static",
            strategy_is_active=False,
            calculation_path="percentile_swrs[failsafe](H=60)",
        )
        assert c.kind == "UNEXPLAINED DIFFERENCE"
        assert "delta=-0.02" in c.evidence
        assert "percentile_swrs[failsafe](H=60)" in c.evidence
        assert "variant isolation not run" in c.evidence

    def test_failure_rate_one_tenth_ulp_explained(self) -> None:
        c = classify_displayed_value(
            Decimal("5.9"),
            Decimal("5.8"),
            unit="percent_1dp",
            strategy_kind="static",
            strategy_is_active=False,
            calculation_path="failure_rate",
        )
        assert c.kind == "EXPLAINED DIFFERENCE"

    def test_failure_rate_two_tenths_unexplained(self) -> None:
        c = classify_displayed_value(
            Decimal("6.0"),
            Decimal("5.8"),
            unit="percent_1dp",
            strategy_kind="static",
            strategy_is_active=False,
            calculation_path="failure_rate",
        )
        assert c.kind == "UNEXPLAINED DIFFERENCE"

    def test_active_glidepath_one_ulp_includes_ath(self) -> None:
        c = classify_displayed_value(
            Decimal("3.33"),
            Decimal("3.34"),
            unit="percent",
            strategy_kind="glidepath",
            strategy_is_active=True,
            calculation_path="test",
        )
        assert c.kind == "EXPLAINED DIFFERENCE"
        assert "ATH" in c.evidence or "nominal" in c.evidence

    def test_passive_glidepath_one_ulp_omits_ath(self) -> None:
        c = classify_displayed_value(
            Decimal("3.33"),
            Decimal("3.34"),
            unit="percent",
            strategy_kind="glidepath",
            strategy_is_active=False,
            calculation_path="test",
        )
        assert c.kind == "EXPLAINED DIFFERENCE"
        assert "ATH" not in c.evidence

    def test_none_is_capability_gap(self) -> None:
        c = classify_displayed_value(
            None,
            Decimal("3.25"),
            unit="percent",
            strategy_kind=None,
            strategy_is_active=False,
            calculation_path="n/a",
        )
        assert c.kind == "CAPABILITY GAP"

    def test_observed_without_strategy_raises(self) -> None:
        with pytest.raises(ValueError, match="strategy context"):
            classify_displayed_value(
                Decimal("3.25"),
                Decimal("3.25"),
                unit="percent",
                strategy_kind=None,
                strategy_is_active=False,
                calculation_path="test",
            )

    def test_usd_exact_reproduced(self) -> None:
        c = classify_displayed_value(
            Decimal("733314"),
            Decimal("733314"),
            unit="usd",
            strategy_kind="glidepath",
            strategy_is_active=False,
            calculation_path="n/a",
        )
        assert c.kind == "REPRODUCED"


class TestStructuralAndCompare:
    def test_structural_pass(self) -> None:
        spec = load_part20_audit_spec(AUDIT_SPEC_PATH)
        counts = spec.structural_counts
        problems = structural_checks(
            counts,
            total_cohorts=counts.total_cohorts,
            cape_available=counts.cape_available,
            cape_high=counts.cape_high,
            strategy_count=counts.strategy_count,
            cells_a=counts.cells_a,
            cells_b=counts.cells_b,
            cells_c=counts.cells_c,
            cells_d=counts.cells_d,
            cells_e_cases=counts.cells_e_cases,
        )
        assert problems == []

    def test_structural_fail(self) -> None:
        spec = load_part20_audit_spec(AUDIT_SPEC_PATH)
        problems = structural_checks(
            spec.structural_counts,
            total_cohorts=1738,
            cape_available=spec.structural_counts.cape_available,
            cape_high=spec.structural_counts.cape_high,
            strategy_count=spec.structural_counts.strategy_count,
            cells_a=spec.structural_counts.cells_a,
            cells_b=spec.structural_counts.cells_b,
            cells_c=spec.structural_counts.cells_c,
            cells_d=spec.structural_counts.cells_d,
            cells_e_cases=spec.structural_counts.cells_e_cases,
        )
        assert problems == ["total_cohorts=1738 != 1739"]

    def test_compare_anchor_capability_gap_when_unobserved(self) -> None:
        spec = load_part20_audit_spec(AUDIT_SPEC_PATH)
        anchor = spec.anchors_for("E")[0]
        strategy = next(
            (s for s in part20_strategy_universe() if s.id == anchor.strategy),
            None,
        )
        comparison = compare_anchor(anchor, None, strategy, 0, "n/a")
        assert comparison.classification.kind == "CAPABILITY GAP"
        assert comparison.strategy_id == "gp_070_090_annual"

    def test_compare_anchor_reproduced(self) -> None:
        spec = load_part20_audit_spec(AUDIT_SPEC_PATH)
        anchor = spec.anchors_for("A")[0]
        strategy = next(
            s for s in part20_strategy_universe() if s.id == anchor.strategy
        )
        comparison = compare_anchor(
            anchor, Decimal("3.25"), strategy, 383, "percentile_swrs[failsafe]"
        )
        assert comparison.classification.kind == "REPRODUCED"
        assert comparison.calculation_path == "percentile_swrs[failsafe]"
        assert comparison.unit == "percent"


class TestExecutionStrategySelection:
    def test_all_static_uses_auto_fastest_backend(self) -> None:
        assert (
            choose_execution_strategy(100_000, all_static=True)
            is ExecutionStrategy.AUTO
        )

    def test_mixed_large_uses_parallel(self) -> None:
        assert (
            choose_execution_strategy(500, all_static=False)
            is ExecutionStrategy.PARALLEL
        )

    def test_mixed_small_uses_auto(self) -> None:
        assert (
            choose_execution_strategy(499, all_static=False)
            is ExecutionStrategy.AUTO
        )

    def test_parallel_chunk_units_proven_safe_bound(self) -> None:
        # Host probe: 12,800 OK; 19,200+ BrokenProcessPool. Bound is 12,000.
        assert PART20_PARALLEL_CHUNK_UNITS == 12_000
        assert PART20_PARALLEL_CHUNK_UNITS < 19_200
        assert PART20_PARALLEL_CHUNK_UNITS >= 12_800 - 800

    def test_sub_bundle_preserves_order_and_counts(self) -> None:
        """Partition sub-bundles keep unit order and logical counts."""
        from fbf.core.datasets import load_canonical_dataset
        from fbf.core.execution import ExecutionOptions
        from fbf.core.research.part20_planner import Part20ExecutionContext
        from fbf.core.research.part20_strategies import part20_strategy_universe

        if not MANIFEST_PATH.is_file():
            pytest.skip("canonical manifest not present")
        trajectory = load_canonical_dataset(Path("data/ern"))
        ctx = Part20ExecutionContext.create(MANIFEST_PATH, trajectory)
        strats = part20_strategy_universe()
        statics = [s for s in strats if s.is_static][:2]
        glide = [s for s in strats if not s.is_static][:2]
        cohorts = ctx.populations.high_dates[:5]
        rows = [(s, c, Decimal("0.035")) for s in statics + glide for c in cohorts]
        bundle = ctx.build_units(
            rows=rows,
            horizon_months=721,
            final_value_target=Decimal("0"),
            step_label="unit_sub",
        )
        n = len(bundle.plan.units)
        static_idx = [i for i, s in enumerate(bundle.strategies) if s.is_static]
        glide_idx = [i for i, s in enumerate(bundle.strategies) if not s.is_static]
        assert len(static_idx) + len(glide_idx) == n
        assert len(static_idx) == len(statics) * len(cohorts)
        assert len(glide_idx) == len(glide) * len(cohorts)

        sub_s = ctx._sub_bundle(bundle, static_idx)
        sub_g = ctx._sub_bundle(bundle, glide_idx)
        assert len(sub_s.plan.units) == len(static_idx)
        assert len(sub_g.plan.units) == len(glide_idx)
        # Order within each partition matches original relative order
        for orig_list, sub in ((static_idx, sub_s), (glide_idx, sub_g)):
            for j, oi in enumerate(orig_list):
                assert sub.plan.units[j] is bundle.plan.units[oi]
                assert sub.strategies[j] is bundle.strategies[oi]
        # Merged logical count
        assert len(sub_s.plan.units) + len(sub_g.plan.units) == n
        _ = ExecutionOptions()  # import used; no execution in unit suite
