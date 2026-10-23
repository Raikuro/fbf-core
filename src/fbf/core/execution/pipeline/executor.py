from __future__ import annotations

from abc import ABC, abstractmethod

from fbf.core.execution.pipeline.simulation import ExperimentDefinition, ExperimentRun


class SimulationExecutor(ABC):
    """Abstract simulation executor contract.

    Implementations execute every context in an ``ExperimentDefinition`` and
    return their immutable aggregate in the original order.
    """

    processes_whole_definition: bool = False

    @abstractmethod
    def execute(self, definition: ExperimentDefinition) -> ExperimentRun:
        """Execute every declared context and return their immutable aggregate."""
        raise NotImplementedError
