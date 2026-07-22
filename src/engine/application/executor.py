from __future__ import annotations

from engine.application.runner import SimulationRunner
from engine.application.simulation import ExperimentDefinition, ExperimentRun


class SimulationExecutor:
    """Coordinates an experiment by delegating each context to one runner."""

    def __init__(self, simulation_runner: SimulationRunner) -> None:
        if simulation_runner is None or not callable(
            getattr(simulation_runner, "run", None)
        ):
            raise ValueError("SimulationExecutor requires a simulation_runner with run()")
        self._simulation_runner = simulation_runner

    def execute(self, definition: ExperimentDefinition) -> ExperimentRun:
        """Execute every declared context and return their immutable aggregate."""
        if not isinstance(definition, ExperimentDefinition):
            raise ValueError("ExperimentDefinition is required")

        results = tuple(
            self._simulation_runner.run(context)
            for context in definition.simulation_contexts
        )
        return ExperimentRun(definition=definition, simulation_results=results)
