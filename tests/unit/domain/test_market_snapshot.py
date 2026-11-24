from __future__ import annotations

import copy
import pickle
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Any

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.market_snapshot import MarketSnapshot

_ASSET = AssetClass(id="equity", name="", description="")

_AUXILIARY_DECIMAL_FIELDS = ("inflation", "inflation_cumulative", "running_ath")
_BOOLEAN_FIELDS = ("is_ath", "is_underwater")


def _snapshot(*, cape: Any = None) -> MarketSnapshot:
    return MarketSnapshot(
        date=date(2000, 1, 1),
        index_levels={_ASSET: Decimal("100")},
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100"),
        cape=cape,
    )


def _snapshot_with(**overrides: Any) -> MarketSnapshot:
    fields: dict[str, Any] = {
        "date": date(2000, 1, 1),
        "index_levels": {_ASSET: Decimal("100")},
        "inflation": Decimal("0"),
        "inflation_cumulative": Decimal("0"),
        "is_ath": True,
        "is_underwater": False,
        "running_ath": Decimal("100"),
        "cape": None,
    }
    fields.update(overrides)
    return MarketSnapshot(**fields)


def test_none_cape_is_preserved() -> None:
    assert _snapshot(cape=None).cape is None


def test_valid_decimal_cape_is_preserved_exactly() -> None:
    cape = Decimal("25.12345678901234567890")

    snapshot = _snapshot(cape=cape)

    assert snapshot.cape is cape
    assert snapshot.cape.as_tuple() == cape.as_tuple()


def test_negative_finite_cape_is_accepted() -> None:
    cape = Decimal("-12.5000")

    snapshot = _snapshot(cape=cape)

    assert snapshot.cape is cape
    assert snapshot.cape.as_tuple() == cape.as_tuple()


@pytest.mark.parametrize(
    "cape",
    [25.0, "25.0", 25],
    ids=["float", "str", "int"],
)
def test_non_decimal_cape_is_rejected(cape: Any) -> None:
    with pytest.raises(
        TypeError,
        match="MarketSnapshot cape must be a Decimal or None",
    ):
        _snapshot(cape=cape)


@pytest.mark.parametrize(
    "cape",
    [
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
    ids=["nan", "snan", "infinity", "negative_infinity"],
)
def test_non_finite_cape_is_rejected(cape: Decimal) -> None:
    with pytest.raises(
        ValueError,
        match="MarketSnapshot cape must be finite",
    ):
        _snapshot(cape=cape)


def test_valid_date_is_preserved() -> None:
    snapshot = _snapshot_with(date=date(2001, 2, 3))

    assert snapshot.date == date(2001, 2, 3)


def test_none_date_is_rejected() -> None:
    with pytest.raises(ValueError, match="MarketSnapshot date must be set"):
        _snapshot_with(date=None)


@pytest.mark.parametrize(
    "invalid_date",
    ["2000-01-01", 20000101, datetime(2000, 1, 1)],
    ids=["str", "int", "datetime"],
)
def test_non_date_is_rejected(invalid_date: Any) -> None:
    with pytest.raises(
        TypeError,
        match="MarketSnapshot date must be a date",
    ):
        _snapshot_with(date=invalid_date)


def test_valid_index_level_is_preserved_exactly() -> None:
    level = Decimal("123.4500")

    snapshot = _snapshot_with(index_levels={_ASSET: level})

    assert snapshot.index_levels[_ASSET] is level
    assert snapshot.index_levels[_ASSET].as_tuple() == level.as_tuple()


def test_zero_index_level_is_allowed() -> None:
    snapshot = _snapshot_with(index_levels={_ASSET: Decimal("0.00")})

    assert snapshot.index_levels[_ASSET] == Decimal("0.00")


def test_empty_index_levels_is_allowed() -> None:
    snapshot = _snapshot_with(index_levels={})

    assert snapshot.index_levels == {}


@pytest.mark.parametrize(
    "invalid_key",
    ["equity", 1, None, ("equity",)],
    ids=["str", "int", "none", "tuple"],
)
def test_non_asset_class_key_is_rejected(invalid_key: Any) -> None:
    with pytest.raises(
        TypeError,
        match="MarketSnapshot index_levels keys must be AssetClass",
    ):
        _snapshot_with(index_levels={invalid_key: Decimal("100")})


def test_none_index_level_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="MarketSnapshot index_levels must not contain None",
    ):
        _snapshot_with(index_levels={_ASSET: None})


@pytest.mark.parametrize(
    "invalid_level",
    [100, 100.0, "100", True],
    ids=["int", "float", "str", "bool"],
)
def test_non_decimal_index_level_is_rejected(invalid_level: Any) -> None:
    with pytest.raises(
        TypeError,
        match="MarketSnapshot index_levels values must be Decimal",
    ):
        _snapshot_with(index_levels={_ASSET: invalid_level})


@pytest.mark.parametrize(
    "invalid_level",
    [
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
    ids=["nan", "snan", "infinity", "negative_infinity"],
)
def test_non_finite_index_level_is_rejected(invalid_level: Decimal) -> None:
    with pytest.raises(
        ValueError,
        match="MarketSnapshot index_levels values must be finite",
    ):
        _snapshot_with(index_levels={_ASSET: invalid_level})


def test_negative_index_level_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="MarketSnapshot index_levels values must be non-negative",
    ):
        _snapshot_with(index_levels={_ASSET: Decimal("-0.01")})


@pytest.mark.parametrize("field", _AUXILIARY_DECIMAL_FIELDS)
@pytest.mark.parametrize(
    "value",
    [Decimal("0"), Decimal("12.3450"), Decimal("-3.5")],
    ids=["zero", "positive", "negative"],
)
def test_finite_decimal_auxiliary_field_is_preserved_exactly(
    field: str,
    value: Decimal,
) -> None:
    snapshot = _snapshot_with(**{field: value})

    actual = getattr(snapshot, field)
    assert actual is value
    assert actual.as_tuple() == value.as_tuple()


