# S5.4-R2: Execution & Research Result Storage Architecture Design

**Stage:** S5.4-R2 — Architecture design (no implementation)  
**Status:** COMPLETE  
**Date:** 2026-09-05  
**Scope:** Bounded-memory execution, persisted research data model, storage format, implementation sequence  

---

## A. Problem Statement

S5.4 requires executing 93,906 simulation units (54 cells × 1,739 cohorts) for the ERN Part 49 leverage study. The current architecture has two independent problems:

1. **Execution lifetime**: All 93,906 `SimulationResult` objects are held in memory simultaneously via tuple comprehension in `executor.py:22-25`. Peak memory: ~56 GB. OOM kills at ~93 GB.

2. **Result representation**: Persisting raw `SimulationResult` objects produces ~20 GB (pickle) or ~146 GB (JSON-in-SQLite). Most storage is redundant: constant fields serialized 361 times per trajectory, full `MarketSnapshot` objects embedded when recoverable from dataset identity.

These are independent problems requiring independent solutions.

---

## B. Consumer Access Pattern Audit

### B.1 What Consumers Actually Need

| Consumer | Full trajectory? | Statistics only? | Specific monthly fields |
|----------|:-:|:-:|-----------------|
| `part3_aggregation.py` | | **X** | `statistics.success` |
| `cape_aggregation.py` | | **X** | `statistics.success` |
| P10: `get_result_statistics()` | | **X** | `final_wealth`, `max_drawdown`, `success`, `failure_month` |
| P10: `get_result_trajectory_percentiles()` | **X** | | `portfolio_value` per month |
| P11: `get_cohort_horizon_grid()` | | **X** | `success`, `failure_month`, `final_wealth` |
| ERN SWR oracle (CLI) | | **X** | `units_run`, `units_failed` per cell |
| Part 49 debt tests | **X** (in-memory) | | `debt_snapshot.*` per month |
| LTV trajectory analysis | **X** (in-memory) | | `debt_snapshot.ltv` per month |
| Failure analysis | | **X** | `failure_month` |

### B.2 Key Finding

**5 of 8 consumers need only statistics/summaries.** Only 3 consumers need full trajectories, and 2 of those are in-memory-only (debt/LTV analysis). The only consumer that needs persisted full trajectories is P10 percentile visualization.

### B.3 Current Persistence Gaps

The `SimulationResultCodec` does NOT serialize:
- `debt_snapshot` (Part 49 debt state) — lost on persistence
- `failure_state` (reason string) — only `failure_month` is persisted

This means Part 49 debt trajectory analysis cannot be performed on persisted data today.

---

## C. Bounded-Memory Execution Semantics

### C.1 Current Architecture

```
ResearchExecutor.execute(plan)
  → translate ALL units to SimulationContexts  (O(N) memory)
  → SimulationExecutor.execute(definition)
    → tuple(runner.run(context) for context in contexts)  (O(N) memory)
  → ExperimentRun(simulation_results=tuple(...))  (O(N) memory)
  → return to caller  (O(N) memory)
```

Total: O(N) memory for N units. For 93,906 units: ~56 GB.

### C.2 Proposed: Batched Execution with Emit-and-Release

```
BatchedExecutor.execute(plan, batch_size=1000)
  for batch in partition(plan.units, batch_size):
      contexts = translate(batch)           # O(batch_size) memory
      results = execute(contexts)           # O(batch_size) memory
      emit(results)                         # callback: persist/aggregate
      del results                           # release
      del contexts                          # release
  return BatchExecutionReport(...)          # O(1) — summary only
```

Total: O(batch_size) memory. For batch_size=1000: ~160 MB.

### C.3 Execution Boundary Contract

```python
class BatchedExecutor:
    """Executes a ResearchPlan in bounded-memory batches."""
    
    def execute(
        self,
        plan: ResearchPlan,
        batch_size: int = 1000,
        on_batch_complete: Callable[[BatchResult], None] | None = None,
    ) -> BatchExecutionReport:
        """Execute plan in batches, emitting each batch for persistence.
        
        Parameters
        ----------
        plan:
            The research plan to execute.
        batch_size:
            Number of units per batch. Memory is O(batch_size).
        on_batch_complete:
            Called after each batch is executed and before results are released.
            The callback receives a BatchResult containing the batch's
            SimulationResults and must persist or aggregate them before returning.
            After the callback returns, the batch's results are released from memory.
        
        Returns
        -------
        BatchExecutionReport
            Aggregate statistics: total units, batches, timing, success/failure counts.
            Does NOT contain SimulationResult objects.
        """
```

