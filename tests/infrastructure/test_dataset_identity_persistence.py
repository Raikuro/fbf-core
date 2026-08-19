"""Tests for WP-PERSISTENCE-DATASET-IDENTITY.

Verifies dataset resource identity persistence, slicing preservation,
file loader initialization, and legacy version fallback / ambiguity handling.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.decision_context import DecisionContext
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies.allocation_policy import AllocationPolicy
from fbf.core.domain.policies.decisions import AllocationDecision, WithdrawalDecision
from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy
from fbf.core.persistence.studies.sqlite.codecs import DefaultDatasetResolver
from fbf.core.persistence.studies.sqlite.context import (
    _load_dataset_from_file,
    create_persistence_context,
)
from fbf.core.persistence.studies.sqlite.errors import StudyNotFoundError
from fbf.core.persistence.studies.sqlite.sqlite_repository import (
    ExperimentIdentity,
    PersistenceReconstructionContext,
    SQLiteRepository,
)
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition


def _make_dummy_dataset(
    num_snapshots: int = 12,
    version: str = "1.0",
    identifier: str | None = None,
) -> Dataset:
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
        version=version,
        identifier=identifier,
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
# Test 1: Loader establishes identity
# ---------------------------------------------------------------------------


def test_loader_establishes_dataset_identifier(tmp_path: Path) -> None:
    dataset_file = tmp_path / "sp500.json"
    raw_data = {
        "version": "1.0",
        "frequency": "monthly",
        "snapshots": [
            {
                "date": "2000-01-01",
                "inflation": "0.02",
                "inflation_cumulative": "1.0",
                "is_ath": False,
                "is_underwater": False,
                "running_ath": "100.0",
                "index_levels": {"equity": "100.0"},
            }
        ],
    }
    dataset_file.write_text(json.dumps(raw_data), encoding="utf-8")

    dataset = _load_dataset_from_file(dataset_file)

    assert dataset.identifier == "sp500"
    assert dataset.version == "1.0"


# ---------------------------------------------------------------------------
# Test 2: Slice preserves identity
# ---------------------------------------------------------------------------


def test_slice_preserves_identifier_and_version() -> None:
    original = _make_dummy_dataset(num_snapshots=24, version="1.0", identifier="sp500")
    sliced = original.slice(date(2000, 1, 1), 12)

    assert sliced.identifier == "sp500"
    assert sliced.version == "1.0"
    assert len(sliced) == 12


# ---------------------------------------------------------------------------
# Test 3: Save persists canonical identity
# ---------------------------------------------------------------------------


def test_save_experiment_persists_canonical_identifier(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    repo = SQLiteRepository(str(db_path))
    dataset = _make_dummy_dataset(num_snapshots=12, version="1.0", identifier="sp500")
    exp_def = _make_experiment_def(dataset)
    ctx = create_persistence_context()
    ctx = PersistenceReconstructionContext(
        dataset_resolver=DefaultDatasetResolver({"sp500": dataset}),
        policy_codecs=ctx.policy_codecs,
        simulation_result_codec=ctx.simulation_result_codec,
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
    assert row[0] == "sp500"
    assert row[0] != "1.0"


# ---------------------------------------------------------------------------
# Test 4: Legacy database with unique version
# ---------------------------------------------------------------------------


def test_legacy_database_unique_version(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    repo = SQLiteRepository(str(db_path))

    dataset = _make_dummy_dataset(num_snapshots=12, version="1.0", identifier="sp500")
    exp_def = _make_experiment_def(dataset)
    resolver = DefaultDatasetResolver({"sp500": dataset})

    ctx = create_persistence_context()
    ctx = PersistenceReconstructionContext(
        dataset_resolver=resolver,
        policy_codecs=ctx.policy_codecs,
        simulation_result_codec=ctx.simulation_result_codec,
    )

    exp_id = repo.save_experiment(
        identity=ExperimentIdentity(name="legacy_exp", revision="v1"),
        experiment=exp_def,
        context=ctx,
    )

    # Manually update row in DB to simulate old behavior where dataset_identifier = "1.0"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "UPDATE experiments SET dataset_identifier = '1.0' WHERE experiment_id = ?",
            (exp_id,),
        )
        conn.commit()

    # Attempt to load experiment — should resolve via legacy version fallback
    loaded_exp = repo.load_experiment(exp_id, ctx)
    assert loaded_exp.dataset.version == "1.0"
    assert loaded_exp.dataset.identifier == "sp500"


# ---------------------------------------------------------------------------
# Test 5: Legacy database with ambiguous version
# ---------------------------------------------------------------------------


def test_legacy_database_ambiguous_version_fails(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_ambiguous.db"
    repo = SQLiteRepository(str(db_path))

    sp500_ds = _make_dummy_dataset(num_snapshots=12, version="1.0", identifier="sp500")
    acwi_ds = _make_dummy_dataset(num_snapshots=12, version="1.0", identifier="acwi")

    exp_def = _make_experiment_def(sp500_ds)
    resolver = DefaultDatasetResolver({"sp500": sp500_ds, "acwi": acwi_ds})

    ctx = create_persistence_context()
    ctx = PersistenceReconstructionContext(
        dataset_resolver=resolver,
        policy_codecs=ctx.policy_codecs,
        simulation_result_codec=ctx.simulation_result_codec,
    )

    exp_id = repo.save_experiment(
        identity=ExperimentIdentity(name="ambiguous_exp", revision="v1"),
        experiment=exp_def,
        context=ctx,
    )

    # Manually set dataset_identifier to legacy "1.0"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "UPDATE experiments SET dataset_identifier = '1.0' WHERE experiment_id = ?",
            (exp_id,),
        )
        conn.commit()

    # Resolution must fail with StudyNotFoundError and communicate ambiguity
    with pytest.raises(StudyNotFoundError, match="Ambiguous legacy dataset version"):
        repo.load_experiment(exp_id, ctx)


# ---------------------------------------------------------------------------
# Test 6: Full divergent identity round trip
# ---------------------------------------------------------------------------


def test_full_divergent_identity_round_trip(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    dataset_file = data_dir / "sp500_historical.json"
    raw_data = {
        "version": "1.0",
        "frequency": "monthly",
        "snapshots": [
            {
                "date": f"2000-{(i % 12) + 1:02d}-01",
                "inflation": "0.02",
                "inflation_cumulative": "1.0",
                "is_ath": False,
                "is_underwater": False,
                "running_ath": "100.0",
                "index_levels": {"equity": "100.0"},
            }
            for i in range(12)
        ],
    }
    dataset_file.write_text(json.dumps(raw_data), encoding="utf-8")

    loaded_ds = _load_dataset_from_file(dataset_file)
    assert loaded_ds.identifier == "sp500_historical"
    assert loaded_ds.version == "1.0"

    db_path = tmp_path / "e2e.db"
    repo = SQLiteRepository(str(db_path))

    exp_def = _make_experiment_def(loaded_ds, name="e2e_exp")
    resolver = DefaultDatasetResolver.from_data_dir(str(data_dir))

    ctx = create_persistence_context()
    ctx = PersistenceReconstructionContext(
        dataset_resolver=resolver,
        policy_codecs=ctx.policy_codecs,
        simulation_result_codec=ctx.simulation_result_codec,
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
    assert row[0] == "sp500_historical"

    # Reload experiment and verify
    reloaded_exp = repo.load_experiment(exp_id, ctx)
    assert reloaded_exp.dataset.identifier == "sp500_historical"
    assert reloaded_exp.dataset.version == "1.0"
