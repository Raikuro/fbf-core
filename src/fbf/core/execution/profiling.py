"""Execution profiling infrastructure.

Provides a ``Profiler`` protocol and several implementations:

- ``NoOpProfiler``: zero overhead, used by default.
- ``ExecutionProfiler``: collects wall-clock timings and execution statistics.
- ``CpuProfiler``: optional cProfile integration for CPU hotspot analysis.
- ``MemoryProfiler``: optional process RSS tracking.
- ``CompositeProfiler``: orchestrates wall-clock, CPU, and memory profiling.

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
                   (optionally composed with CpuProfiler, MemoryProfiler)

Nested Phases
-------------
The ``ExecutionProfiler`` supports nested phase timing via a stack-based
approach.  When ``start("A")`` is called, then ``start("B")``, ``stop("B")``
finishes the inner phase before ``stop("A")`` finishes the outer phase.
The ``phase_timings`` property returns the flat ordered list (backward
compatible), while ``nested_report`` returns the full tree.
"""

from __future__ import annotations

import cProfile
import io
import pstats
import resource
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


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


@dataclass(frozen=True)
class NestedPhaseTiming:
    """Hierarchical timing for a single execution phase with optional children.

    Attributes
    ----------
    phase:
        The phase name.
    elapsed_seconds:
        Wall-clock seconds for this phase (inclusive of children).
    cpu_seconds:
        CPU seconds for this phase, or ``None`` when CPU profiling is not
        active.
    peak_rss_bytes:
        Peak resident set size in bytes at the end of this phase, or ``None``
        when memory profiling is not active.
    children:
        Ordered child phases nested within this phase.
    count:
        Number of times this phase was entered (for call-count semantics).
    """

    phase: str
    elapsed_seconds: float
    cpu_seconds: float | None = None
    peak_rss_bytes: int | None = None
    children: tuple[NestedPhaseTiming, ...] = ()
    count: int = 1


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


def _format_nested_tree(
    timings: tuple[NestedPhaseTiming, ...],
    lines: list[str],
    indent: int = 0,
    parent_fraction: float = 1.0,
) -> None:
    """Recursively format nested phase timings as an indented tree."""
    prefix = "  " * indent
    connector = "├── " if indent > 0 else ""
    for t in timings:
        fraction = (t.elapsed_seconds / parent_fraction * 100) if parent_fraction > 0 else 0
        rss_info = ""
        if t.peak_rss_bytes is not None:
            rss_mib = t.peak_rss_bytes / (1024 * 1024)
            rss_info = f"  [RSS {rss_mib:.1f} MiB]"
        cpu_info = ""
        if t.cpu_seconds is not None:
            cpu_info = f"  [CPU {t.cpu_seconds:.4f}s]"
        count_info = f"  (×{t.count})" if t.count > 1 else ""

        lines.append(
            f"{prefix}{connector}{t.phase:<35s} "
            f"{t.elapsed_seconds:>10.4f}s "
            f"({fraction:>5.1f}%){cpu_info}{rss_info}{count_info}"
        )
        if t.children:
            _format_nested_tree(t.children, lines, indent + 1, t.elapsed_seconds)


