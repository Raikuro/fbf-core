# Roadmap: Migration to a Single Numba Execution Engine

**Status:** Complete. Phases A, B, C, and D are complete, including D4.3
legacy-engine deletion; D5a and D5b are complete. Numba is the sole production
simulation engine, `ExecutionBackend.FAST` is the only backend value, Core is
`0.3.0`, and consumer pins are updated. The independent historical oracle
(`tools/ern/reference_oracle.py`) is preserved (see §9).
**Scope:** FBF Core execution layer (`src/fbf/core/execution/`).
**Objective:** Make Numba the sole simulation engine, delete the legacy
Reference execution stack, and preserve `tools/ern/reference_oracle.py` as the
independent historical published-ERN oracle.

> This document records the completed migration plan and the deletion gates
> that governed it. Historical phase sections describe the pre-deletion state;
> current architecture and surfaces are described in §§1–2, §7.2, and §§9–10.

---

## 1. Objective and Target Architecture

### 1.1 Objective

1. Numba is the sole execution engine for simulation workloads.
2. No production path depends on the legacy Reference execution stack.
3. Unsupported workloads raise `UnsupportedConfigurationError`; there is no
   fallback engine.
4. The legacy Reference engine and its redundant abstractions are deleted.
5. `tools/ern/reference_oracle.py` remains untouched as an independent
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
  4. Every unit generic-Numba-eligible → `NumbaSimulationExecutor`
     (fixed-real, constant-nominal, escalating, buy-and-hold, glidepath, and
     combined glidepath + escalating families may be mixed in one plan).
  5. Otherwise → `UnsupportedConfigurationError`.
- Explicit FAST applies the same families with additional mixed-plan checks:
  a plan containing Part 52 units must be entirely Part 52-eligible; likewise
  for Part 49. Unsatisfied plans raise `UnsupportedConfigurationError`.
- There is no Decimal, reference, or pure-Python simulation fallback.

### 2.2 Executors

| Executor | File | Eligible workloads | Ineligible handling |
|----------|------|--------------------|---------------------|
| `NumbaSimulationExecutor` | `strategies/numba_executor.py` | Generic fixed-real (including explicit N-asset allocations), constant-nominal, escalating, buy-and-hold (including non-zero expense ratios), glidepath, and combined glidepath + escalating families | Raises `UnsupportedConfigurationError`; no fallback executor |
| `Part49NumbaExecutor` | `strategies/part49_numba_executor.py` | Constant allocation + `Part49WithdrawalPolicy`, 2 assets, zero fee, debt/LTV supported | Raises `UnsupportedConfigurationError` |
| `Part52NumbaExecutor` | `strategies/part52_numba_executor.py` | Constant allocation + `Part52WithdrawalPolicy`, 2 assets, interest-rate source, supported additive fee | Raises `UnsupportedConfigurationError` |
| `Part49BuyAndHoldNumbaExecutor` | `strategies/part49_buy_and_hold_numba_executor.py` | Buy-and-hold + `Part49WithdrawalPolicy`, 2 assets, zero fee, debt/LTV supported | Raises `UnsupportedConfigurationError` |

`SimulationExecutor` (`pipeline/executor.py`) is an abstract application-layer
contract. `parallel_executor.py` exposes a low-level `parallel_execute()` helper
used by Core equivalence tests; the high-level API does not expose parallel
execution.

### 2.3 Shared eligibility and grouping

`strategies/eligibility.py` owns the shared predicates and trajectory helpers:
`is_constant_allocation_eligible`, `_weights_by_class`, dataset identity/cluster/group
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
| `is_constant_allocation_eligible` | `strategies/eligibility.py` | Constant allocation + monthly fixed-real withdrawal, horizon ≥ 1, dataset ≥ horizon; either exactly 2 holdings with one equity or an explicit allocation mapping covering held classes |
| `_is_constant_nominal_eligible` | `strategies/numba_executor.py` | Constant allocation + monthly constant withdrawal, horizon ≥ 1, dataset ≥ horizon, 2 holdings, one equity |
| `_is_escalating_eligible` | `strategies/numba_executor.py` | Constant allocation + escalating withdrawal (monthly or annual), horizon ≥ 1, dataset ≥ horizon, 2 holdings, one equity, `v0 == initial_wealth` |
| `_is_glidepath_escalating_eligible` | `strategies/numba_executor.py` | Glidepath + escalating withdrawal (monthly or annual), horizon ≥ 1, dataset ≥ horizon, 2 holdings, one equity, `v0 == initial_wealth`; uses escalating timing with the glidepath's monthly or annual cadence |
| `_is_buy_and_hold_eligible` | `strategies/numba_executor.py` | Buy-and-hold + monthly fixed-real, horizon ≥ 1, dataset ≥ horizon, 2 holdings, one equity, `v0 == initial_wealth`; expense ratio supported with the workbook additive convention |
| `_is_glidepath_eligible` | `strategies/numba_executor.py` | Glidepath + monthly fixed-real, 2 holdings, one equity, `v0 == initial_wealth` |
| `is_part52_eligible` | `strategies/part52_numba_executor.py` | Constant allocation + monthly Part 52 withdrawal, 2 holdings, one equity, interest-rate source, supported additive fee |
| `is_part49_eligible` | `strategies/part49_numba_executor.py` | Part 49 withdrawal, 2 assets, monthly frequency, zero fee, debt/LTV fields, interest-rate source |
| `is_part49_buy_and_hold_eligible` | `strategies/part49_buy_and_hold_numba_executor.py` | Buy-and-hold + Part 49 withdrawal, 2 assets, zero fee, debt/LTV fields, interest-rate source |

**Multi-asset status:** explicit N-asset allocations are supported by the
generic fixed-real family. Constant-nominal, escalating, Part 49 debt, and
Part 52 retain the two-asset form; explicit multi-asset configurations are
rejected rather than routed to another engine. Combined glidepath + escalating
is also two-asset only.

