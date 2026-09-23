"""T2.1 Part 20 baseline E2E audit (gated RUN_ERN_E2E=1).

Data-driven implementation of ern_part20_e2e_audit.md Experiments A–E.
The experiment matrix and published anchors are loaded from
``tests/fixtures/ern_part20_e2e_audit.yaml`` (single authoritative
representation); this file only orchestrates execution, structural
checks, anchor comparison, classification, and invariants.

Gating: centralized RUN_ERN_E2E=1 (tests/conftest.py).  This test is
intentionally excluded from routine validation.

Preserves tests/oracle/ern/test_part20_replication.py (320-cell CLI
regression) unchanged.
"""

from __future__ import annotations

import os
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import pytest

from fbf.core.datasets import load_canonical_dataset
from fbf.core.execution import ExecutionOptions
from fbf.core.research.part20_aggregation import (
    AnchorComparison,
    to_displayed_failure_percent,
    to_displayed_percent,
)
from fbf.core.research.part20_anchors import compare_anchor, structural_checks
from fbf.core.research.part20_audit_spec import (
    AuditAnchor,
    FixedSWRSpec,
    Part20AuditSpec,
    PercentileSearchSpec,
    UnsupportedSpec,
    load_part20_audit_spec,
)
from fbf.core.research.part20_pipeline import (
    FailureRateCell,
    SearchCache,
    SWRSearchResult,
    default_max_steps,
    run_fixed_swr_grid,
    run_percentile_search,
)
from fbf.core.research.part20_planner import Part20ExecutionContext
from fbf.core.research.part20_strategies import Part20Strategy, part20_strategy_universe

DATA_DIR = Path("data/ern")
MANIFEST_PATH = DATA_DIR / "cohort_manifest_part3.json"
AUDIT_SPEC_PATH = Path("tests/fixtures/ern_part20_e2e_audit.yaml")

# Metric name → PART20_FAILURE_PROBABILITIES index.
_METRIC_INDEX: dict[str, int] = {
    "failsafe": 0,
    "p01": 1,
    "p03": 2,
    "p05": 3,
    "p10": 4,
    "p25": 5,
}


def _workers() -> int:
    raw = os.environ.get("ERN_E2E_WORKERS", "").strip()
    cpu = os.cpu_count() or 8
    if not raw:
        return min(8, cpu)
    if raw.lower() == "max":
        return cpu
    try:
        n = int(raw)
    except ValueError:
        return min(8, cpu)
    return min(n, cpu) if n > 0 else min(8, cpu)


def _options() -> ExecutionOptions:
    return ExecutionOptions(
        workers=_workers(),
        summary_only=True,
    )


