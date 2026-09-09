"""Root test configuration — centralized ERN research workload gating.

Two categories of heavyweight ERN research workloads are controlled by the
shared ``RUN_ERN_E2E=1`` environment variable:

1. **Canonical Research E2E** (``@pytest.mark.ern_e2e``):
   Complete canonical ERN research replication through the production/public
   execution path. Uses canonical data and methodology with no material
   approximation.

2. **Non-Canonical Research Validation** (``@pytest.mark.research_validation``):
   Research-scale validation that executes a published or research-derived
   scenario but currently contains a material methodology/data substitution
   (e.g., Part 52 fixed-rate approximation instead of historical FFR).

Both categories are skipped by default. Setting ``RUN_ERN_E2E=1`` enables
both, because they share the same execution gate:

    RUN_ERN_E2E=1 pytest

This avoids a fragmented environment-variable model (RUN_ERN_E2E,
RUN_RESEARCH_VALIDATION, RUN_HEAVY_TESTS, etc.). The single flag means:

    Enable heavyweight ERN research validation workloads.

The marker taxonomy remains distinct to make the classification visible:

- ``ern_e2e``: canonical Research E2E (full methodology, no approximation)
- ``research_validation``: non-canonical research validation (documented approximations)

Invariant:
- If RUN_ERN_E2E is not enabled, no canonical E2E and no heavyweight
  research validation runs.
- If RUN_ERN_E2E is enabled, all canonical E2Es and all heavyweight
  research validations are eligible to run.
"""

from __future__ import annotations

import os

import pytest

_HEAVYWEIGHT_MARKERS = ("ern_e2e", "research_validation")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip heavyweight ERN research workloads unless RUN_ERN_E2E=1."""
    if os.environ.get("RUN_ERN_E2E") == "1":
        return

    skip_ern_e2e = pytest.mark.skip(
        reason="canonical ERN E2E skipped (set RUN_ERN_E2E=1 to enable)",
    )
    skip_research_validation = pytest.mark.skip(
        reason="heavyweight ERN research validation skipped (set RUN_ERN_E2E=1 to enable)",
    )
    for item in items:
        if "ern_e2e" in item.keywords:
            item.add_marker(skip_ern_e2e)
        elif "research_validation" in item.keywords:
            item.add_marker(skip_research_validation)
