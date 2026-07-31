from __future__ import annotations

from decimal import Decimal

from engine.domain.model.allocation import AllocationTarget
from engine.domain.model.asset import AssetClass
from engine.domain.model.money import Currency, Money
from engine.domain.policies.allocation_policy import AllocationPolicy
from engine.domain.policies.decisions import (
    AllocationDecision,
    PolicyDecision,
    WithdrawalDecision,
)
from engine.domain.policies.policy import Policy
from engine.domain.policies.withdrawal_policy import WithdrawalPolicy


class DummyPolicy(Policy):
    def decide(self, context: object) -> PolicyDecision:
        return PolicyDecision(reason="dummy")


class DummyAllocationPolicy(AllocationPolicy):
    def decide(self, context: object) -> AllocationDecision:
        asset = AssetClass(id="test", name="Test", description="")
        return AllocationDecision(
            reason="dummy",
            allocation_target=AllocationTarget(weights={asset: Decimal("1")}),
        )


class DummyWithdrawalPolicy(WithdrawalPolicy):
    def decide(self, context: object) -> WithdrawalDecision:
        return WithdrawalDecision(
            reason="dummy",
            nominal_amount=Money(Decimal("0"), Currency.EUR),
            real_amount=Money(Decimal("0"), Currency.EUR),
        )


def test_policy_base_class_instantiation() -> None:
    policy = DummyPolicy()
    assert isinstance(policy, Policy)


def test_allocation_policy_interface() -> None:
    policy = DummyAllocationPolicy()
    assert isinstance(policy, AllocationPolicy)


def test_withdrawal_policy_interface() -> None:
    policy = DummyWithdrawalPolicy()
    assert isinstance(policy, WithdrawalPolicy)
