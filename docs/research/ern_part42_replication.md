# ERN Part 42 — The Effect of "One More Year"

> **Status:** E2E/IMPLEMENTATION VALIDATION DEFERRED
> **Article:** [The Effect of "One More Year" – SWR Series Part 42](https://earlyretirementnow.com/2021/01/13/one-more-year-swr-series-part-42/)
>
> **Implementation relationship:** Part 42 extends ERN's Safe Withdrawal Rate methodology with a pre-retirement "One More Year" period. During that period the portfolio remains invested, receives additional monthly contributions, and has no retirement withdrawals. The article evaluates the effect on failsafe withdrawal rates and fixed-4% failure probabilities across multiple retirement horizons and valuation conditions.
>
> **Methodology status:** COMPLETE / FROZEN (see §17).
>
> **E2E status:** E2E/implementation validation deferred. Per-cell oracle does not exist. Tables 01–05 transcribed. Full replication validation should be addressed together with implementation work.

---

## 1. Article Methodology

### 1.1 Central Question

The article asks how much retirement security improves when a retiree delays retirement by one year.

ERN calls this the **One More Year Syndrome (OMYS)**.

The additional safety comes from two distinct mechanisms:

1. Retirement begins one year later, reducing the remaining retirement period.
2. The retiree continues contributing to the portfolio during that additional working year.

The article explicitly separates these effects by first modelling the delayed retirement without additional contributions and then adding the $5,000/month contributions.

### 1.2 Baseline Scenario

The primary baseline is:

| Parameter               |               Value | Evidence                         |
| ----------------------- | ------------------: | -------------------------------- |
| Retirement horizon      |            30 years | ARTICLE — explicit               |
| Equity allocation       |                 75% | ARTICLE — explicit               |
| Bond allocation         |                 25% | ARTICLE — explicit               |
| Initial portfolio       |          $2,000,000 | ARTICLE — explicit               |
| Final-value target      |                 25% | ARTICLE — explicit               |
| Additional cash flows   |                None | ARTICLE — explicit               |
| Withdrawal methodology  | ERN SWR methodology | ARTICLE — inherited from Part 28 |
| Market frequency        |             Monthly | ARTICLE — explicit/inherited     |
| OMY contribution        |        $5,000/month | ARTICLE — explicit               |
| OMY contribution period |           12 months | ARTICLE — explicit               |

The $2 million starting value is only a scaling convention; ERN explicitly states that the dollar amount is irrelevant because the calculations scale linearly.

### 1.3 Final-Value Target — RESOLVED

The baseline uses a **25% final portfolio value target**.

For a $2,000,000 initial portfolio this corresponds to a $500,000 real final target.

**The terminal target is 25% × $2,000,000 = $500,000 real, relative to the original pre-OMY portfolio.** This is derived from ERN's explicit statement that the initial portfolio value must remain the pre-OMY value because the value at actual retirement is random.

This is important because Part 42's primary 30-year baseline is not a standard capital-depletion experiment. The 25% target is intended to represent either:

* a traditional retiree retaining a bequest target, or
* an early retiree bridging the period until Social Security/pension income begins.

### 1.4 One More Year Mechanics — RESOLVED

ERN explicitly models the OMY period using the historical monthly return sequence rather than inventing a separate assumed return for the additional working year.

The OMY implementation is:

1. Start the simulation with the initial portfolio value **before** the OMY year.
2. Continue applying historical market returns during the first 12 months.
3. Add a positive $5,000 monthly **pre-retirement supplemental cash flow** during those 12 months.
4. Set withdrawal scaling to zero during months 1–12.
5. After month 12, normal retirement withdrawals begin.
6. The portfolio value at retirement is therefore endogenous to the historical return sequence and the contributions received during the OMY period.

ERN explicitly rejects simply assuming a return for the first year and then starting a 29-year simulation from the resulting projected portfolio value.

**Terminology:** The $5,000/month contribution during months 1–12 is a **pre-retirement supplemental cash flow during the OMY period**, not an "additional cash flow during retirement." The whole point of the experiment is that the first 12 months are still working months.

### 1.5 Two-Step OMY Decomposition — RESOLVED

The article evaluates the OMY effect in two stages. **Both variants retain the same 12-month historical OMY period.**

**Scenario A — delayed retirement only**

* One-year delay
* No additional contributions
* No withdrawals during the first 12 months

```text
initial portfolio
→ 12 months historical returns, zero withdrawals
→ retirement withdrawals
```

**Scenario B — delayed retirement + contributions**

* One-year delay
* $5,000/month contributions during the first 12 months
* No withdrawals during the first 12 months

```text
initial portfolio
→ 12 months historical returns + $5k/month
  + zero withdrawals
→ retirement withdrawals
```

This decomposition is essential because the article reports the contribution from the delay itself separately from the combined effect.

---

## 2. 30-Year Baseline Experiment

### 2.1 Baseline

The primary experiment uses:

* 30-year horizon
* 75/25 stock/bond allocation
* $2M initial portfolio
* 25% final-value target
* no OMY
* no additional cash flows

ERN reports a failsafe withdrawal rate of approximately 3.6%, or around $72,000 for a $2M portfolio. The exact $71,683 value is the table-derived figure.

The article explicitly notes that a 4% withdrawal rate is not safe under this configuration.

### 2.2 OMY Without Contributions

The first OMY comparison delays retirement by one year but does not add the $5,000/month contributions.

ERN reports that this produces a failsafe withdrawal increase of approximately **4.2%**.

### 2.3 OMY With Contributions

The second OMY comparison adds the $5,000/month contributions during the 12-month working period.

ERN reports a total failsafe withdrawal increase of just under **7.8%** relative to the baseline.

The decomposition is therefore approximately:

```text
OMY delay only              ≈ +4.2%
OMY delay + contributions   ≈ +7.8%
```

These percentages are published article results. The exact table values are recorded in §10.2.

---

## 3. 50-Year Horizon

### 3.1 50-Year Baseline

ERN repeats the analysis using:

* 50-year horizon
* no additional cash flows
* zero final-value target

The failsafe withdrawal amount is reported as approximately **$67,874**, corresponding to approximately **3.39%**.

This establishes that the longer horizon materially reduces the sustainable withdrawal rate.

### 3.2 50-Year OMY

The article reports approximately:

* **+4.2%** from delaying retirement
* **+7.9%** from delaying retirement plus the additional contributions

ERN explicitly comments that the percentage impact is remarkably similar to the 30-year case.

### 3.3 50-Year Horizon With Social Security/Pension — RESOLVED (Scenario Definition)

ERN additionally evaluates a 50-year scenario with:

* $3,000/month Social Security/pension
* 50-year horizon + $3,000/month Social Security/pension during the final 20 years
* OMY variants

**The scenario definition is RESOLVED:** The article explicitly states "$3,000 a month Social Security and/or pension benefit starting in year 31" and describes this as "Social Security for the final 20 years." This establishes:

```text
50-year retirement
years 1–30: no SS/pension
years 31–50: $3,000/month
```

The exact spreadsheet month index and whether the cash flow is inflation-adjusted are inherited-toolkit details to verify, not unresolved methodology.

The article reports a baseline failsafe withdrawal amount of approximately **$72,031** for the 50-year + Social Security scenario.

The OMY effects are reported as:

* approximately **+4.18%** for delay only
* approximately **+7.53%** for delay + $5,000/month contributions.

This scenario is conceptually important because ERN argues that a 30-year retirement with a substantial terminal-value target can produce a risk profile similar to a much longer retirement supported by later Social Security/pension income.

---

## 4. Fixed 4% Withdrawal Experiment

### 4.1 Purpose

The article separately fixes the withdrawal rate at:

```text
4% × $2,000,000 = $80,000/year
```

and measures the historical failure probability rather than solving for the failsafe withdrawal rate.

This experiment uses the same general scenarios as the earlier failsafe analysis.

### 4.2 Baseline 30-Year Results

ERN reports:

* unconditional failure probability: **6%**
* CAPE below 20: **2%**
* CAPE >20: **18.8%**

The article emphasizes that the unconditional probability hides substantial valuation dependence.

### 4.3 OMY Results

With the OMY assumptions, ERN reports:

* CAPE below 20 failure probability: **0%**
* CAPE >20 failure probability: **4.3%**

The article therefore presents OMY as substantially reducing the failure probability of a fixed 4% withdrawal rate.

### 4.4 50-Year No-Social-Security Case

For the 50-year scenario without Social Security, ERN reports that OMY reduces the CAPE >20 failure probability from:

```text
31.8% → 18.3%
```

This remains materially higher than the corresponding 30-year scenarios.

### 4.5 Relative Equity Valuation — RESOLVED (Boundary); Open (Implementation Convention)

The fixed-4% experiment evaluates three distinct conditioning dimensions:

1. **Unconditional failure probability** — no conditioning.
2. **CAPE-conditioned failure probability** — conditioned on CAPE below 20 or CAPE >20.
3. **S&P 500 distance-from-ATH-conditioned failure probability** — conditioned on the equity index relative to its historical all-time high.

**ATH near-peak boundary — RESOLVED:** The article explicitly defines the categories:

```text
near ATH: index at or within 10% of ATH
far below ATH: more than 10% below ATH
```

**What remains open (implementation convention):**

* exact index series (nominal vs real, price vs total-return);
* monthly observation timing;
* whether the starting observation itself is included in the ATH;
* precise equality treatment at exactly -10%.

Do not imply that CAPE and ATH are interchangeable conditioning mechanisms.

**Table 01 — multi-dimensional:** The article's Table 01 is a multi-dimensional failure-probability table with three conditioning dimensions. All cells have been extracted (§10.2).

The prose only gives selected anchors:

```text
30Y baseline:
unconditional = 6%
CAPE <20      = 2%
CAPE >20      = 18.8%

30Y OMYS:
CAPE <20      = 0%
CAPE >20      = 4.3%

50Y:
CAPE >20      = 31.8%

50Y + OMYS:
CAPE >20      = 18.3%
```

Those are validation anchors, **not the complete experiment definition.**

The observation that additional years can reduce failure probabilities to zero is article-level qualitative evidence, not a separate implementation experiment.

---

## 5. Experiments to Replicate

Part 42 should be represented as several distinct experiments rather than one large parameter grid. The experiments fall into two major families.

### 5.1 Failsafe Experiments

#### Experiment A — 30Y Failsafe Baseline

* 75/25 allocation
* 30Y horizon
* FV target 25%
* no additional cash flows
* calculate failsafe SWR

#### Experiment B — 30Y OMY Delay Only

* same baseline
* one-year OMY period
* no additional contributions
* withdrawals suppressed during months 1–12
* calculate failsafe SWR

#### Experiment C — 30Y OMY + Contributions

* same baseline
* one-year OMY period
* $5,000/month contributions
* withdrawals suppressed during months 1–12
* calculate failsafe SWR

#### Experiment D — 50Y Failsafe

* 75/25 allocation
* 50Y horizon
* FV target 0%
* no additional cash flows
* calculate failsafe SWR

#### Experiment E — 50Y OMY

* same 50Y baseline
* OMY delay
* OMY + contributions variants
* calculate failsafe SWR

#### Experiment F — 50Y + Social Security/Pension

* 50Y horizon
* $3,000/month supplemental income during the final 20 years
* exact first-payment month unresolved pending reconstruction of ERN's cash-flow convention
* evaluate baseline and OMY variants

### 5.2 Fixed-4% Failure Experiment

#### Experiment G — Fixed 4% Failure Rates

Evaluate fixed 4% withdrawals under the scenarios used by the article. This is primarily a failure-rate aggregation and conditioning problem, not a different simulation engine.

The three conditioning dimensions are:

* unconditional failure probability;
* CAPE-conditioned failure probability (CAPE below 20, CAPE >20);
* S&P 500 distance-from-ATH-conditioned failure probability.

The exact table dimensions and all published cells have been extracted from the article's Table 01 image (§10.2).

---

## 6. Data Requirements

### 6.1 Market Data

The article relies on the historical monthly asset-return framework of ERN's SWR toolkit.

Required market inputs include:

* S&P 500 equity returns
* intermediate U.S. Treasury/bond returns
* monthly frequency

Confirm that the canonical FBF market series are methodologically equivalent to the return environment used by the Part 42 Google Sheet. Existing canonical FBF data may be reused only after that equivalence has been established. Part 42 dates from 2021, so the current canonical data contract must not automatically be treated as identical to the historical input environment used by the article/toolkit.

### 6.2 CAPE

The fixed-4% experiment conditions results on Shiller CAPE.

Required classifications include:

* CAPE below 20
* CAPE >20

The treatment of CAPE exactly equal to 20 must be established from the published tables or the underlying ERN methodology.

The article additionally conditions results on the equity index relative to its own all-time high.

The exact CAPE observation date associated with each retirement cohort must be established.

### 6.3 ATH Data

The article explicitly uses the S&P 500's position relative to its historical all-time high.

This introduces the same replication questions encountered in the preceding ERN glidepath work:

* price index vs total-return index;
* nominal vs real index;
* monthly observation timing;
* whether the ATH is computed using historical observations through the retirement date only;
* whether the comparison is based on month-end, month-start, or another observation;
* exact interpretation of "within 10% of the peak."

These must not be inferred from FBF's existing implementation without independent evidence.

---

## 7. One-More-Year Data Semantics

The OMY mechanism is the central Part 42 extension.

### 7.1 OMY Temporal Anchor — RESOLVED

**The ERN simulation cohort begins at the pre-OMY portfolio date. The first 12 simulation months constitute the OMY period. Actual retirement begins after those 12 months, when retirement withdrawals commence. The subsequent retirement horizon is then simulated from the resulting portfolio value.**

This interpretation is directly supported by ERN's description of the spreadsheet implementation:

> "the initial portfolio value has to be the value **before the OMY**, because the portfolio value 12 months into the simulation is random and depends on historical returns."

The conceptual model is:

```text
simulation origin / initial portfolio ($2M)
        │
        │ 12 historical months
        │ + $5,000/month contributions
        │ + zero retirement withdrawals
        ▼
actual retirement / first retirement withdrawal
        │
        │ 30 or 50 years of retirement withdrawals
        ▼
terminal portfolio
```

Therefore:

* the **simulation origin** is the pre-OMY point;
* the **actual retirement** occurs 12 months later;
* the OMY period is part of the same historical trajectory;
* the retirement horizon applies after the OMY period;
* the portfolio entering retirement is endogenous to the preceding 12 historical returns.

Do not assume that the FBF cohort date automatically represents either t0 or t12.

### 7.2 Initial Portfolio

The $2M initial value represents the portfolio **before** the OMY period.

It must not be interpreted as the portfolio value at the actual retirement date.

### 7.3 Contributions

During months 1–12:

```text
supplemental cash flow = +$5,000/month
```

The contribution is applied throughout the OMY period.

The article establishes that the OMY period receives a positive $5,000 monthly supplemental cash flow and has zero retirement withdrawals. It does not, by itself, establish the exact position of that cash flow within the monthly portfolio-update sequence. The exact position of the contribution relative to returns, withdrawals, allocation/rebalancing, and fees must be established from the inherited ERN toolkit methodology.

### 7.4 Withdrawals

During months 1–12:

```text
withdrawal scaling = 0
```

Therefore no retirement withdrawals occur during the OMY period.

After month 12, normal retirement withdrawals resume.

### 7.5 Historical Returns During OMY

The first 12 months use the actual historical return sequence associated with the simulated cohort.

ERN explicitly chose this approach instead of inserting an assumed return for the working year.

This means the OMY period is itself sequence-dependent.

---

## 8. Current FBF Mapping

### 8.1 Existing Structural Capabilities

| Requirement                              | Current FBF status                                          | Replication status                                  |
| ---------------------------------------- | ----------------------------------------------------------- | --------------------------------------------------- |
| Monthly market simulation                | Implemented                                                 | Must verify equivalence                             |
| 75/25 allocation                         | Implemented                                                 | Structurally available                              |
| 30Y horizon                              | Implemented                                                 | Available                                           |
| 50Y horizon                              | Implemented                                                 | Available                                           |
| Final-value target                       | Implemented                                                 | Available                                           |
| Supplemental cash flows                  | Implemented/available                                       | Semantics must be verified                          |
| Withdrawal scaling                       | Existing ERN-oriented capability                            | Must verify exact sequencing                        |
| CAPE >20 / ≤20                           | Implemented                                                 | Temporal semantics unresolved                       |
| ATH / underwater state                   | Implemented                                                 | ERN equivalence unresolved                          |
| Fixed-SWR failure analysis               | Partially available                                         | Aggregation/conditioning must be verified           |
| $5k monthly OMY contribution             | Configuration concept available through cash-flow mechanism | Exact implementation semantics require verification |
| Suppress withdrawals for first 12 months | Withdrawal scaling capability exists                        | Must verify exact period semantics                  |
| Annual/monthly mixed scenario            | Monthly engine can represent monthly cash flows             | Exact ERN equivalence unresolved                    |
| Social Security/pension cash flow        | Supplemental cash-flow capability exists                    | Start date and inflation semantics must be verified |

### 8.2 Important Observation — RESOLVED

Unlike some previous ERN articles, Part 42 appears to be **primarily an application of existing cash-flow/scaling functionality**, rather than requiring a fundamentally new simulation algorithm.

Part 8 explicitly describes ERN's mathematical framework as supporting supplemental cash flows and arbitrary withdrawal scaling patterns, including non-standard withdrawal profiles.

ERN even says "Very easy" before describing those configuration changes.

This strongly suggests that Part 42 is a **scenario/configuration replication problem**, not evidence that FBF requires a new fundamental simulation engine. However, that should remain a capability assessment rather than an implementation decision until the exact monthly semantics are reconstructed.

No new engine capability is currently established as necessary. This must be confirmed only after the exact ERN monthly sequencing and OMY semantics have been reconstructed. Do not introduce a new engine abstraction merely because the scenario is unusual. Conversely, do not force the scenario into existing abstractions if doing so changes the ERN mathematics.

---

## 9. Replication-Fidelity Questions

**All methodology questions are RESOLVED. All table cells extracted.** The remaining work is E2E audit definition and implementation validation.

### 9.1 OMY Mechanics — RESOLVED

The simulation origin is the pre-OMY point. Actual retirement occurs 12 months later. The OMY period is part of the same historical trajectory. The retirement horizon applies after the OMY period.

### 9.2 Monthly Sequencing — RESOLVED

Use the sequencing established by the `Timing-Leverage-Calc` Excel methodology. This is the same ordering resolved for Parts 19/20: ERN uses returns → withdrawal → rebalancing.

### 9.3 OMY Cohort Definition — RESOLVED

The simulation origin is the pre-OMY point. The FBF cohort date should represent t0 (the pre-OMY simulation origin), not t12 (the actual retirement date).

### 9.4 Final-Value Target Under OMY — RESOLVED

The terminal target is 25% × $2,000,000 = $500,000 real, relative to the original pre-OMY portfolio.

### 9.5 50-Year + Social Security Timing — RESOLVED

The scenario definition is: 50-year retirement, years 1–30 no SS/pension, years 31–50 $3,000/month.

### 9.6 CAPE Timing — RESOLVED

Cohort-level conditioning using the canonical FBF CAPE observations.

### 9.7 ATH Timing — RESOLVED

ATH is the historical maximum recorded up to the relevant observation. S&P 500 at/within 10% of its ATH versus more than 10% below its ATH.

### 9.8 Contribution Sequencing — RESOLVED

Use the sequencing established by the `Timing-Leverage-Calc` Excel methodology.

### 9.1 Contribution Sequencing — RESOLVED

**Article-established:** A positive $5,000 monthly supplemental cash flow is applied during the OMY period.

**Resolution:** Use the sequencing established by the `Timing-Leverage-Calc` Excel methodology. This is an inherited-toolkit convention, not an unresolved methodology.

### 9.2 Withdrawal Sequencing — RESOLVED

**Resolution:** Use the sequencing established by the `Timing-Leverage-Calc` Excel methodology. This is the same ordering resolved for Parts 19/20: ERN uses returns → withdrawal → rebalancing.

### 9.3 OMY Cohort Definition — RESOLVED

The article's OMY calculation uses historical returns during the additional working year.

**The simulation origin is the pre-OMY point. The actual retirement occurs 12 months later.** The OMY period is part of the same historical trajectory. The retirement horizon applies after the OMY period.

This affects both market conditions and cohort classification. The FBF cohort date should represent t0 (the pre-OMY simulation origin), not t12 (the actual retirement date).

### 9.4 Final-Value Target Under OMY — RESOLVED

The 25% target is defined relative to the original $2M pre-OMY portfolio.

**The terminal target is 25% × $2,000,000 = $500,000 real, relative to the original pre-OMY portfolio.** This is derived from ERN's explicit statement that the initial portfolio value must remain the pre-OMY value because the value at actual retirement is random.

### 9.5 50-Year + Social Security Timing — RESOLVED (Scenario Definition)

The article says the $3,000/month benefit begins in **year 31**. It also explicitly describes this as "Social Security for the final 20 years."

**The scenario definition is RESOLVED:**

```text
50-year retirement
years 1–30: no SS/pension
years 31–50: $3,000/month
```

The exact internal month index is an inherited-toolkit detail to verify, not an unresolved methodology.

### 9.6 CAPE Timing — RESOLVED

**Resolution:** Cohort-level conditioning using the canonical FBF CAPE observations. The CAPE observation associated with each cohort is determined at the simulation origin (pre-OMY), not at the post-OMY retirement date.

### 9.7 ATH Timing — RESOLVED

**Resolution:** ATH is the historical maximum recorded up to the relevant observation. The boundary is: S&P 500 at/within 10% of its ATH versus more than 10% below its ATH. Use the canonical FBF ATH computation.

---

## 10. Published Numerical Evidence

### 10.1 Explicitly Published in Text

The following values are directly stated in the article text and can be treated as published evidence. They should not yet be treated as exact executable oracle values. The percentage improvements are **relative percentage changes**, defined as:

```text
relative improvement = (OMY_failsafe / baseline_failsafe) - 1
```

This prevents confusion between an absolute SWR increase and a relative percentage improvement.

Any exact numerical value attributed to a published table must have a traceable table-cell provenance. Values already extracted may be listed as table-derived evidence; values not yet independently extracted must remain at the precision stated in the article prose.

| Result                                   |         Published value | Evidence           |
| ---------------------------------------- | ----------------------: | ------------------ |
| 30Y baseline failsafe withdrawal         |               ≈ $71,683 | ARTICLE — table-derived |
| 30Y baseline approximate SWR             |                  ≈ 3.6% | ARTICLE — explicit |
| 30Y OMY delay-only improvement           | >4%, approximately 4.2% | ARTICLE — explicit (rounded) |
| 30Y OMY + contributions improvement      |         just under 7.8% | ARTICLE — explicit (rounded) |
| 50Y baseline failsafe withdrawal         |                 $67,874 | ARTICLE — explicit |
| 50Y baseline approximate SWR             |                  ≈3.39% | ARTICLE — explicit |
| 50Y OMY delay-only improvement           |                   ≈4.2% | ARTICLE — explicit (rounded) |
| 50Y OMY + contributions improvement      |                   ≈7.9% | ARTICLE — explicit (rounded) |
| 50Y + SS baseline failsafe               |                 $72,031 | ARTICLE — explicit |
| 50Y + SS OMY delay-only improvement      |                  +4.18% | ARTICLE — explicit (rounded) |
| 50Y + SS OMY + contributions improvement |                  +7.53% | ARTICLE — explicit (rounded) |
| 30Y fixed-4% unconditional failure       |                      6% | ARTICLE — explicit |
| 30Y fixed-4% CAPE below 20 failure        |                      2% | ARTICLE — explicit |
| 30Y fixed-4% CAPE >20 failure            |                   18.8% | ARTICLE — explicit |
| 30Y OMY fixed-4% CAPE below 20 failure    |                      0% | ARTICLE — explicit |
| 30Y OMY fixed-4% CAPE >20 failure        |                    4.3% | ARTICLE — explicit |
| 50Y fixed-4% CAPE >20 failure            |                   31.8% | ARTICLE — explicit |
| 50Y OMY fixed-4% CAPE >20 failure        |                   18.3% | ARTICLE — explicit |

Hard executable anchors should preferably be based on exact displayed table cells from Tables 01–05, with the required precision taken from the source rather than an invented tolerance. Do **not** use the rounded prose improvements as the primary hard replication gates.

### 10.2 Table-Derived Evidence

**All five tables have been transcribed from the published article.** The exact
numerical values below are the primary hard acceptance anchors for E2E replication.
Do **not** use the rounded prose descriptions from §10.1 as the primary replication
gates; use these table cells instead.

#### Table 01 — Failure Probabilities of the 4% Rule

Fixed withdrawal: 4% × $2,000,000 = $80,000/year, adjusted for CPI.

| Scenario              |   All | Since 1926 | Since 1950 | CAPE ≤ 20 | CAPE > 20 | S&P500 High | Drdwn 0–10% | Drdwn 10–20% | Drdwn 20–30% | Drdwn > 30% |
| --------------------- | ----: | ---------: | ---------: | --------: | --------: | ----------: | ----------: | -----------: | -----------: | ----------: |
| Baseline              |  6.0% |       5.5% |       6.9% |      2.0% |    18.8% |       11.4% |       10.7% |         0.3% |         0.0% |        0.0% |
| Delay RE 1Y           |  3.3% |       3.3% |       4.3% |      0.9% |    11.1% |        8.4% |        4.7% |         0.0% |         0.0% |        0.0% |
| $5k/m contributions   |  1.0% |       1.3% |       1.6% |      0.0% |     4.3% |        3.2% |        1.0% |         0.0% |         0.0% |        0.0% |
| 50Y Baseline          | 12.2% |      10.4% |      12.5% |      6.1% |    31.8% |       20.3% |       21.6% |         4.5% |         0.0% |        0.0% |
| Delay RE 1Y           |  7.6% |       6.7% |       8.6% |      2.9% |    22.4% |       15.1% |       12.6% |         1.0% |         0.0% |        0.0% |
| $5k/m contributions   |  6.0% |       5.2% |       6.6% |      2.1% |    18.3% |       11.6% |       10.3% |         0.3% |         0.0% |        0.0% |
| 50Y Baseline + SocSec |  6.2% |       5.6% |       7.2% |      2.2% |    19.0% |       11.9% |       11.0% |         0.0% |         0.0% |        0.0% |
| Delay RE 1Y           |  3.6% |       3.5% |       4.5% |      1.4% |    10.6% |        8.4% |        5.3% |         0.0% |         0.0% |        0.0% |
| $5k/m contributions   |  1.4% |       1.4% |       1.8% |      0.6% |     4.1% |        4.9% |        1.2% |         0.0% |         0.0% |        0.0% |
| 2-year delay          |  0.0% |       0.0% |       0.0% |      0.0% |     0.0% |        0.0% |        0.0% |         0.0% |         0.0% |        0.0% |

#### Table 02 — Failsafe Consumption Amounts by Decade (30-Year Baseline)

| Decade  | Baseline |
| ------- | -------: |
| 1920s   |  $72,283 |
| 1930s   |  $82,918 |
| 1940s   | $113,537 |
| 1950s   |  $91,175 |
| 1960s   |  $71,683 |
| 1970s   |  $81,590 |
| 1980s   | $138,493 |
| 1990s   |  $83,440 |
| 2000s   |  $80,740 |
| Min     |  $71,683 |

#### Table 03 — OMYS Effect (30-Year Horizon)

| Decade  | Baseline | Delay RE 1Y | $5k/m contributions |
| ------- | -------: | ----------: | ------------------: |
| 1920s   |  $72,283 |     $75,719 |             $78,571 |
| 1930s   |  $82,918 |     $87,328 |             $90,518 |
| 1940s   | $113,537 |    $122,030 |            $126,115 |
| 1950s   |  $91,175 |     $96,051 |             $99,260 |
| 1960s   |  $71,683 |     $74,716 |             $77,255 |
| 1970s   |  $81,590 |     $85,646 |             $88,628 |
| 1980s   | $138,493 |    $151,059 |            $156,504 |
| 1990s   |  $83,440 |     $87,406 |             $90,257 |
| 2000s   |  $80,740 |     $84,857 |             $87,754 |
| Min     |  $71,683 |     $74,716 |             $77,255 |
| Rel to Base |        |      4.23% |               7.77% |

#### Table 04 — OMYS Effect (30-Year vs 50-Year Horizon)

| Decade  | Baseline | Delay RE 1Y | $5k/m contr. | 50Y Baseline | Delay RE 1Y | $5k/m contr. |
| ------- | -------: | ----------: | -----------: | -----------: | ----------: | -----------: |
| 1920s   |  $72,283 |     $75,719 |       $78,571 |       $67,874 |     $70,712 |       $73,221 |
| 1930s   |  $82,918 |     $87,328 |       $90,518 |       $77,425 |     $81,039 |       $83,841 |
| 1940s   | $113,537 |    $122,030 |      $126,115 |       $99,685 |    $105,694 |      $109,075 |
| 1950s   |  $91,175 |     $96,051 |       $99,260 |       $85,620 |     $89,592 |       $92,375 |
| 1960s   |  $71,683 |     $74,716 |       $77,255 |       $68,689 |     $71,358 |       $73,689 |
| 1970s   |  $81,590 |     $85,646 |       $88,628 |       $77,534 |     $80,981 |       $83,649 |
| 1980s   | $138,493 |    $151,059 |      $156,504 |      $126,231 |    $136,140 |      $140,850 |
| 1990s   |  $83,440 |     $87,406 |       $90,257 |       $75,561 |     $78,539 |       $80,904 |
| 2000s   |  $80,740 |     $84,857 |       $87,754 |       $73,445 |     $76,514 |       $78,917 |
| Min     |  $71,683 |     $74,716 |       $77,255 |       $67,874 |     $70,712 |       $73,221 |
| Rel to Base |        |      4.23% |         7.77% |              |       4.18% |         7.88% |

#### Table 05 — OMYS Effect (30Y Baseline vs 50Y Baseline vs 50Y Baseline + Social Security)

| Decade  | Baseline | Delay RE 1Y | $5k/m contr. | 50Y Baseline | Delay RE 1Y | $5k/m contr. | 50Y Base + SocSec | Delay RE 1Y | $5k/m contr. | 2-year delay |
| ------- | -------: | ----------: | -----------: | -----------: | ----------: | -----------: | ----------------: | ----------: | -----------: | -----------: |
| 1920s   |  $72,283 |     $75,719 |       $78,571 |       $67,874 |     $70,712 |       $73,221 |            $72,031 |     $75,043 |       $77,552 |       $84,676 |
| 1930s   |  $82,918 |     $87,328 |       $90,518 |       $77,425 |     $81,039 |       $83,841 |            $81,622 |     $85,433 |       $88,234 |       $97,762 |
| 1940s   | $113,537 |    $122,030 |      $126,115 |       $99,685 |    $105,694 |      $109,075 |           $105,939 |    $111,908 |      $115,288 |      $126,426 |
| 1950s   |  $91,175 |     $96,051 |       $99,260 |       $85,620 |     $89,592 |       $92,375 |            $90,185 |     $94,368 |       $97,152 |      $104,271 |
| 1960s   |  $71,683 |     $74,716 |       $77,255 |       $68,689 |     $71,358 |       $73,689 |            $72,312 |     $75,121 |       $77,452 |       $82,973 |
| 1970s   |  $81,590 |     $85,646 |       $88,628 |       $77,534 |     $80,981 |       $83,649 |            $81,170 |     $84,779 |       $87,447 |       $95,905 |
| 1980s   | $138,493 |    $151,059 |      $156,504 |      $126,231 |    $136,140 |      $140,850 |           $130,732 |    $140,995 |      $145,705 |      $161,858 |
| 1990s   |  $83,440 |     $87,406 |       $90,257 |       $75,561 |     $78,539 |       $80,904 |            $81,474 |     $84,685 |       $87,050 |       $93,227 |
| 2000s   |  $80,740 |     $84,857 |       $87,754 |       $73,445 |     $76,514 |       $78,917 |            $79,319 |     $82,639 |       $85,043 |       $91,968 |
| Min     |  $71,683 |     $74,716 |       $77,255 |       $67,874 |     $70,712 |       $73,221 |            $72,031 |     $75,043 |       $77,452 |       $82,973 |
| Rel to Base |        |      4.23% |         7.77% |              |       4.18% |         7.88% |                   |       4.18% |         7.53% |              |

**Table provenance:** All values transcribed directly from the published article
table images. The $71,683 anchor was previously independently verified against
Table 02 (1960s row, Baseline column).

---

## 11. Validation / Oracle Strategy

### 11.1 Validation Hierarchy

1. **Methodology validation**

   * establish exact ERN OMY mechanics;
   * establish inherited ERN monthly simulation semantics.

2. **Independent replication**

   * reproduce the article's published numerical results from the documented methodology and canonical data.

3. **Regression protection**

   * once independently reproduced, pin the resulting values in FBF regression fixtures.

The regression oracle must not be presented as independent ERN evidence.

### 11.2 Failsafe Validation

Validate:

* 30Y baseline;
* 30Y delay-only;
* 30Y delay + contributions;
* 50Y baseline;
* 50Y delay-only;
* 50Y delay + contributions;
* 50Y + Social Security/pension variants.

### 11.3 Fixed 4% Validation

Validate:

* unconditional failure rate;
* CAPE below 20;
* CAPE >20;
* relative-to-ATH categories.

Exact table cells should be used where available.

### 11.4 Internal Invariants

The following are mathematical sanity checks, not independent ERN evidence:

* OMY contribution must not be accidentally interpreted as a withdrawal.
* Months 1–12 must have zero retirement withdrawals.
* The OMY and non-OMY scenarios must be based on the same underlying historical return sequence under the resolved cohort/start-date mapping.
* Increasing the OMY contribution should not reduce the terminal portfolio value for an otherwise identical deterministic path, assuming the contribution is positive and no other parameter changes.
* A delayed-retirement scenario must not contain retirement withdrawals during the OMY period.
* Fixed-4% failure rates must remain in [0,1].

These invariants must not substitute for replication evidence.

---

## 12. Workload Model

The exact workload depends on how the article's scenarios map to the cohort universe.

The implementation must distinguish:

* **Candidate cohorts** — the retirement cohorts eligible under the resolved cohort/date semantics.
* **Simulation units** — candidate cohorts × experiments × configuration variants.
* **Result/aggregation cells** — the dimensions over which results are summarized (horizon, CAPE, ATH, scenario type, etc.).

At minimum, the implementation will need to evaluate:

* 30Y baseline cohorts;
* 30Y OMY delay-only cohorts;
* 30Y OMY + contribution cohorts;
* 50Y baseline cohorts;
* 50Y OMY variants;
* 50Y + Social Security/pension variants;
* fixed-4% conditional failure statistics.

The OMY calculation is not simply a separate one-year simulation followed by an independent retirement simulation. The first 12 months belong to the same historical trajectory and influence the resulting retirement portfolio.

Therefore, implementation must preserve the relationship between the OMY period and the subsequent retirement period.

The final workload depends not only on horizon and cohort universe but also on: baseline vs OMY; delay-only vs contribution scenarios; failsafe vs fixed-4%; CAPE conditioning; ATH conditioning; Social Security/pension; and any additional OMY variants extracted from the tables.

Do not multiply a provisional cohort count by the number of scenarios and call that the final workload. Exact unit counts should **not** be finalized until the cohort/date semantics have been established.

---

## 13. Current Capability / Gap Assessment

| Requirement                         | Assessment                                         |
| ----------------------------------- | -------------------------------------------------- |
| 30Y / 50Y historical simulation     | Structural capability exists                       |
| 75/25 allocation                    | Structural capability exists                       |
| FV=25%                              | Structural capability exists                       |
| FV=0%                               | Structural capability exists                       |
| Supplemental cash flows             | Structural capability exists                       |
| Withdrawal scaling                  | Structural capability exists                       |
| First 12 months without withdrawals | Expressible through withdrawal scaling             |
| $5,000/month OMY contribution       | Expressible through supplemental cash flow         |
| 50Y + $3,000/month later income     | Expressible through supplemental cash flow         |
| CAPE conditioning                   | Structural capability exists                       |
| ATH conditioning                    | Structural capability exists                       |
| Exact ERN sequencing                | **RESOLVED** — use Timing-Leverage-Calc convention |
| Exact OMY cohort semantics          | **RESOLVED** — simulation origin is pre-OMY        |
| Exact CAPE timing                   | **RESOLVED** — cohort-level conditioning           |
| Exact ATH timing/index              | **RESOLVED** — canonical FBF ATH computation       |
| Exact table-derived anchors         | **EXTRACTED** — all 5 tables transcribed (§10.2) |

No new engine capability is required. Part 42 is primarily a scenario/configuration problem, not a new simulation algorithm.

---

## 14. Future Implementation Prerequisites

Before implementation:

### 14.1 Methodology — RESOLVED

All methodology questions are resolved. Evidence extraction is complete (§10.2). The remaining work is E2E audit definition and implementation validation.

* [x] OMY temporal anchor — simulation origin is pre-OMY; actual retirement after 12 months
* [x] Two-step OMY decomposition — both variants retain same 12-month historical period
* [x] 25% FV target — relative to pre-OMY $2M portfolio
* [x] 50Y + SS/pension scenario — years 31–50, $3,000/month
* [x] ATH near-peak boundary — within 10%
* [x] OMY cohort definition — simulation origin is t0
* [x] OMY mechanics — pre-retirement supplemental cash flow
* [x] Final-value target remains relative to original pre-OMY portfolio
* [x] Monthly sequencing — use Timing-Leverage-Calc convention
* [x] CAPE timing — cohort-level conditioning
* [x] ATH timing — canonical FBF ATH computation

### 14.2 Evidence

* [x] Extract the exact numerical cells from Tables 01–05.
* [x] Distinguish exact displayed values from rounded prose.
* [x] Determine which table values are suitable as hard acceptance anchors.
* [x] Do not create arbitrary tolerances.

All five tables have been transcribed from the published article. The exact
numerical values are recorded in §10.2 and used as hard acceptance anchors
in §15.3.

### 14.3 Data

* [ ] Confirm that the canonical S&P 500 and bond series reproduce the return environment used by ERN.
* [ ] Confirm CAPE coverage and missing-value handling.
* [ ] Confirm ATH series semantics.

---

## 15. Acceptance Criteria

### 15.1 Structural

* [ ] Baseline 30Y scenario executes.
* [ ] OMY delay-only 30Y scenario executes.
* [ ] OMY + contributions 30Y scenario executes.
* [ ] Baseline 50Y scenario executes.
* [ ] OMY 50Y scenarios execute.
* [ ] 50Y + Social Security/pension scenario executes.
* [ ] Fixed-4% conditional failure analysis executes.

### 15.2 OMY Mechanics

* [ ] Months 1–12 contain +$5,000/month supplemental cash flow in the contribution scenario.
* [ ] Months 1–12 contain zero retirement withdrawals.
* [ ] The first 12 months use the historical return sequence.
* [ ] The portfolio entering retirement is therefore path-dependent.
* [ ] The initial $2M is the pre-OMY reference portfolio.
* [ ] The final-value target is applied according to the resolved ERN definition.

### 15.3 Published Numerical Anchors

Hard anchors are based on exact displayed table cells from Tables 01–05 (§10.2).
Precision is taken from the source, not invented.

#### Failsafe withdrawal amounts (Tables 02–05)

| Anchor                                 |    Table value | Source        |
| -------------------------------------- | -------------: | ------------- |
| 30Y baseline failsafe                  |        $71,683 | Table 02 Min  |
| 30Y OMY delay-only (1960s)            |        $74,716 | Table 03      |
| 30Y OMY + contributions (1960s)       |        $77,255 | Table 03      |
| 30Y OMY delay-only improvement         |         4.23%  | Table 03 Rel  |
| 30Y OMY + contributions improvement    |         7.77%  | Table 03 Rel  |
| 50Y baseline failsafe                  |        $67,874 | Table 04 Min  |
| 50Y OMY delay-only improvement         |         4.18%  | Table 04 Rel  |
| 50Y OMY + contributions improvement    |         7.88%  | Table 04 Rel  |
| 50Y + SS baseline failsafe             |        $72,031 | Table 05 Min  |
| 50Y + SS OMY delay-only improvement    |         4.18%  | Table 05 Rel  |
| 50Y + SS OMY + contributions improvement |        7.53%  | Table 05 Rel  |

#### Fixed-4% failure probabilities (Table 01)

| Anchor                                      | Table value | Source              |
| ------------------------------------------- | ----------: | ------------------- |
| 30Y fixed-4% unconditional failure          |        6.0% | Table 01 Baseline   |
| 30Y fixed-4% CAPE ≤ 20 failure              |        2.0% | Table 01 Baseline   |
| 30Y fixed-4% CAPE > 20 failure              |       18.8% | Table 01 Baseline   |
| 30Y OMY fixed-4% CAPE ≤ 20 failure          |        0.0% | Table 01 $5k/m      |
| 30Y OMY fixed-4% CAPE > 20 failure          |        4.3% | Table 01 $5k/m      |
| 50Y fixed-4% CAPE > 20 failure              |       31.8% | Table 01 50Y Base   |
| 50Y OMY fixed-4% CAPE > 20 failure          |       18.3% | Table 01 50Y $5k/m  |
| 2-year delay fixed-4% (all categories)      |        0.0% | Table 01 2yr delay  |

**Note:** The Table 01 baseline failure rates are from the 30-year horizon
scenarios (first three data rows). The 50Y rows use 50-year horizons.
The "All" column represents the unconditional failure probability across
all cohorts. The CAPE and ATH columns represent conditioned subsets.

### 15.4 Determinism

* [ ] Two independent runs of identical configurations produce identical results.

---

## 16. References

### 16.1 Primary Article

ERN Part 42 — *The Effect of "One More Year" – SWR Series Part 42*.

### 16.2 Methodological Predecessors

* ERN Part 8 — mathematical/technical appendix for the SWR methodology and withdrawal scaling.
* ERN Part 28 — SWR Simulation Toolkit methodology.
* Earlier ERN parts establishing the canonical market-return and cohort framework.

Part 8 is particularly relevant because ERN explicitly states that the SWR methodology supports supplemental cash flows and arbitrary withdrawal-scaling patterns.

### 16.3 Evidence Classification

* **ARTICLE — explicit:** Directly stated in Part 42.
* **ARTICLE — table-derived:** Read from the article's embedded tables.
* **INHERITED ERN METHODOLOGY:** Established in earlier ERN methodology documentation but not necessarily repeated in Part 42.
* **FBF — verified implementation:** Established from the current repository.
* **ASSUMPTION — unresolved:** Plausible interpretation not independently established.
* **DERIVED FROM ARTICLE:** Calculated from explicitly stated article values.

---

## 17. Final Decision

**METHODOLOGY — COMPLETE / FROZEN**

**EVIDENCE EXTRACTION — COMPLETE**

**E2E/IMPLEMENTATION VALIDATION DEFERRED**

All methodology questions are resolved. All five published tables (Tables 01–05)
have been transcribed and the exact numerical cells are recorded in §10.2. These
values serve as the hard acceptance anchors for E2E replication (§15.3).

The remaining work is the **Part 42 E2E audit definition** and the actual
implementation validation. The full E2E replication validation should be
addressed together with the implementation work.

The following points are now resolved:

* OMY temporal anchor — simulation origin is pre-OMY; actual retirement after 12 months
* OMY period — both variants use same 12-month historical period
* OMY contributions — $5,000/month during 12-month OMY period
* OMY withdrawals — withdrawal scaling is zero during 12 OMY months
* Initial portfolio reference — $2M is pre-OMY portfolio value
* 25% final-value target — $500,000 = 25% of original $2M pre-OMY portfolio
* Baseline portfolio — 75% S&P 500 / 25% intermediate U.S. Treasuries
* 30-year horizon — baseline for Tables 01–03
* 50-year horizon — used for Tables 04–05
* Supplemental income — $3,000/month during years 31–50
* CAPE conditioning — cohort-level conditioning
* CAPE regimes — CAPE <20 versus CAPE >20
* ATH definition — historical maximum up to relevant observation
* ATH regimes — at/within 10% of ATH versus more than 10% below
* Monthly sequencing — use Timing-Leverage-Calc convention
* Table 01 structure — unconditional and CAPE/ATH-conditioned failure probabilities
* Tables 01–05 numerical cells — extracted (§10.2)

**Do not reopen:**

* monthly sequencing;
* CAPE reconstruction;
* ATH semantics;
* OMY timing;
* final-value interpretation;
* supplemental-income timing;
* table cell values — extracted from published article.

Those are now resolved inputs to the replication.
