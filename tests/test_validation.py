from __future__ import annotations

from engine.domain.validation.validation import ValidationResult, ValidationState


def test_validation_result_states() -> None:
    result = ValidationResult(state=ValidationState.SUCCESS, errors=(), warnings=())

    assert result.is_success()
    assert not result.is_error()


def test_validation_result_with_error() -> None:
    result = ValidationResult(state=ValidationState.WARNING, errors=(), warnings=())
    updated = result.with_error("invalid data")

    assert updated.state == ValidationState.ERROR
    assert updated.errors == ("invalid data",)


def test_validation_result_with_warning() -> None:
    result = ValidationResult(state=ValidationState.SUCCESS, errors=(), warnings=())
    updated = result.with_warning("check data")

    assert updated.state == ValidationState.WARNING
    assert updated.warnings == ("check data",)
