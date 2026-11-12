"""Scenario A is a configuration-behaviour check, not 2016 replication."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from fbf.core.datasets.ern import load_cape_rows, prepare_ern_dataset
from fbf.core.domain.model.money import Currency, Money
from fbf.core.execution import ExecutionOptions, ExecutionStrategy
from fbf.core.research.cohort_manifest import build_effective_manifest
from fbf.core.research.part3_pipeline import execute_part3_pipeline
from fbf.core.research.part3_study import build_part3_plan_from_configuration
from fbf.core.study.builder import StudyConfiguration

_DATA_DIR = Path("data/inputs/ern")
_INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)


def _scenario_a_raw() -> dict[str, Any]:
    return {
        "metadata": {
            "name": "ERN Part 3 Scenario A",
            "version": "1.0",
            "description": "2016-vintage projection configuration behaviour",
        },
        "cohorts": {
            "start_date": "1871-02-01",
            "end_date": "2016-09-01",
            "horizon_years": [30],
            "cohort_horizon_years": 60,
        },
        "allocation_policy": {
            "type": "ConstantAllocationPolicy",
            "equity_allocation": [1.0],
        },
        "withdrawal_policy": {"type": "FixedRealWithdrawalPolicy"},
        "experiments": [
            {"id": "A", "withdrawal_rate": 0.04, "final_value_target": 0.0}
        ],
        "dataset": {
            "historical_data_cutoff": "2016-09-01",
            "projection": {
                "phase_months": 120,
                "equity": {
                    "annual_real_return": 0.066,
                    "annual_real_return_after": 0.066,
                },
                "bonds": {
                    "annual_real_return": 0.0,
                    "annual_real_return_after": 0.0,
                },
                "inflation": {"mode": "constant", "annual_rate": 0.026},
                "ffr": {"policy": "constant_rate", "constant_rate": 0.0},
            },
        },
        "expense_ratio": 0.0005,
    }


def test_scenario_a_full_coverage_metadata() -> None:
    config = StudyConfiguration.from_yaml(_scenario_a_raw())
    prepared = prepare_ern_dataset(
        _DATA_DIR,
        config=config.projection_config,
        required_through=date(2076, 9, 1),
        legacy_mode=config.legacy_mode,
    )

    assert prepared.metadata.historical_data_cutoff == date(2016, 9, 1)
    assert prepared.metadata.projection_start == date(2016, 10, 1)
    assert prepared.metadata.projection_end == date(2076, 9, 1)
    assert len(prepared.dataset) == 2469

    manifest = build_effective_manifest(
        dataset=prepared.dataset,
        metadata=prepared.metadata,
        cape_rows=load_cape_rows(_DATA_DIR),
        cohort_start=date(1871, 2, 1),
        cohort_end=date(2016, 9, 1),
        fee=Decimal("0.0005"),
        require_cape=True,
    )
    assert len(manifest.cohorts) == 1748
    assert manifest.cohorts[-1].max_horizon_months == 721
    assert manifest.statistics["horizon_eligibility"]["h720"] == 1748


@pytest.mark.ern_e2e
def test_scenario_a_executes_without_anchor_claims() -> None:
    config = StudyConfiguration.from_yaml(_scenario_a_raw())
    plan_result = build_part3_plan_from_configuration(
        _DATA_DIR,
        _INITIAL_WEALTH,
        configuration=config,
    )
    assert len(plan_result.cohorts) == 1748
    assert len(plan_result.param_configs) == 1

    result = execute_part3_pipeline(
        plan_result,
        options=ExecutionOptions(strategy=ExecutionStrategy.AUTO),
    )
    assert result.total_units == 1748
