"""Dataset distribution contract tests (Phase 2 closure, 2.8).

The dataset distribution model is decided in ``DATASETS.md``: datasets are
external to the ``fbf-core`` wheel, and an installed-only deployment obtains
a Dataset Directory separately.  These tests statically enforce the packaging
half of that contract — that the wheel cannot contain dataset files without a
deliberate packaging change.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"
_PYPROJECT = _REPO_ROOT / "pyproject.toml"


def _iter_python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py"))


def test_no_dataset_json_under_src() -> None:
    """The package tree must not contain dataset files."""
    data_files = sorted(
        p for p in _SRC_DIR.rglob("*") if p.is_file() and p.suffix.lower() == ".json"
    )
    assert data_files == [], (
        f"Dataset JSON files found under src/ would be packaged in the wheel: "
        f"{data_files}. Datasets are external (see DATASETS.md)."
    )


def test_package_data_declares_only_py_typed() -> None:
    """Wheel package-data must be exactly the py.typed marker.

    If a dataset were ever added to package-data, this test fails by design:
    dataset distribution must be decided deliberately (DATASETS.md).
    """
    with _PYPROJECT.open("rb") as fh:
        pyproject = tomllib.load(fh)
    package_data = pyproject["tool"]["setuptools"].get("package-data", {})
    assert package_data == {"fbf.core": ["py.typed"]}, (
        f"Unexpected package-data: {package_data}. Expected exactly "
        f"{{'fbf.core': ['py.typed']}} so datasets stay out of the wheel."
    )


def test_repo_dataset_dir_lives_outside_src() -> None:
    """The committed dataset bundle must remain outside the package tree."""
    data_dir = _REPO_ROOT / "data"
    src_path = _SRC_DIR.resolve()
    assert data_dir.resolve() != src_path
    assert data_dir.exists() or True  # presence is repo-dependent; exclusion is the contract
    assert not data_dir.resolve().is_relative_to(src_path), (
        "The data/ directory must live outside src/ so it cannot be packaged."
    )


def test_no_well_known_dataset_path_in_production_code() -> None:
    """Production code must not hardcode a dataset directory path.

    Dataset discovery is explicit (a supplied data_dir); there is no built-in
    well-known path.  A search for repository-relative dataset paths in src/
    must come up empty.
    """
    offenders: list[str] = []
    for p in _iter_python_files(_SRC_DIR):
        text = p.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if 'data/ern' in line or 'Path("data' in line or 'Path("data/' in line:
                offenders.append(f"{p}:{line_no}: {line.strip()}")
    assert offenders == [], (
        f"Production code hardcodes a dataset path: {offenders}. "
        f"Dataset discovery must be explicit via data_dir (see DATASETS.md)."
    )
