# S5 — ERN Part 49 Full Study Execution: Architecture & Implementation Plan

**Stage:** S5 — Part 49 Leverage Execution  
**Status:** APPROVED FOR IMPLEMENTATION  
**Date:** 2026-09-04  

---

## A. Current S5 Starting State

### Repository

```
branch:     main
ahead:      5 commits (C2–C5 + K.7)
clean:      yes
tests:      1482 passed, 6 skipped
ruff:       All checks passed
mypy:       235 source files, no issues
contract:   16 passed
```

### S4 Commits

| Hash | Description |
|------|-------------|
| 9961f43 | C5: S4 validation closure report |
| 3749464 | C4: benchmark Part 49 debt execution performance |
| a99a268 | C3: validate Part 49 multi-cohort isolation |
| c3f4201 | C2: validate Part 49 ERN anchor scenarios |
| a6894cd | K.7: research-layer debt plumbing — Part 49 study executability |

### S4 Handoff Contract (valid, no regression)

1. Debt semantics frozen (10-step monthly ordering)
2. Decimal remains canonical/reference
3. LTV observation ≠ enforcement (Part 49: observation only)
4. Part 49 withdrawal semantics fixed (3% + 1% = 4%)
5. Cohort-specific portfolio initialization required
6. Initial wealth reconciliation invariant
7. Multi-cohort execution isolated
8. Performance baseline: 1.178× non-debt

---

## B. Part 49 Methodology

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

### Swept Parameters (grid axes)

| Axis | Values | Cardinality |
|------|--------|-------------|
| Equity allocation | [0.75, 1.0] | 2 |
| Withdrawal rate | [0.03 .. 0.05] in 0.25% steps | 9 |
| Real interest rate | [0.0, 0.015, 0.03] | 3 |

**Grid: 2 × 9 × 3 = 54 cells × 1,739 cohorts = 93,906 simulation units**

### Interest Rate Semantics

ERN tests three real interest rates representing different margin-loan cost scenarios:
- **0%**: Interest-free borrowing (theoretical lower bound)
- **1.5%**: Low-cost margin loan (Interactive Brokers typical)
- **3%**: High-cost margin loan (brokerage house typical)

All rates are real (inflation-adjusted), consistent with the dataset.

### Baseline Comparison

The Part 49 leverage results are compared against the non-leverage baseline (the 180-cell SWR grid: 5 equity × 9 SWR × 4 horizon). The oracle table at `data/ern/p49_oracle_table.csv` provides these baseline success rates.

---

## C. Dataset Audit

### Dataset: `ern_swr_h720.json`

| Property | Value |
|----------|-------|
| Snapshots | 2,459 |
| Date range | 1871-01-31 to 2075-11-01 |
| Frequency | Monthly |
| Asset classes | equity, bond (2 trajectories) |
| Data type | Real (inflation-adjusted) index levels |
| Inflation fields | Zero (placeholder; real data) |
| Fee drag | 5 bps p.a. per component |
| Historical data | 1871-01 to 2016-09 (1,750 months) |
| Forward projection | 2016-10 to 2075-11 (710 months) |
| Equity projection | 6.6% real p.a. constant |
| Bond projection | 0% (first 120 months post-2016), then 2.6% real p.a. |

### Cohort Coverage

| Horizon | Feasible cohorts | Range |
|---------|-----------------|-------|
| 30 years (361 months) | 2,099 | 1871-01-31 to 2045-11-01 |
| 60 years (721 months) | 1,739 | 1871-01-31 to 2015-11-01 |

### Cohort Population Selection (Critical Methodology Decision)

ERN uses a **fixed cohort set of 1,739** across ALL horizons (30y, 40y, 50y, 60y) and ALL studies (Parts 19, 20, 42, 49). This is not merely a dataset limitation — it is a deliberate methodological choice for **cross-horizon comparability**.

**Why 1,739 cohorts (not 2,099):**

1. The longest horizon (60y = 721 months) determines the cohort population: `2,459 - 721 + 1 = 1,739`
2. Using the same cohort set ensures that a 95% success rate for 30y and a 65% success rate for 60y are computed over the **same population of retirement cohorts**
3. This makes success rates directly comparable across horizons without adjusting for different cohort populations

