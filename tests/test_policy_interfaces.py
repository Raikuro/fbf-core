from __future__ import annotations

from engine.domain.policies.allocation_policy import AllocationPolicy
from engine.domain.policies.policy import Policy
from engine.domain.policies.withdrawal_policy import WithdrawalPolicy


class DummyPolicy(Policy):
    def decide(self, context: object):
        return None


class DummyAllocationPolicy(AllocationPolicy):
    def decide(self, context: object):
        return None


class DummyWithdrawalPolicy(WithdrawalPolicy):
    def decide(self, context: object):
        return None


def test_policy_base_class_instantiation() -> None:
    policy = DummyPolicy()
    assert isinstance(policy, Policy)


def test_allocation_policy_interface() -> None:
    policy = DummyAllocationPolicy()
    assert isinstance(policy, AllocationPolicy)


def test_withdrawal_policy_interface() -> None:
    policy = DummyWithdrawalPolicy()
    assert isinstance(policy, WithdrawalPolicy)
