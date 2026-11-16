"""Smoke test for the committed ERN Part 52 example study.

The test validates the example through the public study API: YAML parsing,
configuration construction, and plan building. It does not execute simulations
or persist results.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from fbf.core.domain.model.money import Currency, Money
from fbf.core.study import BuiltStudy, StudyConfiguration, build_study_plan, load_yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EXAMPLE_PATH = _REPO_ROOT / "examples" / "studies" / "ern_part52.yaml"
_DATA_DIR = _REPO_ROOT / "data" / "inputs" / "ern"
_INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)

_EXPECTED_PARAM_COMBINATIONS = 6
_EXPECTED_COHORTS = 1739
_EXPECTED_UNITS = 10434
_EXPECTED_SCHEDULE_MONTHS = 361


@pytest.fixture(scope="module")
def raw_example() -> dict[str, Any]:
    return load_yaml(_EXAMPLE_PATH)


@pytest.fixture(scope="module")
def study_config(raw_example: dict[str, Any]) -> StudyConfiguration:
    return StudyConfiguration.from_yaml(raw_example)


@pytest.fixture(scope="module")
def built_study(study_config: StudyConfiguration) -> BuiltStudy:
    return build_study_plan(study_config, str(_DATA_DIR), _INITIAL_WEALTH)


def test_example_parses_as_study_configuration(
    raw_example: dict[str, Any],
    study_config: StudyConfiguration,
) -> None:
    assert raw_example["debt"]["ltv_enforcement"] is False
    assert raw_example["cohorts"]["cohort_horizon_years"] == 60
    assert study_config.withdrawal_policy_type == "Part52WithdrawalPolicy"
    assert study_config.cohort_horizon_years == 60
    assert study_config.debt_ltv_enforcement is False


def test_example_builds_expected_plan_dimensions(built_study: BuiltStudy) -> None:
    assert len(built_study.param_configs) == _EXPECTED_PARAM_COMBINATIONS
    assert len(built_study.cohorts) == _EXPECTED_COHORTS
    assert len(built_study.plan.units) == _EXPECTED_UNITS


def test_example_uses_observation_only_ltv(built_study: BuiltStudy) -> None:
    for unit in built_study.plan.units:
        assert unit.ltv_enforcement is False


def test_example_has_ffr_derived_schedules(built_study: BuiltStudy) -> None:
    for unit in built_study.plan.units:
        schedule = unit.interest_rate_schedule
        assert schedule is not None
        assert len(schedule) == _EXPECTED_SCHEDULE_MONTHS
