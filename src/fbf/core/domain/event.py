from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class SimulationEvent:
    """Immutable event generated during a Simulation.

    Responsibilities:
    - represent a factual occurrence in the simulation timeline

    Invariants:
    - event payload is immutable
    """

    date: date
    type: str
    payload: dict[str, Any] | None = None
