"""Unit tests for the frozen ParameterSweepEngine public contract."""

from dataclasses import FrozenInstanceError
from math import inf, nan
from types import MappingProxyType

import pytest

from research import ParameterAxis, ParameterConfiguration, ParameterSweepEngine


class TestParameterConfiguration:
    """Tests for the immutable, long-lived parameter identity."""

    def test_defensively_copies_and_freezes_bindings(self) -> None:
        source = {"withdrawal_rate": 0.04}
        configuration = ParameterConfiguration(source)
        source["withdrawal_rate"] = 0.05

        assert configuration.get("withdrawal_rate") == 0.04
        assert isinstance(configuration.values, MappingProxyType)
        with pytest.raises(TypeError):
            configuration.values["withdrawal_rate"] = 0.05  # type: ignore[index]

    def test_attribute_immutability(self) -> None:
        configuration = ParameterConfiguration({"equity": 0.6})

        with pytest.raises(FrozenInstanceError):
            configuration.values = {}  # type: ignore[misc]

    def test_canonical_access_and_missing_name(self) -> None:
        configuration = ParameterConfiguration({"zeta": "z", "alpha": 1})

        assert configuration.names() == ("alpha", "zeta")
        assert configuration.items() == (("alpha", 1), ("zeta", "z"))
        with pytest.raises(KeyError):
            configuration.get("missing")

    def test_equality_and_hash_ignore_mapping_insertion_order(self) -> None:
        first = ParameterConfiguration({"equity": 0.6, "withdrawal": 0.04})
        second = ParameterConfiguration({"withdrawal": 0.04, "equity": 0.6})
        different = ParameterConfiguration({"equity": 0.5, "withdrawal": 0.04})

        assert first == second
        assert hash(first) == hash(second)
        assert first != different
        assert {first, second, different} == {first, different}
        assert {first: "result"}[second] == "result"

    @pytest.mark.parametrize("values", [{}, {"": 1}, {"   ": 1}, {1: 1}])
    def test_rejects_empty_or_invalid_names(self, values: object) -> None:
        with pytest.raises(ValueError):
            ParameterConfiguration(values)  # type: ignore[arg-type]

    @pytest.mark.parametrize("value", [None, object(), [1], {"nested": 1}, lambda: 1])
    def test_rejects_non_primitive_values(self, value: object) -> None:
        with pytest.raises(ValueError, match="int, float, bool, or str"):
            ParameterConfiguration({"parameter": value})  # type: ignore[dict-item]

    @pytest.mark.parametrize("value", [1, 1.5, True, "static"])
    def test_accepts_every_scalar_kind(self, value: int | float | bool | str) -> None:
        assert ParameterConfiguration({"parameter": value}).get("parameter") == value


