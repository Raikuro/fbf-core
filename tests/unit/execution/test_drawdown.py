"""Unit tests for flow-adjusted drawdown calculations."""

from __future__ import annotations

import inspect
from decimal import Decimal
from typing import Any, cast

import numpy as np
import pytest

from fbf.core.domain.model.money import Currency, Money
from fbf.core.execution.strategies.drawdown import (
    ContributionPositiveFlow,
    FlowTiming,
    compute_drawdown,
    flows_from_timeline_net_cash_flows,
)


def _flows(*amounts: float) -> tuple[ContributionPositiveFlow, ...]:
    return tuple(ContributionPositiveFlow(amount) for amount in amounts)


def test_single_observation_has_zero_drawdown() -> None:
    path = compute_drawdown([100.0], flow_timing=FlowTiming.END)

    assert path.investment_index == (1.0,)
    assert path.drawdowns == (0.0,)
    assert path.max_drawdown == 0.0


def test_no_flow_drawdown_tracks_peak_to_trough() -> None:
    path = compute_drawdown(
        [100.0, 120.0, 90.0, 140.0, 105.0],
        flow_timing=FlowTiming.END,
    )

    assert path.investment_index == pytest.approx((1.0, 1.2, 0.9, 1.4, 1.05))
    assert path.drawdowns == pytest.approx((0.0, 0.0, 0.25, 0.0, 0.25))
    assert path.max_drawdown == pytest.approx(0.25)


def test_fee_remains_in_the_investment_return() -> None:
    path = compute_drawdown([100.0, 99.0], flow_timing=FlowTiming.END)

    assert path.investment_index == pytest.approx((1.0, 0.99))
    assert path.drawdowns == pytest.approx((0.0, 0.01))
    assert path.max_drawdown == pytest.approx(0.01)


def test_end_timed_withdrawal_is_neutralized() -> None:
    path = compute_drawdown(
        [100.0, 90.0, 90.0],
        _flows(0.0, -10.0, 0.0),
        flow_timing=FlowTiming.END,
    )

    assert path.investment_index == pytest.approx((1.0, 1.0, 1.0))
    assert path.drawdowns == pytest.approx((0.0, 0.0, 0.0))
    assert path.max_drawdown == pytest.approx(0.0)


def test_end_timed_withdrawal_does_not_hide_the_loss() -> None:
    path = compute_drawdown(
        [100.0, 70.0],
        _flows(0.0, -10.0),
        flow_timing=FlowTiming.END,
    )

    assert path.investment_index == pytest.approx((1.0, 0.8))
    assert path.drawdowns == pytest.approx((0.0, 0.2))
    assert path.max_drawdown == pytest.approx(0.2)


def test_contribution_does_not_mask_the_drawdown() -> None:
    path = compute_drawdown(
        [100.0, 130.0, 104.0],
        _flows(0.0, 50.0, 0.0),
        flow_timing=FlowTiming.END,
    )

    assert path.investment_index == pytest.approx((1.0, 0.8, 0.64))
    assert path.drawdowns == pytest.approx((0.0, 0.2, 0.36))
    assert path.max_drawdown == pytest.approx(0.36)


@pytest.mark.parametrize(
    ("net_worth", "expected_index", "expected_drawdowns"),
    [
        ([100.0, 90.0], (1.0, 1.0), (0.0, 0.0)),
        ([100.0, 72.0], (1.0, 0.8), (0.0, 0.2)),
    ],
)
def test_beginning_timed_withdrawal_is_neutralized(
    net_worth: list[float],
    expected_index: tuple[float, ...],
    expected_drawdowns: tuple[float, ...],
) -> None:
    path = compute_drawdown(
        net_worth,
        _flows(0.0, -10.0),
        flow_timing=FlowTiming.BEGINNING,
    )

    assert path.investment_index == pytest.approx(expected_index)
    assert path.drawdowns == pytest.approx(expected_drawdowns)
    assert path.max_drawdown == pytest.approx(max(expected_drawdowns))


def test_zero_net_worth_without_flow_is_a_total_loss() -> None:
    path = compute_drawdown([100.0, 0.0], flow_timing=FlowTiming.END)

    assert path.investment_index == pytest.approx((1.0, 0.0))
    assert path.drawdowns == pytest.approx((0.0, 1.0))
    assert path.max_drawdown == pytest.approx(1.0)


def test_non_positive_net_worth_is_a_total_loss() -> None:
    path = compute_drawdown([100.0, 50.0, 0.0, 0.0], flow_timing=FlowTiming.END)

    assert path.investment_index == pytest.approx((1.0, 0.5, 0.0, 0.0))
    assert path.drawdowns == pytest.approx((0.0, 0.5, 1.0, 1.0))
    assert path.max_drawdown == pytest.approx(1.0)


