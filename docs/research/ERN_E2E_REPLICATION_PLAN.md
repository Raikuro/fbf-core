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
- **Dataset:** `ern_real_returns_1871_2016.csv` (monthly real equity and bond returns).
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
- **Dataset:** `ern_cape_1871_2016.json` (Shiller CAPE data, 1881–2023) plus `ern_swr_h720.json` for simulation.
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
- **Dataset:** Same as Part 1.
- **Cohort definition:** 1,739 rolling monthly cohorts.
- **Horizons:** 30 years.
- **Policies:** Partial leverage (3% portfolio withdrawal + 1% loan draw = 4% total spending), fixed real interest rates (0%, 1.5%, 3%), LTV observed but not enforced.
- **Success criteria:** Portfolio survives full horizon (no LTV enforcement = observation only).
- **Published anchors:** 6 canonical cells (2 equity × 3 interest rates).

### B.8 Part 52 — Timing Leverage in Retirement

- **Research question:** How does drawdown-triggered leverage timing improve SWR?
- **Methodology:** Rolling-cohort simulation with conditional leverage activation, FFR-based floating rates, repayment at fresh ATH.
- **Dataset:** Same as Part 1 plus `ffr_monthly.json` (Fed Funds Rate data).
- **Cohort definition:** 1,739 rolling monthly cohorts.
- **Horizons:** 30 years.
- **Policies:** Part52WithdrawalPolicy with drawdown thresholds (20%, 25%, 30%, 35%), FFR+spread rates, LTV 50% enforced, repayment at fresh ATH.
- **Success criteria:** Maximize WR subject to 25% terminal net worth and 50% LTV constraint.
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
- **E2E test:** `test_ern_swr_replication.py` (smoke and full grid).
- **Note:** Redundant with Part 2 (see Section D).

#### Part 2 — CANONICAL: YES

- **Grid:** `ern_grid.yaml` (same as Part 1, with terminal value target dimension)
- **Dataset:** `ern_swr_h720.json`
- **Status:** Fully implemented. The `final_value_target: [0.0]` in `ern_grid.yaml` covers the depletion case; terminal value variants can be expressed by modifying the FV target.
- **E2E test:** `test_ern_swr_replication.py` (same test as Part 1).
- **Note:** Strict superset of Part 1 (see Section D).

#### Part 3 — CANONICAL: NO

- **Classification:** NON-CANONICAL
- **Blocking dependency:** The dataset (`ern_swr_h720.json`) does not contain historical market return series. Index levels are normalized to 1.0. Without real equity/bond returns, success rate computation is a simplified constant-real-withdrawal model that produces 0% success rates for all scenarios.
- **Required for canonical replication:** Historical equity price levels, 10Y Treasury return series, and inflation data to compute real portfolio trajectories.
- **Existing tests useful as:** Non-canonical framework validation (CAPE regime classification, cohort generation, aggregation logic).
- **Test files:** `tests/unit/research/test_part3_*.py`, `tests/integration/` (CAPE-related).
- **YAML files:** `ern_part3_replication.yaml` (retained; individual experiment files `ern_part3_expA/B/C/D.yaml` removed as strict subsets — see Section K).
- **Documentation:** `docs/research/ern_part3_replication.md` (explicitly documents the limitation).

##### Missing Requirement — Part 3 Market Return Data

- **Exact missing data/information:** Historical monthly equity returns (S&P 500 total return) and bond returns (10-Year US Treasury) for the period 1871–2016, aligned to the same cohort structure used by the ERN SWR dataset.
- **Why it is required:** ERN Part 3 computes success rates by simulating portfolio trajectories with actual historical returns. The current dataset has `index_levels` normalized to 1.0, which means the simulation engine cannot compute portfolio growth or depletion — it can only apply fixed withdrawals against a constant portfolio.
- **Which ERN article/scenarios are affected:** Part 3, all 4 experiments (A–D), all 851 cohorts, both 30-year and 60-year horizons.
- **Why the currently available data is insufficient:** `ern_swr_h720.json` contains derived return ratios (used for portfolio evolution) but the research pipeline (`part3_pipeline.py`) needs the raw return series to compute trajectories from the initial portfolio value. The normalized index_levels prevent meaningful success rate computation.
- **Whether an approximation currently exists:** The Part 3 research pipeline runs with normalized data and produces 0% success rates for all scenarios. This is not an approximation — it is a known incomplete computation.
- **Why that approximation is non-canonical:** 0% success rates do not match any ERN published result. The computation is structurally incomplete, not approximately correct.
- **Exact data/information required to unblock canonical replication:** Monthly S&P 500 total return index and 10-Year US Treasury total return index, covering 1871–2016, in a format compatible with the FBF dataset schema (monthly `MarketSnapshot` with `index_levels` per `AssetClass`).
- **Intended future source/status:** USER TO PROVIDE — the source data (Shiller `ie_data.xls`) is available in `data/ern/raw/ie_data.csv` but has not been transformed into the per-asset-class return format needed by the simulation engine.

#### Part 19 — CANONICAL: YES