### C.4 BatchResult Contract

```python
@dataclass(frozen=True)
class BatchResult:
    """One batch of completed simulation results, emitted for persistence."""
    batch_index: int
    unit_results: tuple[SimulationResult, ...]  # bounded by batch_size
    wall_time_seconds: float
    peak_memory_bytes: int
```

### C.5 BatchExecutionReport Contract

```python
@dataclass(frozen=True)
class BatchExecutionReport:
    """Aggregate report from a batched execution. Contains NO trajectory data."""
    plan: ResearchPlan  # reference only, not copied
    total_units: int
    total_batches: int
    successful_units: int
    failed_units: int
    total_wall_time_seconds: float
    per_batch_timing: tuple[float, ...]
    per_batch_memory: tuple[int, ...]
```

### C.6 Key Design Decisions

1. **Deterministic sequential batches**: No parallelism initially. Simpler, deterministic, easier to debug.

2. **Arbitrary fixed-size batches**: Not coupled to cells or cohorts. The scheduler does not need to understand research structure.

3. **Callback-based persistence**: `on_batch_complete` receives `BatchResult` and is responsible for persisting it. The executor does not know about storage.

4. **No checkpoint/resume yet**: Each batch is persisted atomically by the callback. Resume can be added later by tracking which batches completed.

5. **ResearchExecutor adaptation**: `ResearchExecutor.execute()` currently builds `ExperimentRun` from all results. It should be adapted to use `BatchedExecutor` and emit batches. The `ExperimentRun` contract can be preserved for small runs (batch_size >= total_units) by collecting all results.

---

## D. Persisted Research-Result Data Model

### D.1 Design Principle

The persisted representation is a **research-storage model**, not a serialized Python object graph. It should be designed for:
- Compact storage
- Efficient research queries
- Independence from Python runtime objects
- Long-term stability (not coupled to code changes)

### D.2 Research Data Model

```
StudyResult (top-level)
├── study_metadata
│   ├── name, description, version
│   ├── dataset_identifier, dataset_version
│   ├── initial_wealth, currency
│   ├── horizon_months
│   └── policy_configurations (allocation, withdrawal, debt)
├── cell_results[] (one per parameter cell)
│   ├── cell_key (equity, swr, interest_rate, ...)
│   ├── cell_metadata (parameters)
│   ├── cell_summary
│   │   ├── units_total, units_successful, units_failed
│   │   ├── success_rate
│   │   ├── terminal_wealth_percentiles (p10, p25, p50, p75, p90)
│   │   ├── max_drawdown_stats (min, max, mean, median)
│   │   └── failure_month_histogram
│   └── cohort_results[] (one per cohort in this cell)
│       ├── cohort_start_date
│       ├── trajectory_summary
│       │   ├── success (bool)
│       │   ├── failure_month (int | None)
│       │   ├── failure_state (str | None)
│       │   ├── final_wealth (Decimal)
│       │   ├── max_drawdown (float)
│       │   └── months_simulated (int)
│       └── trajectory_detail[] (monthly, optional)
│           ├── period_index (int)
│           ├── date (ISO string)
│           ├── portfolio_value (Decimal)
│           ├── equity_units, bond_units (Decimal)
│           ├── allocation_weights (dict, stored once per cell)
│           ├── withdrawal_amount (Decimal, stored once per cell)
│           ├── loan_balance (Decimal, optional)
│           ├── cash_balance (Decimal, optional)
│           ├── ltv (Decimal, optional)
│           └── net_worth (Decimal, optional)
```

### D.3 Normalization Rules