@dataclass
class EnhancedProfileReport:
    """Enhanced profiling report with hierarchical phase tree and metadata.

    Attributes
    ----------
    root_phases:
        Top-level phases forming the root of the timing tree.
    metrics:
        Scalar metrics keyed by name.
    environment:
        Metadata about the profiling environment (Python version, platform, etc.).
    """

    root_phases: tuple[NestedPhaseTiming, ...] = ()
    metrics: dict[str, int | float] = field(default_factory=dict)
    environment: dict[str, str] = field(default_factory=dict)

    @property
    def total_seconds(self) -> float:
        """Total wall-clock time across all root phases."""
        return sum(t.elapsed_seconds for t in self.root_phases)

    def format(self) -> str:
        """Format the report as a hierarchical human-readable tree."""
        lines: list[str] = []
        lines.append("=" * 72)
        lines.append("EXECUTION PROFILE (HIERARCHICAL)")
        lines.append("=" * 72)

        if self.environment:
            lines.append("\nEnvironment:")
            for key, value in self.environment.items():
                lines.append(f"  {key}: {value}")

        if self.root_phases:
            lines.append("\nPhase Tree:")
            _format_nested_tree(self.root_phases, lines)
            lines.append(f"\n  {'TOTAL':<35s}  {self.total_seconds:>10.4f}s")

        if self.metrics:
            lines.append("\nMetrics:")
            max_key = max(len(k) for k in self.metrics)
            for metric_name, metric_value in self.metrics.items():
                if isinstance(metric_value, float):
                    lines.append(f"  {metric_name:<{max_key}}  {metric_value:>10.4f}")
                else:
                    lines.append(f"  {metric_name:<{max_key}}  {metric_value:>10,}")

        lines.append("=" * 72)
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the report to a JSON-compatible dictionary."""
        return {
            "total_seconds": self.total_seconds,
            "environment": self.environment,
            "metrics": self.metrics,
            "phases": [_nested_to_dict(t) for t in self.root_phases],
        }


def _nested_to_dict(t: NestedPhaseTiming) -> dict[str, Any]:
    """Convert a NestedPhaseTiming to a JSON-compatible dict."""
    d: dict[str, Any] = {
        "phase": t.phase,
        "elapsed_seconds": t.elapsed_seconds,
        "count": t.count,
    }
    if t.cpu_seconds is not None:
        d["cpu_seconds"] = t.cpu_seconds
    if t.peak_rss_bytes is not None:
        d["peak_rss_bytes"] = t.peak_rss_bytes
    if t.children:
        d["children"] = [_nested_to_dict(c) for c in t.children]
    return d


def _collect_phase_timings_flat(
    timings: tuple[NestedPhaseTiming, ...],
) -> list[PhaseTiming]:
    """Flatten nested phase timings to a list of PhaseTiming."""
    flat: list[PhaseTiming] = []
    for t in timings:
        flat.append(PhaseTiming(phase=t.phase, elapsed_seconds=t.elapsed_seconds))
        flat.extend(_collect_phase_timings_flat(t.children))
    return flat


class ExecutionProfiler:
    """Profiler that collects wall-clock timings, nested phases, and scalar metrics.

    Supports nested phase timing: ``start("A")`` followed by ``start("B")``
    creates a parent-child relationship.  ``stop("B")`` finishes the inner
    phase, then ``stop("A")`` finishes the outer phase.

    Usage::

        profiler = ExecutionProfiler()
        profiler.start("total")
        profiler.start("planning")
        # ... planning ...
        profiler.stop("planning")
        profiler.start("execution")
        # ... execution ...
        profiler.stop("execution")
        profiler.stop("total")
        profiler.record("groups", 42)
        report = profiler.get_report()
    """

    __slots__ = (
        "_starts",
        "_timings",
        "_metrics",
        "_open_phases",
        "_children_map",
        "_root_children",
    )

    def __init__(self) -> None:
        self._starts: dict[str, float] = {}
        self._timings: list[PhaseTiming] = []
        self._metrics: dict[str, int | float] = {}
        # Names of currently open phases in start order (LIFO stack)
        self._open_phases: list[str] = []
        # Children collected for each phase name (id -> children)
        self._children_map: dict[str, list[NestedPhaseTiming]] = {}
        # Children collected for root-level phases
        self._root_children: list[NestedPhaseTiming] = []

    def start(self, phase: str) -> None:
        """Begin timing a named phase."""
        self._starts[phase] = time.perf_counter()
        self._open_phases.append(phase)

    def stop(self, phase: str) -> None:
        """End timing a named phase and record the elapsed time."""
        start = self._starts.pop(phase, None)
        if start is not None:
            elapsed = time.perf_counter() - start
            self._timings.append(PhaseTiming(phase=phase, elapsed_seconds=elapsed))

            # Remove phase from the open stack
            for i in range(len(self._open_phases) - 1, -1, -1):
                if self._open_phases[i] == phase:
                    self._open_phases.pop(i)
                    break

            # Collect any children that were completed between this phase's
            # start and stop.  Children are phases that were opened and closed
            # while this phase was the topmost open phase.
            children = self._children_map.pop(phase, [])
            node = NestedPhaseTiming(
                phase=phase,
                elapsed_seconds=elapsed,
                children=tuple(children),
            )

            # Attach to parent or root
            if self._open_phases:
                parent_name = self._open_phases[-1]
                if parent_name not in self._children_map:
                    self._children_map[parent_name] = []
                self._children_map[parent_name].append(node)
            else:
                self._root_children.append(node)

    def record(self, key: str, value: int | float) -> None:
        """Record a scalar metric."""
        self._metrics[key] = value

    @property
    def phase_timings(self) -> list[PhaseTiming]:
        """Flat ordered list of phase timings (backward compatible)."""
        return list(self._timings)

    @property
    def nested_report(self) -> EnhancedProfileReport:
        """Hierarchical phase tree report."""
        import platform

        return EnhancedProfileReport(
            root_phases=tuple(self._root_children),
            metrics=dict(self._metrics),
            environment={
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "implementation": platform.python_implementation(),
            },
        )

    def get_report(self) -> ProfileReport:
        """Return the collected profiling report (backward compatible)."""
        return ProfileReport(
            phase_timings=list(self._timings),
            metrics=dict(self._metrics),
        )


class CpuProfiler:
    """Optional cProfile integration for CPU hotspot analysis.

    When enabled, wraps execution in a ``cProfile.Profile`` and captures
    CPU time distribution.  Disabled by default — pass ``enabled=True``
    to activate.

    Usage::

        cpu = CpuProfiler(enabled=True)
        cpu.enable()
        # ... execution ...
        cpu.disable()
        stats = cpu.get_stats()
    """

    __slots__ = ("_enabled", "_profile", "_is_running")

    def __init__(self, enabled: bool = False) -> None:
        self._enabled = enabled
        self._profile: cProfile.Profile | None = None
        self._is_running = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        """Start CPU profiling."""
        if self._enabled and not self._is_running:
            self._profile = cProfile.Profile()
            self._profile.enable()
            self._is_running = True

    def disable(self) -> None:
        """Stop CPU profiling."""
        if self._is_running and self._profile is not None:
            self._profile.disable()
            self._is_running = False

    def get_stats(self) -> pstats.Stats | None:
        """Return pstats.Stats for the profiled section, or None if disabled."""
        if self._profile is None:
            return None
        stream = io.StringIO()
        stats = pstats.Stats(self._profile, stream=stream)
        return stats

    def format_stats(self, top_n: int = 20) -> str:
        """Format the top N CPU hotspots as a human-readable string."""
        if self._profile is None:
            return "CPU profiling not active"
        stream = io.StringIO()
        stats = pstats.Stats(self._profile, stream=stream)
        stats.sort_stats("cumulative")
        stats.print_stats(top_n)
        return stream.getvalue()


class MemoryProfiler:
    """Optional process RSS tracking using resource.getrusage().

    Captures peak RSS at points of interest.  On Linux, also reads
    /proc/self/status for VmRSS when available.

    Usage::

        mem = MemoryProfiler(enabled=True)
        mem.snapshot("before_work")
        # ... work ...
        mem.snapshot("after_work")
        report = mem.get_report()
    """

    __slots__ = ("_enabled", "_snapshots", "_start_rss_bytes")

    def __init__(self, enabled: bool = False) -> None:
        self._enabled = enabled
        self._snapshots: list[tuple[str, int]] = []
        self._start_rss_bytes: int | None = None
        if enabled:
            self._start_rss_bytes = _get_peak_rss_bytes()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def snapshot(self, label: str) -> None:
        """Record a memory snapshot with the given label."""
        if self._enabled:
            rss = _get_peak_rss_bytes()
            self._snapshots.append((label, rss))

    def get_peak_rss_bytes(self) -> int | None:
        """Return peak RSS in bytes, or None if disabled."""
        if not self._enabled or not self._snapshots:
            return None
        return max(rss for _, rss in self._snapshots)

    def get_current_rss_bytes(self) -> int | None:
        """Return current RSS in bytes, or None if disabled."""
        if not self._enabled:
            return None
        return _get_current_rss_bytes()

    def get_report(self) -> dict[str, Any]:
        """Return memory profiling data."""
        if not self._enabled:
            return {}
        peak = self.get_peak_rss_bytes()
        return {
            "enabled": True,
            "peak_rss_bytes": peak,
            "peak_rss_mib": peak / (1024 * 1024) if peak is not None else None,
            "start_rss_bytes": self._start_rss_bytes,
            "snapshots": [
                {"label": label, "rss_bytes": rss}
                for label, rss in self._snapshots
            ],
        }


def _get_peak_rss_bytes() -> int:
    """Get peak RSS in bytes from the operating system."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # ru_maxrss is in KB on Linux, bytes on macOS
    if sys.platform == "linux":
        return usage.ru_maxrss * 1024
    return usage.ru_maxrss


