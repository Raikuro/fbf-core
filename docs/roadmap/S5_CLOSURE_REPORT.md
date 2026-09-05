# S5.8 — ERN Part 49 Replication: Final Closure Report

**Stage:** S5.8 — S5 Closure  
**Status:** COMPLETE  
**Date:** 2026-09-05  

---

## 1. Phase Summary (S5.0–S5.8)

| Phase | Commit | Scope | Status |
|-------|--------|-------|--------|
| S5.0 | `fc54202` | Part 49 grid and dataset audit | COMPLETE |
| S5.1 | `fc54202` | Generic interest-rate parameter axis | COMPLETE |
| S5.2 | `2bb72fa` | cohort_horizon_years + grid materialization | COMPLETE |
| S5.3 | `0060694` | End-to-end smoke execution tests | COMPLETE |
| S5.4 | `53badc7` | Canonical Part 49 full execution (10,434 units) | COMPLETE |
| S5.5-R1 | `775d415` | Zero-interest debt semantic correction + aggregation | COMPLETE |
| S5.6 | `5778892` | ERN research validation report | COMPLETE |
| S5.7 | `afebc8d` | Performance benchmark and scaling validation | COMPLETE |
| S5.8 | *(this)* | S5 closure | COMPLETE |

**Total commits:** 8 (S5.0/S5.1 combined in one commit)

---

## 2. Canonical Part 49 Workload Definition

The canonical ERN Part 49 replication workload:

| Parameter | Value |
|-----------|-------|
| Equity allocations | 2 (75%, 100%) |
| Real interest rates | 3 (0%, 1.5%, 3%) |
| Grid cells | 6 |
| Cohorts | 1,739 (60-year horizon, 1871-01-31 to 2015-11-01) |
| Total simulation units | 10,434 |
| Monthly steps per unit | 361 (30y × 12 + 1 base period) |
| Total monthly simulations | 3,766,674 |
| Dataset | `ern_swr_h720.json` (2,459 snapshots) |

**Fixed parameters (not swept):**
- Portfolio withdrawal rate: 3% (SWR)
- Loan draw rate: 1% (total spending: 4%)
- LTV limit: 75% (observation only, NOT enforced)
- Horizon: 30 years (361 months)
- LTV enforcement: OFF

**Distinction from FBF extended research grids:**
The canonical workload replicates only the published ERN Part 49 methodology. The original S5 architecture plan included a 54-cell grid (9 SWR × 2 equity × 3 interest), which is an FBF research extension. This was explicitly excluded from S5 to maintain fidelity to the published methodology. The framework retains the capability for user-defined grids via the generic parameter-axis system.

---

## 3. Key Semantic Corrections Made During S5

### Zero-Interest Debt Correction (S5.5-R1)

**Previous behavior (incorrect):**
- `interest_rate = 0` was interpreted as "no debt configured"
- Zero-interest debt scenarios produced no debt snapshots, no LTV evaluation, no loan draws

**Corrected behavior:**
- `interest_rate = 0` means zero-cost debt when borrowing is configured
- Draws occur, loan balance increases, LTV is evaluated, but no interest accrues
- The distinction between "no debt" and "zero-interest debt" is now explicit

**Implementation:**
- `LoanDrawStep`: Draws when `loan_draw_amount > 0` (not based on `interest_rate`)
- `InterestAccrualStep`: Guards on `loan_balance <= 0` (not on `interest_rate`)
- `LTVEvaluationStep`: Guards on `loan_balance <= 0` (not on `interest_rate`)
- `BuildDecisionContextStep`: Guards on `loan_balance > 0 or interest_rate > 0`
- `MonthlyResultBuilderStep`: Guards on `loan_balance > 0 or interest_rate > 0`

**Validation:**
- 18 unit tests in `test_zero_interest_debt.py`
- Integration tests updated in `test_part49.py` and `test_part49_smoke_execution.py`
- Three debt states verified: no debt, zero-interest debt, interest-bearing debt

**General engine semantics:**
This correction is NOT a Part 49 special case. It is a general engine semantic correction that affects all debt scenarios. The guard logic is now based on loan balance and draw amount rather than interest rate, which is the correct architectural behavior.

---

## 4. ERN Validation Status and Explicit Limitations