| Rule | Current (MonthlyResult) | Normalized (Research Model) |
|------|------------------------|----------------------------|
| MarketSnapshot | Embedded per month | Recoverable from dataset + period_index. Store dataset_identity + period_index only. |
| Allocation weights | Per month (new object each time) | Constant per cell for ConstantAllocationPolicy. Store once at cell level. |
| AllocationTarget | Per month (new object each time) | Same as allocation. Store once at cell level. |
| WithdrawalDecision amounts | Per month (new object each time) | Constant per cell for Part49WithdrawalPolicy. Store once at cell level. |
| Dead fields (6 fields) | Per month (always defaults) | Not stored. |
| Portfolio holdings | Per month (genuinely varying) | Stored per month. But only units per asset, not full AssetClass objects. |
| DebtSnapshot | Per month (when interest > 0) | Stored per month. Not currently persisted by codec. |

### D.4 Storage Size Estimate

| Component | Current (pickle) | Normalized | Savings |
|-----------|-----------------|------------|---------|
| Per trajectory metadata | ~500 bytes | ~300 bytes | 40% |
| Per trajectory statistics | ~200 bytes | ~200 bytes | 0% |
| Per trajectory monthly data | 361 × ~600 bytes | 361 × ~48 bytes | 92% |
| Per trajectory total | ~217 KB | ~17.6 KB | 92% |
| Full 54-cell grid (93,906 units) | ~19.97 GB | ~1.65 GB | 92% |
| Minimum ERN (10,434 units) | ~2.27 GB | ~184 MB | 92% |

The 92% reduction comes from:
- Not embedding MarketSnapshot per month (saves ~300 bytes/month)
- Not embedding Allocation/AllocationTarget per month (saves ~120 bytes/month)
- Not embedding WithdrawalDecision per month (saves ~80 bytes/month)
- Not storing 6 dead fields (saves ~20 bytes/month)
- Storing portfolio holdings as raw values, not full objects (saves ~100 bytes/month)

---

## E. Storage Format Comparison

### E.1 Options Evaluated

| Option | Format | Dependencies | Query capability |
|--------|--------|-------------|-----------------|
| **A. Current JSON-in-SQLite** | JSON blobs in relational tables | sqlite3 (stdlib) | Full SQL on metadata; no SQL on monthly values |
| **B. Normalized SQLite** | Structured columns + binary monthly data | sqlite3 (stdlib) | SQL on metadata + summaries; binary for trajectories |
| **C. File-per-cell** | JSON metadata + binary trajectory files | None (struct stdlib) | File-level access only |
| **D. Hybrid: SQLite + files** | SQLite for metadata/summaries + file-per-trajectory | sqlite3 (stdlib) | SQL on summaries; file access for trajectories |

### E.2 Evaluation Against Access Patterns

| Access pattern | Option A | Option B | Option C | Option D |
|---------------|----------|----------|----------|----------|
| Per-cell success rate | SQL | SQL | File scan | SQL |
| Terminal wealth percentiles | SQL | SQL | File scan | SQL |
| Trajectory percentile bands | Full scan | Full scan | File scan | File scan |
| Single trajectory retrieval | SQL | SQL + decode | File read | File read |
| Export to CSV | Full scan | Full scan | File scan | File scan |
| Resume interrupted run | SQL | SQL | File existence | SQL + file existence |
| Schema evolution | Easy (JSON) | Moderate (ALTER TABLE) | Hard (binary layout) | Moderate |

### E.3 Recommendation

**Option D: Hybrid SQLite + files** for the following reasons:

1. **SQLite for metadata and summaries**: Experiments, plans, cell summaries, trajectory summaries are relational data that benefit from SQL queries. They are small (~MB) and change infrequently.

2. **Files for trajectories**: Monthly trajectory data is large (~GB), write-once/read-for-analysis, and benefits from binary encoding. File-per-cell or file-per-trajectory is natural for batch writes.

3. **No new dependencies**: Uses only `sqlite3` (stdlib) and `struct` (stdlib) for binary encoding.

4. **Natural batch alignment**: Each batch writes to one or more trajectory files. Atomic writes are trivial (write-then-rename).

5. **Dataset reference**: Trajectories reference the dataset by identifier + start_offset, not by embedding market data. The dataset is loaded once and shared.

### E.4 File Layout

