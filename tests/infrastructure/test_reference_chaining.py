"""Unit tests for reference horizon chaining helper behaviour."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from cli.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from engine.application.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    SimulationResult,
)
from engine.application.simulation_context import SimulationContext
from engine.domain.model.asset import AssetClass
from engine.domain.model.dataset import Dataset
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.money import Currency, Money
from engine.domain.model.portfolio import AssetHolding, Portfolio
from infrastructure.execution.parallel_executor import _create_default_simulation_executor
from infrastructure.execution.reference_chaining import (
    ChainedReferenceSimulationExecutor,
    _build_derived_result,
    _dataset_is_identity_prefix,
    _reference_chaining_group_key,
)

_WEALTH = Money(Decimal("1000000"), Currency.EUR)


def _make_flat_dataset(months: int, price: Decimal = Decimal("100")) -> Dataset:
    equity = AssetClass(id="equity", name="", description="")
    bond = AssetClass(id="bond", name="", description="")
    snapshots = []
    current = date(2000, 1, 1)
    for _ in range(months):
        snapshots.append(
            MarketSnapshot(
                date=current,
                index_levels={equity: price, bond: price},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=price,
            )
        )
        current = date(current.year + (current.month // 12), current.month % 12 + 1, 1)
    return Dataset(snapshots=tuple(snapshots), frequency="monthly", version="1.0")


def _make_portfolio(initial_wealth: Money) -> Portfolio:
    equity = AssetClass(id="equity", name="", description="")
    bond = AssetClass(id="bond", name="", description="")
    half_units = initial_wealth.amount / Decimal("2")
    return Portfolio(
        holdings=(
            AssetHolding(asset_class=equity, units=half_units),
            AssetHolding(asset_class=bond, units=half_units),
        )
    )


def _make_context(
    dataset: Dataset,
    horizon_months: int,
    withdrawal_rate: Decimal,
    initial_wealth: Money = _WEALTH,
) -> SimulationContext:
    return SimulationContext(
        experiment_name="test",
        cohort="test-cohort",
        start_date=dataset.start_date,
        horizon_months=horizon_months,
        initial_wealth=initial_wealth,
        initial_portfolio=_make_portfolio(initial_wealth),
        dataset=dataset,
        allocation_policy=ConstantAllocationPolicy(Decimal("0.5")),
        withdrawal_policy=FixedRealWithdrawalPolicy(withdrawal_rate=withdrawal_rate),
    )


def _execute_reference(context: SimulationContext) -> SimulationResult:
    executor = _create_default_simulation_executor()
    definition = EngineExperimentDefinition(
        name=context.experiment_name,
        description="test",
        simulation_contexts=(context,),
    )
    return executor.execute(definition).simulation_results[0]


def _assert_results_equal(left: SimulationResult, right: SimulationResult) -> None:
    assert left == right


class TestBuildDerivedResult:
    def test_successful_derived_horizon_matches_independent_reference(self) -> None:
        dataset = _make_flat_dataset(20)
        longest = _make_context(dataset, horizon_months=20, withdrawal_rate=Decimal("0.04"))
        shorter = _make_context(
            dataset.slice(dataset.start_date, 12),
            horizon_months=12,
            withdrawal_rate=Decimal("0.04"),
        )

        longest_result = _execute_reference(longest)
        derived_result = _build_derived_result(longest_result, longest.horizon_months, shorter)
        independent_result = _execute_reference(shorter)

        _assert_results_equal(derived_result, independent_result)
        assert derived_result.statistics.success is True
        assert derived_result.statistics.failure_month is None
        assert derived_result.statistics.months_simulated == 12
        assert derived_result.statistics.final_wealth == independent_result.statistics.final_wealth
        assert len(derived_result.timeline.monthly_results) == 12

    def test_derived_horizon_before_failure_matches_independent_reference(self) -> None:
        dataset = _make_flat_dataset(30)
        longest = _make_context(dataset, horizon_months=30, withdrawal_rate=Decimal("0.5"))

        longest_result = _execute_reference(longest)
        assert longest_result.statistics.success is False
        assert longest_result.statistics.failure_month is not None

        shorter_horizon = longest_result.statistics.failure_month
        assert shorter_horizon is not None and shorter_horizon > 0
        success_prefix = _make_context(
            dataset.slice(dataset.start_date, shorter_horizon),
            horizon_months=shorter_horizon,
            withdrawal_rate=Decimal("0.5"),
        )

        derived_result = _build_derived_result(
            longest_result, longest.horizon_months, success_prefix
        )
        independent_result = _execute_reference(success_prefix)

        _assert_results_equal(derived_result, independent_result)
        assert derived_result.statistics.success is True
        assert derived_result.statistics.failure_month is None
        assert derived_result.statistics.months_simulated == shorter_horizon
        assert derived_result.statistics.final_wealth == independent_result.statistics.final_wealth
        assert len(derived_result.timeline.monthly_results) == shorter_horizon

    def test_failure_at_derived_horizon_boundary_includes_failure_month(self) -> None:
        dataset = _make_flat_dataset(30)
        longest = _make_context(dataset, horizon_months=30, withdrawal_rate=Decimal("0.5"))

        longest_result = _execute_reference(longest)
        assert longest_result.statistics.success is False
        assert longest_result.statistics.failure_month is not None

        boundary_horizon = longest_result.statistics.failure_month + 1
        boundary_context = _make_context(
            dataset.slice(dataset.start_date, boundary_horizon),
            horizon_months=boundary_horizon,
            withdrawal_rate=Decimal("0.5"),
        )

        derived_result = _build_derived_result(
            longest_result, longest.horizon_months, boundary_context
        )
        independent_result = _execute_reference(boundary_context)

        _assert_results_equal(derived_result, independent_result)
        assert derived_result.statistics.success is False
        assert (
            derived_result.statistics.failure_month
            == independent_result.statistics.failure_month
        )
        assert (
            derived_result.statistics.months_simulated
            == independent_result.statistics.months_simulated
        )
        assert derived_result.statistics.final_wealth == independent_result.statistics.final_wealth
        assert len(derived_result.timeline.monthly_results) == (
            independent_result.statistics.months_simulated
        )
        # The reference runner breaks out of the pipeline before the failing
        # month is written, so the timeline ends at failure_month - 1.
        expected_last = derived_result.statistics.failure_month
        assert expected_last is not None
        assert derived_result.timeline.monthly_results[-1].period_index == expected_last - 1

    def test_identical_horizon_returns_longest_result_unchanged(self) -> None:
        dataset = _make_flat_dataset(20)
        longest = _make_context(dataset, horizon_months=20, withdrawal_rate=Decimal("0.04"))
        longest_result = _execute_reference(longest)

        derived_result = _build_derived_result(longest_result, longest.horizon_months, longest)

        assert derived_result is longest_result

    def test_successful_derived_final_wealth_is_prefix_value(self) -> None:
        """Shorter success horizon final wealth equals its prefix month's value."""
        dataset = _make_flat_dataset(20)
        longest = _make_context(dataset, horizon_months=20, withdrawal_rate=Decimal("0.04"))
        shorter = _make_context(
            dataset.slice(dataset.start_date, 8),
            horizon_months=8,
            withdrawal_rate=Decimal("0.04"),
        )

        longest_result = _execute_reference(longest)
        derived_result = _build_derived_result(longest_result, longest.horizon_months, shorter)
        independent_result = _execute_reference(shorter)

        _assert_results_equal(derived_result, independent_result)
        assert derived_result.statistics.success is True
        assert derived_result.statistics.final_wealth == independent_result.statistics.final_wealth
        assert len(derived_result.timeline.monthly_results) == 8

    def test_derived_result_after_failure_matches_failure_statistics(self) -> None:
        """Horizons beyond the failure month reproduce the failure statistics."""
        dataset = _make_flat_dataset(30)
        longest = _make_context(dataset, horizon_months=30, withdrawal_rate=Decimal("0.5"))
        longest_result = _execute_reference(longest)
        assert longest_result.statistics.failure_month is not None

        fm = longest_result.statistics.failure_month
        beyond = _make_context(
            dataset.slice(dataset.start_date, fm + 2),
            horizon_months=fm + 2,
            withdrawal_rate=Decimal("0.5"),
        )
        derived_result = _build_derived_result(longest_result, longest.horizon_months, beyond)
        independent_result = _execute_reference(beyond)

        _assert_results_equal(derived_result, independent_result)
        assert derived_result.statistics.failure_month == fm
        assert derived_result.statistics.months_simulated == fm
        assert derived_result.statistics.success is False

    def test_successful_derived_horizon_equal_to_failure_month(self) -> None:
        """A horizon exactly equal to failure_month succeeds."""
        dataset = _make_flat_dataset(30)
        longest = _make_context(dataset, horizon_months=30, withdrawal_rate=Decimal("0.5"))
        longest_result = _execute_reference(longest)
        assert longest_result.statistics.failure_month is not None

        fm = longest_result.statistics.failure_month
        exact = _make_context(
            dataset.slice(dataset.start_date, fm),
            horizon_months=fm,
            withdrawal_rate=Decimal("0.5"),
        )
        derived_result = _build_derived_result(longest_result, longest.horizon_months, exact)
        independent_result = _execute_reference(exact)

        _assert_results_equal(derived_result, independent_result)
        assert derived_result.statistics.success is True
        assert derived_result.statistics.months_simulated == fm
        assert derived_result.statistics.final_wealth == independent_result.statistics.final_wealth


