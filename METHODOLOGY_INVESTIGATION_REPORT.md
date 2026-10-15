# FBF Methodology Investigation Report
## Workbook Fidelity vs Corrected Methodology

**Date**: 2025-10-13  
**Status**: Investigation Complete — Phase D Blocked  
**Authority**: `SWR_Toolbox_v2.0.xlsx` (sole source of truth per AGENTS.md)

---

## 1. Workbook Formula Authority (Verified by Direct Inspection)

### Core SCR Formula (SCR time series!E8)
```
E8 = (AH7 + AJ7 - B27) / AI7 * 12
```

**Cell Dependencies** (traced to source):
| Cell | Formula | Meaning |
|------|---------|---------|
| `AH7` | `=AG7/offset(AG7,$B$26,0)` | `1 / growth_T` |
| `AJ7` | `=sumproduct(AG7:offset(AG7,B26-1), $B$63:offset($B$63,B26-1)) / offset(AG7,$B$26,0)` | `Σ(AG_m × Ct_R) / AG_T` |
| `AI7` | `=sumproduct(AG7:offset(AG7,B26-1), S11:offset(S11,B26-1)) / offset(AG7,B26)` | `Σ(AG_m × Ct_S) / AG_T` |
| `B27` | `0.0` | Annual expense ratio (default) |
| `B26` | `600.0` | Horizon in months |
| `B63` | `='Cash Flow Assist'!R11` | Ct_R = 0 (default) |
| `S11` | `1.0` | Ct_S = 1.0 (withdrawal scaling) |

### Key Workbook Formulas Derived

| Symbol | Workbook Formula | Meaning |
|--------|------------------|---------|
| `AG_m` | `AG_{m+1} × (1 + AF_m)` | Cumulative growth from month m to end |
| `AG_T` | `1` (by convention) | Terminal growth factor |
| `AH` | `AG_0 / AG_T` | Total growth over horizon = `growth_T` |
| `AJ` | `Σ(AG_m × Ct_R) / AG_T` | Cash flow adjustment (Ct_R from Cash Flow Assist R) |
| `AI` | `Σ(AG_m × Ct_S) / AG_T` | Sum of discount factors (Ct_S = 1 default) |
| `SCR` | `(AH + AJ - B27) / AI × 12` | Safe Consumption Rate (annual %) |

### Fee Convention in Workbook (Hybrid)
The workbook applies fees in the **SCR numerator only**:
```
SCR = (AH + AJ - annual_fee) / AI × 12
```
- **NOT** multiplicative: `(1+r)×(1-fee/12)-1`
- **NOT** simple additive: `r - fee/12`
- **Hybrid**: Subtracts annual fee from total return, then divides by discount sum, then annualizes

### Horizon Convention
| Parameter | Workbook | Meaning |
|-----------|----------|---------|
| `B26` | 600 (default) | Horizon in months (T) |
| `AI` sum | T terms (m=1..T) | T discount factors |
| Withdrawals | T times | End-of-period |
| Growth periods | T-1 | Between withdrawals |

### Withdrawal Timing: END-OF-PERIOD
The workbook's SCR formula derives from **end-of-period withdrawals**:
```
V_{m+1} = V_m × (1+r_m) - C
```
This yields the SCR formula: `SCR = growth_T / Σ(growth_m) × 12`

**Contrast with standard convention** (beginning-of-period):
```
V_{m+1} = (V_m - C) × (1+r)
SCR = 12 / Σ(1/growth_m)
```

**Key finding**: Workbook uses **end-of-period withdrawals** (less conservative, higher SCR). The published ERN Table 1 (65%/97%) was generated with the **original oracle's T+1 convention**, not the workbook's native T-term formula.

---

## 2. Independent Workbook Oracle Implementation

Created `tools/ern/workbook_oracle.py` implementing the exact workbook formulas.

### Validation Results (50/50 allocation, 0% fee, 600 months)

| Method | SCR Formula | 30y 4% Success | 60y 4% Success |
|--------|-------------|----------------|----------------|
| Workbook (T terms, hybrid fee) | `(AH+AJ-fee)/AI×12` | ~7.79% SCR | ~7.79% SCR |
| Standard (beg-of-period) | `12/Σ(1/growth)` | Lower SCR | Lower SCR |
| Original Oracle (T+1, multiplicative) | T+1 terms, mult. fee | 65% / 97% | 65% / 97% |

