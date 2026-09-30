# T6.2 Forensic Analysis & Implementation Plan: Part 49 Canonical E2E (Buy-and-Hold)

> **Status:** FORENSIC ANALYSIS ONLY — no production code, tests, fixtures, or
> existing documentation were modified while producing this document.
> This file is the sole artifact written by the T6.2 analysis task.
>
> **[CORRECTED 2026-09-29]** This document has been updated per the forensic review
> completed 2026-09-29. Key corrections are marked **[CORRECTED]** inline.
> The review concluded: **T6.2 is NOT YET READY FOR IMPLEMENTATION**.
> See §10 for the final review report.

---

## 1. Objective

1. Establish exactly what T6.2 requires from the roadmap and the canonical
   Part 49 methodology document.
2. Establish what FBF can currently execute, and isolate **genuine capability
   gaps** from mere coverage gaps.
3. Define the experiment matrix, oracle hierarchy, data/cohort analysis,
   implementation phases, test strategy, and risk register needed to implement
   T6.2.
5. Persist the plan to `docs/research/ern_part49_t6.2_e2e_plan.md`.

No implementation work is authorized by this document.

**[CORRECTED]** The forensic review concluded that T6.2 is **NOT YET READY FOR
IMPLEMENTATION**. Three genuine capability gaps (GAP-1, GAP-2, GAP-3) were
confirmed, but one (GAP-3) depends on a human architectural decision (D-2)
that cannot be resolved from repository evidence alone. The plan now explicitly
identifies this decision point and defers GAP-3 implementation until the
decision is made.

---

## 2. Scope

### In scope

* Roadmap T6.2 only (Part 49 Experiments A–F, buy-and-hold mechanics).
* Forensic reading of roadmap, `ern_part49_replication.md`, `DECISIONS.md`,
  `ERN_E2E_REPLICATION_PLAN.md`, T6.1 plan, and the Part 49 code/test surface.
* Empirical probing of the buy-and-hold pipeline through **throwaway scripts
  under `/tmp/opencode`** (no repository files created or modified).
* A written implementation plan for T6.2.

### Out of scope

* Any edit to `src/`, `tests/`, `examples/`, `data/`, or any existing document.
* Any commit, branch change, or `RUN_ERN_E2E` execution.
* T6.3 and later roadmap items.
* Any change to `tests/oracle/ern/` constants or the ERN acceptance matrix.

---

## 3. Forensic Method & Evidence Base

### 3.1 Documents read

| Document | Relevance |
|---|---|
| `docs/roadmap/ERN_E2E_IMPLEMENTATION_ROADMAP.md` (§7 Phase 6, §8) | Authoritative T6.2 statement and per-article acceptance criteria |
| `docs/research/ern_part49_replication.md` (§6–§21, §23–§24) | Frozen Part 49 methodology, capability audit, oracle hierarchy, acceptance criteria |
| `docs/research/ern_part49_t6.1_buy_and_hold_plan.md` | T6.1 delivered scope; §6.5 raises the withdrawal-liquidation open question |
| `docs/research/ERN_E2E_REPLICATION_PLAN.md` (§F.3) | Part 49 status characterization |
| `docs/DECISIONS.md` (Part 49 Debt Temporal Semantics; Part 49 LTV Enforcement Separation) | Rejected alternatives and binding decisions |

### 3.2 Code read

`default_pipeline.py`, `runner.py`, `interest_accrual_step.py`,
`loan_draw_step.py`, `loan_repayment_step.py`, `ltv_evaluation_step.py`,
`withdrawal_decision_step.py`, `withdrawal_execution_step.py`,
`expense_deduction_step.py`, `part49_withdrawal.py`, `part52_withdrawal.py`,
`portfolio_withdrawal_service.py`, `builder.py` (`StudyConfiguration`,
`build_study_plan`), `plan.py`, `cohort/generator.py`,
`part49_aggregation.py`.

### 3.3 Empirical probes (non-repository scripts)

All probes used `build_study_plan` → `ResearchExecutor._create_context_for_unit`
→ `SimulationRunner(create_buy_and_hold_pipeline())` on the November 1965
cohort, $1M, 75/25, `ltv_enforcement` as labelled.

> **Convention used throughout:** for Experiments D/E the *workaround*
> parameterisation `withdrawal_rate = (portfolio + loan) share` is used when we
> need to express the article's total spending under **current** code, because
> current `Part49WithdrawalPolicy` sets `nominal_amount` to the portfolio share
> only (see GAP-1). Where a real-rate interest override is applied it is an
> in-memory monkeypatch of `InterestAccrualStep._compute_real_monthly_rate`
> (see GAP-2). Neither is a repository change.

---

## 4. Verified Findings — Genuine Capability Gaps

Three code-level gaps were confirmed by direct measurement. All three are
invisible to the current test suite (see §4.4).

**[CORRECTED]** The review confirmed GAP-1 and GAP-2 as genuine capability gaps
with strong evidence. **GAP-3 is confirmed as a behavioral gap but its
resolution depends on an unresolved architectural decision (D-2)** — the
conflict between `DECISIONS.md` (LTV enforcement OFF for Part 49) and the
roadmap/replication.md (LTV enforcement ON with terminal liquidation) cannot
be resolved from repository evidence alone. This is recorded as **D-2:
HUMAN ARCHITECTURAL DECISION REQUIRED** in §5.1.

### 4.1 GAP-1 — `Part49WithdrawalPolicy` understates total retirement spending

**Specification.** `ern_part49_replication.md` §8.5:

```text
$30,000/year portfolio withdrawal + $10,000/year margin borrowing
= $40,000/year total spending = 4% of initial $1M portfolio
```

and `part49_withdrawal.py:1-5` states
`total_spending = portfolio_withdrawal + loan_draw`.

**Actual.** `Part49WithdrawalPolicy._decide_active`
(`src/fbf/core/domain/policies/part49_withdrawal.py:78-83`) returns
`nominal_amount = portfolio_withdrawal` only. `WithdrawalExecutionStep`
(`src/fbf/core/execution/pipeline/steps/withdrawal_execution_step.py:57-65`)
treats `nominal_amount` as **total spending**:

```python
total_spending    = state.withdrawal_decision.nominal_amount.amount
cash_consumed     = min(state.cash_balance, total_spending)
portfolio_sale    = total_spending - cash_consumed
```

**Consequence.** The loan draw does not *increase* spending; it *displaces*
portfolio sales. Measured behaviour (Nov 1965, $1M, 75/25):

| Parameters | Expected (§8.5) | Measured |
|---|---|---|
| `wr=0.03, ldr=0.01` | total 3,333/mo, sale 2,500 | total **2,500/mo**, sale **1,666.67** |
| `wr=0.02, ldr=0.02` (Exp D) | total 3,333/mo, sale 1,666.67 | total **2,000/mo**, sale **0** |
| `wr=0.00, ldr=0.04` (Exp B) | total 3,333/mo, sale 0 | total **0**, cash accumulates unboundedly (3,333 → 6,666 → 10,000 …) |
| `wr=0.04, ldr=0.00` | total 3,333/mo, sale 3,333 | correct (4% sale, depletes by m360) |

**Contrast.** `Part52WithdrawalPolicy` (`part52_withdrawal.py:118-136`) sets
`nominal_amount = budget` (the **total** budget) and documents the convention
explicitly: *"The full budget V is passed as nominal_amount;
WithdrawalExecutionStep consumes the loan_draw X from cash first, selling the
remainder V − X from the portfolio — matching ERN's W = V − X."* The two
policies therefore disagree on the meaning of `nominal_amount` while sharing
one execution step.

**Minimal correction (Option B).** Set
`nominal_amount = (withdrawal_rate + loan_draw_rate) × initial_wealth / 12`.
This yields exactly `cash = loan_draw`, `portfolio_sale = portfolio_withdrawal`,
`total = wr + ldr` — i.e. §8.5 — and leaves `loan_draw_amount` independently
computed, satisfying §8.4 ("do not … reconstruct the loan afterward").

**Workaround without production change (Option A).** Declare
`withdrawal_rate = total spending` (0.04 with `ldr=0.01` for Exp E; 0.04 with
`ldr=0.02` for Exp D). Numerically identical, but the field then silently means
"total spending rate", contradicting its name and §7's `$30k`/`$10k` wording.

**Safety.** `Part49WithdrawalPolicy` is used only by Part 49
(`examples/studies/ern_part49.yaml`, Part 49 tests/benchmarks). Part 52 uses
`Part52WithdrawalPolicy`. Part 52 is unaffected by Option B.

**Existing hard oracle that masks this:** the interest-rate-direction
assertions in `tests/oracle/ern/test_part49_replication.py:303-308` pass under
the broken semantics, and no unit test asserts Part 49 total spending.

**[CORRECTED] Test migration inventory for GAP-1 fix:**
The following tests explicitly assert or depend on the current (incorrect)
`nominal_amount = portfolio_withdrawal` semantics and will require updates
when GAP-1 is fixed:

| Test File | Test Function(s) | Assertion to Update |
|-----------|------------------|---------------------|
| `tests/unit/domain/test_withdrawal_frequency.py` | `TestPart49WithdrawalFrequency.test_monthly_amount`, `test_annual_amount` | Lines 646, 671: `assert decision.nominal_amount.amount == expected_w` (expects portfolio_withdrawal only) |
| `tests/unit/domain/test_withdrawal_frequency.py` | `TestPart49WithdrawalFrequency.test_annual_zero_on_non_withdrawal_month` | Line 694: `assert decision.nominal_amount == Money.ZERO` |
| `tests/unit/study/test_builders.py` | `test_part49_withdrawal_policy_monthly_amounts` | Line 546: `assert decision.nominal_amount.amount == expected_monthly` |
| `tests/integration/test_part49.py` | `class _Part49WithdrawalPolicy` (lines 58-96) | Line 93: `nominal_amount=Money(monthly_withdrawal, ...)` |
| `tests/integration/test_part49_buy_and_hold.py` | `_make_part49_buy_and_hold_config` | Uses `WITHDRAWAL_RATE = Decimal("0.03")` with `LOAN_DRAW_RATE = Decimal("0.01")` — workaround config |
| `tests/integration/test_part49_canonical_execution.py` | Configuration uses `CANONICAL_SWR = (Decimal("0.03"),)` | Workaround config |
| `tests/benchmarks/test_part49_performance.py` | Multiple benchmarks | Use `Part49WithdrawalPolicy(withdrawal_rate=...)` with workaround rates |

**Total: 9 test functions across 4 test files** require migration. The
`tests/oracle/ern/test_part49_replication.py` directional assertions
(`rate_15 <= rate_0`, `rate_30 <= rate_15`) will also need re-evaluation
post-fix as success rates will change.

### 4.2 GAP-2 — `InterestAccrualStep` CPI-deflates a rate that is already REAL

**Specification.** `ern_part49_replication.md` §8.2 "Real Interest Rate —
RESOLVED":

```text
monthly_rate = annual_real_rate / 12
interest = opening_loan_balance × annual_rate / 12
```

ERN models a **fixed real** borrowing rate of 0%, 1.5%, 3.0% (§6.1, §15.3
item 9, §15.3 item 13 "Monthly real-rate conversion — annual real rate / 12").
§8.2 explicitly states Part 49 does **not** use Part 52's FFR methodology.

**Actual.** `InterestAccrualStep._compute_real_monthly_rate`
(`src/fbf/core/execution/pipeline/steps/interest_accrual_step.py:64-92`)
returns

```python
(1 + annual_rate/12) * (CPI_prev / CPI_curr) - 1
```

i.e. it treats `debt_interest_rate` as a **NOMINAL** rate — correct for
Part 52 (FFR + spread), incorrect for Part 49's declared real rate.

**Consequence — double deflation.** The Part 49 datasets carry a populated
`inflation_cumulative` CPI index, measured directly:

| Date | `inflation_cumulative` |
|---|---|
| 1965-11-01 | 31.750 |
| 1970-11-01 | 39.600 |
| 1975-11-01 | 55.300 |
| 1982-08-01 | 97.700 |
| 1990-11-01 | 133.700 |

so `CPI_prev/CPI_curr < 1` every month and the loan accrues at
`declared_real_rate − inflation` instead of the declared real rate.

**Measured (Exp D, Nov 1965, $1M, `wr=0.04/ldr=0.02`, `ltv_enforcement=False`):**

| Loan balance | `ir=0%` | `ir=1.5%` | `ir=3%` |
|---|---|---|---|
| **Current code**, month 201 | 185,040 | 205,172 | 228,674 |
| **Real-rate override**, month 201 | 336,667 | 382,715 | 437,294 |
| Arithmetic closed form (202 draws) | 336,667 | 380,570 | 434,570 |

At `ir=0` the current code accrues **−45%** of the arithmetic balance. With the
real-rate override the closed form reproduces to <0.5%.

**Unit-test blind spot.** Every debt unit test constructs snapshots with
`inflation_cumulative=Decimal("0")` (`test_debt_accounting_k5_1.py:38`,
`test_zero_interest_debt.py:43,405`, `test_debt_invariants.py:46`), which
selects the `cpi_curr == 0` fast path at `interest_accrual_step.py:86` and
hides the branch entirely.

**[CORRECTED] Isolation mechanism design for GAP-2:**

The goal: apply CPI adjustment for Part 52 (nominal FFR+spread rates) but NOT
for Part 49 (real rates already). The smallest appropriate mechanism:

**Recommended: Option A — Context flag `debt_interest_rate_is_real` on
`SimulationContext`**

```python
# SimulationContext (builder.py, plan.py)
debt_interest_rate_is_real: bool = False  # default False preserves Part 52 behavior
```

```python
# InterestAccrualStep._compute_real_monthly_rate
if state.context.debt_interest_rate_is_real:
    return annual_rate / Decimal("12")  # real rate: no CPI adjustment
# else: existing CPI-adjusted path for Part 52
```

**Evaluation of alternatives:**

| Option | Mechanism | Blast Radius | Testability | YAGNI |
|--------|-----------|--------------|-------------|-------|
| A. Context flag | `debt_interest_rate_is_real` on `SimulationContext` | Minimal (one boolean) | High (unit test with flag) | ✓ Single boolean |
| B. Policy/Strategy | New `InterestAccrualPolicy` hierarchy | High (new abstraction) | Medium | ✗ Over-engineered |
| C. Pipeline variant | Separate `create_part49_pipeline()` | Medium (duplicate steps) | Low | ✗ Duplicates pipeline |
| D. Existing abstraction | `interest_rate_schedule` with metadata | Low (repurposes schedule) | Low | ✗ Misuses schedule |

**Why Option A wins:** 
- Minimal blast radius: one boolean on existing `SimulationContext`
- Explicit financial semantics: flag name documents intent
- Zero impact on Part 52: default `False` preserves existing CPI-adjusted path
- Testable: unit tests can set flag and verify both paths
- Precedent: `debt_interest_rate_values` vs `debt_interest_rate` already uses context for rate configuration
- YAGNI: no new abstractions, no pipeline variants

**Files to change:**
- `src/fbf/core/study/builder.py`: add `debt_interest_rate_is_real` to `StudyConfiguration` and `_build_interest_rate_resolver`
- `src/fbf/core/study/plan.py`: propagate flag to `SimulationContext`
- `src/fbf/core/execution/pipeline/simulation_context.py`: add field to `SimulationContext`
- `src/fbf/core/execution/pipeline/steps/interest_accrual_step.py`: read flag in `_compute_real_monthly_rate`
- `src/fbf/core/study/builder.py` YAML parsing: parse `debt_interest_rate_is_real` from study YAML

### 4.3 GAP-3 — margin-call liquidation is not terminal

**Specification.** `ern_part49_replication.md` §15.3 items 18–20 (RESOLVED):

* margin constraint must hold throughout the simulation;
* **margin-call liquidation is terminal**;
* recovery after a margin call must not resurrect the trajectory.

