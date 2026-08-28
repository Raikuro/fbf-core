# Execution Architecture

This document describes the public execution model, internal implementation mapping, and strategy routing policy for the FBF execution engine.

---

## 1. Public Backend and Strategy Model

### ExecutionBackend

| Value | Contract |
|-------|----------|
| `DEFAULT` | Exact Decimal semantics. Optimized fast path when eligible; internal fallback to legacy Decimal reference for ineligible contexts. |
| `FAST` | Maximum-throughput float64 semantics. Requires the optional Numba dependency (`pip install fbf-core[numba]`). |

### ExecutionStrategy

| Value | Contract |
|-------|----------|
| `AUTO` | The execution backend chooses the appropriate strategy based on workload size, backend capabilities, and available host resources. |
| `SEQUENTIAL` | Force single-process execution regardless of workload. |
| `PARALLEL` | Explicitly request multiprocessing. Not supported by `FAST`; raises `ValueError`. |

---

## 2. Backend × Strategy Matrix

| Backend | AUTO | SEQUENTIAL | PARALLEL |
|---------|------|------------|----------|
| `DEFAULT` | Workload-aware routing (see §3) | Force sequential | Force parallel |
| `FAST` | Always sequential | Sequential | **ValueError** |

### Unsupported Combinations

`FAST + PARALLEL` raises a clear `ValueError` with the message:

> FAST backend does not support parallel execution. Use strategy=ExecutionStrategy.AUTO or strategy=ExecutionStrategy.SEQUENTIAL instead.

---

## 3. AUTO Routing Policy for DEFAULT

When `strategy=AUTO` and `backend=DEFAULT`, the execution layer selects sequential or parallel based on:

- **Workload size**: total number of simulation units in the plan
- **Available workers**: the `workers` option (resource hint / upper bound) or host CPU count
- **Parallel threshold**: plans with fewer than `_DEFAULT_PARALLEL_UNIT_THRESHOLD` (500) units always execute sequentially

The routing logic:

```
available_workers = workers if workers is not None else min(8, os.cpu_count())
use_parallel = (total_units >= 500) and (available_workers > 1)
```

Key design points:

- `workers` is an optional resource hint, not a directive to parallelize
- `workers=8, strategy=AUTO` does NOT automatically imply parallel execution
- `workers=8, strategy=SEQUENTIAL` must remain sequential
- `workers=8, strategy=PARALLEL` explicitly requests parallel execution
- `workers=None` inspects host capabilities and uses a conservative default

For `FAST`, AUTO always resolves to sequential because parallel execution was measured as counterproductive at all scales.

The threshold is derived from measured sequential-vs-parallel crossover data on the reference development host (4 workers, 120-month horizon, Fast Path Decimal):

| Units | Sequential | Parallel (4 workers) | Speedup | Verdict |
|-------|-----------|---------------------|---------|---------|
| 100 | 111ms | 115ms | 0.97x | Neutral |
| 200 | 231ms | 268ms | 0.86x | Neutral |
| 300 | 345ms | 319ms | 1.08x | Neutral |
| 400 | 453ms | 355ms | 1.28x | Parallel |
| 500 | 578ms | 407ms | 1.42x | Parallel |
| 1,000 | 1,119ms | 672ms | 1.66x | Parallel |
| 5,000 | 5,516ms | 2,348ms | 2.35x | Parallel |

The threshold (500) is an execution-routing policy, not a backend invariant — it may be adjusted as batching, execution overhead, or host hardware changes.

---

## 4. Internal Implementation Mapping

The public `DEFAULT`/`FAST` names describe the user-facing contract. The current implementation mapping is an internal detail that may evolve:

```
DEFAULT
  → FastPathSimulationExecutor
       → eligible contexts: bit-exact Decimal closed-form recurrence
       → ineligible contexts: Legacy Reference Decimal (automatic internal fallback)

FAST
  → NumbaSimulationExecutor
       → Numba JIT scalar kernel, float64 arithmetic
       → sequential execution only
```

### Dependency Model

```
pip install fbf-core
    → DEFAULT backend available (no external dependencies)

pip install fbf-core[numba]
    → FAST backend available
```

When FAST is requested but Numba is not installed, `execute_study_plan` raises a clear `ModuleNotFoundError`:

> FAST backend requires the optional Numba dependency. Install it with: pip install fbf-core[numba]

No silent fallback to DEFAULT occurs.

---

## 5. Legacy Reference

The legacy Reference engine (full 9-step Decimal pipeline) is:

- **Mathematically unchanged**: the canonical oracle for correctness
- **Unavailable as a public backend**: not an `ExecutionBackend` value
- **Internally reachable**: as automatic fallback for DEFAULT when the fast path is ineligible
- **Available for testing**: differential and regression tests verify equivalence

It should not be selected automatically as an independent execution mode.

---

## 6. Profiling

Profiling is injected through the execution boundary. The default `NoOpProfiler` has zero overhead. Pass `ExecutionProfiler()` via `ExecutionOptions.with_profiling()` to collect phase timings. The profiler is resolved once at the execution boundary and propagated to executors — no scattered conditionals.

---

## 7. Configuration Examples

```python
from fbf.core.execution import ExecutionBackend, ExecutionOptions, execute_study_plan

# Default: exact Decimal, automatic routing
execute_study_plan(built)

# Explicit sequential
execute_study_plan(built, options=ExecutionOptions(
    backend=ExecutionBackend.DEFAULT,
    strategy=ExecutionStrategy.SEQUENTIAL,
))

# Explicit parallel with worker limit
execute_study_plan(built, options=ExecutionOptions(
    backend=ExecutionBackend.DEFAULT,
    strategy=ExecutionStrategy.PARALLEL,
    workers=4,
))

# FAST backend (requires numba)
execute_study_plan(built, options=ExecutionOptions(
    backend=ExecutionBackend.FAST,
))

# With profiling
execute_study_plan(built, options=ExecutionOptions.with_profiling(
    backend=ExecutionBackend.DEFAULT,
))
```
