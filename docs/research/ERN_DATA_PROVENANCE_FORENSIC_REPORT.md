# ERN Part 20 — Data Provenance Forensic Audit Report

**Date:** 2026-10-03  
**Status:** COMPLETE — Current implementation complies with canonical data policy  
**Investigation Scope:** Full repository audit of data sources for Part 20 A–D experiments

---

## 1. Canonical Data Policy (Reaffirmed)

Per the task directive, the canonical data policy for FBF is:

| Data Type | Canonical Source | Policy |
|-----------|-----------------|--------|
| S&P 500 Total-Return (nominal) | `data/ern/spx_tr.csv` | Sole source; do not truncate arbitrarily |
| S&P 500 Total-Return (real) | `data/ern/spx_tr_real.csv` | Sole source; do not truncate arbitrarily |
| 10-Year Bond Real Returns | `data/ern/bond_10y_tr_real.csv` | Sole source |
| CPI | `data/ern/cpi.csv` | Sole source |
| CAPE (Shiller) | `data/ern/cape_shiller.csv` | Sole source; no ERN/workbook CAPE substitution |
| `ern_swr_h720.json` | Legacy/derived artifact | **Not a canonical source**; must not influence canonical calculations |

---

## 2. Current Runtime Provenance — Verified Canonical

### 2.1 Market Data (Equity, Bonds, CPI, ATH/Underwater)

| Component | Source | Loader | Verification |
|-----------|--------|--------|--------------|
| S&P 500 real returns | `spx_tr_real.csv` | `load_ern_dataset()` → `_load_csv()` | ✅ Canonical |
| S&P 500 nominal index | `spx_tr.csv` | `load_ern_dataset()` → `_load_csv()` | ✅ Canonical |
| Bond real returns | `bond_10y_tr_real.csv` | `load_ern_dataset()` → `_load_csv()` | ✅ Canonical |
| CPI levels | `cpi.csv` | `load_ern_dataset()` → `_load_csv()` | ✅ Canonical |
| ATH/underwater state | Computed from `spx_tr.csv` nominal index | Inside `load_ern_dataset()` | ✅ Canonical |

**Runtime Path:**  
`Part20ExecutionContext.create(manifest, trajectory)` → `trajectory = load_canonical_dataset(DATA_DIR)` → `load_ern_dataset()` → reads 4 CSVs → builds `Dataset` of `MarketSnapshot[]`

**No alternative data sources are used in production code (`src/`).**

---

### 2.2 CAPE Data

| Component | Source | Verification |
|-----------|--------|--------------|
| CAPE values in manifest | `cape_shiller.csv` (extracted to manifest at build time) | ✅ Canonical |
| CAPE regime classification | `classify_cape_binary(entry.cape_value)` from manifest | ✅ Canonical |
| Cohort populations (HIGH/LOW) | Derived from manifest CAPE values | ✅ Canonical |

**Manifest metadata:** `cape_source: "cape_shiller.csv"` (correct)

**No ERN CAPE (`ern` column in workbook) or alternative CAPE series used in production.**

---

### 2.3 Forward Projection

| Parameter | Value | Source |
|-----------|-------|--------|
| Equity forward return | 6.6% real p.a. | ERN Part 1 §4 (Dec 7, 2016) |
| Bond forward (months 1–120) | 0% real p.a. | ERN Part 1 §4 |
| Bond forward (month 121+) | 2.6% real p.a. | ERN Part 1 §4 |
| Historical end | 2016-09 (last historical month) | ERN Part 1 §4 |
| Projection start | 2016-10 | ERN Part 1 §4 |
| Projection end | 2075-11 | Sufficient for 60Y horizons |

**Implementation:** `src/fbf/core/datasets/ern.py` lines 59–64, 191–266  
**Policy Compliance:** The 2016-09 historical cutoff is **not** an arbitrary truncation — it is the documented ERN Part 1 §4 methodology boundary ("We extrapolate past the current history and append equity and bond returns after September 2016").

---

## 3. Discovered Alternative Data Sources (Non-Canonical)

### 3.1 `ern_swr_h720.json` — Legacy Derived Artifact

| Aspect | Details |
|--------|---------|
| **What is it?** | Precomputed `MarketSnapshot[]` sequence originally produced by ERN SWR Toolbox Google Sheet |
| **Can it be reconstructed?** | Yes — `tools/ern/build_ern_swr_h720.py` reconstructs it from canonical CSVs |
| **Used in production (`src/`)?** | **NO** — zero references in `src/` |
| **Used in canonical Part 20 tests?** | **NO** — Part 20 E2E tests use `load_canonical_dataset()` |
| **Referenced in manifest?** | `market_source: "ern_swr_h720.json"` — metadata only |
| **Used in unit tests?** | As a string identifier `"ern_swr_h720"` in `tests/unit/study/test_builders.py` and `tests/unit/execution/test_research_layer_debt_flow.py` — but study builder resolves to `load_canonical_dataset()` |

