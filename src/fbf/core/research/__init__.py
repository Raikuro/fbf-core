"""Public research workflows.

This package is the Tier 2 boundary for supported research APIs.  Only the
names exported here are stable; the implementation submodules remain Tier 3.
"""

from __future__ import annotations

from fbf.core.research.part3_aggregation import (
    Part3AggregationResult,
    RegimeAggregation,
)
from fbf.core.research.part3_pipeline import (
    Part3ExecutionResult,
    execute_part3_pipeline,
)
from fbf.core.research.part3_planner import (
    CohortManifest,
    CohortManifestEntry,
    Part3PlannerConfig,
    Part3PlanResult,
    load_manifest,
    materialize_part3_plan,
)

__all__ = [
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
]
