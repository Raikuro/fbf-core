from __future__ import annotations

import pickle
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Any

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.execution.pipeline.simulation import (
    MonthlyResult,
    SimulationResult,
    SimulationStatistics,
    SimulationTimeline,
)

_EQUITY = AssetClass(id="equity", name="Equity", description="")
_BOND = AssetClass(id="bond", name="Bond", description="")


def _make_result() -> SimulationResult:
    snapshot = MarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={
            _EQUITY: Decimal("100.00"),
            _BOND: Decimal("50.00"),
        },
        inflation=Decimal("0.00"),
        inflation_cumulative=Decimal("0.00"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100.00"),
        cape=Decimal("25.5"),
    )
    monthly = MonthlyResult(
        date=date(2000, 1, 1),
        period_index=0,
        market_snapshot=snapshot,
        portfolio=Portfolio(
            holdings=(
                AssetHolding(asset_class=_EQUITY, units=Decimal("10")),
                AssetHolding(asset_class=_BOND, units=Decimal("20")),
            )
        ),
        allocation=None,
        allocation_target=None,
        allocation_drift=None,
        withdrawal_decision=None,
        rebalance_result=None,
        drawdown=0.0,
        cumulative_return=0.0,
        cumulative_inflation=0.0,
        events=(),
    )
    return SimulationResult(
        timeline=SimulationTimeline(monthly_results=(monthly,)),
        statistics=SimulationStatistics(
            final_wealth=Money(Decimal("2000"), Currency.EUR),
            max_drawdown=0.0,
            success=True,
            failure_month=None,
            failure_state=None,
            months_simulated=1,
            execution_time_seconds=0.01,
        ),
    )


def test_simulation_result_pickle_round_trip_preserves_immutable_snapshot() -> None:
    original = _make_result()

    restored = pickle.loads(pickle.dumps(original))

    assert restored == original
    original_snapshot = original.timeline.monthly_results[0].market_snapshot
    restored_snapshot = restored.timeline.monthly_results[0].market_snapshot
    assert restored_snapshot == original_snapshot
    assert restored_snapshot.index_levels is not original_snapshot.index_levels
    assert isinstance(restored_snapshot.index_levels, MappingProxyType)

    levels: Any = restored_snapshot.index_levels
    with pytest.raises(TypeError):
        levels[_EQUITY] = Decimal("1")

    assert restored_snapshot.index_levels[_EQUITY] == Decimal("100.00")
