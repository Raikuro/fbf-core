# Roadmap: Migration to a Single Numba Execution Engine

**Status:** Phase A — Routing & Test Coverage Fixes **IN PROGRESS** 🔄
**Scope:** FBF Core execution layer (`src/fbf/core/execution/`).
**Objective:** Make Numba the sole simulation engine, progressively shrink and
eventually delete the legacy Reference execution stack, and preserve
`tools/ern/reference_oracle.py` as the independent canonical ERN oracle.

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
   implementation for validating canonical ERN workbook replication.

### 1.2 Target architecture

```
YAML
  → StudyConfiguration.from_yaml()
  → build_study_plan() / run_study()
  → execute_study_plan()  (backend dispatch)
  → NumbaSimulationExecutor / Part52NumbaExecutor / unified Numba engine
  → SimulationResult (statistics + optional monthly trajectory)

Independent oracle (never imported by production code):
  tools/ern/reference_oracle.py
```

There is no second generic Decimal engine in the target state.

### 1.3 Naming ambiguity — verified consumers and migration approach

The token **"reference"** currently denotes three different things. They must
not be conflated:

| Term | File / symbol | What it actually is today |
|------|---------------|---------------------------|
| `ExecutionBackend.REFERENCE` | `execution/__init__.py:140`, routed at `:436-439` | **Decimal closed-form fast path** (`FastPathSimulationExecutor`). It is *not* the legacy engine. |
| `ReferenceSimulationExecutor` / `execute_reference()` | `execution/strategies/reference.py:312`, `:455` | The legacy 9-step Decimal pipeline wrapped with horizon derivation and memory-bounded slice dispatch. |
| "the reference engine" (prose) | `_create_default_simulation_executor()` | The actual legacy Decimal engine: the 9/15-step pipeline built in `parallel_executor.py:42` and `default_pipeline.py:53`. |

**Verified consumers (repository-wide search, 2026-10-15):**
- `ExecutionBackend.REFERENCE`: Used in `execution/__init__.py` backend dispatch; `fbf-cli/src/fbf/cli/commands/run_command.py` CLI flag `--reference`; `tests/unit/execution/test_backend_strategy_matrix.py` routing tests; `tests/unit/execution/test_determinism.py` (one test).
- `ReferenceSimulationExecutor`: Exported from `strategies/__init__.py`; used in `tests/unit/execution/test_reference.py`, `tests/unit/execution/test_trajectory_deduplication.py`, `tests/unit/execution/test_backend_strategy_matrix.py` (as `_make_reference_executor`), `tools/ern/mem_probe_*.py` (memory profiling, test-only).
- `execute_reference()`: Exported from `execution/__init__.py`; used in `tests/unit/execution/test_reference.py`, `tests/integration/test_part42_e2e_audit.py` (monkey-patched), `tools/ern/mem_probe_*.py`.
- `expected_reference_report`, `reference_month_work`: Exported from `execution/__init__.py`; used in CLI completion summary (`run_command.py:530-564, 640-678`).

**Migration approach (per review):**
- Do **not** delete `ReferenceSimulationExecutor` or `execute_reference()` in Phase A. Their unique responsibilities (cohort-slice dispatch for memory safety, report construction) must be migrated first.
- Fix the CLI default-routing bug (`run_command.py` missing `research_result` branch for non-Part3, non-flagged execution) as a separate, explicitly tested change.
- `ExecutionBackend.REFERENCE` rename to `DECIMAL_FAST_PATH` is a breaking public-API change. Trace all consumers first; a deprecation alias may be preferable to immediate removal. This is deferred until Phase C.
- Obsolete equivalence tests (FAST vs legacy reference with multiplicative fee) are already deleted — confirmed.

---

## 1.4 Workbook-First Financial Correctness Policy

`SWR_Toolbox_v2.0.xlsx` is the authoritative specification whenever it defines the relevant behavior.

- Trace the actual workbook formulas and calculation order before implementing or changing financial calculations.
- Preserve the validated workbook behavior, including the additive fee model (`weighted_return - fee/12`) and end-of-period withdrawal semantics (grow → withdraw) where applicable.
- Do not assume that using the same fee convention automatically makes an unsupported workload workbook-equivalent.
- Where the workbook does not define behavior (e.g., dynamic glidepaths, Part 52 timing leverage, buy-and-hold), explicitly specify and test the simulator extension. Do not silently invent financial semantics.
- Keep `tools/ern/workbook_oracle.py` and `tools/ern/reference_oracle.py` independent of production Numba code. They are the validation oracles.
- Do not regenerate, replace, or delete existing oracle data (`data/ern/p49_oracle_table.csv`) until its provenance, intended purpose, and relationship to published ERN results have been established. If the workbook and published ERN methodology differ (they do: workbook uses additive fee + end-of-period; reference oracle uses multiplicative fee + beginning-of-month), document the difference rather than silently overwriting one with the other.

---

## 1.5 Memory-Safety Requirements

- The ERN canonical grid (313,020 units × 720 months) materializes ~0.37 MiB/unit of timeline payload (~110 GiB total). Memory-bounded cohort-slice dispatch (`reference.py:_slice_plan_units`) is the **only** current protection.
- Any trajectory materialization (Phase B6) **requires** cohort-slice dispatch (Phase B7) to be implemented first or concurrently.
- Summary-only execution (`summary_only=True`) must remain efficient and is the default for large grids.
- Timeline materialization is opt-in unless existing public behavior requires otherwise.
- The 16 GB memory target is a validation target, not an assumed guarantee. Actual workload requirements and execution environments must be measured.

---

## 2. Verified Current Execution Architecture

This section reflects the repository as inspected, not prior audit summaries.

### 2.1 Backend selection (`execution/__init__.py`)

- Public enum: `ExecutionBackend.REFERENCE = "reference"`,
  `ExecutionBackend.FAST = "fast"` (`:140-141`).