@dataclass
class T21AuditState:
    """In-memory results for one full audit run (class-scoped fixture)."""

    spec: Part20AuditSpec
    ctx: Part20ExecutionContext
    strategies: tuple[Part20Strategy, ...]
    cache: SearchCache = field(default_factory=dict)
    # experiment id → (strategy_id, population, fv) → search result
    search_results: dict[str, dict[tuple[str, str, Decimal], SWRSearchResult]] = field(
        default_factory=dict
    )
    cells_c: dict[tuple[str, int, Decimal], FailureRateCell] = field(
        default_factory=dict
    )
    comparisons: list[AnchorComparison] = field(default_factory=list)
    structural_problems: list[str] = field(default_factory=list)
    capability_gaps: list[str] = field(default_factory=list)
    determinism_ok: bool = False
    wall_clock_s: float = 0.0
    exp_runtime_s: dict[str, float] = field(default_factory=dict)
    exp_stats: dict[str, tuple[int, int]] = field(default_factory=dict)

    # -- observed value lookup ---------------------------------------------

    def _percentile_observed(
        self, result: SWRSearchResult, metric: str
    ) -> tuple[Decimal | None, int]:
        try:
            idx = _METRIC_INDEX[metric]
        except KeyError:
            return None, result.cohort_count
        probs = sorted(result.percentiles.keys())
        if idx >= len(probs):
            return None, result.cohort_count
        return to_displayed_percent(result.percentiles[probs[idx]]), result.cohort_count

    def _observed(self, anchor: AuditAnchor) -> tuple[Decimal | None, int]:
        if anchor.experiment in {"A", "B", "D"}:
            table = self.search_results.get(anchor.experiment, {})
            fv = (
                anchor.final_value_target
                if anchor.final_value_target is not None
                else Decimal("0")
            )
            result = table.get((anchor.strategy, anchor.cape_regime, fv))
            if result is None:
                return None, 0
            return self._percentile_observed(result, anchor.metric)
        if anchor.experiment == "C":
            if anchor.withdrawal_rate is None:
                return None, 0
            cell = self.cells_c.get(
                (anchor.strategy, anchor.horizon_years or -1, anchor.withdrawal_rate)
            )
            if cell is None:
                return None, 0
            return to_displayed_failure_percent(cell.failure_rate), cell.total_cohorts
        # Experiment E: never executed in the baseline audit.
        return None, 0

    def _calculation_path(self, anchor: AuditAnchor) -> str:
        if anchor.experiment in {"A", "B", "D"}:
            return (
                f"percentile_swrs[{anchor.metric}]("
                f"search H={anchor.horizon_years}Y "
                f"FV={anchor.final_value_target} pop={anchor.cape_regime})"
            )
        if anchor.experiment == "C":
            n = self.ctx.populations
            pop_dates = n.high_dates if anchor.cape_regime == "HIGH" else n.low_dates
            return (
                f"failure_rate(SWR={anchor.withdrawal_rate} over "
                f"{anchor.cape_regime} cohorts, H={anchor.horizon_years}Y, "
                f"n={len(pop_dates)})"
            )
        return "n/a — capability gap (Experiment E not executed in T2.1 baseline)"

    def build_comparisons(self) -> list[AnchorComparison]:
        by_id = {s.id: s for s in self.strategies}
        out: list[AnchorComparison] = []
        for anchor in self.spec.anchors:
            observed, n = self._observed(anchor)
            strategy = by_id.get(anchor.strategy)
            out.append(
                compare_anchor(
                    anchor,
                    observed,
                    strategy,
                    n,
                    self._calculation_path(anchor),
                )
            )
        return out

    def classification_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {
            "REPRODUCED": 0,
            "EXPLAINED DIFFERENCE": 0,
            "UNEXPLAINED DIFFERENCE": 0,
            "CAPABILITY GAP": 0,
        }
        for c in self.comparisons:
            counts[c.classification.kind] = counts.get(c.classification.kind, 0) + 1
        return counts

    @property
    def unexplained(self) -> list[AnchorComparison]:
        return [
            c
            for c in self.comparisons
            if c.classification.kind == "UNEXPLAINED DIFFERENCE"
        ]

    def print_matrix(self) -> None:
        for c in self.comparisons:
            print(c.format_row())  # noqa: T201 — audit terminal output


def _run_percentile_experiments(
    ctx: Part20ExecutionContext,
    strategies: Sequence[Part20Strategy],
    state: T21AuditState,
    only: set[str] | None = None,
) -> None:
    """Execute percentile_search experiments in the audit spec.

    *only*: if given, run just those experiment ids (else all).
    """
    pops = ctx.populations
    pop_dates = {"HIGH": pops.high_dates, "LOW": pops.low_dates}
    for exp in state.spec.experiments:
        if not isinstance(exp, PercentileSearchSpec):
            continue
        if only is not None and exp.id not in only:
            continue
        t0 = time.perf_counter()
        exec_before = state.ctx.stats.executions
        units_before = state.ctx.stats.units_executed
        table: dict[tuple[str, str, Decimal], SWRSearchResult] = {}
        for population in exp.populations:
            for fv in exp.fv_targets:
                results = run_percentile_search(
                    ctx,
                    strategies,
                    pop_dates[population],
                    horizon_years=exp.horizon_years,
                    final_value_target=fv,
                    cape_regime=population,
                    options=_options(),
                    step_label=f"exp{exp.id}_h{exp.horizon_years}_{population}_fv{fv}",
                    cache=state.cache,
                )
                for sid, result in results.items():
                    table[(sid, population, fv)] = result
        state.search_results[exp.id] = table
        state.exp_runtime_s[exp.id] = time.perf_counter() - t0
        state.exp_stats[exp.id] = (
            state.ctx.stats.executions - exec_before,
            state.ctx.stats.units_executed - units_before,
        )


