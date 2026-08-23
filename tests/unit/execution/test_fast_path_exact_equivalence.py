"""Exact-equivalence invariants between the reference engine and the fast paths.

Reference-vs-fast equivalence is an exactness contract, not a tolerance:

- the ``decimal`` closed form replicates the reference engine's per-month
  per-asset ``Decimal`` arithmetic (withdrawal ratio + residual rebalance), so
  success, failure month, months simulated and final wealth — including the
  sub-1e-22 EUR failure residual — must match **to the last digit**;
- the ``float`` closed form is a double-precision algebraic recurrence: success,
  failure month and months simulated must match exactly, and final wealth is
  bounded (measured <= 9e-6 EUR on synthetic grids);
- horizon derivation must be bit-identical to evaluating each context on its own.

The only known, documented divergence is ``float`` outcome flips at crafted
exact-equality depletion boundaries (``V_m == C`` for a simulated month), which
are measure-zero on real data and are pinned here as regression guards.
"""

from __future__ import annotations

import random
from datetime import date
from decimal import Decimal
from typing import cast

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from fbf.core.execution.pipeline.executor import SimulationExecutor
from fbf.core.execution.pipeline.simulation import SimulationResult
from fbf.core.execution.strategies.fast_path import (
    FastPathSimulationExecutor,
    Precision,
)
from fbf.core.execution.strategies.parallel_executor import sequential_execute
from fbf.core.execution.strategies.reference import ReferenceSimulationExecutor
from fbf.core.study.builder import build_initial_portfolio
from fbf.core.study.internal.cohort.generator import CohortGenerator
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.axis import ParameterAxis
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.internal.parameter.engine import ParameterSweepEngine
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan, materialize_research_plan

EQ = AssetClass(id="equity", name="", description="")
BD = AssetClass(id="bond", name="", description="")

_WEALTH = Money(Decimal("1000000"), Currency.EUR)

# Measured float final-wealth deviation vs the reference across synthetic grids
# is <= 9e-6 EUR; 1e-4 is the documented bound with headroom.
FLOAT_WEALTH_TOLERANCE = Decimal("1e-4")


def _dataset(n_months: int, seed: int = 7, flat: bool = False) -> Dataset:
    rng = random.Random(seed)
    pe = pb = Decimal("100")
    snapshots: list[MarketSnapshot] = []
    d = date(1980, 1, 1)
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
        if not flat:
            pe *= Decimal(str(1 + rng.gauss(0.006, 0.045)))
            pb *= Decimal(str(1 + rng.gauss(0.002, 0.01)))
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return Dataset(snapshots=snapshots, frequency="monthly", version="1.0")


def build_grid_plan(
    dataset: Dataset,
    horizons: tuple[int, ...],
    weights: tuple[float, ...] = (0.5,),
    rates: tuple[float, ...] = (0.04,),
) -> ResearchPlan:
    """Build a synthetic grid plan over *horizons* x *weights* x *rates*."""
    cohorts = CohortGenerator.generate_rolling_monthly(dataset, max(horizons) * 12)
    configs = ParameterSweepEngine.cartesian_product(
        [
            ParameterAxis(name="horizon_years", values=tuple(horizons)),
            ParameterAxis(name="equity_allocation", values=tuple(weights)),
            ParameterAxis(name="withdrawal_rate", values=tuple(rates)),
        ]
    )
    alloc = ConstantAllocationPolicy(Decimal("0.5"))
    withdraw = FixedRealWithdrawalPolicy(Decimal("0.04"))
    exp_def = ExperimentDefinition(
        name="equiv",
        description="exact-equivalence grid",
        dataset=dataset,
        horizon_months=max(horizons) * 12,
        initial_wealth=_WEALTH,
        cohorts=cohorts,
        allocation_policies=(alloc,),
        withdrawal_policies=(withdraw,),
    )
    _alloc_by_weight: dict[Decimal, ConstantAllocationPolicy] = {}
    _withdraw_by_rate: dict[Decimal, FixedRealWithdrawalPolicy] = {}

    def _resolve_policies(
        config: ParameterConfiguration,
    ) -> tuple[ConstantAllocationPolicy, FixedRealWithdrawalPolicy]:
        weight = Decimal(str(config.get("equity_allocation")))
        resolved_alloc = _alloc_by_weight.get(weight)
        if resolved_alloc is None:
            resolved_alloc = ConstantAllocationPolicy(equity_allocation=weight)
            _alloc_by_weight[weight] = resolved_alloc
        rate = Decimal(str(config.get("withdrawal_rate")))
        resolved_withd = _withdraw_by_rate.get(rate)
        if resolved_withd is None:
            resolved_withd = FixedRealWithdrawalPolicy(withdrawal_rate=rate)
            _withdraw_by_rate[rate] = resolved_withd
        return resolved_alloc, resolved_withd

    return materialize_research_plan(
        experiment_def=exp_def,
        canonical_trajectory=dataset,
        cohorts=cohorts,
        param_configs=configs,
        initial_portfolio=build_initial_portfolio(_WEALTH),
        horizon_resolver=lambda c: int(c.get("horizon_years")) * 12,
        policy_resolver=_resolve_policies,
    )


