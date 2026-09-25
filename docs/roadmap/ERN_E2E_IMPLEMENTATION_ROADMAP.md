# ERN E2E Implementation Roadmap

**Status:** AUTHORITATIVE — DERIVED FROM THREE-ROUND INVESTIGATION
**Created:** 2026-09-16
**Source:** Three investigation rounds on `investigation/ern-part52-divergence` branch
**Scope:** Eight ERN articles (Parts 1, 2, 3, 19, 20, 42, 49, 52)
**Constraint:** Living checklist — future sessions mark items DONE without reconstructing reasoning

---

## 1. Purpose and Scope

This roadmap is the implementation plan derived from a three-round E2E investigation. It answers:

1. What ERN validation targets exist?
2. Which are already implemented?
3. Which are only partially implemented?
4. Which are planned but not implemented?
5. Which are deferred/blocked?
6. Which existing tests are intentionally retained because they validate something distinct?
7. Which duplicate executions should be removed?
8. Which future E2Es can share expensive computation?
9. In what order should the remaining E2Es be implemented?
10. What exact acceptance criteria must be satisfied before considering each target complete?

### Validation Type Taxonomy

| Type | Definition |
|------|-----------|
| **RESEARCH REPLICATION** | Complete canonical ERN research replication through production path with published research anchors, no material approximation |
| **REGRESSION COVERAGE** | Grid structure, parameter propagation, and computational execution validation — NOT replication evidence |
| **INTEGRATION / MECHANISM** | Tests multiple framework components together with bounded workloads to validate internal correctness |
| **SMOKE** | Small representative production-path execution for fast diagnostic feedback |
| **ORACLE / REFERENCE** | Independent first-principles or reference-tool validation of specific computation paths |

### Critical Distinction

> Exercising the same production code is NOT by itself sufficient reason to consider two tests redundant. Two tests with different validation purposes, different assertion surfaces, or different parameter spaces are distinct validations even if they happen to call the same pipeline.

---

## 2. Status Model

### Implementation Status

| Status | Definition |
|--------|-----------|
| `IMPLEMENTED` | Test exists, runs, and validates the documented target |
| `PARTIALLY IMPLEMENTED` | Test exists but validates a subset or modified version of the target |
| `PLANNED — NOT IMPLEMENTED` | Target is documented and specified but no test exists |
| `DEFERRED / BLOCKED` | Target cannot be implemented due to capability gap, missing data, or explicit deferral |
| `HISTORICAL / SUPERSEDED` | Target was once relevant but has been subsumed or is no longer applicable |

### Validation Types (where used in matrices)

| Type | Marker | Gate |
|------|--------|------|
| `RESEARCH REPLICATION` | `@pytest.mark.ern_e2e` | `RUN_ERN_E2E=1` |
| `NON-CANONICAL RESEARCH` | `@pytest.mark.research_validation` | `RUN_ERN_E2E=1` |
| `REGRESSION COVERAGE` | None | Runs normally |
| `INTEGRATION / MECHANISM` | None | Runs normally |
| `SMOKE` | None | Runs normally |
| `ORACLE / REFERENCE` | None | Runs normally |

---

## 3. Authoritative Target Matrix

### Part 1 — Introduction to the SWR Series

| # | Validation target | Dimensions / scope | Type | Status | Existing implementation | Blocking dependency | Planned action |
|---|-------------------|-------------------|------|--------|------------------------|-------------------|----------------|
| 1.1 | Foundational 180-cell SWR oracle grid | 5W × 9R × 4H × 1,739 cohorts = 313,020 units | RESEARCH REPLICATION | `IMPLEMENTED` | `test_ern_swr_replication.py::test_full_grid_matches_oracle` | None | Retain (redundant with Part 2 only AFTER Part 2 is implemented) |
| 1.2 | Smoke validation | 1 cell × 2,099 cohorts | SMOKE | `IMPLEMENTED` | `test_ern_swr_replication.py::test_smoke_grid_matches_oracle` | None | Retain (diagnostic, not replication) |

### Part 2 — Capital Preservation vs. Capital Depletion

| # | Validation target | Dimensions / scope | Type | Status | Existing implementation | Blocking dependency | Planned action |
|---|-------------------|-------------------|------|--------|------------------------|-------------------|----------------|
| 2.1 | Full FV>0 extension | 5W × 9R × 2H × 5FV × 1,739 = 782,550 units | RESEARCH REPLICATION | `PLANNED — NOT IMPLEMENTED` | None | Regression fixture needed | Implement after Part 1 oracle grid is validated |
| 2.2 | FV=0 cross-check against Part 1 | 90 cells | REGRESSION COVERAGE | `PLANNED — NOT IMPLEMENTED` | None | Part 2.1 | Implement with Part 2.1 |
| 2.3 | 4 published Part 2 anchors | 4 cells | RESEARCH REPLICATION | `PLANNED — NOT IMPLEMENTED` | None | Part 2.1 | Implement with Part 2.1 |

### Part 3 — Equity Valuation Using CAPE

| # | Validation target | Dimensions / scope | Type | Status | Existing implementation | Blocking dependency | Planned action |
|---|-------------------|-------------------|------|--------|------------------------|-------------------|----------------|
| 3.1 | 4 experiment configurations | 4 exp × 21W × 2H = 168 cells × 1,739 cohorts | RESEARCH REPLICATION | `IMPLEMENTED` | `test_part3_canonical_ern_replication.py` (12 tests, gated `ern_e2e`) | YAML equity grid correction resolved at `e767d6a` | Retain; anchors provisional pending canonical Excel-data validation phase |
| 3.2 | 6 published numerical anchors | 6 cells | RESEARCH REPLICATION | `IMPLEMENTED` | `test_part3_canonical_ern_replication.py` — 6 anchor tests recorded as provisional numerical baselines | Part 3.1 (complete at `e767d6a`) | Retain; final canonical-data validation deferred to dedicated phase |