def _get_current_rss_bytes() -> int:
    """Get current RSS in bytes. Falls back to peak RSS on unsupported platforms."""
    if sys.platform == "linux":
        try:
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) * 1024
        except (OSError, ValueError, IndexError):
            pass
    # Fallback: use peak RSS (not ideal, but available)
    return _get_peak_rss_bytes()


class CompositeProfiler:
    """Orchestrates wall-clock, CPU, and memory profiling.

    Implements the ``Profiler`` protocol and delegates to the individual
    profiler components.  The wall-clock profiler is always active; CPU
    and memory profilers are opt-in.

    Usage::

        profiler = CompositeProfiler(
            wall_clock=True,
            cpu_profiling=True,
            memory_profiling=True,
        )
        profiler.start("total")
        # ... execution ...
        profiler.stop("total")
        report = profiler.get_report()
        enhanced = profiler.get_enhanced_report()
    """

    __slots__ = (
        "_wall_clock",
        "_cpu",
        "_memory",
        "_cpu_enabled",
        "_memory_enabled",
    )

    def __init__(
        self,
        wall_clock: bool = True,
        cpu_profiling: bool = False,
        memory_profiling: bool = False,
    ) -> None:
        self._wall_clock = ExecutionProfiler() if wall_clock else None
        self._cpu = CpuProfiler(enabled=cpu_profiling)
        self._memory = MemoryProfiler(enabled=memory_profiling)
        self._cpu_enabled = cpu_profiling
        self._memory_enabled = memory_profiling

    def start(self, phase: str) -> None:
        """Begin timing a named phase."""
        if self._wall_clock is not None:
            self._wall_clock.start(phase)
        if self._cpu_enabled:
            self._cpu.enable()
        if self._memory_enabled:
            self._memory.snapshot(f"{phase}_start")

    def stop(self, phase: str) -> None:
        """End timing a named phase."""
        if self._memory_enabled:
            self._memory.snapshot(f"{phase}_end")
        if self._cpu_enabled:
            self._cpu.disable()
        if self._wall_clock is not None:
            self._wall_clock.stop(phase)

    def record(self, key: str, value: int | float) -> None:
        """Record a scalar metric."""
        if self._wall_clock is not None:
            self._wall_clock.record(key, value)

    def get_report(self) -> ProfileReport:
        """Return the collected profiling report (backward compatible)."""
        if self._wall_clock is not None:
            return self._wall_clock.get_report()
        return ProfileReport()

    def get_enhanced_report(self) -> EnhancedProfileReport:
        """Return the enhanced hierarchical profiling report."""
        wall_report = (
            self._wall_clock.nested_report
            if self._wall_clock is not None
            else EnhancedProfileReport()
        )
        # Enrich with CPU and memory data
        cpu_stats = self._cpu.format_stats() if self._cpu_enabled else None
        memory_data = self._memory.get_report() if self._memory_enabled else None

        metrics = dict(wall_report.metrics)
        if cpu_stats is not None:
            metrics["cpu_profiling"] = 1
        if memory_data is not None:
            peak = memory_data.get("peak_rss_bytes")
            if peak is not None:
                metrics["peak_rss_bytes"] = peak
                metrics["peak_rss_mib"] = memory_data["peak_rss_mib"]

        return EnhancedProfileReport(
            root_phases=wall_report.root_phases,
            metrics=metrics,
            environment=wall_report.environment,
        )
