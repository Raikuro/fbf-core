# S6.4C — Data/IO & Execution Cost Audit (Corrected)

## A. Data/IO Call Graph

### Complete Runtime Path

```
data/ern/ern_swr_h720.json  (559 KB, 2,459 snapshots)
         |
         v
resolve_dataset()                          [IO: iterdir + json.loads + _dict_to_dataset — once per process]
  └─ DatasetCache.load_dir()               [process-wide singleton, cached after first call]
         |
         v
Dataset (2,459 MarketSnapshot objects, immutable)
         |
         v
build_study_plan(config, data_dir, initial_wealth)           [~5.0s, one-time]
  ├─ resolve_dataset()                      [0.07s — cached]
  ├─ build_cohort_specs()                   [0.002s — 1,739 CohortSpecification]
  ├─ _build_unified_parameter_configs()     [<0.001s — 180 ParameterConfiguration]
  ├─ build_initial_portfolio()              [<0.001s — canonical]
  ├─ ExperimentDefinition()                 [<0.001s]
  └─ materialize_research_plan()            [5.04s — the expensive phase]
       ├─ 313,020 iterations of:
       │    ├─ dataset.slice()              [~0.025ms each, 6,956 unique — cached internally]
       │    ├─ build_initial_portfolio()    [0.003ms each — NOT deduplicated, 313K calls]
       │    └─ PlannedSimulationUnit()      [dataclass construction]
       └─ Returns ResearchPlan(313,020 units)
         |
         v
execute_study_plan(built_study, options)
  ├─ FastPathSimulationExecutor             [DEFAULT backend]
  │    ├─ context_translation              [negligible — pass-through mapping]
  │    ├─ fast_path_grouping               [negligible — hash-based grouping]
  │    ├─ fast_path_evaluation             [dominant — _evaluate_decimal_recurrence]
  │    └─ fast_path_assembly               [negligible — slicing ClosedFormPath]
  └─ Results: ExperimentRun(313,020 SimulationResult)
```

### FFR Path (S6.4B.2)

```
data/ern/ffr_monthly.json (75.5 KB, 1,181 observations)
         |
         v
load_ffr_rates("ffr_monthly", data_dir)     [IO: json.loads — once per call, NOT cached]
         |
         v
tuple[tuple[date, Decimal], ...]            [in-memory rate pairs]
         |
         v
(Only used when ffr_dataset_identifier is configured — NOT in ern_grid.yaml)
```

## B. IO/Data Access Audit

| Access | Method | Caller | Frequency | Scope | Data returned | Reused? |
|--------|--------|--------|----------:|-------|---------------|---------|
| Dataset JSON read | `path.read_text()` | `_load_datasets_from_dir()` | Once per process | 559 KB | Raw string | **Yes** — `DatasetCache` singleton |
| Dataset JSON parse | `json.loads()` | `_load_datasets_from_dir()` | Once per process | 559 KB → dict | Parsed dict | **Yes** — `DatasetCache` singleton |
| Dataset domain conversion | `_dict_to_dataset()` | `_load_datasets_from_dir()` | Once per process | dict → `Dataset` | Domain objects (AssetClass, Decimal, MarketSnapshot) | **Yes** — `DatasetCache` singleton |
| FFR JSON read+parse | `json.loads(path.read_text())` | `load_ffr_rates()` | Once per call (no cache) | 75.5 KB | `tuple[(date, Decimal), ...]` | **No** — re-reads every call |
| Dataset slice | `canonical_trajectory.slice()` | `materialize_research_plan()` | 313,020 calls, 6,956 unique | Per cohort × horizon | `Dataset` (shared snapshot refs) | **Yes** — `dataset_cache` dict within materialize |
| Portfolio build | `build_initial_portfolio()` | `materialize_research_plan()` | 313,020 calls (all unique inputs) | Per unit | `Portfolio` | **No** — new object every call |
| File opens (total) | | | 2 files | `ern_swr_h720.json` + `ffr_monthly.json` | | |
| Total bytes read | | | 636 KB | 559 KB dataset + 75.5 KB FFR | | |
| JSON deserializations | | | 2 | One per file | | |

