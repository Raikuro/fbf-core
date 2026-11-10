"""Differential tests for the Numba net-cash-flow workbook kernel."""

from __future__ import annotations

import random
from dataclasses import replace
from decimal import Decimal

import numpy as np
import pytest

from fbf.core.execution.strategies.numba_kernel import (
    _simulate_trajectory_workbook_net_flows,
)

D = Decimal


def _reference(
    growth_factors: list[Decimal],
    initial_value: Decimal,
    withdrawal_monthly: Decimal,
    start_period: int,
    end_period: int,
    external_monthly: Decimal,
) -> tuple[Decimal, bool, int]:
    value = initial_value
    for period, growth in enumerate(growth_factors):
        external = (
            external_monthly if start_period <= period < end_period else D("0")
        )
        net_cash_flow = withdrawal_monthly - external
        if net_cash_flow > value:
            return D("0"), False, period
        value = (value - net_cash_flow) * growth
    return value, True, -1


def test_kernel_contribution_is_invested_before_returns() -> None:
    final_value, success, fail_month, _ = (
        _simulate_trajectory_workbook_net_flows(
            np.array([2.0], dtype=np.float64),
            100.0,
            0.0,
            0,
            1,
            100.0,
            1,
        )
    )

    assert success is True
    assert fail_month == -1
    assert final_value == pytest.approx(400.0)


def test_kernel_exact_depletion_succeeds_and_next_period_fails() -> None:
    success_final, success, _, _ = _simulate_trajectory_workbook_net_flows(
        np.ones(10, dtype=np.float64), 100.0, 10.0, 0, 0, 0.0, 10
    )
    assert success is True
    assert success_final == pytest.approx(0.0)

    _, failure, fail_month, _ = _simulate_trajectory_workbook_net_flows(
        np.ones(11, dtype=np.float64), 100.0, 10.0, 0, 0, 0.0, 11
    )
    assert failure is False
    assert fail_month == 10


def test_kernel_captures_values_with_net_flows() -> None:
    out = np.empty(4, dtype=np.float64)
    final_value, success, _, _ = _simulate_trajectory_workbook_net_flows(
        np.array([1.1, 1.1, 1.1], dtype=np.float64),
        1000.0,
        10.0,
        1,
        2,
        100.0,
        3,
        out,
    )

    assert success is True
    assert final_value == pytest.approx(out[-1])
    assert out[0] == pytest.approx(1000.0)
    assert out[1] == pytest.approx((1000.0 - 10.0) * 1.1)
    assert out[2] == pytest.approx((out[1] + 90.0) * 1.1)
    assert out[3] == pytest.approx((out[2] - 10.0) * 1.1)


def test_kernel_matches_decimal_reference_on_random_inputs() -> None:
    rng = random.Random(42)
    for _ in range(50):
        horizon = rng.randint(1, 60)
        growth = [D(str(rng.uniform(0.95, 1.08))) for _ in range(horizon)]
        initial = D(str(rng.uniform(10_000, 1_000_000)))
        withdrawal = D(str(rng.uniform(0, 20_000)))
        external = D(str(rng.uniform(-20_000, 5_000)))
        start = rng.randint(0, horizon - 1)
        end = rng.randint(start + 1, horizon)
        if rng.random() < 0.25:
            withdrawal = D("50000")

        expected_value, expected_success, expected_fail = _reference(
            growth, initial, withdrawal, start, end, external
        )
        final_value, success, fail_month, _ = (
            _simulate_trajectory_workbook_net_flows(
                np.array([float(g) for g in growth], dtype=np.float64),
                float(initial),
                float(withdrawal),
                start,
                end,
                float(external),
                horizon,
            )
        )

        assert success is expected_success
        assert fail_month == expected_fail
        if expected_success:
            tolerance = max(abs(float(expected_value)), 1.0) * 1e-9
            assert final_value == pytest.approx(float(expected_value), abs=tolerance)
        else:
            assert final_value == 0.0



def test_schedule_is_part_of_the_constant_allocation_group_key() -> None:
    from fbf.core.domain.model.cash_flow import ExternalCashFlowSchedule
    from fbf.core.domain.model.money import Currency, Money
    from fbf.core.execution.strategies.eligibility import _group_key
    from tests.unit.execution.test_timeline_materialization import (
        _context,
        _dataset,
    )

    dataset = _dataset(24, D("0.006"), D("0.002"))
    unscheduled = _context(dataset, 24)
    scheduled = replace(
        unscheduled,
        external_cash_flow_schedule=ExternalCashFlowSchedule(
            start_period=3,
            end_period=8,
            monthly_amount=Money(D("1000"), Currency.EUR),
            horizon_transitions=23,
        ),
    )

    assert _group_key(unscheduled) != _group_key(scheduled)


def test_schedule_is_rejected_for_non_fixed_real_policies() -> None:
    from fbf.core.domain.model.cash_flow import ExternalCashFlowSchedule
    from fbf.core.domain.model.money import Currency, Money
    from fbf.core.domain.policies import ConstantWithdrawalPolicy
    from fbf.core.execution.strategies.numba_executor import (
        is_numba_context_eligible,
    )
    from tests.unit.execution.test_timeline_materialization import (
        _context,
        _dataset,
    )

    dataset = _dataset(24, D("0.006"), D("0.002"))
    context = replace(
        _context(dataset, 24),
        withdrawal_policy=ConstantWithdrawalPolicy(D("0.04")),
        external_cash_flow_schedule=ExternalCashFlowSchedule(
            start_period=3,
            end_period=8,
            monthly_amount=Money(D("1000"), Currency.EUR),
            horizon_transitions=23,
        ),
    )

    assert is_numba_context_eligible(context) is False