def test_end_timed_full_withdrawal_leaves_zero_drawdown() -> None:
    path = compute_drawdown(
        [100.0, 0.0],
        _flows(0.0, -100.0),
        flow_timing=FlowTiming.END,
    )

    assert path.investment_index == pytest.approx((1.0, 1.0))
    assert path.drawdowns == pytest.approx((0.0, 0.0))
    assert path.max_drawdown == pytest.approx(0.0)


def test_beginning_timed_full_withdrawal_leaves_zero_drawdown() -> None:
    path = compute_drawdown(
        [100.0, 0.0],
        _flows(0.0, -100.0),
        flow_timing=FlowTiming.BEGINNING,
    )

    assert path.investment_index == pytest.approx((1.0, 1.0))
    assert path.drawdowns == pytest.approx((0.0, 0.0))
    assert path.max_drawdown == pytest.approx(0.0)


def test_end_timed_zero_invested_capital_preserves_index() -> None:
    path = compute_drawdown(
        [100.0, 0.0, 0.0],
        _flows(0.0, -100.0, 0.0),
        flow_timing=FlowTiming.END,
    )

    assert path.investment_index == pytest.approx((1.0, 1.0, 1.0))
    assert path.drawdowns == pytest.approx((0.0, 0.0, 0.0))
    assert path.max_drawdown == pytest.approx(0.0)


def test_beginning_zero_invested_capital_with_wealth_raises() -> None:
    with pytest.raises(ValueError, match="invested capital is zero"):
        compute_drawdown(
            [100.0, 90.0],
            _flows(0.0, -100.0),
            flow_timing=FlowTiming.BEGINNING,
        )


def test_negative_invested_capital_raises_for_end_timed_flows() -> None:
    with pytest.raises(ValueError, match="invested capital is negative"):
        compute_drawdown([100.0, -50.0, 60.0], flow_timing=FlowTiming.END)


def test_negative_invested_capital_raises_for_beginning_timed_flows() -> None:
    with pytest.raises(ValueError, match="invested capital is negative"):
        compute_drawdown(
            [100.0, 90.0],
            _flows(0.0, -150.0),
            flow_timing=FlowTiming.BEGINNING,
        )


def test_end_timed_withdrawal_can_leave_negative_raw_net_worth() -> None:
    path = compute_drawdown(
        [100.0, -50.0],
        _flows(0.0, -100.0),
        flow_timing=FlowTiming.END,
    )

    assert path.investment_index == pytest.approx((1.0, 0.5))
    assert path.drawdowns == pytest.approx((0.0, 0.5))
    assert path.max_drawdown == pytest.approx(0.5)


def test_negative_adjusted_wealth_exceeds_one_hundred_percent() -> None:
    path = compute_drawdown([100.0, -50.0], flow_timing=FlowTiming.END)

    assert path.investment_index == pytest.approx((1.0, -0.5))
    assert path.drawdowns == pytest.approx((0.0, 1.5))
    assert path.max_drawdown == pytest.approx(1.5)


def test_negative_growth_factor_is_allowed() -> None:
    path = compute_drawdown(
        [100.0, 10.0],
        _flows(0.0, 50.0),
        flow_timing=FlowTiming.END,
    )

    assert path.investment_index == pytest.approx((1.0, -0.4))
    assert path.drawdowns == pytest.approx((0.0, 1.4))
    assert path.max_drawdown == pytest.approx(1.4)


def test_negative_index_can_recover_toward_zero() -> None:
    path = compute_drawdown(
        [100.0, 10.0, 5.0],
        _flows(0.0, 50.0, 0.0),
        flow_timing=FlowTiming.END,
    )

    assert path.investment_index == pytest.approx((1.0, -0.4, -0.2))
    assert path.drawdowns == pytest.approx((0.0, 1.4, 1.2))
    assert path.max_drawdown == pytest.approx(1.4)


def test_negative_index_can_flip_positive() -> None:
    path = compute_drawdown(
        [100.0, 10.0, 0.0],
        _flows(0.0, 50.0, 110.0),
        flow_timing=FlowTiming.END,
    )

    assert path.investment_index == pytest.approx((1.0, -0.4, 4.4))
    assert path.drawdowns == pytest.approx((0.0, 1.4, 0.0))
    assert path.max_drawdown == pytest.approx(1.4)


def test_zero_adjusted_wealth_absorbs_the_index() -> None:
    path = compute_drawdown(
        [100.0, 10.0, 50.0, 100.0],
        _flows(0.0, 50.0, 50.0, 0.0),
        flow_timing=FlowTiming.END,
    )

    assert path.investment_index == pytest.approx((1.0, -0.4, 0.0, 0.0))
    assert path.drawdowns == pytest.approx((0.0, 1.4, 1.0, 1.0))
    assert path.max_drawdown == pytest.approx(1.4)