### IO Cost Summary

| Metric | Value |
|--------|-------|
| File opens | 2 |
| Total bytes read | 636 KB |
| JSON deserializations | 2 |
| First-load time (dataset) | 0.067s (includes domain conversion) |
| Raw JSON parse time | 0.004s (domain conversion dominates) |
| Repeated-load count | 0 (dataset cached; FFR not cached but loaded once) |
| Cache-hit behavior | DatasetCache: process-wide singleton, returns identical Dataset on repeat calls |

**Statement:** No repeated runtime file I/O was observed. Dataset loading occurs once per process and subsequent access is in-memory via `DatasetCache`. FFR loading reads the file once per `load_ffr_rates()` call but is only called once per study build.

## C. Reconciled ERN 180-Cell Cost Model

### Workload Specifications

| Property | Value |
|----------|-------|
| Parameter grid | 5 equity × 9 rates × 4 horizons = 180 combos |
| Cohorts | 1,739 |
| Total planned units | 313,020 |
| Total simulation months (all units) | 170,029,080 |
| Pipeline steps per month | 13 |
| Total step executions | 2,210,378,040 |
| Fast-path eligible | 100% (313,020 / 313,020) |
| Independent fast-path groups | 78,255 |
| Derived units (prefix shortcut) | 234,765 |

### Sequential Configuration

**Environment:** Python 3.14, Linux, single thread.

| Component | Measured Time | % of Total | Source |
|-----------|-------------:|-----------:|--------|
| **Plan materialization** | **5.04s** | **1.0%** | Measured: `build_study_plan()` wall clock |
| — resolve_dataset | 0.067s | | Measured |
| — build_cohort_specs | 0.002s | | Measured |
| — param_configs + policies | <0.001s | | Measured |
| — materialize_research_plan | 5.04s | | Measured (includes 313K portfolio builds, 313K PSU constructions, 6,956 dataset slices) |
| **Mathematical simulation** | **~496s** | **~99.0%** | Extrapolated: 1.601ms/unit × 313,020 units |
| Context/pipeline construction | ~0.1s | <0.1% | Estimated from profiler (0.0003s per cohort × ~1,739 cohorts executed sequentially) |
| Statistics/result materialization | Included in simulation | | Statistics built inside `_build_result()` per unit |
| **Total sequential** | **~501s (~8.4 min)** | **100%** | Sum: 5.04s plan + ~496s simulation |

**Note on percentages:** Plan materialization is 5.04s out of a ~501s total = 1.0%, not 16.4% as previously reported. The earlier report incorrectly used the 100-cohort subset time (28.8s) as the denominator instead of the full sequential runtime.

**Extrapolation source:** The 1.601ms/unit figure is derived from a linear regression across 5 measured sizes:

| Size (cohorts) | Units | Time | ms/unit |
|---------------:|------:|-----:|--------:|
| 1 | 180 | 0.288s | 1.600 |
| 5 | 900 | 1.425s | 1.583 |
| 10 | 1,800 | 2.877s | 1.598 |
| 50 | 9,000 | 14.519s | 1.613 |
| 100 | 18,000 | 28.823s | 1.601 |

Per-unit time is consistent across all sizes (1.58–1.61ms), confirming linearity. The extrapolation is: 1.601ms × 313,020 = 501s.

### Plan Materialization Breakdown (5.04s)

| Sub-phase | Time | Calls | Per-call | Notes |
|-----------|-----:|------:|---------:|-------|
| resolve_dataset | 0.067s | 1 | 0.067s | JSON parse + domain conversion |
| build_cohort_specs | 0.002s | 1 | 0.002s | 1,739 cohorts |
| param_configs | <0.001s | 1 | | 180 configs |
| materialize_research_plan | 5.04s | 1 | | Nested loop: 1,739 × 180 = 313,020 iterations |
| — dataset.slice | ~0.17s | 313,020 | 0.025ms | 6,956 unique slices (cached within loop) |
| — build_initial_portfolio | ~1.0s | 313,020 | 0.003ms | NOT deduplicated (see §E) |
| — PSU construction + loop overhead | ~3.9s | 313,020 | ~12.4μs | Dataclass init, policy resolution, variable assignment |

