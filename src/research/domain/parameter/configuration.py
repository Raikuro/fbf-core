"""Immutable parameter-space configuration value object."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from research.domain.parameter.types import ParameterScalar

_PARAMETER_SCALAR_TYPES = (int, float, bool, str)


@dataclass(frozen=True, eq=False)
class ParameterConfiguration:
    """Immutable, domain-agnostic named assignment of primitive parameter values."""

    values: Mapping[str, ParameterScalar]

    def __post_init__(self) -> None:
        """Validate bindings and replace them with an immutable defensive copy."""
        bindings = dict(self.values)
        if not bindings:
            raise ValueError("ParameterConfiguration values cannot be empty.")

        for name, value in bindings.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError(
                    "ParameterConfiguration parameter names cannot be empty or whitespace."
                )
            if type(value) not in _PARAMETER_SCALAR_TYPES:
                raise ValueError("ParameterConfiguration values must be int, float, bool, or str.")

        object.__setattr__(self, "values", MappingProxyType(bindings))

    def get(self, name: str) -> ParameterScalar:
        """Return the value bound to ``name``."""
        return self.values[name]

    def names(self) -> tuple[str, ...]:
        """Return parameter names in canonical sorted order."""
        return tuple(sorted(self.values))

    def items(self) -> tuple[tuple[str, ParameterScalar], ...]:
        """Return bindings in canonical sorted order."""
        return tuple((name, self.values[name]) for name in self.names())

    def __eq__(self, other: object) -> bool:
        """Compare configurations by their unordered name-to-value bindings."""
        if not isinstance(other, ParameterConfiguration):
            return NotImplemented
        return self.values == other.values

    def __hash__(self) -> int:
        """Hash the canonical ordered binding form."""
        return hash(self.items())
