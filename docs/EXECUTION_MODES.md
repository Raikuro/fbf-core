# FBF Execution-Mode Architecture & Matrix

This document provides a comprehensive guide to the execution architecture, numerical backends, execution strategies, and configuration matrix of the **FIRE Backtesting Framework (FBF)**.

---

## 1. Architectural Model

Execution in FBF is decoupled into four orthogonal dimensions:

```text
CLI / API Configuration
         │
         ▼
Execution Options & Profiling Boundary  (ExecutionOptions, Profiler)
         │
         ├── Numerical Backend / Executor  (Reference, Fast Path Float/Decimal, Numba)
         └── Execution Strategy            (Sequential, Parallel)
```

1. **Numerical Backend / Executor**: Determines the algorithm and number representation used to evaluate individual simulation contexts.
2. **Execution Strategy**: Determines how work is dispatched across CPU workers (`sequential_execute` vs `parallel_execute`).
3. **Horizon Derivation**: Optimisation that evaluates the longest horizon once per family and derives shorter-horizon results.
4. **Profiling**: Instrumentation resolved once at the execution boundary (`ExecutionProfiler` vs `NoOpProfiler`).

---

## 2. Complete Execution Mode Matrix

| Backend / Path | Precision | Strategy | Horizon Derivation | Fallback Behavior | Eligibility Requirements | CLI Flag | API Entry |
|---|---|---|---|---|---|---|---|
| **Default Pipeline** | Decimal | Sequential / Parallel | ❌ None (direct evaluation) | N/A (canonical reference engine) | All contexts | N/A (default for non-derived API runs) | `execute_study_plan(built, options)` (default) |
| **Reference (Horizon Derivation)** | Decimal | Sequential / Parallel | ✅ Reuse longest path per family | Evaluates non-derivable contexts directly | `ConstantAllocationPolicy` + `FixedRealWithdrawalPolicy` | Default or `--reference` | `execute_reference(plan, ...)` |
| **Fast Path Float** | `float64` | Sequential / Parallel | ✅ Reuses closed-form recurrence | Delegates non-eligible to default Decimal pipeline | `ConstantAlloc` + `FixedWithdrawal` + 2-asset portfolio | `--fast-path` | `FastPathSimulationExecutor(precision="float")` |
| **Fast Path Decimal** | Decimal | Sequential / Parallel | ✅ Reuses closed-form recurrence | Delegates non-eligible to default Decimal pipeline | Same as Fast Path Float | N/A (API only) | `FastPathSimulationExecutor(precision="decimal")` |
| **Numba Accelerated** | NumPy / Numba `float64` | Sequential / Parallel | ✅ Reuses longest path GF array | Delegates non-eligible to default Decimal pipeline | `ConstantAlloc` + `FixedWithdrawal` + 2-asset portfolio | N/A (API only) | `execute_numba(plan, ...)` or `options.use_numba=True` |

---

## 3. Detailed Backend Descriptions

### A. Reference Decimal Engine (Canonical Oracle)
- **Class**: `SimulationExecutor(SimulationRunner(...))`
- **Module**: `fbf.core.execution.pipeline.executor`
- **Representation**: 100% `Decimal` arithmetic using Python's `decimal.Decimal`.
- **Pipeline**: Full 9-step monthly simulation pipeline (`InitializeAllocationStep`, `BuildDecisionContextStep`, `WithdrawalDecisionStep`, `WithdrawalExecutionStep`, `AllocationDecisionStep`, `PortfolioRebalanceStep`, `MarketEvolutionStep`, `MonthlyResultBuilderStep`, `SimulationStateUpdateStep`).
- **Guarantees**: Absolute canonical truth. Defines the mathematical model of the framework.

### B. Reference Executor with Horizon Derivation
- **Class**: `ReferenceSimulationExecutor`
- **Module**: `fbf.core.execution.strategies.reference`
- **Representation**: `Decimal` arithmetic.
- **Behavior**: Groups context families sharing identical trajectory parameters `(start_date, equity_allocation, withdrawal_rate, initial_wealth, initial_portfolio)`. Evaluates the longest horizon through the canonical Reference pipeline, and derives shorter-horizon results by reading off prefix timelines.
- **CLI Default**: Running `sim-retire run <yaml>` without backend flags defaults to this executor. Memory-safe dispatch partitions large plans into cohort-aligned slices of 100 cohorts.

### C. Fast Path (Float & Decimal)
- **Class**: `FastPathSimulationExecutor`
- **Module**: `fbf.core.execution.strategies.fast_path`
- **Representation**: `float64` (fast closed-form) or `Decimal` (bit-exact closed-form).
- **Recurrence**:
  \[
  V_0 = \text{value}(\text{portfolio}_0), \quad C = V_0 \times \frac{\text{withdrawal\_rate}}{12}, \quad V_{m+1} = (V_m - C) \times g_m
  \]
- **Eligibility**: Restricted to 2-asset portfolios (equity + bond) under `ConstantAllocationPolicy` and `FixedRealWithdrawalPolicy`. Non-eligible contexts fall back to `ReferenceSimulationExecutor`.
- **CLI Flag**: `--fast-path` selects `precision="float"`. `precision="decimal"` is available programmatically.

### D. Numba Accelerated Backend
- **Class**: `NumbaSimulationExecutor`
- **Module**: `fbf.core.execution.strategies.numba_executor`
- **Representation**: Numba JIT scalar kernel operating on float64 NumPy arrays.
- **Growth Factor Cache**: Precomputes growth factor arrays keyed by `(start_date, equity_allocation)`. For the ERN 78,255 trajectory group workload, this reduces GF array construction to 8,695 unique arrays.
- **Whole Definition Flag**: Sets `processes_whole_definition = True` so batch dispatchers pass whole plans intact to maximize cross-context GF caching.

---

## 4. Execution Strategies & Dispatching

- **Sequential (`sequential_execute`)**: Executes all units in a single process. When fine-grained progress callbacks are provided, non-grouped executors process unit-by-unit.
- **Parallel (`parallel_execute`)**: Uses `concurrent.futures.ProcessPoolExecutor` with initializer-seeded worker state (`_initialize_worker`) so large experiment definitions and datasets are pickled once per process, not per task.
- **Cohort-Slice Dispatch**: Used by `execute_reference` to process large workloads in memory-safe cohort slices, ensuring timeline materialization stays under memory limits while preserving family-level horizon derivation.

---

## 5. Summary & Persistence Constraints

- **Timeline Retention**: Full reference execution materializes monthly timelines (`SimulationTimeline`).
- **Summary-Only (`--summary-only`)**: Discards per-month timelines, retaining only `SimulationStatistics` (final wealth, drawdown, success, failure month).
- **Persistence (`--persist-study`)**: SQLite database storage requires full per-month timelines. Therefore, `--summary-only` and `--fast-path` cannot be combined with `--persist-study`.