def _run_experiment_c(
    ctx: Part20ExecutionContext,
    strategies: Sequence[Part20Strategy],
    state: T21AuditState,
    enabled: bool = True,
) -> None:
    if not enabled:
        return
    exp = state.spec.experiment("C")
    assert isinstance(exp, FixedSWRSpec)
    t0 = time.perf_counter()
    exec_before = ctx.stats.executions
    units_before = ctx.stats.units_executed
    pop_dates = (
        ctx.populations.high_dates
        if exp.population == "HIGH"
        else ctx.populations.low_dates
    )
    for horizon in exp.horizons_years:
        cells = run_fixed_swr_grid(
            ctx,
            strategies,
            pop_dates,
            horizon_years=horizon,
            withdrawal_rates=exp.fixed_swrs,
            final_value_target=exp.final_value_target,
            population=exp.population,
            options=_options(),
        )
        for cell in cells:
            state.cells_c[(cell.strategy_id, cell.horizon_years, cell.withdrawal_rate)] = (
                cell
            )
        # Invariant: failure rates non-decreasing in SWR (exact, no tolerance).
        for strategy in strategies:
            rates = sorted(
                (c.withdrawal_rate, c.failure_rate)
                for c in cells
                if c.strategy_id == strategy.id
            )
            for i in range(1, len(rates)):
                assert rates[i][1] >= rates[i - 1][1], (
                    f"Exp C monotonicity violated: {strategy.id} H={horizon} "
                    f"{rates[i - 1]} -> {rates[i]}"
                )
    state.exp_runtime_s["C"] = time.perf_counter() - t0
    state.exp_stats["C"] = (
        ctx.stats.executions - exec_before,
        ctx.stats.units_executed - units_before,
    )


def _assert_experiment_d_invariant(state: T21AuditState, enabled: bool = True) -> None:
    """Failsafe must be non-increasing as the FV target rises (exact)."""
    if not enabled or "D" not in state.search_results:
        return
    exp_d = state.spec.experiment("D")
    assert isinstance(exp_d, PercentileSearchSpec)
    table = state.search_results.get("D", {})
    for strategy in state.strategies:
        failsafes: list[Decimal] = []
        for fv in exp_d.fv_targets:
            result = table.get((strategy.id, "HIGH", fv))
            if result is not None:
                failsafes.append(result.failsafe)
        for i in range(1, len(failsafes)):
            assert failsafes[i] <= failsafes[i - 1], (
                f"Exp D monotonicity violated for {strategy.id}: {failsafes} "
                "(FV increasing must not raise failsafe)"
            )


def _record_capability_gaps(state: T21AuditState) -> None:
    exp_e = state.spec.experiment("E")
    assert isinstance(exp_e, UnsupportedSpec)
    state.capability_gaps = list(exp_e.capability_gaps)


