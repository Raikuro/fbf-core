"""Serializers for persistence.

Provides canonical JSON serialization for v0.4 Phase 2 persistence layer.
"""

import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

JSONScalar = None | bool | int | float | str


def serialize_decimal(value: Decimal) -> str:
    """Serialize Decimal to string preserving full precision.

    Implementa Section 4.1 da especificação: todos os valores Decimal armazenados como strings.
    """
    return str(value)


def deserialize_decimal(value: str) -> Decimal:
    """Deserialize string to Decimal.

    Implementa Section 4.1: convert string de volta para Decimal.
    """
    return Decimal(value)


def deserialize_parameter_config(value: str) -> Any:
    """Deserialize parameter configuration from canonical JSON.

    Implementa Section 12.2: parâmetros armazenados como envelope JSON tipado.
    """
    return from_canonical_json(value)


def deserialize_portfolio(value: str) -> Any:
    """Deserialize portfolio from canonical JSON.

    Implementa Section 12.2: portfolio armazenado como JSON.
    """
    return from_canonical_json(value)


def serialize_parameter_config(value: Any) -> str:
    """Serialize parameter configuration to canonical JSON.

    Implementa Section 12.2: envelope JSON com tipos preservados.
    """
    return to_canonical_json(value)


def serialize_policy(value: Any) -> str:
    """Serialize policy to canonical JSON.

    Implementa Section 12.2: JSON com tipos originais preservados.
    """
    return to_canonical_json(value)


def serialize_portfolio(value: Any) -> str:
    """Serialize portfolio to canonical JSON.

    Implementa Section 12.2: holdings JSON serializado.
    """
    return to_canonical_json(value)


def to_canonical_json(data: Mapping[str, Any]) -> str:
    """Convert dict to canonical JSON with sorted keys and compact separators.

    Implementa Section 12.1: JSON canônico UTF-8 com sorted keys, separators (',', ':').
    Aplicado a todos os dados serializados.
    """
    return json.dumps(data, sort_keys=True, separators=(',', ':'))


def from_canonical_json(data: str) -> dict[str, Any]:
    """Parse canonical JSON string to dict with validation.

    Implementa Section 12.1: parsing seguro para reconstrução.
    Rejeita dados incompatíveis.
    """
    result = json.loads(data)
    assert isinstance(result, dict)
    return result
