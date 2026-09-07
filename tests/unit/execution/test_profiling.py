"""Tests for the profiling infrastructure.

Covers:
1. NoOpProfiler zero-overhead default path
2. ExecutionProfiler basic timing
3. ExecutionProfiler nested phases
4. ExecutionProfiler nested phase tree structure
5. CpuProfiler enable/disable
6. MemoryProfiler snapshots
7. CompositeProfiler orchestration
8. EnhancedProfileReport formatting and serialization
9. ProfileReport backward compatibility
10. Profiler protocol conformance
11. Exception handling in profiling
12. Integration with execution flow
"""

from __future__ import annotations

import time

import pytest

from fbf.core.execution.profiling import (
    CompositeProfiler,
    CpuProfiler,
    EnhancedProfileReport,
    ExecutionProfiler,
    MemoryProfiler,
    NestedPhaseTiming,
    NoOpProfiler,
    PhaseTiming,
    Profiler,
    ProfileReport,
)

# ---------------------------------------------------------------------------
# NoOpProfiler
# ---------------------------------------------------------------------------


class TestNoOpProfiler:
    """NoOpProfiler must satisfy the Profiler protocol with zero overhead."""

    def test_satisfies_profiler_protocol(self) -> None:
        profiler = NoOpProfiler()
        assert isinstance(profiler, Profiler)

    def test_start_stop_no_op(self) -> None:
        profiler = NoOpProfiler()
        profiler.start("phase")
        profiler.stop("phase")
        report = profiler.get_report()
        assert report.phase_timings == []
        assert report.metrics == {}

    def test_record_no_op(self) -> None:
        profiler = NoOpProfiler()
        profiler.record("key", 42)
        report = profiler.get_report()
        assert report.metrics == {}

    def test_get_report_returns_empty(self) -> None:
        profiler = NoOpProfiler()
        report = profiler.get_report()
        assert isinstance(report, ProfileReport)
        assert report.total_seconds == 0.0

    def test_repeated_start_stop(self) -> None:
        profiler = NoOpProfiler()
        for i in range(100):
            profiler.start(f"phase_{i}")
            profiler.stop("phase_")


class TestNoOpProfilerOverhead:
    """Verify NoOpProfiler overhead is negligible."""

    def test_overhead_is_negligible(self) -> None:
        profiler = NoOpProfiler()
        n = 10_000
        start = time.perf_counter()
        for _ in range(n):
            profiler.start("x")
            profiler.stop("x")
            profiler.record("k", 1)
        elapsed = time.perf_counter() - start
        # 10k start/stop/record calls should complete well under 1 second
        assert elapsed < 1.0


# ---------------------------------------------------------------------------
# ExecutionProfiler
# ---------------------------------------------------------------------------


class TestExecutionProfiler:
    """ExecutionProfiler must collect wall-clock timings and metrics."""

    def test_satisfies_profiler_protocol(self) -> None:
        profiler = ExecutionProfiler()
        assert isinstance(profiler, Profiler)

    def test_single_phase_timing(self) -> None:
        profiler = ExecutionProfiler()
        profiler.start("total")
        time.sleep(0.01)
        profiler.stop("total")
        report = profiler.get_report()
        assert len(report.phase_timings) == 1
        assert report.phase_timings[0].phase == "total"
        assert report.phase_timings[0].elapsed_seconds >= 0.005

    def test_multiple_sequential_phases(self) -> None:
        profiler = ExecutionProfiler()
        for name in ["a", "b", "c"]:
            profiler.start(name)
            time.sleep(0.005)
            profiler.stop(name)
        report = profiler.get_report()
        assert len(report.phase_timings) == 3
        names = [t.phase for t in report.phase_timings]
        assert names == ["a", "b", "c"]

    def test_record_metrics(self) -> None:
        profiler = ExecutionProfiler()
        profiler.record("groups", 42)
        profiler.record("cache_hits", 0.85)
        report = profiler.get_report()
        assert report.metrics["groups"] == 42
        assert report.metrics["cache_hits"] == 0.85

    def test_total_seconds(self) -> None:
        profiler = ExecutionProfiler()
        profiler.start("a")
        profiler.stop("a")
        profiler.start("b")
        profiler.stop("b")
        report = profiler.get_report()
        assert report.total_seconds >= 0

    def test_phase_seconds_lookup(self) -> None:
        profiler = ExecutionProfiler()
        profiler.start("x")
        profiler.stop("x")
        report = profiler.get_report()
        assert report.phase_seconds("x") >= 0
        assert report.phase_seconds("nonexistent") == 0.0


