"""Concrete implementations of persistence codec protocols.

Provides production-ready implementations of the three codec
protocols required by PersistenceReconstructionContext:

- DefaultDatasetResolver: resolves dataset identifiers to Dataset objects
- AllocationPolicyCodec: PolicyCodec for AllocationPolicy compatible objects
- WithdrawalPolicyCodec: PolicyCodec for WithdrawalPolicy compatible objects
- SimulationResultCodec: Codec for SimulationResult objects
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from engine.domain.policies.allocation_policy import AllocationPolicy
from engine.domain.policies.withdrawal_policy import WithdrawalPolicy
from infrastructure.persistence.errors import StudyNotFoundError
from infrastructure.persistence.serializers import to_canonical_json

if TYPE_CHECKING:
    from engine.application.simulation import MonthlyResult, SimulationResult
    from engine.domain.model.dataset import Dataset

from infrastructure.persistence.sqlite_repository import (
    JSONScalar,
    PolicyKind,
    SerializedSimulationResult,
)


class DefaultDatasetResolver:
    """Resolves dataset identifiers to Dataset objects.

    Uses an in-memory registry pre-populated at construction time.
    In production the registry is loaded from a data directory.
    """

    def __init__(self, datasets: Mapping[str, Dataset] | None = None) -> None:
        self._datasets = dict(datasets) if datasets else {}

    @classmethod
    def from_data_dir(cls, data_dir: str) -> DefaultDatasetResolver:
        from .dataset_cache import get_default_dataset_cache
        return cls(datasets=get_default_dataset_cache().load_dir(data_dir))

    def resolve(self, dataset_identifier: str) -> Dataset:
        # Step 1: Canonical identifier lookup
        dataset = self._datasets.get(dataset_identifier)
        if dataset is not None:
            return dataset
        for d in self._datasets.values():
            if d.identifier == dataset_identifier:
                return d

        # Step 2: Legacy version fallback lookup
        matching_by_version = [
            d for d in self._datasets.values() if d.version == dataset_identifier
        ]
        if len(matching_by_version) == 1:
            return matching_by_version[0]
        if len(matching_by_version) > 1:
            matching_ids = sorted(d.identifier or "unknown" for d in matching_by_version)
            raise StudyNotFoundError(
                f"Ambiguous legacy dataset version '{dataset_identifier}': "
                f"matched multiple datasets ({', '.join(matching_ids)})"
            )

        # Step 3: No matches found
        raise StudyNotFoundError(
            f"Dataset not found: '{dataset_identifier}'"
        )


class _ConcreteAllocationPolicy(AllocationPolicy):
    """Concrete AllocationPolicy subclass for serialization round-trip.

    Carries equity_allocation parameter through dump/load.
    Not intended for execution — raises NotImplementedError on decide.
    """

    def __init__(self, equity_allocation: str = "1.0") -> None:
        self.equity_allocation = equity_allocation

    def decide(self, context: Any) -> Any:
        raise NotImplementedError(
            "_ConcreteAllocationPolicy is a serialization placeholder"
        )


class _ConcreteWithdrawalPolicy(WithdrawalPolicy):
    """Concrete WithdrawalPolicy subclass for serialization round-trip.

    Carries withdrawal_rate parameter through dump/load.
    Not intended for execution — raises NotImplementedError on decide.
    """

    def __init__(self, withdrawal_rate: str = "0.04") -> None:
        self.withdrawal_rate = withdrawal_rate

    def decide(self, context: Any) -> Any:
        raise NotImplementedError(
            "_ConcreteWithdrawalPolicy is a serialization placeholder"
        )


class AllocationPolicyCodec:
    """Codec for AllocationPolicy-compatible objects.

    Serializes equity_allocation and reconstructs a concrete
    policy instance on load.
    """

    policy_type: str = "AllocationPolicy"
    policy_kind: PolicyKind = PolicyKind.ALLOCATION

    def dump(self, policy: Any) -> Mapping[str, JSONScalar]:
        equity = str(getattr(policy, "equity_allocation", "1.0"))
        return {"equity_allocation": equity}

    def load(self, parameters: Mapping[str, JSONScalar]) -> Any:
        equity = str(parameters.get("equity_allocation", "1.0"))
        return _ConcreteAllocationPolicy(equity_allocation=equity)


class WithdrawalPolicyCodec:
    """Codec for WithdrawalPolicy-compatible objects.

    Serializes withdrawal_rate and reconstructs a concrete
    policy instance on load.
    """

    policy_type: str = "WithdrawalPolicy"
    policy_kind: PolicyKind = PolicyKind.WITHDRAWAL

    def dump(self, policy: Any) -> Mapping[str, JSONScalar]:
        rate = str(getattr(policy, "withdrawal_rate", "0.04"))
        return {"withdrawal_rate": rate}

    def load(self, parameters: Mapping[str, JSONScalar]) -> Any:
        rate = str(parameters.get("withdrawal_rate", "0.04"))
        return _ConcreteWithdrawalPolicy(withdrawal_rate=rate)


class SimulationResultCodec:
    """Codec for SimulationResult objects.

    Provides lossless serialization of SimulationResult:
    - All Decimal precision preserved as strings
    - Date values preserved as ISO strings
    - Booleans, integers, floats preserved exactly
    - Monthly payload order preserved
    """

    def dump(self, result: SimulationResult) -> SerializedSimulationResult:
        serialized = self._serialize(result)
        return SerializedSimulationResult(
            statistics_payload_json=serialized.statistics_payload_json,
            monthly_payloads_json=serialized.monthly_payloads_json,
        )

    def load(
        self,
        statistics_payload_json: str,
        monthly_payloads_json: Sequence[str],
    ) -> SimulationResult:
        from engine.application.simulation import (
            SimulationResult,
            SimulationStatistics,
            SimulationTimeline,
        )
        from engine.domain.model.money import Currency, Money

        stats_data = json.loads(statistics_payload_json)
        statistics = SimulationStatistics(
            final_wealth=Money(
                amount=Decimal(stats_data["final_wealth_amount"]),
                currency=Currency(stats_data["final_wealth_currency"]),
            ),
            max_drawdown=stats_data["max_drawdown"],
            success=stats_data["success"],
            failure_month=stats_data.get("failure_month"),
            months_simulated=stats_data["months_simulated"],
            execution_time_seconds=stats_data["execution_time_seconds"],
        )

        monthly_list: list[MonthlyResult] = []
        for p in monthly_payloads_json:
            data = json.loads(p)
            # Skip dummy markers inserted by SQLiteRepository._save_simulation_result
            # for empty timelines ({"dummy": True}). This couples the codec to the
            # repository's internal convention; see NEXT_SESSION.md P3.1 TD-1.
            if not data.get("date"):
                continue
            monthly_list.append(self._deserialize_monthly(data))
        monthly_results = tuple(monthly_list)

        timeline = SimulationTimeline(monthly_results=monthly_results)
        return SimulationResult(timeline=timeline, statistics=statistics)

    def _serialize(
        self, result: SimulationResult
    ) -> SerializedSimulationResult:
        stats = result.statistics
        stats_payload = {
            "final_wealth_amount": str(stats.final_wealth.amount),
            "final_wealth_currency": stats.final_wealth.currency.value,
            "max_drawdown": stats.max_drawdown,
            "success": stats.success,
            "failure_month": stats.failure_month,
            "months_simulated": stats.months_simulated,
            "execution_time_seconds": stats.execution_time_seconds,
        }

        monthly = tuple(
            to_canonical_json(self._serialize_monthly(mr))
            for mr in result.timeline.monthly_results
        )

        return SerializedSimulationResult(
            statistics_payload_json=to_canonical_json(stats_payload),
            monthly_payloads_json=monthly,
        )

    def _serialize_monthly(self, mr: MonthlyResult) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "date": mr.date.isoformat(),
            "period_index": mr.period_index,
            "drawdown": mr.drawdown,
            "cumulative_return": mr.cumulative_return,
            "cumulative_inflation": mr.cumulative_inflation,
        }

        market_snapshot = {
            "date": mr.market_snapshot.date.isoformat(),
            "index_levels": {
                aid: str(level)
                for aid, level in (
                    (k.id, v) for k, v in mr.market_snapshot.index_levels.items()
                )
            },
            "inflation": str(mr.market_snapshot.inflation),
            "inflation_cumulative": str(mr.market_snapshot.inflation_cumulative),
            "is_ath": mr.market_snapshot.is_ath,
            "is_underwater": mr.market_snapshot.is_underwater,
            "running_ath": str(mr.market_snapshot.running_ath),
        }
        payload["market_snapshot"] = market_snapshot

        holdings = []
        for h in mr.portfolio.holdings:
            holdings.append(
                {
                    "asset_class_id": h.asset_class.id,
                    "units": str(h.units),
                }
            )
        payload["portfolio_holdings"] = holdings

        if mr.allocation is not None:
            payload["allocation"] = {
                aid: str(w)
                for aid, w in (
                    (k.id, v) for k, v in mr.allocation.weights.items()
                )
            }
        if mr.allocation_target is not None:
            payload["allocation_target"] = {
                aid: str(w)
                for aid, w in (
                    (k.id, v) for k, v in mr.allocation_target.weights.items()
                )
            }

        if mr.allocation_drift is not None:
            payload["allocation_drift"] = str(mr.allocation_drift)
        if mr.withdrawal_decision is not None:
            payload["withdrawal_decision"] = str(mr.withdrawal_decision)
        if mr.rebalance_result is not None:
            payload["rebalance_result"] = str(mr.rebalance_result)

        payload["events"] = [str(e) for e in mr.events]

        return payload

    def _deserialize_monthly(
        self, data: dict[str, Any]
    ) -> MonthlyResult:
        from engine.application.simulation import MonthlyResult
        from engine.domain.model.allocation import Allocation, AllocationTarget
        from engine.domain.model.asset import AssetClass
        from engine.domain.model.market_snapshot import MarketSnapshot
        from engine.domain.model.portfolio import AssetHolding, Portfolio

        ms_data = data.get("market_snapshot", {})
        asset_cache: dict[str, AssetClass] = {}

        def _get_asset(aid: str) -> AssetClass:
            if aid not in asset_cache:
                asset_cache[aid] = AssetClass(
                    id=aid, name=aid, description="Reconstructed"
                )
            return asset_cache[aid]

        index_levels = {}
        for aid, level_str in ms_data.get("index_levels", {}).items():
            index_levels[_get_asset(aid)] = Decimal(level_str)

        market_snapshot = MarketSnapshot(
            date=date.fromisoformat(ms_data.get("date", data["date"])),
            index_levels=index_levels,
            inflation=Decimal(ms_data.get("inflation", "0")),
            inflation_cumulative=Decimal(
                ms_data.get("inflation_cumulative", "0")
            ),
            is_ath=ms_data.get("is_ath", False),
            is_underwater=ms_data.get("is_underwater", False),
            running_ath=Decimal(ms_data.get("running_ath", "0")),
        )

        holdings = []
        for h_data in data.get("portfolio_holdings", []):
            holdings.append(
                AssetHolding(
                    asset_class=_get_asset(h_data["asset_class_id"]),
                    units=Decimal(h_data["units"]),
                )
            )
        portfolio = Portfolio(holdings=tuple(holdings))

        allocation = None
        if "allocation" in data:
            alloc_weights = {
                _get_asset(aid): Decimal(w)
                for aid, w in data["allocation"].items()
            }
            if alloc_weights:
                allocation = Allocation(weights=alloc_weights)

        allocation_target = None
        if "allocation_target" in data:
            target_weights = {
                _get_asset(aid): Decimal(w)
                for aid, w in data["allocation_target"].items()
            }
            if target_weights:
                allocation_target = AllocationTarget(
                    weights=target_weights
                )

        return MonthlyResult(
            date=date.fromisoformat(data["date"]),
            period_index=data["period_index"],
            market_snapshot=market_snapshot,
            portfolio=portfolio,
            allocation=allocation,
            allocation_target=allocation_target,
            allocation_drift=data.get("allocation_drift"),
            withdrawal_decision=data.get("withdrawal_decision"),
            rebalance_result=data.get("rebalance_result"),
            drawdown=data["drawdown"],
            cumulative_return=data["cumulative_return"],
            cumulative_inflation=data["cumulative_inflation"],
            events=data.get("events", []),
        )