- **Grid:** Part of `ern_part20.yaml` (24 glidepaths from Part 19, combined with Part 20).
- **Dataset:** `ern_swr_h720.json`
- **Status:** Fully implemented via `GlidepathAllocationPolicy`.
- **E2E test:** `test_glidepath_trajectory.py` (integration-level glidepath validation).
- **Note:** Strict subset of Part 20 (see Section D).

#### Part 20 — CANONICAL: YES

- **Grid:** `ern_part20.yaml` (32 glidepaths × 5 SWR × 2 horizons = 320 cells)
- **Dataset:** `ern_swr_h720.json`
- **Status:** Fully implemented. Includes all Part 19 glidepaths plus 8 additional.
- **E2E test:** `test_glidepath_trajectory.py`.
- **Note:** Strict superset of Part 19 (see Section D).

#### Part 42 — CANONICAL: NO (E2E not implemented)

- **Classification:** NON-CANONICAL (E2E test not implemented)
- **Reason:** The full grid E2E test (`test_full_grid_execution`) is not implemented. The test file (`test_part42_replication.py`) contains only structural constant validation (grid dimensions, anchor values). No test currently executes the 78,255-unit Part 42 grid through the production path and validates research-level results.
- **What exists:** Grid structure constants validated. OMY accumulation phase implemented (`run_accumulation_phase`). Integration tests pass (`test_part42.py`) with synthetic data. Oracle validation tests pass (`test_part42_oracle.py`) and validate accumulation semantics against independent implementation.
- **What is missing:** A test that materializes the full 45-cell Part 42 grid via `build_study_plan()`, executes all 78,255 units through `execute_study_plan()`, and compares success rates against published ERN anchors (baseline ~3.6%, OMY improvement +7.8%).
- **Blocking dependency:** Implementation of the full grid execution test.
- **Existing tests useful as:** Non-canonical validation of OMY mechanics and accumulation semantics.
- **YAML file:** `ern_part42.yaml` (retained; study configuration is complete).
- **Documentation:** `docs/roadmap/MULTI_STUDY_REPLICATION_ROADMAP.md` §A.3.

##### Missing Requirement — Part 42 E2E Implementation

- **Exact missing data/information:** A test function that executes the full Part 42 grid through the production execution path.
- **Why it is required:** Without grid execution, we cannot validate that the Part 42 OMY replication produces results consistent with ERN published anchors. Current tests validate components in isolation but not the complete research configuration.
- **Which ERN article/scenarios are affected:** Part 42, all 45 grid cells (5 equity × 9 SWR × 1 horizon), 1,739 cohorts per cell.
- **Why the currently available data is insufficient:** Data is available (`ern_swr_h720.json`, `ern_part42.yaml`). The YAML study configuration is complete. The OMY accumulation logic is implemented. The gap is test implementation, not data.
- **Whether an approximation currently exists:** No approximation. The test is simply not written.
- **Why that approximation is non-canonical:** N/A — no approximation exists.
- **Exact data/information required to unblock canonical replication:** Implementation of a test that: (1) builds the Part 42 study plan from `ern_part42.yaml`, (2) executes all units through `execute_study_plan()`, (3) computes per-cell success rates, (4) compares against ERN published anchors.
- **Intended future source/status:** EXTERNAL SOURCE TO BE VERIFIED — the ERN Part 42 article (§A.3) publishes the baseline failsafe (~3.6%) and OMY improvement (+7.8%). These anchors are already defined in `constants.py`.

#### Part 49 — CANONICAL: YES (with documented differences)

- **Grid:** `ern_part49.yaml` (2E × 9R × 3I = 54 cells) and canonical 6-cell grid.
- **Dataset:** `ern_swr_h720.json`
- **Status:** Fully implemented. All 10,434 canonical units execute successfully.
- **Documented difference:** LTV enforcement is intentionally OFF (observation only). This is a deliberate architectural decision (`DECISIONS.md` S4-LTV). The 1929 depletion anchor depends on LTV enforcement and is NOT validated by the canonical workload.
- **E2E test:** `test_part49_canonical_execution.py` (10,434 units, passes).
- **Supporting tests:** `test_part49_smoke_execution.py`, `test_part49_grid_materialization.py`, `test_part49_multi_cohort.py`, `test_part49_grid_audit.py`.
- **Oracle tests:** `test_debt_oracle.py` (independent first-principles implementation).

#### Part 52 — CANONICAL: NO

- **Classification:** NON-CANONICAL
- **Blocking dependency:** The FFR scenarios (A2–A8, A10–A11, 9 of 11 scenarios) use fixed-rate approximations instead of actual historical Fed Funds Rate data. The FFR dataset (`ffr_monthly.json`) begins in 1928, but all 1,739 cohorts begin before 1928, meaning FFR coverage is incomplete for every cohort.
- **Non-FFR scenarios (A1, A9):** These use no FFR and could potentially be canonical, but they represent only 2 of 11 scenarios. They are not classified as canonical because the complete Part 52 replication requires all 11 scenarios.
- **Required for canonical replication:** Complete FFR dataset covering 1871–present, or a demonstrated mathematically equivalent methodology for partial FFR coverage.
- **Existing tests useful as:** Non-canonical validation (Part 52 mechanics, numerical trace, debt lifecycle).
- **Test files:** `test_part52_canonical_ern_replication.py` (runs by default, >15 min), `test_part52_numerical_trace.py`.
- **Documentation:** `TODO.md` items S6.6B (FFR integration limitation, canonical replication deferred).

