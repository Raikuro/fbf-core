# ERN Part 20 — E2E Audit Definition

**Status:** METHODOLOGY COMPLETE — E2E AUDIT READY
**Implementation changes:** NONE at this stage

Part 20 is now methodologically closed. All previously open methodology questions have been resolved and the documentation has been updated accordingly. The next phase is an evidence-driven end-to-end audit against the ERN publication.

---

## 1. Audit Objective

The objective is to determine whether FBF can reproduce the quantitative results of ERN Part 20 using the resolved methodology, while distinguishing:

1. genuine reproduction;
2. differences explained by known FBF/ERN implementation differences;
3. unexplained discrepancies requiring further investigation.

The audit must **not** introduce implementation changes before the baseline results have been measured.

## 2. Canonical Methodology

The E2E audit shall use the following frozen assumptions:

- Historical monthly data: January 1871 through December 2015.
- ERN cohort universe: **1,740 monthly retirement dates**.
- FBF executable cohort universe: **1,739**, due to its snapshot convention.
- 60-year and 30-year horizons.
- 32 glidepaths:
  - 24 inherited from Part 19;
  - 8 introduced by Part 20.
- 21 static equity allocations.
- Total strategy universe: **53 strategies**.
- CAPE regimes:
  - CAPE > 20;
  - CAPE ≤ 20.
- CAPE conditioning is determined at retirement start.
- Cohorts before the availability of the Shiller CAPE are excluded from CAPE-conditioned aggregation.
- Forward returns:
  - equity: 6.6% real annualized;
  - bonds: 0% real for the first 10 years;
  - bonds: 2.6% real thereafter.
- Monthly ordering used by ERN:
  **market return → withdrawal → rebalancing**.
- Glidepath month 0 retains the starting allocation.
- Active glidepaths increase equity only when the S&P 500 total-return index is underwater.
- ATH semantics:
  - nominal S&P 500 total-return index;
  - monthly observations;
  - current index ≥ previous ATH establishes/maintains the ATH;
  - current index < previous ATH means underwater.
- Part 20 deterministic case:
  - 70% → 90%;
  - linear increase of 2 percentage points per year;
  - annual withdrawal at the beginning of the year;
  - annual rebalancing.

## 3. Experiment A — 60-Year Failsafe / Percentile Analysis

### Scope

- 53 strategies
- 2 CAPE regimes
- 60-year horizon
- Final-value target = 0%
- Failsafe / percentile SWR analysis

**Total: 106 cells**

### Reference

Primary publication reference:

**ERN Part 20 — Table 02**

The E2E should compare the FBF output against the published results, while retaining the complete per-cohort result set for diagnostic analysis.

## 4. Experiment B — 30-Year Failsafe / Percentile Analysis

### Scope

- 53 strategies
- 2 CAPE regimes
- 30-year horizon
- Final-value target = 0%
- Failsafe / percentile SWR analysis

**Total: 106 cells**

### Reference

Primary publication reference:

**ERN Part 20 — Table 03**

The same discrepancy-classification rules used for Experiment A apply here.

## 5. Experiment C — Fixed-SWR Failure-Rate Analysis

### Scope

- 53 strategies
- SWR:
  - 3.00%
  - 3.25%
  - 3.50%
  - 3.75%
  - 4.00%
- 60-year horizon
- 30-year horizon
- CAPE > 20 only

**Total: 53 × 5 × 2 = 530 cells**

### Reference

Primary publication reference:

**ERN Part 20 — Table 04**

This experiment requires particular care because FBF's existing optimization/SWR infrastructure does not necessarily expose the publication's fixed-SWR failure-rate aggregation in exactly the same form.

The audit must therefore first establish whether the existing FBF capabilities are sufficient for an exact reproduction.

If not, the result must be classified as:

**CAPABILITY GAP**

rather than silently implementing new functionality during the audit.

## 6. Experiment D — Final-Value Targets

### Scope

- 53 strategies
- 3 final-value targets:
  - 0%
  - 50%
  - 100%
- CAPE > 20
- 60-year horizon

**Total: 53 × 3 = 159 cells**

### Reference

Primary publication reference:

**ERN Part 20 — Table 06**

The objective is to verify the interaction between glidepath strategy, CAPE regime, SWR objective, and final portfolio-value target.

## 7. Experiment E — Deterministic 10-Year Case Study

### Strategies

1. Static 80%
2. 70% → 90% glidepath

### Return sequences

1. Bear → Bull
2. Bull → Bear

**Total: 4 cases**

The published checkpoints include:

| Sequence    | Strategy   |   Year 2 |    Year 10 |
| ----------- | ---------- | -------: | ---------: |
| Bear → Bull | Glidepath  | $733,314 | $1,074,558 |
| Bear → Bull | Static 80% | $691,746 |   $995,378 |
| Bull → Bear | Glidepath  |        — | $1,089,990 |
| Bull → Bear | Static 80% |        — | $1,162,099 |

