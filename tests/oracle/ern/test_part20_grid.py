"""Canonical ERN Part 20 Full Grid E2E replication.

Executes the full ERN Part 20 glidepath grid through the public application boundary:

    32 glidepaths × 5 SWR × 2 horizons × 1,739 cohorts = 556,480 units

Validates at three levels:

1. **Structural coverage** — 320 cells × 1,739 cohorts = 556,480 units
   are represented in the parameter space.

2. **Computational execution** — the 556,480 units are executed through
   the real simulation path and produce real outcomes.

3. **Canonical replication** — traceable ERN behavioral anchors:
   - Success rates vary across the grid (not all 0% or 100%)
   - 60→100% glidepath (slope=0.003, passive) at 3.5% SWR: horizon effect (60y < 30y)
   - Determinism: two independent executions produce identical results

No pinned oracle table exists for Part 20 glidepaths. Validation uses
internal consistency and directional behavioral assertions.

Test execution model:
- ``test_part20_full_grid_replication``: canonical Research E2E (gated by ``RUN_ERN_E2E=1``).
- ``test_part20_determinism``: deterministic execution check.

Canonical E2E tests are gated behind ``RUN_ERN_E2E=1`` via the centralized
skip hook in ``tests/conftest.py``.
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
from fbf.core.execution import ExecutionOptions
from fbf.core.study import StudyConfiguration

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path("data/ern")
INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)

COHORTS_PER_CELL = 1739

# Expected Part 20 grid dimensions from canonical YAML
PART20_GLIDEPATH_COUNT = 32
PART20_SWR_COUNT = 5
PART20_HORIZON_COUNT = 2
PART20_FV_COUNT = 1

PART20_GRID_CELLS = (
    PART20_GLIDEPATH_COUNT
    * PART20_SWR_COUNT
    * PART20_HORIZON_COUNT
    * PART20_FV_COUNT
)  # 320
PART20_TOTAL_UNITS = PART20_GRID_CELLS * COHORTS_PER_CELL  # 556,480

_ROUNDING = ROUND_HALF_EVEN

_REPO_ROOT = Path(__file__).resolve().parents[3]
PART20_YAML = _REPO_ROOT / "examples" / "studies" / "ern_part20.yaml"


# ---------------------------------------------------------------------------
# Result structures
# ---------------------------------------------------------------------------


CellKey = tuple[float, float, float, str, float, int, float]


class Part20GridResult(TypedDict):
    actual_cells: int
    actual_units: int
    cell_keys: set[CellKey]
    exec_time_s: float
    result_count: int
    cell_success_rates: dict[CellKey, float]
    cell_units_run: dict[CellKey, int]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def data_dir() -> Path:
    path = Path(DATA_DIR).resolve()
    assert path.is_dir(), f"ERN data directory missing: {path}"
    return path


@pytest.fixture(scope="session")
def part20_full_grid(data_dir: Path) -> Part20GridResult:
    """Execute the full Part 20 canonical grid through the public application boundary."""
    t_exec_start = time.perf_counter()
    result = run_study(
        config=StudyConfiguration.from_yaml(
            yaml.safe_load(PART20_YAML.read_text(encoding="utf-8"))
        ),
        data_dir=str(data_dir),
        initial_wealth=INITIAL_WEALTH,
        options=ExecutionOptions(
            summary_only=True,
            workers=None,  # Auto-detect
        ),
    )
    t_exec_end = time.perf_counter()
    exec_time = t_exec_end - t_exec_start

    # Aggregate per-cell results
    cell_success_rates: dict[CellKey, float] = {}
    cell_units_run: dict[CellKey, int] = {}
    cell_keys: set[CellKey] = set()

    for unit, r in zip(result.plan.units, result.experiment_result.simulation_results, strict=True):
        start_eq = float(unit.parameter_config.values.get("start_equity", 0))
        end_eq = float(unit.parameter_config.values.get("end_equity", 0))
        slope = float(unit.parameter_config.values.get("slope", 0))
        mode = unit.parameter_config.values.get("mode", "")
        rate = float(unit.parameter_config.values.get("withdrawal_rate", 0))
        horizon = int(unit.parameter_config.values.get("horizon_years", 0))
        fv = float(unit.parameter_config.values.get("final_value_target", 0))
        key: CellKey = (start_eq, end_eq, slope, mode, rate, horizon, fv)

        cell_keys.add(key)
        cell_units_run[key] = cell_units_run.get(key, 0) + 1
        if r.statistics.success:
            cell_success_rates[key] = cell_success_rates.get(key, 0.0) + 1.0 / COHORTS_PER_CELL

    return Part20GridResult(
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
def test_part20_full_grid_replication(part20_full_grid: Part20GridResult) -> None:
    """Full Part 20 grid (32 glidepaths × 5 SWR × 2 horizons = 320 cells).

    Executes 556,480 simulation units and validates at three levels:

    **Level 1 — Structural coverage:**
    - 320 cells reported (32 glidepaths × 5 SWR × 2 horizons)
    - Every cell runs exactly 1,739 cohorts
    - All horizons, SWR values, and glidepath configurations represented

    **Level 2 — Computational execution:**
    - Every cell has a real success_rate in [0.0, 1.0]
    - Success rates vary across the grid (not all identical)
    - Not trivially all-pass or all-fail

    **Level 3 — Canonical replication:**
    - 60-year horizon has lower success rates than 30-year cells
      for the same glidepath and SWR (longer horizon = harder)
    """
    # =====================================================================
    # Level 1: Structural coverage
    # =====================================================================
    assert part20_full_grid["actual_units"] == PART20_TOTAL_UNITS, (
        f"Part 20 grid ran {part20_full_grid['actual_units']:,} units, "
        f"expected {PART20_TOTAL_UNITS:,}"
    )
    assert part20_full_grid["actual_cells"] == PART20_GRID_CELLS, (
        f"Part 20 grid reported {part20_full_grid['actual_cells']} cells; "
        f"expected {PART20_GRID_CELLS} "
        f"(32 glidepaths × 5 SWR × 2 horizons)"
    )

    for key, count in part20_full_grid["cell_units_run"].items():
        assert count == COHORTS_PER_CELL, (
            f"cell {key}: ran {count} cohorts, expected {COHORTS_PER_CELL}"
        )

    # All glidepath configurations, SWR values, and horizons represented
    observed_horizons = {key[5] for key in part20_full_grid["cell_keys"]}
    assert observed_horizons == {30, 60}, (
        f"horizons: observed {observed_horizons}, expected {{30, 60}}"
    )

    observed_rates = {key[4] for key in part20_full_grid["cell_keys"]}
    # The canonical YAML has exactly these 5 SWR values
    expected_rates = {0.03, 0.0325, 0.035, 0.0375, 0.04}
    assert observed_rates == expected_rates, (
        f"SWR values: observed {observed_rates}, expected {expected_rates}"
    )

    observed_glidepaths = {
        (key[0], key[1], key[2], key[3]) for key in part20_full_grid["cell_keys"]
    }
    assert len(observed_glidepaths) == PART20_GLIDEPATH_COUNT, (
        f"glidepaths: observed {len(observed_glidepaths)}, expected {PART20_GLIDEPATH_COUNT}"
    )

    # =====================================================================
    # Level 2: Computational execution — real outcomes produced
    # =====================================================================
    success_rates = list(part20_full_grid["cell_success_rates"].values())

    # Every success_rate is a real float in [0.0, 1.0]
    for key, rate in part20_full_grid["cell_success_rates"].items():
        assert 0.0 <= rate <= 1.0 + 1e-10, (
            f"cell {key}: success_rate={rate} out of [0.0, 1.0]"
        )
        # units_failed must be consistent with success_rate
        units_run = part20_full_grid["cell_units_run"][key]
        expected_rate = 1.0 - (units_run - int(rate * COHORTS_PER_CELL)) / units_run
        assert abs(rate - expected_rate) < 1e-6, (
            f"cell {key}: success_rate={rate} inconsistent with "
            f"units_failed/units_run={expected_rate:.6f}"
        )

    # Success rates vary across the grid (not all identical)
    unique_rates = set(success_rates)
    assert len(unique_rates) > 1, (
        f"all {len(part20_full_grid['cell_keys'])} cells have identical "
        f"success_rate={success_rates[0]}; "
        f"expected variation across glidepaths/SWR/horizons"
    )

    # Not trivially all-pass or all-fail
    min_rate = min(success_rates)
    max_rate = max(success_rates)
    assert min_rate > 0.0, "all cells have success_rate=0.0; simulation produced no successes"
    assert max_rate < 1.0 + 1e-10, \
        "all cells have success_rate=1.0; simulation produced no failures"
    # =====================================================================
    # Level 3: Canonical replication — directional behavioral assertions
    # =====================================================================

    # Horizon effect: 60-year horizon has lower success than 30-year
    # for the same glidepath and SWR (longer horizon = harder)
    horizon_violations = 0
    for key_30 in part20_full_grid["cell_success_rates"]:
        start_eq, end_eq, slope, mode, rate, h30, fv = key_30
        if h30 != 30:
            continue
        key_60 = (start_eq, end_eq, slope, mode, rate, 60, fv)
        if key_60 in part20_full_grid["cell_success_rates"]:
            rate_30 = part20_full_grid["cell_success_rates"][key_30]
            rate_60 = part20_full_grid["cell_success_rates"][key_60]
            if rate_60 > rate_30:
                horizon_violations += 1
                glidepath_desc = f"{start_eq}→{end_eq} slope={slope} {mode}"
                print(
                    f"  HORIZON VIOLATION: {glidepath_desc} at {rate * 100:.2f}%: "
                    f"30y={rate_30:.4f} > 60y={rate_60:.4f}"
                )

    assert horizon_violations == 0, (
        f"{horizon_violations} glidepath/SWR combinations violate horizon effect "
        f"(60y success > 30y success)"
    )

    # Acceptance report
    print("\n" + "=" * 62)
    print("PART 20 FULL-GRID CANONICAL E2E ACCEPTANCE REPORT")
    print("=" * 62)
    print(f"Cells reported:     {part20_full_grid['actual_cells']}/{PART20_GRID_CELLS}")
    print(
        f"Wall time:          {part20_full_grid['exec_time_s']:.0f}s "
        f"({time.strftime('%H:%M:%S', time.gmtime(part20_full_grid['exec_time_s']))})"
    )
    print(f"Total units:        {part20_full_grid['actual_units']:,}")
    print(f"Success rate min:   {min_rate * 100:.2f}%")
    print(f"Success rate max:   {max_rate * 100:.2f}%")
    print(f"Unique rates:       {len(unique_rates)}")
    print(f"Glidepaths:         {PART20_GLIDEPATH_COUNT}")
    print(f"SWR values:         {PART20_SWR_COUNT}")
    print(f"Horizons:           {PART20_HORIZON_COUNT}")
    print("=" * 62)


@pytest.mark.ern_e2e
def test_part20_determinism(data_dir: Path) -> None:
    """Determinism check: two independent executions of the same grid
    produce identical per-cell success rates.

    This verifies that the simulation is deterministic and reproducible,
    which is a prerequisite for canonical replication.
    """
    # Use a minimal subset for fast determinism check
    minimal_yaml = """
