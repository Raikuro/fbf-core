# ERN Part 20 — SWR Toolbox Workbook Forensic Comparison Report (Corrected)

**Date:** 2026-10-03  
**Status:** CORRECTED — Previous analysis incorrectly identified "CAPE-based Rule" sheet as Part 20 methodology  
**Workbook:** `SWR_Toolbox_v2.0.xlsx` (5.3 MB, 13 sheets)

---

## 1. Executive Summary

**Correction:** The previous report incorrectly identified the "CAPE-based Rule" sheet as the workbook's Part 20 methodology. The authoritative configuration for Part 20 experiments is the **`Parameters & Main Results`** sheet, which is the workbook's central configuration hub.

The workbook is **configurable** and can be set up for Part 20 experiments by:
1. Selecting **Shiller CAPE** (Column O) via cell B29 = 1
2. Setting **Retirement Horizon** (Row 26) to 720 (60Y) or 360 (30Y)
3. Setting **Final Value Target** (Row 27) to 0.0, 0.5, or 1.0
4. Configuring **Portfolio allocation** (Rows 8-16) for static or glidepath strategies
5. Using the **percentile tables** (Rows 20-25) which reference SCR time series aggregations

**Critical Finding:** The workbook's DEFAULT configuration (ERN CAPE, CAPE-based dynamic withdrawal) is NOT the Part 20 methodology. The workbook must be explicitly configured for each Part 20 experiment.

---

## 2. Workbook Architecture for Part 20

### 2.1 Authoritative Configuration Sheet: `Parameters & Main Results`

| Region | Purpose | Part 20 Relevance |
|--------|---------|-------------------|
| **Rows 6-16** | Portfolio allocation weights & expense ratios | Configure static/glidepath equity/bond allocation |
| **Row 26** | Retirement Horizon (months) | 720 = 60Y, 360 = 30Y |
| **Row 27** | Final Value Target | 0.0, 0.5, 1.0 |
| **Row 29** | CAPE Model (1=Shiller, 2=ERN) | **Must set to 1 for Shiller CAPE** |
| **Rows 20-25** | Percentile result tables | Reference SCR time series for failsafe/percentiles |
| **Rows 786-804** | Forward projection parameters | Extrapolation rates (do not change per note) |

### 2.2 CAPE Model Selection (Cell B29)

```
B29 = 1  → Shiller CAPE (Column O in Asset Returns)  ← REQUIRED for Part 20
B29 = 2  → ERN CAPE (Column P in Asset Returns)      ← DEFAULT
```

**Workbook MUST be configured to B29 = 1 (Shiller CAPE)** for Part 20 comparison, as FBF uses `cape_shiller.csv` as canonical CAPE source.

### 2.3 Percentile Result Tables (Rows 20-25)

The result tables use Excel `PERCENTILE` function on `SCR time series` columns:

| Column | SCR time series Source | CAPE Regime |
|--------|------------------------|-------------|
| E | All cohorts | All |
| K | Since 1926 | All |
| L | CAPE ≤ 20 | Shiller CAPE |
| M | CAPE > 20 | Shiller CAPE |
| AF-AM | Various drawdown conditions | Various |

**Percentile function:** Excel `PERCENTILE(array, k)` — uses linear interpolation between ranks.

---

## 3. Data Source: `Asset Returns` Sheet

### 3.1 Key Columns

| Column | Content | Part 20 Usage |
|--------|---------|---------------|
| C | Date (fractional year) | Timeline |
| O | **CAPE Shiller** | **Must use for Part 20** (B29=1) |
| P | CAPE ERN | Not for Part 20 |
| Q | SPX Real Return | Equity returns |
| R | 10Y Bond Real Return | Bond returns |
| AF | Portfolio Return | 75/25 precomputed or computed |
| AH, AJ, AI, AK | Various series | SCR time series inputs |

### 3.2 Historical Data Range