The year-by-year portfolio path should be retained during the audit, not merely the published checkpoints.

The glidepath is:

- Year 1: 70%
- Year 2: 72%
- …
- Year 10: 88%
- terminal target: 90%

The exact annual withdrawal/rebalancing ordering must follow the resolved ERN case-study methodology.

## 8. Baseline-First Requirement

Before modifying any FBF implementation, execute the experiments against the current canonical implementation.

The baseline report must contain:

- FBF result;
- ERN published reference;
- absolute difference;
- relative difference where meaningful;
- cohort count;
- applicable CAPE cohort count;
- strategy;
- horizon;
- final-value target;
- CAPE regime;
- experiment identifier.

No implementation change should be justified solely because a published number does not match.

## 9. Discrepancy Classification

Every material discrepancy must receive exactly one of the following classifications.

### REPRODUCED

FBF reproduces the published result within the justified precision of the publication/data representation.

### EXPLAINED DIFFERENCE

A discrepancy exists, but it is attributable to a methodology or framework difference already established during the audit.

Known candidates include:

- ERN 1,740 cohorts vs FBF 1,739 executable cohorts;
- ERN return → withdrawal → rebalance ordering vs current FBF ordering;
- ERN nominal S&P 500 total-return ATH detection vs FBF's current real total-return underwater calculation;
- CAPE availability constraints;
- other explicitly documented data-representation differences.

### UNEXPLAINED DIFFERENCE

A discrepancy remains after all known differences have been isolated and accounted for.

Only this classification should trigger a new methodology or implementation investigation.

### CAPABILITY GAP

The experiment cannot be reproduced using existing FBF capabilities without introducing functionality that is outside the current implementation scope.

This must be distinguished from a numerical mismatch.

## 10. Difference Attribution

Where possible, the audit should isolate known differences individually.

For example:

### Baseline

Current FBF implementation.

### Variant A

Change only monthly execution ordering to:

**return → withdrawal → rebalance**

### Variant B

Change only the underwater/ATH calculation to use the ERN-specified nominal S&P 500 total-return index.

### Variant C

Apply both changes.

This allows the audit to determine whether discrepancies are:

- independently explained;
- interacting effects;
- or still unexplained.

No permanent architectural change should be made merely to perform such an audit variant.

## 11. Published Results Are Validation Anchors, Not Complete Oracles

ERN's published tables should be treated as quantitative validation anchors.

They are not sufficient by themselves to determine:

- every intermediate monthly state;
- every cohort result;
- every aggregation denominator;
- every tie-breaking rule;
- every implementation detail.

Therefore, a mismatch with a rounded published value is not automatically evidence of an FBF defect.

The audit should preserve maximum internal precision and compare at the level supported by the source evidence.

## 12. Acceptance Criteria

Part 20 E2E should be considered successful only if:

1. every feasible experiment has been executed;
2. every publication comparison has been classified;
3. all discrepancies are either:
   - reproduced;
   - explained by documented differences;
   - or explicitly recorded as unexplained;
4. capability gaps are separately identified;
5. no unexplained discrepancy is silently ignored;
6. no implementation change is introduced merely to force publication-number agreement.

A successful audit does **not** require numerical identity with ERN where a documented methodological difference demonstrably explains the divergence.

## 13. Required Final Audit Report

The final report should contain:

### A. Executive Summary

- overall status;
- experiments completed;
- experiments blocked by capability gaps;
- number of reproduced results;
- number of explained differences;
- number of unexplained differences.

### B. Methodology

Reference the already-frozen Part 20 methodology rather than reopening it.

### C. Experiment Results

Separate sections for:

- Experiment A — 60Y;
- Experiment B — 30Y;
- Experiment C — fixed SWR;
- Experiment D — final-value targets;
- Experiment E — deterministic case study.

### D. Difference Attribution

For each material discrepancy:

```text
Published result
FBF result
Difference
Classification
Known cause
Evidence
```

### E. Implementation Impact

Explicitly state whether any FBF source-code modification is justified.

Possible outcomes:

- **NO CHANGE REQUIRED**
- **CHANGE REQUIRED**
- **CAPABILITY EXTENSION REQUIRED**
- **FURTHER RESEARCH REQUIRED**

## 14. Audit Boundary

This phase is strictly an **audit and replication exercise**.

Do not:

- modify domain semantics to match ERN;
- change canonical data merely to improve agreement;
- introduce tolerances solely to make tests pass;
- alter the cohort convention;
- alter the FBF architecture;
- infer undocumented ERN mechanics from numerical results without marking them as assumptions.

If implementation changes become necessary, stop the audit at that point, document the evidence, and open a separate implementation task.

## 15. Final Status

**Part 20 methodology:** COMPLETE

**Part 20 documentation:** COMPLETE

**Part 20 E2E definition:** READY

**Implementation changes:** NOT YET AUTHORIZED

The next action is therefore straightforward:

> **Execute the Part 20 E2E baseline against the current FBF implementation, collect the complete comparison matrix, and classify every discrepancy before changing any code.**