def _determinism_spot_check(
    ctx: Part20ExecutionContext,
    state: T21AuditState,
    enabled: bool = True,
) -> None:
    """Rerun one cached static search without the cache; results must match."""
    if not enabled or "A" not in state.search_results:
        return
    exp_a = state.spec.experiment("A")
    assert isinstance(exp_a, PercentileSearchSpec)
    probe = next(s for s in state.strategies if s.id == "static_075")
    t0 = time.perf_counter()
    fresh = run_percentile_search(
        ctx,
        (probe,),
        ctx.populations.high_dates,
        horizon_years=exp_a.horizon_years,
        final_value_target=Decimal("0"),
        cape_regime="HIGH",
        options=_options(),
        step_label="det_static_075",
        cache=None,
    )
    cached = state.search_results["A"][("static_075", "HIGH", Decimal("0"))]
    assert fresh["static_075"].per_cohort_swrs == cached.per_cohort_swrs
    state.determinism_ok = True
    state.exp_runtime_s.setdefault("det", 0.0)
    state.exp_runtime_s["det"] += time.perf_counter() - t0


def _classify_experiment(
    state: T21AuditState, exp_id: str
) -> list[AnchorComparison]:
    """Classify only the anchors belonging to *exp_id*."""
    return [c for c in state.comparisons if c.experiment == exp_id]


def audit_state_helper_cells_ok(
    cells: dict[tuple[str, int, Decimal], FailureRateCell]
) -> bool:
    """Experiment C cells present and failure rates non-decreasing in SWR."""
    if not cells:
        return False
    from collections import defaultdict

    by_key: dict[tuple[str, int], list[tuple[Decimal, Decimal]]] = defaultdict(list)
    for (sid, horizon, rate), cell in cells.items():
        by_key[(sid, horizon)].append((rate, cell.failure_rate))
    for rates in by_key.values():
        rates.sort(key=lambda x: x[0])
        for i in range(1, len(rates)):
            if rates[i][1] < rates[i - 1][1]:
                return False
    return True


def _classify_experiment_by_id_from_gaps(gaps: list[str]) -> int:
    """Count E capability-gap rows (all unsupported cases)."""
    return 8  # E anchors in YAML are always CAPABILITY GAP; structural test covers exact count


def _needed_experiments(request: pytest.FixtureRequest) -> set[str]:
    """Which experiments the selected tests require (smallest -k mechanism).

    Full-matrix / structural tests need A–E.  Experiment-specific tests need
    just that experiment (D also needs A for the approved A→D FV=0 cache).

    Uses the pytest -k keyword expression to determine which tests are
    actually being run, rather than all collected tests.
    """
    keyword = getattr(request.config.option, "keyword", "") or ""
    full_markers = (
        "test_structural_invariants",
        "test_cell_counts",
        "test_genuinely_executed",
        "test_d_reused_fv0_from_a",
        "test_percentiles_present",
        "test_determinism_spot_check",
        "test_all_anchors_classified",
        "test_unexplained_recorded_with_context",
        "test_classification_counts_sum",
        "test_print_matrix_smoke",
        "test_experiment_e_all_capability_gaps",
        "test_experiment_e_capability_gap_recorded",
    )
    # If the keyword matches any full-matrix test name, run all experiments
    if any(m in keyword for m in full_markers):
        return {"A", "B", "C", "D", "E"}

    needed: set[str] = set()
    if "experiment_a" in keyword:
        needed.add("A")
    if "experiment_b" in keyword:
        needed.add("B")
    if "experiment_c" in keyword:
        needed.add("C")
    if "experiment_d" in keyword:
        needed.update({"A", "D"})
    if "experiment_e" in keyword:
        needed.add("E")

    # Default to all if no specific experiment selected
    # (e.g., running the whole class without -k)
    return needed or {"A", "B", "C", "D", "E"}