**Source evidence:**
- `tools/ern/reference_oracle.py`: `START_FIRST=1`, `START_LAST=1739` (fixed across all horizons)
- `tests/oracle/ern/constants.py`: `COHORTS_PER_CELL = 1739` (used for all grid cells)
- `tests/oracle/ern/test_ern_timeline_regression.py`: "The cohort set is fixed by the longest horizon"

**Part 49 uses 1,739 cohorts** because:
1. The baseline comparison (non-leverage SWR grid) uses 1,739 cohorts
2. Part 49 results must be comparable to the baseline
3. Using 2,099 cohorts would introduce a different population, making comparisons invalid

**Grid cardinality:** `54 cells × 1,739 cohorts = 93,906 simulation units`

### Dataset Sufficiency

- ✓ Sufficient for 30-year horizon
- ✓ Covers all 1,739 ERN cohorts
- ✓ Both equity and bond trajectories present
- ✓ Real (inflation-adjusted) quantities
- ✓ No transformations required beyond what FBF already implements

---

## D. Study-Grid Definition

### Grid Axes

```
Axis 1: equity_allocation    [0.75, 1.0]              (2 values)
Axis 2: withdrawal_rate      [0.03 .. 0.05] step 0.0025 (9 values)
Axis 3: interest_rate        [0.0, 0.015, 0.03]        (3 values)
Fixed:  horizon              30 years
Fixed:  leverage_split       3% portfolio + 1% loan
Fixed:  ltv_limit            75% (observed, not enforced)
```

### Cell Count

```
2 × 9 × 3 = 54 cells
54 × 1,739 cohorts = 93,906 simulation units
```

### Axis Meanings

| Axis | Unit | Range | Interpretation |
|------|------|-------|----------------|
| equity_allocation | fraction | 0.75 – 1.0 | Portfolio stock allocation |
| withdrawal_rate | annual | 3.0% – 5.0% | Portfolio withdrawal rate |
| interest_rate | annual real | 0% – 3% | Margin loan cost |

### Independence

All three axes are independent. Each cell is a distinct (equity, SWR, interest_rate) combination. No chaining, no dependencies between cells.

---

## E. Existing Architecture Reuse

### Fully Reusable (no changes)

| Component | Evidence |
|-----------|----------|
| `execute_study_plan` | Generic orchestrator; takes BuiltStudy, returns ResearchExecutionResult |
| `ResearchExecutor` | Stateless; translates PlannedSimulationUnit → SimulationContext |
| `SimulationRunner` | Initializes state from context, runs pipeline |
| All 13 pipeline steps | Including LoanDrawStep, InterestAccrualStep, LTVEvaluationStep |
| `PlannedSimulationUnit` | Already has `interest_rate` field |
| `SimulationContext` | Already has `interest_rate` field |
| `SimulationState` | Already has `interest_rate`, `loan_balance` fields |
| `Part49WithdrawalPolicy` | Fixed 3% + 1% semantics |
| `ConstantAllocationPolicy` | For 75/25 and 100/0 allocations |
| `ResearchExecutionResult` | Per-unit results with success/failure |
| `SimulationStatistics` | `success: bool`, `failure_month`, `failure_state` |
| SQLite persistence | Full CRUD for experiments, plans, results |
| Dataset caching | Per (cohort, horizon) in materialize_research_plan |

### Needs Changes (small scope)

| Gap | Scope | Difficulty |
|-----|-------|------------|
| `interest_rate` as parameter axis | builder.py + plan.py plumbing | Small |
| YAML array for `debt.interest_rate` | builder.py parsing | Small |
| Aggregation by `interest_rate` | New or extended aggregation | Small |
| Full grid YAML config | ern_part49.yaml expansion | Trivial |

---

## F. Missing Architecture

### 1. Interest Rate as Generic Parameter Axis

**Current state:** `debt_interest_rate` is a scalar on `StudyConfiguration`, applied uniformly to all simulation units.

**Required state:** `interest_rate` must vary per cell as a grid axis. This must be implemented as a **generic framework capability**, not a Part 49-specific special case.

