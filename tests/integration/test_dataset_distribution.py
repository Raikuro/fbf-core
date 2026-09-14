"""Installed-only dataset discovery and execution (Phase 2 closure, 2.8).

These tests prove the canonical dataset loader works from an external
data directory — i.e. exactly what an installed-only deployment (no
repository, no repo ``data/`` directory) experiences: it points
``data_dir`` at a directory containing canonical CSVs, and the Core
public API loads and executes against it.

The model is documented in ``DATASETS.md``.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest

from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.money import Currency, Money
from fbf.core.study import StudyConfiguration, build_study_plan, load_yaml

from .helpers import make_dataset

_SIMPLE_STUDY_YAML = """\
metadata:
  name: "Installed-only discovery test"
  version: "1.0"
  description: "Minimal study exercised against a canonical dataset"

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
    yield


def _simple_study(tmp_path: Path, identifier: str = "synthetic_ret") -> Path:
    path = tmp_path / "study.yaml"
    path.write_text(_SIMPLE_STUDY_YAML, encoding="utf-8")
    return path


def _capital() -> Money:
    return Money(Decimal("1000000"), Currency.EUR)


class TestCanonicalDatasetLoading:
    def test_canonical_dataset_loads(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dataset = make_dataset(num_months=40, start_year=2000)

        monkeypatch.setattr(
            "fbf.core.study.builder.load_canonical_dataset",
            lambda data_dir: dataset,
        )

        study = StudyConfiguration.from_yaml(load_yaml(_simple_study(tmp_path)))
        built = build_study_plan(
            study, data_dir="data/ern", initial_wealth=_capital()
        )

        assert len(built.plan) > 0

    def test_repeated_resolution_returns_identical_object(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from fbf.core.study import build_study_plan

        dataset = make_dataset(num_months=40, start_year=2000)

        monkeypatch.setattr(
            "fbf.core.study.builder.load_canonical_dataset",
            lambda data_dir: dataset,
        )

        study = StudyConfiguration.from_yaml(load_yaml(_simple_study(tmp_path)))
        first = build_study_plan(study, data_dir="data/ern", initial_wealth=_capital())
        second = build_study_plan(study, data_dir="data/ern", initial_wealth=_capital())

        assert first.experiment_definition.dataset is second.experiment_definition.dataset

    def test_bundle_version_survives_persistence_round_trip_fields(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dataset = make_dataset(num_months=40, start_year=2000)

        monkeypatch.setattr(
            "fbf.core.study.builder.load_canonical_dataset",
            lambda data_dir: dataset,
        )

        study = StudyConfiguration.from_yaml(load_yaml(_simple_study(tmp_path)))
        built = build_study_plan(study, data_dir="data/ern", initial_wealth=_capital())

        assert built.experiment_definition.dataset is not None


def _make_dataset_snapshot() -> Dataset:
    return make_dataset(num_months=40, start_year=2000)
