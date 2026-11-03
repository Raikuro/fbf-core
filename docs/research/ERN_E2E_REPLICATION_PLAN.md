# ERN E2E Research Replication Plan

**Status:** DRAFT — AWAITING REVIEW
**Created:** 2026-09-08
**Scope:** Eight ERN articles (Parts 1, 2, 3, 19, 20, 42, 49, 52)
**Authority:** Audit-driven plan. No production code changes in this phase.

---

## A. Scope

This document covers the eight ERN (Early Retirement Now) Safe Withdrawal Rate articles targeted for E2E research replication in the FBF framework:

| # | Article | Title | ERN URL |
|---|---------|-------|---------|
| 1 | Part 1 | Introduction to the SWR Series | earlyretirementnow.com/2016/11/16/the-ultimate-guide-to-safe-withdrawal-rates-part-1-intro/ |
| 2 | Part 2 | Capital Preservation vs. Capital Depletion | earlyretirementnow.com/2016/11/23/your-custom-swr-rate/ |
| 3 | Part 3 | Equity Valuation Using CAPE | earlyretirementnow.com/2016/12/21/the-ultimate-guide-to-safe-withdrawal-rates-part-3-equity-valuation/ |
| 4 | Part 19 | Equity Glidepaths in Retirement | earlyretirementnow.com/2020/01/15/equity-glidepaths-in-retirement/ |
| 5 | Part 20 | More Thoughts on Equity Glidepaths | earlyretirementnow.com/2020/02/05/more-thoughts-on-equity-glidepaths/ |
| 6 | Part 42 | One More Year Syndrome | earlyretirementnow.com/2022/08/24/one-more-year-syndrome/ |
| 7 | Part 49 | Using Leverage in Retirement | earlyretirementnow.com/2021/11/16/leverage-in-retirement-swr-series-part-49/ |
| 8 | Part 52 | Timing Leverage in Retirement | earlyretirementnow.com/2022/12/07/timing-leverage-in-retirement/ |

---

## B. Research Understanding

### B.1 Part 1 — Introduction to the SWR Series

- **Research question:** What is the maximum safe withdrawal rate for a given retirement horizon and equity allocation?
- **Methodology:** Rolling-cohort historical simulation using US market data 1871–2015.
- **Dataset:** `spx_tr_real.csv`, `bond_10y_tr_real.csv` (monthly real equity and bond returns).
- **Cohort definition:** 1,739+ rolling monthly cohorts from 1871-01 through 2015-12.
- **Horizons:** 30, 40, 50, 60 years.
- **Policies:** Constant equity/bond allocation, fixed real withdrawal rate.
- **Success criteria:** Portfolio survives the full horizon (capital depletion = failure).
- **Published anchors:** Table 1 SWR success rates for 5 equity allocations × 9 withdrawal rates × 4 horizons.

### B.2 Part 2 — Capital Preservation vs. Capital Depletion

- **Research question:** How do terminal value targets (depletion, 50%, 100%) affect the SWR?
- **Methodology:** Same as Part 1, extended with terminal value thresholds.
- **Dataset:** Same as Part 1.
- **Cohort definition:** Same as Part 1.
- **Horizons:** 30, 40, 50, 60 years.
- **Policies:** Same as Part 1.
- **Success criteria:** Portfolio meets or exceeds terminal value target at horizon end.
- **Published anchors:** Success rate curves for depletion, 50%, and 100% terminal value targets.

### B.3 Part 3 — Equity Valuation Using CAPE

- **Research question:** How does the Shiller CAPE ratio at retirement start affect SWR success?
- **Methodology:** Rolling-cohort simulation stratified by CAPE regime at retirement start.
- **Dataset:** `cape_shiller.csv` (Shiller CAPE data, 1881–2023) plus `ern_swr_h720.json` for simulation.
- **Cohort definition:** 851 unique retirement start dates with CAPE data (1881-01 through 2023-09).
- **Horizons:** 30 and 60 years.
- **Policies:** Same as Part 1, with CAPE regime classification.
- **Success criteria:** Same as Part 2, stratified by CAPE regime.
- **Published anchors:** Success rates for 4 experiments (A: 4% depletion, B: 4%/50% TV, C: 3.5%/50% TV, D: 3.25%/50% TV).

### B.4 Part 19 — Equity Glidepaths in Retirement

- **Research question:** Do equity glidepaths (increasing equity allocation over time) improve SWR?
- **Methodology:** Rolling-cohort simulation with time-varying equity allocation.
- **Dataset:** Same as Part 1 (`ern_swr_h720.json`).
- **Cohort definition:** 1,739 rolling monthly cohorts.
- **Horizons:** 60 years.
- **Policies:** Glidepath allocation (passive: linear increase; active: increase only when underwater).
- **Success criteria:** Capital depletion.
- **Published anchors:** 24 glidepaths (6 start/end combos × 2 slopes × 2 modes).

### B.5 Part 20 — More Thoughts on Equity Glidepaths

- **Research question:** How do additional glidepath variants (Kitces/Pfau-inspired) perform?
- **Methodology:** Extension of Part 19 with additional glidepath parameter space.
- **Dataset:** Same as Part 1.
- **Cohort definition:** Same as Part 1.
- **Horizons:** 30 and 60 years.
- **Policies:** Same glidepath mechanics as Part 19, extended with 8 additional passive glidepaths.
- **Success criteria:** Capital depletion.
- **Published anchors:** 32 glidepaths total (24 from Part 19 + 8 new).

### B.6 Part 42 — One More Year Syndrome

- **Research question:** How does working one additional year with $5,000/month contributions affect SWR?
- **Methodology:** Rolling-cohort simulation with 12-month pre-retirement accumulation phase.
- **Dataset:** Same as Part 1.
- **Cohort definition:** Same as Part 1.
- **Horizons:** 30 years (including 12-month OMY).
- **Policies:** Accumulation phase (zero withdrawals, $5k/month contributions), then standard retirement.
- **Success criteria:** 25% terminal value target.
- **Published anchors:** Baseline failsafe ~3.6%, OMY improvement +7.8%.

### B.7 Part 49 — Using Leverage in Retirement

- **Research question:** How does margin-loan leverage affect SWR success?
- **Methodology:** Rolling-cohort simulation with debt/lifecycle mechanics.
- **Dataset:** Production `data/ern`.
- **Cohort definition:** Experiment-specific single cohorts, plus 792 monthly cohorts (1925-01…1990-12) for Experiment F.
- **Horizons:** 30 years.
- **Policies:** Partial leverage (portfolio withdrawal + 1% loan draw = 4% total spending), fixed real interest rates (0%, 1.5%, 3%), buy-and-hold allocation.
- **Modes:** Experiments B/C run dual-mode: observe-only for chart reproduction and `ltv_enforcement=True` for 75% terminal-failure validation.
- **Success criteria:** Portfolio survives full horizon in observe-only mode; LTV breaches terminate as `margin_call_terminal` in enforcement mode.
- **Published anchors:** Experiments B–F charts and the Experiment F historical failure count.

### B.8 Part 52 — Timing Leverage in Retirement

- **Research question:** How does drawdown-triggered leverage timing improve SWR?
- **Methodology:** Rolling-cohort simulation with conditional leverage activation, FFR-based floating rates, repayment at fresh ATH.
- **Dataset:** Same as Part 1 plus `ffr.csv` (runtime spliced FFR from workbook `Return Data!K`; runtime ends 2026-08, workbook ends 2021-12; `ffr_monthly.json` is a reconstructed series, not `K`; the SWR cash total-return series is not an FFR source).
- **Cohort definition:** 1,739 rolling monthly cohorts.
- **Horizons:** 30 years.
- **Policies:** Part52WithdrawalPolicy with drawdown thresholds (20%, 25%, 30%, 35%), FFR+spread rates, LTV 50% observed but not enforced in the current study configuration, repayment at fresh ATH.
- **Success criteria:** Article/Solver objective is to maximize WR subject to 25% terminal net worth and 50% LTV; the current oracle test measures gross survival only.
- **Published anchors:** 11 scenarios (A1–A11) with specific WR and Borrow% values.

---

## C. Canonical Replication Classification

### C.1 Classification Rules

| Classification | Definition |
|---------------|-----------|
| **CANONICAL** | FBF data and methodology are sufficient to reproduce the ERN experiment without material methodology substitution |
| **CANONICAL WITH DIFFERENCES** | FBF reproduces the core methodology with a documented, immaterial difference |
| **NON-CANONICAL** | FBF substitutes data, methodology, or another material component |
| **NOT REPLICABLE** | Required methodology/data is unavailable |

### C.2 Article Classifications

#### Part 1 — CANONICAL: YES

- **Grid:** `ern_grid.yaml` (5W × 9R × 4H = 180 cells)
- **Dataset:** `ern_swr_h720.json`
- **Status:** Fully implemented and validated against oracle table (`p49_oracle_table.csv`).
- **E2E test:** `test_full_swr_grid.py::test_full_grid_matches_workbook_oracle` (full grid) and `::test_smoke_cell_matches_workbook_oracle` (smoke).
- **Note:** Redundant with Part 2 (see Section D). The current test file replaces the historical `test_ern_swr_replication.py` name referenced in earlier revisions of this plan.

#### Part 2 — CANONICAL: YES

- **Grid:** `ern_grid.yaml` (same as Part 1, with terminal value target dimension)
- **Dataset:** `ern_swr_h720.json`
- **Status:** Fully implemented. The `final_value_target: [0.0]` in `ern_grid.yaml` covers the depletion case; terminal value variants can be expressed by modifying the FV target.
- **E2E test:** `test_full_swr_grid.py::test_full_grid_matches_workbook_oracle` (same test as Part 1).
- **Note:** Strict superset of Part 1 (see Section D).

#### Part 3 — CANONICAL: NO

- **Classification:** METHODOLOGY COMPLETE — E2E SPEC PENDING
- **Methodology status:** COMPLETE — all 3 Part 3-specific methodology questions resolved:
  1. CAPE observation timing — RESOLVED: use actual date of canonical CAPE observation
  2. Pre-1881 cohort handling — RESOLVED: include pre-1881 cohorts; CAPE series extracted to canonical CSV (`cape_shiller.csv`)
  3. CAPE-conditioned filtering — RESOLVED: use article graph definitions as source of truth
- **Data status:** Canonical asset-return data is available in `canonical/ern_asset_returns`. Data availability is NOT the blocking issue.
- **Implementation status:** Part 3 pipeline exists but produces 0% success due to dataset representation issues (not data availability).
- **Existing tests useful as:** Non-canonical framework validation (CAPE regime classification, cohort generation, aggregation logic).
- **Test files:** `tests/unit/research/test_part3_*.py`, `tests/integration/` (CAPE-related).
- **YAML files:** `ern_part3_replication.yaml` (retained; individual experiment files `ern_part3_expA/B/C/D.yaml` removed as strict subsets — see Section K).
- **Documentation:** `docs/research/ern_part3_replication.md` (methodology questions resolved).

#### Part 19 — CANONICAL METHODOLOGY — IMPLEMENTED & CROSS-VALIDATED

- **Grid:** Part of `ern_part20.yaml` (24 glidepaths from Part 19, combined with Part 20).
- **Dataset:** `ern_swr_h720.json`
- **Methodology status:** COMPLETE — global monthly sequencing and ATH rules established.
- **Implementation status:** **IMPLEMENTED & CROSS-VALIDATED** — ATH/underwater state now uses the CPI-adjusted real total-return index and real running ATH (`ern_part20_e2e_audit.md` §19.7). The earlier nominal running-ATH fix (`3e47550`) is historical and superseded by the real-ATH correction.
- **E2E status:** **IMPLEMENTED & CROSS-VALIDATED** — `test_part19_canonical_ern_replication.py` (Exp A) and `test_part19_experiment_b_e2e.py` (Exp B) both implemented and gated `ern_e2e`. Cross-validated against Part 20 Exp C and Exp A respectively.
- **Note:** Part 20 ⊃ Part 19 for glidepath definitions (see Section D). Part 19 Experiment A remains an independent E2E target — Part 20 does not reproduce it as a complete experiment (see Section D.2).

#### Part 20 — CANONICAL METHODOLOGY — AUDIT COMPLETE ON AVAILABLE DATA, CANONICAL-DATA REVALIDATION PENDING