class TestChainedReferenceSimulationExecutor:
    def test_chained_reference_matches_independent_reference_for_prefix_slices(self) -> None:
        dataset = _make_flat_dataset(30)
        longest = _make_context(dataset, horizon_months=30, withdrawal_rate=Decimal("0.5"))
        shorter = _make_context(
            dataset.slice(dataset.start_date, 24),
            horizon_months=24,
            withdrawal_rate=Decimal("0.5"),
        )

        executor = ChainedReferenceSimulationExecutor()
        definition = EngineExperimentDefinition(
            name="test",
            description="test",
            simulation_contexts=(longest, shorter),
        )
        run = executor.execute(definition)

        reference_long = _execute_reference(longest)
        reference_short = _execute_reference(shorter)

        assert run.simulation_results[0] == reference_long
        assert run.simulation_results[1] == reference_short
        assert executor.chaining_report is not None
        assert executor.chaining_report.derived_results == 1
        assert executor.chaining_report.longest_path_evaluations == 1

    def test_non_prefix_dataset_falls_back_to_independent_reference(self) -> None:
        """A shorter context whose dataset is not an identity prefix of the
        longest is evaluated independently and never derived from it."""
        dataset_a = _make_flat_dataset(30)
        dataset_b = _make_flat_dataset(24, price=Decimal("200"))
        longest = _make_context(
            dataset_a, horizon_months=30, withdrawal_rate=Decimal("0.04")
        )
        shorter = _make_context(
            dataset_b, horizon_months=24, withdrawal_rate=Decimal("0.04")
        )
        assert _reference_chaining_group_key(longest) == _reference_chaining_group_key(shorter)
        assert dataset_a is not dataset_b
        assert not _dataset_is_identity_prefix(shorter, longest)

        executor = ChainedReferenceSimulationExecutor()
        definition = EngineExperimentDefinition(
            name="test",
            description="test",
            simulation_contexts=(longest, shorter),
        )
        run = executor.execute(definition)

        reference_long = _execute_reference(longest)
        reference_short = _execute_reference(shorter)

        assert run.simulation_results[0] == reference_long
        assert run.simulation_results[1] == reference_short
        assert executor.chaining_report is not None
        assert executor.chaining_report.independent_evaluations == 1
        assert executor.chaining_report.derived_results == 0

    def test_mixed_prefix_and_non_prefix_reports_count_derived_and_independent(self) -> None:
        """A family with both eligible and ineligible shorter contexts reports
        both derived and independent evaluations correctly."""
        dataset = _make_flat_dataset(30)
        prefix_short = _make_context(
            dataset.slice(dataset.start_date, 24),
            horizon_months=24,
            withdrawal_rate=Decimal("0.04"),
        )
        longest = _make_context(
            dataset, horizon_months=30, withdrawal_rate=Decimal("0.04")
        )
        non_prefix = _make_context(
            _make_flat_dataset(24, price=Decimal("150")),
            horizon_months=24,
            withdrawal_rate=Decimal("0.04"),
        )

        executor = ChainedReferenceSimulationExecutor()
        definition = EngineExperimentDefinition(
            name="test",
            description="test",
            simulation_contexts=(longest, prefix_short, non_prefix),
        )
        run = executor.execute(definition)

        reference_prefix = _execute_reference(prefix_short)
        reference_non_prefix = _execute_reference(non_prefix)

        assert run.simulation_results[0] == _execute_reference(longest)
        assert run.simulation_results[1] == reference_prefix
        assert run.simulation_results[2] == reference_non_prefix
        assert executor.chaining_report is not None
        assert executor.chaining_report.derived_results == 1
        assert executor.chaining_report.independent_evaluations == 1
        assert executor.chaining_report.longest_path_evaluations == 1
