"""Contract tests for ``failure_month`` under the final-value success criterion.

``failure_month`` records the month of an *operational terminal failure* —
portfolio depletion or terminal margin-call liquidation.  A trajectory that
survives to the horizon but misses the final-value target is an
evaluation-criterion failure: it sets ``success=False`` while ``failure_month``
and ``failure_state`` remain ``None``.

These tests pin the contract at two levels:

1. Every final-value-check implementation across execution modes agrees on the
   contract (direct, parametrized over the private helpers).
2. Equivalent FixedReal configurations produce consistent end-to-end results
   through the REFERENCE and FAST execution modes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal

import pytest

from fbf.core.domain.model.money import Currency, Money
from fbf.core.execution.pipeline.executor import SimulationExecutor
from fbf.core.execution.pipeline.simulation import (
    SimulationResult,
    SimulationStatistics,
    SimulationTimeline,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies import (
    fast_path,
    numba_executor,
    part49_numba_executor,
    part52_numba_executor,
    reference,
)
from fbf.core.study.plan import ResearchPlan
from tests.unit.execution.conftest import make_context, make_dataset, make_plan

_FV_CHECK = Callable[[SimulationResult, SimulationContext], SimulationResult]

_FV_CHECKS = [
    pytest.param(fast_path._apply_fv_check, id="fast_path"),
    pytest.param(reference._apply_fv_check, id="reference"),
    pytest.param(numba_executor._apply_fv_check, id="numba"),
    pytest.param(part52_numba_executor._apply_fv_check, id="part52_numba"),
    pytest.param(part49_numba_executor._apply_part49_fv_check, id="part49_numba"),
]

_INITIAL_WEALTH = Decimal("1000")
_HORIZON = 12


def _context(
    final_value_target: Decimal | None,
    initial_wealth: Decimal = _INITIAL_WEALTH,
) -> SimulationContext:
    base = make_context(make_dataset(_HORIZON + 1), _HORIZON)
    return replace(
        base,
        initial_wealth=Money(initial_wealth, Currency.EUR),
        horizon_months=_HORIZON,
        final_value_target=final_value_target,
    )


def _result(
    *,
    success: bool,
    final_wealth: Decimal,
    failure_month: int | None = None,
    failure_state: str | None = None,
) -> SimulationResult:
    return SimulationResult(
        timeline=SimulationTimeline(monthly_results=()),
        statistics=SimulationStatistics(
            final_wealth=Money(final_wealth, Currency.EUR),
            max_drawdown=0.0,
            success=success,
            failure_month=failure_month,
            failure_state=failure_state,
            months_simulated=_HORIZON,
        ),
    )


class TestFvCheckContract:
    """Every mode's FV check implements the same failure_month contract."""

    @pytest.mark.parametrize("fv_check", _FV_CHECKS)
    def test_target_miss_flips_success_only(self, fv_check: _FV_CHECK) -> None:
        ctx = _context(Decimal("2"))
        result = _result(success=True, final_wealth=Decimal("1500"))
        out = fv_check(result, ctx)
        assert out.statistics.success is False
        assert out.statistics.failure_month is None
        assert out.statistics.failure_state is None

    @pytest.mark.parametrize("fv_check", _FV_CHECKS)
    def test_target_met_is_unchanged(self, fv_check: _FV_CHECK) -> None:
        ctx = _context(Decimal("2"))
        result = _result(success=True, final_wealth=Decimal("2500"))
        assert fv_check(result, ctx) is result

    @pytest.mark.parametrize("fv_check", _FV_CHECKS)
    def test_no_target_is_unchanged(self, fv_check: _FV_CHECK) -> None:
        result = _result(success=True, final_wealth=Decimal("1"))
        assert fv_check(result, _context(None)) is result

    @pytest.mark.parametrize("fv_check", _FV_CHECKS)
    def test_depletion_month_is_preserved(self, fv_check: _FV_CHECK) -> None:
        ctx = _context(Decimal("0.5"))
        result = _result(
            success=False,
            final_wealth=Decimal("0"),
            failure_month=5,
            failure_state="depleted",
        )
        out = fv_check(result, ctx)
        assert out.statistics.success is False
        assert out.statistics.failure_month == 5
        assert out.statistics.failure_state == "depleted"

    @pytest.mark.parametrize("fv_check", _FV_CHECKS)
    def test_margin_call_month_is_preserved(self, fv_check: _FV_CHECK) -> None:
        ctx = _context(Decimal("0.5"))
        result = _result(
            success=False,
            final_wealth=Decimal("100"),
            failure_month=40,
            failure_state="margin_call_terminal",
        )
        out = fv_check(result, ctx)
        assert out.statistics.failure_month == 40
        assert out.statistics.failure_state == "margin_call_terminal"


def _plan_with_target(target: Decimal) -> ResearchPlan:
    base = make_plan(horizons=[120], weights=[0.5], rates=[0.04])
    units = tuple(replace(unit, final_value_target=target) for unit in base.units)
    return ResearchPlan(experiment_definition=base.experiment_definition, units=units)


def _execute_fixed_real(target: Decimal, fast: bool) -> SimulationStatistics:
    pytest.importorskip("numba")
    from fbf.core.execution.strategies.parallel_executor import sequential_execute

    executor: SimulationExecutor
    if fast:
        from fbf.core.execution.strategies.numba_executor import (
            NumbaSimulationExecutor,
        )

        executor = NumbaSimulationExecutor()
    else:
        from fbf.core.execution.strategies.fast_path import FastPathSimulationExecutor

        executor = FastPathSimulationExecutor()

    run = sequential_execute(
        _plan_with_target(target),
        simulation_executor=executor,
        summary_only=True,
    )
    assert len(run.results) == 1
    return run.results[0].statistics


class TestFixedRealCrossModeConsistency:
    """Equivalent FixedReal configurations agree across REFERENCE and FAST."""

    def test_fv_miss_is_consistent(self) -> None:
        reference_stats = _execute_fixed_real(Decimal("100"), fast=False)
        fast_stats = _execute_fixed_real(Decimal("100"), fast=True)
        for stats in (reference_stats, fast_stats):
            assert stats.success is False
            assert stats.failure_month is None
            assert stats.failure_state is None

    def test_fv_target_met_is_consistent(self) -> None:
        reference_stats = _execute_fixed_real(Decimal("0.5"), fast=False)
        fast_stats = _execute_fixed_real(Decimal("0.5"), fast=True)
        for stats in (reference_stats, fast_stats):
            assert stats.success is True
            assert stats.failure_month is None
            assert stats.failure_state is None
