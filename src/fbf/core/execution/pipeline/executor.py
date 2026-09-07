from __future__ import annotations

import time

from fbf.core.execution.pipeline.runner import SimulationRunner
from fbf.core.execution.pipeline.simulation import ExperimentDefinition, ExperimentRun


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

        t_start = time.perf_counter()
        results = tuple(
            self._simulation_runner.run(context)
            for context in definition.simulation_contexts
        )
        t_end = time.perf_counter()
        self._last_execution_seconds = t_end - t_start
        return ExperimentRun(definition=definition, simulation_results=results)
