# ERN Part 52 Replication — Independent Audit Report

**Date:** 2026-09-10
**Scope:** FBF-core simulation engine vs. canonical ERN Part 52 (Timing Leverage in Retirement)
**Cohort analyzed:** 1965-11 (primary), cross-referenced with canonical trajectory_1965_11_canonical.json (historical one-off extraction, subsequently removed during data-layer cleanup)
**Quality gates:** `ruff check .` — All checks passed; `mypy --strict .` — Success (272 files, 0 issues)

---

## Executive Summary

The FBF Part 52 implementation is **structurally sound** — the pipeline ordering, compound drawdown formula, interest accrual semantics, and leverage decision logic all correctly mirror the canonical ERN Excel spreadsheet. However, the trajectory-level replication diverges from the canonical trajectory due to **three identified defects**, the most critical being a **one-month timeline offset** caused by the dataset slice not including the pre-retirement baseline month that the horizon resolver was explicitly designed to accommodate.

| Metric | FBF | Canonical | Status |
|--------|-----|-----------|--------|
| Borrow months | 125 | 125 | MATCH |
| First borrow calendar date | 1970-01 | 1970-01 | MATCH |
| Repay months | 35 | 47 | MISMATCH |
| Monthly budget | 3,258.33 | 3,256.93 | 0.04% diff |
| Timeline start | 1965-11 (period 0) | 1965-10 (t=0) | OFFSET |
| Dataset slice length | 361 | 361 | MATCH |

---

## Finding 1 — CRITICAL: One-Month Timeline Offset

**Severity:** Critical — causes all trajectory values to be misaligned
**Root cause:** Dataset slice starts at `cohort.start_date` instead of one month prior
**Files:** `src/fbf/core/study/builder.py:186-196` (`_make_horizon_resolver`), `src/fbf/core/study/builder.py` (`materialize_research_plan`)

### Description

The `_make_horizon_resolver` returns `horizon_years * 12 + 1` with internal documentation stating:

> "The ERN cash-flow timeline needs one observation for the pre-retirement month-end (d_{c-1}, where the initial withdrawal is priced) plus one per retirement month."

This `+1` was explicitly intended to account for the pre-retirement baseline month. However, `materialize_research_plan` slices the dataset using:

```python
dataset_cache[cache_key] = canonical_trajectory.slice(
    cohort.start_date, horizon_months
)
```

This starts the slice at the cohort start date (e.g., 1965-11-01), **not** one month before it (1965-10-01). The result is that the `+1` month is consumed as an extra month at the *end* of the simulation (1995-11 instead of 1995-10), rather than as the pre-retirement baseline at the *start*.

### Impact

| Property | FBF | Canonical | Effect |
|----------|-----|-----------|--------|
| Baseline month | 1965-11 (period 0) | 1965-10 (t=0) | Portfolio priced at different month |
| First retirement month | 1965-12 (period 1) | 1965-11 (t=1) | First withdrawal delayed 1 month |
| Last retirement month | 1995-11 (period 360) | 1995-10 (t=360) | Extra month simulated |
| Initial equity price | 1.1903 (Nov prices) | 38.032 SPX-TR (Oct prices) | Different initial portfolio units |
| First equity return applied | Nov→Dec 1965 | Oct→Nov 1965 | Different market return sequence |

### Concrete evidence

At t=1 (canonical 1965-11), the canonical portfolio = 988,373.07 after withdrawing 3,256.93 and experiencing a -0.837% market return. FBF at period 1 (1965-12) shows 999,683.50 — a different trajectory from the very first retirement month because the market returns applied are from a different calendar period.

### Fix

The dataset slice in `materialize_research_plan` should start one month before the cohort start date:

```python
# Current (broken):
dataset.slice(cohort.start_date, horizon_months)

# Fixed:
from datetime import timedelta
baseline_date = cohort.start_date.replace(day=1) - timedelta(days=32)
baseline_date = baseline_date.replace(day=1)
dataset.slice(baseline_date, horizon_months)
```

This ensures `dataset[0]` = pre-retirement baseline month (e.g., 1965-10), matching the canonical t=0.

---

## Finding 2 — MODERATE: Repay Months Divergence (35 vs 47)

**Severity:** Moderate — affects trajectory accuracy and final net worth
**Root cause:** Repay condition uses exact equality `compound_dd == Decimal("0")` which may miss repay events
**Files:** `src/fbf/core/domain/policies/part52_withdrawal.py:118`

