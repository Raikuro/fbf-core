"""Validation abstractions for the Engine domain."""

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
    """Immutable result of domain validation."""

    state: ValidationState
    errors: Sequence[str]
    warnings: Sequence[str]

    def is_success(self) -> bool:
        return self.state == ValidationState.SUCCESS

    def is_error(self) -> bool:
        return self.state == ValidationState.ERROR

    def with_error(self, error: str) -> ValidationResult:
        return ValidationResult(
            state=ValidationState.ERROR,
            errors=tuple(self.errors) + (error,),
            warnings=self.warnings,
        )

    def with_warning(self, warning: str) -> ValidationResult:
        new_state = (
            ValidationState.WARNING
            if self.state != ValidationState.ERROR
            else ValidationState.ERROR
        )
        return ValidationResult(
            state=new_state,
            errors=self.errors,
            warnings=tuple(self.warnings) + (warning,),
        )