def _execute(
    plan: ResearchPlan, executor: SimulationExecutor | None = None
) -> tuple[SimulationResult, ...]:
    return sequential_execute(
        plan, summary_only=True, simulation_executor=executor
    ).results


def _assert_exact(
    a: SimulationResult,
    b: SimulationResult,
    unit: PlannedSimulationUnit,
    field: str,
) -> None:
    a_val = getattr(a.statistics, field)
    b_val = getattr(b.statistics, field)
    assert a_val == b_val, (
        f"{field}: reference {a_val!r} vs fast {b_val!r} "
        f"(unit h={unit.horizon_months} "
        f"config={unit.parameter_config})"
    )


class TestDecimalPathBitExact:
    def test_realistic_grid_matches_to_the_last_digit(self) -> None:
        """Decimal fast path is bit-exact with the reference on a realistic grid."""
        dataset = _dataset(241)
        plan = build_grid_plan(
            dataset,
            horizons=(2, 3),
            weights=(0.0, 0.25, 0.75, 1.0),
            rates=(0.04, 0.1),
        )
        reference = _execute(plan)
        decimal = _execute(plan, FastPathSimulationExecutor(precision="decimal"))

        for unit, ref, got in zip(plan.units, reference, decimal, strict=True):
            _assert_exact(ref, got, unit, "success")
            _assert_exact(ref, got, unit, "failure_month")
            _assert_exact(ref, got, unit, "months_simulated")
            _assert_exact(ref, got, unit, "final_wealth")

    def test_exact_equality_boundaries_match_to_the_last_digit(self) -> None:
        """Decimal stays bit-exact where V_m == C (the old recurrence diverged).

        With flat returns the portfolio value declines linearly, so for
        ``withdrawal_rate = 12/H`` the pre-withdrawal value equals the monthly
        withdrawal ``C`` at a simulated month.  The algebraic closed-form
        recurrence mis-rounds this equality; the decimal replica reproduces the
        reference's unit-based arithmetic exactly.
        """
        for horizons, rates in (((2,), (0.5,)), ((5,), (0.4,))):
            dataset = _dataset(max(horizons) * 12 + 1, flat=True)
            plan = build_grid_plan(dataset, horizons, rates=rates)
            reference = _execute(plan)
            decimal = _execute(plan, FastPathSimulationExecutor(precision="decimal"))
            for unit, ref, got in zip(plan.units, reference, decimal, strict=True):
                _assert_exact(ref, got, unit, "success")
                _assert_exact(ref, got, unit, "failure_month")
                _assert_exact(ref, got, unit, "months_simulated")
                _assert_exact(ref, got, unit, "final_wealth")


