from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence, Tuple

from engine.application.simulation import SimulationState


class PipelineStep(ABC):
    """Abstract pipeline step for monthly simulation execution."""

    @abstractmethod
    def execute(self, state: SimulationState) -> SimulationState:
        raise NotImplementedError


class SimulationPipeline:
    """Ordered monthly simulation pipeline."""

    def __init__(self, steps: Sequence[PipelineStep]) -> None:
        self._steps = tuple(steps)
        self._validate_steps()

    @property
    def steps(self) -> Tuple[PipelineStep, ...]:
        return self._steps

    def _validate_steps(self) -> None:
        if not self._steps:
            raise ValueError("SimulationPipeline requires at least one PipelineStep")

        seen_types: set[type] = set()
        last_order = -1

        for step in self._steps:
            if not isinstance(step, PipelineStep):
                raise TypeError("All pipeline steps must implement PipelineStep")

            step_type = type(step)
            if step_type in seen_types:
                raise ValueError(f"Duplicate pipeline step type: {step_type.__name__}")
            seen_types.add(step_type)

            sequence_order = getattr(step, "sequence_order", None)
            if not isinstance(sequence_order, int):
                raise ValueError(
                    f"PipelineStep {step_type.__name__} must define an integer sequence_order"
                )

            if sequence_order <= last_order:
                raise ValueError(
                    "Pipeline steps must be provided in ascending sequence_order"
                )
            last_order = sequence_order

    def execute(self, state: SimulationState) -> SimulationState:
        for step in self._steps:
            state = step.execute(state)
        return state