- `execute_study_plan(plan, options)` (`:354`):
  - `backend is None` → `_auto_select_backend()` (`:292`):
    1. Numba unavailable → `FastPathSimulationExecutor` (Decimal closed form).
    2. All units Part52-eligible → `Part52NumbaExecutor`.
    3. All units FixedReal-eligible → `NumbaSimulationExecutor`.
    4. All units glidepath-eligible → `NumbaSimulationExecutor`.
    5. Otherwise → `FastPathSimulationExecutor` (Decimal closed form).
  - `backend == FAST` → requires Numba; selects `Part52NumbaExecutor` if all
    Part52, else `NumbaSimulationExecutor` (`:402-435`).
  - `backend == REFERENCE` → `FastPathSimulationExecutor` (`:436-439`).
- Strategy: `REFERENCE`-routed work may use `parallel_execute` when
  `units >= 500` and `workers > 1` (`:488`); Numba-routed work is always
  sequential (`:468-485`).

### 2.2 Executors

| Executor | File | Eligible workloads | Ineligible handling |
|----------|------|--------------------|---------------------|
| `FastPathSimulationExecutor` | `strategies/fast_path.py` | Constant allocation + FixedReal, 2 assets, dataset covers horizon | Batches ineligible contexts to `self._reference` (`:896`) |
| `NumbaSimulationExecutor` | `strategies/numba_executor.py` | (a) Constant allocation + FixedReal; (b) Glidepath + FixedReal; 2 assets | Per-context `self._reference` (`:530`) |
| `Part52NumbaExecutor` | `strategies/part52_numba_executor.py` | Constant allocation + `Part52WithdrawalPolicy`, 2 assets, `expense_ratio ∈ {None, 0}`, `interest_rate_schedule` set | Per-context `self._reference` (`:408`) |
| `ReferenceSimulationExecutor` | `strategies/reference.py:312` | Any context (wraps legacy engine) | Delegates non-prefix to legacy engine per context (`:407`) |
| `_create_default_simulation_executor()` | `strategies/parallel_executor.py:42` | Any context (legacy engine factory) | — |

Every Numba/Decimal executor constructs its fallback with
`self._reference = reference_executor or _create_default_simulation_executor()`
(`fast_path.py:817`, `numba_executor.py:255`,
`part52_numba_executor.py:217`, `reference.py:322`).

### 2.3 Legacy engine composition

- `_create_default_simulation_executor()` (`parallel_executor.py:42`) builds a
  `SimulationPipeline` with these steps: `InitializeAllocationStep`,
  `ExpenseDeductionStep`, `BuildDecisionContextStep`, `WithdrawalDecisionStep`,
  `InterestAccrualStep`, `LoanDrawStep`, `SupplementalCashFlowStep`,
  `WithdrawalExecutionStep`, `LoanRepaymentStep`, `AllocationDecisionStep`,
  `PortfolioRebalanceStep`, `MarketEvolutionStep`, `LTVEvaluationStep`,
  `MonthlyResultBuilderStep`, `FailureDetectionStep`,
  `SimulationStateUpdateStep`.
- `default_pipeline.py:53` (`create_default_pipeline`) and `:108`
  (`create_buy_and_hold_pipeline`) provide the same steps for direct pipeline
  users and buy-and-hold.

### 2.4 Output contract

- Legacy engine → full `SimulationTimeline(monthly_results=(...))`, including
  `MonthlyResult.debt_snapshot`.
- `FastPathSimulationExecutor`, `NumbaSimulationExecutor`,
  `Part52NumbaExecutor` → `SimulationTimeline(monthly_results=())` (empty).
- Persistence (`persistence/studies/sqlite/codecs.py`) round-trips
  `monthly_results`; empty timelines therefore persist nothing per month.
- `ui`/CLI: `--fast-path` is rejected together with `--persist-study` because
  the fast path cannot supply persisted timelines.

### 2.5 Eligibility predicates (source of truth)

| Predicate | File:line | Requires |
|-----------|-----------|----------|
| `is_fast_path_eligible` | `fast_path.py:156` | `ConstantAllocationPolicy`, `FixedRealWithdrawalPolicy`, horizon ≥ 1, dataset ≥ horizon, exactly 2 holdings, exactly 1 `equity` |
| `_is_numba_eligible` | `numba_executor.py:114` | alias of `is_fast_path_eligible` |
| `_is_glidepath_eligible` | `numba_executor.py:123` | `GlidepathAllocationPolicy`, `FixedRealWithdrawalPolicy`, 2 holdings, 1 `equity` |
| `is_part52_eligible` | `part52_numba_executor.py:66` | `ConstantAllocationPolicy`, `Part52WithdrawalPolicy`, 2 holdings, 1 `equity`, `expense_ratio ∈ {None, 0}`, `interest_rate_schedule is not None` |

**Verified gap:** the eligibility gates, not the numerical kernels, are the
dominant blocker. For example, `_weights_by_class` (`fast_path.py:190`) and the
growth-factor computation (`numba_kernel.py:301`) already operate on an
arbitrary number of asset classes; the 2-asset restriction is imposed by the
predicates and by `ConstantAllocationPolicy` exposing only
`equity_allocation`.

---

## 3. Capability and Migration Matrix

Classification key:
**1** = already supported by Numba; **2** = partially supported;
**3** = not supported; **4** = fundamentally specialized (needs design);
**5** = obsolete/redundant.