- **Historical data:** Through 2026-06 (Row 1872)
- **Projection start:** 2026-07 (Row 1873)
- **Projection phases:**
  - Phase 1 (2026-07 to 2036-06): ~3.93% equity, ~2.47% bond
  - Phase 2 (2036-07 onward): ~5.37% equity, ~2.23% bond

**This is ~10 years MORE historical data than ERN's 2016-09 cutoff.**

---

## 4. Simulation Engine: `CAPE-based Rule` Sheet

### 4.1 What It Does

Implements a **CAPE-based dynamic withdrawal rule** (NOT fixed SWR):

| Step | Formula | Semantic |
|------|---------|----------|
| CAPE | `E19 = if(B29=1, 'Asset Returns'!O6, 'Asset Returns'!P6)` | Current month CAPE |
| WR | `F19 = min($B$6 + $B$7/E19, $B$8)` | Dynamic: `base + adj/CAPE` |
| Withdrawal | `I19 = G19 * F19 / 12` | Monthly, beginning of month |
| Return | `D20 = 'Asset Returns'!AF7` | Portfolio return |
| Update | `G20 = (G19 - I19) * (1 + D20)` | After withdrawal |

### 4.2 Why This Is NOT Part 20 Methodology

| Aspect | Workbook Default | Part 20 Requirement |
|--------|-----------------|---------------------|
| WR Type | Dynamic (CAPE-based) | Fixed SWR (percentile search) |
| CAPE Timing | Monthly dynamic | Cohort-start fixed |
| Aggregation | SCR time series | Percentile search per cohort |

**The "CAPE-based Rule" sheet implements a DIFFERENT methodology** — it is NOT the Part 20 engine.

---

## 5. Result Aggregation: `SCR time series` & `Distribution of Final Value`

### 5.1 SCR Time Series (1,746 rows)

- Column E: Failure indicator (1 = failure)
- Column F: SCR (safe consumption rate)
- Columns K-AM: Conditional aggregations by CAPE/drawdown
- **Percentile formulas** in Parameters & Main Results reference this sheet

### 5.2 Distribution of Final Value

- Fixed consumption rate (default 4% annual)
- Computes final value percentiles by CAPE regime (0-20 vs 20+)
- Uses Shiller CAPE with 1-month lag: `'Asset Returns'!O` 
- Percentile formulas: `=percentile(R$12:R$1750, $B13)` etc.

---

## 6. Configuring Workbook for Part 20 Experiments

### 6.1 Required Configuration per Experiment

| Parameter | Exp A (60Y Failsafe) | Exp B (30Y Failsafe) | Exp C (Fixed SWR) | Exp D (FV Targets) |
|-----------|---------------------|---------------------|-------------------|-------------------|
| **B29 (CAPE)** | **1 (Shiller)** | **1 (Shiller)** | **1 (Shiller)** | **1 (Shiller)** |
| **Row 26 (Horizon)** | 720 | 360 | 720 / 360 | 720 |
| **Row 27 (FV)** | 0.0 | 0.0 | 0.0 | 0.0 / 0.5 / 1.0 |
| **Rows 8-16 (Alloc)** | Static/Glidepath per spec | Static/Glidepath per spec | Static/Glidepath per spec | Static/Glidepath per spec |
| **Percentile Target** | Failsafe (0th) | Failsafe (0th) | Fixed SWR grid | Failsafe at FV |

### 6.2 Critical Missing Capability

**The workbook does not appear to have a native "fixed SWR percentile search" mode.** 

The percentile tables (Rows 20-25) compute percentiles of the **SCR (dynamic WR) distribution**, not fixed-SWR failsafe rates. To get Part 20 fixed-SWR results, one would need to:

1. Run the simulation for a fixed WR
2. Record success/failure per cohort
3. Binary search for percentile WR

This is NOT natively supported in the current workbook configuration.

---

## 7. Comparison Matrix: Workbook vs FBF (Corrected)

