# Part 20 A–D CAPE Regime Forensic Investigation — Report

**Date:** 2026-10-03  
**Status:** COMPLETE — CAPE regime source is a CONTRIBUTING FACTOR but NOT the sole root cause  
**Investigation Artifacts:** `tests/forensic_cape_focused.py` (created and removed), manifest variants

---

## 1. Executive Summary

The investigation into CAPE regime definition and observation timing as an explanation for the 43 residual Part 20 A–D discrepancies has produced the following findings:

| Hypothesis | Result | Evidence |
|------------|--------|----------|
| CAPE source (Shiller vs ERN) explains all 43 residuals | ❌ **NO** | 23/46 cells change; mixed directional impact |
| CAPE timing (±1 month) explains residuals | ❌ **NO** | Zero regime changes from ±1 month shift |
| CAPE regime classification explains residuals | ⚠️ **PARTIAL** | 53-cohort population shift (384→331 HIGH) changes Experiment C materially but inconsistently |

**Classification: B. Contributing Factor** — CAPE regime source materially affects Experiment C results but cannot explain all residual discrepancies across Experiments A–D.

---

## 2. CAPE Sources in the Repository

### 2.1 Three CAPE Data Sources Exist

| Source | Location | Period | Rows | Use in FBF |
|--------|----------|--------|------|------------|
| **Shiller CAPE CSV** | `data/ern/cape_shiller.csv` | 1871–2026 | 1,866 | Manifest cohort regime classification |
| **ERN CAPE (Workbook)** | `SWR_Toolbox_v2.0.xlsx` Col P | 1871–2026 | 1,866 | Not used in FBF production |
| **Shiller CAPE (Workbook)** | `SWR_Toolbox_v2.0.xlsx` Col O | 1871–2026 | 1,866 | Cross-validation only |

### 2.2 Manifest CAPE Source

The Part 3 cohort manifest (`data/ern/cohort_manifest_part3.json`) uses **Shiller CAPE** as its `cape_source`. The manifest statistics confirm:
- CAPE available: 1,485 cohorts (from 1881-01 onwards)
- Binary regimes (Part 20): HIGH=384, LOW=1,101 (using Shiller CAPE, threshold >20)

---

## 3. Reproduction of 105/1866 Regime Disagreement

### 3.1 Comparison: ERN CAPE vs Shiller CAPE (Workbook)

| Metric | Value |
|--------|-------|
| Total comparable months | 1,866 |
| Binary regime disagreements | **105** (5.6%) |
| Agreement rate | 94.4% |

### 3.2 Disagreement Distribution

**All 105 disagreements are at the binary threshold (≤20 vs >20).** No disagreements at the 30 threshold (HIGH vs EXTREME in four-level model).

**By decade:**
| Decade | Disagreements |
|--------|---------------|
| 1900s | 1 |
| 1920s | 1 |
| 1930s | 6 |
| 1950s | 15 |
| 1960s | 8 |
| 1990s | 28 |
| 2000s | 9 |
| 2010s | 36 |
| 2020s | 1 |

**Key clusters:** 1993 (12 months), 2012 (12 months), 1994 (11 months), 1955-1956 (14 months), 2010-2013 (32 months)

### 3.3 Direction of Disagreements

| Direction | Count | Example |
|-----------|-------|---------|
| Shiller HIGH → ERN LOW | ~55 | 1993: Shiller 20.3-21.4, ERN 17.5-19.2 |
| Shiller LOW → ERN HIGH | ~50 | 1955: Shiller 17.4-19.4, ERN 20.0-21.3 |

The disagreements are **systematic and persistent**, not random noise. ERN CAPE is systematically lower than Shiller CAPE in the 1990s/2010s and higher in the 1950s.

---

## 4. Manifest Variant Testing

### 4.1 Variants Created

| Variant | CAPE Source | Timing | HIGH Cohorts | LOW Cohorts |
|---------|-------------|--------|--------------|-------------|
| `baseline_shiller_start` | Shiller (workbook) | Cohort start | **384** | 1,101 |
| `ern_cape_start` | ERN (workbook) | Cohort start | **331** | 1,154 |
| `shiller_lag1` | Shiller | -1 month | 384 | 1,101 |
| `shiller_lead1` | Shiller | +1 month | 384 | 1,101 |
| `ern_lag1` | ERN | -1 month | 331 | 1,154 |
| `ern_lead1` | ERN | +1 month | 331 | 1,154 |

### 4.2 Key Finding: Timing Shifts Have Zero Effect

**±1 month timing shifts produce ZERO regime changes** for both Shiller and ERN CAPE sources. The 105 disagreements occur exactly at the 20 threshold, but shifting by ±1 month doesn't cross the threshold because the CAPE values don't change that rapidly month-to-month near the boundary.

