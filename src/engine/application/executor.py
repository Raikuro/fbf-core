from __future__ import annotations

from engine.application.simulation import ExperimentRun


class SimulationExecutor:
    """Coordinates execution of multiple simulations for an ExperimentRun."""

    def execute(self, run: ExperimentRun) -> None:
        raise NotImplementedError