@pytest.mark.parametrize("field", _AUXILIARY_DECIMAL_FIELDS)
@pytest.mark.parametrize(
    "invalid_value",
    [0, 0.0, "0", None],
    ids=["int", "float", "str", "none"],
)
def test_non_decimal_auxiliary_field_is_rejected(
    field: str,
    invalid_value: Any,
) -> None:
    with pytest.raises(
        TypeError,
        match=f"MarketSnapshot {field} must be a Decimal",
    ):
        _snapshot_with(**{field: invalid_value})


@pytest.mark.parametrize("field", _AUXILIARY_DECIMAL_FIELDS)
@pytest.mark.parametrize(
    "invalid_value",
    [
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
    ids=["nan", "snan", "infinity", "negative_infinity"],
)
def test_non_finite_auxiliary_field_is_rejected(
    field: str,
    invalid_value: Decimal,
) -> None:
    with pytest.raises(
        ValueError,
        match=f"MarketSnapshot {field} must be finite",
    ):
        _snapshot_with(**{field: invalid_value})


@pytest.mark.parametrize("field", _BOOLEAN_FIELDS)
@pytest.mark.parametrize("value", [True, False], ids=["true", "false"])
def test_boolean_flag_accepts_bool(field: str, value: bool) -> None:
    snapshot = _snapshot_with(**{field: value})

    assert getattr(snapshot, field) is value


@pytest.mark.parametrize("field", _BOOLEAN_FIELDS)
@pytest.mark.parametrize("value", [0, 1], ids=["int_zero", "int_one"])
def test_boolean_flag_rejects_integers(field: str, value: int) -> None:
    with pytest.raises(
        TypeError,
        match=f"MarketSnapshot {field} must be a bool",
    ):
        _snapshot_with(**{field: value})


@pytest.mark.parametrize("field", _BOOLEAN_FIELDS)
@pytest.mark.parametrize(
    "value",
    ["true", None, 0.0, 1.0],
    ids=["str", "none", "float_zero", "float_one"],
)
def test_boolean_flag_rejects_non_boolean(field: str, value: Any) -> None:
    with pytest.raises(
        TypeError,
        match=f"MarketSnapshot {field} must be a bool",
    ):
        _snapshot_with(**{field: value})


def test_index_levels_are_defensively_copied_from_original_mapping() -> None:
    source = {_ASSET: Decimal("100")}
    snapshot = _snapshot_with(index_levels=source)

    source[_ASSET] = Decimal("999")

    assert snapshot.index_levels[_ASSET] == Decimal("100")


def test_index_levels_cannot_be_mutated_through_exposed_mapping() -> None:
    snapshot = _snapshot()
    levels: Any = snapshot.index_levels

    with pytest.raises(TypeError):
        levels[_ASSET] = Decimal("1")
    with pytest.raises(AttributeError):
        levels.update({_ASSET: Decimal("1")})
    with pytest.raises(TypeError):
        del levels[_ASSET]

    assert snapshot.index_levels[_ASSET] == Decimal("100")


def test_index_levels_support_mapping_interface() -> None:
    bond = AssetClass(id="bond", name="Bond", description="")
    source = {_ASSET: Decimal("100"), bond: Decimal("50")}
    snapshot = _snapshot_with(index_levels=source)

    levels = snapshot.index_levels

    assert levels[_ASSET] == Decimal("100")
    assert _ASSET in levels
    assert set(levels) == {_ASSET, bond}
    assert levels.get(bond) == Decimal("50")
    assert levels.get(AssetClass(id="missing", name="", description="")) is None
    assert set(levels.items()) == {
        (_ASSET, Decimal("100")),
        (bond, Decimal("50")),
    }
    assert dict(levels) == source


def test_equivalent_snapshots_compare_equal() -> None:
    first = _snapshot_with(index_levels={_ASSET: Decimal("100")})
    second = _snapshot_with(index_levels={_ASSET: Decimal("100")})

    assert first == second


def test_getstate_does_not_expose_original_mapping() -> None:
    snapshot = _snapshot_with(index_levels={_ASSET: Decimal("100")})

    state = snapshot.__getstate__()
    state["index_levels"][_ASSET] = Decimal("999")

    assert snapshot.index_levels[_ASSET] == Decimal("100")


def test_pickle_round_trip_preserves_equality_and_immutability() -> None:
    original = _snapshot_with(index_levels={_ASSET: Decimal("100")})

    restored = pickle.loads(pickle.dumps(original))

    assert restored == original
    assert isinstance(restored.index_levels, MappingProxyType)
    levels: Any = restored.index_levels
    with pytest.raises(TypeError):
        levels[_ASSET] = Decimal("1")


def test_deepcopy_preserves_equality_and_immutability() -> None:
    original = _snapshot_with(index_levels={_ASSET: Decimal("100")})

    restored = copy.deepcopy(original)

    assert restored == original
    assert isinstance(restored.index_levels, MappingProxyType)
    levels: Any = restored.index_levels
    with pytest.raises(TypeError):
        levels[_ASSET] = Decimal("1")


def test_setstate_revalidates_reconstructed_state() -> None:
    snapshot = _snapshot()
    invalid_state = snapshot.__getstate__()
    invalid_state["index_levels"] = {_ASSET: Decimal("-1")}

    restored = object.__new__(MarketSnapshot)
    with pytest.raises(
        ValueError,
        match="MarketSnapshot index_levels values must be non-negative",
    ):
        restored.__setstate__(invalid_state)
