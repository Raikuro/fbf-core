"""Canonical ERN Part 3 E2E replication — Equity Valuation Using CAPE.

Executes the 4 ERN Part 3 experiment configurations (A-D) with the canonical
21-equity-weight grid and validates against the 6 published numerical anchors.

The 4 experiments are specific (WR, FV) pairs - NOT a Cartesian product:

    Exp A: 4% SWR, 0% TV (depletion)
    Exp B: 4% SWR, 50% TV
    Exp C: 3.5% SWR, 50% TV
    Exp D: 3.25% SWR, 50% TV

Each experiment runs 21 equity allocations (0-100% in 5% steps) x 2 horizons
(30Y, 60Y) x 1,739 canonical cohorts = 168 ERN parameter cells total.
The full YAML Cartesian product yields 252 cells (3 WR x 2 FV x 21 eq x 2 H).

Published anchors (from docs/research/ern_part3_replication.md section 1.7):

    Overall (no CAPE condition):
        C, 60Y, 100% equity -> 96%
        D, 60Y, 100% equity -> 97%

    CAPE 20-30 conditioned:
        A, 30Y, 100% equity -> 89%
        A, 60Y, 100% equity -> 72%
        B, 60Y, 100% equity -> 71%
        C, 60Y, 100% equity -> 88%
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from fbf.core.datasets import load_canonical_dataset
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies.cape_regime import CapeRegime
from fbf.core.execution import ExecutionOptions, ExecutionStrategy
from fbf.core.research.part3_pipeline import execute_part3_pipeline
from fbf.core.research.part3_planner import (
    Part3PlannerConfig,
    load_manifest,
    materialize_part3_plan,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path("data/ern")
MANIFEST_PATH = DATA_DIR / "cohort_manifest_part3.json"
INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)

# Tolerance for anchor comparison: 1 percentage point.
ANCHOR_TOLERANCE = Decimal("0.01")

# The canonical 21 equity weights (0% to 100% in 5% steps)
EQUITY_WEIGHTS: tuple[Decimal, ...] = tuple(
    Decimal(str(i)) / Decimal("20") for i in range(21)
)

# ---------------------------------------------------------------------------
# ERN experiment definitions (specific WR/FV pairs, not Cartesian)
# ---------------------------------------------------------------------------

ERN_EXPERIMENTS: dict[str, tuple[Decimal, Decimal]] = {
    "A": (Decimal("0.04"), Decimal("0.0")),
    "B": (Decimal("0.04"), Decimal("0.5")),
    "C": (Decimal("0.035"), Decimal("0.5")),
    "D": (Decimal("0.0325"), Decimal("0.5")),
}

# Unique WR and FV values for the planner config (deduplicated, order-preserved)
_ERN_WR: tuple[Decimal, ...] = tuple(
    dict.fromkeys(wr for wr, _ in ERN_EXPERIMENTS.values())
)
_ERN_FV: tuple[Decimal, ...] = tuple(
    dict.fromkeys(fv for _, fv in ERN_EXPERIMENTS.values())
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.ern_e2e
@pytest.mark.skipif(
    not MANIFEST_PATH.is_file(), reason="Canonical manifest not present"
)
class TestPart3CanonicalERNReplication:
    """Canonical ERN Part 3 replication — 4 experiments, 6 published anchors."""

    @pytest.fixture(scope="class")
    def execution_result(self) -> tuple[Any, Any]:
        """Execute the full Part 3 pipeline once for all tests.

        Returns (plan_result, pipeline_result).
        """
        manifest = load_manifest(MANIFEST_PATH)
        trajectory = load_canonical_dataset(DATA_DIR)

        config = Part3PlannerConfig(
            equity_allocations=EQUITY_WEIGHTS,
            withdrawal_rates=_ERN_WR,
            horizon_years=(30, 60),
            final_value_targets=_ERN_FV,
            allocation_policy_type="ConstantAllocationPolicy",
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
        )

        plan_result = materialize_part3_plan(
            manifest=manifest,
            canonical_trajectory=trajectory,
            config=config,
            initial_wealth=INITIAL_WEALTH,
        )

        options = ExecutionOptions(strategy=ExecutionStrategy.AUTO)
        pipeline_result = execute_part3_pipeline(plan_result, options=options)

        return plan_result, pipeline_result

    def test_all_experiments_execute(
        self, execution_result: tuple[Any, Any]
    ) -> None:
        """All parameter cells execute without error."""
        plan_result, pipeline_result = execution_result
        n_cohorts = len(plan_result.cohorts)
        n_params = len(plan_result.param_configs)
        expected_units = n_cohorts * n_params
        assert pipeline_result.total_units == expected_units

    def test_manifest_cohort_count(
        self, execution_result: tuple[Any, Any]
    ) -> None:
        """1,739 canonical cohorts are present."""
        plan_result, _ = execution_result
        assert len(plan_result.cohorts) == 1739

    def test_equity_weight_count(
        self, execution_result: tuple[Any, Any]
    ) -> None:
        """21 equity weights are materialized in the parameter configs."""
        plan_result, _ = execution_result
        equities = {
            Decimal(str(pc.values.get("equity_allocation", "0")))
            for pc in plan_result.param_configs
        }
        assert len(equities) == 21
        for w in EQUITY_WEIGHTS:
            assert w in equities, f"Missing equity weight {w}"

    def test_horizon_count(
        self, execution_result: tuple[Any, Any]
    ) -> None:
        """2 horizons (30Y, 60Y) are materialized."""
        plan_result, _ = execution_result
        horizons = {
            int(pc.values.get("horizon_years", 0))
            for pc in plan_result.param_configs
        }
        assert horizons == {30, 60}

    def test_experiment_cell_count(
        self, execution_result: tuple[Any, Any]
    ) -> None:
        """3 WR x 2 FV x 21 equity x 2 H = 252 param configs (full Cartesian)."""
        plan_result, _ = execution_result
        n_params = len(plan_result.param_configs)
        assert n_params == 252

    def test_ern_experiment_params_present(
        self, execution_result: tuple[Any, Any]
    ) -> None:
        """All 4 ERN experiment (WR, FV) pairs exist in the parameter grid."""
        plan_result, _ = execution_result
        wr_fv_pairs = {
            (
                Decimal(str(pc.values.get("withdrawal_rate", "0"))),
                Decimal(str(pc.values.get("final_value_target", "0"))),
            )
            for pc in plan_result.param_configs
        }
        for exp_id, (wr, fv) in ERN_EXPERIMENTS.items():
            assert (wr, fv) in wr_fv_pairs, (
                f"ERN experiment {exp_id} (WR={wr}, FV={fv}) not in grid"
            )

    # -----------------------------------------------------------------------
    # Anchor assertions
    # -----------------------------------------------------------------------

    def test_anchor_A_30Y_CAPE20_30(
        self, execution_result: tuple[Any, Any]
    ) -> None:
        """Anchor A: 4% SWR, 0% TV, 30Y, 100% equity, CAPE 20-30 -> 89%."""
        _, pipeline_result = execution_result
        wr, fv = ERN_EXPERIMENTS["A"]
        row = _find_cape_row(
            pipeline_result.aggregation.regime_aggregations,
            wr, fv, 30, Decimal("1.0"), CapeRegime.HIGH,
        )
        assert row is not None, "No CAPE 20-30 row for A/30Y"
        rate = row.success_rate
        expected = Decimal("0.89")
        assert abs(rate - expected) <= ANCHOR_TOLERANCE, (
            f"Anchor A/30Y/CAPE20-30: expected ~{expected}, got {rate} "
            f"({row.successful_cohorts}/{row.total_cohorts})"
        )

    def test_anchor_A_60Y_CAPE20_30(
        self, execution_result: tuple[Any, Any]
    ) -> None:
        """Anchor A: 4% SWR, 0% TV, 60Y, 100% equity, CAPE 20-30 -> 72%."""
        _, pipeline_result = execution_result
        wr, fv = ERN_EXPERIMENTS["A"]
        row = _find_cape_row(
            pipeline_result.aggregation.regime_aggregations,
            wr, fv, 60, Decimal("1.0"), CapeRegime.HIGH,
        )
        assert row is not None, "No CAPE 20-30 row for A/60Y"
        rate = row.success_rate
        expected = Decimal("0.72")
        assert abs(rate - expected) <= ANCHOR_TOLERANCE, (
            f"Anchor A/60Y/CAPE20-30: expected ~{expected}, got {rate} "
            f"({row.successful_cohorts}/{row.total_cohorts})"
        )

    def test_anchor_B_60Y_CAPE20_30(
        self, execution_result: tuple[Any, Any]
    ) -> None:
        """Anchor B: 4% SWR, 50% TV, 60Y, 100% equity, CAPE 20-30 -> 71%."""
        _, pipeline_result = execution_result
        wr, fv = ERN_EXPERIMENTS["B"]
        row = _find_cape_row(
            pipeline_result.aggregation.regime_aggregations,
            wr, fv, 60, Decimal("1.0"), CapeRegime.HIGH,
        )
        assert row is not None, "No CAPE 20-30 row for B/60Y"
        rate = row.success_rate
        expected = Decimal("0.71")
        assert abs(rate - expected) <= ANCHOR_TOLERANCE, (
            f"Anchor B/60Y/CAPE20-30: expected ~{expected}, got {rate} "
            f"({row.successful_cohorts}/{row.total_cohorts})"
        )

    def test_anchor_C_60Y_overall(
        self, execution_result: tuple[Any, Any]
    ) -> None:
        """Anchor C: 3.5% SWR, 50% TV, 60Y, 100% equity, Overall -> 96%."""
        plan_result, pipeline_result = execution_result
        wr, fv = ERN_EXPERIMENTS["C"]
        overall = _compute_overall_by_cell(
            plan_result, pipeline_result.results
        )
        key = (wr, fv, 60, Decimal("1.0"))
        successes, total = overall[key]
        rate = _rate(successes, total)
        expected = Decimal("0.96")
        assert abs(rate - expected) <= ANCHOR_TOLERANCE, (
            f"Anchor C/60Y/overall: expected ~{expected}, got {rate} "
            f"({successes}/{total})"
        )

    def test_anchor_C_60Y_CAPE20_30(
        self, execution_result: tuple[Any, Any]
    ) -> None:
        """Anchor C: 3.5% SWR, 50% TV, 60Y, 100% equity, CAPE 20-30 -> 88%."""
        _, pipeline_result = execution_result
        wr, fv = ERN_EXPERIMENTS["C"]
        row = _find_cape_row(
            pipeline_result.aggregation.regime_aggregations,
            wr, fv, 60, Decimal("1.0"), CapeRegime.HIGH,
        )
        assert row is not None, "No CAPE 20-30 row for C/60Y"
        rate = row.success_rate
        expected = Decimal("0.88")
        assert abs(rate - expected) <= ANCHOR_TOLERANCE, (
            f"Anchor C/60Y/CAPE20-30: expected ~{expected}, got {rate} "
            f"({row.successful_cohorts}/{row.total_cohorts})"
        )

    def test_anchor_D_60Y_overall(
        self, execution_result: tuple[Any, Any]
    ) -> None:
        """Anchor D: 3.25% SWR, 50% TV, 60Y, 100% equity, Overall -> 97%."""
        plan_result, pipeline_result = execution_result
        wr, fv = ERN_EXPERIMENTS["D"]
        overall = _compute_overall_by_cell(
            plan_result, pipeline_result.results
        )
        key = (wr, fv, 60, Decimal("1.0"))
        successes, total = overall[key]
        rate = _rate(successes, total)
        expected = Decimal("0.97")
        assert abs(rate - expected) <= ANCHOR_TOLERANCE, (
            f"Anchor D/60Y/overall: expected ~{expected}, got {rate} "
            f"({successes}/{total})"
        )