### Validated (9 of 11 criteria)

| # | Criterion | Evidence |
|---|-----------|----------|
| 1 | All six canonical cells execute | 10,434 units, 0 failures |
| 2 | Core Part49 methodology reproduced | Loan draws, interest accrual, LTV observation, net-worth identity |
| 3 | LTV observation reproduced | LTV computed at every period, reported in results |
| 4 | Cause of 1929 discrepancy identified | LTV enforcement intentionally disabled |
| 5 | 1965 LTV behavior qualitatively consistent | LTV stays below 75% limit |
| 6 | Discrepancies documented with provenance | S5.6 report with provenance classification |
| 7 | No production code changes required | S5.5-R1 corrections only |
| 8 | Quality gates pass | ruff, mypy, pytest all clean |
| 9 | Validation report complete | `S5_6_ERN_VALIDATION_REPORT.md` |

### Not Validated (1 of 11 criteria)

| # | Criterion | Status | Reason |
|---|-----------|--------|--------|
| 10 | 1929 depletion anchor reproduced | **NOT VALIDATED** | Depends on LTV enforcement, which is intentionally disabled |

### Not Applicable (1 of 11 criteria)

| # | Criterion | Status | Reason |
|---|-----------|--------|--------|
| 11 | LTV enforcement reproduced | **NOT APPLICABLE** | Intentionally disabled in canonical workload |

**Key limitation:** The 1929 depletion anchor (portfolio exhaustion after ~12 years at 100% equity with full leverage) is NOT reproduced by the canonical FBF workload. This is because ERN assumes margin-call enforcement (forced liquidation when LTV > 75%), while FBF deliberately uses `ltv_enforcement: false`. The discrepancy is documented and the architectural decision is intentional.

**Do not upgrade qualitative or non-applicable validation results into PASS for closure purposes.** The NOT VALIDATED status for the 1929 anchor remains accurate and is preserved as-is.

---

## 5. Performance/Scalability Conclusions

### Canonical Workload Characteristics

| Metric | Value |
|--------|-------|
| Total wall time | 369.85s (6.2 minutes) |
| Throughput | 28.2 units/s, 10,191 months/s |
| Peak RSS | 11.1 GB (11,376 MB) |
| Result memory (pickle) | 3.0 GB (10,434 SimulationResults) |
| MonthlyResult memory (pickle) | 6.5 GB (3,766,674 MonthlyResults) |
| Debt overhead | 1.84× non-debt baseline |
| Scaling | Linear (~1.1 MB/unit) |

### Scalability Boundary

The canonical 10,434-unit workload is **operationally viable** on the benchmark hardware (16-core, 16 GB RAM). However, the eager full-result materialization architecture creates a known scalability boundary:

- **Current envelope:** ~14,000 units (estimated 15 GB RSS, approaching 16 GB limit)
- **Borderline:** ~50,000 units (estimated 55 GB RSS, requires 64 GB machine)
- **Not viable:** ~100,000 units (estimated 110 GB RAM, requires high-memory server)

**Eager full-result materialization is acceptable for the current canonical workload.** The architecture represents a known scalability boundary that is explicitly deferred rather than addressed preemptively.

### Deferred Architecture Research

The following architecture findings were established during S5 but are explicitly deferred for future workloads that exceed the current practical envelope:

1. **Batched execution** (`BatchedExecutor` with emit-and-release semantics): Process units in batches of 1,000 with constant ~160 MB peak memory. Total execution time is constant (~155 min for 93,906 units) regardless of batch size.
2. **Normalized persistence** (research-storage model): Store constants once per cell, recover MarketSnapshot from dataset reference, reduce storage from ~20 GB to ~2 GB. The persisted representation is a purpose-built research data model, not a serialized Python object graph.
3. **Hybrid storage format**: SQLite for metadata/summaries + binary files (`struct.pack`) for trajectories. No new dependencies (stdlib `sqlite3` + `struct`).
4. **6 architecturally dead MonthlyResult fields**: `allocation_drift`, `rebalance_result`, `drawdown`, `cumulative_return`, `cumulative_inflation`, `events` — introduced in initial commit (`c07c5b8`), never populated, confirmed dead via provenance audit.
5. **Implementation sequence**: Minimum replication first (S5.4-R3), then batched execution (S5.4-R4), then normalized persistence (S5.4-R5), then full grid (S5.4-S5/S5.6).