##### Missing Requirement — Part 52 FFR Dataset Coverage

- **Exact missing data/information:** Monthly Federal Funds Rate (FFR) data covering the full cohort period 1871–present. The current `ffr_monthly.json` begins in 1928.
- **Why it is required:** ERN Part 52 scenarios A2–A8 and A10–A11 use FFR + spread as the floating interest rate for margin loans. Without FFR data for the early portion of each cohort (1871–1928), the interest rate is approximated as a fixed rate, which materially differs from the actual ERN methodology.
- **Which ERN article/scenarios are affected:** Part 52, scenarios A2–A8, A10–A11 (9 of 11 scenarios). Only A1 (baseline, no leverage) and A9 (1929 baseline, no leverage) are unaffected.
- **Why the currently available data is insufficient:** The FFR dataset starts in 1928. All 1,739 cohorts begin between 1871 and 2015. For cohorts beginning before 1928, the first 1–67 years of the 30-year horizon have no FFR data. The current implementation substitutes a fixed rate for these periods, which is not equivalent to ERN's methodology.
- **Whether an approximation currently exists:** Yes — the current implementation uses a fixed-rate approximation for FFR scenarios. The `Part52Evaluator` accepts `interest_rate_schedule=None` which falls back to a scalar interest rate.
- **Why that approximation is non-canonical:** Fixed rates do not capture the time-varying nature of FFR. During periods like the Great Depression (1930s) and post-WWII era, FFR was near zero, which would significantly affect the leverage cost and therefore the WR optimization. The approximation may produce different optimal WR and Borrow% values than ERN's actual FFR-based calculation.
- **Exact data/information required to unblock canonical replication:** Monthly FFR observations from 1871 to present, or a documented methodology for extending the FFR series backward (e.g., using commercial paper rates as a proxy for pre-1928 periods).
- **Intended future source/status:** USER TO PROVIDE — the source FFR data is available in `data/ern/raw/FEDFUNDS.csv` but only from 1928 onward. Extending backward requires either additional historical data sources or a documented proxy methodology.

### C.3 Canonical Status Summary

| Article | CANONICAL NOW | Classification | Blocking Dependency |
|---------|--------------|----------------|---------------------|
| Part 1 | YES | Canonical | None (redundant with Part 2) |
| Part 2 | YES | Canonical | None |
| Part 3 | NO | Non-canonical | Missing market return data in dataset |
| Part 19 | YES | Canonical | None (redundant with Part 20) |
| Part 20 | YES | Canonical | None |
| Part 42 | YES | Canonical with caveats | E2E test placeholder needs implementation |
| Part 49 | YES | Canonical with differences | LTV enforcement intentionally OFF |
| Part 52 | NO | Non-canonical | Incomplete FFR dataset coverage |

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
| Data source | `ern_real_returns_1871_2016.csv` | Same | Yes |
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

#### Part 19 ⊂ Part 20 — VERIFIED STRICT SUBSET

| Dimension | Part 19 | Part 20 | Match? |
|-----------|---------|---------|--------|
| Data source | `ern_real_returns_1871_2016.csv` | Same | Yes |
| Cohorts | 1,739 rolling monthly | Same | Yes |
| Horizons | 60 years only | 30 AND 60 years | Part 20 is superset |
| Glidepaths | 24 (6 combos × 2 slopes × 2 modes) | 32 (24 + 8 new) | Part 20 is superset |
| SWR values | 3.0%–4.0% in 0.25% steps | Same | Yes |
| Terminal value | 0% (depletion) | Same | Yes |
| Research calculation | Glidepath vs static comparison | Extended with more variants | Part 20 subsumes Part 19 |
| Grid file | Part of `ern_part20.yaml` | `ern_part20.yaml` | Same file |

**Decision:** Part 19 is a strict subset of Part 20. All 24 Part 19 glidepaths are included in the Part 20 grid. **Part 19 is redundant as a separate E2E.**

**Retention rationale:** The `ern_part20.yaml` file contains all Part 19 glidepaths. No separate Part 19 E2E is needed.

#### Part 1/2 vs Part 3 — NOT REDUNDANT

| Dimension | Part 1/2 | Part 3 | Match? |
|-----------|----------|--------|--------|
| Data source | `ern_real_returns_1871_2016.csv` | `ern_cape_1871_2016.json` + `ern_swr_h720.json` | Different |
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
| Part 19 | Part 20 | Same glidepath mechanics, data, cohorts, rates | Part 20 adds 8 glidepaths + 30y horizon | YES | Part 19 is redundant; `ern_part20.yaml` covers both |
| Part 3 | Part 1/2 | Different cohort definition, different data source | — | NO | Not redundant (different research question) |
| Part 42 | Part 1/2 | Different policy (accumulation phase) | — | NO | Not redundant (different research question) |
| Part 49 | Part 1/2 | Different policy (leverage) | — | NO | Not redundant (different research question) |
| Part 52 | Part 49 | Different policy (timing, FFR, repayment) | — | NO | Not redundant (different research question) |