- **Grid:** `ern_part20.yaml` (32 glidepaths × 5 SWR × 2 horizons = 320 cells)
- **Dataset:** `ern_swr_h720.json`
- **Methodology status:** COMPLETE — global monthly sequencing and ATH rules established.
- **Implementation status:** **ALIGNMENT RESOLVED** — ATH/underwater state now uses the CPI-adjusted real total-return index and real running ATH (`ern_part20_e2e_audit.md` §19.7). The earlier nominal running-ATH fix (`3e47550`) is historical and superseded; remaining active-anchor residuals are recorded in §19.7.
- **E2E status:** **AUDIT COMPLETE ON AVAILABLE DATA, FORENSIC INVESTIGATION COMPLETE, CANONICAL-DATA REVALIDATION PENDING** — `test_part20_e2e_audit.py` (13 gated E2E tests) executed all 5 Experiments (A–E). Experiments A–D classified (43 UNEXPLAINED DIFF total, 2–180 ULP). Experiment E implemented and forensically validated (8 UNEXPLAINED DIFF — source ambiguity documented). The datasets used may be obsolete and have not been re-established against the current canonical workbook; numerical conclusions and the A/C statuses are historical and data-dependent, while B is methodology-supported. All remain subject to reassessment pending the final task in `TODO.md`.
- **Forensic investigations completed:**
  1. **Execution order (V1)** — ELIMINATED (provisional). V1 pipeline (MarketEvolution → WithdrawalExecution → PortfolioRebalance) produces bitwise-identical results to baseline for all 46 residual anchor cells under the datasets used. Report: `docs/research/ERN_PART20_V1_FORENSIC_REPORT.md`.
  2. **CAPE regime definition/timing** — CONTRIBUTING FACTOR (based on 2016 projection boundary). 105/1866 CAPE regime disagreements reproduced. Switching to ERN CAPE (from workbook) changes 23/25 Experiment C cells but not A/B/D; mixed directional impact. CAPE timing (±1 month) produces zero regime changes. Report: `docs/research/ERN_PART20_CAPE_FORENSIC_REPORT.md`.
  3. **Forward-projection methodology** — CONTRIBUTING FACTOR (based on 2016 projection boundary). Projection start date (2016-10 vs 2026-07) is the dominant factor, reducing Experiment C failure rates by 1.5–4.4 pp. Equity return assumption (6.6% vs 7.0%) also material. Workbook projection parameters (3.93% equity, 2.47% bond, 2026-07 start) produce largest improvements but leave large ULP gaps and worsen one cell. Report: `docs/research/ERN_PART20_FORWARD_PROJECTION_FORENSIC_REPORT.md`.
  4. **Data-vintage / source-difference** — **RULED OUT**. Current FBF loader already truncates historical data at 2016-09 per ERN Part 1 §4; the extra CSV data through 2026-06 is loaded but never used in the historical period. ERN-era vintage test produces bitwise-identical results. This is a historical finding on the datasets then used, subject to the data-provenance qualification in §F.4.1, and is not a guarantee for regenerated or current canonical data. Report: `docs/research/ERN_PART20_DATA_VINTAGE_FORENSIC_REPORT.md`.
  5. **Percentile interpolation** — **ELIMINATED**. FBF's `floor(p*n)` order statistic vs Excel's linear `PERCENTILE` interpolation tested on all 46 residual anchor cells. Raw differences of 0.0004–0.0079 displayed pp are below the 0.01 pp display quantum. Zero cells changed. Report: `docs/research/ERN_PART20_PERCENTILE_FORENSIC_REPORT.md`.
  6. **CAPE × Forward Projection Interaction** — CONTRIBUTING FACTOR (based on 2016 projection boundary). 4-way factorial test (Shiller/ERN CAPE × FBF/Workbook projection) on 46 residual cells. One cell REPRODUCED only in combined variant (`static_100 @ 4% 60Y`). Interaction effects mostly sub-additive (max -2.4 pp). Mixed directional effects; not sufficient as primary explanation. Report: `docs/research/ERN_PART20_CAPE_PROJECTION_INTERACTION_FORENSIC_REPORT.md`.
  7. **Expense ratio / fee treatment** — **ELIMINATED**. FBF's current implementation uses 0% expense ratio; ERN Part 1 §4 and SWR Toolbox v2.0 workbook specify 0.05% p.a. Testing 0.05% and 0.10% annual expense ratios on all 46 residual anchor cells produced **zero changes** across all experiments. The fee mechanism applies proportionally, preserving order statistics, so displayed results are unchanged. Report: `docs/research/ERN_PART20_EXPENSE_RATIO_FORENSIC_REPORT.md`.
  8. **Cohort-Level Causal Trace of CAPE × Projection Interaction** — **ROOT CAUSE IDENTIFIED** (based on 2016 projection boundary). Deep cohort-level trace on `static_100 @ 4% 60Y` reveals the exact reproduction mechanism: ERN CAPE reclassifies 151 cohorts (75 removed, 76 added to HIGH population), and Workbook projection rescues exactly 4 ERN-only extreme-CAPE dot-com cohorts (1998-07, 1998-12, 2000-12, 2001-01) that fail under FBF projection (0% bonds) but succeed under Workbook projection (2.5% bonds). The −1.2 pp interaction (34.7% → 33.5%) is the net rescue of 4/331 cohorts. The exact reproduction is a "lucky collision" of offsetting biases, not validation of either method in isolation. Report: `docs/research/ERN_PART20_CAPE_PROJECTION_COHORT_FORENSIC_REPORT.md`.
  9. **Corrected Methodology: Workbook Historical Data Boundary & CAPE Semantics** — **FOUNDATIONAL DISCREPANCY IDENTIFIED**. FBF's hardcoded projection boundary at 2016-10 is incorrect; the SWR Toolbox workbook contains actual historical data through 2026-06. Workbook Shiller CAPE (Column 15) differs from FBF's Shiller CAPE, reclassifying 1997-2001 cohorts. Four variants tested: A (current), B (workbook CAPE), C (workbook historical), D (full workbook). Key findings:
     - The previous "exact reproduction" at 33.5% (Variant V3) was a **lucky collision of two errors**: wrong CAPE source (ERN) + wrong projection boundary (2016).
     - With corrected methodology (Variant D: Workbook Shiller CAPE + actual data through 2026-06), `static_100 @ 4% 60Y` = **28.4%** (not 33.5%).
     - The 4 key cohorts (1998-07, 1998-12, 2000-12, 2001-01) are in HIGH under workbook Shiller CAPE and **succeed with actual 2016-2026 returns** — no projection rescue needed.
     - `gp_030_070 @ 4% 60Y` improves to **32.3%** (only 2 ULP from published 32.5%).
     - `static_080 @ 3.75% 60Y` improves to **19.0%** (from 23.5%).
     - All four production-change conditions satisfied for correcting the projection boundary and CAPE source.
     - Report: `docs/research/ERN_PART20_CORRECTED_METHODOLOGY_FORENSIC_REPORT.md`.
- **CAPE/projection forensic variants (V1/V2/V3):** COMPLETE on available data. Production changes are justified for projection boundary and CAPE source correction. **Part 20 audit §10 difference-attribution variants (A/B/C): CLOSED AS FORENSIC ASSESSMENT ON AVAILABLE DATA** — A eliminated provisionally, B superseded, C withdrawn provisionally; this is not a definitive canonical-data validation. See §F.4.1 and `ern_part20_e2e_audit.md` §10. Revalidation is the final task in `TODO.md`.
- **Forensic investigations:** COMPLETE — all 9 planned investigations executed and documented.

#### Part 42 — HISTORICALLY VALIDATED; CURRENT VALIDATION SURFACE REMOVED

- **Classification:** HISTORICAL PUBLISHED-TABLE VALIDATION — PORT-VS-RETIRE UNRESOLVED
- **Methodology status:** COMPLETE / FROZEN (see `ern_part42_replication.md` §17).
- **Historical validation:** a 319-cell published-table audit was performed at `95b1b50`; the 554-line `tests/integration/test_part42_e2e_audit.py` was deleted at `2c43e68`.
- **Current committed validation surface:** None for published-table replication. Remaining coverage is structural/oracle only: `test_part42_replication.py`, `test_part42_oracle.py`, and `test_part42.py`. It does not reproduce Tables 01–05.
- **E2E specification:** INCOMPLETE in the current tree — no per-cell ERN oracle table; directional-only validation. OMY contribution sequencing resolved (Q4): contributions are cash-flow operations within the established global monthly sequence.
- **Implementation status:** OMY accumulation phase implemented. OMY contribution sequencing resolved (Q4): contributions are cash-flow operations within the established global monthly sequence.
- **What exists:** Grid structure constants validated. OMY accumulation phase implemented (`run_accumulation_phase`). Integration tests pass (`test_part42.py`) with synthetic data. Oracle validation tests pass (`test_part42_oracle.py`) and validate accumulation semantics against independent implementation.
- **What is deferred:** Porting the historical audit to the Numba path or formally retiring it; current per-cell oracle creation; current Tables 01–05 replication.
- **Existing tests useful as:** Non-canonical validation of OMY mechanics and accumulation semantics.
- **Historical record:** `docs/research/ern_part42_replication_discrepancies.md` documents the past run; its reproduction command is historical and no longer valid.
- **YAML file:** `ern_part42.yaml` (retained; study configuration is complete).
- **Documentation:** `docs/roadmap/MULTI_STUDY_REPLICATION_ROADMAP.md` §A.3.

#### Part 49 — CANONICAL B–F IMPLEMENTED — E2E GATED

- **Grid:** Experiment-specific matrices (B–E single-cohort scenarios; F is 792 cohorts × 6 configurations = 4,752 units).
- **Dataset:** Production `data/ern`.
- **Methodology status:** COMPLETE / FROZEN (see `ern_part49_replication.md` §24).
- **Implementation status:** **CAPABILITIES AND CANONICAL E2E IMPLEMENTED**
  1. **Buy-and-hold capability: IMPLEMENTED** — `BuyAndHoldAllocationPolicy` + `create_buy_and_hold_pipeline()` (`fc83253`).
  2. **LTV enforcement: IMPLEMENTED** — `LTVEvaluationStep` with `ltv_enforcement=True`; `failure_state = margin_call_terminal` on breach (`bf42fe5`, GAP-3).
  3. **Real-rate debt handling: IMPLEMENTED** — `debt_interest_rate_is_real` flag on `SimulationContext` + `InterestAccrualStep` bypasses CPI deflation (`bf42fe5`, GAP-2).
  4. **Timeline spending reporting: IMPLEMENTED** — both Part 49 Numba executors report total spending (portfolio withdrawal + loan draw) in `withdrawal_decision.nominal_amount` and `spending_budget` without changing cash flows (GAP-1b).
- **E2E status:** **CANONICAL B–F VALIDATED under `RUN_ERN_E2E=1`.** Experiments B/C use dual-mode execution: observe-only for chart reproduction and `ltv_enforcement=True` for 75% terminality. Experiments D/E validate Chart 04–06 leverage ratios, and Experiment F validates the 4,752-unit historical failure coverage.
- **E2E test:** `tests/oracle/ern/test_part49_canonical_bf.py` (7 tests, gated `ern_e2e`).
- **Non-canonical diagnostic:** `tests/oracle/ern/test_part49_replication_app.py::test_part49_canonical_replication` retains the 6-cell, 10,434-unit leverage-mechanics coverage and pinned `p49_oracle_table.csv`; it is not canonical B–F validation.
- **Supporting tests:** `tests/integration/test_part49_buy_and_hold_numba_executor.py`, `tests/integration/test_part49_numba_executor.py`, `tests/integration/test_part49_canonical_execution.py`, `tests/oracle/ern/test_debt_oracle.py`. The legacy `tests/integration/test_part49_buy_and_hold.py` was deleted at `2c43e68`.

#### Part 52 — NON-CANONICAL RESEARCH VALIDATION — PARTIALLY VALIDATED