| # | Capability | Current implementation (file:symbol) | Class | Numba support / fallback | Gap | Required migration | Tests / consumers | Blockers | Acceptance criteria |
|---|------------|--------------------------------------|:----:|--------------------------|-----|--------------------|-------------------|----------|---------------------|
| 1 | Fixed-real withdrawals (workbook SCR) | `concrete.py:119` `FixedRealWithdrawalPolicy` | 1 | `_simulate_trajectory_end_of_period` (`numba_kernel.py:116`), `_compute_workbook_scr` (`:43`), `_evaluate_workbook_scr_path` (`fast_path.py:402`), `_process_static_group` (`numba_executor.py:576`) | None for summary stats | None | `tests/unit/execution/test_fast_path.py`, Part20 tests | None | SCR-based success matches workbook SCR formula; end-of-period trajectory matches workbook timing |
| 2 | Constant nominal withdrawals | `concrete.py:83` `ConstantWithdrawalPolicy` | 3 | None; falls back to legacy | Withdrawal is `V_m·rate/12`, not a constant `C` | Add kernel variant where withdrawal scales with current value; extend eligibility | `tests/unit/execution/test_backend_strategy_matrix.py:264`; generic studies | Recurrence change (`V_{m+1}=(V_m)(1-rate/12)g_m`) | A dedicated recurrence test + differential vs legacy |
| 3 | Constant allocation weights | `concrete.py:23` `ConstantAllocationPolicy` | 1 | `_weights_by_class` (`fast_path.py:190`) | None | None | ERN grid, Part 19/20 | None | Already covered |
| 4 | Time-varying weights / glidepaths (dynamic, not in workbook) | `glidepath.py` `GlidepathAllocationPolicy` | 2 | `_is_glidepath_eligible` (`numba_executor.py:123`), `_compute_equity_weight_sequence` (`:181`), `compute_growth_factors_varying_weights_batch` (`numba_kernel.py:378`) | **Not adapted to workbook methodology**; uses legacy beginning-of-period recurrence with multiplicative fee | Document coherent extension spec; implement workbook-aligned timing/fee for glidepaths | Part 19/20 (`research/part19_*`, `part20_*`) | Workbook does not implement glidepaths; extension must be designed | Static workbook fidelity complete; glidepath fidelity NOT STARTED |
| 5 | Two-asset portfolios | `fast_path.py:183`, `numba_executor.py:143` | 1 | All Numba kernels | None | None | ERN workloads | None | Already covered |
| 6 | Multi-asset portfolios (3+) | Eligibility rejects >2 holdings | 2 | Kernel math is generic; predicate is not | `_weights_by_class` assigns `equity→w`, all others→`1-w` (only valid for 2 assets) | Introduce explicit per-class target weights; relax predicate; verify rebalance semantics | Generic studies | `ConstantAllocationPolicy` exposes only `equity_allocation` | New policy/weight source + differential test on 3 assets |
| 7 | Expense ratios / fee application (workbook additive) | `expense_deduction_step.py` `ExpenseDeductionStep` | 1 | Workbook SCR formula uses additive fee in returns: `weighted_return - fee/12`; growth factors computed with fee embedded; end-of-period trajectory in `numba_kernel.py:116` and `fast_path.py:434` | Fee model aligned with workbook for static allocations; Part 49/52 may differ | **COMPLETE** (implemented in workbook SCR path) | `ern_grid.yaml` sets `expense_ratio: 0.0005`; Part20 tests updated | Fee model differs by study (Part 49 vs Part 52 vs legacy) | Static allocation: workbook additive fee validated; Dynamic glidepaths: pending |
| 8 | Debt state + loan drawdown | `loan_draw_step.py` `LoanDrawStep`; `part49_withdrawal.py`, `part52_withdrawal.py` | 2 | Part52 kernel `_simulate_part52` (`numba_kernel.py:703`) tracks `Y`, draws | Part 49 leverage (`Part49WithdrawalPolicy`) not eligible | Generalize debt kernel or add Part 49 eligibility | `tests/integration/test_part52_*`, Part 49 debt tests | Requires `interest_rate_schedule` for Part52 | Part 52 + Part 49 leverage E2E pass |
| 9 | Repay at fresh ATH | `loan_repayment_step.py` `LoanRepaymentStep` | 1 | `_simulate_part52` repay branch (`numba_kernel.py:788-818`) | None for Part52 | None | `test_part52_compound_drawdown.py` | None | Part 52 E2E pass |
| 10 | Floating-rate interest (FFR) | `interest_accrual_step.py` `InterestAccrualStep` | 1 | `_compute_monthly_rates` (`part52_numba_executor.py:112`) | None for Part52 | None | `test_part52_ffr_floating_rate.py` | None | Part 52 FFR test pass |
| 11 | LTV evaluation / enforcement | `ltv_evaluation_step.py` `LTVEvaluationStep` | 1 | `_simulate_part52` LTV branch (`numba_kernel.py:824-849`) | None for Part52 | None | `test_part52_*`, Part 49 | None | Part 52/49 LTV tests pass |
| 12 | Horizon derivation | `reference.py:330`, `fast_path.py:783`, `numba_executor.py:278`, `part52_numba_executor.py:228` | 1 | Present in all executors | None | Remove the legacy-only copy once `ReferenceSimulationExecutor` is deleted | `test_fast_path.py::test_executor_shares_longest_path` | None | Derivation report matches direct evaluation |
| 13 | FV target deduplication | `reference.py:206`, `fast_path.py:470`, `numba_executor.py:708` | 1 | Present in all executors | None | None | `test_trajectory_deduplication.py` | None | Per-target classification preserved |
| 14 | Cohort + slice execution | `reference.py:428` `_slice_plan_units`; `parallel_executor.py` | 2 | Executors process whole definitions; `parallel_execute` slices | Memory-bounded slice dispatch exists only in `execute_reference` | Port slice dispatch to the unified Numba path | `test_reference.py::TestSliceDispatchMemorySafety` | Empty timelines currently mask memory cost | Slice == whole-plan equality on a large grid |
| 15 | Deterministic execution | `execution/deterministic.py` `execute_deterministic_trajectory` | 4 | None; uses pipeline directly | Requires monthly checkpoints | Decide: reimplement on Numba with trajectory output, or keep as a specialized feature | `tests/unit/execution/test_deterministic.py` | Depends on #16 | Deterministic result contract preserved |
| 16 | Full monthly trajectory | `monthly_result_builder_step.py` `MonthlyResultBuilderStep` | 3 | None (empty timelines) | Numba kernels emit statistics only | Add optional trajectory materialization to Numba kernels | Persistence, Part 49/52 aggregation, deterministic | Memory/IPC cost; per-month portfolio reconstruction | Trajectory equals legacy month-by-month on a representative case |
| 17 | Result persistence | `persistence/studies/sqlite/codecs.py` | 3 | Depends on #16 | FAST path cannot persist | Enable once #16 lands; relax CLI guard | `run_command.py` (`--persist-study` vs `--fast-path`) | #16 | Save/load round-trip preserves statistics and timelines |
| 18 | Memory-bounded large grids | `reference.py:_MAX_UNITS_PER_WORKER`, `_DEFAULT_SLICE_COHORTS` | 2 | Works for summaries; breaks if timelines added | Whole-definition result lists held in memory | Unified slice/batch dispatch | `tests/benchmarks/`, ERN grid | #14, #16 | Peak RSS within documented host budget on 313k units |
| 19 | Buy-and-hold allocation | `concrete.py:49` `BuyAndHoldAllocationPolicy`; `default_pipeline.py:108` | 3 | None; predicate rejects it | Weights drift (no monthly rebalance), so growth factors are path-dependent on units, not constant | New recurrence: track units, apply returns without rebalancing | `test_part49_buy_and_hold.py` | Different recurrence from rebalanced model | Buy-and-hold E2E / differential pass |
| 20 | Escalating withdrawal | `escalating_withdrawal.py` `EscalatingWithdrawalPolicy` | 3 | None | Withdrawal grows annually by `(1+esc)^years` | Value-independent scalar withdrawal schedule; easy to add | Part 20 Experiment E (`part20_experiment_e.py`) | Eligibility + schedule in kernel | Experiment E E2E pass |
| 21 | Supplemental cash flow | `supplemental_cash_flow_step.py` | 3 | None (inactive by default) | Additional external cash flow | Add once a real consumer activates it | None active today | No active consumer | Only migrate if a consumer exists |
| 22 | CAPE-regime aggregation | `research/part20_*`, `cape_aggregation.py`, `cape_regime.py` | 4 | None | Regime classification layer | Keep as a post-processing layer over Numba results | Part 20 (`part20_pipeline.py`) | Aggregation, not simulation | Part 20 E2E pass |
| 23 | `ReferenceSimulationExecutor` wrapper | `reference.py:312` | 5 | Redundant (derivation already in `FastPathSimulationExecutor`) | — | Delete after migrations | `test_reference.py`, `test_determinism.py` | Public export `execute_reference` | No production consumer |
| 24 | `execute_reference()` public API | `reference.py:455` | 5 | Redundant | — | Redirect/delete | `test_reference.py::TestSliceDispatchMemorySafety` | Public export | No production consumer |
| 25 | `ExpenseDeductionStep` | `expense_deduction_step.py` | 4 | Not used by Numba; Part 52/49 use legacy fee convention | Different fee model from canonical workbook | Preserve until every legacy-pipeline consumer is migrated | `test_part49_buy_and_hold.py:108` | Part 49/52 fee semantics | Only delete when no pipeline consumer remains |

