"""Research-scale tests for explicit N-asset allocation through the engine.

Validates the explicit (N >= 2) ``ConstantAllocationPolicy`` form against an
independent Decimal oracle, and verifies backend routing, cache identity, and
the deferred-strategy fallback for allocations the Numba kernels do not encode.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import (
    ConstantAllocationPolicy,
    ConstantWithdrawalPolicy,
    FixedRealWithdrawalPolicy,
)
from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy
from fbf.core.execution.pipeline.executor import SimulationExecutor
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    SimulationResult,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.fast_path import (
    evaluate_closed_form,
    is_fast_path_eligible,
)
from fbf.core.execution.strategies.numba_executor import (
    NumbaSimulationExecutor,
    _is_constant_nominal_eligible,
)
from fbf.core.execution.strategies.part52_numba_executor import is_part52_eligible
from fbf.core.execution.strategies.reference import ReferenceSimulationExecutor
from fbf.core.study.builder import build_initial_portfolio

_EQ = AssetClass(id="equity", name="", description="")
_BD = AssetClass(id="bond", name="", description="")
_GD = AssetClass(id="gold", name="", description="")
_ASSETS = (_EQ, _BD, _GD)

_WEIGHTS = {"equity": Decimal("0.5"), "bond": Decimal("0.3"), "gold": Decimal("0.2")}
_INITIAL_WEALTH = Decimal("1000000")
_RATE = Decimal("0.04")

_NUMBA = NumbaSimulationExecutor()
_REFERENCE = ReferenceSimulationExecutor()


def _make_dataset(n_months: int) -> Dataset:
    snapshots = []
    pe = pb = pg = Decimal("100")
    for m in range(n_months):
        snapshots.append(
            MarketSnapshot(
                date=date(1900 + m // 12, m % 12 + 1, 1),
                index_levels={_EQ: pe, _BD: pb, _GD: pg},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            )
        )
        pe *= Decimal("1.007")
        pb *= Decimal("1.003")
        pg *= Decimal("1.005")
    return Dataset(snapshots=tuple(snapshots), frequency="monthly")


def _make_context(
    dataset: Dataset,
    horizon: int,
    weights: dict[str, Decimal] | None = None,
    *,
    rate: Decimal = _RATE,
    fee: Decimal | None = None,
    withdrawal_policy: WithdrawalPolicy | None = None,
) -> SimulationContext:
    start = dataset[0].date
    wealth = Money(_INITIAL_WEALTH, Currency.EUR)
    if weights is None:
        allocation: ConstantAllocationPolicy = ConstantAllocationPolicy(Decimal("0.5"))
    else:
        allocation = ConstantAllocationPolicy(allocations=dict(weights))
    return SimulationContext(
        experiment_name="test",
        cohort=str(start),
        start_date=start,
        horizon_months=horizon,
        initial_wealth=wealth,
        initial_portfolio=build_initial_portfolio(wealth, dataset),
        dataset=dataset.slice(start, horizon),
        allocation_policy=allocation,
        withdrawal_policy=(
            withdrawal_policy
            if withdrawal_policy is not None
            else FixedRealWithdrawalPolicy(rate)
        ),
        expense_ratio=fee,
    )


def _oracle(
    dataset: Dataset,
    horizon: int,
    weights: dict[AssetClass, Decimal],
    rate: Decimal,
    fee: Decimal,
) -> tuple[Decimal, bool, Decimal]:
    """Independent Decimal reproduction of the workbook SCR methodology."""
    snapshots = dataset.snapshots
    n_assets = Decimal(len(_ASSETS))
    initial_value = sum(
        (
            (_INITIAL_WEALTH / n_assets)
            / snapshots[0].index_levels[ac]
            * snapshots[0].index_levels[ac]
            for ac in _ASSETS
        ),
        Decimal("0"),
    )
    n_returns = horizon - 1
    returns = []
    for m in range(n_returns):
        monthly = Decimal("0")
        for asset_class, weight in weights.items():
            monthly += weight * (
                snapshots[m + 1].index_levels[asset_class]
                / snapshots[m].index_levels[asset_class]
                - Decimal("1")
            )
        returns.append(monthly - fee / Decimal("12"))

    cumulative = [Decimal("1")]
    for monthly in returns:
        cumulative.append(cumulative[-1] * (Decimal("1") + monthly))
    scr = Decimal("12") / sum(Decimal("1") / cumulative[t] for t in range(n_returns))

    value: Decimal = initial_value
    withdrawal = initial_value * rate / Decimal("12")
    for monthly in returns:
        if value < withdrawal:
            value = Decimal("0")
            break
        value = (value - withdrawal) * (Decimal("1") + monthly)
    return scr, scr >= rate, value


def _run(executor: SimulationExecutor, context: SimulationContext) -> SimulationResult:
    definition = EngineExperimentDefinition(
        name="test", description="test", simulation_contexts=(context,)
    )
    run = executor.execute(definition)
    return run.simulation_results[0]


def _weights_ordered() -> dict[AssetClass, Decimal]:
    return {_EQ: _WEIGHTS["equity"], _BD: _WEIGHTS["bond"], _GD: _WEIGHTS["gold"]}


@pytest.mark.parametrize("fee", [Decimal("0"), Decimal("0.0005")])
def test_fast_path_matches_independent_oracle(fee: Decimal) -> None:
    dataset = _make_dataset(241)
    context = _make_context(dataset, 120, _WEIGHTS, fee=fee)
    result = evaluate_closed_form(context)
    _, expected_success, expected_value = _oracle(
        dataset.slice(dataset[0].date, 120), 120, _weights_ordered(), _RATE, fee
    )
    assert result.statistics.success is expected_success
    assert result.statistics.final_wealth.amount == expected_value


@pytest.mark.parametrize("fee", [Decimal("0"), Decimal("0.0005")])
def test_numba_matches_fast_path(fee: Decimal) -> None:
    dataset = _make_dataset(241)
    context = _make_context(dataset, 120, _WEIGHTS, fee=fee)
    fast = evaluate_closed_form(context)
    numba = _run(_NUMBA, context)
    assert numba.statistics.success == fast.statistics.success
    assert numba.statistics.failure_month == fast.statistics.failure_month
    assert numba.statistics.months_simulated == fast.statistics.months_simulated
    diff = abs(
        numba.statistics.final_wealth.amount - fast.statistics.final_wealth.amount
    )
    assert diff < Decimal("0.05")


def test_numba_matches_fast_path_on_depletion() -> None:
    dataset = _make_dataset(241)
    context = _make_context(dataset, 120, _WEIGHTS, rate=Decimal("0.20"))
    fast = evaluate_closed_form(context)
    numba = _run(_NUMBA, context)
    assert not fast.statistics.success
    assert numba.statistics.success == fast.statistics.success
    assert numba.statistics.failure_month == fast.statistics.failure_month


class TestEligibility:
    def test_explicit_three_asset_eligible(self) -> None:
        dataset = _make_dataset(121)
        context = _make_context(dataset, 120, _WEIGHTS)
        assert is_fast_path_eligible(context)

    def test_legacy_three_asset_not_eligible(self) -> None:
        dataset = _make_dataset(121)
        context = _make_context(dataset, 120, None)
        assert not is_fast_path_eligible(context)

    def test_explicit_incomplete_mapping_not_eligible(self) -> None:
        dataset = _make_dataset(121)
        context = _make_context(
            dataset, 120, {"equity": Decimal("0.5"), "bond": Decimal("0.5")}
        )
        assert not is_fast_path_eligible(context)


class TestGroupIdentity:
    def test_reordered_mapping_shares_gf_cache(self) -> None:
        executor = NumbaSimulationExecutor()
        dataset = _make_dataset(241)
        ordered = _make_context(dataset, 120, _WEIGHTS)
        reordered = _make_context(
            dataset,
            120,
            {"gold": Decimal("0.2"), "bond": Decimal("0.3"), "equity": Decimal("0.5")},
        )
        executor.execute(
            EngineExperimentDefinition(
                name="t",
                description="t",
                simulation_contexts=(ordered, reordered),
            )
        )
        assert len(executor.gf_cache) == 1

    def test_distinct_weights_separate_entries(self) -> None:
        executor = NumbaSimulationExecutor()
        dataset = _make_dataset(241)
        a = _make_context(dataset, 120, _WEIGHTS)
        b = _make_context(
            dataset,
            120,
            {"equity": Decimal("0.4"), "bond": Decimal("0.3"), "gold": Decimal("0.3")},
        )
        executor.execute(
            EngineExperimentDefinition(
                name="t", description="t", simulation_contexts=(a, b)
            )
        )
        assert len(executor.gf_cache) == 2


class TestDeferredFallback:
    def test_nominal_gate_rejects_explicit(self) -> None:
        dataset = _make_dataset(121)
        context = _make_context(
            dataset,
            120,
            _WEIGHTS,
            withdrawal_policy=ConstantWithdrawalPolicy(_RATE),
        )
        assert not _is_constant_nominal_eligible(context)

    def test_nominal_explicit_matches_reference(self) -> None:
        dataset = _make_dataset(241)
        context = _make_context(
            dataset,
            120,
            _WEIGHTS,
            withdrawal_policy=ConstantWithdrawalPolicy(_RATE),
        )
        numba = _run(_NUMBA, context)
        reference = _run(_REFERENCE, context)
        assert numba.statistics.success == reference.statistics.success
        assert (
            numba.statistics.final_wealth.amount
            == reference.statistics.final_wealth.amount
        )

    def test_part52_gate_rejects_explicit(self) -> None:
        dataset = _make_dataset(121)
        context = _make_context(dataset, 120, _WEIGHTS)
        assert not is_part52_eligible(context)
