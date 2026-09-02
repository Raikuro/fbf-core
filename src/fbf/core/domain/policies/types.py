"""Public policy-type enums — the single source of truth for valid policy types.

These enums are the canonical registry of allocation and withdrawal policy
types.  They carry the metadata that consumers (CLI, UI) need:

* ``yaml_name``:  the canonical string used in study YAML ``type`` fields.
* ``display_name``:  human-readable label for UIs and CLI headers.
* ``parameter_key``:  the YAML key that carries the policy's scalar value.

CLI and UI must import these enums from ``fbf.core.domain.policies`` (Tier 2)
or ``fbf.core`` (Tier 1).  They must not maintain independent lists of valid
policy type names.
"""

from __future__ import annotations

from enum import Enum


class AllocationPolicyType(Enum):
    """Enumeration of valid allocation policy types."""

    CONSTANT = ("ConstantAllocationPolicy", "Constant Allocation", "equity_allocation")
    GLIDEPATH = ("GlidepathAllocationPolicy", "Glidepath", "start_equity")

    def __init__(
        self, yaml_name: str, display_name: str, parameter_key: str
    ) -> None:
        self.yaml_name = yaml_name
        self.display_name = display_name
        self.parameter_key = parameter_key

    @classmethod
    def from_yaml_name(cls, name: str) -> AllocationPolicyType:
        """Look up an allocation policy type by its YAML ``type`` string.

        Raises ``ValueError`` if *name* is not a valid allocation policy type.
        """
        for member in cls:
            if member.yaml_name == name:
                return member
        valid = ", ".join(m.yaml_name for m in cls)
        raise ValueError(
            f"Unsupported allocation policy type: {name!r} "
            f"(valid types: {valid})"
        )


class WithdrawalPolicyType(Enum):
    """Enumeration of valid withdrawal policy types."""

    FIXED_REAL = ("FixedRealWithdrawalPolicy", "Fixed Real", "withdrawal_rate")
    CONSTANT = ("ConstantWithdrawalPolicy", "Constant", "withdrawal_rate")

    def __init__(
        self, yaml_name: str, display_name: str, parameter_key: str
    ) -> None:
        self.yaml_name = yaml_name
        self.display_name = display_name
        self.parameter_key = parameter_key

    @classmethod
    def from_yaml_name(cls, name: str) -> WithdrawalPolicyType:
        """Look up a withdrawal policy type by its YAML ``type`` string.

        Raises ``ValueError`` if *name* is not a valid withdrawal policy type.
        """
        for member in cls:
            if member.yaml_name == name:
                return member
        valid = ", ".join(m.yaml_name for m in cls)
        raise ValueError(
            f"Unsupported withdrawal policy type: {name!r} "
            f"(valid types: {valid})"
        )