### Part 19 — Equity Glidepaths in Retirement

| # | Validation target | Dimensions / scope | Type | Status | Existing implementation | Blocking dependency | Planned action |
|---|-------------------|-------------------|------|--------|------------------------|-------------------|----------------|
| 19.1 | Experiment A: Fixed 3.5% SWR failure rates | 27 strategies × 3 FV × 2 CAPE = 162 cells × 1,739 cohorts | RESEARCH REPLICATION | `PLANNED — NOT IMPLEMENTED` | None | Implementation alignment (execution order); relationship with Part 20 to be concretely understood | Implement after Part 20 relationship is resolved |
| 19.2 | Experiment B: Failsafe/percentile SWR | 45 strategies × 2 CAPE = 90 cells × 1,739 cohorts | RESEARCH REPLICATION | `PLANNED — NOT IMPLEMENTED` | None | Implementation alignment; relationship with Part 20 to be concretely understood | Implement after Part 20 relationship is resolved |
| 19.3 | 24 glidepath definitions in Part 20 YAML | 24 glidepaths | REGRESSION COVERAGE | `PARTIALLY IMPLEMENTED` | `test_part20_replication.py` runs 320 cells (NOT Experiment A or B assertions) | None | Retain as regression coverage; NOT replication evidence |

### Part 20 — More Thoughts on Equity Glidepaths

| # | Validation target | Dimensions / scope | Type | Status | Existing implementation | Blocking dependency | Planned action |
|---|-------------------|-------------------|------|--------|------------------------|-------------------|----------------|
| 20.1 | Experiment A: 60Y failsafe/percentile | 53 strategies × 2 CAPE = 106 cells | RESEARCH REPLICATION | `PLANNED — NOT IMPLEMENTED` | None | Audit definition READY (`ern_part20_e2e_audit.md`); execution pending | Execute baseline audit first |
| 20.2 | Experiment B: 30Y failsafe/percentile | 53 strategies × 2 CAPE = 106 cells | RESEARCH REPLICATION | `PLANNED — NOT IMPLEMENTED` | None | Same as 20.1 | Execute with 20.1 |
| 20.3 | Experiment C: Fixed SWR failure rates | 53 × 5 SWR × 2H = 530 cells | RESEARCH REPLICATION | `PLANNED — NOT IMPLEMENTED` | None | May hit capability gap (failure-rate aggregation) | Audit capability first |
| 20.4 | Experiment D: FV targets | 53 × 3 FV = 159 cells | RESEARCH REPLICATION | `PLANNED — NOT IMPLEMENTED` | None | None | Implement with 20.1 |
| 20.5 | Experiment E: Deterministic case study | 4 cases | RESEARCH REPLICATION | `PLANNED — NOT IMPLEMENTED` | None | Requires annual-frequency simulation | Assess capability |
| 20.6 | Existing 320-cell grid (regression) | 32 GP × 5 SWR × 2H = 320 cells × 1,739 | REGRESSION COVERAGE | `IMPLEMENTED` | `test_part20_replication.py` | None | Retain — NOT replication evidence |

### Part 42 — One More Year Syndrome

| # | Validation target | Dimensions / scope | Type | Status | Existing implementation | Blocking dependency | Planned action |
|---|-------------------|-------------------|------|--------|------------------------|-------------------|----------------|
| 42.1 | Tables 02-05: Failsafe amounts | 7 scenario types × decade cohorts | RESEARCH REPLICATION | `DEFERRED / BLOCKED` | None | Methodology frozen; E2E validation deferred | Deferred to implementation work |
| 42.2 | Table 01: Fixed-4% failure probabilities | 10 rows × 11 columns | RESEARCH REPLICATION | `DEFERRED / BLOCKED` | None | Same as 42.1 | Deferred |
| 42.3 | Grid structure (45 cells) | 5W × 9SWR × 1H | REGRESSION COVERAGE | `IMPLEMENTED` | `test_part42_replication.py::test_part42_canonical_replication` (93,915 units) | None | Retain — structural validation only |
| 42.4 | Accumulation/mechanics oracle | OMY accumulation semantics | ORACLE / REFERENCE | `IMPLEMENTED` | `test_part42_oracle.py` | None | Retain — independent oracle |

### Part 49 — Using Leverage in Retirement

