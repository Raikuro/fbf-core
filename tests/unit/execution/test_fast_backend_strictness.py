"""Contract tests for strict explicit-FAST execution.

Explicit ``FAST`` must either run every context on a Numba kernel or reject the
plan with ``UnsupportedConfigurationError``.  It must never construct or call
the legacy reference executor as an internal fallback.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies import (
    BuyAndHoldAllocationPolicy,
    ConstantAllocationPolicy,
    ConstantWithdrawalPolicy,
    EscalatingWithdrawalPolicy,
    FixedRealWithdrawalPolicy,
    WithdrawalFrequency,
)
from fbf.core.domain.policies.glidepath import GlidepathAllocationPolicy
from fbf.core.execution import (
    ExecutionBackend,
    ExecutionOptions,
    ExecutionStrategy,
    NoOpProfiler,
    UnsupportedConfigurationError,
    _auto_select_backend,
    _extract_simulation_contexts,
    execute_study_plan,
)
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
)
from fbf.core.execution.strategies.fast_path import (
    FastPathSimulationExecutor,
    is_fast_path_eligible,
)
from fbf.core.execution.strategies.numba_executor import (
    NumbaSimulationExecutor,
    is_numba_context_eligible,
)
from fbf.core.study.builder import BuiltStudy
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan

EQUITY = AssetClass(id="equity", name="", description="")
BOND = AssetClass(id="bond", name="", description="")
GOLD = AssetClass(id="gold", name="", description="")

INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)
START = date(1965, 11, 1)


def _make_dataset(months: int = 13, *, include_gold: bool = False) -> Dataset:
    snapshots = []
    equity = bond = gold = Decimal("100")
    current = START
    for _ in range(months):
        levels = {EQUITY: equity, BOND: bond}
        if include_gold:
            levels[GOLD] = gold
        snapshots.append(
            MarketSnapshot(
                date=current,
                index_levels=levels,
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            )
        )
        equity *= Decimal("1.005")
        bond *= Decimal("1.002")
        gold *= Decimal("1.003")
        current = date(current.year + (current.month // 12), current.month % 12 + 1, 1)
    return Dataset(snapshots=tuple(snapshots), frequency="monthly")


def _two_asset_portfolio() -> Portfolio:
    return Portfolio(
        holdings=(
            AssetHolding(asset_class=EQUITY, units=Decimal("5000")),
            AssetHolding(asset_class=BOND, units=Decimal("5000")),
        )
    )


def _three_asset_portfolio() -> Portfolio:
    units = (INITIAL_WEALTH.amount / Decimal("3")) / Decimal("100")
    return Portfolio(
        holdings=(
            AssetHolding(asset_class=EQUITY, units=units),
            AssetHolding(asset_class=BOND, units=units),
            AssetHolding(asset_class=GOLD, units=units),
        )
    )


def _make_built_study(
    allocation_policy: Any,
    withdrawal_policy: Any,
    *,
    portfolio: Portfolio | None = None,
    dataset: Dataset | None = None,
    final_value_target: Decimal | None = None,
    loan_draw_rate: Decimal | None = None,
) -> BuiltStudy:
    dataset = dataset or _make_dataset()
    unit = PlannedSimulationUnit(
        cohort=CohortSpecification(start_date=START),
        parameter_config=ParameterConfiguration(values={"withdrawal_rate": 0.04}),
        allocation_policy=allocation_policy,
        withdrawal_policy=withdrawal_policy,
        initial_portfolio=portfolio or _two_asset_portfolio(),
        dataset=dataset,
        horizon_months=12,
        final_value_target=final_value_target,
        loan_draw_rate=loan_draw_rate,
    )
    experiment = ExperimentDefinition(
        name="FAST strictness",
        description="FAST strictness",
        dataset=dataset,
        horizon_months=12,
        initial_wealth=INITIAL_WEALTH,
        cohorts=(unit.cohort,),
        allocation_policies=(allocation_policy,),
        withdrawal_policies=(withdrawal_policy,),
    )
    plan = ResearchPlan(experiment_definition=experiment, units=(unit,))
    return BuiltStudy(
        plan=plan,
        experiment_definition=experiment,
        cohorts=(unit.cohort,),
        param_configs=(unit.parameter_config,),
    )


def _fast_options() -> ExecutionOptions:
    return ExecutionOptions(
        backend=ExecutionBackend.FAST,
        strategy=ExecutionStrategy.SEQUENTIAL,
        summary_only=True,
    )


@pytest.mark.parametrize(
    ("allocation_policy", "withdrawal_policy"),
    [
        (
            ConstantAllocationPolicy(Decimal("0.6")),
            FixedRealWithdrawalPolicy(Decimal("0.04")),
        ),
        (
            ConstantAllocationPolicy(Decimal("0.6")),
            ConstantWithdrawalPolicy(Decimal("0.04")),
        ),
        (
            ConstantAllocationPolicy(Decimal("0.6")),
            EscalatingWithdrawalPolicy(
                Decimal("0.035"),
                Decimal("0.02"),
                frequency=WithdrawalFrequency.MONTHLY,
            ),
        ),
        (
            BuyAndHoldAllocationPolicy(Decimal("0.6")),
            FixedRealWithdrawalPolicy(Decimal("0.04")),
        ),
        (
            GlidepathAllocationPolicy(
                Decimal("0.4"),
                Decimal("0.8"),
                Decimal("0.005"),
                "passive",
            ),
            FixedRealWithdrawalPolicy(Decimal("0.04")),
        ),
    ],
)
def test_supported_generic_families_never_construct_reference(
    monkeypatch: pytest.MonkeyPatch,
    allocation_policy: Any,
    withdrawal_policy: Any,
) -> None:
    def _unexpected_reference(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("explicit FAST must not construct a reference executor")

    monkeypatch.setattr(
        "fbf.core.execution.strategies.numba_executor._create_default_simulation_executor",
        _unexpected_reference,
    )
    monkeypatch.setattr(
        "fbf.core.execution.strategies.parallel_executor._create_reference_simulation_executor",
        _unexpected_reference,
    )

    built = _make_built_study(allocation_policy, withdrawal_policy)
    result = execute_study_plan(built, _fast_options())

    assert len(result.results) == 1


def test_unsupported_generic_workload_raises() -> None:
    built = _make_built_study(
        ConstantAllocationPolicy(Decimal("0.5")),
        FixedRealWithdrawalPolicy(Decimal("0.04")),
        portfolio=_three_asset_portfolio(),
        dataset=_make_dataset(include_gold=True),
    )

    with pytest.raises(UnsupportedConfigurationError, match="FAST backend"):
        execute_study_plan(built, _fast_options())


def test_auto_keeps_graceful_route_for_unsupported_workload() -> None:
    built = _make_built_study(
        ConstantAllocationPolicy(Decimal("0.5")),
        FixedRealWithdrawalPolicy(Decimal("0.04")),
        portfolio=_three_asset_portfolio(),
        dataset=_make_dataset(include_gold=True),
    )

    executor = _auto_select_backend(built, NoOpProfiler())
    assert isinstance(executor, FastPathSimulationExecutor)


def test_non_workbook_static_requires_v0_equals_initial_wealth() -> None:
    allocation = ConstantAllocationPolicy(
        allocations={
            "equity": Decimal("0.5"),
            "bond": Decimal("0.3"),
            "gold": Decimal("0.2"),
        }
    )
    dataset = _make_dataset(include_gold=True)
    portfolio = _three_asset_portfolio()

    workbook_built = _make_built_study(
        allocation,
        FixedRealWithdrawalPolicy(Decimal("0.04")),
        portfolio=portfolio,
        dataset=dataset,
    )
    workbook_context = _extract_simulation_contexts(workbook_built.plan)[0]
    assert is_fast_path_eligible(workbook_context)
    assert is_numba_context_eligible(workbook_context)

    target_built = _make_built_study(
        allocation,
        FixedRealWithdrawalPolicy(Decimal("0.04")),
        portfolio=portfolio,
        dataset=dataset,
        final_value_target=Decimal("0.5"),
    )
    target_context = _extract_simulation_contexts(target_built.plan)[0]
    assert is_fast_path_eligible(target_context)
    assert not is_numba_context_eligible(target_context)

    with pytest.raises(UnsupportedConfigurationError, match="FAST backend"):
        execute_study_plan(target_built, _fast_options())


def test_strict_executor_rejects_ineligible_without_reference() -> None:
    executor = NumbaSimulationExecutor(require_all_eligible=True)
    built = _make_built_study(
        ConstantAllocationPolicy(Decimal("0.5")),
        FixedRealWithdrawalPolicy(Decimal("0.04")),
        portfolio=_three_asset_portfolio(),
        dataset=_make_dataset(include_gold=True),
    )
    contexts = _extract_simulation_contexts(built.plan)
    definition = EngineExperimentDefinition(
        name="strict",
        description="strict",
        simulation_contexts=contexts,
    )

    with pytest.raises(UnsupportedConfigurationError, match="FAST backend"):
        executor.execute(definition)


def test_debt_configuration_raises_for_generic_fast() -> None:
    built = _make_built_study(
        ConstantAllocationPolicy(Decimal("0.6")),
        FixedRealWithdrawalPolicy(Decimal("0.04")),
        loan_draw_rate=Decimal("0.01"),
    )

    with pytest.raises(UnsupportedConfigurationError, match="FAST backend"):
        execute_study_plan(built, _fast_options())
