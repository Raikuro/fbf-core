# S5 — ERN Part 49 Replication: Architecture & Implementation Plan

**Stage:** S5 — Part 49 Leverage Replication  
**Status:** APPROVED FOR IMPLEMENTATION (revised scope)  
**Date:** 2026-09-04 (revised 2026-09-05)  

---

## A. Scope Correction (2026-09-05)

### What Changed

The original S5 plan defined a 54-cell grid (2 equity × 9 SWR × 3 interest). This was an FBF research extension beyond the ERN Part 49 replication contract.

**Revised scope**: The canonical ERN Part 49 replication uses 6 cells (2 equity × 3 interest, SWR fixed at 3% + 1% loan = 4% total).

### Rationale

The 9-point SWR sweep (3% to 5%) is an FBF systematic extension that:
- Is NOT part of ERN Part 49's published methodology
- Accounts for 9× of the 54-cell grid scaling
- Was the primary driver of the 93,906-unit workload

The framework retains the capability for user-defined parameter grids. The built-in Part 49 replication should execute only the canonical ERN methodology.

### Revised Workload

| Metric | Original | Revised |
|--------|----------|---------|
| Cells | 54 | **6** |
| Units | 93,906 | **10,434** |
| Month-simulations | 33.9M | **3.77M** |
| Reduction | — | **89%** |

---

## B. Current S5 Starting State

### Repository

```
branch:     main
ahead:      8 commits (S5.0–S5.3)
clean:      yes (untracked audit docs only)
tests:      passing
```

### Completed S5 Phases

| Phase | Description | Status |
|-------|-------------|--------|
| S5.0 | Part 49 grid & dataset audit | **COMPLETE** (`fc54202`) |
| S5.1 | Generic parameter-axis plumbing | **COMPLETE** (`fc54202`) |
| S5.2 | Research-plan/grid materialization | **COMPLETE** (`2bb72fa`) |
| S5.3 | Small end-to-end smoke execution | **COMPLETE** (`0060694`) |

### S4 → S5 Handoff Contract (valid, no regression)

1. Debt semantics frozen (10-step monthly ordering)
2. Decimal remains canonical/reference
3. LTV observation ≠ enforcement (Part 49: observation only)
4. Part 49 withdrawal semantics fixed (3% + 1% = 4%)
5. Cohort-specific portfolio initialization required
6. Initial wealth reconciliation invariant
7. Multi-cohort execution isolated
8. Performance baseline: 1.178× non-debt

---

## C. Part 49 Methodology

### What ERN Part 49 Studies

ERN Part 49 ("Using Leverage in Retirement") investigates whether margin loans improve retirement outcomes. The core question: does borrowing at a low real interest rate to invest more in equities produce better outcomes than a standard withdrawal-only strategy?

### Fixed Parameters (not swept)

| Parameter | Value | Source |
|-----------|-------|--------|
| Portfolio withdrawal rate | 3% of initial_wealth | ERN Part 49 §3 |
| Loan draw rate | 1% of initial_wealth | ERN Part 49 §3 |
| Total spending | 4% of initial_wealth | 3% + 1% |
| LTV limit | 75% | Interactive Brokers margin requirement |
| LTV enforcement | OFF (observe only) | ERN reports LTV > 75% |
| Dataset | `ern_swr_h720.json` | US market real returns |
| Horizon | 30 years | ERN Part 49 primary analysis |

### Canonical Swept Parameters

| Axis | Values | Cardinality |
|------|--------|-------------|
| Equity allocation | [0.75, 1.0] | 2 |
| Real interest rate | [0.0, 0.015, 0.03] | 3 |

**Canonical grid: 2 × 3 = 6 cells × 1,739 cohorts = 10,434 simulation units**

### Interest Rate Semantics

ERN tests three real interest rates representing different margin-loan cost scenarios:
- **0%**: Interest-free borrowing (theoretical lower bound)
- **1.5%**: Low-cost margin loan (Interactive Brokers typical)
- **3%**: High-cost margin loan (brokerage house typical)

All rates are real (inflation-adjusted), consistent with the dataset.

### FBF Research Extension (outside S5 scope)

The framework supports user-defined parameter grids that extend beyond ERN's methodology. An example is the 9-point SWR sweep (3% to 5%), which produces a 54-cell grid. This is a valid FBF research experiment but is NOT part of the ERN Part 49 replication contract.

---

## D. Dataset Audit

### Dataset: `ern_swr_h720.json`

| Property | Value |
|----------|-------|
| Snapshots | 2,459 |
| Date range | 1871-01-31 to 2075-11-01 |
| Frequency | Monthly |
| Asset classes | equity, bond (2 trajectories) |
| Data type | Real (inflation-adjusted) index levels |