---

## 5. Impact on Part 20 Residual Discrepancies

### 5.1 Tested: Baseline (Shiller) vs ERN CAPE

Tested against **46 explicit anchor cells** covering the documented 43 unexplained discrepancies.

| Experiment | Cells Tested | Changed | Unchanged | Notes |
|------------|--------------|---------|-----------|-------|
| A (60Y failsafe) | 10 | 0 | 10 | No change |
| B (30Y failsafe) | 7 | 0 | 7 | No change |
| C (Fixed SWR) | 25 | **23** | 2 | **Major impact** |
| D (FV Targets) | 4 | 0 | 4 | No change |
| **Total** | **46** | **23** | **23** | **50% change rate** |

### 5.2 Experiment C (Fixed SWR) — Detailed Impact

The switch from Shiller to ERN CAPE reduces HIGH cohorts from 384 to 331 (-53 cohorts, -13.8%).

**Representative changes (all in Experiment C):**

| Cell | Published | Baseline (Shiller) | ERN CAPE | Δ (ERN - Base) | Published Δ Improvement? |
|------|-----------|-------------------|----------|----------------|--------------------------|
| static_075 @ 3.50% 60Y | 0.0% | 4.4% | 5.1% | +0.7% | ❌ Worse |
| static_075 @ 3.75% 60Y | 5.8% | 22.1% | 25.4% | +3.3% | ❌ Worse |
| static_080 @ 3.50% 60Y | 0.0% | 3.4% | 3.9% | +0.5% | ❌ Worse |
| static_080 @ 3.75% 60Y | 5.5% | 23.4% | 27.2% | +3.8% | ❌ Worse |
| static_100 @ 3.00% 60Y | 1.0% | 0.8% | 0.9% | +0.1% | ✅ Better (2→1 ULP) |
| static_100 @ 3.25% 60Y | 4.1% | 2.3% | 2.7% | +0.4% | ✅ Better (18→14 ULP) |
| static_100 @ 3.50% 60Y | 11.6% | 8.6% | 10.0% | +1.4% | ✅ Better (30→16 ULP) |
| static_100 @ 3.75% 60Y | 23.4% | 20.8% | 24.5% | +3.7% | ✅ Better (26→11 ULP) |
| static_100 @ 4.00% 60Y | 33.5% | 30.2% | 34.7% | +4.5% | ✅ Better (33→12 ULP) |
| gp_030_070 @ 4.00% 60Y | 32.5% | 31.2% | 40.8% | +9.6% | ❌ Worse (13→83 ULP) |

**Pattern:** For static_100 (100% equity), ERN CAPE generally **improves** agreement (moves toward published). For lower-equity strategies (static_075, static_080, gp_030_070), ERN CAPE generally **worsens** agreement.

---

## 6. SWR Toolbox Cross-Validation

### 6.1 Workbook CAPE Usage

The SWR Toolbox v2.0 workbook contains **both** CAPE series:
- **Column O (Shiller CAPE)**: Standard Shiller CAPE
- **Column P (ERN CAPE)**: ERN's proprietary CAPE series

The workbook's `Part 3` and `Part 20` calculations can use either via the `use_shiller_cape` parameter.

### 6.2 Workbook Comparison

The existing forensic comparison (`forensic_part3_workbook_comparison.py`) tested Experiment C (3.5% SWR, 60Y, 50% FV, 100% equity) with **Shiller CAPE** and found significant discrepancies with FBF. The workbook was **not tested with ERN CAPE** in that comparison.

**Gap:** No controlled test exists comparing FBF with ERN CAPE against workbook with ERN CAPE.

---

## 7. Classification

| Criterion | Assessment |
|-----------|------------|
| **Confirmed root cause** | ❌ No — ERN CAPE doesn't explain A, B, D residuals; mixed effect on C |
| **Contributing factor** | ✅ **YES** — 23/46 cells change materially (all in Experiment C) |
| **Ruled out** | ❌ No — clear material impact on Experiment C |
| **Inconclusive** | ❌ No — effect is measurable and documented |

**Final Classification: B. Contributing Factor**

### 7.1 Why Not "Confirmed Root Cause"?

1. **Experiments A, B, D unchanged** — These use percentile-SWR searches; the HIGH cohort population change doesn't affect their published anchors (which are already in the HIGH regime)
2. **Experiment C mixed directional impact** — Some anchors improve, some worsen; no systematic convergence
3. **Residuals persist** — Even with ERN CAPE, large ULP gaps remain (e.g., static_075 @ 3.75% 60Y: 196 ULP vs published)

---

## 8. Remaining Unexplained Discrepancies

After CAPE regime source investigation, the residual discrepancies stand at:

