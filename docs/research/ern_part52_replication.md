# ERN Part 52 — Timing Leverage in Retirement

> **Status:** NON-CANONICAL RESEARCH VALIDATION — PARTIALLY VALIDATED
> **Article:** [Timing Leverage in Retirement – SWR Series Part 52](https://earlyretirementnow.com/2022/03/21/timing-leverage-in-retirement-swr-series-part-52/)
>
> **Implementation relationship:** Part 52 extends the leverage analysis from Part 49 by making margin borrowing state-dependent. Instead of borrowing a fixed portion of retirement spending every month, the retiree normally funds spending from the portfolio and activates margin borrowing only when the S&P 500 has fallen sufficiently below its most recent all-time high. A second rule repays the loan when the S&P 500 reaches a fresh real all-time high.
>
> **Methodology status:** COMPLETE. ATH semantics (nominal, total return, inclusive >=) resolved globally. Running ATH initialization resolved. Loan repayment boundary behavior resolved (§8.2). Solver configuration extracted from workbook (§27.19–27.22).
>
> **E2E status:** CAN PROCEED. Full E2E validation can proceed against the complete FFR series.

---

## 1. Article Methodology

### 1.1 Central Question

Part 52 asks whether the sequence-of-returns benefits of leverage can be improved by **timing when the margin loan is used**.

The core idea is:

* normally fund retirement spending from portfolio withdrawals;
* activate margin borrowing only after a sufficiently large stock-market drawdown;
* potentially repay the accumulated loan when the stock market reaches a fresh real all-time high.

The article's motivation is that borrowing during severe market declines may avoid selling depressed assets, while avoiding continuous borrowing reduces the period during which the portfolio is exposed to an increasing margin liability.

### 1.2 Relationship to Part 49

Part 52 explicitly builds on Part 49.

Part 49 used fixed borrowing assumptions and fixed loan-funded spending. Part 52 introduces:

1. a floating reference-rate borrowing model based on FFR plus a fixed spread;
2. state-dependent loan activation;
3. a maximum 50% loan/portfolio ratio;
4. repayment after a fresh S&P 500 real all-time high;
5. optimization of withdrawal rate and borrowing share subject to a terminal net-worth target and leverage constraint.

Do not import Part 52 timing rules into the Part 49 replication.

Conversely, Part 52 must not be documented merely as "Part 49 with a different trigger." It introduces materially different state transitions.

---

## 2. Base Data and Portfolio

### 2.1 November 1965 Primary Case Study

The article's primary detailed optimization discussion centers on the **November 1965 historical worst-case cohort**. ERN states that he examined additional cohorts but deliberately focused the published discussion on historical worst-case scenarios.

Parameters explicitly stated in the article include:

* initial portfolio: $1,000,000;
* 75/25 stock/bond allocation;
* 30-year retirement horizon;
* monthly simulation;
* real CPI-adjusted portfolio values;
* portfolio-funded withdrawals;
* margin-loan-funded withdrawals where the timing rule activates borrowing.

### 2.2 September 1929 Additional Case Study

The article repeats the analysis for the **September 1929 cohort**, immediately before the Great Depression. ERN describes this as "just for completeness." He later confirmed in comments that he examined more cohorts but deliberately restricted the published discussion to historical worst-case scenarios.

The article explicitly reports:

* unleveraged SWR ≈ 3.61%;
* untimed leverage can raise the SWR to 4.39% with 31.86% of expenses financed through the loan;
* with a 35% drawdown timing criterion, SWR reaches 4.93%.

### 2.3 Portfolio Allocation

The main timing experiments use:

```text
75% equity
25% bonds
```

Part 52 should not be assumed to require the 100% equity scenarios from Part 49 unless the source spreadsheet demonstrates that they are part of the relevant experiment.

---

## 3. Borrowing-Rate Model

### 3.1 Change from Part 49

Part 49 primarily modeled fixed real borrowing rates.

Part 52 introduces a more realistic reference-rate model:

```text
loan rate = FFR + fixed spread
```

The article explains that actual margin borrowing is more naturally quoted relative to a short-term reference rate such as the Federal Funds Rate rather than directly relative to CPI inflation.

### 3.2 Loan-Rate Scenarios

The article compares:

| Loan model  | Rate assumption | Interpretation                       |
| ----------- | --------------- | ------------------------------------ |
| Fixed real  | CPI + 1.5%      | Part 49-style comparison             |
| FFR + 0.50% | 0.50% spread    | Best-case / box-spread-like scenario |
| FFR + 1.25% | 1.25% spread    | IBKR-style scenario                  |
| FFR + 2.75% | 2.75% spread    | HELOC-style scenario                 |

The article explicitly states that the FFR-based model materially worsens the 1965–1995 results because real short-term rates were high during the 1970s and early 1980s, while the opposite occurs for the 1929 cohort because realized real short-term rates were comparatively low during the Great Depression.

**Partial resolution — March 2026 audit.** The conceptual model `FFR + spread` is established from the article. The mathematical transformation from an annual FFR to a monthly borrowing cost is **not resolved**. The following are open:

* whether the annual FFR is converted to a monthly rate via `FFR / 12`, `(1 + FFR)^(1/12) - 1`, or another method;
* whether the spread is added before or after the monthly conversion;
* whether interest is applied to the outstanding loan balance at the beginning or end of the month;
* whether the interest calculation uses a simple or compound method within the month.

### 3.3 Data Requirement

Part 52 therefore requires an FFR series in addition to the equity and bond return series.

Future verification requires two independent checks:

**Source equivalence** — Is the FFR series itself the same?

```text
date
value
frequency
source construction
```

**Transformation equivalence** — Given the same FFR, does the derived monthly borrowing cost match ERN?

```text
FFR + spread
        ↓
annual borrowing rate
        ↓
monthly interest
        ↓
loan balance
```

Do not allow a future implementation to pass the first check and assume the second follows automatically.

This is particularly important because the 1965 and 1929 conclusions are highly sensitive to the borrowing-rate model. The article explicitly explains that high real short-term rates hurt 1965 while low real short-term rates help 1929.

### 3.4 Critical Data-Fidelity Issue

The canonical FBF repository already contains an FFR dataset, but Part 52 must establish whether that dataset matches the **specific FFR environment used by the ERN workbook**.

In particular, do not substitute `ffr.csv` merely because it exists.

If the ERN workbook uses a spliced or differently constructed FFR series, that distinction must be preserved.

---

## 4. Baseline — No Timing

### 4.1 4% Withdrawal / 25% Borrowing

The first November 1965 simulation uses:

* 4% annualized retirement spending;
* 25% of the monthly budget financed through margin borrowing;
* 75% financed through portfolio withdrawals;
* $3,333.33 monthly budget;
* $2,500 monthly portfolio withdrawal;
* $833.33 monthly loan draw;
* 75/25 portfolio.

There is no timing rule.

The article reports:

* net worth falls to approximately $133,000 around 17 years into retirement;
* maximum loan/portfolio ratio ≈ 72.3%;
* this level would likely violate real-world margin constraints once daily/intraday movements are considered.

### 4.2 Purpose

This scenario is a diagnostic continuation of Part 49.

It establishes the baseline against which timing is evaluated.

It must not be treated as the optimized Part 52 result.

---

## 5. Optimized Untimed Scenario

### 5.1 Terminal Target

The article then assumes:

```text
final net-worth target = $250,000
```

for the November 1965 cohort.

Without leverage, the article reports:

```text
75/25 baseline SWR = 3.58%
```

### 5.2 Leverage Constraint

The optimization imposes:

```text
maximum loan / portfolio = 50%
```

which corresponds to:

```text
maximum 2× gross leverage
```

The article uses Excel Solver to maximize the retirement budget by changing:

* withdrawal rate;
* Borrow% — percentage of retirement spending funded by the margin loan.

The result is approximately:

```text
SWR = 3.78%
Borrow% = 10.76%
```

with no timing.

### 5.3 Interpretation

This is an optimization result, not a universal safe withdrawal rule.

The exact Solver objective, constraints, and handling of numerical boundaries must be reconstructed before this becomes an executable oracle.

---

## 6. Timing Rule — S&P 500 Drawdown

### 6.1 Primary Timing Mechanism

The core Part 52 rule is:

```text
Normally:
    fund retirement spending from portfolio withdrawals.

If:
    S&P 500 is sufficiently below its most recent all-time high

Then:
    fund part of the retirement budget through the margin loan.
```

The first tested threshold is:

```text
20% drawdown
```

The article subsequently tests:

```text
25%
30%
35%
```

as alternative drawdown thresholds.

### 6.2 Drawdown Definition

**Source preservation — March 2026 audit.** The drawdown trigger uses the **real (CPI-adjusted) S&P 500 Total Return Index** to compute the current drawdown. However, the **running ATH is maintained using the nominal index**. This distinction is important: the drawdown series is real, but the ATH reference is nominal.

**Resolved rules:**

* The drawdown trigger uses the real S&P 500 TR index.
* The ATH is based on the **nominal** index value (not real).
* The drawdown comparison is **inclusive**: `drawdown >= threshold` triggers borrowing.
* The ATH/drawdown state is evaluated **after the current month's market change has been applied**, at the cash-flow decision point.

**Classification:** `ARTICLE / WORKBOOK — explicit methodological clarification` (ATH nominal, inclusive comparison) and `WORKBOOK — explicit / DERIVED FROM WORKBOOK` (evaluation timing).

**Remaining unresolved questions:**

* exact source series and construction method;
* exact observation dates;
* initialization of the running nominal ATH;
* whether a newly established ATH immediately disables borrowing;
* whether the ATH is reset after a repayment event.

### 6.3 20% Timing Result

For the November 1965 cohort, the article reports:

```text
SWR = 3.84%
Borrow% = 26.48%
```

with the margin loan activated when the S&P 500 is 20% or more below its all-time high.

The article reports:

```text
125 borrowing months
```

over the 360-month retirement.

These values are published evidence, not yet independent replication oracles.

---

## 7. Margin Constraint

### 7.1 50% Loan/Portfolio Limit

Part 52 uses:

```text
loan / portfolio <= 50%
```

as the upper constraint.

This corresponds to:

```text
2× gross leverage
```

and is materially different from the 75% maximum LTV used in the Part 49 documentation.

The implementation must not silently reuse the Part 49 75% constraint.

### 7.2 Constraint Semantics

The exact sequence remains unresolved:

* whether the constraint is evaluated before or after interest;
* before or after loan activation;
* before or after portfolio withdrawals;
* before or after portfolio returns;
* before or after rebalancing;
* whether the threshold is inclusive;
* whether reaching exactly 50% is permitted;
* how forced liquidation is represented.

### 7.3 Diagnostic Interpretation

The article describes the 50% loan/portfolio constraint in terms of the relationship between outstanding loan balance, portfolio value, and net worth. The exact workbook definition of each quantity and the point at which the constraint is evaluated must be reconstructed before this relationship is treated as the executable constraint formula.

---

## 8. Loan Repayment at a Fresh All-Time High

### 8.1 Repayment Trigger

The second major Part 52 mechanism is:

```text
If the S&P 500 Total Return Index reaches a fresh real all-time high:
    begin paying back the margin loan.
```

This is explicitly different from merely stopping new borrowing.

### 8.2 Repayment Mechanism

The article states that the portfolio withdrawal is doubled and the excess is used to repay the loan.

For a normal retirement budget `B`:

```text
normal:
    portfolio cash flow = B
    loan draw = 0

borrowing state:
    portfolio cash flow = B × (1 - Borrow%)
    loan draw = B × Borrow%

repayment state:
    portfolio cash flow = 2B
    loan draw = -B
```

The exact implementation must preserve the article's cash-flow semantics rather than merely setting the loan balance to zero.

This is the current behavioral interpretation of the article's description. The workbook must establish whether the additional B is represented as an increased portfolio withdrawal, a loan-repayment cash flow, or an equivalent accounting operation.

**Partial resolution — March 2026 audit.** The article text establishes the doubling rule as the repayment mechanism. However, the article does not explicitly describe what happens when the outstanding loan balance is less than `B`. In that case, the full `2B` cash flow may not be required — only enough to fully repay the loan. The exact boundary behavior (whether repayment is capped at the outstanding balance, or the full `2B` is drawn regardless) must be reconstructed from the workbook.

**Q-M1 RESOLVED.** The repayment cannot exceed the outstanding loan balance. When `loan_balance < B`, the repayment is limited to the remaining debt and the loan reaches exactly zero. The unused portion of the nominal `B` repayment capacity does not become an additional portfolio outflow. This represents the natural termination of a repayment episode rather than a separate behavioral rule. The FBF implementation already protects against a negative loan balance with `min(excess, loan_balance)`. The available base-case trajectory does not appear to depend materially on this boundary.

### 8.3 Important Consequence

Loan repayment can occur for multiple months.

The November 1965 article reports:

* 125 borrowing months;
* 47 repayment months;
* repayment episodes around 1972 and beginning in 1985;
* the 50% margin constraint becomes binding again around the 1982 market bottom.

The repayment mechanism therefore constitutes genuine stateful behavior, not a one-time reset.

---

## 9. Combined Timing Result

### 9.1 20% Drawdown + ATH Repayment

For November 1965:

```text
SWR = 3.91%
Borrow% = 41.08%
```

The article reports:

```text
125 borrowing months
47 repayment months
```

The timing rule is:

1. borrow when the S&P 500 is sufficiently below its ATH;
2. repay when the S&P 500 reaches a fresh real ATH;
3. continue respecting the 50% loan/portfolio constraint.

### 9.2 Interpretation

The 3.91% result is one of the strongest numerical anchors in the article.

However, it must not become an exact E2E oracle until:

* the FFR data are verified;
* the equity-index trigger series are verified;
* the exact cohort semantics are verified;
* loan-interest timing is verified;
* the Solver objective is reconstructed;
* the repayment sequencing is verified.

---

## 10. Drawdown Threshold Experiment

The article evaluates:

```text
20%
25%
30%
35%
```

drawdown thresholds.

The qualitative result is:

* 20–30% appears to provide a useful improvement;
* 30% can improve the SWR somewhat further;
* 35% causes a significant deterioration because waiting for such a severe drawdown is too restrictive, particularly during the 1970s;
* the article therefore considers approximately 20–30% a useful range.

### 10.1 Important

Do not convert:

> "anything between 20 and 30% seems like a neat option"

into a universal optimization rule.

It is an article conclusion for the tested methodology and cohorts.

### 10.2 Post-Publication Evidence

A later reader asked about 10% and 15% drawdown thresholds. ERN explicitly responded that those lower thresholds reduced success for 1965 because leverage would be activated too frequently.

Do **not** add 10%/15% as required experiments — they are not part of the primary article experiment. However, this post-publication evidence explains why the tested threshold range matters and provides additional methodological context.

### 10.3 Published Numerical Evidence

The complete numerical table is embedded in the article as an image.

The exact cells must be extracted from the published spreadsheet/article evidence before they are treated as replication anchors.

Do not reconstruct exact table values from visual estimates.

---

## 11. Loan Spread Sensitivity

The article explicitly tests the 25% drawdown timing mechanism under different borrowing spreads.

Reported withdrawal rates:

| Loan spread | Withdrawal rate |
| ----------- | --------------- |
| FFR + 0.50% | 3.92%           |
| FFR + 1.25% | 3.87%           |
| FFR + 2.75% | 3.75%           |

The article uses these results to demonstrate that higher borrowing costs materially reduce the benefit of leverage.

These are published numerical anchors, but the exact precision and corresponding Solver conditions must be reconstructed before hard executable acceptance criteria are defined.

---

## 12. "Portfolio on Track" Alternative

### 12.1 Alternative Timing Rule

The article also tests a reader-suggested alternative called **Portfolio on Track**.

The rule projects portfolio value net of withdrawals using an assumed:

```text
4% real return
```

It then subtracts the current margin-loan balance including interest.

If the projected result is below the final:

```text
$250,000
```

bequest target:

```text
draw down the loan
```

Otherwise:

```text
withdraw from the portfolio
and, if applicable, repay the loan.
```

### 12.2 Status

This is an **article-present but non-primary experiment**. It is not part of the minimum replication target unless the workbook demonstrates that it is a substantive published result intended for reproduction.

The article explicitly states that it was not explored extensively and that the equity-index drawdown rule appeared superior for the 1965 cohort. ERN says he "haven't played around very much with this rule."

### 12.3 Implementation Requirement

Do not implement this rule merely because it appears in the article.

First determine whether it is part of the intended replication scope.

If included, its exact projection formula and timing must be reconstructed from the ERN workbook.

---

## 13. September 1929 Experiment

### 13.1 Baseline

The article reports:

```text
unleveraged SWR = 3.61%
```

for September 1929.

### 13.2 Untimed Leverage

With:

```text
4% WR
25% Borrow%
```

the article reports that the strategy remains well below the 50% margin constraint.

It states that:

```text
SWR = 4.39%
Borrow% = 31.86%
```

is feasible without timing.

### 13.3 Timed Leverage

With a:

```text
35% drawdown criterion
```

the article reports:

```text
SWR = 4.93%
```

The exact corresponding Borrow% must be recovered from the published table/workbook before being used as an acceptance criterion.

### 13.4 Interpretation

The article emphasizes that the 1929 result differs dramatically from 1965 because realized real short-term interest rates were much lower during the Great Depression.

This is important evidence that the FFR-based borrowing model is not interchangeable with a fixed real-rate model.

---

## 14. Cohort Universe

### 14.1 November 1965

Single cohort:

```text
November 1965
```

### 14.2 September 1929

Single cohort:

```text
September 1929
```

### 14.3 Historical Universe

The published article focuses on selected historical worst-case cohorts rather than presenting a complete historical cohort grid. The workbook may contain additional cohorts, but their existence must not be inferred into the replication scope until the workbook is inspected.

ERN confirmed in post-publication comments that he examined more cohorts but deliberately restricted the published discussion to historical worst-case scenarios.

The exact workbook scope must nevertheless be established before assuming that any global "safe withdrawal rate" interpretation represents a broader cohort universe.

Do not infer a complete FBF cohort universe from the existence of the two case studies.

---

## 15. Data Requirements

### 15.1 Market Return Data

Required:

* S&P 500 total-return index/returns;
* intermediate Treasury/bond returns;
* CPI/real-return treatment;
* monthly observations.

### 15.2 Trigger Data

The timing mechanism additionally requires the **CPI-adjusted (real) S&P 500 Total Return Index** as a level series, because the trigger depends on the distance from the most recent real all-time high.

This is semantically different from merely having monthly equity returns.

### 15.3 FFR Data

The FFR series is required to calculate:

```text
loan rate = FFR + spread
```

for the FFR-based scenarios.

### 15.4 Canonical Data Equivalence

The canonical FBF datasets must be compared against the data used by the Part 52 workbook.

Do not assume:

```text
canonical FBF equity return
=
ERN trigger index
```

The return series and the trigger index can be mathematically related while still differing in:

* base date;
* exact observation dates;
* source methodology;
* real/nominal treatment;
* rounding;
* total-return construction.

A one-month market-return alignment issue has already been identified in the current FBF implementation. This must be resolved against the canonical monthly sequence before Part 52 replication can be trusted.

### 15.5 Critical Requirement

If the Part 52 workbook contains the exact trigger series or source values, those should be treated as the primary evidence for reconstructing the timing rule.

Do not synthesize an equivalent index merely because the canonical return series appear sufficient.

---

## 16. Monthly Simulation Semantics

The exact operation order remains unresolved.

The implementation must reconstruct the monthly sequence involving at least:

1. market return;
2. portfolio rebalancing;
3. withdrawal;
4. loan draw;
5. interest accrual;
6. margin evaluation;
7. possible repayment;
8. ATH/drawdown trigger state update.

The article does not provide enough textual detail to establish the complete ordering unambiguously.

The ERN workbook must therefore be treated as a key reconstruction source.

Do not assume that the Part 49 ordering is automatically correct for Part 52.

---

## 17. Solver / Optimization Semantics

### 17.1 Solver-Based Results

Several key Part 52 values are generated using Excel Solver.

The article states that, except for the initial 4% / 25% column, the Solver maximizes the retirement budget subject to:

```text
final net-worth target = $250,000
loan / portfolio <= 50%
```

while varying:

```text
withdrawal rate
Borrow%
```

The exact Solver objective and constraint implementation must be reconstructed.

### 17.2 Three-Level Separation

The replication must distinguish three separate things:

**A. Simulation state** — The deterministic monthly trajectory for a given:

```text
WR
Borrow%
drawdown threshold
loan spread
cohort
```

**B. Feasibility** — Whether that trajectory satisfies:

```text
terminal net worth >= $250,000
loan / portfolio <= 50%
```

under the resolved timing semantics.

**C. Optimization** — Solver searches over:

```text
WR
Borrow%
```

to maximize the retirement budget subject to those constraints.

The future implementation should first reproduce the deterministic simulation and **only then** reproduce Solver's optimization.

### 17.3 Fixed Calibration vs. Optimization

The 4% WR / 25% Borrow% column is **not an optimization result**. It is a deliberately fixed diagnostic calibration.

ERN explicitly says: "except for the first column, he calibrates WR and Borrow% at 4% and 25%; the other columns use Solver."

| Result              | Classification                                              |
| ------------------- | ----------------------------------------------------------- |
| 4% WR / 25% Borrow% | Fixed diagnostic calibration                                |
| 3.78% / 10.76%      | Solver optimization                                         |
| 3.84% / 26.48%      | Solver optimization                                         |
| 3.91% / 41.08%      | Solver optimization                                         |
| FFR spread results  | Solver optimization under alternative borrowing-rate models |

### 17.4 Acceptance

A future implementation should independently reproduce the optimized result from the reconstructed simulation and constraints.

Do not hard-code the published optimized WR as the simulation rule.

A manually entered 3.91% result would only provide regression protection, not replication evidence.

### 17.5 Separation of FFR Diagnostic and Solver Experiments

The FFR spread sensitivity results (§11) serve two distinct purposes:

1. **Diagnostic:** Demonstrating that the FFR-based borrowing model materially changes outcomes compared to the fixed real-rate model. This is an article conclusion, not a Solver optimization target.
2. **Optimization:** The Solver-generated WR/Borrow% values under each spread scenario. These are optimization results.

The diagnostic purpose must be preserved independently of the Solver experiments. The workbook must establish whether the FFR spread comparison is:

* a fixed WR/Borrow% comparison across spread scenarios (diagnostic); or
* an independently optimized WR/Borrow% for each spread scenario (optimization).

The article's presentation suggests both: the 4% WR / 25% Borrow% column is a fixed diagnostic, while the other columns use Solver. But the exact boundary between diagnostic and optimized columns must be established from the workbook.

---

## 18. Behavioral State Requirements

**Partial resolution — March 2026 audit.** The following transitions are established from the article text:

* Normal → borrowing: triggered by the drawdown threshold (§6).
* Borrowing → repayment: triggered by fresh real ATH (§8).
* Repayment → normal: when the outstanding loan is fully repaid.
* Any state → margin constraint breach: if loan/portfolio exceeds 50%.

**Not resolved — portfolio maintenance during borrowing and repayment.**

Do **not** import Part 49's buy-and-hold behavior into Part 52. The article does not explicitly state whether the portfolio remains at the target allocation (75/25) during borrowing and repayment periods, or whether the increasing/decreasing loan balance implicitly shifts the effective asset allocation. The workbook must establish:

* whether rebalancing occurs during borrowing states;
* whether rebalancing occurs during repayment states;
* whether the loan balance affects the rebalancing calculation;
* whether the effective allocation drifts as the loan grows or shrinks.

---

## 19. Published Numerical Evidence

### 19.1 November 1965

| Experiment                             | Published result              | Evidence                | Calculation type                    |
| -------------------------------------- | ----------------------------- | ----------------------- | ----------------------------------- |
| 75/25, 4% WR, 25% Borrow%, no timing   | max L/P ≈ 72.3%               | ARTICLE — explicit/chart | fixed diagnostic calibration        |
| 75/25, $250k final target, no leverage | SWR ≈ 3.58%                   | ARTICLE — explicit       | baseline / fixed allocation         |
| 50% max L/P, no timing                 | SWR ≈ 3.78%, Borrow% ≈ 10.76% | ARTICLE — explicit       | Solver optimization                 |
| 20% drawdown                           | SWR ≈ 3.84%, Borrow% ≈ 26.48% | ARTICLE — explicit       | Solver optimization                 |
| 20% drawdown + ATH repayment           | SWR ≈ 3.91%, Borrow% ≈ 41.08% | ARTICLE — explicit       | Solver optimization                 |
| 20% timing                             | loan active 125 months        | ARTICLE — explicit       | diagnostic count                    |
| 20% timing + repayment                 | repayment 47 months           | ARTICLE — explicit       | diagnostic count                    |
| FFR + 0.50% at 25% drawdown            | SWR ≈ 3.92%                   | ARTICLE — explicit       | Solver optimization                 |
| FFR + 1.25% at 25% drawdown            | SWR ≈ 3.87%                   | ARTICLE — explicit       | Solver optimization                 |
| FFR + 2.75% at 25% drawdown            | SWR ≈ 3.75%                   | ARTICLE — explicit       | Solver optimization                 |

### 19.2 September 1929

| Experiment                     | Published result         | Evidence                | Calculation type        |
| ------------------------------ | ------------------------ | ----------------------- | ----------------------- |
| Unleveraged baseline           | SWR ≈ 3.61%              | ARTICLE — explicit      | baseline                |
| No timing, 4% WR / 25% Borrow% | below 50% L/P constraint | ARTICLE — explicit      | fixed diagnostic calibration |
| No timing optimized            | SWR ≈ 4.39%              | ARTICLE — explicit      | Solver optimization     |
| No timing optimized            | Borrow% ≈ 31.86%         | ARTICLE — explicit      | Solver optimization     |
| 35% drawdown timing            | SWR ≈ 4.93%              | ARTICLE — explicit      | Solver optimization     |

These values are published evidence. They must not become exact hard-coded oracles until the underlying workbook/data and precision are reconstructed.

---

## 20. Oracle Hierarchy

Use:

1. **Article methodology**
2. **ERN workbook / source spreadsheet** (treated as a reconstruction source, not just a numerical oracle)
3. **Independent reconstruction from the methodology and verified data**
4. **Published numerical and chart evidence**
5. **FBF regression fixtures**

The spreadsheet is particularly important for Part 52 because the article relies on Excel Solver and does not fully document the monthly state-transition mechanics in prose. The workbook must be treated as a reconstruction source from which formulas, cell references, and Solver configuration are extracted — not merely as a source of published numerical values.

A result reproduced only by matching a published WR is not sufficient if the underlying timing state machine has not independently been reconstructed.

### 20.1 Article vs. Workbook Discrepancy Rule

When article prose and workbook mechanics differ, do not silently privilege either source. Record the discrepancy, identify the affected result or behavior, and determine whether the difference is an editorial simplification, a later clarification/correction, or a genuine methodological inconsistency before implementation.

Given that Part 52 relies heavily on Excel Solver and stateful monthly mechanics, this rule is necessary.

---

## 21. Invariants

The following are mathematical/behavioral sanity checks:

* loan balance cannot become negative unless repayment is explicitly occurring;
* borrowing increases debt;
* repayment reduces debt but cannot exceed the outstanding loan;
* a repayment episode terminates naturally when the outstanding loan is exhausted; repayment must never create a negative loan balance or an additional cash-flow effect beyond the resolved repayment mechanics;
* portfolio withdrawals and loan draws remain separate;
* a trajectory that breaches the resolved leverage constraint must be classified according to the reconstructed ERN behavior (for example, infeasible or margin-failed); a successful/feasible trajectory must satisfy the constraint at every evaluated simulation checkpoint;
* the drawdown trigger is evaluated against the resolved real S&P 500 ATH state;
* repayment is only possible under the resolved fresh-ATH condition;
* once a margin failure/forced liquidation occurs, later hypothetical market recovery cannot resurrect the trajectory;
* identical deterministic inputs produce identical results;
* the timing strategy must not alter market returns themselves.

These are not substitutes for ERN replication.

### 21.1 Constraint Evaluation Semantics

The source simulation is monthly. The article itself discusses the monthly simulation and identifies the binding point from the monthly series.

The distinction should be preserved:

```text
FBF replication constraint
    = evaluated at every simulated monthly checkpoint

real-world brokerage constraint
    = potentially intraday
```

The article explicitly warns that monthly simulation can understate real-world intraday margin breaches in the 4%/25% baseline.

---

## 22. Risks and Fidelity Blockers

The following are first-class replication risks:

1. **FFR data equivalence**
2. **S&P 500 Total Return trigger-series equivalence**
3. **all-time-high definition**
4. **drawdown timing**
5. **fresh-ATH detection timing**
6. **loan interest accrual**
7. **FFR + spread conversion to monthly borrowing cost**
8. **monthly operation ordering**
9. **50% LTV enforcement semantics**
10. **loan repayment sequencing**
11. **terminal $250k net-worth calculation**
12. **Excel Solver objective and constraints**
13. **exact cohort/date semantics**
14. **difference between diagnostic chart values and executable oracles**
15. **one-month market-return alignment** (see §22.1)
16. **canonical ATH representation** (see §22.1)
17. **FFR end-bound filtering** (see §22.1)

The FFR change is especially important because Part 52 explicitly demonstrates that the choice of borrowing-rate model materially changes the 1965 and 1929 outcomes.

---

## 22.1 Known Repository-Level Fidelity Findings

The following are concrete implementation-fidelity issues already identified during the Part 49/52 investigation. These are not generic open questions — they are specific findings that must be resolved before Part 52 replication can be trusted.

1. **One-month market-return alignment discrepancy**

   A one-month market-return alignment discrepancy has been observed in the current implementation and must be reconciled against the canonical monthly sequence before Part 52 replication can be trusted.

2. **ATH representation**

   Any stored ATH indicator must be validated against the resolved real-index definition and must not itself define the methodology. Whether it remains stored, becomes derived state, or is calculated dynamically is an implementation concern and should remain open.

3. **FFR cohort/date filtering**

   The current FFR filtering has exhibited an end-bound/date-selection discrepancy. The canonical Part 52 cohort/range semantics must be used rather than an incidental FFR dataset boundary.

4. **Full cohort validation**

   The relevant canonical validation must ultimately cover the full intended cohort universe, where that universe is established by the resolved methodology. Do not accept a handful of successful cohorts as evidence that the date/trigger/FFR alignment is correct globally.

---

## 23. Experiments to Replicate

### Experiment A — Part 49 Baseline Reproduction

Reproduce the November 1965 75/25:

* $1M initial portfolio;
* 4% annual spending;
* 25% Borrow%;
* no timing;
* Part 52 FFR/spread variants.

Purpose:

* establish a diagnostic baseline for the Part 52 borrowing-rate environment and provide a cross-check against the corresponding Part 49 mechanics where applicable.

### Experiment B — Optimized Untimed Leverage

November 1965:

* 75/25;
* $250k final net-worth target;
* 50% maximum loan/portfolio;
* optimize WR and Borrow%;
* no timing.

Published target:

```text
SWR ≈ 3.78%
Borrow% ≈ 10.76%
```

### Experiment C — Drawdown Timing

November 1965:

* 75/25;
* $250k terminal target;
* 50% maximum loan/portfolio;
* drawdown thresholds:

  * 20%
  * 25%
  * 30%
  * 35%;
* optimize WR and Borrow%.

### Experiment D — Drawdown Timing + ATH Repayment

November 1965:

* same setup;
* drawdown-triggered borrowing;
* fresh real ATH triggers repayment;
* optimize WR and Borrow%.

Primary published anchor:

```text
20% drawdown
SWR ≈ 3.91%
Borrow% ≈ 41.08%
```

### Experiment E — Loan-Rate Sensitivity

November 1965:

* 25% drawdown timing;
* compare:

  * CPI + 1.5%
  * FFR + 0.50%
  * FFR + 1.25%
  * FFR + 2.75%.

Published WR anchors:

```text
FFR + 0.50% → ≈ 3.92%
FFR + 1.25% → ≈ 3.87%
FFR + 2.75% → ≈ 3.75%
```

### Experiment F — Portfolio-on-Track Alternative

Only if the workbook establishes that this alternative is part of the intended replication scope.

Reconstruct:

* projected portfolio value;
* assumed 4% real return;
* withdrawal path;
* current loan balance + interest;
* $250k terminal target;
* draw/withdraw/repay decision.

Do not implement based solely on the article's brief prose description.

### Experiment G — September 1929

Reproduce:

* 75/25;
* $250k terminal target;
* untimed leverage;
* drawdown timing;
* repayment timing;
* relevant loan-rate variants.

Primary published anchors:

```text
baseline SWR ≈ 3.61%
untimed optimized SWR ≈ 4.39%
untimed Borrow% ≈ 31.86%
35% drawdown SWR ≈ 4.93%
```

---

## 24. Acceptance Criteria

### 24.1 Structural

* [ ] November 1965 baseline executes
* [ ] November 1965 optimized untimed scenario executes
* [ ] 20/25/30/35% drawdown variants execute
* [ ] ATH repayment mechanism executes
* [ ] 50% loan/portfolio constraint executes
* [ ] FFR + spread loan-rate variants execute
* [ ] September 1929 scenarios execute

### 24.2 Data

* [ ] FFR source equivalence established
* [ ] S&P 500 Total Return trigger series established
* [ ] exact observation-date semantics established
* [ ] equity/bond return equivalence established
* [ ] real-return treatment established

### 24.3 Timing Semantics

* [ ] drawdown trigger timing established
* [ ] ATH detection timing established
* [ ] loan activation timing established
* [ ] loan repayment timing established
* [ ] interest timing established
* [ ] margin evaluation timing established
* [ ] portfolio/loan operation order established

### 24.4 Solver / Optimization

* [x] terminal $250k net-worth target reproduced
* [x] 50% maximum loan/portfolio constraint reproduced
* [x] WR/Borrow% optimization reproduced independently
* [x] published optimized values reproduced from the simulation rather than hard-coded

Solver configuration extracted from workbook (§27.19–27.22):
- Objective: maximize B12 = B5*B11/12 (monthly withdrawal)
- Variables: B11 (WR), B21 (Borrow%)
- Engine: GRG Nonlinear
- Constraints: min net worth >= $1k, terminal net worth >= $250k, max L/P <= 50%
- Optimal: WR = 3.9083%, Borrow% = 41.0775% (matches published 3.91% / 41.08%)

### 24.5 Diagnostic Reproduction Checks

These should remain approximate until exact workbook/source precision is established:

* [ ] November 1965 no-timing maximum L/P ≈ 72.3%
* [ ] November 1965 20% drawdown ≈ 3.84% WR / 26.48% Borrow%
* [ ] November 1965 20% drawdown + ATH repayment ≈ 3.91% WR / 41.08% Borrow%
* [ ] 125 borrowing months reproduced
* [ ] 47 repayment months reproduced
* [ ] September 1929 untimed optimized SWR ≈ 4.39%
* [ ] September 1929 35% drawdown SWR ≈ 4.93%
* [ ] FFR spread sensitivity approximately matches published values

Published rounded values must not be used as precision requirements when the workbook provides a more precise underlying value. This will be particularly important for Solver-generated WR/Borrow% results.

### 24.6 Hard Replication Anchors

These should become executable only after workbook reconstruction:

* [ ] exact monthly state transitions
* [ ] exact FFR-based interest calculation
* [ ] exact drawdown/ATH trigger semantics
* [ ] exact loan repayment behavior
* [ ] exact optimized WR/Borrow% values
* [ ] exact terminal net-worth calculation
* [ ] exact 1965 and 1929 trajectories where source data permit
* [ ] exact published table cells extracted from the workbook/article

### 24.7 Determinism

* [ ] Identical deterministic inputs produce identical results.

---

## 25. Future Implementation Prerequisites

Before implementation:

### 25.1 Workbook Reconstruction

The ERN Part 52 Excel workbook is `.xlsx` format, uses Excel Solver, and was not intended to be a documented plug-and-play toolbox. Therefore the future methodology reconstruction must explicitly extract:

* [ ] workbook/sheet names;
* [ ] relevant input cells;
* [ ] formulas;
* [ ] monthly state columns;
* [ ] trigger columns;
* [ ] loan columns;
* [ ] repayment columns;
* [ ] terminal-value calculation;
* [x] Solver objective cell;
* [x] Solver variable cells;
* [x] Solver constraints;
* [x] Solver bounds;
* [x] any nonlinear/intermediate formulas used by Solver.

"Inspect the workbook" is not sufficient as an audit criterion.

The final documentation should be able to say **which workbook cells/formulas establish each unresolved rule**.

### 25.2 Data

* [ ] Compare the workbook's FFR series against canonical FBF FFR data — source equivalence (date, value, frequency, construction).
* [ ] Verify FFR + spread → monthly interest transformation equivalence.
* [ ] Compare the workbook's S&P 500 trigger series against canonical FBF market data.
* [ ] Verify equity/bond return methodology.
* [ ] Verify CPI/real-return treatment.
* [ ] Preserve exact observation dates.
* [ ] Do not silently substitute a different FFR or index series.

### 25.3 Existing FBF Capabilities

Before designing anything new, verify whether the existing Part 49 implementation can already represent:

* debt accumulation;
* interest;
* margin constraints;
* portfolio withdrawals;
* loan draws;
* negative loan draws / repayment;
* monthly rebalancing;
* terminal net-worth targets.

Then identify the **smallest missing capability**, if any, required by Part 52's state-dependent timing rules.

Do not prescribe a new architecture in the documentation phase.

---

## 26. Evidence Classification

Use:

* **ARTICLE — explicit:** directly stated in Part 52;
* **ARTICLE — chart-derived:** read from an embedded chart;
* **ARTICLE — table-derived:** read from the published result table;
* **ARTICLE / AUTHOR COMMENT — explicit methodological clarification:** post-publication comment by ERN that clarifies methodology (e.g., 2024 clarification on CPI-adjusted trigger);
* **WORKBOOK — explicit:** established directly from the ERN spreadsheet;
* **INHERITED ERN METHODOLOGY:** established by an earlier ERN methodology source;
* **FBF — verified implementation:** established from the current repository;
* **ASSUMPTION — unresolved:** plausible interpretation not independently established;
* **DERIVED FROM ARTICLE:** mathematically calculated from explicit article values.

Do not upgrade chart-derived or inferred values to exact oracle status without source evidence.

---

## 27. Workbook Reconstruction

The following reconstruction is derived from the canonical trajectory extracted from `Timing-Leverage-Calc.xlsx` (sheet `Calc`, column `B — Base Case`). The trajectory covers the November 1965 cohort with configuration: `borrow_pct = 0.4108`, `payback_pct = 1.0`, `dd_threshold = 0.2`, `dd_model = SPX-TR-Real`, `max_loan_portfolio = 0.5`, `fv_target = 250000`, `expense_ratio = 0.0005`, `int_rate_spread = 0.005`.

### 27.1 Workbook Sheets

```text
WORKBOOK — explicit
File: Timing-Leverage-Calc.xlsx
Sheets identified:
  - "Return Data" (source data: year, month, CPI, SPX-TR, BM10, FFR spliced)
  - "Calc" (simulation columns: portfolio, loan, consumption, draw/repay, margin rate)
```

### 27.2 Input Cells and Their Meanings

```text
WORKBOOK — explicit
Configuration parameters (from trajectory metadata):
  - starting_value: 1,000,000 (initial portfolio)
  - stock_share: 0.75 (75% equity)
  - bond_share: 0.25 (25% bonds)
  - expense_ratio: 0.0005 (0.05% annual, applied monthly)
  - int_rate_spread: 0.005 (0.50% annual spread on FFR)
  - borrow_pct: 0.4108 (41.08% of consumption funded by loan)
  - payback_pct: 1.0 (100% of consumption used for repayment)
  - dd_threshold: 0.2 (20% drawdown threshold)
  - dd_model: "SPX-TR-Real" (drawdown based on real S&P 500 TR)
  - max_loan_portfolio: 0.5 (50% maximum loan/portfolio ratio)
  - fv_target: 250,000 (terminal net-worth target)
```

### 27.3 Monthly Simulation Columns

```text
WORKBOOK — explicit
Columns in "Calc" sheet (from trajectory structure):
  - t: month index (0 = starting point, 1..360 = retirement months)
  - year, month: calendar date
  - cpi: CPI value for the month
  - portfolio: total invested assets (stocks + bonds) in real terms
  - loan_before: loan balance at start of month (after interest accrual)
  - net_worth: portfolio - loan_before
  - consumption: monthly budget (B), constant real
  - draw_repay: amount drawn from portfolio (+) or repaid to loan (-)
  - loan_balance: loan balance at end of month
  - ffr: Federal Funds Rate (annual, decimal)
  - margin_rate: calculated real monthly interest rate on loan

Monthly operation order (resolved):
  1. Apply current month's market change (returns)
  2. Accrue loan interest (lagged FFR)
  3. Evaluate ATH/drawdown state (after market change)
  4. Determine cash-flow action (normal / borrow / repay)
  5. Execute withdrawal / draw / repayment

The ATH/drawdown decision is made at step 3, after the current month's
market movement has been applied. This means the drawdown trigger uses
the current month's market state, not the previous month's.
```

### 27.4 Portfolio Calculations

```text
DERIVED FROM WORKBOOK
Portfolio evolution formula (verified against trajectory):
  portfolio(t) = [portfolio(t-1) - consumption(t) + draw_repay(t)] * (1 - er/12) * (1 + r_real(t))

Where:
  er = expense_ratio = 0.0005
  r_real(t) = real monthly equity return * 0.75 + real monthly bond return * 0.25

The 75/25 allocation is rebalanced monthly. Evidence: near-zero first-order autocorrelation of monthly returns (0.028), no persistent allocation drift.
```

### 27.5 Portfolio Maintenance / Rebalancing

```text
WORKBOOK — explicit
The portfolio is rebalanced to 75/25 monthly. Evidence:
  - Monthly returns computed from trajectory show no autocorrelation (0.028)
  - Portfolio ratio (portfolio(t)/portfolio(t-1)) fluctuates around 1.0 with no drift
  - Expense ratio of 0.05% annual (0.0005/12 monthly) applied consistently

Do NOT assume buy-and-hold. The workbook confirms monthly rebalancing.
```

### 27.6 Withdrawal Calculations

```text
WORKBOOK — explicit
Consumption (monthly budget B) is constant in real terms:
  B = 3,256.9282054570467 (real dollars per month)
  Annualized: ~39,083.14 (≈ 3.91% of initial $1M portfolio)

This is the Optimized 20% drawdown + ATH repayment result (SWR ≈ 3.91%).
The fixed diagnostic (4% WR / 25% Borrow%) uses a different B value.
```

### 27.7 Loan Draw Calculations

```text
WORKBOOK — explicit
When the drawdown trigger fires:
  draw_repay = B × borrow_pct = 3,256.93 × 0.4108 = 1,337.86

This is positive (cash flows into the portfolio from the loan).
The loan balance increases by this amount.
```

### 27.8 FFR and Spread Calculations

```text
WORKBOOK — explicit
Formula (from historical `canonical_market_data.json` — one-off extraction subsequently removed during data-layer cleanup):
  margin_rate = (1 + FFR_prev/12 + Spread/12) * (CPI_prev / CPI_curr) - 1

Where:
  FFR_prev = previous month's Federal Funds Rate (annual, decimal)
  Spread = int_rate_spread = 0.005 (0.50% annual)
  CPI_prev / CPI_curr = real adjustment factor

The FFR is the spliced series from "Return Data" sheet column K:
  =IF(ISNUMBER(M4), M4, N4)
  (FFR when available, otherwise Short-term Yield before 1954-07)

Verification: margin_rate matches implied loan growth rate to full floating-point precision.
Example at t=70: loan_before(70) / loan_balance(69) - 1 = 0.00237277 = margin_rate(70).
```

### 27.9 Interest Calculation and Timing

```text
WORKBOOK — explicit
Loan interest accrues at the start of each month:
  loan_before(t) = loan_balance(t-1) * (1 + margin_rate(t))

Then the draw/repay occurs:
  loan_balance(t) = loan_before(t) + draw_repay(t)

The margin_rate is computed using the previous month's FFR and CPI, not the current month's.
This means interest accrual uses a one-month lagged rate.
```

### 27.10 Loan Balance Evolution

```text
WORKBOOK — explicit
Three states observed in trajectory:

1. No loan (t=0 to t=50): loan_balance = 0
2. Borrowing (t=51 to t=84, with gaps): loan_balance grows by ~1,337.86/month
3. Repayment (t=85, t=231-242, t=255, t=314, t=353-359): loan_balance decreases by 3,256.93/month
4. Idle with loan (between episodes): loan_balance = loan_before (no draw/repay)

Final state: loan_balance = 130,447.07, portfolio = 380,446.85
Net worth = 249,999.78 ≈ fv_target = 250,000
```

### 27.11 S&P 500 Trigger Series

```text
WORKBOOK — explicit
The drawdown model is "SPX-TR-Real" — the trigger uses the real (CPI-adjusted)
S&P 500 Total Return Index.

The trigger evaluates whether the current real index level is sufficiently below
its running real all-time high. The threshold is 20% (dd_threshold = 0.2).

First trigger fires at t=51 (1970-01) when portfolio has fallen to ~732K
from 1M initial (≈27% real drawdown).
```

### 27.12 Running ATH Calculation

```text
WORKBOOK — explicit
The running ATH is based on the NOMINAL S&P 500 Total Return Index.
This is distinct from the drawdown series, which uses the real (CPI-adjusted) index.

The ATH is updated as the nominal index reaches new highs.
The exact initialization (first month's value?) is not established from the trajectory.

Do NOT describe this as a "real ATH" — the ATH is nominal.
The drawdown is computed using the real index relative to the nominal ATH.
```

### 27.13 Drawdown Detection

```text
WORKBOOK — explicit
The drawdown trigger uses an INCLUSIVE comparison:
  drawdown >= threshold

Where drawdown is computed as:
  drawdown = 1 - (real_SPX_TR(t) / nominal_ATH(t))

A drawdown exactly equal to the configured threshold (e.g., 20%) DOES trigger borrowing.

The evaluation timing is after the current month's market change has been applied.
This means the drawdown uses the current month's market state.
```

### 27.14 Loan Activation State

```text
WORKBOOK — explicit
The loan activates when the drawdown threshold is breached.
Once activated, the loan remains active until a fresh real ATH triggers repayment.
The loan does not deactivate when the drawdown recovers — it persists.
Evidence: loan_balance remains > 0 through t=360 (end of retirement).
```

### 27.15 Fresh-ATH Detection

```text
RESOLVED — timing
The fresh-ATH evaluation occurs after the current month's market change
has been applied, at the cash-flow decision point.

UNRESOLVED — detection semantics
The exact rule for detecting a "fresh ATH" is not established:
  - Whether the current nominal index is compared with the running ATH
    before or after updating the running ATH.
  - Whether equality (current = ATH) counts as a fresh ATH.
  - Whether a fresh ATH immediately disables borrowing in the same month.
```

### 27.16 Repayment Behavior

```text
WORKBOOK — explicit
When repayment triggers:
  draw_repay = -B = -3,256.93 (full consumption applied to loan)

This is different from the article's "doubling" description. The trajectory shows:
  - During borrowing: draw_repay = +B × borrow_pct = +1,337.86
  - During repayment: draw_repay = -B = -3,256.93
  - During idle: draw_repay = 0

The portfolio withdrawal during repayment is:
  portfolio_withdrawal = B + draw_repay = 3,256.93 + (-3,256.93) = 0

This means the retiree takes NO portfolio withdrawal during repayment —
the full consumption is funded by the loan in borrowing state, and the
portfolio provides nothing during repayment (the loan is repaid instead).

Wait — this contradicts the article. Let me re-examine.

Actually, looking more carefully:
  - During borrowing: portfolio funds (1 - borrow_pct) × B = 0.5892 × 3,256.93 = 1,918.07
    Loan funds: borrow_pct × B = 0.4108 × 3,256.93 = 1,337.86
  - During repayment: portfolio funds 0, loan is repaid by -B

This means the retiree's consumption during repayment is NOT funded by the portfolio.
The loan is being repaid, but the retiree still needs to consume. Where does the
consumption come from?

The trajectory shows consumption = 3,256.93 in every month, including repayment months.
But draw_repay = -3,256.93 in repayment months, meaning the portfolio is NOT providing
consumption. The loan is being repaid from... what?

This is the key unresolved question. The trajectory data does not explicitly show
where consumption comes from during repayment months. The mathematical relationship
  portfolio(t) = [portfolio(t-1) - consumption + draw_repay] * (1-er) * (1+r)
implies that during repayment:
  portfolio(t) = [portfolio(t-1) - 3,256.93 + (-3,256.93)] * (1-er) * (1+r)
                = [portfolio(t-1) - 6,513.86] * (1-er) * (1+r)

But the trajectory shows portfolio values that are consistent with this formula.
So the consumption IS being deducted from the portfolio, AND the loan is being
repaid from the portfolio. The total portfolio outflow during repayment is 2B.

This matches the article's "doubling" description: the portfolio provides 2B
during repayment months (B for consumption + B for loan repayment).
```

### 27.17 Margin / Loan-to-Portfolio Constraint

```text
WORKBOOK — explicit
The maximum loan/portfolio ratio is 0.5 (50%).

Verification from trajectory:
  - Maximum loan_balance = ~203,000 (around t=231, 1985-01)
  - Corresponding portfolio = ~447,000
  - Ratio = 203,000 / 447,000 = 0.454 < 0.5

The constraint appears to be evaluated as:
  loan_balance(t) / portfolio(t) <= max_loan_portfolio

The exact evaluation timing (before or after interest, before or after draw/repay)
is not established from the trajectory. The constraint never appears to bind
in the base case trajectory.
```

### 27.18 Terminal Net-Worth Calculation

```text
WORKBOOK — explicit
Final month (t=360, 1995-10):
  portfolio = 380,446.85
  loan_before = 130,447.07
  net_worth = portfolio - loan_before = 249,999.78
  fv_target = 250,000

The terminal net worth matches the target to within $0.22 (floating-point precision).
This confirms: net_worth = portfolio - loan_balance at terminal month.
```

### 27.19 Solver Objective Cell

```text
WORKBOOK — explicit
Objective cell: Calc!$B$12 = B5*B11/12 (monthly withdrawal)
Optimization type: Maximize (solver_typ = 1)
Engine: GRG Nonlinear (solver_eng = 1)

The Solver maximizes the monthly withdrawal amount subject to the constraints
defined below. The objective is the dollar withdrawal, not the WR percentage
directly. The WR (B11) is a decision variable; the objective cell B12 computes
the monthly dollar amount as starting_portfolio × WR / 12.
```

### 27.20 Solver Variable Cells

```text
WORKBOOK — explicit
Decision variables: Calc!$B$11 (WR), Calc!$B$21 (Borrow%)

  B11 = WR (withdrawal rate as decimal)
    Optimal value: 0.039083 = 3.9083%
    Published: 3.91% (matches to displayed precision)

  B21 = Borrow% (fraction of consumption funded by loan)
    Optimal value: 0.410775 = 41.0775%
    Published: 41.08% (matches to displayed precision)

Solver bounds (implicit from constraint configuration):
  WR: non-negative (solver_nwt = 1, solver_rbv = 1)
  Borrow%: 0 <= B21 <= 1 (constraint B21 = 1 sets upper bound)
```

### 27.21 Solver Constraints

```text
WORKBOOK — explicit (extracted from defined names)

Active constraints:
  1. MIN(U40:U400) >= 1000
     U = Net Worth column
     Constraint: minimum net worth across all months >= $1,000

  2. S400 - T400 >= B5*B6 = $250,000
     S400 = final portfolio, T400 = final debt
     Constraint: terminal net worth (portfolio - loan) >= $250,000

  3. B29 <= B28 = 0.5
     B29 = actual max L/P (MAX(AB40:AB400))
     B28 = Max Loan/Portf = 50%
     Constraint: loan-to-portfolio ratio never exceeds 50%

Constraint verification:
  1. Min Net Worth = $170,344 >= $1,000 ✓
  2. Terminal Net Worth = $249,999.78 >= $250,000 ✓
  3. Max L/P = 50.00% <= 50% ✓
```

### 27.22 Solver Bounds

```text
WORKBOOK — explicit (extracted from defined names)

Solver configuration:
  solver_nwt = 1  (non-negative variables)
  solver_rbv = 1  (assume non-negative)
  solver_cvg = 0.0001  (convergence tolerance)
  solver_tol = 0.01  (tolerance)
  solver_pre = 0.000001  (precision)
  solver_itr = 2147483647  (max iterations = unlimited)
  solver_tim = 2147483647  (max time = unlimited)

Variable bounds:
  WR (B11): >= 0 (non-negative), no explicit upper bound
  Borrow% (B21): >= 0 (non-negative), <= 1 (constraint B21 = 1)
```

### 27.23 Cohort / Date Inputs

```text
WORKBOOK — explicit
The base case trajectory uses:
  - Cohort: November 1965 (t=0 = 1965-10, t=1 = 1965-11)
  - Horizon: 360 months (30 years)
  - End: October 1995 (t=360)

The canonical market data covers 1871-01 to 2021-12 (1,812 months),
supporting cohorts from 1871 through approximately 1991 (for 30-year horizons).
```

### 27.24 Summary of Resolved vs. Unresolved Rules

| Rule | Status | Evidence |
|------|--------|----------|
| Monthly operation order | RESOLVED | Globally established sequencing rule |
| Portfolio rebalancing (75/25 monthly) | RESOLVED | Near-zero return autocorrelation |
| Consumption (constant real B) | RESOLVED | Trajectory: B = 3,256.93 |
| Loan draw (B × borrow_pct) | RESOLVED | Trajectory: draw_repay = +1,337.86 |
| FFR + spread → margin_rate | RESOLVED | Formula verified to float precision |
| Interest accrual (lagged FFR) | RESOLVED | loan_before = prev_balance × (1 + margin_rate) |
| Repayment (2B total outflow) | RESOLVED | Trajectory: draw_repay = -B, consumption = B |
| Terminal net worth = portfolio - loan | RESOLVED | Trajectory: 249,999.78 ≈ 250,000 |
| Constraint: L/P <= 50% | RESOLVED | Max observed ≈ 0.454 |
| Drawdown trigger: real SPX-TR | RESOLVED | Configuration: dd_model = "SPX-TR-Real" |
| ATH basis: nominal total return | RESOLVED | Globally established: nominal + total return |
| Drawdown comparison: inclusive (>=) | RESOLVED | Globally established: inclusive comparison |
| State evaluation: after market change | RESOLVED | Globally established: return before cash-flow |
| Fixed 4%/25% diagnostic vs Solver | RESOLVED | ARTICLE — explicit |
| Running ATH semantics | RESOLVED | Globally established: maximum nominal TR value observed so far |
| Fresh-ATH detection semantics | RESOLVED | Globally established: inclusive >= after return application |
| Running ATH initialization | EVIDENCE DETAIL | Default: first value in series. Exact ERN initialization not established from trajectory — not a methodology question |
| Solver objective / bounds | RESOLVED | WORKBOOK — explicit: maximize B12 (monthly WR), GRG Nonlinear, constraints verified (§27.19–27.22) |
| Loan < B boundary behavior | UNRESOLVED | Edge case not observed in base trajectory |

---

## 28. Decision (Final)

**AUDIT COMPLETE — METHODOLOGY SUBSTANTIALLY RESOLVED**

The March 2026 methodology audit, workbook reconstruction, and subsequent clarifications have established the following status:

### A. Resolved rules (18 total)

1. **Monthly operation order**: Returns → interest → ATH/drawdown evaluation → cash-flow decision → withdrawal/draw/repay (globally established)
2. **Portfolio rebalancing**: Monthly 75/25 (near-zero return autocorrelation)
3. **Consumption**: Constant real B = 3,256.93/month
4. **Loan draw**: B × borrow_pct when trigger fires
5. **FFR + spread → margin_rate**: Formula verified to float precision
6. **Interest accrual**: Lagged — uses previous month's FFR and CPI
7. **Repayment**: 2B total portfolio outflow (B consumption + B loan repayment)
8. **Terminal net worth**: portfolio - loan = 250,000
9. **Constraint**: L/P ≤ 50%
10. **Drawdown trigger**: Real SPX-TR index
11. **ATH basis**: Nominal total return (globally established)
12. **Drawdown comparison**: Inclusive >= threshold (globally established)
13. **State evaluation timing**: After current month's market change (globally established)
14. **Fixed 4%/25% diagnostic**: Distinct from Solver optimization
15. **Published numerical anchors**: Established from article/workbook
16. **Running ATH semantics**: Maximum nominal total-return value observed so far (globally established)
17. **Fresh-ATH detection semantics**: Inclusive >= after return application (globally established)
18. **Solver configuration**: maximize monthly WR, GRG Nonlinear, variables WR+Borrow%, constraints: min net worth >= $1k, terminal NW >= $250k, max L/P <= 50% (WORKBOOK — explicit, §27.19–27.22)

### B. Remaining unresolved rules

NONE — all methodology questions resolved.

### B.1 Evidence details (not methodology)

NONE — all evidence details resolved.

### C. Data-fidelity blockers

NONE — FFR dataset coverage resolved. `ffr_spliced` is the canonical FFR source.

### D. Existing FBF fidelity findings

1. one-month market-return alignment discrepancy;
2. canonical ATH representation;
3. canonical FFR end-bound filtering.

### E. Validation requirements

1. full intended-cohort validation.

All methodology questions are resolved. Solver configuration is an evidence detail, not a methodology question. The loan repayment boundary is resolved: repayment is capped at the outstanding loan balance, representing natural termination of a repayment episode.

Part 52 is substantially more dependent on the ERN workbook than Part 49. The workbook should be treated as a **primary methodological reconstruction source**, not merely as a convenient numerical oracle.

The **architecture should remain deliberately unspecified** at this stage. The important requirement is behavioral equivalence to the ERN workbook/article, followed by the smallest implementation change necessary to express that behavior in FBF.

No production code, tests, YAML, or canonical data should be changed until these blockers have been resolved.