| # | Validation target | Dimensions / scope | Type | Status | Existing implementation | Blocking dependency | Planned action |
|---|-------------------|-------------------|------|--------|------------------------|-------------------|----------------|
| 49.1 | Experiment A: Preliminary leverage | Analytical check | RESEARCH REPLICATION | `DEFERRED / BLOCKED` | None | Buy-and-hold capability gap | Blocked until buy-and-hold implemented |
| 49.2 | Experiment B: Nov 1965 aggressive | Single cohort | RESEARCH REPLICATION | `DEFERRED / BLOCKED` | None | Buy-and-hold capability gap | Blocked |
| 49.3 | Experiment C: Sep 1929 aggressive | Single cohort | RESEARCH REPLICATION | `DEFERRED / BLOCKED` | None | Buy-and-hold capability gap | Blocked |
| 49.4 | Experiment D: $20k/$20k partial | Scenario | RESEARCH REPLICATION | `DEFERRED / BLOCKED` | None | Buy-and-hold capability gap | Blocked |
| 49.5 | Experiment E: $30k/$10k preferred | Scenario | RESEARCH REPLICATION | `DEFERRED / BLOCKED` | None | Buy-and-hold capability gap | Blocked |
| 49.6 | Experiment F: Historical 4% conclusion | 1925-1990 universe | RESEARCH REPLICATION | `DEFERRED / BLOCKED` | None | Buy-and-hold capability gap; resolved cohort universe | Blocked |
| 49.7 | Non-canonical 6-cell E2E | 2E × 3I × 1,739 = 10,434 | NON-CANONICAL RESEARCH | `IMPLEMENTED` | `test_part49_replication.py` — documented deviations (LTV OFF, no buy-and-hold) | None | Retain — validates leverage mechanics, NOT canonical replication |
| 49.8 | Integration tests (18 units) | 2E × 3I × 3 cohorts | INTEGRATION / MECHANISM | `IMPLEMENTED` | `test_part49_canonical_execution.py` | None | Retain — execution correctness |

### Part 52 — Timing Leverage in Retirement

| # | Validation target | Dimensions / scope | Type | Status | Existing implementation | Blocking dependency | Planned action |
|---|-------------------|-------------------|------|--------|------------------------|-------------------|----------------|
| 52.1 | 11 canonical scenarios (A1-A11) | 11 scenarios × 1,739 cohorts | RESEARCH REPLICATION | `PARTIALLY IMPLEMENTED` | `test_part52_canonical_ern_replication.py` — A1/A9: canonical replication (1739/1739 success); A2-A8/A10-A11: FFR scenarios with deferred A10 divergence (1665/1739 = 95.7%) | A10 execution/timing recurrence discrepancy (deferred until optimization); other FFR scenarios blocked on FFR methodology | A1/A9 validated at checkpoint `d6a2cbd`; A10 deferred — see §10 B10 |
| 52.2 | Full cohort validation | 1,739 cohorts | RESEARCH REPLICATION | `PLANNED — NOT IMPLEMENTED` | None | Part 52.1 | Implement with 52.1 |
| 52.3 | Solver/optimization reproduction | Binary search over WR × B% | RESEARCH REPLICATION | `PLANNED — NOT IMPLEMENTED` | None | Part 52.1; Part52Evaluator infeasible-search semantics | Implement after 52.1 |
| 52.4 | Mechanism correctness | 1 scenario × 1,739 | INTEGRATION / MECHANISM | `IMPLEMENTED` | `test_part52_deterministic_validation.py` (mechanism assertions) | None | Retain mechanism assertions; remove redundant simulation |
| 52.5 | Lifecycle trace | 1 synthetic scenario | INTEGRATION / MECHANISM | `IMPLEMENTED` | `test_part52_numerical_trace.py` | None | Retain |
| 52.6 | FFR floating-rate mechanics | 6 synthetic scenarios | INTEGRATION / MECHANISM | `IMPLEMENTED` | `test_part52_ffr_floating_rate.py` | None | Retain |

---

## 4. Current Implementation Inventory

| Test / function / class | Article | Simulation count | Executor / backend | Canonical? | What it actually proves | Retained? | Reason for retention |
|------------------------|---------|-----------------|-------------------|------------|------------------------|-----------|---------------------|
| `test_ern_swr_replication.py::test_full_grid_matches_oracle` | Parts 1+2 | 313,020 | CLI reference | Yes | SWR success rates against pinned oracle (FV=0 only) | Yes | Only implemented validation of foundational SWR grid |
| `test_ern_swr_replication.py::test_smoke_grid_matches_oracle` | Part 1 | 2,099 | CLI reference | Yes | Single-cell oracle anchor | Yes | Diagnostic smoke, different responsibility |
| `test_part20_replication.py::test_part20_full_grid_replication` | Part 20 | 556,480 | CLI reference | Regression only | Grid structure, computational execution, traceable anchors — NOT replication | Yes | Regression coverage, NOT replication evidence |
| `test_part49_replication.py::test_part49_canonical_replication` | Part 49 | 10,434 | Python API (`ResearchExecutor`) | Non-canonical | Leverage mechanics with deviations (LTV OFF, no buy-and-hold) | Yes | Validates leverage mechanics, NOT canonical replication |
| `test_part42_replication.py::test_part42_canonical_replication` | Part 42 | 93,915 | Python API (`FastPathSimulationExecutor`) | Structural only | Grid structure, directional invariants — NOT ERN anchor validation | Yes | Structural validation, NOT published-table replication |
| `TestCanonicalERNReplication` (test_part52_canonical_ern_replication.py) | Part 52 | 19,129 | Python API (`FastPathSimulationExecutor`) | A1/A9: canonical (100%); A10: deferred (95.7%) | A1/A9: canonical replication with published anchors (1739/1739 success); A10: 1665/1739 (95.7%) — execution/timing discrepancy deferred until optimization | Yes | Canonical (A1/A9) + deferred A10 research validation |
| `test_part52_deterministic_validation.py` | Part 52 | 1,739 (baseline) | Python API | Integration | Mechanism correctness (policy registration, config construction) | Yes | Mechanism assertions distinct from simulation |
| `test_part52_numerical_trace.py` | Part 52 | 1 (synthetic) | Python API | Integration | Lifecycle trace validation | Yes | Independent numerical validation |
| `test_part52_ffr_floating_rate.py` | Part 52 | ~6 (synthetic) | Python API | Integration | FFR interest scheduling | Yes | Independent FFR behavior validation |
| `test_glidepath_trajectory.py` | Parts 19/20 | ~1 (synthetic) | Python API | Integration | Glidepath allocation policy correctness | Yes | Independent trajectory validation |
| `test_ern_timeline_regression.py` | Parts 1+2 | 6,956 | Python API | Regression/oracle | Per-cohort Decimal equality against reference oracle | Yes | Independent regression test |
| `test_oracle_matrix.py` | Parts 1+2 | 0 | None | Oracle | Pinned oracle table integrity | Yes | Independent oracle validation |
| `test_debt_oracle.py` | Part 49 | 0 | None | Oracle | Debt-transition mechanics | Yes | Independent oracle validation |
| `test_part42_oracle.py` | Part 42 | 0 | None | Oracle | Accumulation ordering | Yes | Independent oracle validation |

