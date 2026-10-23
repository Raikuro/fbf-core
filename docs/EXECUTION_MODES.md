# Execution Architecture

This document describes the public execution model, internal implementation mapping, and strategy routing policy for the FBF execution engine.

---

## 1. Public Backend and Strategy Model

### ExecutionBackend

| Value | Contract |
|-------|----------|
| `DECIMAL_FAST_PATH` | Exact-Decimal execution path. It currently wraps the legacy reference engine and performs horizon derivation for eligible workload families. Used for validation, debugging, oracle comparisons, and regression testing. It is not the Numba backend and is not itself the legacy engine. `REFERENCE` is a deprecated same-value alias retained throughout `0.2.x`. |
| `FAST` | Optimized float64 backend. Requires the optional Numba dependency (`pip install fbf-core[numba]`). Automatically selects the best validated kernel (Part52, Part49, Part49 buy-and-hold, or the generic Numba executor) based on workload. A workload it cannot execute on Numba raises `UnsupportedConfigurationError` rather than silently falling back to the Decimal path; use `None` (AUTO) for graceful routing. |
| `None` (default) | AUTO dispatch. Capability-driven routing: selects FAST when all units are eligible, `DECIMAL_FAST_PATH` otherwise. This is the recommended production path. |

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
2. If numba is available and all units are Part49-eligible → `Part49NumbaExecutor`
3. If numba is available and all units are Part49 buy-and-hold-eligible → `Part49BuyAndHoldNumbaExecutor`
4. If numba is available and all units are eligible for one generic Numba family → `NumbaSimulationExecutor`
5. Otherwise → `FastPathSimulationExecutor` (`DECIMAL_FAST_PATH`)

### Explicit backend selection

```python
# Exact-Decimal path (for validation, debugging, oracle comparisons)
execute_study_plan(built, options=ExecutionOptions(backend=ExecutionBackend.DECIMAL_FAST_PATH))

# Explicit optimized backend
execute_study_plan(built, options=ExecutionOptions(backend=ExecutionBackend.FAST))
```

### Summary

```
unspecified (None)         → AUTO dispatch (try FAST, fall back to DECIMAL_FAST_PATH)
DECIMAL_FAST_PATH          → exact-Decimal execution path
FAST                       → explicit optimized Numba backend
REFERENCE                  → deprecated same-value alias for DECIMAL_FAST_PATH
```

---

## 3. Backend × Strategy Matrix

| Backend | AUTO | SEQUENTIAL | PARALLEL |
|---------|------|------------|----------|
| `None` (AUTO dispatch) | Capability-driven backend + workload-aware routing | Capability-driven backend + force sequential | Capability-driven backend + force parallel (ValueError if FAST) |
| `DECIMAL_FAST_PATH` | Workload-aware routing (see §4) | Force sequential | Force parallel |
| `FAST` | Always sequential | Sequential | **ValueError** |

### Unsupported Combinations

`FAST + PARALLEL` raises a clear `ValueError` with the message:

> FAST backend does not support parallel execution. Use strategy=ExecutionStrategy.AUTO or strategy=ExecutionStrategy.SEQUENTIAL instead.

When `backend=None` and AUTO dispatch selects a Numba executor, `PARALLEL` also raises the same `ValueError`.

---

## 4. AUTO Routing Policy for DECIMAL_FAST_PATH

When `strategy=AUTO` and `backend=DECIMAL_FAST_PATH` (or AUTO dispatch falls back to it), the execution layer selects sequential or parallel based on:

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

The public `DECIMAL_FAST_PATH`/`FAST` names describe the user-facing contract (`REFERENCE` is a deprecated alias). The current implementation mapping is an internal detail that may evolve:

```
AUTO dispatch (backend=None)
  → Part52NumbaExecutor               (when all units are Part52-eligible)
  → Part49NumbaExecutor               (when all units are Part49-eligible)
  → Part49BuyAndHoldNumbaExecutor     (when all units are Part49 buy-and-hold-eligible)
  → NumbaSimulationExecutor           (when all units share one generic Numba family)
  → FastPathSimulationExecutor        (otherwise, same as DECIMAL_FAST_PATH)

DECIMAL_FAST_PATH (and deprecated alias REFERENCE)
  → FastPathSimulationExecutor
       → eligible contexts: bit-exact Decimal closed-form recurrence
       → ineligible contexts: Legacy Reference Decimal (automatic internal fallback)

FAST
  → Part52NumbaExecutor (when all units Part52-eligible)
       → Part52 scalar kernel, float64 arithmetic
       → any ineligible context: raise UnsupportedConfigurationError
         (no silent fallback; the Part52 kernel and the Decimal pipeline
          have different fee/ordering conventions)
  → Part49NumbaExecutor / Part49BuyAndHoldNumbaExecutor
       → dedicated scalar kernels, float64 arithmetic
       → any ineligible context: raise UnsupportedConfigurationError
  → NumbaSimulationExecutor (generic families)
       → Numba JIT scalar kernel, float64 arithmetic
       → any ineligible context: raise UnsupportedConfigurationError
         (explicit FAST passes require_all_eligible=True and constructs no
          reference executor)
       → sequential execution only
```