**Change:**
- `StudyConfiguration.debt_interest_rate: Decimal | None` → `debt_interest_rate_values: tuple[Decimal, ...] | None`
- YAML parsing: `_parse_optional_decimal_scalar` → `_parse_optional_decimal_array`
- `_build_unified_parameter_configs`: add `interest_rate` as a `ParameterAxis`
- `_make_interest_rate_resolver`: extract `interest_rate` from `ParameterConfiguration`
- `materialize_research_plan`: accept `interest_rate_resolver` instead of scalar `interest_rate`

**Constraint:** No `if study == PART49` logic. The framework gains a reusable capability.

### 2. Research Result Contract

Before full execution, establish which metrics Part 49 requires:

| Metric | Justification | Source |
|--------|--------------|--------|
| success/failure rate | ERN methodology (primary output) | SimulationStatistics.success |
| failure month | ERN methodology | SimulationStatistics.failure_month |
| terminal portfolio value | ERN methodology | SimulationResult.timeline[-1] |
| terminal loan balance | Part 49 requirement | DebtSnapshot |
| maximum LTV | Part 49 requirement (ERN reports LTV) | DebtSnapshot.ltv |
| failure state | Part 49 requirement | SimulationStatistics.failure_state |

Monthly trajectories (LTV, net worth, debt) are NOT persisted by default. They are reconstructed from terminal snapshots when needed.

### 3. Aggregation by Interest Rate

**Current state:** `aggregate_success_rates` groups by `(equity_allocation, withdrawal_rate, horizon_years)`.

**Required state:** Add `interest_rate` to the aggregation key.

**Change:** Extend `_extract_param` to include `interest_rate` in grouping.

### 4. Full Grid YAML Configuration

**Current state:** `ern_part49.yaml` defines 1 cell.

**Required state:** `ern_part49.yaml` defines 54 cells.

**Change:** Expand the YAML arrays.

---

## G. Execution Model

### Flow

```
ern_part49.yaml (54 cells)
    ↓
builder.load_yaml() → StudyConfiguration
    ↓
builder.build_study_plan()
    ├─ _build_unified_parameter_configs()  → 54 ParameterConfigurations
    ├─ build_cohort_specs()                → 1,739 cohorts
    ├─ materialize_research_plan()         → 54 × 1,739 = 93,906 PlannedSimulationUnits
    └─ BuiltStudy
    ↓
execute_study_plan(BuiltStudy, ExecutionOptions)
    ↓
ResearchExecutor.execute(ResearchPlan)
    ├─ Sequential if < 500 units
    └─ Parallel (AUTO routing) if >= 500 units
    ↓
ResearchExecutionResult
    ├─ result.plan.units[i]  → PlannedSimulationUnit (cohort, param_config)
    └─ result.results[i]     → SimulationResult (timeline, statistics)
    ↓
Aggregation: group by (equity, SWR, interest_rate)
    ├─ per-cell success rate
    ├─ per-cell failure month distribution
    └─ per-cell terminal values
    ↓
Persistence: SQLite (optional)
```

### Where Components Fit

| Component | Role |
|-----------|------|
| **Decimal oracle** | Canonical reference; all results computed via Decimal engine |
| **Numba optimization** | Optional fast path; differential-tested against Decimal |
| **Dataset reuse** | `ern_swr_h720.json` shared across all cells; sliced per cohort |
| **Workers** | Sequential or parallel; AUTO routing handles threshold |
| **Persistence** | Optional; saves experiment, plan, results to SQLite |
| **Horizon chaining** | NOT needed; single 30-year horizon |

---

## H. Performance Model (Preliminary Estimate)

### Simulation Count

```
54 cells × 1,739 cohorts = 93,906 units
93,906 units × 361 months = 33,899,066 month-simulations
```

### Estimated Runtime

| Component | Estimate |
|-----------|----------|
| Per-unit overhead (context, pipeline init) | ~30ms (from C4 benchmark) |
| Per-month work (13 pipeline steps) | ~0.08ms (from C4: 30.8ms / 361 months) |
| Total per-unit | ~60ms |
| Sequential total | ~94 minutes |
| Parallel (8 workers) | ~12 minutes |

