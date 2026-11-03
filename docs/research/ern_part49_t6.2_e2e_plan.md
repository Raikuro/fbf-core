# T6.2 Implementation Plan: Part 49 Canonical E2E (Experiments B–F)

> **Status:** IMPLEMENTED & VALIDATED — completion recorded 2026-11-03.
>
> **Scope:** Roadmap T6.2, simulation Experiments B–F only. Experiment A remains
> the separate analytical task under Part 49.1 and is not absorbed here.
>
> **Authority:** `ern_part49_replication.md`, the ERN Part 49 article, and the
> approved pre-flight decisions recorded in §2. Chart-derived values remain
> diagnostic unless the article or canonical workbook establishes an exact hard
> anchor.

---

## 1. Objective

1. Deliver canonical buy-and-hold E2E coverage for Part 49 Experiments B–F.
2. Use the existing single Numba execution path. Do not restore the legacy
   Reference engine, add a parallel execution path, or introduce compatibility
   abstractions.
3. Preserve the underlying simulation cash flows while correcting the reported
   total-spending values in the Numba timelines (GAP-1b).
4. Keep canonical workloads gated by `@pytest.mark.ern_e2e` and
   `RUN_ERN_E2E=1`.
5. Preserve production datasets and pinned oracle tables. Do not regenerate
   canonical data.

---

## 2. Pre-Flight Resolution Record

### 2.1 Resolved decisions

| Item | Decision | Evidence |
|---|---|---|
| D-1 Chart 04 table inversion | Editorial correction: the correct ordering is `0% < 1.5% < 3%`. | Article text lists `93 / 84 / just under 72%` in descending-rate order; §13.5/§15.2 chart values are `71.60 / 84.45 / 93.11`. |
| D-3 monthly sequencing | **No code change.** Current `interest → draw → withdrawal → growth` is economically equivalent to growth from the prior month-end before current flows. | Current code and the “growth from prior month-end” variant are identical. The alternative that applies the current month's return before flows (`doc_g0`) shifts the return series and moves Chart 04 away from the article. |
| Q-2/Q-6 Exp B/C spending | `wr=0, ldr=0.04` is **article-derived**, not an assumption. | Article: 30-year loan balances of `$1.5M` at 1.5% and `$1.9M` at 3% imply about `$40k/year` loan draws. |
| Fee scope | Canonical Part 49 uses `expense_ratio=0`. The ERN 0.05% fee is already embedded in the dataset. | `TODO.md` fee-model entry is closed; dataset returns are net of the same fee drag. |
| Experiment F universe | `1925-01 … 1990-12` = **792 cohorts**; six configurations = **4,752 units**. | Verified through `build_study_plan(..., cohort_filter=...)`. |
| Dataset | Use production `data/ern`, not `published_2016`. | The 1990 cohort ends in 2020, so there is no projection contamination. `published_2016` forward-projects 2016–2020 and is test infrastructure. |
| T6.2 scope | Experiments **B–F** only. Experiment A remains 49.1. | Approved pre-flight decision. |
| Experiment B/C mode | **Dual-mode.** Mode 1 (`ltv_enforcement=False`) reproduces the article charts. Mode 2 (`ltv_enforcement=True`) independently validates 75% enforcement and terminal failure. | Chart 02/03 observations are portfolio-below-loan observations, not 75%-margin-call observations. The two modes answer different questions. |
| GAP-1b | Both Part 49 Numba executors must report total spending consistently in `withdrawal_decision.nominal_amount` and `spending_budget`. Cash flows must not change. | The policy already reports total spending; the Numba timelines currently report only the portfolio withdrawal. |

### 2.2 Capability state after `bf42fe5`

The earlier forensic plan's GAP-1, GAP-2, and GAP-3 are **already delivered**:

* GAP-1: `Part49WithdrawalPolicy.nominal_amount` is total spending
  (`portfolio_withdrawal + loan_draw`).
* GAP-2: `debt_interest_rate_is_real=True` bypasses CPI deflation and applies
  `annual_real / 12`.
* GAP-3: margin-call liquidation is terminal under `ltv_enforcement=True`.