```
results/
├── study_metadata.json          # Study configuration, dataset identity
├── cells/
│   ├── cell_075_030_000.json    # Cell metadata + summary
│   ├── cell_075_030_015.json
│   ├── ...
│   └── cell_100_050_030.json
├── trajectories/
│   ├── cell_075_030_000/
│   │   ├── 1871-01-31.bin       # Binary trajectory for cohort 1871-01-31
│   │   ├── 1871-02-28.bin
│   │   └── ...
│   ├── cell_075_030_015/
│   │   └── ...
│   └── ...
├── summaries/
│   ├── cell_success_rates.json  # Pre-computed per-cell success rates
│   ├── terminal_wealth_grid.json
│   └── ltv_trajectories.json    # Optional: LTV analysis results
└── execution_log.json           # Batch execution timing, memory, throughput
```

### E.5 Binary Trajectory Format

Each trajectory file is a `struct.pack`-encoded binary blob:

```python
TRAJECTORY_HEADER = struct.Struct("<I I d d ? I d")  # 37 bytes
# uint32: period_count
# uint32: dataset_offset (index into master dataset)
# float64: initial_wealth
# float64: final_wealth
# bool: success
# uint32: failure_month (0xFFFFFFFF if none)
# float64: max_drawdown

MONTHLY_RECORD = struct.Struct("<I d d d d d d d")  # 61 bytes
# uint32: period_index
# float64: portfolio_value
# float64: equity_units
# float64: bond_units
# float64: loan_balance (0.0 if no debt)
# float64: cash_balance (0.0 if no debt)
# float64: ltv (0.0 if no debt)
# float64: net_worth (portfolio + cash - loan)
```

**Size per trajectory**: 37 + (361 × 61) = 22,058 bytes (~22 KB)  
**Size for 93,906 trajectories**: ~2.07 GB  
**Size for 10,434 trajectories (minimum ERN)**: ~230 MB

**Note**: This uses `float64` for simplicity. For decimal precision requirements, a variable-length Decimal encoding can be substituted at the cost of larger files and slower I/O. The tradeoff should be evaluated against actual precision requirements.

---

## F. Relationship Between Components

### F.1 Component Relationship Diagram

```
ResearchPlan (immutable, shared)
    │
    ▼
BatchedExecutor (new)
    │
    ├── for each batch:
    │       │
    │       ▼
    │   SimulationExecutor (existing, unchanged)
    │       │
    │       ▼
    │   SimulationRunner → SimulationResult × batch_size
    │       │
    │       ▼
    │   on_batch_complete callback
    │       │
    │       ├── ResearchResultSerializer (new)
    │       │       │
    │       │       ▼
    │       │   Normalized trajectory data
    │       │       │
    │       │       ▼
    │       │   ResearchResultStore (new)
    │       │       │
    │       │       ▼
    │       │   files/ + SQLite metadata
    │       │
    │       └── AggregationAccumulator (new, optional)
    │               │
    │               ▼
    │           Incremental cell summaries
    │
    ▼
BatchExecutionReport (summary only, no trajectories)
```

### F.2 What Changes vs. What Stays

| Component | Status | Reason |
|-----------|--------|--------|
| `SimulationRunner` | **Unchanged** | Continues building full `SimulationResult` |
| `SimulationExecutor` | **Unchanged** | Continues executing contexts sequentially |
| `MonthlyResultBuilderStep` | **Unchanged** | Continues capturing full monthly state |
| `ResearchExecutor` | **Adapted** | Uses `BatchedExecutor` for large plans; preserves `ExperimentRun` for small plans |
| `SimulationResult` | **Unchanged** | Execution model stays rich |
| `ExperimentRun` | **Preserved** | For small runs (batch_size >= total), all results collected |
| New: `BatchedExecutor` | **New** | Bounded-memory batch loop with callback |
| New: `BatchResult` | **New** | Batch emission contract |
| New: `BatchExecutionReport` | **New** | Aggregate report without trajectories |
| New: `ResearchResultSerializer` | **New** | Converts `SimulationResult` to normalized format |
| New: `ResearchResultStore` | **New** | Writes normalized data to files + SQLite |
| New: `AggregationAccumulator` | **New** | Incremental cell/cohort summaries |
| SQLite codec | **Deprecated** | Replaced by normalized format for new runs |
| Dead fields (6) | **Not extracted** | `ResearchResultSerializer` simply does not read them |

