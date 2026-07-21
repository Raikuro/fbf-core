from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence


class ValidationState(Enum):
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class ValidationResult:
    """Immutable result of domain validation.

    Responsibilities:
    - represent structural and domain validation outcomes

    Invariants:
    - state reflects the highest-severity issue present
    """

    state: ValidationState
    errors: Sequence[str]
    warnings: Sequence[str]