The earlier T6.2b/T6.2c phases are therefore obsolete. The only remaining
production correction is **GAP-1b** (timeline reporting).

### 2.3 Remaining diagnostic limitations

| # | Question | Treatment |
|---|---|---|
| Q-1 | Article's asset-liquidation rule for withdrawals | Keep proportional liquidation; article does not specify an alternative. Record as a diagnostic limitation. |
| Q-3 | Numeric oracle for Experiment F | None exists. Exercise structural coverage and the article's qualitative 4% claim; do not invent an oracle. |
| Q-5 | Exact month indexing of “month 201” | Report both index 200 and 201 where relevant; chart-derived values remain diagnostic. |
| Q-7 | Exact tolerance for Chart 03 | Use a documented diagnostic band, not a fabricated hard anchor. Report measured values alongside the article. |

### 2.4 Measured pre-flight values (production dataset)

Exp D, Nov 1965, 75/25, `ltv_enforcement=False`, buy-and-hold:

| Real rate | Measured L/P at index 200 | Article (corrected) |
|---|---|---|
| 0% | 73.20% | ≈72% |
| 1.5% | 83.16% | ≈84% |
| 3.0% | 94.96% | ≈93% |

Exp E, Nov 1965, 75/25, `ltv_enforcement=False`, buy-and-hold:

| Real rate | Measured max L/P | Article |
|---|---|---|
| 1.5% | 59.08% at index 200 | 57.68% |
| 3.0% | 72.24% at index 348 | 70.25% |

Exp B, Nov 1965, `wr=0, ldr=0.04`:

| Real rate | First `portfolio < loan` | First 75% LTV terminal |
|---|---|---|
| 1.5% | index 199 | index 167 |
| 3.0% | index 189 | index 147 |

Exp C, Sep 1929, 75/25, `wr=0, ldr=0.04`, 3% real:

| Mode | Month 238 portfolio | Month 238 loan | Month 238 net |
|---|---|---|---|
| Observe-only | ≈$1.133M | ≈$1.088M | ≈$45k |
| Article | ≈$1.185M | ≈$1.085M | ≈$100k |

Under 75% enforcement the same run terminates at month 204, before month 238.
This is why Experiment C requires dual-mode execution.

Exp F, 1925–1990, Exp E config (`wr=0.03, ldr=0.01`), observe-only:

* 792 cohorts × 6 configurations = 4,752 units.
* 75/25: 2,376/2,376 successful.
* 100/0: 2,373/2,376 successful; the three failures are the 1929-08 cohort at
  all three real rates, depleted at month 295.

The article's “4% never failed” claim applies to the preferred 75/25 strategy.
The 100/0 failures are recorded as a diagnostic result, not silently dropped.

---

## 3. Experiment Matrix

All experiments use buy-and-hold mechanics, production `data/ern`, monthly
withdrawals, and real borrowing rates. `ltv_limit=0.75`.

| ID | Cohort(s) | Equity | Real rates | Spending | Mode | Acceptance |
|---|---|---|---|---|---|---|
| B | 1965-11 | 0.75, 1.00 | 1.5%, 3.0% | `wr=0, ldr=0.04` | Mode 1 observe (`ltv_enforcement=False`); Mode 2 enforce (`True`) | Mode 1: `portfolio < loan` inside the article's 180–200 window. Mode 2: terminal `margin_call_terminal`, no recovery. |
| C | 1929-09 | 0.75, 1.00 | 1.5%, 3.0% | `wr=0, ldr=0.04` | Mode 1 observe; Mode 2 enforce | Mode 1: month-238 values within a documented diagnostic band of the article. Mode 2: terminal failure. |
| D | 1965-11 | 0.75 | 0%, 1.5%, 3.0% | total 4% (2% portfolio + 2% loan) | Observe-only | L/P ordering and approximate Chart 04 values. |
| E | 1965-11, 1929-09 | 0.75 | 0%, 1.5%, 3.0% | total 4% (3% portfolio + 1% loan) | Observe-only | Max L/P below 75%; approximate Chart 05/06 values; ordering by rate. |
| F | 1925-01 … 1990-12 (792) | 0.75, 1.00 | 0%, 1.5%, 3.0% | Exp E config | Observe-only | 4,752 units; 75/25 all successful; 100/0 exactly three 1929-08 failures; no unexpected failure states. |

