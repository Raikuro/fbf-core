"""Domain policies (base protocols, concrete policies, and type enums)."""

from __future__ import annotations

from fbf.core.domain.policies.allocation_policy import AllocationPolicy
from fbf.core.domain.policies.concrete import (
    ConstantAllocationPolicy,
    ConstantWithdrawalPolicy,
    FixedRealWithdrawalPolicy,
)
from fbf.core.domain.policies.decisions import AllocationDecision, WithdrawalDecision
from fbf.core.domain.policies.glidepath import GlidepathAllocationPolicy
from fbf.core.domain.policies.policy import Policy
from fbf.core.domain.policies.types import AllocationPolicyType, WithdrawalPolicyType
from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy

__all__ = [
    "Policy",
    "AllocationPolicy",
    "WithdrawalPolicy",
    "AllocationDecision",
    "WithdrawalDecision",
    "ConstantAllocationPolicy",
    "ConstantWithdrawalPolicy",
    "FixedRealWithdrawalPolicy",
    "GlidepathAllocationPolicy",
    "AllocationPolicyType",
    "WithdrawalPolicyType",
]