class TestFloatPath:
    def test_outcomes_exact_and_wealth_bounded(self) -> None:
        """Float matches outcomes exactly; final wealth within a small bound."""
        dataset = _dataset(241)
        plan = build_grid_plan(
            dataset,
            horizons=(2, 3),
            weights=(0.0, 0.25, 0.75, 1.0),
            rates=(0.04, 0.1),
        )
        reference = _execute(plan)
        float_path = _execute(plan, FastPathSimulationExecutor(precision="float"))

        for unit, ref, got in zip(plan.units, reference, float_path, strict=True):
            _assert_exact(ref, got, unit, "success")
            _assert_exact(ref, got, unit, "failure_month")
            _assert_exact(ref, got, unit, "months_simulated")
            diff = abs(ref.statistics.final_wealth.amount - got.statistics.final_wealth.amount)
            assert diff <= FLOAT_WEALTH_TOLERANCE, (
                f"final_wealth diff {diff} > {FLOAT_WEALTH_TOLERANCE} "
                f"(unit h={unit.horizon_months} config={unit.parameter_config})"
            )

    def test_wealth_bound_across_parameter_sweep(self) -> None:
        """Float wealth deviation stays bounded across a wide parameter sweep."""
        dataset = _dataset(300)
        plan = build_grid_plan(
            dataset,
            horizons=(1, 2, 3, 5),
            weights=(0.0, 0.25, 0.5, 0.75, 1.0),
            rates=(0.03, 0.04, 0.05, 0.08),
        )
        reference = _execute(plan)
        float_path = _execute(plan, FastPathSimulationExecutor(precision="float"))
        max_diff = Decimal("0")

        for unit, ref, got in zip(plan.units, reference, float_path, strict=True):
            _assert_exact(ref, got, unit, "success")
            _assert_exact(ref, got, unit, "failure_month")
            _assert_exact(ref, got, unit, "months_simulated")
            diff = abs(ref.statistics.final_wealth.amount - got.statistics.final_wealth.amount)
            if diff > max_diff:
                max_diff = diff

        assert max_diff <= FLOAT_WEALTH_TOLERANCE, (
            f"max final_wealth diff {max_diff} > {FLOAT_WEALTH_TOLERANCE}"
        )

    def test_non_boundary_flat_control_matches_outcomes(self) -> None:
        """On flat data without an exact-equality boundary, float matches exactly."""
        plan = build_grid_plan(_dataset(25, flat=True), (2,), rates=(0.3,))
        reference = _execute(plan)
        float_path = _execute(plan, FastPathSimulationExecutor(precision="float"))
        for unit, ref, got in zip(plan.units, reference, float_path, strict=True):
            _assert_exact(ref, got, unit, "success")
            _assert_exact(ref, got, unit, "failure_month")
            _assert_exact(ref, got, unit, "months_simulated")

    def test_single_month_context(self) -> None:
        """Float handles single-month horizon correctly."""
        dataset = _dataset(25)
        plan = build_grid_plan(dataset, (1,), rates=(0.04,))
        reference = _execute(plan)
        float_path = _execute(plan, FastPathSimulationExecutor(precision="float"))
        for unit, ref, got in zip(plan.units, reference, float_path, strict=True):
            _assert_exact(ref, got, unit, "success")
            _assert_exact(ref, got, unit, "failure_month")
            _assert_exact(ref, got, unit, "months_simulated")

    def test_long_horizon_context(self) -> None:
        """Float handles long horizon (600 months) correctly."""
        dataset = _dataset(610)
        plan = build_grid_plan(dataset, (5,), rates=(0.04,))
        reference = _execute(plan)
        float_path = _execute(plan, FastPathSimulationExecutor(precision="float"))
        for unit, ref, got in zip(plan.units, reference, float_path, strict=True):
            _assert_exact(ref, got, unit, "success")
            _assert_exact(ref, got, unit, "failure_month")
            _assert_exact(ref, got, unit, "months_simulated")
            diff = abs(ref.statistics.final_wealth.amount - got.statistics.final_wealth.amount)
            assert diff <= FLOAT_WEALTH_TOLERANCE

    def test_exact_equality_boundary_flip_is_pinned(self) -> None:
        """Float may flip outcomes at crafted V_m == C boundaries.

        ``V_m == C`` at a simulated month is measure-zero on real data (it
        requires an exact integer-coincidence of withdrawal rate and horizon),
        but it is a real float-vs-reference divergence.  Decimal stays exact
        there (see ``TestDecimalPathBitExact``); the float flip is pinned below
        as a regression guard so any change to the recurrence arithmetic is
        caught.
        """
        plan = build_grid_plan(_dataset(25, flat=True), (2,), rates=(0.5,))
        reference = _execute(plan)
        float_path = _execute(plan, FastPathSimulationExecutor(precision="float"))
        assert all(ref.statistics.success for ref in reference)  # reference: all success
        assert all(not got.statistics.success for got in float_path)  # float: all fail at 23
        for got in float_path:
            assert got.statistics.failure_month == 23
            # F3: on depletion the float path reports exactly zero residual wealth
            # (the reference leaves a sub-1e-22 EUR rounding residual); the
            # decimal path reproduces the exact residual (bit-exact tests above).
            assert got.statistics.final_wealth.amount == Decimal("0")


class TestDerivationBitExact:
    @pytest.mark.parametrize("precision", ["float", "decimal"])
    def test_derived_equals_direct_closed_form(self, precision: str) -> None:
        """Derived derivation is bit-identical to per-context closed-form evaluation."""
        dataset = _dataset(241)
        plan = build_grid_plan(
            dataset,
            horizons=(2, 3),
            weights=(0.0, 0.5, 1.0),
            rates=(0.04, 0.08),
        )
        prec = cast(Precision, precision)
        direct = _execute(plan, FastPathSimulationExecutor(precision=prec))
        derived = _execute(plan, FastPathSimulationExecutor(precision=prec))
        for unit, d, ch in zip(plan.units, direct, derived, strict=True):
            _assert_exact(d, ch, unit, "success")
            _assert_exact(d, ch, unit, "failure_month")
            _assert_exact(d, ch, unit, "months_simulated")
            _assert_exact(d, ch, unit, "final_wealth")


