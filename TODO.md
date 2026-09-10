# Technical TODOs

Unresolved technical work with continuing value. Completed or superseded items
must be removed. See `AGENTS.md` for the documentation policy governing this
file.

---

## S2 Part 20: 0.111 pp/month Glidepath Endpoint Timing

**Classification:** intentional semantic consequence (not a defect)

The Part 20 glidepaths with 0.111 pp/month slope (30→70% and 20→60%)
reach their target equity at month 361, not month 360.

### Explanation

The slope is interpreted as 0.111 percentage points per month, applied as a
fraction: `slope_fraction = 0.111 / 100 = 0.00111`. The equity weight at
month `t` is:

```
equity(t) = min(start + slope_fraction * t, end_equity)
```

For 30→70% (40pp spread):
- Month 360: `30 + 0.111 * 360 = 69.960%` (not yet 70%)
- Month 361: `30 + 0.111 * 361 = 70.071%` → capped to 70%

For 20→60% (40pp spread):
- Month 360: `20 + 0.111 * 360 = 59.960%` (not yet 60%)
- Month 361: `20 + 0.111 * 361 = 60.071%` → capped to 60%

### Why this is correct

The 0.111 pp/month value is a rounded representation of the Kitces/Pfau
glidepath slope. The ceiling of 40/0.111 = 360.36 is 361 months. This is an
intentional consequence of the slope granularity, not an implementation defect.

The 361-month endpoint should be preserved as-is. Do not round the slope or
adjust the implementation to force the endpoint at month 360.

---

## S1 Follow-Up: ERN Validation Discrepancies

**Classification:** CLOSED — investigation accepted

The S1 glidepath investigation is complete. All validated findings are
recorded in `docs/research/ERN_E2E_REPLICATION_PLAN.md` §F.4.1.

### Final classification

**GLIDEPATH DISCREPANCY NOT ESTABLISHED — PRESENTATION/GRID ARTIFACT**

### Validated findings (summary)

1. **Cohort universe** — CLOSED. FBF and ERN use identical monthly cohorts
   (Feb 1871–Dec 2015, 1,739 cohorts, 383 with CAPE > 20).

2. **CAPE cohort selection** — CLOSED. No divergence found.

3. **Withdrawal frequency** — CLOSED. Monthly and annual validation
   performed. Frequency is not the primary explanation. Configurable
   frequency implementation remains valid.

4. **Fee model** — CLOSED. ERN applies 0.05% p.a. monthly. FBF dataset
   embeds the same fee drag. FBF-derived returns match ERN net returns.

5. **Return construction / forward extrapolation** — CLOSED. Realized and
   forward returns match ERN. No correction required.

6. **Static allocation calculation** — CLOSED. The mathematical failsafe
   agrees with the FBF oracle. Apparent differences with published 3.25%
   are attributable to ERN's search/reporting convention and rounded
   success-rate presentation.

7. **Glidepath / rebalancing mechanics** — CLOSED. FBF applies glidepath
   target at beginning of monthly cycle and rebalances before market
   evolution. Consistent with available ERN methodology description.
   ERN glidepath source not available in this repository; full
   source-level equivalence cannot be claimed but no divergence
   established.

8. **Part 20 published anchors** — IMPORTANT. The previously supplied
   3.47% value has no traceable occurrence in ERN code, tests, or
   documented Part 20 values. The traceable anchor is 3.34% for the
   60→100% glidepath / CAPE > 20 / FV=1.0 configuration. FBF produces
   381/382 = 99.7% success at 3.34%, which rounds to 100% under ERN's
   success-rate convention.

### Do not reopen

Do not reopen Part 20 methodology investigations unless new evidence
contradicts these validated conclusions. Do not create new tasks to
investigate fees, withdrawal frequency, cohort selection, return
construction, forward extrapolation, static allocation mathematics, or
rebalancing mechanics merely because FBF's precise binary-searched failsafe
differs from a published ERN percentage. Published ERN percentages must be
interpreted according to the documented search/grid and success-rate
conventions.

---

## S1 Follow-Up: Part 19 Configuration Representation

**Classification:** architectural/documentation follow-up — RESOLVED in L.1

The generic builder (`_build_unified_parameter_configs`) creates Cartesian
products of independent parameter axes. Part 19 requires constrained
`(start, end, slope)` combinations where slopes are associated with specific
start/end pairs.