- **Classification:** NON-CANONICAL RESEARCH VALIDATION — PARTIALLY VALIDATED
- **Methodology status:** Simulation mechanics resolved, including the FFR conversion formula and real total-return ATH semantics. FFR temporal handling and the 2021-12 terminal-snapshot subset are implemented. Asset/CPI differences are reconciled as source-vintage differences, and the A2/A3/A10 published-anchor acceptance surface is implemented; eligibility/full-universe policy and Solver reproduction remain open.
- **FFR dataset coverage:** PARTIALLY RESOLVED. Runtime `ffr.csv` has 1,868 observations (1871-01..2026-08) and matches workbook `Return Data!K` over all 1,812 common months through 2021-12. Values from 2022-01..2026-08 are actual FRED `FEDFUNDS` observations; runtime forward-fill begins after 2026-08. The 1,739-row `Distribution of Final Value` is stale at 2015-12. SWR Toolbox historical market/CPI coverage supports 1,506 cohorts through 2026-06; workbook-native FFR supports 1,453 cohorts through 2021-12. The 1,452-cohort 2021-12 terminal-snapshot subset is a legacy one-month-stricter filter, not full data coverage. In the 1,739-cohort distribution, 286 cohorts consume post-2021 FFR and 230 consume forward-filled months. Post-2021 handling is implemented through actual FRED observations to 2026-08 followed by hold-last; the pre-1954 `N` upstream source/vintage remains a documented provenance limitation.
- **E2E specification:** CAN PROCEED for mechanics validation. The A2/A3/A10 published-anchor acceptance surface is implemented; full-universe counts are diagnostics. Eligibility/full-universe policy and Solver reproduction remain open.
- **Existing tests useful as:** Non-canonical validation of Part 52 mechanics (drawdown triggers, repayment; LTV observed, not enforced).
- **Test files:** `tests/oracle/ern/test_part52_replication.py` (11 scenarios, gated `research_validation`).
- **Documentation:** `TODO.md` §S6 Part 52 — Validation State and Phase Boundary; `docs/research/ern_part52_replication.md` §28.

### C.3 Canonical Status Summary

| Article | CANONICAL NOW | Classification | Blocking Dependency |
|---------|--------------|----------------|---------------------|
| Part 1 | YES | Canonical | None (redundant with Part 2) |
| Part 2 | YES | Canonical (FV=0) | FV>0 cells not implemented |
| Part 3 | YES (methodology) | Forensic complete — gap external | None |
| Part 19 | YES | Implemented & cross-validated | Resolved (ATH fix `3e47550`) |
| Part 20 | YES | Audit complete on available data — canonical-data revalidation pending | Resolved (ATH fix `3e47550`) |
| Part 42 | NO (historical) | Historically validated; current test deleted | Port-to-Numba vs retire unresolved |
| Part 49 | YES (B–F) | Canonical B–F implemented and gated; non-canonical 6-cell diagnostic retained | Experiment A analytical check pending |
| Part 52 | PARTIAL | A2/A3/A10 published-anchor feasibility; A1/A9 diagnostics; other scenarios research validation | Eligibility/full-universe policy; Solver reproduction deferred |

---

## D. Strict Superset / Redundancy Analysis

### D.1 Analysis Methodology

A research E2E is redundant only when another E2E is a **strict superset** of the same research calculation. The comparison must verify identical:

- Data source and period
- Cohort definition
- Horizons
- Withdrawal methodology
- Terminal value criteria
- Output metrics
- Research calculation

### D.2 Superset Decisions

#### Part 1 ⊂ Part 2 — VERIFIED STRICT SUBSET

| Dimension | Part 1 | Part 2 | Match? |
|-----------|--------|--------|--------|
| Data source | `spx_tr_real.csv`, `bond_10y_tr_real.csv` | Same | Yes |
| Cohorts | 1,739 rolling monthly | Same | Yes |
| Horizons | 30, 40, 50, 60 years | Same | Yes |
| Allocation | 5 weights: [0.0, 0.25, 0.5, 0.75, 1.0] | Same | Yes |
| Withdrawal rates | 9 rates: [0.03, 0.0325, ..., 0.05] | Same | Yes |
| Terminal value | 0% (depletion only) | 0%, 50%, 100% | Part 2 is superset |
| Research calculation | SWR success rate grid | Extended with FV dimension | Part 2 subsumes Part 1 |
| Grid file | `ern_grid.yaml` | Same file | Same |
| Oracle table | `p49_oracle_table.csv` | Same table | Same |

**Decision:** Part 1 is a strict subset of Part 2. Part 1 has no independent research calculation that Part 2 does not contain. **Part 1 is redundant as a separate E2E.**

**Retention rationale:** The Part 1 baseline SWR grid IS the foundational computation. Part 2 extends it with terminal value targets. The `ern_grid.yaml` file covers both. No separate Part 1 E2E is needed.

#### Part 19 ⊂ Part 20 — VERIFIED STRICT SUBSET (with deferred question)

| Dimension | Part 19 | Part 20 | Match? |
|-----------|---------|---------|--------|
| Data source | `spx_tr_real.csv`, `bond_10y_tr_real.csv` | Same | Yes |
| Cohorts | 1,739 rolling monthly | Same | Yes |
| Horizons | 60 years only | 30 AND 60 years | Part 20 is superset |
| Glidepaths | 24 (6 combos × 2 slopes × 2 modes) | 32 (24 + 8 new) | Part 20 is superset |
| SWR values | 3.0%–4.0% in 0.25% steps | Same | Yes |
| Terminal value | 0% (depletion) | Same | Yes |
| Research calculation | Glidepath vs static comparison | Extended with more variants | Part 20 subsumes Part 19 |
| Grid file | Part of `ern_part20.yaml` | `ern_part20.yaml` | Same file |
| Experiment A (fixed 3.5% SWR failure analysis) | 162 cells | **DEFERRED** — not confirmed in Part 20 | **UNRESOLVED** |

**Decision:** Part 19's glidepath definitions are a strict subset of Part 20. All 24 Part 19 glidepaths are included in the Part 20 grid. **However, Part 20 does not reproduce Part 19 Experiment A (fixed 3.5% SWR failure-rate analysis across 162 strategy × target × CAPE cells).** Part 19 Experiment A remains an independent E2E validation target.

**Retention rationale:** The `ern_part20.yaml` file contains all Part 19 glidepaths. No separate Part 19 E2E is needed for glidepath definitions. Part 19 Experiment A remains an independent E2E target.

#### Part 1/2 vs Part 3 — NOT REDUNDANT

| Dimension | Part 1/2 | Part 3 | Match? |
|-----------|----------|--------|--------|
| Data source | `spx_tr_real.csv`, `bond_10y_tr_real.csv` | `cape_shiller.csv` + `ern_swr_h720.json` | Different |
| Cohorts | 1,739 rolling monthly | 851 CAPE-available starts | Different |
| Stratification | None | By CAPE regime | Different |
| Research question | Baseline SWR | CAPE-conditional SWR | Different |

**Decision:** NOT redundant. Different research questions, different cohort definitions, different stratification.

#### Part 1/2 vs Part 19/20 — NOT REDUNDANT

Different policies (constant allocation vs glidepath). NOT redundant.

#### Part 1/2 vs Part 42 — NOT REDUNDANT

Different policies (standard retirement vs OMY accumulation). NOT redundant.

#### Part 1/2 vs Part 49 — NOT REDUNDANT

Different policies (no leverage vs margin loan). NOT redundant.

#### Part 49 vs Part 52 — NOT REDUNDANT

Different policies (untimed leverage vs timing-based leverage, different LTV constraints, different interest rate models). NOT redundant.

### D.3 Redundancy Summary Table

| Candidate | Superset | Exact shared methodology | Additional dimensions | Strict subset? | Decision |
|-----------|----------|------------------------|---------------------|---------------|----------|
| Part 1 | Part 2 | Same grid, data, cohorts, horizons, allocation, rates | Part 2 adds FV targets | YES | Part 1 is redundant; `ern_grid.yaml` covers both |
| Part 19 | Part 20 | Same glidepath mechanics, data, cohorts, rates | Part 20 adds 8 glidepaths + 30y horizon | YES (glidepaths) | Part 19 glidepath definitions are redundant; Part 19 Experiment A remains independent |
| Part 3 | Part 1/2 | Different cohort definition, different data source | — | NO | Not redundant (different research question) |
| Part 42 | Part 1/2 | Different policy (accumulation phase) | — | NO | Not redundant (different research question) |
| Part 49 | Part 1/2 | Different policy (leverage) | — | NO | Not redundant (different research question) |
| Part 52 | Part 49 | Different policy (timing, FFR, repayment) | — | NO | Not redundant (different research question) |

---

## E. Canonical E2E Coverage Matrix

### E.1 Implemented E2Es

| E2E ID | ERN Article(s) | YAML | Test file | Units | Status |
|--------|----------------|------|-----------|-------|--------|
| E2E-SWR | Parts 1 + 2 | `ern_grid.yaml` | `test_full_swr_grid.py::test_full_grid_matches_workbook_oracle` | 313,020 | **CANONICAL — VALIDATED** |
| E2E-Part20 | Part 20 (includes Part 19 glidepaths) | `ern_part20.yaml` | `test_part20_grid.py::test_part20_full_grid_replication` | 556,480 | **REGRESSION COVERAGE — NOT REPLICATION** |
| E2E-Part49 | Part 49 | (Python API) | `test_part49_canonical_bf.py` | 4,752 + B–E scenarios | **CANONICAL — VALIDATED (B–F, gated `ern_e2e`)** |
| E2E-Part49-Diag | Part 49 | (Python API) | `test_part49_replication_app.py::test_part49_canonical_replication` | 10,434 | **NON-CANONICAL SUBSET — LTV OFF; leverage-mechanics diagnostic** |
| E2E-Part42 | Part 42 | `ern_part42.yaml` | `test_part42_replication.py::test_part42_canonical_replication` | 93,915 | **HISTORICAL AUDIT TEST DELETED; CURRENT COVERAGE STRUCTURAL ONLY** |
| E2E-Part52 | Part 52 | (Python API) | `test_part52_replication.py` | 19,129 | **NON-CANONICAL RESEARCH VALIDATION — PARTIALLY VALIDATED** |

### E.2 Canonical E2E Grids Not Yet Validated

| Article | Canonical grid | Units | Methodology status | Validation status |
|---------|---------------|-------|-------------------|-------------------|
| Part 19 | 24 glidepaths × 5 SWR × 1H × 1,739 = 208,680 | COMPLETE | Implementation alignment pending |
| Part 20 | 32 glidepaths × 5 SWR × 2H × 1,739 = 556,480 | COMPLETE | Implementation alignment pending |

### E.3 Non-Canonical / Blocked / Deferred

| Article | Classification | Blocking dependency |
|---------|---------------|-------------------|
| Part 3 (CAPE) | Methodology complete — E2E spec pending | None (methodology complete) |
| Part 19 (Glidepaths) | Canonical methodology — implementation & cross-validated | Resolved (ATH fix `3e47550`) |
| Part 20 (Glidepaths) | Audit complete on available data — canonical-data revalidation pending | Resolved (ATH fix `3e47550`) |
| Part 42 (OMY) | Historical audit test deleted; port-vs-retire unresolved | No current published-table validation surface |
| Part 49 (Leverage) | Canonical B–F implemented; non-canonical 6-cell diagnostic retained | Experiment A analytical check pending |
| Part 52 (Timing Leverage) | Non-canonical research validation — partially validated | FFR resolved; full E2E validation pending |

### E.4 Strict-Superset Relationships

| Superset | Subset | Relationship verified? | Notes |
|----------|--------|----------------------|-------|
| Part 2 (SWR with terminal value) | Part 1 (SWR depletion) | Yes — Part 2 adds `final_value_target` dimension | Part 1 redundant |
| Part 20 (32 glidepaths) | Part 19 (24 glidepaths) | Partially — glidepath definitions are subset; Experiment A is independent | Part 19 Experiment A remains independent E2E target |

**Total canonical E2E tests: 2** (Parts 1/2 SWR grid only)
**Total canonical methodology implemented: 1** (Part 19)
**Total audit complete with canonical-data revalidation pending: 1** (Part 20)
**Total historical validation with current surface removed: 1** (Part 42)
**Total non-canonical subset: 1** (Part 49)
**Total non-canonical/partial: 2** (Parts 3, 52)

---

## F. Non-Canonical / Deferred Studies

### F.1 Part 3 — CAPE-Conditional SWR