### F.3 Backward Compatibility

| Scenario | Impact |
|----------|--------|
| Existing SQLite databases | Continue to work with existing `SQLiteRepository` code |
| New execution runs | Use `BatchedExecutor` + `ResearchResultStore` |
| Existing `ExperimentRun` consumers | Continue to work for small runs |
| ERN oracle tests | Unchanged — CLI subprocess, parses stdout |
| Part 49 research consumers | Adapted to read from new store |

---

## G. Implementation Sequence

### G.1 Guiding Principles

1. **Minimum replication first**: Execute 6-cell / 10,434-unit workload before building infrastructure for 54-cell grid.
2. **Separate concerns**: Execution batching ≠ persistence ≠ aggregation. Implement one at a time.
3. **No premature optimization**: Do not add parallelism, checkpoint/resume, or complex scheduling before proving sequential batching works.
4. **Preserve existing contracts**: `ExperimentRun`, `SimulationResult`, `MonthlyResult` stay unchanged for existing consumers.

### G.2 Proposed Stages

#### S5.4-R3 — Minimum Replication Execution

**Scope**: Execute the canonical 6-cell / 10,434-unit workload with current architecture.

**Why first**: Validates that the canonical ERN replication works at meaningful scale before building new infrastructure.

**Workload**:
- 2 equity allocations × 3 interest rates × 1,739 cohorts
- SWR fixed at 3% + 1% loan = 4% total

**Measurements**:
- Wall-clock time
- Peak RSS
- Execution throughput (units/second)
- Result size (pickle)
- Per-cell success rates
- ERN anchor consistency (95%, 65%, 97%)

**Memory**: ~6 GB peak (fits on development machine). This is architecturally unhealthy but acceptable as a one-time validation run.

**Exit criteria**: All 10,434 units execute successfully. Per-cell success rates match ERN expectations within tolerance.

#### S5.4-R4 — Batched Execution Implementation

**Scope**: Implement `BatchedExecutor` with callback-based persistence.

**Deliverables**:
- `BatchedExecutor` class
- `BatchResult` dataclass
- `BatchExecutionReport` dataclass
- Adaptation of `ResearchExecutor` to use `BatchedExecutor`
- Unit tests with small batches

**Design constraints**:
- Deterministic sequential batches
- Arbitrary fixed-size batches (not cell/cohort-aware)
- No parallelism
- No checkpoint/resume
- Callback receives `BatchResult`, responsible for persistence

**Verification**: Execute minimum ERN replication (10,434 units) with batch_size=1000. Verify identical results to S5.4-R3. Measure peak RSS (~160 MB expected).

#### S5.4-R5 — Normalized Persistence Implementation

**Scope**: Implement `ResearchResultSerializer` and `ResearchResultStore`.

**Deliverables**:
- `ResearchResultSerializer` — converts `SimulationResult` to normalized format
- `ResearchResultStore` — writes to files + SQLite metadata
- `AggregationAccumulator` — incremental cell/cohort summaries
- Binary trajectory format (struct.pack)
- SQLite schema for metadata + summaries

**Design constraints**:
- No raw pickle as canonical format
- Normalized representation independent of Python object layout
- Trajectory data in binary files; metadata in SQLite
- Dead fields not extracted
- `debt_snapshot` included in normalized format (fixes current persistence gap)

**Verification**: Persist minimum ERN replication. Verify:
- Storage size < 250 MB (vs ~2.27 GB current)
- All trajectory data round-trips correctly
- Cell summaries match in-memory computation
- Debt state is preserved (currently lost by codec)

#### S5.4-S5/S5.6 — Full Grid Execution + Analysis

**Scope**: Execute full 54-cell grid with batched execution + normalized persistence.

**Prerequisites**: S5.4-R3, R4, R5 complete.

**Workload**: 54 cells × 1,739 cohorts = 93,906 units.

**Expected resources**:
- Peak memory: ~160 MB (bounded by batch_size)
- Storage: ~1.65 GB (normalized) vs ~19.97 GB (current)
- Wall-clock: ~26 hours (estimated from S5.4-R3 measurements)

