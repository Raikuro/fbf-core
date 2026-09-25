"""Part 19 pipeline — Experiments A and B.

Experiment A: Fixed 3.5% SWR failure rates using existing Part 20 infrastructure.
Experiment B: Failsafe/Percentile SWR using existing Part 20 percentile-search infrastructure.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from fbf.core.execution import ExecutionOptions
from fbf.core.research.part19_strategies import (
    part19_experiment_a_strategies,
    part19_experiment_b_strategies,
)
from fbf.core.research.part20_aggregation import PART20_FAILURE_PROBABILITIES, percentile_swrs
from fbf.core.research.part20_pipeline import (
    SearchCache,
    run_fixed_swr_grid,
    run_percentile_search,
)
from fbf.core.research.part20_planner import Part20ExecutionContext

__all__ = [
    "PART19_EXPERIMENT_A_SWR",
    "PART19_EXPERIMENT_A_HORIZON_YEARS",
    "PART19_EXPERIMENT_A_FV_TARGETS",
    "Part19ExperimentACell",
    "run_experiment_a",
    "PART19_EXPERIMENT_B_HORIZON_YEARS",
    "PART19_EXPERIMENT_B_FV_TARGET",
    "PART19_EXPERIMENT_B_CAPE_CONDITIONS",
    "PART19_EXPERIMENT_B_PERCENTILES",
    "Part19ExperimentBCell",
    "run_experiment_b",
]

# Fixed parameters for Part 19 Experiment A
PART19_EXPERIMENT_A_SWR = Decimal("0.035")  # 3.5%
PART19_EXPERIMENT_A_HORIZON_YEARS = 60
PART19_EXPERIMENT_A_FV_TARGETS = (Decimal("0"), Decimal("0.5"), Decimal("1"))

# Fixed parameters for Part 19 Experiment B
PART19_EXPERIMENT_B_HORIZON_YEARS = 60
PART19_EXPERIMENT_B_FV_TARGET = Decimal("0")
PART19_EXPERIMENT_B_CAPE_CONDITIONS = ("ALL", "HIGH")

# Percentile probabilities (failsafe=0%, p01, p03, p05, p10, p25)
PART19_EXPERIMENT_B_PERCENTILES = PART20_FAILURE_PROBABILITIES


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


@dataclass(frozen=True, slots=True)
class Part19ExperimentBCell:
    """One Part 19 Experiment B cell result.

    Contains the percentile SWR metrics for one strategy × CAPE condition.
    """

    strategy_id: str
    horizon_years: int
    final_value_target: Decimal
    cape_condition: str  # "ALL" or "HIGH"
    cohort_count: int
    per_cohort_swrs: tuple[Decimal, ...]

    @property
    def percentiles(self) -> dict[Decimal, Decimal]:
        """Percentile SWRs: failsafe (p00), p01, p03, p05, p10, p25."""
        return percentile_swrs(self.per_cohort_swrs)

    @property
    def failsafe(self) -> Decimal:
        """Failsafe SWR = p00 (0% failure probability)."""
        return self.percentiles[Decimal("0")]

    @property
    def p01(self) -> Decimal:
        """1st percentile SWR."""
        return self.percentiles[Decimal("0.01")]

    @property
    def p03(self) -> Decimal:
        """3rd percentile SWR."""
        return self.percentiles[Decimal("0.03")]

    @property
    def p05(self) -> Decimal:
        """5th percentile SWR."""
        return self.percentiles[Decimal("0.05")]

    @property
    def p10(self) -> Decimal:
        """10th percentile SWR."""
        return self.percentiles[Decimal("0.10")]

    @property
    def p25(self) -> Decimal:
        """25th percentile SWR."""
        return self.percentiles[Decimal("0.25")]


def run_experiment_b(
    ctx: Part20ExecutionContext,
    *,
    cape_conditions: Sequence[str] = PART19_EXPERIMENT_B_CAPE_CONDITIONS,
    options: ExecutionOptions | None = None,
    cache: SearchCache | None = None,
) -> tuple[Part19ExperimentBCell, ...]:
    """Execute Part 19 Experiment B: Failsafe/Percentile SWR.

    Args:
        ctx: Part20ExecutionContext with cohort populations and trajectory.
        cape_conditions: CAPE conditions to test (default: "ALL", "HIGH").
        options: Execution options (default: summary_only=True, auto workers).
        cache: Optional search cache for cross-experiment reuse.

    Returns:
        Tuple of Part19ExperimentBCell results for each
        strategy × CAPE condition combination.
        Expected: 45 strategies × 2 CAPE = 90 cells.
    """
    if options is None:
        options = ExecutionOptions(summary_only=True)

    strategies = part19_experiment_b_strategies()

    # Get cohort populations
    all_dates = ctx.populations.all_dates  # 1,739 cohorts (All CAPE)
    high_dates = ctx.populations.high_dates  # 383 cohorts (CAPE > 20)

    cape_populations = {
        "ALL": all_dates,
        "HIGH": high_dates,
    }

    cells: list[Part19ExperimentBCell] = []

    for cape_cond in cape_conditions:
        if cape_cond not in cape_populations:
            raise ValueError(f"Unknown CAPE condition: {cape_cond}")

        cohort_dates = cape_populations[cape_cond]

        # Run percentile search for this CAPE condition
        search_results = run_percentile_search(
            ctx=ctx,
            strategies=strategies,
            cohort_dates=cohort_dates,
            horizon_years=PART19_EXPERIMENT_B_HORIZON_YEARS,
            final_value_target=PART19_EXPERIMENT_B_FV_TARGET,
            cape_regime=cape_cond,
            options=options,
            step_label=f"part19_expB_{cape_cond}",
            cache=cache,
        )

        # Convert SWRSearchResult to Part19ExperimentBCell
        for strategy_id, search_result in search_results.items():
            cells.append(
                Part19ExperimentBCell(
                    strategy_id=strategy_id,
                    horizon_years=search_result.horizon_years,
                    final_value_target=search_result.final_value_target,
                    cape_condition=cape_cond,
                    cohort_count=search_result.cohort_count,
                    per_cohort_swrs=search_result.per_cohort_swrs,
                )
            )

    # Verify expected cell count
    expected_cells = len(strategies) * len(cape_conditions)
    if len(cells) != expected_cells:
        raise RuntimeError(
            f"Part 19 Experiment B produced {len(cells)} cells, expected {expected_cells}"
        )

    # Verify deterministic ordering: sort by (cape_condition, strategy_id) for reproducibility
    cells.sort(key=lambda c: (c.cape_condition, c.strategy_id))

    return tuple(cells)
