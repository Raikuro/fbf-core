"""Canonical ERN Part 2 final-value-target replication E2E.

The full production regression grid is:

    5 weights x 9 rates x 2 horizons x 5 final-value targets
    x 1,739 cohorts = 450 cells / 782,550 units

The full grid is compared cell-by-cell against
``data/ern/part2_regression_fixture.csv``. That fixture is generated through
the production path by ``tools/ern/build_part2_regression_fixture.py`` and is
regression evidence only.

Independent replication evidence is provided by the four Part 2 success-rate
anchors stated in the article. Those anchors are evaluated on the frozen
``data/ern/published_2016`` dataset because the original article uses the
September 2016 data vintage; the current production dataset extends through
June 2026 and is covered by the regression grid instead.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

import pytest
import yaml

from fbf.core.application import run_study
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.money import Currency, Money
from fbf.core.execution import ExecutionBackend, ExecutionOptions
from fbf.core.study import StudyConfiguration
from tests.support.ern.constants import (
    WORKBOOK_ORACLE_CSV,
    OracleTable,
    load_oracle_table,
)
from tests.support.ern.published_dataset import load_published_ern_dataset

_REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = _REPO_ROOT / "data" / "ern"
PART2_YAML = _REPO_ROOT / "examples" / "studies" / "ern_part2.yaml"

INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)
COHORTS_PER_CELL = 1739

WEIGHTS = (
    Decimal("1.0"),
    Decimal("0.75"),
    Decimal("0.5"),
    Decimal("0.25"),
    Decimal("0.0"),
)
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
HORIZONS = (30, 60)
FV_TARGETS = (
    Decimal("0.0"),
    Decimal("0.25"),
    Decimal("0.5"),
    Decimal("0.75"),
    Decimal("1.0"),
)

type CellKey = tuple[Decimal, Decimal, int, Decimal]

ANCHORS = (
    (Decimal("1.0"), Decimal("0.035"), 60, Decimal("0.0"), Decimal("98")),
    (Decimal("1.0"), Decimal("0.035"), 60, Decimal("1.0"), Decimal("96")),
    (Decimal("1.0"), Decimal("0.04"), 30, Decimal("0.0"), Decimal("97")),
    (Decimal("1.0"), Decimal("0.04"), 30, Decimal("1.0"), Decimal("80")),
)
ANCHOR_TOLERANCE_PP = Decimal("1")


@dataclass(frozen=True)
class Part2Execution:
    actual_cells: int
    actual_units: int
    cell_units_run: dict[CellKey, int]
    cell_success_count: dict[CellKey, int]
    exec_time_s: float


def _key_from_values(values: Mapping[str, int | float | bool | str]) -> CellKey:
    return (
        Decimal(str(values["equity_allocation"])),
        Decimal(str(values["withdrawal_rate"])),
        int(str(values["horizon_years"])),
        Decimal(str(values["final_value_target"])),
    )


def _run_part2(config: StudyConfiguration) -> Part2Execution:
    start = time.perf_counter()
    result = run_study(
        config=config,
        data_dir=str(DATA_DIR),
        initial_wealth=INITIAL_WEALTH,
        options=ExecutionOptions(
            backend=ExecutionBackend.FAST,
            summary_only=True,
            workers=None,
        ),
    )
    elapsed = time.perf_counter() - start

    cell_units_run: dict[CellKey, int] = {}
    cell_success_count: dict[CellKey, int] = {}
    for unit, simulation in zip(
        result.plan.units,
        result.experiment_result.simulation_results,
        strict=True,
    ):
        key = _key_from_values(unit.parameter_config.values)
        cell_units_run[key] = cell_units_run.get(key, 0) + 1
        if simulation.statistics.success:
            cell_success_count[key] = cell_success_count.get(key, 0) + 1

    return Part2Execution(
        actual_cells=len(cell_units_run),
        actual_units=len(result.experiment_result.simulation_results),
        cell_units_run=cell_units_run,
        cell_success_count=cell_success_count,
        exec_time_s=elapsed,
    )


@pytest.fixture(scope="session")
def part2_config() -> StudyConfiguration:
    return StudyConfiguration.from_yaml(
        yaml.safe_load(PART2_YAML.read_text(encoding="utf-8"))
    )


@pytest.fixture(scope="session")
def part2_execution(part2_config: StudyConfiguration) -> Part2Execution:
    return _run_part2(part2_config)


@pytest.fixture(scope="session")
def part1_workbook_oracle() -> OracleTable:
    return load_oracle_table(WORKBOOK_ORACLE_CSV)


@pytest.fixture(scope="session")
def published_dataset() -> Dataset:
    return load_published_ern_dataset()


@pytest.mark.ern_e2e
def test_part2_fv0_matches_part1_workbook_oracle(
    part2_execution: Part2Execution,
    part1_workbook_oracle: OracleTable,
) -> None:
    fv0_keys = tuple(
        (weight, rate, horizon, Decimal("0.0"))
        for weight in WEIGHTS
        for rate in RATES
        for horizon in HORIZONS
    )
    assert len(fv0_keys) == 90

    mismatches: list[tuple[CellKey, Decimal, int]] = []
    for key in fv0_keys:
        weight, rate, horizon, _target = key
        assert part2_execution.cell_units_run.get(key, 0) == COHORTS_PER_CELL

        success_count = part2_execution.cell_success_count.get(key, 0)
        actual_pct = (
            Decimal(success_count) / Decimal(COHORTS_PER_CELL) * Decimal("100")
        ).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)
        expected_pct = part1_workbook_oracle[(float(weight), horizon)][float(rate)]
        if actual_pct != Decimal(expected_pct):
            mismatches.append((key, actual_pct, expected_pct))

    print("\n" + "=" * 62)
    print("ERN PART 2.2 FV=0 CROSS-CHECK AGAINST PART 1")
    print("=" * 62)
    print(f"Cells checked: {len(fv0_keys)}")
    print(f"Mismatches:    {len(mismatches)}")
    for key, actual, expected in mismatches[:20]:
        print(f"  {key}: actual={actual}%, part1={expected}%")
    print("=" * 62)

    assert not mismatches, (
        f"{len(mismatches)} FV=0 Part 2 cells differ from the Part 1 workbook oracle"
    )


@pytest.mark.ern_e2e
def test_part2_published_anchors(
    published_dataset: Dataset,
) -> None:
    config = StudyConfiguration(
        name="part2-published-anchors",
        description="",
        version="",
        allocation_policy_type="ConstantAllocationPolicy",
        allocation_policy_values=(Decimal("1.0"),),
        withdrawal_policy_type="FixedRealWithdrawalPolicy",
        withdrawal_policy_values=(Decimal("0.035"), Decimal("0.04")),
        horizon_years=(30, 60),
        final_value_target_values=(Decimal("0.0"), Decimal("1.0")),
        expense_ratio=Decimal("0.0005"),
        cohort_horizon_years=60,
        cohort_start_date=date(1871, 1, 1),
        cohort_end_date=date(2015, 11, 1),
    )
    result = run_study(
        config=config,
        data_dir=str(DATA_DIR),
        initial_wealth=INITIAL_WEALTH,
        options=ExecutionOptions(
            backend=ExecutionBackend.FAST,
            summary_only=True,
            workers=None,
        ),
        dataset=published_dataset,
    )

    totals: dict[CellKey, int] = {}
    successes: dict[CellKey, int] = {}
    for unit, simulation in zip(
        result.plan.units,
        result.experiment_result.simulation_results,
        strict=True,
    ):
        key = _key_from_values(unit.parameter_config.values)
        totals[key] = totals.get(key, 0) + 1
        if simulation.statistics.success:
            successes[key] = successes.get(key, 0) + 1

    for weight, rate, horizon, target, published in ANCHORS:
        key = (weight, rate, horizon, target)
        assert totals[key] == COHORTS_PER_CELL
        actual = (
            Decimal(successes.get(key, 0))
            / Decimal(COHORTS_PER_CELL)
            * Decimal("100")
        )
        deviation = abs(actual - published)
        assert deviation <= ANCHOR_TOLERANCE_PP, (
            f"anchor {key}: actual={actual}%, published={published}%, "
            f"deviation={deviation}pp"
        )