class TestReferenceDerivationBitExact:
    def test_reference_matches_reference_engine(self) -> None:
        """Reference execution reproduces reference engine execution exactly."""
        dataset = _dataset(241)
        plan = build_grid_plan(
            dataset,
            horizons=(2, 3),
            weights=(0.0, 0.5, 1.0),
            rates=(0.04, 0.08),
        )
        reference = _execute(plan)
        ref_exec = _execute(plan, ReferenceSimulationExecutor())

        for unit, ref, got in zip(plan.units, reference, ref_exec, strict=True):
            _assert_exact(ref, got, unit, "success")
            _assert_exact(ref, got, unit, "failure_month")
            _assert_exact(ref, got, unit, "months_simulated")
            _assert_exact(ref, got, unit, "final_wealth")

    def test_reference_preserves_failure_month_boundary(self) -> None:
        """Derived shorter horizons preserve failure month boundaries exactly."""
        dataset = _dataset(40, flat=True)
        plan = build_grid_plan(
            dataset,
            horizons=(2, 3),
            weights=(1.0,),
            rates=(0.5,),
        )
        reference = _execute(plan)
        ref_exec = _execute(plan, ReferenceSimulationExecutor())

        assert any(
            ref.statistics.failure_month is not None
            and ref.statistics.months_simulated == ref.statistics.failure_month
            for ref in reference
        )

        for unit, ref, got in zip(plan.units, reference, ref_exec, strict=True):
            _assert_exact(ref, got, unit, "success")
            _assert_exact(ref, got, unit, "failure_month")
            _assert_exact(ref, got, unit, "months_simulated")
            _assert_exact(ref, got, unit, "final_wealth")

    def test_representative_multi_horizon_grid_matches_exactly(self) -> None:
        """A representative multi-horizon x weight x rate grid is bit-exact.

        Exercises three horizons, several allocation weights and multiple
        withdrawal rates so every derivation branch (success, failure cut,
        boundary) appears in the grid.
        """
        dataset = _dataset(241)
        plan = build_grid_plan(
            dataset,
            horizons=(1, 2, 3),
            weights=(0.0, 0.25, 0.5, 0.75, 1.0),
            rates=(0.04, 0.1, 0.5),
        )
        reference = _execute(plan)
        ref_exec = _execute(plan, ReferenceSimulationExecutor())

        assert len(plan.units) > 500
        for unit, ref, got in zip(plan.units, reference, ref_exec, strict=True):
            _assert_exact(ref, got, unit, "success")
            _assert_exact(ref, got, unit, "failure_month")
            _assert_exact(ref, got, unit, "months_simulated")
            _assert_exact(ref, got, unit, "final_wealth")

    def test_expected_report_matches_live_executor_report(self) -> None:
        """The plan-level oracle equals the executor's live report."""
        from fbf.core.execution.strategies.reference import (
            expected_reference_report,
        )

        dataset = _dataset(241)
        plan = build_grid_plan(
            dataset,
            horizons=(2, 3),
            weights=(1.0,),
            rates=(0.04,),
        )
        expected = expected_reference_report(plan)

        executor = ReferenceSimulationExecutor()
        _execute(plan, executor)
        live = executor.report
        assert live is not None
        assert live == expected

        n_cohorts = len({u.cohort.start_date for u in plan.units})
        assert expected.groups == n_cohorts
        assert expected.longest_path_evaluations == n_cohorts
        assert expected.derived_results == n_cohorts
        assert expected.independent_evaluations == 0
        longest = max(u.horizon_months or 0 for u in plan.units)
        assert expected.month_work == n_cohorts * longest

    def test_parallel_reference_matches_sequential(self) -> None:
        """Parallel execution stays bit-exact and worker-batched reference works.

        The reference executor advertises ``processes_whole_definition`` so
        ``parallel_execute`` hands whole batches through hybrid, keeping horizon derivation
        effective while results remain identical to sequential execution.
        """
        from fbf.core.execution.strategies.parallel_executor import parallel_execute

        dataset = _dataset(241)
        plan = build_grid_plan(
            dataset,
            horizons=(2, 3),
            weights=(0.0, 0.5, 1.0),
            rates=(0.04, 0.08),
        )
        sequential = _execute(plan, ReferenceSimulationExecutor())
        parallel = parallel_execute(
            plan,
            max_workers=2,
            simulation_executor=ReferenceSimulationExecutor(),
            summary_only=True,
        ).results

        assert len(parallel) == len(plan.units)
        for unit, seq, par in zip(plan.units, sequential, parallel, strict=True):
            _assert_exact(seq, par, unit, "success")
            _assert_exact(seq, par, unit, "failure_month")
            _assert_exact(seq, par, unit, "months_simulated")
            _assert_exact(seq, par, unit, "final_wealth")
