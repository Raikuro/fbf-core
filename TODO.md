# Technical TODOs

Unresolved technical work with continuing value. Completed or superseded items
must be removed. See `AGENTS.md` for the documentation policy governing this
file.

---

## Next Actionable Task

**Part 2.1 — full FV>0 canonical E2E** is the next pending research task. The
cohort-date configuration prerequisite is implemented; the remaining
prerequisites are the FBF-generated Part 2 regression fixture and resolution of
the documented warm-up timing question. Part 2.2 and Part 2.3 follow Part 2.1.

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

**Classification:** simulation mechanics resolved; FFR data-fidelity policy implemented; asset/CPI differences reconciled as source-vintage; A2/A3/A10 published-anchor acceptance surface implemented. Eligibility and Solver reproduction remain open.

This section supersedes the former S6.P FFR prerequisite, S6.6B FFR integration
limitation, and S6.6B canonical-replication-deferred entries.

### Resolved simulation mechanics

- The workbook FFR conversion is resolved: annual FFR plus spread divided by 12,
  multiplied by `CPI_{t-1}/CPI_t`, with a one-month FFR lag and interest applied
  before the current draw/repayment.
- Terminal-month, repayment, and fixed-parameter feasibility semantics are
  implemented in the production Part 52 path.
- A controlled production-path probe matches the workbook margin-rate formula at
  machine precision. Full-trajectory equivalence is qualified by the documented
  asset/CPI source-vintage difference; exact numerical equivalence with the 2022
  Timing workbook is not an acceptance criterion (see
  `docs/research/ern_part52_replication.md` §3.4.1). This establishes
  implementation consistency, not independent methodological confirmation.

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
- Coverage-layer filtering (eligibility) and solver reproduction remain open.
  The A2/A3/A10 published-anchor acceptance surface is implemented; full-universe
  counts are diagnostics, not canonical acceptance.

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
- Coverage layers must not be conflated:
  - The workbook `Distribution of Final Value` sheet defines 1,739 retirement
    labels (1871-02..2015-12; runtime starts 1871-01..2015-11). The sheet is
    stale relative to the underlying data and does not extend to 2026-06.
  - Complete historical market/CPI coverage is 1,506 runtime cohorts (starts
    1871-01..1996-06; terminal snapshots through 2026-06).
  - Complete workbook-native FFR coverage is 1,453 runtime cohorts (starts
    through 1992-01; latest consumed FFR through 2021-12).
  - The legacy 2021-12 terminal-snapshot subset is 1,452 cohorts. It is one
    month stricter than FFR consumption because 1992-01 consumes FFR through
    2021-12 but has a 2022-01 terminal snapshot.
  - With the accepted runtime FFR extension through 2026-08, historical
    market/CPI coverage remains 1,506. The full 1,739-cohort distribution is a
    projection/extension diagnostic, not historical data coverage.
- In the full 1,739-cohort distribution universe, 286 cohorts consume
  post-2021 FFR and 230 consume forward-filled months from 2026-09 onward.

### Phase 1 — FFR data fidelity (policy implemented; asset/CPI vintage reconciled)

1. The 2021-12 cutoff is not a SWR Toolbox data boundary. It comes from the
   separate FFR workbook `Timing-Leverage-Calc.xlsx` `Return Data!K`, which ends
   at 2021-12. SWR Toolbox historical returns/CPI end at 2026-06, and SWR
   Toolbox contains no FFR series. The 1,739-row distribution sheet is stale at
   2015-12. The 1,452 subset is therefore a legacy conservative filter, not
   full data coverage or an automatically correct canonical universe. Complete
   historical market/CPI coverage is 1,506 cohorts; workbook-native FFR coverage
   is 1,453. The filter is explicit at a Part 52 caller and covered by
   `tests/integration/test_part52_cohort_coverage.py`; the oracle does not
   apply it, and the full 1,739-cohort distribution remains the diagnostic
   default.
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
5. Asset/CPI differences are reconciled as source-vintage differences, not an
   open runtime defect. Runtime asset/CPI comes from SWR Toolbox v2.0; observed
   CPI differences reach `0.653` index points, and the 2008-12 return anomaly is
   explained by faulty Timing `Return Data!E` levels. Exact numerical
   equivalence with the 2022 Timing workbook is not a valid acceptance test
   (see `docs/research/ern_part52_replication.md` §3.4.1). This remains separate
   from FFR temporal coverage.
6. Do not introduce a pre-1928 proxy or fixed-rate fallback without explicit
   authorization; no silent fallback should conceal missing data.
7. Do not substitute the SWR cash total-return series for FFR. Its post-1954
   annualized returns have a `0.464` pp mean absolute error against FRED FFR;
   see `docs/research/ern_part52_replication.md` §3.5.