**Resolution:** L.1 introduced the `allocation_policy.configurations` list in
the YAML schema, enabling explicit parameter tuples that are crossed only
with the remaining study axes (withdrawal_rate, horizon_years). This
eliminates the need for Cartesian products of glidepath parameters.

---

## S1 Follow-Up: Performance Profiling

**Classification:** future optimization candidate

The active glidepath policy performs an O(M) historical scan at each of the
721 monthly periods per cohort. S1 measurement results:

* Total policy calls per config: 11,284,371
* Total historical comparisons (active): 4,073,657,931
* Active execution time: ~126s per config (8 workers)
* Passive execution time: ~100s per config (8 workers)
* Absolute overhead: ~26s (26% of passive)
* Extrapolated full 24-config grid: ~45 min total, ~5 min overhead

### Current decision

**No optimization is warranted now.** The overhead is measurable but does not
fundamentally change the project's performance characteristics.

### Future profiling requirements

Before any optimization, establish a reproducible baseline and profile:

* total simulation time;
* policy evaluation time (including historical scans);
* withdrawal-decision time;
* allocation/rebalancing time;
* market-evolution time;
* statistics/aggregation time;
* serialization/IPC overhead;
* worker/process overhead.

### Potential optimization hypothesis (do not implement without profiling)

If profiling later demonstrates that repeated historical scans are a material
bottleneck, a prefix-count representation (precomputed running count of
underwater periods) could be evaluated. This would trade O(M) per-call work
for O(1) lookup at the cost of O(M) preprocessing and memory. Do not
implement without profiling evidence.

---

## S6 Part 52 Numerical Discrepancy Investigation

**Classification:** partially resolved — leverage discrepancy resolved, baseline discrepancy deferred

### Leverage-induced discrepancy — RESOLVED (S6.5B, commit e9f0e5f)

The missing `LoanRepaymentStep` in `_create_default_simulation_executor()`
caused loans to be drawn but never repaid, accumulating interest
indefinitely. This was the root cause of all 19 leverage-induced failures
observed at WR=3.5%.

- Without fix (WR=3.50%, B%=41.08%): 1720/1739 (19 leverage-induced failures)
- With fix (WR=3.50%, B%=41.08%): **1739/1739** (all succeed)
- With fix (WR=3.91%, B%=41.08%): 1733/1739 (6 baseline failures remain)

Pipeline parity regression tests (`test_pipeline_parity.py`) now protect
against future divergence between the canonical and parallel pipelines.

### Remaining baseline discrepancy — DEFERRED to E2E validation pass

Six cohorts fail at WR=3.91% even with B%=0 (no leverage):

| Cohort | Failure month |
|--------|--------------|
| 1929-09-01 | 339 |
| 1965-11-01 | 344 |
| 1965-12-01 | 354 |
| 1966-01-01 | 354 |
| 1966-02-01 | 350 |
| 1968-12-01 | 328 |

- All six failures are **portfolio depletion**, not LTV enforcement
- Loan balance is zero at failure (no outstanding debt)
- The same six cohorts fail at B%=0 — this is NOT leverage-related
- LoanRepaymentStep parity is no longer implicated
- ERN anchor: all 1,739 cohorts succeed at WR=3.91%, B%=41.08%
- FBF result: 1733/1739 (99.65%) at WR=3.91%, any B%

**Deferred to:** comprehensive E2E/replication validation pass. Potential
causes: dataset provenance, success criterion timing, forward extrapolation
methodology, or withdrawal timing conventions. See S6 architecture plan
for investigation areas.

---

## S6 Part 52 Parameter-Grid Architecture Gap

**Classification:** architectural gap — blocks S6.4 and S6.6

`borrow_pct` and `drawdown_threshold` cannot participate in the generic
Cartesian product grid. The `ParameterAxis` and `ParameterSweepEngine` are
generic, but `_build_unified_parameter_configs` is not — it has hardcoded
knowledge of which fields map to which axes.

### Current state

```python
StudyConfiguration
    → scalar borrow_pct        # works
    → scalar drawdown_threshold # works
    → borrow_pct axis           # NOT possible
    → drawdown_threshold axis   # NOT possible
```

### Approved correction (Option 1 — minimal)

- Add `borrow_pct_values: tuple[Decimal, ...] | None` to StudyConfiguration
- Add `drawdown_threshold_values: tuple[Decimal, ...] | None` to StudyConfiguration
- Construct corresponding ParameterAxis instances in `_build_unified_parameter_configs`
- Include them in the existing Cartesian product mechanism