**Withdrawal-frequency status:** the generic fixed-real, constant-nominal,
buy-and-hold, and fixed-real glidepath kernels, plus the Part 49 and Part 52
debt kernels, implement monthly withdrawals only. An annual withdrawal policy
is rejected with `UnsupportedConfigurationError` rather than executed as
monthly. Escalating withdrawals (including combined glidepath + escalating) and
the deterministic kernel support both monthly and annual frequency.

---

## 3. Capability and Migration Matrix

Classification key:
**1** = implemented and supported in the delivered architecture;
**2** = implemented with a documented scope limitation or pending canonical validation;
**3** = not implemented;
**4** = specialized dedicated path or post-processing layer;
**5** = obsolete/removed.

| # | Capability | Current implementation (file:symbol) | Class | Delivered support | Gap | Required migration | Tests / consumers | Blockers | Acceptance criteria |
|---|------------|--------------------------------------|:----:|-------------------|-----|--------------------|-------------------|----------|---------------------|
| 1 | Fixed-real withdrawals (workbook SCR) | `FixedRealWithdrawalPolicy` (`domain/policies/concrete.py`) | 1 | `_process_static_group` (`numba_executor.py`) selects the workbook path; `_simulate_trajectory_workbook` and `_compute_workbook_scr` (`numba_kernel.py`) implement withdraw-before-growth and additive fee; no fallback | Monthly frequency only; annual fixed-real withdrawals are rejected. | None | `tests/unit/strategies/test_numba_executor_differential.py`, `tests/unit/execution/test_workbook_outcome_contract.py`, `tests/unit/execution/test_fast_backend_strictness.py`, `tests/integration/test_numba_e2e.py` | None | SCR and trajectory match the independent workbook recurrence; depletion month is trajectory-derived |
| 2 | Constant nominal withdrawals | `ConstantWithdrawalPolicy` (`domain/policies/concrete.py`); `_simulate_trajectory_constant_nominal` (`numba_kernel.py`) | 2 | `_is_constant_nominal_eligible` / `_process_constant_nominal_group` (`numba_executor.py`); value-scaled recurrence with additive fee | Two-asset constant allocation only; monthly frequency only (annual rejected); glidepath + constant-nominal is rejected. The dedicated independent numerical recurrence was not retained after D4.3; current coverage is routing and mixed-family execution | None for `ConstantAllocationPolicy`; add dedicated independent numerical coverage if required | `tests/unit/execution/test_fast_backend_strictness.py`, `tests/unit/strategies/test_multi_asset_allocation.py` | None | Routing, eligibility, and mixed-family execution pass; dedicated independent numerical recurrence is not currently pinned |
| 3 | Constant allocation weights | `ConstantAllocationPolicy` (`domain/policies/concrete.py`) | 1 | `resolve_target_weights` and `_weights_by_class` (`strategies/eligibility.py`) drive every Numba kernel; fixed-real supports the scalar two-asset form and explicit N-asset `allocations` | Other withdrawal families remain scalar two-asset (see #6) | None | `tests/unit/domain/test_multi_asset_allocation.py`, `tests/unit/strategies/test_multi_asset_allocation.py`, `tests/unit/execution/test_backend_strategy_matrix.py` | None | Scalar and explicit-allocation weight resolution is covered; unsupported forms fail closed |
| 4 | Time-varying weights / glidepaths (ERN dynamic extension) | `GlidepathAllocationPolicy` (`domain/policies/glidepath.py`) | 2 | `_is_glidepath_eligible`, `_compute_equity_weight_sequence`, `_process_glidepath_group` (`numba_executor.py`); `compute_growth_factors_varying_weights_batch` (`numba_kernel.py`) | Shared workbook mechanics are aligned: base row, `horizon - 1` withdraw/grow periods, terminal compounding, additive fee. ERN active/passive weights and cadence are intentional extensions. Fixed-real glidepath withdrawals are monthly only; annual withdrawal frequency is rejected (allocation cadence remains monthly/annual). Canonical Part 19/20 E2E is pending | None for implementation; canonical Part 19/20 E2E validation when authorized | `tests/unit/strategies/test_numba_glidepath_workbook.py`, `tests/unit/domain/test_glidepath_annual_cadence.py`, `tests/integration/test_glidepath_trajectory.py` | Workbook defines only its fixed linear glidepath; canonical E2E not re-run | Withdraw-before-growth, terminal compounding, annual/monthly cadence, and trajectory-depletion success are covered by independent tests |
| 5 | Two-asset portfolios | `simulation_context` holdings; `strategies/eligibility.py` | 1 | All generic and dedicated Numba kernels consume two-asset equity/bond portfolios | None | None | `tests/unit/strategies/test_numba_differential.py`, `tests/unit/execution/test_backend_strategy_matrix.py` | None | Two-asset eligibility and execution are covered across policy families |
| 6 | Multi-asset portfolios (3+) | `ConstantAllocationPolicy.allocations`; `resolve_target_weights`; `_weights_by_class` | 2 | Explicit N-asset fixed-real support; growth factors are N-asset; no legacy form | Nominal, escalating, Part 49 debt, and Part 52 remain two-asset and reject explicit allocations with `UnsupportedConfigurationError` | None; expand only if a consumer requires N-asset in another family | `tests/unit/domain/test_multi_asset_allocation.py`, `tests/unit/strategies/test_multi_asset_allocation.py` | Policy-dependent scope | Independent N-asset Decimal oracle and differential tests pass for fixed-real; other families reject explicit N-asset |
| 7 | Expense ratios / fee application (workbook additive) | `_compute_growth_factors_numpy` and `compute_growth_factors_varying_weights_batch` (`numba_kernel.py`) | 2 | Additive fee (`weighted_return - fee/12`) is embedded in generic fixed-real, constant-nominal, escalating (including combined glidepath + escalating), buy-and-hold, glidepath, and Part 52 growth factors | Part 49 debt and Part 49 buy-and-hold support zero fee only and reject non-zero fees; the deleted legacy fee model is not reproduced | None; retain zero-fee scope for Part 49 unless a consumer requires legacy fee semantics | `tests/unit/strategies/test_numba_executor_differential.py`, `tests/unit/strategies/test_numba_glidepath_workbook.py`, `tests/unit/strategies/test_numba_glidepath_escalating.py`, `tests/unit/strategies/test_numba_buy_and_hold.py`, `tests/unit/strategies/test_part52_growth_factor_fee.py`, `tests/integration/test_part49_numba_executor.py` | Study-specific fee scope | Workbook additive fee is validated for supported paths; unsupported Part 49 non-zero fees are rejected explicitly |
| 8 | Debt state + loan drawdown | `Part49NumbaExecutor`; `Part52NumbaExecutor`; `Part49BuyAndHoldNumbaExecutor`; `_simulate_part49`, `_simulate_part52`, `_simulate_part49_buy_and_hold` (`numba_kernel.py`) | 1 | Part 52 drawdown-triggered borrowing and Part 49 fixed `loan_draw_rate` are implemented on Numba with no fallback | Part 49 and Part 52 require monthly frequency; Part 49 also requires zero fee and two assets; Part 52 requires an interest-rate source | None | `tests/integration/test_part52_numba_executor.py`, `tests/integration/test_part49_numba_executor.py`, `tests/integration/test_part49_buy_and_hold_numba_executor.py`, `tests/unit/execution/debt_recurrence_reference.py` | Supported-scope constraints above | Part 52 and Part 49 debt paths pass Numba execution and independent Decimal recurrence tests |
| 9 | Repay at fresh ATH | `_simulate_part52` (`numba_kernel.py`) | 1 | Fresh-ATH repayment branch is implemented in the Part 52 kernel | None for Part 52 | None | `tests/integration/test_part52_compound_drawdown.py`, `tests/integration/test_part52_numba_executor.py` | None | Borrow/repay ordering and loan balances match independent recurrence tests |
| 10 | Floating-rate interest (FFR) | `_compute_monthly_rates` (`part52_numba_executor.py`); `_simulate_part52` (`numba_kernel.py`) | 1 | CPI-adjusted monthly rate computation and per-month interest accrual are implemented in the Part 52 path | None for Part 52 | None | `tests/integration/test_part52_ffr_floating_rate.py`, `tests/unit/execution/test_ffr_rate_alignment.py` | None | FFR schedule and fixed-rate fallback tests pass |
| 11 | LTV evaluation / enforcement | `_simulate_part52`, `_simulate_part49`, `_simulate_part49_buy_and_hold` (`numba_kernel.py`) | 1 | LTV evaluation, liquidation, and terminal failure states are implemented in all debt kernels | None for supported debt configurations | None | `tests/integration/test_part52_numba_executor.py`, `tests/integration/test_part49_numba_executor.py`, `tests/integration/test_part49_buy_and_hold_numba_executor.py` | None | LTV terminal-state and enforcement tests pass |
| 12 | Horizon derivation | `_trajectory_clusters` (`strategies/eligibility.py`); group keys and executors | 1 | Identity-prefix clustering and per-executor derivation keys derive shorter horizons from a longest evaluated path | None | None | `tests/unit/strategies/test_numba_executor_differential.py`, `tests/integration/test_part52_numba_executor.py`, `tests/unit/strategies/test_numba_glidepath_escalating.py` | None | Derivation reports and differential results match direct evaluation |
| 13 | FV target deduplication | `_apply_fv_check` (`numba_executor.py`, `part52_numba_executor.py`, `part49_numba_executor.py`) | 1 | `final_value_target` is excluded from trajectory keys and applied per context after the shared path | None | None | `tests/unit/execution/test_trajectory_deduplication.py` | None | Distinct targets share one path and retain per-target success classification |
| 14 | Cohort + slice execution | `iter_cohort_slices` (`execution/slicing.py`); `iter_execute_study_plan` (`execution/__init__.py`) | 1 | Lazy cohort-aligned slices; whole-plan materialization guard; Core slices consumed by incremental SQLite persistence | Slice target is a memory-control target, not a hard bound; consumers must release slices | None | `tests/unit/execution/test_plan_slicing.py`, `tests/unit/execution/test_streaming_execution.py`, `tests/infrastructure/test_streaming_persistence.py`, `tests/oracle/ern/test_streaming_aggregate.py` | Largest cohort size and retained consumer state still affect residency | Streaming, whole-plan, and persisted aggregates agree; per-slice failure metadata is preserved |
| 15 | Deterministic execution | `execute_deterministic_trajectory` (`execution/deterministic.py`); `simulate_deterministic_two_asset` (`strategies/deterministic_kernel.py`) | 4 | Dedicated two-asset unit-tracking Numba kernel: annual/monthly rebalance, intra-year drift, workbook additive fee, annual/monthly withdrawals, failure signalling; unsupported configurations raise `UnsupportedConfigurationError` | Multi-asset, Part 49/52, and buy-and-hold are outside the deterministic kernel's supported scope; there is no fallback and no fee rejection | None for supported two-asset policies | `tests/unit/execution/test_deterministic.py`, `tests/unit/execution/test_deterministic_kernel.py`, `tests/unit/research/test_part20_experiment_e.py` | Supported-scope constraints above | Deterministic contract preserved; independent Decimal differential and corrected Experiment E values pass |
| 16 | Full monthly trajectory | `execution/strategies/trajectory.py`; Numba executors | 1 | Optional `SimulationTimeline` materialization for generic and dedicated Numba executors | Grid-scale materialization requires streaming slices | None | `tests/unit/execution/test_timeline_materialization.py`, `tests/integration/test_numba_e2e.py` | Memory and serialization cost | Timeline values match independent recurrence and executor statistics |
| 17 | Result persistence | `persistence/studies/sqlite/codecs.py`, `schema.py`, `sqlite_repository.py` | 1 | Schema v4 incremental writer with per-slice transactions, attempt tokens, explicit status, completion verification, and completed-result filtering | Recovery is explicit by design; there is no automatic age-based recovery | None | `tests/infrastructure/test_streaming_persistence.py`, `tests/infrastructure/test_sqlite_persistence.py`, `tests/infrastructure/test_schema_migration.py` | None | Round-trip preserves statistics and timelines; interrupted attempts remain invisible until explicitly completed |
| 18 | Memory-bounded large grids | `execution/slicing.py`; `execution/__init__.py`; `tests/benchmarks/test_memory_bounded_execution.py` | 1 | Streaming API bounds residency by slice target; D2 full-grid streaming validation is recorded in §9 | Slice target is not a hard bound; release slices before advancing | None | `tests/benchmarks/test_memory_bounded_execution.py`, `tests/oracle/ern/test_streaming_aggregate.py` | None | D2 full-grid streaming validation is recorded; the manual memory benchmark remains opt-in |
| 19 | Buy-and-hold allocation | `BuyAndHoldAllocationPolicy` (`domain/policies/concrete.py`); `_simulate_trajectory_buy_and_hold` (`numba_kernel.py`); `_is_buy_and_hold_eligible` (`numba_executor.py`) | 1 | Generic two-asset unit-tracking kernel with endogenous drift and workbook additive fee; Part 49 leveraged buy-and-hold uses `Part49BuyAndHoldNumbaExecutor` | Generic buy-and-hold is two-asset and monthly-frequency only (annual rejected); Part 49 leveraged buy-and-hold remains zero-fee and monthly-only; no canonical ERN buy-and-hold oracle | None | `tests/unit/strategies/test_numba_buy_and_hold.py`, `tests/integration/test_part49_buy_and_hold_numba_executor.py` | Part 49 zero-fee scope; no canonical buy-and-hold oracle | Zero- and non-zero-fee generic differentials pass; Part 49 supported scope passes |
| 20 | Escalating withdrawal | `EscalatingWithdrawalPolicy` (`domain/policies/escalating_withdrawal.py`) | 2 | `_simulate_trajectory_escalating` (`numba_kernel.py`); `_process_escalating_group` and `_process_glidepath_escalating_group` (`numba_executor.py`); deterministic Experiment E remains separate | General path supports constant allocation and combined glidepath + escalating; canonical Part 20 E2E is pending | None for implementation; canonical Part 20 E2E validation when authorized | `tests/unit/strategies/test_numba_escalating.py`, `tests/unit/strategies/test_numba_glidepath_escalating.py`, `tests/unit/execution/test_deterministic_kernel.py` | Deterministic annual contract remains separate; combined cadence is monthly/annual | Combined path matches independent Decimal recurrence for both cadences and withdrawal frequencies; deterministic Experiment E matches its own contract; canonical E2E pending |
| 21 | Supplemental cash flow | Not implemented | 3 | No production implementation | Additional external cash flow | Add only if a real consumer activates it | None | No active consumer | Not applicable until a consumer exists |
| 22 | CAPE-regime aggregation | `research/cape_aggregation.py`; `research/part20_aggregation.py`; `domain/policies/cape_regime.py` | 4 | Post-processing layer over Numba results; no simulation-kernel involvement | Canonical Part 20 E2E is pending | None | `tests/unit/research/test_part20_*`, `tests/unit/research/test_cape_classification.py`, `tests/integration/test_part20_e2e_audit.py` | Aggregation, not simulation | CAPE classification and aggregation tests pass; canonical Part 20 E2E pending |
| 23 | `ReferenceSimulationExecutor` wrapper | Removed in D4.3 | 5 | Obsolete; Numba executors own derivation and execution | None | None | No current references | None | No production references; boundary tests pass |
| 24 | `execute_reference()` public API | Removed in D4.3 | 5 | Obsolete; no replacement API | None | None | No current references | None | No production references; public facade tests pass |
| 25 | `ExpenseDeductionStep` | Removed in D4.3 | 5 | Obsolete; additive fee lives in Numba growth factors; Part 49 retains zero-fee scope | None | None | No current references | None | No references remain; fee contracts are documented in §§1.4 and 5.2 |

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
   allocations, Part 52, and glidepaths. Additive fee is embedded in the growth factors
   (`g_m' = g_m - fee/12`, matching the workbook's `1 + r - f/12`), not the
   multiplicative form. See the B1 milestone below. Glidepath fee alignment is
   implemented in the varying-weight growth factors and validated under
   capability #4.

2. **B2 — Constant nominal withdrawal.** ✅ Implemented for
   `ConstantAllocationPolicy`: value-scaled recurrence
   `V_{m+1} = V_m * (1 - rate/12) * g_m`. Trace the domain model and execution
   order before extending to other allocation policies.

3. **B3 — Escalating withdrawal.** ✅ Implemented for
   `ConstantAllocationPolicy` and, under capability #20, for
   `GlidepathAllocationPolicy`: value-independent annual schedule
   `v0 * withdrawal_rate * (1 + escalation_rate) ** (m // 12)`. The combined
   path uses the escalating timing contract and advances glidepath weights by
   its configured `MONTHLY` or `ANNUAL` cadence. The deterministic adapter
   remains a separate annual workbook contract through D3.

4. **B4 — Buy-and-hold.** ✅ Implemented: a non-rebalancing unit-tracking
   recurrence with explicit specification, including the workbook additive
   expense convention (a simulator extension — the workbook does not define
   buy-and-hold). See the B4 milestone below.

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
   Glidepath fee alignment is implemented in the varying-weight growth factors
   and validated under capability #4.

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
- Dynamic glidepath extension specification documented and validated: shared
  workbook timing/fee mechanics plus the ERN active/passive weight sequence.
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
  **Note:** the Part 19/20 canonical E2E suites have not been re-run after the
  glidepath recurrence correction; that re-validation is pending (see §5.2).
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
- **Part 19/20 (glidepath extension).** The workbooks define the shared
  withdrawal/growth mechanics but not ERN's dynamic glidepath. The extension is
  specified as two separable layers:
  1. **Shared workbook mechanics (validated against both workbooks).** The
     pre-retirement snapshot is the base row and has no withdrawal. Each of the
     `horizon - 1` periods withdraws before growth:
     `P(t) = (P(t-1) - W(t)) * (1 + R(t))`, the final period's return is
     compounded, and the additive fee is embedded as
     `weighted_return - fee/12`. Depletion is reported with the base-row month
     convention (first withdrawal period is month 1).
  2. **ERN-specific weight sequence (simulator extension).** The equity weight
     is `min(start + slope * advancements, end)`. With annual cadence,
     `advancements = m // 12`; with monthly passive mode it is the period index;
     with monthly active mode it is the count of beginning-of-period underwater
     snapshots. The workbook's own glidepath is a fixed 120-month linear
     transition, so it is not used as the ERN weight authority. Success remains
     trajectory depletion; the workbook SCR verdict is defined only for static
     allocations.
  3. **Combined glidepath + escalating (general Numba path).** The combined path
     uses the escalating timing contract (withdraw before growth, escalation at
     `m // 12`, no growth after the final withdrawal) while glidepath weights
     advance at the configured monthly or annual cadence. The deterministic
     Experiment E adapter remains a separate annual workbook contract.
  4. **Canonical E2E validation (pending).** The heavyweight Part 19/20
     canonical E2E suites have not been re-run after the recurrence correction.
     They remain explicitly pending: the independent Decimal differential and
     controlled-trajectory tests validate the shared mechanics and the
     extension, but they do not establish canonical Part 19/20 grid
     equivalence. Historical oracle data and pinned published-ERN expectations
     are unchanged and are not used to validate the new recurrence.

  | Layer | Evidence | Status |
  |-------|----------|--------|
  | Shared workbook mechanics | Workbook formula trace; `test_numba_glidepath_workbook.py` Decimal recurrence | Confirmed |
  | ERN dynamic extension | `test_glidepath_trajectory.py`; S0-F1 timing decision | Specified and unit/integration tested |
  | Combined glidepath + escalating | `test_numba_glidepath_escalating.py` Decimal recurrence | Unit tested |
  | Canonical Part 19/20 E2E | `RUN_ERN_E2E=1` grid suites | **Pending** (not run) |

  CAPE aggregation is unchanged.
- **Buy-and-hold** — no periodic rebalancing.
- **Deterministic trajectory** — checkpoint contract.

Where no independent oracle exists (e.g. Part 52 without a pinned cell table,
Part 49 debt), document the behavioral contract from the existing behavioral
and independent recurrence tests **before** treating the Numba migration as
verified.
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
| Routing | AUTO selects the expected Numba executor; backend × strategy matrix | Keep; naming reflects §1.3 |
| Obsolete implementation equivalence | `FAST == legacy Reference` where methodologies differ | **DELETED** in Phase A (§7.3) |

---

## 6. Dependencies, Risks, and Unresolved Questions

### 6.1 Dependencies

- Numba is an optional install extra (`fbf-core[numba]`) but is mandatory for
  simulation execution. Core has no pure-Python fallback; a missing Numba fails
  explicitly. The CLI declares the extra and uses explicit FAST (D5a).
- Trajectory materialization (#16), cohort-slice dispatch (#14/D2), streaming
  persistence (#17), debt aggregation, and deterministic execution are
  implemented. `iter_execute_study_plan()` bounds residency by slice, and
  persistence consumes released slices.
- No unresolved dependency blocks the single-engine architecture.

### 6.2 Risks

1. **Fee-model divergence.** The deleted legacy `ExpenseDeductionStep` used a
   linear approximation with a timing correction; the canonical workbook uses
   an **additive fee embedded in returns** (`weighted_return - fee/12`). The
   `reference_oracle.py` uses multiplicative fees (its own methodology).
   Fee support must follow the *study's* required model, not a single global
   rule. The workbook additive fee convention is implemented for generic
   fixed-real, constant-nominal, escalating (including combined glidepath +
   escalating), buy-and-hold, glidepath, and Part 52 paths. Part 49 debt and
   Part 49 buy-and-hold retain a zero-fee scope and reject non-zero fees
   explicitly; the deleted legacy fee model is not reproduced.
2. **Methodology drift.** Forcing Part 52 onto the Part 49 recurrence would
   silently change results. Preserve per-study semantics.
3. **Trajectory payload size.** Materializing timelines for the full ERN grid
   is enormous. Whole-plan materialized execution is guarded, and grid-scale
   trajectory work must use cohort-slice dispatch and incremental persistence.
4. **Public API breakage.** D4.3 removed the `DECIMAL_FAST_PATH`/`REFERENCE`
   backend values and the legacy reporting/execution exports, bumped Core to
   `0.3.0`, and updated consumer pins. Future breaking changes still require a
   Core minor-version increment.
5. **CLI routing — resolved by D5a.** The legacy `--reference`, `--fast-path`,
   and `--validate` flags are removed; `run`, `compare`, `optimize`, and Part 3
   use explicit FAST and require `fbf-core[numba]`.

### 6.3 Resolved architectural decisions

1. **Numba dependency:** optional at install time, mandatory for execution;
   Core and CLI fail explicitly rather than falling back.
2. **Backend naming:** `DECIMAL_FAST_PATH` and `REFERENCE` are removed;
   `ExecutionBackend.FAST` is the only backend value.
3. **Legacy public API consumers:** no production consumer remained;
   `execute_reference`, `expected_reference_report`, and
   `reference_month_work` are deleted.
4. **Deterministic adapter:** implemented on the Numba kernel, with no fallback
   engine.
5. **CLI default:** explicit FAST for all execution commands.

### 6.4 Open research-validation question

The authoritative behavioral oracle for Part 52 and debt-aware Part 49 remains
an open research-validation question where no pinned cell table exists. This
does not affect the execution architecture; see `TODO.md`.

---

## 7. File- and Symbol-Level Migration Inventory

> **Historical record.** Sections 7.1–7.1.5 and 8 preserve the migration
> inventory and deletion gate as they stood before D4.3. Pre-deletion symbols,
> files, and fallback descriptions there are not current architecture. See
> §§1–2, §7.2, and §§9–10 for the delivered state.

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
| `src/fbf/core/execution/strategies/numba_kernel.py` | `_simulate_trajectory`, `_simulate_trajectory_end_of_period`, `_simulate_trajectory_workbook`, `_compute_workbook_scr`, `_simulate_part52` | B/C/D | **Workbook SCR COMPLETE**; nominal/escalating/buy-and-hold complete (B2/B3/B4); glidepath uses the workbook recurrence; trajectories (D1); debt snapshots |
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
| `ExecutionBackend` | `execution/__init__.py` | `FAST` is the only backend value; `DECIMAL_FAST_PATH` and `REFERENCE` are removed. |
| `--reference`, `--fast-path` | `fbf-cli/src/fbf/cli/commands/run_command.py` | Removed by D5a. |
| `--validate` | same file | Removed by D5a. |
| `compare` / `optimize` execution | `compare_command.py`, `optimize_command.py` | D5a routes both through explicit FAST `execute_study_plan`. |
| Part 3 execution/imports | `run_command.py` | D5a uses the Tier 2 `fbf.core.research` facade and explicit FAST. |
| CLI packaging | `fbf-cli/pyproject.toml` | D5a declares `fbf-core[numba]`, making Numba mandatory for the CLI; Core has no fallback. |
| Persistence guard | `run_command.py` | D5a removed the flag and persists explicit FAST runs with `materialize_timeline=True`. |
| `ExecutionOptions` | `execution/__init__.py` | `summary_only`, `materialize_timeline`, `glidepath_gf_cache` |

### 7.3 Test inventory

> **Historical migration inventory.** Statuses and paths below describe the
> test plan and its state during the migration. Entries that list deleted tests
> as passing or retained refer to their pre-D4.3 status. Current tests are
> authoritative.

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

**D5a CLI evidence.** D5a is complete in `fbf-cli`: all execution commands use
`ExecutionOptions(backend=ExecutionBackend.FAST)`; `run`, `compare`, `optimize`,
and Part 3 do not use the deleted legacy runner; missing Numba and unsupported
configurations fail explicitly; and CLI production imports resolve through the
Tier 1/Tier 2 Core facade. CLI contract tests cover these boundaries.

---

## 8. Final Deletion Gate for the Legacy Reference Engine

**Status:** Satisfied by D4.3. This gate is retained as the audit record for
the deletion decision.

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

The milestone table and completed-milestone log record evidence at the time of
each commit. Deleted file paths in historical entries are not current
implementation references; the current inventory is §3.

| Milestone | Status | Evidence | Commit | Notes |
|-----------|--------|----------|--------|-------|
| A1: CLI execution routing | ✅ Complete | Explicit FAST for `run`/`compare`/`optimize`/Part 3; legacy flags removed; `fbf-core[numba]` required | 3181bf5 (fbf-cli) | Completed by D5a |
| A2: Part 52 Numba test coverage | ✅ Complete | 12 new tests exercise Numba path | f427202 | Tests prove eligible configs execute on Numba without fallback |
| A3: Document legacy consumers | ✅ Complete | §1.3 | b4ff4ad | Verified via grep |
| E1: Strict Numba FAST execution | ✅ Complete (enabler) | `test_fast_backend_strictness.py`; explicit FAST rejects ineligible contexts; AUTO unchanged | f28f571 (fbf-core) | Hardens §2.1/§2.2; not a roadmap phase completion |
| E2: Public Part 3 research facade | ✅ Complete (enabler) | `fbf.core.research` Tier 2; `tests/contract/test_research_public_api.py` | d44213c (fbf-core) | Prerequisite for D5a; CLI still imports Tier 3 until D5a |
| B1: Expense ratios (additive fee) | ✅ Complete (audited & fixed) | `numba_kernel.py`, `part52_numba_executor.py`, `test_numba_executor_differential.py`, `test_numba_glidepath_workbook.py`, `test_numba_buy_and_hold.py`, `test_part52_growth_factor_fee.py` | 8dfbf24 (audited) | Static, constant-nominal, escalating (including combined glidepath + escalating), buy-and-hold, glidepath, and Part 52 use the additive fee; Part 49 debt/buy-and-hold remain zero-fee; **Critical cache key + fee pass-through bug fixed** |
| Capability #4: Glidepath shared mechanics | ✅ Complete (E2E pending) | `numba_executor.py` `_process_glidepath_group`; `test_numba_glidepath_workbook.py`; `test_glidepath_trajectory.py` | See git history | Workbook recurrence applied (base row, `horizon - 1` periods, terminal compounding, additive fee); ERN active/passive weight sequence retained and specified in §5.2; canonical Part 19/20 E2E not re-run |
| Capability #20: Glidepath + escalating | ✅ Complete (canonical E2E pending) | `numba_executor.py` `_process_glidepath_escalating_group`; `test_numba_glidepath_escalating.py` | See git history | General Numba combined path uses escalating timing and glidepath cadence; fixed-real workbook timing and the deterministic Experiment E contract are unchanged; canonical Part 20 E2E not re-run |
| B2: Constant nominal withdrawal | ✅ Complete (implementation; validation gap documented in §3) | `numba_kernel.py`, `numba_executor.py`, `test_fast_backend_strictness.py` | 00b5770 | Recurrence `V_{m+1}=V_m*(1-rate/12)*g_m` implemented with the additive fee; current coverage is routing and mixed-family execution; the dedicated independent numerical differential was removed with the legacy engine |
| Numba cache/dataset identity fix | ✅ Complete | `test_numba_executor_differential.py`, `test_part52_numba_executor.py` | 99aa5a4 | Dataset-identity tokens + identity-prefix clustering in both Numba executors |
| B2 audit: Part 52 derivation key | ✅ Complete | `test_part52_numba_executor.py` | a00c0ec | Monthly-rate prefix guard added; per-context FV dims (`initial_wealth`, `final_value_target`) decoupled from grouping |
| B3: Escalating withdrawal | ✅ Complete (including capability #20) | `numba_kernel.py`, `numba_executor.py`, `test_numba_escalating.py`, `test_numba_glidepath_escalating.py` | 65f1f67; combined path see git history | Value-independent annual schedule; general Numba glidepath + escalating now uses the escalating timing contract with `MONTHLY`/`ANNUAL` glidepath cadence; deterministic annual glidepath + escalating remains separate under D3 |
| Buy-and-hold initial allocation | ✅ Complete (correction) | `default_pipeline.py`, `allocation_decision_step.py`, `portfolio_rebalance_step.py`, `test_part49_buy_and_hold.py` | 3f2f788 | Buy-and-hold applied the 50/50 default; allocation now applied once in period 0 |
| B4: Buy-and-hold | ✅ Complete (non-debt, additive fee) | `numba_kernel.py`, `numba_executor.py`, `execution/__init__.py`, `test_numba_buy_and_hold.py` | 5179a3b (B4); see git history for the fee extension | Unit-tracking kernel with workbook additive fee; weight drift uses the gross blended return; Part 49 leverage → C4, multi-asset → B5 |
| B5: Multi-asset | ✅ Complete (fixed-real scope) | `domain/policies/concrete.py`, `execution/strategies/eligibility.py`, `numba_executor.py`, `test_multi_asset_allocation.py` | 85d72582f047279d5d9c42ca3f3cb0e3d9099c7b | Explicit N-asset `allocations` and a single `resolve_target_weights`; nominal, escalating, Part 49, and Part 52 reject explicit allocations with `UnsupportedConfigurationError` |
| C1: Part 52 Numba-only | ✅ Complete | `part52_numba_executor.py`, `execution/__init__.py`, `test_part52_dispatch_contract.py` | 2343c225278d1e02722a9567ab911e835215b6ff | Eligible Part 52 runs on Numba; explicit FAST on an ineligible Part 52 workload raises `UnsupportedConfigurationError` (no silent fallback) |
| C2: Part 52 fee behavior | ✅ Complete (B1) | `_compute_growth_factors_numpy` (`numba_kernel.py`) fee passed by `part52_numba_executor.py`; `TestPart52ExpenseRatioSupport`, `TestPart52ExpenseRatioIndependentValidation` | 8dfbf24 (audited) | Additive fee `g_m = Σ_j w_j·P_{j,m}/P_{j,m-1} − fee/12` embedded in kernel growth factors |
| C3: Part 49 debt migration | ✅ Complete | `part49_numba_executor.py`, `test_part49_numba_executor.py`; production flag propagation covered in `test_research_layer_debt_flow.py` | 5d5a569 | 10,434-unit Part 49 full-path E2E passed with `ExecutionBackend.FAST` and a concrete `Part49NumbaExecutor.execute` call-count assertion. All 6 cells × 1,739 cohorts executed; the non-leverage historical comparison against the pinned published oracle passes, and leverage directionality holds. Production conformance uses the workbook-derived oracle. |
| C4: Part 49 buy-and-hold | ✅ Complete (supported scope, Option B) | `part49_buy_and_hold_numba_executor.py`, `test_part49_buy_and_hold_numba_executor.py`; production flag propagation covered in `test_research_layer_debt_flow.py` | 6abda00 | Supported scope: Part 49 buy-and-hold, two assets, zero fee. Option B approved after independent verification of synthetic production-path dispatch, independent Decimal differential, legacy differential, LTV, and real-rate tests. The C4 gate is independent of C3; the 10,434-unit constant-allocation test is unrelated. This closure does not establish real-data canonical-scale equivalence, 1,739-cohort coverage, or a canonical ERN buy-and-hold oracle. |
| C5: LTV terminal state | ✅ Complete | `numba_kernel.py`, `part49_numba_executor.py`, `part49_buy_and_hold_numba_executor.py`, `part52_numba_executor.py`; `test_part49_numba_executor.py`, `test_part49_buy_and_hold_numba_executor.py`, `test_part52_numba_executor.py` | b5ad4a2, 5d5a569, 6abda00 | Part 49 debt, Part 49 buy-and-hold, and Part 52 Numba kernels emit `margin_call_terminal` and match Decimal/legacy references. Targeted Numba executor and debt flag propagation tests pass. C3 and C4 closure are governed by their separate gates. |
| D1: Trajectory materialization | ✅ Complete | `execution/strategies/*`, `execution/strategies/trajectory.py`, `test_timeline_materialization.py` | 46687ce | Optional flag; use D2 streaming at grid scale |
| D2: Cohort-slice for memory | ✅ Complete | `execution/slicing.py`, `execution/__init__.py`, `optimization/part52_evaluator.py`, `research/part49_aggregation.py`, `persistence/studies/sqlite/sqlite_repository.py`, `tests/oracle/ern/test_streaming_aggregate.py` | a46ab2c | Streaming API + guard + consumer migration + incremental persistence + CLI persistence wiring complete. Historical full-grid validation before D4.3: 313,020 units through `iter_execute_study_plan` in 16 summary-only slices; peak RSS 451.3 MiB on the then-current REFERENCE backend and 582.2 MiB on FAST, under 16 GB. Streaming matched whole-plan on every cell, both then-current backends agreed, and the production grid matched `workbook_oracle_table.csv` 180/180 exactly. The routine regression streams a four-cell production subset across all 1,739 cohorts, persists/reloads it, and matches streaming, whole-plan, and persisted per-cell aggregates to the workbook oracle with exact Decimal equality. The 13/180 published-oracle differences are documented as the T vs T+1 historical divergence, not a production failure. The routine regression is committed in `9f00a89` as Step A and was validated against both the current workspace and an isolated `HEAD + A` worktree. |
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
- **Scope note:** escalating withdrawal was initially migrated for
  `ConstantAllocationPolicy` in the general Numba executor. Capability #20 later
  extended the general path to `GlidepathAllocationPolicy` using the escalating
  timing contract and the glidepath's own cadence. The deterministic Experiment
  E path remains separate on the dedicated D3 kernel (capability #15), which
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
      fee_m = fee_annual / 12
      for m in 0 .. horizon-1:
          if C > V_m: failure at month m
          V_m <- V_m - C
          if m < horizon - 1:
              G = w_m * ge[m] + (1 - w_m) * gb[m]
              w_{m+1} = w_m * ge[m] / G
              V_{m+1} = V_m * (G - fee_m)

  The proportional liquidation used to fund withdrawals is the reference
  behavior for the fee-free case.  The expense term follows the workbook
  additive convention and leaves weight drift on the gross blended return.
- Extended `NumbaSimulationExecutor` with `_is_buy_and_hold_eligible`,
  `_buy_and_hold_group_key` (excludes `initial_wealth` because the withdrawal
  base is `v0`; includes the expense ratio), `_process_buy_and_hold_group`, and
  a per-dataset-token per-asset growth-factor cache (`_bh_growth_cache`).
  Unlike the static/glidepath paths, a single blended growth-factor series
  cannot be precomputed because the weights are path-dependent, so the kernel
  consumes the equity and bond series separately. AUTO backend dispatch now
  routes all-buy-and-hold workloads to `NumbaSimulationExecutor`.
- **Eligibility** requires `BuyAndHoldAllocationPolicy` + `FixedRealWithdrawalPolicy`,
  a two-asset equity/bond portfolio present in the dataset, and
  `v0 == initial_wealth`. Expense ratios are supported: the kernel applies the
  workbook additive convention `blended_gross_return - fee_annual/12` after the
  withdrawal, while weight drift continues to use the gross blended return.
  Multi-asset portfolios (B5) and Part 49 leverage (`loan_draw_rate > 0`, C4)
  remain out of scope and are rejected rather than routed to another engine.
- Validation in `tests/unit/strategies/test_numba_buy_and_hold.py`: closed-form
  flat-market and zero-withdrawal hand calculations, a drift-vs-rebalanced
  check, an independent Decimal unit-tracking recurrence across horizons,
  allocations, and expense ratios (including zero and non-zero fees),
  depletion-boundary cases, additive-vs-multiplicative fee discrimination,
  fee-invariant weight drift, terminal-period behavior, batch
  sequential/parallel equivalence, hand-derived zero- and non-zero-fee
  terminal values, per-context `final_value_target`, eligibility (mismatch,
  three-asset, constant-allocation exclusions), grouping (shared trajectory,
  distinct allocations, distinct fees, distinct datasets), and AUTO/FAST
  routing plus missing-Numba failure behavior.
- All quality gates pass: ruff, mypy, pytest (unit, infrastructure, integration,
  contract).

### Known Limitations

1. **Workbook recalculation not completed** — LibreOffice headless timed out;
   validation uses pre-calculated saved workbook values.
2. **Reference oracle divergence** — `tools/ern/reference_oracle.py` uses
   multiplicative fee + beginning-of-month withdrawals (matches published
   Table 1); `workbook_oracle.py` uses additive fee + beginning-of-month
   withdrawals (matches workbook formulas). Documented in §1.4.
3. **Part 19/20 canonical E2E validation pending** — the glidepath recurrence
   correction is validated by independent Decimal differential and
   controlled-trajectory tests, but the heavyweight canonical Part 19/20 E2E
   suites have not been re-run. Do not treat them as passed until
   `RUN_ERN_E2E=1` validation is performed. See §5.2 for the layer split
   between workbook-confirmed mechanics, the ERN extension, and pending E2E
   validation.
4. **Multi-asset support is policy-dependent** — explicit N-asset allocations
   are supported for fixed-real only. Nominal, escalating, Part 49 debt, and
   Part 52 retain the two-asset form; explicit multi-asset configurations are
   rejected with `UnsupportedConfigurationError`.
5. **CLI routing is unified** — D5a removed the legacy flags and routed
   `run`/`compare`/`optimize`/Part 3 through explicit FAST with mandatory Numba.
6. **No legacy fallback exists** — AUTO and explicit FAST both reject
   ineligible contexts with `UnsupportedConfigurationError`.
7. **Withdrawal frequency is policy-family dependent** — the generic
   fixed-real, constant-nominal, buy-and-hold, fixed-real glidepath, Part 49,
   and Part 52 Numba kernels implement monthly withdrawals only and reject
   annual frequency. Escalating withdrawals (including combined glidepath +
   escalating) and the deterministic kernel support both monthly and annual.
   Annual configurations are rejected explicitly and are never executed as
   monthly.

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
- Numba withdrawal kernels that implement a single monthly schedule reject
  annual frequency explicitly; annual withdrawals are supported only by the
  escalating and deterministic paths.
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

- **Class 1 (implemented and supported):** 1, 3, 5, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19.
- **Class 2 (scope-limited or validation-pending):** 2, 4, 6, 7, 20.
- **Class 3 (not implemented):** 21.
- **Class 4 (specialized dedicated path or post-processing):** 15, 22.
- **Class 5 (obsolete/removed):** 23, 24, 25.
