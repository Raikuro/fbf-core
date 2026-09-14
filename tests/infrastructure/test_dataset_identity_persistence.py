"""Tests for dataset persistence contract.

Verifies:
- Dataset slicing preserves length
- Save/load round trip works with CanonicalDatasetLoader
- dataset_identifier column is always NULL for new records
"""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.decision_context import DecisionContext
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies.allocation_policy import AllocationPolicy
from fbf.core.domain.policies.decisions import AllocationDecision, WithdrawalDecision
from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy
from fbf.core.persistence.studies.sqlite.context import create_persistence_context
from fbf.core.persistence.studies.sqlite.sqlite_repository import (
    ExperimentIdentity,
    PersistenceReconstructionContext,
    SQLiteRepository,
)
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition


def _make_dummy_dataset(num_snapshots: int = 12) -> Dataset:
    equity = AssetClass(id="equity", name="Equity", description="")
    fixed_snapshots = []
    year = 2000
    month = 1
    for i in range(num_snapshots):
        fixed_snapshots.append(
            MarketSnapshot(
                date=date(year, month, 1),
                index_levels={equity: Decimal("100.0") + Decimal(i)},
                inflation=Decimal("0.02"),
                inflation_cumulative=Decimal("1.0"),
                is_ath=False,
                is_underwater=False,
                running_ath=Decimal("100.0"),
            )
        )
        month += 1
        if month > 12:
            month = 1
            year += 1

    return Dataset(
        snapshots=tuple(fixed_snapshots),
        frequency="monthly",
    )


def _make_experiment_def(dataset: Dataset, name: str = "test_exp") -> ExperimentDefinition:
    class _DummyAlloc(AllocationPolicy):
        equity_allocation = "1.0"

        def decide(self, context: DecisionContext) -> AllocationDecision:
            raise NotImplementedError

    class _DummyWithdraw(WithdrawalPolicy):
        withdrawal_rate = "0.04"

        def decide(self, context: DecisionContext) -> WithdrawalDecision:
            raise NotImplementedError

    return ExperimentDefinition(
        name=name,
        description="Test experiment description",
        dataset=dataset,
        horizon_months=12,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        cohorts=(CohortSpecification(start_date=date(2000, 1, 1)),),
        allocation_policies=(_DummyAlloc(),),
        withdrawal_policies=(_DummyWithdraw(),),
    )


# ---------------------------------------------------------------------------
# Test 1: Slice preserves length
# ---------------------------------------------------------------------------


def test_slice_preserves_length() -> None:
    original = _make_dummy_dataset(num_snapshots=24)
    sliced = original.slice(date(2000, 1, 1), 12)

    assert len(sliced) == 12


# ---------------------------------------------------------------------------
# Test 2: Save persists NULL dataset_identifier
# ---------------------------------------------------------------------------


def test_save_experiment_persists_null_dataset_identifier(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    repo = SQLiteRepository(str(db_path))
    dataset = _make_dummy_dataset(num_snapshots=12)
    exp_def = _make_experiment_def(dataset)

    class _TestLoader:
        def load(self) -> Dataset:
            return dataset

    ref_ctx = create_persistence_context("data/ern")
    ctx = PersistenceReconstructionContext(
        dataset_loader=_TestLoader(),
        policy_codecs=ref_ctx.policy_codecs,
        simulation_result_codec=ref_ctx.simulation_result_codec,
    )

    exp_id = repo.save_experiment(
        identity=ExperimentIdentity(name="sp500_exp", revision="v1"),
        experiment=exp_def,
        context=ctx,
    )

    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT dataset_identifier FROM experiments WHERE experiment_id = ?",
            (exp_id,),
        ).fetchone()

    assert row is not None
    assert row[0] is None


# ---------------------------------------------------------------------------
# Test 3: Full round trip with synthetic dataset
# ---------------------------------------------------------------------------


def test_full_round_trip_with_synthetic_dataset(tmp_path: Path) -> None:
    dataset = _make_dummy_dataset(num_snapshots=12)

    db_path = tmp_path / "e2e.db"
    repo = SQLiteRepository(str(db_path))

    exp_def = _make_experiment_def(dataset, name="e2e_exp")

    class _TestLoader:
        def load(self) -> Dataset:
            return dataset

    ref_ctx = create_persistence_context("data/ern")
    ctx = PersistenceReconstructionContext(
        dataset_loader=_TestLoader(),
        policy_codecs=ref_ctx.policy_codecs,
        simulation_result_codec=ref_ctx.simulation_result_codec,
    )

    exp_id = repo.save_experiment(
        identity=ExperimentIdentity(name="e2e_exp", revision="v1"),
        experiment=exp_def,
        context=ctx,
    )

    # Verify column value
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT dataset_identifier FROM experiments WHERE experiment_id = ?",
            (exp_id,),
        ).fetchone()
    assert row is not None
    assert row[0] is None

    # Reload experiment and verify
    reloaded_exp = repo.load_experiment(exp_id, ctx)
    assert reloaded_exp is not None