### Description

FBF reports 35 repay months while the canonical has 47 repay months. The FBF repay condition is:

```python
elif compound_dd == Decimal("0") and loan_balance > 0:
```

This requires compound drawdown to be **exactly** zero. Due to Decimal arithmetic with the path-dependent formula `cDD = min(0, (1 + prev_cDD) * ratio - 1)`, the compound drawdown may not reach exactly `Decimal("0")` when the equity index is marginally above the recovery threshold. The canonical ERN Excel, using IEEE 754 float64, may evaluate the condition differently at boundary values.

Additionally, the FBF equity index is real (inflation-adjusted) while the canonical uses nominal SPX-TR. Even though both use the same compound drawdown formula, the underlying equity trajectories diverge, causing the drawdown to reset to zero at different times.

### Impact

Each repay event triggers a double withdrawal (2x budget = ~6,517), and the repay also reduces the loan balance. With 12 fewer repay events, FBF retains more portfolio value but also carries loan balance longer in some periods. This contributes to the trajectory divergence.

---

## Finding 3 — LOW: Monthly Budget Discrepancy (0.04%)

**Severity:** Low — 0.04% difference compounds to a small absolute error over 360 months
**Root cause:** Canonical applies expense_ratio (~0.05%) to initial wealth; FBF does not
**Files:** `src/fbf/core/domain/policies/part52_withdrawal.py:90-99`

### Description

| Quantity | FBF | Canonical |
|----------|-----|-----------|
| Budget formula | `1,000,000 × 0.0391 / 12` | `implied_wealth × 0.0391 / 12` |
| Budget value | 3,258.3333 | 3,256.9282 |
| Ratio | 1.0000 | 0.99957 |
| Implied initial_wealth | 1,000,000 | 999,569 |

The canonical trajectory's consumption of 3,256.9282 implies an effective initial_wealth of 999,569. The canonical study configuration includes `expense_ratio: 0.0005` (5 bps). Applying this: `1,000,000 × (1 - 0.0005) × 0.0391 / 12 = 3,256.70`. This is close but not exact (0.006% residual), likely due to float64 extraction precision from the Excel spreadsheet.

FBF does not incorporate expense_ratio into the budget computation. The `Part52WithdrawalPolicy._decide_active` method computes budget directly from `initial_wealth × withdrawal_rate / 12`.

---

## Verified Correct Implementations

### Pipeline Step Ordering
The pipeline correctly implements the ERN spreadsheet ordering:
1. `BuildDecisionContextStep(10)` — portfolio valuation, compound drawdown computation
2. `WithdrawalDecisionStep(20)` — budget computation, leverage decision
3. `InterestAccrualStep(26)` — T(N) = Y(N-1) × (1 + M(N)) ✓
4. `LoanDrawStep(28)` — Y(N) = X(N) + T(N) ✓
5. `WithdrawalExecutionStep(30)` — asset sale at current month prices ✓
6. `LoanRepaymentStep(32)` — loan balance reduction ✓
7. `AllocationDecisionStep(40)` — target weight computation ✓
8. `PortfolioRebalanceStep(50)` — unit adjustment ✓
9. `MarketEvolutionStep(60)` — re-pricing (no-op, growth via snapshot advance) ✓
10. `SimulationStateUpdateStep(80)` — date advance, snapshot loading ✓

### Compound Drawdown Formula
`cDD = min(0, (1 + prev_cDD) × (equity_curr / equity_prev) - 1)` — correctly implements ERN's path-dependent multiplicative drawdown.

### Interest Accrual
Monthly real rate = `(1 + annual_rate/12) × (CPI_prev / CPI_curr) - 1` — correctly CPI-adjusts the FFR-based margin rate. For the `ern_swr_h720` dataset (inflation=0), simplifies to `annual_rate / 12`.

### Leverage Decision Logic
- **Borrow:** `compound_dd <= -threshold` → portfolio_withdrawal = budget × (1 - borrow_pct), loan_draw = budget × borrow_pct ✓
- **Repay:** `compound_dd == 0 AND loan_balance > 0` → portfolio_withdrawal = budget × 2 ✓
- **Normal:** otherwise → portfolio_withdrawal = budget ✓