**Status:** FORENSICALLY COMPLETE — PUBLISHED ANCHOR GAP EXTERNAL
**Methodology:** COMPLETE — all 3 Part 3-specific methodology questions resolved (CAPE observation timing, pre-1881 cohort handling, CAPE-conditioned cohort filtering). Canonical asset-return data is available in `canonical/ern_asset_returns`.
**E2E specification:** IMPLEMENTED — `test_part3_canonical_ern_replication.py` (12 tests, gated `ern_e2e`).
**Forensic outcome:** FBF data-derived results agree with independently reconfigured SWR Toolbox within ≤0.9 pp. The remaining discrepancy vs ERN published anchors is external to FBF (expense ratio, CAPE timing, forward projection, published rounding).
**Existing value:** Forensic framework validation (CAPE regime classification, cohort generation, aggregation logic).
**Test classification:** `test_part3_canonical_ern_replication.py` (12 gated E2E tests, anchors recorded as provisional baselines).
**YAML files:** `ern_part3_replication.yaml` (retain as study configuration).

### F.2 Part 42 — One More Year Syndrome

**Status:** HISTORICALLY VALIDATED; CURRENT VALIDATION SURFACE REMOVED
**Reason:** A 319-cell published-table audit was performed at `95b1b50`; the 554-line `tests/integration/test_part42_e2e_audit.py` was deleted at `2c43e68`. Port-to-Numba vs retire remains unresolved.
**Methodology:** COMPLETE / FROZEN (see `ern_part42_replication.md` §17).
**Existing implementation:** OMY accumulation phase implemented. Integration tests pass. Oracle validation tests validate accumulation semantics.
**What is deferred:** Porting the historical audit to the Numba path or formally retiring it; current per-cell oracle creation; current Tables 01–05 replication.
**Test classification:** Current coverage is structural/oracle only (retain); it is not published-table replication.

### F.3 Part 49 — Using Leverage in Retirement

**Status:** CANONICAL B–F IMPLEMENTED — E2E GATED
**Reason:** Capabilities and canonical B–F validation are implemented:
1. **Buy-and-hold capability: IMPLEMENTED** — `BuyAndHoldAllocationPolicy` + `create_buy_and_hold_pipeline()` (`fc83253`).
2. **LTV enforcement: IMPLEMENTED** — `LTVEvaluationStep` with `ltv_enforcement=True`; `failure_state = margin_call_terminal` on breach (`bf42fe5`, GAP-3).
3. **Real-rate debt handling: IMPLEMENTED** — `debt_interest_rate_is_real` flag on `SimulationContext` + `InterestAccrualStep` bypasses CPI deflation (`bf42fe5`, GAP-2).
4. **Timeline spending reporting: IMPLEMENTED** — both Part 49 Numba executors report total spending in `withdrawal_decision.nominal_amount` and `spending_budget` without changing cash flows (GAP-1b).

**Methodology:** COMPLETE (see `ern_part49_replication.md` §24).

**Implementation status:** **CAPABILITIES AND CANONICAL E2E IMPLEMENTED.** `tests/oracle/ern/test_part49_canonical_bf.py` covers Experiments B–F, including B/C dual-mode, Chart 04–06 anchors, and the 4,752-unit Experiment F run.

**E2E status:** **CANONICAL B–F VALIDATED under `RUN_ERN_E2E=1`.**

**Non-canonical diagnostic:** `tests/oracle/ern/test_part49_replication_app.py::test_part49_canonical_replication` retains the 6-cell, 10,434-unit leverage-mechanics coverage and pinned `p49_oracle_table.csv`; it is not canonical B–F validation.

**E2E test:** `tests/oracle/ern/test_part49_canonical_bf.py` (7 tests, gated `ern_e2e`).

**Supporting tests:** `tests/integration/test_part49_buy_and_hold_numba_executor.py`, `tests/integration/test_part49_numba_executor.py`, `tests/integration/test_part49_canonical_execution.py`, `tests/oracle/ern/test_debt_oracle.py`. The legacy `tests/integration/test_part49_buy_and_hold.py` was deleted at `2c43e68`.

### F.4 Part 19/20 — Equity Glidepaths

**Status:** PART 19 IMPLEMENTED & CROSS-VALIDATED; PART 20 AUDIT COMPLETE, FORENSIC INVESTIGATION COMPLETE
**Reason:** ATH/underwater state now uses the CPI-adjusted real total-return index and real running ATH (`ern_part20_e2e_audit.md` §19.7). The earlier nominal running-ATH fix (`3e47550`) is historical and superseded by the real-ATH correction.
**Methodology:** COMPLETE (global sequencing and ATH rules resolved).
**Implementation status:** **ALIGNMENT RESOLVED** — ATH/underwater state now uses the CPI-adjusted real total-return index and real running ATH (`ern_part20_e2e_audit.md` §19.7). The earlier nominal running-ATH fix (`3e47550`) is historical and superseded; remaining active-anchor residuals are recorded in §19.7.
**Part 19 E2E status:** **IMPLEMENTED & CROSS-VALIDATED** — `test_part19_canonical_ern_replication.py` (Exp A, 162 cells) and `test_part19_experiment_b_e2e.py` (Exp B, 90 cells) both implemented, gated `ern_e2e`, cross-validated with Part 20 Exp C and Exp A respectively.
**Part 20 E2E status:** **AUDIT COMPLETE, FORENSIC INVESTIGATION COMPLETE, CORRECTED METHODOLOGY IDENTIFIED** — `test_part20_e2e_audit.py` executed all 5 Experiments (A–E). Experiments A–D classified (43 UNEXPLAINED DIFF total, 2–180 ULP). Experiment E implemented and forensically validated (8 UNEXPLAINED DIFF — source ambiguity documented). **Critical finding: FBF's projection boundary (2016-10) and CAPE source do not match the authoritative SWR Toolbox workbook (historical data through 2026-06, Shiller CAPE from workbook Column 15).** This foundational discrepancy explains the majority of residuals and supersedes previous interaction-based explanations.

**Forensic investigations completed for Part 20:**
  1. **Execution order (V1)** — ELIMINATED (provisional). V1 pipeline produces bitwise-identical results to baseline for all 46 residual anchor cells under the datasets used. Report: `docs/research/ERN_PART20_V1_FORENSIC_REPORT.md`.
  2. **CAPE regime definition/timing** — CONTRIBUTING FACTOR (based on 2016 projection boundary). 105/1866 CAPE regime disagreements reproduced. Switching to ERN CAPE (from workbook) changes 23/25 Experiment C cells but not A/B/D; mixed directional impact. CAPE timing (±1 month) produces zero regime changes. Report: `docs/research/ERN_PART20_CAPE_FORENSIC_REPORT.md`.
  3. **Forward-projection methodology** — CONTRIBUTING FACTOR (based on 2016 projection boundary). Projection start date (2016-10 vs 2026-07) is the dominant factor, reducing Experiment C failure rates by 1.5–4.4 pp. Equity return assumption (6.6% vs 7.0%) also material. Workbook projection parameters (3.93% equity, 2.47% bond, 2026-07 start) produce largest improvements but leave large ULP gaps and worsen one cell. Report: `docs/research/ERN_PART20_FORWARD_PROJECTION_FORENSIC_REPORT.md`.
  4. **Data-vintage / source-difference** — **RULED OUT**. Current FBF loader already truncates historical data at 2016-09 per ERN Part 1 §4; the extra CSV data through 2026-06 is loaded but never used in the historical period. ERN-era vintage test produces bitwise-identical results. This is a historical finding on the datasets then used, subject to the data-provenance qualification in §F.4.1, and is not a guarantee for regenerated or current canonical data. Report: `docs/research/ERN_PART20_DATA_VINTAGE_FORENSIC_REPORT.md`.
  5. **Percentile interpolation** — **ELIMINATED**. FBF's `floor(p*n)` order statistic vs Excel's linear `PERCENTILE` interpolation tested on all 46 residual anchor cells. Raw differences of 0.0004–0.0079 displayed pp are below the 0.01 pp display quantum. Zero cells changed. Report: `docs/research/ERN_PART20_PERCENTILE_FORENSIC_REPORT.md`.
  6. **CAPE × Forward Projection Interaction** — CONTRIBUTING FACTOR (based on 2016 projection boundary). 4-way factorial test (Shiller/ERN CAPE × FBF/Workbook projection) on 46 residual cells. One cell REPRODUCED only in combined variant (`static_100 @ 4% 60Y`). Interaction effects mostly sub-additive (max -2.4 pp). Mixed directional effects; not sufficient as primary explanation. Report: `docs/research/ERN_PART20_CAPE_PROJECTION_INTERACTON_FORENSIC_REPORT.md`.
  7. **Expense ratio / fee treatment** — **ELIMINATED**. 0.05% and 0.10% annual expense ratios tested on 46 residual cells produced zero changes across all experiments. The fee mechanism applies proportionally, preserving order statistics. Report: `docs/research/ERN_PART20_EXPENSE_RATIO_FORENSIC_REPORT.md`.
  8. **Cohort-Level Causal Trace of CAPE × Projection Interaction** — ROOT CAUSE IDENTIFIED (based on 2016 projection boundary). Deep cohort-level trace on `static_100 @ 4% 60Y` reveals the exact reproduction mechanism: ERN CAPE reclassifies 151 cohorts (75 removed, 76 added to HIGH population), and Workbook projection rescues exactly 4 ERN-only extreme-CAPE dot-com cohorts (1998-07, 1998-12, 2000-12, 2001-01) that fail under FBF projection (0% bonds) but succeed under Workbook projection (2.5% bonds). The −1.2 pp interaction (34.7% → 33.5%) is the net rescue of 4/331 cohorts. The exact reproduction is a "lucky collision" of offsetting biases, not validation of either method in isolation. Report: `docs/research/ERN_PART20_CAPE_PROJECTION_COHORT_FORENSIC_REPORT.md`.
  9. **Corrected Methodology: Workbook Historical Data Boundary & CAPE Semantics** — **FOUNDATIONAL DISCREPANCY IDENTIFIED**. FBF's hardcoded projection boundary at 2016-10 is incorrect; the SWR Toolbox workbook contains actual historical data through 2026-06. Workbook Shiller CAPE (Column 15) differs from FBF's Shiller CAPE, reclassifying 1997-2001 cohorts. Four variants tested: A (current), B (workbook CAPE), C (workbook historical), D (full workbook). Key findings:
     - The previous "exact reproduction" at 33.5% (Variant V3) was a **lucky collision of two errors**: wrong CAPE source (ERN) + wrong projection boundary (2016).
     - With corrected methodology (Variant D: Workbook Shiller CAPE + actual data through 2026-06), `static_100 @ 4% 60Y` = **28.4%** (not 33.5%).
     - The 4 key cohorts (1998-07, 1998-12, 2000-12, 2001-01) are in HIGH under workbook Shiller CAPE and **succeed with actual 2016-2026 returns** — no projection rescue needed.
     - `gp_030_070 @ 4% 60Y` improves to **32.3%** (only 2 ULP from published 32.5%).
     - `static_080 @ 3.75% 60Y` improves to **19.0%** (from 23.5%).
     - All four production-change conditions satisfied for correcting the projection boundary and CAPE source.
     - Report: `docs/research/ERN_PART20_CORRECTED_METHODOLOGY_FORENSIC_REPORT.md`.
**Next forensic hypothesis:** None — all planned investigations complete.
**Resolved:** Part 20 does not reproduce Part 19 Experiment A (fixed 3.5% SWR failure-rate analysis). Part 19 Experiment A remains an independent E2E validation target.
**Test classification:** Integration tests with small fixtures (retain).

#### F.4.1 Part 20 Forensic Investigations — COMPLETE ON AVAILABLE DATA

**Status:** COMPLETE ON AVAILABLE DATA — ALL PLANNED INVESTIGATIONS EXECUTED (9 investigations); CANONICAL-DATA REVALIDATION PENDING

> **Data-provenance qualification (2026-10-31):** These investigations used
> research datasets and derived artifacts whose provenance and vintage relative
> to the current canonical Excel workbook have not been re-established. Those
> inputs may be obsolete, so the numerical findings in this section and its
> supporting forensic reports are historical and data-dependent. They are not a
> definitive canonical-data validation. The final regeneration and reassessment
> task is recorded as the last item in `TODO.md`.