**Note:** These are preliminary estimates. S5.7 will measure the actual workload.

### Memory

```
93,906 units × ~2KB per result ≈ 188 MB
Dataset: ~2.5 MB
Total: ~200 MB
```

---

## I. Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| 1 | Interest rate axis plumbing breaks existing single-rate path | Low | High | Regression tests; existing C3 tests must pass |
| 2 | 93K units exceed memory | Low | Medium | Streaming aggregation; no full result set in memory |
| 3 | ERN chart-derived values don't match FBF exactly | High | Low | Document as qualitative; FBF is architecturally faithful |
| 4 | Forward projection bias dominates late cohorts | Medium | Low | Document; use only historical cohorts for validation |
| 5 | Decimal runtime too slow for full grid | Low | Medium | Numba fast path available; measure before optimizing |
| 6 | Parallel execution serialization errors | Low | High | Test with small grid first; compare sequential vs parallel |
| 7 | Aggregation produces wrong success rates | Low | High | Independent verification against manual calculation |
| 8 | Cohort slicing wrong for 30-year horizon | Very Low | High | Already validated in C3 (12 cohorts) |

---

## J. Proposed S5 Phases

### S5.0 — Part 49 Grid & Dataset Audit

**Objective:** Verify the 1,739 cohorts methodologically and establish grid cardinality.

**Files:**
- `docs/roadmap/S5_ARCHITECTURE_PLAN.md` — this document (updated)
- Test file: `tests/integration/test_part49_grid_audit.py`

**Architecture:**
- Verify which retirement start dates ERN considers
- Verify why FBF has 1,739 valid cohorts
- Verify earliest/latest valid dates
- Verify horizon coverage for every cohort
- Verify dataset transformation matches ERN methodology
- Prove grid cardinality: 2 × 9 × 3 = 54 cells

**Tests:**
- Cohort count matches ERN (1,739)
- Every cohort supports complete 30-year trajectory
- No cohort excluded without justification
- Grid axes produce exactly 54 ParameterConfigurations

**Gate:** ruff + mypy + pytest

**Acceptance:** Grid cardinality methodologically justified; dataset sufficient.

**Non-goals:** Implementation, execution.

---

### S5.1 — Generic Parameter-Axis Plumbing

**Objective:** Make `interest_rate` a generic parameter axis (not Part 49-specific).

**Files:**
- `src/fbf/core/study/builder.py` — StudyConfiguration field, YAML parsing, parameter axis
- `src/fbf/core/study/plan.py` — interest_rate resolver in materialize_research_plan
- Test file: `tests/unit/study/test_interest_rate_axis.py`

**Architecture:**
- `StudyConfiguration.debt_interest_rate: Decimal | None` → `debt_interest_rate_values: tuple[Decimal, ...] | None`
- YAML parsing: `_parse_optional_decimal_scalar` → `_parse_optional_decimal_array`
- `_build_unified_parameter_configs`: add `interest_rate` as a `ParameterAxis`
- `_make_interest_rate_resolver`: extract `interest_rate` from `ParameterConfiguration`
- `materialize_research_plan`: accept `interest_rate_resolver` instead of scalar `interest_rate`

**Constraint:** No Part 49-specific logic. Generic framework capability.

**Tests:**
- Existing C3 tests pass (regression)
- Interest rate resolver extracts correct values from ParameterConfiguration
- Single-value interest_rate path unchanged (backward compatible)
- Multi-value interest_rate produces distinct cells

**Gate:** ruff + mypy + unit tests

**Acceptance:** Interest rate varies per cell; existing single-rate path unchanged.

**Non-goals:** Full grid, aggregation, persistence.

---

### S5.2 — Research-Plan/Grid Materialization Validation

**Objective:** Prove grid expansion correctly produces 54 cells × 1,739 cohorts = 93,906 units.

**Files:**
- `examples/studies/ern_part49.yaml` — expand to full grid
- Test file: `tests/integration/test_part49_grid_materialization.py`

**Architecture:**
- Expand YAML to full 54-cell grid
- Materialize plan and validate:
  - No missing combinations
  - No duplicate combinations
  - Every equity value appears
  - Every SWR value appears
  - Every interest rate appears
  - Cohort coverage is correct
  - Every PlannedSimulationUnit receives correct parameters
  - Every parameter reaches SimulationContext unchanged