---

## 4. Ordered Migration Phases

### Phase A — Routing Fixes, Test Coverage, and CLI Repair

Goal: fix routing bugs, establish genuine Numba test coverage, repair the CLI
default execution path, and document the verified consumers of legacy symbols.
**Do not delete `ReferenceSimulationExecutor`, `execute_reference()`, or public
exports in this phase.** Their unique responsibilities (cohort-slice dispatch
for memory safety, report construction) must be migrated first.

Work items:

1. **A1 — Fix CLI default-routing bug.**
   `fbf-cli/src/fbf/cli/commands/run_command.py` has a missing `research_result`
   branch for non-Part3, non-flagged execution (lines 457-595). Implement the
   default path: `research_result = execute_study_plan(built, options=ExecutionOptions(...))`.
   Add explicit test for default (no flags), `--fast-path`, and `--reference` routes.

2. **A2 — Establish genuine Part 52 Numba test coverage.**
   Current Part 52 integration tests (`test_part52_compound_drawdown.py`,
   `test_part52_ffr_floating_rate.py`, `test_part52_numerical_trace.py`) all
   use `create_default_pipeline()` directly, bypassing `Part52NumbaExecutor`.
   Add tests that instantiate `Part52NumbaExecutor` and verify eligible
   configurations execute **without** invoking the fallback. Test expense
   ratios, FFR schedules, loan draw/repay ordering, LTV enforcement, terminal
   failure states, and boundary conditions.

3. **A3 — Document verified consumers of legacy symbols (completed in §1.3).**
   No deletions. Trace consumers for `ExecutionBackend.REFERENCE`,
   `ReferenceSimulationExecutor`, `execute_reference()`,
   `expected_reference_report`, `reference_month_work`.

4. **A4 — Keep obsolete equivalence tests deleted** (already done).

5. **A5 — Keep `parallel_executor._create_default_simulation_executor()`**
   until Phase D; it is the fallback used by every executor.

Phase A gate:
- CLI default path, `--fast-path`, and `--reference` all work and are tested.
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