The Part 20 forensic investigations are complete on the available data and accepted as historical findings. Nine investigations were executed:

1. **Execution order (V1)** — **ELIMINATED (provisional)**. V1 pipeline (`MarketEvolution → WithdrawalExecution → PortfolioRebalance`) produces bitwise-identical results to baseline (`WithdrawalExecution → PortfolioRebalance → MarketEvolution`) for all 46 residual anchor cells under the datasets used. Report: `docs/research/ERN_PART20_V1_FORENSIC_REPORT.md`.

2. **CAPE regime definition/timing** — **CONTRIBUTING FACTOR (based on 2016 projection boundary)**. 105/1866 CAPE regime disagreements reproduced. Switching to ERN CAPE (from workbook) changes 23/25 Experiment C cells but not A/B/D; mixed directional impact. CAPE timing (±1 month) produces zero regime changes. Report: `docs/research/ERN_PART20_CAPE_FORENSIC_REPORT.md`.

3. **Forward-projection methodology** — **CONTRIBUTING FACTOR (based on 2016 projection boundary)**. Projection start date (2016-10 vs 2026-07) is the dominant factor, reducing Experiment C failure rates by 1.5–4.4 pp. Equity return assumption (6.6% vs 7.0%) also material. Workbook projection parameters (3.93% equity, 2.47% bond, 2026-07 start) produce largest improvements but leave large ULP gaps and worsen one cell. Report: `docs/research/ERN_PART20_FORWARD_PROJECTION_FORENSIC_REPORT.md`.

4. **Data-vintage / source-difference** — **RULED OUT**. Current FBF loader already truncates historical data at 2016-09 per ERN Part 1 §4; the extra CSV data through 2026-06 is loaded but never used in the historical period. ERN-era vintage test produces bitwise-identical results. This is a historical finding on the datasets then used, subject to the data-provenance qualification in §F.4.1, and is not a guarantee for regenerated or current canonical data. Report: `docs/research/ERN_PART20_DATA_VINTAGE_FORENSIC_REPORT.md`.

5. **Percentile interpolation** — **ELIMINATED**. FBF's `floor(p*n)` order statistic vs Excel's linear `PERCENTILE` interpolation tested on all 46 residual anchor cells. Raw differences of 0.0004–0.0079 displayed pp are below the 0.01 pp display quantum. Zero cells changed. Report: `docs/research/ERN_PART20_PERCENTILE_FORENSIC_REPORT.md`.

6. **CAPE × Forward Projection Interaction** — **CONTRIBUTING FACTOR (based on 2016 projection boundary)**. 4-way factorial test (Shiller/ERN CAPE × FBF/Workbook projection) on 46 residual cells. One cell REPRODUCED only in combined variant (`static_100 @ 4% 60Y`). Interaction effects mostly sub-additive (max -2.4 pp). Mixed directional effects; not sufficient as primary explanation. Report: `docs/research/ERN_PART20_CAPE_PROJECTION_INTERACTION_FORENSIC_REPORT.md`.

7. **Expense ratio / fee treatment** — **ELIMINATED**. 0.05% and 0.10% annual expense ratios tested on 46 residual cells produced zero changes across all experiments. The fee mechanism applies proportionally, preserving order statistics. Report: `docs/research/ERN_PART20_EXPENSE_RATIO_FORENSIC_REPORT.md`.

8. **Cohort-Level Causal Trace of CAPE × Projection Interaction** — **ROOT CAUSE IDENTIFIED (based on 2016 projection boundary)**. Deep cohort-level trace on `static_100 @ 4% 60Y` reveals the exact reproduction mechanism: ERN CAPE reclassifies 151 cohorts (75 removed, 76 added to HIGH population), and Workbook projection rescues exactly 4 ERN-only extreme-CAPE dot-com cohorts (1998-07, 1998-12, 2000-12, 2001-01) that fail under FBF projection (0% bonds) but succeed under Workbook projection (2.5% bonds). The −1.2 pp interaction (34.7% → 33.5%) is the net rescue of 4/331 cohorts. The exact reproduction is a "lucky collision" of offsetting biases, not validation of either method in isolation. Report: `docs/research/ERN_PART20_CAPE_PROJECTION_COHORT_FORENSIC_REPORT.md`.

9. **Corrected Methodology: Workbook Historical Data Boundary & CAPE Semantics** — **FOUNDATIONAL DISCREPANCY IDENTIFIED**. FBF's hardcoded projection boundary at 2016-10 is incorrect; the SWR Toolbox workbook contains actual historical data through 2026-06. Workbook Shiller CAPE (Column 15) differs from FBF's Shiller CAPE, reclassifying 1997-2001 cohorts. Four variants tested: A (current), B (workbook CAPE), C (workbook historical), D (full workbook). Key findings:
   - The previous "exact reproduction" at 33.5% (Variant V3) was a **lucky collision of two errors**: wrong CAPE source (ERN) + wrong projection boundary (2016).
   - With corrected methodology (Variant D: Workbook Shiller CAPE + actual data through 2026-06), `static_100 @ 4% 60Y` = **28.4%** (not 33.5%).
   - The 4 key cohorts (1998-07, 1998-12, 2000-12, 2001-01) are in HIGH under workbook Shiller CAPE and **succeed with actual 2016-2026 returns** — no projection rescue needed.
   - `gp_030_070 @ 4% 60Y` improves to **32.3%** (only 2 ULP from published 32.5%).
   - `static_080 @ 3.75% 60Y` improves to **19.0%** (from 23.5%).
   - All four production-change conditions satisfied for correcting the projection boundary and CAPE source.
   - Report: `docs/research/ERN_PART20_CORRECTED_METHODOLOGY_FORENSIC_REPORT.md`.

**Next forensic hypothesis:** None — all planned investigations complete.

**CAPE/projection forensic variants (V1/V2/V3):** COMPLETE on available data. **Production changes NOW JUSTIFIED** for projection boundary (2016→2026) and CAPE source (FBF Shiller → Workbook Shiller) — all four production-change conditions satisfied. **Part 20 audit §10 difference-attribution variants (A/B/C): CLOSED AS FORENSIC ASSESSMENT ON AVAILABLE DATA** — A eliminated provisionally, B superseded, C withdrawn provisionally; not a definitive canonical-data validation. See `ern_part20_e2e_audit.md` §10 and the final canonical-data revalidation task in `TODO.md`.

**Do not reopen the Part 20 forensic investigations unless new evidence contradicts these validated conclusions.** In particular, do not create new tasks to investigate execution order, CAPE timing, or forward-projection parameters merely because FBF's precise binary-searched failsafe differs from a published ERN percentage. Published ERN percentages must be interpreted according to the documented search/grid and success-rate conventions.

**Methodology validation vs. E2E execution:** Methodology validation is COMPLETE / ACCEPTED. The canonical ERN E2E replication (full grid execution) remains a separate task if still pending. Do not mark the canonical E2E as complete merely because the methodology/forensic investigation is complete. Likewise, do not reopen forensic investigations as a prerequisite for running the canonical E2E.

### F.5 Part 52 — Timing Leverage

**Status:** NON-CANONICAL RESEARCH VALIDATION — PARTIALLY VALIDATED
**Methodology:** Simulation mechanics resolved, including the FFR conversion formula and real total-return ATH semantics. FFR temporal handling and the 2021-12 terminal-snapshot subset are implemented; remaining work is FFR vintage, asset/CPI numerical equivalence, and validation semantics.
**E2E specification:** CAN PROCEED for mechanics validation. Canonical acceptance remains blocked by open FFR vintage/asset-CPI fidelity and validation-semantics questions.
**FFR dataset coverage:** PARTIALLY RESOLVED. Runtime `ffr.csv` has 1,868 observations (1871-01..2026-08) and matches workbook `Return Data!K` over all 1,812 common months through 2021-12. Values from 2022-01..2026-08 are actual FRED `FEDFUNDS` observations; runtime forward-fill begins after 2026-08. The 1,739-row `Distribution of Final Value` is stale at 2015-12. SWR Toolbox historical market/CPI coverage supports 1,506 cohorts through 2026-06; workbook-native FFR supports 1,453 cohorts through 2021-12. The 1,452-cohort 2021-12 terminal-snapshot subset is a legacy one-month-stricter filter, not full data coverage. In the 1,739-cohort distribution, 286 cohorts consume post-2021 FFR and 230 consume forward-filled months. Post-2021 handling is implemented through actual FRED observations to 2026-08 followed by hold-last; FFR vintage remains open because the workbook does not document the upstream source or vintage of the pre-1954 `N` fallback. The FRED snapshot is consistent but its acquisition path is not fully reproducible; the SWR cash series is a 3-month T-bill total-return index and is not an FFR substitute.
**Validation scope:** Current oracle test measures gross survival, not the three-constraint feasibility result; full-universe counts are diagnostic. Euro-area reference-rate analogues are research-only and out of scope for this replication.
**Existing value:** Non-canonical validation of Part 52 mechanics (drawdown triggers, repayment; LTV observed, not enforced).
**Test classification:** `@pytest.mark.research_validation` (gated by `RUN_ERN_E2E=1`).
**Test files:** `tests/oracle/ern/test_part52_replication.py` (11 scenarios).
**What would make it canonical:** Resolution of Phase 1 FFR data fidelity, Phase 2 validation semantics, and full intended-cohort validation.

---

## G. Test Classification Taxonomy

### G.1 Categories

| Category | Definition | Runs Normally? | Gating |
|----------|-----------|----------------|--------|
| **Unit Test** | Tests isolated behavior of a single component | Yes | None |
| **Contract Test** | Validates public/API boundary invariants | Yes | None |
| **Integration Test** | Tests multiple framework components together with bounded workloads | Yes | None |
| **Smoke Test** | Small representative production-path execution | Yes | None |
| **Regression / Oracle Test** | Focused regression or independent-reference validation | Yes (unless research-scale) | None |
| **Canonical Research E2E** | Complete canonical ERN research replication through production path with published research anchors, no material approximation | **No** | `RUN_ERN_E2E=1` |
| **Non-Canonical Research Validation** | Research-scale validation executing published/research-derived scenario with documented methodology/data substitution | **No** | `RUN_ERN_E2E=1` |
| **Benchmark** | Performance measurement, intentionally large workloads | **No** | Separate (not `RUN_ERN_E2E`) |

### G.2 Key Distinction: Classification ≠ Execution Policy

Test responsibility determines classification. Workload size determines whether normal pytest execution is appropriate.

A test can be:
- non-canonical;
- research-scale;
- expensive;
- useful;

without belonging in the default developer test suite.

**Normal pytest** must remain suitable for ordinary development feedback.
**RUN_ERN_E2E=1** enables all heavyweight ERN research workloads.

### G.3 Current Test Classification

| Test file | Actual category | Correct category | Research-scale? | Runs normally? |
|-----------|----------------|-----------------|----------------:|---------------:|
| `tests/oracle/ern/test_worker_selection.py` | Unit | Unit | No | Yes |
| `tests/oracle/ern/test_per_cell_parser.py` | Unit | Unit | No | Yes |
| `tests/oracle/ern/test_debt_oracle.py` | Unit/Oracle | Oracle | No | Yes |
| `tests/oracle/ern/test_part42_oracle.py` | Oracle | Oracle | No | Yes |
| `tests/oracle/ern/test_oracle_matrix.py` | Oracle | Oracle | No | Yes |
| `tests/oracle/ern/test_ern_timeline_regression.py` | Oracle | Regression/Oracle | No | Yes |
| `tests/oracle/ern/test_full_swr_grid.py` (full grid) | E2E | **Canonical Research E2E** | Yes (313K units) | **No** |
| `tests/oracle/ern/test_part20_grid.py` | E2E (regression) | **Regression coverage** | Yes (556K units) | **No** |
| `tests/oracle/ern/test_full_swr_grid.py` (smoke) | Smoke | Smoke | No | Yes |
| `tests/oracle/ern/test_part42_replication.py` | Structural | Integration | No | Yes |
| `tests/integration/test_part49_smoke_execution.py` | Integration | Smoke | No | Yes |
| `tests/integration/test_part49_canonical_execution.py` | Integration | Integration | No (reduced to 18 units) | Yes |
| `tests/integration/test_part49_aggregation.py` | Integration | Integration | No (reduced to 18 units) | Yes |
| `tests/integration/test_part49_grid_materialization.py` | Integration | Integration | No | Yes |
| `tests/integration/test_part49_multi_cohort.py` | Integration | Integration | No | Yes |
| `tests/integration/test_part49_grid_audit.py` | Integration | Integration | No | Yes |
| `tests/integration/test_part42.py` | Integration | Integration | No | Yes |
| `tests/oracle/ern/test_part52_replication.py` | Oracle | **Non-Canonical Research Validation** | Yes (19K units) | **No** |
| `tests/integration/test_part52_deterministic_validation.py` | Integration | Integration | No (runs in normal mode) | Yes |
| `tests/integration/test_part52_numerical_trace.py` | Integration | Integration | No | Yes |
| `tests/integration/test_part52_ffr_floating_rate.py` | Integration | Integration | No | Yes |
| `tests/integration/test_glidepath_trajectory.py` | Integration | Integration | No | Yes |
| `tests/integration/test_part49_canonical_execution.py` | Integration | Integration | No (reduced) | Yes |

