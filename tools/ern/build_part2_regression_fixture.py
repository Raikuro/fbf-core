#!/usr/bin/env python3
"""Generate the ERN Part 2 regression fixture through the production path.

The fixture is a deterministic regression baseline for the full Part 2
reproduction subset:

    5 weights x 9 rates x 2 horizons x 5 final-value targets
    x 1,739 cohorts = 782,550 units

It is generated from ``examples/studies/ern_part2.yaml`` using the current
production dataset in ``data/inputs/ern`` and the public ``run_study``
application path. It is explicitly a regression fixture, not an independent ERN
replication oracle. The published article anchors are validated separately
against the verified canonical dataset with the article's cohort window.
"""

from __future__ import annotations

import argparse
import csv
import sys
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

import yaml

from fbf.core.application import run_study
from fbf.core.domain.model.money import Currency, Money
from fbf.core.execution import ExecutionBackend, ExecutionOptions
from fbf.core.study import StudyConfiguration

_TOOL_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TOOL_DIR.parents[1]
_DEFAULT_DATA_DIR = _REPO_ROOT / "data" / "inputs" / "ern"
_FIXTURE_DIR = _REPO_ROOT / "data" / "ern"
_DEFAULT_OUTPUT = _FIXTURE_DIR / "part2_regression_fixture.csv"
_PART2_YAML = _REPO_ROOT / "examples" / "studies" / "ern_part2.yaml"

INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)
COHORTS_PER_CELL = 1739
EXPECTED_CELLS = 5 * 9 * 2 * 5
EXPECTED_UNITS = EXPECTED_CELLS * COHORTS_PER_CELL

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

FIELDS = (
    "equity_weight",
    "withdrawal_rate",
    "horizon_years",
    "final_value_target",
    "units_run",
    "success_count",
    "success_rate",
)

type CellKey = tuple[Decimal, Decimal, int, Decimal]


def _part2_config() -> StudyConfiguration:
    return StudyConfiguration.from_yaml(
        yaml.safe_load(_PART2_YAML.read_text(encoding="utf-8"))
    )


def _expected_keys() -> list[CellKey]:
    return [
        (weight, rate, horizon, target)
        for weight in WEIGHTS
        for rate in RATES
        for horizon in HORIZONS
        for target in FV_TARGETS
    ]


def build_rows(data_dir: Path) -> list[dict[str, str]]:
    """Run the Part 2 grid and return fixture rows keyed by cell parameters."""
    config = _part2_config()
    expected_keys = _expected_keys()
    expected_key_set = set(expected_keys)

    result = run_study(
        config=config,
        data_dir=str(data_dir),
        initial_wealth=INITIAL_WEALTH,
        options=ExecutionOptions(
            backend=ExecutionBackend.FAST,
            summary_only=True,
            workers=None,
        ),
    )

    if len(result.plan.units) != EXPECTED_UNITS:
        raise ValueError(
            f"plan has {len(result.plan.units)} units, expected {EXPECTED_UNITS}"
        )

    units_run: dict[CellKey, int] = {}
    success_count: dict[CellKey, int] = {}
    for unit, simulation in zip(
        result.plan.units,
        result.experiment_result.simulation_results,
        strict=True,
    ):
        values = unit.parameter_config.values
        key: CellKey = (
            Decimal(str(values["equity_allocation"])),
            Decimal(str(values["withdrawal_rate"])),
            int(values["horizon_years"]),
            Decimal(str(values["final_value_target"])),
        )
        if key not in expected_key_set:
            raise ValueError(f"unexpected cell key: {key}")
        units_run[key] = units_run.get(key, 0) + 1
        if simulation.statistics.success:
            success_count[key] = success_count.get(key, 0) + 1

    if set(units_run) != expected_key_set:
        missing = expected_key_set - set(units_run)
        extra = set(units_run) - expected_key_set
        raise ValueError(
            f"cell coverage mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )

    rows: list[dict[str, str]] = []
    for key in expected_keys:
        weight, rate, horizon, target = key
        units = units_run[key]
        successes = success_count.get(key, 0)
        if units != COHORTS_PER_CELL:
            raise ValueError(f"cell {key} ran {units} units, expected {COHORTS_PER_CELL}")
        success_rate = (
            Decimal(successes) / Decimal(units)
        ).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
        rows.append(
            {
                "equity_weight": str(weight),
                "withdrawal_rate": str(rate),
                "horizon_years": str(horizon),
                "final_value_target": str(target),
                "units_run": str(units),
                "success_count": str(successes),
                "success_rate": str(success_rate),
            }
        )

    return rows


def write_fixture(rows: list[dict[str, str]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=_DEFAULT_DATA_DIR,
        help="Production ERN dataset directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help="Fixture CSV output path",
    )
    args = parser.parse_args(argv)

    rows = build_rows(args.data_dir)
    write_fixture(rows, args.output)
    total_units = sum(int(row["units_run"]) for row in rows)
    total_successes = sum(int(row["success_count"]) for row in rows)
    print(
        f"wrote {len(rows)} cells / {total_units:,} units "
        f"({total_successes:,} successes) to {args.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