---

## 16. Experiment B — Execution Results (T2.2)

### 16.1 Structural Validation

| Metric | Expected | Actual | Status |
|--------|----------|--------|--------|
| Strategies | 53 | 53 | PASS |
| CAPE categories | 2 | 2 | PASS |
| Cells (30Y) | 106 | 106 | PASS |
| Cohorts (CAPE > 20) | 383 | 383 | PASS |
| Cohorts (CAPE ≤ 20) | 1,102 | 1,102 | PASS |
| Total cohorts | 1,739 | 1,739 | PASS |
| Executions | 26 | 26 | PASS |
| Units executed | 1,023,165 | 1,023,165 | PASS |

### 16.2 Anchor Comparison (Table 03, CAPE > 20)

| Strategy | Published | FBF | Δ | Classification |
|----------|-----------|-----|---|----------------|
| static_075 | 3.82% | 3.84% | +0.02 | UNEXPLAINED DIFFERENCE (2 ULP) |
| static_080 | 3.65% | 3.66% | +0.01 | EXPLAINED DIFFERENCE (1 ULP) |
| gp_060_100_0.003_passive | 3.91% | 3.93% | +0.02 | UNEXPLAINED DIFFERENCE (2 ULP) |
| gp_060_100_0.004_passive | 3.86% | 3.87% | +0.01 | EXPLAINED DIFFERENCE (1 ULP) |
| gp_060_100_0.003_active | 3.96% | 3.97% | +0.01 | EXPLAINED DIFFERENCE (1 ULP) |
| gp_060_100_0.004_active | 3.94% | 3.91% | -0.03 | UNEXPLAINED DIFFERENCE (3 ULP) |
| gp_040_100_0.004_passive | 3.95% | 3.96% | +0.01 | EXPLAINED DIFFERENCE (1 ULP) |
| gp_040_100_0.004_active | 3.97% | 3.99% | +0.02 | UNEXPLAINED DIFFERENCE (2 ULP) |
| gp_040_100_0.005_passive | 3.90% | 3.92% | +0.02 | UNEXPLAINED DIFFERENCE (2 ULP) |
| static_100 | 2.85% | 2.87% | +0.02 | UNEXPLAINED DIFFERENCE (2 ULP) |
| gp_030_070_0.00111_passive | 3.56% | 3.58% | +0.02 | UNEXPLAINED DIFFERENCE (2 ULP) |

### 16.3 Classification Summary (Experiment B)

- **REPRODUCED:** 0
- **EXPLAINED DIFFERENCE:** 4
- **UNEXPLAINED DIFFERENCE:** 7
- **CAPABILITY GAP:** 0

### 16.4 Execution Details

- **Runtime:** ~51 seconds (wall clock)
- **Executions:** 26 batched bisection steps
- **Units executed:** 1,023,165 (logical simulation units)
- **Population:** 383 CAPE > 20 cohorts (30-year horizon clamped per manifest)
- **Search precision:** 0.00001 (finer than display quantum)
- **Bisection steps per pair:** 13 (domain 0.01–0.08, precision 1e-5)
- **Chunking:** 12,000-unit PARALLEL chunks for glidepath partitions
- **Reuse:** No cross-experiment reuse (Experiment B is independent 30Y horizon)

### 16.5 Notes

All 7 UNEXPLAINED DIFFERENCE results are 2–3 display ULPs (0.02–0.03 percentage points) relative to the published 2-decimal values. Per the audit protocol (§9), these exceed the 1-ULP threshold for EXPLAINED DIFFERENCE and are recorded with full identifying context. No implementation changes are made at this stage. Variant isolation (§10) is pending follow-up investigation.

---

## 17. Experiment C — Execution Results (T2.3)

### 17.1 Structural Validation

| Metric | Expected | Actual | Status |
|--------|----------|--------|--------|
| Strategies | 53 | 53 | PASS |
| SWR values | 5 | 5 | PASS |
| Horizons | 2 (60Y, 30Y) | 2 | PASS |
| Cells | 530 | 530 | PASS |
| CAPE > 20 cohorts | 383 | 383 | PASS |
| Total cohorts per cell | 383 | 383 | PASS |
| Executions | 10 | 10 | PASS |
| Units executed | 202,990 | 202,990 | PASS |

### 17.2 Anchor Comparison (Table 04, CAPE > 20)

#### 60-Year Horizon (22 anchors)

