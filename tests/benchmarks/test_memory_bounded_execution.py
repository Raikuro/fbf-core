"""Isolated-process benchmarks for bounded streaming execution.

These are manual benchmarks, not part of the routine quality gate.  Run with::

    RUN_MEMORY_BENCH=1 .venv/bin/python -m pytest \
        tests/benchmarks/test_memory_bounded_execution.py -s

Each measurement runs in a fresh interpreter so peak RSS is attributable to a
single workload.  The materialized cases keep the slice target fixed and grow
the total workload; peak residency should stay near the slice target instead of
scaling with the total number of units.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

if os.environ.get("RUN_MEMORY_BENCH") != "1":
    pytest.skip(
        "manual memory benchmark; set RUN_MEMORY_BENCH=1 to run",
        allow_module_level=True,
    )

pytestmark = [pytest.mark.benchmark, pytest.mark.slow]

_PROBE = Path(__file__).with_name("_memory_bounded_probe.py")


def _measure(
    units: int,
    slice_units: int,
    *,
    materialize: bool,
    per_cohort: int = 1,
    persist: bool = False,
) -> dict[str, Any]:
    completed = subprocess.run(
        [
            sys.executable,
            str(_PROBE),
            "--units",
            str(units),
            "--slice",
            str(slice_units),
            "--materialize",
            "1" if materialize else "0",
            "--per-cohort",
            str(per_cohort),
            *(("--persist",) if persist else ()),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    result: dict[str, Any] = json.loads(lines[-1])
    return result


def test_materialized_residency_tracks_slice_not_total() -> None:
    slice_units = 200
    rows = [
        _measure(units, slice_units, materialize=True)
        for units in (200, 400, 800)
    ]
    for row in rows:
        print(row)

    small, medium, large = rows
    assert small["executed"] == 200
    assert medium["executed"] == 400
    assert large["executed"] == 800
    assert small["months"] == medium["months"] == large["months"] == 720

    slice_payload_mib = small["slice"] * small["payload_mib_per_unit"]
    allowance_mib = 2.0 * slice_payload_mib + 256.0
    assert large["peak_delta_mb"] <= allowance_mib

    growth_mib = large["peak_delta_mb"] - small["peak_delta_mb"]
    assert growth_mib <= 128.0, (
        "peak residency grew with total workload; expected the slice target "
        f"to dominate (small={small['peak_delta_mb']} MiB, "
        f"large={large['peak_delta_mb']} MiB)"
    )


def test_default_materialized_slice_stays_bounded() -> None:
    slice_units = 500
    rows = [
        _measure(units, slice_units, materialize=True)
        for units in (500, 1000)
    ]
    for row in rows:
        print(row)

    small, large = rows
    assert small["executed"] == 500
    assert large["executed"] == 1000
    assert large["peak_delta_mb"] <= small["peak_delta_mb"] + 128.0
    assert large["peak_delta_mb"] <= 2.0 * slice_units * 1.6 + 256.0


def test_default_summary_slice_stays_bounded() -> None:
    slice_units = 20_000
    rows = [
        _measure(
            units,
            slice_units,
            materialize=False,
            per_cohort=100,
        )
        for units in (20_000, 40_000)
    ]
    for row in rows:
        print(row)

    small, large = rows
    assert small["executed"] == 20_000
    assert large["executed"] == 40_000
    assert large["peak_delta_mb"] <= small["peak_delta_mb"] + 64.0
    assert large["peak_delta_mb"] <= 256.0


def test_streamed_persisted_materialized_stays_bounded() -> None:
    slice_units = 200
    rows = [
        _measure(units, slice_units, materialize=True, persist=True)
        for units in (200, 400)
    ]
    for row in rows:
        print(row)

    small, large = rows
    assert small["persisted_status"] == large["persisted_status"] == "completed"
    assert small["persisted_units"] == 200
    assert large["persisted_units"] == 400
    assert large["peak_delta_mb"] <= small["peak_delta_mb"] + 128.0
    assert large["persist_db_mb"] > small["persist_db_mb"] > 0
