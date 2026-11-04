# ERN Part 2 — Capital Preservation vs. Capital Depletion

**Status:** IMPLEMENTED — Part 2.1 canonical FV>0 E2E.
**Source:** [ERN Part 2](https://earlyretirementnow.com/2016/12/14/the-ultimate-guide-to-safe-withdrawal-rates-part-2-capital-preservation-vs-capital-depletion/)
**Created:** 2026-09-14
**Revised:** 2026-11-04 (Part 2.1 implementation — warm-up timing resolved, production regression fixture generated, canonical anchors validated on the frozen published-2016 dataset)
**Prior revision:** 2026-09-14 (evidence classification pass — §2.1 inheritance discipline, cohort statement rewrite, anchor precision verification, grid evidence downgrade, regression fixture naming, ±1pp tolerance justification, warm-up reframe, YAML gap preservation, behavioral E2E framing, FV=0 overlap invariant)

---

## 1. Research Objective

ERN Part 2 extends the Part 1 baseline by studying how success probabilities change when the retirement target is **capital preservation** (maintaining a fraction of initial real wealth) rather than **capital depletion** (consuming all wealth). The article asks: how much does the sustainable withdrawal rate decrease when the retiree must preserve 25%, 50%, 75%, or 100% of initial real capital at the end of the retirement horizon?

The article reuses the monthly-frequency rolling-cohort historical simulation framework from Part 1 and adds a **final-value target** dimension to the success criterion.

---

## 2. Methodology

### 2.1 Inherited from Part 1 (unchanged)

All of the following are inherited unchanged from Part 1 (see `ern_part1_replication.md` Section 2). Each item carries the evidence classification established by the Part 1 methodology audit. Do not inherit a statement from Part 1 merely because it appears there — every item must be independently verified against the Part 1 audit classification.

**Evidence classification legend** (per Part 1 §6.3):

| Tag | Meaning |
|-----|---------|
| **ERN source-established** | What the article explicitly states |
| **Independently-derived replication assumption** | Arithmetic or interpretation required to turn the prose into an executable monthly model |
| **FBF/oracle-consistent only** | Behavior observed in the current implementation but not established by the article |

| Assumption | Value | Evidence Classification |
|------------|-------|------------------------|
| Portfolio | Two-asset: US equities (S&P 500 TR) + US bonds (10Y Treasury TR) | **ERN source-established** — article §2.1 |
| Historical data period | January 1871 through September 2016 | **ERN source-established** — article states real returns through Sep 2016 |
| Monthly simulation frequency | Monthly | **ERN source-established** — article explicitly uses monthly frequency |
| Real-return treatment | CSVs contain real (inflation-adjusted) returns | **ERN source-established** — article: "translated into monthly real returns" |
| 0.05% annual fee drag | 0.05% annual; monthly conversion `1 - annual/12` | **ERN source-established** for the 0.05% magnitude; **independently-derived replication assumption** for the monthly conversion formula — article does not specify the monthly conversion formula or exact point of application within each step |
| Initial withdrawal timing | One-twelfth of annual rate, applied at market close of previous month | **ERN source-established** — the article's warm-up states the first withdrawal occurs at the beginning of the month; **verified equivalent** to the FBF `d_{c-1}..d_{c+T-1}` window by the deterministic warm-up test |
| Inflation-adjusted withdrawals | CPI-adjusted monthly | **ERN source-established** — article: CPI-adjusted; **FBF/oracle-consistent only** for the real-space constant-withdrawal representation — `FixedRealWithdrawalPolicy` is an FBF implementation detail |
| Portfolio rebalancing | To target weights at month end | **ERN source-established** — article: rebalancing at month end |
| Forward projection after Sep 2016 | Equity ~6.6% real annual, bonds 0% for first 10y then ~2.6% real annual | **ERN source-established** for the annual rates (~6.6%, ~2.6%, 0% for 10y); **independently-derived replication assumption** for the annual-to-monthly conversion `(1+r)^(1/12)-1` and the exact 120-month boundary — article does not publish monthly rates or the precise month count |
| Cohort construction | 1,739 rolling monthly cohorts shared across all horizons | **Independently-derived replication assumption** — article states 1,739 start dates; the shared-cohort-universe design is the source-level fact; the FBF mechanism (longest-horizon-derived on a 2,459-snapshot dataset) is an implementation detail, not article methodology (see §2.1.1) |
| Equity allocations | 0% to 100% in 5% increments (21 values) | **FBF/oracle-consistent only** for the 21-value grid — not explicitly enumerated in article text; inferred from the table image and Part 1 structure (see §5.1) |
| Withdrawal rates | 3.0% to 5.0% in 0.25% increments (9 values) | **FBF/oracle-consistent only** for the 9-value grid — not explicitly enumerated in article text; inferred from the table image and Part 1 structure (see §5.1) |

#### 2.1.1 Cohort Universe: Source-Level Fact vs. Implementation Detail

The shared cohort universe is a source-level methodological fact:

> The experiment uses 1,739 retirement start dates across the four horizons in Part 1, and Part 2 reuses that same cohort universe for its 30Y and 60Y results.

The explanation involving "determined by longest horizon 60Y = 721 months on a 2,459-snapshot dataset" is an FBF implementation/reconstruction explanation — how the cohort dates are algorithmically constructed from the dataset structure. It is not something the Part 2 article establishes.

The following should be kept distinct:

1. **Article experiment dimension:** 1,739 shared start dates (ERN source-established count).
2. **FBF mechanism used to construct those dates:** implementation detail (how the algorithm produces those dates from the dataset).
3. **Dataset snapshot count / 721-month calculation:** implementation/reconstruction detail (how the 2,459-snapshot dataset constrains the feasible cohort window).

Part 2 introduces **no change** to any of these inherited assumptions.

### 2.2 Part 2-Specific Methodology

#### 2.2.1 Final-Value Target Dimension

Part 2 adds a final-value target as an additional **evaluation dimension**. The
target does not select a different simulation recurrence or alter the
month-by-month path; it is applied to the completed trajectory. The success
criterion becomes:

```
success = survived (portfolio did not deplete before horizon end)
          AND
          (final_value_target is None
           OR final_wealth >= final_value_target * initial_wealth)
```

where:

- `survived` means the portfolio did not reach zero (or negative) at any point during the simulation.
- `final_wealth` is the portfolio value at the end of the final simulation month.
- `initial_wealth` is the starting portfolio value.
- `final_value_target` is a fraction (e.g., `0.5` means 50% of initial wealth).

**Critical property:** The final-value criterion is evaluated **only at the final period**. A trajectory may temporarily fall below the target during retirement and still count as successful, as long as it finishes at or above the target. This is explicitly stated in the article:

> "Note that the success criterion applies only to the final period. You could temporarily fall below that target, but as long as you finish above the target, we call it a success."

This is **not** a path constraint. The engine continues simulating after a temporary target breach. The only early-termination condition is portfolio depletion (value ≤ 0).

#### 2.2.2 Final-Value Targets

| Target | Fraction | Meaning |
|--------|----------|---------|
| 0% | 0.0 | Capital depletion (same as Part 1 / Trinity Study) |
| 25% | 0.25 | Preserve 25% of initial real wealth |
| 50% | 0.50 | Preserve 50% of initial real wealth |
| 75% | 0.75 | Preserve 75% of initial real wealth |
| 100% | 1.00 | Full capital preservation (maintain all initial real wealth) |

#### 2.2.3 Horizons

The article reports success probabilities for **30-year and 60-year horizons only**. The 40-year and 50-year horizons from Part 1 are omitted "to keep the table size manageable."

---

## 3. Final-Value Target Semantics (FBF Implementation)

### 3.1 Success Criterion in FBF

The FBF engine implements the terminal-only final-value check as follows:

**File:** `src/fbf/core/execution/pipeline/statistics_builder.py:59-63`

```python
success = survived
if survived and state.context.final_value_target is not None:
    threshold = state.context.final_value_target * state.context.initial_wealth.amount
    if final_wealth.amount < threshold:
        success = False
```

The formula is:

```
success = survived AND (final_wealth >= final_value_target × initial_wealth)
```

Fixed-real Numba execution uses the workbook recurrence for every target. The
terminal threshold is applied to the completed trajectory by `_apply_fv_check`.
Positive-target final wealth can therefore differ from earlier builds that
selected a non-workbook recurrence for positive targets.

### 3.2 Properties

| Property | FBF Behavior | Article Requirement |
|----------|-------------|---------------------|
| Evaluated at terminal period only | ✅ Yes — checked once after simulation completes | ✅ "success criterion applies only to the final period" |
| Temporary breach allowed | ✅ Yes — engine continues after target breach | ✅ "You could temporarily fall below that target" |
| Same simulated path for every target | ✅ Yes — universal workbook recurrence; target applied after the path | ✅ Consistent with article |
| Proportional comparison | ✅ `target_fraction × initial_wealth` | ✅ "25%, 50%, 75%, and 100% of the capital" |
| Only depletion stops simulation | ✅ Early termination only on `value ≤ 0` | ✅ Consistent with article |
| Real terms | ✅ Engine operates on real returns for ERN datasets | ✅ "real, inflation-adjusted" |

### 3.3 Precedent: Multiple FV Targets in FBF

The existing `ern_part3_replication.yaml` already demonstrates multi-target support:

```yaml
final_value_target: [0.0, 0.5]
```

This produces a Cartesian product: each (equity, rate, horizon) cell is duplicated for each FV target. The YAML syntax is ready for Part 2 expansion.

---

## 4. Warm-Up Calculation

The article presents a deterministic Excel warm-up example before the historical simulation. It assumes:

- Initial portfolio: $1,000,000
- Constant real portfolio return: 4% p.a.
- First withdrawal at the **beginning** of the first month
- Subsequent withdrawals are inflation-adjusted
- Several final-value targets/horizons

### 4.1 Published Maximum Withdrawal Rates

| Strategy | SWR | Horizon | Target |
|----------|-----|---------|--------|
| Full capital preservation | 3.92% | 60Y | FV=100% |
| 50% remaining after 60Y | 4.12% | 60Y | FV=50% |
| Capital depletion after 60Y | 4.33% | 60Y | FV=0% |
| 50% remaining after 30Y | 4.79% | 30Y | FV=50% |
| Capital depletion after 30Y | 5.66% | 30Y | FV=0% |

### 4.2 The 3.92% vs 4.00% Difference

The article explains: "Why not 4.00%? That's because the initial withdrawal takes place at the beginning, not the end of the month." The 0.08 percentage-point difference results from the timing of the first withdrawal relative to the first return accrual.

### 4.3 Classification

These values are **published analytical reference values** — deterministic results from a simplified constant-return model. They are not the primary historical replication oracle, but they are executable acceptance criteria for withdrawal timing and terminal-value semantics.

### 4.4 Resolution: FBF Reproduces the Warm-Up

The warm-up timing question is resolved. The article's beginning-of-month withdrawal is economically and temporally equivalent to the FBF ERN window `d_{c-1}..d_{c+T-1}`:

1. The initial portfolio is observed at the previous month's close (`d_{c-1}`).
2. The first withdrawal occurs at that close, before any retirement return is applied.
3. The portfolio then earns `T` monthly returns, with each subsequent withdrawal taken at the beginning of its month.
4. The final value is measured at `d_{c+T-1}` after exactly `T` return intervals.

The annual 4% constant return is converted to an effective monthly return, `(1.04)^(1/12) - 1`. Using that convention, the FBF production path reproduces all five published maximum withdrawal rates to their published two-decimal precision.

The deterministic validation is `tests/oracle/ern/test_part2_warmup.py`. It constructs a constant-return dataset, executes the production FAST path with two probe withdrawal rates, and solves the linear withdrawal relation for each final-value target. A simple-additive or end-of-month recurrence does not reproduce the published `3.92%` / `5.66%` values.

---

## 5. Simulation Grid

### 5.1 Article's Grid (evidence classification)

The article's main results table (image: `swr-part2-table1.png`) has the following evidence status for each dimension:

| Dimension | Values | Evidence Classification |
|-----------|--------|------------------------|
| Horizons | 30Y, 60Y | **ERN source-established** — article text states 30Y and 60Y horizons |
| Final-value targets | 0%, 25%, 50%, 75%, 100% | **ERN source-established** — article text lists these targets |
| Equity weights | 0% to 100% in 5% increments (21 values) | **Visually observed from the published table image** — not explicitly enumerated in article text. The article text only states: "The table below is an extension of the results from last week." The 21-weight grid is inferred from the image and Part 1's structure. If the image has been inspected, this is visually verified; if not, the evidence classification should be downgraded to "inherited from Part 1 structure" |
| Withdrawal rates | 3.0% to 5.0% in 0.25% increments (9 values) | **Visually observed from the published table image** — not explicitly enumerated in article text. Same caveat as equity weights above |

**Important:** The exact equity-weight and withdrawal-rate grid values are embedded in the article's table image, not in the textual source. The 21-weight × 9-rate grid is inferred from Part 1's table structure and the visual appearance of the image. The document does not claim that the image independently establishes these values — they are visually observed and consistent with Part 1's structure.

### 5.2 FBF's Designated Reproduction Subset

| Dimension | FBF Subset | Article Full Grid |
|-----------|-----------|-------------------|
| Horizons | 30Y, 60Y | 30Y, 60Y |
| Equity weights | 0%, 25%, 50%, 75%, 100% (5 values) | 0%–100% in 5% steps (21 values) |
| Withdrawal rates | 3.0%–5.0% in 0.25% steps (9 values) | 3.0%–5.0% in 0.25% steps (9 values) |
| Final-value targets | 0%, 25%, 50%, 75%, 100% (5 values) | 0%, 25%, 50%, 75%, 100% (5 values) |
| Cohorts | 1,739 (shared across all horizons) | 1,739 (shared across all horizons) |

**Note on cohort count:** The article uses 1,739 retirement start dates shared across all horizons in Part 1, and Part 2 reuses that same cohort universe for its 30Y and 60Y results. This is the source-level methodological fact: the same cohort start dates are used across horizons for cross-horizon comparability. The FBF implementation constructs these dates using a rolling-monthly algorithm on the 2,459-snapshot dataset; the longest horizon (60Y = 721 months) determines the feasible window, but this is an implementation mechanism, not an article-level specification. For shorter horizons (e.g., 30Y = 361 months), each of the same 1,739 cohorts receives a shorter dataset slice, but the cohort start dates are identical.

**FBF subset size:**

```
5 equity × 9 rates × 2 horizons × 5 FV targets × 1,739 cohorts
= 782,550 simulation units
```

**Article full grid size (estimated):**

```
21 equity × 9 rates × 2 horizons × 5 FV targets × 1,739 cohorts
= 3,286,710 simulation units
```

### 5.3 Distinction Between Grid Scopes

1. **Full article research grid** — 21 equity weights × 9 rates × 2 horizons × 5 FV targets. The 21 weights and 9 rates are visually observed from the article's table image, not enumerated in text. Horizons and FV targets are source-established.
2. **FBF designated reproduction subset** — 5 representative equity weights × 9 rates × 2 horizons × 5 FV targets. This is the subset implemented by the Part 2.1 E2E.
3. **Part 2.1 E2E** — validates the FBF subset against the generated regression fixture and the four published anchors, not the complete article grid.

---

## 6. Published Numerical Anchors

### 6.1 Exact Values from Article Text

The article explicitly states these success rates as Part 2-specific results:

| Equity | Rate | Horizon | FV Target | Success Rate | Source | Precision |
|--------|------|---------|-----------|-------------|--------|-----------|
| 100% | 3.5% | 60Y | 0% | 98% | Article text | Rounded to whole percentage |
| 100% | 3.5% | 60Y | 100% | 96% | Article text | Rounded to whole percentage |
| 100% | 4.0% | 30Y | 0% | 97% | Article text | Rounded to whole percentage |
| 100% | 4.0% | 30Y | 100% | 80% | Article text | Rounded to whole percentage |

**Verification notes for each anchor:**

1. **100% equity / 3.5% / 60Y / FV=0 → 98%**: Exact allocation (100% equity), exact rate (3.5%), exact horizon (60Y), exact FV target (0%). Value appears in article prose as a success-rate comparison. Rounded to whole percentage.
2. **100% equity / 3.5% / 60Y / FV=100% → 96%**: Same cell with FV=100% target. Value appears in article prose. Rounded to whole percentage.
3. **100% equity / 4.0% / 30Y / FV=0 → 97%**: Exact allocation (100% equity), exact rate (4.0%), exact horizon (30Y), exact FV target (0%). Value appears in article prose. Rounded to whole percentage.
4. **100% equity / 4.0% / 30Y / FV=100% → 80%**: Same cell with FV=100% target. Value appears in article prose. Rounded to whole percentage.

**All four anchors are stated in article prose, not only visible in the table image.** The article refers to the original 2016 table (consistent with the canonical dataset period 1871-01 through 2016-09), not the later 2023 updated table.

**Inherited Part 1 cross-reference (not a new Part 2 anchor):**

| Equity | Rate | Horizon | FV Target | Success Rate | Source |
|--------|------|---------|-----------|-------------|--------|
| 50% | 4.0% | 60Y | 0% | 65% | Part 1 result, cross-referenced in Part 2 article text |

The 65% value appears in the Part 2 article as a comparison point ("look at the 65% success rate vs. 95% success rate for capital depletion, 50% equity weight, and 4% withdrawal rate"), but it is a Part 1 result for FV=0, not a new Part 2 finding. It should be used as a Part 1 cross-check, not as a Part 2-specific anchor.

### 6.2 Warm-Up Reference Values (Deterministic)

| Target | Horizon | SWR | Source |
|--------|---------|-----|--------|
| FV=100% | 30Y | 3.92% | Article warm-up |
| FV=50% | 60Y | 4.12% | Article warm-up |
| FV=0% | 60Y | 4.33% | Article warm-up |
| FV=50% | 30Y | 4.79% | Article warm-up |
| FV=0% | 30Y | 5.66% | Article warm-up |

### 6.3 Scatter-Plot Statistical References

| Metric | Value | Horizon | Source |
|--------|-------|---------|--------|
| Median SWR difference (FV=0 vs FV=100%) | ≈ 1.25 pp | 30Y | Article text |
| Median SWR difference (FV=0 vs FV=100%) | ≈ 0.19 pp | 60Y | Article text |

### 6.4 Classification

| Value | Classification | Notes |
|-------|---------------|-------|
| 98%, 96%, 97%, 80% success rates | **Rounded published values** — Part 2-specific anchors from article text | ERN publishes success probabilities as whole percentages; values are rounded to nearest integer |
| 65% success rate (50% equity / 4% / 60Y / FV=0) | **Inherited Part 1 cross-reference** — not a new Part 2 anchor | Part 1 result, cross-referenced in Part 2 article text for comparison |
| 3.92%, 4.12%, 4.33%, 4.79%, 5.66% SWR | **Published analytical reference values** — deterministic warm-up, not historical simulation | Source-established; reproduced by the production path and pinned by the warm-up test (§4.4) |
| 1.25pp, 0.19pp median differences | **Rounded published values** — approximate scatter-plot statistics | Per-cohort data not available; exact values not published |
| 0.50% haircut for 30Y→60Y extrapolation | **Qualitative research conclusion** — approximate rule of thumb from article summary | Not a hard numerical test |

---

## 7. Qualitative Findings

The following are the article's main conclusions. They are research observations, not software acceptance criteria.

### 7.1 Capital Preservation vs. Depletion

Capital preservation materially lowers sustainable withdrawal rates. The warm-up calculation shows:

```
30Y:  FV=0 → 5.66%,  FV=50% → 4.79%,  FV=100% → 3.92%
60Y:  FV=0 → 4.33%,  FV=50% → 4.12%,  FV=100% → 3.92%
```

Over 30 years, capital depletion adds 1.74 percentage points to the SWR (5.66% − 3.92%). Over 60 years, it adds only 0.41 percentage points (4.33% − 3.92%).

### 7.2 30Y vs 60Y Extrapolation

Capital-depletion rules should **not** be extrapolated from 30 years to 60 years. The article argues:

- Median outcomes are misleading — the Trinity Study is about **tail-event** probabilities.
- After 30 years, a portfolio with value > 0 (not a Trinity failure) may still be compromised enough to run dry in another 5–10 years.
- The article reports a **0.50 percentage-point haircut** to the withdrawal rate is needed to restore comparable success rates when extending from 30Y to 60Y.

### 7.3 Equity Allocation

For long horizons, success probabilities generally improve with higher equity allocations and deteriorate materially below roughly 70% equity. The article notes: "the success probabilities seem to drop off quite significantly when going below 70% equity weight."

### 7.4 Capital Preservation Paradox

The 60-year capital-preservation success rate can be **slightly higher** than the 30-year capital-preservation success rate at sufficiently high equity allocations. This is not a contradiction: a portfolio below 100% after 30 years may recover above the target during the following 30 years.

**Implication for implementation:** The final-value target must be evaluated **only at the final horizon**, not at every intermediate month. This is consistent with FBF's terminal-only evaluation (Section 3.2).

### 7.5 Bonds

Bonds have a low historical real return (2.6% real over the full 1871+ period) and become increasingly problematic for very long retirement horizons. Over 60 years, "the success probability is monotonically increasing in the equity weight."

---

## 8. Scatter-Plot Results

The article presents scatter plots comparing per-cohort SWRs under FV=0 vs FV=100% for an 80/20 portfolio:

### 8.1 30-Year Horizon

- Each dot represents a retirement cohort's maximum SWR under FV=0 (x-axis) vs FV=100% (y-axis).
- The dots fall significantly below the 45-degree line.
- **Median distance: ≈ 1.25 percentage points.**
- To preserve capital over 30 years, you must cut your SWR by about 1.25pp.

### 8.2 60-Year Horizon

- The dots cluster much closer to the 45-degree line.
- **Median distance: ≈ 0.19 percentage points.**
- Lowering the SWR by less than 0.19pp makes the difference between running dry and capital preservation.

### 8.3 Reproducibility

The exact per-cohort SWR values underlying these scatter plots are **not published** in the article. The charts cannot be independently reproduced from the published numerical values alone.

---

## 9. Public FBF Mapping

### 9.1 Current YAML Schema Support

The `StudyConfiguration` dataclass already supports:

```python
final_value_target_values: tuple[Decimal, ...] | None = None
```

This becomes a Cartesian-product axis in the simulation grid. The YAML syntax is:

```yaml
final_value_target: [0.0, 0.25, 0.5, 0.75, 1.0]
```

### 9.2 Precedent

The existing `ern_part3_replication.yaml` already uses multiple FV targets:

```yaml
final_value_target: [0.0, 0.5]
```

### 9.3 Part 2 Study Configuration

The canonical configuration is `examples/studies/ern_part2.yaml`:

```yaml
metadata:
  name: "ERN Part 2 — Capital Preservation vs. Capital Depletion"
  version: "1.0"
  description: "ERN Part 2: 5 weights x 9 rates x 2 horizons x 5 FV targets x 1,739 cohorts"

cohorts:
  horizon_years: [30, 60]
  cohort_horizon_years: 60
  start_date: "1871-01"
  end_date: "2015-11"

allocation_policy:
  type: "ConstantAllocationPolicy"
  equity_allocation: [1.0, 0.75, 0.5, 0.25, 0.0]

withdrawal_policy:
  type: "FixedRealWithdrawalPolicy"
  withdrawal_rate: [0.03, 0.0325, 0.035, 0.0375, 0.04, 0.0425, 0.045, 0.0475, 0.05]

final_value_target: [0.0, 0.25, 0.5, 0.75, 1.0]
expense_ratio: 0.0005
```

**This uses only the current public FBF contract.** No Part-2-specific YAML fields, no new CLI flags, no new engine behavior are required for the final-value target dimension itself.

However, this does not close the temporal-configuration gap identified by the Part 1 audit (Part 1 §4.2–4.4). That gap is now addressed for **cohort selection** by optional inclusive bounds on the shared cohort universe:

```yaml
cohorts:
  horizon_years: [30, 60]
  start_date: 1871-01
  end_date: 2015-11
```

`cohorts.start_date` and `cohorts.end_date` accept `YYYY-MM` (canonical monthly form, expanded to the first day) or full `YYYY-MM-DD` dates. If one bound is omitted, the corresponding dataset boundary is used. If both are omitted, the pre-existing rolling-monthly universe is produced unchanged. The bounds affect cohort selection only: they do not change the simulation horizon, the base snapshot, or the dataset's historical/projection boundary. A separate data-cutoff configuration remains out of scope and must not be conflated with this cohort-date contract.

For the FBF production dataset, the default 1,739-cohort universe runs from the 1871-01-31 base snapshot through the 2015-11-01 cohort start. A Part 2 configuration can lock that window explicitly without changing any financial semantics.

### 9.4 Execution Command

```bash
sim-retire --data-dir data/ern run examples/studies/ern_part2.yaml \
  --no-persist --summary-only --workers max
```

---

## 10. Part 2.1 E2E Specification

### 10.1 Input Fixtures

| Fixture | Source | Purpose |
|---------|--------|---------|
| Production ERN dataset (`data/ern`) | Canonical current production data | Full 450-cell regression grid |
| Published-2016 fixture (`data/ern/published_2016`) | Frozen ERN article-vintage data | Four independent published anchors |
| Regression fixture (`data/ern/part2_regression_fixture.csv`) | Generated by `tools/ern/build_part2_regression_fixture.py` through the production path | Exact cell counts for the full grid; explicitly not a replication oracle |

### 10.2 Study Configuration

The YAML in Section 9.3. The key expansion from Part 1 is:

- `final_value_target: [0.0, 0.25, 0.5, 0.75, 1.0]` (5 targets instead of 1)
- `cohorts.horizon_years: [30, 60]` (2 horizons instead of 4)
- Explicit `cohorts.start_date: "1871-01"` / `cohorts.end_date: "2015-11"` bounds lock the intended 1,739-cohort window.

### 10.3 Execution

```bash
# Full grid + published anchors (requires RUN_ERN_E2E=1):
RUN_ERN_E2E=1 pytest tests/oracle/ern/test_ern_part2.py -v

# Deterministic warm-up timing validation (normal suite):
pytest tests/oracle/ern/test_part2_warmup.py -v

# Regenerate the regression fixture through the production path:
python tools/ern/build_part2_regression_fixture.py
```

### 10.4 Expected Outputs

The implemented Part 2.1 E2E validates:

1. **Full-grid regression** — all 450 cells (including the FV=0 cells) execute on the current production dataset and match the regression fixture's exact success counts.
2. **Published anchors** — the four article anchors (Section 6.1) execute on the frozen published-2016 dataset and are checked against the article's rounded values with the documented ±1 pp publication-rounding tolerance.
3. **Warm-up timing** — the deterministic 4% constant-return scenario reproduces the published `3.92%` through `5.66%` maximum withdrawal rates.

FV=0 comparison against the Part 1 oracle is **Part 2.2**, not Part 2.1. The FV=0 cells are present in the Part 2.1 regression fixture, but Part 2.1 does not assert the Part 1 cross-check.

### 10.5 Oracle Strategy

The E2E requires two distinct validation strategies, which must not be conflated:

**Independent replication validation:**

```
ERN methodology / published data
        ↓
independently derived inputs and/or oracle
        ↓
FBF simulation
```

This is the primary replication evidence. It establishes that FBF reproduces ERN's published results using inputs derived from the article's methodology.

**Regression validation:**

```
FBF-generated regression fixture
        ↓
FBF simulation
```

This establishes internal consistency: FBF produces results consistent with its own implementation. It is useful as a regression fixture but is **not** independent replication evidence.

**For Part 2, the article publishes only 4 explicit success-rate anchors** (Section 6.1, excluding the 65% Part 1 cross-reference). This is insufficient to construct a complete independent oracle for the 450-cell grid. The limitation must be documented rather than resolved by using a FBF-generated oracle as the primary validation source.

The implemented approach is:

1. **Hard-fail on the 4 published Part 2 anchors** — independent replication validation against the article's explicit numerical claims, using the frozen published-2016 dataset.
2. **FBF-generated regression fixture for the full grid** — explicitly labelled as a regression fixture, not a replication oracle. Named `part2_regression_fixture.csv` (not `part2_oracle.csv`). It establishes internal consistency across all 450 cells but does not independently prove that those values match ERN's methodology.
3. **FV=0 cross-check against Part 1 oracle** — deferred to Part 2.2. It is a consistency check for the 90 overlapping cells (see §10.6.1), not Part 2.1 replication evidence.

The FBF-generated table is a **regression fixture required for deterministic regression coverage**, not an ERN replication oracle. It does not increase our knowledge of whether FBF matches ERN — it only establishes that FBF's own implementation is self-consistent.

### 10.6 Assertions

| Assertion Type | Scope | Dataset | Tolerance | Tolerance Justification |
|---------------|-------|---------|-----------|------------------------|
| Hard-fail anchors | 4 cells from article text (Section 6.1) | Frozen published-2016 | ±1 pp | **Publication rounding tolerance** — ERN publishes success probabilities as whole percentages; the acceptance criterion compares against the published rounded value, not an exact numerical target. This is fundamentally different from a floating-point tolerance: it accounts for the source's own rounding, not numerical representation error. |
| Full grid | 450 cells (5W × 9R × 2H × 5FV) | Current production | Exact success counts against regression fixture | **Regression fixture comparison** — deterministic internal consistency check |
| FV=0 cross-check | 90 cells (5W × 9R × 2H, FV=0) | Current production | Part 2.2 scope | **Overlap/regression invariant with Part 1** — deferred from Part 2.1 |

#### 10.6.1 FV=0 Overlap: Regression Invariant with Part 1

The 90 FV=0 cells in the Part 2 grid represent the **overlap between the designated Part 2 subset and the Part 1 subset**:

```
Part 2 FV=0 cells: 5 equity weights × 9 rates × 2 horizons (30Y, 60Y) × 1 FV target (0%)
                 = 90 cells

Part 1 cells:     5 equity weights × 9 rates × 4 horizons (30Y, 40Y, 50Y, 60Y) × 1 FV target (0%)
                 = 180 cells
```

The 90 Part 2 FV=0 cells are a strict subset of the 180 Part 1 cells (same 5 weights × 9 rates, restricted to the 2 shared horizons).

This overlap is a **regression invariant**: changing the Part 2 final-value-target dimension must not alter FV=0 results. Part 2.1 includes the FV=0 cells in its regression fixture but does not compare them to the Part 1 oracle. That cross-check is Part 2.2.

This invariant is stronger and clearer than merely saying the cells "should match" — it explicitly defines the 90 cells as the overlap and establishes the regression purpose.

### 10.7 Independent Forward-Return Validation

Part 2 uses **identical** forward assumptions to Part 1. The published anchors use the explicit published-2016 forward fixture; the production regression grid uses the current production projection. Independent forward-return fixture validation remains the Part 1 methodology task described in Part 1 §5.3; Part 2 does not introduce a separate forward assumption.

---

## 11. E2E Scope Decision

### 11.1 Does Part 2 Require a New E2E?

**Yes.** The key question is: does Part 2 introduce a distinct externally observable behavior that deserves independent E2E coverage?

**Yes, it does.** The distinct behavior is:

> Terminal final-value preservation changes the success criterion while allowing intermediate target breaches.

This is a meaningful E2E concern even if the engine already has the capability. The new E2E is justified by:

1. **New behavioral coverage** — Part 2 exercises the terminal-only final-value check (`final_wealth >= target × initial_wealth`) over a broader target and horizon grid. This is a distinct externally observable behavior: the success criterion now includes a terminal wealth constraint that may be temporarily breached during retirement.
2. **New regression fixture coverage** — the existing oracle (`p49_oracle_table.csv`) contains only FV=0 values. A new regression fixture with FV>0 values is needed for the Part 2 grid.
3. **FV > 0 coverage** — the existing E2E explicitly skips cells where `fv > 0` (see `_assert_cell_matches` in `test_ern_swr_replication.py`). The Part 2 E2E fills this gap.
4. **Part 2-specific grid** — 2 horizons × 5 FV targets (vs Part 1's 4 horizons × 1 FV target).
5. **Published Part 2 anchors** — the article publishes 4 explicit success-rate values for FV>0 cells (Section 6.1).
6. **Part 2.2 follow-up** — the 90 FV=0 cells overlapping with Part 1 are included in the Part 2.1 regression grid, but their Part 1 cross-check remains Part 2.2 scope.

The new E2E is **not** justified by the need to implement new final-value engine behavior — that capability already exists and is verified by unit tests (Section 3). It is justified by the need to provide **behavioral coverage** of the terminal-only FV check across the Part 2 grid.

### 11.2 Recommended Approach

**Separate Part 2 E2E test file** (`tests/oracle/ern/test_ern_part2.py`), not an extension of the Part 1 E2E. The implemented Part 2.1 coverage is:

```
Part 1 E2E
    → FV=0 production-conformance scope

Part 2.1 E2E
    → Full 450-cell regression grid (current production)
    → FV=25/50/75/100 coverage (new behavioral dimension)
    → 4 published anchors (frozen published-2016 dataset)
    → Regression fixture (FBF-generated — not replication evidence)

Part 2.2 E2E (deferred)
    → FV=0 cross-check against the Part 1 oracle
```

The Part 1 E2E remains focused on the Part 1 reproduction subset. The Part 2.1 anchors are independent replication evidence; the full-grid fixture is regression evidence only.

### 11.3 FV=0 Cross-Validation: Regression Invariant with Part 1

The 90 FV=0 cells in the Part 2 grid overlap with the Part 1 grid (for the 5 representative equity weights and 2 shared horizons: 30Y and 60Y). Part 2.1 includes these cells in the regression fixture. Part 2.2 will verify that they produce identical results to the Part 1 oracle. This is a **regression invariant**: changing the Part 2 final-value-target dimension must not alter FV=0 results. It is a consistency check, not new replication evidence.

---

## 12. Known Gaps and Ambiguities

### 12.1 Article Grid Values in Images

The exact equity-weight and withdrawal-rate grid values are embedded in the article's table image (`swr-part2-table1.png`), not enumerated in the textual source. The article text only states: "The table below is an extension of the results from last week." The 21-weight × 9-rate grid is visually observed from the image and consistent with Part 1's structure, but is not independently established by the article text.

**Impact:** The Part 2.1 E2E validates the FBF reproduction subset (5 representative weights), not the complete 21-weight article grid.

### 12.2 Updated Table (2023)

The article includes an updated table (added 2023-07-26) with data through 2022/2023. The article states: "not much of a difference." The updated table is **not** the primary replication target — the original 2016 table is, consistent with the canonical dataset period (1871-01 through 2016-09).

### 12.3 Warm-Up Timing Resolved

The article's beginning-of-month withdrawal and FBF's previous-month-close cohort window are economically and temporally equivalent (Section 4.4). The production path reproduces all five published warm-up maximum withdrawal rates; `tests/oracle/ern/test_part2_warmup.py` pins the convention. This gap is closed.

### 12.4 Forward-Projection Assumptions

Part 2 uses identical forward-projection assumptions to Part 1. The independent forward-return fixture described in Part 1 §5.3 remains the source of methodology validation. Part 2 does not introduce any different forward assumptions.

### 12.5 40Y and 50Y Horizons Omitted

The article omits 40Y and 50Y horizons from the Part 2 table "to keep the table size manageable." The FBF YAML supports these horizons, but `examples/studies/ern_part2.yaml` uses only 30Y and 60Y to match the article's published scope.

### 12.6 Article's Qualitative Statements

The article makes several qualitative observations (0.50pp haircut, 70% equity threshold, bonds problematic for long horizons) that should not become hard numerical acceptance criteria. They are research conclusions, not simulation specifications.

---

## 13. Expected Result Classification

| Result | Classification | Notes |
|--------|---------------|-------|
| FV=0 success rates (5W × 9R × 2H) | Regression fixture cells in Part 2.1; Part 1 cross-check deferred to Part 2.2 | Included in the 450-cell production regression grid. Part 1 consistency is a Part 2.2 invariant (§10.6.1) |
| FV=100% success rates (4 cells) | Independent replication evidence — published ERN anchors | 98%, 96%, 97%, 80% from article text; validated on the frozen published-2016 dataset with ±1 pp tolerance |
| FV=25%, 50%, 75% success rates | Not published in text — in table image only | Cannot validate independently from text; covered by the FBF-generated regression fixture as internal consistency only |
| Warm-up SWRs (3.92%–5.66%) | Published analytical reference values | Reproduced by the production path and pinned by `test_part2_warmup.py`; timing resolved in §4.4 |
| Scatter-plot median differences (1.25pp, 0.19pp) | Rounded published values | Per-cohort data not available |
| 0.50pp haircut rule | Qualitative research conclusion | Not a hard numerical test |
| 70% equity threshold | Qualitative research conclusion | Not a hard numerical test |

**Validation hierarchy:**

1. **Independent replication evidence:** Published ERN numerical anchors (Section 6.1) and independently derived methodology/data.
2. **Part 1 oracle cross-check:** The existing pinned FBF replication oracle (`p49_oracle_table.csv`). Useful for consistency checking as a regression invariant (§10.6.1), but it is an FBF-generated regression fixture, not independent replication evidence.
3. **Part 2 regression evidence:** The FBF-generated regression fixture for FV>0 cells where ERN does not publish underlying numerical results. Must never be presented as independent evidence that FBF matches ERN.

---

## 14. Summary

ERN Part 2 extends Part 1 by adding a final-value target dimension to the success criterion. The key addition is the **terminal-only** check: `final_wealth >= target × initial_wealth`. The target is evaluation-only: fixed-real execution uses the workbook recurrence for every target, and the terminal threshold is applied to the completed trajectory (Section 3). The YAML configuration supports multiple FV targets as a Cartesian-product axis (Section 9). No Part-2-specific engine behavior, YAML fields, or CLI flags were required for the final-value target dimension itself.

Part 2.1 is implemented:

1. `examples/studies/ern_part2.yaml` defines the 450-cell, 782,550-unit reproduction subset with explicit cohort bounds.
2. `data/ern/part2_regression_fixture.csv` is generated through the production path by `tools/ern/build_part2_regression_fixture.py`.
3. `tests/oracle/ern/test_ern_part2.py` validates the full grid against the fixture and checks the four published anchors on the frozen published-2016 dataset.
4. `tests/oracle/ern/test_part2_warmup.py` resolves and pins the beginning-of-month warm-up timing.

The Part 1 FV=0 cross-check remains Part 2.2 scope. The scatter-plot statistics (Section 8) remain unusable as acceptance criteria because the per-cohort values are not published.