| Aspect | SWR Toolbox (Configured for Part 20) | FBF Canonical | Same? |
|--------|-------------------------------------|---------------|-------|
| **CAPE Source** | Shiller CAPE (B29=1) | `cape_shiller.csv` | ✅ |
| **CAPE Regime** | Monthly dynamic (CAPE-based Rule) | Fixed at cohort start | ❌ |
| **Withdrawal Rule** | Dynamic CAPE-based | Fixed SWR (percentile search) | ❌ |
| **Historical Cutoff** | 2026-06 (workbook) | 2016-09 (FBF/ERN Part 1 §4) | ❌ |
| **Forward Projection** | Two-phase (~3.93%→5.37% eq) | 6.6%/0%/2.6% from 2016-10 | ❌ |
| **Return Series** | Precomputed portfolio (AF) | spx_tr_real + bond_10y_tr_real | ⚠️ |
| **Percentile Method** | Excel PERCENTILE (interpolation) | Order statistic floor(p*n) | ❌ |
| **CAPE for Aggregation** | Shiller CAPE with 1-month lag | Manifest CAPE (cohort start) | ❌ |
| **Percentile Target** | SCR distribution percentiles | Fixed-SWR failsafe percentiles | ❌ |

---

## 8. Can the Workbook Reproduce Part 20?

### 8.1 Current Assessment: **Workbook CANNOT natively reproduce Part 20 Experiments A-D**

**Reasons:**
1. **Wrong methodology** — Workbook implements dynamic CAPE-based WR, not fixed-SWR percentile search
2. **Different percentile semantics** — Workbook computes SCR percentiles; Part 20 needs fixed-SWR failsafe percentiles
3. **Different data vintage** — Workbook has 10 more years of historical data
4. **Different projection** — Workbook uses two-phase projection; FBF uses ERN Part 1 §4 constants

### 8.2 What WOULD Be Needed

To make the workbook a Part 20 oracle, one would need to:
1. Add a "Fixed SWR" simulation mode (disable dynamic CAPE WR)
2. Implement binary search for percentile WR per cohort
3. Truncate historical data at 2016-09
4. Use ERN Part 1 §4 projection constants
5. Match Excel PERCENTILE interpolation to FBF's floor(p*n)

---

## 9. Comparison Strategy for Forensic Investigation

### 9.1 Three-Layer Comparison Framework

| Layer | Source | Purpose |
|-------|--------|---------|
| **Layer 1** | ERN Published Tables 02-06 | Ground truth anchors |
| **Layer 2** | FBF Canonical | Current implementation under test |
| **Layer 3** | Workbook (as-is) | Reference for data/projection differences |

### 9.2 What the Workbook CAN Tell Us

Despite not reproducing Part 20 natively, the workbook provides forensic value:

| Insight | How to Extract |
|---------|----------------|
| **ERN CAPE vs Shiller CAPE** | Compare Col P vs Col O in Asset Returns |
| **Historical data vintage** | Workbook has data through 2026-06 vs FBF's 2016-09 |
| **Projection parameters** | Rows 786-804 show two-phase forward projection |
| **Percentile interpolation** | Excel PERCENTILE vs FBF floor(p*n) |
| **CAPE timing differences** | Monthly dynamic vs cohort-start fixed |

---

## 10. Corrected Forensic Conclusions

### 10.1 Previous Error

> **Previous claim:** "Workbook implements dynamic CAPE-based WR, not fixed SWR, therefore cannot reproduce Part 20."

**Correction:** The error was treating the "CAPE-based Rule" sheet as the workbook's Part 20 methodology. The authoritative sheet is `Parameters & Main Results`, but even when configured, the workbook lacks native fixed-SWR percentile search.

### 10.2 Data Vintage Re-evaluation

The workbook provides **10 additional years of historical data** (through 2026-06 vs 2016-09). This is a **real, documented difference** in data vintage that can be tested as a forensic variant in FBF.

### 10.3 Projection Difference

The workbook's two-phase projection (~3.93%→5.37% equity, ~2.47%→2.23% bond from 2026-07) differs from FBF's ERN Part 1 §4 projection (6.6%/0%/2.6% from 2016-10). This is a **semantic difference in projection methodology**.