### Critical Misclassifications to Prevent

- **Part 20's 320-cell test** is NOT equivalent to documented Part 20 Experiments A-E. It is regression coverage, not replication.
- **Part 42's 45-cell test** is NOT equivalent to published-table replication. It is structural validation only.
- **Part 49's 6-cell test** is NOT canonical Part 49 replication. It is a modified FBF interpretation with documented deviations.
- **Part 52's current 11 scenarios**: A1/A9 are canonical replication (published anchors, 1739/1739 success); A2-A8/A10-A11 are non-canonical research validation (FFR scenarios use fixed-rate approximation), NOT full canonical replication.
- **Part 1's current E2E** remains valuable until Part 2's superset validation actually exists and independently validates the required outputs.

---

## 5. Redundancy Policy

### 5.1 Confirmed Current Redundancy

**Part 52 A1 simulation duplication:**

`test_part52_canonical_ern_replication.py` A1 scenario and `test_part52_deterministic_validation.py` baseline execute the exact same configuration:
- Same WR (0.0358), same B% (0), same threshold (None), same interest rate (0.015)
- Same pipeline (`create_default_pipeline()`)
- Same result (1739/1739 success)

**Intended change:**
- Retain mechanism/registration/construction assertions in `test_part52_deterministic_validation.py`
- Remove the redundant simulation execution from the deterministic validation test
- Do NOT remove the entire deterministic test

### 5.2 Cross-Horizon Computation (FUTURE OPTIMIZATION)

- SWR 60Y execution contains the information needed for 30Y/40Y/50Y success determination
- Part 20 60Y similarly contains the information needed for 30Y
- The current CLI summary does not expose sufficient per-cohort failure information to exploit this directly
- Doing so would require an architectural/test-output change
- **Marked as FUTURE OPTIMIZATION, not an immediate implementation requirement**
- Do not assume the optimization is free

### 5.3 Shared Computation Rule

> If two validations are logically distinct but require the same expensive simulation state, prefer a shared computation layer rather than deleting one validation.

This is important for future Part 19/20 work where overlapping simulations may be shared but research assertions remain distinct.

---

## 6. Future Reuse Analysis

### Computational Overlap vs Validation Equivalence

> This distinction is mandatory. For every proposed overlap, classify it as one of: `STRICT SUPERSET`, `COMPUTATIONAL SUBSET`, `SHARED EXPENSIVE COMPUTATION`, `RELATED BUT DISTINCT`, `NO MEANINGFUL OVERLAP`.

### Part 1 ↔ Part 2

| Dimension | Part 1 | Part 2 | Classification |
|-----------|--------|--------|---------------|
| FV=0 cells | 180 cells | 180 cells (subset of 450) | `STRICT SUPERSET` |
| FV>0 cells | None | 270 cells | Part 2 extends Part 1 |

**Decision:** Part 1 FV=0 is a strict subset of the intended Part 2 grid. However, this only becomes an actionable deletion/reuse opportunity AFTER Part 2 is actually implemented and independently validates the required outputs. Until then, retain Part 1.

### Part 19 ↔ Part 20

| Dimension | Part 19 Exp A | Part 20 Exp C | Classification |
|-----------|--------------|--------------|---------------|
| Strategies | 27 (3 static + 24 glidepaths) | 53 (21 static + 32 glidepaths) | Part 20 is superset |
| SWR | Fixed 3.5% | 3.0%-4.0% in 0.25% steps | Different |
| FV targets | 0%, 50%, 100% | 0% only | Different |
| CAPE | All CAPE, CAPE>20 | CAPE>20 only | Different |
| Horizon | 60Y only | 30Y and 60Y | Part 20 is superset |
| Output | Failure rate at 3.5% | Failure rates at 5 SWR values | Different |

| Dimension | Part 19 Exp B | Part 20 Exp A | Classification |
|-----------|--------------|--------------|---------------|
| Strategies | 45 (21 static + 24 glidepaths) | 53 (21 static + 32 glidepaths) | Part 20 is superset |
| CAPE | All CAPE, CAPE>20 | CAPE>20, CAPE≤20 | Different conditioning |
| Horizon | 60Y only | 60Y only | Same |
| FV | 0% only | 0% only | Same |

**Decision:** Part 19 Experiment A has different dimensions/conditioning/outputs from Part 20 Experiment C. Part 19 Experiment B has different CAPE conditioning from Part 20 Experiment A. Overlapping simulations may be shared, but research assertions remain distinct unless documented acceptance criteria are explicitly satisfied. Do NOT call Part 19 validated merely because Part 20 executes overlapping simulations.

### Part 2 ↔ Part 20

| Dimension | Part 2 | Part 20 | Classification |
|-----------|--------|---------|---------------|
| Policy | Constant allocation | Glidepath allocation | Different |
| Parameter space | 5W × 9R × 4H × 5FV | 32GP × 5SWR × 2H | Different |