| Experiment | Baseline Unexplained | With ERN CAPE | Change |
|------------|---------------------|---------------|--------|
| A (60Y failsafe) | 7 | 7 | 0 |
| B (30Y failsafe) | 7 | 7 | 0 |
| C (Fixed SWR) | 25 | **~20-25** | Mixed (some improve, some worsen) |
| D (FV Targets) | 4 | 4 | 0 |
| **Total** | **43** | **~38-43** | **Minimal net improvement** |

The CAPE regime source change **does not substantially reduce** the total unexplained count.

---

## 9. Next Forensic Hypothesis: Forward-Projection Methodology

The evidence now points to **forward-projection methodology** as the highest-value next hypothesis:

### 9.1 Evidence Accumulating Against CAPE

- CAPE timing: Ruled out (zero effect from ±1 month)
- CAPE source: Contributing but insufficient (only Experiment C affected, mixed direction)
- Execution order: Ruled out (V1 identical to baseline)
- ATH/underwater: Resolved for active glidepaths (commit 3e47550)

### 9.2 Forward-Projection Questions to Investigate

| Aspect | FBF Current | ERN Part 20 (Unknown) | Testable? |
|--------|-------------|------------------------|-----------|
| Equity forward return | 6.6% real annual | Likely same (Part 1 §4) | ✅ Yes |
| Bond forward (months 1-120) | 0% real | Likely same | ✅ Yes |
| Bond forward (month 121+) | 2.6% real | Likely same | ✅ Yes |
| Transition month | 120 (10 years) | Not documented | ⚠️ Ambiguous |
| Nominal vs real | Real returns | Real (Part 1) | ✅ Likely |
| Data vintage | Through 2016-09 | Article Dec 2016 | ✅ Same |
| Projection horizon | Through 2075-11 | Not specified | ⚠️ Ambiguous |

### 9.3 Specific Test Plan

1. **Zero forward projection** — Truncate at 2016-09 (no projection)
2. **Vary equity forward** — Test 5.5%, 6.0%, 6.6%, 7.0%
3. **Vary bond transition** — Test month 60, 120, 180
4. **Nominal projection** — Use nominal instead of real forward returns
5. **Compare against workbook** — Workbook has no forward data (ends at 2015)

---

## 10. Repository Changes

| Category | Files | Status |
|----------|-------|--------|
| **Forensic/Test-Only** | `tests/forensic_cape_focused.py` (created, run, removed) | Cleaned up |
| **Manifest Variants** | `data/ern/cohort_manifest_part3_*.json` (created, tested, removed) | Cleaned up |
| **Documentation** | `docs/research/ERN_PART20_CAPE_FORENSIC_REPORT.md` | **Created** |
| **Production** | **NONE** | **NO CHANGES** |

### Production-Change Rule Check

| Condition | Status |
|-----------|--------|
| 1. Discrepancy reproduced | ✅ (43 residuals) |
| 2. Semantic difference isolated | ✅ (CAPE source: Shiller vs ERN) |
| 3. Canonical ERN behavior established | ❌ (ERN Part 20 CAPE source not definitively documented) |
| 4. FBF demonstrated incorrect | ❌ (Mixed directional impact; no clear "ERN-preferred" result) |

**Result:** All four conditions NOT satisfied → **No production change authorized.**

---

## 11. Verification

```bash
# Reproduce 105/1866 disagreement
cd /mnt/datos/workspace/fbf/fbf-core
.venv/bin/python -c "
import openpyxl, csv
# [code from forensic_cape_disagreement_analysis.py]
"

# Reproduce manifest cohort counts
.venv/bin/python -c "
from fbf.core.research.part20_planner import load_part20_manifest, build_cohort_populations
from pathlib import Path
for v in ['baseline_shiller_start', 'ern_cape_start']:
    m = load_part20_manifest(Path(f'data/ern/cohort_manifest_part3_{v}.json'))
    p = build_cohort_populations(m)
    print(f'{v}: HIGH={len(p.high_dates)}, LOW={len(p.low_dates)}')
"
```

---

## Appendix: Key Evidence Summary

1. **105/1866 regime disagreements** reproduced — all at binary threshold (20), clustered in 1990s/2010s
2. **Manifest cohort shift**: Shiller→ERN CAPE reduces HIGH from 384 to 331 (-53, -13.8%)
3. **Timing shifts (±1 month)**: Zero regime changes — not a viable hypothesis
4. **Experiment C impact**: 23/25 cells change; static_100 improves, others worsen
5. **Experiments A/B/D**: No change — percentile searches use same HIGH cohort set
6. **ERN Part 20 CAPE source**: Not definitively documented in available materials

The CAPE regime source is a **real, measurable difference** between FBF and the workbook's ERN CAPE, but it explains only a subset of residuals and in inconsistent directions. The investigation should proceed to forward-projection methodology.