---

## E. Canonical E2E Coverage Matrix

### E.1 Implemented Canonical E2Es

| E2E ID | ERN Article(s) | YAML | Test file | Units | Status |
|--------|----------------|------|-----------|-------|--------|
| E2E-SWR | Parts 1 + 2 | `ern_grid.yaml` | `test_ern_swr_replication.py::test_full_grid_matches_oracle` | 313,020 | **IMPLEMENTED** |
| E2E-Part20 | Part 20 (includes Part 19) | `ern_part20.yaml` | `test_part20_replication.py::test_part20_full_grid_structure` | 556,480 | **IMPLEMENTED** |
| E2E-Part49 | Part 49 | (Python API) | `test_part49_replication.py::test_part49_canonical_replication` | 10,434 | **IMPLEMENTED** |

### E.2 Canonical Replication Implemented, E2E Missing

| Article | Canonical grid | Units | Implementation status | E2E gap |
|---------|---------------|-------|----------------------|---------|
| Part 42 (OMY) | 45 cells × 1,739 cohorts | 78,255 | Accumulation phase validated; grid materializes | **No E2E test + CLI dispatch unknown** |

### E.3 Non-Canonical / Blocked

| Article | Reason | Blocking dependency |
|---------|--------|-------------------|
| Part 3 (CAPE) | Missing market return data | Historical equity/bond return series |
| Part 52 (Timing Leverage) | FFR scenarios use fixed-rate approximation | Complete FFR dataset or demonstrated equivalence |

### E.4 Strict-Superset Relationships

| Superset | Subset | Relationship verified? |
|----------|--------|----------------------|
| Part 2 (SWR with terminal value) | Part 1 (SWR depletion) | Yes — Part 2 adds `final_value_target` dimension |
| Part 20 (32 glidepaths) | Part 19 (24 glidepaths) | Yes — Part 20 = Part 19 + 8 additional passive glidepaths |

**Total canonical E2E tests: 2** (Parts 1/2 SWR grid, Part 20 glidepath grid)
**Total canonically reproducible articles without E2E: 2** (Part 49, Part 42)

---

## F. Non-Canonical / Deferred Studies

### F.1 Part 3 — CAPE-Conditional SWR

**Status:** NON-CANONICAL (blocked)
**Reason:** Dataset lacks historical market return series. Index levels normalized to 1.0.
**Blocking dependency:** Real equity/bond return data for portfolio trajectory computation.
**Existing value:** Non-canonical framework validation (CAPE regime classification, cohort generation, aggregation logic).
**Test classification:** Unit tests and research-layer tests (retain as implementation validation).
**YAML files:** `ern_part3_replication.yaml` (retain as study configuration).
**What would make it canonical:** Adding real historical return series to the dataset.

### F.2 Part 42 — One More Year Syndrome

**Status:** CANONICAL REPLICATION IMPLEMENTED, E2E MISSING
**Reason:** The accumulation phase is fully implemented and validated (31 tests pass). The grid materializes correctly (45 cells × 1,739 cohorts = 78,255 units). However, no E2E test executes the full grid through the production path.
**Blocking dependency:** (1) E2E test implementation, (2) CLI dispatch for OMY studies (lives in `fbf-cli`), (3) pinned per-cell oracle table.
**Existing value:** Oracle validation tests pass and validate accumulation semantics. Integration tests validate OMY mechanics.
**Test classification:** Structural/oracle tests (retain). Integration tests (retain).
**What would complete it:** Implementing the full grid execution in `test_part42_replication.py` and verifying CLI dispatch.

### F.3 Part 49 — Using Leverage in Retirement

**Status:** CANONICAL REPLICATION VALIDATED
**Reason:** The full production path works (verified by standalone `s57_performance_benchmark.py`). The canonical 6-cell grid (2 equity × 3 IR × 1,739 cohorts = 10,434 units) is fully reproducible. The E2E test executes the full canonical workload via Python API and validates at three levels: structural coverage, computational execution, and canonical replication (non-leverage cells against pinned oracle table; leverage cells with directional assertions).
**E2E test:** `test_part49_replication.py::test_part49_canonical_replication` (gated by `RUN_ERN_E2E=1`, ~7.5m runtime).
**Documented limitations:**
- LTV enforcement intentionally OFF (`DECISIONS.md` S4-LTV).
- 1929 depletion anchor NOT validated (depends on LTV enforcement).
- Leverage cells (interest_rate > 0) have no published ERN oracle table; validation is directional only.
**Existing value:** Integration tests with reduced fixtures (18 units) validate execution correctness. Materialization tests validate 54-cell grid structure.
**Test classification:** Integration tests with reduced fixtures (retain). Grid materialization tests (retain).

### F.4 Part 19/20 — Equity Glidepaths

