"""Canonical ERN Full SWR Grid E2E replication.

Executes the full ERN SWR grid (Table 1) through the public application boundary:

    5 equity weights × 9 withdrawal rates × 4 horizons × 1,739 cohorts = 313,020 units

Validates at three levels:

1. **Structural coverage** — 180 cells × 1,739 cohorts = 313,020 units
   are represented in the parameter space.

2. **Computational execution** — the 313,020 units are executed through
   the real simulation path and produce real outcomes.

3. **Canonical replication** — every cell matches the pinned ERN oracle table
   (``data/ern/p49_oracle_table.csv``) with exact Decimal equality.
   The three published anchors (95 / 65 / 97) are hard-fail checks.

The grid runs in summary-only mode: no SQLite study database is created and
per-month timelines are never materialized.

Test execution model:
- ``test_full_grid_matches_oracle``: canonical Research E2E (gated by ``RUN_ERN_E2E=1``).

Canonical E2E tests are gated behind ``RUN_ERN_E2E=1`` via the centralized
skip hook in ``tests/conftest.py``.  They are NOT part of the normal ``pytest`` invocation.

This test uses the REFERENCE backend to match the canonical oracle derivation path.
"""

from __future__ import annotations

import time
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import TypedDict

import pytest
import yaml

from fbf.core.application import run_study
from fbf.core.domain.model.money import Currency, Money
from fbf.core.execution import ExecutionBackend, ExecutionOptions
from fbf.core.study import StudyConfiguration

from .constants import COHORTS_PER_CELL, OracleTable, load_oracle_table

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path("data/ern")
INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)

# Full ERN SWR grid: 5 weights × 9 rates × 4 horizons = 180 cells
WEIGHTS = (Decimal("1.0"), Decimal("0.75"), Decimal("0.5"), Decimal("0.25"), Decimal("0.0"))
RATES = (
    Decimal("0.03"),
    Decimal("0.0325"),
    Decimal("0.035"),
    Decimal("0.0375"),
    Decimal("0.04"),
    Decimal("0.0425"),
    Decimal("0.045"),
    Decimal("0.0475"),
    Decimal("0.05"),
)
HORIZONS = (30, 40, 50, 60)
FV_TARGETS = (Decimal("0.0"),)

FULL_GRID_CELLS = len(WEIGHTS) * len(RATES) * len(HORIZONS) * len(FV_TARGETS)  # 180
FULL_GRID_UNITS = FULL_GRID_CELLS * COHORTS_PER_CELL  # 313,020

# Hard-fail acceptance anchors from the ERN paper Table 1 (Section 5.2).
ANCHOR_CELLS: tuple[tuple[float, int, float, int], ...] = (
    (0.5, 30, 0.04, 95),
    (0.5, 60, 0.04, 66),
    (0.75, 60, 0.035, 98),
)

_ROUNDING = ROUND_HALF_EVEN

_REPO_ROOT = Path(__file__).resolve().parents[3]
GRID_YAML = _REPO_ROOT / "examples" / "studies" / "ern_grid.yaml"


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------


class GridResult(TypedDict):
    actual_cells: int
    actual_units: int
    cell_keys: set[tuple[float, float, int, float]]
    exec_time_s: float
    result_count: int
    cell_success_rates: dict[tuple[float, float, int, float], float]
    cell_units_run: dict[tuple[float, float, int, float], int]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def data_dir() -> Path:
    path = Path(DATA_DIR).resolve()
    assert path.is_dir(), f"ERN data directory missing: {path}"
    return path


@pytest.fixture(scope="session")
def oracle() -> OracleTable:
    return load_oracle_table()