### Future improvement (Option 2 — generic, deferred)

A genuinely generic axes mapping may eventually be preferable, but is not
required to unblock Part 52.

---

## S6 Historical Rate Data Coverage (1871–1954)

**Classification:** data gap — blocks S6.6 canonical replication

The FFR dataset covers only 1928-04 to 2026-08. ERN cohorts begin 1871.
Any cohort starting before 1928-04 lacks interest-rate data.

### Impact confirmed (S6.6B)

`build_interest_rate_schedule` fails with ValueError for cohorts starting
before 1928-04. FFR scenarios (A2-A8, A10-A11) used fixed-rate approximation
as documented fallback. These are NOT canonical ERN executions.

### Required coverage

| Period | Source | Status |
|--------|--------|--------|
| 1954+ | FRED FEDFUNDS | IMPLEMENTED (S6.2) |
| 1928–1954 | FRED category 33951 | METHODOLOGY DECIDED (S6.P), NOT IMPLEMENTED |
| pre-1928 | Call money rate proxy | METHODOLOGY DECIDED (S6.P), NOT IMPLEMENTED |

### Requirements for S6.4

1. Retrieve and transform FRED category 33951 data (1928–1954)
2. Source and validate call money rate proxy (pre-1928)
3. Extend `ffr_monthly.json` schema or implement multi-source loading
4. Integrate into `build_interest_rate_schedule` with strict coverage validation
5. Audit provenance and continuity of S6.P methodology before implementation

**No silent fallback should conceal missing data.**

---

## S6 Dataset Loader Type Discrimination

**Classification:** architectural debt — not blocking S6.3

The JSON dataset loader identifies auxiliary datasets by checking
`"frequency" in raw`. This is fragile: any JSON file with a `"frequency"`
key could be misidentified.

### Current behavior

```python
if "frequency" in raw:
    # Assume Dataset
else:
    # Ignore file
```

### Recommended future correction

Use positive identification rather than key presence:
- Explicit dataset type field
- Schema discriminator
- Registry
- Validation of both `frequency` and `snapshots`

### Current workaround

The FFR file was renamed `"frequency"` → `"data_frequency"` to avoid
collision. This is acceptable as a tactical workaround but the broader
issue must not disappear.

---

## Deferred Scalability Architecture

**Classification:** deferred — not required for current canonical workloads

These items were designed during S5 (see `docs/roadmap/S5_4_R2_ARCHITECTURE.md`
and `docs/roadmap/S5_7_PERFORMANCE_REPORT.md`) but are intentionally deferred.
The canonical Part 49 workload (10,434 units) completes successfully within
operational resource limits (~6.2 min, ~11.1 GB RSS).

### Batched execution (`BatchedExecutor`)

- **What:** Process simulation units in bounded-memory batches with
  emit-and-release semantics, replacing eager full-result materialization.
- **Why deferred:** Current canonical workloads (~10k units) fit in memory.
  The OOM boundary (~14k units on 16 GB) has not been reached by any
  required study.
- **Revisit when:** A required research workload exceeds ~14,000 units, or
  when Part 52 grid expansion approaches the memory envelope.
- **Architecture reference:** `S5_4_R2_ARCHITECTURE.md` §C (Batched Execution).
- **Expectation:** Required when larger grids are needed. Not optional.

### Normalized research persistence

- **What:** Replace serialized `SimulationResult` objects with a purpose-built
  research-storage model (metadata in SQLite, trajectories in binary files).
- **Why deferred:** Current pickle-based persistence is adequate for canonical
  workloads. The 92% storage reduction is significant but not operationally
  necessary yet.
- **Revisit when:** Research grids exceed the current storage envelope or
  when result retrieval patterns demand SQL queries on summaries.
- **Architecture reference:** `S5_4_R2_ARCHITECTURE.md` §D (Research Data Model).
- **Expectation:** Required when larger grids are needed. Not optional.

### Hybrid SQLite + binary storage

- **What:** SQLite for metadata/summaries + binary `struct.pack` files for
  trajectories. No new dependencies (stdlib `sqlite3` + `struct`).
- **Why deferred:** Tied to the normalized persistence redesign. Not needed
  until the persistence layer is redesigned.
- **Revisit when:** Normalized persistence is implemented.
- **Architecture reference:** `S5_4_R2_ARCHITECTURE.md` §E (Storage Format).
- **Expectation:** Part of the persistence redesign. Not standalone.

### Result-model normalization

