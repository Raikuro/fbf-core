"""Shared pytest configuration for the P4.9 E2E package.

Registers the ``ern_e2e`` marker used to gate the slow ERN study runs.
"""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "ern_e2e: black-box ERN SWR replication run (slow; enable with RUN_ERN_E2E=1)",
    )