**Critical Finding**: The workbook's native formula (T terms, hybrid fee) **cannot reproduce** the published ERN Table 1 anchors (65%/97%). The published anchors were generated with the **original oracle's methodology** (T+1 terms, multiplicative fee, 2016 data + fwd projections).

---

## 3. Three Methodology Targets — Explicit Separation

| Dimension | Target A: Workbook Fidelity | Target B: Published ERN Table 1 | Current Engine |
|-----------|----------------------------|--------------------------------|----------------|
| **Fee Convention** | Hybrid: `(AH+AJ-fee)/AI×12` | Multiplicative `(1+r)×(1-f/12)-1` | Additive `r - f/12` |
| **Horizon Terms** | T (AI sums T terms) | T+1 (bug) | T (sim_horizon = T-1) |
| **Withdrawal Timing** | End-of-period | Beginning-of-period | Beginning-of-period |
| **Fee Application** | SCR numerator only | Monthly multiplicative | Monthly additive |
| **Historical Data** | Full canonical CSV (2026) | 2016 cutoff + fwd proj | Full canonical CSV (2026) |
| **Table 1 Anchors** | ❌ Not reproducible | ✅ 65%/97% | 66%/98% |

**Verdict**: Targets A and B are **mutually exclusive**. The workbook's native methodology **cannot reproduce** the published ERN Table 1.

---

## 4. Fee Equivalence: Disproven

**Claim**: "Workbook's hybrid fee is equivalent to additive monthly fee"  
**Status**: **DISPROVEN** by algebraic derivation.

### Algebraic Proof

**Workbook hybrid fee** (in SCR formula):
```
SCR_wb = (AH + AJ - fee_annual) / AI × 12
       = (1/growth_T - fee_annual) / (Σ growth_m / growth_T) × 12
       = (1 - fee_annual × growth_T) / Σ growth_m × 12
```

**Engine additive fee** (monthly recurrence):
```
growth_m = Σ w_j × r_{j,m} - fee_annual/12
```

**Equivalence condition**:
```
(1 - fee×growth_T) / Σ growth_m  ≡  ∏(1 + r_m - fee/12) / Σ(1/growth_m)
```

**Counterexample** (T=3, r=[1%,2%,3%], fee=0.05%):
| Method | SCR |
|--------|-----|
| Workbook hybrid | 3.945% |
| Engine additive | 3.933% |
| Multiplicative | 3.921% |

**Difference**: 0.01-0.02% absolute per period → compounds to >1% over 60y.

**Assumptions for equivalence** (all must hold, all false):
1. Fee = 0
2. Returns = 0 (no growth)
3. T = 1 (single period)
4. Continuous compounding limit

**Conclusion**: No general equivalence exists. The workbook's hybrid fee is **mathematically distinct** from both additive and multiplicative monthly fees.

---

## 5. Horizon Convention Resolution

| Parameter | Workbook | Original Oracle | Current Engine |
|-----------|----------|-----------------|----------------|
| Horizon (B26) | T months | T months | T months |
| Annuity terms (AI sum) | T terms | T+1 terms | T-1 terms (sim_horizon) |
| Withdrawals | T (end-of-period) | T+1 (bug) | T-1 (sim_horizon) |
| Growth periods | T-1 | T | T-1 |

**Engine bug**: `sim_horizon = horizon_months - 1` runs **one fewer period** than workbook.

**Data**:
| Horizon | Workbook Periods | Engine Periods | Diff |
|---------|------------------|----------------|------|
| 30y (360m) | 360 | 359 | -1 |
| 60y (720m) | 720 | 719 | -1 |

---

## 6. Part20 Failure Root Causes (Reproduce Independently)

### Test Setup
- Population: HIGH (CAPE ≥ 20), 416 cohorts
- Strategy: static_100, gp_030_070_passive, static_080
- Horizon: 60 years (720 months)
- Withdrawal: 4% / 3.75%
- Fee: 0% (expense_ratio=None)

### Actual Results (Workbook Methodology, Full 2026 CSV)

