# Roadmap: Migration to a Single Numba Execution Engine

**Status:** Phase B — Capability Expansion **IN PROGRESS** 🔄
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

### 1.3 Naming ambiguity that must eventually be resolved

The token **"reference"** currently denotes three different things. They must
not be conflated:

| Term | File / symbol | What it actually is today |
|------|---------------|---------------------------|
| `ExecutionBackend.REFERENCE` | `execution/__init__.py:140`, routed at `:436-439` | **Decimal closed-form fast path** (`FastPathSimulationExecutor`). It is *not* the legacy engine. |
| `ReferenceSimulationExecutor` / `execute_reference()` | `execution/strategies/reference.py:312`, `:455` | The legacy 9-step Decimal pipeline wrapped with horizon derivation and memory-bounded slice dispatch. |
| "the reference engine" (prose) | `_create_default_simulation_executor()` | The actual legacy Decimal engine: the 9/15-step pipeline built in `parallel_executor.py:42` and `default_pipeline.py:53`. |

**Consequence:** `ExecutionBackend.REFERENCE` is a *Delegate* to the fast path,
while `execute_reference()` is the legacy engine. Any plan that says "remove
Reference" must first disambiguate these. A future rename is recommended
(e.g. `ExecutionBackend.DECIMAL_FAST_PATH` and `LEGACY_ENGINE`), but that is a
breaking public-API change and is out of scope for this roadmap except as a
noted follow-up.

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

### Phase A — Remove redundant legacy dependencies

Goal: stop routing already-Numba-capable functionality through legacy
abstractions, and delete dead wrappers — **without** deleting shared pipeline
code that still serves unmigrated workloads.

Work items:

1. **A1 — Disambiguate names (documentation + symbol-level plan only).**
   Record the three meanings of "reference" (§1.3). Prepare (do not yet land) a
   rename plan for `ExecutionBackend.REFERENCE`.
2. **A2 — Delete `ReferenceSimulationExecutor` and `execute_reference()`** once
   the public export is removed and any CLI call site is redirected to
   `execute_study_plan(..., backend=...)` or to the unified path. Horizon
   derivation and FV dedup are already implemented in
   `FastPathSimulationExecutor` (`fast_path.py`) and both Numba executors.
3. **A3 — Retire `execute_reference`, `expected_reference_report`,
   `reference_month_work`** lazy exports from `execution/__init__.py`
   (`:53`, `:62`, `:70`) or redirect them to the surviving implementation.
4. **A4 — Delete obsolete equivalence tests** (see §7.3) that assert
   `FAST == legacy Reference` where the two intentionally differ.
5. **A5 — Keep `parallel_executor._create_default_simulation_executor()`** until
   Phase D; it is the fallback used by every executor.

Phase A gate: no production consumer imports `ReferenceSimulationExecutor` or
`execute_reference`; all eligible ERN workloads route through Numba/Decimal fast
path; remaining legacy fallback is only used by genuinely unmigrated
workloads.

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

---

### Phase B Sub-task: Workbook SCR Implementation — COMPLETE ✅

**Status**: The workbook SCR methodology for static allocations has been implemented across the fast path and Numba executor, and validated against the saved workbook values for the documented acceptance case.

**Implemented components:**

| Component | File | Status |
|-----------|------|--------|
| Core workbook SCR formulas | `src/fbf/core/execution/strategies/workbook_scr.py` | COMPLETE |
| Fast path eligibility + evaluation | `src/fbf/core/execution/strategies/fast_path.py` (`_use_workbook_scr`, `_evaluate_workbook_scr_path`, `evaluate_closed_form`) | COMPLETE |
| Numba kernel SCR + end-of-period trajectory | `src/fbf/core/execution/strategies/numba_kernel.py` (`_compute_workbook_scr`, `_simulate_trajectory_end_of_period`) | COMPLETE |
| Numba executor integration | `src/fbf/core/execution/strategies/numba_executor.py` (`_use_workbook_scr`, `_process_static_group`) | COMPLETE |

**Workbook fidelity scope:**
- **Static allocations (ConstantAllocationPolicy + FixedRealWithdrawalPolicy, FV=0)**: Workbook SCR formula applied for success determination; end-of-period trajectory (grow → withdraw) used for final wealth with fee embedded in returns (`weighted_return - fee/12`).
- **Dynamic glidepaths (GlidepathAllocationPolicy)**: **NOT adapted** — remain on legacy beginning-of-period recurrence with multiplicative fee. A separate extension specification is required.

**Validated passing checks:**
- Ruff lint: **All checks passed**
- Strict mypy: **Success: no issues found in 317 source files**
- Contract tests: **16/16 passed**
- Fast-path unit tests (including depletion boundary, multi-horizon equivalence): **22/22 passed**
- Part20 corrected methodology tests: **9/9 passed** (expectations updated to workbook methodology)
- Oracle matrix tests: **3/3 passed**
- Full unit suite: **597 passed**
- Integration + contract suites: **229 passed, 83 skipped (ERN E2E)**
- Performance benchmarks: **3 passed**

