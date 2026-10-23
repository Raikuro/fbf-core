# Roadmap: Migration to a Single Numba Execution Engine

**Status:** Complete. Phases A, B, C, and D are complete, including D4.3
legacy-engine deletion; D5a and D5b are complete. Numba is the sole production
simulation engine, `ExecutionBackend.FAST` is the only backend value, Core is
`0.3.0`, and consumer pins are updated. The independent historical oracle
(`tools/ern/reference_oracle.py`) is preserved (see §9).
**Scope:** FBF Core execution layer (`src/fbf/core/execution/`).
**Objective:** Make Numba the sole simulation engine, progressively shrink and
eventually delete the legacy Reference execution stack, and preserve
`tools/ern/reference_oracle.py` as the independent historical published-ERN oracle.

> This document is a plan. It does not authorize code changes. Every phase
> lists explicit deletion and migration gates that must be satisfied before
> the next phase begins.

---

## 1. Objective and Target Architecture

### 1.1 Objective

1. Numba is the sole execution engine for simulation workloads.
2. Functionality already supported by Numba must stop depending on the legacy
   Reference execution stack.
3. Functionality Numba does not yet support is documented as an explicit
   migration item.
4. The legacy Reference pipeline shrinks as capabilities migrate.
5. Once all required capability has migrated, the legacy Reference engine and
   its redundant abstractions are deleted.
6. `tools/ern/reference_oracle.py` remains untouched as an independent
   implementation for validating historical published-ERN replication.

### 1.2 Target architecture

```
YAML
  → StudyConfiguration.from_yaml()
  → build_study_plan() / run_study()
  → execute_study_plan()  (backend dispatch)
  → NumbaSimulationExecutor / Part52NumbaExecutor / unified Numba engine
  → SimulationResult (statistics + optional monthly trajectory)

Independent historical oracle (never imported by production code):
  tools/ern/reference_oracle.py
```

There is no second generic Decimal engine in the target state.

### 1.3 Naming after D4.3

D4.3 removed the naming ambiguity by deleting both alternative meanings:

| Former term | Disposition |
|-------------|-------------|
| `ExecutionBackend.DECIMAL_FAST_PATH` / `REFERENCE` | Deleted. `FAST` is the only backend value. |
| `ReferenceSimulationExecutor` / `execute_reference()` | Deleted. The internal Numba executors reject unsupported contexts explicitly. |
| "the reference engine" (legacy nine-step Decimal pipeline) | Deleted, including its pipeline steps, factories, and reporting helpers. |

The word "reference" now survives only in **independent oracles**:

- `tools/ern/reference_oracle.py` is the historical published-ERN oracle. It
  is never imported by production code.
- `tools/ern/workbook_oracle.py` is the production-conformance oracle.

Test-only independent Decimal recurrences are named explicitly as oracles and
are not production execution paths.

---

## 1.4 Workbook-First Financial Correctness Policy

`SWR_Toolbox_v2.0.xlsx` is the authoritative specification whenever it defines the relevant behavior.

- Trace the actual workbook formulas and calculation order before implementing or changing financial calculations.
- Preserve the validated workbook behavior, including the additive fee model (`weighted_return - fee/12`) and beginning-of-month withdrawal semantics (withdraw → grow) where applicable.
- Do not assume that using the same fee convention automatically makes an unsupported workload workbook-equivalent.
- Where the workbook does not define behavior (e.g., dynamic glidepaths, Part 52 timing leverage, buy-and-hold), explicitly specify and test the simulator extension. Do not silently invent financial semantics.
- Keep `tools/ern/workbook_oracle.py` and `tools/ern/reference_oracle.py` independent of production Numba code. `workbook_oracle.py` is the production-conformance oracle; `reference_oracle.py` is the historical published-ERN replication oracle.
- Do not regenerate, replace, or delete existing oracle data (`data/ern/p49_oracle_table.csv` or `data/ern/workbook_oracle_table.csv`). The workbook and published ERN methodologies differ (workbook uses T cohort terms and an additive fee; the reference oracle uses T+1 terms and a multiplicative fee; both withdraw at the beginning of the month). Document the difference rather than silently overwriting one with the other.

---

## 1.5 Memory-Safety Requirements

- The ERN canonical grid (313,020 units × 720 months) serializes ~0.32 MiB/unit of timeline payload (~100 GiB total). Retaining materialized results in memory costs roughly 1.5 MiB/unit on a 64-bit CPython host, so whole-grid retention is a multi-hundred-GiB proposition; the serialized payload is not an RSS estimate.
- `iter_execute_study_plan()` (D2) executes a plan lazily in cohort-aligned slices and does not retain slices internally. `execute_study_plan()` remains the whole-plan API and rejects materialized plans above `ExecutionOptions.max_materialized_units` (default 1,000) with `UnsupportedConfigurationError`.
- Default slice targets are 500 units for materialized execution and 20,000 units for summary-only execution. A cohort larger than the target is emitted intact, so the target is a memory-control parameter, not a hard bound. Consumers must release each slice before advancing (for example `del chunk`) to keep only one slice resident.
- Measured on a synthetic 720-month, fixed-real workload (isolated subprocesses): 200-unit materialized slices peaked ~272–294 MiB above the post-plan baseline across 200–800 total units; 500-unit slices peaked ~628–645 MiB across 500–1,000 total units; 20,000-unit summary slices peaked ~59–64 MiB across 20,000–40,000 total units. Peak residency tracked the slice target rather than total workload size. These figures are indicative, not a guarantee for every host or workload.
- Incremental persistence (D2, schema v4) writes each completed slice in its own `BEGIN IMMEDIATE` transaction. The 200-unit materialized streaming run peaked ~284 MiB above the post-setup baseline whether or not slices were persisted, and a 400-unit run peaked ~289 MiB; persistence added ~4 MiB peak residency. The resulting SQLite database was ~204 MiB for 200 units and ~408 MiB for 400 units (~1.02 MiB/unit). Persistence cost is therefore storage-bound, not resident-memory bound, when the writer receives released slices.
- Any trajectory materialization (Phase D1) **requires** cohort-slice dispatch (Phase D2) to be implemented first or concurrently.
- Summary-only execution (`summary_only=True`) must remain efficient and is the default for large grids.
- Timeline materialization is opt-in unless existing public behavior requires otherwise.
- The 16 GB memory target is a validation target, not an assumed guarantee. Actual workload requirements and execution environments must be measured.

---

## 2. Current Execution Architecture

This section describes the repository after D4.3.

### 2.1 Backend selection (`execution/__init__.py`)

- Public enum: `ExecutionBackend.FAST = "fast"` is the only value.
  `DECIMAL_FAST_PATH` and `REFERENCE` no longer exist.
- `execute_study_plan(plan, options)`:
  - `backend is None` (AUTO) or `backend == FAST` selects a Numba executor
    through capability routing. Both paths fail closed.
  - Missing Numba raises `ModuleNotFoundError` with installation guidance.
  - `ExecutionStrategy.AUTO` and `SEQUENTIAL` execute sequentially.
    `PARALLEL` raises `ValueError` because it is counterproductive for Numba.
- AUTO routing order:
  1. All units Part 52-eligible → `Part52NumbaExecutor`.
  2. All units Part 49-eligible → `Part49NumbaExecutor`.
  3. All units Part 49 buy-and-hold-eligible →
     `Part49BuyAndHoldNumbaExecutor`.
  4. All units fixed-real-eligible → `NumbaSimulationExecutor`.
  5. All units constant-nominal-eligible → `NumbaSimulationExecutor`.
  6. All units escalating-eligible → `NumbaSimulationExecutor`.
  7. All units zero-fee buy-and-hold-eligible → `NumbaSimulationExecutor`.
  8. All units glidepath-eligible → `NumbaSimulationExecutor`.
  9. Otherwise → `UnsupportedConfigurationError`.
- Explicit FAST applies the same families with additional mixed-plan checks:
  a plan containing Part 52 units must be entirely Part 52-eligible; likewise
  for Part 49. Unsatisfied plans raise `UnsupportedConfigurationError`.
- There is no Decimal, reference, or pure-Python simulation fallback.

### 2.2 Executors

| Executor | File | Eligible workloads | Ineligible handling |
|----------|------|--------------------|---------------------|
| `NumbaSimulationExecutor` | `strategies/numba_executor.py` | Generic fixed-real (including explicit N-asset allocations), constant-nominal, escalating, zero-fee buy-and-hold, and glidepath families | Raises `UnsupportedConfigurationError`; no fallback executor |
| `Part49NumbaExecutor` | `strategies/part49_numba_executor.py` | Constant allocation + `Part49WithdrawalPolicy`, 2 assets, debt/LTV supported | Raises `UnsupportedConfigurationError` |
| `Part52NumbaExecutor` | `strategies/part52_numba_executor.py` | Constant allocation + `Part52WithdrawalPolicy`, 2 assets, interest-rate source, supported additive fee | Raises `UnsupportedConfigurationError` |
| `Part49BuyAndHoldNumbaExecutor` | `strategies/part49_buy_and_hold_numba_executor.py` | Buy-and-hold + `Part49WithdrawalPolicy`, 2 assets, zero fee, debt/LTV supported | Raises `UnsupportedConfigurationError` |

`SimulationExecutor` (`pipeline/executor.py`) is an abstract application-layer
contract. `parallel_executor.py` exposes a low-level `parallel_execute()` helper
used by Core equivalence tests; the high-level API does not expose parallel
execution.

### 2.3 Shared eligibility and grouping

`strategies/eligibility.py` owns the shared predicates and trajectory helpers:
`is_fast_path_eligible`, `_weights_by_class`, dataset identity/cluster/group
helpers, and trajectory prefix clustering. The dedicated executors and the
generic executor import these helpers; there is no legacy pipeline module.

`pipeline/schedule.py` models rebalance cadence as an `ExecutionSchedule` with
a private `"rebalance"` key. It has no dependency on pipeline steps.

### 2.4 Output contract

- Numba executors return empty timelines by default
  (`materialize_timeline=False`).
- With `materialize_timeline=True` they emit monthly results, including debt
  snapshots where applicable.
- Persistence round-trips `monthly_results`; empty timelines persist nothing per
  month.
- Streaming persistence (schema v4) stores an explicit execution lifecycle in
  `execution_results.status` plus `attempt_id`/`completed_units` metadata.
  `begin_execution`, `append_execution_slice`, and `complete_execution` are
  crash-safe: slice rows and counters commit atomically, appends are contiguous
  and idempotent per attempt, and completion verifies expected unit/result
  coverage. `list_incomplete_executions`, `fail_execution`, and
  `abandon_execution` replace age-based cleanup. Completed-result reads filter
  `status = 'completed'`.
- The CLI and UI use explicit FAST and require `fbf-core[numba]`. Persisted
  runs use `materialize_timeline=True` with the streaming API and incremental
  writer.

### 2.5 Eligibility predicates (source of truth)

| Predicate | Location | Requires |
|-----------|----------|----------|
| `is_fast_path_eligible` | `strategies/eligibility.py` | Constant allocation + fixed-real withdrawal, horizon ≥ 1, dataset ≥ horizon; either exactly 2 holdings with one equity or an explicit allocation mapping covering held classes |
| `_is_numba_eligible` | `strategies/numba_executor.py` | Alias of `is_fast_path_eligible` |
| `_is_constant_nominal_eligible` | `strategies/numba_executor.py` | Constant allocation + constant withdrawal, horizon ≥ 1, dataset ≥ horizon, 2 holdings, one equity |
| `_is_escalating_eligible` | `strategies/numba_executor.py` | Constant allocation + escalating withdrawal, horizon ≥ 1, dataset ≥ horizon, 2 holdings, one equity, `v0 == initial_wealth` |
| `_is_buy_and_hold_eligible` | `strategies/numba_executor.py` | Buy-and-hold + fixed-real, horizon ≥ 1, dataset ≥ horizon, 2 holdings, one equity, `v0 == initial_wealth`, fee ∈ {None, 0} |
| `_is_glidepath_eligible` | `strategies/numba_executor.py` | Glidepath + fixed-real, 2 holdings, one equity, `v0 == initial_wealth` |
| `is_part52_eligible` | `strategies/part52_numba_executor.py` | Constant allocation + Part 52 withdrawal, 2 holdings, one equity, interest-rate source, supported additive fee |
| `is_part49_eligible` | `strategies/part49_numba_executor.py` | Part 49 withdrawal, 2 assets, monthly frequency, supported fee, debt/LTV fields |
| `is_part49_buy_and_hold_eligible` | `strategies/part49_buy_and_hold_numba_executor.py` | Buy-and-hold + Part 49 withdrawal, 2 assets, zero fee, debt/LTV fields |

**Multi-asset status:** explicit N-asset allocations are supported by the
generic fixed-real family. Constant-nominal, escalating, and Part 52 retain the
two-asset form; explicit multi-asset configurations are rejected rather than
routed to another engine.

---

## 3. Capability and Migration Matrix

Classification key:
**1** = already supported by Numba; **2** = partially supported;
**3** = not supported; **4** = fundamentally specialized (needs design);
**5** = obsolete/redundant.