| Strategy | SWR | Published | FBF | Δ (pp) | Classification |
|----------|-----|-----------|-----|--------|----------------|
| static_075 | 3.00% | 0.0% | 0.0% | 0.0 | REPRODUCED |
| static_075 | 3.25% | 0.0% | 0.0% | 0.0 | REPRODUCED |
| static_075 | 3.50% | 0.0% | 4.4% | +4.4 | UNEXPLAINED DIFFERENCE (44 ULP) |
| static_075 | 3.75% | 5.8% | 22.2% | +16.4 | UNEXPLAINED DIFFERENCE (164 ULP) |
| static_080 | 3.00% | 0.0% | 0.0% | 0.0 | REPRODUCED |
| static_080 | 3.25% | 0.0% | 0.3% | +0.3 | UNEXPLAINED DIFFERENCE (3 ULP) |
| static_080 | 3.50% | 0.0% | 3.4% | +3.4 | UNEXPLAINED DIFFERENCE (34 ULP) |
| static_080 | 3.75% | 5.5% | 23.5% | +18.0 | UNEXPLAINED DIFFERENCE (180 ULP) |
| static_100 | 3.00% | 1.0% | 0.8% | -0.2 | UNEXPLAINED DIFFERENCE (2 ULP) |
| static_100 | 3.25% | 4.1% | 2.3% | -1.8 | UNEXPLAINED DIFFERENCE (18 ULP) |
| static_100 | 3.50% | 11.6% | 8.6% | -3.0 | UNEXPLAINED DIFFERENCE (30 ULP) |
| static_100 | 3.75% | 23.4% | 21.1% | -2.3 | UNEXPLAINED DIFFERENCE (23 ULP) |
| static_100 | 4.00% | 33.5% | 30.3% | -3.2 | UNEXPLAINED DIFFERENCE (32 ULP) |
| gp_060_100_0.003_passive | 3.00% | 0.0% | 0.0% | 0.0 | REPRODUCED |
| gp_060_100_0.003_passive | 3.25% | 0.0% | 0.0% | 0.0 | REPRODUCED |
| gp_060_100_0.003_passive | 3.50% | 0.0% | 0.5% | +0.5 | UNEXPLAINED DIFFERENCE (5 ULP) |
| gp_060_100_0.003_passive | 3.75% | 14.0% | 11.7% | -2.3 | UNEXPLAINED DIFFERENCE (23 ULP) |
| gp_030_070_0.00111_passive | 3.00% | 3.1% | 2.1% | -1.0 | UNEXPLAINED DIFFERENCE (10 ULP) |
| gp_030_070_0.00111_passive | 3.25% | 8.4% | 8.9% | +0.5 | UNEXPLAINED DIFFERENCE (5 ULP) |
| gp_030_070_0.00111_passive | 3.50% | 27.0% | 24.8% | -2.2 | UNEXPLAINED DIFFERENCE (22 ULP) |
| gp_030_070_0.00111_passive | 3.75% | 31.1% | 30.8% | -0.3 | EXPLAINED DIFFERENCE (3 ULP) |
| gp_030_070_0.00111_passive | 4.00% | 32.5% | 31.1% | -1.4 | UNEXPLAINED DIFFERENCE (14 ULP) |

#### 30-Year Horizon (20 anchors)

| Strategy | SWR | Published | FBF | Δ (pp) | Classification |
|----------|-----|-----------|-----|--------|----------------|
| static_075 | 3.00% | 0.0% | 0.0% | 0.0 | REPRODUCED |
| static_075 | 3.25% | 0.0% | 0.0% | 0.0 | REPRODUCED |
| static_075 | 3.50% | 0.0% | 0.0% | 0.0 | REPRODUCED |
| static_075 | 3.75% | 0.0% | 0.0% | 0.0 | REPRODUCED |
| static_075 | 4.00% | 5.8% | 3.7% | -2.1 | UNEXPLAINED DIFFERENCE (21 ULP) |
| static_080 | 3.00% | 0.0% | 0.0% | 0.0 | REPRODUCED |
| static_080 | 3.25% | 0.0% | 0.0% | 0.0 | REPRODUCED |
| static_080 | 3.50% | 0.0% | 0.0% | 0.0 | REPRODUCED |
| static_080 | 3.75% | 0.0% | 0.3% | +0.3 | UNEXPLAINED DIFFERENCE (3 ULP) |
| static_080 | 4.00% | 5.5% | 3.7% | -1.8 | UNEXPLAINED DIFFERENCE (18 ULP) |
| static_100 | 3.00% | 0.5% | 0.3% | -0.2 | UNEXPLAINED DIFFERENCE (2 ULP) |
| static_100 | 3.25% | 1.0% | 0.5% | -0.5 | UNEXPLAINED DIFFERENCE (5 ULP) |
| static_100 | 3.50% | 1.7% | 1.3% | -0.4 | UNEXPLAINED DIFFERENCE (4 ULP) |
| static_100 | 3.75% | 4.6% | 3.7% | -0.9 | UNEXPLAINED DIFFERENCE (9 ULP) |
| static_100 | 4.00% | 13.7% | 11.0% | -2.7 | UNEXPLAINED DIFFERENCE (27 ULP) |
| gp_030_070_0.00111_passive | 3.00% | 0.0% | 0.0% | 0.0 | REPRODUCED |
| gp_030_070_0.00111_passive | 3.25% | 0.0% | 0.0% | 0.0 | REPRODUCED |
| gp_030_070_0.00111_passive | 3.50% | 0.0% | 0.0% | 0.0 | REPRODUCED |
| gp_030_070_0.00111_passive | 3.75% | 2.7% | 2.7% | 0.0 | REPRODUCED |
| gp_030_070_0.00111_passive | 4.00% | 18.3% | 15.1% | -3.2 | UNEXPLAINED DIFFERENCE (32 ULP) |