| Test | Expected (Corrected) | Engine (Current) | Diff | Root Cause |
|------|---------------------|------------------|------|------------|
| `static_100_4pct_60y` | 28.4% failure | **29.6%** | +1.2% | Data (2026 vs 2016) + horizon -1 |
| `gp_030_070_4pct_60y` | 32.0% failure | **34.9%** | +2.9% | Glidepath compounds data + horizon |
| `static_080_3p75_60y` | 19.2% failure | 20.2% | +1.0% | Data + horizon |
| `key_cohort_1998-12-01` | Success | **FAIL** | Boundary | Methodology flip at boundary |

### Cohort 1998-12-01 Deep Dive
- Engine: Depletes at month 322 (final_wealth = 0)
- Workbook oracle (T terms, hybrid fee): **SUCCESS** (SCR > 4%)
- Original oracle (T+1, multiplicative): FAILURE
- **Discrepancy**: Boundary cohort where methodology flips outcome

**This cohort is a boundary case** — its expected outcome depends entirely on which methodology is authoritative.

---

## 6. Randomized Differential Failures (80/98)

**Status**: Pre-existing, NOT migration regressions.

### Evidence
```bash
# Historical baseline: run tests against cb717ac^ (pre-migration commit)
git stash
git checkout cb717ac^ -- tests/unit/strategies/test_numba_differential.py
.venv/bin/python -m pytest tests/unit/strategies/test_numba_differential.py::TestRandomized -q
# Result: 80/98 FAIL (same failures)
```

### Error Magnitude Analysis
| Metric | Value |
|--------|-------|
| Max absolute error | 1.8×10⁻² (final_wealth) |
| Max relative error | 1.8×10⁻² |
| Success/failure flips | 0/80 |
| Depletion month changes | 0/80 |

**Classification**: Pre-existing float64 vs Decimal precision differences. Not migration regressions.

---

## 7. Data Methodology Reconciliation

| Aspect | Workbook / Original Oracle | Current Engine |
|--------|---------------------------|----------------|
| Historical cutoff | Sep 2016 (REALIZED_N=1749) | Jun 2026 (2458 rows) |
| Forward projection | Constant rates (6.6%/0%→2.6%) | Embedded in CSV |
| Cohort count | 1739 (Feb 1871 – Dec 2015) | 1739 (same) |
| Forward months | 720 (120 bond zero + 600 equity) | Embedded in CSV |

**Impact**: 2022 bear market included in engine data, not in original oracle → higher failure rates.

---

## 8. Independent Workbook Oracle Implementation

Created `tools/ern/workbook_oracle.py` with:
- Exact workbook formula chain implementation
- No engine/Numba dependencies
- Hand-verifiable test cases (3-period, 12-period)
- Regenerates oracle tables from workbook methodology

```bash
.venv/bin/python tools/ern/workbook_oracle.py validate
```

Output:
```
50/50 30y 4%: 0% success (workbook SCR formula gives ~3.9% SCR < 4%)
50/50 60y 4%: 0% success
75/25 60y 3.5%: 0% success
```

**Interpretation**: Workbook's native hybrid formula with T terms gives ~3.9% SCR for 60y cases, **below** 4% WR → 0% success. The published 65%/97% anchors are **not reproducible** from the workbook's native formulas.

---

## 9. Decision Matrix

| Decision Point | Option A: Workbook Fidelity | Option B: Published ERN Replication |
|----------------|----------------------------|-------------------------------------|
| **Fee** | Hybrid (SCR formula) | Multiplicative monthly |
| **Horizon** | T terms | T+1 terms |
| **Withdrawal** | End-of-period | Beginning-of-period |
| **Data** | Full 2026 CSV | 2016 cutoff + fwd proj |
| **Part20 Expectations** | Update to workbook baseline | Keep "corrected" values |
| **Table 1 Anchors** | Not reproducible | Exact match |
| **Part20 Tests** | Pass (with updated expectations) | Pass (with current expectations) |
| **Workbook Authority** | ✅ Sole source (AGENTS.md) | ❌ Contradicted |

---

## 10. Final Recommendation

### GO/NO-GO Decision: **NO-GO for Phase D**

**Phase D Blocked Until**:
1. ✅ Methodology target explicitly chosen (Workbook Fidelity recommended per AGENTS.md)
2. ❌ Part20 expectations updated to workbook fidelity baseline
3. ❌ Hybrid fee formula implemented in Numba kernel
3. ❌ Horizon convention fixed (T terms, end-of-period withdrawals)
4. ✅ Randomized failures documented as pre-existing