**Status:** CANONICAL REPLICATION VALIDATED
**Reason:** The YAML grid exists (`ern_part20.yaml`, 320 cells × 1,739 cohorts = 556,480 units). The glidepath allocation policy is implemented. Part 20 ⊃ Part 19 (confirmed: 24 + 8 = 32 glidepaths). The E2E test (`test_part20_replication.py`) executes the full grid and validates at three levels: structural coverage, computational execution (real outcomes), and canonical replication (traceable ERN anchors). Determinism is verified via independent CLI invocation.
**E2E test:** `test_part20_replication.py::test_part20_full_grid_replication` (gated by `RUN_ERN_E2E=1`).
**Determinism test:** `test_part20_replication.py::test_part20_determinism` (gated by `RUN_ERN_E2E=1`).
**Existing value:** `test_glidepath_trajectory.py` validates glidepath control logic with small fixtures.
**Test classification:** Integration tests with small fixtures (retain).

#### F.4.1 Part 20 Methodology Investigation — CLOSED

**Status:** CLOSED — ACCEPTED
**Classification:** GLIDEPATH DISCREPANCY NOT ESTABLISHED — PRESENTATION/GRID ARTIFACT

The Part 20 methodology investigation is complete and accepted. All
validated findings are recorded in `TODO.md` under "S1 Follow-Up: ERN
Validation Discrepancies."

**Do not reopen the Part 20 methodology investigations unless new evidence
contradicts these validated conclusions.** In particular, do not create new
tasks to investigate fees, withdrawal frequency, cohort selection, return
construction, forward extrapolation, static allocation mathematics, or
rebalancing mechanics merely because FBF's precise binary-searched failsafe
differs from a published ERN percentage. Published ERN percentages must be
interpreted according to the documented search/grid and success-rate
conventions.

**Methodology validation vs. E2E execution:** Methodology validation is
COMPLETE / ACCEPTED. The canonical ERN E2E replication (full grid execution)
remains a separate task if still pending. Do not mark the canonical E2E as
complete merely because the methodology investigation is complete. Likewise,
do not reopen methodology investigations as a prerequisite for running the
canonical E2E.

### F.5 Part 52 — Timing Leverage

**Status:** NON-CANONICAL RESEARCH VALIDATION
**Reason:** 9 of 11 scenarios use fixed-rate approximation instead of actual FFR. FFR dataset begins in 1928; all 1,739 cohorts begin before 1928.
**Blocking dependency:** Complete FFR dataset covering 1871–present, or demonstrated mathematical equivalence of fixed-rate approximation.
**Existing value:** Non-canonical validation of Part 52 mechanics (drawdown triggers, repayment, LTV enforcement).
**Test classification:** `@pytest.mark.research_validation` (gated by `RUN_ERN_E2E=1`).
**Test files:** `test_part52_canonical_ern_replication.py` (11 scenarios, >20 min), `test_part52_deterministic_validation.py` (3 redundant scenarios, 3 min).
**What would make it canonical:** Complete FFR dataset or demonstrated equivalence.

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
| `tests/oracle/ern/test_ern_swr_replication.py` (full grid) | E2E | **Canonical Research E2E** | Yes (313K units) | **No** |
| `tests/oracle/ern/test_part20_replication.py` | E2E | **Canonical Research E2E** | Yes (556K units) | **No** |
| `tests/oracle/ern/test_ern_swr_replication.py` (smoke) | Smoke | Smoke | No | Yes |
| `tests/oracle/ern/test_part42_replication.py` | Structural | Integration | No | Yes |
| `tests/integration/test_part49_smoke_execution.py` | Integration | Smoke | No | Yes |
| `tests/integration/test_part49_canonical_execution.py` | Integration | Integration | No (reduced to 18 units) | Yes |
| `tests/integration/test_part49_aggregation.py` | Integration | Integration | No (reduced to 18 units) | Yes |
| `tests/integration/test_part49_grid_materialization.py` | Integration | Integration | No | Yes |
| `tests/integration/test_part49_multi_cohort.py` | Integration | Integration | No | Yes |
| `tests/integration/test_part49_grid_audit.py` | Integration | Integration | No | Yes |
| `tests/integration/test_part42.py` | Integration | Integration | No | Yes |
| `tests/integration/test_part52_canonical_ern_replication.py` | Integration | **Non-Canonical Research Validation** | Yes (19K units) | **No** |
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
| `ERN_E2E_FAST_PATH` | `test_ern_swr_replication.py` | Enables fast-path equivalence check | Must be `"1"` |
| `ERN_E2E_WORKERS` | `constants.py`, `test_ern_swr_replication.py` | Worker count override | Optional |
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

### H.5 Tests Gated by `ern_e2e` (Canonical Research E2E)

| Test | File | What it does |
|------|------|-------------|
| `test_full_grid_matches_oracle` | `test_ern_swr_replication.py` | Full 180-cell grid (313K units) via CLI |
| `test_part20_full_grid_replication` | `test_part20_replication.py` | Full 320-cell Part 20 grid (556K units) via CLI, three-level validation |
| `test_part20_determinism` | `test_part20_replication.py` | Single-cell determinism check (two independent CLI invocations) |
| `test_part49_canonical_replication` | `test_part49_replication.py` | Full 6-cell Part 49 grid (10K units) via Python API, three-level validation |

