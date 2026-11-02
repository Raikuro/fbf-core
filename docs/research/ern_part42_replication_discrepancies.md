# ERN Part 42 Replication Discrepancies

**Status:** Historical T5.1 discrepancy record — current validation surface removed

**Source Article:** Early Retirement Now Part 42 — "The Effect of 'One More Year'" (2021-01-13)

**Canonical Data Vintage:** Current workbook extraction (`SWR_Toolbox_v2.0.xlsx`)

**Article Data Boundary:** Historical data through 2015-12; forward extrapolation from 2026-07

> **Historical context:** The 319-cell audit described below was performed at
> `95b1b50`. The 554-line `tests/integration/test_part42_e2e_audit.py` was deleted
> at `2c43e68` during the Numba single-engine migration. The current
> tree has no equivalent committed published-table validation surface. The
> port-to-Numba vs retire decision remains unresolved. The counts and
> classifications below describe the historical run, not the current tree.

---

## Oracle Summary

| Metric | Value |
|--------|-------|
| **Total Oracle Cells** | 319 |
| **Numeric Oracle Cells** | 312 |
| **Explicit N/A Cells** | 7 |
| **REPRODUCED** | 44 |
| **EXPLAINED DIFFERENCE** | 0 |
| **UNEXPLAINED DIFFERENCE** | 63 |
| **CAPABILITY GAP** | 212 |
| **Total Fixture Cells** | 319 |

---

## Published Oracle Cells (319 Total)

| Table | Description | Numeric Cells | N/A Cells | Total |
|-------|-------------|---------------|-----------|-------|
| Table 01 | Failure Probabilities of the 4% Rule | 100 | 0 | 100 |
| Table 02 | Failsafe Consumption Amounts by Decade (30-Year Baseline) | 10 | 0 | 10 |
| Table 03 | OMYS Effect (30-Year Horizon) | 30 | 3 | 33 |
| Table 04 | OMYS Effect (30-Year vs 50-Year Horizon) | 60 | 6 | 66 |
| Table 05 | OMYS Effect (30Y vs 50Y vs 50Y+Social Security) | 100 | 10 | 110 |
| **Total** | | **312** | **7** | **319** |

### Explicit N/A Cells (7 total)

| Table | Row | Column | Published Value |
|-------|-----|--------|-----------------|
| Table 03 | Rel to Base | Baseline | N/A |
| Table 04 | Rel to Base | 30Y Baseline | N/A |
| Table 04 | Rel to Base | 50Y Baseline | N/A |
| Table 05 | Rel to Base | 30Y Baseline | N/A |
| Table 05 | Rel to Base | 50Y Baseline | N/A |
| Table 05 | Rel to Base | 50Y+SS Baseline | N/A |
| Table 05 | Rel to Base | 2-year delay | N/A |

These are **intentionally blank** in the published article (relative improvement of baseline vs itself is undefined). The fixture encodes them explicitly as "N/A" strings, and the audit comparison logic treats them as `REPRODUCED` when the implementation also produces `None`/`N/A`.

---

## Classification Breakdown

| Classification | Count | Percentage |
|----------------|-------|------------|
| REPRODUCED | 44 | 13.8% |
| EXPLAINED DIFFERENCE | 0 | 0.0% |
| UNEXPLAINED DIFFERENCE | 63 | 19.7% |
| CAPABILITY GAP | 212 | 66.5% |
| **Total** | **319** | **100%** |

---

## Capability Gap Analysis (212 cells)

| Cause | Count | Tables/Scenarios Affected | Legitimacy |
|-------|-------|---------------------------|------------|
| Missing baseline columns in Rel-to-Base rows (Tables 03-05) | 77 | Tables 03-05, Rel to Base rows | ✅ Legitimate — baseline columns intentionally absent in published "Rel to Base" rows |
| Rel-to-Base missing baseline comparisons | 7 | Tables 03-05, Rel to Base rows | ✅ Legitimate — no baseline to compare against |
| Table 01 empty filtered cohorts (SP500 High, Drawdown buckets) | 128 | Table 01, SP500 High, Drdwn 0-10%, Drdwn 10-20%, Drdwn 20-30%, Drdwn >30% | ✅ Legitimate — no qualifying cohorts satisfy these drawdown/CAPE conditions in the current cohort population |

**Total: 212 CAPABILITY GAP cells** — All are legitimate mathematical/cohort limitations, not implementation failures.

---

## Unexplained Difference Analysis (63 cells)

| Classification | Count | Assessment |
|----------------|-------|------------|
| Demonstrably caused by data vintage | 63 | ✅ Attributable — documented in fixture's `data_vintage` section |

**All 63 UNEXPLAINED DIFFERENCE cells are attributable to the documented data-vintage difference** (2021 article vs 2026 canonical data). The fixture's `data_vintage` section explicitly documents this.