**Status:** **LEGACY/FORENSIC ONLY** — Does not affect canonical calculations.

---

### 3.2 ERN CAPE / Workbook CAPE

| Source | Location | Used in Production? |
|--------|----------|---------------------|
| Workbook Column P (ERN CAPE) | `SWR_Toolbox_v2.0.xlsx` | **NO** — only in `tests/forensic_part3_workbook_comparison.py` (forensic cross-validation) |
| Workbook Column O (Shiller CAPE) | `SWR_Toolbox_v2.0.xlsx` | **NO** — only in forensic comparison tools |

**Status:** **FORENSIC ONLY** — Legitimate cross-validation tools, not production.

---

### 3.3 SWR Toolbox Workbook (`SWR_Toolbox_v2.0.xlsx`)

| Aspect | Details |
|--------|---------|
| Historical equity data | Through 2026-06 (10 years beyond ERN 2016 cutoff) |
| Projection start | 2026-07 (differs from ERN's 2016-10) |
| Equity projection | ~3.93% real (phase 1), ~5.37% (phase 2) — differs from ERN 6.6% |
| Bond projection | ~2.47% real from start — differs from ERN 0%/2.6% |

**Status:** **INDEPENDENT IMPLEMENTATION** — Not used as canonical source. Used only in forensic cross-validation tools.

---

## 4. S&P 500 Truncation Analysis

### Finding: The 2016-09 Cutoff Is Intentional ERN Methodology

**Location:** `src/fbf/core/datasets/ern.py` line 63: `_HISTORICAL_END = datetime(2016, 10, 1)`

```python
# Historical period (1871-03 through 2016-09)
while current_date < _HISTORICAL_END:
    # ... use CSV returns ...
```

**This is NOT an arbitrary truncation.** It is the documented ERN Part 1 §4 methodology (Dec 7, 2016):

> "We extrapolate past the current history and append equity and bond returns after September 2016."

The CSV files (`spx_tr_real.csv`, `spx_tr.csv`, etc.) contain data through 2026-06, but the loader **intentionally stops using historical data at 2016-09** and switches to forward projection constants. This is the **correct implementation of ERN methodology**, not an arbitrary truncation.

**Evidence:**
- Comment in code: `# Forward projection constants (ERN canonical — Part 1 §4, Dec 7 2016)`
- Loop condition: `while current_date < _HISTORICAL_END` where `_HISTORICAL_END = datetime(2016, 10, 1)`
- Forward projection loop: `while current_date <= _PROJECTION_END` (2075-11)

---

## 5. Cohort-Universe Provenance

| Component | Source | Verification |
|-----------|--------|--------------|
| Cohort dates | `cohort_manifest_part3.json` (built from canonical data) | ✅ Canonical |
| Market availability | Manifest `market_available` field | ✅ Canonical |
| CAPE values | Manifest `cape_value` from `cape_shiller.csv` | ✅ Canonical |
| CAPE regimes | Manifest `cape_regime` from `cape_shiller.csv` via `classify_cape_binary` | ✅ Canonical |
| Max horizon per cohort | Manifest `max_horizon_months` | ✅ Canonical |

**Manifest metadata:** `market_source: "ern_swr_h720.json"` (metadata only), `cape_source: "cape_shiller.csv"` (correct)

---

## 6. Impact on Part 20 A–D Baseline

### Test Verification

**Test:** `tests/integration/test_part20_e2e_audit.py::TestPart20T21BaselineAudit`

**Data flow in test:**
```python
trajectory = load_canonical_dataset(DATA_DIR)  # ← CSVs
ctx = Part20ExecutionContext.create(MANIFEST_PATH, trajectory)  # ← Manifest + CSVs
```

**No alternative data sources used.**

**Result:** Part 20 baseline uses exactly the intended canonical sources:
- Equity: `spx_tr.csv` (nominal) + `spx_tr_real.csv` (real)
- Bonds: `bond_10y_tr_real.csv`
- CPI: `cpi.csv`
- CAPE: `cape_shiller.csv` (via manifest)

---

## 7. Concrete Discrepancies Between Current and Intended Provenance

| # | Location | Current Behavior | Intended Behavior | Status |
|---|----------|------------------|-------------------|--------|
| 1 | Manifest `market_source` | `"ern_swr_h720.json"` | Should reflect actual source: CSVs | **MINOR** — Metadata only; doesn't affect runtime |
| 2 | `ern_swr_h720.json` exists in repo | Present as committed artifact | Could be removed or marked as derived | **COSMETIC** — Doesn't affect runtime |
| 3 | Unit tests use `"ern_swr_h720"` string | Test builders use string identifier | Should use canonical loader | **MINOR** — Test-only; study builder uses canonical loader |

**None of these affect runtime canonical calculations.**

---

## 8. Recommended Minimum Production Changes

| Change | File | Priority | Rationale |
|--------|------|----------|-----------|
| Update manifest `market_source` | `data/ern/cohort_manifest_part3.json` | LOW | Change `"ern_swr_h720.json"` → `"spx_tr.csv, spx_tr_real.csv, bond_10y_tr_real.csv, cpi.csv (via load_ern_dataset)"` |
| Update unit test builders | `tests/unit/study/test_builders.py` | LOW | Replace `"ern_swr_h720"` identifier with canonical loader call |
| Update debt flow tests | `tests/unit/execution/test_research_layer_debt_flow.py` | LOW | Same as above |
| Add provenance comment to `ern_swr_h720.json` | `data/ern/ern_swr_h720.json` | LOW | Clarify it's a derived artifact, not canonical source |

**All are metadata/cosmetic changes. No runtime behavior changes required.**

---

## 9. Answers to Required Questions

### 1. Is `spx_tr.csv` the sole runtime source of S&P 500 data?
**YES.** `spx_tr.csv` (nominal index) and `spx_tr_real.csv` (real returns) are the sole sources. Loaded via `load_ern_dataset()` → `load_canonical_dataset()`. The 2016-09 historical cutoff is the documented ERN Part 1 §4 methodology, not arbitrary truncation.

### 2. Is `cape_shiller.csv` the sole runtime CAPE source?
**YES.** `cape_shiller.csv` is the sole CAPE source. Manifest `cape_source: "cape_shiller.csv"`. CAPE values in manifest come from this file. No ERN CAPE or workbook CAPE used in production.

### 3. Does `ern_swr_h720.json` affect any canonical calculation?
**NO.** It is a legacy derived artifact. Production code (`src/`) has zero references to it. Part 20 E2E tests use `load_canonical_dataset()` from CSVs. Manifest `market_source` field is metadata only.

### 4. Is `spx_tr.csv` being artificially truncated?
**NO.** The 2016-09 historical cutoff in `load_ern_dataset()` is the documented ERN Part 1 §4 methodology ("extrapolate past the current history and append equity and bond returns after September 2016"). The full CSV data through 2026-06 is loaded into maps but intentionally not used for historical period — this is correct ERN methodology.

### 5. Does the current Part 20 baseline use exactly the intended canonical sources?
**YES.** Verified through code audit:
- Market data: CSVs via `load_canonical_dataset()` → `load_ern_dataset()`
- CAPE: `cape_shiller.csv` via manifest
- Forward projection: ERN Part 1 §4 constants (6.6%/0%/2.6%)
- Cohort universe: Manifest (built from canonical data)

### 6. What minimum production changes are required?
**None for runtime correctness.** Only metadata/cosmetic improvements:
1. Update manifest `market_source` to reflect actual CSV sources
2. Update unit test string identifiers to use canonical loader
3. Document `ern_swr_h720.json` as derived artifact

---

## 10. Re-evaluation of Previous Part 20 Forensic Conclusions

The previous conclusion that *"data vintage/source was ruled out"* (in `ERN_PART20_DATA_VINTAGE_FORENSIC_REPORT.md`) is **correct but for a different reason than originally stated**:

- **Original reasoning:** "Current FBF loader already truncates at 2016-09 per Part 1 §4"
- **Corrected reasoning:** The 2016-09 cutoff **IS** the canonical ERN methodology. There is no "modern FBF vintage vs ERN-era vintage" difference because **FBF correctly implements the ERN-era vintage by design**.

The data-vintage hypothesis was correctly ruled out, but the framing should be:
> **FBF already uses the ERN-era data vintage by design** (per Part 1 §4). There is no alternative "modern data vintage" in the canonical calculation path.

---

## 11. Verification Commands

```bash
# Verify production code uses canonical CSVs
grep -r "load_canonical_dataset\|load_ern_dataset" src/fbf/core/ | grep -v "__pycache__"

# Verify no ern_swr_h720.json in production
grep -r "ern_swr_h720" src/

# Verify CAPE source in manifest
cat data/ern/cohort_manifest_part3.json | grep cape_source

# Verify test uses canonical loader
grep "load_canonical_dataset" tests/integration/test_part20_e2e_audit.py

# Verify no ERN CAPE in production
grep -r "cape_ern\|ERN_CAPE" src/
```

All commands confirm canonical provenance.

---

## 12. Conclusion

**The Part 20 A–D baseline already uses exactly the intended canonical data sources.** The repository contains legacy/forensic artifacts (`ern_swr_h720.json`, workbook CAPE columns) but they are properly isolated in tools/ and tests/forensic/ directories and do not leak into canonical calculations.

**No production changes required for data provenance compliance.** Only minor metadata updates recommended for clarity.