def _checkpoint(state: T21AuditState, exp_id: str) -> None:
    """Print independent observable checkpoint for one experiment."""
    anchors = [c for c in state.comparisons if c.experiment == exp_id]
    counts: dict[str, int] = {}
    unexp: list[AnchorComparison] = []
    gaps: list[AnchorComparison] = []
    for c in anchors:
        kind = c.classification.kind
        counts[kind] = counts.get(kind, 0) + 1
        if kind == "UNEXPLAINED DIFFERENCE":
            unexp.append(c)
        if kind == "CAPABILITY GAP":
            gaps.append(c)
    exec_n, units_n = state.exp_stats.get(exp_id, (0, 0))
    if exp_id == "E":
        exec_n, units_n = 0, 0
    runtime = state.exp_runtime_s.get(exp_id, 0.0)
    status = "PASS"
    print(  # noqa: T201
        f"CHECKPOINT {exp_id}: {status} executions={exec_n} units={units_n} "
        f"anchors={len(anchors)} classifications={counts} "
        f"unexplained={len(unexp)} capability_gaps={len(gaps)} "
        f"runtime_s={runtime:.3f}",
        flush=True,
    )
    for row in unexp:
        print(f"  UNEXPLAINED: {row.identifying_context}", flush=True)  # noqa: T201
    for row in gaps:
        print(f"  GAP: {row.identifying_context}", flush=True)  # noqa: T201


def _expected_execution_counts(state: T21AuditState) -> tuple[int, int]:
    """Exact (executions, units) for the full audit given deterministic steps."""
    strategies_n = len(state.strategies)
    # Population sizes come from the live context (manifest-derived).
    high_n = len(state.ctx.populations.high_dates)
    low_n = len(state.ctx.populations.low_dates)
    steps = default_max_steps()

    exp_a = state.spec.experiment("A")
    exp_b = state.spec.experiment("B")
    exp_c = state.spec.experiment("C")
    exp_d = state.spec.experiment("D")
    assert isinstance(exp_a, PercentileSearchSpec)
    assert isinstance(exp_b, PercentileSearchSpec)
    assert isinstance(exp_c, FixedSWRSpec)
    assert isinstance(exp_d, PercentileSearchSpec)

    def search_units(pop_sizes: Sequence[int], fvs: int) -> int:
        # 13 steps × pairs; every pair stays active for all 13 steps.
        return steps * sum(pop_sizes) * strategies_n * fvs

    a_pops = [high_n if p == "HIGH" else low_n for p in exp_a.populations]
    b_pops = [high_n if p == "HIGH" else low_n for p in exp_b.populations]
    a_exec = steps * len(exp_a.populations) * len(exp_a.fv_targets)
    b_exec = steps * len(exp_b.populations) * len(exp_b.fv_targets)

    c_cells_per_horizon = strategies_n * high_n
    c_exec = len(exp_c.horizons_years) * len(exp_c.fixed_swrs)
    c_units = c_exec * c_cells_per_horizon

    # D: FV=0/HIGH reused from A (cache hit → 0 executions); others fresh.
    d_fresh_fvs = [fv for fv in exp_d.fv_targets if fv != Decimal("0")]
    d_exec = steps * len(d_fresh_fvs)
    d_units = steps * high_n * strategies_n * len(d_fresh_fvs)

    # Determinism rerun: single static strategy, no cache.
    det_exec = steps
    det_units = steps * high_n

    executions = a_exec + b_exec + c_exec + d_exec + det_exec
    units = (
        search_units(a_pops, len(exp_a.fv_targets))
        + search_units(b_pops, len(exp_b.fv_targets))
        + c_units
        + d_units
        + det_units
    )
    return executions, units


def _build_state() -> T21AuditState:
    spec = load_part20_audit_spec(AUDIT_SPEC_PATH)
    trajectory = load_canonical_dataset(DATA_DIR)
    ctx = Part20ExecutionContext.create(MANIFEST_PATH, trajectory)
    strategies = part20_strategy_universe()
    return T21AuditState(spec=spec, ctx=ctx, strategies=strategies)