---

## H. Migration Path

### H.1 Existing Code

| Component | Migration |
|-----------|-----------|
| `SQLiteRepository` | Deprecate for new runs. Continue to work for existing databases. |
| `SimulationResultCodec` | Deprecate. New runs use `ResearchResultSerializer`. |
| `ResearchExecutor` | Adapt to use `BatchedExecutor` for large plans. Preserve `ExperimentRun` for small plans. |
| `ExperimentRun` | Preserve as-is for backward compatibility. New large runs may not produce it (only `BatchExecutionReport`). |
| `MonthlyResult` | No changes. Execution model stays rich. |
| Dead fields (6) | Not extracted by new serializer. Remove in future cleanup. |

### H.2 Existing Tests

| Test category | Impact |
|---------------|--------|
| Unit tests (pipeline, steps) | Unchanged — test execution, not persistence |
| Integration tests (S5.2, S5.3) | Unchanged — test materialization and execution |
| Infrastructure tests (codecs, SQLite) | Continue to test existing codec/SQLite code |
| Contract tests | Update to verify new `BatchedExecutor` contract |

### H.3 Dead Field Removal

Deferred to a separate cleanup after S5.4-R5. The new `ResearchResultSerializer` simply does not extract them. No `MonthlyResult` dataclass change needed until the old SQLite codec is retired.

---

## I. Answers to Architecture Questions

### I.1 Batch Granularity

**Arbitrary fixed-size batches.** Not coupled to cells or cohorts initially. Rationale:
- Easier to benchmark
- Simpler scheduler
- Avoids assumptions about future workload distribution

The scheduler may later support semantic partitioning (e.g., batch by cell) if profiling shows it improves cache locality or aggregation efficiency.

### I.2 Result Store Format

**Hybrid: SQLite for metadata/summaries + binary files for trajectories.** Rationale:
- SQLite is already in the project (stdlib `sqlite3`)
- Metadata benefits from SQL queries (experiments, plans, summaries)
- Trajectories benefit from binary encoding (6× smaller than JSON)
- File-per-cell aligns with batch writes (atomic via write-then-rename)

### I.3 Incremental Aggregation

**Yes, via `AggregationAccumulator` callback.** Per batch:
- Update cell-level success/failure counts
- Update terminal wealth statistics
- Update failure month histogram
- Optionally compute trajectory percentile bands

Do NOT discard canonical trajectories merely because aggregates exist.

### I.4 Parallel Batching

**No, not initially.** First make bounded-memory sequential batching correct and deterministic. Then benchmark. Parallelism can be added later by:
- Partitioning the plan across workers
- Each worker runs `BatchedExecutor` independently
- Aggregation accumulator must be thread-safe

### I.5 Checkpoint/Resume

**Desirable but not required for first implementation.** If each completed batch is persisted atomically, checkpoint/resume may emerge naturally later by:
- Checking which batch files exist
- Skipping completed batches
- Resuming from next batch index

Do not design a complicated resumable scheduler prematurely.

---

## J. Conclusion

### Key Architectural Decisions

1. **Two independent problems**: Execution lifetime (batching) ≠ result representation (normalization). Solve separately.

2. **Research-storage model**: The persisted representation is NOT a serialized Python object graph. It is a purpose-built research data model designed for compact storage and efficient queries.

3. **Hybrid storage**: SQLite for metadata + binary files for trajectories. Leverages existing stdlib capabilities.

4. **Callback-based persistence**: `BatchedExecutor` emits `BatchResult` via callback. The executor does not know about storage. The callback is responsible for persistence.

5. **Minimum replication first**: Execute 6-cell workload before building infrastructure for 54-cell grid.

6. **No premature optimization**: No parallelism, checkpoint/resume, or complex scheduling in first implementation.

7. **Dead fields deferred**: Not part of S5.4 critical path. New serializer simply does not extract them.

### Recommended Next Step

**S5.4-R3: Minimum Replication Execution.** Execute 10,434 units with current architecture. Measure baseline. Validate ERN replication correctness. This is the prerequisite for all subsequent architecture work.
