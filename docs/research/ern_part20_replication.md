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
| `ern_cape_1871_2016.json` | 1881-01 through 2023-09 | FBF — verified |

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

### 11.5 Fixed SWR Failure Rates (Table 04, CAPE > 20)

`—` means the corresponding value was not reported in the selected published table cell; it is not interpreted as zero, missing simulation data, or a failed case.

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