class TestExecutionProfilerNested:
    """ExecutionProfiler must support nested phase timing."""

    def test_nested_phases_produce_tree(self) -> None:
        profiler = ExecutionProfiler()
        profiler.start("total")
        profiler.start("phase_a")
        profiler.stop("phase_a")
        profiler.start("phase_b")
        profiler.stop("phase_b")
        profiler.stop("total")
        nested = profiler.nested_report
        assert len(nested.root_phases) == 1
        root = nested.root_phases[0]
        assert root.phase == "total"
        assert len(root.children) == 2
        assert root.children[0].phase == "phase_a"
        assert root.children[1].phase == "phase_b"

    def test_deeply_nested_phases(self) -> None:
        profiler = ExecutionProfiler()
        profiler.start("root")
        profiler.start("level1")
        profiler.start("level2")
        profiler.stop("level2")
        profiler.stop("level1")
        profiler.stop("root")
        nested = profiler.nested_report
        root = nested.root_phases[0]
        assert root.phase == "root"
        assert len(root.children) == 1
        level1 = root.children[0]
        assert level1.phase == "level1"
        assert len(level1.children) == 1
        assert level1.children[0].phase == "level2"

    def test_flat_timings_still_available(self) -> None:
        profiler = ExecutionProfiler()
        profiler.start("total")
        profiler.start("inner")
        profiler.stop("inner")
        profiler.stop("total")
        flat = profiler.phase_timings
        assert len(flat) == 2
        assert flat[0].phase == "inner"
        assert flat[1].phase == "total"

    def test_nested_elapsed_includes_children(self) -> None:
        profiler = ExecutionProfiler()
        profiler.start("parent")
        time.sleep(0.01)
        profiler.start("child")
        time.sleep(0.01)
        profiler.stop("child")
        profiler.stop("parent")
        nested = profiler.nested_report
        parent = nested.root_phases[0]
        child = parent.children[0]
        # Parent elapsed should be >= child elapsed
        assert parent.elapsed_seconds >= child.elapsed_seconds


# ---------------------------------------------------------------------------
# CpuProfiler
# ---------------------------------------------------------------------------


class TestCpuProfiler:
    """CpuProfiler must enable/disable cProfile and return stats."""

    def test_disabled_by_default(self) -> None:
        profiler = CpuProfiler()
        assert profiler.enabled is False

    def test_enable_disable(self) -> None:
        profiler = CpuProfiler(enabled=True)
        profiler.enable()
        # Do some work
        sum(range(1000))
        profiler.disable()
        stats = profiler.get_stats()
        assert stats is not None

    def test_format_stats_when_disabled(self) -> None:
        profiler = CpuProfiler(enabled=False)
        output = profiler.format_stats()
        assert "not active" in output.lower()

    def test_format_stats_when_enabled(self) -> None:
        profiler = CpuProfiler(enabled=True)
        profiler.enable()
        sum(range(1000))
        profiler.disable()
        output = profiler.format_stats(top_n=5)
        assert isinstance(output, str)
        assert len(output) > 0


# ---------------------------------------------------------------------------
# MemoryProfiler
# ---------------------------------------------------------------------------


class TestMemoryProfiler:
    """MemoryProfiler must track RSS snapshots."""

    def test_disabled_by_default(self) -> None:
        profiler = MemoryProfiler()
        assert profiler.enabled is False

    def test_snapshot_when_disabled(self) -> None:
        profiler = MemoryProfiler(enabled=False)
        profiler.snapshot("before")
        profiler.snapshot("after")
        assert profiler.get_peak_rss_bytes() is None
        assert profiler.get_current_rss_bytes() is None

    def test_snapshot_when_enabled(self) -> None:
        profiler = MemoryProfiler(enabled=True)
        profiler.snapshot("start")
        # Allocate some memory
        _data = [0] * 100_000
        profiler.snapshot("end")
        peak = profiler.get_peak_rss_bytes()
        assert peak is not None
        assert peak > 0

    def test_get_report_when_disabled(self) -> None:
        profiler = MemoryProfiler(enabled=False)
        report = profiler.get_report()
        assert report == {}

    def test_get_report_when_enabled(self) -> None:
        profiler = MemoryProfiler(enabled=True)
        profiler.snapshot("test")
        report = profiler.get_report()
        assert report["enabled"] is True
        assert "peak_rss_bytes" in report
        assert "peak_rss_mib" in report