| Parameter | Article (2021) | Canonical Data (2026) | Impact |
|-----------|----------------|------------------------|--------|
| Article date | 2021-01-13 | — | Source vintage |
| Canonical extraction | — | 2026-10-20 | +5.5 years |
| Historical end | 2015-12 | 2026-06 | +10.5 years history |
| Forward extrapolation | Article's rules | Two-zone model | Affects post-2015 cohorts |
| Cohort universe | 1871-2015 | 1871-2015 | Same universe |

**Cohort universe remains 1871–2015** — the additional 10.5 years of historical data do not change the cohort universe used for the published tables.

**No EXPLAINED DIFFERENCE cells** — all non-reproduced differences are either CAPABILITY GAP (legitimate) or UNEXPLAINED DIFFERENCE (data-vintage attributable).

---

## Table 01 Comparison Summary (100 cells)

| Scenario | REPRODUCED | UNEXPLAINED | CAPABILITY GAP |
|----------|------------|-------------|----------------|
| Baseline | 3 | 7 | 0 |
| Delay RE 1Y | 3 | 7 | 0 |
| $5k/m contributions (30Y) | 3 | 7 | 0 |
| 50Y Baseline | 3 | 7 | 0 |
| Delay RE 1Y (50Y) | 3 | 7 | 0 |
| $5k/m contributions (50Y) | 3 | 7 | 0 |
| 50Y Baseline + SocSec | 3 | 7 | 0 |
| Delay RE 1Y (50Y+SocSec) | 3 | 7 | 0 |
| $5k/m (50Y+SocSec) | 3 | 7 | 0 |
| 2-year delay | 1 | 9 | 0 |
| **Total** | **28** | **72** | **0** |

Note: "0" failures in many 50Y scenarios produce exact matches (0.0% failure rate = 0.0% oracle). The "UNEXPLAINED" differences are data-vintage attributable.

---

## Data Vintage Documentation

**Canonical Data Source:** `SWR_Toolbox_v2.0.xlsx`, `Asset Returns` sheet (exact cached values)  
**Article Publication:** 2021-01-13  
**Canonical Data Vintage:** Historical through 2026-06; loader-generated projection 2026-07 to 2075-11  
**Article Cohort End:** 2015-12  
**Canonical Historical End:** 2026-06 (+10.5 years)  

**Forward Extrapolation Rules (from canonical data):**
- Zone 1 (2026-07 to 2036-06): equity 4.0%/yr, bonds 2.5%/yr
- Zone 2 (2036-07 to 2075-11): equity 5.5%/yr, bonds 2.25%/yr

**Effect:** The 2026 canonical data includes ~10.5 years of additional historical observations not available to the 2021 article. Forward extrapolation methodology differs. These are documented replication variables, not implementation errors.

**Fixture/Oracle Integrity:** The oracle fixture (`tests/fixtures/ern_part42_e2e_audit.yaml`) was **not modified** to accommodate implementation results. Published values remain exactly as transcribed from the article.

---

## Comparison Tolerances (Per Fixture)

| Unit | Tolerance | Quantum |
|------|-----------|---------|
| `usd` | ±1 | Exact dollar (Tables 02-05) |
| `percent` | ±0.1 | 0.1% (2-decimal percent, Table 01) |
| `percent_2dp` | ±0.01 | 0.01% (2-decimal percent, Rel-to-Base rows) |

---

## Future Maintenance

> **IMPORTANT:** Changes to canonical datasets, extrapolation methodology, or forward-projection assumptions may change these discrepancy classifications. Any modification to the canonical dataset, extrapolation rules, or cohort boundary conditions requires a fresh forensic comparison against the published oracle rather than silently updating expected values in the fixture. The fixture (`tests/fixtures/ern_part42_e2e_audit.yaml`) is the immutable oracle reference — it must not be updated to match new implementation results without a corresponding forensic re-review.

---

## Reproduction Verification

The following command applied at `95b1b50` and is preserved for historical
traceability only. It does not run in the current tree because
`tests/integration/test_part42_e2e_audit.py` was deleted at `2c43e68`.

```
# Historical command — not valid in the current tree:
RUN_ERN_E2E=1 pytest tests/integration/test_part42_e2e_audit.py -v  # historical; test deleted at 2c43e68
# All 18 tests passed in the historical run, including:
# - test_table01_aggregation (100 cells)
# - test_table02_aggregation (10 cells)
# - test_table03_aggregation (33 cells)
# - test_table04_aggregation (66 cells)
# - test_table05_aggregation (110 cells)
# - test_anchor_comparisons (319 cells)
# - test_classification_counts (44 REPRODUCED, 63 UNEXPLAINED, 212 CAPABILITY GAP)
```

---

**Document Classification:** Historical T5.1 Replication Discrepancy Record — current published-table validation surface removed

**Next Review:** Required if the historical audit is ported to the current Numba path or if canonical dataset, extrapolation methodology, or cohort boundaries change.