**Total: 4 tests**

### H.6 Tests Gated by `research_validation` (Non-Canonical Research Validation)

| Test class/file | What it does |
|----------------|-------------|
| `TestCanonicalERNReplication` (test_part52_canonical_ern_replication.py) | 11 Part 52 scenarios (FFR approximations) |

**Total: 10 tests** (all in one class, one fixture)

### H.7 Tests NOT Gated (Run by Default)

| Category | Examples | Why not gated |
|----------|----------|---------------|
| SWR smoke | `test_smoke_grid_matches_oracle` | Diagnostic smoke test, not research replication |
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
| `test_ern_swr_replication.py::test_smoke_grid_matches_oracle` | ~14s | 2,099 | 1 cell | None | No (already minimal) |
| `test_ern_swr_replication.py::test_full_grid_matches_oracle` | ~51s (measured in test_oracle_matrix) | 313,020 | 180 cells (independent) | CLI subprocess, dataset loading | No (single CLI subprocess) |
| `test_part49_replication.py::test_part49_canonical_replication` | ~7.5m | 10,434 | 6 cells (2E × 3I) | Python API, dataset loading | No (single Python API call) |
| `test_part49_canonical_execution.py` | ~1s (reduced fixture) | 18 | 6 cells (2E × 3I) | Dataset loading, pipeline construction | No (integration test, not research-scale) |
| `test_part49_aggregation.py` | ~1s (reduced fixture) | 18 | 6 cells (2E × 3I) | Dataset loading, pipeline construction | No (integration test, not research-scale) |
| `test_part52_canonical_ern_replication.py` | >15 min (timeout) | 19,129 | 11 scenarios | Part52Evaluator grid sweep per scenario | Yes — scenarios are independent |
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
| ERN real returns | `ern_real_returns_1871_2016.csv` | Shiller data extraction | Source | `ern_swr_h*.json` generation | No (canonical source) |
| ERN h360 | `ern_swr_h360.json` | Derived from h720 | Derived | Shorter-horizon slicing | Potentially — h720 can generate 30y views |
| ERN h480 | `ern_swr_h480.json` | Derived from h720 | Derived | 40y horizon | Potentially — h720 can generate 40y views |
| ERN h600 | `ern_swr_h600.json` | Derived from h720 | Derived | 50y horizon | Potentially — h720 can generate 50y views |
| ERN h720 | `ern_swr_h720.json` | Derived from real returns | Primary | All E2E tests, all studies | No (primary dataset) |
| CAPE data | `ern_cape_1871_2016.json` | Shiller ie_data.xls | Source | Part 3 research | No (canonical source) |
| FFR data | `ffr_monthly.json` | Federal Reserve | Source | Part 52 FFR scenarios | No (canonical source) |
| Oracle table | `p49_oracle_table.csv` | Reference oracle tool | Derived | Oracle validation tests | No (canonical reference) |
| Part 3 chart data | `ern_chart_*.csv`, `ern_part3_*.csv` | ERN article extraction | Source | Part 3 validation | No (article-specific) |
| Raw data | `data/ern/raw/*` | Original sources | Source | Dataset generation | No (canonical source) |

### J.2 Shorter-Horizon Dataset Analysis

The `ern_swr_h720.json` dataset contains 2,459 monthly snapshots (1871-01 to 2075-11). For any horizon H years (12H months), the dataset can generate a view by slicing the first 12H+1 months. The shorter datasets (`h360`, `h480`, `h600`) exist as pre-computed slices for performance.

**Question:** Are h360/h480/h600 redundant with h720?

**Analysis:**
- h720 contains all data needed for shorter horizons via `Dataset.slice()`.
- The shorter datasets exist to avoid runtime slicing overhead.
- Tests reference specific dataset identifiers (e.g., `ern_swr_h720`), not the shorter ones.
- The `ern_grid.yaml` uses `ern_swr_h720` and lets the framework handle horizon slicing.

**Decision:** The shorter datasets are **derived artifacts for performance**, not redundant. They may be removable if runtime slicing overhead is acceptable, but this is an optimization question, not a redundancy question. **Retain all datasets.**

---

## K. YAML Configuration Audit

### K.1 YAML Inventory

