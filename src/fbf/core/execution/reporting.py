"""Execution plan coverage reporting.

Pure plan-level report calculations shared by the public execution facade and
the CLI.  This module deliberately has no dependency on any executor,
including the legacy reference and fast-path implementations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from fbf.core.domain.policies import (
    ConstantAllocationPolicy,
    FixedRealWithdrawalPolicy,
    allocation_identity,
)
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan


@dataclass(frozen=True)
class ReferenceReport:
    logical_units: int
    groups: int
    longest_path_evaluations: int
    derived_results: int
    independent_evaluations: int
    month_work: int


def _unit_horizon_months(plan: ResearchPlan, unit: PlannedSimulationUnit) -> int:
    """Return the effective horizon of *unit* (per-unit, else experiment default)."""
    return (
        unit.horizon_months
        if unit.horizon_months is not None
        else plan.experiment_definition.horizon_months
    )


def _unit_group_key(
    plan: ResearchPlan, unit: PlannedSimulationUnit
) -> tuple[object, ...]:
    """Return the plan-level group key for *unit*.

    Mirrors the reference executor's context key on the fields the research
    orchestrator maps into a ``SimulationContext``: cohort start date, policy
    scalars, experiment initial wealth and the unit's initial portfolio.
    """
    allocation = cast(ConstantAllocationPolicy, unit.allocation_policy)
    withdrawal = cast(FixedRealWithdrawalPolicy, unit.withdrawal_policy)
    asset_classes = tuple(h.asset_class for h in unit.initial_portfolio.holdings)
    return (
        unit.cohort.start_date,
        allocation_identity(allocation, asset_classes),
        withdrawal.withdrawal_rate,
        plan.experiment_definition.initial_wealth,
        unit.initial_portfolio,
    )


def _unit_dataset_is_identity_prefix(
    candidate: PlannedSimulationUnit,
    longest: PlannedSimulationUnit,
) -> bool:
    """Plan-level identity-prefix check on unit datasets."""
    candidate_snapshots = candidate.dataset.snapshots
    longest_snapshots = longest.dataset.snapshots
    if len(candidate_snapshots) > len(longest_snapshots):
        return False
    return all(a is b for a, b in zip(candidate_snapshots, longest_snapshots, strict=False))


def _unit_dataset_is_identity_prefix_memo(
    candidate: PlannedSimulationUnit,
    longest: PlannedSimulationUnit,
    memo: dict[tuple[int, int], bool],
) -> bool:
    key = (id(candidate.dataset), id(longest.dataset))
    result = memo.get(key)
    if result is None:
        result = _unit_dataset_is_identity_prefix(candidate, longest)
        memo[key] = result
    return result


def expected_reference_report(plan: ResearchPlan) -> ReferenceReport:
    """Compute the report *plan* would produce, without executing.

    Applies exactly the same grouping and dataset prefix guard as the
    reference executor, so the report is the execution-independent truth for
    the plan: the longest horizon per family is evaluated once and every
    shorter prefix-consistent horizon is derived from it.
    """
    groups: dict[tuple[object, ...], list[PlannedSimulationUnit]] = {}
    for unit in plan.units:
        groups.setdefault(_unit_group_key(plan, unit), []).append(unit)

    prefix_memo: dict[tuple[int, int], bool] = {}
    longest_evaluations = 0
    derived = 0
    independent = 0
    month_work = 0
    for units in groups.values():
        longest_unit = max(units, key=lambda u: _unit_horizon_months(plan, u))
        longest_evaluations += 1
        month_work += _unit_horizon_months(plan, longest_unit)
        for unit in units:
            if unit is longest_unit:
                continue
            if _unit_dataset_is_identity_prefix_memo(unit, longest_unit, prefix_memo):
                derived += 1
            else:
                independent += 1
                month_work += _unit_horizon_months(plan, unit)

    return ReferenceReport(
        logical_units=len(plan.units),
        groups=len(groups),
        longest_path_evaluations=longest_evaluations,
        derived_results=derived,
        independent_evaluations=independent,
        month_work=month_work,
    )


def reference_month_work(plan: ResearchPlan) -> int:
    """Return the reference-path month-work for *plan*.

    The reference engine simulates every unit for its full horizon, so the total
    month-work is the sum of all per-unit horizons.
    """
    return sum(
        unit.horizon_months
        if unit.horizon_months is not None
        else plan.experiment_definition.horizon_months
        for unit in plan.units
    )


__all__ = [
    "ReferenceReport",
    "expected_reference_report",
    "reference_month_work",
]