**Tests:**
- 54 ParameterConfigurations produced
- 93,906 PlannedSimulationUnits produced
- No duplicate (cohort, parameter_config) identities
- Parameter propagation verified end-to-end
- Grid completeness: every (equity, SWR, interest_rate) combination present

**Gate:** ruff + mypy + pytest

**Acceptance:** Grid materialization is correct and complete.

**Non-goals:** Execution, aggregation.

---

### S5.3 — Small End-to-End Smoke Execution

**Objective:** Execute a multidimensional smoke grid to validate end-to-end flow.

**Files:**
- Test file: `tests/integration/test_part49_smoke_execution.py`

**Architecture:**
- Execute smoke grid: 2 equity × 2 SWR × 2 interest_rate × 10 cohorts = 80 units
- Validate results against isolated executions
- Compare sequential vs parallel execution

**Tests:**
- Smoke execution completes without error
- Results contain correct cohort/parameter alignment
- Sequential ≡ parallel (for smoke grid)
- Per-unit success/failure states are valid
- Parameter values match input configuration

**Gate:** ruff + mypy + pytest

**Acceptance:** End-to-end flow works; results are structurally valid.

**Non-goals:** Full 93K execution, aggregation, ERN comparison.

---

### S5.4 — Full 54-Cell Execution

**Objective:** Execute all 54 cells × 1,739 cohorts = 93,906 units.

**Files:**
- Test file: `tests/integration/test_part49_full_execution.py`

**Architecture:**
- Execute full grid via `execute_study_plan`
- Use parallel execution (AUTO routing)
- Collect all results
- Measure runtime and memory

**Tests:**
- Full grid completes without error
- All 93,906 units produce valid results
- No silently skipped cells or cohorts

**Gate:** ruff + mypy + pytest

**Acceptance:** All 93,906 units executed; results available for aggregation.

**Non-goals:** Aggregation, ERN comparison, persistence.

---

### S5.5 — Research Result Aggregation

**Objective:** Compute per-cell success rates and aggregate statistics.

**Files:**
- `src/fbf/core/research/part49_aggregation.py` (new) or extend existing
- Test file: `tests/integration/test_part49_aggregation.py`

**Architecture:**
- Group results by (equity_allocation, withdrawal_rate, interest_rate)
- Compute per-cell:
  - success rate
  - failure month distribution
  - terminal portfolio value
  - terminal loan balance
  - maximum LTV
- Validate conservation: successes + failures = completed units

**Tests:**
- Aggregation produces correct number of cells (54)
- Success rates are between 0% and 100%
- Conservation invariant holds for every cell
- Aggregation is deterministic
- Cross-check against manual calculation for one cell

**Gate:** ruff + mypy + pytest

**Acceptance:** 54-row aggregation table with valid success rates and conservation.

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

### S5.7 — Full-Workload Performance/Scaling Validation

**Objective:** Measure actual full workload and characterize performance.

**Files:**
- Test file: `tests/benchmarks/test_part49_full_performance.py`

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
- Full grid runtime measured
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

## K. Explicit S4 → S5 Handoff

### What S5 May Rely Upon

1. Debt semantics frozen (10-step monthly ordering)
2. Decimal remains canonical/reference
3. LTV observation ≠ enforcement (Part 49: observation only)
4. Part 49 withdrawal semantics fixed (3% + 1% = 4%)
5. Cohort-specific portfolio initialization required
6. Initial wealth reconciliation invariant
7. Multi-cohort execution isolated
8. Performance baseline: 1.178× non-debt

### What S5 Is Responsible For

- Interest rate as generic parameter axis (framework capability)
- Full 54-cell grid YAML configuration
- Grid materialization validation
- Full grid execution (93,906 units)
- Research result aggregation with conservation invariants
- ERN research validation with provenance classification
- Performance characterization (measure only)
- Documentation and closure

---

## L. Decision

**S5 PLAN — APPROVED FOR IMPLEMENTATION**

Begin with S5.0/S5.1 only.
