"""Unit tests for the optional drawdown execution adapter."""

from __future__ import annotations

from decimal import Decimal

import numpy as np
import pytest

from fbf.core.execution.strategies.drawdown import (
    ContributionPositiveFlow,
    FlowTiming,
)
from fbf.core.execution.strategies.drawdown_adapter import (
    compute_optional_drawdown,
    withdrawals_as_contribution_flows,
)


def test_no_observations_are_unavailable() -> None:
    result = compute_optional_drawdown([], flow_timing=FlowTiming.END)

    assert result.drawdowns == ()
    assert result.max_drawdown is None


def test_single_observation_has_no_measurable_drawdown() -> None:
    result = compute_optional_drawdown([100.0], flow_timing=FlowTiming.END)

    assert result.drawdowns == (None,)
    assert result.max_drawdown is None


def test_first_drawdown_is_none_and_later_values_are_measured() -> None:
    result = compute_optional_drawdown(
        [100.0, 120.0, 90.0],
        flow_timing=FlowTiming.END,
    )

    assert result.drawdowns[0] is None
    assert result.drawdowns[1:] == pytest.approx((0.0, 0.25))
    assert result.max_drawdown == pytest.approx(0.25)


def test_flat_path_has_a_measured_zero_maximum() -> None:
    result = compute_optional_drawdown(
        [100.0, 100.0],
        flow_timing=FlowTiming.END,
    )

    assert result.drawdowns == (None, 0.0)
    assert result.max_drawdown == 0.0


def test_invalid_initial_observation_is_unavailable() -> None:
    result = compute_optional_drawdown(
        [0.0, 100.0, 90.0],
        flow_timing=FlowTiming.END,
    )

    assert result.drawdowns == (None, None, None)
    assert result.max_drawdown is None


def test_non_finite_later_observation_is_unavailable() -> None:
    result = compute_optional_drawdown(
        [100.0, float("nan"), 90.0],
        flow_timing=FlowTiming.END,
    )

    assert result.drawdowns == (None, None, None)
    assert result.max_drawdown is None


def test_end_timed_withdrawal_is_removed_from_drawdown() -> None:
    result = compute_optional_drawdown(
        [100.0, 90.0],
        withdrawals_as_contribution_flows([Decimal("10"), Decimal("10")]),
        flow_timing=FlowTiming.END,
    )

    assert result.drawdowns == (None, 0.0)
    assert result.max_drawdown == 0.0


def test_beginning_timed_withdrawal_is_removed_from_drawdown() -> None:
    result = compute_optional_drawdown(
        [100.0, 90.0],
        withdrawals_as_contribution_flows([Decimal("0"), Decimal("10")]),
        flow_timing=FlowTiming.BEGINNING,
    )

    assert result.drawdowns == (None, 0.0)
    assert result.max_drawdown == 0.0


def test_undefined_flow_adjusted_return_is_unavailable() -> None:
    result = compute_optional_drawdown(
        [100.0, 90.0],
        (ContributionPositiveFlow(0.0), ContributionPositiveFlow(-150.0)),
        flow_timing=FlowTiming.BEGINNING,
    )

    assert result.drawdowns == (None, None)
    assert result.max_drawdown is None


def test_numpy_observations_are_supported() -> None:
    result = compute_optional_drawdown(
        np.array([100.0, 80.0]),
        flow_timing=FlowTiming.END,
    )

    assert result.drawdowns[0] is None
    assert result.drawdowns[1] == pytest.approx(0.2)
    assert result.max_drawdown == pytest.approx(0.2)


def test_withdrawals_convert_to_negative_contributions() -> None:
    flows = withdrawals_as_contribution_flows(
        [Decimal("0"), Decimal("10.5")]
    )

    assert float(flows[0]) == 0.0
    assert float(flows[1]) == -10.5
