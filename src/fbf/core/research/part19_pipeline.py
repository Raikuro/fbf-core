"""Part 19 pipeline — Experiment A: Fixed 3.5% SWR failure rates.

Orchestrates the Part 19 Experiment A execution using existing Part 20
infrastructure: Part20ExecutionContext and run_fixed_swr_grid.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from fbf.core.execution import ExecutionOptions
from fbf.core.research.part19_strategies import part19_experiment_a_strategies
from fbf.core.research.part20_pipeline import run_fixed_swr_grid
from fbf.core.research.part20_planner import Part20ExecutionContext

__all__ = [
    "PART19_EXPERIMENT_A_SWR",
    "PART19_EXPERIMENT_A_HORIZON_YEARS",
    "PART19_EXPERIMENT_A_FV_TARGETS",
    "Part19ExperimentACell",
    "run_experiment_a",
]

# Fixed parameters for Part 19 Experiment A
PART19_EXPERIMENT_A_SWR = Decimal("0.035")  # 3.5%
PART19_EXPERIMENT_A_HORIZON_YEARS = 60
PART19_EXPERIMENT_A_FV_TARGETS = (Decimal("0"), Decimal("0.5"), Decimal("1"))


@dataclass(frozen=True, slots=True)
class Part19ExperimentACell:
    """One Part 19 Experiment A cell result.

    Extends FailureRateCell with the CAPE condition label for clarity.
    """

    strategy_id: str
    horizon_years: int
    withdrawal_rate: Decimal
    final_value_target: Decimal
    cape_condition: str  # "ALL" or "HIGH"
    failures: int
    total_cohorts: int

    @property
    def failure_rate(self) -> Decimal:
        if self.total_cohorts == 0:
            return Decimal("0")
        return Decimal(self.failures) / Decimal(self.total_cohorts)


def run_experiment_a(
    ctx: Part20ExecutionContext,
    *,
    fv_targets: Sequence[Decimal] = PART19_EXPERIMENT_A_FV_TARGETS,
    cape_conditions: Sequence[str] = ("ALL", "HIGH"),
    options: ExecutionOptions | None = None,
) -> tuple[Part19ExperimentACell, ...]:
    """Execute Part 19 Experiment A: fixed 3.5% SWR failure rates.

    Args:
        ctx: Part20ExecutionContext with cohort populations and trajectory.
        fv_targets: Final value targets to test (default: 0%, 50%, 100%).
        cape_conditions: CAPE conditions to test (default: "ALL", "HIGH").
        options: Execution options (default: summary_only=True, auto workers).

    Returns:
        Tuple of Part19ExperimentACell results for each
        strategy × FV target × CAPE condition combination.
        Expected: 27 strategies × 3 FV × 2 CAPE = 162 cells.
    """
    if options is None:
        options = ExecutionOptions(summary_only=True)

    strategies = part19_experiment_a_strategies()

    # Get cohort populations
    all_dates = ctx.populations.all_dates  # 1,739 cohorts (All CAPE)
    high_dates = ctx.populations.high_dates  # 383 cohorts (CAPE > 20)

    cape_populations = {
        "ALL": all_dates,
        "HIGH": high_dates,
    }

    cells: list[Part19ExperimentACell] = []

    for fv in fv_targets:
        for cape_cond in cape_conditions:
            if cape_cond not in cape_populations:
                raise ValueError(f"Unknown CAPE condition: {cape_cond}")

            cohort_dates = cape_populations[cape_cond]

            # Run fixed-SWR grid for this FV target and CAPE condition
            fr_cells = run_fixed_swr_grid(
                ctx=ctx,
                strategies=strategies,
                cohort_dates=cohort_dates,
                horizon_years=PART19_EXPERIMENT_A_HORIZON_YEARS,
                withdrawal_rates=(PART19_EXPERIMENT_A_SWR,),
                final_value_target=fv,
                population=cape_cond,  # Pass through for labeling
                options=options,
            )

            # Convert to Part19ExperimentACell with explicit CAPE condition
            for fr_cell in fr_cells:
                cells.append(
                    Part19ExperimentACell(
                        strategy_id=fr_cell.strategy_id,
                        horizon_years=fr_cell.horizon_years,
                        withdrawal_rate=fr_cell.withdrawal_rate,
                        final_value_target=fv,
                        cape_condition=cape_cond,
                        failures=fr_cell.failures,
                        total_cohorts=fr_cell.total_cohorts,
                    )
                )

    # Verify expected cell count
    expected_cells = len(strategies) * len(fv_targets) * len(cape_conditions)
    if len(cells) != expected_cells:
        raise RuntimeError(
            f"Part 19 Experiment A produced {len(cells)} cells, expected {expected_cells}"
        )

    return tuple(cells)
