"""R5 trajectory deduplication tests.

Proves that final_value_target is treated as an evaluation dimension, not a
simulation dimension: trajectories with different FV targets share a single
simulation path, and the FV check is applied per-target after evaluation.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.reference import (
    ReferenceSimulationExecutor,
    _evaluate_fv_target,
    _reference_group_key,
)
from fbf.core.study.builder import build_initial_portfolio

EQ = AssetClass(id="equity", name="", description="")
BD = AssetClass(id="bond", name="", description="")


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
    return Dataset(snapshots=snapshots, frequency="monthly", version="1.0")


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
    portfolio = build_initial_portfolio(Money(Decimal("1000000"), Currency.EUR))
    return SimulationContext(
        experiment_name="test",
        cohort=f"{start_year}-{start_month:02d}",
        start_date=sd,
        horizon_months=horizon_months,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        initial_portfolio=portfolio,
        dataset=ds.slice(sd, horizon_months),
        allocation_policy=ConstantAllocationPolicy(equity_allocation=equity_allocation),
        withdrawal_policy=FixedRealWithdrawalPolicy(
            withdrawal_rate=withdrawal_rate,
        ),
        final_value_target=final_value_target,
    )


class TestFvTargetEvaluationDimension:
    """final_value_target is an evaluation dimension, not a trajectory dimension."""

    def test_group_key_excludes_fv_target(self) -> None:
        ctx1 = _make_context(final_value_target=Decimal("0"))
        ctx2 = _make_context(final_value_target=Decimal("100"))
        assert _reference_group_key(ctx1) == _reference_group_key(ctx2)

    def test_group_key_includes_trajectory_params(self) -> None:
        ctx1 = _make_context(equity_allocation=Decimal("0.6"))
        ctx2 = _make_context(equity_allocation=Decimal("0.8"))
        assert _reference_group_key(ctx1) != _reference_group_key(ctx2)

    def test_different_targets_same_trajectory_share_group(self) -> None:
        ctx_no_target = _make_context(final_value_target=None)
        ctx_fv0 = _make_context(final_value_target=Decimal("0"))
        ctx_fv100 = _make_context(final_value_target=Decimal("100"))
        key_no = _reference_group_key(ctx_no_target)
        key_fv0 = _reference_group_key(ctx_fv0)
        key_fv100 = _reference_group_key(ctx_fv100)
        assert key_no == key_fv0 == key_fv100


class TestEvaluateFvTarget:
    """_evaluate_fv_target correctly applies the final-value criterion."""

    W1M = Money(Decimal("1000000"), Currency.EUR)

    def test_no_target_survival_only(self) -> None:
        fw = Money(Decimal("500000"), Currency.EUR)
        assert _evaluate_fv_target(True, fw, self.W1M, None) is True

    def test_no_target_failure(self) -> None:
        fw = Money(Decimal("0"), Currency.EUR)
        assert _evaluate_fv_target(False, fw, self.W1M, None) is False

    def test_positive_target_above(self) -> None:
        fw = Money(Decimal("1500000"), Currency.EUR)
        assert _evaluate_fv_target(True, fw, self.W1M, Decimal("1.0")) is True

    def test_positive_target_below(self) -> None:
        fw = Money(Decimal("800000"), Currency.EUR)
        assert _evaluate_fv_target(True, fw, self.W1M, Decimal("1.0")) is False

    def test_target_zero_survived_positive_wealth(self) -> None:
        fw = Money(Decimal("100000"), Currency.EUR)
        assert _evaluate_fv_target(True, fw, self.W1M, Decimal("0")) is True

    def test_target_zero_survived_zero_wealth(self) -> None:
        fw = Money(Decimal("0"), Currency.EUR)
        assert _evaluate_fv_target(True, fw, self.W1M, Decimal("0")) is True

    def test_failure_overrides_positive_target(self) -> None:
        fw = Money(Decimal("999999"), Currency.EUR)
        assert _evaluate_fv_target(False, fw, self.W1M, Decimal("0")) is False


class TestReferenceExecutorDeduplication:
    """ReferenceSimulationExecutor evaluates trajectory once per unique group."""

    def test_single_trajectory_with_multiple_targets(self) -> None:
        ds = _make_dataset()
        ctx_fv0 = _make_context(final_value_target=Decimal("0"), dataset=ds)
        ctx_fv100 = _make_context(final_value_target=Decimal("100"), dataset=ds)

        # Build a real SimulationResult with 1.5M final wealth
        from fbf.core.execution.pipeline.simulation import (
            ExperimentDefinition as EngineExperimentDefinition,
            SimulationResult,
            SimulationStatistics,
            SimulationTimeline,
        )

        timeline = SimulationTimeline(monthly_results=())
        stats_ok = SimulationStatistics(
            final_wealth=Money(Decimal("1500000"), Currency.EUR),
            max_drawdown=0.2,
            success=True,
            failure_month=None,
            months_simulated=240,
            execution_time_seconds=0.0,
        )
        result = SimulationResult(timeline=timeline, statistics=stats_ok)

        executor = ReferenceSimulationExecutor()
        with patch.object(executor, "_evaluate_reference", return_value=result) as mock_eval:
            definition = EngineExperimentDefinition(
                name="test",
                description="",
                simulation_contexts=(ctx_fv0, ctx_fv100),
            )
            run = executor.execute(definition)

            # Only 1 trajectory evaluation despite 2 targets
            assert mock_eval.call_count == 1
            assert len(run.simulation_results) == 2

    def test_targets_produce_different_success_rates(self) -> None:
        ds = _make_dataset()
        ctx_fv0 = _make_context(final_value_target=Decimal("0"), dataset=ds)
        ctx_fv100 = _make_context(final_value_target=Decimal("100"), dataset=ds)

        from fbf.core.execution.pipeline.simulation import (
            ExperimentDefinition as EngineExperimentDefinition,
            SimulationResult,
            SimulationStatistics,
            SimulationTimeline,
        )

        timeline = SimulationTimeline(monthly_results=())
        # 500K final wealth — survives FV=0 but fails FV=100
        stats = SimulationStatistics(
            final_wealth=Money(Decimal("500000"), Currency.EUR),
            max_drawdown=0.2,
            success=True,
            failure_month=None,
            months_simulated=240,
            execution_time_seconds=0.0,
        )
        result = SimulationResult(timeline=timeline, statistics=stats)

        executor = ReferenceSimulationExecutor()
        with patch.object(executor, "_evaluate_reference", return_value=result):
            definition = EngineExperimentDefinition(
                name="test",
                description="",
                simulation_contexts=(ctx_fv0, ctx_fv100),
            )
            run = executor.execute(definition)

            # FV=0: survived (500K >= 0), FV=100: failed (500K < 100M)
            assert run.simulation_results[0].statistics.success is True
            assert run.simulation_results[1].statistics.success is False

    def test_five_targets_correct_monotone_classification(self) -> None:
        """Verify correct per-target pass/fail with 5 targets.

        Target semantics: final_wealth >= target * initial_wealth.
        With initial_wealth = 1M and final_wealth = 63M (ratio 63x):
          FV=0   → success (63M >= 0)
          FV=25  → success (63M >= 25M)
          FV=50  → success (63M >= 50M)
          FV=75  → failure (63M < 75M)
          FV=100 → failure (63M < 100M)
        """
        ds = _make_dataset()
        targets = [Decimal("0"), Decimal("25"), Decimal("50"), Decimal("75"), Decimal("100")]
        contexts = [_make_context(final_value_target=t, dataset=ds) for t in targets]

        from fbf.core.execution.pipeline.simulation import (
            ExperimentDefinition as EngineExperimentDefinition,
            SimulationResult,
            SimulationStatistics,
            SimulationTimeline,
        )

        timeline = SimulationTimeline(monthly_results=())
        # 63M final wealth → ratio = 63x initial_wealth
        stats = SimulationStatistics(
            final_wealth=Money(Decimal("63000000"), Currency.EUR),
            max_drawdown=0.15,
            success=True,
            failure_month=None,
            months_simulated=240,
            execution_time_seconds=0.0,
        )
        result = SimulationResult(timeline=timeline, statistics=stats)

        executor = ReferenceSimulationExecutor()
        with patch.object(executor, "_evaluate_reference", return_value=result) as mock_eval:
            definition = EngineExperimentDefinition(
                name="test",
                description="",
                simulation_contexts=tuple(contexts),
            )
            run = executor.execute(definition)

            # Only 1 trajectory evaluation for 5 targets
            assert mock_eval.call_count == 1
            assert len(run.simulation_results) == 5

            expected = [True, True, True, False, False]
            for i, (target, exp) in enumerate(zip(targets, expected, strict=True)):
                actual = run.simulation_results[i].statistics.success
                assert actual == exp, (
                    f"FV={target}: expected {exp}, got {actual}"
                )

            fw_values = [
                r.statistics.final_wealth.amount for r in run.simulation_results
            ]
            assert len(set(fw_values)) == 1, "All targets must share same final_wealth"
