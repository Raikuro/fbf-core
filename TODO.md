# Technical TODOs

Unresolved technical work with continuing value. Completed or superseded items
must be removed. See `AGENTS.md` for the documentation policy governing this
file.

---

## External Integration: UI Timeline Persistence

**Classification:** external integration gap — deferred; not a Core execution
defect

### Problem

The UI execution flow in `fbf-ui` calls `execute_study_plan()` without
`materialize_timeline=True` and persists through `save_execution_result`.
Persisted UI runs therefore contain empty monthly timelines, so trajectory
charts have no data even though the run completed successfully.

### Core status

Core supports materialized timelines through `iter_execute_study_plan()` and
incremental persistence through the streaming writer. No Core execution
semantics need to change for this integration.

### Required resolution

Resolve in `fbf-ui`: request materialized trajectories and persist completed
slices incrementally, then add an integration test proving a UI-created study
exposes non-empty trajectory data. Do not change Core execution behavior as
part of that work.

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

## S6 Part 52 — Validation State and Phase Boundary

**Classification:** simulation mechanics resolved; FFR data-fidelity policy implemented; asset/CPI equivalence and validation semantics open

This section supersedes the former S6.P FFR prerequisite, S6.6B FFR integration
limitation, and S6.6B canonical-replication-deferred entries.

### Resolved simulation mechanics

- The workbook FFR conversion is resolved: annual FFR plus spread divided by 12,
  multiplied by `CPI_{t-1}/CPI_t`, with a one-month FFR lag and interest applied
  before the current draw/repayment.
- Terminal-month, repayment, and fixed-parameter feasibility semantics are
  implemented in the production Part 52 path.
- A controlled production-path probe matches the workbook margin-rate formula at
  machine precision. Full-trajectory equivalence remains subject to the separate
  asset/CPI numerical-equivalence item; this establishes implementation
  consistency, not independent methodological confirmation.

### Phase 2 anchor feasibility (bounded implementation)

- The A10 `1929-09` anchor in `tests/oracle/ern/test_part52_replication.py` now
  calls `evaluate_part52_feasibility()` for the same planned unit and built
  study used by the oracle execution. It asserts gross survival separately from
  each workbook feasibility condition and asserts all three conditions hold
  together.
- Full-universe feasibility accounting is now exercised by a gated A10
  diagnostic (`tests/integration/test_part52_full_universe_feasibility.py`)
  that verifies helper/oracle gross survival for every unit and reports the
  coverage-layer feasibility table. Its counts are current-vintage diagnostics,
  not canonical acceptance constants.
- Coverage-layer semantics are machine-checked in
  `tests/integration/test_part52_coverage_layer_semantics.py`: the legacy
  (1,452) and workbook-FFR (1,453) layers are fully historical; the
  historical-market layer (1,506) adds 53 cohorts using the FRED FFR extension;
  the distribution layer (1,739) adds 233 projection-dependent cohorts. The
  eligibility decision among these layers remains open.
- Acceptance policy, coverage-layer filtering, and solver reproduction remain
  open.

### FFR data equivalence (bounded)

- Workbook `Return Data!K` is the spliced FFR series `IF(ISNUMBER(M), M, N)`;
  `M` covers 1954-07..2021-12 and `N` covers 1871-01 onward.
- Runtime `data/ern/ffr.csv` contains 1,868 monthly observations from
  1871-01..2026-08 and matches `K` exactly over all 1,812 common months through
  2021-12. Values from 2022-01..2026-08 are actual FRED `FEDFUNDS`
  observations, not synthetic or forward-filled. Runtime forward-fill begins
  after 2026-08.
- `data/ern/ffr_monthly.json` is a reconstructed series covering
  1928-04..2026-08. Exact numeric comparison with `K` yields 522 differences:
  306 substantive differences before 1954-07 and 216 post-1954 floating-point
  artifacts (maximum absolute difference approximately `2.78e-17`). A tolerance
  of `1e-15` yields 306 differences (for example, 1929-09: 3.16% in `K`, 6.07%
  in the JSON).
- `data/ern/ffr.provenance.json` records the workbook-derived historical
  segment and the separate FRED extension. `data/ern/ffr.csv` has 1,868
  observations from 1871-01..2026-08 and is regenerated by
  `tools/ern/extract_ffr_from_workbook.py`. The FRED snapshot is consistent
  with the embedded data and workbook `M`, but its acquisition path is not
  fully reproducible from repository evidence; see `DATASETS.md`.
