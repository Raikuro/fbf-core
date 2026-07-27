"""Serializers for persistence."""

import json
from decimal import Decimal
from typing import Any, Mapping

JSONScalar = None | bool | int | float | str

def serialize_decimal(value: Decimal) -> str:
    return str(value)

def deserialize_decimal(value: str) -> Decimal:
    return Decimal(value)

def deserialize_parameter_config(value: str) -> Any:
    return from_canonical_json(value)

def deserialize_portfolio(value: str) -> Any:
    return from_canonical_json(value)

def serialize_parameter_config(value: Any) -> str:
    return to_canonical_json(value)

def serialize_policy(value: Any) -> str:
    return to_canonical_json(value)

def serialize_portfolio(value: Any) -> str:
    return to_canonical_json(value)

def to_canonical_json(data: Mapping[str, Any]) -> str:
    # Use sort_keys=True, separators=(',', ':')
    return json.dumps(data, sort_keys=True, separators=(',', ':'))

def from_canonical_json(data: str) -> dict[str, Any]:
    result = json.loads(data)
    assert isinstance(result, dict)
    return result
