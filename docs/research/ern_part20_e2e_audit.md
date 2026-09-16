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
