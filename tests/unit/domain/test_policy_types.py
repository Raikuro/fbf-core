"""Tests for policy-type enums (AllocationPolicyType, WithdrawalPolicyType)."""

from __future__ import annotations

import pytest

from fbf.core.domain.policies.types import AllocationPolicyType, WithdrawalPolicyType


class TestAllocationPolicyType:
    """Tests for AllocationPolicyType enum."""

    def test_constant_member_metadata(self) -> None:
        member = AllocationPolicyType.CONSTANT
        assert member.yaml_name == "ConstantAllocationPolicy"
        assert member.display_name == "Constant Allocation"
        assert member.parameter_key == "equity_allocation"

    def test_from_yaml_name_valid(self) -> None:
        result = AllocationPolicyType.from_yaml_name("ConstantAllocationPolicy")
        assert result is AllocationPolicyType.CONSTANT

    def test_from_yaml_name_invalid(self) -> None:
        with pytest.raises(ValueError, match="Unsupported allocation policy type"):
            AllocationPolicyType.from_yaml_name("UnknownPolicy")

    def test_all_members_exhaustive(self) -> None:
        members = list(AllocationPolicyType)
        assert len(members) == 1
        assert members[0] is AllocationPolicyType.CONSTANT


class TestWithdrawalPolicyType:
    """Tests for WithdrawalPolicyType enum."""

    def test_fixed_real_member_metadata(self) -> None:
        member = WithdrawalPolicyType.FIXED_REAL
        assert member.yaml_name == "FixedRealWithdrawalPolicy"
        assert member.display_name == "Fixed Real"
        assert member.parameter_key == "withdrawal_rate"

    def test_constant_member_metadata(self) -> None:
        member = WithdrawalPolicyType.CONSTANT
        assert member.yaml_name == "ConstantWithdrawalPolicy"
        assert member.display_name == "Constant"
        assert member.parameter_key == "withdrawal_rate"

    def test_from_yaml_name_valid_fixed_real(self) -> None:
        result = WithdrawalPolicyType.from_yaml_name("FixedRealWithdrawalPolicy")
        assert result is WithdrawalPolicyType.FIXED_REAL

    def test_from_yaml_name_valid_constant(self) -> None:
        result = WithdrawalPolicyType.from_yaml_name("ConstantWithdrawalPolicy")
        assert result is WithdrawalPolicyType.CONSTANT

    def test_from_yaml_name_invalid(self) -> None:
        with pytest.raises(ValueError, match="Unsupported withdrawal policy type"):
            WithdrawalPolicyType.from_yaml_name("UnknownPolicy")

    def test_all_members_exhaustive(self) -> None:
        members = list(WithdrawalPolicyType)
        assert len(members) == 2
        yaml_names = {m.yaml_name for m in members}
        assert yaml_names == {"FixedRealWithdrawalPolicy", "ConstantWithdrawalPolicy"}