### Cohort Population

| Horizon | Feasible cohorts | Range |
|---------|-----------------|-------|
| 30 years (361 months) | 2,099 | 1871-01-31 to 2045-11-01 |
| 60 years (721 months) | 1,739 | 1871-01-31 to 2015-11-01 |

Part 49 uses **1,739 cohorts** (the 60-year set) for cross-horizon comparability with the baseline non-leverage SWR grid.

---

## E. Execution Model

### Canonical Flow

```
ern_part49.yaml (6 cells)
    ↓
builder.load_yaml() → StudyConfiguration
    ↓
builder.build_study_plan()
    ├─ _build_unified_parameter_configs()  → 6 ParameterConfigurations
    ├─ build_cohort_specs()                → 1,739 cohorts
    ├─ materialize_research_plan()         → 6 × 1,739 = 10,434 PlannedSimulationUnits
    └─ BuiltStudy
    ↓
execute_study_plan(BuiltStudy, ExecutionOptions)
    ↓
ResearchExecutor.execute(ResearchPlan)
    ↓
ResearchExecutionResult
    ├─ result.plan.units[i]  → PlannedSimulationUnit
    └─ result.results[i]     → SimulationResult (timeline, statistics)
    ↓
Aggregation: group by (equity, interest_rate)
    ├─ per-cell success rate
    ├─ per-cell failure month distribution
    └─ per-cell terminal values
    ↓
ERN validation: compare against published values
```

### Where Components Fit

| Component | Role |
|-----------|------|
| **Decimal oracle** | Canonical reference; all results computed via Decimal engine |
| **Dataset reuse** | `ern_swr_h720.json` shared across all cells; sliced per cohort |
| **Workers** | Sequential or parallel; AUTO routing handles threshold |
| **Persistence** | Optional; not required for S5 completion |

---

## F. Performance Model (Preliminary Estimate)

### Simulation Count

```
6 cells × 1,739 cohorts = 10,434 units
10,434 units × 361 months = 3,766,674 month-simulations
```

### Estimated Runtime

| Component | Estimate |
|-----------|----------|
| Per-unit overhead (context, pipeline init) | ~30ms (from C4 benchmark) |
| Per-month work (13 pipeline steps) | ~0.08ms (from C4) |
| Total per-unit | ~60ms |
| Sequential total | ~10 minutes |
| Parallel (8 workers) | ~2 minutes |

### Memory

```
10,434 units × ~2KB per result ≈ 21 MB
Dataset: ~2.5 MB
Total: ~25 MB
```

**Note**: These are preliminary estimates. S5.7 will measure the actual workload.

---

## G. Revised S5 Phases

### S5.0 — Part 49 Grid & Dataset Audit

**Objective:** Verify the 1,739 cohorts methodologically and establish grid cardinality.

**Status:** COMPLETE (`fc54202`)

---

### S5.1 — Generic Parameter-Axis Plumbing

**Objective:** Make `interest_rate` a generic parameter axis (not Part 49-specific).

**Status:** COMPLETE (`fc54202`)

---

### S5.2 — Research-Plan/Grid Materialization Validation

**Objective:** Prove grid expansion correctly produces 6 cells × 1,739 cohorts = 10,434 units.

**Status:** COMPLETE (`2bb72fa`)

---

### S5.3 — Small End-to-End Smoke Execution

**Objective:** Execute a small multidimensional smoke grid to validate end-to-end flow.

**Status:** COMPLETE (`0060694`)

---

### S5.4 — Canonical Part 49 Full Execution

**Objective:** Execute the canonical 6-cell ERN Part 49 replication.

**Files:**
- Test file: `tests/integration/test_part49_canonical_execution.py` (new)

**Workload:**
- 2 equity allocations × 3 interest rates × 1,739 cohorts = 10,434 units
- SWR fixed at 3% + 1% loan = 4% total spending

**Architecture:**
- Execute canonical grid via `execute_study_plan`
- Use parallel execution (AUTO routing)
- Collect all results
- Measure runtime and memory

**Tests:**
- Canonical grid completes without error
- All 10,434 units produce valid results
- No silently skipped cells or cohorts
- Per-cell unit counts match expectations (1,739 per cell)

**Gate:** ruff + mypy + pytest

**Acceptance:** All 10,434 units executed; results available for aggregation.

**Non-goals:** Aggregation, ERN comparison, persistence, batching architecture.

---

### S5.5 — Research Result Aggregation

**Objective:** Compute per-cell success rates and aggregate statistics for the 6 canonical cells.

**Files:**
- `src/fbf/core/research/part49_aggregation.py` (new) or extend existing
- Test file: `tests/integration/test_part49_aggregation.py`

