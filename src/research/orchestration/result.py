"""Research execution result value object.

Contains ``ResearchExecutionResult`` — the minimal, immutable orchestration output
returned by ``ResearchExecutor`` after delegating a ``ResearchPlan`` to the engine.

Provenance is maintained by index alignment:
    plan.units[i] corresponds to experiment_result.simulation_results[i]
for all 0 ≤ i < len(plan).

Callers requiring paired iteration can write:
    zip(result.plan.units, result.results)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from engine.application.simulation import ExperimentRun, SimulationResult
from research.domain.plan import ResearchPlan

if TYPE_CHECKING:
    pass


@dataclass(frozen=True, slots=True)
class ResearchExecutionResult:
    """Lossless execution result maintaining direct 1-to-1 index provenance.

    Fields
    ------
    plan:
        The immutable ``ResearchPlan`` that was executed. Preserved unmodified.
    experiment_result:
        The ``ExperimentRun`` returned by ``SimulationExecutor``. Contains the
        ordered tuple of individual ``SimulationResult`` objects produced by the
        frozen v0.1 engine.

    Invariant
    ---------
    ``len(plan.units) == len(experiment_result.simulation_results)``

    The caller may iterate provenance pairs via:
        ``zip(result.plan.units, result.results)``
    """

    plan: ResearchPlan
    experiment_result: ExperimentRun

    def __post_init__(self) -> None:
        if self.plan is None:
            raise ValueError("ResearchExecutionResult.plan cannot be None")
        if self.experiment_result is None:
            raise ValueError("ResearchExecutionResult.experiment_result cannot be None")
        if len(self.plan.units) != len(self.experiment_result.simulation_results):
            raise ValueError(
                f"Mismatch between plan units ({len(self.plan.units)}) and "
                f"engine results ({len(self.experiment_result.simulation_results)})"
            )

    @property
    def results(self) -> tuple[SimulationResult, ...]:
        """Ordered tuple of individual engine SimulationResults matching plan.units.

        ``results[i]`` is the outcome of executing ``plan.units[i]``.
        """
        return self.experiment_result.simulation_results