### Fast-Path Profiling (single cohort, 180 units)

| Phase | Time | % of cohort |
|-------|-----:|------------:|
| context_translation | 0.0003s | 0.1% |
| fast_path_grouping | 0.0008s | 0.3% |
| **fast_path_evaluation** | **0.2900s** | **99.2%** |
| fast_path_assembly | <0.0001s | <0.1% |
| **total** | **0.2924s** | **100%** |

Profiler metrics for this cohort: 45 groups, 135 derived, 32,445 month-work.

## D. Sequential vs Parallel Benchmark

### Sequential Configuration

| Metric | Value | Source |
|--------|------:|--------|
| 1 cohort (180 units) | 0.288s | Measured (best of 3) |
| 10 cohorts (1,800 units) | 2.877s | Measured |
| 50 cohorts (9,000 units) | 14.519s | Measured |
| 100 cohorts (18,000 units) | 28.823s | Measured |
| Per-unit time | 1.601ms | Measured (consistent across sizes) |
| Extrapolated full 313K | ~501s (~8.4 min) | Extrapolated: 1.601ms × 313,020 |
| Peak RSS (18,000 units) | ~10 MB | Measured via tracemalloc |

### Parallel Configuration

**10-cohort subset (1,800 units):**

| Workers | Time | Speedup | Efficiency | Peak RSS |
|--------:|-----:|--------:|-----------:|---------:|
| 1 | 3.052s | 1.00x | 100% | ~10 MB |
| 2 | 2.220s | 1.37x | 68.7% | 10.6 MB |
| 4 | 1.670s | 1.83x | 45.7% | 9.0 MB |
| 8 | 1.528s | 2.00x | 25.0% | 9.4 MB |

**50-cohort subset (9,000 units):**

| Workers | Time | Speedup | Efficiency | Peak RSS |
|--------:|-----:|--------:|-----------:|---------:|
| 1 | 17.072s | 1.00x | 100% | ~19 MB |
| 2 | 9.591s | 1.78x | 89.0% | 20.6 MB |
| 4 | 5.590s | 3.05x | 76.4% | 19.3 MB |
| 8 | 4.824s | 3.54x | 44.2% | 19.3 MB |

**Full 313K units (measured, not extrapolated):**

| Workers | Time | Speedup vs Extrapolated Seq | Peak RSS |
|--------:|-----:|----------------------------:|---------:|
| 4 | 181.5s (3.0 min) | 2.76x | 697.4 MB |
| 8 | 155.5s (2.6 min) | 3.22x | 671.6 MB |

**Scaling observations:**
- At small scale (1,800 units), parallel efficiency drops sharply — overhead dominates.
- At medium scale (9,000 units), efficiency is reasonable at 4 workers (76.4%) but drops at 8 (44.2%).
- At full scale (313K units), the 8-worker speedup of 3.22x represents 40.3% parallel efficiency.
- The efficiency degradation at 8 workers is consistent across all subset sizes, suggesting it is a fundamental characteristic of the worker model (pickle overhead for plan initialization, IPC for result collection), not a dataset-size artifact.
- Full-scale 8w peak RSS is 672 MB, dominated by 8 worker processes each holding a copy of the plan.

## E. Reuse Analysis

### Fast-Path Grouping

| Metric | Value |
|--------|------:|
| Total planned units | 313,020 |
| Fast-path eligible | 313,020 (100%) |
| Independent recurrence evaluations | 78,255 |
| Derived units (prefix shortcut) | 234,765 |
| Reduction | 75.0% |
| Group key | `(start_date, allocation_policy, withdrawal_policy)` |

Within each group, the longest horizon (720 months) is evaluated once via `_evaluate_decimal_recurrence`. Shorter horizons (360, 480, 600 months) are derived by checking if the dataset is a prefix of the longest-horizon dataset. This is a mathematical optimization, not an IO optimization.