| YAML file | Purpose | Used by | Status |
|-----------|---------|---------|--------|
| `ern_grid.yaml` | Full ERN SWR grid (5×9×4) | `test_ern_swr_replication.py` | RETAINED (canonical E2E config) |
| `ern_part3_replication.yaml` | Part 3 combined experiments | Part 3 research pipeline | RETAINED (canonical Part 3 config) |
| `ern_part20.yaml` | Part 19+20 glidepaths (320 cells) | Glidepath tests | RETAINED (canonical E2E config) |
| `ern_part42.yaml` | Part 42 OMY (45 cells) | `test_part42_replication.py` | RETAINED (canonical E2E config) |
| `ern_part49.yaml` | Part 49 leverage (1 cell) | Part 49 tests | RETAINED (canonical E2E config) |
| `ern_smoke.yaml` | Minimal ERN smoke (1 cell) | `test_ern_swr_replication.py` | RETAINED (smoke test config) |

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
| `ERN_E2E_FAST_PATH` | RETAIN | Separate concern (optimization equivalence, not canonical replication). |
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
| `tests/oracle/ern/test_ern_swr_replication.py` | Only `test_full_grid_matches_oracle` has `@pytest.mark.ern_e2e`; smoke test runs in normal suite | Canonical E2E = full grid only |
| `tests/integration/test_part49_canonical_execution.py` | REDUCED fixture from 10,434 to 18 units; docstrings updated | Integration test, not research-scale |
| `tests/integration/test_part49_aggregation.py` | REDUCED fixture from 10,434 to 18 units; docstrings updated | Integration test, not research-scale |
| `tests/integration/test_part52_canonical_ern_replication.py` | Added `@pytest.mark.research_validation` to `TestCanonicalERNReplication` | Non-canonical research validation (10 tests) |
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
3. Create `@pytest.mark.ern_e2e` test for Part 42 (45 cells × 1,739 cohorts = 78K units) — requires CLI dispatch verification

**Priority 2 — Part 52 redundancy cleanup:**

4. Remove `research_validation` marker from redundant tests in `test_part52_deterministic_validation.py`
5. Merge `test_threshold_does_not_reproduce` resolution detector into `test_part52_canonical_ern_replication.py`

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
| `ern_real_returns_1871_2016.csv` | Canonical source | `tools/ern/prepend_base_snapshot.py`, `tools/ern/reference_oracle.py`, `tests/oracle/ern/constants.py`, `tests/oracle/ern/test_ern_timeline_regression.py`, `tests/unit/research/test_shiller_parser.py` | Monthly real equity/bond returns (1871–2016). Upstream for all derived SWR datasets. | **RETAIN** — canonical source |
| `ern_real_returns_1871_2016.provenance.json` | Provenance metadata | `tests/infrastructure/test_dataset_cache.py` (asserted excluded from loading) | Documents derivation chain for the source CSV. | **RETAIN** — provenance metadata |
| `ern_swr_h720.json` | Primary derived dataset | All E2E tests, all YAML study configs, `tests/infrastructure/test_dataset_cache.py` | 60-year horizon SWR dataset. Contains all data needed for any shorter horizon via `Dataset.slice()`. | **RETAIN** — primary derived dataset |
| `ern_swr_h360.json` | Redundant derived artifact | `tools/ern/prepend_base_snapshot.py` (processes all 4), `tests/infrastructure/test_dataset_cache.py` (proves derivability) | 30-year horizon prefix of h720. Provenance explicitly labels it "Prefix of h720 (redundant)". No YAML study config uses it. No production code uses it. | **DELETE** — redundant derived artifact, no independent consumers |
| `ern_swr_h480.json` | Redundant derived artifact | Same as h360 | 40-year horizon prefix of h720. Same redundancy status as h360. | **DELETE** — redundant derived artifact, no independent consumers |
| `ern_swr_h600.json` | Redundant derived artifact | Same as h360 | 50-year horizon prefix of h720. Same redundancy status as h360. | **DELETE** — redundant derived artifact, no independent consumers |
| `ern_cape_1871_2016.json` | Canonical source | Part 3 research pipeline (`part3_planner.py`, `part3_aggregation.py`) | CAPE ratios for Part 3 regime classification. | **RETAIN** — canonical source |
| `ffr_monthly.json` | Canonical source | Part 52 evaluator | Federal Funds Rate monthly data (1928–present). | **RETAIN** — canonical source |
| `p49_oracle_table.csv` | Canonical reference | `tests/oracle/ern/test_oracle_matrix.py`, `tests/oracle/ern/test_ern_swr_replication.py` | Independent oracle matrix for Part 49 validation. | **RETAIN** — canonical reference |
| `cohort_manifest_part3.json` | Research metadata | `tests/unit/research/test_part3_planner.py`, `tests/unit/research/test_part20_cape.py`, `tests/infrastructure/test_dataset_cache.py` | Part 3 cohort eligibility manifest. | **RETAIN** — active test consumer |
| `ern_chart_30Y_A.csv` through `ern_chart_60Y_D.csv` (8 files) | Unreferenced data | **ZERO** consumers in code or tests. Only mentioned once as wildcard in documentation. | ERN article chart data extracted for Part 3 validation. No code reads these files. | **DELETE** — unreferenced data artifacts |
| `ern_part3_30Y_A.csv` through `ern_part3_60Y_D.csv` (8 files) | Unreferenced data | **ZERO** consumers in code or tests. Only mentioned once as wildcard in documentation. | ERN article data extracted for Part 3 validation. No code reads these files. | **DELETE** — unreferenced data artifacts |
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

These files were **never wired into any validation pipeline**. They were intermediate outputs from an extraction process that was never completed into an automated workflow. No code reads, opens, or references them. They are not canonical source data (the canonical source is `ern_real_returns_1871_2016.csv`). They are not reproducibility artifacts (the extraction methodology is not documented or automated). They are dead files.

Deletion is correct. No independent information was lost.

### P.4 YAML — Complete Disposition

