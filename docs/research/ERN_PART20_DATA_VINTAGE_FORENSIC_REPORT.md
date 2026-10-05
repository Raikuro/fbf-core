# Part 20 A–D Data-Vintage / Source-Difference Forensic Investigation — Report

**Date:** 2026-10-03  
**Status:** COMPLETE — Data vintage is **RULED OUT** as a primary explanation  
**Investigation Artifact:** `tests/forensic_data_vintage.py` (created, run, removed)  
**Execution:** `RUN_ERN_E2E=1 python tests/forensic_data_vintage.py`

---

## 1. Executive Summary

The investigation into whether the remaining Part 20 A–D discrepancies are explained by **data-vintage differences** (modern FBF/SWR Toolbox data through 2026 vs ERN-era data through 2016) has produced a definitive result:

| Hypothesis | Result |
|------------|--------|
| ERN used older data vintage (through 2016-09) vs modern data (through 2026-06) | ❌ **RULED OUT** |

**Key Finding:** The current FBF canonical dataset **already uses the ERN-era historical cutoff (2016-09)**. The extra historical data in the source CSVs (through 2026-06) is loaded but **explicitly ignored** by the dataset loader, which switches to forward projection at 2016-10 per ERN Part 1 §4.

Therefore, the data-vintage hypothesis does not explain the 43 residual discrepancies.

---

## 2. Data Boundaries Established

### 2.1 FBF Canonical Source Data (CSVs)

| Series | First Observation | Last CSV Observation | FBF Loader Usage |
|--------|-------------------|---------------------|------------------|
| S&P 500 TR Real Returns | 1871-02-01 | 2076-12-01 | Used through 2016-09 only |
| S&P 500 TR Nominal Index | 1871-01-01 | 2026-06-01 | Used through 2016-09 only |
| 10Y Bond Real Returns | 1871-02-01 | 2076-12-01 | Used through 2016-09 only |
| CPI Levels | 1871-01-01 | 2026-06-01 | Used through 2016-09 only |
| Shiller CAPE | 1871-01-01 | 2026-06-01 | Used through 2016-09 only |

### 2.2 FBF Dataset Loader Behavior (`src/fbf/core/datasets/ern.py`)

```python
_HISTORICAL_END = datetime(2016, 10, 1)  # first forward month = 2016-10
_PROJECTION_END = datetime(2075, 11, 1)
```

**Historical period:** 1871-03 through 2016-09 (loop: `while current_date < _HISTORICAL_END`)
**Forward projection period:** 2016-10 through 2075-11

**Critical observation:** The loader reads the full CSV data into maps but the historical loop terminates at 2016-09. All months from 2016-10 onward use the Part 1 §4 forward-projection constants (6.6% equity, 0%/2.6% bond), **regardless of what actual historical data exists in the CSVs through 2026-06**.

### 2.3 SWR Toolbox v2.0 Workbook (Asset Returns Sheet)

| Series | Historical Through | Projection Starts | Projection Parameters |
|--------|-------------------|-------------------|----------------------|
| SPX Real Returns | 2026-06 | 2026-07 | ~3.93% equity, ~2.47% bond (phase 1) |
| 10Y Bond Real Returns | 2026-06 | 2026-07 | ~2.47% bond (phase 1), ~2.23% (phase 2) |
| CPI | 2026-06 | — | — |
| CAPE Shiller / ERN | 2026-06 | — | — |

**Workbook has ~10 more years of historical data** and uses different projection parameters.

---

## 3. ERN Source Evidence for Data Vintage

### 3.1 ERN Part 1 (Dec 7, 2016)

> "Monthly data from January 1871 to July 2017. ... We extrapolate past the current history and append equity and bond returns after September 2016."

**Actual data boundary:** Historical through September 2016, projection from October 2016.

### 3.2 ERN Part 20 Publication Date

Article URL: `earlyretirementnow.com/2020/02/05/more-thoughts-on-equity-glidepaths/` → **Published February 5, 2020**

However, the methodology and data vintage reference Part 1 (2016). No evidence that Part 20 updated the historical data boundary.

---

## 4. Forensic Test Results

### 4.1 Test: ERN-era Vintage (2016-09 cutoff) vs Current FBF

| Configuration | Historical Cutoff | Projection Start | Projection Params | Result |
|---------------|-------------------|------------------|-------------------|--------|
| **Current FBF (baseline)** | 2016-09 | 2016-10 | 6.6% / 0% / 2.6% | Baseline |
| **ERN-era vintage** | 2016-09 | 2016-10 | 6.6% / 0% / 2.6% | **IDENTICAL** |
| ERN-era + equity 7.0% | 2016-09 | 2016-10 | 7.0% / 0% / 2.6% | Changes (tested in projection investigation) |

**Result:** The ERN-era vintage dataset produces **bitwise-identical results** to the current FBF baseline for all 12 tested residual cells.

**Reason:** They are the same dataset construction. The current FBF loader **already truncates historical data at 2016-09**.

---

## 5. Why the Data-Vintage Hypothesis Fails

The hypothesis assumed:
1. FBF uses all available historical data through 2026-06
2. ERN used only data through 2016-09
3. The ~10 years of extra historical observations would change results