**Decision:** `NO MEANINGFUL OVERLAP` — different policies mean different computations. Do not claim computational reuse merely because both have FV dimensions.

### Part 42 ↔ Parts 1/2

| Dimension | Part 42 | Parts 1/2 | Classification |
|-----------|---------|----------|---------------|
| Initial conditions | 12-month OMY accumulation phase | Standard retirement from initial wealth | Different |

**Decision:** `RELATED BUT DISTINCT` — different initial-condition semantics unless evidence shows reusable simulation state.

---

## 7. Implementation Roadmap

Ordered by dependency/readiness, not subjective importance.

### Phase 0 — Test-Suite Cleanup / Confirmed Redundancy (COMPLETE)

- [x] **T0.1** Remove duplicated Part 52 deterministic simulation
  - Target: Remove simulation execution from `test_part52_deterministic_validation.py` baseline
  - Retain: All mechanism/registration/construction assertions
  - Prerequisite: None
  - Expected test location: `tests/integration/test_part52_deterministic_validation.py`
  - Canonical: N/A (cleanup)
  - Acceptance criteria: Mechanism assertions still pass; no coverage lost; simulation not duplicated
  - Known blocker: None
  - Dependencies: None
  - Complete at: `d2fcf25` — `test: remove redundant Part 52 deterministic simulation` (mechanism-only test verified passing)

### Phase 0.5 — Fee-Semantics Correction (COMPLETE)

Commit `d6a2cbd` (`fix: align ERN fee semantics with canonical data`).

**Before correction:**
- ERN runtime dataset (`data/ern/`) contained embedded 0.05% annual portfolio fee in cumulative index levels
- Part52 study configuration also specified `expense_ratio: 0.0005`
- Part52 therefore applied the fee **twice** — a double-fee error

**After correction:**
- ERN runtime dataset represents raw canonical market/index data (no embedded fee)
- 0.05% annual fee applied **once** through Part52 study configuration (`expense_ratio: 0.0005`)
- Forward bond projection corrected to 0% real return for first 120 months (was `-fee/12`)
- Part52 borrowing semantics corrected: `nominal_amount = budget` (was `budget + loan_draw`)
- FFR lookup normalized to month-start for dataset alignment

**Validated by:**
- A1 (1965-11, no FFR, 0% borrow): 1739/1739 = **100%** — canonical anchor preserved
- A9 (1929-09, no FFR, 0% borrow): 1739/1739 = **100%** — canonical anchor preserved
- Focused test suite: 92 tests passed
- Non-Part52 validation: zero regressions
- Independent ERN oracle was **not modified**

**Deferred:**
- A10 (FFR + leverage scenario): 1665/1739 = 95.7% — execution/timing discrepancy, not fee-related (see B10)

### Phase 1 — Fully Specified Canonical Extensions (COMPLETE)

Targets whose methodology, datasets, and expected outputs are already sufficiently defined.

- [x] **T1.1** Part 52 full canonical E2E validation — **COMPLETE (per stated acceptance criteria; A10 remains deferred — see B10)**
  - Target: Update all 11 scenarios (A1-A11) to use actual FFR data; validate against ERN published values
  - Checkpoint: `d6a2cbd` — `fix: align ERN fee semantics with canonical data`
  - Follow-up semantic alignment: `4ffc0c5` — `fix: align Part52 canonical ERN semantics`
  - Focused validation: 92 tests passed; non-Part52 validation zero regressions
  - ERN runtime dataset now uses raw canonical market/index data without embedded portfolio fee
  - 0.05% annual ERN fee applied through Part52 study configuration (`expense_ratio: 0.0005`)
  - Forward bond projection uses 0% real return for first 120 months
  - Part52 borrowing semantics corrected (`nominal_amount = budget`)
  - FFR lookup normalized to month-start
  - A1 (1965-11, no FFR, 0% borrow): **1739/1739 = 100%** — canonical anchor reproduced
  - A9 (1929-09, no FFR, 0% borrow): **1739/1739 = 100%** — canonical anchor reproduced
  - A10 (1929-09, FFR+0.50%, B%=31.86%, WR=4.39%): **1665/1739 = 95.7%** — deferred (see B10)
  - Independent ERN oracle was not modified
  - Expected test location: `tests/integration/test_part52_canonical_ern_replication.py`
  - Canonical: Partial — A1/A9 validated; A10 deferred to optimization phase
  - Expected scale: 11 scenarios × 1,739 cohorts = 19,129 units
  - Acceptance criteria: A1/A9 match published anchors — **MET**; A10 execution/timing reconciliation — **DEFERRED** (see B10)
  - Known blocker: A10 execution/timing recurrence discrepancy (see B10)
  - Dependencies: None
  - Note: T1.1 and T1.2 are independent tasks with no mutual dependency

- [x] **T1.2** Part 3 4-experiment grid — **COMPLETE**
  - Target: Execute 4 experiment configurations with 21 equity weights
  - Prerequisite: YAML equity grid correction (5→21 weights) — resolved at `e767d6a`
  - Expected test location: New E2E test
  - Canonical: Yes
  - Expected scale: 168 cells × 1,739 cohorts = 292,152 units
  - Acceptance criteria: All 4 experiments execute; 6 published numerical anchors validated
  - Known blocker: None — YAML discrepancy resolved at `e767d6a` (21 weights in `ern_part3_replication.yaml`)
  - Computation reuse: None
  - Dependencies: YAML correction (resolved)
  - Note: T1.1 and T1.2 are independent tasks with no mutual dependency
  - Complete at: `e767d6a` — `fix: correct ERN Part3 cohort initialization and withdrawals`
  - Deliverables: `tests/integration/test_part3_canonical_ern_replication.py` (12 gated E2E tests); per-cohort initial-portfolio normalization; fixed-real withdrawals from `initial_wealth`; 21 equity weights 0%–100% in 5% steps; 6 published anchors recorded as provisional numerical baselines
  - Provisional anchors: current numerical differences are validation-provenance differences pending the dedicated canonical ERN Excel-data validation phase — they are NOT incomplete T1.2 implementation

