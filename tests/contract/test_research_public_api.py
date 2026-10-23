"""Contract tests for the public Tier 2 research facade."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from fbf.core.domain import (
    AssetClass,
    Currency,
    Dataset,
    MarketSnapshot,
    Money,
)
from fbf.core.execution import (
    ExecutionBackend,
    ExecutionOptions,
    ExecutionStrategy,
)
from fbf.core.research import (
    CohortManifest,
    CohortManifestEntry,
    Part3AggregationResult,
    Part3ExecutionResult,
    Part3PlannerConfig,
    Part3PlanResult,
    RegimeAggregation,
    execute_part3_pipeline,
    load_manifest,
    materialize_part3_plan,
)

EXPECTED_PUBLIC_SYMBOLS = {
    "CohortManifest",
    "CohortManifestEntry",
    "Part3AggregationResult",
    "Part3ExecutionResult",
    "Part3PlanResult",
    "Part3PlannerConfig",
    "RegimeAggregation",
    "execute_part3_pipeline",
    "load_manifest",
    "materialize_part3_plan",
}

EQUITY = AssetClass(id="equity", name="", description="")
BOND = AssetClass(id="bond", name="", description="")
START = date(2000, 1, 1)


def _make_dataset(months: int = 26) -> Dataset:
    snapshots = []
    current = START
    for _ in range(months):
        snapshots.append(
            MarketSnapshot(
                date=current,
                index_levels={EQUITY: Decimal("100"), BOND: Decimal("50")},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("1"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            )
        )
        current = date(
            current.year + (current.month // 12),
            current.month % 12 + 1,
            1,
        )
    return Dataset(snapshots=tuple(snapshots), frequency="monthly")


def _write_manifest(tmp_path: Path) -> Path:
    payload = {
        "version": "test",
        "description": "public API contract",
        "market_source": "synthetic",
        "cape_source": "synthetic",
        "fee": 0.0,
        "statistics": {"total_cohorts": 2},
        "cohorts": [
            {
                "cohort_date": "2000-01-01",
                "market_available": True,
                "cape_available": True,
                "cape_value": 25.0,
                "cape_regime": "HIGH",
                "start_month_index": 0,
                "max_horizon_months": 25,
            },
            {
                "cohort_date": "2000-02-01",
                "market_available": True,
                "cape_available": True,
                "cape_value": 12.0,
                "cape_regime": "BELOW_15",
                "start_month_index": 1,
                "max_horizon_months": 24,
            },
        ],
    }
    path = tmp_path / "cohort_manifest_part3.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_public_research_facade_symbols() -> None:
    """The facade exposes exactly the reviewed Part 3 public surface."""
    import fbf.core.research as research

    assert set(research.__all__) == EXPECTED_PUBLIC_SYMBOLS


def test_public_research_facade_supports_part3_workflow(tmp_path: Path) -> None:
    """Plan, execute, and aggregate Part 3 using only public imports."""
    manifest = load_manifest(_write_manifest(tmp_path))
    assert isinstance(manifest, CohortManifest)
    assert isinstance(manifest.cohorts[0], CohortManifestEntry)

    config = Part3PlannerConfig(
        equity_allocations=(Decimal("0.5"),),
        withdrawal_rates=(Decimal("0.04"),),
        horizon_years=(1,),
        final_value_targets=(Decimal("0"),),
        allocation_policy_type="ConstantAllocationPolicy",
        withdrawal_policy_type="FixedRealWithdrawalPolicy",
    )
    plan_result = materialize_part3_plan(
        manifest,
        _make_dataset(),
        config,
        Money(Decimal("1000000"), Currency.EUR),
    )
    assert isinstance(plan_result, Part3PlanResult)
    assert len(plan_result.plan.units) == 2

    result = execute_part3_pipeline(
        plan_result,
        ExecutionOptions(
            backend=ExecutionBackend.DECIMAL_FAST_PATH,
            strategy=ExecutionStrategy.SEQUENTIAL,
        ),
    )
    assert isinstance(result, Part3ExecutionResult)
    assert result.total_units == 2
    assert len(result.results) == 2
    assert isinstance(result.aggregation, Part3AggregationResult)
    assert result.aggregation.total_units == 2
    assert result.aggregation.excluded_no_cape == 0
    assert {
        aggregation.cape_regime.name
        for aggregation in result.aggregation.regime_aggregations
    } == {"HIGH", "BELOW_15"}
    assert all(
        isinstance(aggregation, RegimeAggregation)
        for aggregation in result.aggregation.regime_aggregations
    )