def test_withdrawal_during_existing_drawdown_is_neutralized() -> None:
    path = compute_drawdown(
        [100.0, 80.0, 70.0],
        _flows(0.0, 0.0, -10.0),
        flow_timing=FlowTiming.END,
    )

    assert path.investment_index == pytest.approx((1.0, 0.8, 0.8))
    assert path.drawdowns == pytest.approx((0.0, 0.2, 0.2))
    assert path.max_drawdown == pytest.approx(0.2)


def test_contribution_during_existing_drawdown_is_neutralized() -> None:
    path = compute_drawdown(
        [100.0, 80.0, 100.0],
        _flows(0.0, 0.0, 10.0),
        flow_timing=FlowTiming.END,
    )

    assert path.investment_index == pytest.approx((1.0, 0.8, 0.9))
    assert path.drawdowns == pytest.approx((0.0, 0.2, 0.1))
    assert path.max_drawdown == pytest.approx(0.2)


def test_exact_recovery_to_previous_peak_resets_drawdown() -> None:
    path = compute_drawdown([100.0, 80.0, 100.0], flow_timing=FlowTiming.END)

    assert path.investment_index == pytest.approx((1.0, 0.8, 1.0))
    assert path.drawdowns == pytest.approx((0.0, 0.2, 0.0))
    assert path.max_drawdown == pytest.approx(0.2)


def test_timeline_cash_flow_conversion_inverts_the_sign() -> None:
    converted = flows_from_timeline_net_cash_flows(
        (
            Money(Decimal("0"), Currency.EUR),
            Money(Decimal("10"), Currency.EUR),
            Money(Decimal("-5"), Currency.EUR),
            None,
        )
    )

    assert converted == _flows(0.0, -10.0, 5.0, 0.0)

    path = compute_drawdown(
        [100.0, 90.0, 95.0, 95.0],
        converted,
        flow_timing=FlowTiming.END,
    )
    assert path.investment_index == pytest.approx((1.0, 1.0, 1.0, 1.0))
    assert path.max_drawdown == pytest.approx(0.0)


def test_flow_timing_is_required_and_keyword_only() -> None:
    parameter = inspect.signature(compute_drawdown).parameters["flow_timing"]

    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        cast(Any, compute_drawdown)([100.0, 90.0])


def test_invalid_runtime_flow_timing_raises() -> None:
    with pytest.raises(ValueError, match="unsupported flow timing"):
        compute_drawdown(
            [100.0, 90.0],
            flow_timing=cast(FlowTiming, "end"),
        )


def test_invalid_runtime_flow_timing_raises_with_single_observation() -> None:
    with pytest.raises(ValueError, match="unsupported flow timing"):
        compute_drawdown(
            [100.0],
            flow_timing=cast(FlowTiming, "end"),
        )


def test_first_flow_entry_is_ignored() -> None:
    with_initial_flow = compute_drawdown(
        [100.0, 120.0],
        _flows(999.0, 0.0),
        flow_timing=FlowTiming.END,
    )
    without_initial_flow = compute_drawdown(
        [100.0, 120.0],
        flow_timing=FlowTiming.END,
    )

    assert with_initial_flow == without_initial_flow


def test_numpy_net_worth_series_are_accepted() -> None:
    path = compute_drawdown(
        np.array([100.0, 120.0, 90.0], dtype=np.float64),
        flow_timing=FlowTiming.END,
    )

    assert path.investment_index == pytest.approx((1.0, 1.2, 0.9))
    assert path.max_drawdown == pytest.approx(0.25)


@pytest.mark.parametrize(
    "net_worth",
    [
        [],
        [0.0],
        [-1.0],
        [100.0, float("nan")],
        [100.0, float("inf")],
    ],
)
def test_invalid_net_worth_raises(net_worth: list[float]) -> None:
    with pytest.raises(ValueError):
        compute_drawdown(net_worth, flow_timing=FlowTiming.END)


def test_mismatched_flow_length_raises() -> None:
    with pytest.raises(ValueError, match="match"):
        compute_drawdown(
            [100.0, 90.0],
            _flows(0.0),
            flow_timing=FlowTiming.END,
        )


def test_non_finite_flow_raises() -> None:
    with pytest.raises(ValueError, match="finite"):
        compute_drawdown(
            [100.0, 90.0],
            _flows(0.0, float("nan")),
            flow_timing=FlowTiming.END,
        )


def test_non_finite_growth_factor_raises() -> None:
    with pytest.raises(ValueError, match="finite growth factor"):
        compute_drawdown([1e-300, 1e308], flow_timing=FlowTiming.END)


def test_non_finite_investment_index_raises() -> None:
    with pytest.raises(ValueError, match="index is not finite"):
        compute_drawdown(
            [1e-300, 1.0, 8e307],
            _flows(0.0, 0.0, -8e307),
            flow_timing=FlowTiming.END,
        )
