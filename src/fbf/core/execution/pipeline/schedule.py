"""Execution scheduling abstraction for controlling step cadence.

This module provides the StepCadence enum and ExecutionSchedule class that
allow fine-grained control over when pipeline steps execute.

The default behavior (no schedule or EVERY_PERIOD cadence) preserves all
existing monthly execution semantics.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fbf.core.execution.pipeline.pipeline import PipelineStep


class StepCadence(Enum):
    """Cadence at which a pipeline step executes.

    EVERY_PERIOD — executes every monthly period (existing default behavior)
    ANNUAL — executes only at annual boundaries (period_index % 12 == 0)
    """

    EVERY_PERIOD = "every_period"
    ANNUAL = "annual"


class ExecutionSchedule:
    """Controls the execution cadence of pipeline steps.

    An ExecutionSchedule maps pipeline step types to their cadence.
    Steps not in the map default to EVERY_PERIOD (monthly execution).

    The schedule is consulted by SimulationRunner.run() before executing
    each step. It does not change the pipeline order or step semantics.
    """

    def __init__(
        self,
        step_cadences: dict[type[PipelineStep], StepCadence] | None = None,
    ) -> None:
        self._step_cadences: dict[type[PipelineStep], StepCadence] = (
            step_cadences.copy() if step_cadences else {}
        )

    def get_cadence(self, step_type: type[PipelineStep]) -> StepCadence:
        """Get the cadence for a step type.

        Returns EVERY_PERIOD if no explicit cadence is configured.
        """
        return self._step_cadences.get(step_type, StepCadence.EVERY_PERIOD)

    def should_execute(
        self, step_type: type[PipelineStep], period_index: int
    ) -> bool:
        """Determine if a step should execute at the given period index.

        Parameters
        ----------
        step_type:
            The type of the pipeline step.
        period_index:
            The current simulation period index (0-based).

        Returns
        -------
        bool
            True if the step should execute, False otherwise.
        """
        cadence = self.get_cadence(step_type)
        if cadence == StepCadence.EVERY_PERIOD:
            return True
        if cadence == StepCadence.ANNUAL:
            return period_index % 12 == 0
        return False
