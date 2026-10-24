# Execution Architecture

This document describes the public execution model and the Numba backend
routing policy. The legacy Decimal engine, the Decimal fast path, and the
nine-step pipeline have been removed.

---

## 1. Public Backend and Strategy Model

### ExecutionBackend

| Value | Contract |
|-------|----------|
| `FAST` | The Numba-backed execution engine. Requires the optional Numba dependency (`pip install fbf-core[numba]`). Selects the dedicated Part 52, Part 49, Part 49 buy-and-hold, or generic Numba executor based on the workload. Unsupported configurations raise `UnsupportedConfigurationError`; there is no fallback engine. |
| `None` (default) | AUTO dispatch. Applies the same capability-driven Numba routing as explicit `FAST`. If no Numba executor supports the whole plan, AUTO raises `UnsupportedConfigurationError`; if Numba is unavailable, it raises `ModuleNotFoundError`. |

`ExecutionBackend` has no Decimal or reference value.

### ExecutionStrategy

| Value | Contract |
|-------|----------|
| `AUTO` | Resolve to sequential execution. Included for compatibility with the public options model. |
| `SEQUENTIAL` | Force single-process execution. |
| `PARALLEL` | Rejected with `ValueError`. Parallel execution was measured as counterproductive for the Numba engine at all scales. |

---

## 2. Backend Selection Semantics

### Default behavior (no backend specified)

```python
execute_study_plan(built)  # backend=None, strategy=AUTO
```

AUTO dispatch selects the executor that supports every unit in the plan:

1. All units Part 52-eligible → `Part52NumbaExecutor`
2. All units Part 49-eligible → `Part49NumbaExecutor`
3. All units Part 49 buy-and-hold-eligible → `Part49BuyAndHoldNumbaExecutor`
4. Every unit eligible for the generic Numba kernels → `NumbaSimulationExecutor`
   (generic families may be mixed in one plan)
5. Otherwise → `UnsupportedConfigurationError`

AUTO never constructs a legacy or Decimal fallback.

### Explicit backend selection

```python
# Explicit Numba backend
execute_study_plan(built, options=ExecutionOptions(backend=ExecutionBackend.FAST))
```

Explicit `FAST` applies the same routing and the same fail-closed guarantees.
A plan that mixes a dedicated Part 52/49 family with another family is rejected;
mixed generic families are handled by one `NumbaSimulationExecutor`.

### Summary

```
None (AUTO)  → Numba capability routing; fail closed
FAST         → Numba capability routing; fail closed
```

---

## 3. Backend × Strategy Matrix

| Backend | AUTO | SEQUENTIAL | PARALLEL |
|---------|------|------------|----------|
| `None` (AUTO dispatch) | Capability-driven Numba routing (sequential) | Capability-driven Numba routing (sequential) | **ValueError** |
| `FAST` | Numba capability routing (sequential) | Sequential | **ValueError** |

### Unsupported Combinations

`PARALLEL` raises a clear `ValueError`:

> The Numba backend does not support parallel execution. Use strategy=ExecutionStrategy.AUTO or strategy=ExecutionStrategy.SEQUENTIAL instead.

---

## 4. Internal Implementation Mapping

```
AUTO dispatch (backend=None) and FAST
  → Part52NumbaExecutor               (when all units are Part52-eligible)
  → Part49NumbaExecutor               (when all units are Part49-eligible)
  → Part49BuyAndHoldNumbaExecutor     (when all units are Part49 buy-and-hold-eligible)
  → NumbaSimulationExecutor           (when every unit is generic-Numba-eligible;
                                       generic families may be mixed)
  → UnsupportedConfigurationError

All executors
  → scalar Numba kernels, float64 arithmetic
  → sequential execution only
  → any ineligible context: raise UnsupportedConfigurationError
```

### FAST Eligibility

| Workload | Eligibility | Executor |
|----------|-------------|----------|
| Part52: `ConstantAllocationPolicy` + `Part52WithdrawalPolicy` + 2 assets + dataset coverage + an interest-rate source covering the horizon | All units eligible | `Part52NumbaExecutor` |
| Part49: dedicated eligibility predicate (2 assets, monthly frequency, zero fee where required, debt/LTV supported) | All units eligible | `Part49NumbaExecutor` |
| Part49 buy-and-hold: dedicated eligibility predicate (2 assets, zero fee, debt/LTV supported) | All units eligible | `Part49BuyAndHoldNumbaExecutor` |
| Generic fixed-real: `ConstantAllocationPolicy` + `FixedRealWithdrawalPolicy` + supported portfolio/dataset | All units eligible | `NumbaSimulationExecutor` |
| Generic constant-nominal: `ConstantAllocationPolicy` + `ConstantWithdrawalPolicy` + supported 2-asset portfolio/dataset | All units eligible | `NumbaSimulationExecutor` |
| Generic escalating: `ConstantAllocationPolicy` + `EscalatingWithdrawalPolicy` + supported 2-asset portfolio/dataset + `float(v0) == float(initial_wealth)` | All units eligible | `NumbaSimulationExecutor` |
| Generic buy-and-hold: `BuyAndHoldAllocationPolicy` + `FixedRealWithdrawalPolicy` + 2 assets + zero fee + `float(v0) == float(initial_wealth)` | All units eligible | `NumbaSimulationExecutor` |
| Generic glidepath: `GlidepathAllocationPolicy` + `FixedRealWithdrawalPolicy` + supported 2-asset portfolio/dataset + `float(v0) == float(initial_wealth)` | All units eligible | `NumbaSimulationExecutor` |
| Mixed dedicated-family plan, or any unsupported workload | Not eligible | `UnsupportedConfigurationError` |

Generic fixed-real execution uses the workbook recurrence for every
final-value target. The target is an evaluation dimension applied per context
after the shared trajectory; it does not select a different recurrence.

The generic Numba kernels convert the initial portfolio value and
`initial_wealth` to float64. Eligibility therefore requires their float64
representations to agree; Decimal representations may differ by negligible
division rounding.

The generic Numba families do not model debt/LTV fields; those configurations
belong to the dedicated Part 49/52 executors.

### Dependency Model

```
pip install fbf-core[numba]
    → FAST backend available
    → AUTO dispatch available

pip install fbf-core
    → core domain, planning, persistence, and oracles remain importable
    → executing a study raises ModuleNotFoundError with installation guidance
```

When Numba is unavailable, explicit `FAST` raises:

> FAST backend requires the optional Numba dependency. Install it with: pip install fbf-core[numba]

AUTO dispatch raises:

> Execution requires the optional Numba dependency. Install it with: pip install fbf-core[numba]

---

## 5. Profiling

Profiling is injected through the execution boundary. The default `NoOpProfiler`
has zero overhead. Pass `ExecutionProfiler()` via
`ExecutionOptions.with_profiling()` to collect phase timings. The profiler is
resolved once at the execution boundary and propagated to executors.

---

## 6. Configuration Examples

```python
from fbf.core.execution import ExecutionBackend, ExecutionOptions, execute_study_plan

# Default: AUTO dispatch through the Numba backend
execute_study_plan(built)

# Explicit Numba backend
execute_study_plan(built, options=ExecutionOptions(
    backend=ExecutionBackend.FAST,
))

# Explicit sequential execution
execute_study_plan(built, options=ExecutionOptions(
    backend=ExecutionBackend.FAST,
    strategy=ExecutionStrategy.SEQUENTIAL,
))

# With profiling
execute_study_plan(built, options=ExecutionOptions.with_profiling(
    backend=ExecutionBackend.FAST,
))
```