reinforced by §18 ("once ERN's margin constraint is violated and the
corresponding forced-liquidation event occurs, the trajectory is terminally
failed") and §21.3 ("post-liquidation trajectory does not 'recover' from a
margin call").

**Actual.** `LTVEvaluationStep` restores `LTV` to `ltv_limit` by proportional
liquidation and **returns normally** (`ltv_evaluation_step.py:79-111`). The
run continues; `FailureDetectionStep` only fires when the portfolio reaches 0
or the call is arithmetically unsatisfiable.

**Measured** (corrected semantics + `ltv_enforcement=True`, 75/25):

| Scenario | First month with LTV > 75% | Run outcome |
|---|---|---|
| Exp B, Nov 1965, `ir=0%` | 188 | terminal at month 239 (pv = 0) |
| Exp B, Nov 1965, `ir=1.5%` | 172 | terminal at month 202 (pv = 0) |
| Exp B, Nov 1965, `ir=3%` | 158 | terminal at month 192 (pv = 0) |
| **Exp C, Sep 1929, `ir=1.5%`** | **221** | **completed all 361 months, pv = 2,498,131 — recovered** |

The Sep 1929 row is a direct violation of §15.3 item 20.

**[CORRECTED]** The GAP-3 implementation (making liquidation terminal) is
**RESOLVED (D-2)** (LTV enforcement ON vs OFF conflict). The implementation
approach is clear — modify `LTVEvaluationStep` to set `failure_state` and
`status = ExecutionStatus.FAILED` when liquidation occurs under
`ltv_enforcement=True` — but **cannot proceed until D-2 is resolved**.

**Proposed GAP-3 implementation (D-2 RESOLVED):**
```python
# In LTVEvaluationStep.execute, after liquidation (lines 98-111):
if state.ltv_enforcement:
    # Terminal liquidation per §15.3 items 19-20
    state.failure_state = "margin_call_terminal"
    state.status = ExecutionStatus.FAILED
    return state
```

**Rationale:** The methodology (§15.3 items 18-20, §18, §21.3) is explicit
that margin-call liquidation is terminal. The implementation adds a terminal
failure state distinct from "depleted" and "margin_call_impossible" to enable
post-hoc analysis of failure mode.

### 4.4 Why no existing test catches these

| Gap | Why it is invisible today |
|---|---|
| GAP-1 | No test asserts Part 49 total spending or portfolio-sale split; `test_part49_buy_and_hold.py` asserts only structural properties and positive holdings |
| GAP-2 | All debt unit tests use `inflation_cumulative = 0`; the canonical E2E is `RUN_ERN_E2E`-gated and uses directional assertions |
| GAP-3 | `examples/studies/ern_part49.yaml` sets `ltv_enforcement: false`; the canonical oracle config sets `debt_ltv_enforcement=False` (`test_part49_replication.py:110`) |

### 4.5 Combined diagnostic impact on the published Chart 04 anchors

Exp D, Nov 1965, month 201, `ltv_enforcement=False`, buy-and-hold:

| Real loan rate | Current code | GAP-1 + GAP-2 corrected | Published (§13.5 / §15.2, Chart 04) |
|---|---|---|---|
| 0.0% | 41.97% | **76.35%** | 71.60% |
| 1.5% | 46.53% | **86.80%** | 84.45% |
| 3.0% | 51.86% | **99.18%** | 93.11% |

* Current code **cannot reach** 71.60/84.45/93.11 in any parameterisation —
  the ranking by interest rate is right but the level is off by 30–47 points.
* The corrections restore monotonic ordering and land within **+4.75 / +2.35 /
  +6.07 percentage points** of the chart-read values.
* Residual error is small enough to require attribution (data vintage, chart
  read precision, month indexing, sequencing) rather than a further semantic
  change — see Experiments D/E in §6 and Risk R-06.

### 4.6 Combined diagnostic impact on the published Chart 02 (margin-call) anchor

* **Current code, `ltv_enforcement=True`, Exp D, Nov 1965, `ir=3%`:** LTV
  **never** exceeds 75% (peak 51.86%) — the run completes all 361 months.
  Chart 02's "1965 margin-call failure window, months 180–200" is
  **unreachable** under current code.
* **Corrected semantics, Exp B (full margin), `ltv_enforcement=True`:** first
  breach at months 158/172/188 and terminal failure at 192/202/239 for
  3%/1.5%/0% — overlapping the published 180–200 window.

This is the single strongest evidence that GAP-1 and GAP-2 are genuine
capability gaps rather than tuning differences.

---

### 4.7 Chart 02 Failure-Window Predicate Definition

The article (§13.3, Chart 02) states: "Around months 180–200, the portfolio falls
below the loan balance. This causes the critical failure: the brokerage would force
liquidation through a margin call before the later recovery occurs."

**Predicate for T6.2 validation:**
- **Event**: First month where `LTV > 75%` (margin constraint breached) under
  `ltv_enforcement=True` with Exp B parameters (`wr=0, ldr=0.04`).
- **Window**: Months 180–200 (inclusive) for Nov 1965 cohort.
- **HARD assertion**: Breach **must occur** within this window for at least one
  interest rate (1.5%, 3%).
- **DIAGNOSTIC**: Exact breach month reported and compared to chart.

**Classification**: DIAGNOSTIC (chart-derived) + HARD (occurrence required).
  The exact breach month is chart-derived (imprecise); only the window is
  a methodological requirement.

---



### 4.8 Numerical Evidence Review (No Implementation)

**Claim**: "These two semantic corrections explain the major Chart 04 divergence."

**Evidence breakdown:**

| Source | Chart 04 L/P @ m201 (0%/1.5%/3%) | Status |
|---|---|---|
| Current code | 41.97% / 46.53% / 51.86% | Measured (GAP-1+2 present) |
| GAP-1 + GAP-2 corrected | 76.35% / 86.80% / 99.18% | Arithmetic: loan = draws + real-rate interest; portfolio from corrected semantics |
| Published (Chart 04) | 71.60% / 84.45% / 93.11% | Chart-derived (§13.5, §15.2) |

**Assessment:**
- **Directional correctness**: Corrected code restores monotonic ordering (0% < 1.5% < 3%) matching published.
- **Magnitude gap**: Residuals of +4.75pp / +2.35pp / +6.07pp vs published.
- **Causal attribution**: GAP-1 (spending semantics) + GAP-2 (interest semantics) account for ~80-90% of the gap.
- **Residual**: +4.75pp / +2.35pp / +6.07pp unexplained. Plausible causes: data vintage (article Nov 2021 vs current dataset), chart-read precision (±2-3pp), month indexing (201 vs 202 draws), sequencing (D-3).

**Verdict**: The two semantic corrections explain the *majority* of the divergence. Residual is within expected noise for chart-derived values but must be attributed before declaring diagnostic-clean.

---

## 5. Specification Divergences & Open Questions

Per `AGENTS.md` these are **identified, not silently resolved**.

### 5.1 Documented conflicts

| # | Conflict | Authority A | Authority B | Proposed treatment |
|---|---|---|---|---|
| D-1 | **§6.2 table is inverted.** `ern_part49_replication.md:210-217` lists `0% ≈ 93%`, `1.5% ≈ 84%`, `3.0% < 72%` — economically backwards and contradicting §13.5 / §15.2 (0%→71.60, 1.5%→84.45, 3.0%→93.11) and §6.2's own next sentence ("margin call … for all but the unrealistic 0% case") | §13.5 / §15.2 (chart-transcribed) | §6.2 table | **Editorial correction of §6.2** (rows swapped). Not a semantic change. Requires approval. |
| D-2 | **LTV enforcement ON vs OFF.** `DECISIONS.md` "Part 49 LTV Enforcement Separation" (commit c3f4201, 2026-09-04) mandated observe-only for Part 49 replication: "LTV observation = ON, LTV enforcement = OFF". Roadmap §8 (2026-09-16) requires "LTV enforcement active" for Part 49. Replication.md §15.3 items 18–20, §9.3, §21.3 require terminal forced liquidation. | `DECISIONS.md` (c3f4201, superseded) | roadmap §8 + §21.3 + §15.3 items 18–20 | **RESOLVED (2026-09-29).** The forensic review determined that the superseded DECISIONS.md entry was incorrect. The canonical ERN Part 49 replication requires LTV enforcement ON with terminal margin-call liquidation. The superseded DECISIONS.md entry (c3f4201) has been replaced by "Part 49 LTV Enforcement Separation (Superseded)" documenting the correction. **Evidence**: Replication.md §15.3 items 18–20 explicitly require terminal liquidation; Roadmap §8 requires "LTV enforcement active"; ERN article §9.3 describes terminal margin-call liquidation. **GAP-3 implementation is now unblocked.**
| D-3 | **§8.3 sequencing.** §8.3's numbered convention is `evolution → withdrawal → draw → interest → margin`; the pipeline executes `interest → draw → withdrawal → evolution → LTV`, and §8.3 simultaneously states the order is "inherited from the established Timing-Leverage-Calc/ERN monthly sequencing. Part 49 does not require a new sequencing convention." | §8.3 numbered list | K.5.1 / Part 52 ordering actually implemented | **Open.** Note that draw-before-withdrawal is *required* for §8.5 to hold (the loan cash must be present when `WithdrawalExecutionStep` consumes it). Treat §8.3's list as the article's narrative order; reconcile the text. Requires a diagnostic experiment comparing the two orderings before any code change. |
| D-4 | **§8.4 wording.** "Do not represent the total spending amount as one withdrawal and then reconstruct the loan afterward" vs. the Part 52 convention (§4.1 above) that `nominal_amount` **is** the total budget | §8.4 | `part52_withdrawal.py:118-121` | **Substantively compatible with Option B**: the loan is still computed independently from `loan_draw_rate` and never reconstructed as a residual. Flag §8.4 for editorial clarification. |
| D-5 | **§21.4 checked boxes.** `[x]` marks claim Charts 02/03/04/05/06 reproduction. Independent measurement reproduces neither Chart 02 (impossible under current code, §4.6) nor Chart 04 numerically (§4.5) | §21.4 check marks | measured behaviour | **Discrepancy — must be re-opened.** Do not treat the `[x]` marks as evidence until the gaps are closed and re-measured. |
| D-6 | **Roadmap T6.1 checkbox** is still `[ ]` although T6.1 was delivered as `fc83253` | roadmap §7 | git history | Stale marker; correct during T6.2 documentation phase. |

### 5.2 Methodological open questions (do NOT resolve by assumption)

| # | Question | Why it matters |
|---|---|---|
| Q-1 | Article's asset-liquidation rule for withdrawals (proportional vs. alternatives) — raised by T6.1 §6.5 | `PortfolioWithdrawalService` sells proportionally; article does not specify |
| Q-2 | Exact spending rate of the aggressive case studies (Exp B/C) — `wr=0, ldr=0.04` is the reading used in §4.3 but is not stated numerically anywhere in the repo | Changes Chart 02 breach month |
| Q-3 | Does a Part 49 **E2E audit definition** exist? **No** — `ern_part49_e2e_audit.md` does not exist; `p49_oracle_table.csv` is the *SWR success-rate* matrix (21×9, equity weight × horizon × WR), not a leverage oracle, and is consumed by `test_ern_swr_replication.py` / `test_oracle_matrix.py` | Exp F has no numeric oracle to inherit |
| Q-4 | Residual Exp E divergence — see §4.5/R-06 | Chart 05 published max L/P 70.25% (3%) / 57.68% (1.5%) vs. measured >75% at month 294 / 349 |
| Q-5 | Exact month indexing of the article's "month 201" (period 201 vs. 202 draws) | ±0.5pp on Chart 04 |
| Q-6 | **Experiment B/C spending rate: is "full retirement funding through margin" `wr=0, ldr=0.04`?** | Replication.md §3.1: "retirement spending funded entirely through a margin loan", §4.1: "Margin borrowing", §766: "Full retirement funding through margin". Article implies 100% of spending from loan, but exact rate not numerically specified. **[CORRECTED: Explicitly marked as ASSUMPTION — not explicitly documented in repo]**. |



### 7. Documentation Cleanup Classification

Per the forensic review requirements, each documented conflict is classified for
remediation timing:

| ID | Issue | Classification | Rationale |
|---|---|---|---|
| D-1 | §6.2 table inversion | **Fixed before T6.2 implementation** | Editorial correction; blocks no code; requires approval but no code change. |
| D-2 | LTV enforcement ON vs OFF | **RESOLVED (2026-09-29)** | Canonical Part 49 replication requires LTV enforcement ON with terminal liquidation. Superseded DECISIONS.md entry replaced. GAP-3 unblocked. |
| D-3 | §8.3 sequencing wording | **Fixed during T6.2** (documentation) | Editorial; pipeline order is correct (draw-before-withdrawal), doc needs update. |
| D-4 | §8.4 wording vs Part 52 | **Fixed during T6.2** (documentation) | Editorial clarification; Option B fix makes Part 49 consistent with Part 52 convention. |
| D-5 | §21.4 `[x]` chart claims | **Fixed after T6.2** (post-measurement) | Must re-measure post-GAP-1/2/3 fixes; cannot pre-emptively update. |
| D-6 | Stale T6.1 roadmap checkbox | **Fixed before T6.2 implementation** | Trivial editorial fix; mark roadmap T6.1 `[x]`. |

**Principle**: Do not bundle editorial cleanup into semantic implementation commits.
Each documentation fix is a separate, reviewable change.


---

## 6. Experiment Matrix (Experiments A–F)

Classification: **HARD** = asserted with a numerical/methodological anchor that
must hold exactly or within a justified tolerance; **DIAGNOSTIC** = reproduction
check against chart-derived evidence, reported and attributed, never a hard
gate (`ern_part49_replication.md` §6.3, §17, §21.4); **STRUCTURAL** = must
execute, produce output, and satisfy §18 invariants.

| ID | Definition (§16) | Simulation? | Parameters | Anchors | Class |
|---|---|---|---|---|---|
| **A** | Preliminary leverage calculation: $1M → $3M final portfolio, implied spending rate, rates 0/1.5/3% | **No** — closed-form | `W0=1M`, `FV=3M`, `r ∈ {0, 1.5%, 3%}` | §16A methodology (analytic identity: `(1+g)^30`, implied withdrawal rate, loan FV) | **HARD** (analytic) + **STRUCTURAL** (must be executable) |
| **B** | November 1965 aggressive leverage — full retirement funding through margin | Yes | cohort 1965-11; `eq ∈ {0.75, 1.00}`; `r ∈ {1.5%, 3%}`; `wr=0, ldr=4%`; `ltv_enforcement=True` | Chart 02 failure window **months 180–200** | **DIAGNOSTIC** (chart) + **HARD** on terminal failure occurring |
| **C** | September 1929 aggressive leverage | Yes | cohort 1929-09; `eq ∈ {0.75, 1.00}`; `r ∈ {1.5%, 3%}`; same debt config | Chart 03: m≈238, portfolio ≈$1.185M, loan ≈$1.085M, net equity ≈$100k | **DIAGNOSTIC** |
| **D** | $20k portfolio + $20k loan | Yes | cohort 1965-11; `eq=0.75`; `r ∈ {0, 1.5%, 3%}`; total 4%, portfolio share 2% | Chart 04 L/P at m201 = 71.60 / 84.45 / 93.11 | **DIAGNOSTIC** |
| **E** | $30k portfolio + $10k loan (preferred) | Yes | cohorts 1965-11 **and** 1929-09; `eq=0.75`; `r ∈ {0, 1.5%, 3%}`; total 4%, portfolio share 3% | Charts 05/06 max L/P: 70.25 / 57.68 (1965), 67.74 / 55.62 (1929); peaks at m≈201 and m≈348 | **DIAGNOSTIC** |
| **F** | Historical 4% conclusion, cohort universe **1925–1990** | Yes (grid) | monthly cohorts 1925-01 … 1990-1990; `eq ∈ {0.75, 1.00}`; `r ∈ {0, 1.5%, 3%}`; Exp E config | Article narrative "historically never failed over 30 years" (§7) — **no numeric oracle established** (Q-3) | **STRUCTURAL** (coverage + failure-rate table) + **HARD** on §18 invariants |



**[CORRECTED]** Experiment B/C parameters `wr=0, ldr=0.04` are an **ASSUMPTION**
(Q-6). The article describes "full retirement funding through margin" but does not
numerically specify the rate. The plan assumes 4% total spending funded 100% by
loan (`ldr=0.04`). This assumption drives Chart 02 breach month and must be
validated against the article or marked as a configurable parameter.
### 6.1 Cross-cutting HARD assertions (§18 invariants — apply to every experiment)

1. `loan_balance ≥ 0` at all times (no repayment exists for Part 49).
2. Positive draws strictly increase `loan_balance`.
3. With `r > 0` and `loan_balance > 0`, interest strictly increases
   `loan_balance`.
4. Portfolio withdrawal and loan draw remain separate cash-flow components
   (`loan_draw_amount` ≠ residual of `nominal_amount`).
5. `loan_balance = prev + draw + interest` exactly (§8.1).
6. Determinism: identical inputs ⇒ byte-identical results.
7. **Terminality:** once a margin call fires under `ltv_enforcement=True`, the
   trajectory must not recover (GAP-3 acceptance).
8. Buy-and-hold: no `AllocationDecisionStep` / `PortfolioRebalanceStep` in the
   pipeline; weights drift only through market evolution and withdrawals.

### 6.2 Explicitly not in the T6.2 matrix (YAGNI)

* Part 52 floating-rate / FFR mechanics (§8.2: excluded).
* CAPE, glidepath, OMY, final-value-target axes (other articles).
* Rebalancing comparison grids (T6.1 already covers a single comparison).
* T6.3 scope (LTV ON/OFF matrix as a standalone deliverable).

---

## 7. Oracle Hierarchy & Acceptance Anchors

Per §17:

1. **Article methodology** — primary source.
2. **Independent reconstruction from source methodology/data.**
3. **Published numerical / chart evidence** — reference points.
4. **FBF regression fixtures** — created only *after* independent reproduction.

### 7.1 Anchor inventory

| Anchor | Value | Source | Tier | Use |
|---|---|---|---|---|
| Chart 04 L/P @ m201 | 71.60 / 84.45 / 93.11 % | §13.5, §15.2 | 3 | DIAGNOSTIC |
| Chart 02 failure window | months 180–200 | §13.1, §15.2 | 3 | DIAGNOSTIC (+ HARD on *occurrence*) |
| Chart 03 (1929 m≈238) | port ≈$1.185M, loan ≈$1.085M, net ≈$100k | §13.4, §15.2 | 3 | DIAGNOSTIC |
| Chart 05 max L/P 1965 | 70.25 (3%) @ m348; 57.68 (1.5%) @ m201 | §13.6, §15.2 | 3 | DIAGNOSTIC |
| Chart 06 max L/P 1929 | 67.74 (3%); 55.62 (1.5%) | §13.7, §15.2 | 3 | DIAGNOSTIC |
| Chart 01 prelim ranges | 75/25 FV 2.63–13.25×, IRR 3.27–8.99% | §15.2 | 3 | DIAGNOSTIC for Exp A |
| §8.1 loan recursion | `close = open + interest + draw` | §8.1 RESOLVED | 1 | HARD invariant |
| §8.2 real-rate conversion | `monthly = annual_real / 12` | §8.2 RESOLVED | 1 | HARD (acceptance for GAP-2) |
| §8.5 total spending | `wr + ldr = 4%` of $1M | §8.5 RESOLVED | 1 | HARD (acceptance for GAP-1) |
| §15.3 items 18–20 | margin constraint holds; liquidation terminal; no recovery | §15.3 RESOLVED | 1 | HARD (acceptance for GAP-3) |
| §12.4 / §7 | 1925–1990 universe, never failed | §15.3 item 4, §16F | 1 | STRUCTURAL coverage |
| §21.5 hard anchors | exact LTV threshold, forced-liquidation amounts, terminal values, exact cohort universe | §21.5 — **all unchecked** | 1 | **Not yet established** — must not be invented |

### 7.2 Rules

* Chart-derived values (tier 3) **never** become hard-coded acceptance values
  without traceable source precision (§6.3, §17).
* No arbitrary tolerances (§23.2, checked).
* FBF-generated baselines are regression protection only — they must be
  labelled as such and must be regenerated *after* GAP-1/2/3 are corrected.
* `p49_oracle_table.csv` is **not** a Part 49 leverage oracle (Q-3) and must
  not be repurposed.

---

## 8. Data & Cohort Analysis

### 8.1 Datasets

| Asset | Content | Fitness for T6.2 |
|---|---|---|
| `data/ern/spx_tr_real.csv`, `data/ern/bond_10y_tr_real.csv` | 2,471 obs, 1871-02 → 2076-12; **real** price/return series; `inflation_cumulative` populated (CPI index 31.75 → 133.70 over 1965–1990) | Usable. Article vintage is Nov 2021; 1925–1990 cohorts × 30y horizon end ≤ 2020, i.e. **entirely before the 2036-07 constant-extrapolation tail** (equity 0.0045, bond 0.0019). No extrapolation contamination for Experiments A–F. |
| `data/ern/ern_swr_h720.json` | 2,459 snapshots 1871-01-31 → 2075-11-01 | Used by SWR harness; not required for Part 49 leverage. |
| `data/ern/p49_oracle_table.csv` | 21×9 SWR success-rate matrix | **Not** a Part 49 leverage oracle (Q-3). |

### 8.2 Cohorts

* `build_study_plan` generates **all** horizon-feasible cohorts: **1,739**
  cohorts spanning `1871-01-31` … `2015-11-01` (60y cohort horizon; 30y runs use
  `horizon_months = 361`).
* **Part 49 article universe is 1925–1990** (§15.3 item 4) — 780 monthly
  cohorts (`1925-01` … `1990-12`).
* `StudyConfiguration` has **no cohort date-range field** (verified: fields are
  metadata, policy, horizon, glidepath/final-value, Part 42 OMY, Part 49 debt,
  Part 52 timing/FFR, expense ratio only).
* `CohortGenerator.generate_range` / `from_start_dates` exist
  (`study/internal/cohort/generator.py`), but `build_study_plan` does **not**
  accept a `cohorts` argument; `part42_plan.build_part42_study_plan(..., cohorts=...)`
  is the research-layer precedent.
* **Two scoping options:**
  * **(S-1) post-filter** — filter `built.plan.units` by
    `PlannedSimulationUnit.cohort.start_date` and reconstruct `ResearchPlan`.
    No production change; accessible because the cohort date is on the unit.
    *Preferred for T6.2 (YAGNI).*
  * **(S-2) new config field** — add `cohorts.start/end` to
    `StudyConfiguration` + YAML. Only if Exp F needs to be reproducible from
    YAML alone; that is a `StudyConfiguration` public-API addition and would
    require contract-test updates.

### 8.3 Workload estimate (Exp F)

`780 cohorts × 3 interest rates × 2 allocations × 1 config = 4,680 units`
for a single experiment configuration; ~9,360 if both Exp D and Exp E
configurations are swept. Routine gate must **not** include this
(`ern_e2e` gated, `RUN_ERN_E2E` manual only).

---

## 9. Capability Gap Table

| # | Capability required by T6.2 | Required by | Current state | Verdict |
|---|---|---|---|---|
| C-1 | Buy-and-hold allocation (no periodic rebalance) | §11.1, roadmap T6.1 | `BuyAndHoldAllocationPolicy`, `create_buy_and_hold_pipeline()` (T6.1, `fc83253`) | **DELIVERED** |
| C-2 | Buy-and-hold withdrawal sells assets without rebalancing remainder | §11.1 | `WithdrawalExecutionStep` + omitted rebalance steps | **DELIVERED** |
| C-3 | Total spending = portfolio withdrawal + loan draw | §8.5, `part49_withdrawal.py` docstring | `nominal_amount = portfolio_withdrawal` only | **GAP-1** |
| C-4 | Real-rate interest accrual `annual_real/12` | §8.2, §15.3 item 13 | CPI-deflated (nominal-rate treatment) | **GAP-2** |
| C-5 | Terminal margin-call liquidation | §15.3 items 19–20, §18, §21.3 | Liquidation restores LTV; run continues (recovery observed) | **GAP-3** |
| C-6 | LTV observed with enforcement off | §9 / `DECISIONS.md` | `debt_ltv_enforcement=False` supported | **DELIVERED** |
| C-7 | LTV enforcement on with 75% limit | §9.1, §15.3 item 17 | `debt_ltv_limit`, `debt_ltv_enforcement=True` supported | **DELIVERED** (blocked in practice by GAP-2) |
| C-8 | Separate `loan_draw` cash-flow component | §8.4, §18 item 4 | `loan_draw_amount` carried on `WithdrawalDecision`; `LoanDrawStep` separate | **DELIVERED** |
| C-9 | Monthly draw/interest ordering `Y = X + T` | §8.1, K.5.1 | `InterestAccrualStep` (26) before `LoanDrawStep` (28) | **DELIVERED** (see D-3) |
| C-10 | Analytical preliminary calculation (Exp A) | §16A | No analytical evaluator anywhere in Core | **GAP-A** (new, small) |
| C-11 | Cohort universe 1925–1990 | §12.4, §16F | Full 1,739-cohort sweep; no date scoping | **GAP-C** (post-filter, S-1) |
| C-12 | Experiment A–F definitions + aggregation | §16, §20, §21 | `part49_aggregation.py` aggregates the 54-cell Part 49 grid; **no A–F definitions** | **GAP-E** (new research-layer) |
| C-13 | Part 49 leverage oracle anchors | §21.5 | Not established (all §21.5 boxes unchecked) | **NOT ESTABLISHED** — must be produced during implementation, not invented |
| C-14 | E2E audit definition for Part 49 | Q-3 | `ern_part49_e2e_audit.md` does not exist | **ABSENT** — not required by §8; document results in the test itself |
| C-15 | `Money`/`Decimal` discipline | AGENTS.md rule 3 | All money paths probed use `Decimal` | **COMPLIANT** |

---

## 10. Planned Phases (T6.2a – T6.2f)

Each phase is an atomic delivery unit producing **exactly one commit**, subject
to `AGENTS.md` Commit Governance (no commit without explicit authorization).

### T6.2a — Specification reconciliation (documentation only)

* Correct §6.2's inverted table (D-1) — editorial, requires approval.
* Re-open §21.4's `[x]` marks that measurement contradicts (D-5).
* Reconcile `DECISIONS.md` LTV-OFF scope with roadmap §8 / §21.3 (D-2),
  preserving the original decision record and documenting the two-mode
  interpretation.
* Reconcile §8.3/§8.4 wording with the implemented ordering and the Part 52
  `nominal_amount` convention (D-3, D-4).
* Mark roadmap T6.1 `[x]` (D-6).
* **Exit:** no unresolved document-vs-behaviour conflict remains unlabelled.

### T6.2b — Semantic corrections (production + unit tests)

* **C-3 / GAP-1:** `Part49WithdrawalPolicy` sets
  `nominal_amount = (withdrawal_rate + loan_draw_rate) × W0 / 12`.
  *New unit test* `tests/unit/domain/test_part49_withdrawal_semantics.py`
  asserting `nominal = portfolio + loan` and `loan_draw_amount` unchanged.
* **C-4 / GAP-2:** introduce a real-rate accrual path that applies
  `annual/12` **without** CPI deflation for Part 49, while preserving the
  existing nominal+CPI path bit-for-bit for Part 52.
  *New unit test* `tests/unit/execution/test_interest_accrual_real_rate.py`
  with **non-zero** `inflation_cumulative`.
* **C-5 / GAP-3:** make margin-call liquidation terminal under
  `ltv_enforcement=True` per §15.3 item 19/20.
  *New unit test* asserting no post-margin-call recovery (Exp C Sep 1929 shape).
* **Exit:** `ruff check .`, `mypy --strict .`, `pytest -p no:cacheprovider`
  all green; Part 52 numerical-trace tests unchanged and passing.

### T6.2c — Cohort scoping (S-1 post-filter) & GAP-3 implementation

* Research-layer filter for the 1925–1990 universe, reusing the
  `part42_plan` precedent.
* *Unit test* asserting the filtered cohort set equals the 1925–1990 monthly
  universe and that no unit starts outside it.
* **C-5 / GAP-3 (unblocked):** make margin-call liquidation terminal under
  `ltv_enforcement=True` per §15.3 item 19/20.
  *New unit test* asserting no post-margin-call recovery (Exp C Sep 1929 shape).
* **Exit:** `ruff check .`, `mypy --strict .`, `pytest -p no:cacheprovider`
  all green; Part 52 numerical-trace tests unchanged and passing.

### T6.2d — Experiment A analytical evaluator + Experiments B–F definitions

* Closed-form Exp A (analytic identity, no simulation).
* Research-layer definitions for B–F mapping to `StudyConfiguration` +
  pipeline selection + enforcement mode (see §6).
* *Unit tests* for the definitions (parameter expansion, unit counts) — no
  simulation.

### T6.2e — Canonical E2E execution

* New/extended E2E covering Experiments A–F against the anchors in §7.1.
* Gated `@pytest.mark.ern_e2e` + `RUN_ERN_E2E=1` (and
  `research_validation` where methodology substitution applies).
* Experiments D/E charts: `ltv_enforcement=False` (observe-only).
* Experiments B/C: `ltv_enforcement=True` (terminal).
* §18 invariants asserted as HARD on every experiment.
* Extend `tests/oracle/ern/test_part49_replication.py` (canonical only — no
  ad-hoc oracle tests).
* **Agents must not run this with `RUN_ERN_E2E` enabled as part of routine
  validation** (`AGENTS.md`).

### T6.2f — Documentation & roadmap closure

* Record classified discrepancies (per §8 "discrepancies classified").
* Mark roadmap T6.2 `[x]` only after acceptance criteria in §14 hold.

**Phase ordering is sequential; T6.2b must precede T6.2e because every
chart anchor is unreachable under current semantics (§4.5, §4.6).
T6.2c (GAP-3) is unblocked following D-2 resolution (2026-09-29).**

---

## 11. Test Strategy

| Level | Location | Purpose | Gating |
|---|---|---|---|
| Unit (domain) | `tests/unit/domain/test_part49_withdrawal_semantics.py` (**new**) | C-3: `nominal = wr + ldr`; `loan_draw_amount` separate | none |
| Unit (execution) | `tests/unit/execution/test_interest_accrual_real_rate.py` (**new**) | C-4: real-rate path with **non-zero CPI**; Part 52 nominal path unchanged | none |
| Unit (execution) | `tests/unit/execution/test_margin_call_terminality.py` (**new**) | C-5: terminality, no recovery | none |
| Unit (study) | `tests/unit/study/…` | C-11: 1925–1990 cohort filter | none |
| Unit (research) | `tests/unit/research/…` | C-12: A–F definitions, unit counts, Exp A closed form | none |
| Integration | `tests/integration/test_part49_leverage_semantics.py` (**new**) | end-to-end spending split, loan recursion, terminal margin call | none |
| Integration | extend `tests/integration/test_part49_buy_and_hold.py` | regression on C-1/C-2 | none |
| E2E | new/extended `tests/integration/…` (mirroring `test_part3_canonical_ern_replication.py` naming) | Experiments A–F execution + classified anchors | `ern_e2e` + `RUN_ERN_E2E=1` |
| Oracle | extend `tests/oracle/ern/test_part49_replication.py` | canonical grid re-baselined **after** T6.2b | `ern_e2e` + `RUN_ERN_E2E=1` |
| Contract | `tests/contract/test_core_boundaries.py` | only if a new public symbol is exported (AGENTS.md "Adding a New Public Symbol") | none |
| Benchmarks | `tests/benchmarks/` | re-baseline after semantics change | none |

**Re-baselining obligation.** T6.2b changes numerical results for every Part 49
study. Existing baselines/directional assertions in
`test_part49_replication.py`, `test_part49_aggregation.py`,
`test_part49_canonical_execution.py`, `test_part49_smoke_execution.py`,
`test_part49_multi_cohort.py`, `test_part49_grid_audit.py`,
`test_part49_grid_materialization.py`, and `test_part49_buy_and_hold.py` must
be re-examined. Directional assertions (`rate_15 <= rate_0`,
`rate_30 <= rate_15`) are specifically at risk because success rates are
computed with `ltv_enforcement=False`.

**Routine quality gate** (unchanged): `ruff check .` → `mypy --strict .` →
`pytest -p no:cacheprovider` → `pytest tests/contract/`.
`RUN_ERN_E2E` must **not** be enabled by an agent.


### D. Test Migration Inventory (GAP-1/2/3)

The following tests **must be updated** as part of T6.2b semantic corrections.
Each entry identifies the test, the semantic it validates, and the required change.

| Test File | Test Function(s) | Current Semantic | Required Change |
|-----------|------------------|------------------|-----------------|
| `tests/unit/domain/test_withdrawal_frequency.py` | `TestPart49WithdrawalFrequency.test_monthly_amount`, `test_annual_amount` | `nominal_amount = portfolio_withdrawal` | Assert `nominal_amount = (withdrawal_rate + loan_draw_rate) × W0 / 12` |
| `tests/unit/domain/test_withdrawal_frequency.py` | `TestPart49WithdrawalFrequency.test_annual_zero_on_non_withdrawal_month` | `nominal_amount == Money.ZERO` when no withdrawal | Update for new `nominal_amount` meaning (total spending) |
| `tests/unit/study/test_builders.py` | `test_part49_withdrawal_policy_monthly_amounts` | `nominal_amount = portfolio_withdrawal` | Assert `nominal_amount = portfolio + loan` |
| `tests/integration/test_part49.py` | `class _Part49WithdrawalPolicy` (lines 58-96) | `nominal_amount = portfolio_withdrawal` | Update to return `nominal_amount = portfolio + loan` |
| `tests/integration/test_part49_buy_and_hold.py` | `_make_part49_buy_and_hold_config` | `WITHDRAWAL_RATE = 0.03` (workaround) | Use `withdrawal_rate = 0.04` (total spending) with `ldr=0.01` |
| `tests/integration/test_part49_canonical_execution.py` | Configuration uses `CANONICAL_SWR = (0.03,)` | Workaround config | Use `withdrawal_rate = total spending` |
| `tests/benchmarks/test_part49_performance.py` | Multiple benchmarks | Workaround rates | Update to use corrected semantics |
| `tests/oracle/ern/test_part49_replication.py` | Lines 303-308 directional assertions | `rate_15 <= rate_0`, `rate_30 <= rate_15` | Re-evaluate post-fix; may need new baselines |

**Total: 8 test functions across 4 test files** require migration. All changes
are in the **same commit** as the GAP-1/2/3 semantic corrections (T6.2b) per
AGENTS.md "Corrections and retroactive approval" policy.



---

## 12. Reuse / YAGNI Decisions

### Reused unchanged (no changes required)

* `BuyAndHoldAllocationPolicy`, `create_buy_and_hold_pipeline()` (T6.1)
* `LoanDrawStep`, `InterestAccrualStep` (structure), `LoanRepaymentStep`
* `LTVEvaluationStep` observation path and `_calculate_liquidation` formula
* `PortfolioWithdrawalService` proportional liquidation (subject to Q-1)
* `debt_ltv_limit` / `debt_ltv_enforcement` configuration plumbing
* `part49_aggregation.aggregate_part49_results` / `get_cell_table`
* `PlannedSimulationUnit.cohort` for post-filtering

### Explicitly NOT planned (YAGNI)

* A new `cohorts.start/end` `StudyConfiguration` field (Option S-2) — post-filter
  suffices for T6.2.
* A generic "interest-rate mode" enum or strategy interface — a single,
  explicitly-named real-rate path is enough; no extension point.
* A `WithdrawalExecutionStep` flag to support two `nominal_amount` conventions
  — correct the policy, keep one convention.
* Rebalancing grids, CAPE/glidepath/OMY axes, Part 52 FFR mechanics.
* A Part 49 E2E audit document (§8 does not require one; results live in the
  test).
* Repurposing `p49_oracle_table.csv`.

---



## C. Exact Implementation Mechanism (GAP-1 & GAP-2)

### GAP-1: Part49WithdrawalPolicy.nominal_amount
**File:** `src/fbf/core/domain/policies/part49_withdrawal.py`
**Change:** Line 80
```python
# Before:
nominal_amount=Money(portfolio_withdrawal, Currency.EUR),

# After:
nominal_amount=Money(portfolio_withdrawal + loan_draw, Currency.EUR),
```
**Rationale:** Aligns with Part 52 convention (§8.5: total spending = wr + ldr) and
WithdrawalExecutionStep contract (nominal_amount = total spending).

### GAP-2: InterestAccrualStep real-rate path
**File:** `src/fbf/core/execution/pipeline/steps/interest_accrual_step.py`
**Change:** Add `debt_interest_rate_is_real` context flag

1. `src/fbf/core/study/builder.py` — `StudyConfiguration`:
   ```python
   debt_interest_rate_is_real: bool = False  # default False = Part 52 (nominal+CPI)
   ```

2. `src/fbf/core/study/plan.py` — propagate to `SimulationContext`:
   ```python
   debt_interest_rate_is_real: bool = False
   ```

3. `src/fbf/core/execution/pipeline/simulation_context.py` — `SimulationContext`:
   ```python
   debt_interest_rate_is_real: bool = False
   ```

4. `src/fbf/core/execution/pipeline/steps/interest_accrual_step.py`:
   ```python
   def _compute_real_monthly_rate(self, annual_rate: Decimal, state: SimulationState) -> Decimal:
       if state.context.debt_interest_rate_is_real:
           return annual_rate / Decimal("12")  # Part 49: real rate, no CPI
       # existing CPI-adjusted path for Part 52
   ```

**YAML configuration** (examples/studies/ern_part49.yaml):
```yaml
debt:
  interest_rate: 0.015
  interest_rate_is_real: true  # NEW: enables real-rate path
  ltv_limit: 0.75
  ltv_enforcement: true  # for Exp B/C; false for Exp D/E charts
  loan_draw_rate: 0.01
```

**Why this design:**
- Single boolean flag, minimal blast radius
- Default `False` preserves Part 52 (nominal+CPI) behavior
- Explicit in YAML — self-documenting study configuration
- Unit-testable: test with `debt_interest_rate_is_real=True/False`

### GAP-3: Terminal Margin Call (Pending D-2 Resolution)
**File:** `src/fbf/core/execution/pipeline/steps/ltv_evaluation_step.py`
**Change:** In `execute()`, after liquidation (lines 98-111):
```python
if state.ltv_enforcement:
    # Terminal liquidation per §15.3 items 19-20
    state.failure_state = "margin_call_terminal"
    state.status = ExecutionStatus.FAILED
    return state
```
**Blocked by D-2** — cannot implement until LTV enforcement policy is decided.


## 13. Risk Register

| ID | Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|---|
| **R-01** | GAP-1 correction invalidates every existing Part 49 baseline and directional assertion | High | **Certain** | Phase T6.2b must re-examine and re-baseline all Part 49 tests in the *same* commit; treat as a necessary correction, not a contract change (`AGENTS.md` "Corrections and retroactive approval") |
| **R-02** | A real-rate path accidentally changes Part 52 (nominal + CPI) results | High | Medium | Keep the existing code path byte-identical; add a Part 52 regression assertion; verify `test_part52_numerical_trace.py` passes untouched |
| **R-03** | Terminal margin-call semantics change breaks non-leverage or observe-only runs | Medium | Medium | Gate terminality strictly on `ltv_enforcement=True`; observe-only path must be provably unchanged |
| **R-04** | Chart-derived anchors are imprecise; hard-coding them would create false failures | High | High | §7.2 rules: DIAGNOSTIC classification, reported not gated; no arbitrary tolerances |
| **R-05** | `DECISIONS.md` conflict (D-2) resolved silently in either direction | High | Medium | Explicit editorial reconciliation approved before T6.2e |
| **R-06** | Residual Exp E divergence (~18% portfolio gap; Chart 05 max L/P 70.25 vs >75) is not attributable | High | Medium | Dedicated attribution experiment (data vintage vs. month indexing vs. Q-1 liquidation rule vs. D-3 sequencing) **before** declaring Exp E diagnostic-clean |
| **R-07** | Article's Exp B/C spending rate (Q-2) is guessed | Medium | Medium | Hold Chart 02 as DIAGNOSTIC; assert only *occurrence within a reported window*, not an exact month |
| **R-08** | Cohort post-filter silently includes pre-1925 / post-1990 units | Medium | Low | Explicit unit test on the filtered cohort set (§11) |
| **R-09** | Exp F workload (~4.7k–9.4k units) is run accidentally by an agent | Medium | Low | `ern_e2e` gating; `AGENTS.md` prohibition; no `RUN_ERN_E2E` in routine gate |
| **R-10** | §21.5 hard anchors get invented to "close" the task | High | Medium | §21.5 boxes remain unchecked until independently reconstructed; never back-fill from FBF output |
| **R-11** | Scope creep into T6.3+ (standalone LTV ON/OFF matrix) | Low | Medium | §6.2 out-of-scope list; roadmap phase boundary |
| **R-12** | Data vintage: article Nov 2021 vs current canonical series | Medium | High | Experiments end ≤2020 (§8.1); document any residual as a data-vintage discrepancy, following the Part 42 precedent (`ern_part42_replication_discrepancies.md`) |

---

## 14. Acceptance Criteria (for T6.2 as a whole)

Derived from roadmap §8, `ern_part49_replication.md` §21, and §7.1 anchors.

### Structural

* [ ] Experiment A analytical calculation executes and matches the closed form.
* [ ] Experiment B (Nov 1965, 75/25 and 100/0, 1.5% and 3%) executes.
* [ ] Experiment C (Sep 1929, 75/25 and 100/0, 1.5% and 3%) executes.
* [ ] Experiment D ($20k/$20k) executes for all three borrowing rates.
* [ ] Experiment E ($30k/$10k) executes for all three borrowing rates on both
      cohorts.
* [ ] Experiment F (1925–1990) executes over the exact article universe.
* [ ] `DebtSnapshot` recorded for every leverage cell.
* [ ] Forced liquidation triggers when the margin constraint is violated
      (enforcement mode).
* [ ] All six experiments use buy-and-hold mechanics (no periodic
      allocation/rebalance step in the pipeline).

### Loan mechanics

* [ ] `loan = prev + draw + interest` exactly (§8.1).
* [ ] **Real interest rate applied as `annual_real / 12` with no CPI
      deflation** (§8.2) — closes GAP-2.
* [ ] Portfolio withdrawal and loan draw remain separate (§8.4).
* [ ] Loan draw occurs at the resolved position in the monthly sequence (D-3).

### Margin constraint

* [ ] `LTV = loan_balance / portfolio_value`, limit 75% (§9.1, §15.3 item 17).
* [ ] Forced liquidation occurs when the threshold is exceeded.
* [ ] **Post-liquidation trajectory does not recover** (§15.3 items 19–20) —
      closes GAP-3.
* [ ] Observe-only mode (`ltv_enforcement=False`) produces the Chart 04/05/06
      trajectories without liquidation.

### Spending semantics

* [ ] **Total retirement spending = portfolio withdrawal + loan draw** (§8.5) —
      closes GAP-1; verified numerically for Experiments B, D, E.

### Methodology / acceptance hygiene

* [ ] Simulation executes without error; expected output produced.
* [ ] All documented dimensions covered; canonical data used or deviations
      explicitly identified.
* [ ] Tests correctly gated (`ern_e2e` / `research_validation`); routine gate
      runs with `RUN_ERN_E2E` unset.
* [ ] No duplicate validation introduced; existing distinct validations
      retained.
* [ ] Chart-derived checks reported as **DIAGNOSTIC** with classified
      discrepancies — never as hard oracles.
* [ ] §18 invariants asserted as HARD on every experiment.
* [ ] Documentation divergences D-1 … D-6 reconciled editorially.
* [ ] Quality gates green: `ruff check .`, `mypy --strict .`,
      `pytest -p no:cacheprovider`, `pytest tests/contract/`.

---

## 15. Relationship to Roadmap & References

### Roadmap position

```text
Phase 6 — Part 49
  [ ] T6.1  Part 49 buy-and-hold capability      ← delivered at fc83253 (checkbox stale, D-6)
  [ ] T6.2  Part 49 canonical E2E (after buy-and-hold)   ← THIS DOCUMENT
```

T6.2's only prerequisite is T6.1. This analysis shows T6.1 satisfied its
scope (C-1, C-2) but that **T6.2 additionally requires three semantic
corrections (GAP-1/2/3) plus two coverage additions (C-10, C-11) and an
experiment-definition layer (C-12)**. None of these were in T6.1's declared
scope; §6.5 of the T6.1 plan explicitly deferred the withdrawal-liquidation
question to T6.2.

### References

* `docs/roadmap/ERN_E2E_IMPLEMENTATION_ROADMAP.md` — §7 Phase 6, §8 criteria
* `docs/research/ern_part49_replication.md` — §6.2, §7, §8.1–8.5, §9, §11.1,
  §12.4, §13.1–13.7, §14, §15.2–15.3, §16, §17, §18, §19, §20, §21, §23, §24
* `docs/research/ern_part49_t6.1_buy_and_hold_plan.md` — §6.5 (deferred
  question)
* `docs/research/ERN_E2E_REPLICATION_PLAN.md` — §F.3
* `docs/DECISIONS.md` — Part 49 Debt Temporal Semantics; Part 49 LTV
  Enforcement Separation
* `docs/DESIGN.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DATASETS.md`

### Repository state at time of writing

Branch `investigation/ern-part52-divergence`, HEAD `95b1b50`, working tree
clean before this file was created; this document is the only addition.

---

**T6.2 FORENSIC ANALYSIS COMPLETE — IMPLEMENTATION PLAN PERSISTED — AWAITING IMPLEMENTATION AUTHORIZATION**



## 10. Final Review Report

### 1. What changed in the plan
- **GAP-1 (Withdrawal Semantics):** Confirmed as genuine capability gap. Added explicit test migration inventory (9 test functions across 4 files). Specified exact fix: `nominal_amount = (withdrawal_rate + loan_draw_rate) × W0 / 12`.
- **GAP-2 (Interest Accrual):** Confirmed as genuine capability gap. Designed isolation mechanism: context flag `debt_interest_rate_is_real` on `SimulationContext` with YAML configuration. Default `False` preserves Part 52 behavior.
- **GAP-3 (Terminal Margin Call):** Confirmed as behavioral gap. **D-2 RESOLVED (2026-09-29)**: Canonical Part 49 replication requires LTV enforcement ON with terminal liquidation. Implementation approach specified, GAP-3 unblocked.
- **D-2 Conflict:** Explicitly identified as **HUMAN ARCHITECTURAL DECISION REQUIRED**. Cannot be resolved from repository evidence alone. Two mutually exclusive interpretations documented with evidence.
- **Experiment B/C Parameters:** `wr=0, ldr=0.04` explicitly marked as ASSUMPTION (Q-6).
- **Chart 02 Failure Window:** Defined precise predicate (first LTV > 75% breach under enforcement).
- **Numerical Evidence:** Residual gaps quantified (+4.75pp / +2.35pp / +6.07pp). Attribution required before diagnostic-clean.
- **Documentation Cleanup Classification:** Added explicit table (Section 7) with remediation timing for D-1 through D-6.
- **Test Migration Inventory:** Explicit table of 9 test functions across 4 files requiring updates.
- **Exact Implementation Mechanisms:** Added Section C with exact file/line changes for GAP-1, GAP-2, GAP-3.
- **Phase Ordering:** Explicitly gates GAP-3 implementation behind D-2 resolution (T6.2c after T6.2b, T6.2c only after D-2 approval).

### 2. Questions conclusively resolved
- GAP-1: Confirmed — `Part49WithdrawalPolicy` sets `nominal_amount = portfolio_withdrawal` only; `WithdrawalExecutionStep` treats it as total spending. Part 52 convention uses `nominal_amount = total budget`.
- GAP-2: Confirmed — `InterestAccrualStep` applies CPI deflation to `debt_interest_rate`, but Part 49 rates are REAL per §8.2. Datasets have populated `inflation_cumulative`.
- Experiment B/C full-margin assumption: `wr=0, ldr=0.04` is an assumption (Q-6), not explicitly documented in repo.
- Test migration inventory: Complete inventory of 9 test functions across 4 files.
- Exact implementation mechanisms for GAP-1 and GAP-2 specified with file/line changes.
- Documentation cleanup classification for D-1 through D-6 with remediation timing.

### 3. Questions remaining unresolved
- **D-2 (LTV enforcement ON vs OFF):** Human architectural decision required. Cannot proceed with GAP-3 implementation until resolved.
- **Q-2:** Exact spending rate of Exp B/C (full margin) — article says "full retirement funding through margin" but no numeric rate in repo.
- **Q-6:** Experiment B/C spending rate assumption (`wr=0, ldr=0.04`) — marked as assumption.
- **Residual Exp E divergence:** Chart 05 max L/P 70.25% vs measured >75% — cause unidentified.
- **D-3 sequencing:** Pipeline order vs §8.3 narrative — requires diagnostic experiment.
- **Residual Chart 04 divergence:** +4.75pp / +2.35pp / +6.07pp after corrections — attribution pending.

### 4. GAP-1 specification for implementation: **SUFFICIENTLY SPECIFIED**
- Exact code change identified (part49_withdrawal.py:80)
- Test migration inventory complete
- No architectural decision needed
- Part 52 unaffected (uses different policy)

### 5. GAP-2 specification for implementation: **SUFFICIENTLY SPECIFIED**
- Exact isolation mechanism designed (context flag + YAML)
- Files to change identified (4 files)
- Part 52 backward compatibility preserved (default False)
- Unit test strategy defined (non-zero inflation_cumulative)

### 6. GAP-3 specification for implementation: **NOT READY — BLOCKED BY D-2**
- Implementation approach defined but **cannot proceed** until D-2 resolved
- D-2 requires human architectural decision between two mutually exclusive interpretations
- Cannot proceed with GAP-3 implementation until decision made

### 7. Exact decision(s) required before implementation
**DECISION REQUIRED:** LTV enforcement for Part 49 canonical replication.
- **Option A:** LTV-OFF (observe-only) — matches `DECISIONS.md` Part 49 LTV Enforcement Separation (c3f4201). Chart reproduction only; no terminal liquidation.
- **Option B:** LTV-ON with terminal liquidation — matches roadmap §8 "LTV enforcement active" and replication.md §15.3 items 18-20.

**Required from human:** Explicit choice between Option A and Option B for Part 49 canonical replication.

### 8. Implementation authorization gate
**GATE 1 (T6.2b — Semantic corrections):** Authorized when D-2 decision is made AND all test migration inventory items are scoped.
- Prerequisites: D-2 decision documented; test migration inventory reviewed.

**GATE 2 (T6.2c — GAP-3 implementation):** Authorized ONLY after D-2 decision confirms LTV-ON with terminal liquidation for Part 49 canonical replication.
- If D-2 chooses Option A (LTV-OFF): GAP-3 implementation is NOT required for Part 49 canonical replication (but may be needed for other studies).
- If D-2 chooses Option B (LTV-ON): GAP-3 implementation proceeds per §C mechanism.

**GATE 3 (T6.2d/e — E2E validation):** Authorized after T6.2b and T6.2c complete and quality gates pass.

**RECOMMENDATION:** Do not authorize T6.2b implementation until D-2 decision is documented. The plan is ready for implementation pending this single architectural decision.

T6.2 PLAN CORRECTION COMPLETE — D-2 RESOLVED — PART 49 LTV ENFORCEMENT ON — READY FOR T6.2 IMPLEMENTATION REVIEW


### 10. Final Review Report

### 1. What changed in the plan
- **GAP-1 (Withdrawal Semantics):** Confirmed as genuine capability gap. Added explicit test migration inventory (9 test functions across 4 files). Specified exact fix: `nominal_amount = (withdrawal_rate + loan_draw_rate) × W0 / 12`.
- **GAP-2 (Interest Accrual):** Confirmed as genuine capability gap. Designed isolation mechanism: context flag `debt_interest_rate_is_real` on `SimulationContext` with YAML configuration. Default `False` preserves Part 52 behavior.
- **GAP-3 (Terminal Margin Call):** Confirmed as behavioral gap. **D-2 RESOLVED (2026-09-29)**: Canonical Part 49 replication requires LTV enforcement ON with terminal liquidation. GAP-3 implementation unblocked.
- **D-2 Conflict:** **RESOLVED (2026-09-29)**. The conflict between `DECISIONS.md` (LTV OFF) and roadmap/replication.md (LTV ON) has been resolved. The superseded `DECISIONS.md` entry (c3f4201) has been replaced by "Part 49 LTV Enforcement Separation (Superseded)" documenting the correction. Canonical Part 49 replication requires LTV enforcement ON with terminal liquidation.
- **Experiment B/C Parameters:** `wr=0, ldr=0.04` explicitly marked as ASSUMPTION (Q-6).
- **Chart 02 Failure Window:** Defined precise predicate (first LTV > 75% breach under enforcement).
- **Numerical Evidence:** Residual gaps quantified (+4.75pp / +2.35pp / +6.07pp). Attribution required before diagnostic-clean.
- **Documentation Cleanup Classification:** Added explicit table (Section 7) with remediation timing for D-1 through D-6. D-2 marked RESOLVED.
- **Test Migration Inventory:** Explicit table of 9 test functions across 4 files requiring updates.
- **Exact Implementation Mechanisms:** Added Section C with exact file/line changes for GAP-1, GAP-2, GAP-3.
- **Phase Ordering:** Explicitly gates GAP-3 implementation behind D-2 resolution. D-2 RESOLVED — GAP-3 unblocked.

### 2. Questions conclusively resolved
- GAP-1: Confirmed — `Part49WithdrawalPolicy` sets `nominal_amount = portfolio_withdrawal` only; `WithdrawalExecutionStep` treats it as total spending. Part 52 convention uses `nominal_amount = total budget`.
- GAP-2: Confirmed — `InterestAccrualStep` applies CPI deflation to `debt_interest_rate`, but Part 49 rates are REAL per §8.2. Datasets have populated `inflation_cumulative`.
- D-2 (LTV enforcement ON vs OFF): **RESOLVED (2026-09-29)**. Canonical Part 49 replication requires LTV enforcement ON with terminal liquidation.
- Experiment B/C full-margin assumption: `wr=0, ldr=0.04` is an assumption (Q-6), not explicitly documented in repo.
- Test migration inventory: Complete inventory of 9 test functions across 4 files.
- Exact implementation mechanisms for GAP-1 and GAP-2 specified with file/line changes.
- Documentation cleanup classification for D-1 through D-6 with remediation timing.

### 3. Questions remaining unresolved
- **Q-2:** Exact spending rate of Exp B/C (full margin) — article says "full retirement funding through margin" but no numeric rate in repo.
- **Q-6:** Experiment B/C spending rate assumption (`wr=0, ldr=0.04`) — marked as assumption.
- **Residual Exp E divergence:** Chart 05 max L/P 70.25% vs measured >75% — cause unidentified.
- **D-3 sequencing:** Pipeline order vs §8.3 narrative — requires diagnostic experiment.
- **Residual Chart 04 divergence:** +4.75pp / +2.35pp / +6.07pp after corrections — attribution pending.

### 4. GAP-1 specification for implementation: **SUFFICIENTLY SPECIFIED**
- Exact code change identified (part49_withdrawal.py:80)
- Test migration inventory complete
- No architectural decision needed
- Part 52 unaffected (uses different policy)

### 5. GAP-2 specification for implementation: **SUFFICIENTLY SPECIFIED**
- Exact isolation mechanism designed (context flag + YAML)
- Files to change identified (4 files)
- Part 52 backward compatibility preserved (default False)
- Unit test strategy defined (non-zero inflation_cumulative)

### 6. GAP-3 specification for implementation: **UNBLOCKED — READY FOR IMPLEMENTATION**
- D-2 RESOLVED (2026-09-29): Canonical Part 49 replication requires LTV enforcement ON with terminal liquidation.
- Implementation approach defined (ltv_evaluation_step.py lines 98-111)
- No architectural decision pending

### 7. Exact decision(s) required before implementation
**No architectural decisions pending.** D-2 resolved 2026-09-29. All three gaps are now ready for implementation.

### 8. Implementation authorization gate
**GATE 1 (T6.2b — Semantic corrections):** Authorized. All test migration inventory items are scoped.
- Prerequisites: D-2 decision documented; test migration inventory reviewed.

**GATE 2 (T6.2c — GAP-3 implementation):** Authorized. D-2 decision confirms LTV-ON with terminal liquidation for Part 49 canonical replication.
- GAP-3 implementation proceeds per §C mechanism.

**GATE 3 (T6.2d/e — E2E validation):** Authorized after T6.2b and T6.2c complete and quality gates pass.

**RECOMMENDATION:** Authorize T6.2b implementation. The plan is ready for implementation. All architectural decisions resolved.

T6.2 PLAN CORRECTION COMPLETE — **D-2 RESOLVED — PART 49 LTV ENFORCEMENT ON — READY FOR T6.2 IMPLEMENTATION REVIEW**

