"""Deterministic Cartesian parameter-space generator."""

from __future__ import annotations

import math
from collections.abc import Sequence
from itertools import product

from research.domain.parameter.axis import ParameterAxis
from research.domain.parameter.configuration import ParameterConfiguration
from research.domain.parameter.types import ParameterScalar


class ParameterSweepEngine:
    """Stateless utility for generating deterministic parameter grids."""

    @staticmethod
    def axis_from_values(name: str, values: Sequence[ParameterScalar]) -> ParameterAxis:
        """Construct an axis that preserves the supplied value order."""
        return ParameterAxis(name=name, values=tuple(values))

    @staticmethod
    def axis_from_range(
        name: str,
        start: int | float,
        stop: int | float,
        step: int | float,
    ) -> ParameterAxis:
        """Construct an axis from a closed, deterministic numeric progression."""
        ParameterSweepEngine._validate_range_argument("start", start)
        ParameterSweepEngine._validate_range_argument("stop", stop)
        ParameterSweepEngine._validate_range_argument("step", step)

        if step == 0:
            raise ValueError("ParameterSweepEngine range step cannot be zero.")
        if start != stop and (stop - start) * step < 0:
            raise ValueError(
                "ParameterSweepEngine range step direction must progress from start toward stop."
            )
        if start == stop:
            return ParameterAxis(name=name, values=(start,))

        if type(start) is int and type(stop) is int and type(step) is int:
            step_count = abs(stop - start) // abs(step)
            integer_values = tuple(start + index * step for index in range(step_count + 1))
            return ParameterAxis(name=name, values=integer_values)

        float_start = float(start)
        float_stop = float(stop)
        float_step = float(step)
        ratio = abs((float_stop - float_start) / float_step)
        nearest = round(ratio)
        if math.isclose(
            float_start + nearest * float_step,
            float_stop,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            step_count = nearest
        else:
            step_count = math.floor(ratio)

        float_values = tuple(float_start + index * float_step for index in range(step_count + 1))
        if math.isclose(float_values[-1], float_stop, rel_tol=0.0, abs_tol=1e-12):
            float_values = float_values[:-1] + (float_stop,)
        return ParameterAxis(name=name, values=float_values)

    @staticmethod
    def cartesian_product(
        axes: Sequence[ParameterAxis],
    ) -> tuple[ParameterConfiguration, ...]:
        """Return the complete product, with the rightmost axis varying fastest."""
        axis_tuple = tuple(axes)
        if not axis_tuple:
            raise ValueError("ParameterSweepEngine axes cannot be empty.")
        if any(not isinstance(axis, ParameterAxis) for axis in axis_tuple):
            raise ValueError("ParameterSweepEngine axes must contain only ParameterAxis instances.")

        names = tuple(axis.name for axis in axis_tuple)
        if len(set(names)) != len(names):
            raise ValueError("ParameterSweepEngine axis names must be unique.")

        return tuple(
            ParameterConfiguration(dict(zip(names, combination, strict=True)))
            for combination in product(*(axis.values for axis in axis_tuple))
        )

    @staticmethod
    def generate(axes: Sequence[ParameterAxis]) -> tuple[ParameterConfiguration, ...]:
        """Ergonomic alias for :meth:`cartesian_product`."""
        return ParameterSweepEngine.cartesian_product(axes)

    @staticmethod
    def _validate_range_argument(name: str, value: int | float) -> None:
        """Validate one numeric range argument, rejecting bool and non-finite values."""
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(
                f"ParameterSweepEngine range {name} must be a finite int or float, not bool."
            )
