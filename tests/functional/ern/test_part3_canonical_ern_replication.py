"""ERN Part 3 E2E replication — canonical 2026 and historical 2016.

Executes the 4 ERN Part 3 experiment configurations (A-D) with the
21-equity-weight grid. The historical 2016 replication validates against the
six published numerical anchors; the canonical 2026 study asserts its own
deterministic regression snapshots.

The 4 experiments are specific (WR, FV) pairs - NOT a Cartesian product:

    Exp A: 4% SWR, 0% TV (depletion)
    Exp B: 4% SWR, 50% TV
    Exp C: 3.5% SWR, 50% TV
    Exp D: 3.25% SWR, 50% TV

Each experiment runs 21 equity allocations (0-100% in 5% steps) x 2 horizons
(30Y, 60Y) x 1,739 canonical cohorts = 168 ERN parameter cells total.

Published anchors (see docs/ERN_METHODOLOGY.md section 2):

    Overall (no CAPE condition):
        C, 60Y, 100% equity -> 96%

    CAPE 20-30 conditioned:
        A, 30Y, 100% equity -> 89%
        A, 60Y, 100% equity -> 72%
        B, 60Y, 100% equity -> 71%
        C, 60Y, 100% equity -> 88%
        D, 60Y, 100% equity -> 97%

The published 97% is the D/60Y/CAPE20-30 result, not the D overall-population
result. D overall is retained as a diagnostic and is never compared with 97%.

The canonical 2026 study uses the current canonical configuration. The
historical 2016 replication uses the dedicated article-era configuration with
a September 2016 cutoff and the Article Part 1 forward projections.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies.cape_regime import CapeRegime
from fbf.core.execution import (
    ExecutionOptions,
    iter_execute_study_plan,
)
from fbf.core.research.part3_aggregation import aggregate_part3_results
from fbf.core.research.part3_pipeline import adapt_part3_to_builtin
from fbf.core.research.part3_planner import PART3_EXPENSE_RATIO
from fbf.core.research.part3_study import (
    build_part3_plan_from_configuration,
    load_packaged_part3_configuration,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path("data/inputs/ern")
INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)

# Tolerance for anchor comparison: 1 percentage point.
ANCHOR_TOLERANCE = Decimal("0.01")

_CANONICAL_CONFIG = load_packaged_part3_configuration()
_HISTORICAL_2016_CONFIG = load_packaged_part3_configuration("part3_2016.yaml")


def _experiment_pairs(config: Any) -> dict[str, tuple[Decimal, Decimal]]:
    if config.experiments is None:
        raise RuntimeError("Packaged Part 3 configuration must define experiments")
    return {
        experiment.id: (experiment.withdrawal_rate, experiment.final_value_target)
        for experiment in config.experiments
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CellResult:
    rate: Decimal
    successes: int
    total: int


@dataclass(frozen=True)
class _Part3Metrics:
    """Lightweight Part 3 execution metrics retained by the E2E tests."""

    total_units: int
    n_cohorts: int
    n_params: int
    equities: frozenset[Decimal]
    horizons: frozenset[int]
    wr_fv_pairs: frozenset[tuple[Decimal, Decimal]]
    all_units_have_configured_expense_ratio: bool
    a30_high: _CellResult
    a60_high: _CellResult
    b60_high: _CellResult
    c60_overall: _CellResult
    c60_high: _CellResult
    d60_high: _CellResult
    d60_overall: _CellResult


@dataclass(frozen=True)
class _StreamedPart3Result:
    """Memory-bounded Part 3 execution result used by the E2E tests."""

    results: tuple[Any, ...]
    aggregation: Any

    @property
    def total_units(self) -> int:
        return len(self.results)


def _execute_part3_streaming(
    plan_result: Any, options: ExecutionOptions
) -> _StreamedPart3Result:
    """Execute Part 3 in bounded slices and aggregate the summary results."""
    builtin = adapt_part3_to_builtin(plan_result)
    summary_results: list[Any] = []
    for chunk in iter_execute_study_plan(builtin, options=options):
        summary_results.extend(chunk.result.results)

    n_cohorts = len(plan_result.cohorts)
    n_params = len(plan_result.param_configs)
    per_unit_cohorts = tuple(
        cohort for cohort in plan_result.cohorts for _ in range(n_params)
    )
    per_unit_params = tuple(
        param for _ in range(n_cohorts) for param in plan_result.param_configs
    )
    results = tuple(summary_results)
    aggregation = aggregate_part3_results(
        cohorts=per_unit_cohorts,
        param_configs=per_unit_params,
        simulation_results=results,
        get_cape_metadata=plan_result.get_cape_metadata,
    )
    return _StreamedPart3Result(results=results, aggregation=aggregation)


def _compute_overall_by_cell(
    plan_result: Any,
    execution_results: tuple[Any, ...],
) -> dict[tuple[Decimal, Decimal, int, Decimal], tuple[int, int]]:
    """Compute overall (all-cohort) success rates per parameter cell.

    Returns a dict mapping (wr, fv, horizon, equity) -> (successes, total).
    """
    n_cohorts = len(plan_result.cohorts)
    n_params = len(plan_result.param_configs)

    cell_stats: dict[
        tuple[Decimal, Decimal, int, Decimal], tuple[int, int]
    ] = defaultdict(lambda: (0, 0))

    idx = 0
    for _cohort_idx in range(n_cohorts):
        for param_idx in range(n_params):
            pc = plan_result.param_configs[param_idx]
            wr = Decimal(str(pc.values.get("withdrawal_rate", "0")))
            raw_fv = pc.values.get("final_value_target")
            fv = Decimal(str(raw_fv)) if raw_fv is not None else Decimal("0")
            horizon = int(pc.values.get("horizon_years", 0))
            equity = Decimal(str(pc.values.get("equity_allocation", "0")))

            success = execution_results[idx].statistics.success
            key = (wr, fv, horizon, equity)
            s, t = cell_stats[key]
            cell_stats[key] = (s + (1 if success else 0), t + 1)
            idx += 1

    return dict(cell_stats)


def _rate(successes: int, total: int) -> Decimal:
    if total == 0:
        return Decimal("0")
    return Decimal(str(successes)) / Decimal(str(total))


def _find_cape_row(
    regime_aggregations: tuple[Any, ...],
    wr: Decimal,
    fv: Decimal,
    horizon: int,
    equity: Decimal,
    cape_regime: CapeRegime,
) -> Any:
    """Find the single matching regime aggregation row."""
    rows = [
        r for r in regime_aggregations
        if (
            r.withdrawal_rate == wr
            and r.terminal_target == fv
            and r.horizon_years == horizon
            and r.equity_allocation == equity
            and r.cape_regime == cape_regime
        )
    ]
    return rows[0] if len(rows) == 1 else None


def _cape_cell(
    regime_aggregations: tuple[Any, ...],
    wr: Decimal,
    fv: Decimal,
    horizon: int,
    equity: Decimal,
    cape_regime: CapeRegime,
) -> _CellResult:
    row = _find_cape_row(
        regime_aggregations, wr, fv, horizon, equity, cape_regime
    )
    if row is None:
        raise AssertionError(
            f"No {cape_regime} row for WR={wr}, FV={fv}, "
            f"horizon={horizon}, equity={equity}"
        )
    return _CellResult(
        rate=row.success_rate,
        successes=row.successful_cohorts,
        total=row.total_cohorts,
    )


def _overall_cell(
    overall: dict[tuple[Decimal, Decimal, int, Decimal], tuple[int, int]],
    wr: Decimal,
    fv: Decimal,
    horizon: int,
    equity: Decimal,
) -> _CellResult:
    successes, total = overall[(wr, fv, horizon, equity)]
    return _CellResult(
        rate=_rate(successes, total),
        successes=successes,
        total=total,
    )


@pytest.fixture(scope="class")
def part3_metrics(request: pytest.FixtureRequest) -> _Part3Metrics:
    """Execute Part 3 and retain only lightweight metrics for assertions."""
    assert request.cls is not None
    config: Any = request.cls.CONFIG
    experiments: dict[str, tuple[Decimal, Decimal]] = request.cls.EXPERIMENTS

    plan_result = build_part3_plan_from_configuration(
        DATA_DIR,
        INITIAL_WEALTH,
        configuration=config,
    )
    options = ExecutionOptions(
    )
    pipeline_result = _execute_part3_streaming(plan_result, options)
    overall = _compute_overall_by_cell(plan_result, pipeline_result.results)

    regimes = pipeline_result.aggregation.regime_aggregations
    a_wr, a_fv = experiments["A"]
    b_wr, b_fv = experiments["B"]
    c_wr, c_fv = experiments["C"]
    d_wr, d_fv = experiments["D"]

    return _Part3Metrics(
        total_units=pipeline_result.total_units,
        n_cohorts=len(plan_result.cohorts),
        n_params=len(plan_result.param_configs),
        equities=frozenset(
            Decimal(str(pc.values.get("equity_allocation", "0")))
            for pc in plan_result.param_configs
        ),
        horizons=frozenset(
            int(pc.values.get("horizon_years", 0))
            for pc in plan_result.param_configs
        ),
        wr_fv_pairs=frozenset(
            (
                Decimal(str(pc.values.get("withdrawal_rate", "0"))),
                Decimal(str(pc.values.get("final_value_target", "0"))),
            )
            for pc in plan_result.param_configs
        ),
        all_units_have_configured_expense_ratio=all(
            unit.expense_ratio == PART3_EXPENSE_RATIO
            for unit in plan_result.plan
        ),
        a30_high=_cape_cell(
            regimes, a_wr, a_fv, 30, Decimal("1.0"), CapeRegime.HIGH
        ),
        a60_high=_cape_cell(
            regimes, a_wr, a_fv, 60, Decimal("1.0"), CapeRegime.HIGH
        ),
        b60_high=_cape_cell(
            regimes, b_wr, b_fv, 60, Decimal("1.0"), CapeRegime.HIGH
        ),
        c60_overall=_overall_cell(
            overall, c_wr, c_fv, 60, Decimal("1.0")
        ),
        c60_high=_cape_cell(
            regimes, c_wr, c_fv, 60, Decimal("1.0"), CapeRegime.HIGH
        ),
        d60_high=_cape_cell(
            regimes, d_wr, d_fv, 60, Decimal("1.0"), CapeRegime.HIGH
        ),
        d60_overall=_overall_cell(
            overall, d_wr, d_fv, 60, Decimal("1.0")
        ),
    )


def _assert_anchor(
    label: str,
    cell: _CellResult,
    expected: Decimal,
) -> None:
    assert abs(cell.rate - expected) <= ANCHOR_TOLERANCE, (
        f"Anchor {label}: expected ~{expected}, got {cell.rate} "
        f"({cell.successes}/{cell.total})"
    )


def _assert_counts(
    label: str,
    cell: _CellResult,
    successes: int,
    total: int,
) -> None:
    assert (cell.successes, cell.total) == (successes, total), (
        f"Canonical regression {label}: expected {successes}/{total}, "
        f"got {cell.successes}/{cell.total}"
    )


# ---------------------------------------------------------------------------
# Shared replication tests
# ---------------------------------------------------------------------------


class _Part3ReplicationBase:
    """Shared structure and diagnostic tests for a Part 3 replication."""

    CONFIG: Any
    EXPERIMENTS: dict[str, tuple[Decimal, Decimal]]

    def test_all_experiments_execute(self, part3_metrics: _Part3Metrics) -> None:
        """All parameter cells execute without error."""
        assert part3_metrics.total_units == (
            part3_metrics.n_cohorts * part3_metrics.n_params
        )

    def test_all_units_use_configured_expense_ratio(
        self, part3_metrics: _Part3Metrics
    ) -> None:
        """The configured 0.05% annual fee reaches every planned unit."""
        assert Decimal("0.0005") == PART3_EXPENSE_RATIO
        assert part3_metrics.all_units_have_configured_expense_ratio

    def test_manifest_cohort_count(self, part3_metrics: _Part3Metrics) -> None:
        """1,739 canonical cohorts are present."""
        assert part3_metrics.n_cohorts == 1739

    def test_equity_weight_count(self, part3_metrics: _Part3Metrics) -> None:
        """21 equity weights are materialized in the parameter configs."""
        assert len(part3_metrics.equities) == 21
        for w in self.CONFIG.allocation_policy_values:
            assert w in part3_metrics.equities, f"Missing equity weight {w}"

    def test_horizon_count(self, part3_metrics: _Part3Metrics) -> None:
        """2 horizons (30Y, 60Y) are materialized."""
        assert part3_metrics.horizons == {30, 60}

    def test_experiment_cell_count(self, part3_metrics: _Part3Metrics) -> None:
        """4 explicit A-D pairs x 21 equity x 2 H = 168 param configs."""
        assert part3_metrics.n_params == 168

    def test_ern_experiment_params_present(
        self, part3_metrics: _Part3Metrics
    ) -> None:
        """All 4 ERN experiment (WR, FV) pairs exist in the parameter grid."""
        for exp_id, (wr, fv) in self.EXPERIMENTS.items():
            assert (wr, fv) in part3_metrics.wr_fv_pairs, (
                f"ERN experiment {exp_id} (WR={wr}, FV={fv}) not in grid"
            )

    def test_D_60Y_overall_diagnostic_is_not_published_anchor(
        self, part3_metrics: _Part3Metrics
    ) -> None:
        """D overall is a diagnostic; the published 97% belongs to CAPE 20-30."""
        assert part3_metrics.d60_overall.total == part3_metrics.n_cohorts
        assert (
            part3_metrics.d60_overall.successes
            >= part3_metrics.d60_high.successes
        )
        assert part3_metrics.d60_overall.rate >= part3_metrics.d60_high.rate, (
            f"D/60Y/overall diagnostic: {part3_metrics.d60_overall.rate} "
            f"({part3_metrics.d60_overall.successes}/"
            f"{part3_metrics.d60_overall.total}); "
            f"D/60Y/CAPE20-30: {part3_metrics.d60_high.rate} "
            f"({part3_metrics.d60_high.successes}/"
            f"{part3_metrics.d60_high.total})"
        )
        # Deliberately no comparison with 0.97: that is the HIGH-regime anchor.


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


@pytest.mark.ern_e2e
class TestPart3CanonicalERNReplication(_Part3ReplicationBase):
    """Canonical 2026 Part 3 study with its current assumptions.

    These tests are deterministic regression snapshots of the canonical study.
    They do not compare canonical outputs against the historical 2016 article
    anchors; those comparisons are recorded as diagnostics in the methodology
    documentation and the audit report.
    """

    CONFIG = _CANONICAL_CONFIG
    EXPERIMENTS = _experiment_pairs(_CANONICAL_CONFIG)

    def test_canonical_A_30Y_CAPE20_30(
        self, part3_metrics: _Part3Metrics
    ) -> None:
        """Canonical A/30Y/CAPE20-30 regression snapshot."""
        _assert_counts("A/30Y/CAPE20-30", part3_metrics.a30_high, 321, 358)

    def test_canonical_A_60Y_CAPE20_30(
        self, part3_metrics: _Part3Metrics
    ) -> None:
        """Canonical A/60Y/CAPE20-30 regression snapshot."""
        _assert_counts("A/60Y/CAPE20-30", part3_metrics.a60_high, 258, 358)

    def test_canonical_B_60Y_CAPE20_30(
        self, part3_metrics: _Part3Metrics
    ) -> None:
        """Canonical B/60Y/CAPE20-30 regression snapshot."""
        _assert_counts("B/60Y/CAPE20-30", part3_metrics.b60_high, 256, 358)

    def test_canonical_C_60Y_overall(
        self, part3_metrics: _Part3Metrics
    ) -> None:
        """Canonical C/60Y/overall regression snapshot."""
        _assert_counts(
            "C/60Y/overall", part3_metrics.c60_overall, 1700, 1739
        )

    def test_canonical_C_60Y_CAPE20_30(
        self, part3_metrics: _Part3Metrics
    ) -> None:
        """Canonical C/60Y/CAPE20-30 regression snapshot."""
        _assert_counts("C/60Y/CAPE20-30", part3_metrics.c60_high, 328, 358)

    def test_canonical_D_60Y_CAPE20_30(
        self, part3_metrics: _Part3Metrics
    ) -> None:
        """Canonical D/60Y/CAPE20-30 regression snapshot."""
        _assert_counts("D/60Y/CAPE20-30", part3_metrics.d60_high, 349, 358)

    def test_canonical_D_60Y_overall(self, part3_metrics: _Part3Metrics) -> None:
        """Canonical D/60Y/overall diagnostic regression snapshot."""
        _assert_counts("D/60Y/overall", part3_metrics.d60_overall, 1727, 1739)


@pytest.mark.ern_e2e
class TestPart32016ERNReplication(_Part3ReplicationBase):
    """Historical 2016 Part 3 replication with article-era assumptions."""

    CONFIG = _HISTORICAL_2016_CONFIG
    EXPERIMENTS = _experiment_pairs(_HISTORICAL_2016_CONFIG)

    def test_anchor_A_30Y_CAPE20_30(self, part3_metrics: _Part3Metrics) -> None:
        """Anchor A: 4% SWR, 0% TV, 30Y, 100% equity, CAPE 20-30 -> 89%."""
        _assert_anchor(
            "A/30Y/CAPE20-30", part3_metrics.a30_high, Decimal("0.89")
        )

    def test_anchor_A_60Y_CAPE20_30(self, part3_metrics: _Part3Metrics) -> None:
        """Anchor A: 4% SWR, 0% TV, 60Y, 100% equity, CAPE 20-30 -> 72%."""
        _assert_anchor(
            "A/60Y/CAPE20-30", part3_metrics.a60_high, Decimal("0.72")
        )

    def test_anchor_B_60Y_CAPE20_30(self, part3_metrics: _Part3Metrics) -> None:
        """Anchor B: 4% SWR, 50% TV, 60Y, 100% equity, CAPE 20-30 -> 71%."""
        _assert_anchor(
            "B/60Y/CAPE20-30", part3_metrics.b60_high, Decimal("0.71")
        )

    def test_anchor_C_60Y_overall(self, part3_metrics: _Part3Metrics) -> None:
        """Anchor C: 3.5% SWR, 50% TV, 60Y, 100% equity, Overall -> 96%."""
        _assert_anchor(
            "C/60Y/overall", part3_metrics.c60_overall, Decimal("0.96")
        )

    def test_anchor_C_60Y_CAPE20_30(
        self, part3_metrics: _Part3Metrics
    ) -> None:
        """Anchor C: 3.5% SWR, 50% TV, 60Y, 100% equity, CAPE 20-30 -> 88%."""
        _assert_anchor(
            "C/60Y/CAPE20-30", part3_metrics.c60_high, Decimal("0.88")
        )

    def test_anchor_D_60Y_CAPE20_30(
        self, part3_metrics: _Part3Metrics
    ) -> None:
        """Anchor D: 3.25% SWR, 50% TV, 60Y, 100% equity, CAPE 20-30 -> 97%."""
        _assert_anchor(
            "D/60Y/CAPE20-30", part3_metrics.d60_high, Decimal("0.97")
        )

    def test_2016_exact_regression_counts(
        self, part3_metrics: _Part3Metrics
    ) -> None:
        """Exact 2016 counts under prior-month (CAPE t-1) classification."""
        _assert_counts("A/30Y/CAPE20-30", part3_metrics.a30_high, 321, 358)
        _assert_counts("A/60Y/CAPE20-30", part3_metrics.a60_high, 258, 358)
        _assert_counts("B/60Y/CAPE20-30", part3_metrics.b60_high, 255, 358)
        _assert_counts("C/60Y/overall", part3_metrics.c60_overall, 1674, 1739)
        _assert_counts("C/60Y/CAPE20-30", part3_metrics.c60_high, 318, 358)
        _assert_counts("D/60Y/CAPE20-30", part3_metrics.d60_high, 348, 358)
        _assert_counts("D/60Y/overall", part3_metrics.d60_overall, 1723, 1739)