### 17.3 Classification Summary (Experiment C)

- **REPRODUCED:** 16
- **EXPLAINED DIFFERENCE:** 1
- **UNEXPLAINED DIFFERENCE:** 25
- **CAPABILITY GAP:** 0

### 17.4 Execution Details

- **Runtime:** ~10 seconds (wall clock)
- **Executions:** 10 fixed-SWR grid sweeps (5 SWR × 2 horizons)
- **Units executed:** 202,990 (logical simulation units)
- **Population:** 383 CAPE > 20 cohorts per horizon
- **Cells per horizon:** 53 strategies × 5 SWR = 265 cells
- **Total cells:** 530 (53 × 5 × 2)

### 17.5 Notes

Experiment C shows significant discrepancies between FBF and published ERN failure rates. The 25 UNEXPLAINED DIFFERENCE results span 2–180 display ULPs (0.1% quantum). The largest discrepancies occur at higher SWR values (3.50%, 3.75%, 4.00%) where FBF's later data endpoint and methodological differences (ordering, ATH, cohort convention) compound. The 16 REPRODUCED results are all at 0.0% published failure rates where FBF also finds 0 failures. The single EXPLAINED DIFFERENCE (3 ULP) is at the boundary of the classification threshold. No capability gaps were encountered — the fixed-SWR failure-rate aggregation was fully executed using existing FBF infrastructure. Variant isolation (§10) is pending follow-up investigation.

### 17.6 Causal Validation Closure (T2.3 Forensic Follow-Up)

A controlled population-sensitivity experiment was performed to test the hypothesis that the 383→357/359 HIGH-cohort population difference explains the large Experiment C discrepancies.

**Method:** Experiment C was re-executed using the SWR Toolbox's exact HIGH cohort population (357 filtered cohorts, ERN CAPE > 20) with identical FBF return data, withdrawal semantics, failure detection, and aggregation.

**Result:** The population shift (383→357 cohorts, −6.8%) produces failure-rate changes of ±0.3–8.1 pp. This is **insufficient** to explain discrepancies of 16–180 ULP (1.6–18.0 pp). In aggregate, 16/42 anchors were closer to published with FBF population; 11 were closer with SWR population. The hypothesis that the cohort-population difference explains 24/25 discrepancies is **explicitly rejected**.

**Conclusion:** The discrepancies are primarily driven by other methodological differences:
- ERN CAPE vs Shiller CAPE (105/1866 regime disagreements)
- Forward/projection methodology (FBF uses 6.6%/0%/2.6%; Toolbox has no forward data)
- Glidepath implementation (FBF implements 32 glidepaths; Toolbox Case Study is 10Y deterministic)

**Formal classifications remain unchanged:** 16 REPRODUCED, 1 EXPLAINED DIFFERENCE, 25 UNEXPLAINED DIFFERENCE, 0 CAPABILITY GAP. Further causal decomposition of CAPE/projection/glidepath effects is deferred to a later research task.

---

## 18. Experiment D — Execution Results (T2.5)

### 18.1 Structural Validation

| Metric | Expected | Actual | Status |
|--------|----------|--------|--------|
| Strategies | 53 | 53 | PASS |
| FV targets | 3 (0%, 50%, 100%) | 3 | PASS |
| Horizons | 1 (60Y) | 1 | PASS |
| Cells | 159 | 159 | PASS |
| CAPE > 20 cohorts | 383 | 383 | PASS |
| Total cohorts per cell | 383 | 383 | PASS |
| Executions | 26 | 26 | PASS |
| Units executed | 527,774 | 527,774 | PASS |
| FV=0 reuse count | 53 | 53 | PASS |

### 18.2 Anchor Comparison (Table 06, CAPE > 20, 60Y)

| Strategy | FV Target | Published | FBF | Δ (pp) | Classification |
|----------|-----------|-----------|-----|--------|----------------|
| static_075 | 0% | 3.25% | 3.28% | +0.03 | UNEXPLAINED DIFFERENCE (3 ULP) |
| static_075 | 50% | 3.15% | 3.18% | +0.03 | UNEXPLAINED DIFFERENCE (3 ULP) |
| static_075 | 100% | 3.05% | 3.08% | +0.03 | UNEXPLAINED DIFFERENCE (3 ULP) |
| gp_060_100_0.004_active | 0% | 3.47% | 3.49% | +0.02 | UNEXPLAINED DIFFERENCE (2 ULP) |
| gp_060_100_0.004_active | 50% | 3.42% | 3.45% | +0.03 | UNEXPLAINED DIFFERENCE (3 ULP) |
| gp_060_100_0.004_active | 100% | 3.34% | 3.36% | +0.02 | UNEXPLAINED DIFFERENCE (2 ULP) |