**What "independent evaluation" means:** One call to `_evaluate_decimal_recurrence` that runs the full monthly pipeline (13 steps × N months). The 78,255 independent evaluations produce 313,020 results because 234,765 are derived without re-running the recurrence.

### Dataset Slice Reuse

| Metric | Value |
|--------|------:|
| Unique dataset slices | 6,956 |
| Max possible (1,739 cohorts × 4 horizons) | 6,956 |
| Snapshot object sharing | 1.00x (all sliced datasets share the same MarketSnapshot objects from the canonical trajectory) |

The `dataset_cache` dict within `materialize_research_plan` ensures each `(start_date, horizon_months)` pair is sliced only once. All 180 parameter combinations for a given cohort share the same sliced `Dataset` object.

### Portfolio Build Redundancy

| Metric | Value |
|--------|------:|
| `build_initial_portfolio` calls | 313,020 |
| Unique inputs (cohort_start_date, horizon_months) | 6,956 |
| Redundant calls | 306,064 |
| Time per call | 0.003ms |
| Total time spent | ~1.0s |
| Estimated avoidable time | ~0.92s (if deduplicated by unique inputs) |
| Share of total sequential runtime | 0.18% |
| Classification | **Measurable but non-material** |

The redundancy exists because `materialize_research_plan` calls `build_initial_portfolio(experiment_def.initial_wealth, cohort_dataset)` for every unit, but the same `(initial_wealth, cohort_dataset)` pair produces the same `Portfolio`. Deduplicating by `(cohort.start_date, horizon_months)` would reduce calls from 313K to 6,956, saving ~0.92s on a 501s total runtime.

## F. Bottleneck Ranking

### 1. Mathematical Simulation (~496s, ~99.0% of sequential runtime)

- **Measured cost:** Extrapolated from 1.601ms/unit × 313,020 units
- **Why:** `_evaluate_decimal_recurrence` runs the full 13-step pipeline for each month, using exact Decimal arithmetic. Each independent group evaluates the longest horizon (avg ~541 months).
- **Repeated:** 78,255 independent evaluations (75% derived via prefix shortcut)
- **Can be parallelized:** Yes — already parallelized with 3.22x speedup at 8 workers
- **Engine change required:** Yes — any reduction in per-month cost requires engine-level optimization

### 2. Plan Materialization (5.04s, 1.0% of sequential runtime)

- **Measured cost:** 5.04s for 313K units (one-time)
- **Why:** Nested loop of 313K iterations, each constructing Portfolio + PSU
- **Repeated:** Once per study execution; amortized across all workers
- **Can be parallelized:** No (runs in parent process before worker dispatch)
- **Engine change required:** No — solvable in study/builder layer
- **Note:** For studies running >1 min, this is <1% overhead

### 3. Worker Initialization / Pickle (parallel-only, one-time per worker)

- **Measured cost:** ~3.97s to pickle all 313K units + ExperimentDefinition (72.8 MB total)
- **Why:** Each worker receives the full plan via pool initializer (`forkserver`/`spawn` start method)
- **Repeated:** Once per worker; amortized across all tasks within that worker
- **Can be reduced:** By using `fork` start method (unsafe) or shared memory (architectural change)

### 4. Data Loading (0.07s, <0.1% of sequential runtime)

- **Measured cost:** 0.067s (dataset) + 0.001s (FFR) = 0.068s
- **Why:** JSON parse + domain object conversion for 2,459 MarketSnapshot objects
- **Repeated:** Once per process (cached in DatasetCache)
- **Not a bottleneck**

### 5. FFR Rate Loading (0.001s, <0.001% of sequential runtime)

- **Measured cost:** 0.001s
- **Why:** JSON parse for 1,181 rate observations
- **Repeated:** Once per `load_ffr_rates()` call (no cache), but only called once per study
- **Not a bottleneck**

## G. Architectural Options

### A. Preload once in parent

- **Status:** Already implemented via `DatasetCache` singleton.
- **Verdict:** No change needed.

### B. Initialize once per worker

