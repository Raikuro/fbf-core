"""Parameter-axis construction helper."""

from __future__ import annotations

from dataclasses import dataclass

from research.domain.parameter.types import ParameterScalar

_PARAMETER_SCALAR_TYPES = (int, float, bool, str)


@dataclass(frozen=True)
class ParameterAxis:
    """Immutable named dimension of a research parameter space."""

    name: str
    values: tuple[ParameterScalar, ...]

    def __post_init__(self) -> None:
        """Validate the axis name and its homogeneous, unique values."""
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("ParameterAxis name cannot be empty or whitespace.")

        values = tuple(self.values)
        if not values:
            raise ValueError("ParameterAxis values cannot be empty.")
        if any(type(value) not in _PARAMETER_SCALAR_TYPES for value in values):
            raise ValueError("ParameterAxis values must be int, float, bool, or str.")
        if any(type(value) is not type(values[0]) for value in values[1:]):
            raise ValueError("ParameterAxis values must be homogeneous in scalar type.")
        has_duplicates = any(
            value == previous for index, value in enumerate(values) for previous in values[:index]
        )
        if has_duplicates:
            raise ValueError("ParameterAxis values must be unique.")

        object.__setattr__(self, "values", values)
