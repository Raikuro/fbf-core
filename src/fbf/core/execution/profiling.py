"""Execution profiling infrastructure.

Provides a ``Profiler`` protocol and two implementations:

- ``NoOpProfiler``: zero overhead, used by default.
- ``ExecutionProfiler``: collects wall-clock timings and execution statistics.

The profiler is resolved **once** at the execution boundary (``ExecutionOptions``)
and propagated to executors.  Normal execution uses ``NoOpProfiler`` which has
negligible overhead — the method calls are effectively free because the Python
interpreter can inline trivial no-op methods.

Architecture::

    CLI / Consumer
         │
         └── ExecutionOptions(profiler=...)
               │
               ▼
         execute_study_plan / sequential_execute / parallel_execute
               │
               ▼
         ResearchExecutor / SimulationExecutor
               │
               ├── NoOpProfiler → no-op (zero overhead)
               │
               └── ExecutionProfiler → collects timings
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@runtime_checkable
class Profiler(Protocol):
    """Protocol for execution profilers.

    A profiler records timing and metadata at well-defined execution phases.
    The ``NoOpProfiler`` satisfies this protocol with zero overhead.
    """

    def start(self, phase: str) -> None:
        """Begin timing a named phase."""
        ...

    def stop(self, phase: str) -> None:
        """End timing a named phase."""
        ...

    def record(self, key: str, value: int | float) -> None:
        """Record a scalar metric (e.g., group count, cache hits)."""
        ...

    def get_report(self) -> ProfileReport:
        """Return the collected profiling report."""
        ...


class NoOpProfiler:
    """Profiler with zero overhead for normal execution.

    All methods are no-ops.  The Python interpreter can inline these,
    making the overhead negligible (a single method dispatch per call).
    """

    __slots__ = ()

    def start(self, phase: str) -> None:
        pass

    def stop(self, phase: str) -> None:
        pass

    def record(self, key: str, value: int | float) -> None:
        pass

    def get_report(self) -> ProfileReport:
        return ProfileReport()


@dataclass(frozen=True)
class PhaseTiming:
    """Wall-clock timing for a single execution phase."""

    phase: str
    elapsed_seconds: float


@dataclass
class ProfileReport:
    """Collected profiling data from an execution run.

    Attributes
    ----------
    phase_timings:
        Ordered list of phase timings (wall-clock seconds).
    metrics:
        Scalar metrics keyed by name (e.g., ``"groups"``, ``"gf_cache_hits"``).
    """

    phase_timings: list[PhaseTiming] = field(default_factory=list)
    metrics: dict[str, int | float] = field(default_factory=dict)

    @property
    def total_seconds(self) -> float:
        """Total wall-clock time across all recorded phases."""
        return sum(t.elapsed_seconds for t in self.phase_timings)

    def phase_seconds(self, phase: str) -> float:
        """Return wall-clock seconds for a specific phase, or 0.0 if not found."""
        for t in self.phase_timings:
            if t.phase == phase:
                return t.elapsed_seconds
        return 0.0

    def format(self) -> str:
        """Format the report as human-readable text."""
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append("EXECUTION PROFILE")
        lines.append("=" * 60)

        if self.phase_timings:
            lines.append("\nPhase Timings:")
            max_label = max(len(t.phase) for t in self.phase_timings)
            for t in self.phase_timings:
                lines.append(f"  {t.phase:<{max_label}}  {t.elapsed_seconds:>10.4f}s")
            lines.append(f"  {'TOTAL':<{max_label}}  {self.total_seconds:>10.4f}s")

        if self.metrics:
            lines.append("\nMetrics:")
            max_key = max(len(k) for k in self.metrics)
            for key, value in self.metrics.items():
                if isinstance(value, float):
                    lines.append(f"  {key:<{max_key}}  {value:>10.4f}")
                else:
                    lines.append(f"  {key:<{max_key}}  {value:>10,}")

        lines.append("=" * 60)
        return "\n".join(lines)


class ExecutionProfiler:
    """Profiler that collects wall-clock timings and scalar metrics.

    Usage::

        profiler = ExecutionProfiler()
        profiler.start("total")
        # ... execution ...
        profiler.stop("total")
        profiler.record("groups", 42)
        report = profiler.get_report()
    """

    __slots__ = ("_starts", "_timings", "_metrics")

    def __init__(self) -> None:
        self._starts: dict[str, float] = {}
        self._timings: list[PhaseTiming] = []
        self._metrics: dict[str, int | float] = {}

    def start(self, phase: str) -> None:
        """Begin timing a named phase."""
        self._starts[phase] = time.perf_counter()

    def stop(self, phase: str) -> None:
        """End timing a named phase and record the elapsed time."""
        start = self._starts.pop(phase, None)
        if start is not None:
            elapsed = time.perf_counter() - start
            self._timings.append(PhaseTiming(phase=phase, elapsed_seconds=elapsed))

    def record(self, key: str, value: int | float) -> None:
        """Record a scalar metric."""
        self._metrics[key] = value

    def get_report(self) -> ProfileReport:
        """Return the collected profiling report."""
        return ProfileReport(
            phase_timings=list(self._timings),
            metrics=dict(self._metrics),
        )
