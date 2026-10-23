# Profiling Infrastructure

This document describes the profiling and timing instrumentation available
in `fbf-core`. All profiling is **opt-in** and has zero overhead when
disabled.

## Quick Start

### Enable execution profiling

```python
from fbf.core import ExecutionOptions, ExecutionProfiler, execute_study_plan

options = ExecutionOptions.with_profiling()
result = execute_study_plan(built_study, options)
print(options.profiler.get_report().format())
```

### Enable nested profiling with CPU and memory

```python
from fbf.core import CompositeProfiler, ExecutionOptions, execute_study_plan

profiler = CompositeProfiler(
    wall_clock=True,
    cpu_profiling=True,
    memory_profiling=True,
)
options = ExecutionOptions(profiler=profiler)
result = execute_study_plan(built_study, options)
print(profiler.get_enhanced_report().format())
```

## Architecture

### Design Principles

1. **Zero overhead when disabled**: `NoOpProfiler` is the default; all
   method calls are no-ops that the Python interpreter inlines.

2. **Opt-in**: Profiling is activated only when an `ExecutionProfiler` or
   `CompositeProfiler` is explicitly passed via `ExecutionOptions`.

3. **No invasive conditionals**: The production code never contains
   `if profiling_enabled:` checks. The profiler is injected once at the
   execution boundary and propagated through the call chain.

4. **Hierarchical**: Nested `start`/`stop` calls automatically produce a
   timing tree.

### Class Hierarchy

```
Profiler (Protocol)
├── NoOpProfiler          # Zero overhead (default)
├── ExecutionProfiler     # Wall-clock timing with nested phases
└── CompositeProfiler     # Orchestrates ExecutionProfiler + CpuProfiler + MemoryProfiler
    ├── CpuProfiler       # Optional cProfile integration
    └── MemoryProfiler    # Optional RSS tracking via resource.getrusage()
```

### Data Flow

```
CLI / Consumer
     │
     └── ExecutionOptions(profiler=...)
           │
           ▼
     execute_study_plan()
           │
           ├── backend_selection
           ├── strategy_selection
           └── sequential_dispatch
                 │
                 └── ResearchExecutor
                       ├── context_translation
                       └── engine_execution
                             └── Numba executor
                                   ├── *_grouping
                                   ├── *_growth_factors
                                   ├── *_kernel_execution
                                   └── *_assembly
```

## What Is Measured

### Execution Layer

| Phase | Granularity | Source |
|-------|-------------|--------|
| `total` | Full execution | `execute_study_plan()` |
| `backend_selection` | Backend init | `execute_study_plan()` |
| `strategy_selection` | Strategy routing | `execute_study_plan()` |
| `sequential_setup` | Sequential init | `sequential_execute()` |
| `sequential_execution` | Research executor | `sequential_execute()` |
| `context_translation` | Unit→Context | `ResearchExecutor` |
| `engine_execution` | Executor dispatch | `ResearchExecutor` |
| `numba_grouping` | Generic Numba grouping | `NumbaSimulationExecutor` |
| `numba_growth_factors_static` | Static GF computation | `NumbaSimulationExecutor` |
| `numba_growth_factors_glidepath` | Glidepath GF computation | `NumbaSimulationExecutor` |
| `numba_kernel_execution` | Numba kernels | `NumbaSimulationExecutor` |
| `numba_assembly` | Numba assembly | `NumbaSimulationExecutor` |
| `part52_grouping`, `part52_growth_factors`, `part52_kernel_execution`, `part52_assembly` | Part 52 phases | `Part52NumbaExecutor` |
| `part49_grouping`, `part49_growth_factors`, `part49_kernel_execution`, `part49_assembly` | Part 49 phases | `Part49NumbaExecutor` |
| `part49_bh_grouping`, `part49_bh_growth_factors`, `part49_bh_kernel_execution`, `part49_bh_assembly` | Part 49 buy-and-hold phases | `Part49BuyAndHoldNumbaExecutor` |

### Scalar Metrics

