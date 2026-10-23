"""Execution scheduling abstraction for controlling step cadence.

This module provides the StepCadence enum and ExecutionSchedule class that
allow fine-grained control over when pipeline steps execute.

The default behavior (no schedule or EVERY_PERIOD cadence) preserves all
existing monthly execution semantics.
"""

from __future__ import annotations

from enum import Enum

# The rebalance cadence is configured under this key.  It is intentionally not
# tied to a pipeline step class: the optimized executor is the only consumer.
_REBALANCE_STEP = "rebalance"


class StepCadence(Enum):
    """Cadence at which a pipeline step executes.

    EVERY_PERIOD — executes every monthly period (existing default behavior)
    ANNUAL — executes only at annual boundaries (period_index % 12 == 0)
    """

    EVERY_PERIOD = "every_period"
    ANNUAL = "annual"


class ExecutionSchedule:
    """Controls the execution cadence of scheduled simulation behavior.

    An ExecutionSchedule maps a step key to its cadence.  Keys not in the map
    default to EVERY_PERIOD (monthly execution).  The optimized deterministic
    executor consults only the rebalance cadence.

    The rebalance helpers (:meth:`explicit_rebalance_cadence`,
    :meth:`rebalance_cadence`, and :meth:`with_rebalance_cadence`) let
    deterministic callers configure rebalance cadence without importing any
    pipeline implementation.
    """

    def __init__(
        self,
        step_cadences: dict[object, StepCadence] | None = None,
    ) -> None:
        self._step_cadences: dict[object, StepCadence] = (
            step_cadences.copy() if step_cadences else {}
        )

    def get_cadence(self, step_type: object) -> StepCadence:
        """Get the cadence for a step key.

        Returns EVERY_PERIOD if no explicit cadence is configured.
        """
        return self._step_cadences.get(step_type, StepCadence.EVERY_PERIOD)

    def explicit_rebalance_cadence(self) -> StepCadence | None:
        """Return the explicitly configured rebalance cadence, if any."""
        return self._step_cadences.get(_REBALANCE_STEP)

    def rebalance_cadence(self) -> StepCadence:
        """Return the effective rebalance cadence.

        Returns EVERY_PERIOD when the rebalance entry is absent.
        """
        return self.explicit_rebalance_cadence() or StepCadence.EVERY_PERIOD

    def with_rebalance_cadence(self, cadence: StepCadence) -> ExecutionSchedule:
        """Return a copy with the rebalance entry configured to *cadence*."""
        updated = dict(self._step_cadences)
        updated[_REBALANCE_STEP] = cadence
        return ExecutionSchedule(updated)

    def custom_non_rebalance_cadences(self) -> tuple[tuple[str, StepCadence], ...]:
        """Return non-default cadences configured for non-rebalance entries.

        Deterministic execution only supports rebalance cadence. These entries
        are reported so unsupported configurations are rejected explicitly.
        """
        return tuple(
            (
                step_type.__name__
                if isinstance(step_type, type)
                else str(step_type),
                cadence,
            )
            for step_type, cadence in self._step_cadences.items()
            if step_type != _REBALANCE_STEP
            and cadence is not StepCadence.EVERY_PERIOD
        )

    def should_execute(self, step_type: object, period_index: int) -> bool:
        """Determine if a step should execute at the given period index.

        Parameters
        ----------
        step_type:
            The step key.
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