class TestParameterAxis:
    """Tests for axis construction-time invariants."""

    def test_coerces_values_to_tuple_and_preserves_order(self) -> None:
        axis = ParameterAxis("family", ["static", "glidepath"])  # type: ignore[arg-type]

        assert axis.values == ("static", "glidepath")
        with pytest.raises(FrozenInstanceError):
            axis.name = "other"  # type: ignore[misc]

    @pytest.mark.parametrize("name", ["", "   ", 1])
    def test_rejects_blank_or_non_string_name(self, name: object) -> None:
        with pytest.raises(ValueError, match="name cannot be empty or whitespace"):
            ParameterAxis(name, (1,))  # type: ignore[arg-type]

    def test_rejects_empty_duplicate_and_heterogeneous_values(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            ParameterAxis("rate", ())
        with pytest.raises(ValueError, match="must be unique"):
            ParameterAxis("rate", (1, 1))
        with pytest.raises(ValueError, match="homogeneous"):
            ParameterAxis("rate", (True, 1))
        with pytest.raises(ValueError, match="homogeneous"):
            ParameterAxis("rate", (1, 1.0))

    @pytest.mark.parametrize("value", [None, object(), (1,), {"value": 1}])
    def test_rejects_non_scalar_values(self, value: object) -> None:
        with pytest.raises(ValueError, match="int, float, bool, or str"):
            ParameterAxis("rate", (value,))  # type: ignore[arg-type]


class TestParameterSweepEngine:
    """Tests for factories, products, validation, and deterministic order."""

    def test_axis_from_values_preserves_order(self) -> None:
        assert ParameterSweepEngine.axis_from_values("family", ["z", "a"]) == ParameterAxis(
            "family", ("z", "a")
        )

    def test_integer_range_is_closed_and_integral(self) -> None:
        axis = ParameterSweepEngine.axis_from_range("months", 0, 10, 2)

        assert axis.values == (0, 2, 4, 6, 8, 10)
        assert all(type(value) is int for value in axis.values)

    @pytest.mark.parametrize(
        ("name", "start", "stop", "step"),
        [("equity", 0.0, 1.0, 0.05), ("withdrawal", 0.030, 0.050, 0.001)],
    )
    def test_float_research_grids_include_expected_endpoint(
        self, name: str, start: float, stop: float, step: float
    ) -> None:
        axis = ParameterSweepEngine.axis_from_range(name, start, stop, step)

        assert len(axis.values) == 21
        assert axis.values[0] == pytest.approx(start, abs=1e-12)
        assert axis.values[-1] == pytest.approx(stop, abs=1e-12)
        assert axis.values[10] == pytest.approx(start + 10 * step, abs=1e-12)
        assert all(type(value) is float for value in axis.values)

    def test_singleton_and_descending_ranges(self) -> None:
        assert ParameterSweepEngine.axis_from_range("singleton", 5, 5, -1).values == (5,)
        assert ParameterSweepEngine.axis_from_range("descending", 5, -1, -2).values == (5, 3, 1, -1)

    @pytest.mark.parametrize(
        ("start", "stop", "step"),
        [(0, 1, 0), (1, 0, 1), (0, 1, -1), (0, 1, True), (nan, 1, 1), (0, inf, 1)],
    )
    def test_rejects_invalid_ranges(
        self, start: int | float, stop: int | float, step: int | float
    ) -> None:
        with pytest.raises(ValueError):
            ParameterSweepEngine.axis_from_range("range", start, stop, step)

    def test_single_axis_product_preserves_axis_order(self) -> None:
        axis = ParameterAxis("family", ("static", "glide"))

        assert ParameterSweepEngine.cartesian_product([axis]) == (
            ParameterConfiguration({"family": "static"}),
            ParameterConfiguration({"family": "glide"}),
        )

    def test_two_axis_product_uses_rightmost_axis_fastest(self) -> None:
        left = ParameterAxis("equity", (0.5, 0.6))
        right = ParameterAxis("months", (60, 120, 180))

        configurations = ParameterSweepEngine.cartesian_product([left, right])

        assert len(configurations) == 6
        assert tuple(configuration.items() for configuration in configurations) == (
            (("equity", 0.5), ("months", 60)),
            (("equity", 0.5), ("months", 120)),
            (("equity", 0.5), ("months", 180)),
            (("equity", 0.6), ("months", 60)),
            (("equity", 0.6), ("months", 120)),
            (("equity", 0.6), ("months", 180)),
        )

    def test_three_axis_glidepath_surface_is_complete_and_deterministic(self) -> None:
        start = ParameterSweepEngine.axis_from_range("glide_start", 0.0, 1.0, 0.1)
        end = ParameterSweepEngine.axis_from_range("glide_end", 0.0, 1.0, 0.1)
        months = ParameterAxis("glide_months", (60, 120, 180))

        first = ParameterSweepEngine.generate([start, end, months])
        second = ParameterSweepEngine.generate([start, end, months])

        assert len(first) == 363
        assert first == second
        assert first[0] == ParameterConfiguration(
            {"glide_start": 0.0, "glide_end": 0.0, "glide_months": 60}
        )
        assert first[-1] == ParameterConfiguration(
            {"glide_start": 1.0, "glide_end": 1.0, "glide_months": 180}
        )

    @pytest.mark.parametrize("axes", [[], [None], [ParameterAxis("x", (1,)), "bad"]])
    def test_rejects_empty_or_invalid_product_axes(self, axes: object) -> None:
        with pytest.raises(ValueError):
            ParameterSweepEngine.cartesian_product(axes)  # type: ignore[arg-type]

    def test_rejects_duplicate_axis_names(self) -> None:
        with pytest.raises(ValueError, match="names must be unique"):
            ParameterSweepEngine.generate([ParameterAxis("x", (1,)), ParameterAxis("x", (2,))])

    def test_generate_is_exact_alias_of_cartesian_product(self) -> None:
        axes = [ParameterAxis("x", (1, 2)), ParameterAxis("y", ("a", "b"))]

        assert ParameterSweepEngine.generate(axes) == ParameterSweepEngine.cartesian_product(axes)