| Key | Description |
|-----|-------------|
| `total_units` | Total simulation units |
| `numba_groups`, `part49_groups`, `part49_bh_groups`, `part52_groups` | Executor context groups |
| `numba_derived`, `part49_derived`, `part49_bh_derived`, `part52_derived` | Derived results (horizon-prefix shortcut) |
| `numba_independent`, `part49_independent`, `part49_bh_independent`, `part52_independent` | Independent evaluations |
| `numba_month_work`, `part49_month_work`, `part49_bh_month_work`, `part52_month_work` | Total month-work units |
| `numba_gf_cache_hits`, `part49_gf_cache_hits`, `part49_bh_gf_cache_hits`, `part52_gf_cache_hits` | Growth-factor cache hits |
| `numba_gf_cache_misses`, `part49_gf_cache_misses`, `part49_bh_gf_cache_misses`, `part52_gf_cache_misses` | Growth-factor cache misses |
| `sequential_units` | Units in sequential execution |

### Per-Unit Timing

`execution_time_seconds` is set for every `SimulationResult` by the production
executors. This field is excluded from dataclass equality comparisons
(`compare=False`) to avoid flaky test comparisons.

### CPU Profiling

`CpuProfiler` wraps Python's `cProfile.Profile`. When enabled via
`CompositeProfiler(cpu_profiling=True)`, it profiles the entire execution
and produces a top-N hotspot report.

### Memory Profiling

`MemoryProfiler` uses `resource.getrusage(RUSAGE_SELF)` for peak RSS
and `/proc/self/status` for current RSS (Linux). When enabled via
`CompositeProfiler(memory_profiling=True)`, it captures RSS at phase
start/end boundaries.

## Output Formats

### Flat Report (backward compatible)

```python
report = profiler.get_report()  # ProfileReport
print(report.format())
#EXECUTION PROFILE
#============================================================
#Phase Timings:
#  total               155.1234s
#  context_translation   0.0234s
#  engine_execution    154.8000s
#  TOTAL               155.1234s
#
#Metrics:
#  total_units            1,000
#============================================================
```

### Hierarchical Report

```python
enhanced = profiler.get_enhanced_report()  # EnhancedProfileReport
print(enhanced.format())
#EXECUTION PROFILE (HIERARCHICAL)
#========================================================================
#
#Environment:
#  python: 3.13.0
#  platform: Linux-...
#
#Phase Tree:
#  total                                 155.1234s (100.0%)
#  ├── backend_selection                   0.0012s   (0.0%)
#  ├── strategy_selection                  0.0001s   (0.0%)
#  └── sequential_dispatch               155.1200s  (99.9%)
#      ├── sequential_setup                0.0005s   (0.0%)
#      └── sequential_execution          155.1195s  (99.9%)
#          ├── context_translation         0.0234s   (0.0%)
#          └── engine_execution           154.8000s  (99.7%)
#              └── numba_kernel_execution 154.5000s  (99.5%)
#
#  TOTAL                                 155.1234s
#
#Metrics:
#  total_units            1,000
#  numba_groups             100
#  numba_derived            900
#========================================================================
```

### JSON Serialization

```python
import json
d = enhanced.to_dict()
print(json.dumps(d, indent=2))
```

## Low-Level Parallel Helper

The high-level execution API rejects `PARALLEL` strategy for Numba workloads.
The low-level `parallel_execute()` helper remains available to Core tests that
validate process-parallel equivalence. Its profiler records parent overhead,
worker computation, and result assembly in the parent process only.

## Limitations

1. **Wall-clock timing includes OS scheduling delays** — a phase may
   appear slower than actual computation due to context switches.

2. **CPU profiling (`cProfile`) adds ~10-20% overhead** — use only for
   diagnostic profiling, not production monitoring.

3. **Memory profiling captures peak RSS** — it does not track individual
   allocations or per-object sizes. Use `tracemalloc` or external tools
   for allocation profiling.

4. **Worker processes are not profiled** — the profiler runs in the parent
   process. Worker computation time is inferred from wall-clock differences.

5. **`execution_time_seconds` is excluded from equality** — this field
   is a runtime measurement and does not affect simulation semantics.