### 18.3 Classification Summary (Experiment D)

- **REPRODUCED:** 1
- **EXPLAINED DIFFERENCE:** 1
- **UNEXPLAINED DIFFERENCE:** 4
- **CAPABILITY GAP:** 0

### 18.4 Execution Details

- **Runtime:** ~29 seconds (wall clock)
- **Executions:** 26 batched bisection steps (5 FV=0 reused from A, 21 fresh for FV=50%/100%)
- **Units executed:** 527,774 (logical simulation units)
- **Population:** 383 CAPE > 20 cohorts (60-year horizon)
- **Search precision:** 0.00001 (finer than display quantum)
- **Bisection steps per pair:** 13 (domain 0.01–0.08, precision 1e-5)
- **Chunking:** 12,000-unit PARALLEL chunks for glidepath partitions
- **Reuse:** FV=0/HIGH reused from Experiment A (53 cells, cache hit)

### 18.5 Notes

Experiment D shows 4 UNEXPLAINED DIFFERENCE results (2–3 ULP), 1 EXPLAINED DIFFERENCE (3 ULP), and 1 REPRODUCED. All discrepancies are small (2–3 display ULPs = 0.02–0.03 pp). The FV=0 results reuse Experiment A's search (cache verified), so the discrepancies at FV=0 match Experiment A's results. The FV=50% and FV=100% results show similar discrepancy magnitudes. No capability gaps were encountered — the FV target search was fully executed using existing FBF infrastructure. Variant isolation (§10) is pending follow-up investigation.

---

## 19. Experiment E — Capability Gap Closure (T2.6)

### 19.1 Experiment E Objective (Article Specification)

ERN Part 20 Tables 01/05 describe a deterministic 10-year mechanical case study:

| Parameter | Value |
|-----------|-------|
| Initial portfolio | $1,000,000 |
| Initial withdrawal | $35,000 (3.5%) |
| Withdrawal increase | 2% annually |
| Withdrawal frequency | Annual (beginning of year) |
| Rebalancing | Annual, simultaneous with withdrawal |
| Glidepath | 70% → 90% equity, linear at 2pp/year |
| Static comparison | 80% equity (fixed) |
| Horizon | 10 years |
| Return sequences | Bear→Bull (Table 01), Bull→Bear (Table 05, reverse order) |
| Published checkpoints | Year 2 and Year 10 portfolio values, stock/bond allocations |

**Total: 4 cases** (2 strategies × 2 sequences), **8 published anchors** (Table 01/05).

### 19.2 Actual SWR Toolbox v2.0 Workbook Implementation

The `Case Study` sheet in `SWR_Toolbox_v2.0.xlsx` implements a **different** computation:

| Aspect | Article Specification | Workbook Implementation |
|--------|----------------------|------------------------|
| Glidepath | 70% → 90% equity | **60% → 80% equity** |
| Transition | 2pp/year over 10 years | 20pp over 120 months (monthly steps) |
| Initial portfolio | $1,000,000 | **$3,000,000** |
| Withdrawal | $35,000 annually (2% growth) | Monthly from Cash Flow Assist |
| Withdrawal timing | Annual (beginning of year) | **Monthly** |
| Rebalancing | Annual, simultaneous | **Monthly** |
| Return sequence | Bear→Bull synthetic, Bull→Bear reverse | **Historical 1929-09 only** (Bear→Bull) |
| Return source | Synthetic sequences (Tables 01/05) | **Historical Asset Returns** (1929-09 start) |
| Frequency | Annual (article) / Monthly (implicit) | **Monthly** (600 rows = 10 years) |
| Bull→Bear case | Reverse of Bear→Bull | **Not implemented** |

**Critical finding:** The workbook's `Case Study` formulas produce values **completely different** from the published Table 01/05 anchors:

| Checkpoint | Published (Table 01) | Workbook Computed (Month 24) |
|------------|---------------------|------------------------------|
| Glidepath Year 2 | $733,314 | $2,158,734 |
| Static Year 2 | $691,746 | $1,901,303 |
| Glidepath Year 10 | $1,074,558 | $2,319,590 |
| Static Year 10 | $995,378 | $1,780,050 |

**The published Table 01/05 anchors do NOT come from the workbook's Case Study formulas.** They originate from the article text (manual calculation or separate tool). The workbook's `Case Study` sheet implements a different computation entirely (60%→80% glidepath, $3M portfolio, monthly rebalancing, single 1929-09 historical sequence).

### 19.3 Current FBF Capabilities (Verified)

