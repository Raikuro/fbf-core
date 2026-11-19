"""Regression coverage for the removed ``legacy_mode`` compatibility switch."""

from __future__ import annotations

import inspect
from dataclasses import fields
from datetime import date
from decimal import Decimal

import pytest

from fbf.core import StudyConfiguration, load_canonical_dataset
from fbf.core.datasets.ern import (
    FfrFuturePolicy,
    PreparedDatasetMetadata,
    prepare_ern_dataset,
)
from fbf.core.study.builder import _prepare_ffr_rates

_RATES = (
    (date(2020, 1, 1), Decimal("0.010")),
    (date(2020, 2, 1), Decimal("0.020")),
    (date(2020, 3, 1), Decimal("0.030")),
)


def _raw_config() -> dict[str, object]:
    return {
        "metadata": {"name": "legacy-mode-removal"},
        "cohorts": {"horizon_years": [1]},
        "allocation_policy": {
            "type": "ConstantAllocationPolicy",
            "equity_allocation": [0.75],
        },
        "withdrawal_policy": {
            "type": "FixedRealWithdrawalPolicy",
            "withdrawal_rate": [0.04],
        },
    }


def test_study_configuration_has_no_legacy_mode_field() -> None:
    assert "legacy_mode" not in {field.name for field in fields(StudyConfiguration)}


def test_prepared_dataset_metadata_has_no_legacy_mode_field() -> None:
    assert "legacy_mode" not in {
        field.name for field in fields(PreparedDatasetMetadata)
    }


def test_public_signatures_have_no_legacy_mode_parameter() -> None:
    for function in (load_canonical_dataset, prepare_ern_dataset):
        assert "legacy_mode" not in inspect.signature(function).parameters


def test_from_yaml_rejects_legacy_mode_key() -> None:
    raw = _raw_config()
    raw["legacy_mode"] = True

    with pytest.raises(ValueError, match="legacy_mode is no longer supported"):
        StudyConfiguration.from_yaml(raw)


def test_from_yaml_rejects_compatibility_mapping() -> None:
    raw = _raw_config()
    raw["compatibility"] = {"mode": "legacy"}

    with pytest.raises(ValueError, match="compatibility is no longer supported"):
        StudyConfiguration.from_yaml(raw)


def test_ffr_policy_fail_is_not_overridden() -> None:
    prepared, forward_fill, forward_rate = _prepare_ffr_rates(
        _RATES,
        cutoff=date(2020, 2, 1),
        policy=FfrFuturePolicy(mode="fail"),
    )

    assert prepared == _RATES[:2]
    assert forward_fill is False
    assert forward_rate is None


def test_ffr_policy_constant_rate_is_not_overridden() -> None:
    prepared, forward_fill, forward_rate = _prepare_ffr_rates(
        _RATES,
        cutoff=date(2020, 2, 1),
        policy=FfrFuturePolicy(mode="constant_rate", constant_rate=Decimal("0.005")),
    )

    assert prepared == _RATES[:2]
    assert forward_fill is False
    assert forward_rate == Decimal("0.005")


def test_ffr_policy_last_observed_forward_fills() -> None:
    prepared, forward_fill, forward_rate = _prepare_ffr_rates(
        _RATES,
        cutoff=date(2020, 2, 1),
        policy=FfrFuturePolicy(mode="last_observed_at_cutoff"),
    )

    assert prepared == _RATES[:2]
    assert forward_fill is True
    assert forward_rate is None
