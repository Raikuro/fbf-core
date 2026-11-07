"""Production streaming, whole-plan, and persisted aggregate conformance.

This is a routine regression test, not a full-grid E2E. It executes a
production subset (four representative cells across all 1,739 cohorts),
streams it in multiple slices, persists and reloads it, and compares every
per-cell aggregate against the workbook-derived oracle with exact Decimal
equality.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any

import pytest

from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.money import Currency, Money
from fbf.core.execution import (
    ExecutionBackend,
    ExecutionOptions,
    ExecutionStrategy,
    execute_study_plan,
    iter_execute_study_plan,
)
from fbf.core.persistence.studies.sqlite import (
    AllocationPolicyCodec,
    PersistenceReconstructionContext,
    ResultsNotFoundError,
    SimulationResultCodec,
    SQLiteRepository,
    WithdrawalPolicyCodec,
)
from fbf.core.persistence.studies.sqlite.sqlite_repository import ExperimentIdentity
from fbf.core.study import BuiltStudy, StudyConfiguration, build_study_plan
from tests.support.ern.constants import (
    COHORTS_PER_CELL,
    DATA_DIR,
    WORKBOOK_ORACLE_CSV,
    OracleTable,
    load_oracle_table,
)

INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)

_WEIGHTS = (Decimal("0.5"), Decimal("0.75"))
_RATES = (Decimal("0.03"), Decimal("0.04"))
_HORIZON = 30
_FV_TARGET = Decimal("0.0")
_EXPECTED_UNITS = len(_WEIGHTS) * len(_RATES) * COHORTS_PER_CELL
_SLICE_UNITS = 500
_ROUNDING = ROUND_HALF_EVEN

_AggregateKey = tuple[float, float, int, float]
_Aggregate = tuple[int, int, Decimal]


class _DatasetLoader:
    def __init__(self, dataset: Dataset) -> None:
        self._dataset = dataset

    def load(self) -> Dataset:
        return self._dataset


def _reconstruction_context(dataset: Dataset) -> PersistenceReconstructionContext:
    return PersistenceReconstructionContext(
        dataset_loader=_DatasetLoader(dataset),
        policy_codecs={
            ("allocation", "AllocationPolicy"): AllocationPolicyCodec(),
            ("withdrawal", "WithdrawalPolicy"): WithdrawalPolicyCodec(),
        },
        simulation_result_codec=SimulationResultCodec(),
    )


def _build_subset_plan() -> BuiltStudy:
    config = StudyConfiguration(
        name="D2 Streaming Aggregate",
        description="Production streaming aggregate regression",
        version="1.0",
        allocation_policy_type="ConstantAllocationPolicy",
        allocation_policy_values=_WEIGHTS,
        withdrawal_policy_type="FixedRealWithdrawalPolicy",
        withdrawal_policy_values=_RATES,
        horizon_years=(_HORIZON,),
        cohort_horizon_years=60,
        final_value_target_values=(_FV_TARGET,),
        expense_ratio=Decimal("0.0005"),
    )
    return build_study_plan(config, str(DATA_DIR), INITIAL_WEALTH)


def _cell_key(unit: Any) -> _AggregateKey:
    return (
        float(unit.parameter_config.values["equity_allocation"]),
        float(unit.parameter_config.values["withdrawal_rate"]),
        int(unit.parameter_config.values["horizon_years"]),
        float(unit.parameter_config.values.get("final_value_target", 0)),
    )


def _aggregate(units: Sequence[Any], results: Sequence[Any]) -> dict[_AggregateKey, _Aggregate]:
    counts: dict[_AggregateKey, tuple[int, int]] = {}
    for unit, result in zip(units, results, strict=True):
        key = _cell_key(unit)
        total, successes = counts.get(key, (0, 0))
        success = result.statistics is not None and result.statistics.success
        counts[key] = (total + 1, successes + int(success))

    return {
        key: (
            total,
            successes,
            (Decimal(successes) / Decimal(total) * Decimal(100)).quantize(
                Decimal("1"), rounding=_ROUNDING
            ),
        )
        for key, (total, successes) in counts.items()
    }


def _expected_cell_keys() -> set[_AggregateKey]:
    return {
        (float(weight), float(rate), _HORIZON, float(_FV_TARGET))
        for weight in _WEIGHTS
        for rate in _RATES
    }


def _assert_matches_workbook(
    aggregates: dict[_AggregateKey, _Aggregate], oracle: OracleTable
) -> None:
    assert set(aggregates) == _expected_cell_keys()
    for key, (total, _successes, success_pct) in aggregates.items():
        weight, rate, horizon, _fv = key
        assert total == COHORTS_PER_CELL
        assert success_pct == Decimal(oracle[(weight, horizon)][rate])


def test_streaming_aggregate_matches_workbook_oracle_and_persistence(
    tmp_path: Path,
) -> None:
    pytest.importorskip("numba")

    built = _build_subset_plan()
    oracle = load_oracle_table(WORKBOOK_ORACLE_CSV)
    options = ExecutionOptions(
        backend=ExecutionBackend.FAST,
        strategy=ExecutionStrategy.SEQUENTIAL,
        summary_only=True,
    )

    assert len(built.plan.units) == _EXPECTED_UNITS
    assert len(built.cohorts) == COHORTS_PER_CELL

    repo = SQLiteRepository(str(tmp_path / "streaming-aggregate.db"))
    context = _reconstruction_context(built.experiment_definition.dataset)
    experiment_id = repo.save_experiment(
        ExperimentIdentity(name="d2-streaming-aggregate", revision="v1"),
        built.experiment_definition,
        context,
    )
    plan_id = repo.save_plan(built.plan, experiment_id, context)
    attempt = repo.begin_execution(plan_id, len(built.plan.units), context)

    units: list[Any] = []
    results: list[Any] = []
    slice_starts: list[int] = []
    started = time.perf_counter()
    for chunk in iter_execute_study_plan(built, options, max_units_per_slice=_SLICE_UNITS):
        slice_starts.append(chunk.start_index)
        units.extend(chunk.result.plan.units)
        results.extend(chunk.result.results)
        attempt = repo.append_execution_slice(
            attempt.result_id,
            attempt.attempt_id,
            chunk.start_index,
            chunk.result.results,
            context,
        )

        if len(slice_starts) == 1:
            assert repo.find_result_by_plan(plan_id) is None
            assert repo.get_execution_result_metadata(plan_id) is None
            assert repo.get_result_statistics(attempt.result_id) is None
            assert repo.get_available_parameters(attempt.result_id) is None
            assert [item.result_id for item in repo.list_incomplete_executions()] == [
                attempt.result_id
            ]
            with pytest.raises(ResultsNotFoundError):
                repo.load_execution_result(plan_id, context)

    elapsed = time.perf_counter() - started

    assert len(slice_starts) > 1
    assert slice_starts[0] == 0
    assert slice_starts == sorted(set(slice_starts))
    assert len(units) == _EXPECTED_UNITS
    assert len(results) == _EXPECTED_UNITS
    assert attempt.completed_units == _EXPECTED_UNITS

    streaming = _aggregate(units, results)
    _assert_matches_workbook(streaming, oracle)

    expected_successes = sum(successes for _, successes, _ in streaming.values())
    completed = repo.complete_execution(
        attempt.result_id, attempt.attempt_id, elapsed
    )
    assert completed.status == "completed"
    assert completed.completed_units == _EXPECTED_UNITS
    assert completed.success_count == expected_successes
    assert completed.failure_count == _EXPECTED_UNITS - expected_successes

    assert repo.list_incomplete_executions() == []
    assert repo.find_result_by_plan(plan_id) == attempt.result_id
    assert repo.find_plan_by_result(attempt.result_id) == plan_id
    assert repo.get_execution_attempt(attempt.result_id) == completed

    metadata = repo.get_execution_result_metadata(plan_id)
    assert metadata is not None
    assert metadata["total_units"] == _EXPECTED_UNITS
    assert metadata["success_count"] == expected_successes
    assert metadata["failure_count"] == _EXPECTED_UNITS - expected_successes

    loaded = repo.load_execution_result(plan_id, context)
    assert len(loaded.plan.units) == _EXPECTED_UNITS
    assert len(loaded.results) == _EXPECTED_UNITS
    loaded_aggregates = _aggregate(loaded.plan.units, loaded.results)
    _assert_matches_workbook(loaded_aggregates, oracle)
    assert loaded_aggregates == streaming

    whole_plan = execute_study_plan(built, options)
    assert len(whole_plan.plan.units) == _EXPECTED_UNITS
    assert len(whole_plan.results) == _EXPECTED_UNITS
    whole_plan_aggregates = _aggregate(whole_plan.plan.units, whole_plan.results)
    _assert_matches_workbook(whole_plan_aggregates, oracle)
    assert whole_plan_aggregates == streaming