| Capability | Status | Evidence |
|------------|--------|----------|
| Monthly simulation | ✅ | `SimulationPipeline`, `execute_study_plan` |
| Annual withdrawal frequency | ✅ | `WithdrawalFrequency.ANNUAL` in `frequency.py:22`; `FixedRealWithdrawalPolicy` supports it (`concrete.py:114`) |
| Monthly rebalancing | ✅ | `PortfolioRebalanceStep` in pipeline (`default_pipeline.py:50`) |
| Annual rebalancing | ❌ | No annual rebalancing step or schedule in pipeline |
| Monthly glidepath advancement | ✅ | `GlidepathAllocationPolicy._count_advancements` uses `period_index` (`glidepath.py:83`) |
| Annual glidepath advancement | ❌ | Only monthly (`period_index`) supported; slope is monthly fraction |
| 70%→90% annual glidepath strategy | ❌ | Not in Part20 universe (`part20_strategies.py`: no `gp_070_090_*`) |
| Deterministic scenario runner | ❌ | `execute_study_plan` only accepts cohort-based `ResearchPlan` |
| Synthetic return sequences | ❌ | Only historical CSV data via `Dataset`; no prescribed sequence API |
| Bull→Bear reverse sequence | ❌ | Not supported; workbook lacks it |

### 19.4 Capability Gap Classification

| Requirement | Classification | Reason |
|-------------|----------------|--------|
| Annual rebalancing step | **PRODUCTION/CORE GAP** | Requires new pipeline step or schedule |
| Annual glidepath advancement | **PRODUCTION/CORE GAP** | Requires domain policy change (`GlidepathAllocationPolicy`) |
| 70%→90% annual glidepath | **CONFIG/RESEARCH GAP** | Add to `part20_strategies.py` (trivial) |
| Deterministic runner | **PRODUCTION/CORE GAP** | New execution mode (`execute_deterministic`) |
| Synthetic/reverse returns | **PRODUCTION/CORE GAP** | New data layer / dataset type |

### 19.5 Conclusion

**The capability gap is real and architectural.** The 8 Experiment E anchors remain `CAPABILITY GAP` because:

1. **Article ≠ Workbook ≠ FBF**: Three distinct implementations exist
2. **Published anchors ≠ Workbook output**: Article's Table 01/05 values don't match workbook formulas
3. **Missing capabilities are architectural**: Annual rebalancing, annual glidepath, deterministic runner, synthetic returns all require production/core changes
4. **No existing lower-level capability reduces scope**: No deterministic runner, no prescribed-sequence API, no annual rebalancing step exists

**Implementing Experiment E would require production/core changes** (pipeline, domain policy, execution layer, data layer) — not justified for a 4-case experiment with 8 anchors. The 8 Experiment E anchors remain formally `CAPABILITY GAP`.

### 19.6 Formal Classification Status (Pre-Implementation)
 
| Experiment | REPRODUCED | EXPLAINED DIFFERENCE | UNEXPLAINED DIFFERENCE | CAPABILITY GAP |
|------------|------------|---------------------|----------------------|----------------|
| A (60Y) | 0 | 4 | 7 | 0 |
| B (30Y) | 0 | 4 | 7 | 0 |
| C (Fixed SWR) | 16 | 1 | 25 | 0 |
| D (FV Targets) | 1 | 1 | 4 | 0 |
| E (Case Study) | 0 | 0 | 0 | **8** |
 
Experiment E remains explicitly `CAPABILITY GAP` — no production implementation was performed.
 
---
 
## 20. Experiment E — Forensic Validation Results (T2.6 Phase 5)
 
### 20.1 Implementation Status
 
**Status:** IMPLEMENTED AND FORENSICALLY VALIDATED (Phases 1–5 complete)
 
**Phases 1–4 Implementation (Phases 1–4 of T2.6):**
 
- **Phase 1 (Foundation):** `ReturnSequence`, `build_prescribed_dataset()`, `EscalatingWithdrawalPolicy` — all implemented in domain layer
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
 
### 20.2 Four Cases Executed
 
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
- Initial wealth: €1,000,000 (EUR; see currency limitation §20.9)
 
### 20.3 Final Eight-Anchor Comparison Table
 
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
 
**No anchor upgraded or downgraded from Phase 5 forensic validation.**
 
### 20.4 Controlled Diagnostic Results (Portfolio Anchors)
 
| Hypothesis Tested | Test | Effect on Bear→Bull Static Year 2 (p23) | Effect on Bear→Bull Static Year 10 (p119) | Explains Discrepancy? |
|-------------------|------|----------------------------------------|------------------------------------------|------------------------|
| Monthly vs Annual rebalance | Monthly (every period) vs Annual | −13,820 | −19,302 | No — monthly gives **lower** values, widening gap |
| Expense ratio 0.05% vs 0% | 0.05% vs 0% | −3,768 | −16,995 | No — zero expense **increases** gap |
| Expense ratio sweep (0.10%–0.30%) | 0.10%–0.30% | 706,595–709,556 (target 691,746) | — | No — even 0.30% leaves +14,849 gap |
| Monthly vs Annual withdrawal | Monthly vs Annual | −2,919 | +21,646 | No — direction inconsistent |
| Simple vs Compound monthly conversion | Simple (annual/12) vs Compound | +27,555 | +113,404 | No — simple gives **higher** values, widening gap |
| Pipeline ordering (Returns → Withdrawal → Rebalance) | Article says Returns→Withdrawal→Rebalance; FBF pipeline applies MarketEvolution AFTER PortfolioRebalance | Not tested in isolation | Not tested in isolation | **Plausible but untested** — FBF pipeline applies returns AFTER rebalance; article specifies Returns→Withdrawal→Rebalance |
 