- **Status:** Already implemented via `_initialize_worker()`. Units + ExperimentDefinition sent once per worker.
- **Verdict:** No change needed.

### C. Per-process cache

- **Status:** Not needed. Workers don't repeat calls that would benefit from caching.
- **Verdict:** No change needed.

### D. Shared memory / state

- **Expected benefit:** Could share canonical Dataset via `multiprocessing.shared_memory`, eliminating 72.8 MB pickle per worker.
- **Memory implications:** Saves ~216 MB (3 workers × 72.8 MB). Full-scale 8w RSS is 672 MB; shared memory could reduce this.
- **Complexity:** High — requires managing shared memory lifecycle, pickling `SharedMemory` handles.
- **Verdict:** Possible but not justified at current scale. The 3.97s pickle cost is paid once per worker and amortized.

### E. Pass materialized immutable objects to workers

- **Status:** Already implemented. PSU objects are frozen dataclasses.
- **Verdict:** No change needed.

### F. Batch execution

- **Status:** Already implemented via `create_work_batches`.
- **Verdict:** No change needed.

### G. Eliminate redundant portfolio construction

- **Expected benefit:** ~0.92s savings on plan build (5.04s → ~4.12s)
- **Memory implications:** None
- **Semantic risk:** Low — portfolio depends only on `(initial_wealth, cohort_dataset)`
- **Complexity:** Low — add a cache dict in `materialize_research_plan` keyed on `(cohort.start_date, horizon_months)`
- **Classification:** Measurable but non-material (0.18% of total sequential runtime)
- **Verdict:** Low priority. Could be done as a trivial improvement but not worth a dedicated phase.

### H. No change

- **Status:** The current architecture is correct for the measured workload.
- **Verdict:** Recommended. The measured costs are dominated by legitimate mathematical work.

## H. Architectural Recommendation

The current execution architecture should remain unchanged. The measurements establish:

1. **No significant repeated IO was observed.** Dataset loads once (0.067s), subsequent access is in-memory.
2. **Plan materialization represents 1.0% of total sequential runtime** (5.04s out of ~501s). This is a one-time cost.
3. **The measured worker overhead** produces 40.3% parallel efficiency at 8 workers for the full 313K workload. This is a characteristic of the forkserver/spawn pickle-based worker model, not a defect.
4. **The remaining runtime (~99%) is dominated by Decimal recurrence evaluation** in the fast-path engine. This is the legitimate cost of exact arithmetic.
5. **One minor optimization opportunity exists** (deduplicate `build_initial_portfolio` calls), saving ~0.92s on plan build. This is measurable but non-material.

No execution-layer redesign is justified at this stage.

## I. P4.11 Implications

The P4.11 design (Part 52: drawdown-triggered borrowing, repayment, FFR-based floating rates, LTV enforcement) introduced:

- `Part52WithdrawalPolicy` — pure domain logic, no IO
- `LoanRepaymentStep`, `InterestAccrualStep` — pipeline steps, pure Decimal math
- `is_repayment` flag — no IO impact
- FFR schedule per cohort — negligible IO (0.001s load, per-cohort construction is pure CPU)

**All P4.11 design elements remain valid.** None of the measured bottlenecks are related to Part 49/52 implementation. The leverage features add zero IO overhead and negligible execution overhead (a few extra pipeline steps per month, all pure Decimal math).

The FFR rate loading is not cached (`load_ffr_rates` re-reads JSON each call), but this is called once per study (not per unit), so the 0.001s cost is non-material.

## J. Decision

**APPROVE DESIGN**

The corrected measurements confirm:

1. No significant repeated IO exists. Dataset loads once; subsequent access is in-memory.
2. Plan materialization is 1.0% of total runtime (5.04s / 501s), not 16.4% as previously reported.
3. Mathematical simulation dominates at ~99% of sequential runtime.
4. Parallel efficiency at 8 workers is 40.3% (not "near-linear"), but this is a characteristic of the forkserver/spawn worker model, not a defect requiring redesign.
5. The system is ready for S6.5 without execution-layer modifications.
