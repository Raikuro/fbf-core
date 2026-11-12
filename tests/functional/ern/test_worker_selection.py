"""CLI argv contract for the ERN E2E worker-selection logic.

The pure worker-count resolution tests live in
``tests/unit/execution/test_worker_selection.py``.  This functional test keeps
the external-CLI argv boundary: it verifies the resolved count is passed
through verbatim to the ``sim-retire run --workers N`` argv.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.functional.cli_harness import CliHarness
from tests.support.ern.constants import ERN_E2E_MAX_WORKERS, resolve_e2e_workers


def test_worker_count_passes_through_to_cli_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The resolved count must reach the real CLI as ``--workers N``.

    The harness is constructed with an explicit ``cli`` path so no ``sim-retire``
    console script needs to be present: this is a pure Core-side argv-contract
    test and must not depend on the CLI binary.
    """
    captured: dict[str, Any] = {}

    def fake_run(harness_self: CliHarness, args: list[str], timeout: int) -> Any:
        captured["args"] = args
        from tests.functional.cli_harness import CliResult

        return CliResult(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr(CliHarness, "run", fake_run)
    harness = CliHarness(
        cli=Path("__no_such_cli__"),
        data_dir=Path("data/inputs/ern"),
        home_dir=tmp_path,
    )

    workers = resolve_e2e_workers(ERN_E2E_MAX_WORKERS, host_cpu_count=32)
    study_path = tmp_path / "study.yaml"
    harness.run_study(study_path, workers=workers, persist=False)

    # run_study hands the exact worker count to CliHarness.run, which builds
    # the final subprocess argv (prefixing the CLI binary and --data-dir).
    assert captured["args"] == [
        "run",
        str(study_path),
        "--workers",
        "32",
        "--no-persist",
        "--summary-only",
    ]