**Architecture:**
- Group results by (equity_allocation, interest_rate)
- Compute per-cell:
  - success rate
  - failure month distribution
  - terminal portfolio value
  - terminal loan balance
  - maximum LTV
- Validate conservation: successes + failures = completed units

**Tests:**
- Aggregation produces correct number of cells (6)
- Success rates are between 0% and 100%
- Conservation invariant holds for every cell
- Aggregation is deterministic
- Cross-check against manual calculation for one cell

**Gate:** ruff + mypy + pytest

**Acceptance:** 6-row aggregation table with valid success rates and conservation.

**Non-goals:** ERN comparison, chart reproduction.

---

### S5.6 — ERN Research Validation

**Objective:** Compare FBF results against ERN published values with provenance classification.

**Files:**
- Test file: `tests/oracle/ern/test_part49_validation.py`

**Architecture:**
- For every ERN comparison, classify provenance:
  - ERN stated value
  - ERN chart-derived value
  - ERN methodology-derived value
  - FBF reconstructed value
- Classify comparison type:
  - exact numerical comparison
  - tolerance-based numerical comparison
  - chart-derived comparison
  - qualitative trajectory comparison

**Tests:**
- At least 4 anchor scenarios validated (from C2)
- Multi-rate results qualitatively consistent with ERN
- Documented comparison table with provenance labels

**Gate:** ruff + mypy + pytest

**Acceptance:** Results are qualitatively consistent with ERN; discrepancies documented with provenance.

**Non-goals:** Exact numerical reproduction (chart-derived values are approximate).

---

### S5.7 — Performance and Resource Measurement

**Objective:** Measure actual canonical workload and characterize performance.

**Files:**
- Test file: `tests/benchmarks/test_part49_performance.py`

**Architecture:**
- Measure wall-clock runtime
- Measure throughput (units/second)
- Measure peak memory
- Measure CPU utilization
- Distinguish:
  - A. mathematical work
  - B. execution overhead
  - C. IO/data-access overhead
- Measure worker scaling

**Tests:**
- Canonical grid runtime measured
- Throughput characterized
- Memory usage characterized
- Worker scaling quantified
- No mixing of work categories

**Gate:** ruff + mypy + pytest

**Acceptance:** Performance characterized; no bottlenecks identified.

**Non-goals:** Optimization (measure only).

---

### S5.8 — S5 Closure

**Objective:** Document S5 results and close the stage.

**Files:**
- `docs/roadmap/S5_VALIDATION_CLOSURE_REPORT.md`

**Architecture:**
- Consolidate all S5 results
- Document final acceptance matrix
- Define S5 → S6 handoff contract

**Tests:** N/A (documentation only)

**Gate:** All quality gates pass

**Acceptance:** S5 closure report complete.

**Non-goals:** S6 work.

---

## H. Deferred Architecture Research

The following architecture investigations are valuable but NOT required for S5. They should be classified as:

> **Scalability Architecture Research — Deferred pending demonstrated framework requirement**

| Document | Finding | Status |
|----------|---------|--------|
| S5.4-R1-A | MonthlyResult field classification (6 dead fields) | Complete, deferred |
| S5.4-R1-A2 | Historical provenance audit of dead fields | Complete, deferred |
| S5.4-R1-B | Duplication analysis, ERN minimum vs extended workload | Complete, deferred |
| S5.4-R2 | Execution & storage architecture design | Complete, deferred |

**When these should be revisited:**
- If the canonical 10,434-unit workload exceeds practical memory limits
- If a future user-defined study requires significantly larger workloads
- When FBF needs to support production-scale research experiments

**What should NOT happen:**
- Batching architecture should not be implemented preemptively
- Normalized persistence should not replace the current storage model
- MonthlyResult should not be modified for storage optimization
- The dead fields should not be removed as part of S5

---

## I. Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| 1 | Interest rate axis plumbing breaks existing single-rate path | Low | High | Regression tests; existing C3 tests must pass |
| 2 | ERN chart-derived values don't match FBF exactly | High | Low | Document as qualitative; FBF is architecturally faithful |
| 3 | Forward projection bias dominates late cohorts | Medium | Low | Document; use only historical cohorts for validation |
| 4 | Parallel execution serialization errors | Low | High | Test with small grid first; compare sequential vs parallel |
| 5 | Aggregation produces wrong success rates | Low | High | Independent verification against manual calculation |

---

## J. Decision

**S5 PLAN — REVISED SCOPE — APPROVED FOR IMPLEMENTATION**

Canonical workload: 6 cells × 1,739 cohorts = 10,434 units.

Proceed with S5.4.