These findings are documented in the definitive architecture reference:
- `docs/roadmap/S5_4_R2_ARCHITECTURE.md` — Execution and research result storage architecture design

---

## 6. Deferred Architectural Work

The deferred architecture document is formally incorporated into the repository as a committed research artifact. It is NOT implemented during S5 and remains as the definitive reference for future scalability work.

| Document | Purpose | Key Findings |
|----------|---------|--------------|
| `S5_4_R2_ARCHITECTURE.md` | Execution and research result storage architecture design | BatchedExecutor design, research-storage model, hybrid storage (SQLite + binary), normalization rules, implementation sequence (R3→R4→R5) |

**Classification rationale:** Three additional investigation documents were produced during S5 (`S5_4_R1A_AUDIT.md`, `S5_4_R1B_AUDIT.md`, `S5_4_R1_ARCHITECTURE.md`) but are excluded from the repository:

- `S5_4_R1A_AUDIT.md` (field audit): Historical provenance audit of dead fields. Key findings (6 dead fields, field classification) are captured in the S5.6 validation report and this closure report. The detailed commit-level provenance is investigation material, not durable architectural knowledge.
- `S5_4_R1B_AUDIT.md` (architecture audit): Cost model and object duplication analysis. Superseded by R2, which includes R1B's findings plus the consumer access pattern audit, storage format comparison, and implementation sequence.
- `S5_4_R1_ARCHITECTURE.md` (initial batch architecture): Initial proposal for `BatchScheduler`/`ResultStore`. Superseded by R2, which refines the design with emit-and-release semantics, research-storage model, and hybrid storage format.

---

## 7. Repository/Documentation Changes

### S5 Commits

| Hash | Description | Files |
|------|-------------|-------|
| `fc54202` | S5.0/S5.1: generic interest-rate axis + Part 49 grid audit | Grid audit, parameter axis |
| `2bb72fa` | S5.2: cohort_horizon_years + grid materialization | Grid materialization, 361-month horizon |
| `0060694` | S5.3: end-to-end smoke execution tests | Smoke tests |
| `53badc7` | S5.4: canonical Part 49 execution (10,434 units) | Execution test, canonical workload |
| `775d415` | S5.5-R1: zero-interest debt correction + aggregation | Pipeline steps, aggregation, 18 unit tests |
| `5778892` | S5.6: ERN research validation report | Validation report |
| `afebc8d` | S5.7: performance benchmark + scaling validation | Benchmark script, performance report |

### Documentation

| File | Purpose | Status |
|------|---------|--------|
| `docs/roadmap/S5_ARCHITECTURE_PLAN.md` | S5 architecture plan | Committed (S5.0) |
| `docs/roadmap/S5_6_ERN_VALIDATION_REPORT.md` | ERN validation report | Committed (S5.6) |
| `docs/roadmap/S5_7_PERFORMANCE_REPORT.md` | Performance report | Committed (S5.7) |
| `docs/roadmap/s57_benchmark_results.json` | Raw benchmark results | Committed (S5.7) |
| `docs/roadmap/S5_4_R2_ARCHITECTURE.md` | Deferred: architecture design | Committed (S5.8) |
| `docs/roadmap/S5_CLOSURE_REPORT.md` | S5 closure report | Committed (S5.8) |

### Code Changes

| File | Change | Commit |
|------|--------|--------|
| `src/fbf/core/execution/pipeline/steps/loan_draw_step.py` | Draw on `loan_draw_amount > 0` | S5.5-R1 |
| `src/fbf/core/execution/pipeline/steps/interest_accrual_step.py` | Guard on `loan_balance <= 0` | S5.5-R1 |
| `src/fbf/core/execution/pipeline/steps/ltv_evaluation_step.py` | Guard on `loan_balance <= 0` | S5.5-R1 |
| `src/fbf/core/execution/pipeline/steps/build_decision_context_step.py` | Guard on `loan_balance > 0 or interest_rate > 0` | S5.5-R1 |
| `src/fbf/core/execution/pipeline/steps/monthly_result_builder_step.py` | Guard on `loan_balance > 0 or interest_rate > 0` | S5.5-R1 |
| `src/fbf/core/research/part49_aggregation.py` | Cell-level aggregation | S5.5-R1 |