- The SWR cash series (`SWR_Toolbox_v2.0.xlsx` `Asset Returns!I`) is a
  3-month T-bill total-return index, not FFR. It must not be used as a
  pre-1928 proxy or post-2021 extension.
- CPI and real asset-return series end at 2026-06. The canonical dataset's
  forward projection begins at 2026-07 and extends to 2075-11.
- In the full 1,739-cohort universe, 286 cohorts consume post-2021 FFR and
  230 consume forward-filled months from 2026-09 onward. The canonical
  workbook-backed universe is 1,452 cohorts; see the Phase 1 section below.

### Phase 1 — FFR data fidelity (policy implemented; asset/CPI equivalence open)

1. Canonical cohort eligibility is implemented as full workbook coverage:
   terminal asset/CPI snapshot on or before 2021-12, yielding 1,452 cohorts.
   The FFR-only boundary is 1,453 because 1992-01 consumes FFR through 2021-12
   but has a 2022-01 terminal snapshot. The filter is explicit at the Part 52
   caller; the extended diagnostic default remains 1,739 cohorts.
2. Post-2021 FFR handling is defined and implemented: actual FRED through
   2026-08, then hold the last observed rate. In the full universe, 286 cohorts
   consume post-2021 FFR and 230 consume forward-filled months; the
   no-forward-fill variant contains 1,509 cohorts.
3. The 1871–1954 `N` fallback is accepted as the workbook's documented splice,
   but its upstream source and vintage are not documented. The provenance file
   records this limitation.
4. The canonical `ffr.csv` artifact is frozen by SHA-256. FRED acquisition
   metadata remains a documented provenance limitation; do not invent a
   download recipe or silently replace the artifact.
5. Remaining Phase 1 data-fidelity item: asset/CPI numerical equivalence with
   the Timing workbook. Runtime asset/CPI comes from SWR Toolbox v2.0; observed
   CPI differences reach `0.653` index points and a 2008-12 return anomaly
   remains. This is separate from FFR temporal coverage.
6. Do not introduce a pre-1928 proxy or fixed-rate fallback without explicit
   authorization; no silent fallback should conceal missing data.
7. Do not substitute the SWR cash total-return series for FFR. Its post-1954
   annualized returns have a `0.464` pp mean absolute error against FRED FFR;
   see `docs/research/ern_part52_replication.md` §3.5.

### Phase 2 — validation semantics and oracle assertions (open)

1. Distinguish `statistics.success` (gross survival) from the three-constraint
   feasibility result in oracle assertions.
2. Treat full-universe counts as diagnostic, not canonical acceptance targets.
   At fixed A10 parameters, the current diagnostic is `1739/1739` gross survival
   and `1323/1739` all-three.
3. Correct scenario provenance and classification descriptions: A4–A8 and A11
   use BF-discovered Borrow%; A1 and A9 are non-FFR baselines.
4. Record that LTV is observed but not enforced in the current study
   configuration and that the final-value target is not configured in the oracle
   test.
5. Reassess the A2/A3/A10 full-universe assertions only after asset/CPI
   equivalence and the feasibility metric wiring are resolved.

### Deferred

- Workbook Solver replication.
- Euro-area reference-rate analogue. This is research-only and requires a
  separate, explicitly authorized design; see `DATASETS.md` and
  `docs/research/ern_part52_replication.md` §3.6.

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

## Numba Annual Withdrawal Frequency Coverage

**Classification:** unsupported Numba scope — rejected explicitly

The generic fixed-real, constant-nominal, buy-and-hold, fixed-real glidepath,
Part 49, and Part 52 Numba kernels implement monthly withdrawals only. The
policy layer, escalating Numba paths (including combined glidepath + escalating),
and the deterministic kernel support annual frequency, but the monthly-only
kernels must reject annual contexts rather than execute a full annual amount
every month.

### Required resolution

If a consumer requires annual withdrawals in a monthly-only family, implement
the annual withdrawal boundary (`period_index % 12 == 0`) in the corresponding
kernel and add an independent Decimal recurrence test for annual timing.
Otherwise retain the explicit rejection. Do not silently map annual to monthly.

---
