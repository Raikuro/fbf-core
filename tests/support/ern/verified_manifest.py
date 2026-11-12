"""Verified runtime Part 3 manifest for tests.

The manifest is derived from canonical historical inputs and the packaged
Part 3 configuration.  It is materialized in a temporary directory only so
tests can exercise the public file loader; no projected manifest is committed.
"""

from __future__ import annotations

import atexit
import shutil
import tempfile
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from fbf.core.datasets.ern import load_cape_rows, prepare_ern_dataset
from fbf.core.research.cohort_manifest import (
    build_effective_manifest,
    manifest_to_dict,
)
from fbf.core.research.part3_planner import PART3_EXPENSE_RATIO
from tests.support.ern.constants import CANONICAL_DATA_DIR


@lru_cache(maxsize=1)
def verified_manifest_data() -> dict[str, Any]:
    """Return the effective manifest built from canonical historical inputs."""
    prepared = prepare_ern_dataset(
        CANONICAL_DATA_DIR,
        required_through=date(2075, 12, 1),
    )
    manifest = build_effective_manifest(
        dataset=prepared.dataset,
        metadata=prepared.metadata,
        cape_rows=load_cape_rows(CANONICAL_DATA_DIR),
        cohort_start=date(1871, 2, 1),
        cohort_end=date(2015, 12, 1),
        fee=PART3_EXPENSE_RATIO,
        require_cape=True,
    )
    return manifest_to_dict(manifest)


@lru_cache(maxsize=1)
def verified_manifest_path() -> Path:
    """Return a temporary path holding the effective manifest."""
    from tools.ern.build_cohort_manifest import write_manifest

    directory = Path(tempfile.mkdtemp(prefix="fbf-verified-manifest-"))
    atexit.register(shutil.rmtree, directory, ignore_errors=True)
    path = directory / "cohort_manifest_part3.json"
    write_manifest(verified_manifest_data(), path)
    return path