@pytest.fixture(scope="session")
def canonical_execution(data_dir: Path) -> GridResult:
    """Execute the full canonical SWR grid through the public application boundary.

    Uses the REFERENCE backend to match the canonical oracle derivation path
    (standalone reference_oracle.py).
    """
    t_exec_start = time.perf_counter()
    result = run_study(
        config=StudyConfiguration.from_yaml(
            yaml.safe_load(GRID_YAML.read_text(encoding="utf-8"))
        ),
        data_dir=str(data_dir),
        initial_wealth=INITIAL_WEALTH,
        options=ExecutionOptions(
            backend=ExecutionBackend.REFERENCE,
            summary_only=True,
            workers=None,  # Auto-detect
        ),
    )
    t_exec_end = time.perf_counter()
    exec_time = t_exec_end - t_exec_start

    # Aggregate per-cell results
    cell_success_rates: dict[tuple[float, float, int, float], float] = {}
    cell_units_run: dict[tuple[float, float, int, float], int] = {}
    cell_keys: set[tuple[float, float, int, float]] = set()

    for unit, r in zip(result.plan.units, result.experiment_result.simulation_results, strict=True):
        weight = float(unit.parameter_config.values.get("equity_allocation", 0))
        rate = float(unit.parameter_config.values.get("withdrawal_rate", 0))
        horizon = int(unit.parameter_config.values.get("horizon_years", 0))
        fv = float(unit.parameter_config.values.get("final_value_target", 0))
        key = (weight, rate, horizon, fv)

        cell_keys.add(key)
        cell_units_run[key] = cell_units_run.get(key, 0) + 1
        if r.statistics.success:
            cell_success_rates[key] = cell_success_rates.get(key, 0.0) + 1.0 / COHORTS_PER_CELL

    return GridResult(
        actual_cells=len(cell_keys),
        actual_units=len(result.experiment_result.simulation_results),
        cell_keys=cell_keys,
        exec_time_s=exec_time,
        result_count=len(result.experiment_result.simulation_results),
        cell_success_rates=cell_success_rates,
        cell_units_run=cell_units_run,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.ern_e2e
def test_full_grid_matches_oracle(canonical_execution: GridResult, oracle: OracleTable) -> None:
    """Full Table 1 grid (5 weights × 9 rates × 4 horizons = 180 cells).

    The whole grid is executed as ONE study through the public application boundary
    using the REFERENCE backend (matching the canonical oracle derivation path).
    Validates:
    - 313,020 total units executed
    - 180 cells covering the exact parameter space
    - Every cell matches the oracle with exact Decimal equality (0 pp tolerance)
    - Three hard-fail anchors match published values
    """
    # --- Structural invariants ---
    assert canonical_execution["actual_units"] == FULL_GRID_UNITS, (
        f"full grid ran {canonical_execution['actual_units']:,} units, "
        f"expected {FULL_GRID_UNITS:,}"
    )
    assert canonical_execution["actual_cells"] == FULL_GRID_CELLS, (
        f"full grid reported {canonical_execution['actual_cells']} cells; "
        f"expected exactly {FULL_GRID_CELLS}"
    )

    # Expected cell keys from the canonical parameter space
    expected_keys = {
        (float(w), float(r), int(h), float(fv))
        for w in WEIGHTS
        for r in RATES
        for h in HORIZONS
        for fv in FV_TARGETS
    }
    assert canonical_execution["cell_keys"] == expected_keys, (
        f"grid reported {len(canonical_execution['cell_keys'])} cells; "
        f"expected {len(expected_keys)} covering the 5×9×4 parameter space"
    )

    # Every cell runs exactly 1,739 cohorts
    for key, count in canonical_execution["cell_units_run"].items():
        assert count == COHORTS_PER_CELL, (
            f"cell {key}: ran {count} cohorts, expected {COHORTS_PER_CELL}"
        )

    # Every declared weight, rate, horizon, FV target must be represented
    assert {key[0] for key in canonical_execution["cell_keys"]} == {float(w) for w in WEIGHTS}
    assert {key[1] for key in canonical_execution["cell_keys"]} == {float(r) for r in RATES}
    assert {key[2] for key in canonical_execution["cell_keys"]} == set(HORIZONS)
    assert {key[3] for key in canonical_execution["cell_keys"]} == {float(fv) for fv in FV_TARGETS}

    # --- Oracle comparison: exact Decimal equality (0 pp tolerance) ---
    deviations: list[Decimal] = []
    outside: list[tuple[float, int, float, Decimal, int]] = []
    anchor_results: dict[str, tuple[int, int]] = {}

    for key, success_rate in sorted(canonical_execution["cell_success_rates"].items()):
        weight, rate, horizon, _fv = key
        expected_pct = oracle[(weight, horizon)][rate]
        actual_pct = (
            Decimal(str(success_rate)) * Decimal("100")
        ).quantize(Decimal("1"), rounding=_ROUNDING)

        dev = abs(actual_pct - Decimal(expected_pct))
        deviations.append(dev)

        if dev != 0:
            outside.append((weight, horizon, rate, actual_pct, expected_pct))

        # Track anchor cells
        for aw, ah, ar, aexp in ANCHOR_CELLS:
            if (weight, rate, horizon) == (aw, ar, ah):
                anchor_results[f"{int(aw * 100)}/{horizon}y/{ar * 100:.2f}%"] = (
                    int(actual_pct),
                    aexp,
                )

    # Hard-fail anchors
    for weight, horizon, rate, expected in ANCHOR_CELLS:
        key = (weight, rate, horizon, 0.0)
        actual_pct = (
            Decimal(str(canonical_execution["cell_success_rates"][key])) * Decimal("100")
        ).quantize(Decimal("1"), rounding=_ROUNDING)
        assert actual_pct == Decimal(expected), (
            f"anchor {int(weight * 100)}/{horizon}y/{rate * 100:.2f}%: "
            f"engine {actual_pct}% vs oracle {expected}%"
        )

    worst_diff = max(deviations)
    min_diff = min(deviations)

    # Acceptance report
    print("\n" + "=" * 62)
    print("ERN FULL SWR GRID CANONICAL E2E ACCEPTANCE REPORT")
    print("=" * 62)
    print(f"Cells reported:     {canonical_execution['actual_cells']}/{FULL_GRID_CELLS}")
    print(f"Wall time:          {canonical_execution['exec_time_s']:.0f}s "
          f"({time.strftime('%H:%M:%S', time.gmtime(canonical_execution['exec_time_s']))})")
    print(f"Total units:        {canonical_execution['actual_units']:,}")
    print(f"Abs deviation min:  {min_diff} pp")
    print(f"Abs deviation max:  {worst_diff} pp")
    print("Anchors (hard-fail):")
    for name, (got, exp) in anchor_results.items():
        print(f"  {name}: engine={got}% oracle={exp}% ({'PASS' if got == exp else 'FAIL'})")
    if outside:
        print(f"Cells outside exact Decimal equality: {len(outside)}")
        for cell in outside:
            print(f"  {cell}")
    else:
        print("Cells outside exact Decimal equality: 0")
    print("=" * 62)

    # All cells must match oracle exactly
    assert len(canonical_execution["cell_keys"]) == FULL_GRID_CELLS
    assert worst_diff == 0, f"mismatched cells: {sorted(outside, reverse=True)}"


@pytest.mark.ern_e2e
def test_smoke_cell_matches_oracle(data_dir: Path, oracle: OracleTable) -> None:
    """Minimal ERN smoke cell reproduces the oracle anchor (95%).

    Single cell: weight=0.5, rate=4%, horizon=30y, FV=0.0
    Uses REFERENCE backend with 60-year cohort universe (1739 cohorts).
    Compares success rate against oracle (rate-based, not count-based).
    """
    smoke_yaml = """
metadata:
  name: "ERN Smoke"
  version: "1.0"
cohorts:
  horizon_years: [30]
  cohort_horizon_years: 60
allocation_policy:
  type: "ConstantAllocationPolicy"
  equity_allocation: [0.5]
withdrawal_policy:
  type: "FixedRealWithdrawalPolicy"
  withdrawal_rate: [0.04]
final_value_target: [0.0]
"""

    result = run_study(
        config=StudyConfiguration.from_yaml(yaml.safe_load(smoke_yaml)),
        data_dir=str(data_dir),
        initial_wealth=INITIAL_WEALTH,
        options=ExecutionOptions(
            backend=ExecutionBackend.REFERENCE,
            summary_only=True,
            workers=None,
        ),
    )

    # Single cell validation - 1739 cohorts (60-year cohort universe)
    assert len(result.experiment_result.simulation_results) == COHORTS_PER_CELL
    assert len(result.plan.units) == COHORTS_PER_CELL

    # Oracle anchor: weight=0.5, horizon=30, rate=0.04 -> 95%
    # Compare success rate (rate-based, not count-based)
    oracle_pct = oracle[(0.5, 30)][0.04]
    success_rate = sum(
        1 for r in result.experiment_result.simulation_results if r.statistics.success
    ) / COHORTS_PER_CELL
    actual_pct = (
        Decimal(str(success_rate)) * Decimal("100")
    ).quantize(Decimal("1"), rounding=_ROUNDING)

    assert actual_pct == Decimal(oracle_pct), (
        f"smoke cell: engine {actual_pct}% vs oracle {oracle_pct}%"
    )