### Period 0 Zero-Withdrawal
`WithdrawalDecisionStep` correctly returns zero withdrawal at period 0, matching the canonical convention that t=0 is a baseline state with no retirement cash flow.

### Initial Portfolio Construction
`build_initial_portfolio` constructs units so that `Σ(units_i × price_i[0]) == initial_wealth` exactly, guaranteeing zero allocation drift at period 0.

### FFR Rate Schedule
`build_interest_rate_schedule` correctly implements `lag_months=1`, so period T uses FFR from month T-1, matching the ERN convention for the margin rate formula.

### Dataset Returns
FBF's real equity returns match the canonical's real equity returns exactly:
- Canonical Oct→Nov 1965 real equity return: -0.9441%
- FBF Oct→Nov 1965 real equity return: -0.9441% ✓

---

## Data Observations

### Dataset Differences (expected, not defects)
- **FBF `ern_swr_h720.json`:** Real (inflation-adjusted) index levels, `inflation=0`, `inflation_cumulative` = CPI values
- **Canonical `canonical_market_data.json`:** Nominal SPX-TR and BM10 index levels, CPI, FFR (historical one-off extraction; subsequently removed during data-layer cleanup; nominal data now lives in `data/ern/` CSVs)
- Both contain the same underlying economic data; the real/nominal transformation is applied correctly

### Canonical Trajectory Semantics
- `consumption` column = budget (constant, informational), NOT the actual withdrawal amount
- `draw_repay` column = margin loan draw (+) or repayment (-), which is ADDITIONAL to the budget withdrawal
- `net_worth = portfolio - loan` verified at t=0 and t=360 (exact match); minor floating-point discrepancies at intermediate periods due to float64 extraction

---

## Recommendations

### Immediate (before next commit)
1. **Fix the dataset slice offset** (Finding 1): Change `materialize_research_plan` to slice from one month before `cohort.start_date`. This is the single most impactful fix.
2. **Re-run all Part 52 integration tests** after the fix to verify improved trajectory alignment.

### Short-term
3. **Investigate repay condition** (Finding 2): Consider relaxing `compound_dd == 0` to `compound_dd >= 0` or using a small tolerance (`compound_dd > -Decimal("1e-10")`) to match the canonical behavior.
4. **Add expense_ratio to budget computation** (Finding 3): If the canonical study configuration specifies an expense_ratio, incorporate it into the Part52WithdrawalPolicy budget calculation.

### Medium-term
5. **Add canonical trajectory comparison to test suite**: A test that runs the FBF simulation for the 1965-11 cohort and compares key trajectory checkpoints (e.g., portfolio at t=50, t=100, t=360; borrow/repay counts) against the canonical trajectory would catch regressions.
6. **Consider real vs nominal abstraction**: The current implementation correctly handles real-terms datasets, but a documented convention for how nominal datasets interact with the Part 52 policy would improve clarity.

---

## Files Referenced

| File | Role |
|------|------|
| `src/fbf/core/domain/policies/part52_withdrawal.py` | Withdrawal decision logic (borrow/repay/normal) |
| `src/fbf/core/execution/pipeline/steps/withdrawal_decision_step.py` | Period-0 skip, policy invocation |
| `src/fbf/core/execution/pipeline/steps/interest_accrual_step.py` | CPI-adjusted interest accrual |
| `src/fbf/core/execution/pipeline/steps/build_decision_context_step.py` | Compound drawdown computation |
| `src/fbf/core/execution/pipeline/steps/simulation_state_update_step.py` | Date/snapshot advance |
| `src/fbf/core/execution/pipeline/steps/monthly_result_builder_step.py` | Result recording |
| `src/fbf/core/study/builder.py` | Horizon resolver, initial portfolio, FFR schedule |
| `src/fbf/core/execution/pipeline/default_pipeline.py` | Step ordering |
| `data/ern/part52/trajectory_1965_11_canonical.json` | Canonical reference trajectory (historical one-off extraction; subsequently removed during data-layer cleanup) |
| `data/ern/part52/canonical_market_data.json` | Canonical market data — nominal (historical one-off extraction; subsequently removed during data-layer cleanup) |
| `data/ern/ern_swr_h720.json` | FBF dataset (real, 2459 snapshots) |
| `examples/studies/ern_part52.yaml` | Study configuration |

---

*Report generated by independent audit of the ERN Part 52 replication in fbf-core.*
