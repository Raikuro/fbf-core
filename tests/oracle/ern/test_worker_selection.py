"""Tests for the ERN E2E worker-selection logic (fast, runs by default).

Covers ``constants.resolve_e2e_workers``: the conservative default, the
explicit ``ERN_E2E_WORKERS=max`` all-CPU option, the ``ERN_E2E_WORKERS=N``
override, host-CPU capping, and invalid values.  Also verifies the resolved
count is passed through verbatim to the ``sim-retire run --workers N`` argv.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.oracle.cli_harness import CliHarness

from .constants import (
    ERN_E2E_MAX_WORKERS,
    ERN_E2E_WORKERS_BASELINE,
    resolve_e2e_workers,
)


def test_default_is_conservative_baseline() -> None:
    assert resolve_e2e_workers(None, host_cpu_count=32) == ERN_E2E_WORKERS_BASELINE
    assert resolve_e2e_workers("", host_cpu_count=32) == ERN_E2E_WORKERS_BASELINE


def test_default_never_exceeds_host_cpus() -> None:
    assert resolve_e2e_workers(None, host_cpu_count=4) == 4


def test_max_uses_all_available_cpus() -> None:
    assert resolve_e2e_workers(ERN_E2E_MAX_WORKERS, host_cpu_count=32) == 32
    assert resolve_e2e_workers("max", host_cpu_count=16) == 16
    assert resolve_e2e_workers("MAX", host_cpu_count=16) == 16


def test_explicit_override_is_not_capped_at_baseline() -> None:
    # A host with >= 16 CPUs must honor a 16-worker request even though the
    # conservative default is 8 (the baseline is not a hard cap).
    assert resolve_e2e_workers("16", host_cpu_count=32) == 16
    assert resolve_e2e_workers("4", host_cpu_count=32) == 4


def test_override_capped_to_host_cpus() -> None:
    assert resolve_e2e_workers("16", host_cpu_count=8) == 8
    assert resolve_e2e_workers("64", host_cpu_count=12) == 12


def test_whitespace_tolerated() -> None:
    assert resolve_e2e_workers(" 8 ", host_cpu_count=32) == 8


@pytest.mark.parametrize("bad", ["0", "-3", "abc", "8.5", "maxx"])
def test_invalid_values_raise(bad: str) -> None:
    with pytest.raises(ValueError):
        resolve_e2e_workers(bad, host_cpu_count=32)


def test_worker_count_passes_through_to_cli_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The resolved count must reach the real CLI as ``--workers N``."""
    captured: dict[str, Any] = {}

    def fake_run(harness_self: CliHarness, args: list[str], timeout: int) -> Any:
        captured["args"] = args
        from tests.oracle.cli_harness import CliResult

        return CliResult(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr(CliHarness, "run", fake_run)
    harness = CliHarness(data_dir=Path("data/ern"), home_dir=Path("/tmp/x"))

    workers = resolve_e2e_workers(ERN_E2E_MAX_WORKERS, host_cpu_count=32)
    harness.run_study(Path("/tmp/study.yaml"), workers=workers, persist=False)

    # run_study hands the exact worker count to CliHarness.run, which builds
    # the final subprocess argv (prefixing the CLI binary and --data-dir).
    assert captured["args"] == [
        "run",
        "/tmp/study.yaml",
        "--workers",
        "32",
        "--no-persist",
        "--summary-only",
    ]