**Known gaps (not workbook fidelity failures):**
- The independent workbook oracle (`tools/ern/workbook_oracle.py`) and the test oracle (`_workbook_oracle_result`) implement the workbook formulas independently; they do not invoke production calculation helpers.
- The differential tests that compared workbook-based Numba results against the legacy reference engine methodology have been removed; they compared against the legacy multiplicative-fee methodology.
- Fresh spreadsheet recalculation in Excel/LibreOffice was **not completed** (LibreOffice headless timed out); validation is against pre-calculated workbook saved values.

**Acceptance criteria for workbook fidelity (static):**
1. ✅ Independent validation of the SCR calculation against the workbook formulas.
2. ✅ Agreement between SCR-based success classification and workbook-calculated examples.
3. ✅ Validation of end-of-period trajectory and final wealth against the workbook or hand-verifiable cases (for the documented acceptance case).
4. ✅ Tests covering fees, horizon boundaries, and depletion.

These criteria are **COMPLETE for the tested cases** (600-month horizon, 75/25 equity/bond, 4% WR, 0.05% fee). Broader independent acceptance coverage remains pending.

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
| `src/fbf/core/execution/strategies/reference.py` | `ReferenceSimulationExecutor`, `execute_reference`, `_slice_plan_units`, `expected_reference_report`, `_build_derived_result` | A/D | Delete (port slice dispatch in B7) |
| `src/fbf/core/execution/strategies/workbook_scr.py` | `compute_workbook_growth_factors`, `compute_workbook_scr`, `workbook_scr_success` | B | **COMPLETE** — workbook SCR core implementation |
| `src/fbf/core/execution/__init__.py` | `execute_reference`, `expected_reference_report` exports (`:53`,`:62`); REFERENCE branch (`:436`) | A/D | Remove/redirect; resolve naming |
| `src/fbf/core/execution/strategies/parallel_executor.py` | `_create_default_simulation_executor` (`:42`) | D | Delete after fallbacks removed |
| `src/fbf/core/execution/pipeline/default_pipeline.py` | `create_default_pipeline`, `create_buy_and_hold_pipeline` | D | Delete/retain per pipeline consumers |
| `src/fbf/core/execution/pipeline/steps/expense_deduction_step.py` | `ExpenseDeductionStep` | B/D | Migrate fee to Numba; delete only via §8 gate |
| `src/fbf/core/execution/strategies/fast_path.py` | `FastPathSimulationExecutor`, `self._reference` (`:817`), `_use_workbook_scr`, `_evaluate_workbook_scr_path`, `evaluate_closed_form` | B/D | **Workbook SCR COMPLETE**; decide survival (fallback vs delete) |
| `src/fbf/core/execution/strategies/numba_executor.py` | `NumbaSimulationExecutor`, `self._reference` (`:255`), `_use_workbook_scr`, `_process_static_group` | B/D | **Workbook SCR COMPLETE**; extend; remove fallback |
| `src/fbf/core/execution/strategies/part52_numba_executor.py` | `Part52NumbaExecutor`, `self._reference` (`:217`) | C/D | Generalize; remove fallback |
| `src/fbf/core/execution/strategies/numba_kernel.py` | `_simulate_trajectory`, `_simulate_trajectory_end_of_period`, `_simulate_trajectory_varying`, `_compute_workbook_scr`, `_simulate_part52` | B/C | **Workbook SCR COMPLETE**; add nominal/escalating withdrawal, trajectories, debt snapshots |
| `src/fbf/core/execution/deterministic.py` | `execute_deterministic_trajectory` | B/D | Reimplement or retain |

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
| `tests/unit/execution/test_reference.py` | Legacy executor internals | A/D | Delete/port needed cases |
| `tests/unit/execution/test_trajectory_deduplication.py` | Behavioral (FV dedup) | A | Keep; retarget to surviving executor |
| `tests/unit/execution/test_backend_equivalence.py` | Routing | A | Keep; fix "reference" naming |
| `tests/unit/execution/test_backend_strategy_matrix.py` | Routing | A | Keep |
| `tests/unit/execution/test_pipeline_parity.py` | Behavioral/equivalence | A/D | Reclassify |
| `tests/unit/strategies/test_numba_executor_differential.py` | Differential vs legacy (legacy methodology) | B/C | **DELETED** — compared workbook-based numba vs legacy reference |
| `tests/unit/execution/test_grid_reference.py` | Legacy grid | A/D | Reclassify |
| `tests/integration/test_numba_e2e.py` | Numba E2E (legacy comparison) | B/C | **DELETED** — compared workbook-based numba vs legacy reference |
| `tests/integration/test_part52_*` | Behavioral (debt) | C | Keep; run on Numba |
| `tests/integration/test_part49_*` | Behavioral/canonical | C | Keep |
| `tests/benchmarks/test_*` | Performance | B | Keep; update to unified path |
| `fbf-cli/tests/unit/test_run_command.py`, `test_grid_cli_contract.py` | Routing/CLI | A | Keep; align to repaired dispatch |
| `tests/unit/execution/test_fast_path.py` | Fast path workbook SCR | B | **PASSING** (22/22) — validates workbook SCR path, depletion boundary, multi-horizon equivalence |
| `tests/unit/research/test_part20_corrected_methodology.py` | Part20 workbook fidelity | B | **PASSING** (9/9) — updated expectations for workbook methodology |

---

## 8. Final Deletion Gate for the Legacy Reference Engine

The legacy engine may be deleted only when **all** of the following hold:

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
   removed deliberately.
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