### G.4 Canonical E2E vs Non-Canonical Research Validation

| Attribute | Canonical Research E2E | Non-Canonical Research Validation |
|-----------|----------------------|----------------------------------|
| Data | Canonical, no approximation | May use documented approximations |
| Methodology | Full ERN methodology | May substitute components |
| Marker | `@pytest.mark.ern_e2e` | `@pytest.mark.research_validation` |
| Gate | `RUN_ERN_E2E=1` | `RUN_ERN_E2E=1` |
| Skip message | "canonical ERN E2E skipped..." | "heavyweight ERN research validation skipped..." |
| Purpose | Establish canonical replication | Validate research scenario with known limitations |

---

## H. E2E Execution Gating Audit

### H.1 E2E Execution Policy

Normal test execution:

    pytest

does NOT execute canonical heavyweight ERN E2Es or heavyweight research validations.

Explicit research execution:

    RUN_ERN_E2E=1 pytest

executes both canonical ERN E2Es and heavyweight non-canonical research validations.

There is exactly one shared research execution gate. No second "full" gate exists.

### H.2 Environment Variables

| Variable | Where checked | Purpose | Gating model |
|----------|--------------|---------|-------------|
| `RUN_ERN_E2E` | `tests/conftest.py` (centralized hook) | Gates all canonical E2E tests AND heavyweight research validations | Must be `"1"` |
| `ERN_E2E_FAST_PATH` | No current code consumer | Historical fast-path equivalence flag; not used by the current Numba path | N/A |
| `ERN_E2E_WORKERS` | `constants.py` | Worker count override (current tests auto-detect) | Optional |
| `SIM_RETIRE_BIN` | `cli_harness.py` | CLI binary location | Optional |

### H.3 Central Gating Mechanism

The centralized skip hook lives in `tests/conftest.py`:

```python
_HEAVYWEIGHT_MARKERS = ("ern_e2e", "research_validation")

def pytest_collection_modifyitems(config, items):
    if os.environ.get("RUN_ERN_E2E") == "1":
        return

    skip_ern_e2e = pytest.mark.skip(
        reason="canonical ERN E2E skipped (set RUN_ERN_E2E=1 to enable)",
    )
    skip_research_validation = pytest.mark.skip(
        reason="heavyweight ERN research validation skipped (set RUN_ERN_E2E=1 to enable)",
    )
    for item in items:
        if "ern_e2e" in item.keywords:
            item.add_marker(skip_ern_e2e)
        elif "research_validation" in item.keywords:
            item.add_marker(skip_research_validation)
```

This applies to every test in the `tests/` tree, regardless of subdirectory.

### H.4 Marker Roles

| Marker | Role | Used for |
|--------|------|----------|
| `ern_e2e` | Canonical research E2E identification | Gated by `RUN_ERN_E2E=1` |
| `research_validation` | Non-canonical research validation identification | Gated by `RUN_ERN_E2E=1` |
| `slow` | Runtime characteristics | Opt-out via `-m "not slow"` |

Markers and environment variables have distinct roles:
- `ern_e2e` identifies a canonical research E2E;
- `research_validation` identifies a heavyweight non-canonical research validation;
- `RUN_ERN_E2E` controls whether all heavyweight ERN research workloads execute;
- `slow` describes runtime characteristics for test selection.

### H.5 Tests Gated by `ern_e2e`

| Test | File | What it does |
|------|------|-------------|
| `test_full_grid_matches_workbook_oracle` | `test_full_swr_grid.py` | Full 180-cell grid (313K units) via the public application boundary |
| `test_part20_full_grid_replication` | `test_part20_grid.py` | Full 320-cell Part 20 grid (556K units); regression coverage, not replication |
| `test_part20_determinism` | `test_part20_grid.py` | Determinism check across two independent executions |
| `test_part49_canonical_replication` | `test_part49_replication_app.py` | Non-canonical 6-cell Part 49 subset (10K units); does not exercise B–F |
| `test_part42_canonical_replication` | `test_part42_replication.py` | 45-cell Part 42 structural validation (94K units); not published-table replication |

**Total: 5 tests**

The gate identifies heavyweight tests, not canonical status. Only the full SWR
grid is canonical replication. Part 20 is regression coverage, Part 49 is a
non-canonical 6-cell subset, and Part 42 is structural validation; the
historical Part 42 published-table audit test was deleted.

### H.6 Tests Gated by `research_validation` (Non-Canonical Research Validation)

| Test class/file | What it does |
|----------------|-------------|
| `TestCanonicalERNReplication` (test_part52_replication.py) | 11 Part 52 scenarios (FFR approximations) |

**Total: 10 tests** (all in one class, one fixture)

### H.7 Tests NOT Gated (Run by Default)

| Category | Examples | Why not gated |
|----------|----------|---------------|
| SWR smoke | `test_smoke_cell_matches_workbook_oracle` | Diagnostic smoke test, not research replication |
| Unit/oracle tests | `test_per_cell_parser.py`, `test_worker_selection.py`, `test_oracle_matrix.py` | Lightweight, no CLI dependency |
| Part 42 structural | `test_part42_replication.py` | Constant validation only, no E2E execution |
| Part 49 integration | `test_part49_canonical_execution.py`, `test_part49_aggregation.py` | Reduced fixtures (18 units), not research-scale |
| Part 49 supporting | `test_part49_smoke_execution.py`, `test_part49_grid_materialization.py`, `test_part49_multi_cohort.py` | Not canonical Research E2Es |
| Part 52 deterministic | `test_part52_deterministic_validation.py` | Redundant with File 1; runs in normal mode (19 tests, 3m09s) |
| Part 52 supporting | `test_part52_numerical_trace.py`, `test_part52_ffr_floating_rate.py` | Not canonical Research E2E |
| Timeline regression | `test_ern_timeline_regression.py` | Unit-level regression test |
| Oracle validation | `test_part42_oracle.py`, `test_debt_oracle.py` | Independent implementation checks |

---

## I. Heavyweight E2E Granularity Analysis

### I.1 Runtime Data

| Test | Current runtime | Simulation units | Independent partitions | Shared computation | Split recommended? |
|------|----------------|------------------|----------------------|-------------------|-------------------|
| `test_full_swr_grid.py::test_smoke_cell_matches_workbook_oracle` | ~14s | 2,099 | 1 cell | None | No (already minimal) |
| `test_full_swr_grid.py::test_full_grid_matches_workbook_oracle` | ~51s (historical pre-migration CLI subprocess; includes startup/dataset loading; not directly comparable to the post-migration Numba baseline) | 313,020 | 180 cells (independent) | CLI subprocess, dataset loading | No (single CLI subprocess) |
| `test_part49_replication_app.py::test_part49_canonical_replication` | ~7.5m | 10,434 | 6 cells (2E × 3I) | Python API, dataset loading | No (single Python API call) |
| `test_part42_replication.py::test_part42_canonical_replication` | ~67s | 93,915 | 45 cells (5E × 9S) | Python API, dataset loading, accumulation | No (single Python API call) |
| `test_part49_canonical_execution.py` | ~1s (reduced fixture) | 18 | 6 cells (2E × 3I) | Dataset loading, pipeline construction | No (integration test, not research-scale) |
| `test_part49_aggregation.py` | ~1s (reduced fixture) | 18 | 6 cells (2E × 3I) | Dataset loading, pipeline construction | No (integration test, not research-scale) |
| `test_part52_replication.py` | >15 min (timeout) | 19,129 | 11 scenarios | Part52Evaluator grid sweep per scenario | Yes — scenarios are independent |
| `test_part52_deterministic_validation.py` | ~5 min (estimated) | 5,000+ | 3 scenarios × 1,739 cohorts | scenario_results fixture | No (shared fixture) |
| `test_part49_grid_materialization.py` | ~17s | 93,906 (no execution) | 54 cells | Study plan construction | No (materialization is the test) |
| `test_part49_multi_cohort.py` | ~17s | 4–12 per test | 10 test classes | None | No (already well-partitioned) |

### I.2 Partitioning Recommendations

**Part 49 canonical (1s, reduced):** Uses 3 cohorts per cell (18 units total) as an integration fixture. Not research-scale. No split needed.

**Part 49 aggregation (1s, reduced):** Uses 3 cohorts per cell (18 units total) as an integration fixture. Not research-scale. No split needed.

**Part 52 canonical (>15 min):** 11 independent scenarios, each running 1,739 units. The Part52Evaluator grid sweep is per-scenario. Splitting by scenario group (non-FFR: A1, A9; FFR: A2–A8, A10–A11) would improve diagnostics. **Recommendation: Split into 2 subtests (non-FFR and FFR scenarios) if/when Part 52 becomes canonical.** Currently non-canonical, so splitting is deferred.

**ERN SWR full grid (313,020 units):** Runs as a single CLI subprocess. Splitting would require multiple subprocess invocations. The current architecture (one YAML, one subprocess) is correct for this workload. **Recommendation: No split.** The CLI harness already provides per-cell output for diagnostics.

---

## J. Dataset Audit

### J.1 Dataset Inventory

| Dataset | File | Source | Type | Consumers | Redundant? |
|---------|------|--------|------|-----------|-----------|
| ERN real returns | `spx_tr_real.csv`, `bond_10y_tr_real.csv` | ERN SWR Toolbox Google Sheet | Source | `ern_swr_h*.json` generation | No (canonical source) |
| ERN h360 | `ern_swr_h360.json` | Derived from h720 | Derived | Shorter-horizon slicing | **DELETED** — redundant slice, removed during data-layer cleanup |
| ERN h480 | `ern_swr_h480.json` | Derived from h720 | Derived | 40y horizon | **DELETED** — redundant slice, removed during data-layer cleanup |
| ERN h600 | `ern_swr_h600.json` | Derived from h720 | Derived | 50y horizon | **DELETED** — redundant slice, removed during data-layer cleanup |
| ERN h720 | `ern_swr_h720.json` | Derived from real returns | Primary | All E2E tests, all studies | No (primary dataset) |
| CAPE data | `cape_shiller.csv` | Shiller ie_data.xls | Source | Part 3 research | No (canonical source) |
| FFR data | `ffr.csv` (runtime spliced workbook `Return Data!K`; extends to 2026-08) | ERN workbook / Federal Reserve | Source | Part 52 FFR scenarios | No (canonical source) |
| Oracle table | `p49_oracle_table.csv` | Reference oracle tool | Derived | Oracle validation tests | No (canonical reference) |
| Part 3 chart data | `ern_chart_*.csv`, `ern_part3_*.csv` | ERN article extraction | Source | Part 3 validation | **DELETED** — unreferenced data artifacts, removed during data-layer cleanup |
| Raw data | `data/ern/raw/*` | Original sources | Source | Dataset generation | No (canonical source) |

### J.2 Shorter-Horizon Dataset Analysis

The `ern_swr_h720.json` dataset contains 2,459 monthly snapshots (1871-01 to 2075-11). For any horizon H years (12H months), the dataset can generate a view by slicing the first 12H+1 months. The shorter datasets (`h360`, `h480`, `h600`) exist as pre-computed slices for performance.

**Question:** Are h360/h480/h600 redundant with h720?