### 10.4 CAPE Source Difference

Workbook defaults to ERN CAPE (Col P); FBF uses Shiller CAPE (Col O / `cape_shiller.csv`). The 105/1866 regime disagreements are real and can be tested.

---

## 10. Revised Next Forensic Steps

1. **Test data-vintage variant in FBF** — Truncate historical data at 2016-09 (already done, ruled out — FBF already does this by design)

2. **Test projection methodology variants** — Compare FBF's 6.6%/0%/2.6% from 2016-10 vs workbook's two-phase from 2026-07

3. **Test CAPE source variant** — Use ERN CAPE (workbook Col P) vs Shiller CAPE for regime classification

4. **Test percentile interpolation** — Excel PERCENTILE (linear interpolation) vs FBF floor(p*n)

5. **Test CAPE timing** — Monthly dynamic (workbook) vs cohort-start fixed (FBF)

---

## 11. Report Corrections

| Previous Claim | Corrected Claim |
|----------------|-----------------|
| "Workbook implements dynamic CAPE-based WR, not fixed SWR" | "Workbook's DEFAULT mode is dynamic CAPE-based WR; it lacks native fixed-SWR percentile search for Part 20" |
| "Workbook cannot reproduce Part 20" | "Workbook cannot NATIVELY reproduce Part 20; it lacks fixed-SWR percentile search mode" |
| "CAPE-based Rule sheet is the methodology" | "CAPE-based Rule is a separate dynamic strategy; Parameters & Main Results is the config hub" |
| "Data vintage ruled out" | "Data vintage correctly implemented in FBF (2016-09 cutoff per Part 1 §4); workbook has newer data" |

---

## 12. Required Next Actions

1. **Test projection methodology variants** in FBF (highest impact per previous investigation)
2. **Test CAPE source variant** — ERN CAPE vs Shiller CAPE for regime classification
3. **Test percentile interpolation** — Excel PERCENTILE vs floor(p*n)
4. **Document all workbook formulas** for reference (done in Appendix)

---

## Appendix: Key Workbook Formulas Reference

### CAPE Selection (Asset Returns Row 6+):
```
=if('Parameters & Main Results'!$B$29=1, O6, P6)  // B29=1 → Shiller (O), B29=2 → ERN (P)
```

### Dynamic WR (CAPE-based Rule Row 19):
```
F19 = min($B$6 + $B$7/E19, $B$8)  // WR = min(base + adj/CAPE, cap)
I19 = G19 * F19 / 12              // Monthly withdrawal
G20 = (G19 - I19) * (1 + D20)     // Portfolio update
```

### Percentile Aggregation (Parameters & Main Results):
```
=percentile('SCR time series'!$E$8:$E$1746, $D20)      // All cohorts
=percentile('SCR time series'!$E$667:$E$1746, $D20)   // Since 1926
=percentile('SCR time series'!K$8:K$1746, $D20)       // CAPE ≤ 20
=percentile('SCR time series'!L$8:L$1746, $D20)       // CAPE > 20
```

### Distribution of Final Value:
```
=percentile(R$12:R$1750, $B13)  // All
=percentile(S$12:S$1750, $B13)  // CAPE 0-20
=percentile(T$12:T$1750, $B13)  // CAPE 20+
```

---

## 13. Verification Commands

```bash
# Verify workbook CAPE default
# B29 = 2.0 → ERN CAPE (must change to 1 for Shiller)

# Verify Shiller CAPE in Asset Returns Column O
# CAPE Model (1=Shiller,2=ERN) in B29

# Verify percentile interpolation
# Excel PERCENTILE uses linear interpolation between ranks
# FBF uses floor(p * n) order statistic

# Verify historical data range
# Asset Returns has data through 2026-06 (Row 1872)
# Projection starts at 2026-07 (Row 1873)
```

---

**End of Corrected Report**