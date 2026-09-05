"""Part 49 canonical aggregation.

Groups completed Part 49 simulation results by (equity_allocation,
interest_rate) cells and produces per-cell success rates, failure
details, and terminal-value statistics.

This module belongs to the Research layer.  It does not modify the
simulation engine or the canonical datasets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import (
    Any,
)

from fbf.core.execution.pipeline.simulation import SimulationResult
from fbf.core.study.internal.parameter.configuration import (
    ParameterConfiguration,
)

# ---------------------------------------------------------------------------
# Result data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FailureRecord:
    """Detailed record of a single failed trajectory."""

    cohort_start_date: str
    equity_allocation: Decimal
    interest_rate: Decimal
    failure_month: int
    failure_state: str | None
    final_wealth: Decimal
    final_loan_balance: Decimal
    final_ltv: Decimal
    final_net_worth: Decimal
    months_simulated: int


@dataclass(frozen=True)
class CellAggregation:
    """Aggregated data for one (equity_allocation, interest_rate) cell."""

    equity_allocation: Decimal
    interest_rate: Decimal
    withdrawal_rate: Decimal
    loan_draw_rate: Decimal
    horizon_years: int
    ltv_enforcement: bool
    total_cohorts: int
    successful_cohorts: int
    failed_cohorts: int
    failure_records: tuple[FailureRecord, ...] = field(default_factory=tuple)
    terminal_wealths: tuple[Decimal, ...] = field(default_factory=tuple)
    terminal_loan_balances: tuple[Decimal, ...] = field(default_factory=tuple)
    terminal_ltvs: tuple[Decimal, ...] = field(default_factory=tuple)

    @property
    def success_rate(self) -> Decimal:
        """Success rate as a Decimal fraction (0.0 to 1.0)."""
        if self.total_cohorts == 0:
            return Decimal("0")
        return Decimal(str(self.successful_cohorts)) / Decimal(
            str(self.total_cohorts)
        )

    @property
    def failure_months(self) -> tuple[int, ...]:
        """Sorted tuple of failure month values."""
        return tuple(sorted({fr.failure_month for fr in self.failure_records}))


@dataclass(frozen=True)
class Part49AggregationResult:
    """Complete aggregation of Part 49 simulation results by cell."""

    cell_aggregations: tuple[CellAggregation, ...]
    total_units: int

    @property
    def cell_count(self) -> int:
        """Number of distinct cells."""
        return len(self.cell_aggregations)


# ---------------------------------------------------------------------------
# Aggregation function
# ---------------------------------------------------------------------------


def _extract_param(
    param: ParameterConfiguration,
    name: str,
    default: str = "0",
) -> str:
    """Extract a string parameter value, returning *default* if absent."""
    val = param.values.get(name)
    return str(val) if val is not None else default


def _build_failure_record(
    unit: Any,
    result: SimulationResult,
) -> FailureRecord:
    """Build a FailureRecord from a failed simulation unit and result."""
    equity = Decimal(str(unit.parameter_config.values.get("equity_allocation", "0")))
    ir = unit.interest_rate if unit.interest_rate is not None else Decimal("0")

    stats = result.statistics
    last_mr = (
        result.timeline.monthly_results[-1]
        if result.timeline and result.timeline.monthly_results
        else None
    )

    final_wealth = stats.final_wealth.amount if stats.final_wealth is not None else Decimal("0")
    final_loan = Decimal("0")
    final_ltv = Decimal("0")
    final_nw = Decimal("0")

    if last_mr is not None and last_mr.debt_snapshot is not None:
        final_loan = last_mr.debt_snapshot.loan_balance
        final_ltv = last_mr.debt_snapshot.ltv
        final_nw = last_mr.debt_snapshot.net_worth

    return FailureRecord(
        cohort_start_date=str(unit.cohort.start_date),
        equity_allocation=equity,
        interest_rate=ir,
        failure_month=stats.failure_month if stats.failure_month is not None else -1,
        failure_state=stats.failure_state,
        final_wealth=final_wealth,
        final_loan_balance=final_loan,
        final_ltv=final_ltv,
        final_net_worth=final_nw,
        months_simulated=stats.months_simulated,
    )


def aggregate_part49_results(
    units: tuple[Any, ...],
    simulation_results: tuple[SimulationResult, ...],
) -> Part49AggregationResult:
    """Aggregate Part 49 simulation results by (equity, interest_rate) cell.

    For each unique combination of (equity_allocation, interest_rate),
    computes the success rate and captures failure details.

    Parameters
    ----------
    units:
        Ordered tuple of ``PlannedSimulationUnit`` objects.
    simulation_results:
        Ordered tuple of ``SimulationResult`` objects from engine
        execution.  Must be index-aligned with *units*.

    Returns
    -------
    Part49AggregationResult
        Frozen aggregation with per-cell success rates and failure records.

    Raises
    ------
    ValueError
        If input sequences have mismatched lengths.
    """
    if len(units) != len(simulation_results):
        raise ValueError(
            f"Input sequences must have matching lengths: "
            f"units={len(units)}, results={len(simulation_results)}"
        )

    # Cell key -> accumulator
    cell_key_type = tuple[Decimal, Decimal]
    CellAccumulator = dict[str, Any]
    accumulators: dict[cell_key_type, CellAccumulator] = {}

    def _get_acc(key: cell_key_type) -> CellAccumulator:
        if key not in accumulators:
            accumulators[key] = {
                "success": 0,
                "total": 0,
                "failures": [],
                "wealths": [],
                "loans": [],
                "ltvs": [],
                "withdrawal_rate": Decimal("0"),
                "loan_draw_rate": Decimal("0"),
                "horizon_years": 0,
                "ltv_enforcement": False,
            }
        return accumulators[key]

    for unit, result in zip(units, simulation_results, strict=True):
        equity = Decimal(
            str(unit.parameter_config.values.get("equity_allocation", "0"))
        )
        ir = unit.interest_rate if unit.interest_rate is not None else Decimal("0")
        key = (equity, ir)
        acc = _get_acc(key)

        acc["total"] += 1
        successful = result.statistics.success if result.statistics is not None else False
        if successful:
            acc["success"] += 1

        # Capture failure details
        if not successful and result.statistics is not None:
            acc["failures"].append(_build_failure_record(unit, result))

        # Extract terminal values from statistics and last monthly result
        if result.statistics is not None and result.statistics.final_wealth is not None:
            acc["wealths"].append(result.statistics.final_wealth.amount)

        last_mr = (
            result.timeline.monthly_results[-1]
            if result.timeline and result.timeline.monthly_results
            else None
        )
        if last_mr is not None and last_mr.debt_snapshot is not None:
            acc["loans"].append(last_mr.debt_snapshot.loan_balance)
            acc["ltvs"].append(last_mr.debt_snapshot.ltv)

        # Store parameter metadata (same for all units in a cell)
        wr = unit.parameter_config.values.get("withdrawal_rate", 0)
        acc["withdrawal_rate"] = Decimal(str(wr))
        acc["loan_draw_rate"] = unit.loan_draw_rate or Decimal("0")
        horizon = unit.horizon_months
        acc["horizon_years"] = (horizon // 12) if horizon is not None else 0
        acc["ltv_enforcement"] = unit.ltv_enforcement

    # Build sorted cell aggregations
    cell_aggs = []
    for (equity, ir), acc in sorted(accumulators.items()):
        cell_aggs.append(
            CellAggregation(
                equity_allocation=equity,
                interest_rate=ir,
                withdrawal_rate=acc["withdrawal_rate"],
                loan_draw_rate=acc["loan_draw_rate"],
                horizon_years=acc["horizon_years"],
                ltv_enforcement=acc["ltv_enforcement"],
                total_cohorts=acc["total"],
                successful_cohorts=acc["success"],
                failed_cohorts=acc["total"] - acc["success"],
                failure_records=tuple(acc["failures"]),
                terminal_wealths=tuple(acc["wealths"]),
                terminal_loan_balances=tuple(acc["loans"]),
                terminal_ltvs=tuple(acc["ltvs"]),
            )
        )

    return Part49AggregationResult(
        cell_aggregations=tuple(cell_aggs),
        total_units=len(simulation_results),
    )


def get_cell_table(
    aggregation: Part49AggregationResult,
) -> list[dict[str, Any]]:
    """Format aggregation results as a list of dictionaries.

    Returns
    -------
    list[dict[str, Any]]
        One dict per cell with keys:
        equity_allocation, interest_rate, withdrawal_rate,
        loan_draw_rate, horizon_years, ltv_enforcement,
        total_cohorts, successful, failed, success_rate.
    """
    results = []
    for agg in aggregation.cell_aggregations:
        results.append(
            {
                "equity_allocation": agg.equity_allocation,
                "interest_rate": agg.interest_rate,
                "withdrawal_rate": agg.withdrawal_rate,
                "loan_draw_rate": agg.loan_draw_rate,
                "horizon_years": agg.horizon_years,
                "ltv_enforcement": agg.ltv_enforcement,
                "total_cohorts": agg.total_cohorts,
                "successful": agg.successful_cohorts,
                "failed": agg.failed_cohorts,
                "success_rate": agg.success_rate,
            }
        )
    return results