---

## 8. Final Quality Gates

| Gate | Command | Result |
|------|---------|--------|
| Lint | `ruff check src tests` | All checks passed |
| Type check | `mypy --strict .` | Success: no issues found in 243 source files |
| Unit + contract tests | `pytest tests/unit/ tests/contract/` | 1078 passed, 0 failed |
| Contract tests | `pytest tests/contract/` | 16 passed |

---

## 9. Recommended Next Phase

**S5 is complete.** The canonical ERN Part 49 replication has been executed, validated, benchmarked, and documented.

**Authoritative next phase (from MULTI_STUDY_REPLICATION_ROADMAP.md):**

**S6 — Part 52 Timing Leverage**: Add drawdown-triggered borrowing, repayment semantics, and FFR-based floating interest. The Part 49 debt infrastructure (loan_draw_step, interest_accrual_step, ltv_evaluation_step) is directly reusable.

**Engine modification assessment for S6:** No engine modification is currently justified. S6 planning must verify whether the existing engine and pipeline contracts can express Part 52 semantics cleanly. Any engine change must be justified by a concrete architectural limitation and must preserve the Decimal reference engine's mathematical behavior. See `MULTI_STUDY_REPLICATION_ROADMAP.md` §J for the engine change assessment framework.

**Deferred framework enhancements (NOT roadmap phases, tracked in TODO.md):**

- **User-defined research grids**: The generic parameter-axis system (S5.1) already supports arbitrary parameter sweeps. No additional phase is required.
- **Scalability architecture** (batched execution, normalized persistence): Documented in `S5_4_R2_ARCHITECTURE.md`. Required only when workloads exceed the ~14,000-unit envelope. Tracked in TODO.md under "Deferred Scalability Architecture."
- **Result-model cleanup** (dead MonthlyResult fields): Separate model-cleanup decision. Tracked in TODO.md under "Dead MonthlyResult fields."
- **FFR dataset investigation**: Blocking prerequisite for Part 52 floating-rate scenarios. Tracked in TODO.md under "S6 Prerequisite: FFR Dataset Investigation."

**Do not begin S6 without explicit authorization.**

---

## 10. S5 Acceptance Matrix

| # | Criterion | Evidence | Status |
|---|-----------|----------|--------|
| 1 | S5.0–S5.7 all complete | Commit history verified | **PASS** |
| 2 | Canonical workload correctly defined | 6 cells × 1,739 cohorts = 10,434 units | **PASS** |
| 3 | Zero-interest debt correction included | S5.5-R1 commit, 18 unit tests | **PASS** |
| 4 | Semantic correction is general (not Part 49-specific) | Guards based on loan_balance, not interest_rate | **PASS** |
| 5 | 1929 validation gap documented | S5.6 report, NOT VALIDATED status preserved | **PASS** |
| 6 | LTV enforcement limitation documented | S5.6 report, architectural decision preserved | **PASS** |
| 7 | Performance characteristics measured | S5.7 report, 6.2 min, 11.1 GB RSS | **PASS** |
| 8 | Scalability boundary documented | S5.7 report, ~14,000 unit envelope | **PASS** |
| 9 | Deferred work formally documented | `S5_4_R2_ARCHITECTURE.md` committed as definitive architecture reference | **PASS** |
| 10 | Quality gates pass | ruff, mypy, pytest all clean | **PASS** |
| 11 | No unnecessary production changes | Only semantic corrections, no optimization | **PASS** |

**S5 ACCEPTANCE: ALL CRITERIA PASS**

---

## S5.8 Status

**S5.8 COMPLETE — RECONCILED 2026-09-05**

The S5 phase (ERN Part 49 replication) is internally consistent, properly documented, and complete. All 8 subphases are complete, the canonical workload is correctly defined and validated, semantic corrections are properly recorded, validation boundaries are preserved, and performance characteristics are documented. Deferred architectural work is formally tracked in TODO.md. Next-phase recommendations have been reconciled with the authoritative roadmap (S6 = Part 52 Timing Leverage).