Experiment A (analytic `$1M → $3M`, implied withdrawal rates) is **not** part of
T6.2.

---

## 4. Data and Cohorts

* Production files: `data/ern/spx_tr_real.csv`, `data/ern/bond_10y_tr_real.csv`,
  `data/ern/cpi.csv`.
* Cohort universe: `1925-01` through `1990-12` inclusive.
* `build_study_plan` / `run_study` accept `cohort_filter`, so no new
  `StudyConfiguration` field is required.
* `published_2016` is not used for B–F.
* `p49_oracle_table.csv` is not a Part 49 leverage oracle and is not
  repurposed.

---

## 5. Remaining Capability Gap

### GAP-1b — Numba timeline reports only portfolio withdrawal

**Specification.** Total spending is `portfolio_withdrawal + loan_draw`.
`WithdrawalDecision.nominal_amount` and `spending_budget` must report total
spending; `loan_draw_amount` remains the separately reported draw.

**Actual.** Both `Part49NumbaExecutor` and `Part49BuyAndHoldNumbaExecutor`
construct timelines with `withdrawal_amounts=[portfolio_withdrawal]`. The
simulation cash flow is correct, but the reported `nominal_amount` and
`spending_budget` understate total spending.

**Correction.** Pass `portfolio_withdrawal + loan_draw` as the timeline
withdrawal amount in both executors. Do not change the kernel, portfolio sale,
loan draw, debt balance, or failure semantics.

**Regression coverage.** Add tests for both executors asserting:

* `withdrawal_decision.nominal_amount == portfolio_withdrawal + loan_draw`;
* `withdrawal_decision.spending_budget == total spending`;
* `withdrawal_decision.loan_draw_amount == loan_draw`;
* portfolio values and loan balances are unchanged relative to the independent
  debt recurrence.

---

## 6. Implementation Phases

Each phase is an atomic delivery unit. Do not commit until explicitly
authorized.

### T6.2a — This plan — COMPLETE

* Replace stale forensic conclusions with the approved pre-flight decisions.
* Mark GAP-1/2/3 delivered, GAP-1b outstanding.
* Fix the Experiment F count, dataset choice, scope, and dual-mode B/C design.
* **Exit:** no unresolved document-vs-decision conflict remains.

### T6.2b — GAP-1b correction and regression tests — COMPLETE

* Update both Part 49 Numba executors to report total spending in timelines.
* Add the regression tests described in §5.
* **Exit:** `ruff`, `mypy --strict`, routine `pytest`, and contract tests pass;
  cash-flow results are unchanged.

### T6.2c — Canonical B–F test module — COMPLETE

* Add one canonical oracle test module under `tests/oracle/ern/`.
* Build configurations from the production YAML in-memory; do not add
  production research-layer abstractions.
* Implement B/C dual-mode, D/E observe-only, and F structural coverage.
* Mark canonical workloads `@pytest.mark.ern_e2e`.
* **Exit:** the module is skipped without `RUN_ERN_E2E=1` and executes
  successfully with it.

### T6.2d — Targeted canonical validation — COMPLETE

* Run the new B–F module once with `RUN_ERN_E2E=1` (not the full oracle suite).
* Record measured anchors, failure counts, and any remaining discrepancies.
* **Exit:** all hard invariants pass; diagnostic anchors are reported.

### T6.2e — Documentation closure — COMPLETE

* Update `ern_part49_replication.md` status and E2E status.
* Update roadmap T6.1/T6.2 markers and the stale Part 49 status text.
* Update `TODO.md` only where the pre-flight identified genuine remaining work.
* Do not regenerate datasets or pinned oracle tables.

---

## 7. Test Strategy

