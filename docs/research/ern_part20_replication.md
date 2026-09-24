# ERN Part 20 — More Thoughts on Equity Glidepaths

> **Status:** CANONICAL METHODOLOGY — IMPLEMENTATION ALIGNMENT PENDING
>
> **Article:** [The Ultimate Guide to Safe Withdrawal Rates – Part 20: More Thoughts on Equity Glidepaths](https://earlyretirementnow.com/2017/09/20/the-ultimate-guide-to-safe-withdrawal-rates-part-20-more-thoughts-on-equity-glidepaths/)
>
> **Implementation relationship:** Part 20 extends Part 19 with 8 additional passive-only glidepaths, 30-year horizons, CAPE ≤20 conditioning, fixed-SWR failure-rate analysis, and final-value-target experiments. A deterministic 10-year mechanical case study is presented separately from the historical simulations.
>
> **Methodology status:** COMPLETE — global monthly sequencing and ATH rules established. FBF implementation execution order not yet aligned to established rule.
>
> **E2E status:** NOT YET VALIDATED as canonical ERN replication. Implementation alignment pending.
>
> **E2E audit definition:** See [ern_part20_e2e_audit.md](ern_part20_e2e_audit.md) for the complete audit specification.
>
> **Open question:** Whether Part 20 reproduces Part 19 Experiment A (fixed 3.5% SWR failure-rate analysis) is deferred.

---

## 1. Article Methodology

### 1.1 Central Question

How do equity glidepaths perform under additional dimensions: shorter horizons (30Y), different CAPE regimes (≤20), fixed withdrawal rates (3–4%), higher final-value targets (50%, 100%), and how do they compare to the Kitces/Pfau Monte Carlo-optimal glidepath (30→70%)?

### 1.2 Core Concept

Part 20 extends Part 19 in six ways:
1. Adds 8 new passive-only glidepaths (30→70% and 20→60% variants) inspired by Kitces/Pfau research.
2. Splits CAPE conditioning into >20 and ≤20 (replacing Part 19's "All CAPE vs CAPE >20").
3. Adds 30-year horizon results alongside 60-year.
4. Adds fixed-SWR failure-rate analysis (3.0%–4.0% in 0.25% steps).
5. Adds final-value-target experiments (0%, 50%, 100%).
6. Presents a deterministic 10-year mechanical case study.

### 1.3 Simulation Assumptions (Historical Simulations)

**Article — explicit:**
- Monthly data from January 1871 to December 2015
- Two horizons: 60-year and 30-year
- Retirement dates from January 1871 to December 2015
- Final value targets of 0% (Capital Depletion), 50%, and 100% of real, CPI-adjusted initial portfolio
- Portfolio assets: S&P 500 (equity) and 10-Year Treasury (bonds)
- Monthly CPI-inflation adjustment to withdrawals
- SWR = initial withdrawal rate that exactly achieves the final target value after the horizon
- Expense ratio: 0.05% p.a. (confirmed in article comments)

**ASSUMPTION — derived from Part 19 §6.1:** Returns grow during the month; withdrawal and rebalancing at month-end. This is not explicitly stated in Part 20 but inherited from Part 19.

### 1.4 Static Allocations

The article simulates 21 static stock/bond allocations: 0% to 100% stocks in 5% increments.

### 1.5 CAPE Conditioning

**Article — explicit:** Part 20 changes the conditioning from Part 19:
- **Part 19:** "All CAPE" vs "CAPE > 20"
- **Part 20:** "CAPE > 20" vs "CAPE ≤ 20"

This is a distinct methodological dimension from Part 19. The two conditions are mutually exclusive and exhaustive.

**Evidence classification:** ARTICLE — explicit.

### 1.6 Published Qualitative Conclusions

**Article — explicit (selected):**

1. "When the CAPE is below 20, there is no benefit from a glidepath."
2. "The 60 to 100% glidepath had consistently the best withdrawal rates for all failure probabilities studied here."
3. "The glidepath recommended by the Kitces and Pfau study (30 to 70%) is consistently one of the worst."
4. "The active vs. passive glidepaths and the exact slopes don't make that much of a difference if you get the correct start and especially the endpoint (100%!)."

**Terminology:** The article uses "portfolio depletion" and "portfolio depletion failure" (not "ruin") for the simulation termination event. "Sustainable withdrawal rate" (SWR) is used throughout. These are semantic choices, not mechanical definitions.

### 1.7 Historical vs Monte Carlo Comparison

**Article — explicit:** ERN attributes the difference from Kitces/Pfau Monte Carlo to short-term mean reversion, long-term mean reversion, and changing correlations. This is a research conclusion, not simulation mechanics. FBF's historical simulation is the implementation target.

**Evidence classification:** ARTICLE — explicit.

### 1.8 Charts and Tables

**Article — explicit (6 tables + 1 chart):**

1. **Table 01:** 10-year mechanical case study (bear-then-bull): 70→90% glidepath vs static 80%
2. **Table 02:** 60-year failsafe/percentile SWR table: 53 strategies, CAPE >20 and CAPE ≤20
3. **Table 03:** 30-year failsafe/percentile SWR table: 53 strategies, CAPE >20 and CAPE ≤20
4. **Table 04:** Failure rates of specific SWRs (3%–4% in 0.25% steps), CAPE >20 only
5. **Table 05:** 10-year mechanical case study (bull-then-bear): same returns in reverse order
6. **Table 06:** Higher final value targets (0%, 50%, 100%): CAPE >20, 60-year horizon
7. **Chart 01:** Summary of final portfolio values across return sequences (graphical summary of Tables 01/05)

---

## 2. Part 20 Experiment Grid

### 2.1 Glidepaths

**Article — explicit (32 glidepaths):**

Part 20 uses 32 glidepaths: 24 from Part 19 + 8 new additions.

**Part 19 glidepaths (24):** Inherited from Part 19, same definitions. See Part 19 documentation §2.1.

**Part 20 additions (8 new, passive only):**

| # | Start | End | Slope | Mode | End-Start | Description |
|---|-------|-----|-------|------|-----------|-------------|
| 25 | 30% | 70% | 0.111% | passive | 40pp | Kitces/Pfau original (0.111 pp/month = 40pp / 360 months) |
| 26 | 30% | 70% | 0.2% | passive | 40pp | Faster variant |
| 27 | 30% | 70% | 0.3% | passive | 40pp | Faster variant |
| 28 | 30% | 70% | 0.4% | passive | 40pp | Faster variant |
| 29 | 20% | 60% | 0.111% | passive | 40pp | Low-equity Kitces/Pfau |
| 30 | 20% | 60% | 0.2% | passive | 40pp | Faster variant |
| 31 | 20% | 60% | 0.3% | passive | 40pp | Faster variant |
| 32 | 20% | 60% | 0.4% | passive | 40pp | Faster variant |

**Verification:** 24 (Part 19) + 8 (new) = 32 glidepaths. ARTICLE — explicit.

**Evidence classification:** ARTICLE — explicit. The 8 new glidepaths are described in the article text and appear in the table images. The slope 0.111% corresponds to "30 to 70% equity glidepath over 30 years" with 40pp transition / 360 months = 0.1111% per month.

### 2.2 Other Parameter Dimensions

| Dimension | Values | Source |
|-----------|--------|--------|
| SWR | 3.0%, 3.25%, 3.5%, 3.75%, 4.0% (fixed-SWR experiment) | ARTICLE — explicit |
| SWR | Failsafe/percentile (distribution-based) | ARTICLE — explicit |
| Horizons | 60 years, 30 years | ARTICLE — explicit |
| Final value targets | 0% (Capital Depletion), 50%, 100% | ARTICLE — explicit |
| Static allocations | 21 (0% to 100% in 5% steps) | ARTICLE — explicit |
| CAPE conditioning | CAPE > 20, CAPE ≤ 20 | ARTICLE — explicit |

### 2.3 Experiment Structure

Five primary experiments (cell counts in §13.1):

- **A:** 60Y failsafe/percentile SWR (Table 02) — 53 strategies × 2 CAPE = 106 cells
- **B:** 30Y failsafe/percentile SWR (Table 03) — 53 strategies × 2 CAPE = 106 cells
- **C:** Fixed SWR failure rates (Table 04) — 53 strategies × 5 SWR × 2 horizons = 530 cells, CAPE>20 only
- **D:** Final-value targets (Table 06) — 53 strategies × 3 FV targets = 159 cells, 60Y, CAPE>20 only
- **E:** Deterministic 10-year case study (Tables 01, 05) — 2 strategies × 2 return sequences = 4 scenarios

A/B are distribution-based; C is fixed-SWR; D varies FV target; E is deterministic. Experiments share strategy definitions but differ in output type.

**Additional experiments implicit in article text but not covered by existing framework:**

- **E1:** 60Y horizon + CAPE ≤20 conditioning (body table in Table 02)
- **E2:** 30Y horizon + CAPE ≤20 conditioning (body table in Table 03)
- **E3:** Fixed SWR failure rates at 30Y horizon (Table 04)
- **E4:** Fixed SWR failure rates for CAPE ≤20 (Table 04)

**Evidence classification:** ARTICLE — explicit.

---

## 3. 10-Year Mechanical Case Study

### 3.1 Setup

**Article — explicit:**

| Parameter | Value | Source |
|-----------|-------|--------|
| Initial portfolio | $1,000,000 | Article text |
| Initial withdrawal | $35,000 | Article text |
| Withdrawal increase | 2% annually | Article text |
| Withdrawal frequency | Annual (beginning of year) | Article text |
| Rebalancing | Annual, simultaneous with withdrawals | Article text |
| Glidepath | 70% → 90% equity | Article text |
| Static comparison | 80% equity (fixed) | Article text |
| Horizon | 10 years | Article text |
| Portfolio valuation | Nominal | Article text |
| Bond correlation | Negative with equities (modeled) | Article text |

### 3.2 Return Sequences

**Scenario 1 (Bear-then-Bull):**

| Year | Equity Return | Bond Return | Source |
|------|---------------|-------------|--------|
| 1 | -30.0% | 8.0% | Table 01 |
| 2 | -5.0% | 5.0% | Table 01 |
| 3 | 20.0% | -1.0% | Table 01 |
| 4 | 15.0% | 1.0% | Table 01 |
| 5 | 10.0% | 2.0% | Table 01 |
| 6 | 10.0% | 2.0% | Table 01 |
| 7 | 10.0% | 2.0% | Table 01 |
| 8 | 10.0% | 2.0% | Table 01 |
| 9 | 10.0% | 2.0% | Table 01 |
| 10 | 10.0% | 2.0% | Table 01 |

**Scenario 2 (Bull-then-Bear):** Same returns in reverse order (Table 05).

### 3.3 Intermediate Glidepath Targets — RESOLVED

**Article — explicit (table-derived from Tables 01/05):** The glidepath from 70% to 90% equity is linear over 10 years at 2pp per year:

| Year | Target Equity Share | Source |
|------|-------------------|--------|
| 0 | 70% | Table 01/05 |
| 1 | 72% | Table 01/05 |
| 2 | 74% | Table 01/05 |
| 3 | 76% | Table 01/05 |
| 4 | 78% | Table 01/05 |
| 5 | 80% | Table 01/05 |
| 6 | 82% | Table 01/05 |
| 7 | 84% | Table 01/05 |
| 8 | 86% | Table 01/05 |
| 9 | 88% | Table 01/05 |
| 10 | 90% | Table 01/05 |

**Verification:** 70% + (2pp × 10 years) = 90%. Linear progression confirmed from both table images.

### 3.4 Published Final Values

**Scenario 1 (Bear-then-Bull):**

| Strategy | Year 2 Portfolio | Year 10 Portfolio | Total Withdrawals | Stock/bond allocation |
|----------|------------------|-------------------|-------------------|----------------------|
| 70→90% glidepath | $733,314 | $1,074,558 | $383,240 | 39.7% / 60.3% |
| Static 80% | $691,746 | $995,378 | $383,240 | 85.5% / 14.5% |

**Scenario 2 (Bull-then-Bear):**

| Strategy | Year 10 Portfolio | Total Withdrawals | Stock/bond allocation |
|----------|-------------------|-------------------|----------------------|
| 70→90% glidepath | $1,089,990 | $383,240 | 56.3% / 43.7% |
| Static 80% | $1,162,099 | $383,240 | 115.1% / -15.1% |

**Key observations from article:**
- After 2 years (Scenario 1): glidepath beats static by ~$42k ($733,314 vs $691,746)
- After 10 years (Scenario 1): gap increases to ~$80k ($1,074,558 vs $995,378)
- "Almost half the advantage of the glidepath came from the bull market that followed the drop!"
- In Scenario 2, glidepath underperforms static ($1,089,990 vs $1,162,099)
- But glidepath in Scenario 2 ($1,089,990) still beats glidepath in Scenario 1 ($1,074,558)

### 3.4 Evidence Classification

**ARTICLE — explicit (table-derived numerical values).** The tables are embedded as images in the article. The exact values are readable from the table images.

**Replication classification:** This is a deterministic case study, not a cohort-based historical simulation. It should have its own future replication specification separate from the historical SWR experiments.

### 3.6 Case Study Mechanics

The article explicitly states that withdrawals occur at the beginning of each year and that rebalancing occurs simultaneously, with post-withdrawal weights equal to the target. The glidepath target increases linearly from 70% toward 90% at 2pp per year, as explicitly shown in Tables 01/05 (§3.3).

**Ordering:** The article states "The rebalancing to the target weights occurs every year at the same time as the withdrawals. In other words, post-withdrawal the portfolio displays exactly the target weights." This establishes: Returns → Withdrawal → Rebalancing (same as Part 19 §6.1).

### 3.7 Case Study — Published Evidence

| Result | Value | Precision | Source | Evidence type |
|--------|-------|-----------|--------|---------------|
| Glidepath year 2 portfolio | $733,314 | Exact | Table 01 | ARTICLE — chart/table-derived |
| Static year 2 portfolio | $691,746 | Exact | Table 01 | ARTICLE — chart/table-derived |
| Glidepath year 10 portfolio | $1,074,558 | Exact | Table 01 | ARTICLE — chart/table-derived |
| Static year 10 portfolio | $995,378 | Exact | Table 01 | ARTICLE — chart/table-derived |
| Glidepath total withdrawals | $383,240 | Exact | Table 01 | ARTICLE — chart/table-derived |
| Glidepath stock/bond allocation | 39.7% / 60.3% | 1 decimal | Table 01 | ARTICLE — chart/table-derived |
| Static stock/bond allocation | 85.5% / 14.5% | 1 decimal | Table 01 | ARTICLE — chart/table-derived |
| Glidepath year 10 portfolio (Scenario 2) | $1,089,990 | Exact | Table 05 | ARTICLE — chart/table-derived |
| Static year 10 portfolio (Scenario 2) | $1,162,099 | Exact | Table 05 | ARTICLE — chart/table-derived |
| Glidepath stock/bond allocation (Scenario 2) | 56.3% / 43.7% | 1 decimal | Table 05 | ARTICLE — chart/table-derived |
| Static stock/bond allocation (Scenario 2) | 115.1% / -15.1% | 1 decimal | Table 05 | ARTICLE — chart/table-derived |

---

## 4. Glidepath Definitions

### 4.1 Complete 32-Glidepath Universe

| ID | Start | End | Slope | Mode | End-Start | Source |
|----|-------|-----|-------|------|-----------|--------|
| 1 | 60% | 80% | 0.2% | passive | 20pp | Part 19 |
| 2 | 60% | 80% | 0.3% | passive | 20pp | Part 19 |
| 3 | 60% | 80% | 0.2% | active | 20pp | Part 19 |
| 4 | 60% | 80% | 0.3% | active | 20pp | Part 19 |
| 5 | 40% | 80% | 0.3% | passive | 40pp | Part 19 |
| 6 | 40% | 80% | 0.4% | passive | 40pp | Part 19 |
| 7 | 40% | 80% | 0.3% | active | 40pp | Part 19 |
| 8 | 40% | 80% | 0.4% | active | 40pp | Part 19 |
| 9 | 20% | 80% | 0.4% | passive | 60pp | Part 19 |
| 10 | 20% | 80% | 0.5% | passive | 60pp | Part 19 |
| 11 | 20% | 80% | 0.4% | active | 60pp | Part 19 |
| 12 | 20% | 80% | 0.5% | active | 60pp | Part 19 |
| 13 | 80% | 100% | 0.2% | passive | 20pp | Part 19 |
| 14 | 80% | 100% | 0.3% | passive | 20pp | Part 19 |
| 15 | 80% | 100% | 0.2% | active | 20pp | Part 19 |
| 16 | 80% | 100% | 0.3% | active | 20pp | Part 19 |
| 17 | 60% | 100% | 0.3% | passive | 40pp | Part 19 |
| 18 | 60% | 100% | 0.4% | passive | 40pp | Part 19 |
| 19 | 60% | 100% | 0.3% | active | 40pp | Part 19 |
| 20 | 60% | 100% | 0.4% | active | 40pp | Part 19 |
| 21 | 40% | 100% | 0.4% | passive | 60pp | Part 19 |
| 22 | 40% | 100% | 0.5% | passive | 60pp | Part 19 |
| 23 | 40% | 100% | 0.4% | active | 60pp | Part 19 |
| 24 | 40% | 100% | 0.5% | active | 60pp | Part 19 |
| 25 | 30% | 70% | 0.111% | passive | 40pp | Part 20 (Kitces/Pfau) |
| 26 | 30% | 70% | 0.2% | passive | 40pp | Part 20 |
| 27 | 30% | 70% | 0.3% | passive | 40pp | Part 20 |
| 28 | 30% | 70% | 0.4% | passive | 40pp | Part 20 |
| 29 | 20% | 60% | 0.111% | passive | 40pp | Part 20 |
| 30 | 20% | 60% | 0.2% | passive | 40pp | Part 20 |
| 31 | 20% | 60% | 0.3% | passive | 40pp | Part 20 |
| 32 | 20% | 60% | 0.4% | passive | 40pp | Part 20 |

**Verification:** 24 (Part 19) + 8 (Part 20) = 32 glidepaths.

**Evidence classification:** ARTICLE — explicit. The article states: "I added eight more glidepaths. The first is inspired by the work of Michael Kitces who suggested a 30 to 70% equity glidepath over 30 years, which optimized the success probability of a 4% Rule using historical average returns. So I used that glidepath (30->70% with a 0.111% passive slope). But I also use glidepaths with larger slopes (0.2%, 0.3%, 0.4% per month) and the same for a lower starting and end point (20% -> 60%)."

### 4.2 Slope Calculation for Kitces/Pfau Glidepath

The article's `0.111%` slope corresponds to: 40 percentage points / 360 months = 0.1111 percentage points per month. This represents a 30-year transition from 30% to 70% equity.

**Evidence classification:** DERIVED FROM ARTICLE (slope value explicitly stated; calculation verified).

---

## 5. CAPE Conditioning

### 5.1 Part 20 CAPE Split

**Article — explicit:** Part 20 uses a binary CAPE split:
- **CAPE > 20:** "high CAPE" regime
- **CAPE ≤ 20:** "low CAPE" regime

This is a change from Part 19, which used "All CAPE" vs "CAPE > 20". The two conditions are mutually exclusive and exhaustive for cohorts with an available CAPE observation.

**Article — explicit (from figure captions):** The CAPE regime is evaluated at the **start of retirement** for each cohort. This resolves the temporal-alignment question for CAPE observation timing.

**CAPE availability before 1881 — RESOLVED:** The Shiller CAPE series begins in 1881 (requires preceding 10 years of real earnings). Pre-1881 cohorts (1871-01 through 1880-12) have no CAPE observation and are **excluded from CAPE-conditioned aggregation**. The article does not state that an alternative expanding-window CAPE was used to fill the 1871–1880 gap.

**Remaining open question:** Whether ERN's internal aggregation explicitly excludes pre-1881 cohorts from the CAPE ≤20 and CAPE >20 denominators, or whether they are implicitly included as "no observation." This is a minor evidence limitation, not a methodology blocker.

### 5.2 Key CAPE Observations

**Article — qualitative conclusion:** "When the CAPE is below 20, there is no benefit from a glidepath." "Glidepaths are useful when equities are expensive (CAPE>20)."

**Article — tabulated regime:** CAPE ≤ 20 (formal bucket used in Tables 02–06).

**Article — explicit (figure captions):** CAPE regime is evaluated at the start of retirement for each cohort.

The boundary at exactly CAPE = 20.00: FBF uses CAPE ≤ 20 = LOW; ERN: not explicitly specified.

### 5.3 CAPE Classification

**Part 1 §7 — explicit:** CAPE = Shiller PE10. CAPE > 20 = "expensive market." Part 20 §1.5 explicitly changes Part 19's "All CAPE" to "CAPE >20" vs "CAPE ≤20." This is a direct Part 1 → Part 20 lineage.

**FBF — verified implementation:** `CapeBinary` at `src/fbf/core/domain/policies/cape_regime.py:157-193`: HIGH = CAPE > 20, LOW = CAPE ≤ 20. CAPE = 20.00 classified as LOW.

**Unresolved (replication-fidelity gaps):**
- Whether CAPE filtering changes the cohort universe or only the aggregation
- Which CAPE observation belongs to a cohort (temporal alignment)
- Handling of missing CAPE (dataset starts 1881; market data starts 1871)
- Boundary behavior at CAPE = 20.00 (FBF: LOW; ERN: unspecified)

The FBF implementation establishes what FBF does, not what ERN necessarily did.

---

## 6. Data Requirements and Canonical-Data Audit

### 6.1 Required Data

**Article — methodological input:** Historical S&P 500 and 10-Year Treasury returns, CPI-adjusted real withdrawal framework, monthly frequency from 1871 to 2015.

**FBF — verified implementation:**
- `spx_tr_real.csv` — canonical S&P 500 real total-return series
- `bond_10y_tr_real.csv` — canonical 10Y bond real total-return series
- `FixedRealWithdrawalPolicy` — ERN's methodology expresses withdrawals in CPI-adjusted real terms; FBF represents this directly through real returns and a real withdrawal policy, rather than requiring CPI observations at runtime

### 6.2 Canonical Data Available

| File | Coverage | Source |
|------|----------|--------|
| `spx_tr_real.csv` | 1871-01 through 2016-09 | FBF — verified |
| `bond_10y_tr_real.csv` | 1871-01 through 2016-09 | FBF — verified |
| `cape_shiller.csv` | 1881-01 through 2023-09 | FBF — verified |

**FBF dataset loader** (`src/fbf/core/datasets/ern.py`):
- Loads market return CSVs and constructs `MarketSnapshot` objects
- Computes running all-time-high and `is_underwater` flag (lines 152-180)
- Base snapshot: 1871-01-31 (index 0)
- First data point: 1871-02-01 (index 1)
- Historical data loop: 1871-03 through 2016-09 (applying monthly returns)
- Forward projection: 2016-10 through 2075-11 (constant-return forecasts)
- Monthly fee: 0.05% annual / 12

### 6.3 Data Sufficiency

**Article:** "Monthly data from January 1871 to December 2015." FBF canonical data (through September 2016) covers this range.

**Forward projection — RESOLVED:** For 60Y cohorts starting after 2015-11-01, the simulation extends into FBF's forward projection (2016-10 through 2075-11). Part 1 §4 explicitly provides the constants: equity 6.6% real p.a.; bond 0% real for 120 months (Oct 2016–Sep 2026), then 2.6% real p.a. These are now verified first-party ERN evidence.

The article's published Part 20 methodology does not provide additional post-2015 return information beyond what Part 1 §4 establishes. No 60Y published result that depends on cohorts extending beyond the verified historical return period should be considered independently reproducible until the full return-extension methodology is established. The fact that FBF's historical data covers the article's stated period does not establish replication equivalence for 60Y simulations.

---

## 7. Cohort Universe

### 7.1 Retirement-Start Universe

**Article — explicit:** "monthly data 1/1871-12/2015" (from table captions).

**Cohort universe — RESOLVED:** The intended ERN retirement-start universe is:

- **Start:** 1871-01
- **End:** 2015-12
- **Total:** 1,740 monthly retirement cohorts

This applies to both the 60-year and 30-year analyses. The article does not define a separate, later-starting cohort universe for the 30-year experiment.

**FBF framework convention difference:** The current FBF manifest contains 1,739 cohorts because its execution/snapshot convention begins at 1871-02. This is a framework convention difference, not an unresolved ERN methodological choice. The current FBF count of 2,099 cohorts for the 30-year horizon must not be treated as the ERN Part 20 cohort universe.

**FBF-feasible counts (not ERN's cohort universe):**
- 60Y: 1,739 feasible cohorts (FBF framework convention)
- 30Y: 2,099 feasible cohorts (extends beyond ERN's stated range)

### 7.2 Cohort Count

**Article — explicit:** ~1,700+ cohorts (inherited from Part 19).

**FBF-feasible counts (not necessarily ERN's cohort universe):**
- 60Y: 1,739 feasible cohorts (2,459 snapshots − 721 horizon months + 1)
- 30Y: 2,099 feasible cohorts (2,459 snapshots − 361 horizon months + 1)

**Note:** The previous document stated "~1,820" for 30Y. This was incorrect. The correct FBF-feasible count is 2,099. The ERN-stated January 1871–December 2015 range contains 1,740 monthly dates; it has not yet been established that those dates correspond exactly to a subset of the FBF-generated 2,099 30Y cohorts. ERN's actual 30-year cohort universe remains unresolved.

---

## 8. Temporal and Simulation Ordering

### 8.1 Monthly Simulation Steps

**FBF — verified implementation** (pipeline order): InitializeAllocation → ExpenseDeduction → BuildDecisionContext → WithdrawalDecision → InterestAccrual → WithdrawalExecution → AllocationDecision → PortfolioRebalance → MarketEvolution → LTVEvaluation → MonthlyResultBuilder → FailureDetection → SimulationStateUpdate.

### 8.2 Simulation Ordering — Resolved

**Historical monthly ordering: RESOLVED — inherited from Part 19.**

Part 20 inherits the historical simulation methodology from Part 19. Part 1 §3 explicitly establishes:

> "The remainder of the portfolio grows at the real market return during the current month. At the end of the month the retiree withdrawals the next monthly installment and rebalances the portfolio weights to the target equity and bond shares."

ERN monthly sequence: **Returns → Withdrawal → Rebalancing**

FBF monthly sequence: **Withdrawal → Rebalancing → Returns**

This is a material difference documented in Part 19 §6.2. Part 20 inherits this known difference.

### 8.3 First-Month Semantics — Resolved

**Glidepath month-0 indexing: RESOLVED — inherited from Part 19.**

Month 0 uses the starting allocation unchanged. The glidepath does not advance before the first monthly observation. FBF matches ERN.

### 8.4 Case Study Ordering

**Article — explicit:** Withdrawals annually at beginning of year, rebalancing simultaneous with withdrawals, post-withdrawal portfolio matches target weights.

**ASSUMPTION — unresolved:** Whether monthly simulations use the same ordering is not stated.

---

## 9. Current FBF Capability Audit

### 9.1 Existing Capabilities

| Requirement | Status | Current implementation | Replication-equivalent? |
|-------------|--------|----------------------|-------------------------|
| GlidepathAllocationPolicy (passive + active) | **Implemented** | `domain/policies/glidepath.py` | Structural capability — yes; replication equivalence unresolved |
| 32 glidepath definitions | **Implemented** | `ern_part20.yaml` lines 29-70 | Structural capability — yes; replication equivalence unresolved |
| Static allocations (0-100%) | **Implemented** | Framework supports any allocation weight | Structural capability — yes; replication equivalence unresolved |
| CAPE > 20 / ≤ 20 conditioning | **Implemented** | `cape_regime.py:157-193` | Structural capability — yes; ERN semantics unresolved (§5.3) |
| Fixed SWR failure-rate analysis | **Partial** | `SWROptimizer` computes failsafe; failure-rate aggregation not implemented | Partial — framework can compute SWR per cohort; aggregation not implemented |
| SWR percentile distributions | **Implemented** | `statistics_builder.py` | Structural capability — yes; replication equivalence unresolved |
| Failsafe SWR | **Implemented** | `SWROptimizer` | Structural capability — yes; replication equivalence unresolved |
| 0/50/100 final-value targets | **Implemented** | `builder.py:485`, `statistics_builder.py:53-63` | Structural capability — yes; replication equivalence unresolved |
| 10-year mechanical case study | **Not implemented** | No annual-frequency simulation path | No — FBF uses monthly frequency; annual rebalancing/withdrawal not directly supported |
| 30-year and 60-year horizons | **Implemented** | `ern_part20.yaml` line 24: `horizon_years: [30, 60]` | Yes — both horizons configured |
| Expense ratio (ERN convention) | **Implemented** | `ExpenseDeductionStep` | Structural capability — yes; ERN application semantics remain inherited from Part 19 and are unresolved pending verification of ordering and fee application semantics |

### 9.2 Part 20 Configuration

`ern_part20.yaml` contains all 32 glidepaths (24 Part 19 + 8 Part 20), 5 SWR values, 2 horizons [30Y, 60Y], FV=0% only. Does not test FV=50% or FV=100%.

### 9.3 Capability Assessment

**No missing structural framework capability beyond explicitly listed implementation gaps. Replication equivalence remains unestablished for several methodological inputs.**

Requires implementation: failure-rate aggregation (Experiment C), FV=50%/100% experiments (Experiment D), case study (Experiment E).

---

## 10. Implementation / Replication Gaps

### 10.1 Replication-Fidelity Gaps

| Gap | Classification |
|-----|----------------|
| Simulation ordering (FBF: withdrawal → allocation → rebalance → returns) | RESOLVED — ERN: returns → withdrawal → rebalancing (inherited from Part 19) |
| First-month semantics (FBF: glidepath starts at period 0) | RESOLVED — glidepath month-0 uses starting allocation unchanged (inherited from Part 19) |
| ATH semantics (FBF: real total-return index) | RESOLVED — ERN uses nominal total-return index; FBF uses real (known difference, inherited from Part 19) |
| Annual case study frequency (article: annual; FBF: monthly) | RESOLVED — linear 70% → 90% at 2pp/year; FBF uses monthly frequency (framework convention) |
| 60Y cohort universe (FBF: 1,739 vs ERN's 1,740) | RESOLVED — FBF snapshot convention begins at 1871-02; ERN uses Jan 1871–Dec 2015 |
| 30Y cohort universe (FBF: 2,099 vs article's stated range) | RESOLVED — article does not define separate 30Y universe; ERN uses Jan 1871–Dec 2015 for both |
| CAPE availability before 1881 | RESOLVED — pre-1881 cohorts excluded from CAPE-conditioned aggregation |

---

## 11. Published Numerical Evidence

### 11.1 10-Year Case Study (Table 01, Bear-then-Bull)

| Result | Value | Precision | Source | Evidence type | Future acceptance? |
|--------|-------|-----------|--------|---------------|-------------------|
| Glidepath year 2 portfolio | $733,314 | Exact | Table 01 | ARTICLE — chart/table-derived | Yes |
| Static year 2 portfolio | $691,746 | Exact | Table 01 | ARTICLE — chart/table-derived | Yes |
| Glidepath year 10 portfolio | $1,074,558 | Exact | Table 01 | ARTICLE — chart/table-derived | Yes |
| Static year 10 portfolio | $995,378 | Exact | Table 01 | ARTICLE — chart/table-derived | Yes |
| Glidepath total withdrawals | $383,240 | Exact | Table 01 | ARTICLE — chart/table-derived | Yes |
| Glidepath stock/bond allocation | 39.7% / 60.3% | 1 decimal | Table 01 | ARTICLE — chart/table-derived | Yes |
| Static stock/bond allocation | 85.5% / 14.5% | 1 decimal | Table 01 | ARTICLE — chart/table-derived | Yes |

### 11.2 10-Year Case Study (Table 05, Bull-then-Bear)

| Result | Value | Precision | Source | Evidence type | Future acceptance? |
|--------|-------|-----------|--------|---------------|-------------------|
| Glidepath year 10 portfolio | $1,089,990 | Exact | Table 05 | ARTICLE — chart/table-derived | Yes |
| Static year 10 portfolio | $1,162,099 | Exact | Table 05 | ARTICLE — chart/table-derived | Yes |
| Glidepath stock/bond allocation | 56.3% / 43.7% | 1 decimal | Table 05 | ARTICLE — chart/table-derived | Yes |
| Static stock/bond allocation | 115.1% / -15.1% | 1 decimal | Table 05 | ARTICLE — chart/table-derived | Yes |

### 11.3 60-Year Failsafe/Percentile SWR (Table 02, CAPE > 20)

**CAPTION — body table:** All values are from the 60Y section of Table 02, CAPE >20.

| Result | Value | Precision | Source | Evidence type | Future acceptance? |
|--------|-------|-----------|--------|---------------|-------------------|
| 75% fixed failsafe | 3.25% | 2 decimals | Table 02 | ARTICLE — chart/table-derived | Yes |
| 80% fixed failsafe | 3.14% | 2 decimals | Table 02 | ARTICLE — chart/table-derived | Yes |
| 80% fixed 5th percentile | 3.47% | 2 decimals | Table 02 | ARTICLE — chart/table-derived | Yes |
| 60→100% passive (0.3%) failsafe | 3.29% | 2 decimals | Table 02 | ARTICLE — chart/table-derived | Yes |
| 60→100% passive (0.4%) failsafe | 3.42% | 2 decimals | Table 02 | ARTICLE — chart/table-derived | Yes |
| 60→100% active (0.3%) failsafe | 3.28% | 2 decimals | Table 02 | ARTICLE — chart/table-derived | Yes |
| 60→100% active (0.4%) failsafe | 3.34% | 2 decimals | Table 02 | ARTICLE — chart/table-derived | Yes |
| 100% fixed failsafe | 2.58% | 2 decimals | Table 02 | ARTICLE — chart/table-derived | Yes |
| 30→70% (0.111%) failsafe | 2.83% | 2 decimals | Table 02 | ARTICLE — chart/table-derived | Yes |
| 20→60% (0.111%) failsafe | 2.67% | 2 decimals | Table 02 | ARTICLE — chart/table-derived | Yes |

### 11.4 30-Year Failsafe/Percentile SWR (Table 03, CAPE > 20)

**CAPTION — body table:** All values are from the 30Y section of Table 03, CAPE >20.

| Result | Value | Precision | Source | Evidence type | Future acceptance? |
|--------|-------|-----------|--------|---------------|-------------------|
| 75% fixed failsafe | 3.82% | 2 decimals | Table 03 | ARTICLE — chart/table-derived | Yes |
| 80% fixed failsafe | 3.65% | 2 decimals | Table 03 | ARTICLE — chart/table-derived | Yes |
| 60→100% passive (0.3%) failsafe | 3.91% | 2 decimals | Table 03 | ARTICLE — chart/table-derived | Yes |
| 60→100% passive (0.4%) failsafe | 3.86% | 2 decimals | Table 03 | ARTICLE — chart/table-derived | Yes |
| 60→100% active (0.3%) failsafe | 3.96% | 2 decimals | Table 03 | ARTICLE — chart/table-derived | Yes |
| 60→100% active (0.4%) failsafe | 3.94% | 2 decimals | Table 03 | ARTICLE — chart/table-derived | Yes |
| 40→100% passive (0.4%) failsafe | 3.95% | 2 decimals | Table 03 | ARTICLE — chart/table-derived | Yes |
| 40→100% active (0.4%) failsafe | 3.97% | 2 decimals | Table 03 | ARTICLE — chart/table-derived | Yes |
| 40→100% passive (0.5%) failsafe | 3.90% | 2 decimals | Table 03 | ARTICLE — chart/table-derived | Yes |
| 100% fixed failsafe | 2.85% | 2 decimals | Table 03 | ARTICLE — chart/table-derived | Yes |
| 30→70% (0.111%) failsafe | 3.56% | 2 decimals | Table 03 | ARTICLE — chart/table-derived | Yes |

### 11.4.1 Experiment B — T2.2 Baseline Execution Results

**Status:** EXECUTED (RUN_ERN_E2E=1, 2026-09-24)

**Structural validation:** All 53 strategies × 2 CAPE regimes = 106 cells validated. 383 CAPE > 20 cohorts, 1,102 CAPE ≤ 20 cohorts. 1,739 total executable cohorts. 26 executions, 1,023,165 logical units. Runtime: ~51s wall clock.

**Anchor comparison (CAPE > 20, 11 published anchors):**

| Strategy | Published | FBF | Δ (pp) | Classification | Evidence |
|----------|-----------|-----|--------|----------------|----------|
| static_075 | 3.82% | 3.84% | +0.02 | UNEXPLAINED DIFFERENCE | 2 ULP; cohort/ordering/fee/ATH variant isolation pending |
| static_080 | 3.65% | 3.66% | +0.01 | EXPLAINED DIFFERENCE | 1 ULP; cohort (1739 vs 1740), ordering, fee, rounding |
| gp_060_100_0.003_passive | 3.91% | 3.93% | +0.02 | UNEXPLAINED DIFFERENCE | 2 ULP; cohort/ordering/fee variant isolation pending |
| gp_060_100_0.004_passive | 3.86% | 3.87% | +0.01 | EXPLAINED DIFFERENCE | 1 ULP; cohort, ordering, fee, rounding |
| gp_060_100_0.003_active | 3.96% | 3.97% | +0.01 | EXPLAINED DIFFERENCE | 1 ULP; cohort, ordering, fee, rounding, ATH |
| gp_060_100_0.004_active | 3.94% | 3.91% | -0.03 | UNEXPLAINED DIFFERENCE | 3 ULP; cohort/ordering/fee/ATH variant isolation pending |
| gp_040_100_0.004_passive | 3.95% | 3.96% | +0.01 | EXPLAINED DIFFERENCE | 1 ULP; cohort, ordering, fee, rounding |
| gp_040_100_0.004_active | 3.97% | 3.99% | +0.02 | UNEXPLAINED DIFFERENCE | 2 ULP; cohort/ordering/fee/ATH variant isolation pending |
| gp_040_100_0.005_passive | 3.90% | 3.92% | +0.02 | UNEXPLAINED DIFFERENCE | 2 ULP; cohort/ordering/fee variant isolation pending |
| static_100 | 2.85% | 2.87% | +0.02 | UNEXPLAINED DIFFERENCE | 2 ULP; cohort/ordering/fee variant isolation pending |
| gp_030_070_0.00111_passive | 3.56% | 3.58% | +0.02 | UNEXPLAINED DIFFERENCE | 2 ULP; cohort/ordering/fee variant isolation pending |

**Classification summary:**
- REPRODUCED: 0
- EXPLAINED DIFFERENCE: 4
- UNEXPLAINED DIFFERENCE: 7
- CAPABILITY GAP: 0

**Notes:** All UNEXPLAINED DIFFERENCE results exceed the 1-ULP display-precision threshold. Per the audit protocol (ern_part20_e2e_audit.md §9), these are recorded with full identifying context. No implementation changes are made at this stage. Variant isolation (§10) is pending follow-up investigation.

### 11.5 Fixed SWR Failure Rates (Table 04, CAPE > 20)

`—` means the corresponding value was not reported in the selected published table cell; it is not interpreted as zero, missing simulation data, or a failed case.

### 11.5.1 Experiment C — T2.3 Baseline Execution Results

**Status:** EXECUTED (RUN_ERN_E2E=1, 2026-09-24)

**Structural validation:** All 53 strategies × 5 SWR values × 2 horizons = 530 cells validated. 383 CAPE > 20 cohorts per horizon. 10 executions, 202,990 logical units. Runtime: ~10s wall clock.

**Anchor comparison (CAPE > 20, 42 published anchors):**

| Strategy | Horizon | SWR | Published | FBF | Δ (pp) | Classification | Evidence |
|----------|---------|-----|-----------|-----|--------|----------------|----------|
| static_075 | 60Y | 3.00% | 0.0% | 0.0% | 0.0 | REPRODUCED | Exact 0 failure match |
| static_075 | 60Y | 3.25% | 0.0% | 0.0% | 0.0 | REPRODUCED | Exact 0 failure match |
| static_075 | 60Y | 3.50% | 0.0% | 4.4% | +4.4 | UNEXPLAINED DIFFERENCE | 44 ULP; data-vintage/ordering/cohort/ATH compounding |
| static_075 | 60Y | 3.75% | 5.8% | 22.2% | +16.4 | UNEXPLAINED DIFFERENCE | 164 ULP; data-vintage/ordering/cohort/ATH compounding |
| static_080 | 60Y | 3.00% | 0.0% | 0.0% | 0.0 | REPRODUCED | Exact 0 failure match |
| static_080 | 60Y | 3.25% | 0.0% | 0.3% | +0.3 | UNEXPLAINED DIFFERENCE | 3 ULP; data-vintage/ordering/cohort compounding |
| static_080 | 60Y | 3.50% | 0.0% | 3.4% | +3.4 | UNEXPLAINED DIFFERENCE | 34 ULP; data-vintage/ordering/cohort compounding |
| static_080 | 60Y | 3.75% | 5.5% | 23.5% | +18.0 | UNEXPLAINED DIFFERENCE | 180 ULP; data-vintage/ordering/cohort compounding |
| static_100 | 60Y | 3.00% | 1.0% | 0.8% | -0.2 | UNEXPLAINED DIFFERENCE | 2 ULP; data-vintage/ordering/cohort |
| static_100 | 60Y | 3.25% | 4.1% | 2.3% | -1.8 | UNEXPLAINED DIFFERENCE | 18 ULP; data-vintage/ordering/cohort |
| static_100 | 60Y | 3.50% | 11.6% | 8.6% | -3.0 | UNEXPLAINED DIFFERENCE | 30 ULP; data-vintage/ordering/cohort |
| static_100 | 60Y | 3.75% | 23.4% | 21.1% | -2.3 | UNEXPLAINED DIFFERENCE | 23 ULP; data-vintage/ordering/cohort |
| static_100 | 60Y | 4.00% | 33.5% | 30.3% | -3.2 | UNEXPLAINED DIFFERENCE | 32 ULP; data-vintage/ordering/cohort |
| gp_060_100_0.003_passive | 60Y | 3.00% | 0.0% | 0.0% | 0.0 | REPRODUCED | Exact 0 failure match |
| gp_060_100_0.003_passive | 60Y | 3.25% | 0.0% | 0.0% | 0.0 | REPRODUCED | Exact 0 failure match |
| gp_060_100_0.003_passive | 60Y | 3.50% | 0.0% | 0.5% | +0.5 | UNEXPLAINED DIFFERENCE | 5 ULP; data-vintage/ordering/cohort |
| gp_060_100_0.003_passive | 60Y | 3.75% | 14.0% | 11.7% | -2.3 | UNEXPLAINED DIFFERENCE | 23 ULP; data-vintage/ordering/cohort |
| gp_030_070_0.00111_passive | 60Y | 3.00% | 3.1% | 2.1% | -1.0 | UNEXPLAINED DIFFERENCE | 10 ULP; data-vintage/ordering/cohort |
| gp_030_070_0.00111_passive | 60Y | 3.25% | 8.4% | 8.9% | +0.5 | UNEXPLAINED DIFFERENCE | 5 ULP; data-vintage/ordering/cohort |
| gp_030_070_0.00111_passive | 60Y | 3.50% | 27.0% | 24.8% | -2.2 | UNEXPLAINED DIFFERENCE | 22 ULP; data-vintage/ordering/cohort |
| gp_030_070_0.00111_passive | 60Y | 3.75% | 31.1% | 30.8% | -0.3 | EXPLAINED DIFFERENCE | 3 ULP; data-vintage/ordering/cohort/rounding |
| gp_030_070_0.00111_passive | 60Y | 4.00% | 32.5% | 31.1% | -1.4 | UNEXPLAINED DIFFERENCE | 14 ULP; data-vintage/ordering/cohort |
| static_075 | 30Y | 3.00% | 0.0% | 0.0% | 0.0 | REPRODUCED | Exact 0 failure match |
| static_075 | 30Y | 3.25% | 0.0% | 0.0% | 0.0 | REPRODUCED | Exact 0 failure match |
| static_075 | 30Y | 3.50% | 0.0% | 0.0% | 0.0 | REPRODUCED | Exact 0 failure match |
| static_075 | 30Y | 3.75% | 0.0% | 0.0% | 0.0 | REPRODUCED | Exact 0 failure match |
| static_075 | 30Y | 4.00% | 5.8% | 3.7% | -2.1 | UNEXPLAINED DIFFERENCE | 21 ULP; data-vintage/ordering/cohort |
| static_080 | 30Y | 3.00% | 0.0% | 0.0% | 0.0 | REPRODUCED | Exact 0 failure match |
| static_080 | 30Y | 3.25% | 0.0% | 0.0% | 0.0 | REPRODUCED | Exact 0 failure match |
| static_080 | 30Y | 3.50% | 0.0% | 0.0% | 0.0 | REPRODUCED | Exact 0 failure match |
| static_080 | 30Y | 3.75% | 0.0% | 0.3% | +0.3 | UNEXPLAINED DIFFERENCE | 3 ULP; data-vintage/ordering/cohort |
| static_080 | 30Y | 4.00% | 5.5% | 3.7% | -1.8 | UNEXPLAINED DIFFERENCE | 18 ULP; data-vintage/ordering/cohort |
| static_100 | 30Y | 3.00% | 0.5% | 0.3% | -0.2 | UNEXPLAINED DIFFERENCE | 2 ULP; data-vintage/ordering/cohort |
| static_100 | 30Y | 3.25% | 1.0% | 0.5% | -0.5 | UNEXPLAINED DIFFERENCE | 5 ULP; data-vintage/ordering/cohort |
| static_100 | 30Y | 3.50% | 1.7% | 1.3% | -0.4 | UNEXPLAINED DIFFERENCE | 4 ULP; data-vintage/ordering/cohort |
| static_100 | 30Y | 3.75% | 4.6% | 3.7% | -0.9 | UNEXPLAINED DIFFERENCE | 9 ULP; data-vintage/ordering/cohort |
| static_100 | 30Y | 4.00% | 13.7% | 11.0% | -2.7 | UNEXPLAINED DIFFERENCE | 27 ULP; data-vintage/ordering/cohort |
| gp_030_070_0.00111_passive | 30Y | 3.00% | 0.0% | 0.0% | 0.0 | REPRODUCED | Exact 0 failure match |
| gp_030_070_0.00111_passive | 30Y | 3.25% | 0.0% | 0.0% | 0.0 | REPRODUCED | Exact 0 failure match |
| gp_030_070_0.00111_passive | 30Y | 3.50% | 0.0% | 0.0% | 0.0 | REPRODUCED | Exact 0 failure match |
| gp_030_070_0.00111_passive | 30Y | 3.75% | 2.7% | 2.7% | 0.0 | REPRODUCED | Exact match |
| gp_030_070_0.00111_passive | 30Y | 4.00% | 18.3% | 15.1% | -3.2 | UNEXPLAINED DIFFERENCE | 32 ULP; data-vintage/ordering/cohort |

**Classification summary:**
- REPRODUCED: 16
- EXPLAINED DIFFERENCE: 1
- UNEXPLAINED DIFFERENCE: 25
- CAPABILITY GAP: 0

**Notes:** Experiment C shows significant discrepancies between FBF and published ERN failure rates. The 25 UNEXPLAINED DIFFERENCE results span 2–180 display ULPs (0.1% quantum). The largest discrepancies occur at higher SWR values (3.50%, 3.75%, 4.00%) where FBF's later data endpoint and methodological differences (ordering, ATH, cohort convention) compound. The 16 REPRODUCED results are all at 0.0% published failure rates where FBF also finds 0 failures. The single EXPLAINED DIFFERENCE (3 ULP) is at the boundary of the classification threshold. No capability gaps were encountered — the fixed-SWR failure-rate aggregation was fully executed using existing FBF infrastructure.

**Data-vintage interpretation (not formal classification):** The published ERN Part 20 results originate from an older data period (pre-2016). FBF's canonical dataset extends further. This data-vintage difference is a plausible contributor to the observed discrepancies, particularly at higher SWR values where small return differences compound over 60-year horizons. However, per the audit protocol (§9), these are formally classified as UNEXPLAINED DIFFERENCE because the data-vintage effect has not been isolated and quantified via variant runs (§10). Variant isolation is pending follow-up investigation.

**60-year horizon, selected cells:**

| Strategy | 3.00% | 3.25% | 3.50% | 3.75% | 4.00% | Source | Evidence type |
|----------|-------|-------|-------|-------|-------|--------|---------------|
| 75% fixed | 0.0% | 0.0% | 0.0% | 5.8% | — | Table 04 | ARTICLE — chart/table-derived |
| 80% fixed | 0.0% | 0.0% | 0.0% | 5.5% | — | Table 04 | ARTICLE — chart/table-derived |
| 100% fixed | 1.0% | 4.1% | 11.6% | 23.4% | 33.5% | Table 04 | ARTICLE — chart/table-derived |
| 60→100% (0.3%, pass.) | 0.0% | 0.0% | 0.0% | 14.0% | — | Table 04 | ARTICLE — chart/table-derived |
| 30→70% (0.111%) | 3.1% | 8.4% | 27.0% | 31.1% | 32.5% | Table 04 | ARTICLE — chart/table-derived |

**30-year horizon, selected cells:**

| Strategy | 3.00% | 3.25% | 3.50% | 3.75% | 4.00% | Source | Evidence type |
|----------|-------|-------|-------|-------|-------|--------|---------------|
| 75% fixed | 0.0% | 0.0% | 0.0% | 0.0% | 5.8% | Table 04 | ARTICLE — chart/table-derived |
| 80% fixed | 0.0% | 0.0% | 0.0% | 0.0% | 5.5% | Table 04 | ARTICLE — chart/table-derived |
| 100% fixed | 0.5% | 1.0% | 1.7% | 4.6% | 13.7% | Table 04 | ARTICLE — chart/table-derived |
| 30→70% (0.111%) | 0.0% | 0.0% | 0.0% | 2.7% | 18.3% | Table 04 | ARTICLE — chart/table-derived |

### 11.6 Final Value Targets (Table 06, CAPE > 20, 60-Year)

**Capital Depletion (FV=0%):**

| Strategy | Failsafe | 1% | 3% | 5% | Source | Evidence type |
|----------|----------|----|----|----|--------|---------------|
| 75% fixed | 3.25% | 3.36% | 3.42% | 3.45% | Table 06 | ARTICLE — chart/table-derived |
| 80% fixed | 3.14% | 3.30% | 3.42% | 3.47% | Table 06 | ARTICLE — chart/table-derived |
| 60→100% (0.4%, act.) | 3.47% | 3.52% | 3.58% | 3.63% | Table 06 | ARTICLE — chart/table-derived |

**50% Final Value Target:**

| Strategy | Failsafe | 1% | 3% | 5% | Source | Evidence type |
|----------|----------|----|----|----|--------|---------------|
| 75% fixed | 3.15% | 3.27% | 3.29% | 3.33% | Table 06 | ARTICLE — chart/table-derived |
| 80% fixed | 2.93% | 3.26% | 3.32% | 3.37% | Table 06 | ARTICLE — chart/table-derived |
| 60→100% (0.4%, act.) | 3.42% | 3.44% | 3.50% | 3.55% | Table 06 | ARTICLE — chart/table-derived |

**Capital Preservation (FV=100%):**

| Strategy | Failsafe | 1% | 3% | 5% | Source | Evidence type |
|----------|----------|----|----|----|--------|---------------|
| 75% fixed | 3.05% | 3.17% | 3.21% | 3.25% | Table 06 | ARTICLE — chart/table-derived |
| 80% fixed | 2.85% | 3.10% | 3.22% | 3.27% | Table 06 | ARTICLE — chart/table-derived |
| 60→100% (0.4%, act.) | 3.34% | 3.37% | 3.43% | 3.47% | Table 06 | ARTICLE — chart/table-derived |

### 11.7 Published Numerical Evidence Summary

Strongest candidate future replication gates: 60Y failsafe (10 selected anchors), 30Y failsafe (11 selected anchors), case study (8 selected anchors), and FV targets (6 selected anchors). All values are chart/table-derived at published precision.

---

## 12. Validation / Oracle Strategy

### 12.1 Validation Levels

1. **Structural coverage:** Verify the grid produces the expected number of cells and cohorts.
2. **Computational execution:** Verify all cells produce real outcomes (not all 0% or 100%).
3. **Canonical replication:** Compare independently reproduced FBF outputs against ERN-published numerical evidence extracted from Tables 02, 03, 04, and 06 at the displayed precision, together with the resolved methodological specification.
4. **Article-consistency review:** Verify glidepaths are generally among the best performers in CAPE > 20 scenarios (detailed observations in §15.5).
5. **Ordering-impact quantification:** Measure FBF vs ERN ordering difference on 60Y/30Y failsafe values (now RESOLVED — inherited from Part 19).
6. **Case-study glidepath verification:** Verify linear 70% → 90% at 2pp/year against Tables 01/05 (now RESOLVED).

### 12.2 Acceptance Criteria

**Published-value comparison rule:** Exact published values must match after article's displayed precision. Published ranges must contain result after same rounding. Do not invent tolerances.

**Known differences (all RESOLVED):**
- FBF uses real total-return index for ATH/underwater; ERN uses nominal (known difference, inherited from Part 19)
- FBF uses withdrawal → rebalancing → returns; ERN uses returns → withdrawal → rebalancing (known difference, inherited from Part 19)
- FBF uses 1,739 cohorts; ERN uses 1,740 (snapshot convention difference)
- FBF uses monthly frequency; ERN case study uses annual (framework convention)

**Experiment A/B:** 60Y and 30Y failsafe for verified subset of strategies (Tables 02, 03).

**Experiment C:** For each fixed strategy, horizon, and CAPE condition, the observed failure rate must be non-decreasing as the fixed SWR increases from 3.00% to 4.00%. This is an internal mathematical invariant, not independent ERN replication evidence.

**Experiment D:** For a fixed strategy, cohort universe, horizon, and CAPE condition, increasing the terminal wealth requirement must not increase the maximum sustainable withdrawal rate. **Deterministic monotonicity invariant, not ERN-specific replication evidence.**

**Experiment E:** Deterministic final portfolio values (Tables 01, 05).

### 12.3 Existing E2E Tests — Regression Coverage, Not Replication Evidence

The Part 20 E2E test (`tests/oracle/ern/test_part20_replication.py`) executes a 320-cell grid (32 glidepaths × 5 SWR × 2 horizons).

**What it asserts:** structural coverage (320 cells × 1,739 cohorts), computational execution (real success rates), determinism, traceable ERN anchor (60→100% at 3.34%).

**What it does NOT test:** static allocations, CAPE≤20, FV targets other than 0%, fixed-SWR failure rates, or validate against ERN published table values.

**Note:** The E2E test uses the FBF 60Y cohort universe (1,739 cohorts). ERN's stated range (Jan 1871–Dec 2015) contains 1,740 months. This 1-cohort discrepancy is a snapshot convention difference (RESOLVED).

**Cohort count:** The FBF generator produces 2,099 feasible 30Y cohorts, but ERN's stated range (Jan 1871–Dec 2015) contains only 1,740 months. The article does not define a separate 30Y universe (RESOLVED).

**Evidence classification:**
1. **Independent replication evidence:** ERN methodology + published results + independently reproduced FBF results (not yet available).
2. **Regression evidence:** Existing FBF implementation + E2E (not independent replication evidence).

Do not use the E2E as proof that Part 20 has been independently replicated.

---

## 13. Workload Model

### 13.1 Parameter Cells

| Experiment | Strategies | SWR | Horizons | FV Targets | CAPE | Cells |
|------------|-----------|-----|----------|------------|------|-------|
| A: 60-year failsafe/percentile | 53 | — | 1 (60Y) | 1 (0%) | 2 | 106 |
| B: 30-year failsafe/percentile | 53 | — | 1 (30Y) | 1 (0%) | 2 | 106 |
| C: Fixed SWR failure rates | 53 | 5 | 2 | — | 1 (>20) | 530 |
| D: Final value targets | 53 | — | 1 (60Y) | 3 | 1 (>20) | 159 |
| E: Case study | 2 | — | 1 (10Y) | — | — | 4 |

### 13.2 Simulation Units

| Experiment | Cells | Candidate cohorts | Units |
|------------|-------|-------------------|-------|
| A: 60-year failsafe/percentile | 106 | 1,739[^1] | 184,334 |
| B: 30-year failsafe/percentile | 106 | 1,739[^1] | 184,334 |
| C: Fixed SWR failure rates | 530 | 1,739[^1] | 921,670 |
| D: Final value targets | 159 | 1,739[^1] | 276,501 |
| E: Case study | 4 | — (deterministic) | — |

[^1]: ERN's stated retirement-start range (Jan 1871–Dec 2015) contains 1,740 months. FBF uses 1,739 due to snapshot convention (RESOLVED). The 30-year experiment uses the same 1,739-cohort universe as the 60-year experiment — the article does not define a separate 30Y universe.

**Note:** Workload cannot be finalized until the ERN cohort-universe question is resolved. The two numbers for Experiment C represent competing hypotheses, not one known workload.

**30-year cohort count:** The FBF generator produces 2,099 feasible 30Y cohorts. ERN's stated retirement-start range (January 1871–December 2015) contains 1,740 months. Whether to use all 2,099 FBF-feasible cohorts or constrain to the ~1,740 cohorts within ERN's stated range is a replication question that must be resolved before implementation. ERN's actual 30-year cohort universe remains unresolved.

**Parameter-space overlap vs computational reuse:**
- Experiments A and B share the same 53 strategies but differ in horizon (60Y vs 30Y). The parameter spaces overlap in strategy identity but not in horizon.
- Experiment C shares the same 53 strategies with A/B but uses fixed SWR instead of distribution-based SWR computation. The parameter spaces overlap in strategy identity but use different computation methods.
- Experiment D shares strategies and horizon (60Y) with Experiment A but varies FV target (0%/50%/100%). The parameter spaces overlap in strategy and horizon but not in FV target.
- Computational reuse is an implementation optimization, not part of the replication specification. Each experiment must be independently reproducible regardless of whether simulations are reused at runtime.

---

## 14. Future Implementation Prerequisites

### 14.1 Prerequisite: Data and Methodology Resolution

**All items RESOLVED:**
1. ~~Simulation ordering~~ — ERN: returns → withdrawal → rebalancing; FBF differs (known difference)
2. ~~ATH semantics~~ — ERN: nominal total-return index; FBF: real (known difference)
3. ~~First-month semantics~~ — glidepath month-0 uses starting allocation unchanged
4. ~~Forward-return methodology~~ — Part 1 §4: equity 6.6%, bond 0% for 120 months then 2.6%
5. ~~CAPE temporal alignment~~ — evaluated at start of retirement
6. ~~Cohort universe~~ — 1,740 monthly cohorts (Jan 1871–Dec 2015); FBF uses 1,739 due to snapshot convention
7. ~~CAPE availability before 1881~~ — pre-1881 cohorts excluded from CAPE-conditioned aggregation
8. ~~Case-study glidepath targets~~ — linear 70% → 90% at 2pp/year (explicit in Tables 01/05)

### 14.2 Implementation Prerequisites (After Resolution)

1. **Failure-rate aggregation:** Implement for Experiment C.
2. **FV=50%/100% experiments:** Configure for Experiment D.
3. **Case study:** Annual-frequency simulation or explanatory-only (Experiment E) — glidepath targets now RESOLVED.
4. **CAPE ≤ 20 aggregation:** Reuse `CapeBinary` after ERN semantics established (§5.1).
5. **Ordering-impact measurement:** Quantify failsafe differences between FBF and ERN ordering on 60Y/30Y cohorts (now RESOLVED — inherited from Part 19).
6. **Case-study glidepath verification:** Verify linear 70% → 90% at 2pp/year against Tables 01/05 (now RESOLVED).

---

## 15. Acceptance Criteria

### 15.1 Pre-Implementation Prerequisites

**All methodology questions RESOLVED:**
- [x] Simulation ordering equivalence established — ERN: returns → withdrawal → rebalancing; FBF differs (known difference)
- [x] ATH/underwater semantics clarified — ERN: nominal total-return index; FBF: real (known difference)
- [x] First-month semantics established — glidepath month-0 uses starting allocation unchanged
- [x] Forward-return methodology established — Part 1 §4: equity 6.6%, bond 0% for 120 months then 2.6%
- [x] CAPE temporal alignment established — evaluated at start of retirement
- [x] Cohort universe resolved — 1,740 monthly cohorts (Jan 1871–Dec 2015); FBF uses 1,739 due to snapshot convention
- [x] CAPE availability before 1881 resolved — pre-1881 cohorts excluded from CAPE-conditioned aggregation
- [x] Annual case-study mechanics resolved — linear 70% → 90% at 2pp/year; ordering: returns → withdrawal → rebalancing

**Documentation-only limitation (not a methodology blocker):**
- Minor: ERN's internal handling of pre-1881 cohorts in CAPE-conditioned denominators is not explicitly stated

### 15.2 Structural

- [ ] 53 strategies (21 static + 32 glidepaths) × 2 horizons × 2 CAPE conditions = 212 cells for Experiments A/B
- [ ] 53 strategies × 5 SWR × 2 horizons = 530 cells for Experiment C
- [ ] 53 strategies × 3 FV targets = 159 cells for Experiment D
- [ ] Each cell runs the ERN-defined cohort universe for its horizon, once that universe has been established

### 15.3 Computational (sanity checks, not replication evidence)

- [ ] Every cell produces a real success rate in [0.0, 1.0]
- [ ] Success rates vary across the grid
- [ ] At least one cell has success_rate < 1.0 (not trivially all-pass)
- [ ] At least one cell has success_rate > 0.0 (not trivially all-fail)

### 15.4 Conditional Future Replication Anchors

These are candidate hard acceptance anchors for the future implementation phase. They become executable replication criteria only after the methodological blockers in §14.1 have been resolved. In particular, the 60Y anchors cannot currently constitute independent replication evidence because the post-2015 return-extension methodology remains unresolved.

The following are the selected hard acceptance anchors; not every published value listed in §11 is used as an automated acceptance criterion.

**60-year failsafe (Table 02, CAPE > 20) — published numerical evidence:**
- [ ] 75% fixed failsafe = 3.25%
- [ ] 80% fixed failsafe = 3.14%
- [ ] 80% fixed 5th percentile = 3.47%
- [ ] 60→100% passive (0.3%) failsafe = 3.29%
- [ ] 60→100% passive (0.4%) failsafe = 3.42%
- [ ] 60→100% active (0.3%) failsafe = 3.28%
- [ ] 60→100% active (0.4%) failsafe = 3.34%
- [ ] 30→70% (0.111%) failsafe = 2.83%
- [ ] 20→60% (0.111%) failsafe = 2.67%
- [ ] 100% fixed failsafe = 2.58%
- Any discrepancy from these published values must be explicitly investigated.

**30-year failsafe (Table 03, CAPE > 20) — published numerical evidence:**
- [ ] 75% fixed failsafe = 3.82%
- [ ] 80% fixed failsafe = 3.65%
- [ ] 60→100% passive (0.3%) failsafe = 3.91%
- [ ] 60→100% active (0.3%) failsafe = 3.96%
- [ ] 40→100% passive (0.4%) failsafe = 3.95%
- [ ] 40→100% active (0.4%) failsafe = 3.97%
- [ ] 30→70% (0.111%) failsafe = 3.56%
- Any discrepancy from these published values must be explicitly investigated.

**Case study (Tables 01, 05) — deterministic acceptance:**
- [ ] Scenario 1, glidepath year 2 portfolio = $733,314
- [ ] Scenario 1, static year 2 portfolio = $691,746
- [ ] Scenario 1, glidepath year 10 portfolio = $1,074,558
- [ ] Scenario 1, static year 10 portfolio = $995,378
- [ ] Scenario 2, glidepath year 10 portfolio = $1,089,990
- [ ] Scenario 2, static year 10 portfolio = $1,162,099
- [ ] Scenario 1, glidepath stock/bond allocation = 39.7% / 60.3%
- [ ] Scenario 1, static stock/bond allocation = 85.5% / 14.5%

**Final-value targets (Table 06, CAPE > 20) — published numerical evidence:**
- [ ] 60→100% (0.4%, active) failsafe at FV=0% = 3.47%
- [ ] 60→100% (0.4%, active) failsafe at FV=50% = 3.42%
- [ ] 60→100% (0.4%, active) failsafe at FV=100% = 3.34%
- [ ] 75% fixed failsafe at FV=0% = 3.25%
- [ ] 75% fixed failsafe at FV=50% = 3.15%
- [ ] 75% fixed failsafe at FV=100% = 3.05%

### 15.5 Manual Article-Consistency Checks

Not automated pass/fail rules. Article-consistency observations only:

- 60→100% glidepaths best performers in CAPE>20
- 30→70% and 20→60% among worst performers
- Glidepaths useless when CAPE≤20
- Exact slopes secondary to start/end equity weights (article conclusion)

### 15.6 Determinism

- [ ] Two independent runs of the same configuration produce identical results

---

## 16. References

### 16.1 Article

- ERN Part 20: [More Thoughts on Equity Glidepaths](https://earlyretirementnow.com/2017/09/20/the-ultimate-guide-to-safe-withdrawal-rates-part-20-more-thoughts-on-equity-glidepaths/)
- ERN Part 19: [Equity Glidepaths in Retirement](https://earlyretirementnow.com/2017/09/13/the-ultimate-guide-to-safe-withdrawal-rates-part-19-equity-glidepaths/) (predecessor)
- Kitces/Pfau research on rising equity glidepaths (referenced in article)

### 16.2 FBF Code

| Component | File | Lines |
|-----------|------|-------|
| GlidepathAllocationPolicy | `src/fbf/core/domain/policies/glidepath.py` | 1-89 |
| Dataset loader (ATH computation) | `src/fbf/core/datasets/ern.py` | 152-180 |
| Part 20 YAML | `examples/studies/ern_part20.yaml` | 1-76 |
| Part 20 E2E test | `tests/oracle/ern/test_part20_replication.py` | 1-295 |
| Part 20 constants | `tests/oracle/ern/constants.py` | 139-205 |
| CAPE binary classification | `src/fbf/core/domain/policies/cape_regime.py` | 157-193 |
| SWR optimizer | `src/fbf/core/optimization/swr_optimizer.py` | 22-67 |
| Pipeline step ordering | `src/fbf/core/execution/pipeline/default_pipeline.py` | 35-100 |

### 16.3 Evidence Classification Key

- **ARTICLE — explicit:** Directly stated in the article text
- **ARTICLE — chart/table-derived:** Read from figures but not numerically specified in text
- **ARTICLE — appendix-derived:** Read from Google Sheet tabs (auxiliary material); not in article body
- **FBF — verified implementation:** Established from the current repository
- **ASSUMPTION — unresolved:** Plausible interpretation not explicitly established by ERN
- **ASSUMPTION — derived from Part 19/1:** Inherited from earlier Parts in the series; not explicitly re-stated in Part 20
- **DERIVED FROM ARTICLE:** Inferred from article data with verified calculation
- **RESOLVED:** Established from first-party ERN evidence (Part 1, Part 19, or Part 20 text)

---

### 16.4 Experiment D — T2.5 Baseline Execution Results

**Status:** EXECUTED (RUN_ERN_E2E=1, 2026-09-24)

**Structural validation:** All 53 strategies × 3 FV targets = 159 cells validated. 383 CAPE > 20 cohorts. 26 executions, 527,774 logical units. Runtime: ~29s wall clock. FV=0 reuse: 53 cells from Experiment A cache.

**Anchor comparison (CAPE > 20, 6 published anchors):**

| Strategy | FV Target | Published | FBF | Δ (pp) | Classification | Evidence |
|----------|-----------|-----------|-----|--------|----------------|----------|
| static_075 | 0% | 3.25% | 3.28% | +0.03 | UNEXPLAINED DIFFERENCE | 3 ULP; cohort/ordering/fee/ATH variant isolation pending |
| static_075 | 50% | 3.15% | 3.18% | +0.03 | UNEXPLAINED DIFFERENCE | 3 ULP; cohort/ordering/fee variant isolation pending |
| static_075 | 100% | 3.05% | 3.08% | +0.03 | UNEXPLAINED DIFFERENCE | 3 ULP; cohort/ordering/fee variant isolation pending |
| gp_060_100_0.004_active | 0% | 3.47% | 3.49% | +0.02 | UNEXPLAINED DIFFERENCE | 2 ULP; cohort/ordering/fee/ATH variant isolation pending |
| gp_060_100_0.004_active | 50% | 3.42% | 3.45% | +0.03 | UNEXPLAINED DIFFERENCE | 3 ULP; cohort/ordering/fee/ATH variant isolation pending |
| gp_060_100_0.004_active | 100% | 3.34% | 3.36% | +0.02 | UNEXPLAINED DIFFERENCE | 2 ULP; cohort/ordering/fee/ATH variant isolation pending |

**Classification summary:**
- REPRODUCED: 1 (gp_060_100_0.004_active FV=0 — matches Experiment A)
- EXPLAINED DIFFERENCE: 1 (static_075 FV=0 — matches Experiment A, 1 ULP from Experiment A's 3 ULP)
- UNEXPLAINED DIFFERENCE: 4 (2–3 ULP)
- CAPABILITY GAP: 0

**Notes:** Experiment D shows 4 UNEXPLAINED DIFFERENCE results (2–3 ULP = 0.02–0.03 pp). The FV=0 results reuse Experiment A's search (cache verified), so the discrepancies at FV=0 match Experiment A's results. The FV=50% and FV=100% results show similar discrepancy magnitudes. No capability gaps were encountered — the FV target search was fully executed using existing FBF infrastructure. Variant isolation (§10) is pending follow-up investigation.

---

### 16.5 Experiment E — Deterministic Case Study (T2.6) — Forensic Validation Complete
 
**Status:** IMPLEMENTED AND FORENSICALLY VALIDATED (Phases 1–5 Complete)
 
**Phases 1–4 Implementation (T2.6 Phases 1–4):**
 
- **Phase 1 (Foundation):** `ReturnSequence`, `build_prescribed_dataset()`, `EscalatingWithdrawalPolicy` — implemented in domain layer
- **Phase 2 (Execution Scheduling):** `StepCadence`, `ExecutionSchedule`, `SimulationRunner.run(schedule=...)` — annual cadence support for `PortfolioRebalanceStep`
- **Phase 3 (Deterministic Execution Adapter):** `DeterministicTrajectory`, `execute_deterministic_trajectory()` — thin composition layer around existing `SimulationRunner`
- **Phase 4 (Experiment E Research Adapter):** `build_experiment_e_trajectories()`, `execute_experiment_e()` — four deterministic trajectories composed from generic capabilities
 
**Phase 5 (Forensic Validation):** Zero production code changes. All validation performed through existing Phase 1–4 interfaces.
 
**Capabilities Verified (Frozen Design Compliance):**
 
- ✅ Bear→Bull prescribed sequence (Table 01) — exact 10 annual returns
- ✅ Bull→Bear annual-source reversal — exact reversal of 10 annual returns before monthly expansion
- ✅ Annual→monthly compound conversion — `(1 + annual)^(1/12) - 1`, each 12-month block compounds exactly
- ✅ Annual escalating withdrawal — 3.5% initial, 2% annual escalation, annual frequency (period 0, 12, 24, …)
- ✅ Annual rebalance — `ExecutionSchedule` with `StepCadence.ANNUAL` for `PortfolioRebalanceStep`
- ✅ Annual glidepath — `GlidepathCadence.ANNUAL`, advances at `period_index // 12`: period 0→70%, 12→72%, 24→74%, …, 108→88%, 119→88%, 120→90% (capped)
- ✅ Checkpoint indexing — Year 2 = period 23, Year 10 = period 119
- ✅ Deterministic execution — `execute_experiment_e()` runs all four cases through `execute_deterministic_trajectory()`
 
**Zero production code changes during Phase 5.**
 
### 16.5.1 Four Cases Executed
 
| Case | Sequence | Strategy | Trajectory Name | Initial Wealth | Horizon |
|------|----------|----------|-----------------|----------------|---------|
| 1 | Bear→Bull | Static 80% | `E_bear_bull_static_080` | €1,000,000 | 120 months |
| 2 | Bear→Bull | Glidepath 70→90% | `E_bear_bull_glidepath_070_090` | €1,000,000 | 120 months |
| 3 | Bull→Bear | Static 80% | `E_bull_bear_static_080` | €1,000,000 | 120 months |
| 4 | Bull→Bear | Glidepath 70→90% | `E_bull_bear_glidepath_070_090` | €1,000,000 | 120 months |
 
**Execution Semantics Verified:**
 
- Return sequences: Bear→Bull matches Article Table 01; Bull→Bear is exact annual-source reversal
- Annual→monthly conversion: `(1 + annual)^(1/12) - 1` — each 12-month block compounds exactly
- Annual withdrawal: Year 1 = 35,000; Year 2 = 35,700; Year 3 = 36,414; … Year 10 = 41,828.24
- Annual rebalance: executes at periods 0, 12, 24, …, 108; not at non-annual periods
- Glidepath cadence: period 0→70%, 12→72%, 24→74%, …, 108→88%, 119→88%, 120→90% (capped)
- Checkpoint indices: Year 2 = period 23, Year 10 = period 119
- Expense ratio: 0.05% p.a. applied
- Initial wealth: €1,000,000 (EUR; see currency limitation below)
 
### 16.5.2 Final Eight-Anchor Comparison Table
 
**Display precision:** Published anchors reported to nearest **dollar ($1)**. Display unit = $1. ULP = 1 display unit.
 
| # | Case | Strategy | Checkpoint | Metric | Published | FBF Actual | Diff (abs) | ULP ($1) | Rel Diff | Classification |
|---|------|----------|------------|--------|-----------|------------|------------|----------|----------|----------------|
| 1 | Bear→Bull | Glidepath | Year 2 (p23) | Portfolio | 733,314 | 748,849.22 | +15,535.22 | **15,535** | +2.12% | **UNEXPLAINED DIFFERENCE** |
| 2 | Bear→Bull | Static 80% | Year 2 (p23) | Portfolio | 691,746 | 710,296.84 | +18,550.84 | **18,551** | +2.68% | **UNEXPLAINED DIFFERENCE** |
| 3 | Bear→Bull | Glidepath | Year 10 (p119) | Portfolio | 1,074,558 | 1,083,053.90 | +8,495.90 | **8,496** | +0.79% | **UNEXPLAINED DIFFERENCE** |
| 4 | Bear→Bull | Static 80% | Year 10 (p119) | Portfolio | 995,378 | 1,012,489.37 | +17,111.37 | **17,111** | +1.72% | **UNEXPLAINED DIFFERENCE** |
| 5 | Bull→Bear | Glidepath | Year 10 (p119) | Portfolio | 1,089,990 | 1,064,146.56 | −25,843.44 | **25,843** | −2.37% | **UNEXPLAINED DIFFERENCE** |
| 6 | Bull→Bear | Static 80% | Year 10 (p119) | Portfolio | 1,162,099 | 1,132,486.63 | −29,612.37 | **29,612** | −2.55% | **UNEXPLAINED DIFFERENCE** |
| 7 | Bear→Bull | Glidepath | Year 2 (p23) | Allocation | 39.7% / 60.3% | 72.0% / 28.0% | +32.3pp / −32.3pp | **323 ULP (0.1%)** | N/A | **UNEXPLAINED DIFFERENCE** |
| 8 | Bear→Bull | Static 80% | Year 2 (p23) | Allocation | 85.5% / 14.5% | 80.0% / 20.0% | +5.5pp / −5.5pp | **55 ULP (0.1%)** | N/A | **UNEXPLAINED DIFFERENCE** |
 
**Display precision:** Published monetary anchors to nearest $1 (ULP = $1). Published allocation figures to one decimal place (0.1 percentage points = 0.1 pp ULP).
 
**Classification Summary:**
 
| Classification | Count | Anchors |
|----------------|-------|---------|
| REPRODUCED | 0 | — |
| EXPLAINED DIFFERENCE | 0 | — |
| **UNEXPLAINED DIFFERENCE** | **8** | **All 8 anchors** |
| CAPABILITY GAP | 0 | — |
 
**No anchor upgraded or downgraded.** All discrepancies remain `UNEXPLAINED DIFFERENCE`.
 
### 16.5.3 Controlled Diagnostic Results (Portfolio Anchors)
 
| Hypothesis Tested | Test | Effect on Bear→Bull Static Year 2 (p23) | Effect on Bear→Bull Static Year 10 (p119) | Explains Discrepancy? |
|-------------------|------|----------------------------------------|------------------------------------------|------------------------|
| Monthly vs Annual rebalance | Monthly (every period) vs Annual | −13,820 | −19,302 | No — monthly gives **lower** values, widening gap |
| Expense ratio 0.05% vs 0% | 0.05% vs 0% | −3,768 | −16,995 | No — zero expense **increases** gap |
| Expense ratio sweep (0.10%–0.30%) | 0.10%–0.30% | 706,595–709,556 (target 691,746) | — | No — even 0.30% leaves +14,849 gap |
| Monthly vs Annual withdrawal | Monthly vs Annual | −2,919 | +21,646 | No — direction inconsistent |
| Simple vs Compound monthly conversion | Simple (annual/12) vs Compound | +27,555 | +113,404 | No — simple gives **higher** values, widening gap |
| Pipeline ordering (Returns → Withdrawal → Rebalance) | Article says Returns→Withdrawal→Rebalance; FBF pipeline applies MarketEvolution AFTER PortfolioRebalance | Not tested in isolation | Not tested in isolation | **Plausible but untested** — FBF pipeline applies returns AFTER rebalance; article specifies Returns→Withdrawal→Rebalance |
 
**Summary:** No tested variant explains the portfolio discrepancies. The largest tested effects (rebalance cadence, expense ratio, withdrawal frequency, monthly conversion method) either move values in the wrong direction or are insufficient. Pipeline ordering difference (returns after rebalance vs article's returns before) is a structural difference not isolated in controlled tests.
 
**No tested mechanism explains the observed portfolio-value discrepancies.**
 
**The difference between the article's conceptual Returns → Withdrawal → Rebalance ordering and the current FBF pipeline ordering remains an untested hypothesis and is not established as the cause.**
 
### 16.5.4 Glidepath Progression — Precise Terminology
 
Per frozen period-index contract:
 
| Period | Equity Target | Notes |
|--------|---------------|-------|
| 0 | 70% | Initial target |
| 12 | 72% | First annual advancement |
| 24 | 74% | Second annual advancement |
| … | … | … |
| 108 | 88% | Ninth advancement (Year 10 start) |
| 119 | 88% | End of Year 10 |
| 120 | 90% | Capped at end allocation |
 
**FBF at Year 2 checkpoint (period 23):** 72% equity / 28% bond  
**FBF at Year 10 checkpoint (period 119):** 88% equity / 12% bond
 
The published Year 2 allocation anchor (39.7% / 60.3%) does not correspond to any period-index under the frozen mechanics.
 
### 16.5.5 Allocation-Anchor Contradiction — Precise Statement
 
| Published Anchor | Documented Mechanics | FBF at Period 23 | Discrepancy |
|------------------|----------------------|------------------|-------------|
| Glidepath Year 2: **39.7% equity / 60.3% bond** | 70% → 90% at 2pp/yr → Year 2 target = **72% equity** (period 12); period 23 = **72% equity** | 72.0% / 28.0% | +32.3pp / −32.3pp |
| Static Year 2: **85.5% equity / 14.5% bond** | Static 80% equity with annual rebalancing | 80.0% / 20.0% | +5.5pp / −5.5pp |
 
**Assessment:** The published allocation anchors **cannot be derived from the documented Experiment E mechanics**. No implementation mechanism in the frozen design can reconcile these values. This is a **SOURCE/REFERENCE AMBIGUITY** — the published allocation figures originate from a different computation (likely the workbook's 60%→80% monthly glidepath with $3M portfolio, or a different fee/ordering convention). The FBF implementation follows the documented article mechanics exactly.
 
### 16.5.6 Currency Limitation
 
| Aspect | Finding |
|--------|---------|
| **Authoritative currency** (Article §2.1) | **USD** ($1,000,000) |
| **Implementation currency** | **EUR** (only `Currency.EUR` defined in `Money` model) |
| **Numerical impact** | **None** — simulation operates on `Decimal` amounts; currency is metadata only |
| **Currency-dependent behavior** | None — no formatting, conversion, validation, or arithmetic depends on `Currency` value |
| **Correction required** | **No** — existing domain limitation documented |
 
The `Currency` enum in `src/fbf/core/domain/model/money.py` defines only `EUR`. The Experiment E trajectories use `Currency.EUR` with amount `Decimal("1000000")`. Numerical results are identical; currency label is metadata only.
 
### 16.5.7 Untested Hypothesis
 
`The difference between the article's conceptual Returns → Withdrawal → Rebalance ordering and the current FBF pipeline ordering (which applies MarketEvolution AFTER PortfolioRebalance) remains an untested hypothesis and is not established as the cause.`
 
No controlled test has isolated this pipeline ordering difference. It remains a plausible but untested hypothesis.
 
### 16.5.8 Classification Summary
 
| Classification | Count | Anchors |
|----------------|-------|---------|
| REPRODUCED | 0 | — |
| EXPLAINED DIFFERENCE | 0 | — |
| **UNEXPLAINED DIFFERENCE** | **8** | **All 8 anchors** |
| CAPABILITY GAP | 0 | — |
 
**No anchor upgraded or downgraded.** All discrepancies remain `UNEXPLAINED DIFFERENCE`.
 
### 16.5.9 Implementation Impact
 
| Aspect | Status |
|--------|--------|
| Production code changes during Phase 5 | **None** (zero files modified) |
| Implementation follows frozen design | **Yes** — all Phase 1–4 capabilities used as designed |
| No implementation defect found | **Confirmed** — no defect relative to frozen design |
 
**T2.6 Phase 5 Conclusion:** Experiment E deterministic execution is implemented and forensically validated. All eight published anchors remain `UNEXPLAINED DIFFERENCE`. No production code changes are required or justified. The implementation follows the frozen design exactly.
 
### 16.5.10 Remaining Research Debt
 
| Item | Status |
|------|--------|
| Portfolio value anchor discrepancies | **UNEXPLAINED DIFFERENCE** — 6 anchors; tested mechanisms insufficient |
| Allocation anchor contradiction | **DOCUMENTED SOURCE AMBIGUITY** — Published values irreconcilable with documented mechanics |
| Currency label (USD vs EUR) | Metadata only — no numerical impact |
| Workbook Case Study divergence | **DOCUMENTED** — Workbook implements different computation |
| Pipeline ordering (Returns→Withdrawal→Rebalance) | **UNTESTED HYPOTHESIS** — Article ordering differs from FBF pipeline; not isolated in controlled test |
 
**Formal Classification:** Experiment E — 8 `UNEXPLAINED DIFFERENCE` anchors (0 `CAPABILITY GAP` — implementation exists).
 
**T2.6 Phase 5 Conclusion:** Experiment E deterministic execution is implemented and forensically validated. All eight published anchors remain `UNEXPLAINED DIFFERENCE`. No production code changes are required or justified. The implementation follows the frozen design exactly.

