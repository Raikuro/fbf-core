"""Focused tests for the standalone published-ERN reference oracle tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.ern import reference_oracle as ro

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DATA_DIR = _REPO_ROOT / "data" / "ern"
_PINNED_ORACLE = _DATA_DIR / "p49_oracle_table.csv"


def test_default_source_and_output_paths_are_separate() -> None:
    """The published source fixture and pinned output artifact are distinct."""
    assert ro._SOURCE_DIR == _DATA_DIR / "published_2016"
    assert ro._OUTPUT_PATH == _PINNED_ORACLE
    assert ro._OUTPUT_PATH.parent != ro._SOURCE_DIR


def test_main_uses_default_source_and_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Omitting --source/--output uses the documented defaults."""
    default_output = tmp_path / "default_oracle.csv"
    monkeypatch.setattr(ro, "_OUTPUT_PATH", default_output)

    assert ro.main([]) == 0
    assert default_output.read_text(encoding="utf-8") == _PINNED_ORACLE.read_text(
        encoding="utf-8"
    )


def test_main_honors_explicit_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit --output overrides the default artifact path."""
    default_output = tmp_path / "default_oracle.csv"
    explicit_output = tmp_path / "explicit_oracle.csv"
    monkeypatch.setattr(ro, "_OUTPUT_PATH", default_output)

    assert ro.main(["--output", str(explicit_output)]) == 0
    assert explicit_output.read_text(encoding="utf-8") == _PINNED_ORACLE.read_text(
        encoding="utf-8"
    )
    assert not default_output.exists()