8. The 2026-11 FFR source audit confirms FRED `FEDFUNDS` as the correct
   post-2021 extension: same H.15 effective-rate measure, monthly, with a
   verified `1954-07..2021-12` overlap against workbook `M`. Source selection
   is no longer open. The remaining decision is eligibility: whether to replace
   the legacy `1,452` terminal filter with the `1,506` historical-market layer.
   The A2/A3/A10 acceptance surface is implemented and asset/CPI differences are
   reconciled as source-vintage; the `1,453`/`1,506` choice still requires an
   explicit rule for post-2021 external FFR observations. Do not change
   production eligibility or refresh the frozen FFR artifact as part of this
   audit. See `docs/research/ern_part52_replication.md` §3.4.
### Phase 2 — validation semantics and oracle assertions (acceptance surface implemented; diagnostics and Solver open)

The canonical oracle test now documents scenario provenance, LTV/final-target
limitations, and the distinction between gross survival and feasibility.

1. **Acceptance surface** — published-anchor fixed-parameter feasibility for
   A2 (`1965-11`), A3 (`1965-11`), and A10 (`1929-09`). Each anchor asserts
   gross survival separately from the three workbook constraints through
   `evaluate_part52_feasibility()`. Passing these assertions does not
   reproduce the workbook Solver or confirm its published optimized WR/Borrow%
   outputs.
2. **Full-universe diagnostics** — gross-survival and feasibility counts are
   diagnostics, not canonical acceptance targets. Report them separately by
   coverage layer (`1,739` distribution, `1,506` historical-market, `1,453`
   workbook-FFR, `1,452` legacy terminal) and by dataset vintage. Current-vintage
   fixed-parameter all-three counts are A2 `1703/1739`, A3 `1735/1739`, and A10
   `1323/1739`; the corresponding historical-market counts are A2 `1470/1506`,
   A3 `1502/1506`, and A10 `1090/1506`. Gross survival is `100%` in every layer
   on this vintage, but these counts are not canonical historical validation.
3. **Solver reproduction** — deferred. The published values are Solver outputs;
   fixed-parameter feasibility at those values is regression protection, not
   Solver replication.
4. **Eligibility** — assessed; decision remains open for full-universe
   diagnostics. `1,452` is a legacy terminal filter and is not canonical.
   `1,453` is the largest workbook-native-FFR universe; `1,506` is the largest
   all-observed-historical universe but requires the FRED FFR extension for 53
   cohorts. The 2026-11 scope audit found no article- or workbook-defined full
   Part 52 universe: the article reports only the `1965-11` and `1929-09` case
   studies, and the Timing workbook has no cohort-distribution sheet. Canonical
   acceptance is therefore anchor-based; the `1,453`/`1,506` choice is a
   diagnostic-universe policy and still requires an explicit rule for post-2021
   external FFR observations. See `docs/research/ern_part52_replication.md`
   §14.3–14.4. Do not choose a universe merely because it has more
   observations.

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
The largest Part 49 workload (the 10,434-unit non-canonical diagnostic)
completes successfully within operational resource limits (~6.2 min,
~11.1 GB RSS).

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

## Final Validation: Regenerate the Relevant ERN Research Datasets and Validation Results Using the Canonical Excel Workbook

**Classification:** future final validation task — deferred until all other
work currently registered in this document and the project roadmaps is
complete; not current implementation work

### Problem

The historical Part 19/20 investigations, including the Part 20 audit §10 A/B/C
closure, used research datasets and derived artifacts whose provenance and
vintage relative to the current canonical Excel workbook have not been
re-established. Those inputs may be obsolete.

The existing numerical evidence must therefore not be treated as reliable,
representative, or definitive validation against the current canonical
workbook. Historical findings remain valid only as findings on the data actually
used, not as final canonical-data conclusions.

### Required resolution

This is the final validation task in the current TODO register and must remain
its last outstanding item. This does not preclude new work being added later.
Start it only after all other work currently registered is complete. Then:

1. Re-extract the required source data directly from the canonical Excel
   workbook.
2. Regenerate the affected datasets and derived research artifacts.
3. Re-run the relevant Part 19/20 comparisons and validation.
4. Reassess the A/B/C conclusions using the regenerated data.
5. Update the forensic reports, audit results, and roadmap statuses accordingly.

Do not regenerate datasets, rerun investigations, or alter historical evidence
as part of the current documentation-only work. Until this task supersedes
them, preserve the historical forensic and audit evidence with its
data-provenance qualification.

### Sequencing

After completion of all other work currently registered in `TODO.md` and the
project roadmaps. This task may revise the current A/B/C statuses only if the
regenerated canonical-data evidence requires it.

---