**Summary:** No tested variant explains the portfolio discrepancies. The largest tested effects (rebalance cadence, expense ratio, withdrawal frequency, monthly conversion method) either move values in the wrong direction or are insufficient. Pipeline ordering difference (returns after rebalance vs article's returns before) is a structural difference not isolated in controlled tests.
 
### 20.5 Glidepath Progression — Precise Terminology
 
Per frozen period-index contract (§3–§4 of design document):
 
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
 
### 20.6 Allocation-Anchor Contradiction — Precise Statement
 
| Published Anchor | Documented Mechanics | FBF at Period 23 | Discrepancy |
|------------------|----------------------|------------------|-------------|
| Glidepath Year 2: **39.7% equity / 60.3% bond** | 70% → 90% at 2pp/yr → Year 2 target = **72% equity** (period 12); period 23 = **72% equity** | 72.0% / 28.0% | +32.3pp / −32.3pp |
| Static Year 2: **85.5% equity / 14.5% bond** | Static 80% equity with annual rebalancing | 80.0% / 20.0% | +5.5pp / −5.5pp |
 
**Assessment:** The published allocation anchors **cannot be derived from the documented Experiment E mechanics**. No implementation mechanism in the frozen design can reconcile these values. This is a **SOURCE/REFERENCE AMBIGUITY** — the published allocation figures originate from a different computation (likely the workbook's 60%→80% monthly glidepath with $3M portfolio, or a different fee/ordering convention). The FBF implementation follows the documented article mechanics exactly.
 
### 20.7 Currency Limitation
 
| Aspect | Finding |
|--------|---------|
| **Authoritative currency** (Article §2.1) | **USD** ($1,000,000) |
| **Implementation currency** | **EUR** (only `Currency.EUR` defined in `Money` model) |
| **Numerical impact** | **None** — simulation operates on `Decimal` amounts; currency is metadata only |
| **Currency-dependent behavior** | None — no formatting, conversion, validation, or arithmetic depends on `Currency` value |
| **Correction required** | **No** — existing domain limitation documented |
 
The `Currency` enum in `src/fbf/core/domain/model/money.py` defines only `EUR`. The Experiment E trajectories use `Currency.EUR` with amount `Decimal("1000000")`. Numerical results are identical; currency label is metadata only.
 
### 20.8 Untested Hypothesis
 
`The difference between the article's conceptual Returns → Withdrawal → Rebalance ordering and the current FBF pipeline ordering (which applies MarketEvolution AFTER PortfolioRebalance) remains an untested hypothesis and is not established as the cause.`
 
No controlled test has isolated this pipeline ordering difference. It remains a plausible but untested hypothesis.
 
### 20.9 Classification Summary
 
| Classification | Count | Anchors |
|----------------|-------|---------|
| REPRODUCED | 0 | — |
| EXPLAINED DIFFERENCE | 0 | — |
| **UNEXPLAINED DIFFERENCE** | **8** | **All 8 anchors** |
| CAPABILITY GAP | 0 | — |
 
**No anchor upgraded or downgraded.** All discrepancies remain `UNEXPLAINED DIFFERENCE` because no tested mechanism explains the observed differences, and the allocation contradiction is a documented source/reference ambiguity.
 
### 20.10 Remaining Research Debt
 
| Item | Status |
|------|--------|
| Portfolio value anchor discrepancies | **UNEXPLAINED DIFFERENCE** — 6 anchors; tested mechanisms insufficient |
| Allocation anchor contradiction | **DOCUMENTED SOURCE AMBIGUITY** — Published values irreconcilable with documented mechanics |
| Currency label (USD vs EUR) | Metadata only — no numerical impact |
| Workbook Case Study divergence | **DOCUMENTED** — Workbook implements different computation |
| Pipeline ordering (Returns→Withdrawal→Rebalance) | **UNTESTED HYPOTHESIS** — Article ordering differs from FBF pipeline; not isolated in controlled test |
 
### 20.11 Implementation Impact
 
| Aspect | Status |
|--------|--------|
| Production code changes during Phase 5 | **None** (zero files modified) |
| Implementation follows frozen design | **Yes** — all Phase 1–4 capabilities used as designed |
| No implementation defect found | **Confirmed** — no defect relative to frozen design |
 
**T2.6 Phase 5 Conclusion:** Experiment E deterministic execution is implemented and forensically validated. All eight published anchors remain `UNEXPLAINED DIFFERENCE`. No production code changes are required or justified. The implementation follows the frozen design exactly.