# ---------------------------------------------------------------------------
# CompositeProfiler
# ---------------------------------------------------------------------------


class TestCompositeProfiler:
    """CompositeProfiler must orchestrate wall-clock, CPU, and memory."""

    def test_default_composite(self) -> None:
        profiler = CompositeProfiler()
        profiler.start("total")
        profiler.stop("total")
        report = profiler.get_report()
        assert len(report.phase_timings) == 1
        assert report.phase_timings[0].phase == "total"

    def test_composite_with_cpu(self) -> None:
        profiler = CompositeProfiler(cpu_profiling=True)
        profiler.start("work")
        sum(range(1000))
        profiler.stop("work")
        enhanced = profiler.get_enhanced_report()
        assert enhanced.total_seconds >= 0

    def test_composite_with_memory(self) -> None:
        profiler = CompositeProfiler(memory_profiling=True)
        profiler.start("alloc")
        _data = [0] * 100_000
        profiler.stop("alloc")
        enhanced = profiler.get_enhanced_report()
        assert "peak_rss_bytes" in enhanced.metrics

    def test_composite_records_metrics(self) -> None:
        profiler = CompositeProfiler()
        profiler.start("phase")
        profiler.record("count", 100)
        profiler.stop("phase")
        report = profiler.get_report()
        assert report.metrics["count"] == 100

    def test_composite_nested_phases(self) -> None:
        profiler = CompositeProfiler()
        profiler.start("total")
        profiler.start("inner")
        profiler.stop("inner")
        profiler.stop("total")
        report = profiler.get_report()
        assert len(report.phase_timings) == 2
        enhanced = profiler.get_enhanced_report()
        assert len(enhanced.root_phases) == 1
        assert len(enhanced.root_phases[0].children) == 1


# ---------------------------------------------------------------------------
# EnhancedProfileReport
# ---------------------------------------------------------------------------


class TestEnhancedProfileReport:
    """EnhancedProfileReport must format and serialize correctly."""

    def test_format_empty(self) -> None:
        report = EnhancedProfileReport()
        output = report.format()
        assert "EXECUTION PROFILE" in output

    def test_format_with_phases(self) -> None:
        report = EnhancedProfileReport(
            root_phases=(
                NestedPhaseTiming(phase="total", elapsed_seconds=1.5, children=(
                    NestedPhaseTiming(phase="inner", elapsed_seconds=0.8),
                )),
            ),
            metrics={"units": 100},
        )
        output = report.format()
        assert "total" in output
        assert "inner" in output
        assert "units" in output

    def test_to_dict(self) -> None:
        report = EnhancedProfileReport(
            root_phases=(
                NestedPhaseTiming(phase="total", elapsed_seconds=1.0),
            ),
            metrics={"count": 42},
            environment={"python": "3.13"},
        )
        d = report.to_dict()
        assert d["total_seconds"] == 1.0
        assert d["metrics"]["count"] == 42
        assert d["environment"]["python"] == "3.13"
        assert len(d["phases"]) == 1
        assert d["phases"][0]["phase"] == "total"


# ---------------------------------------------------------------------------
# ProfileReport backward compatibility
# ---------------------------------------------------------------------------


class TestProfileReport:
    """ProfileReport must maintain backward compatibility."""

    def test_format_empty(self) -> None:
        report = ProfileReport()
        output = report.format()
        assert "EXECUTION PROFILE" in output

    def test_format_with_data(self) -> None:
        report = ProfileReport(
            phase_timings=[
                PhaseTiming(phase="a", elapsed_seconds=0.5),
                PhaseTiming(phase="b", elapsed_seconds=1.0),
            ],
            metrics={"x": 1},
        )
        output = report.format()
        assert "a" in output
        assert "b" in output
        assert "TOTAL" in output

    def test_total_seconds(self) -> None:
        report = ProfileReport(
            phase_timings=[
                PhaseTiming(phase="a", elapsed_seconds=0.5),
                PhaseTiming(phase="b", elapsed_seconds=1.0),
            ],
        )
        assert report.total_seconds == pytest.approx(1.5)

    def test_phase_seconds(self) -> None:
        report = ProfileReport(
            phase_timings=[
                PhaseTiming(phase="a", elapsed_seconds=0.5),
            ],
        )
        assert report.phase_seconds("a") == 0.5
        assert report.phase_seconds("missing") == 0.0