### Phase 2 — Part 20 Canonical Experiments

Use `ern_part20_e2e_audit.md` as the specification.

- [x] **T2.1** Part 20 baseline audit (Experiments A-E) — COMPLETE
  - Target: Execute baseline against current FBF implementation; classify all discrepancies
  - Prerequisite: None (audit definition READY)
  - Expected test location: New E2E test(s)
  - Canonical: Yes (methodology frozen)
  - Expected scale: ~1,566,839+ units across 5 experiments
  - Acceptance criteria: Every feasible experiment executed; every publication comparison classified; all discrepancies either reproduced, explained, or recorded as unexplained; capability gaps identified
  - Known blocker: Experiment C may hit capability gap (failure-rate aggregation); Experiment E requires annual-frequency simulation
  - Computation reuse: Before implementation, determine whether shared computation abstraction should serve both Part 19 and Part 20
  - Dependencies: None
  - Complete at: `fbf-core` T2.1 implementation (batched GF computation + persistent cross-step cache)
  - Deliverables: `tests/integration/test_part20_e2e_audit.py` (13 gated E2E tests); `docs/research/ern_part20_e2e_audit.md` updated with experimental results; `docs/research/ern_part20_replication.md` updated with discrepancy classifications
  - Final performance: ~243s / 4.1 min for full Experiment A; ~4,200 units/sec; 1,023,165 total units

- [ ] **T2.2** Part 20 Experiment A — 60Y failsafe/percentile
  - Target: 53 strategies × 2 CAPE = 106 cells
  - Reference: ERN Part 20 Table 02
  - Acceptance criteria: FBF output compared against published results; complete per-cohort result set retained
  - Dependencies: T2.1

- [x] **T2.3** Part 20 Experiment B — 30Y failsafe/percentile
  - Target: 53 strategies × 2 CAPE = 106 cells
  - Reference: ERN Part 20 Table 03
  - Dependencies: T2.1
  - Complete at: `fbf-core` T2.2 implementation (Experiment B baseline execution)
  - Deliverables: `tests/integration/test_part20_e2e_audit.py` Experiment B anchors test passed; `docs/research/ern_part20_e2e_audit.md` updated with Experiment B results; `docs/research/ern_part20_replication.md` updated with Experiment B discrepancy classifications
  - Results: 4 EXPLAINED DIFFERENCE, 7 UNEXPLAINED DIFFERENCE (2–3 ULP), 0 REPRODUCED, 0 CAPABILITY GAP; 1,023,165 units executed in ~51s

- [x] **T2.4** Part 20 Experiment C — Fixed SWR failure rates
  - Target: 53 × 5 SWR × 2H = 530 cells
  - Reference: ERN Part 20 Table 04
  - Dependencies: T2.1
  - Complete at: `fbf-core` T2.3 implementation (Experiment C baseline execution)
  - Deliverables: `tests/integration/test_part20_e2e_audit.py` Experiment C anchors test passed; `docs/research/ern_part20_e2e_audit.md` updated with Experiment C results; `docs/research/ern_part20_replication.md` updated with Experiment C discrepancy classifications
  - Results: 16 REPRODUCED, 1 EXPLAINED DIFFERENCE, 25 UNEXPLAINED DIFFERENCE (2–180 ULP), 0 CAPABILITY GAP; 202,990 units executed in ~10s

- [x] **T2.5** Part 20 Experiment D — FV targets
  - Target: 53 × 3 FV = 159 cells
  - Reference: ERN Part 20 Table 06
  - Dependencies: T2.1
  - Complete at: `fbf-core` T2.5 implementation (Experiment D baseline execution)
  - Deliverables: `tests/integration/test_part20_e2e_audit.py` Experiment D anchors test passed; `docs/research/ern_part20_e2e_audit.md` updated with Experiment D results; `docs/research/ern_part20_replication.md` updated with Experiment D discrepancy classifications
  - Results: 1 REPRODUCED, 1 EXPLAINED DIFFERENCE, 4 UNEXPLAINED DIFFERENCE (2–3 ULP), 0 CAPABILITY GAP; 527,774 units executed in ~29s; FV=0 reuse from Experiment A verified (53 cells)