### FAST Eligibility

| Workload | Eligibility | Executor |
|----------|-------------|----------|
| Part52: `ConstantAllocationPolicy` + `Part52WithdrawalPolicy` + 2 assets + dataset coverage + an interest-rate source covering the horizon (FFR schedule of at least `horizon_months` entries, or a fixed scalar `interest_rate`) | All units eligible | `Part52NumbaExecutor` |
| Part49: dedicated eligibility predicate (2 assets, monthly frequency, zero fee where required, debt/LTV supported) | All units eligible | `Part49NumbaExecutor` |
| Part49 buy-and-hold: dedicated eligibility predicate (2 assets, zero fee, debt/LTV supported) | All units eligible | `Part49BuyAndHoldNumbaExecutor` |
| Generic fixed-real: `ConstantAllocationPolicy` + `FixedRealWithdrawalPolicy` + supported portfolio/dataset; non-workbook contexts additionally require `v0 == initial_wealth` | All units eligible | `NumbaSimulationExecutor` |
| Generic constant-nominal: `ConstantAllocationPolicy` + `ConstantWithdrawalPolicy` + supported 2-asset portfolio/dataset | All units eligible | `NumbaSimulationExecutor` |
| Generic escalating: `ConstantAllocationPolicy` + `EscalatingWithdrawalPolicy` + supported 2-asset portfolio/dataset + `v0 == initial_wealth` | All units eligible | `NumbaSimulationExecutor` |
| Generic buy-and-hold: `BuyAndHoldAllocationPolicy` + `FixedRealWithdrawalPolicy` + 2 assets + zero fee + `v0 == initial_wealth` | All units eligible | `NumbaSimulationExecutor` |
| Generic glidepath: `GlidepathAllocationPolicy` + `FixedRealWithdrawalPolicy` + supported 2-asset portfolio/dataset + `v0 == initial_wealth` | All units eligible | `NumbaSimulationExecutor` |
| Mixed/unsupported workload | Not eligible | AUTO → `DECIMAL_FAST_PATH`; explicit FAST → `UnsupportedConfigurationError` |

The generic Numba families do not model debt/LTV fields; those configurations belong to the dedicated Part 49/52 executors. Explicit FAST never constructs or calls the legacy reference executor.

### Dependency Model

```
pip install fbf-core
    → DECIMAL_FAST_PATH available (no external dependencies)

pip install fbf-core[numba]
    → FAST backend available + AUTO dispatch uses optimized kernels
```

When FAST is explicitly requested but Numba is not installed, `execute_study_plan` raises a clear `ModuleNotFoundError`:

> FAST backend requires the optional Numba dependency. Install it with: pip install fbf-core[numba]

When `backend=None` (AUTO dispatch) and Numba is not installed, the system silently falls back to `DECIMAL_FAST_PATH`.

---

## 6. Legacy Reference

The legacy Reference engine (full 9-step Decimal pipeline) is:

- **Mathematically unchanged**: the canonical oracle for correctness
- **Unavailable as a public backend**: not an `ExecutionBackend` value
- **Internally reachable**: as automatic fallback for AUTO dispatch and through `DECIMAL_FAST_PATH` (deprecated alias `REFERENCE`). Explicit FAST never falls back: an ineligible context raises `UnsupportedConfigurationError`.
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
# Automatically selects FAST when eligible, DECIMAL_FAST_PATH otherwise
execute_study_plan(built)

# Exact-Decimal path (for validation, debugging, oracle comparisons)
execute_study_plan(built, options=ExecutionOptions(
    backend=ExecutionBackend.DECIMAL_FAST_PATH,
))

# Explicit optimized backend
execute_study_plan(built, options=ExecutionOptions(
    backend=ExecutionBackend.FAST,
))

# Explicit sequential
execute_study_plan(built, options=ExecutionOptions(
    backend=ExecutionBackend.DECIMAL_FAST_PATH,
    strategy=ExecutionStrategy.SEQUENTIAL,
))

# Explicit parallel with worker limit (DECIMAL_FAST_PATH only)
execute_study_plan(built, options=ExecutionOptions(
    backend=ExecutionBackend.DECIMAL_FAST_PATH,
    strategy=ExecutionStrategy.PARALLEL,
    workers=4,
))

# With profiling
execute_study_plan(built, options=ExecutionOptions.with_profiling(
    backend=ExecutionBackend.DECIMAL_FAST_PATH,
))
```
