"""Installed-only dataset discovery and execution (Phase 2 closure, 2.8).

These tests prove the Dataset Directory contract works from an external,
self-contained bundle — i.e. exactly what an installed-only deployment (no
repository, no repo ``data/`` directory) experiences: it obtains a dataset
bundle, points ``data_dir`` at it, and the Core public API discovers and
executes against it.  No test here depends on the committed ``data/ern/``.

The model is documented in ``DATASETS.md``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest

from fbf.core.domain.model.money import Currency, Money
from fbf.core.persistence.studies.sqlite.context import _dataset_to_dict
from fbf.core.persistence.studies.sqlite.errors import StudyNotFoundError
from fbf.core.study import StudyConfiguration, build_study_plan, load_yaml

from .helpers import make_dataset

_SIMPLE_STUDY_YAML = """\
metadata:
  name: "Installed-only discovery test"
  version: "1.0"
  description: "Minimal study exercised against an external dataset bundle"

dataset:
  identifier: "synthetic_ret"

cohorts:
  horizon_years: [1]

allocation_policy:
  type: "ConstantAllocationPolicy"
  equity_allocation: [1.0]

withdrawal_policy:
  type: "FixedRealWithdrawalPolicy"
  withdrawal_rate: [0.04]
"""


@pytest.fixture(autouse=True)
def _isolated_dataset_cache() -> Iterator[None]:
    from fbf.core.persistence.studies.sqlite import clear_default_dataset_cache

    clear_default_dataset_cache()
    yield
    clear_default_dataset_cache()


def _write_bundle(data_dir: Path, identifier: str = "synthetic_ret", version: str = "V1") -> Path:
    """Write a self-contained Dataset Directory conforming to the contract."""
    data_dir.mkdir(parents=True, exist_ok=True)
    dataset = make_dataset(num_months=40, start_year=2000)
    raw = _dataset_to_dict(dataset)
    raw["version"] = version
    path = data_dir / f"{identifier}.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


class TestInstalledOnlyDiscovery:
    def test_dataset_directory_is_discovered_and_used(self, tmp_path: Path) -> None:
        bundle = _write_bundle(tmp_path / "bundle", version="V1")

        study = StudyConfiguration.from_yaml(load_yaml(_simple_study(tmp_path)))
        built = build_study_plan(study, data_dir=str(bundle.parent), initial_wealth=_capital())

        assert len(built.plan) > 0
        resolved = built.experiment_definition.dataset
        assert resolved.identifier == "synthetic_ret"
        assert resolved.version == "V1"

    def test_repeated_resolution_returns_identical_object(self, tmp_path: Path) -> None:
        from fbf.core.study import build_study_plan

        bundle = _write_bundle(tmp_path / "bundle")
        study = StudyConfiguration.from_yaml(load_yaml(_simple_study(tmp_path)))

        first = build_study_plan(study, data_dir=str(bundle.parent), initial_wealth=_capital())
        second = build_study_plan(study, data_dir=str(bundle.parent), initial_wealth=_capital())

        assert first.experiment_definition.dataset is second.experiment_definition.dataset

    def test_missing_dataset_directory_raises_clear_error(self, tmp_path: Path) -> None:
        study = StudyConfiguration.from_yaml(load_yaml(_simple_study(tmp_path)))
        missing = tmp_path / "does-not-exist"
        with pytest.raises(StudyNotFoundError, match="Dataset directory not found"):
            build_study_plan(study, data_dir=str(missing), initial_wealth=_capital())

    def test_unknown_identifier_raises_clear_error(self, tmp_path: Path) -> None:
        _write_bundle(tmp_path / "bundle", identifier="synthetic_ret")
        study_yaml = _simple_study(tmp_path, identifier="NOT_PRESENT")
        study = StudyConfiguration.from_yaml(load_yaml(study_yaml))
        with pytest.raises(StudyNotFoundError, match="Dataset not found"):
            build_study_plan(
                study, data_dir=str(tmp_path / "bundle"), initial_wealth=_capital()
            )

    def test_missing_data_dir_has_no_well_known_fallback(self, tmp_path: Path) -> None:
        """With data_dir=None resolution must fail, never fall back to a repo path."""
        study = StudyConfiguration.from_yaml(load_yaml(_simple_study(tmp_path)))
        with pytest.raises(StudyNotFoundError):
            build_study_plan(study, data_dir=None, initial_wealth=_capital())

    def test_bundle_version_survives_persistence_round_trip_fields(self, tmp_path: Path) -> None:
        bundle = _write_bundle(tmp_path / "bundle", version="V2")
        study = StudyConfiguration.from_yaml(load_yaml(_simple_study(tmp_path)))
        built = build_study_plan(study, data_dir=str(bundle.parent), initial_wealth=_capital())

        # Reproducibility contract: both identifier and version are exposed for recording.
        assert built.experiment_definition.dataset.identifier == "synthetic_ret"
        assert built.experiment_definition.dataset.version == "V2"


def _simple_study(tmp_path: Path, identifier: str = "synthetic_ret") -> Path:
    path = tmp_path / "study.yaml"
    path.write_text(
        _SIMPLE_STUDY_YAML.replace("synthetic_ret", identifier),
        encoding="utf-8",
    )
    return path


def _capital() -> Money:
    return Money(Decimal("1000000"), Currency.EUR)
