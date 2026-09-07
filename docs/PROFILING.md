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
           └── parallel_dispatch / sequential_dispatch
                 │
                 ├── parallel_overhead
                 ├── parallel_pool_creation
                 ├── parallel_task_submission
                 ├── parallel_execution
                 │     └── ResearchExecutor
                 │           ├── context_translation
                 │           └── engine_execution
                 │                 └── SimulationExecutor
                 │                       └── SimulationRunner.run()  [per-unit timing]
                 ├── parallel_result_collection
                 └── parallel_assembly
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
| `parallel_overhead` | Parallel init | `parallel_execute()` |
| `parallel_pool_creation` | Pool creation | `parallel_execute()` |
| `parallel_task_submission` | Task submission | `parallel_execute()` |
| `parallel_execution` | Full parallel | `parallel_execute()` |
| `parallel_result_collection` | Result IPC | `parallel_execute()` |
| `parallel_assembly` | Result assembly | `parallel_execute()` |
| `context_translation` | Unit→Context | `ResearchExecutor` |
| `engine_execution` | Executor dispatch | `ResearchExecutor` |
| `fast_path_grouping` | Fast-path grouping | `FastPathSimulationExecutor` |
| `fast_path_evaluation` | Fast-path eval | `FastPathSimulationExecutor` |
| `fast_path_assembly` | Fast-path assembly | `FastPathSimulationExecutor` |
| `reference_grouping` | Reference grouping | `ReferenceSimulationExecutor` |
| `reference_evaluation` | Reference eval | `ReferenceSimulationExecutor` |
| `reference_assembly` | Reference assembly | `ReferenceSimulationExecutor` |
| `numba_grouping` | Numba grouping | `NumbaSimulationExecutor` |
| `numba_growth_factors` | GF computation | `NumbaSimulationExecutor` |
| `numba_kernel_execution` | Numba kernels | `NumbaSimulationExecutor` |
| `numba_assembly` | Numba assembly | `NumbaSimulationExecutor` |
| Per-unit `execution_time_seconds` | Per-simulation | `SimulationRunner.run()` |

### Scalar Metrics

| Key | Description |
|-----|-------------|
| `total_units` | Total simulation units |
| `fast_path_groups` | Fast-path context groups |
| `fast_path_derived` | Derived results (horizon shortcut) |
| `fast_path_independent` | Independent evaluations |
| `fast_path_month_work` | Total month-work units |
| `reference_groups` | Reference context groups |
| `reference_derived` | Reference derived results |
| `reference_independent` | Reference independent evals |
| `reference_month_work` | Reference month-work |
| `numba_groups` | Numba context groups |
| `numba_gf_cache_hits` | Growth-factor cache hits |
| `numba_gf_cache_misses` | Growth-factor cache misses |
| `parallel_batches` | Number of work batches |
| `parallel_workers` | Worker count |
| `parallel_units` | Units in parallel execution |
| `sequential_units` | Units in sequential execution |

### Per-Unit Timing

`execution_time_seconds` is set for every `SimulationResult` by
`SimulationRunner.run()`. This field is excluded from dataclass equality
comparisons (`compare=False`) to avoid flaky test comparisons.

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
#              └── fast_path_evaluation  154.5000s   (99.5%)
#
#  TOTAL                                 155.1234s
#
#Metrics:
#  total_units            1,000
#  fast_path_groups         100
#  fast_path_derived        900
#========================================================================
```

### JSON Serialization

```python
import json
d = enhanced.to_dict()
print(json.dumps(d, indent=2))
```

## Multi-Process Profiling

The profiler runs in the **parent process only**. Worker processes do not
profile (they have their own address space). The profiler captures:

- **Parent overhead**: pool creation, task submission, result collection
- **Worker computation**: measured indirectly via wall-clock time
- **IPC overhead**: implicit in parallel_execution minus worker computation

To distinguish parent vs. worker time, compare:
- `parallel_execution` (includes worker time)
- `sequential_execution` (pure computation)

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