| Level | Location | Purpose | Gating |
|---|---|---|---|
| Integration | `tests/integration/test_part49_numba_executor.py` | GAP-1b timeline reporting for the rebalancing Numba executor | none |
| Integration | `tests/integration/test_part49_buy_and_hold_numba_executor.py` | GAP-1b timeline reporting for the buy-and-hold Numba executor | none |
| Oracle | new `tests/oracle/ern/test_part49_canonical_bf.py` | Canonical B–F execution, dual-mode B/C, anchors, F coverage | `ern_e2e` + `RUN_ERN_E2E=1` |
| Contract | unchanged | No new public API symbols are required | none |

Routine quality gate:

```bash
ruff check .
mypy --strict .
pytest -p no:cacheprovider
pytest tests/contract/
```

Canonical validation (manual, targeted):

```bash
RUN_ERN_E2E=1 pytest tests/oracle/ern/test_part49_canonical_bf.py -v
```

---

## 8. Acceptance Criteria

### Hard invariants

* [x] GAP-1b: both Numba executors report total spending while leaving cash
      flows unchanged.
* [x] Loan recursion: `loan = previous + draw + interest` for every leveraged
      run.
* [x] Real-rate conversion: `annual_real / 12` with no CPI deflation.
* [x] Portfolio withdrawal and loan draw remain separate.
* [x] `LTV = loan / portfolio`; 75% enforcement is terminal under Mode 2.
* [x] Observe-only Mode 1 does not liquidate.
* [x] All six experiments use buy-and-hold mechanics (no rebalance step).

### Structural

* [x] Exp B: 1965-11, 0.75/1.00 equity, 1.5%/3.0% rates, both modes.
* [x] Exp C: 1929-09, 0.75/1.00 equity, 1.5%/3.0% rates, both modes.
* [x] Exp D: 1965-11, 0.75 equity, three rates, observe-only.
* [x] Exp E: 1965-11 and 1929-09, 0.75 equity, three rates, observe-only.
* [x] Exp F: 792 cohorts × 6 configurations = 4,752 units.
* [x] Experiment A is not part of T6.2.

### Diagnostic

* [x] Chart 02 `portfolio < loan` window 180–200.
* [x] Chart 03 month-238 values reported against the article.
* [x] Chart 04 L/P values reported against the corrected article ordering.
* [x] Chart 05/06 max L/P values reported; no hard-coded chart tolerances.
* [x] Exp F 75/25 success count; 100/0 failures recorded as diagnostics.

---

## 9. Risks and Mitigations

| ID | Risk | Mitigation |
|---|---|---|
| R-01 | GAP-1b changes reported values used by existing tests | Search all Part 49 timeline assertions; no known test asserts the old nominal value. Add explicit regression tests. |
| R-02 | Dual-mode B/C is mistaken for a single canonical result | Label Mode 1 as chart reproduction and Mode 2 as enforcement validation in test names and report output. |
| R-03 | Chart-derived anchors become false hard gates | Keep them diagnostic; assert invariants and occurrence/ordering, not exact chart pixels. |
| R-04 | Exp F is accidentally run in routine validation | Keep the `ern_e2e` marker and `RUN_ERN_E2E` gate. |
| R-05 | 100/0 Exp F failures are mistaken for a regression | Document the exact 1929-08 failures and the article's 75/25 claim. |
| R-06 | Dataset regeneration contaminates validation | Do not regenerate data; use the committed production dataset. |

---

## 9. Completion Record

- GAP-1b is implemented in both Part 49 Numba executors and covered by
  integration regression tests; timeline total spending now includes the loan
  draw without changing cash flows.
- Canonical Experiments B–F are implemented in
  `tests/oracle/ern/test_part49_canonical_bf.py` and validated under
  `RUN_ERN_E2E=1`, including B/C dual-mode and the 4,752-unit Experiment F
  run.
- `ruff check .`, `mypy --strict .`, routine `pytest -p no:cacheprovider`, and
  `pytest tests/contract/` pass.
- Production datasets and pinned oracle tables were not regenerated.

---

## 10. Commit Governance

Implementation and validation are separate from commit authorization. After the
plan, code, tests, and validation are complete, report the diff scope and
request explicit authorization for a single T6.2 commit. Do not create
intermediate commits.