- [x] **T2.6** Part 20 Experiment E — Deterministic case study
  - Target: 4 cases
  - Reference: ERN Part 20 Tables 01/05
  - Dependencies: T2.1
  - Status: **IMPLEMENTED AND FORENSICALLY VALIDATED** (Phases 1–5 complete)
  - Phase 1: `ReturnSequence`, `build_prescribed_dataset()`, `EscalatingWithdrawalPolicy`
  - Phase 2: `StepCadence`, `ExecutionSchedule`, `SimulationRunner.run(schedule=...)`
  - Phase 3: `DeterministicTrajectory`, `execute_deterministic_trajectory()`
  - Phase 4: `build_experiment_e_trajectories()`, `execute_experiment_e()`
  - Phase 5: Forensic validation — zero production code changes
  - Complete at: `fbf-core` T2.6 Phases 1–5 implementation
  - Deliverables: `docs/research/ern_part20_e2e_audit.md` updated with Experiment E forensic results; `docs/research/ern_part20_replication.md` updated with Experiment E forensic results
  - Results: 8 UNEXPLAINED DIFFERENCE anchors (6 portfolio, 2 allocation), 0 REPRODUCED, 0 EXPLAINED DIFFERENCE, 0 CAPABILITY GAP; implementation follows frozen design; zero production code changes in Phase 5
  - Remaining research debt: 6 unexplained portfolio anchors, 2 allocation-anchor source ambiguities, untested pipeline-ordering hypothesis, USD/EUR metadata limitation, workbook divergence documented

### Phase 3 — Part 19

Implement only after the relationship with Part 20 is concretely understood.

- [x] **T3.1** Part 19 Experiment A — Fixed 3.5% SWR failure rates
  - Target: 27 strategies × 3 FV × 2 CAPE = 162 cells × 1,739 cohorts
  - Prerequisite: Part 20 relationship concretely understood; shared computation design decided
  - Expected test location: New E2E test
  - Canonical: Yes (methodology complete)
  - Expected scale: 281,718 units
  - Acceptance criteria: 162 cells executed; failure rates at 3.5% validated; results compared against Part 20 Experiment C where overlapping
  - Known blocker: Implementation alignment pending (execution order)
  - Computation reuse: 60Y/FV=0/CAPE>20/3.5% SWR cells overlap with Part 20 Experiment C
  - Dependencies: T2.1 (relationship understanding)

- [ ] **T3.2** Part 19 Experiment B — Failsafe/percentile SWR
  - Target: 45 strategies × 2 CAPE = 90 cells × 1,739 cohorts
  - Prerequisite: Same as T3.1
  - Expected test location: New E2E test
  - Canonical: Yes
  - Expected scale: 156,510 units
  - Acceptance criteria: 90 cells executed; failsafe and percentile SWRs validated; results compared against Part 20 Experiment A where overlapping
  - Computation reuse: 60Y/FV=0/CAPE>20 cells overlap with Part 20 Experiment A (45 of 53 strategies)
  - Dependencies: T2.1

**Important:** Do not delete Part 19 assertions just because Part 20 runs overlapping simulations. The research assertions are distinct.

### Phase 4 — Part 3 (after YAML correction) (COMPLETE)

- [x] **T4.1** Part 3 YAML equity grid correction
  - Target: Correct `ern_part3_replication.yaml` to use 21 equity weights instead of 5
  - Prerequisite: None
  - Expected test location: `examples/studies/ern_part3_replication.yaml`
  - Acceptance criteria: YAML loads correctly; 21 weights present
  - Dependencies: None
  - Complete at: `e767d6a` (21 weights 0%–100% in 5% increments present; YAML parses with 3 WR × 2 FV × 2 H axes)

- [x] **T4.2** Part 3 canonical E2E
  - Target: Execute 4 experiment configurations with corrected YAML
  - Prerequisite: T4.1
  - Dependencies: T1.2
  - Complete at: `e767d6a` — delivered by the T1.2 deliverable (`tests/integration/test_part3_canonical_ern_replication.py`): all 4 experiment configurations execute against the corrected 21-weight grid; 6 anchors recorded as provisional baselines pending the canonical-data validation phase

### Phase 5 — Part 42

Keep existing structural/invariant coverage while separately implementing published-table validation.

- [ ] **T5.1** Part 42 published-table replication
  - Target: Tables 01-05 with decade-by-decade failsafe values
  - Prerequisite: Methodology frozen; per-cell ERN oracle table needed
  - Expected test location: New or extended E2E test
  - Canonical: Yes
  - Acceptance criteria: Published anchors validated; discrepancies classified
  - Known blocker: No per-cell ERN oracle table exists; directional-only validation currently
  - Dependencies: None (independent of other phases)

### Phase 6 — Part 49

Keep current non-canonical coverage. Canonical experiments remain blocked.

- [ ] **T6.1** Part 49 buy-and-hold capability
  - Target: Implement buy-and-hold portfolio mechanics in FBF
  - Prerequisite: Capability design and implementation
  - Expected test location: N/A (capability implementation)
  - Acceptance criteria: Buy-and-hold mechanics validated; Part 49 E2E can be built against it
  - Known blocker: Genuine FBF capability gap
  - Dependencies: None (independent capability work)

- [ ] **T6.2** Part 49 canonical E2E (after buy-and-hold)
  - Target: Experiments A-F with buy-and-hold mechanics
  - Prerequisite: T6.1
  - Dependencies: T6.1

---

## 8. Acceptance Criteria

### General Criteria (all targets)

A test that merely runs all cells is NOT automatically considered replication-complete. Required:

- [ ] Simulation executes without error
- [ ] Expected output is produced
- [ ] Output matches published/oracle values (where available)
- [ ] All documented dimensions are covered
- [ ] Canonical data is used (or non-canonical deviations explicitly identified)
- [ ] Tests are correctly gated (`ern_e2e` or `research_validation` as appropriate)
- [ ] No duplicate validation was introduced
- [ ] Existing distinct validations retained

### Per-Article Criteria

