"""Part 3 CAPE regime aggregation.

Groups completed Part 3 simulation results by CAPE regime and produces
per-group success rates.  Consumes cohorts, parameter configurations,
and CAPE metadata from the manifest, plus engine execution results.

This module belongs to the Research layer.  It does not modify the
simulation engine or the canonical datasets.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from fbf.core.domain.policies.cape_regime import CapeRegime
from fbf.core.execution.pipeline.simulation import SimulationResult
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration

# ---------------------------------------------------------------------------
# Result data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegimeAggregation:
    """Aggregated success-rate data for one (horizon, parameter, regime) cell."""

    horizon_years: int
    equity_allocation: Decimal
    withdrawal_rate: Decimal
    terminal_target: Decimal | None
    cape_regime: CapeRegime
    successful_cohorts: int
    total_cohorts: int

    @property
    def success_rate(self) -> Decimal:
        """Success rate as a Decimal fraction (0.0 to 1.0)."""
        if self.total_cohorts == 0:
            return Decimal("0")
        return Decimal(str(self.successful_cohorts)) / Decimal(
            str(self.total_cohorts)
        )


@dataclass(frozen=True)
class Part3AggregationResult:
    """Complete aggregation of Part 3 simulation results by CAPE regime."""

    regime_aggregations: tuple[RegimeAggregation, ...]
    total_units: int
    excluded_no_cape: int

    @property
    def regimes(self) -> tuple[CapeRegime, ...]:
        """Unique CAPE regimes present in the aggregation."""
        seen: list[CapeRegime] = []
        for agg in self.regime_aggregations:
            if agg.cape_regime not in seen:
                seen.append(agg.cape_regime)
        return tuple(seen)


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


def aggregate_part3_results(
    cohorts: tuple[CohortSpecification, ...],
    param_configs: tuple[ParameterConfiguration, ...],
    simulation_results: tuple[SimulationResult, ...],
    get_cape_metadata: Callable[[CohortSpecification], tuple[Decimal | None, str | None]],
) -> Part3AggregationResult:
    """Aggregate Part 3 simulation results by CAPE regime.

    For each unique combination of (horizon, equity_allocation,
    withdrawal_rate, terminal_target, CAPE_regime), computes the
    success rate across all cohorts in that cell.

    CAPE regime is obtained from the manifest metadata via
    ``get_cape_metadata`` — no runtime CAPE classification is
    performed.

    Parameters
    ----------
    cohorts:
        Ordered tuple of cohort specifications, one per simulation run.
    param_configs:
        Ordered tuple of parameter configurations, one per simulation run.
    simulation_results:
        Ordered tuple of ``SimulationResult`` objects from engine
        execution.  Must be index-aligned with *cohorts*.
    get_cape_metadata:
        Callable mapping a ``CohortSpecification`` to its CAPE
        ``(value, regime_string)`` pair from the manifest.  Both
        values may be ``None`` when CAPE data is unavailable.

    Returns
    -------
    Part3AggregationResult
        Frozen aggregation with per-regime success rates.

    Raises
    ------
    ValueError
        If input sequences have mismatched lengths.
    """
    if not (len(cohorts) == len(param_configs) == len(simulation_results)):
        raise ValueError(
            f"Input sequences must have matching lengths: "
            f"cohorts={len(cohorts)}, param_configs={len(param_configs)}, "
            f"results={len(simulation_results)}"
        )

    # Aggregation key -> (success_count, total_count)
    agg: dict[
        tuple[int, Decimal, Decimal, Decimal | None, CapeRegime],
        tuple[int, int],
    ] = defaultdict(lambda: (0, 0))

    excluded_no_cape = 0

    for cohort, param, result in zip(
        cohorts, param_configs, simulation_results, strict=True
    ):
        horizon_years = int(_extract_param(param, "horizon_years", "0"))
        equity = Decimal(_extract_param(param, "equity_allocation", "0"))
        withdrawal = Decimal(_extract_param(param, "withdrawal_rate", "0"))
        raw_target = param.values.get("final_value_target")
        target: Decimal | None = (
            Decimal(str(raw_target)) if raw_target is not None else None
        )

        # Look up CAPE metadata from the manifest
        _cape_value, cape_regime_str = get_cape_metadata(cohort)
        if cape_regime_str is None:
            regime = CapeRegime.BELOW_15
            excluded_no_cape += 1
        else:
            regime = CapeRegime[cape_regime_str]

        # Determine success from simulation statistics
        successful = (
            result.statistics.success
            if result.statistics is not None
            else False
        )

        key = (horizon_years, equity, withdrawal, target, regime)
        success_count, total_count = agg[key]
        agg[key] = (success_count + (1 if successful else 0), total_count + 1)

    # Build sorted aggregation results
    def _sort_key(
        item: tuple[tuple[int, Decimal, Decimal, Decimal | None, CapeRegime], tuple[int, int]],
    ) -> tuple[int, Decimal, Decimal, Decimal, int]:
        k = item[0]
        target_sort = k[3] if k[3] is not None else Decimal("-1")
        return (k[0], k[1], k[2], target_sort, k[4].value)

    aggregations = []
    for (horizon_years, equity, withdrawal, target, regime), (
        success_count,
        total_count,
    ) in sorted(agg.items(), key=_sort_key):
        aggregations.append(
            RegimeAggregation(
                horizon_years=horizon_years,
                equity_allocation=equity,
                withdrawal_rate=withdrawal,
                terminal_target=target,
                cape_regime=regime,
                successful_cohorts=success_count,
                total_cohorts=total_count,
            )
        )

    return Part3AggregationResult(
        regime_aggregations=tuple(aggregations),
        total_units=len(simulation_results),
        excluded_no_cape=excluded_no_cape,
    )


def get_regime_table(
    aggregation: Part3AggregationResult,
    *,
    horizon_years: int | None = None,
    equity_allocation: Decimal | None = None,
    withdrawal_rate: Decimal | None = None,
    terminal_target: Any = ...,
) -> list[dict[str, Any]]:
    """Filter and format aggregation results as a list of dictionaries.

    This produces a tabular representation suitable for display or
    comparison against published ERN results.

    Parameters
    ----------
    aggregation:
        The full Part 3 aggregation result.
    horizon_years:
        Filter to this horizon (None = all horizons).
    equity_allocation:
        Filter to this allocation (None = all allocations).
    withdrawal_rate:
        Filter to this withdrawal rate (None = all rates).
    terminal_target:
        Filter to this terminal target.  Use ``...`` (Ellipsis) to
        include all targets; use ``None`` for depletion only.

    Returns
    -------
    list[dict[str, Any]]
        Sorted list of dictionaries with keys:
        horizon, equity_allocation, withdrawal_rate,
        terminal_target, CAPE_regime, successful_cohorts,
        total_cohorts, success_rate.
    """
    results = []
    for agg in aggregation.regime_aggregations:
        if horizon_years is not None and agg.horizon_years != horizon_years:
            continue
        if (
            equity_allocation is not None
            and agg.equity_allocation != equity_allocation
        ):
            continue
        if (
            withdrawal_rate is not None
            and agg.withdrawal_rate != withdrawal_rate
        ):
            continue
        if terminal_target is not ... and agg.terminal_target != terminal_target:
            continue

        regime: CapeRegime = agg.cape_regime
        results.append(
            {
                "horizon": agg.horizon_years,
                "equity_allocation": agg.equity_allocation,
                "withdrawal_rate": agg.withdrawal_rate,
                "terminal_target": agg.terminal_target,
                "CAPE_regime": regime,
                "successful_cohorts": agg.successful_cohorts,
                "total_cohorts": agg.total_cohorts,
                "success_rate": agg.success_rate,
            }
        )

    def _row_sort_key(r: dict[str, Any]) -> tuple[int, Decimal, int]:
        regime: CapeRegime = r["CAPE_regime"]
        return (r["horizon"], r["equity_allocation"], regime.value)

    results.sort(key=_row_sort_key)
    return results