- **What:** Align `MonthlyResult` fields with the normalized research-storage
  model. Normalize `MarketSnapshot`, `Allocation`, `AllocationTarget`, and
  `WithdrawalDecision` to avoid per-month redundant serialization.
- **Why deferred:** Tied to the persistence redesign. The new
  `ResearchResultSerializer` will simply not extract dead fields.
- **Revisit when:** Normalized persistence is implemented.
- **Architecture reference:** `S5_4_R2_ARCHITECTURE.md` §D.3 (Normalization Rules).
- **Expectation:** Part of the persistence redesign. Not standalone.

### Eager `SimulationResult` materialization

- **What:** Current architecture retains all `SimulationResult` objects in
  memory simultaneously. Peak RSS scales linearly with simulation units
  (~1.1 MB/unit).
- **Why deferred:** Operationally viable for canonical workloads. The
  ~14,000-unit envelope has not been exceeded by any required study.
- **Revisit when:** A required workload approaches or exceeds the memory
  envelope, or when `BatchedExecutor` is implemented.
- **Architecture reference:** `S5_4_R2_ARCHITECTURE.md` §C.1 (Current Architecture).
- **Expectation:** Addressed by `BatchedExecutor` when needed.

### Dead `MonthlyResult` fields

- **What:** Six fields in `MonthlyResult` are architecturally dead:
  `allocation_drift`, `rebalance_result`, `drawdown`, `cumulative_return`,
  `cumulative_inflation`, `events`. No producer populates them meaningfully.
- **Why deferred:** Removing them is a separate model-cleanup decision and
  should not be bundled into research replication work.
- **Revisit when:** A broader `MonthlyResult` refactoring or cleanup pass
  is undertaken.
- **Architecture reference:** `S5_CLOSURE_REPORT.md` §6 (Deferred Architectural Work).
- **Expectation:** Optional cleanup. Not blocking any replication phase.

---

## S6 Prerequisite: FFR Dataset Investigation

**Classification:** S6 blocking prerequisite — **RESOLVED in S6.P**

Part 52 (Timing Leverage) requires Federal Funds Rate (FFR) data for
floating-rate interest scenarios (FFR + spread: 0.50%, 1.25%, 2.75%).

### Resolved questions

1. **Exact source:** FRED FEDFUNDS (1954+), FRED category 33951 (1928-1954),
   call money rate proxy (pre-1928). See S6 architecture plan §10.1.
2. **Historical coverage:** FEDFUNDS from 1954-07; daily FFR from 1928-04;
   call money rate from 1857 (proxy for 1871-1928).
3. **Frequency:** Monthly (FEDFUNDS is monthly average of daily figures).
4. **Definition:** Effective federal funds rate (market rate, not target).
5. **Monthly transformation:** FEDFUNDS already monthly; 1928-1954 daily data
   averaged to monthly; pre-1928 proxy already monthly.
6. **Date alignment:** FFR for month M is the rate observed in month M.
   No lag or lead.
7. **Treatment of rate changes:** Monthly average captures mid-month changes.
8. **Correspondence with ERN calculation:** ERN uses FFR + spread for margin
   loan rate. FFR component is the base rate.

### Impact

- FFR data is now sourced and documented. See S6 architecture plan §10.1.
- Fixed-rate Part 52 can be implemented first (S6.1), with FFR integration
  in S6.2.
- Call money rate is the recommended proxy for pre-1928 periods.

### Resolution

Investigated during S6.P. All questions resolved. See S6 architecture plan
§10.1 for full provenance and transformation rules.

---

## S6 Prerequisite: Part 52 Semantic and Architectural Readiness

**Classification:** S6 planning prerequisite — **RESOLVED in S6.P**

### Engine modification assessment

No engine modification is currently justified. The existing engine and
pipeline contracts can express Part 52 semantics cleanly. See S6
architecture plan §4.4 for full assessment.

### New capabilities required

1. **Drawdown evaluation:** Compute drawdown magnitude relative to ATH.
   Uses existing `MarketSnapshot.running_ath` and `index_levels`.
   No new state variable needed. See §10.2.
2. **Conditional loan activation:** Part 52 draws only below threshold.
   Policy-level conditional logic in `Part52WithdrawalPolicy`.
3. **Loan repayment at fresh ATH:** Dedicated `LoanRepaymentStep` at
   sequence_order 32. See §10.3.
4. **Double withdrawal for repayment:** `WithdrawalDecision.portfolio_withdrawal`
   doubled during repayment. See §10.3.