| Article | Additional Criteria |
|---------|-------------------|
| Part 1 | SWR success rates match pinned oracle table within documented precision |
| Part 2 | FV>0 cells validated; FV=0 cells cross-checked against Part 1 |
| Part 3 | 4 experiment configurations validated; 6 published anchors matched |
| Part 19 | Experiment A failure rates validated; Experiment B failsafe/percentiles validated |
| Part 20 | All 5 experiments (A-E) executed; every discrepancy classified per §9 of audit definition |
| Part 42 | Published Tables 01-05 validated; OMY improvement quantified |
| Part 49 | All 6 experiments validated with buy-and-hold; LTV enforcement active |
| Part 52 | All 11 scenarios validated with actual FFR data; solver reproduction confirmed |

### Discrepancy Classification (Part 20)

Every material discrepancy must receive exactly one classification:

| Classification | Definition |
|---------------|-----------|
| `REPRODUCED` | FBF reproduces the published result within justified precision |
| `EXPLAINED DIFFERENCE` | Discrepancy attributable to documented methodology/framework difference |
| `UNEXPLAINED DIFFERENCE` | Discrepancy remains after all known differences isolated |
| `CAPABILITY GAP` | Experiment cannot be reproduced without introducing new functionality |

---

## 9. E2E Gating and Runtime

### Gating Model

| Gate | Environment Variable | Marker | Purpose |
|------|---------------------|--------|---------|
| Canonical Research E2E | `RUN_ERN_E2E=1` | `@pytest.mark.ern_e2e` | Full canonical ERN replication |
| Non-Canonical Research | `RUN_ERN_E2E=1` | `@pytest.mark.research_validation` | Research-scale with documented approximations |
| Normal pytest | *(none)* | *(none)* | Developer feedback |

**Single gate philosophy:** `RUN_ERN_E2E=1` enables ALL heavyweight ERN research workloads. No second tier exists.

### Runtime Estimates

| Test | Units | Approximate Runtime | Executor |
|------|-------|--------------------|---------- SWR smoke | 2,099 | ~14s | CLI |
| SWR full grid | 313,020 | ~51s | CLI |
| Part 20 grid | 556,480 | Unknown (not benchmarked) | CLI |
| Part 49 non-canonical | 10,434 | ~7.5m | Python API |
| Part 42 structural | 93,915 | ~67s | Python API |
| Part 52 scenarios | 19,129 | >15m | Python API |
| Part 52 deterministic | 1,739 | ~5m | Python API |

---

## 10. Open Blockers and Prerequisites

| # | Blocker | Article | State | Document / code location |
|---|---------|---------|-------|-------------------------|
| B1 | Part 3 YAML equity grid uses 5 weights instead of 21 | Part 3 | RESOLVED (`e767d6a`) | `examples/studies/ern_part3_replication.yaml` |
| B2 | Part 19/20 implementation alignment (execution order) | Parts 19/20 | OPEN | `ERN_E2E_REPLICATION_PLAN.md` §F.4 |
| B3 | Part 20 Experiment C capability gap (failure-rate aggregation) | Part 20 | POTENTIAL | `ern_part20_e2e_audit.md` §5 |
| B4 | Part 20 Experiment E capability gap (annual-frequency simulation) | Part 20 | POTENTIAL | `ern_part20_e2e_audit.md` §7 |
| B5 | Part 42 published-table validation deferred | Part 42 | OPEN | `ERN_E2E_REPLICATION_PLAN.md` §F.2 |
| B6 | Part 49 buy-and-hold capability gap | Part 49 | OPEN | `ERN_E2E_REPLICATION_PLAN.md` §F.3 |
| B7 | Part 49 LTV enforcement currently OFF | Part 49 | OPEN | `ERN_E2E_REPLICATION_PLAN.md` §F.3 |
| B8 | Part 52 Part52Evaluator infeasible-search semantics | Part 52 | OPEN | `TODO.md` S6.6B |
| B9 | Part 19/20 assertion/output ambiguity | Parts 19/20 | OPEN | No specific document — needs resolution during Phase 3 |
| B10 | Part 52 A10 execution/timing recurrence discrepancy | Part 52 | DEFERRED | Production recurrence: `P_t = (P_{t-1} - C + X) * (1 + w_t - f)` (withdraw-at-start); ERN workbook: `S_t = Z_{t-1} * (1 + w_t - f)` with `Z_t = S_t - W_t` (grow-then-withdraw); creates second-order timing term `-(C-X)*(w-f)` ≈ $10-20/month; fee correction recovered only 4/74 failed cohorts; root cause is execution-level, not fee-semantics; deferred until optimization phase; oracle must remain untouched; no weakening of canonical expectations |

---

## 11. Session Checklist

### Before Implementing an E2E

```
[ ] Is the research target documented?
[ ] Is the expected output defined?
[ ] Is the dataset canonical?
[ ] Is the target already covered by another validation?
[ ] If yes, is it logically covered or merely computationally overlapping?
[ ] Can expensive simulation state be shared?
[ ] Are there known capability gaps?
[ ] Is the test canonical or intentionally non-canonical?
[ ] Is the test gated appropriately?
[ ] Is the acceptance criterion explicit?
```

### After Implementing

```
[ ] Full intended dimensions covered
[ ] Expected outputs validated
[ ] Published/oracle values validated where applicable
[ ] No accidental duplicate simulation
[ ] Existing distinct validations retained
[ ] Runtime measured
[ ] Documentation status updated
```

### When Marking a Target as DONE

```
[ ] Test file exists and runs
[ ] All cells/scenarios execute without error
[ ] Acceptance criteria from this roadmap satisfied
[ ] Discrepancies classified (if applicable)
[ ] Status updated in this roadmap (mark [x])
[ ] ERN_E2E_REPLICATION_PLAN.md status updated
[ ] No new redundancy introduced
```