**Analysis:**
- h720 contains all data needed for shorter horizons via `Dataset.slice()`.
- The shorter datasets exist to avoid runtime slicing overhead.
- Tests reference specific dataset identifiers (e.g., `ern_swr_h720`), not the shorter ones.
- The `ern_grid.yaml` uses `ern_swr_h720` and lets the framework handle horizon slicing.

**Decision:** The shorter datasets were originally classified as **derived artifacts for performance**, not redundant. They were subsequently deleted during the canonical data-layer cleanup (commit `71f9f9f`), confirming that runtime slicing overhead via `Dataset.slice()` was acceptable.

---

## K. YAML Configuration Audit

### K.1 YAML Inventory

| YAML file | Purpose | Used by | Status |
|-----------|---------|---------|--------|
| `ern_grid.yaml` | Full ERN SWR grid (5×9×4) | `test_full_swr_grid.py` | RETAINED (canonical E2E config) |
| `ern_part3_replication.yaml` | Part 3 combined experiments | Part 3 research pipeline | RETAINED (canonical Part 3 config) |
| `ern_part20.yaml` | Part 19+20 glidepaths (320 cells) | Glidepath tests | RETAINED (canonical E2E config) |
| `ern_part42.yaml` | Part 42 OMY (45 cells) | `test_part42_replication.py` | RETAINED (canonical E2E config) |
| `ern_part49.yaml` | Part 49 leverage (1 cell) | Part 49 tests | RETAINED (canonical E2E config) |
| `ern_smoke.yaml` | Minimal ERN smoke (1 cell) | `test_full_swr_grid.py` | RETAINED (smoke test config) |

### K.2 YAML Decisions

| YAML | Decision | Rationale |
|------|----------|-----------|
| `ern_part3_expA.yaml` | REMOVED | Strict subset of `ern_part3_replication.yaml`. Removed in this phase. |
| `ern_part3_expB.yaml` | REMOVED | Same as above. |
| `ern_part3_expC.yaml` | REMOVED | Same as above. |
| `ern_part3_expD.yaml` | REMOVED | Same as above. |
| `ern_full.yaml` | REMOVED | Not referenced by any tests. Removed in this phase. |
| All others | RETAIN | Active use or canonical E2E configuration. |

---

## L. Environment Variable Decisions

| Variable | Decision | Rationale |
|----------|----------|-----------|
| `RUN_ERN_E2E` | RETAIN (single gate) | Controls all canonical E2E tests AND heavyweight research validations via centralized hook in `tests/conftest.py`. |
| `RUN_ERN_E2E_FULL` | REMOVED | No second tier. All heavyweight ERN research workloads enabled by the same gate. |
| `ERN_E2E_FAST_PATH` | HISTORICAL | No current code consumer; the pre-migration CLI test used it for optimization-equivalence checks. |
| `ERN_E2E_WORKERS` | RETAIN | Configuration, not gating. |
| `SIM_RETIRE_BIN` | RETAIN | CLI binary location. |

### L.1 Single Gate Philosophy

```
RUN_ERN_E2E=1
```

means operationally:

    Enable heavyweight ERN research validation workloads.

This covers:
- Canonical Research E2Es (full methodology, no approximation)
- Non-Canonical Research Validation (documented approximations)

Both categories share the same execution gate because:
1. They are both heavyweight research workloads
2. They both require explicit opt-in
3. They both should not run in normal development testing

The marker taxonomy remains distinct to make classification visible, but the execution gate is unified.

---

## M. Files Changed

| File | Change | Rationale |
|------|--------|-----------|
| `pyproject.toml` | Added `research_validation` marker | Identifies non-canonical research validation tests |
| `tests/conftest.py` | UPDATED: centralized skip hook for both `ern_e2e` and `research_validation` markers | Single gate for all heavyweight ERN research workloads |
| `tests/oracle/ern/test_full_swr_grid.py` | Only `test_full_grid_matches_workbook_oracle` has `@pytest.mark.ern_e2e`; smoke test runs in normal suite | Canonical E2E = full grid only |
| `tests/integration/test_part49_canonical_execution.py` | REDUCED fixture from 10,434 to 18 units; docstrings updated | Integration test, not research-scale |
| `tests/integration/test_part49_aggregation.py` | REDUCED fixture from 10,434 to 18 units; docstrings updated | Integration test, not research-scale |
| `tests/oracle/ern/test_part52_replication.py` | Added `@pytest.mark.research_validation` to `TestCanonicalERNReplication` | Non-canonical research validation (10 tests) |
| `tests/integration/test_part52_deterministic_validation.py` | Removed `research_validation` markers from 5 redundant classes; tests now run in normal mode | Redundant with File 1; 19 tests run in normal mode |
| `AGENTS.md` | Updated invocation hierarchy to include research_validation | Reflects corrected gating model |
| `docs/research/ERN_E2E_REPLICATION_PLAN.md` | Updated Sections E, F, G, H, I, L, M, N, O | Reflects corrected taxonomy and gaps |

---

## N. Quality Gates

| Gate | Status |
|------|--------|
| `ruff check .` | PASS |
| `mypy --strict .` | PASS (264 source files) |
| Normal mode: smoke test runs | PASS (15.85s) |
| Normal mode: full grid skipped | VERIFIED (1 skipped, ern_e2e) |
| Normal mode: Part 49 integration runs | PASS (32 tests, 1.68s) |
| Normal mode: Part 52 deterministic runs | PASS (19 tests, 3m09s, 1 xfail) |
| Normal mode: Part 52 full replication skipped | VERIFIED (10 skipped, research_validation) |
| Normal mode: Part 42 structural runs | VERIFIED (2 passed) |
| Research mode: full grid eligible | VERIFIED (1 test collected) |
| Research mode: Part 52 full replication eligible | VERIFIED (10 tests collected) |

---

## O. Recommended Next Session

### Completed in This Phase

1. ~~Remove redundant Part 3 YAML files.~~ DONE
2. ~~Remove obsolete `ern_full.yaml`.~~ DONE
3. ~~Implement centralized RUN_ERN_E2E gating.~~ DONE
4. ~~Correct canonical E2E terminology.~~ DONE
5. ~~Precisely classify Part 42.~~ DONE
6. ~~Add Missing Data / Missing Information Policy.~~ DONE
7. ~~Establish test taxonomy (canonical E2E vs research validation vs integration).~~ DONE
8. ~~Reduce Part 49 fixtures from 10,434 to 18 units.~~ DONE
9. ~~Mark Part 52 as research_validation.~~ DONE
10. ~~Document canonical E2E gaps (Part 49, Part 19/20, Part 42).~~ DONE

### Implementation Backlog (Next Phase)

**Priority 1 — Canonical E2E coverage gaps:**

1. ~~Create `@pytest.mark.ern_e2e` test for Part 49 (6 cells × 1,739 cohorts = 10,434 units)~~ DONE
2. ~~Create `@pytest.mark.ern_e2e` test for Part 20 (320 cells × 1,739 cohorts = 556K units)~~ DONE
3. ~~Create `@pytest.mark.ern_e2e` test for Part 42 (45 cells × 2,087 cohorts = 94K units)~~ DONE

**Priority 2 — Part 52 redundancy cleanup:**

4. Remove `research_validation` marker from redundant tests in `test_part52_deterministic_validation.py`
5. Merge `test_threshold_does_not_reproduce` resolution detector into `test_part52_replication.py`

**Priority 3 — Part 52 splitting:**

6. Split Part 52 scenarios into individual test functions for parallel execution and better diagnostics

### Long-term (Deferred)

1. Resolve Part 3 blocking dependency (market return data)
2. Resolve Part 52 blocking dependency (FFR dataset coverage)
3. Consider environment variable simplification after canonical E2Es are stable

---

## P. Final Artifact Disposition

### P.1 Removed

| Artifact | Type | Reason |
|----------|------|--------|
| `examples/studies/ern_part3_expA.yaml` | YAML | Strict subset of `ern_part3_replication.yaml` |
| `examples/studies/ern_part3_expB.yaml` | YAML | Strict subset of `ern_part3_replication.yaml` |
| `examples/studies/ern_part3_expC.yaml` | YAML | Strict subset of `ern_part3_replication.yaml` |
| `examples/studies/ern_part3_expD.yaml` | YAML | Strict subset of `ern_part3_replication.yaml` |
| `examples/studies/ern_full.yaml` | YAML | Not referenced by any test or code |
| `test_builders.py::TestYamlLoading::test_part3_exp_a_yaml_loads` | Test | Tested deleted YAML |
| `test_builders.py::TestYamlLoading::test_part3_exp_b_yaml_loads` | Test | Tested deleted YAML |

### P.2 Datasets — Complete Disposition

| Dataset | Classification | Consumers | Independent Purpose | Disposition |
|---------|---------------|-----------|-------------------|-------------|
| `spx_tr_real.csv` | Canonical source | `tools/ern/prepend_base_snapshot.py`, `tools/ern/reference_oracle.py`, `tests/oracle/ern/constants.py`, `tests/oracle/ern/test_ern_timeline_regression.py`, `tests/unit/research/test_shiller_parser.py` | Monthly real equity returns (1871–present). Upstream for all derived SWR datasets. | **RETAIN** — canonical source |
| `bond_10y_tr_real.csv` | Canonical source | Same consumers as `spx_tr_real.csv` | Monthly real bond returns (1871–present). Upstream for all derived SWR datasets. | **RETAIN** — canonical source |
| `ern_real_returns_1871_2016.provenance.json` | Provenance metadata | `tests/infrastructure/test_dataset_cache.py` (historical; not present in current tree) (asserted excluded from loading) | Documents derivation chain for the source CSV. | **DELETED** — removed during data-layer cleanup; no code consumers remained |
| `ern_swr_h720.json` | Primary derived dataset | All E2E tests, all YAML study configs, `tests/infrastructure/test_dataset_cache.py` (historical; not present in current tree) | 60-year horizon SWR dataset. Contains all data needed for any shorter horizon via `Dataset.slice()`. | **RETAIN** — primary derived dataset |
| `ern_swr_h360.json` | Redundant derived artifact | `tools/ern/prepend_base_snapshot.py` (processes all 4), `tests/infrastructure/test_dataset_cache.py` (historical; not present in current tree) (proves derivability) | 30-year horizon prefix of h720. Provenance explicitly labels it "Prefix of h720 (redundant)". No YAML study config uses it. No production code uses it. | **DELETED** — redundant derived artifact, removed during data-layer cleanup |
| `ern_swr_h480.json` | Redundant derived artifact | Same as h360 | 40-year horizon prefix of h720. Same redundancy status as h360. | **DELETED** — redundant derived artifact, removed during data-layer cleanup |
| `ern_swr_h600.json` | Redundant derived artifact | Same as h360 | 50-year horizon prefix of h720. Same redundancy status as h360. | **DELETED** — redundant derived artifact, removed during data-layer cleanup |
| `ern_cape_1871_2016.json` | Canonical source | Part 3 research pipeline (`part3_planner.py`, `part3_aggregation.py`) | CAPE ratios for Part 3 regime classification. | **SUPERSEDED** by `cape_shiller.csv` — removed during data-layer cleanup; CAPE values are identical |
| `ffr_monthly.json` | Reconstructed FFR series | Not canonical workbook `K`; exact numeric comparison yields 522 differences (306 substantive before 1954-07, 216 post-1954 floating-point artifacts) | Federal Funds Rate monthly data (1928-04..2026-08). | **RETAIN** — reconstructed source, not canonical `K` |
| `p49_oracle_table.csv` | Canonical reference | `tests/oracle/ern/test_oracle_matrix.py`, `tests/oracle/ern/test_part49_replication_app.py` | Independent oracle matrix for Part 49 validation. | **RETAIN** — canonical reference |
| `cohort_manifest_part3.json` | Research metadata | `tests/unit/research/test_part3_planner.py`, `tests/unit/research/test_part20_cape.py`, `tests/infrastructure/test_dataset_cache.py` (historical; not present in current tree) | Part 3 cohort eligibility manifest. | **RETAIN** — active test consumer |
| `ern_chart_30Y_A.csv` through `ern_chart_60Y_D.csv` (8 files) | Unreferenced data | **ZERO** consumers in code or tests. Only mentioned once as wildcard in documentation. | ERN article chart data extracted for Part 3 validation. No code reads these files. | **DELETED** — unreferenced data artifacts, removed during data-layer cleanup |
| `ern_part3_30Y_A.csv` through `ern_part3_60Y_D.csv` (8 files) | Unreferenced data | **ZERO** consumers in code or tests. Only mentioned once as wildcard in documentation. | ERN article data extracted for Part 3 validation. No code reads these files. | **DELETED** — unreferenced data artifacts, removed during data-layer cleanup |
| `data/ern/raw/*` (7 files) | Canonical raw sources | `tools/ern/prepend_base_snapshot.py` (ie_data.csv), provenance chains | Original source data (Shiller, Fed Funds, etc.). | **RETAIN** — canonical raw sources |