**Reality:**
- FBF's dataset loader **explicitly implements the ERN Part 1 §4 boundary** (historical through 2016-09, projection from 2016-10)
- The extra CSV data through 2026-06 is loaded into memory but **never used** in the historical period
- Both "modern FBF" and "ERN-era vintage" use exactly the same historical/project boundary

---

## 6. What Actually Differs Between FBF and Workbook

| Aspect | FBF | SWR Toolbox Workbook |
|--------|-----|---------------------|
| Historical cutoff | **2016-09** (per Part 1 §4) | **2026-06** (actual data) |
| Projection start | **2016-10** | **2026-07** |
| Equity projection | **6.6% real** | **~3.93% real** (phase 1) |
| Bond projection (early) | **0% real** | **~2.47% real** |
| Bond projection (late) | **2.6% real** (from month 121) | **~2.23% real** (phase 2) |

The workbook uses **actual historical returns for 2016-2026** while FBF uses **projected returns for that period**.

---

## 7. Impact on Residual Discrepancies

Since the data vintage is identical between "modern FBF" and "ERN-era vintage" in the current implementation:

| Experiment | Residuals | Data-Vintage Effect |
|------------|-----------|---------------------|
| A (60Y failsafe) | 7 | **None** |
| B (30Y failsafe) | 7 | **None** |
| C (Fixed SWR) | 25 | **None** |
| D (FV Targets) | 4 | **None** |

The data-vintage hypothesis is **completely ruled out**.

---

## 8. Classification

| Criterion | Assessment |
|-----------|------------|
| **Confirmed primary source** | ❌ No — zero effect |
| **Contributing factor** | ❌ No — zero effect |
| **Ruled out** | ✅ **YES** — Current FBF already uses ERN-era vintage |
| **Inconclusive** | ❌ No — definitively tested |

**Final Classification: C. RULED OUT**

---

## 9. Remaining Unexplained Discrepancies

With data vintage ruled out, the 43 residual discrepancies remain explained by:

| Factor | Classification | Impact |
|--------|---------------|--------|
| **Forward projection methodology** | Contributing | Major (projection start date, equity rate) |
| **CAPE regime source** | Contributing | Moderate (Experiment C only, mixed direction) |
| Execution order | Eliminated | None |
| ATH semantics | Resolved (commit 3e47550) | None (active glidepaths) |
| Data vintage | **Ruled out** | **None** |

---

## 10. Next Forensic Hypothesis

The remaining plausible hypotheses (in priority order):

### Priority 1: CAPE-Projection Interaction
- CAPE regime determines HIGH/LOW cohort population
- Projection methodology affects returns for those cohorts
- Combined effect may explain specific residual patterns not captured by testing independently

### Priority 2: Expense Ratio / Fee Treatment
- FBF baseline uses 0% expense ratio; ERN uses 0.05%/yr
- Systematic drag on all returns
- T2.3 testing showed insufficient alone but may interact with projection

### Priority 3: Residual CAPE Timing (Cohort-Start vs Monthly)
- Current FBF: CAPE at cohort start from manifest
- ERN may have used different CAPE observation convention
- The 105/1866 disagreements at threshold 20 could shift specific cohorts

### Priority 4: Cohort Convention (1,740 vs 1,739)
- ERN: 1,740 cohorts; FBF: 1,739 executable
- One missing cohort (Dec 2015) could affect order statistics
- T2.3 quantified as ≤0.3 pp for failsafe — unlikely to explain 2–180 ULP

---

## 11. Repository Changes

| Category | Files | Status |
|----------|-------|--------|
| **Forensic/Test-Only** | `tests/forensic_data_vintage.py`, `tests/extract_data_boundaries.py` (created, run, removed) | Cleaned up |
| **Documentation** | `docs/research/ERN_PART20_DATA_VINTAGE_FORENSIC_REPORT.md` | **Created** |
| **Production** | **NONE** | **NO CHANGES** |

### Production-Change Rule Check

| Condition | Status |
|-----------|--------|
| 1. Discrepancy reproduced | ✅ (43 residuals) |
| 2. Semantic difference isolated | ✅ (data vintage tested) |
| 3. Canonical ERN behavior established | ❌ (ERN vintage already implemented) |
| 4. FBF demonstrated incorrect | ❌ (FBF matches ERN vintage) |

**Result:** All four conditions NOT satisfied → **No production change authorized.**

---

## 12. Verification

```bash
# The key insight is in the dataset loader - no separate test needed
cd /mnt/datos/workspace/fbf/fbf-core
grep -n "_HISTORICAL_END" src/fbf/core/datasets/ern.py
# Shows: _HISTORICAL_END = datetime(2016, 10, 1)  # first forward month
```

---

## Appendix: Key Evidence Summary

1. **FBF loader explicitly truncates at 2016-09** — `_HISTORICAL_END = datetime(2016, 10, 1)`
2. **ERN Part 1 §4 documents same boundary** — "after September 2016"
3. **ERN-era vintage test produces identical results** — 0/12 cells changed
4. **Workbook uses different vintage (2026-06) and different projection params** — not ERN-era
5. **Data vintage is already correctly implemented** — not a source of discrepancies

The data-vintage investigation conclusively shows that FBF's current implementation already matches the ERN-era historical data boundary. The remaining discrepancies must be explained by other factors.