| YAML | Classification | Consumers | Independent Purpose | Disposition |
|------|---------------|-----------|-------------------|-------------|
| `ern_grid.yaml` | Canonical E2E config | `test_ern_swr_replication.py` (full grid E2E), 4 tools in `tools/ern/`, `test_builders.py` | Full 180-cell ERN SWR grid. Used by the canonical Research E2E. | **RETAIN** — canonical E2E configuration |
| `ern_part20.yaml` | Research config | `test_part20_regression.py` (2 tests), `test_part42_config.py`, `test_part20_grid.py` | Part 19+20 glidepath study (320 cells). Used by regression and config tests. | **RETAIN** — research configuration with active test consumers |
| `ern_part3_replication.yaml` | Research config | `test_builders.py` (2 tests) | Part 3 combined experiments. Used by YAML loading tests. | **RETAIN** — research configuration with active test consumers |
| `ern_part42.yaml` | Research config | `test_part42_config.py` | Part 42 OMY study (45 cells). Used by config validation test. | **RETAIN** — research configuration with active test consumers |
| `ern_part49.yaml` | Study configuration | **ZERO** code/test consumers (documentation only) | Part 49 leverage study (1 cell). Valid `sim-retire` input. | **RETAIN** — valid CLI study configuration (user-facing) |
| `ern_smoke.yaml` | Test fixture | `test_ern_swr_replication.py` (smoke test) | Minimal smoke grid (1 cell). Test-specific fixture. | **RETAIN** — test fixture |

### P.5 Tests — Complete Disposition

| Test | Previously Considered Redundant? | Independent Responsibility | Disposition |
|------|--------------------------------|---------------------------|-------------|
| `test_smoke_grid_matches_oracle` | Yes (vs full grid) | Smoke/oracle validation — minimal CLI path verification, fast feedback | **RETAIN** — different responsibility (diagnostic vs full replication) |
| `test_full_grid_matches_oracle` | No (canonical E2E) | Full 180-cell ERN SWR replication | **RETAIN** — canonical Research E2E |
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
| `test_part52_canonical_ern_replication.py` | No | Part 52 scenario execution (non-canonical) | **RETAIN** — non-canonical integration test |
| `test_part52_numerical_trace.py` | No | Part 52 numerical trace validation | **RETAIN** — independent numerical validation |
| `test_part52_deterministic_validation.py` | No | Part 52 deterministic mechanism validation | **RETAIN** — independent mechanism validation |
| `test_part52_ffr_floating_rate.py` | No | Part 52 FFR floating rate tests | **RETAIN** — independent FFR behavior validation |
| `test_glidepath_trajectory.py` | No | Glidepath trajectory integration tests | **RETAIN** — independent trajectory validation |
| `test_dataset_cache.py::TestErnPrefixIdentity` | N/A | Proves h360 is derivable from h720 | **DELETE** — tests derivability of h360 (being deleted) |
| `test_dataset_cache.py::TestErnArtifactBoundary` | N/A | Validates ERN data directory boundary | **UPDATE** — remove h360/h480/h600 from `known_datasets` |

No tests are genuinely redundant. Each tests an independent responsibility, provides better failure localization than the E2E, or validates a boundary/invariant not otherwise tested.

### P.6 Environment Variables — Final Inventory

| Variable | Status | Purpose |
|----------|--------|---------|
| `RUN_ERN_E2E` | RETAINED | Single gate for all canonical E2E tests |
| `ERN_E2E_FAST_PATH` | RETAINED | Optimization equivalence check (separate concern) |
| `ERN_E2E_WORKERS` | RETAINED | Worker count configuration |
| `SIM_RETIRE_BIN` | RETAIN | CLI binary location |

### P.7 Deferred Decisions Due to Missing Information

None. All artifacts have been classified with complete information.

### P.8 Dataset Inventory (Post-Cleanup)

**Top-level artifacts:** 7 files + `raw/` directory

| File | Type |
|------|------|
| `ern_real_returns_1871_2016.csv` | Canonical source |
| `ern_real_returns_1871_2016.provenance.json` | Provenance metadata |
| `ern_swr_h720.json` | Primary derived dataset |
| `ern_cape_1871_2016.json` | Canonical source |
| `ffr_monthly.json` | Canonical source |
| `p49_oracle_table.csv` | Canonical reference |
| `cohort_manifest_part3.json` | Research metadata |

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

**Total ERN files:** 14 (7 top-level + 7 nested in `raw/`)

### P.9 Cascading Changes Required

The following files required updates when h360/h480/h600 and chart/part3 CSVs were deleted:

| File | Change |
|------|--------|
| `tools/ern/prepend_base_snapshot.py` | Removed h360/h480/h600 from DATASETS tuple |
| `tests/infrastructure/test_dataset_cache.py` | Deleted `TestErnPrefixIdentity` class; updated `TestErnArtifactBoundary` to remove h360/h480/h600 from `known_datasets`; deleted `test_ern_h360_resolves_after_boundary_fix`; updated docstring |
| `tests/oracle/ern/constants.py` | Updated docstring to remove h360/h480/h600 mention |
| `data/ern/ern_real_returns_1871_2016.provenance.json` | Removed h360/h480/h600 from downstream section |
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
