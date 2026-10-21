"""R5 trajectory deduplication tests for the supported Numba engine.

Proves that final_value_target is treated as an evaluation dimension, not a
simulation dimension: trajectories with different FV targets share a single
grouped simulation path, and the FV check is applied per-target afterwards.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    ExperimentRun,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.numba_executor import NumbaSimulationExecutor
from fbf.core.study.builder import build_initial_portfolio

EQ = AssetClass(id="equity", name="", description="")
BD = AssetClass(id="bond", name="", description="")
INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)


def _make_dataset(start_year: int = 1900, n_months: int = 300) -> Dataset:
    snapshots = []
    pe = pb = Decimal("100")
    d = date(start_year, 1, 1)
    for _ in range(n_months):
        snapshots.append(
            MarketSnapshot(
                date=d,
                index_levels={EQ: pe, BD: pb},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            )
        )
        pe *= Decimal("1.006")
        pb *= Decimal("1.002")
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return Dataset(snapshots=snapshots, frequency="monthly")


def _make_context(
    start_year: int = 1900,
    start_month: int = 1,
    horizon_months: int = 240,
    equity_allocation: Decimal = Decimal("0.6"),
    withdrawal_rate: Decimal = Decimal("0.04"),
    final_value_target: Decimal | None = None,
    dataset: Dataset | None = None,
) -> SimulationContext:
    sd = date(start_year, start_month, 1)
    ds = dataset or _make_dataset(start_year, max(horizon_months, 300))
    portfolio = build_initial_portfolio(INITIAL_WEALTH, ds)
    return SimulationContext(
        experiment_name="test",
        cohort=f"{start_year}-{start_month:02d}",
        start_date=sd,
        horizon_months=horizon_months,
        initial_wealth=INITIAL_WEALTH,
        initial_portfolio=portfolio,
        dataset=ds.slice(sd, horizon_months),
        allocation_policy=ConstantAllocationPolicy(equity_allocation=equity_allocation),
        withdrawal_policy=FixedRealWithdrawalPolicy(
            withdrawal_rate=withdrawal_rate,
        ),
        final_value_target=final_value_target,
    )


def _execute(
    contexts: tuple[SimulationContext, ...],
) -> tuple[NumbaSimulationExecutor, ExperimentRun]:
    executor = NumbaSimulationExecutor()
    definition = EngineExperimentDefinition(
        name="test",
        description="",
        simulation_contexts=contexts,
    )
    return executor, executor.execute(definition)


class TestFvTargetGrouping:
    """final_value_target must not split trajectory groups."""

    def test_different_targets_share_group(self) -> None:
        ds = _make_dataset()
        contexts = (
            _make_context(final_value_target=None, dataset=ds),
            _make_context(final_value_target=Decimal("0"), dataset=ds),
            _make_context(final_value_target=Decimal("100"), dataset=ds),
        )
        executor, run = _execute(contexts)

        assert executor.report is not None
        assert executor.report.groups == 1
        assert len(run.simulation_results) == 3

    def test_trajectory_params_split_groups(self) -> None:
        ds = _make_dataset()
        contexts = (
            _make_context(equity_allocation=Decimal("0.6"), dataset=ds),
            _make_context(equity_allocation=Decimal("0.8"), dataset=ds),
        )
        executor, _ = _execute(contexts)

        assert executor.report is not None
        assert executor.report.groups == 2


class TestFvTargetEvaluation:
    """The FV criterion is applied per context after the shared path."""

    def test_targets_share_path_and_apply_per_context(self) -> None:
        baseline = _execute((_make_context(),))[1].simulation_results[0]
        assert baseline.statistics.success is True
        ratio = (
            baseline.statistics.final_wealth.amount / INITIAL_WEALTH.amount
        )

        targets = (
            Decimal("0"),
            ratio * Decimal("0.5"),
            ratio * Decimal("0.75"),
            ratio * Decimal("1.25"),
            ratio * Decimal("2"),
        )
        ds = _make_dataset()
        contexts = tuple(
            _make_context(final_value_target=target, dataset=ds)
            for target in targets
        )
        executor, run = _execute(contexts)

        assert executor.report is not None
        assert executor.report.groups == 1

        final_wealths = {
            result.statistics.final_wealth.amount
            for result in run.simulation_results
        }
        assert final_wealths == {baseline.statistics.final_wealth.amount}

        expected = (True, True, True, False, False)
        actual = tuple(
            result.statistics.success for result in run.simulation_results
        )
        assert actual == expected

    def test_failure_overrides_positive_target(self) -> None:
        context = _make_context(
            withdrawal_rate=Decimal("2.0"),
            final_value_target=Decimal("0"),
        )
        _, run = _execute((context,))

        result = run.simulation_results[0]
        assert result.statistics.success is False
        assert result.statistics.failure_month is not None