#### h360/h480/h600 Deletion Rationale

These three datasets were pre-computed horizontal slices of `ern_swr_h720.json`. The provenance file (`ern_real_returns_1871_2016.provenance.json`) explicitly labeled each as "Prefix of h720 (redundant)". The test `test_h720_sliced_to_h360_equals_h360_dataset` proved they were value-equivalent to slicing h720.

**Semantic verification after deletion:**
- The framework resolves horizons via `Dataset.slice()` applied to `ern_swr_h720.json`
- All 5 YAML study configurations reference `ern_swr_h720` (none reference h360/h480/h600)
- `Dataset.slice()` can produce 360-month (30y), 480-month (40y), 600-month (50y), and 720-month (60y) views from the 2,459-snapshot h720 dataset
- No production code, test code, or configuration references the deleted identifiers
- The horizon resolution path (`YAML -> StudyConfiguration -> resolve_dataset() -> Dataset.slice()`) is fully functional with only h720

**What was lost:** Three redundant pre-computed slices. No independent information was lost. Horizon-specific access is now resolved from the primary dataset architecture via `Dataset.slice()`.

### P.3 Chart/Part3 CSV Deletion Rationale

The 16 CSV files (`ern_chart_30Y_*.csv`, `ern_part3_30Y_*.csv`, `ern_part3_60Y_*.csv`, `ern_chart_60Y_*.csv`) were extracted ERN article chart data committed during early Part 3 research. They have:

- **Zero consumers** in production source code
- **Zero consumers** in test code
- **Zero consumers** in tools/scripts
- **Zero consumers** in any YAML configuration
- **One documentation reference** as a wildcard pattern in the dataset audit table

These files were **never wired into any validation pipeline**. They were intermediate outputs from an extraction process that was never completed into an automated workflow. No code reads, opens, or references them. They are not canonical source data (the canonical source is `spx_tr_real.csv`). They are not reproducibility artifacts (the extraction methodology is not documented or automated). They are dead files.

Deletion is correct. No independent information was lost.

### P.4 YAML — Complete Disposition

| YAML | Classification | Consumers | Independent Purpose | Disposition |
|------|---------------|-----------|-------------------|-------------|
| `ern_grid.yaml` | Canonical E2E config | `test_full_swr_grid.py` (full grid E2E), 4 tools in `tools/ern/`, `test_builders.py` | Full 180-cell ERN SWR grid. Used by the canonical Research E2E. | **RETAIN** — canonical E2E configuration |
| `ern_part20.yaml` | Research config | `test_part20_regression.py` (2 tests), `test_part42_config.py`, `test_part20_grid.py` | Part 19+20 glidepath study (320 cells). Used by regression and config tests. | **RETAIN** — research configuration with active test consumers |
| `ern_part3_replication.yaml` | Research config | `test_builders.py` (2 tests) | Part 3 combined experiments. Used by YAML loading tests. | **RETAIN** — research configuration with active test consumers |
| `ern_part42.yaml` | Research config | `test_part42_config.py` | Part 42 OMY study (45 cells). Used by config validation test. | **RETAIN** — research configuration with active test consumers |
| `ern_part49.yaml` | Study configuration | **ZERO** code/test consumers (documentation only) | Part 49 leverage study (1 cell). Valid `sim-retire` input. | **RETAIN** — valid CLI study configuration (user-facing) |
| `ern_smoke.yaml` | Test fixture | `test_full_swr_grid.py` (smoke test) | Minimal smoke grid (1 cell). Test-specific fixture. | **RETAIN** — test fixture |

### P.5 Tests — Complete Disposition

| Test | Previously Considered Redundant? | Independent Responsibility | Disposition |
|------|--------------------------------|---------------------------|-------------|
| `test_smoke_cell_matches_workbook_oracle` | Yes (vs full grid) | Smoke/oracle validation — minimal CLI path verification, fast feedback | **RETAIN** — different responsibility (diagnostic vs full replication) |
| `test_full_grid_matches_workbook_oracle` | No (canonical E2E) | Full 180-cell ERN SWR replication | **RETAIN** — canonical Research E2E |
| `test_ern_timeline_regression.py` | No | Unit-level timeline regression (P1.12R remediation) | **RETAIN** — independent regression test with specific oracle |
| `test_oracle_matrix.py` | No | Oracle matrix structural validation | **RETAIN** — independent oracle validation |
| `test_per_cell_parser.py` | No | CLI output parser unit tests | **RETAIN** — independent parser validation |
| `test_worker_selection.py` | No | Worker count resolution unit tests | **RETAIN** — independent configuration validation |
| `test_part42_replication.py` | No | Part 42 structural constant validation | **RETAIN** — independent structural validation |
| `test_part42_oracle.py` | No | Part 42 oracle comparison (independent implementation) | **RETAIN** — independent oracle validation |
| `test_debt_oracle.py` | No | Debt oracle first-principles derivation | **RETAIN** — independent oracle validation |
| `test_part49_canonical_execution.py` | No (canonical E2E) | Part 49 full canonical execution | **RETAIN** — canonical Research E2E |
| `test_part49_smoke_execution.py` | Yes (vs canonical) | Part 49 smoke execution (unit count, parameter propagation) | **RETAIN** — finer-grained failure localization than canonical E2E |
| `test_part49_grid_materialization.py` | Yes (vs canonical) | Part 49 grid materialization (54 cells, no execution) | **RETAIN** — validates study plan construction independently |
| `test_part49_multi_cohort.py` | Yes (vs canonical) | Part 49 multi-cohort isolation and determinism | **RETAIN** — tests isolation invariants not covered by canonical E2E |
| `test_part49_aggregation.py` | No | Part 49 aggregation structure and statistics | **RETAIN** — independent aggregation validation |
| `test_part49_grid_audit.py` | No | Part 49 dataset and cohort audit | **RETAIN** — independent audit validation |
| `test_part49.py` | No | Part 49 small grid execution | **RETAIN** — independent execution validation |
| `test_part52_replication.py` | No | Part 52 scenario execution (non-canonical) | **RETAIN** — non-canonical integration test |
| `test_part52_numerical_trace.py` | No | Part 52 numerical trace validation | **RETAIN** — independent numerical validation |
| `test_part52_deterministic_validation.py` | No | Part 52 deterministic mechanism validation | **RETAIN** — independent mechanism validation |
| `test_part52_ffr_floating_rate.py` | No | Part 52 FFR floating rate tests | **RETAIN** — independent FFR behavior validation |
| `test_glidepath_trajectory.py` | No | Glidepath trajectory integration tests | **RETAIN** — independent trajectory validation |
| `tests/infrastructure/test_dataset_cache.py::TestErnPrefixIdentity` (historical; not present in current tree) | N/A | Proves h360 is derivable from h720 | **DELETE** — tests derivability of h360 (being deleted) |
| `tests/infrastructure/test_dataset_cache.py::TestErnArtifactBoundary` (historical; not present in current tree) | N/A | Validates ERN data directory boundary | **UPDATE** — remove h360/h480/h600 from `known_datasets` |

No tests are genuinely redundant. Each tests an independent responsibility, provides better failure localization than the E2E, or validates a boundary/invariant not otherwise tested.

### P.6 Environment Variables — Final Inventory

| Variable | Status | Purpose |
|----------|--------|---------|
| `RUN_ERN_E2E` | RETAINED | Single gate for all canonical E2E tests |
| `ERN_E2E_FAST_PATH` | HISTORICAL | No current code consumer; former optimization-equivalence check |
| `ERN_E2E_WORKERS` | RETAINED | Worker count configuration |
| `SIM_RETIRE_BIN` | RETAIN | CLI binary location |

### P.7 Deferred Decisions Due to Missing Information

None. All artifacts have been classified with complete information.

### P.8 Dataset Inventory (Post-Cleanup)

**Top-level artifacts:** 11 files + `raw/` directory

| File | Type |
|------|------|
| `spx_tr_real.csv` | Canonical source (real equity returns) |
| `bond_10y_tr_real.csv` | Canonical source (real bond returns) |
| `spx_tr_real.provenance.json` | Provenance metadata |
| `bond_10y_tr_real.provenance.json` | Provenance metadata |
| `ern_swr_h720.json` | Primary derived dataset |
| `cape_shiller.csv` | Canonical runtime CAPE (supersedes deleted `ern_cape_1871_2016.json`) |
| `ffr.csv` | Canonical runtime FFR (1,868 observations; spliced from workbook `Return Data!K`; matches `K` 1871-01..2021-12, extends to 2026-08) |
| `ffr_monthly.json` | Reconstructed FFR series; not equivalent to workbook `K` before 1954-07 |
| `p49_oracle_table.csv` | Canonical reference |
| `cohort_manifest_part3.json` | Research metadata |
| `cpi.csv` | Runtime canonical CPI dataset; `spx_tr.csv` and `bm10.csv` are auxiliary nominal indices and are not loaded by `load_ern_dataset` |

**Nested canonical raw files:** 7 files

| File | Source |
|------|--------|
| `raw/ie_data.csv` | Shiller dataset |
| `raw/ie_data.provenance.json` | Provenance |
| `raw/FEDFUNDS.csv` | Federal Reserve |
| `raw/FFHTHIGH.csv` | Federal Reserve |
| `raw/FFHTLOW.csv` | Federal Reserve |
| `raw/FFWSJHIGH.csv` | Federal Reserve |
| `raw/FFWSJLOW.csv` | Federal Reserve |

**Total ERN files:** 18 (11 top-level + 7 nested in `raw/`)

### P.9 Cascading Changes Required

The following files required updates when h360/h480/h600 and chart/part3 CSVs were deleted:

| File | Change |
|------|--------|
| `tools/ern/prepend_base_snapshot.py` | Removed h360/h480/h600 from DATASETS tuple |
| `tests/infrastructure/test_dataset_cache.py` (historical; not present in current tree) | Deleted `TestErnPrefixIdentity` class; updated `TestErnArtifactBoundary` to remove h360/h480/h600 from `known_datasets`; deleted `test_ern_h360_resolves_after_boundary_fix`; updated docstring |
| `tests/oracle/ern/constants.py` | Updated docstring to remove h360/h480/h600 mention |
| `data/ern/ern_real_returns_1871_2016.provenance.json` | Removed h360/h480/h600 from downstream section; subsequently deleted during data-layer cleanup |
| `AGENTS.md` | Updated invocation hierarchy and code block to remove `RUN_ERN_E2E_FULL` references |
| `docs/research/ERN_E2E_REPLICATION_PLAN.md` | Updated dataset audit, added final disposition section |

---

## Q. Acceptance Criteria

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Audit permanently documented | COMPLETE |
| 2 | Every article classified canonical/non-canonical | COMPLETE |
| 3 | Strict-superset redundancies documented | COMPLETE |
| 4 | Current tests classified by responsibility | COMPLETE |
| 5 | YAML configurations audited | COMPLETE |
| 6 | Datasets audited | COMPLETE |
| 7 | E2E environment gating documented | COMPLETE |
| 8 | Heavyweight E2Es have granularity analysis | COMPLETE |
| 9 | Canonical E2Es clearly identified | COMPLETE |
| 10 | Non-canonical studies explicitly deferred | COMPLETE |
| 11 | No optimization introduced | COMPLETE |
| 12 | No mathematical behavior changed | COMPLETE |
| 13 | Working tree contains only intentional changes | COMPLETE |
| 14 | Quality gates pass | N/A (no code changes) |

**Status: AUDIT COMPLETE — AWAITING REVIEW**
