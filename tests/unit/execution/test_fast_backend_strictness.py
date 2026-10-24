"""Contract tests for fail-closed Numba execution.

Every plan must either run entirely on a Numba kernel or be rejected with
``UnsupportedConfigurationError``.  There is no fallback engine.
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
from fbf.core.domain.policies.part52_withdrawal import Part52WithdrawalPolicy
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
from fbf.core.execution.strategies.eligibility import is_constant_allocation_eligible
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
    interest_rate: Decimal | None = None,
    ltv_limit: Decimal | None = None,
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
        interest_rate=interest_rate,
        ltv_limit=ltv_limit,
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


def _make_mixed_generic_built_study() -> BuiltStudy:
    dataset = _make_dataset()
    fixed_real = PlannedSimulationUnit(
        cohort=CohortSpecification(start_date=START),
        parameter_config=ParameterConfiguration(
            values={"withdrawal_rate": 0.04}
        ),
        allocation_policy=ConstantAllocationPolicy(Decimal("0.6")),
        withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.04")),
        initial_portfolio=_two_asset_portfolio(),
        dataset=dataset,
        horizon_months=12,
    )
    constant_nominal = PlannedSimulationUnit(
        cohort=CohortSpecification(start_date=START),
        parameter_config=ParameterConfiguration(
            values={"withdrawal_rate": 0.03}
        ),
        allocation_policy=ConstantAllocationPolicy(Decimal("0.6")),
        withdrawal_policy=ConstantWithdrawalPolicy(Decimal("0.03")),
        initial_portfolio=_two_asset_portfolio(),
        dataset=dataset,
        horizon_months=12,
    )
    experiment = ExperimentDefinition(
        name="Mixed generic families",
        description="Mixed generic families",
        dataset=dataset,
        horizon_months=12,
        initial_wealth=INITIAL_WEALTH,
        cohorts=(fixed_real.cohort,),
        allocation_policies=(fixed_real.allocation_policy,),
        withdrawal_policies=(
            fixed_real.withdrawal_policy,
            constant_nominal.withdrawal_policy,
        ),
    )
    plan = ResearchPlan(
        experiment_definition=experiment,
        units=(fixed_real, constant_nominal),
    )
    return BuiltStudy(
        plan=plan,
        experiment_definition=experiment,
        cohorts=(fixed_real.cohort,),
        param_configs=(
            fixed_real.parameter_config,
            constant_nominal.parameter_config,
        ),
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
def test_supported_generic_families_execute(
    allocation_policy: Any,
    withdrawal_policy: Any,
) -> None:
    built = _make_built_study(allocation_policy, withdrawal_policy)
    result = execute_study_plan(built, _fast_options())

    assert len(result.results) == 1


@pytest.mark.parametrize(
    ("allocation_policy", "withdrawal_policy"),
    [
        (
            ConstantAllocationPolicy(Decimal("0.6")),
            FixedRealWithdrawalPolicy(
                Decimal("0.04"), frequency=WithdrawalFrequency.ANNUAL
            ),
        ),
        (
            ConstantAllocationPolicy(Decimal("0.6")),
            ConstantWithdrawalPolicy(
                Decimal("0.04"), frequency=WithdrawalFrequency.ANNUAL
            ),
        ),
        (
            BuyAndHoldAllocationPolicy(Decimal("0.6")),
            FixedRealWithdrawalPolicy(
                Decimal("0.04"), frequency=WithdrawalFrequency.ANNUAL
            ),
        ),
        (
            GlidepathAllocationPolicy(
                Decimal("0.4"),
                Decimal("0.8"),
                Decimal("0.005"),
                "passive",
            ),
            FixedRealWithdrawalPolicy(
                Decimal("0.04"), frequency=WithdrawalFrequency.ANNUAL
            ),
        ),
    ],
)
def test_annual_frequency_rejected_by_monthly_only_generic_kernels(
    allocation_policy: Any,
    withdrawal_policy: Any,
) -> None:
    built = _make_built_study(allocation_policy, withdrawal_policy)
    context = _extract_simulation_contexts(built.plan)[0]

    assert not is_numba_context_eligible(context)
    with pytest.raises(UnsupportedConfigurationError):
        execute_study_plan(built, _fast_options())
    with pytest.raises(UnsupportedConfigurationError):
        _auto_select_backend(built, NoOpProfiler())


def test_annual_part52_frequency_rejected_by_dispatch() -> None:
    built = _make_built_study(
        ConstantAllocationPolicy(Decimal("0.75")),
        Part52WithdrawalPolicy(
            withdrawal_rate=Decimal("0.0391"),
            borrow_pct=Decimal("0.4108"),
            drawdown_threshold=Decimal("0.20"),
            frequency=WithdrawalFrequency.ANNUAL,
        ),
        interest_rate=Decimal("0.015"),
        ltv_limit=Decimal("0.5"),
    )

    with pytest.raises(UnsupportedConfigurationError):
        execute_study_plan(built, _fast_options())
    with pytest.raises(UnsupportedConfigurationError):
        execute_study_plan(built, ExecutionOptions(summary_only=True))


def test_annual_escalating_frequency_executes() -> None:
    built = _make_built_study(
        ConstantAllocationPolicy(Decimal("0.6")),
        EscalatingWithdrawalPolicy(
            Decimal("0.035"),
            Decimal("0.02"),
            frequency=WithdrawalFrequency.ANNUAL,
        ),
    )

    result = execute_study_plan(built, _fast_options())

    assert len(result.results) == 1


def test_auto_routes_constant_nominal() -> None:
    built = _make_built_study(
        ConstantAllocationPolicy(Decimal("0.6")),
        ConstantWithdrawalPolicy(Decimal("0.04")),
    )
    result = execute_study_plan(built, ExecutionOptions())

    assert len(result.results) == 1


def test_auto_and_fast_execute_mixed_generic_families() -> None:
    built = _make_mixed_generic_built_study()

    auto = execute_study_plan(built, ExecutionOptions(summary_only=True))
    fast = execute_study_plan(built, _fast_options())

    assert len(auto.results) == 2
    assert len(fast.results) == 2
    assert [r.statistics.success for r in auto.results] == [
        r.statistics.success for r in fast.results
    ]


def test_unsupported_generic_workload_raises() -> None:
    built = _make_built_study(
        ConstantAllocationPolicy(Decimal("0.5")),
        FixedRealWithdrawalPolicy(Decimal("0.04")),
        portfolio=_three_asset_portfolio(),
        dataset=_make_dataset(include_gold=True),
    )

    with pytest.raises(UnsupportedConfigurationError, match="FAST backend"):
        execute_study_plan(built, _fast_options())


def test_auto_rejects_unsupported_workload() -> None:
    built = _make_built_study(
        ConstantAllocationPolicy(Decimal("0.5")),
        FixedRealWithdrawalPolicy(Decimal("0.04")),
        portfolio=_three_asset_portfolio(),
        dataset=_make_dataset(include_gold=True),
    )

    with pytest.raises(UnsupportedConfigurationError):
        _auto_select_backend(built, NoOpProfiler())


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
    assert is_constant_allocation_eligible(workbook_context)
    assert is_numba_context_eligible(workbook_context)

    target_built = _make_built_study(
        allocation,
        FixedRealWithdrawalPolicy(Decimal("0.04")),
        portfolio=portfolio,
        dataset=dataset,
        final_value_target=Decimal("0.5"),
    )
    target_context = _extract_simulation_contexts(target_built.plan)[0]
    assert is_constant_allocation_eligible(target_context)
    assert not is_numba_context_eligible(target_context)

    with pytest.raises(UnsupportedConfigurationError, match="FAST backend"):
        execute_study_plan(target_built, _fast_options())


def test_executor_rejects_ineligible_context() -> None:
    executor = NumbaSimulationExecutor()
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

    with pytest.raises(UnsupportedConfigurationError, match="Numba backend"):
        executor.execute(definition)


def test_debt_configuration_raises_for_generic_fast() -> None:
    built = _make_built_study(
        ConstantAllocationPolicy(Decimal("0.6")),
        FixedRealWithdrawalPolicy(Decimal("0.04")),
        loan_draw_rate=Decimal("0.01"),
    )

    with pytest.raises(UnsupportedConfigurationError, match="FAST backend"):
        execute_study_plan(built, _fast_options())
