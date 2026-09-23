"""Part 20 published-anchor comparison helpers for the T2.1 baseline audit.

Anchor values themselves live in the audit specification YAML
(``tests/fixtures/ern_part20_e2e_audit.yaml``) — external reference data
transcribed from ern_part20_replication.md §11–§15.4.  This module holds
the structural checks and the unit-driven classification dispatch.

Part 19/20 shared abstraction: DEFERRED (T2.1 architecture decision).
"""

from __future__ import annotations

from decimal import Decimal

from fbf.core.research.part20_aggregation import (
    AnchorComparison,
    classify_displayed_value,
)
from fbf.core.research.part20_audit_spec import AuditAnchor, StructuralCounts
from fbf.core.research.part20_strategies import Part20Strategy

__all__ = [
    "compare_anchor",
    "structural_checks",
]


def structural_checks(
    counts: StructuralCounts,
    *,
    total_cohorts: int,
    cape_available: int,
    cape_high: int,
    strategy_count: int,
    cells_a: int,
    cells_b: int,
    cells_c: int,
    cells_d: int,
    cells_e_cases: int,
) -> list[str]:
    """Return structural invariant violations against *counts* (empty = pass)."""
    problems: list[str] = []
    pairs = (
        ("total_cohorts", total_cohorts, counts.total_cohorts),
        ("cape_available", cape_available, counts.cape_available),
        ("cape_high", cape_high, counts.cape_high),
        ("strategy_count", strategy_count, counts.strategy_count),
        ("cells_A", cells_a, counts.cells_a),
        ("cells_B", cells_b, counts.cells_b),
        ("cells_C", cells_c, counts.cells_c),
        ("cells_D", cells_d, counts.cells_d),
        ("cells_E_cases", cells_e_cases, counts.cells_e_cases),
    )
    for label, observed, expected in pairs:
        if observed != expected:
            problems.append(f"{label}={observed} != {expected}")
    return problems


def compare_anchor(
    anchor: AuditAnchor,
    observed: Decimal | None,
    strategy: Part20Strategy | None,
    cohort_count: int,
    calculation_path: str,
) -> AnchorComparison:
    """Classify one published anchor against an observation (or None).

    ``observed is None`` → CAPABILITY GAP regardless of strategy.
    A present observation requires a strategy context.
    """
    strategy_kind: str | None = None
    strategy_is_active = False
    if strategy is not None:
        strategy_kind = strategy.kind
        strategy_is_active = strategy.is_active

    classification = classify_displayed_value(
        observed,
        anchor.published,
        unit=anchor.unit,
        strategy_kind=strategy_kind,
        strategy_is_active=strategy_is_active,
        calculation_path=calculation_path,
    )
    return AnchorComparison(
        experiment=anchor.experiment,
        strategy_id=anchor.strategy,
        metric=anchor.metric,
        horizon_years=anchor.horizon_years,
        final_value_target=anchor.final_value_target,
        cape_regime=anchor.cape_regime,
        published_percent=anchor.published,
        observed_percent=observed,
        classification=classification,
        cohort_count=cohort_count,
        calculation_path=calculation_path,
        unit=anchor.unit,
    )