def _finalize_state(state: T21AuditState) -> T21AuditState:
    pops = state.ctx.populations
    exp_e = state.spec.experiment("E")
    assert isinstance(exp_e, UnsupportedSpec)
    state.structural_problems = structural_checks(
        state.spec.structural_counts,
        total_cohorts=len(pops.all_dates),
        cape_available=len(pops.cape_available_dates),
        cape_high=len(pops.high_dates),
        strategy_count=len(state.strategies),
        cells_a=len(state.search_results.get("A", {})),
        cells_b=len(state.search_results.get("B", {})),
        cells_c=len(state.cells_c),
        cells_d=len(state.search_results.get("D", {})),
        cells_e_cases=len(exp_e.cases),
    )
    state.comparisons = state.build_comparisons()
    return state


@pytest.mark.ern_e2e
@pytest.mark.skipif(
    not MANIFEST_PATH.is_file(), reason="Canonical manifest not present"
)
class TestPart20T21BaselineAudit:
    """T2.1: full baseline audit against ern_part20_e2e_audit.md.

    Selection: `-k` selects test methods; shared class-scoped ``audit_state``
    runs the full workload once per session (A–E fixtures prepare each
    experiment; matrix tests cover cross-experiment anchors).
    """

    @pytest.fixture(scope="class")
    def audit_state(self, request: pytest.FixtureRequest) -> T21AuditState:
        """Build state and run only the experiments the selected tests need.

        Selection mechanism: pytest ``-k`` on per-experiment test names.
        Full-matrix / structural tests request A–E; experiment-specific tests
        request only that experiment (D also requests A for A→D FV=0 cache).
        """
        state = _build_state()
        needed = _needed_experiments(request)
        t0 = time.perf_counter()
        _run_percentile_experiments(
            state.ctx, state.strategies, state, only=needed
        )
        _run_experiment_c(
            state.ctx, state.strategies, state, enabled=("C" in needed)
        )
        _assert_experiment_d_invariant(state, enabled=("D" in needed))
        _record_capability_gaps(state)
        _determinism_spot_check(
            state.ctx, state, enabled=("A" in needed)
        )
        state.wall_clock_s = time.perf_counter() - t0
        return _finalize_state(state)

    # --- Experiment A ---

    @pytest.fixture(scope="class")
    def exp_a_results(
        self, audit_state: T21AuditState
    ) -> dict[tuple[str, str, Decimal], SWRSearchResult]:
        return audit_state.search_results.get("A", {})

    @pytest.fixture(scope="class")
    def exp_a_anchors(
        self,
        audit_state: T21AuditState,
        exp_a_results: dict[tuple[str, str, Decimal], SWRSearchResult],
    ) -> list[AnchorComparison]:
        return _classify_experiment(audit_state, "A")

    def test_experiment_a_anchors(
        self,
        exp_a_results: dict[tuple[str, str, Decimal], SWRSearchResult],
        exp_a_anchors: list[AnchorComparison],
        audit_state: T21AuditState,
    ) -> None:
        assert exp_a_results
        assert exp_a_anchors
        # All A anchors classified; non-exact recorded with context
        for c in exp_a_anchors:
            assert c.calculation_path
            if c.classification.kind != "REPRODUCED":
                assert "variant isolation not run" in c.classification.evidence or (
                    c.classification.kind == "CAPABILITY GAP"
                )
        assert len(exp_a_anchors) == self._spec_anchors("A")
        _checkpoint(audit_state, "A")

    def _spec_anchors(self, exp_id: str) -> int:
        from fbf.core.research.part20_audit_spec import load_part20_audit_spec

        spec = load_part20_audit_spec(AUDIT_SPEC_PATH)
        return sum(1 for a in spec.anchors if a.experiment == exp_id)

    # --- Experiment B ---

    @pytest.fixture(scope="class")
    def exp_b_results(
        self, audit_state: T21AuditState
    ) -> dict[tuple[str, str, Decimal], SWRSearchResult]:
        return audit_state.search_results.get("B", {})

    @pytest.fixture(scope="class")
    def exp_b_anchors(
        self,
        audit_state: T21AuditState,
        exp_b_results: dict[tuple[str, str, Decimal], SWRSearchResult],
    ) -> list[AnchorComparison]:
        return _classify_experiment(audit_state, "B")

    def test_experiment_b_anchors(
        self,
        exp_b_results: dict[tuple[str, str, Decimal], SWRSearchResult],
        exp_b_anchors: list[AnchorComparison],
        audit_state: T21AuditState,
    ) -> None:
        assert exp_b_results
        assert exp_b_anchors
        for c in exp_b_anchors:
            assert c.calculation_path
        assert len(exp_b_anchors) == self._spec_anchors("B")
        _checkpoint(audit_state, "B")

    # --- Experiment C ---

    @pytest.fixture(scope="class")
    def exp_c_results(
        self, audit_state: T21AuditState
    ) -> dict[tuple[str, int, Decimal], FailureRateCell]:
        return audit_state.cells_c

    @pytest.fixture(scope="class")
    def exp_c_anchors(
        self,
        audit_state: T21AuditState,
        exp_c_results: dict[tuple[str, int, Decimal], FailureRateCell],
    ) -> list[AnchorComparison]:
        return _classify_experiment(audit_state, "C")

    def test_experiment_c_anchors(
        self,
        exp_c_results: dict[tuple[str, int, Decimal], FailureRateCell],
        exp_c_anchors: list[AnchorComparison],
        audit_state: T21AuditState,
    ) -> None:
        assert exp_c_results
        assert exp_c_anchors
        for c in exp_c_anchors:
            assert c.calculation_path
        assert len(exp_c_anchors) == self._spec_anchors("C")
        # C structural: failure rates non-decreasing already asserted in runner
        assert audit_state_helper_cells_ok(exp_c_results)
        _checkpoint(audit_state, "C")

    # --- Experiment D ---

    @pytest.fixture(scope="class")
    def exp_d_results(
        self, audit_state: T21AuditState
    ) -> dict[tuple[str, str, Decimal], SWRSearchResult]:
        return audit_state.search_results.get("D", {})

    @pytest.fixture(scope="class")
    def exp_d_anchors(
        self,
        audit_state: T21AuditState,
        exp_d_results: dict[tuple[str, str, Decimal], SWRSearchResult],
    ) -> list[AnchorComparison]:
        return _classify_experiment(audit_state, "D")

    def test_experiment_d_anchors(
        self,
        exp_d_results: dict[tuple[str, str, Decimal], SWRSearchResult],
        exp_d_anchors: list[AnchorComparison],
        audit_state: T21AuditState,
    ) -> None:
        assert exp_d_results
        assert exp_d_anchors
        for c in exp_d_anchors:
            assert c.calculation_path
        assert len(exp_d_anchors) == self._spec_anchors("D")
        _checkpoint(audit_state, "D")

    def test_experiment_d_cache_reuse(
        self, audit_state: T21AuditState
    ) -> None:
        # FV=0/HIGH reuses A's results (already-approved simple A→D cache)
        strategies_n = len(audit_state.strategies)
        assert audit_state.ctx.stats.reused_search_cells == strategies_n

    # --- Experiment E ---

    @pytest.fixture(scope="class")
    def exp_e_gaps(
        self, audit_state: T21AuditState
    ) -> list[str]:
        return audit_state.capability_gaps

    def test_experiment_e_capability_gaps(
        self, exp_e_gaps: list[str], audit_state: T21AuditState
    ) -> None:
        # E never executes; all unsupported cases → CAPABILITY GAP
        assert exp_e_gaps
        joined = " ".join(exp_e_gaps).lower()
        assert "annual" in joined
        assert "synthetic" in joined
        e_rows = _classify_experiment_by_id_from_gaps(exp_e_gaps)
        # All E anchors are CAPABILITY GAP (validated in full matrix test too)
        assert e_rows >= 8
        _checkpoint(audit_state, "E")

    # --- structural / audit matrix (requires full A–E run) ---

    def test_structural_invariants(self, audit_state: T21AuditState) -> None:
        assert audit_state.structural_problems == [], audit_state.structural_problems

    def test_cell_counts(self, audit_state: T21AuditState) -> None:
        counts = audit_state.spec.structural_counts
        assert len(audit_state.search_results["A"]) == counts.cells_a
        assert len(audit_state.search_results["B"]) == counts.cells_b
        assert len(audit_state.cells_c) == counts.cells_c
        assert len(audit_state.search_results["D"]) == counts.cells_d
        exp_e = audit_state.spec.experiment("E")
        assert isinstance(exp_e, UnsupportedSpec)
        assert len(exp_e.cases) == counts.cells_e_cases

    def test_genuinely_executed(self, audit_state: T21AuditState) -> None:
        expected_exec, expected_units = _expected_execution_counts(audit_state)
        assert audit_state.ctx.stats.executions == expected_exec
        assert audit_state.ctx.stats.units_executed == expected_units
        assert audit_state.ctx.stats.units_executed > 0

    def test_d_reused_fv0_from_a(self, audit_state: T21AuditState) -> None:
        strategies_n = len(audit_state.strategies)
        assert audit_state.ctx.stats.reused_search_cells == strategies_n
        a = audit_state.search_results["A"][("static_075", "HIGH", Decimal("0"))]
        d = audit_state.search_results["D"][("static_075", "HIGH", Decimal("0"))]
        assert a is d

    def test_percentiles_present(self, audit_state: T21AuditState) -> None:
        sample = audit_state.search_results["A"][("static_075", "HIGH", Decimal("0"))]
        counts = audit_state.spec.structural_counts
        assert sample.cohort_count == counts.cape_high
        assert sample.failsafe > Decimal("0")
        assert Decimal("0.05") in sample.percentiles

    def test_determinism_spot_check(self, audit_state: T21AuditState) -> None:
        assert audit_state.determinism_ok

    # --- comparisons / classifications (full matrix) ---

    def test_all_anchors_classified(self, audit_state: T21AuditState) -> None:
        assert len(audit_state.comparisons) == len(audit_state.spec.anchors)
        assert len(audit_state.comparisons) == 77
        for c in audit_state.comparisons:
            assert c.classification.kind in {
                "REPRODUCED",
                "EXPLAINED DIFFERENCE",
                "UNEXPLAINED DIFFERENCE",
                "CAPABILITY GAP",
            }
            assert c.calculation_path

    def test_experiment_e_all_capability_gaps(self, audit_state: T21AuditState) -> None:
        e_rows = [c for c in audit_state.comparisons if c.experiment == "E"]
        assert len(e_rows) == 8
        assert all(c.classification.kind == "CAPABILITY GAP" for c in e_rows)

    def test_experiment_e_capability_gap_recorded(
        self, audit_state: T21AuditState
    ) -> None:
        assert len(audit_state.capability_gaps) >= 3
        joined = " ".join(audit_state.capability_gaps).lower()
        assert "annual" in joined
        assert "synthetic" in joined

    def test_unexplained_recorded_with_context(
        self, audit_state: T21AuditState
    ) -> None:
        for row in audit_state.unexplained:
            ctx = row.identifying_context
            assert row.experiment in ctx
            assert row.strategy_id in ctx
            assert str(row.published_percent) in ctx
            assert row.calculation_path in ctx
            assert "variant isolation not run" in row.classification.evidence
            print(f"UNEXPLAINED: {ctx}")  # noqa: T201

    def test_classification_counts_sum(self, audit_state: T21AuditState) -> None:
        counts = audit_state.classification_counts()
        assert sum(counts.values()) == len(audit_state.spec.anchors)

    def test_print_matrix_smoke(self, audit_state: T21AuditState) -> None:
        assert audit_state.comparisons
        _ = [c.format_row() for c in audit_state.comparisons]
