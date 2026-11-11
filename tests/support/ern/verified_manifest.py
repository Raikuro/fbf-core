"""Verified canonical Part 3 cohort manifest for tests.

The committed ``data/ern/cohort_manifest_part3.json`` is a stale v1.0 artifact
that is not reproducible from the verified workbook extraction.  Tests build
the manifest in memory from the verified CSV artifacts using the production
builder, then materialize it in a temporary directory so they can exercise the
production file loader without consuming the stale committed manifest.
"""

from __future__ import annotations

import atexit
import shutil
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any

from tests.support.ern.constants import DATA_DIR
from tools.ern.build_cohort_manifest import build_manifest_file, write_manifest


@lru_cache(maxsize=1)
def verified_manifest_data() -> dict[str, Any]:
    """Return the manifest built from the verified canonical CSV artifacts."""
    return build_manifest_file(DATA_DIR)


@lru_cache(maxsize=1)
def verified_manifest_path() -> Path:
    """Return a temporary path holding the verified manifest."""
    directory = Path(tempfile.mkdtemp(prefix="fbf-verified-manifest-"))
    atexit.register(shutil.rmtree, directory, ignore_errors=True)
    path = directory / "cohort_manifest_part3.json"
    write_manifest(verified_manifest_data(), path)
    return path