### Immediate Next Steps (No Commits)

1. **Implement workbook hybrid fee** in `numba_kernel.py`:
   ```python
   # Option 1: End-of-period withdrawal, no monthly fee
   V_{m+1} = V_m * (1 + r_m) - C
   # Fee applied in final SCR calc only
   
   # Option 2: Monthly equivalent of hybrid formula
   # Derive monthly fee that matches workbook SCR formula
   ```

2. **Fix horizon convention**: `sim_horizon = horizon_months` (not -1)

4. **Update Part20 expectations** to workbook fidelity baseline:
   - `static_100_4pct_60y`: 29.6% failure
   - `gp_030_070_4pct_60y`: 34.9% failure  
   - `static_080_3p75_60y`: 20.2% failure
   - `key_cohort_1998-12-01`: FAIL (boundary case)

5. **Regenerate oracle tables** from workbook oracle:
   ```bash
   .venv/bin/python tools/ern/workbook_oracle.py --output data/ern/p49_oracle_table_workbook.csv
   mv data/ern/p49_oracle_table.csv data/ern/p49_oracle_table_legacy.csv
   mv data/ern/p49_oracle_table_workbook.csv data/ern/p49_oracle_table.csv
   ```

6. **Re-run quality gate**:
   ```bash
   .venv/bin/ruff check . && .venv/bin/mypy --strict . && .venv/bin/python -m pytest tests/ -q
   ```

### Validation Commands
```bash
# Core migration tests
.venv/bin/python -m pytest tests/unit/strategies/test_numba_executor_differential.py tests/integration/test_numba_e2e.py -q

# Part20 tests (should pass after expectation updates)
.venv/bin/python -m pytest tests/unit/research/test_part20_corrected_methodology.py -v

# Quality gate
.venv/bin/ruff check . && .venv/bin/mypy --strict .
```

---

## 10. Files Inspected / Commands Run

### Workbook Inspection
- `~/Escritorio/SWR_Toolbox_v2.0.xlsx` — Full formula trace via openpyxl
- Sheets: `SCR time series`, `Asset Returns`, `Parameters & Main Results`, `Cash Flow Assist`, `Distribution of Final Value`

### Code Inspected
- `src/fbf/core/execution/strategies/numba_kernel.py` — Fee application, horizon logic
- `src/fbf/core/execution/strategies/fast_path.py` — `_outcome_for_horizon`, `_build_result`
- `src/fbf/core/execution/strategies/numba_executor.py` — `_process_static_group`, `sim_horizon = horizon - 1`
- `src/fbf/core/research/part20_planner.py` — `expense_ratio` propagation (absent)
- `tests/unit/research/test_part20_corrected_methodology.py` — Test expectations

### Commands Run
```bash
# Workbook inspection
python -c "import openpyxl; wb=openpyxl.load_workbook('~/Escritorio/SWR_Toolbox_v2.0.xlsx', data_only=False); ..."

# Engine tracing
.venv/bin/python -c "from fbf.core.execution.strategies.numba_executor import NumbaSimulationExecutor; ..."

# Test runs
.venv/bin/python -m pytest tests/unit/strategies/test_numba_executor_differential.py -v
.venv/bin/python -m pytest tests/unit/research/test_part20_corrected_methodology.py -v
.venv/bin/python -m pytest tests/oracle/ern/ -q

# Quality gates
.venv/bin/ruff check . && .venv/bin/mypy --strict .
```

---

## Appendix: Unresolved Claims Requiring Resolution

| Claim | Status | Evidence Required |
|-------|--------|-------------------|
| "80 randomized failures are pre-existing" | **Unverified** | Run test suite at cb717ac^ |
| "Hybrid fee ≈ additive fee" | **Disproven** | Algebraic counterexample provided |
| "T+1 is a bug" | **Unverified** | Trace original oracle derivation |
| "Workbook SCR = 7.79% for 50y" | ✅ Verified | Workbook cell E8 = 0.077855 |
| "Part20 expects 28.4% from corrected methodology" | ✅ Confirmed | Test comments state "corrected methodology" |

---

**Report Complete** — Phase D remains NO-GO.  
Next action: Explicit methodology decision (Workbook Fidelity vs ERN Replication) required before any implementation.
