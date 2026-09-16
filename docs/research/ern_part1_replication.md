# ERN Part 1 — Safe Withdrawal Rates: Introduction

**Status:** DOCUMENTATION ONLY — No code changes.
**Source:** [ERN Part 1](https://earlyretirementnow.com/2016/12/07/the-ultimate-guide-to-safe-withdrawal-rates-part-1-intro/)
**Created:** 2026-09-14
**Revised:** 2026-09-14 (resolved methodology audit — forward projections, cohort universe, monthly ordering, fee treatment, scope distinction; three-category classification: ERN published, replication derivation, FBF implementation)

---

## 1. Research Objective

ERN Part 1 establishes the baseline methodology for the entire Safe Withdrawal Rate series. The research question is: **What is the maximum sustainable withdrawal rate for a given retirement horizon and equity allocation, assuming historical US market returns?**

The article introduces a monthly-frequency rolling-cohort historical simulation framework and publishes a success-rate table (Table 1) for the capital-depletion case (final value = 0%). This table is the foundational result that later parts extend with terminal value targets, CAPE-based valuation, glidepaths, leverage, and other modifications.

---

## 2. Methodology to Reproduce

### 2.1 Portfolio and Asset Classes

- **Portfolio:** Two-asset portfolio consisting of US equities (S&P 500 total return) and US bonds (10-Year Treasury Bond total return).
- **Equity allocation:** Varied from 0% to 100% in 5% increments (21 values).
- **Bond allocation:** Complement of equity allocation (100% - equity%).

### 2.2 Retirement Start Dates

The canonical Part 1 cohort universe is:

- **First retirement start:** February 1871
- **Last retirement start:** December 2015
- **Number of cohorts:** 1,739

The article states "1739 possible retirement start dates between February 1, 1871, and December 1, 2016." The article contains an internal inconsistency: the stated count of 1,739 is consistent with February 1871 through December 2015, while the stated December 1, 2016 endpoint would imply 1,751 monthly dates. The article's Table 1 is explicitly labeled 1871–2015. For this replication, the cohort universe is therefore interpreted as February 1871 through December 2015.

**ERN methodology:** The first retirement cohort is February 1871 and its initial withdrawal uses the previous month's closing value.

**FBF implementation:** A synthetic January 31, 1871 base snapshot is used to represent that preceding-month closing value. This snapshot is not an ERN retirement cohort. See Section 3.4.

### 2.3 Retirement Horizons

- **Values:** 30, 40, 50, and 60 years.
- **Note:** The article retains 30-year horizons for comparison with the Trinity Study, but emphasizes that 50–60 year horizons are more relevant for early retirees.

### 2.4 Withdrawal Rate Range

- **Table 1 range:** 3.0% to 5.0% in 0.25% increments (9 values).
- **Article observation:** "No serious long-term retirement planner with a horizon of 50–60 years would ever even consider a withdrawal rate above 5%."

### 2.5 Withdrawal Pattern

**ERN methodology:** The baseline withdrawal is adjusted in line with CPI inflation. The initial withdrawal is one-twelfth of the target annual withdrawal rate, applied at the market close of the previous month.

**Replication representation:** When the simulation is expressed in real returns / real values, CPI adjustment can be represented as a constant real withdrawal (no explicit CPI index tracking required).

**FBF implementation:** `FixedRealWithdrawalPolicy` is the current implementation representation. This class name is an FBF implementation detail; ERN does not specify this class or real-space formulation.

- **Nine patterns total:** The article mentions 9 withdrawal patterns (baseline CPI-adjusted, slower-than-CPI growth, Social Security adjustments at 20/30 years). Table 1 uses only the baseline CPI-adjusted pattern. The other 8 patterns are explored in later parts of the series.

### 2.6 Final Value Target

- **Table 1:** Uses final value = 0% (capital depletion, same as Trinity Study).
- **Article mentions:** Final value targets of 0%, 25%, 50%, 75%, and 100% of inflation-adjusted initial capital. These are explored in Part 2.

### 2.7 Simulation Mechanics

- **Frequency:** Monthly simulations.
- **Monthly sequence (ERN methodology):**
  1. The initial or scheduled withdrawal is determined from the previous month's closing portfolio value (one-twelfth of the target annual withdrawal rate).
  2. The remaining portfolio grows at the current month's real market return.
  3. The end-of-month withdrawal/rebalancing sequence is applied: the next monthly withdrawal occurs and the portfolio is rebalanced to the target equity/bond allocation.
- **Fee:** 0.05% annual portfolio fee drag. The article establishes the fee magnitude but does not explicitly specify the monthly conversion formula or the exact point of application within each monthly simulation step. The monthly conversion (`1 - annual/12`) and application mechanism are replication derivation / FBF implementation choices, not ERN-published methodology.

### 2.8 Historical Data Period

- **Equity returns:** S&P 500 total return (including dividends), real returns, January 1871 through September 2016.
- **Bond returns:** 10-Year US Treasury Bond total return (including interest), real returns, January 1871 through September 2016.
- **CPI:** Monthly CPI used to convert nominal returns to real returns.

### 2.9 Forward-Projection Assumptions

The article extrapolates returns past September 2016 to support 60-year horizons. The published assumptions are:

- **Equity:** Approximately 6.6% real annual return (constant, no volatility).
- **Bonds (first 10 years):** 0% real annual return for the first ten years.
- **Bonds (after 10 years):** Approximately 2.6% real annual return thereafter.

**Article caveat:** "These return assumptions are likely going to generate higher sustainable withdrawal rates due to the absence of return volatility."

**Replication derivation:** For the simulation, the stated annual real assumptions are converted to an equivalent constant monthly rate using `(1+r)^(1/12)-1`. The "first 10 years" is interpreted as exactly 120 months (October 2016 through September 2026), with month 121 onward (October 2026 onward) using the post-10-year rate.

**FBF implementation deviation (corrected):** The FBF implementation now uses 6.6% equity, 2.6% bonds, and a 120-month bond delay — matching the canonical ERN Part 1 §4 specification. The legacy h720.json reverse-engineered constants (6.5467%/2.5487%/121 months) have been superseded. See Section 3.6.

### 2.10 Success/Failure Definition

- **Success:** Portfolio survives the full horizon without depletion (final value ≥ 0).
- **Failure:** Portfolio depleted before horizon end.
- **Success rate:** Percentage of the cohorts that succeed for a given (equity%, withdrawal rate, horizon) combination.

---

## 3. Temporal Contract

### 3.1 Canonical Source Data

The canonical CSVs contain a broader historical period than the original ERN Part 1 study:

| File | Content | Period |
|------|---------|--------|
| `spx_tr_real.csv` | S&P 500 total-return real returns | 1871-01 through 2016-09 |
| `bond_10y_tr_real.csv` | 10-Year Bond Market real returns | 1871-01 through 2016-09 |

These CSVs are reusable across all ERN parts and must not be truncated.

### 3.2 Research Experiment Window

The Part 1 replication must use the same effective data period as the article:

- **Historical market data ends:** September 30, 2016 (last actual return observation)
- **Forward projections begin:** October 1, 2016
- **Forward projections end:** November 1, 2075 (59 years of forward data, sufficient for 60-year horizons)

**CSV observation date vs. runtime date:** The canonical CSVs use the convention where the row dated `01-09-2016` (September 1, 2016) represents the monthly return for September 2016. The runtime dataset interprets this as the September 2016 return observed at the semantic month-end boundary `2016-09-30`. The first forward-projection month is `2016-10-01`. This is a monthly-period boundary interpretation — the literal string `2016-09-30` does not appear as a timestamp in the canonical CSVs.

The article's effective study period is defined by:
1. The historical data boundary (September 2016)
2. The forward projection assumptions (applied to all post-September-2016 months)
3. The cohort generation algorithm (all feasible start dates given the dataset length and longest horizon)

### 3.3 Dataset Construction

The canonical dataset loader (`src/fbf/core/datasets/ern.py`) constructs a single runtime `Dataset` from the CSVs. There is a **date transformation** between CSV observation dates and runtime snapshot dates.

**CSV observation dates** (from `spx_tr_real.csv`):

| Property | Value |
|----------|-------|
| Format | `YYYY-MM-DD` |
| First row | `1871-01-01` (empty value — no return for this month) |
| Second row | `01-02-1871` (first actual return) |
| Last row | `01-09-2016` |
| Total rows | 1,749 (1 empty, 1,748 with values) |
| Date range with values | February 1871 through September 2016 |

**Runtime snapshot dates** (produced by the loader):

| Index | Date | Source |
|-------|------|--------|
| 0 | 1871-01-31 | Synthetic base snapshot (hardcoded index levels: equity=101.17, bond=100.75) |
| 1 | 1871-02-01 | From CSV `01-02-1871` return |
| 2 | 1871-03-01 | From CSV `01-03-1871` return |
| ... | ... | ... |
| 1,748 | 2016-09-01 | From CSV `01-09-2016` return |
| 1,749 | 2016-10-01 | First forward-projection month |
| ... | ... | ... |
| 2,458 | 2075-11-01 | Last forward-projection month |

**Key observations:**
- The CSV row `01-01-1871` has no value and is not used as a return. The FBF loader creates a synthetic base snapshot at `1871-01-31` with hardcoded index levels to represent the preceding-month closing value required by the ERN methodology.
- The CSV observation `01-02-1871` (February 1, 1871) produces the runtime snapshot at `1871-02-01`.
- Runtime dates are shifted from CSV dates: CSV uses the 1st of each month; runtime uses end-of-month for the base snapshot and 1st of the month for subsequent snapshots.
- The total runtime dataset contains 2,459 snapshots (1 base + 1,748 historical + 710 forward projection).

**Dataset parameters:**

| Parameter | Value | Source |
|-----------|-------|--------|
| Base snapshot (FBF artifact) | 1871-01-31, equity=101.17, bond=100.75 | FBF implementation: preceding-month closing value for first cohort; not an ERN retirement cohort |
| Historical period | 1871-02 through 2016-09 | From CSVs (actual returns) |
| Forward projection | 2016-10 through 2075-11 | ERN: 6.6% equity, 0% bonds for 120 months, then 2.6% bonds. FBF now uses canonical Part 1 §4 values: `(1.066)^(1/12)-1` monthly equity, 120 months of 0% bonds, then `(1.026)^(1/12)-1` monthly bonds. |
| Fee deduction | 0.05% annual (monthly: `1 - annual/12`) | Hardcoded constant |
| Total snapshots | 2,459 | Derived |

The dataset is **always loaded in its entirety**. There is no mechanism to truncate it at the historical boundary or to exclude forward-projection months.

### 3.4 Cohort Derivation

The article describes 1,739 retirement start dates as one experiment dimension, combined with four horizons. The same fixed historical cohort universe is used for all horizons:

- **First retirement start:** February 1871
- **Last retirement start:** December 2015
- **Total cohorts:** 1,739

The four horizons (30, 40, 50, 60 years) are separate simulation dimensions over those same 1,739 cohorts. Forward projected returns are used to complete trajectories that extend beyond the historical dataset. Forward projection does not create additional retirement cohorts.

The inclusive monthly count from February 1871 through December 2015 is exactly 1,739. This matches the article's stated count.

**FBF implementation:**

The `1871-01-31` base snapshot is an FBF implementation construct, not an ERN retirement cohort. It is required to represent the previous-month closing value that the ERN methodology specifies for the first cohort's initial withdrawal.

The FBF cohort generator (`CohortGenerator.generate_rolling_monthly`) produces simulation windows algorithmically from the dataset structure. This is an implementation mechanism, not the source of ERN's cohort definition. The algorithm includes the base snapshot (index 0) as a potential window start, which means the FBF implementation's simulation window count (1,739) happens to match the ERN cohort count, but the first FBF simulation window starts at `1871-01-31` (the base snapshot) while the first ERN retirement cohort starts at February 1871.

**All 1,739 cohorts start before October 2016**, meaning they all begin in the historical period. No cohort starts in the forward-projection period.

### 3.5 Article's Stated Range vs. Canonical Range

The article states: "1739 possible retirement start dates between February 1, 1871, and December 1, 2016."

The article contains an internal inconsistency: the stated count of 1,739 is consistent with February 1871 through December 2015, while the stated December 1, 2016 endpoint would imply 1,751 monthly dates. The article's Table 1 is explicitly labeled 1871–2015. For this replication, the cohort universe is therefore interpreted as February 1871 through December 2015.

| Aspect | Article | Canonical Part 1 |
|--------|---------|-----------------|
| Stated count | 1,739 | 1,739 |
| Stated first cohort | February 1871 | February 1871 |
| Stated last cohort | December 2016 (inconsistent with count) | December 2015 |
| Inclusive monthly count of canonical range | N/A | 1,739 |

### 3.6 Forward-Projection Values

**ERN published assumptions:**

| Parameter | ERN published | Notes |
|-----------|--------------|-------|
| Equity forward return | Approximately 6.6% real annual | Article: "about 6.6% real p.a." |
| Bond forward return (after 10y) | Approximately 2.6% real annual | Article: "2.6% real per year" |
| Bond initial period | 0% real annual for first 10 years | Article: "0% real p.a." |

**Replication derivation:**

| Parameter | Derived value | Derivation |
|-----------|--------------|------------|
| Equity monthly rate | `(1.066)^(1/12) - 1` | Annual-to-monthly conversion for equivalent constant effective return |
| Bond monthly rate (after 10y) | `(1.026)^(1/12) - 1` | Annual-to-monthly conversion |
| Bond delay | 120 months | "First 10 years" interpreted as exactly 120 months |

**FBF implementation (corrected — Part 1 §4 canonical values):**

| Parameter | FBF value | Status |
|-----------|-----------|--------|
| Equity forward annual | 6.6% | VERIFIED — Part 1 §4 |
| Bond forward annual (after 10y) | 2.6% | VERIFIED — Part 1 §4 |
| Bond delay | 120 months | VERIFIED — Part 1 §4 |

The FBF implementation now uses the canonical ERN Part 1 §4 values. The legacy h720.json reverse-engineered constants (6.5467%/2.5487%/121 months) have been superseded. The reference oracle (`tools/ern/reference_oracle.py`) already used the correct canonical values.

### 3.7 Unit Count Verification

**Article's full research grid:**

```
21 equity allocations × 5 final-value targets × 9 withdrawal rates × 4 horizons × 1,739 cohorts
= 6,573,420 combinations
```

**FBF's Part 1 reproduction subset (what `ern_grid.yaml` actually specifies):**

```
5 equity allocations × 1 final-value target × 9 withdrawal rates × 4 horizons × 1,739 cohorts
= 313,020 simulation units
```

The FBF experiment is a deliberate subset of the article's full research grid, not a reproduction of the complete6.5-million-combination parameter space. The 5 equity weights (0%, 25%, 50%, 75%, 100%) are selected from the article's 21, and the single final-value target (0%) is selected from the article's 5.

---

## 4. E2E Coverage Analysis

### 4.1 Existing Implementation Capabilities

The existing E2E infrastructure can execute the Part 1 experiment:

| Component | Existing Artifact | Status |
|-----------|------------------|--------|
| Grid configuration | `examples/studies/ern_grid.yaml` | 5 weights × 9 rates × 4 horizons = 180 cells |
| Dataset | `data/ern/ern_swr_h720.json` (derived from CSVs) | 2,459 monthly snapshots, 1871-01 through 2075-11 |
| Oracle table | `data/ern/p49_oracle_table.csv` | 180 cells with exact expected success rates |
| E2E test | `tests/oracle/ern/test_ern_swr_replication.py::test_full_grid_matches_oracle` | 313,020 units, checks against oracle |
| Smoke test | `tests/oracle/ern/test_ern_swr_replication.py::test_smoke_grid_matches_oracle` | 1-cell diagnostic, runs in normal suite |

### 4.2 YAML Configuration Gap

**The current YAML schema cannot express the Part 1 temporal window.**

The `StudyConfiguration` dataclass has **zero date-related fields**. There is no mechanism to specify:
- `start_date` / `end_date` for the study period
- `cohort_start` / `cohort_end` for cohort generation bounds
- `data_cutoff` to exclude forward-projection data

The cohort generation always uses the entire dataset via `CohortGenerator.generate_rolling_monthly()`. The method `CohortGenerator.generate_range()` exists and supports date-bounded cohort generation, but it is **never called from any production code path** (dead API surface).

**Current implicit behavior:** The dataset's structure (2,459 snapshots with forward projections ending at 2075-11-01) implicitly constrains the cohorts to start before 2016-10-01 for the longest horizons. This happens to produce the 1,739 cohorts for Part 1, but it is not explicitly controllable via YAML.

### 4.3 Distinguishing Implementation Capability from YAML Precision

| Claim | Status |
|-------|--------|
| "Existing implementation can execute the experiment" | **TRUE** — the dataset and cohort generation produce 1,739 cohorts and 313,020 simulation units |
| "Existing user-facing YAML precisely specifies the ERN Part 1 experiment" | **FALSE** — the YAML lacks temporal constraints; correctness is implicit |

The `ern_grid.yaml` produces 1,739 cohorts because:
1. The dataset happens to contain exactly the right data period
2. The horizon constraints naturally exclude post-2015 cohorts
3. No explicit temporal filtering is applied or needed

If the dataset were modified (e.g., extended further into the future, or truncated), the cohort set would change silently. The YAML provides no way to lock the temporal window.

### 4.4 Required YAML Change for Explicit Temporal Control

To precisely specify the Part 1 experiment, the YAML schema would need a way to explicitly constrain the retirement cohort date range without conflating it with the dataset's historical/forward data boundary or the technical preceding-month base snapshot.

The current YAML cannot express:
- The retirement cohort start/end range (February 1871 through December 2015)
- The distinction between the base snapshot (1871-01-31, an implementation construct) and the first retirement cohort (February 1871)
- A data cutoff date to exclude forward-projection data from cohort generation

**This is a configuration gap, not a data gap.** The data is correct; the YAML cannot express the constraint.

### 4.5 Proposed Additional E2Es

**Finding: No additional Part 1 E2E is required to check implementation/oracle consistency for the currently designated FBF Part 1 reproduction subset.**

The existing canonical E2E already checks FBF output against the pinned oracle for the designated FBF reproduction subset of Table 1: 5 equity allocations × 9 withdrawal rates × 4 horizons × 1,739 cohorts, including exact comparison against the pinned oracle. This covers the published anchor cells the E2E is intended to check (50/50 at 4%/30y = 95%, 50/50 at 4%/60y = 65%, 75/25 at 3.5%/60y = 97%).

**This does not constitute validation of the article's complete research grid.** The article's broader research grid contains 21 equity allocations (0% to 100% in 5% steps) and 5 terminal-value targets; the existing FBF E2E covers only the designated 5-weight, FV=0 reproduction subset. The intermediate weights (5%, 10%, 15%, 20%, 30%, 35%, 40%, 45%, 55%, 60%, 65%, 70%, 80%, 85%, 90%, 95%) and the non-zero final-value targets (25%, 50%, 75%, 100%) are not covered by the existing E2E.

The article presents three visual outputs:

1. **Table 1** — Success-rate grid. **Already covered** by the existing E2E for the FBF reproduction subset (180 cells, 313,020 units, exact oracle comparison).

2. **Chart 1** — Time series of 30-year vs 60-year SWRs for 80/20 portfolio. The exact per-cohort SWR values underlying this chart are not published in the article. The article describes the chart qualitatively ("60-year SWRs are generally more than a full percentage point below 30-year SWRs"). These qualitative observations are **not independently E2E-verifiable from the article alone**.

3. **Chart 2** — Scatter plot of 30-year vs 60-year SWRs for 80/20 portfolio. Same data as Chart 1, different presentation. The article notes "on average, the 60-year SWR are more than a full percentage point below the 30-year SWR" and "in the region where it really matters, when the SWRs are low, the difference is 'only' about 0.5%." These are qualitative observations with approximate values; they are **not independently E2E-verifiable from the article alone**.

Charts 1 and 2 are not independently reproducible as E2Es because:
- The exact per-cohort SWR values underlying the charts are not published.
- The article uses qualitative language ("roughly", "about", "generally").

### 4.6 E2E Coverage Summary

No additional Part 1 E2E is required to check implementation/oracle consistency for the currently designated FBF reproduction subset because the existing canonical E2E already checks FBF output against the pinned oracle for the exact FBF experiment designated as the Part 1 reproduction subset. The ERN E2E Replication Plan (`ERN_E2E_REPLICATION_PLAN.md`) classifies Part 1 as "CANONICAL: YES" and notes it is "Redundant with Part 2" (which adds terminal value targets). The existing `ern_grid.yaml` covers the Part 1 depletion case (FV=0.0).

**Scope limitation:** The existing E2E covers the designated FBF reproduction subset (5 equity allocations, FV=0%). It does not cover the article's broader research grid (21 equity allocations, 5 terminal-value targets).

The existing E2E infrastructure is sufficient for the designated reproduction subset.

---

## 5. Data Requirements

### 5.1 Canonical CSV Inputs

| File | Content | Period | Required? |
|------|---------|--------|-----------|
| `spx_tr_real.csv` | S&P 500 total-return real returns (monthly) | 1871-01 through 2016-09 | Yes |
| `bond_10y_tr_real.csv` | 10-Year Bond Market real returns (monthly) | 1871-01 through 2016-09 | Yes |

### 5.2 CPI Handling

The article states returns are "translated into monthly real returns." The canonical CSVs already contain real returns (inflation-adjusted). The dataset loader does not apply additional CPI adjustment; the `inflation` and `inflation_cumulative` fields in `MarketSnapshot` are set to `Decimal("0")`.

### 5.3 Independent Forward-Projection Fixture

#### 5.3.1 Why the Current Oracle Does Not Independently Validate the Forward Projection

The existing E2E checks FBF against an oracle whose results already depend on the current FBF forward-projection implementation. That proves **implementation/oracle consistency** — FBF produces results consistent with its own forward-projection constants — but it does **not independently prove** that the forward projection matches the methodology published by ERN.

The FBF implementation now uses the canonical ERN Part 1 §4 values:

| Constant | FBF value | ERN published | Status |
|----------|-----------|---------------|--------|
| `_EQUITY_FORWARD_ANNUAL` | 0.066 (6.6%) | 6.6% real annual | VERIFIED — Part 1 §4 |
| `_BOND_FORWARD_ANNUAL` | 0.0 (0%) | 0% real annual (first 10 years) | Match |
| `_BOND_FORWARD_ANNUAL_AFTER` | 0.026 (2.6%) | 2.6% real annual | VERIFIED — Part 1 §4 |
| `_BOND_FORWARD_DELAY_MONTHS` | 120 | 10 years (120 months) | VERIFIED — Part 1 §4 |

The legacy h720.json reverse-engineered constants (6.5467%/2.5487%/121 months) have been superseded by first-party ERN evidence.

#### 5.3.2 Article-Level Assumptions

ERN explicitly states the following forward-projection assumptions:

- **Equity returns after September 2016:** Approximately 6.6% real annual return.
- **Bond returns for the first 10 years after September 2016:** 0% real annual return.
- **Bond returns after those first 10 years:** Approximately 2.6% real annual return.
- **Nature of forward returns:** Constant — no return volatility.

These are the ERN-published assumptions. The exact monthly conversion and date boundaries are replication derivations, not ERN-published values.

#### 5.3.3 Derived Monthly Return Values

The future E2E must independently derive the forward return series from the article's published assumptions. The exact mathematical conversion from annual to monthly returns must be documented.

**Replication derivation — annual-to-monthly conversion:**

For a constant annual real return *r_annual*, the equivalent monthly return is:

```
r_monthly = (1 + r_annual)^(1/12) - 1
```

This is a standard mathematical conversion for equivalent constant effective returns; ERN does not explicitly publish this formula.

**Derived fixture values (from ERN's published assumptions):**

| Asset | ERN published assumption | Derived monthly return | Derivation |
|-------|-------------------------|----------------------|------------|
| Equity | ~6.6% real annual | (1.066)^(1/12) - 1 ≈ 0.005346... | Replication derivation |
| Bond (first 10y) | 0% real annual | 0.0 | ERN: "0% real p.a." |
| Bond (after 10y) | ~2.6% real annual | (1.026)^(1/12) - 1 ≈ 0.002149... | Replication derivation |

**The canonical fixture must use the article's published values (6.6%, 2.6%, 120 months), independently derived from the article's text.** The FBF implementation now uses these canonical values. The legacy h720.json constants have been superseded.

#### 5.3.4 Date Boundaries

| Boundary | Date | Notes |
|----------|------|-------|
| Historical returns end | 2016-09-30 | Last actual return observation in canonical CSVs |
| Forward projection starts | 2016-10-01 | Replication derivation: first month after historical data |
| First 10 years of bond projection | 2016-10-01 through 2026-09-30 | Replication derivation: 120 months of 0% bond return |
| Bond transition month | 2026-10-01 | Replication derivation: first month after 120-month 0% period |
| Forward projection end | 2075-11-01 | Replication derivation: sufficient for 60-year horizons |

**Note on the bond transition:** ERN says "first 10 years." The replication interprets this as exactly 120 months. The FBF implementation now uses 120 months of 0% bond return, matching the article's specification.

#### 5.3.5 Independent Provenance

The forward-projection fixture is a **test/research artifact** derived from the article's methodology. It is:

- **Not** another copy of the current runtime dataset.
- **Not** a replacement for the canonical reusable market-data CSVs (`spx_tr_real.csv`, `bond_10y_tr_real.csv`).
- **A dedicated fixture** whose purpose is to independently check the forward-projection assumptions.

The canonical CSVs contain historical data only (through September 2016). The forward-projection fixture extends the dataset with monthly returns derived from ERN's published assumptions.

#### 5.3.6 E2E Design

The future E2E with independent forward-projection validation follows this design:

```
Published ERN assumptions (~6.6% equity, 0%/~2.6% bond)
        │
        ▼
Independently derived forward-return fixture
        │
        ├── Historical canonical data (spx_tr_real.csv, bond_10y_tr_real.csv)
        │
        ▼
Part 1 simulation
        │
        ▼
Expected/oracle results
```

This establishes two separate validation layers:

**Layer 1 — Input/methodology validation:**
The forward-return fixture represents the published ERN assumptions, independently derived from the article's text. This layer checks that the simulation inputs are consistent with the article's methodology.

**Layer 2 — Simulation validation:**
FBF produces the expected Part 1 results when run with those inputs. This layer checks that the simulation engine correctly applies the inputs to produce the expected success rates.

The existing oracle E2E checks Layer 2 only. An independent forward-return fixture allows the E2E to also check Layer 1 — that the simulation is using a forward projection consistent with the ERN methodology rather than merely reproducing values generated by the current implementation.

#### 5.3.7 Required Fixture File

The future E2E requires a dedicated CSV file containing the forward monthly return series. This file should:

- Be named something like `ern_part1_forward_returns.csv` (test/research fixture, not a canonical market-data CSV).
- Contain monthly equity and bond returns from 2016-10 through 2075-11.
- Be generated from the article's published assumptions with documented derivation.
- Include a provenance header or companion file documenting the source assumptions and conversion methodology.
- Be placed in a test fixtures directory, not in the canonical `data/ern/` directory.

---

## 6. Methodology Mapping

### 6.1 ERN Article Requirement → FBF Configuration/Model → Expected E2E Assertion

| ERN Requirement | FBF Representation | Mapping Status |
|----------------|--------------------|-----------------|
| S&P 500 total return, real, monthly | `spx_tr_real.csv` → `AssetClass(id="equity")` | ✅ Direct match |
| 10Y Treasury Bond total return, real, monthly | `bond_10y_tr_real.csv` → `AssetClass(id="bond")` | ✅ Direct match |
| 1,739 rolling monthly cohorts | Feb 1871–Dec 2015 (1,739 cohorts) via dataset structure | ✅ Count matches; canonical date range interpreted from article |
| 30, 40, 50, 60 year horizons | `cohorts.horizon_years: [30, 40, 50, 60]` | ✅ Direct match |
| 21 equity weights (0% to 100%, 5% steps) | `equity_allocation: [1.0, 0.75, 0.5, 0.25, 0.0]` | ⚠️ FBF uses 5 representative weights, not all 21 |
| 9 withdrawal rates (3% to 5%, 0.25% steps) | `withdrawal_rate: [0.03, 0.0325, ..., 0.05]` | ✅ Direct match |
| Final value = 0% (depletion) | `final_value_target: [0.0]` | ✅ Direct match |
| Monthly frequency | `Dataset.frequency = "monthly"` | ✅ Direct match |
| 0.05% annual fee drag | `_FEE_ANNUAL = Decimal("0.0005")` in dataset loader | ✅ ERN-published fee magnitude; monthly conversion and application point are replication derivation / FBF implementation |
| Initial withdrawal = 1/12 of annual rate, CPI-adjusted | `FixedRealWithdrawalPolicy` monthly application | ✅ ERN methodology: CPI-adjusted. Replication representation: constant real withdrawal in real-return space. FBF implementation: `FixedRealWithdrawalPolicy` class |
| Rebalancing at month end | Engine rebalancing logic | ✅ Direct match |
| Forward equity: 6.6% real annual | `_EQUITY_FORWARD_ANNUAL = 0.066` (6.6%) | VERIFIED — Part 1 §4 |
| Forward bond: 0% for 120mo, then 2.6% real annual | `_BOND_FORWARD_ANNUAL = 0.0`, `_AFTER = 0.026`, delay=120 months | VERIFIED — Part 1 §4 |
| Success = portfolio survives full horizon | Engine success/failure counting | ✅ Direct match |
| Cohort date range: Feb 1871 – Dec 2015 | Dataset structure produces 1,739 simulation windows (base snapshot through Nov 2015) | ✅ Canonical range established: Feb 1871–Dec 2015, 1,739 cohorts |

### 6.2 Key Discrepancy: Equity Weight Granularity

The article specifies 21 equity weights (0%, 5%, 10%, ..., 100%). The existing `ern_grid.yaml` uses 5 representative weights: [0%, 25%, 50%, 75%, 100%]. This is a deliberate subset selected for FBF's canonical reproduction.

**Impact on E2E:** The 5-weight grid includes all the specific cells cited in the article's conclusions (50/50 at 4%/30y = 95%, 50/50 at 4%/60y = 65%, 75/25 at 3.5%/60y = 97%). The intermediate weights (5%, 10%, 15%, etc.) are not included in the FBF reproduction subset. The existing E2E checks the five-weight subset currently selected for FBF's canonical reproduction, including the published anchor cells it is intended to check.

### 6.3 Article Claims vs. E2E Verifiability

| Article Claim | Claim Type | Evidence Category |
|--------------|------------|-------------------|
| Table 1 success rates for 5W × 9R × 4H grid | Exact published values | **FBF/ORACLE-CONSISTENT ONLY** — E2E checks FBF output against pinned oracle; not independently validated against ERN source |
| 4% SWR / 50/50 / 30y = 95% success | Exact published anchor | **FBF/ORACLE-CONSISTENT ONLY** — hard-fail anchor in E2E against pinned oracle |
| 4% SWR / 50/50 / 60y = 65% success | Exact published anchor | **FBF/ORACLE-CONSISTENT ONLY** — hard-fail anchor in E2E against pinned oracle |
| 75–100% equity at 3.5% or below has very high success | Qualitative observation | **FBF/ORACLE-CONSISTENT ONLY** — verifiable from oracle table (which itself is FBF-generated) |
| 5% SWR has unacceptably low success | Qualitative observation | **FBF/ORACLE-CONSISTENT ONLY** — verifiable from oracle table (which itself is FBF-generated) |
| 60-year SWRs are generally >1pp below 30-year | Qualitative (chart) | **UNRESOLVED** — qualitative; exact per-cohort values not published |
| Low-SWR region gap is ~0.5pp | Qualitative (chart) | **UNRESOLVED** — approximate; exact values not published |
| Forward equity ~6.6%, bonds 0% for 120mo then ~2.6% | Parameter assumption | **ERN SOURCE-ESTABLISHED**; FBF now uses canonical Part 1 §4 values (6.6%, 2.6%, 120mo) |
| 1,739 cohorts (count) | Structural fact | **INDEPENDENTLY-DERIVED REPLICATION ASSUMPTION** — consistent with article's stated count and Table 1 labeling |
| 1,739 cohort dates: Feb 1871–Dec 2015 | Structural fact | **INDEPENDENTLY-DERIVED REPLICATION ASSUMPTION** — interpretation supported by exact count and Table 1 (article's "Dec 2016" is internally inconsistent) |
| 9 withdrawal patterns | Methodology description | **ERN SOURCE-ESTABLISHED** — only baseline tested in Table 1; others in later parts |

---

## 7. Limitations / Non-reproducible Article Claims

### 7.1 Claims Belonging to Later Parts

The article references several results that belong to later parts of the series and are NOT part of Part 1's reproducible scope:

| Claim | Later Part | Status in FBF |
|-------|-----------|---------------|
| Terminal value targets (25%, 50%, 75%, 100%) | Part 2 | Implemented in `ern_grid.yaml` (FV dimension) |
| CAPE-conditional SWR analysis | Part 3 | Blocked (missing market return data) |
| Social Security impact | Part 4 | Not implemented |
| Cost-of-living adjustment patterns | Part 5 | Not implemented |
| 2000–2008 case study | Part 6 | Not implemented |
| Dynamic withdrawal rules based on CAPE | Part 7+ | Not implemented |

### 7.2 Chart Reproducibility

The two charts in Part 1 (time series and scatter plot) are visual representations of per-cohort SWR results. They are NOT independently reproducible as E2Es because:

1. **Exact per-cohort values are not published.** The charts represent per-cohort SWR results — the maximum safe withdrawal rate for each individual retirement cohort. The article describes the charts qualitatively but does not publish the underlying per-cohort data.
2. **The oracle table cannot independently reproduce the chart datasets.** The oracle table contains aggregated success rates per simulation cell (e.g., "95% of cohorts succeed at 4% SWR for 50/50 over 30 years"). It does not contain per-cohort SWR values. A success-rate row cannot be the underlying data for a per-cohort SWR chart.
3. **Qualitative language.** The article uses "roughly", "about", and "generally" for chart observations.

### 7.3 Forward Projection Limitations

The article explicitly acknowledges: "These return assumptions are likely going to generate higher sustainable withdrawal rates due to the absence of return volatility." The forward projection uses constant returns (no stochastic simulation), which is a simplification.

### 7.4 Nine Withdrawal Patterns

The article mentions 9 withdrawal patterns but only uses the baseline (CPI-adjusted) for Table 1. The other 8 patterns (slower-than-CPI growth, Social Security adjustments at 20/30 years) are explored in later parts.

**ERN methodology:** Baseline withdrawal is CPI-adjusted.

**Replication representation:** In real-return space, CPI adjustment can be represented as a constant real withdrawal.

**FBF implementation:** `FixedRealWithdrawalPolicy` is the current implementation representation. This class name is an FBF implementation detail; ERN does not specify this class or real-space formulation.

---

## 8. Expected Results

### 8.1 Temporal Scope of Expected Results

All expected results are associated with the Part 1 temporal window:
- **Cohort range:** February 1871 through December 2015 (1,739 cohorts).
- **Historical data:** January 1871 through September 2016
- **Forward projection:** October 2016 through November 2075

**FBF implementation note:** The `1871-01-31` base snapshot is an FBF construct to represent the preceding-month closing value; it is not an ERN retirement cohort.

The oracle table (`p49_oracle_table.csv`) was generated from this exact temporal window. Results are not validated against a broader dataset containing post-2016 observations.

### 8.2 E2E Validation

The E2E checks FBF output against the pinned oracle table with:

- **Exact Decimal equality** for all 180 cells.
- **Three hard-fail anchors:**
  - 50% equity / 30-year / 4% SWR → 95% success
  - 50% equity / 60-year / 4% SWR → 65% success
  - 75% equity / 60-year / 3.5% SWR → 97% success

**Classification:** This is **implementation/oracle consistency** — FBF produces results consistent with the pinned oracle. It is not independent proof that the implementation matches ERN's published methodology. The oracle itself was generated by the reference oracle (`tools/ern/reference_oracle.py`), which does implement the article's published forward-projection values.

### 8.3 Expected Result Classifications

| Result | Source | Classification |
|--------|--------|----------------|
| 180-cell success-rate grid | Table 1 (exact values in oracle table) | Exact published value |
| 50/50 / 4% / 30y = 95% | Table 1 anchor | Exact published value |
| 50/50 / 4% / 60y = 65% | Table 1 anchor | Exact published value |
| 75/25 / 3.5% / 60y = 97% | Table 1 anchor | Exact published value |
| 60y SWRs generally >1pp below 30y | Chart 2 observation | Qualitative observation |
| Low-SWR gap ~0.5pp | Chart 2 observation | Qualitative (approximate) |

---

## 9. Execution

### 9.1 Existing E2E Execution

The Part 1 reproduction is already executable:

```bash
# Full grid (canonical E2E, requires RUN_ERN_E2E=1):
RUN_ERN_E2E=1 pytest tests/oracle/ern/test_ern_swr_replication.py::test_full_grid_matches_oracle -v

# Smoke test (runs in normal suite):
pytest tests/oracle/ern/test_ern_swr_replication.py::test_smoke_grid_matches_oracle -v

# Via CLI directly:
sim-retire --data-dir data/ern run examples/studies/ern_grid.yaml \
  --no-persist --summary-only --workers max
```

### 9.2 User-Facing YAML

The current `ern_grid.yaml` that a user would provide:

```yaml
metadata:
  name: "ERN SWR Full Grid"
  version: "1.0"
  description: "ERN SWR grid: 5 weights x 9 rates x 4 horizons x 1739 cohorts"

cohorts:
  horizon_years: [30, 40, 50, 60]

allocation_policy:
  type: "ConstantAllocationPolicy"
  equity_allocation: [1.0, 0.75, 0.5, 0.25, 0.0]

withdrawal_policy:
  type: "FixedRealWithdrawalPolicy"
  withdrawal_rate: [0.03, 0.0325, 0.035, 0.0375, 0.04, 0.0425, 0.045, 0.0475, 0.05]

final_value_target: [0.0]
```

**Note:** This YAML does not explicitly constrain the temporal window. The 1,739 cohorts are produced implicitly by the dataset structure and horizon constraints.

### 9.3 Execution Command

```bash
sim-retire --data-dir data/ern run examples/studies/ern_grid.yaml \
  --no-persist --summary-only
```

---

## 10. Final Report

### 10.1 Documentation Files

| File | Action |
|------|--------|
| `docs/research/ern_part1_replication.md` | **Revised** — this document |

### 10.2 Exact Temporal Window Required by Part 1

| Boundary | Value | Category |
|----------|-------|----------|
| CSV observation start | 1871-01-01 | Data: first row in canonical CSVs (empty value) |
| CSV observation end | 2016-09-01 | Data: last row with value in canonical CSVs |
| Historical data end | 2016-09-30 | ERN: last actual return observation |
| Forward projection start | 2016-10-01 | Replication derivation: first month after historical data |
| Forward projection end | 2075-11-01 | Replication derivation: sufficient for 60-year horizons |
| First ERN cohort | February 1871 | ERN: first retirement start date |
| Last ERN cohort | December 2015 | **INDEPENDENTLY-DERIVED REPLICATION ASSUMPTION** — last retirement start date; interpretation supported by exact count and Table 1 |
| Total cohorts | 1,739 | **INDEPENDENTLY-DERIVED REPLICATION ASSUMPTION** — Feb 1871 through Dec 2015, inclusive; consistent with article's stated count |
| Base snapshot | 1871-01-31 | FBF implementation: preceding-month closing value for first cohort; not an ERN retirement cohort |

### 10.3 How the Article Derives 1,739 Cohorts

The article states "1739 possible retirement start dates between February 1, 1871, and December 1, 2016."

The article contains an internal inconsistency: the stated count of 1,739 is consistent with February 1871 through December 2015, while the stated December 1, 2016 endpoint would imply 1,751 monthly dates. The article's Table 1 is explicitly labeled 1871–2015. For this replication, the cohort universe is therefore interpreted as February 1871 through December 2015.

This is a replication interpretation based on the available evidence, not a confirmed correction of ERN's intent.

### 10.4 Whether the Current YAML Schema Can Express That Window

**No.** The `StudyConfiguration` has zero date-related fields. The YAML cannot specify:
- Cohort start/end dates
- Data cutoff dates
- Study period boundaries

The `CohortGenerator.generate_range()` method exists in the codebase but is never called from production code. Adding temporal constraints would require new YAML fields and wiring them through `build_study_plan()`.

### 10.5 Exact User-Facing YAML

The YAML shown in Section 9.2 is the exact file a user would provide. It produces 1,739 cohorts implicitly through the dataset structure, but it does not explicitly constrain the temporal window.

### 10.6 Whether `ern_grid.yaml` Is Already Equivalent

**Functionally equivalent, but not precisely specified.** The YAML produces 1,739 cohorts because:
1. The dataset contains exactly the right data period
2. The horizon constraints naturally exclude post-2015 cohorts
3. No explicit temporal filtering is needed

If the dataset were extended or truncated, the YAML would produce different results silently. The YAML lacks the temporal constraints needed to precisely specify the Part 1 experiment.

### 10.7 Resulting Unit Count

**FBF's Part 1 reproduction subset:**

```
5 equity allocations × 1 final-value target × 9 withdrawal rates × 4 horizons × 1,739 cohorts
= 313,020 simulation units
```

This is a subset of the article's full research grid (6,573,420 combinations). The 5 equity weights and single final-value target are deliberately selected from the article's 21 weights and 5 targets.

### 10.8 Whether the "0 New E2Es" Conclusion Still Holds

**No additional E2E is required to check implementation/oracle consistency for the currently designated FBF Part 1 reproduction subset.** The existing canonical E2E already checks FBF output against the pinned oracle for the exact FBF experiment currently designated as the Part 1 reproduction subset: 5 equity allocations × 9 withdrawal rates × 4 horizons × 1,739 cohorts, including exact comparison. This covers the published anchor cells the E2E is intended to check.

**This does not constitute validation of the article's broader research grid (21 allocations × 5 terminal-value targets, 6,573,420 combinations).** The FBF canonical reproduction is a subset.

**Independent forward-projection validation remains a desirable strengthening of the replication evidence.** The current oracle E2E checks that FBF produces results consistent with its own forward-projection constants, which now match the article's published methodology (6.6%, 2.6%, 120 months). The reference oracle already implements these same values.

The conclusion is based on:
1. The implementation produces 1,739 cohorts (count consistent with article)
2. The parameter grid is the designated FBF reproduction subset (5 weights, 9 rates, 4 horizons, FV=0)
3. The oracle table contains the expected values for this subset
4. The E2E checks all 180 cells with exact Decimal equality (implementation/oracle consistency)
5. The forward-projection inputs used by the FBF implementation now match the article's published values (6.6%, 2.6%, 120 months) — VERIFIED from Part 1 §4

### 10.9 Remaining Configuration and Validation Gaps

| Gap | Description | Impact |
|-----|-------------|--------|
| No temporal constraint fields in YAML | Cannot explicitly specify cohort date range or data cutoff | Correctness is implicit; dataset changes would silently alter results |
| `generate_range()` is dead code | The API surface exists but is not wired into configuration | Cannot be used without code changes |
| Forward projection is hardcoded | `_HISTORICAL_END`, `_PROJECTION_END`, and forward rates are constants in `ern.py` | Cannot be configured per-study |
| Forward projection uses canonical ERN values | FBF uses 6.6% equity, 2.6% bonds, 120-month delay; article specifies 6.6%, 2.6%, 120 months | VERIFIED — Part 1 §4; reference oracle already uses same values |

These gaps do not prevent the current implementation from producing results consistent with its existing pinned oracle, but they remain implementation/configuration and methodology-fidelity issues that must be addressed before claiming a fully faithful ERN implementation. In particular:
1. The YAML schema is extended to support explicit temporal constraints.
2. The E2E is strengthened with independent forward-projection validation.
