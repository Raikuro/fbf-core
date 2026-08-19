"""Reusable black-box harness for exercising the public ``sim-retire`` CLI.

This harness treats the CLI as a pure external process: it locates the
``sim-retire`` console script, runs it as a subprocess with an isolated
``HOME`` (so the SQLite study database and config stay out of the developer's
real home), and parses only observable CLI output.

The harness is deliberately generic.  Study-specific concerns (datasets,
study YAMLs, expected tables) live in the study test packages that use it.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict, cast

_UNITS_RUN_RE = re.compile(r"Units Run:\s+([0-9,]+)")
_UNITS_FAILED_RE = re.compile(r"Units Failed:\s+([0-9,]+)")
_STATUS_RE = re.compile(r"Status:\s+(.+)")


@dataclass(frozen=True)
class CliResult:
    """Observable outcome of a CLI invocation."""

    exit_code: int
    stdout: str
    stderr: str

    @property
    def units_run(self) -> int | None:
        match = _UNITS_RUN_RE.search(self.stdout)
        return _parse_int(match.group(1)) if match else None

    @property
    def units_failed(self) -> int | None:
        match = _UNITS_FAILED_RE.search(self.stdout)
        return _parse_int(match.group(1)) if match else None

    @property
    def status(self) -> str | None:
        match = _STATUS_RE.search(self.stdout)
        return match.group(1) if match else None


class StudyInfo(TypedDict):
    """One entry of the ``sim-retire list --format json`` ``studies`` array."""

    study_id: str
    name: str
    version: str
    status: str
    units: int
    created_at: str


def _parse_int(value: str) -> int:
    return int(value.replace(",", ""))


def locate_cli() -> Path:
    """Locate the ``sim-retire`` console script.

    Resolution order:
      1. ``SIM_RETIRE_BIN`` environment variable.
      2. The directory containing the current interpreter (venv bin dir).
      3. ``sim-retire`` on ``PATH``.
    """
    env_path = os.environ.get("SIM_RETIRE_BIN")
    if env_path:
        candidate = Path(env_path)
        if candidate.is_file():
            return candidate

    interpreter_dir = Path(sys.executable).parent
    candidate = interpreter_dir / "sim-retire"
    if candidate.is_file():
        return candidate

    path_candidate = shutil.which("sim-retire")
    if path_candidate:
        return Path(path_candidate)

    raise FileNotFoundError(
        "Could not locate the 'sim-retire' console script. Set SIM_RETIRE_BIN "
        "or ensure the CLI is on PATH."
    )


class CliHarness:
    """Runs the public ``sim-retire`` CLI as an isolated subprocess."""

    def __init__(
        self,
        cli: Path | None = None,
        data_dir: Path | None = None,
        home_dir: Path | None = None,
    ) -> None:
        self.cli = cli or locate_cli()
        self.data_dir = data_dir
        self.home_dir = home_dir

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self.home_dir is not None:
            env["HOME"] = str(self.home_dir)
        return env

    def run(self, args: list[str], timeout: int = 1800) -> CliResult:
        """Run ``sim-retire <args>`` and return observable output."""
        argv = [str(self.cli)]
        if self.data_dir is not None:
            argv += ["--data-dir", str(self.data_dir)]
        argv += args
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=self._env(),
        )
        return CliResult(
            exit_code=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
        )

    def run_study(
        self,
        study_yaml: Path,
        workers: int = 4,
        timeout: int = 3600,
        persist: bool = True,
        fast_path: bool = False,
    ) -> CliResult:
        """Run a study file and return the CLI completion summary.

        Parameters
        ----------
        persist:
            When False the CLI is invoked with ``--no-persist --summary-only``:
            nothing is written to the study database and only aggregate
            statistics are kept in memory (the summary output is identical).
        fast_path:
            When True, pass ``--fast-path`` to exercise the closed-form fast
            path (results must match the reference engine).
        """
        argv = ["run", str(study_yaml), "--workers", str(workers)]
        if not persist:
            argv += ["--no-persist", "--summary-only"]
        if fast_path:
            argv += ["--fast-path"]
        return self.run(argv, timeout=timeout)

    def list_studies(self) -> list[StudyInfo]:
        """List stored studies (``sim-retire list --format json``)."""
        result = self.run(["list", "--format", "json"])
        if result.exit_code != 0:
            raise RuntimeError(f"sim-retire list failed: {result.stderr or result.stdout}")
        import json

        return cast(list[StudyInfo], json.loads(result.stdout).get("studies", []))

    def find_study_id(self, name: str) -> str | None:
        """Find the most recently created study id matching *name*."""
        candidates = [s for s in self.list_studies() if s.get("name") == name]
        return candidates[-1]["study_id"] if candidates else None

    def export_summary(self, study_id: str) -> dict[str, Any]:
        """Export a study's summary JSON (``export --format json --metrics summary``)."""
        output = self.home_dir / "export" if self.home_dir else Path.cwd()
        result = self.run(
            [
                "export",
                study_id,
                "--format",
                "json",
                "--metrics",
                "summary",
                "--output",
                str(output),
            ]
        )
        if result.exit_code != 0:
            raise RuntimeError(f"sim-retire export failed: {result.stderr or result.stdout}")
        import glob

        files = glob.glob(str(output / f"{study_id}_export.json"))
        if not files:
            raise RuntimeError(f"No export file produced for {study_id}")
        import json

        return cast(dict[str, Any], json.loads(Path(files[0]).read_text(encoding="utf-8")))