5. **FFR-based floating interest:** FFR dataset sourced. `interest_rate_schedule`
   on `SimulationContext`. See §10.1.

### Reusable from Part 49

- `LoanDrawStep`, `InterestAccrualStep`, `LTVEvaluationStep`
- `Part49WithdrawalPolicy` as base for leverage-aware withdrawal
- `SimulationState` debt fields (`loan_balance`, `cash_balance`,
  `interest_rate`, `ltv_limit`, `ltv_enforcement`)

### Resolution

All semantic questions resolved during S6.P. See S6 architecture plan
§10.1–§10.8 for full findings. Architecture is frozen. Implementation
may proceed with explicit authorization.

---

## S6.6B FFR Integration Limitation — Canonical Replication Blocked

**Classification:** architectural limitation — blocks full canonical ERN replication

### Problem

The framework generates ALL 1,739 cohorts (1871+) and requires FFR data for
the full 30-year simulation horizon. FFR data starts 1928-04. For cohorts
starting before 1928-04, `build_interest_rate_schedule` fails with ValueError.

### Impact on S6.6B

FFR scenarios (A2-A8, A10-A11) used fixed-rate approximation instead of
actual FFR data. These are NOT canonical ERN executions.

| Scenario | Actual Result | Expected | Methodology |
|----------|--------------|----------|-------------|
| A2 | 1739/1739 | 1739/1739 | Fixed-rate approx (D) |
| A3 | 1733/1739 | 1739/1739 | Fixed-rate approx (C) |
| A4 | 1731/1739 | 1739/1739 | Fixed-rate approx (C) |
| A5 | 1736/1739 | 1739/1739 | Fixed-rate approx (C) |
| A6 | 1739/1739 | 1739/1739 | Fixed-rate approx (D) |
| A7 | 1729/1739 | 1739/1739 | Fixed-rate approx (C) |
| A8 | 1738/1739 | 1739/1739 | Fixed-rate approx (C) |
| A10 | 1613/1739 | 1739/1739 | Fixed-rate approx (C) |
| A11 | 1413/1739 | 1739/1739 | Fixed-rate approx (C) |

### Required resolution

1. **Historical FFR partial-coverage architecture:** Determine how a generic
   study should handle datasets whose temporal coverage does not span all
   generated cohorts. Consider cohort filtering, dataset coverage validation,
   or another generic framework-level solution.

2. **Pre-1928 historical FFR methodology:** Investigate whether an
   authoritative historical rate source/proxy exists that is methodologically
   defensible for the ERN replication. Do NOT introduce a proxy now.

### Deferred to

Comprehensive E2E/replication validation pass after FFR coverage is resolved.

---

## S6.6B Part52Evaluator Infeasible-Search Semantics

**Classification:** API ambiguity — does not block S6.6B

### Problem

When the Part52Evaluator grid sweep finds no feasible Borrow%, it returns
Borrow%=0.00% in the provenance. This silently conflates two cases:

a) A feasible optimum at Borrow%=0% (valid result)
b) No feasible Borrow% found by the configured search (fallback)

### Current behavior

```python
# In Part52Evaluator.evaluate():
if outcome.success:
    return outcome  # success=True, borrow_pct is feasible
else:
    # Returns best outcome, which may have borrow_pct=0.00%
    return best_outcome  # success=False, but borrow_pct=0.00%
```

### Required correction

Distinguish explicitly between:
- Feasible optimum at Borrow%=0%
- No feasible Borrow% found (fallback)

Do NOT redesign the optimizer now.

---

## S6.6B Canonical Part 52 Historical Replication — Deferred

**Classification:** deferred — blocked by FFR coverage limitation

### Current state

- 11 published ERN scenarios audited
- A1 and A9: exact matches (non-FFR baselines)
- A2: explainable under documented methodology difference (FFR→fixed approx)
- A3: preserves known six-cohort baseline discrepancy
- A4-A8, A10-A11: deferred methodology/data-coverage discrepancies

### Required before revisiting

1. FFR coverage limitation resolved (see above)
2. Pre-1928 FFR methodology investigated
3. Part52Evaluator infeasible-search semantics corrected

### Do NOT

- Modify the simulation engine
- Modify canonical Part 52 semantics
- Add a pre-1928 proxy
- Change cohort generation
- Change the optimizer
- Change execution architecture
- Add batching or worker architecture
- Rerun expensive optimizer sweeps