1. **B1 — Non-zero expense ratio (additive fee).**
   Add **additive** fee to the growth factor (`g_m' = g_m - fee/12`, matching
   the workbook's `1 + r - f/12`) with the study's required semantics, and
   remove the `expense_ratio` rejection from `is_part52_eligible`.
   **Note:** The workbook uses additive fees (`V_{t+1} = (V_t - C) * (1 + r - f/12)`),
   not the multiplicative form. The reference engine, fast path, and Numba
   kernels must be updated to match. **Scope:** Static allocations (complete),
   glidepaths (pending extension spec), Part 52 (kernel update required).

2. **B2 — Constant nominal withdrawal.**
   Trace the `ConstantWithdrawalPolicy` domain model and existing execution
   order, then define the recurrence, withdrawal timing, failure conditions,
   fees, and inflation adjustments explicitly. Validate with hand-calculated
   examples and independent tests. Do not assume `V_{m+1} = V_m * (1 - rate/12) * g_m`
   without verification.

3. **B3 — Escalating withdrawal.**
   Add a scalar withdrawal schedule input to the kernel and extend eligibility
   to `EscalatingWithdrawalPolicy`. Validate with hand-calculated examples.

4. **B4 — Buy-and-hold.**
   Implement a non-rebalancing recurrence (unit-tracking) with explicit
   specification. Workbook does not define this; document as simulator extension.

5. **B5 — Multi-asset portfolios.**
   Confirm whether existing Numba kernels genuinely support arbitrary asset
   counts or only their numerical helper functions do. Introduce explicit
   per-class target-weight source; relax the 2-asset predicate; verify
   rebalance semantics.

6. **B6 — Full monthly trajectory.**
   Define trajectory semantics and required contents of `SimulationTimeline`
   (including `portfolio`, `market_snapshot`, `debt_snapshot`) before
   implementing materialization. Memory-bounded cohort processing (B7) must be
   implemented first or concurrently.

7. **B7 — Memory-bounded dispatch.**
   Port cohort-aligned slice dispatch (`reference.py:_slice_plan_units`) into
   the unified path so large grids stay within the host memory budget once B6
   adds timeline payloads. Validate against actual ERN grid (313k units).

Design rule: prefer extending the existing Numba executors and kernels over
creating new engines. The executors already share `_group_key`, `_index_series`,
`_weights_by_class`, `_apply_fv_check`, and growth-factor caching.

Phase B gate: every non-debt workload that currently falls back to the legacy
engine has either migrated to Numba with equivalent semantics or is recorded as
a deliberate specialized path; large-grid memory and determinism gates pass.

### Phase B — Expand Numba's generic simulation capabilities

Goal: grow the unified Numba engine to cover the generic (non-debt) workload
classes so they stop using the legacy fallback.

Work items (each independently testable):

1. **B1 — Non-zero expense ratio.** Add **additive** fee to the growth
   factor (`g_m' = g_m - fee/12`, matching the workbook's `1 + r - f/12`)
   with the study's required semantics, and remove the `expense_ratio`
   rejection from `is_part52_eligible`. **Note:** The workbook and oracle
   use additive fees (`V_{t+1} = (V_t - C) * (1 + r - f/12)`), not the
   multiplicative form previously documented here. The reference engine,
   fast path, and Numba kernels must be updated to match.
2. **B2 — Constant nominal withdrawal.** Add a value-scaled withdrawal
   recurrence and extend eligibility to `ConstantWithdrawalPolicy`.
3. **B3 — Escalating withdrawal.** Add a scalar withdrawal schedule input to
   the kernel and extend eligibility to `EscalatingWithdrawalPolicy`.
4. **B4 — Buy-and-hold.** Add a non-rebalancing recurrence (unit-tracking) or
   a documented equivalence check for buy-and-hold growth factors.
5. **B5 — Multi-asset portfolios.** Add an explicit per-class target-weight
   source and relax the 2-asset predicate. The kernel math already generalizes.
6. **B6 — Full monthly trajectory.** Add optional per-month materialization to
   the Numba kernels, preserving the `MonthlyResult` contract (including
   `portfolio`, `market_snapshot`, `debt_snapshot` where applicable).
7. **B7 — Memory-bounded dispatch.** Port cohort-aligned slice dispatch
   (`reference.py:_slice_plan_units`) into the unified path so large grids stay
   within the host memory budget once B6 adds timeline payloads.

Design rule: prefer extending the existing Numba executors and kernels over
creating new engines. The executors already share `_group_key`, `_index_series`,
`_weights_by_class`, `_apply_fv_check`, and growth-factor caching.

Phase B gate: every non-debt workload that currently falls back to the legacy
engine has either migrated to Numba with equivalent semantics or is recorded as
a deliberate specialized path; large-grid memory and determinism gates pass.

### Phase C — Debt-Aware Workloads and Part 49/52 Migration

Goal: migrate Part 49, Part 52, and other debt-aware workloads to Numba.

Work items:

1. **C1 — Part 52 Numba-only execution.**
   Remove fallback from `Part52NumbaExecutor` for eligible configurations.
   Ineligible configurations (missing FFR schedule, non-zero expense ratio before B1)
   fail with explicit `UnsupportedConfigurationError`. Do not silently fall back.

2. **C2 — Part 52 fee behavior (workbook additive).**
   Implement additive fee in Part 52 kernel growth factors. Resolve against
   workbook where defined; for Part 52-specific behavior not defined by workbook,
   use explicit specification and independent numerical checks.

3. **C3 — Part 49 debt (`loan_draw_rate`) migration.**
   Part 49 and Part 52 have different debt semantics (fixed draw rate vs
   drawdown-triggered, no ATH repayment). Implement separate kernel or mode
   flag only if shared implementation is demonstrably clearer, safer, and
   easier to validate than separate kernels. Do not merge merely for code reuse.

4. **C4 — Part 49 buy-and-hold migration.**
   Migrate `create_buy_and_hold_pipeline()` workloads to Numba buy-and-hold
   kernel (B4).

5. **C5 — LTV enforcement terminal state.**
   Add `failure_state="margin_call_terminal"` to Part 52/49 Numba kernels to
   match legacy `LTVEvaluationStep` behavior.

Phase C gate:
- Part 52 eligible configurations execute on Numba with no fallback.
- Part 49 debt workloads execute on Numba.
- LTV enforcement produces `margin_call_terminal` failure state.
- All Part 52/49 integration tests pass on Numba executors.

### Phase D — Trajectories, Memory, and Legacy Removal

Goal: implement trajectory materialization, bounded-memory dispatch, and
remove all legacy pipeline code.

Work items:

1. **D1 — Monthly trajectory materialization.**
   Define `SimulationTimeline` contents (`portfolio`, `market_snapshot`,
   `debt_snapshot`). Add optional `materialize_timeline` flag to Numba
   executors. Implement in kernels with pre-allocated arrays.

2. **D2 — Cohort-slice dispatch for bounded memory.**
   Port `_slice_plan_units` to unified Numba path. Validate ERN grid
   (313k units) stays within memory budget with timelines enabled.

3. **D3 — Deterministic trajectory on Numba.**
   Rewrite `execute_deterministic_trajectory` to use Numba kernel with
   trajectory output and checkpoint extraction.

3. **D4 — Legacy pipeline removal.**
   Delete `_create_default_simulation_executor()`, `create_default_pipeline()`,
   `create_buy_and_hold_pipeline()`, `ExpenseDeductionStep`, all pipeline
   steps, `ReferenceSimulationExecutor`, `execute_reference()`,
   `expected_reference_report`, `reference_month_work`, `FastPathSimulationExecutor`
   (if Numba is mandatory), and all fallback references.

4. **D5 — Public API resolution.**
   Decide on `ExecutionBackend.REFERENCE` rename/removal (breaking change).
   Update CLI to route `--reference` and default path through unified engine.
   Remove `--validate` (tied to Decimal fast path validation).

Phase D gate (Final Deletion Gate):
- All capabilities in §3 migrated or explicitly retained.
- Workbook fidelity for static allocations validated.
- Dynamic glidepath extension specification documented.
- Zero production references to legacy symbols.
- `ExecutionBackend.REFERENCE` renamed/removed; Core minor version bumped.
- CLI routes through unified engine.
- Canonical ERN grids match oracle; all E2E tests pass.
- Large-grid execution within memory budget.
- Quality gates pass: `ruff check .`, `mypy --strict .`, full test suite.
- `tools/ern/reference_oracle.py` unchanged and independently regenerates oracle.

---

## 5. Correctness and Validation Contracts

### 5.1 Canonical ERN correctness

```
ERN YAML
  → StudyConfiguration.from_yaml()
  → run_study()
  → execute_study_plan()  → Numba execution
  → comparison with data/ern/p49_oracle_table.csv
       (independent generator: tools/ern/reference_oracle.py)
```

The contract is **reproduction of the Excel workbook methodology**, not
bit-exact equality with the legacy engine. The workbook uses an **additive
fee embedded in monthly returns** (`weighted_return - fee/12`) and **end-of-period
withdrawals** (grow first, then withdraw). Validation is against the pinned
oracle matrix within the explicitly justified tolerance (exact Decimal equality
where required, or the documented percentage tolerance for success rates).

**Limitation**: The expected values for the acceptance case were read from the
workbook's pre-calculated saved values. Fresh recalculation in Excel or
LibreOffice was not completed (LibreOffice headless timed out). The validation
is against the workbook's saved cached results, not a fresh recalculation.

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
`tools/ern/reference_oracle.py` remains the only workbook oracle and must not
be imported by production code.

### 5.3 Test classification

| Class | Meaning | Action |
|-------|---------|--------|
| Canonical correctness | ERN grid vs `p49_oracle_table.csv` | Keep; primary acceptance |
| Behavioral contract | Part 52/49 debt mechanics, glidepath, deterministic checkpoints | Keep; migrate to run on Numba |
| Determinism | Repeated runs identical; parallel == sequential | Keep |
| Routing | AUTO selects expected executor; backend × strategy matrix | Keep, but fix names once §1.3 is resolved |
| Obsolete implementation equivalence | `FAST == legacy Reference` where methodologies differ | Delete in Phase A (§7.3) |

---

## 6. Dependencies, Risks, and Unresolved Questions

### 6.1 Dependencies

- Numba is an optional dependency (`fbf-core[numba]`). The target single-engine
  architecture implies Numba becomes a hard runtime dependency, or that a
  pure-Python fallback kernel remains. **This is unresolved and must be
  decided before Phase D.**
- Full trajectories (#16) block persistence (#17), debt aggregation, and
  deterministic execution.
- Slice dispatch (#14/B7) blocks memory-bounded execution once #16 lands.

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
   enormous (~0.37 MiB/unit per the legacy notes in `reference.py:419`); B7 is
   a hard prerequisite for persistence at grid scale.
4. **Public API breakage.** Removing `execute_reference`/`ExecutionBackend.REFERENCE`
   semantics is a breaking change and requires a Core minor version bump and
   consumer pin updates.
5. **CLI routing ambiguity.** The CLI `--reference` flag is parsed for mutual
   exclusion but the compliant execution branch is not visibly wired in
   `fbf-cli/src/fbf/cli/commands/run_command.py` (only the `is_part3` and
   `--fast-path` branches assign `research_result`). This should be verified
   and fixed as part of Phase A before relying on CLI behavior. *See §6.3.*

### 6.3 Unresolved questions (require human decision)

1. Is Numba to become a mandatory runtime dependency, or must a pure-Python
   fallback persist? (Determines whether `FastPathSimulationExecutor` survives
   at all.)
2. Should `ExecutionBackend.REFERENCE` be renamed, aliased, or removed?
3. Does any external consumer depend on `execute_reference` /
   `expected_reference_report` as public API?
4. Is `execution/deterministic.py` to be reimplemented on Numba, or retained as
   a specialized trajectory feature?
5. What is the authoritative behavioral oracle for Part 52 and debt-aware
   Part 49 if no pinned cell table exists?
6. What is the intended default CLI execution path (the missing
   `research_result` branch noted in §6.2.5)?

---

## 7. File- and Symbol-Level Migration Inventory

### 7.1 Production files to modify or delete

| File | Symbols | Phase | Action |
|------|---------|:-----:|--------|
| `src/fbf/core/execution/strategies/reference.py` | `ReferenceSimulationExecutor`, `execute_reference`, `_slice_plan_units`, `expected_reference_report`, `_build_derived_result` | D | Delete after slice dispatch ported (B7/D2) and report duties migrated |
| `src/fbf/core/execution/strategies/workbook_scr.py` | `compute_workbook_growth_factors`, `compute_workbook_scr`, `workbook_scr_success` | B | **COMPLETE** — workbook SCR core implementation |
| `src/fbf/core/execution/__init__.py` | `execute_reference`, `expected_reference_report`, `reference_month_work` exports (`:53`,`:62`,`:70`); REFERENCE branch (`:436`) | D | Remove after Phase C; rename `ExecutionBackend.REFERENCE` in Phase C |
| `src/fbf/core/execution/strategies/parallel_executor.py` | `_create_default_simulation_executor` (`:42`) | D | Delete after all fallbacks removed (Phase D4) |
| `src/fbf/core/execution/pipeline/default_pipeline.py` | `create_default_pipeline`, `create_buy_and_hold_pipeline` | D | Delete after all pipeline consumers migrated (Phase D4) |
| `src/fbf/core/execution/pipeline/steps/expense_deduction_step.py` | `ExpenseDeductionStep` | C/D | Migrate fee to Numba (B1); delete in Phase D4 |
| `src/fbf/core/execution/strategies/fast_path.py` | `FastPathSimulationExecutor`, `self._reference` (`:817`), `_use_workbook_scr`, `_evaluate_workbook_scr_path`, `evaluate_closed_form` | C/D | **Workbook SCR COMPLETE**; retain as Decimal fast path if Numba optional; else delete in D4 |
| `src/fbf/core/execution/strategies/numba_executor.py` | `NumbaSimulationExecutor`, `self._reference` (`:255`), `_use_workbook_scr`, `_process_static_group` | B/C/D | **Workbook SCR COMPLETE**; extend; remove fallback in C1/D4 |
| `src/fbf/core/execution/strategies/part52_numba_executor.py` | `Part52NumbaExecutor`, `self._reference` (`:217`) | C | Generalize; remove fallback in C1; add expense ratio (B1) |
| `src/fbf/core/execution/strategies/numba_kernel.py` | `_simulate_trajectory`, `_simulate_trajectory_end_of_period`, `_simulate_trajectory_varying`, `_compute_workbook_scr`, `_simulate_part52` | B/C/D | **Workbook SCR COMPLETE**; add nominal/escalating withdrawal (B2/B3), trajectories (D1), debt snapshots |
| `src/fbf/core/execution/deterministic.py` | `execute_deterministic_trajectory` | D | Reimplement on Numba (D3) |

### 7.2 Configuration / CLI / public surface

| Surface | File | Note |
|---------|------|------|
| `ExecutionBackend` | `execution/__init__.py:123` | Rename/alias question (§6.3) |
| `--reference`, `--fast-path` | `fbf-cli/src/fbf/cli/commands/run_command.py:234-243` | Verify/repair dispatch (§6.2.5) |
| `--validate` | same file `:244` | Ties to fast-path validation of the Decimal fast path |
| Persistence guard | same file `:397-402` | `--fast-path` + `--persist-study` blocked until B6 |
| `ExecutionOptions` | `execution/__init__.py:191` | `summary_only`, `glidepath_gf_cache` |

### 7.3 Test inventory

| Test | Class | Phase | Action |
|------|-------|:-----:|--------|
| `tests/oracle/ern/*` | Canonical correctness | — | Keep (primary acceptance) |
| `tests/unit/execution/test_determinism.py::TestReferenceDecimalEquivalence` | Obsolete equivalence | A | **DELETED** — tested FAST vs legacy reference (multiplicative fee) |
| `tests/unit/execution/test_fast_path_exact_equivalence.py` | Obsolete equivalence | A | **DELETED** — tested FAST vs legacy reference (multiplicative fee) |
| `tests/unit/execution/test_reference.py` | Legacy executor internals | D | Delete after D2; port FV dedup cases to `test_trajectory_deduplication.py` |
| `tests/unit/execution/test_trajectory_deduplication.py` | Behavioral (FV dedup) | A/D | Keep; retarget to `FastPathSimulationExecutor` / `NumbaSimulationExecutor` |
| `tests/unit/execution/test_backend_equivalence.py` | Routing | A | Keep; fix "reference" naming |
| `tests/unit/execution/test_backend_strategy_matrix.py` | Routing | A | Keep; replace `_make_reference_executor()` with `FastPathSimulationExecutor` |
| `tests/unit/execution/test_pipeline_parity.py` | Behavioral/equivalence | C/D | Reclassify; keep behavioral contract tests |
| `tests/unit/strategies/test_numba_executor_differential.py` | Differential vs legacy (legacy methodology) | B/C | **DELETED** — compared workbook-based numba vs legacy reference |
| `tests/unit/execution/test_grid_reference.py` | Legacy grid | C/D | Reclassify; keep routing tests |
| `tests/integration/test_numba_e2e.py` | Numba E2E (legacy comparison) | B/C | **DELETED** — compared workbook-based numba vs legacy reference |
| `tests/integration/test_part52_*` | Behavioral (debt) | C | **REWRITE** to use `Part52NumbaExecutor`; add explicit Numba-path tests |
| `tests/integration/test_part49_*` | Behavioral/canonical | C | **REWRITE** to use Numba executor; add explicit Numba-path tests |
| `tests/benchmarks/test_*` | Performance | B/D | Keep; update to unified path |
| `fbf-cli/tests/unit/test_run_command.py`, `test_grid_cli_contract.py` | Routing/CLI | A | Keep; align to repaired dispatch (A1) |
| `tests/unit/execution/test_fast_path.py` | Fast path workbook SCR | B | **PASSING** (22/22) — validates workbook SCR path, depletion boundary, multi-horizon equivalence |
| `tests/unit/research/test_part20_corrected_methodology.py` | Part20 workbook fidelity | B | **PASSING** (9/9) — updated expectations for workbook methodology |
| `tests/integration/test_part52_numba_executor.py` | Part 52 Numba path | A | **NEW** — prove eligible configs execute without fallback |
| `tests/integration/test_part52_ineligible_error.py` | Unsupported config errors | A | **NEW** — explicit errors for ineligible configs |

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

5. **Public surface resolved.** `execute_reference` and
   `expected_reference_report` are removed from public exports; the
   `ExecutionBackend.REFERENCE` semantics are renamed/aliased/removed and all
   consumer pins updated (Core minor bump if Tier 1/2 API changes).

6. **CLI resolved.** `--reference` and the default execution path route through
   the unified engine; `--fast-path` remains an alias for the same engine or is
   removed deliberately; `--validate` removed (tied to Decimal fast path).

7. **Validation.** Canonical ERN grids match `data/ern/p49_oracle_table.csv`
   (via `tools/ern/reference_oracle.py`) within the justified tolerance; Part
   52 / Part 49 / Part 19 / Part 20 E2E and behavioral tests pass; determinism
   and parallel-equivalence tests pass; persistence round-trips full
   trajectories.

8. **Memory gate.** Large-grid execution (313k units) stays within the
   documented host memory budget with timelines enabled.

9. **Quality gate.** `ruff check .`, `mypy --strict .`, and the full test suite
   pass from a clean checkout per `AGENTS.md`.

10. **Oracle preserved.** `tools/ern/reference_oracle.py` is unchanged and still
    regenerates the oracle table independently.

Deletion is atomic per Phase D and must not occur until gates 1–10 pass.

---

## 9. Progress Tracking

| Milestone | Status | Evidence | Commit | Notes |
|-----------|--------|----------|--------|-------|
| A1: Fix CLI default-routing bug | ✅ Complete | CLI dry-run works for all 3 paths | 8d142d3 (fbf-cli) | `run_command.py` default branch added |
| A2: Part 52 Numba test coverage | ✅ Complete | 12 new tests exercise Numba path | [pending] | Tests prove eligible configs execute on Numba without fallback |
| A3: Document legacy consumers | ✅ Complete | §1.3 | b4ff4ad | Verified via grep |
| B1: Expense ratios (additive fee) | ✅ Static Complete | `workbook_scr.py`, `test_fast_path.py` | 99b4882 | Glidepath/Part 52 pending |
| B2: Constant nominal withdrawal | ⬜ Not Started | — | — | Requires policy trace |
| B3: Escalating withdrawal | ⬜ Not Started | — | — | Part 20 Experiment E |
| B4: Buy-and-hold | ⬜ Not Started | — | — | Unit-tracking kernel |
| B5: Multi-asset | ⬜ Not Started | — | — | Verify kernel support |
| B6: Trajectory materialization | ⬜ Not Started | — | — | Requires B7 first |
| B7: Cohort-slice dispatch | ⬜ Not Started | — | — | Port `_slice_plan_units` |
| C1: Part 52 Numba-only | ⬜ Not Started | — | — | Remove fallback |
| C2: Part 52 fee behavior | ⬜ Not Started | — | — | Additive in kernel |
| C3: Part 49 debt migration | ⬜ Not Started | — | — | Separate kernel or mode |
| C4: Part 49 buy-and-hold | ⬜ Not Started | — | — | Depends on B4 |
| C5: LTV terminal state | ⬜ Not Started | — | — | `margin_call_terminal` |
| D1: Trajectory materialization | ⬜ Not Started | — | — | Optional flag |
| D2: Cohort-slice for memory | ⬜ Not Started | — | — | ERN grid validation |
| D3: Deterministic trajectory | ⬜ Not Started | — | — | Checkpoint extraction |
| D4: Legacy removal | ⬜ Not Started | — | — | Final deletion gate |
| D5: Public API resolution | ⬜ Not Started | — | — | Breaking change decision |

**Legend:** ✅ Complete | 🔄 In Progress | ⬜ Not Started | ❌ Blocked

### Completed Milestones

**99b4882** — "workbook fidelity: implement additive fee model, fix builder horizon bug, add validation tests"
- Implemented workbook SCR methodology for static allocations across `workbook_scr.py`, `fast_path.py`, `numba_kernel.py`, `numba_executor.py`
- Validated against saved workbook values (600-month, 75/25, 4% WR, 0.05% fee)
- All quality gates pass: ruff, mypy, contract tests, unit tests, integration tests

### Known Limitations

1. **Workbook recalculation not completed** — LibreOffice headless timed out; validation against pre-calculated saved values.
2. **Reference oracle divergence** — `tools/ern/reference_oracle.py` uses multiplicative fee + beginning-of-month withdrawals (matches published Table 1); `workbook_oracle.py` uses additive fee + end-of-period (matches workbook formulas). Documented in §1.4.
3. **Part 52 tests bypass Numba** — All existing Part 52 integration tests use `create_default_pipeline()` directly (A2).
4. **CLI default path broken** — Missing `research_result` branch in `run_command.py` (A1).

---

## Appendix A — Verified facts used in this roadmap

- `ExecutionBackend.REFERENCE` routes to `FastPathSimulationExecutor`
  (`execution/__init__.py:436-439`); it is not the legacy engine.
- `execute_reference()` (`reference.py:455`) is the legacy engine with
  cohort-sliced dispatch.
- Every executor falls back to `_create_default_simulation_executor()`
  (`fast_path.py:817`, `numba_executor.py:255`, `part52_numba_executor.py:217`,
  `reference.py:322`).
- Numba executors emit empty timelines (`numba_executor.py:616,686`;
  `part52_numba_executor.py:380`).
- Debt aggregation reads monthly `debt_snapshot`
  (`research/part49_aggregation.py:126-129`,
  `optimization/part52_evaluator.py:192-194`).
- The workbook uses a **hybrid fee convention** (`SCR = (AH + AJ - fee) / AI * 12`)
  with **end-of-period withdrawals** (grow first, then withdraw) and **T terms**
  (T withdrawals, T-1 growth periods).
- `ern_grid.yaml` sets `expense_ratio: 0.0005`; workbook SCR path applies it via the
  hybrid fee formula in `compute_workbook_scr`.
- `tools/ern/reference_oracle.py` uses a **multiplicative fee** and **beginning-of-month
  withdrawals** with **T+1 terms** (historical methodology that matches published
  Table 1); it is the independent oracle, not the workbook methodology.

## Appendix B — Capability classification summary

- **Class 1 (already supported — workbook fidelity for static allocations):** 1, 3, 5, 7, 9, 10, 11, 12, 13.
- **Class 2 (partial — glidepaths supported but not workbook-aligned):** 4, 6, 8, 14, 18.
- **Class 3 (not supported):** 2, 16, 17, 19, 20, 21.
- **Class 4 (specialized):** 15, 22, 25.
- **Class 5 (obsolete/redundant):** 23, 24.