| # | Capability | Current implementation (file:symbol) | Class | Numba support / fallback | Gap | Required migration | Tests / consumers | Blockers | Acceptance criteria |
|---|------------|--------------------------------------|:----:|--------------------------|-----|--------------------|-------------------|----------|---------------------|
| 1 | Fixed-real withdrawals (workbook SCR) | `concrete.py:121` `FixedRealWithdrawalPolicy` | 1 | `_simulate_trajectory_end_of_period` (`numba_kernel.py:104`), `_compute_workbook_scr` (`:63`), `_evaluate_workbook_scr_path` (`fast_path.py:502`), `_process_static_group` (`numba_executor.py:908`) | None for summary stats | None | `tests/unit/execution/test_fast_path.py`, Part20 tests | None | SCR-based success matches workbook SCR formula; end-of-period trajectory matches workbook timing |
| 2 | Constant nominal withdrawals | `concrete.py:85` `ConstantWithdrawalPolicy`; `_simulate_trajectory_constant_nominal` (`numba_kernel.py:204`) | 1 | Numba value-scaled recurrence `V_{m+1}=V_m*(1-rate/12)*g_m` (B2) | Glidepath + constant-nominal not eligible | None for `ConstantAllocationPolicy` | `tests/unit/execution/test_backend_strategy_matrix.py`; generic studies | Additive fee convention (B1) | Recurrence test + differential vs legacy (fee = 0) |
| 3 | Constant allocation weights | `concrete.py:23` `ConstantAllocationPolicy` | 1 | `_weights_by_class` (`fast_path.py:209`) | Fixed-real: legacy two-asset form and explicit N-asset `allocations` (B5); other withdrawal policies retain the legacy two-asset form | None for fixed-real | ERN grid, Part 19/20 | Legacy scalar form exposes only `equity_allocation`; explicit `allocations` covers fixed-real | Covered for legacy 2-asset and explicit N-asset fixed-real (B5) |
| 4 | Time-varying weights / glidepaths (dynamic, not in workbook) | `glidepath.py` `GlidepathAllocationPolicy` | 2 | `_is_glidepath_eligible` (`numba_executor.py:239`), `_compute_equity_weight_sequence` (`:465`), `compute_growth_factors_varying_weights_batch` (`numba_kernel.py:946`) | **Not adapted to workbook methodology**; uses legacy beginning-of-period recurrence with multiplicative fee. D1 timeline materialization and the D3 deterministic adapter do not close this gap | Document coherent extension spec; implement workbook-aligned timing/fee for glidepaths | Part 19/20 (`research/part19_*`, `part20_*`) | Workbook does not implement glidepaths; extension must be designed. **OPEN** | Static workbook fidelity complete; **glidepath fidelity NOT STARTED; specification still missing** |
| 5 | Two-asset portfolios | `fast_path.py:188`, `numba_executor.py:186` | 1 | All Numba kernels | None | None | ERN workloads | None | Already covered |
| 6 | Multi-asset portfolios (3+) | `concrete.py` `ConstantAllocationPolicy.allocations`; `fast_path.py:209` `_weights_by_class` | 1 | Growth-factor helper is N-asset; `_weights_by_class` resolves per-class weights via `resolve_target_weights` (B5) | None for constant fixed-real; nominal/escalating/Part 52 gate to the legacy form | **COMPLETE** (B5) | `tests/unit/domain/test_multi_asset_allocation.py`, `tests/unit/strategies/test_multi_asset_allocation.py` | Deferred withdrawal policies fall back for explicit allocations | Independent N-asset Decimal oracle + differential test on 3 assets pass |
| 7 | Expense ratios / fee application (workbook additive) | `expense_deduction_step.py` `ExpenseDeductionStep` | 1 | Workbook SCR formula uses additive fee in returns: `weighted_return - fee/12`; growth factors computed with fee embedded; end-of-period trajectory in `numba_kernel.py:104` and `fast_path.py:466` | Fee model aligned with workbook for static allocations and Part 52 (C2); Part 49 fee semantics pending | **COMPLETE** (implemented in workbook SCR path and Part 52 kernel) | `ern_grid.yaml` sets `expense_ratio: 0.0005`; Part20 tests updated; Part 52 B1 tests | Fee model differs by study (Part 49 legacy vs Part 52/workbook additive) | Static allocation + Part 52: workbook additive fee validated; Dynamic glidepaths: pending |
| 8 | Debt state + loan drawdown | `loan_draw_step.py` `LoanDrawStep`; `part49_withdrawal.py`, `part52_withdrawal.py` | 2 | Part52 kernel `_simulate_part52` (`numba_kernel.py:1559`) tracks `Y`, draws | Part 49 leverage (`Part49WithdrawalPolicy`) not eligible | Generalize debt kernel or add Part 49 eligibility | `tests/integration/test_part52_*`, Part 49 debt tests | Requires `interest_rate_schedule` for Part52 | Part 52 + Part 49 leverage E2E pass |
| 9 | Repay at fresh ATH | `loan_repayment_step.py` `LoanRepaymentStep` | 1 | `_simulate_part52` repay branch (`numba_kernel.py:1559`, loan-repayment step) | None for Part52 | None | `test_part52_compound_drawdown.py` | None | Part 52 E2E pass |
| 10 | Floating-rate interest (FFR) | `interest_accrual_step.py` `InterestAccrualStep` | 1 | `_compute_monthly_rates` (`part52_numba_executor.py:157`) | None for Part52 | None | `test_part52_ffr_floating_rate.py` | None | Part 52 FFR test pass |
| 11 | LTV evaluation / enforcement | `ltv_evaluation_step.py` `LTVEvaluationStep` | 1 | `_simulate_part52` LTV branch (`numba_kernel.py:1559`, LTV-evaluation step) | None for Part52 | None | `test_part52_*`, Part 49 | None | Part 52/49 LTV tests pass |
| 12 | Horizon derivation | `reference.py:330`, `fast_path.py:783`, `numba_executor.py:278`, `part52_numba_executor.py:228` | 1 | Present in all executors | None | Remove the legacy-only copy once `ReferenceSimulationExecutor` is deleted | `test_fast_path.py::test_executor_shares_longest_path` | None | Derivation report matches direct evaluation |
| 13 | FV target deduplication | `reference.py:206`, `fast_path.py:470`, `numba_executor.py:708` | 1 | Present in all executors | None | None | `test_trajectory_deduplication.py` | None | Per-target classification preserved |
| 14 | Cohort + slice execution | `execution/slicing.py` `iter_cohort_slices`; `execution/__init__.py` `iter_execute_study_plan`; `reference.py:428` `_slice_plan_units` | 2 | Lazy cohort-aligned slices for the unified Numba path; whole-plan `execute_study_plan` guarded; SQLite streaming writer consumes CLI slices | Legacy `execute_reference` slice dispatch remains separate | Retire legacy slice dispatch | `test_plan_slicing.py`, `test_streaming_execution.py`, `test_memory_bounded_execution.py`, `test_streaming_persistence.py` | Slice target is not a hard bound; consumers must release slices | Slice == whole-plan equality across backends; per-slice failure metadata |
| 15 | Deterministic execution | `execution/deterministic.py` `execute_deterministic_trajectory`; `execution/strategies/deterministic_kernel.py` | 4 | Dedicated two-asset unit-tracking Numba kernel (D3): annual/monthly rebalance, intra-year drift, additive fee, annual/monthly withdrawals, failure signalling; unsupported fee-free configurations fall back to the legacy pipeline and fee > 0 raises | None for supported two-asset policies | None | `tests/unit/execution/test_deterministic.py`, `test_deterministic_kernel.py`, `tests/unit/research/test_part20_experiment_e.py` | Multi-asset, Part 49/52, and buy-and-hold are unsupported by the deterministic kernel; fee > 0 raises rather than using the legacy stale-base fee | Deterministic result contract preserved; independent Decimal differential; corrected Experiment E values pinned |
| 16 | Full monthly trajectory | `monthly_result_builder_step.py` `MonthlyResultBuilderStep`; `execution/strategies/trajectory.py` | 3 | Numba executors emit optional `SimulationTimeline` (D1, 46687ce) | Reference/pipeline paths remain separate; materialization at grid scale needs D2 streaming | Keep materialization opt-in; consume through streaming slices | `test_timeline_materialization.py` | Memory/IPC cost; per-month portfolio reconstruction | Trajectory equals legacy month-by-month on a representative case |
| 17 | Result persistence | `persistence/studies/sqlite/codecs.py`; `sqlite_repository.py`; `run_command.py` | 3 | Schema v4 incremental writer: per-slice transactions, attempt tokens, explicit status, completion verification; completed-result readers filter incomplete executions; CLI streams persisted runs and appends each slice | No automatic age-based recovery | Document operational recovery | `test_streaming_persistence.py`, `test_sqlite_persistence.py`, `test_schema_migration.py` | #16, #18 | Save/load round-trip preserves statistics and timelines; interrupted runs are invisible until explicitly completed |
| 18 | Memory-bounded large grids | `execution/slicing.py`, `execution/__init__.py`; legacy `reference.py:_MAX_UNITS_PER_WORKER`, `_DEFAULT_SLICE_COHORTS` | 2 | Streaming API bounds residency by slice target; streaming persistence measured at ~284–289 MiB for 200–400 materialized units | Full 313k-unit grid benchmark not yet validated | Validate full grid | `tests/benchmarks/test_memory_bounded_execution.py` | #14, #16 | Peak RSS within documented host budget on 313k units |
| 19 | Buy-and-hold allocation | `concrete.py:49` `BuyAndHoldAllocationPolicy`; `_simulate_trajectory_buy_and_hold` (`numba_kernel.py:441`); `_is_buy_and_hold_eligible` (`numba_executor.py:267`) | 1 | Numba unit-tracking kernel (B4); weights drift endogenously | Non-zero fee, multi-asset, and Part 49 leverage fall back (see #6 and C4) | None for fee = 0, two assets | `tests/unit/strategies/test_numba_buy_and_hold.py`, `test_part49_buy_and_hold.py` | Non-zero-fee legacy `ExpenseDeductionStep` stale base (`TODO.md`) | Two-asset, fee = 0 differential vs legacy pipeline passes |
| 20 | Escalating withdrawal | `escalating_withdrawal.py` `EscalatingWithdrawalPolicy` | 2 | `_simulate_trajectory_escalating` (`numba_kernel.py`), `_process_escalating_group` (`numba_executor.py`) for `ConstantAllocationPolicy`; deterministic adapter supports constant allocation and annual glidepath through D3 | Glidepath + escalating is not yet eligible in the general Numba executor; the deterministic adapter supports it | Extend general eligibility to `GlidepathAllocationPolicy` | `tests/unit/strategies/test_numba_escalating.py`, `tests/unit/execution/test_deterministic_kernel.py` | General glidepath cadence and the deterministic-trajectory contract are separate migration items | Constant-allocation escalating matches the legacy pipeline (fee = 0) and an independent Decimal recurrence; deterministic annual glidepath + escalating matches the Decimal reference |
| 21 | Supplemental cash flow | `supplemental_cash_flow_step.py` | 3 | None (inactive by default) | Additional external cash flow | Add once a real consumer activates it | None active today | No active consumer | Only migrate if a consumer exists |
| 22 | CAPE-regime aggregation | `research/part20_*`, `cape_aggregation.py`, `cape_regime.py` | 4 | None | Regime classification layer | Keep as a post-processing layer over Numba results | Part 20 (`part20_pipeline.py`) | Aggregation, not simulation | Part 20 E2E pass |
| 23 | `ReferenceSimulationExecutor` wrapper | `reference.py:217` | 5 | Redundant (derivation already in `FastPathSimulationExecutor`) | — | Delete after migrations | `test_reference.py`, `test_determinism.py` | Public export `execute_reference` | No production consumer; resolve in D5b/D4.3 |
| 24 | `execute_reference()` public API | `reference.py:360` | 5 | Redundant | — | Redirect/delete | `test_reference.py::TestSliceDispatchMemorySafety` | Public export | No production consumer; resolve in D5b/D4.3 |
| 25 | `ExpenseDeductionStep` | `expense_deduction_step.py` | 4 | Not used by Numba; Part 52 Numba path uses the additive workbook fee (B1/C2); Part 49 still uses the legacy fee convention | Different fee model from canonical workbook | Preserve until every legacy-pipeline consumer is migrated | `test_part49_buy_and_hold.py:108` | Part 49 fee semantics | Only delete when no pipeline consumer remains |

---

## 4. Ordered Migration Phases

### Phase A — Routing Fixes, Test Coverage, and CLI Repair

Goal: fix routing bugs, establish genuine Numba test coverage, repair the CLI
default execution path, and document the verified consumers of legacy symbols.
**Do not delete `ReferenceSimulationExecutor`, `execute_reference()`, or public
exports in this phase.** Their unique responsibilities (cohort-slice dispatch
for memory safety, report construction) must be migrated first.

Work items:

1. **A1 — CLI execution routing. ⚠️ Partial.**
   CLI commit `8d142d3` added the missing default `research_result` branch for
   non-Part3, non-flagged execution, so default execution no longer falls
   through. However, `--reference` is parsed but ignored and still routes as
   AUTO, `--fast-path` selects the Decimal `FastPathSimulationExecutor`, and
   `compare`/`optimize` still use the legacy runners. Full flag and backend
   resolution, including tests that no longer assert AUTO for `--reference`, is
   **D5a**, not Phase A. Do not describe the CLI as unified before D5a.

2. **A2 — Establish genuine Part 52 Numba test coverage.**
   Current Part 52 integration tests (`test_part52_compound_drawdown.py`,
   `test_part52_ffr_floating_rate.py`, `test_part52_numerical_trace.py`) all
   use `create_default_pipeline()` directly, bypassing `Part52NumbaExecutor`.
   Add tests that instantiate `Part52NumbaExecutor` and verify eligible
   configurations execute **without** invoking the fallback. Test expense
   ratios, FFR schedules, loan draw/repay ordering, LTV enforcement, terminal
   failure states, and boundary conditions.

3. **A3 — Document verified consumers of legacy symbols (completed in §1.3).**
   No deletions. Consumers were traced for `ExecutionBackend.REFERENCE`,
   `ReferenceSimulationExecutor`, `execute_reference()`,
   `expected_reference_report`, and `reference_month_work`; D5b subsequently
   canonicalized the enum and removed the legacy reporting exports from the
   public facade.

4. **A4 — Keep obsolete equivalence tests deleted** (already done).

5. **A5 — Keep `parallel_executor._create_default_simulation_executor()`**
   until Phase D; it remains the fallback for `NumbaSimulationExecutor`,
   `FastPathSimulationExecutor`, `ReferenceSimulationExecutor`, and the
   deterministic legacy path. The dedicated Part 49/52 executors no longer use
   it after D4.1.

Phase A gate (reconciled):
- CLI routing is complete. D5a (CLI commit `3181bf5`) removed the legacy flags
  and routed `run`/`compare`/`optimize`/Part 3 through explicit FAST with a
  mandatory `fbf-core[numba]` dependency. **A1 is complete.**
- Part 52 has tests proving `Part52NumbaExecutor` executes eligible workloads
  without fallback.
- No production consumer imports `ReferenceSimulationExecutor` or
  `execute_reference()` **for new code**; existing test consumers documented.
- All eligible ERN workloads route through Numba/Decimal fast path.
- Remaining legacy fallback only used by genuinely unmigrated workloads.

### Phase B — Expand Numba's Generic Simulation Capabilities

Goal: grow the unified Numba engine to cover the generic (non-debt) workload
classes so they stop using the legacy fallback.

Work items (each independently testable):

1. **B1 — Non-zero expense ratio (additive fee).** ✅ Implemented for static
   allocations and Part 52. Additive fee is embedded in the growth factors
   (`g_m' = g_m - fee/12`, matching the workbook's `1 + r - f/12`), not the
   multiplicative form. See the B1 milestone below. Glidepath fee alignment is
   tracked under capability #4.

2. **B2 — Constant nominal withdrawal.** ✅ Implemented for
   `ConstantAllocationPolicy`: value-scaled recurrence
   `V_{m+1} = V_m * (1 - rate/12) * g_m`. Trace the domain model and execution
   order before extending to other allocation policies.

3. **B3 — Escalating withdrawal.** ✅ Implemented for
   `ConstantAllocationPolicy`: value-independent annual schedule
   `v0 * withdrawal_rate * (1 + escalation_rate) ** (m // 12)`. Glidepath +
   escalating remains future work in the general Numba executor; the
   deterministic adapter supports it through D3.

4. **B4 — Buy-and-hold.** ✅ Implemented: a non-rebalancing unit-tracking
   recurrence with explicit specification (a simulator extension — the workbook
   does not define buy-and-hold). See the B4 milestone below.

5. **B5 — Multi-asset portfolios.** ✅ Implemented (commit
   `85d72582f047279d5d9c42ca3f3cb0e3d9099c7b`): an explicit `allocations`
   mapping on `ConstantAllocationPolicy`, resolved through a single
   `resolve_target_weights` authority, with the fixed-real workbook path
   generalized to N assets. See capability #6.

Trajectory materialization and bounded-memory dispatch are **not** Phase B
items. They were previously listed here as B6/B7 and are consolidated into the
single Phase D milestones D1 (trajectory materialization) and D2 (cohort-slice
dispatch); there are no separate B6/B7 milestones.

Design rule: prefer extending the existing Numba executors and kernels over
creating new engines. The executors already share `_group_key`, `_index_series`,
`_weights_by_class`, `_apply_fv_check`, and growth-factor caching.

Phase B gate: every generic (non-debt) workload that currently falls back to the
legacy engine has either migrated to Numba with equivalent semantics or is
recorded as a deliberate specialized path. Large-grid memory and determinism
gates belong to Phase D (D1/D2).

### Phase C — Debt-Aware Workloads and Part 49/52 Migration

Goal: migrate Part 49, Part 52, and other debt-aware workloads to Numba.

Work items:

1. **C1 — Part 52 Numba-only execution.** ✅ Complete.
   Remove fallback from `Part52NumbaExecutor` for eligible configurations.
   Ineligible configurations (e.g. no interest-rate source — non-zero expense
   ratios are eligible under B1) fail with explicit `UnsupportedConfigurationError`.
   Do not silently fall back.

2. **C2 — Part 52 fee behavior (workbook additive).** ✅ Complete (B1):
   the additive fee is embedded in the Part 52 kernel growth factors as
   `g_m = Σ_j w_j · P_{j,m}/P_{j,m-1} − fee/12`, matching the workbook's
   `1 + r − f/12`. Validated by independent numerical checks
   (`TestPart52ExpenseRatioIndependentValidation`) plus the B1 audit tests.
   Glidepath fee alignment is tracked under capability #4.

3. **C3 — Part 49 debt (`loan_draw_rate`) migration.**
   ✅ Complete.
   Part 49 and Part 52 have different debt semantics (fixed draw rate vs
   drawdown-triggered, no ATH repayment). The dedicated Numba executor and
   kernel are implemented, including real-rate propagation, LTV terminal state,
   and differential tests against the Decimal/legacy path.

   **C3 closure evidence:** the 10,434-unit Part 49 full-path workload ran with
   `ExecutionBackend.FAST` and a patched `Part49NumbaExecutor.execute` call
   counter, proving the whole plan was handled by the Numba executor rather
   than the REFERENCE fallback. The non-leverage historical comparison
   against `p49_oracle_table.csv` passes (100% vs the pinned 100%), and
   leverage-directionality checks pass; the run recorded 10,431 successes
   and 3 failures out of 10,434 units. Production conformance is covered by
   the workbook-derived oracle, not by this historical comparison.

4. **C4 — Part 49 buy-and-hold migration.**
   ✅ Complete for the approved supported scope: Part 49 buy-and-hold,
   `BuyAndHoldAllocationPolicy`, two assets, and zero expense ratio. Acceptance
   uses approved Option B: independently verified production-path synthetic
   differential evidence against independent Decimal and legacy references,
   plus dispatch, eligibility, LTV terminal-state, and real-rate propagation
   tests. Non-zero fees, multi-asset portfolios, and unsupported configurations
   remain explicit fallback cases.

   **C4 closure is independent of C3.** The 10,434-unit constant-allocation
   Part 49 test does not exercise buy-and-hold and is unrelated to C4 closure.
   This C4 closure does not establish real-data canonical-scale buy-and-hold
   equivalence, 1,739-cohort coverage, or a canonical ERN buy-and-hold oracle.
   The decision and its limitations are recorded in the C4 acceptance decision
   below.

5. **C5 — LTV enforcement terminal state.** ✅ Complete.
   Add `failure_state="margin_call_terminal"` to Part 52/49 Numba kernels to
   match legacy `LTVEvaluationStep` behavior.

Phase C gate:
- Part 52 eligible configurations execute on Numba with no fallback. ✅
- Part 49 debt workloads execute on Numba. ✅ Complete; formal C3 gate
  satisfied below.
- LTV enforcement produces `margin_call_terminal` failure state. ✅
- All Part 52/49 integration tests pass on Numba executors. ✅
- **C3 gate:** 10,434-unit Part 49 full-path validation with proof that
  `Part49NumbaExecutor` was selected, plus non-leverage historical oracle
  checks and leverage-directionality checks. ✅
- **C4 gate:** approved Option B for the supported scope, independent of the
  C3 debt E2E. ✅
- C3 is closed by its 10,434-unit Numba-path gate. C4 is closed only for the
  approved supported scope; this does not imply real-data canonical-scale
  equivalence, 1,739-cohort coverage, or a canonical ERN buy-and-hold oracle.
  The existing 10,434-unit constant-allocation test is the C3 evidence; it does
  not close C4.

#### C4 acceptance decision (approved: Option B)

The existing C4 evidence consists of production-path dispatch tests,
independent Decimal-reference differentials, legacy-pipeline differentials,
eligibility tests, LTV terminal-state tests, and real-rate propagation tests
using synthetic datasets. There is no canonical ERN buy-and-hold oracle.
Buy-and-hold is a simulator extension, not a workbook-defined calculation.

| Option | Criterion | Consequences |
|--------|-----------|--------------|
| A | Require a real-data Part 49 buy-and-hold E2E or differential test at canonical scale. | Strongest integration and scale evidence: exercises the real dataset, configuration path, and 1,739-cohort regime. Adds a new test and a heavyweight authorized run. Because no canonical buy-and-hold oracle exists, this would validate production-path consistency and scale, not published-ERN numerical replication. It may duplicate mechanics already covered by synthetic differentials. |
| B | Accept the existing production-path synthetic differential evidence for the supported C4 scope, after independent verification, and record the limitation explicitly. **Approved.** | Reuses the dispatch, independent Decimal-reference, legacy-differential, LTV, and real-rate evidence. Faster and avoids a heavyweight run. Limitation: synthetic data rather than canonical history, not full 1,739-cohort scale, and no real-data buy-and-hold E2E. C4 closure is therefore scoped to the supported configuration and does not claim canonical-scale data coverage. |

**Decision: Option B approved on 2026-10-20.** Independent verification was
completed against the existing targeted C4 Numba-executor and production
debt-flow evidence. C4 is closed for the supported scope only.

**Explicit limitations.** This closure does not establish real-data canonical-
scale buy-and-hold equivalence, does not establish 1,739-cohort coverage, and
does not establish a canonical ERN buy-and-hold oracle. The evidence is
synthetic-data differential testing against independent Decimal and legacy
references, plus production-path dispatch, eligibility, LTV terminal-state,
and real-rate propagation tests. It covers only Part 49 buy-and-hold with two
assets and zero expense ratio. Non-zero fees, multi-asset portfolios, and
unsupported configurations remain fallback cases outside this closure.

**Rationale.** Buy-and-hold has no canonical ERN oracle, so a real-data E2E
would add integration and scale confidence but not canonical numerical
correctness. Option A remains available if real-data canonical-scale coverage
is required later; it is not part of this closure.

### Phase D — Trajectories, Memory, and Legacy Removal

Goal: implement trajectory materialization, bounded-memory dispatch, and
remove all legacy pipeline code.

Ordering: D2 (bounded-memory dispatch) is a hard prerequisite for enabling D1
(trajectory materialization) at grid scale. D1 may be developed concurrently
with D2, but timelines must not be materialized for the full ERN grid until D2
lands. This resolves the former B6/B7 ordering contradiction (trajectory
materialization consumed as much memory as it produced; bounded dispatch had to
exist first).

Work items:

1. **D1 — Monthly trajectory materialization.**
   Define `SimulationTimeline` contents (`portfolio`, `market_snapshot`,
   `debt_snapshot`). Add optional `materialize_timeline` flag to Numba
   executors. Implement in kernels with pre-allocated arrays. Gated on D2 at
   grid scale (see ordering above).

2. **D2 — Cohort-slice dispatch for bounded memory.**
   ✅ Complete; bounded-memory mechanics and the production
   aggregate-correctness regression are in place.
   Implemented `iter_cohort_slices` + `iter_execute_study_plan` with
   cohort-aligned, lazy slices and a 1,000-unit materialization guard on the
   whole-plan API. Default targets: 500 materialized, 20,000 summary.
   Part 52 consumes streaming slices; `Part49Aggregator` supports incremental
   aggregation. Schema v4 adds an incremental SQLite writer (`begin_execution`,
   `append_execution_slice`, `complete_execution`, `fail_execution`,
   `abandon_execution`) with attempt tokens and explicit status; interrupted
   executions are invisible to completed-result readers. The CLI streams
   persisted runs through the writer.

   **D2 closure gate:** execute the full 313,020-unit grid through
   `iter_execute_study_plan` with summary-only result handling, measure peak
   RSS against the documented host budget, and verify the streaming aggregate.
   The existing 313,020-unit whole-plan test is production-conformance
   evidence, not evidence that D2 streaming has passed. A routine
   production-subset regression must also compare streaming, whole-plan, and
   persisted/reloaded per-cell aggregates against the workbook oracle.

   **D2 validation evidence:** the 313,020-unit grid executed through
   `iter_execute_study_plan` in 16 summary-only slices (20,160-unit maximum),
   with all 180 cells reporting 1,739 outcomes. Peak RSS was 451.3 MiB on the
   REFERENCE path (22.9 MiB above the post-plan baseline) and 582.2 MiB on the
   FAST path, both below the 16 GB target. Streaming and whole-plan execution
   agree on every cell, including the 13 that diverge from the pinned published
   oracle, and both backends produce the same aggregate. **Separately tracked
   historical published-ERN oracle divergence (13 cells):** the 13/180 cells that differ from the pinned
   oracle by +1 pp are a methodology-conformance issue, not a streaming defect.
   Targeted independent calculations reproduce all 13
   cells exactly under the workbook convention: changing only the published
   oracle's T+1 withdrawal terms to the workbook's T terms reproduces all 13,
   while changing only the multiplicative fee to the workbook's additive fee
   reproduces one. The primary cause is therefore the documented T vs T+1
   cohort convention; the fee convention is secondary for one cell. Production
   aggregate verification is satisfied separately: the 313,020-unit production
   grid matches `workbook_oracle_table.csv` on all 180 cells with exact
   Decimal equality (FAST, 17s). The published-oracle 13-cell divergence is
   retained as a documented historical comparison, not a production failure.

   **D2 aggregate regression (committed in `9f00a89`):**
   `tests/oracle/ern/test_streaming_aggregate.py` streams a four-cell
   production subset across all 1,739 cohorts, persists and reloads it, and
   compares streaming, whole-plan, and persisted per-cell aggregates to
   `workbook_oracle_table.csv` with exact Decimal equality. It also verifies
   that incomplete attempts remain invisible and completed executions become
   visible. Before commit, the regression was validated against the current
   workspace and against an isolated worktree containing only `HEAD` plus this
   test; the focused test, Ruff, and strict mypy passed in both contexts. It is
   committed in `9f00a89`.

3. **D3 — Deterministic trajectory on Numba.** ✅ Implemented.
   `execute_deterministic_trajectory` now routes
   supported two-asset constant-allocation and glidepath trajectories through a
   dedicated unit-tracking kernel with trajectory output and checkpoint
   extraction.

   The kernel uses the workbook additive fee recurrence
   `V_t = V_{t-1} * (1 + g_t) - V_{t-1} * fee/12 - W_t`, with withdrawals and
   rebalances at the beginning of a period and no rebalancing between annual
   boundaries. Equity and bond units are tracked separately, so actual weights
   drift intra-year and are reported alongside the target weights.

   Corrected Experiment E values under this method (Year 2 / Year 10):

   | Case | p23 | p119 |
   |---|---:|---:|
   | Bear→Bull static 80% | 705,826.662664 | 1,023,204.206346 |
   | Bear→Bull glidepath 70→90% | 745,100.308079 | 1,095,209.593145 |
   | Bull→Bear static 80% | 1,086,802.382015 | 1,143,815.160996 |
   | Bull→Bear glidepath 70→90% | 1,072,649.456103 | 1,073,960.748019 |

   These are research-derived workbook-conformant outputs, not published ERN
   anchors. The published Experiment E values and allocations remain
   `UNEXPLAINED DIFFERENCE` historical references; no anchor was tuned or
   reclassified by this migration. Unsupported fee-free configurations fall
   back to the legacy Decimal pipeline; unsupported configurations with a
   non-zero fee raise `UnsupportedConfigurationError`.

4. **D4 — Legacy pipeline removal.**
   **D4.1 — Remove redundant reference hooks from dedicated Part 49/52
   executors. ✅ Committed in `01e4aeb` (Step B).**
   Removed the `_reference` field, `reference_executor` constructor parameter,
   and factory imports from `Part49NumbaExecutor`, `Part52NumbaExecutor`, and
   `Part49BuyAndHoldNumbaExecutor`. Ineligible configurations continue to raise
   `UnsupportedConfigurationError`; no legacy pipeline code was deleted.
   Focused tests assert the hooks are absent while retaining supported-execution
   and rejection coverage. Before commit, the exact D4.1-only patch was applied
   to an isolated `HEAD` worktree; the three focused integration suites, Ruff,
   and strict mypy passed, and no D4.2 or P1 changes were included.

   **D4.2a — Independent Part 49/52 debt-recurrence coverage. ✅ Committed in
   `ce2ec97` (Step C).** Added test-only Decimal
   recurrences in
   `tests/unit/execution/debt_recurrence_reference.py` and parallel differential
   tests for every Part 49 and Part 52 legacy debt scenario. The independent
   tests do not import the legacy pipeline, the production executors, or the
   Numba kernel. The legacy parity tests were retained during D4.2a as
   temporary secondary checks.

   **D4.2b — Remove redundant legacy debt differentials. ✅ Committed in
   `ce2ec97` (Step C).** Mapped every case in
   `TestPart49DecimalDifferential` and `TestPart52DecimalDifferential` to an
   independent replacement, preserved the unique assertions and hand-calculated
   anchors, then removed the 17 redundant tests and their two local legacy
   helpers. No production code, legacy executor, pipeline, factory, export, or
   oracle data was changed.

   **D4.2c — Part 49 buy-and-hold independent coverage. ✅ Committed in
   `ce2ec97` (Step C).** Mapped every case in
   `TestPart49BuyAndHoldLegacyDifferential` to independent Decimal coverage,
   then extended the independent recurrence to honour CPI-adjusted monthly
   rates, final-value targets, and enforcement-off scenarios. Added independent
   cases for the exact legacy constant-growth return pair at 50% equity,
   CPI-adjusted interest, enforcement off, and final-value-target pass/fail,
   plus a hand-calculated flat-market anchor. The
   legacy differential class remained in place at the end of D4.2c; no D4.2c
   deletion was performed or authorized. Separately inventoried the generic
   buy-and-hold and escalating legacy differentials without modifying them; see
   §7.1.3. Before commit, Steps B and C were validated as exact patches on
   isolated worktrees based on `HEAD` and `HEAD + Step A + Step B`,
   respectively; the affected Part 49/52 suites, Ruff, and strict mypy passed.
   They are committed in `01e4aeb` and `ce2ec97`, respectively.

   **D4.2d — Remaining legacy-dependency matrix. ✅ Complete; documentation
   record committed with this reconciliation.** Classified every remaining
   test-level legacy dependency into three groups: independent coverage exists,
   independent coverage is
   incomplete, or legacy-specific behavior. Produced a prioritized migration
   proposal covering the generic buy-and-hold/escalating differentials, internal
   reference/derived-horizon tests, pipeline parity, FV deduplication,
   determinism, backend-strategy summary-only coverage, multi-asset fallback,
   production-path Part 49/52 integration suites, debt-pipeline structure,
   oracle/benchmark/tool consumers, and Part 42. No test, production file,
   oracle, or expected value was changed. See §7.1.4.

   **D4.2e — Exact P1 deletion proposal. ✅ Complete; documentation record
   committed with this reconciliation.** Reviewed the mapped Part 49
   buy-and-hold, generic
   buy-and-hold, and escalating differentials and proposed exact deletion
   scopes. No file was changed in D4.2e.

   **D4.2f — P1 differential cleanup. ✅ Committed in `1882d22` (Step D).**
   Removed the 10-case Part 49 buy-and-hold
   legacy differential and the four generic buy-and-hold legacy-only cases. Split the mixed generic
   buy-and-hold tests so the independent hand-derived anchors remained, renamed
   the remaining independent case, and removed the now-unused legacy
   setup/comparison code and imports. The generic buy-and-hold file no longer
   imports the legacy pipeline. Focused tests, the routine suite, contract
   tests, Ruff, and strict mypy passed. Before commit, the Step D cleanup patch
   was validated on the `HEAD + A + B + C` base; the affected integration/unit
   suites, Ruff, and strict mypy passed.

   **D4.2g — Escalating independent anchors. ✅ Committed in `1882d22`
   (Step D).** Added annual and monthly escalating recurrence
   cases using the exact legacy horizon and parameters, with independently
   calculated
   final-wealth anchors. Verified success, failure month, and final wealth
   against the test-only recurrence before using the anchors. Focused tests
   passed.

   **D4.2h — Escalating differential removal. ✅ Committed in `1882d22`
   (Step D).** Removed the two-case escalating legacy
   differential and the now-unused legacy pipeline/runner imports. The
   escalating test file is free of legacy-pipeline dependencies. Focused tests,
   the routine suite, contract tests, Ruff, and strict mypy passed. P1
   implementation is closed; the cleanup is committed in `1882d22`.

   **D4.2i — Remaining-work audit. ✅ Complete (read-only; documentation
   committed with this reconciliation).**
   Audited the working tree against the D4.2d matrix and §7.3. Verdict at audit
   time: P1 closed; P2–P4 still open, with P3.1–P3.5 subsequently closed during
   D4.2j; P5 deferred to the final deletion gate/D4.3.
   No file was changed. The audit also identified stale roadmap status,
   matrix/inventory rows, and escalating module/test docstrings.

   **D4.2j — Remaining D4.2 migration. ✅ P2/P3 committed in `35976b6`; P4
   committed in `c04c058`; D4.1/D4.2a–c/P1 committed in `01e4aeb`, `ce2ec97`,
   and `1882d22`; documentation reconciled in Step E.**
   Reconciled the roadmap
   with D4.2e–i and closed P2: replaced the multi-asset reference comparison
   with an independent constant-nominal recurrence and added plan-level Numba
   sequential-repeatability and process-parallel/sequential equivalence. P3.1
   retargeted the four Part 49 production-path suites to
   `Part49NumbaExecutor(materialize_timeline=True)`, replacing the custom test
   withdrawal policy with the production Part 49 policy and preserving debt
   timeline, aggregation, LTV, zero-interest, and terminal-state coverage.
   P3.2 retargeted the Part 52 compound-drawdown, FFR-schedule, and numerical
   trace suites to `Part52NumbaExecutor(materialize_timeline=True)`, preserving
   borrow/repay, per-month interest, fixed-rate fallback, and exact trace
   assertions with float-materialization tolerances. P3.3 retargeted the
   multi-cohort, Part 49 multi-cohort, CLI-plan, and glidepath suites to the
   Numba executors, preserving cohort isolation, process-boundary
   serialization, parallel/sequential equivalence, and glidepath target
   trajectories. P3.4 retargeted the research-layer debt flow tests to
   `Part49NumbaExecutor(materialize_timeline=True)`, preserving debt-parameter
   translation, real/nominal rate propagation, and end-to-end debt timelines.
   P3.5 replaced the broad legacy differential with an independent Decimal
   beginning-of-period recurrence while retaining the edge-case and randomized
   matrix. P4.1 retargeted the FV-target deduplication suite to
   `NumbaSimulationExecutor`, asserting one trajectory group for distinct FV
   targets, one shared final wealth, and per-target success classification.
   P4.2 removed the legacy pipeline-parity suite: its structural step-order
   assertions describe legacy internals with no supported-engine analogue, and
   its behavioral parity contract is already covered by P2.2 and P3.3. P2–P4
   are closed at implementation level. The P2/P3, P4, D4.1, D4.2a–c, and P1
   changes have dedicated commits. With this documentation reconciliation,
   D4.2 is complete.
   The final read-only exit audit found no remaining D4.2-level legacy
   dependency in the migrated suites. Remaining legacy consumers are confined
   to the P5-deferred groups: reference/derived-horizon internals, legacy
   pipeline unit suites, structural debt/schedule tests, summary-only
   equivalence, oracle/benchmark/tool consumers, Part 42, and the active
   production fallbacks. Fast-path-specific suites remain a D5b/D4.3 decision,
   not a D4.2 dependency. P5 and D4.3 legacy-engine deletion are out of scope.
   See §7.1.5 for exit criteria and the D4.2/D4.3 boundary.

   **D4.3 — Legacy-engine deletion. ✅ Complete.** Deleted the legacy execution
   stack: `_create_default_simulation_executor()`, `create_default_pipeline()`,
   `create_buy_and_hold_pipeline()`, `ExpenseDeductionStep` and all pipeline
   steps, `ReferenceSimulationExecutor`, `execute_reference()`,
   `expected_reference_report`, `reference_month_work`,
   `FastPathSimulationExecutor`, the remaining fallback hooks in
   `NumbaSimulationExecutor`, and the deterministic legacy path. Also deleted
   the `DECIMAL_FAST_PATH`/`REFERENCE` backend values, making
   `ExecutionBackend.FAST` the sole backend. Unsupported workloads now fail
   explicitly; no production path selects another engine. Core was bumped to
   `0.3.0` and CLI/UI pins and routing were updated. See §2 for the resulting
   architecture.

5. **D5 — Public API resolution and consumer convergence.**
   D5 is split into two independently reviewable milestones.

   **D5a — CLI single-engine routing. ✅ Complete (CLI commit `3181bf5`).**
   Make Numba a mandatory `fbf-cli` runtime dependency through
   `fbf-core[numba]`. Set explicit `ExecutionBackend.FAST` for `run`,
   `compare`, `optimize`, and Part 3. Remove `--reference`, `--fast-path`, and
   `--validate` from the CLI execution surface rather than retaining no-op or
   misleading options. Route Part 3 through the Tier 2 `fbf.core.research`
   facade (`execute_part3_pipeline`, planner types) instead of Tier 3
   submodules. Replace direct `sequential_execute`/`parallel_execute` calls in
   `compare` and `optimize` with `execute_study_plan` using explicit FAST.
   Materialize timelines only where a command's output or persistence contract
   requires them; keep compare/optimize persistence summary-only if that is the
   existing contract. Unsupported configurations and a missing Numba raise
   explicit errors with no fallback to FastPath or the legacy engine.
   `--workers` must not be silently ignored: reject unsupported parallel
   execution with a clear message unless the documented contract defines it as
   a hint. Preserve existing output and persistence contracts except for the
   approved flag-removal break. D5a does not delete core legacy code, change fee
   semantics, or expand kernel eligibility.

   **D5b — Core backend semantics and legacy public surface. ✅ Complete.**
   Decide and implement `ExecutionBackend.REFERENCE` rename/alias/removal
   (breaking; Core minor version bump) and remove legacy public exports
   (`execute_reference`, `expected_reference_report`, `reference_month_work`
   where no longer required) after all consumer pins are updated. D5b is
   coordinated with D4.3 legacy deletion. Until D4.3, core AUTO dispatch retains
   its legacy fallback; after D5a the CLI does not rely on that fallback.

Phase D gate (Final Deletion Gate):
- All capabilities in §3 migrated or explicitly retained.
- Workbook fidelity for static allocations validated.
- Dynamic glidepath extension specification documented.
- Zero production references to legacy symbols.
- D5b complete: `ExecutionBackend.DECIMAL_FAST_PATH` canonicalized with
  `REFERENCE` retained as a deprecated same-value alias; Core minor version
  bumped; legacy reporting exports removed from the facade; consumer pins
  updated.
- D5a complete: CLI requires Numba, routes `run`/`compare`/`optimize`/Part 3
  through explicit FAST with no selectable legacy/FastPath mode, and has no
  silent fallback.
- Production ERN grids match the workbook-derived oracle; the historical
  published-ERN oracle remains a separate target; all E2E tests pass.
- Phase C closure gates satisfied: C3 10,434-unit Numba-path validation with
  executor-selection proof; C4 approved Option B supported-scope closure.
- D2 full-grid streaming memory, streaming-equivalence, and production
  aggregate gates satisfied: 313,020 units through `iter_execute_study_plan`,
  summary-only handling, 451.3 MiB peak RSS (REFERENCE) under the 16 GB target,
  streaming agreement with whole-plan execution, and 180/180 exact equality
  against the workbook-derived production oracle. The published-ERN oracle
  remains a separate historical target. The existing REFERENCE-backend
  whole-plan full-grid test does not satisfy the streaming gate.
- Large-grid execution within memory budget.
- Quality gates pass: `ruff check .`, `mypy --strict .`, full test suite.
- Both oracle tools are unchanged and independently regenerate their tables.

---

## 5. Correctness and Validation Contracts

### 5.1 ERN correctness targets

The published-ERN replication and workbook-conformant production are separate
targets with different historical boundaries, forward assumptions, and fee
conventions. They must not be compared to each other's oracle.

```
Published ERN historical replication
  → tools/ern/reference_oracle.py
  → data/ern/p49_oracle_table.csv (pinned)

Workbook-conformant production
  → tools/ern/workbook_oracle.py
  → data/ern/workbook_oracle_table.csv (pinned)
  → canonical production dataset
```

The production contract is **reproduction of the Excel workbook methodology**,
not bit-exact equality with the legacy engine or with published-ERN results.
The workbook uses an **additive fee embedded in monthly returns**
(`weighted_return - fee/12`) and **beginning-of-month withdrawals** (withdraw
first, then grow). The published-ERN oracle uses a multiplicative fee but the
same beginning-of-month withdrawal ordering.

**Limitation (workbook target):** The expected values for the workbook
acceptance case were read from the workbook's pre-calculated saved values.
Fresh recalculation in Excel or LibreOffice was not completed (LibreOffice
headless timed out). The validation is against the workbook's saved cached
results, not a fresh recalculation.

### 5.2 Non-ERN workload correctness

Each specialized workload preserves its own semantics:

- **Part 52** — timing leverage, drawdown-triggered borrowing, repayment at
  fresh ATH, FFR interest, LTV enforcement. Its fee/ordering convention is
  that of its own reference and anchors, not the Part 49 workbook.
- **Part 49 (debt)** — `loan_draw_rate` leverage semantics.
- **Part 19/20** — glidepath weight sequences and CAPE aggregation.
- **Buy-and-hold** — no periodic rebalancing.
- **Deterministic trajectory** — checkpoint contract.

Where no independent oracle exists (e.g. Part 52 without a pinned cell table,
Part 49 debt), document the behavioral contract from the existing golden tests
and pipeline-level tests **before** treating the Numba migration as verified.
`tools/ern/reference_oracle.py` is the published-ERN oracle and
`tools/ern/workbook_oracle.py` is the workbook-conformance oracle. Both are
independent of production code and must not be imported by it.

### 5.3 Test classification

| Class | Meaning | Action |
|-------|---------|--------|
| Historical published-ERN replication | Reference oracle vs `p49_oracle_table.csv` | Keep; separate historical target |
| Workbook conformance (production) | Production grid vs `data/ern/workbook_oracle_table.csv` | Keep; production acceptance target |
| Behavioral contract | Part 52/49 debt mechanics, glidepath, deterministic checkpoints | Keep; migrate to run on Numba |
| Determinism | Repeated runs identical; parallel == sequential | Keep |
| Routing | AUTO selects expected executor; backend × strategy matrix | Keep, but fix names once §1.3 is resolved |
| Obsolete implementation equivalence | `FAST == legacy Reference` where methodologies differ | **DELETED** in Phase A (§7.3) |

---

## 6. Dependencies, Risks, and Unresolved Questions

### 6.1 Dependencies

- Numba remains an optional core dependency (`fbf-core[numba]`), and core AUTO
  dispatch retains its legacy fallback until D4.3. **Decision recorded for the
  CLI (D5a): the CLI requires Numba through `fbf-core[numba]` and uses explicit
  FAST, so a missing Numba fails instead of falling back.** Whether core retains
  a pure-Python fallback after D4.3 remains a D4.3/D5b decision.
- Full trajectories (#16) block persistence (#17), debt aggregation, and
  deterministic execution.
- Slice dispatch (#14/D2) blocks memory-bounded execution once #16 lands.

### 6.2 Risks

1. **Fee-model divergence.** The legacy `ExpenseDeductionStep` uses a linear
   approximation with a timing correction; the canonical workbook uses an
   **additive fee embedded in returns** (`weighted_return - fee/12`). The
   `reference_oracle.py` uses multiplicative fees (its own methodology).
   Migrating fee support (B1) must follow the *study's* required model, not
   a single global rule. **Note**: The workbook's additive fee convention has
   been implemented in the workbook SCR path (B1 COMPLETE for static
   allocations).
2. **Methodology drift.** Forcing Part 52 onto the Part 49 recurrence would
   silently change results. Preserve per-study semantics.
3. **Trajectory payload size.** Materializing timelines for 313k units is
   enormous (~0.37 MiB/unit per the legacy notes in `reference.py:419`); D2 is
   a hard prerequisite for persistence at grid scale.
4. **Public API breakage.** D5b removed the legacy reporting exports and
   canonicalized `DECIMAL_FAST_PATH` while retaining `REFERENCE` as a
   same-value alias; Core was bumped to `0.2.0` and consumer pins updated.
   Removing the alias and the legacy implementations remains a future breaking
   change coordinated with D4.3.
5. **CLI routing ambiguity — resolved by D5a.** The legacy `--reference`,
   `--fast-path`, and `--validate` flags were removed; `run`, `compare`,
   `optimize`, and Part 3 use explicit FAST and require `fbf-core[numba]`.
   Core AUTO retains its legacy fallback until D4.3.

### 6.3 Unresolved questions (require human decision)

1. Numba dependency: **resolved for the CLI by D5a** (mandatory through
   `fbf-core[numba]`, explicit FAST, no fallback). Core keeps AUTO fallback
   until D4.3; whether core retains a pure-Python fallback after D4.3 remains
   open.
2. Should `ExecutionBackend.REFERENCE` be renamed, aliased, or removed?
   **Resolved by D5b:** canonicalized as `DECIMAL_FAST_PATH`; `REFERENCE` is a
   deprecated same-value alias through `0.2.x`; removal deferred.
3. Does any external consumer depend on `execute_reference` /
   `expected_reference_report` as public API?
4. Is `execution/deterministic.py` to be reimplemented on Numba, or retained as
   a specialized trajectory feature?
5. What is the authoritative behavioral oracle for Part 52 and debt-aware
   Part 49 if no pinned cell table exists?
6. What is the intended default CLI execution path? **Resolved by D5a:**
   explicit FAST for all execution commands.

---

## 7. File- and Symbol-Level Migration Inventory

### 7.1 Production files to modify or delete

| File | Symbols | Phase | Action |
|------|---------|:-----:|--------|
| `src/fbf/core/execution/strategies/reference.py` | `ReferenceSimulationExecutor`, `execute_reference`, `_slice_plan_units`, `_build_derived_result`, `expected_reference_report` compatibility re-export | D | Delete after slice dispatch ported (D2); report implementation lives in `execution/reporting.py` |
| `src/fbf/core/execution/reporting.py` | `ReferenceReport`, `expected_reference_report`, `reference_month_work` | — | Retain as the pure plan-reporting module; no executor imports |
| `src/fbf/core/execution/strategies/workbook_scr.py` | `compute_workbook_growth_factors`, `compute_workbook_scr`, `workbook_scr_success` | B | **COMPLETE** — workbook SCR core implementation |
| `src/fbf/core/execution/__init__.py` | Legacy reporting exports removed from the facade and `__all__` (D5b); backend enum canonicalized as `DECIMAL_FAST_PATH` with `REFERENCE` alias | D5b (done) | Implementations remain in `execution/reporting.py` and `execution/strategies/reference.py` until D4.3 |
| `src/fbf/core/execution/strategies/parallel_executor.py` | `_create_default_simulation_executor` (`:43`) | D | Delete after all fallbacks removed (Phase D4) |
| `src/fbf/core/execution/pipeline/default_pipeline.py` | `create_default_pipeline`, `create_buy_and_hold_pipeline` | D | Delete after all pipeline consumers migrated (Phase D4) |
| `src/fbf/core/execution/pipeline/steps/expense_deduction_step.py` | `ExpenseDeductionStep` | C/D | Migrate fee to Numba (B1); delete in Phase D4 |
| `src/fbf/core/execution/strategies/fast_path.py` | `FastPathSimulationExecutor`, `self._reference` (`:1087`), `_use_workbook_scr`, `_evaluate_workbook_scr_path`, `evaluate_closed_form` | C/D | **Workbook SCR COMPLETE**; D5a removes it as a selectable CLI execution mode; core retention or deletion is a D4.3/D5b decision |
| `src/fbf/core/execution/strategies/numba_executor.py` | `NumbaSimulationExecutor`, `is_numba_context_eligible`, `self._reference`, `_use_workbook_scr`, `_process_static_group` | B/C/D | **Workbook SCR COMPLETE**; nominal/escalating/buy-and-hold complete (B2/B3/B4); multi-asset (B5); default fallback remains for AUTO, while explicit FAST rejects unsupported contexts |
| `src/fbf/core/execution/strategies/part49_numba_executor.py` | `Part49NumbaExecutor` | D4.1 | Removed `_reference` / `reference_executor`; ineligible configurations raise `UnsupportedConfigurationError` |
| `src/fbf/core/execution/strategies/part52_numba_executor.py` | `Part52NumbaExecutor` | D4.1 | Removed `_reference` / `reference_executor`; ineligible configurations raise `UnsupportedConfigurationError`; expense ratio supported (B1/C2) |
| `src/fbf/core/execution/strategies/part49_buy_and_hold_numba_executor.py` | `Part49BuyAndHoldNumbaExecutor` | D4.1 | Removed `_reference` / `reference_executor`; ineligible configurations raise `UnsupportedConfigurationError` |
| `src/fbf/core/execution/strategies/numba_kernel.py` | `_simulate_trajectory`, `_simulate_trajectory_end_of_period`, `_simulate_trajectory_varying`, `_compute_workbook_scr`, `_simulate_part52` | B/C/D | **Workbook SCR COMPLETE**; nominal/escalating/buy-and-hold complete (B2/B3/B4); trajectories (D1); debt snapshots |
| `src/fbf/core/execution/deterministic.py` | `execute_deterministic_trajectory`, `_execute_legacy_deterministic` | D | Numba kernel implemented (D3); legacy fee-free fallback remains |

### 7.1.1 Reference-hook and legacy-consumer inventory after D4.1

**1. Reference hooks removed in D4.1 (committed in `01e4aeb`; validated on an isolated `HEAD` base before commit):**

- `Part49NumbaExecutor` — `_reference`, `reference_executor`, and
  `_create_default_simulation_executor` import removed.
- `Part52NumbaExecutor` — `_reference`, `reference_executor`, and
  `_create_default_simulation_executor` import removed.
- `Part49BuyAndHoldNumbaExecutor` — `_reference`, `reference_executor`, and
  `_create_reference_simulation_executor` import removed.
- Ineligible configurations in all three raise
  `UnsupportedConfigurationError`. Focused tests assert `_reference` is absent.

**2. Fallbacks still active outside D4.1:**

| Owner | Mechanism | Current behavior |
|-------|-----------|------------------|
| `NumbaSimulationExecutor` (default mode) | `self._reference` | Per-context legacy execution for ineligible contexts; explicit FAST disables this fallback and rejects the plan |
| `FastPathSimulationExecutor` | `self._reference` (`fast_path.py:1087`) | Batches ineligible contexts to the legacy engine |
| `ReferenceSimulationExecutor` | `self._reference` (`reference.py:227`) | Wraps the legacy engine and calls it per context |
| `execution/deterministic.py` | Direct `create_default_pipeline()` | Fee-free unsupported configurations use `_execute_legacy_deterministic()`; non-zero fee raises `UnsupportedConfigurationError` |

**3. Production consumers of the legacy pipeline:**

- `src/fbf/core/execution/__init__.py` — `DECIMAL_FAST_PATH` backend dispatch;
  legacy reporting exports removed by D5b (implementations retained).
- `src/fbf/core/execution/strategies/parallel_executor.py` —
  `_create_default_simulation_executor`, `_AllocationRoutedSimulationExecutor`,
  and default worker/executor construction.
- `src/fbf/core/execution/strategies/reference.py` — legacy executor wrapper,
  slice dispatch, and report construction.
- `src/fbf/core/execution/strategies/fast_path.py` — ineligible-context
  fallback.
- `src/fbf/core/execution/strategies/numba_executor.py` — ineligible-context
  fallback.
- `src/fbf/core/execution/deterministic.py` — fee-free deterministic fallback.
- `src/fbf/core/research/part42_plan.py:180` — imports and calls
  `create_default_pipeline`; the result is currently discarded, but the
  production import remains.
- `fbf-cli/src/fbf/cli/commands/run_command.py` — `--reference`,
  `expected_reference_report`, and `reference_month_work` (external CLI
  consumer).

**4. Tests and tools that still depend on the legacy pipeline:**

- `tests/unit/execution/test_reference.py` — `ReferenceSimulationExecutor`,
  `execute_reference`, and the default factory.
- `tests/unit/execution/test_determinism.py` — legacy reference-repeatability
  coverage; behavioral Numba determinism is covered by `TestNumbaRepeatability`.
- `tests/unit/execution/test_backend_strategy_matrix.py` —
  `_make_reference_executor()` via `create_default_pipeline`.
- `tests/integration/test_part49_buy_and_hold.py` —
  `create_buy_and_hold_pipeline` and `create_default_pipeline`.
- Part 49/52 integration tests that construct `create_default_pipeline`
  directly for behavioral or differential coverage.
- `tests/oracle/ern/test_ern_timeline_regression.py` — default pipeline.
- `tests/integration/test_part49_numba_executor.py` and
  `tests/integration/test_part52_numba_executor.py` no longer import the
  default factory after D4.2b removed their legacy differential classes.
- `tests/benchmarks/test_cost_model.py`,
  `tests/benchmarks/test_part49_performance.py`,
  `tests/benchmarks/test_numba_cost_breakdown.py`, and
  `tools/ern/mem_probe_*.py` — legacy factory / reference executor.

These consumers must be migrated or explicitly retained before the final
deletion gate is satisfied.

### 7.1.2 Independent debt-recurrence coverage after D4.2a/D4.2b

`tests/unit/execution/debt_recurrence_reference.py` implements the fee-free
Part 49 and Part 52 monthly recurrences with exact `Decimal` arithmetic and no
imports from `fbf.core`. The parallel test classes are:

- `tests/integration/test_part49_numba_executor.py::TestPart49IndependentDebtReference`
- `tests/integration/test_part52_numba_executor.py::TestPart52IndependentDebtReference`

D4.2b removed the redundant legacy differential classes after mapping every
scenario to an independent replacement:

| Removed legacy case | Independent replacement |
|---------------------|-------------------------|
| Part 49 flat growth | `test_flat_growth_matches_independent_reference` |
| Part 49 constant growth, zero draw | `test_constant_growth_zero_loan_draw_matches` |
| Part 49 constant growth, positive draw | `test_constant_growth_positive_loan_draw_matches` |
| Part 49 varying returns | `test_varying_returns_match_independent_reference` |
| Part 49 real-rate CPI bypass | `test_real_rate_bypasses_cpi_and_matches` |
| Part 49 CPI-adjusted rate | `test_cpi_adjusted_rate_matches_independent_reference` |
| Part 49 depletion | `test_depleted_matches_independent_reference` |
| Part 49 terminal margin call | `test_margin_call_terminal_matches_independent_reference` |
| Part 49 final-value target pass/fail | `test_final_value_target_pass_and_fail` |
| Part 49 enforcement off | `test_enforcement_off_matches_independent_reference` |
| Part 52 schedule-backed borrowing | `test_schedule_backed_matches_independent_reference` |
| Part 52 fixed-rate borrowing | `test_schedule_less_fixed_rate_matches_independent_reference` |
| Part 52 terminal loan | `test_terminal_loan_matches_independent_reference` |
| Part 52 full-schedule CPI adjustment | `test_schedule_backed_nonzero_inflation_matches_independent_reference` |
| Part 52 partial-schedule CPI adjustment | `test_partial_schedule_nonzero_inflation_matches_independent_reference` |
| Part 52 terminal margin call | `test_margin_call_terminal_matches_independent_reference` |
| Part 52 depletion | `test_depleted_matches_independent_reference` |

The independent tests include one hand-calculated flat-market anchor per part.
The removed legacy classes were the only users of the local
`_reference_result`/`_legacy_terminal_loan` helpers in those files, so those
helpers were removed as well. The remaining Part 49 buy-and-hold and generic
buy-and-hold/escalating legacy differentials were mapped and closed in
D4.2f–D4.2h; see §7.1.3.

### 7.1.3 Part 49 buy-and-hold coverage after D4.2c

`TestPart49BuyAndHoldIndependentReference` now maps every scenario in
`TestPart49BuyAndHoldLegacyDifferential`. The independent recurrence uses
`compute_monthly_rates` from the test-only Decimal helper, so it covers the
real-rate bypass and CPI-adjusted conventions without importing production or
legacy code.

| Legacy case | Independent counterpart | Status |
|-------------|-------------------------|--------|
| Constant growth, 0% equity | `test_constant_growth_matches_reference[0.0-...]` | Existing |
| Constant growth, 50% equity | `test_constant_growth_legacy_returns_match_reference` | Added D4.2c |
| Constant growth, 75% equity | `test_constant_growth_matches_reference[0.75-...]` | Existing |
| Constant growth, 100% equity | `test_constant_growth_matches_reference[1.0-...]` | Existing |
| Varying returns | `test_varying_returns_match_reference` | Existing |
| CPI-adjusted interest | `test_cpi_adjusted_rate_matches_reference` | Added D4.2c |
| Depletion | `test_depletion_matches_reference` | Existing |
| Terminal margin call | `test_ltv_terminal_matches_reference` | Existing |
| Enforcement off | `test_enforcement_off_matches_reference` | Added D4.2c |
| Final-value-target pass/fail | `test_final_value_target_pass_and_fail_match_reference` | Added D4.2c |

The independent class also retains a hand-calculated flat-market/no-leverage
anchor. D4.2f subsequently removed the 10-case
`TestPart49BuyAndHoldLegacyDifferential` after confirming the independent class
mapped every scenario.

**Generic differential status after D4.2f/D4.2h.**

| Differential class | Original legacy-dependent cases | Independent coverage | D4.2 status |
|--------------------|---------------------------------|----------------------|-------------|
| `TestBuyAndHoldExecutorDifferential` | 8 (4 legacy-only, 4 legacy plus independent anchors) | Hand-derived anchors for 0/50/75/100% equity and independent recurrence for 25/60/90% | **CLOSED** — four legacy-only cases and their setup/comparison code removed in D4.2f; remaining mixed tests split and renamed so the independent anchors remain |
| `TestEscalatingExecutorDifferential` | 2 (annual/monthly legacy-only) | Exact-horizon annual/monthly independent recurrence added in D4.2g | **CLOSED** — two legacy-only cases removed in D4.2h; file is legacy-pipeline-free |

### 7.1.4 Legacy-dependency status after D4.2i

Classification:

1. **Independent coverage exists** — a future deletion candidate, but only after
   an exact-scope review and explicit authorization.
2. **Independent coverage incomplete** — add the missing independent cases
   before considering removal.
3. **Legacy-specific behavior** — retain until the legacy code it covers is
   retired; do not treat it as redundant merely because a similar scenario has
   independent coverage.

Status vocabulary: **CLOSED** = D4.2 migration finished; **OPEN** = remaining
D4.2 work; **DEFERRED** = P5/final deletion gate, not D4.2; **DECISION** =
scope choice required before the item can be retired.

| Area / tests | Legacy dependency | What it protects | Independent coverage | Class | D4.2 status |
|--------------|-------------------|------------------|----------------------|:-----:|-------------|
| `TestPart49BuyAndHoldLegacyDifferential` | `create_buy_and_hold_pipeline`, `SimulationRunner` | Part 49 BH legacy parity, 10 scenarios | D4.2c independent class maps all 10 scenarios | 1 | **CLOSED** — removed in D4.2f |
| `TestBuyAndHoldExecutorDifferential` | `create_buy_and_hold_pipeline`, `SimulationRunner` | Fee-free BH parity; 4 legacy-only cases and 4 mixed cases | Hand-derived anchors for 0/50/75/100% equity; independent recurrence for 25/60/90% | 1 | **CLOSED** — four legacy-only cases removed and mixed tests split in D4.2f |
| `TestEscalatingExecutorDifferential` | `create_default_pipeline`, `SimulationRunner` | Annual/monthly escalating parity | Exact-horizon annual/monthly independent recurrence added in D4.2g | 2 | **CLOSED** — two legacy-only cases removed in D4.2h |
| `TestDeferredFallback::test_nominal_explicit_matches_independent_recurrence` | None after D4.2j | Explicit N-asset constant-nominal recurrence | Independent `_constant_nominal_recurrence` added; checks success, failure month, simulated months, and exact final wealth | 2 | **CLOSED** — P2.1 |
| `tests/unit/execution/test_determinism.py` | `_create_default_simulation_executor`, `ReferenceSimulationExecutor` | Reference repeatability, parallel == sequential, reference == reference | `TestNumbaRepeatability` added for plan-level sequential repeatability and process-parallel/sequential equivalence | 2 | **CLOSED** — P2.2; legacy reference repeatability remains a P5 contract |
| `tests/unit/strategies/test_numba_differential.py` | None after D4.2j | Broad edge-case differential: depletion boundaries, horizons, allocations, randomized paths | Independent Decimal beginning-of-period recurrence retained over the full edge/random matrix | 2 | **CLOSED** — P3.5 |
| `tests/unit/execution/test_trajectory_deduplication.py` | None after D4.2j | FV target as an evaluation dimension; one trajectory per group | Retargeted to `NumbaSimulationExecutor`; asserts one group for distinct FV targets, shared final wealth, and per-target success classification | 2 | **CLOSED** — P4.1 |
| `tests/unit/execution/test_pipeline_parity.py` | None after D4.2j | Legacy pipeline step composition/order and leveraged parity | Removed; structural assertions are legacy-only, and sequential/parallel behavioral parity is covered by P2.2 and P3.3 | 3 | **CLOSED** — P4.2 retired with rationale |
| `tests/unit/execution/test_reference.py` | `_create_default_simulation_executor`, `ReferenceSimulationExecutor`, `execute_reference`, `_build_derived_result`, `_slice_plan_units` | Derived horizons, prefix slicing, memory-safe dispatch | N/A — legacy executor internals | 3 | **DEFERRED** — P5 |
| `TestSummaryOnlyEquivalence` (`test_backend_strategy_matrix.py`) | `create_default_pipeline` | Timeline stripping vs statistics equality | Numba/FAST timelines are empty; no non-legacy full-timeline executor is used | 3 | **DEFERRED** — P5 |
| Part 49 BH routing/factory tests (`test_part49_buy_and_hold_numba_executor.py`) | `_create_reference_simulation_executor`, `_create_buy_and_hold_simulation_executor` | Dispatch/rejection behavior of legacy factory paths | N/A — factory-specific assertions | 3 | **DEFERRED** — P5 |
| `tests/integration/test_part49_buy_and_hold.py` | `create_buy_and_hold_pipeline`, `create_default_pipeline` | Legacy BH pipeline structure, withdrawals, debt steps, drift | Numba BH execution tests cover mechanics, not legacy step composition | 3 | **DEFERRED** — P5 |
| Part 49 production-path suites (`test_part49.py`, `test_part49_canonical_execution.py`, `test_part49_smoke_execution.py`, `test_part49_aggregation.py`) | None after D4.2j | Research plan → context → execution → aggregation, debt timelines | Retargeted to `Part49NumbaExecutor(materialize_timeline=True)`; production `Part49WithdrawalPolicy` with `loan_draw_rate`; debt timeline, aggregation, LTV, zero-interest, and terminal-state assertions retained | 2 | **CLOSED** — P3.1 |
| Part 52 legacy trajectory suites (`test_part52_compound_drawdown.py`, `test_part52_ffr_floating_rate.py`, `test_part52_numerical_trace.py`) | None after D4.2j | Compound drawdown, FFR schedule, month-by-month numerical trace | Retargeted to `Part52NumbaExecutor(materialize_timeline=True)`; borrow/repay, per-month interest, fixed-rate fallback, and numerical trace assertions retained with float-materialization tolerances | 2 | **CLOSED** — P3.2 |
| Multi-cohort/parallel suites (`test_multi_cohort_execution.py`, `test_part49_multi_cohort.py`, `test_real_engine_execution.py`, `test_glidepath_trajectory.py`) | None after D4.2j | Cohort isolation, process serialization, CLI-plan execution | Retargeted to `NumbaSimulationExecutor` / `Part49NumbaExecutor(materialize_timeline=True)`; cohort isolation, parallel/sequential equivalence, serialization, and glidepath targets retained | 2 | **CLOSED** — P3.3 |
| Research-layer debt plumbing (`test_research_layer_debt_flow.py`) | None after D4.2j | Context translation, debt-flag propagation, end-to-end debt | Retargeted to `Part49NumbaExecutor(materialize_timeline=True)`; parameter translation, real/nominal rate propagation, and debt timelines retained | 2 | **CLOSED** — P3.4 |
| Debt/pipeline structural suites (`test_debt_pipeline_regression.py`, `test_debt_invariants.py::TestDeterministicPipelineOrder`, `test_schedule.py`, `test_zero_interest_debt.py::TestZeroInterestFullPipeline`) | `create_default_pipeline` | Legacy step order, zero-interest debt, schedule behavior | N/A — legacy pipeline internals | 3 | **DEFERRED** — P5 |
| Legacy pipeline unit suites (`tests/unit/pipeline/test_simulation_runner.py`, `test_simulation_runner_integration.py`, `test_simulation_executor.py`, `test_terminal_depletion.py`, `test_ern_timeline_event_order.py`) | `SimulationRunner`, `create_default_pipeline` | Runner mechanics, step composition, depletion, event order | Numba executor tests cover supported execution behavior; pipeline-internal assertions are legacy-only | 3 | **DEFERRED** — P5 |
| Fast-path/grid suites (`test_fast_path.py`, `test_workbook_outcome_contract.py`, `test_fv_target_failure_month_contract.py`, `test_grid_reference.py`) | `FastPathSimulationExecutor`, `sequential_execute` | Decimal fast-path outcomes, grid derivation, FV failure month | Numba executors cover supported execution behavior; FastPath retention is a D5b/D4.3 decision | 3 | **DEFERRED** — P5 / D5b decision |
| Oracle/benchmark/tool/Part 42 consumers (`test_ern_timeline_regression.py`, benchmark modules and scripts, `tools/ern/mem_probe_*`, `test_part42_e2e_audit.py`) | Default factory/pipeline, `ReferenceSimulationExecutor`, `reference_month_work` | Legacy timeline oracle, performance/memory baselines, Part 42 audit | N/A — intentionally legacy-specific | 3 | **DEFERRED** — P5 / out of scope |

**Prioritized D4.2j plan.**

1. **P1 — CLOSED; committed in `1882d22`.** Exact P1 deletions completed in
   D4.2f and D4.2h.
2. **P2 — CLOSED; committed in `35976b6`.** Added the independent
   constant-nominal N-asset recurrence (replacing the reference-executor
   comparison) and plan-level Numba sequential-repeatability and
   process-parallel/sequential equivalence coverage. Legacy
   reference-repeatability tests remain deferred to P5.
3. **P3 — CLOSED; committed in `35976b6`.** P3.1–P3.5 migrated the Part 49
   production-path, Part 52 trajectory, multi-cohort/parallel, research-layer
   debt, and broad edge/random suites onto supported Numba paths or independent
   recurrences.
4. **P4 — CLOSED; committed in `c04c058`.** P4.1 retargeted
   FV-target/deduplication semantics to `NumbaSimulationExecutor`. P4.2 retired
   the legacy pipeline-parity suite because its structural assertions have no
   supported-engine analogue; its behavioral parity guarantee is already
   covered by P2.2 and P3.3.
5. **P5 — DEFERRED.** Reference/derived-horizon internals, summary-only legacy
   helper coverage, structural debt/schedule tests, oracle/benchmark/tool
   consumers, Part 42, and the active production fallbacks remain
   legacy-specific until D4.3 removes their code paths.

P2–P4 and the related D4.1/D4.2a–c/P1 changes are committed. This documentation
reconciliation completes D4.2; P5 remains deferred.

D4.2i made no test, production, oracle, expected-value, executor, factory,
pipeline, or export change. No heavyweight E2E or full-grid workload was run.

### 7.1.5 D4.2 remaining work, dependencies, and exit criteria

**Scope boundary.**

- **D4.2** is test-migration work: migrate test oracles and contracts away from
  the legacy engine where supported behavior can be independently pinned.
- **D4.3** is legacy-engine deletion: remove production fallbacks, legacy
  factories/pipelines/exports, and the tests that exclusively describe them.
- P2–P4 are D4.2. P5 is D4.3/final-gate work. A legacy dependency that remains
  after D4.2 must be explicitly classified as deferred to P5, not silently
  overlooked.

**Remaining work and dependencies.**

| Group | Remaining work | Dependency / decision |
|-------|----------------|-----------------------|
| P2.1 | **Complete** — independent constant-nominal N-asset recurrence | Preserved the exact multi-asset scenario; no production engine as oracle |
| P2.2 | **Complete** — plan-level Numba repeatability and parallel/sequential equivalence | Legacy reference-repeatability tests classified as P5 |
| P3.1 | **Complete** — retargeted Part 49 production-path suites | Preserved aggregation, debt-timeline, LTV, zero-interest, and terminal-state coverage; custom test policy replaced by the production Part 49 policy |
| P3.2 | **Complete** — retargeted Part 52 trajectory suites | Preserved FFR, compound-drawdown, and month-by-month trace pins using the materialized Part 52 Numba path |
| P3.3 | **Complete** — retargeted multi-cohort/parallel suites | Preserved cohort isolation, process serialization, parallel/sequential equivalence, and glidepath trajectory coverage |
| P3.4 | **Complete** — retargeted research-layer debt end-to-end | Preserved structural translation assertions and added materialized Part 49 debt execution |
| P3.5 | **Complete** — retargeted broad edge/random differential | Preserved the edge-case matrix with an independent Decimal recurrence, not the legacy pipeline |
| P4.1 | **Complete** — retargeted FV-target/deduplication semantics | Numba grouping excludes FV target; per-target classification and shared final wealth are asserted directly |
| P4.2 | **Complete** — retired legacy pipeline-parity suite | Structural legacy-only; sequential/parallel behavioral parity retained by P2.2 and P3.3 |

**Validation requirements after each task.** Focused tests for the changed
group; Ruff; `mypy --strict .`; the routine suite and contract tests at
milestones; and `git diff --check`. No heavyweight E2E or full historical grid
without separate authorization. No oracle or unrelated expected-value changes
to force agreement.

**Explicit D4.2 exit criteria.**

D4.2 is complete because all of the following are verified:

1. P1–P4 are complete, or an explicitly retired contract has a documented,
   defensible rationale.
2. The independent multi-asset recurrence and plan-level Numba determinism gaps
   in P2 are closed.
3. P3 suites retain meaningful behavioral and numerical coverage without using
   the legacy engine as the oracle for migrated tests.
4. P4 semantics are ported to supported behavior or explicitly classified as
   legacy-only.
5. The roadmap accurately reflects completed, open/decision, and deferred work,
   including the P5/D4.3 boundary.
6. Focused tests, the routine suite, contract tests, Ruff, strict mypy, and
   `git diff --check` pass.
7. No oracle or unrelated expected values were changed to force agreement.
8. A final read-only audit identifies remaining legacy dependencies and
   confirms they are deferred to P5/D4.3.

D4.2j does not authorize D4.3 legacy-engine deletion, production fallback
changes, or public API removal.

### 7.2 Configuration / CLI / public surface

| Surface | File | Note |
|---------|------|------|
| `ExecutionBackend` | `execution/__init__.py` | D5b canonicalized `DECIMAL_FAST_PATH`; `REFERENCE` is a deprecated same-value alias through `0.2.x`. |
| `--reference`, `--fast-path` | `fbf-cli/src/fbf/cli/commands/run_command.py` | Removed by D5a. |
| `--validate` | same file | Removed by D5a. |
| `compare` / `optimize` execution | `compare_command.py`, `optimize_command.py` | D5a routes both through explicit FAST `execute_study_plan`. |
| Part 3 execution/imports | `run_command.py` | D5a uses the Tier 2 `fbf.core.research` facade and explicit FAST. |
| CLI packaging | `fbf-cli/pyproject.toml` | D5a declares `fbf-core[numba]`, making Numba mandatory for the CLI. Core AUTO fallback remains until D4.3. |
| Persistence guard | `run_command.py` | D5a removed the flag and persists explicit FAST runs with `materialize_timeline=True`. |
| `ExecutionOptions` | `execution/__init__.py` | `summary_only`, `materialize_timeline`, `glidepath_gf_cache` |

### 7.3 Test inventory

Statuses in this inventory describe committed work. P2/P3 (`35976b6`), P4
(`c04c058`), D4.1 (`01e4aeb`), D4.2a–c (`ce2ec97`), and P1 (`1882d22`) are
committed; the documentation reconciliation is committed in Step E.

| Test | Class | Phase | Action |
|------|-------|:-----:|--------|
| `tests/oracle/ern/*` | Canonical correctness | — | Keep (primary acceptance) |
| `tests/unit/execution/test_determinism.py::TestReferenceDecimalEquivalence` | Obsolete equivalence | A | **DELETED** — tested FAST vs legacy reference (multiplicative fee) |
| `tests/unit/execution/test_fast_path_exact_equivalence.py` | Obsolete equivalence | A | **DELETED** — tested FAST vs legacy reference (multiplicative fee) |
| `tests/unit/execution/test_reference.py` | Legacy executor internals | D | Delete in P5/D4.3; FV dedup cases were ported to `test_trajectory_deduplication.py` in D4.2j |
| `tests/unit/execution/test_trajectory_deduplication.py` | Behavioral (FV dedup) | D | **RETAINED** — retargeted to `NumbaSimulationExecutor` in D4.2j |
| `tests/unit/execution/test_backend_equivalence.py` | Routing | A | Keep; fix "reference" naming |
| `tests/unit/execution/test_backend_strategy_matrix.py` | Routing | A | Keep; replace `_make_reference_executor()` with `FastPathSimulationExecutor` |
| `tests/unit/execution/test_pipeline_parity.py` | Behavioral/equivalence | D | **DELETED** in D4.2j — structural legacy-only assertions; behavioral parity covered by P2.2/P3.3 |
| `tests/unit/strategies/test_numba_executor_differential.py` | Differential vs workbook oracle | B/C | **ACTIVE** — Numba executor vs workbook SCR oracle for static allocations |
| `tests/unit/execution/test_grid_reference.py` | Legacy grid | C/D | Reclassify; keep routing tests |
| `tests/integration/test_numba_e2e.py` | Numba E2E (workbook oracle) | B/C | **ACTIVE** — full study path vs workbook oracle for static allocations |
| `tests/integration/test_part52_*` | Behavioral (debt) | C | **REWRITE** to use `Part52NumbaExecutor`; add explicit Numba-path tests |
| `tests/integration/test_part49_*` | Behavioral/canonical | C | **REWRITE** to use Numba executor; add explicit Numba-path tests |
| `tests/benchmarks/test_*` | Performance | B/D | Keep; update to unified path |
| `fbf-cli/tests/unit/test_run_command.py`, `test_grid_cli_contract.py` | Routing/CLI | A | Keep; align to repaired dispatch (A1) |
| `tests/unit/execution/test_fast_path.py` | Fast path workbook SCR | B | **PASSING** (22/22) — validates workbook SCR path, depletion boundary, multi-horizon equivalence |
| `tests/unit/research/test_part20_corrected_methodology.py` | Part20 workbook fidelity | B | **PASSING** (9/9) — updated expectations for workbook methodology |
| `tests/integration/test_part52_numba_executor.py` | Part 52 Numba path | A/D4.1 | **ACTIVE** — eligible configs execute without a reference hook; D4.1 asserts `_reference` is absent |
| `tests/integration/test_part52_numba_executor.py` (ineligibility cases) | Unsupported config errors | A/D4.1 | **ACTIVE** — ineligible Part 52 configs raise `UnsupportedConfigurationError`; no fallback is invoked |
| `tests/integration/test_part49_numba_executor.py`, `tests/integration/test_part49_buy_and_hold_numba_executor.py` | Part 49 Numba paths | C/D4.1 | **ACTIVE** — eligible configs execute without a reference hook; D4.1 asserts `_reference` is absent |
| `tests/unit/execution/debt_recurrence_reference.py` | Independent Decimal debt recurrence | D4.2a | **ACTIVE** — no production or legacy imports; test-only oracle |
| `tests/integration/test_part49_numba_executor.py::TestPart49IndependentDebtReference` | Part 49 independent differential | D4.2a/D4.2b | **ACTIVE** — all legacy debt scenarios have independent counterparts; hand-calculated anchor retained |
| `tests/integration/test_part52_numba_executor.py::TestPart52IndependentDebtReference` | Part 52 independent differential | D4.2a/D4.2b | **ACTIVE** — all legacy debt scenarios have independent counterparts; hand-calculated anchor retained |
| `TestPart49DecimalDifferential`, `TestPart52DecimalDifferential` | Legacy debt differentials | D4.2b | **DELETED** — 17 cases mapped to the independent classes; local legacy helpers removed |
| `tests/integration/test_part49_buy_and_hold_numba_executor.py::TestPart49BuyAndHoldIndependentReference` | Part 49 buy-and-hold independent differential | D4.2c | **ACTIVE** — maps all 10 legacy scenarios; CPI, enforcement-off, FVT, and hand-calculated anchor included |
| `tests/integration/test_part49_buy_and_hold_numba_executor.py::TestPart49BuyAndHoldLegacyDifferential` | Part 49 buy-and-hold legacy differential | C4/D4.2c/D4.2f | **DELETED** — 10 cases mapped to the independent class and removed in D4.2f |
| `TestBuyAndHoldExecutorDifferential` | Generic buy-and-hold legacy differential | C4/D4.2f | **CLOSED** — four legacy-only cases and legacy setup/comparison code removed; mixed tests split so independent anchors remain |
| `TestEscalatingExecutorDifferential` | Generic escalating legacy differential | B3/D4.2g/D4.2h | **DELETED** — exact-horizon independent anchors added in D4.2g; two legacy cases removed in D4.2h |

**D5a CLI evidence (to be added in `fbf-cli`; not yet present).** The D5a
milestone must prove: all execution commands pass
`ExecutionOptions(backend=ExecutionBackend.FAST)`; `run`, `compare`, `optimize`,
and Part 3 call neither `_create_default_simulation_executor` nor the legacy
runner as an execution path; missing Numba and unsupported configurations fail
explicitly; and CLI production imports resolve only to Tier 1/Tier 2 Core
modules (`fbf.core.research` included, `fbf.core.research.part3_pipeline` and
`part3_planner` excluded). The existing CLI tests that assert `AUTO` for
`--reference` do not satisfy D5a.

---

## 8. Final Deletion Gate for the Legacy Reference Engine

The legacy engine may be deleted only when **all** of the following hold (Phase D gate):

1. **Capability parity.** Every capability in §3 is either class 1 (migrated)
   or an explicitly retained specialized path. No production path calls
   `_create_default_simulation_executor()`.

2. **Workbook fidelity for static allocations.**
   - Independent validation of the SCR calculation against the workbook formulas.
   - Agreement between SCR-based success classification and workbook-calculated examples.
   - Validation of end-of-period trajectory and final wealth against the workbook or hand-verifiable cases.
   - Tests covering fees, horizon boundaries, and depletion.

3. **Dynamic glidepath extension specification documented.**
   - A documented extension specification for glidepath allocation transitions, withdrawals, and depletion.
   - Deterministic tests for allocation transitions, withdrawals, and depletion.
   - Explicit separation between workbook-defined behavior and simulator-specific extension behavior.

4. **No production consumer.** A repository-wide search for the following
   returns no production references (only the roadmap / history):
   - `ReferenceSimulationExecutor`
   - `execute_reference`
   - `_create_default_simulation_executor`
   - `create_default_pipeline`
   - `create_buy_and_hold_pipeline`
   - `ExpenseDeductionStep`
   - `expected_reference_report`
   - `reference_month_work`
   - `reference_executor=`

5. **Public surface resolved (D4.3).** `execute_reference`,
   `expected_reference_report`, and `reference_month_work` are deleted;
   `ExecutionBackend.FAST` is the only backend value, with
   `DECIMAL_FAST_PATH` and `REFERENCE` removed. Consumer pins are updated and
   Core was bumped to `0.3.0`.

6. **CLI resolved (D5a).** `fbf-cli` declares `fbf-core[numba]` and uses
   explicit FAST. `--reference`, `--fast-path`, and `--validate` are removed
   rather than retained as no-ops; `run`, `compare`, `optimize`, and Part 3
   route through the unified FAST path; unsupported configurations and missing
   Numba fail explicitly with no fallback. Core AUTO has no legacy fallback.

7. **Validation.** Production ERN grids match
   `data/ern/workbook_oracle_table.csv` with exact Decimal equality; the
   historical published-ERN oracle remains a separate target. Part 52 /
   Part 49 / Part 19 / Part 20 E2E and behavioral tests pass; determinism and
   parallel-equivalence tests pass; persistence round-trips full trajectories.

8. **Memory gate.** Large-grid execution (313k units) stays within the
   documented host memory budget with timelines enabled.

9. **Quality gate.** `ruff check .`, `mypy --strict .`, and the full test suite
   pass from a clean checkout per `AGENTS.md`.

10. **Oracles preserved.** `tools/ern/reference_oracle.py` remains the
    historical published-ERN oracle; `tools/ern/workbook_oracle.py` remains the
    production-conformance oracle. Each regenerates its own table independently.

Deletion is atomic per Phase D and must not occur until gates 1–10 pass.

---

## 9. Progress Tracking

| Milestone | Status | Evidence | Commit | Notes |
|-----------|--------|----------|--------|-------|
| A1: CLI execution routing | ✅ Complete | Explicit FAST for `run`/`compare`/`optimize`/Part 3; legacy flags removed; `fbf-core[numba]` required | 3181bf5 (fbf-cli) | Completed by D5a |
| A2: Part 52 Numba test coverage | ✅ Complete | 12 new tests exercise Numba path | f427202 | Tests prove eligible configs execute on Numba without fallback |
| A3: Document legacy consumers | ✅ Complete | §1.3 | b4ff4ad | Verified via grep |
| E1: Strict Numba FAST execution | ✅ Complete (enabler) | `test_fast_backend_strictness.py`; explicit FAST rejects ineligible contexts; AUTO unchanged | f28f571 (fbf-core) | Hardens §2.1/§2.2; not a roadmap phase completion |
| E2: Public Part 3 research facade | ✅ Complete (enabler) | `fbf.core.research` Tier 2; `tests/contract/test_research_public_api.py` | d44213c (fbf-core) | Prerequisite for D5a; CLI still imports Tier 3 until D5a |
| B1: Expense ratios (additive fee) | ✅ Complete (audited & fixed) | `workbook_scr.py`, `test_fast_path.py`, `part52_numba_executor.py` | 8dfbf24 (audited) | Static + Part 52 complete; Glidepath pending; **Critical cache key + fee pass-through bug fixed** |
| B2: Constant nominal withdrawal | ✅ Complete | `numba_kernel.py`, `numba_executor.py`, `test_backend_strategy_matrix.py` | 00b5770 | Recurrence `V_{m+1}=V_m*(1-rate/12)*g_m` implemented; matches legacy for flat/growing markets; fee model uses additive convention |
| Numba cache/dataset identity fix | ✅ Complete | `test_numba_executor_differential.py`, `test_part52_numba_executor.py` | 99aa5a4 | Dataset-identity tokens + identity-prefix clustering in both Numba executors |
| B2 audit: Part 52 derivation key | ✅ Complete | `test_part52_numba_executor.py` | a00c0ec | Monthly-rate prefix guard added; per-context FV dims (`initial_wealth`, `final_value_target`) decoupled from grouping |
| B3: Escalating withdrawal | ✅ Complete (ConstantAllocation) | `numba_kernel.py`, `numba_executor.py`, `test_numba_escalating.py` | 65f1f67 | Value-independent annual schedule; deterministic annual glidepath + escalating is implemented under D3; general Numba glidepath + escalating remains deferred |
| Buy-and-hold initial allocation | ✅ Complete (correction) | `default_pipeline.py`, `allocation_decision_step.py`, `portfolio_rebalance_step.py`, `test_part49_buy_and_hold.py` | 3f2f788 | Buy-and-hold applied the 50/50 default; allocation now applied once in period 0 |
| B4: Buy-and-hold | ✅ Complete (non-debt, fee=0) | `numba_kernel.py`, `numba_executor.py`, `execution/__init__.py`, `test_numba_buy_and_hold.py` | 5179a3b | Unit-tracking kernel; Part 49 leverage → C4, multi-asset → B5, fee>0 deferred |
| B5: Multi-asset | ✅ Complete | `concrete.py`, `fast_path.py`, `numba_executor.py`, `test_multi_asset_allocation.py` | 85d72582f047279d5d9c42ca3f3cb0e3d9099c7b | Explicit N-asset `allocations`; single `resolve_target_weights`; nominal/escalating/Part 52 gate to the legacy form and fall back for explicit allocations |
| C1: Part 52 Numba-only | ✅ Complete | `part52_numba_executor.py`, `execution/__init__.py`, `test_part52_dispatch_contract.py` | 2343c225278d1e02722a9567ab911e835215b6ff | Eligible Part 52 runs on Numba; explicit FAST on an ineligible Part 52 workload raises `UnsupportedConfigurationError` (no silent fallback) |
| C2: Part 52 fee behavior | ✅ Complete (B1) | `_compute_growth_factors_numpy` (`numba_kernel.py`) fee passed by `part52_numba_executor.py`; `TestPart52ExpenseRatioSupport`, `TestPart52ExpenseRatioIndependentValidation` | 8dfbf24 (audited) | Additive fee `g_m = Σ_j w_j·P_{j,m}/P_{j,m-1} − fee/12` embedded in kernel growth factors |
| C3: Part 49 debt migration | ✅ Complete | `part49_numba_executor.py`, `test_part49_numba_executor.py`; production flag propagation covered in `test_research_layer_debt_flow.py` | 5d5a569 | 10,434-unit Part 49 full-path E2E passed with `ExecutionBackend.FAST` and a concrete `Part49NumbaExecutor.execute` call-count assertion. All 6 cells × 1,739 cohorts executed; the non-leverage historical comparison against the pinned published oracle passes, and leverage directionality holds. Production conformance uses the workbook-derived oracle. |
| C4: Part 49 buy-and-hold | ✅ Complete (supported scope, Option B) | `part49_buy_and_hold_numba_executor.py`, `test_part49_buy_and_hold_numba_executor.py`; production flag propagation covered in `test_research_layer_debt_flow.py` | 6abda00 | Supported scope: Part 49 buy-and-hold, two assets, zero fee. Option B approved after independent verification of synthetic production-path dispatch, independent Decimal differential, legacy differential, LTV, and real-rate tests. The C4 gate is independent of C3; the 10,434-unit constant-allocation test is unrelated. This closure does not establish real-data canonical-scale equivalence, 1,739-cohort coverage, or a canonical ERN buy-and-hold oracle. |
| C5: LTV terminal state | ✅ Complete | `numba_kernel.py`, `part49_numba_executor.py`, `part49_buy_and_hold_numba_executor.py`, `part52_numba_executor.py`; `test_part49_numba_executor.py`, `test_part49_buy_and_hold_numba_executor.py`, `test_part52_numba_executor.py` | b5ad4a2, 5d5a569, 6abda00 | Part 49 debt, Part 49 buy-and-hold, and Part 52 Numba kernels emit `margin_call_terminal` and match Decimal/legacy references. Targeted Numba executor and debt flag propagation tests pass. C3 and C4 closure are governed by their separate gates. |
| D1: Trajectory materialization | ✅ Complete | `execution/strategies/*`, `execution/strategies/trajectory.py`, `test_timeline_materialization.py` | 46687ce | Optional flag; use D2 streaming at grid scale |
| D2: Cohort-slice for memory | ✅ Complete | `execution/slicing.py`, `execution/__init__.py`, `part52_evaluator.py`, `part49_aggregation.py`, `persistence/studies/sqlite/sqlite_repository.py`, `tests/oracle/ern/test_streaming_aggregate.py` | a46ab2c | Streaming API + guard + consumer migration + incremental persistence + CLI persistence wiring complete. External full-grid validation: 313,020 units through `iter_execute_study_plan` in 16 summary-only slices; peak RSS 451.3 MiB (REFERENCE) / 582.2 MiB (FAST), under 16 GB. Streaming matched whole-plan on every cell, both backends agreed, and the production grid matched `workbook_oracle_table.csv` 180/180 exactly. The routine regression streams a four-cell production subset across all 1,739 cohorts, persists/reloads it, and matches streaming, whole-plan, and persisted per-cell aggregates to the workbook oracle with exact Decimal equality. The 13/180 published-oracle differences are documented as the T vs T+1 historical divergence, not a production failure. The routine regression is committed in `9f00a89` as Step A and was validated against both the current workspace and an isolated `HEAD + A` worktree. |
| D3: Deterministic trajectory | ✅ Complete | `execution/deterministic.py`, `execution/strategies/deterministic_kernel.py`, `test_deterministic_kernel.py`, `test_part20_experiment_e.py` | ccedb79 | Dedicated unit-tracking kernel; additive fee; annual/monthly rebalance; corrected Experiment E values pinned; published anchors remain unresolved |
| D4: Legacy removal | ✅ Complete (D4.2 and D4.3) | `execution/strategies/eligibility.py`, `numba_executor.py`, `part49_numba_executor.py`, `part52_numba_executor.py`, `part49_buy_and_hold_numba_executor.py`, `execution/deterministic.py`; migrated tests and independent Decimal oracles | D4.1–D4.2 commits; D4.3 final phase commit | D4.2 migrated the remaining differentials to independent oracles and retargeted production-path suites to Numba. D4.3 deleted the legacy Decimal engine, nine-step pipeline, Decimal fast path, reference/reporting modules, fallback hooks, and the `DECIMAL_FAST_PATH`/`REFERENCE` backend values. FAST is now fail-closed and the sole execution backend; Core `0.3.0` and CLI/UI pins are updated. |
| D5a: CLI single-engine routing | ✅ Complete | Explicit FAST for `run`/`compare`/`optimize`/Part 3; legacy flags removed; `fbf-core[numba]` required; no fallback | 3181bf5 (fbf-cli) | Tier 2 `fbf.core.research` imports; CLI contract tests cover missing Numba |
| D5b: Core backend/public surface | ✅ Complete; superseded by D4.3 | Legacy reporting exports removed from facade; Core `0.2.0`; consumer pins updated at the time | D5b milestone | Historical. D4.3 removed the `DECIMAL_FAST_PATH`/`REFERENCE` aliases and the legacy implementations; Core is now `0.3.0`. |

**Legend:** ✅ Complete | 🔄 In Progress | ⬜ Not Started | ❌ Blocked

### Completed Milestones

**99b4882** — "workbook fidelity: implement additive fee model, fix builder horizon bug, add validation tests"
- Implemented workbook SCR methodology for static allocations across `workbook_scr.py`, `fast_path.py`, `numba_kernel.py`, `numba_executor.py`
- Validated against saved workbook values (600-month, 75/25, 4% WR, 0.05% fee)
- All quality gates pass: ruff, mypy, contract tests, unit tests, integration tests

**8dfbf24 (audited & fixed)** — "B1: Part 52 expense ratio support (additive fee model)"
- Removed `expense_ratio` rejection from `is_part52_eligible()` in `part52_numba_executor.py`
- **Critical fix**: Part 52 executor was not passing `fee_annual` to `_compute_growth_factors_numpy` and cache key excluded `expense_ratio` — fixed in audit
- Added 7 new tests in `test_part52_numba_executor.py` (plus cache key fix validation):
  - Eligibility: positive fee, zero fee now eligible
  - Numba path: zero fee, positive fee execute without fallback
  - Fee affects wealth: verified fee reduces final wealth (strict inequality)
  - Boundary case: tiny fee (0.0001%) executes on Numba
  - Independent validation: workbook_scr module verifies additive fee model
  - SCR reduction: higher fee reduces SCR
- All quality gates pass: ruff, mypy, pytest (19 Part 52 tests + all existing tests)

**00b5770** — "B2: Constant nominal withdrawal (ConstantWithdrawalPolicy)"
- Implemented recurrence `V_{m+1} = V_m * (1 - rate/12) * g_m` in `_simulate_trajectory_constant_nominal` (beginning-of-period, matching legacy pipeline)
- Added eligibility predicate `_is_constant_nominal_eligible` and group key `_constant_nominal_group_key` (excludes `initial_wealth` since withdrawal scales with current value)
- Extended `NumbaSimulationExecutor` with `_process_constant_nominal_group` for batch processing
- Fee model uses additive convention (embedded in growth factors) consistent with workbook methodology
- Verified against legacy engine: matches for flat/growing markets; fee model differs from legacy `ExpenseDeductionStep` (documented)
- AUTO routing now selects Numba for ConstantWithdrawalPolicy + ConstantAllocationPolicy
- All quality gates pass: ruff, mypy, pytest (541 unit tests + integration tests)

**99aa5a4** — "fix growth-factor / price cache identity collision in both Numba executors"
- Both Numba executors keyed cached growth factors, materialised prices, and
  index series by trajectory parameters (`start_date`, allocation) only. Two
  contexts built from *different* market datasets that shared a start date
  therefore shared one trajectory's cached results: whichever context was
  processed first supplied growth factors for every later one. The bug was
  reachable by any `EngineExperimentDefinition`/`ResearchPlan` mixing per-unit
  datasets that share a start date.
- Fixed by keying every dataset-derived cache on a dataset-identity token
  (`fast_path._dataset_token`) and, for cross-horizon derivation, splitting each
  parameter group into identity-prefix clusters (`fast_path._trajectory_clusters`)
  so a shorter horizon is only ever derived from a trajectory that is a
  snapshot-identity prefix of it.
- The glidepath batch path additionally grouped by `(max_h, fee)` and now applies
  each entry's own expense ratio (previously the per-batch fee leaked from an
  unrelated loop variable).
- The Part 52 executor previously reused `fast_path._group_key`, which keys on
  the withdrawal *rate* only. Contexts differing in `borrow_pct`,
  `drawdown_threshold`, fee, LTV settings, or interest rate were merged into one
  derivation cluster and silently ran with the representative's parameters. It
  now uses a Part 52-specific grouping key (`_part52_group_key`) covering every
  kernel-consumed field except the horizon and `final_value_target`.
- Executors retain strong references to every dataset they have seen, keeping
  identity tokens unique for the executor's lifetime so caches remain valid
  across `execute` calls (reused worker executors) without risk of an id being
  reused by a different trajectory.
- Cache-reuse unit tests were updated: contexts must share the same sliced
  `Dataset` object (as `materialize_research_plan` does), not merely the same
  start date. Added regression tests for both executors verifying that distinct
  trajectories sharing a start date produce the same results together as alone,
  in either declaration order, plus Part 52 tests verifying that contexts
  differing only in `borrow_pct` or `drawdown_threshold` are not merged.
- All quality gates pass: ruff, mypy, pytest (unit, infrastructure, integration,
  contract, benchmarks).

**a00c0ec** — "Part 52 derivation-key correctness audit"
- Audited every context field consumed by the Part 52 kernel path against
  `_part52_group_key`. The shared path consumes `start_date`,
  `equity_allocation`, `expense_ratio`, `initial_portfolio`, `withdrawal_rate`,
  `borrow_pct`, `drawdown_threshold`, `frequency`, `interest_rate`, `ltv_limit`,
  and `ltv_enforcement`; all are in the key. Dataset identity is enforced by the
  identity-prefix guard.
- **Defect found and fixed:** `interest_rate_schedule` was excluded on the
  assumption that it is prefix-consistent for a fixed start date, but the
  identity-prefix cluster guard only checked the market dataset.
  `_compute_monthly_rates` is evaluated once per cluster from the representative
  and reused for every derived horizon, so a shorter context whose own schedule
  diverged within its horizon silently inherited the representative's rates
  (reproduced: the same context produced a different `final_wealth` / `success`
  when clustered than when run alone). Clustering now also
  requires an explicit monthly-rate prefix match
  (`_monthly_rates_prefix_compatible`), threaded through
  `fast_path._trajectory_clusters` as an optional predicate.
- `initial_wealth` and `final_value_target` are per-context *evaluation*
  dimensions consumed only by `_apply_fv_check`, which runs per context after
  the shared path. `initial_wealth` was removed from the group key, and the
  per-horizon result cache is now keyed by
  `(horizon, initial_wealth, final_value_target)` so the FV verdict is never
  shared across contexts that differ in the threshold base.
- Added regression tests for: divergent-within-horizon schedules (not merged),
  shared-prefix schedules (still derived), different horizons, different FV
  targets, different `initial_wealth`, reused-executor sequential calls, and
  dataset pinning.
- Verified invariants (proven by tests): `horizon_months` is excluded because
  each horizon is simulated independently; `final_value_target` and
  `initial_wealth` are excluded because the FV check is per context;
  `interest_rate_schedule` may only be excluded because its consumed prefix is
  now explicitly checked.

**65f1f67** — "B3: Escalating withdrawal (ConstantAllocationPolicy)"
- Added `_simulate_trajectory_escalating` (`numba_kernel.py`) plus sequential and
  parallel batch variants and the `simulate_single_escalating` /
  `simulate_batch_escalating` wrappers. The withdrawal schedule is
  value-independent and frozen at
  `initial_value * withdrawal_rate * (1 + escalation_rate) ** (m // 12)`, taken
  as one lump sum per year (`ANNUAL`, at `m % 12 == 0`) or as a monthly twelfth
  (`MONTHLY`).
- Extended `NumbaSimulationExecutor` with `_is_escalating_eligible`,
  `_escalating_group_key` (excludes `initial_wealth`; the withdrawal base is the
  initial portfolio value `v0`), and `_process_escalating_group`. Growth factors
  are shared through the existing static GF cache. AUTO backend dispatch now
  routes all-escalating workloads to `NumbaSimulationExecutor`; the FAST backend
  already reached it.
- Semantics were established **before** implementing the kernel: an empirical
  run of the legacy `create_default_pipeline()` for both frequencies reproduced
  the hand-calculated flat-market final value exactly (fee = 0), confirming the
  withdrawal timing and escalation recurrence. With a non-zero fee the Numba
  path uses the workbook additive convention and intentionally differs from the
  legacy `ExpenseDeductionStep`, consistent with B1/B2.
- Validation in `tests/unit/strategies/test_numba_escalating.py`: closed-form
  flat-market hand calculations, an independent Decimal recurrence, a
  depletion-boundary case, batch sequential/parallel equivalence, differential
  against the legacy pipeline (fee = 0) for `ANNUAL` and `MONTHLY`, per-context
  `final_value_target` application, ineligible-allocations fall-through, and AUTO
  routing.
- **Scope note:** escalating withdrawal is migrated for `ConstantAllocationPolicy`
  in the general Numba executor. Glidepath allocation + escalating in that
  executor remains future work. The deterministic Experiment E path is now
  implemented separately on the dedicated D3 kernel (capability #15), which
  supports annual glidepath + escalating with the workbook additive fee.
- All quality gates pass: ruff, mypy, pytest (unit, infrastructure, integration,
  contract).

**5179a3b** — "B4: Buy-and-hold (BuyAndHoldAllocationPolicy)"
- Prerequisite correction (`3f2f788`): `create_buy_and_hold_pipeline()` never
  invoked `BuyAndHoldAllocationPolicy` — it omitted both `AllocationDecisionStep`
  and `PortfolioRebalanceStep`, so every buy-and-hold run started from
  `build_initial_portfolio`'s equal weights regardless of `equity_allocation`.
  Both steps gained a `first_period_only` flag and now run only in period 0,
  applying the configured target once before weights drift.
- Added `_simulate_trajectory_buy_and_hold` (`numba_kernel.py`) plus sequential
  and parallel batch variants and the `simulate_single_buy_and_hold` /
  `simulate_batch_buy_and_hold` wrappers. The kernel tracks the equity weight
  explicitly: withdrawals reduce both holdings pro rata (preserving the weight
  immediately before the withdrawal) and the weight drifts between withdrawals
  via the asset-specific returns::

      V_0 = initial_value,  w_0 = equity_weight
      for m in 0 .. horizon-1:
          if C > V_m: failure at month m
          V_m <- V_m - C
          if m < horizon - 1:
              G = w_m * ge[m] + (1 - w_m) * gb[m]
              w_{m+1} = w_m * ge[m] / G
              V_{m+1} = V_m * G

  This matches the legacy buy-and-hold pipeline exactly (fee = 0), because the
  proportional liquidation used to fund withdrawals is the reference behavior.
- Extended `NumbaSimulationExecutor` with `_is_buy_and_hold_eligible`,
  `_buy_and_hold_group_key` (excludes `initial_wealth`; the withdrawal base is
  `v0`), `_process_buy_and_hold_group`, and a per-dataset-token per-asset
  growth-factor cache (`_bh_growth_cache`). Unlike the static/glidepath paths, a
  single blended growth-factor series cannot be precomputed because the weights
  are path-dependent, so the kernel consumes the equity and bond series
  separately. AUTO backend dispatch now routes all-buy-and-hold workloads to
  `NumbaSimulationExecutor`.
- **Eligibility** requires `BuyAndHoldAllocationPolicy` + `FixedRealWithdrawalPolicy`,
  a two-asset equity/bond portfolio present in the dataset, `v0 == initial_wealth`,
  and `expense_ratio in (None, 0)`. Fees are excluded because the legacy
  buy-and-hold path's expense/timing correction is derived from
  `previous_portfolio_value`, which (absent a periodic rebalance) is only
  refreshed in period 0 — so a non-zero fee applies the correction on a stale
  base. A non-zero fee therefore falls back rather than being simulated
  inconsistently (defect recorded in `TODO.md`). Multi-asset portfolios (B5)
  and Part 49 leverage (`loan_draw_rate > 0`, C4) are also out of scope and
  fall back.
- Validation in `tests/unit/strategies/test_numba_buy_and_hold.py`: closed-form
  flat-market and zero-withdrawal hand calculations, a drift-vs-rebalanced
  check, an independent Decimal unit-tracking recurrence across horizons and
  allocations, depletion-boundary cases, batch sequential/parallel equivalence,
  a differential against the legacy buy-and-hold pipeline (fee = 0) anchored to
  hand-derived terminal values, per-context `final_value_target`, eligibility
  (fee, mismatch, three-asset, constant-allocation exclusions), grouping
  (shared trajectory, distinct allocations, distinct datasets), and AUTO routing
  (including a mixed-plan negative case).
- **Known limitation:** buy-and-hold with a non-zero fee is unsupported. The
  legacy pipeline that contained the stale-base defect was deleted in D4.3;
  non-zero-fee buy-and-hold now raises `UnsupportedConfigurationError` rather
  than running an incorrect or approximated recurrence.
- All quality gates pass: ruff, mypy, pytest (unit, infrastructure, integration,
  contract).

### Known Limitations

1. **Workbook recalculation not completed** — LibreOffice headless timed out;
   validation uses pre-calculated saved workbook values.
2. **Reference oracle divergence** — `tools/ern/reference_oracle.py` uses
   multiplicative fee + beginning-of-month withdrawals (matches published
   Table 1); `workbook_oracle.py` uses additive fee + beginning-of-month
   withdrawals (matches workbook formulas). Documented in §1.4.
3. **Glidepath methodology remains unspecified** — the Numba glidepath
   recurrence is not workbook-aligned, and no coherent extension specification
   exists yet (§3 capability #4).
4. **Multi-asset support is policy-dependent** — explicit N-asset allocations
   are supported for fixed-real only. Nominal, escalating, Part 49 debt, and
   Part 52 retain the two-asset form; explicit multi-asset configurations are
   rejected with `UnsupportedConfigurationError`.
5. **CLI routing is unified** — D5a removed the legacy flags and routed
   `run`/`compare`/`optimize`/Part 3 through explicit FAST with mandatory Numba.
6. **Buy-and-hold non-zero fee is unsupported on Numba** — it fails explicitly;
   no approximation or legacy fallback is used.
7. **No legacy fallback exists** — AUTO and explicit FAST both reject
   ineligible contexts with `UnsupportedConfigurationError`.

---

## Appendix A — Current verified facts

- `ExecutionBackend.FAST` is the only backend value. AUTO dispatch and explicit
  FAST both route through the dedicated Part 52, Part 49, Part 49 buy-and-hold,
  or generic Numba executors.
- No production path constructs a legacy Decimal engine, Decimal fast path, or
  pipeline-step chain. The legacy modules and backend values were deleted in
  D4.3.
- Unsupported workloads raise `UnsupportedConfigurationError`. A missing Numba
  installation raises `ModuleNotFoundError` with `pip install fbf-core[numba]`
  guidance.
- Numba executors return empty timelines by default and materialize monthly
  results only with `materialize_timeline=True`.
- `iter_execute_study_plan()` executes plans lazily in cohort-aligned slices;
  `execute_study_plan()` rejects materialized plans above the configured unit
  limit.
- Debt aggregation reads monthly `debt_snapshot` values from materialized
  timelines.
- The workbook uses an additive fee (`weighted_return - fee/12`) with
  beginning-of-month withdrawals and T terms. `tools/ern/workbook_oracle.py`
  encodes that methodology.
- `tools/ern/reference_oracle.py` uses a multiplicative fee, beginning-of-month
  withdrawals, and T+1 terms, matching the historical published ERN results.
  It is independent of production code and must remain untouched.
- The observed full-grid divergence between workbook and published oracles is
  explained by the documented T vs T+1 and fee-convention differences.
- `fbf-cli` and `fbf-ui` depend on `fbf-core[numba]>=0.3.0,<0.4.0` and use
  explicit FAST.
- `fbf-cli` routes `run`, `compare`, `optimize`, and Part 3 through FAST and
  imports the Tier 2 `fbf.core.research` facade for `run`.

## Appendix B — Capability classification summary

- **Class 1 (already supported by Numba):** 1, 2, 3, 5, 7, 9, 10, 11, 12, 13, 19.
- **Class 2 (partial):** 4, 6, 8, 14, 18, 20.
- **Class 3 (not supported):** 16, 17, 21.
- **Class 4 (specialized):** 15, 22, 25.
- **Class 5 (obsolete/redundant):** 23, 24.
