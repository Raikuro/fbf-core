# Execution Architecture

This document describes the public execution model, internal implementation mapping, and strategy routing policy for the FBF execution engine.

---

## 1. Public Backend and Strategy Model

### ExecutionBackend

| Value | Contract |
|-------|----------|
| `REFERENCE` | Authoritative Decimal reference implementation. Exact semantics; used for validation, debugging, oracle comparisons, and regression testing. |
| `FAST` | Optimized float64 backend. Requires the optional Numba dependency (`pip install fbf-core[numba]`). Automatically selects the best validated kernel (Part52 or FixedReal) based on workload. |
| `None` (default) | AUTO dispatch. Capability-driven routing: selects FAST when all units are eligible, REFERENCE otherwise. This is the recommended production path. |

### ExecutionStrategy

| Value | Contract |
|-------|----------|
| `AUTO` | The execution backend chooses the appropriate strategy based on workload size, backend capabilities, and available host resources. |
| `SEQUENTIAL` | Force single-process execution regardless of workload. |
| `PARALLEL` | Explicitly request multiprocessing. Not supported by `FAST`; raises `ValueError`. |

---

## 2. Backend Selection Semantics

### Default behavior (no backend specified)

```python
execute_study_plan(built)  # backend=None, strategy=AUTO
```

AUTO dispatch selects the best validated backend:

1. If numba is available and all units are Part52-eligible → `Part52NumbaExecutor`
2. If numba is available and all units are FixedReal-eligible → `NumbaSimulationExecutor`
3. Otherwise → `FastPathSimulationExecutor` (REFERENCE)

### Explicit backend selection

```python
# Authoritative Decimal reference (for validation, debugging, oracle comparisons)
execute_study_plan(built, options=ExecutionOptions(backend=ExecutionBackend.REFERENCE))

# Explicit optimized backend
execute_study_plan(built, options=ExecutionOptions(backend=ExecutionBackend.FAST))
```

### Summary

```
unspecified (None) → AUTO dispatch (try FAST, fallback to REFERENCE)
REFERENCE           → authoritative reference implementation
FAST                → explicit optimized backend
```

---

## 3. Backend × Strategy Matrix

| Backend | AUTO | SEQUENTIAL | PARALLEL |
|---------|------|------------|----------|
| `None` (AUTO dispatch) | Capability-driven backend + workload-aware routing | Capability-driven backend + force sequential | Capability-driven backend + force parallel (ValueError if FAST) |
| `REFERENCE` | Workload-aware routing (see §4) | Force sequential | Force parallel |
| `FAST` | Always sequential | Sequential | **ValueError** |

### Unsupported Combinations

`FAST + PARALLEL` raises a clear `ValueError` with the message:

> FAST backend does not support parallel execution. Use strategy=ExecutionStrategy.AUTO or strategy=ExecutionStrategy.SEQUENTIAL instead.

When `backend=None` and AUTO dispatch selects a Numba executor, `PARALLEL` also raises the same `ValueError`.

---

## 4. AUTO Routing Policy for REFERENCE

When `strategy=AUTO` and `backend=REFERENCE` (or AUTO dispatch falls back to REFERENCE), the execution layer selects sequential or parallel based on:

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

For FAST (including AUTO dispatch to FAST), AUTO always resolves to sequential because parallel execution was measured as counterproductive at all scales.

---

## 5. Internal Implementation Mapping

The public `REFERENCE`/`FAST` names describe the user-facing contract. The current implementation mapping is an internal detail that may evolve:

```
AUTO dispatch (backend=None)
  → Part52NumbaExecutor      (when all units are Part52-eligible)
  → NumbaSimulationExecutor   (when all units are FixedReal-eligible)
  → FastPathSimulationExecutor (otherwise, same as REFERENCE)

REFERENCE
  → FastPathSimulationExecutor
       → eligible contexts: bit-exact Decimal closed-form recurrence
       → ineligible contexts: Legacy Reference Decimal (automatic internal fallback)

FAST
  → Part52NumbaExecutor (when all units Part52-eligible)
       → Part52 scalar kernel, float64 arithmetic
       → ineligible contexts: Legacy Reference Decimal (automatic internal fallback)
  → NumbaSimulationExecutor (otherwise)
       → Numba JIT scalar kernel, float64 arithmetic
       → ineligible contexts: Legacy Reference Decimal (automatic internal fallback)
       → sequential execution only
```

### FAST Eligibility

| Workload | Eligibility | Executor |
|----------|-------------|----------|
| Part52: `ConstantAllocationPolicy` + `Part52WithdrawalPolicy` + 2 assets + dataset coverage + expense_ratio=0 + interest_rate_schedule | All units eligible | `Part52NumbaExecutor` |
| FixedReal: `ConstantAllocationPolicy` + `FixedRealWithdrawalPolicy` + 2 assets + dataset coverage | All units eligible | `NumbaSimulationExecutor` |
| Mixed/unsupported | Not eligible | Falls back to REFERENCE |

### Dependency Model

```
pip install fbf-core
    → REFERENCE backend available (no external dependencies)

pip install fbf-core[numba]
    → FAST backend available + AUTO dispatch uses optimized kernels
```

When FAST is explicitly requested but Numba is not installed, `execute_study_plan` raises a clear `ModuleNotFoundError`:

> FAST backend requires the optional Numba dependency. Install it with: pip install fbf-core[numba]

When `backend=None` (AUTO dispatch) and Numba is not installed, the system silently falls back to REFERENCE.

---

## 6. Legacy Reference

The legacy Reference engine (full 9-step Decimal pipeline) is:

- **Mathematically unchanged**: the canonical oracle for correctness
- **Unavailable as a public backend**: not an `ExecutionBackend` value
- **Internally reachable**: as automatic fallback for REFERENCE and FAST when contexts are ineligible
- **Available for testing**: differential and regression tests verify equivalence

It should not be selected automatically as an independent execution mode.

---

## 7. Profiling

Profiling is injected through the execution boundary. The default `NoOpProfiler` has zero overhead. Pass `ExecutionProfiler()` via `ExecutionOptions.with_profiling()` to collect phase timings. The profiler is resolved once at the execution boundary and propagated to executors — no scattered conditionals.

---

## 8. Configuration Examples

```python
from fbf.core.execution import ExecutionBackend, ExecutionOptions, ExecutionStrategy, execute_study_plan

# Default: AUTO dispatch (recommended production path)
# Automatically selects FAST when eligible, REFERENCE otherwise
execute_study_plan(built)

# Explicit Decimal reference (for validation, debugging, oracle comparisons)
execute_study_plan(built, options=ExecutionOptions(
    backend=ExecutionBackend.REFERENCE,
))

# Explicit optimized backend
execute_study_plan(built, options=ExecutionOptions(
    backend=ExecutionBackend.FAST,
))

# Explicit sequential
execute_study_plan(built, options=ExecutionOptions(
    backend=ExecutionBackend.REFERENCE,
    strategy=ExecutionStrategy.SEQUENTIAL,
))

# Explicit parallel with worker limit (REFERENCE only)
execute_study_plan(built, options=ExecutionOptions(
    backend=ExecutionBackend.REFERENCE,
    strategy=ExecutionStrategy.PARALLEL,
    workers=4,
))

# With profiling
execute_study_plan(built, options=ExecutionOptions.with_profiling(
    backend=ExecutionBackend.REFERENCE,
))
```