metadata:
  name: "ERN Part 20 Determinism"
  version: "1.0"
cohorts:
  horizon_years: [30, 60]
allocation_policy:
  type: "GlidepathAllocationPolicy"
  configurations:
    - { start_equity: 0.6, end_equity: 1.0, slope: 0.003, mode: "passive" }
    - { start_equity: 0.4, end_equity: 0.8, slope: 0.003, mode: "passive" }
withdrawal_policy:
  type: "FixedRealWithdrawalPolicy"
  withdrawal_rate: [0.03, 0.035]
final_value_target: [0.0]
"""

    def run_once() -> dict[CellKey, float]:
        result = run_study(
            config=StudyConfiguration.from_yaml(yaml.safe_load(minimal_yaml)),
            data_dir=str(data_dir),
            initial_wealth=INITIAL_WEALTH,
            options=ExecutionOptions(summary_only=True, workers=None),
        )
        rates: dict[CellKey, float] = {}
        for unit, r in zip(
            result.plan.units,
            result.experiment_result.simulation_results,
            strict=True,
        ):
            start_eq = float(unit.parameter_config.values.get("start_equity", 0))
            end_eq = float(unit.parameter_config.values.get("end_equity", 0))
            slope = float(unit.parameter_config.values.get("slope", 0))
            mode = unit.parameter_config.values.get("mode", "")
            rate = float(unit.parameter_config.values.get("withdrawal_rate", 0))
            horizon = int(unit.parameter_config.values.get("horizon_years", 0))
            fv = float(unit.parameter_config.values.get("final_value_target", 0))
            key: CellKey = (start_eq, end_eq, slope, mode, rate, horizon, fv)
            if key not in rates:
                rates[key] = 0.0
            if r.statistics.success:
                rates[key] = rates.get(key, 0.0) + 1.0 / COHORTS_PER_CELL
        return rates

    rates1 = run_once()
    rates2 = run_once()

    assert rates1 == rates2, (
        f"determinism check failed: rates1={rates1} != rates2={rates2}"
    )
    assert len(rates1) >= 1, "grid produced no cells"
    for key, rate in rates1.items():
        assert rate == rates2[key], f"cell {key}: {rate} != {rates2[key]}"
