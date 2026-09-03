"""Persistence round-trip test for final_value_target.

Proves that a PlannedSimulationUnit containing a non-None final_value_target
survives persist -> load with the correct value restored.

Also verifies that None (no target) round-trips correctly.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from fbf.core.domain.model.allocation import AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies.allocation_policy import AllocationPolicy
from fbf.core.domain.policies.decisions import AllocationDecision, WithdrawalDecision
from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy
from fbf.core.persistence.studies.sqlite import SQLiteRepository
from fbf.core.persistence.studies.sqlite.sqlite_repository import (
    ExperimentIdentity,
    PersistenceReconstructionContext,
    PolicyKind,
)
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan

# ---------------------------------------------------------------------------
# Test helpers (duplicates of infrastructure/test_sqlite_persistence.py pattern)
# ---------------------------------------------------------------------------

_ASSET = AssetClass(id="equity", name="", description="")
_SNAPSHOTS = tuple(
    MarketSnapshot(
        date=date(2000 + (i // 12), (i % 12) + 1, 1),
        index_levels={_ASSET: Decimal("100.00")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100.00"),
    )
    for i in range(240)
)
_DATASET = Dataset(snapshots=_SNAPSHOTS, frequency="monthly", version="TEST_v1")


class _DummyAlloc(AllocationPolicy):
    def decide(self, context: object) -> AllocationDecision:
        return AllocationDecision(
            reason="stub",
            allocation_target=AllocationTarget(weights={_ASSET: Decimal("1")}),
        )


class _DummyWithdraw(WithdrawalPolicy):
    def decide(self, context: object) -> WithdrawalDecision:
        return WithdrawalDecision(
            reason="stub",
            nominal_amount=Money(Decimal("500"), Currency.EUR),
            real_amount=Money(Decimal("500"), Currency.EUR),
        )


class _DummyDatasetResolver:
    def resolve(self, dataset_identifier: str) -> Dataset:
        return _DATASET


class _DummyAllocCodec:
    policy_type: str = "AllocationPolicy"
    policy_kind = PolicyKind.ALLOCATION

    def dump(self, policy: object) -> dict[str, str]:
        return {"equity_allocation": "0.75"}

    def load(self, parameters: dict[str, str]) -> _DummyAlloc:
        return _DummyAlloc()


class _DummyWithdrawCodec:
    policy_type: str = "WithdrawalPolicy"
    policy_kind = PolicyKind.WITHDRAWAL

    def dump(self, policy: object) -> dict[str, str]:
        return {"withdrawal_rate": "0.04"}

    def load(self, parameters: dict[str, str]) -> _DummyWithdraw:
        return _DummyWithdraw()


class _DummySimCodec:
    def dump(self, result: object) -> object:
        raise NotImplementedError("not needed for unit-level round-trip")

    def load(self, *args: object) -> object:
        raise NotImplementedError("not needed for unit-level round-trip")


def _make_ctx() -> PersistenceReconstructionContext:
    return PersistenceReconstructionContext(
        dataset_resolver=_DummyDatasetResolver(),
        policy_codecs={
            ("allocation", "AllocationPolicy"): _DummyAllocCodec(),  # type: ignore[dict-item]
            ("withdrawal", "WithdrawalPolicy"): _DummyWithdrawCodec(),  # type: ignore[dict-item]
        },
        simulation_result_codec=_DummySimCodec(),  # type: ignore[arg-type]
    )


def _build_experiment() -> ExperimentDefinition:
    return ExperimentDefinition(
        name="fvt-test",
        description="test",
        dataset=_DATASET,
        horizon_months=120,
        initial_wealth=Money(Decimal("100000"), Currency.EUR),
        cohorts=(CohortSpecification(start_date=date(2000, 1, 1)),),
        allocation_policies=(_DummyAlloc(),),
        withdrawal_policies=(_DummyWithdraw(),),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFinalValueTargetPersistence:
    """Round-trip tests for the final_value_target column."""

    def test_non_none_target_round_trips(self, tmp_path: Path) -> None:
        """A unit with final_value_target=0.75 survives persist -> load."""
        repo = SQLiteRepository(str(tmp_path / "test.db"))
        ctx = _make_ctx()
        experiment = _build_experiment()
        exp_id = repo.save_experiment(
            ExperimentIdentity(name="fvt-test", revision="v1"), experiment, ctx
        )

        target = Decimal("0.75")
        unit = PlannedSimulationUnit(
            cohort=CohortSpecification(start_date=date(2000, 1, 1)),
            parameter_config=ParameterConfiguration(
                values={"equity_allocation": 0.75, "withdrawal_rate": 0.04, "horizon_years": 30}
            ),
            allocation_policy=_DummyAlloc(),
            withdrawal_policy=_DummyWithdraw(),
            initial_portfolio=Portfolio(
                holdings=(AssetHolding(asset_class=_ASSET, units=Decimal("100000")),)
            ),
            dataset=_DATASET.slice(date(2000, 1, 1), 120),
            horizon_months=120,
            final_value_target=target,
        )
        plan = ResearchPlan(experiment_definition=experiment, units=(unit,))
        plan_id = repo.save_plan(plan, exp_id, ctx)

        loaded = repo.load_plan(plan_id, ctx)
        assert len(loaded.units) == 1
        assert loaded.units[0].final_value_target == target

    def test_none_target_round_trips(self, tmp_path: Path) -> None:
        """A unit with final_value_target=None survives persist -> load as None."""
        repo = SQLiteRepository(str(tmp_path / "test.db"))
        ctx = _make_ctx()
        experiment = _build_experiment()
        exp_id = repo.save_experiment(
            ExperimentIdentity(name="fvt-none", revision="v1"), experiment, ctx
        )

        unit = PlannedSimulationUnit(
            cohort=CohortSpecification(start_date=date(2000, 1, 1)),
            parameter_config=ParameterConfiguration(
                values={"equity_allocation": 0.75, "withdrawal_rate": 0.04, "horizon_years": 30}
            ),
            allocation_policy=_DummyAlloc(),
            withdrawal_policy=_DummyWithdraw(),
            initial_portfolio=Portfolio(
                holdings=(AssetHolding(asset_class=_ASSET, units=Decimal("100000")),)
            ),
            dataset=_DATASET.slice(date(2000, 1, 1), 120),
            horizon_months=120,
            final_value_target=None,
        )
        plan = ResearchPlan(experiment_definition=experiment, units=(unit,))
        plan_id = repo.save_plan(plan, exp_id, ctx)

        loaded = repo.load_plan(plan_id, ctx)
        assert len(loaded.units) == 1
        assert loaded.units[0].final_value_target is None

    def test_zero_target_round_trips(self, tmp_path: Path) -> None:
        """A unit with final_value_target=0 (capital depletion) survives correctly."""
        repo = SQLiteRepository(str(tmp_path / "test.db"))
        ctx = _make_ctx()
        experiment = _build_experiment()
        exp_id = repo.save_experiment(
            ExperimentIdentity(name="fvt-zero", revision="v1"), experiment, ctx
        )

        unit = PlannedSimulationUnit(
            cohort=CohortSpecification(start_date=date(2000, 1, 1)),
            parameter_config=ParameterConfiguration(
                values={"equity_allocation": 0.75, "withdrawal_rate": 0.04, "horizon_years": 30}
            ),
            allocation_policy=_DummyAlloc(),
            withdrawal_policy=_DummyWithdraw(),
            initial_portfolio=Portfolio(
                holdings=(AssetHolding(asset_class=_ASSET, units=Decimal("100000")),)
            ),
            dataset=_DATASET.slice(date(2000, 1, 1), 120),
            horizon_months=120,
            final_value_target=Decimal("0"),
        )
        plan = ResearchPlan(experiment_definition=experiment, units=(unit,))
        plan_id = repo.save_plan(plan, exp_id, ctx)

        loaded = repo.load_plan(plan_id, ctx)
        assert len(loaded.units) == 1
        assert loaded.units[0].final_value_target == Decimal("0")

    def test_multiple_targets_round_trip(self, tmp_path: Path) -> None:
        """Multiple units with different targets each round-trip correctly."""
        repo = SQLiteRepository(str(tmp_path / "test.db"))
        ctx = _make_ctx()
        experiment = _build_experiment()
        exp_id = repo.save_experiment(
            ExperimentIdentity(name="fvt-multi", revision="v1"), experiment, ctx
        )

        targets = [
            Decimal("0.00"),
            Decimal("0.25"),
            Decimal("0.50"),
            Decimal("0.75"),
            Decimal("1.00"),
        ]
        units = []
        for i, t in enumerate(targets):
            units.append(
                PlannedSimulationUnit(
                    cohort=CohortSpecification(start_date=date(2000, 1 + i, 1)),
                    parameter_config=ParameterConfiguration(
                        values={
                            "equity_allocation": 0.75,
                            "withdrawal_rate": 0.04,
                            "horizon_years": 30,
                        }
                    ),
                    allocation_policy=_DummyAlloc(),
                    withdrawal_policy=_DummyWithdraw(),
                    initial_portfolio=Portfolio(
                        holdings=(AssetHolding(asset_class=_ASSET, units=Decimal("100000")),)
                    ),
                    dataset=_DATASET.slice(date(2000, 1 + i, 1), 120),
                    horizon_months=120,
                    final_value_target=t,
                )
            )

        plan = ResearchPlan(experiment_definition=experiment, units=tuple(units))
        plan_id = repo.save_plan(plan, exp_id, ctx)

        loaded = repo.load_plan(plan_id, ctx)
        assert len(loaded.units) == 5
        for loaded_unit, expected_target in zip(loaded.units, targets, strict=True):
            assert loaded_unit.final_value_target == expected_target
