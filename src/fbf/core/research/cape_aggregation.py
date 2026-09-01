"""CAPE regime result aggregation for retirement cohort analysis.

Aggregates simulation results by CAPE regime, equity allocation,
horizon, withdrawal rate, and terminal value target.

This module operates on the Research layer, grouping simulation results
by the CAPE regime of the retirement start date, as classified by the
CapeRegimeClassification module.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from fbf.core.domain.policies.cape_regime import (
    CapeRegime,
    classify_cape_regime,
)


def aggregate_success_rates(
    simulation_results: tuple[Any, ...],
    param_configs: tuple[Any, ...],
    cohorts: tuple[Any, ...],
    get_cape_for_cohort: Callable[[Any], Decimal | None],
) -> list[dict[str, Any]]:
    """Aggregate simulation results by CAPE regime, equity allocation,
    horizon, withdrawal rate, and terminal value target.

    For each unique combination of (horizon, equity_allocation,
    withdrawal_rate, terminal_target, CAPE_regime), calculate:

        success_rate = successful_cohorts / total_cohorts

    Args:
        simulation_results: Tuple of SimulationResult objects from
            executed study plan. Must be in the same order as the
            plan's units.
        param_configs: Tuple of ParameterConfiguration objects, one
            per unique parameter set. Must match the order of
            simulation_results.
        cohorts: Tuple of CohortSpecification objects, one per cohort
            start date. Must match the order of the plan's units.
        get_cape_for_cohort: Callable that takes a CohortSpecification
            and returns the CAPE Decimal value at the retirement start
            date, or None if CAPE is unavailable.

    Returns:
        List of dictionaries, each containing:
            - experiment: str (e.g. "4pct_depletion", "4pct_50pct_terminal")
            - horizon: int (years)
            - withdrawal_rate: Decimal
            - terminal_target: Decimal | None
            - equity_allocation: Decimal
            - CAPE_regime: CapeRegime enum
            - successful_cohorts: int
            - total_cohorts: int
            - success_rate: Decimal (successful / total)

    Raises:
        ValueError: If input sequences have mismatched lengths.
    """
    # Validate input lengths
    if not (len(simulation_results) == len(param_configs) == len(cohorts)):
        raise ValueError(
            f"Input sequences must have matching lengths: "
            f"results={len(simulation_results)}, "
            f"param_configs={len(param_configs)}, "
            f"cohorts={len(cohorts)}"
        )

    # Aggregation container: key -> (successful_count, total_count)
    # Key format: (horizon_years, equity_allocation, withdrawal_rate,
    #              terminal_target, cape_regime)
    agg: dict[
        tuple[int, Decimal, Decimal, Decimal | None, CapeRegime],
        tuple[int, int],
    ] = defaultdict(lambda: (0, 0))

    # Process each unit
    for result, param_config, cohort in zip(
        simulation_results, param_configs, cohorts, strict=True
    ):
        # Get horizon from parameter config
        horizon_years = int(param_config.get("horizon_years", 0))

        # Get parameter values
        equity_allocation = Decimal(str(param_config.get("equity_allocation", "0")))
        withdrawal_rate = Decimal(str(param_config.get("withdrawal_rate", "0")))
        raw_target = param_config.get("final_value_target")
        terminal_target = (
            Decimal(str(raw_target)) if raw_target is not None else None
        )

        # Classify CAPE regime
        cape_value = get_cape_for_cohort(cohort)
        regime = (
            classify_cape_regime(cape_value)
            if cape_value is not None
            else CapeRegime.BELOW_15
        )

        # Determine success from the simulation result
        # The Statistics.success field indicates success/failure
        # We need to extract it from the result object
        # Success criteria: survived every month AND (if final_value_target
        # configured, final_wealth >= target * initial_wealth)
        # The exact field name depends on the result type; we'll use a
        # flexible approach
        successful = _is_simulation_successful(result)

        # Update aggregation
        key = (horizon_years, equity_allocation, withdrawal_rate, terminal_target, regime)
        success_count, total_count = agg[key]
        agg[key] = (success_count + (1 if successful else 0), total_count + 1)

    # Build result list
    results = []
    for (horizon_years, equity_allocation, withdrawal_rate, terminal_target, regime), (
        successful_cohorts,
        total_cohorts,
    ) in agg.items():
        if total_cohorts > 0:
            success_rate = Decimal(str(successful_cohorts)) / Decimal(str(total_cohorts))
        else:
            success_rate = Decimal("0")

        # Determine experiment name based on parameters
        experiment = _determine_experiment_name(
            withdrawal_rate, terminal_target, horizon_years
        )

        results.append(
            {
                "experiment": experiment,
                "horizon": horizon_years,
                "withdrawal_rate": withdrawal_rate,
                "terminal_target": terminal_target,
                "equity_allocation": equity_allocation,
                "CAPE_regime": regime,
                "successful_cohorts": successful_cohorts,
                "total_cohorts": total_cohorts,
                "success_rate": success_rate,
            }
        )

    # Sort results for deterministic output
    results.sort(key=lambda r: (
        r["experiment"],
        r["horizon"],
        r["equity_allocation"],
        r["CAPE_regime"],
    ))

    return results


def _is_simulation_successful(result: Any) -> bool:
    """Determine if a simulation result represents a successful retirement.

    A simulation is successful if:
    1. The simulation survived every month (no depletion)
    2. If a final_value_target was configured, final_wealth >= target * initial_wealth

    Args:
        result: SimulationResult object from executed study

    Returns:
        True if the simulation was successful, False otherwise.
    """
    # Check the statistics for success flag
    if hasattr(result, "statistics") and result.statistics is not None:
        stats = result.statistics
        if hasattr(stats, "success"):
            return bool(stats.success)

    # Fallback: check if there's a success attribute directly
    if hasattr(result, "success"):
        return bool(result.success)

    # If we can't determine, assume failure (conservative)
    return False


def _determine_experiment_name(
    withdrawal_rate: Decimal,
    terminal_target: Decimal | None,
    horizon_years: int,
) -> str:
    """Determine the experiment name based on parameters.

    Args:
        withdrawal_rate: The withdrawal rate decimal (e.g. 0.04)
        terminal_target: The terminal value target decimal (e.g. 0.0 or 0.5), or None
        horizon_years: The retirement horizon in years

    Returns:
        Experiment name string (e.g. "4pct_depletion", "4pct_50pct_terminal",
        "3pct5_depletion", "3pct5_50pct_terminal")
    """
    rate_pct = float(withdrawal_rate * 100)
    target_str = ""
    if terminal_target is not None:
        target_pct = float(terminal_target * 100)
        if target_pct == 0.0:
            target_str = "0pct_terminal"
        elif target_pct == 50.0:
            target_str = "50pct_terminal"
        else:
            target_str = f"{int(target_pct)}pct_terminal"
    else:
        target_str = "depletion"  # No target = capital depletion

    horizon_str = f"{horizon_years}y"

    # Format rate as "4pct" or "3pct5"
    rate_str = f"{int(rate_pct)}pct" if rate_pct == int(rate_pct) else f"{rate_pct}pct"

    return f"{rate_str}_{target_str}_{horizon_str}"
