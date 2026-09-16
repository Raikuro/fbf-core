# ERN Part 3 Replication — Equity Valuation Using CAPE

## 1. Article Methodology

### 1.1 Core Thesis

ERN Part 3 investigates how equity valuation (measured by CAPE at retirement start)
affects Safe Withdrawal Rate success. The key insight is that **retirement timing
relative to market valuation** is a first-order determinant of portfolio survival.

**Article:** [ERN Part 3: The Ultimate Guide to Safe Withdrawal Rates – Part 3:
Equity Valuation Using CAPE](https://earlyretirementnow.com/2016/12/21/the-ultimate-guide-to-safe-withdrawal-rates-part-3-equity-valuation/)
Published: December 21, 2016.

### 1.2 CAPE Definition

The valuation measure is the **Shiller CAPE (Cyclically-Adjusted Price-to-Earnings)
ratio**:

```
CAPE = Price Level / (10-year rolling average of real earnings)
```

**Source:** Robert Shiller's dataset
(http://www.econ.yale.edu/~shiller/data/ie_data.xls)

**Historical baseline:** 1871–2016 (approximately)

**Evidence classification:** ARTICLE — explicit

### 1.3 CAPE Regime Classification

Four regimes, determined by the CAPE value observed **on the retirement start date**:

| Regime | CAPE Range | Description |
|--------|------------|-------------|
| <15    | CAPE < 15  | Below historical median |
| 15-20  | 15 ≤ CAPE < 20 | Moderate valuation |
| 20-30  | 20 ≤ CAPE < 30 | Elevated valuation |
| ≥30    | CAPE ≥ 30  | Extreme overvaluation |

**Boundary conditions:**
- CAPE 14.99 → <15
- CAPE 15.00 → 15-20
- CAPE 19.99 → 15-20
- CAPE 20.00 → 20-30
- CAPE 29.99 → 20-30
- CAPE 30.00 → ≥30

**Look-ahead prevention:** CAPE is classified **exactly once** at retirement start.
Future CAPE values are never consulted — replication invariant derived from the
article's methodology. The article explicitly describes the curves as corresponding
to CAPE regimes **at the beginning of retirement**.

**Evidence classification:** ARTICLE — explicit (regime boundaries); ARTICLE — chart-derived (average returns by regime); replication invariant (look-ahead prevention)

### 1.4 Article Experiments

The article presents **four distinct simulation configurations**, each testing a
different withdrawal strategy across CAPE regimes. The labels `expA`–`expD` below
are **internal FBF documentation labels**; ERN does not name these configurations.

**Experiment definitions:**

| Config | Withdrawal Rate | Terminal Value Target | Horizons | Equity Grid |
|--------|-----------------|----------------------|----------|-------------|
| expA   | 4.00%           | 0% (depletion)       | 30Y, 60Y | 0–100% in 5% increments |
| expB   | 4.00%           | 50% of initial wealth | 30Y, 60Y | 0–100% in 5% increments |
| expC   | 3.50%           | 50% of initial wealth | 30Y, 60Y | 0–100% in 5% increments |
| expD   | 3.25%           | 50% of initial wealth | 30Y, 60Y | 0–100% in 5% increments |

**Source qualification:**
- **4 experiment configurations:** ARTICLE — explicit (withdrawal rates and
  terminal values stated in text; each configuration presented separately with
  its own chart)
- **21 equity allocations [0%, 5%, 10%, …, 95%, 100%]:** ARTICLE — chart-derived
  (the article's simulation charts show equity allocation curves spanning 0% to
  100%, with plotted observations consistent with 5-percentage-point increments;
  this is the basis for interpreting the replication equity grid as 21 allocations)
- **2 horizons [30Y, 60Y]:** ARTICLE — explicit (stated in text and figure captions)

**Total (strict ERN replication):** 4 configurations × 21 equity allocations × 2 horizons = **168 parameter cells**

### 1.5 Temporal Alignment

**Retirement start date:** The date on which the first withdrawal occurs and the
CAPE regime is determined.

**CAPE observation:** CAPE is observed on the retirement start date. The FBF
canonical CAPE data is represented at month-start dates (e.g., `1881-01-01`)
following the Shiller dataset format. The article itself does not explicitly
specify whether its retirement-date CAPE lookup should be interpreted as
month-start or month-end.

**Cohort definition:** Each retirement start date is a cohort. Multiple horizons
(30Y, 60Y) are tested for each cohort.

**Historical study period:** Approximately 1871–2016, with the article discussing
over 1,700 possible retirement start dates.

**Ambiguity:** The article does not specify whether CAPE is aligned to month-start
or month-end. The FBF implementation uses month-start alignment based on the Shiller
dataset format. This alignment is assumed consistent with the article but is not
explicitly verified.

**Evidence classification:** ASSUMPTION — unresolved (temporal alignment details)

### 1.6 Article Charts

The article presents four chart pairs (30Y top panel, 60Y bottom panel):

**Chart 1:** 4% SWR, 0% terminal value (capital depletion)
**Chart 2:** 4% SWR, 50% terminal value
**Chart 3:** 3.5% SWR, 50% terminal value
**Chart 4:** 3.25% SWR, 50% terminal value

Each chart plots success rate as a function of equity allocation (0%–100%)
with separate lines for each CAPE regime (<15, 15-20, 20-30, ≥30).

**Equity grid evidence:** The article's simulation charts show equity allocation
curves spanning 0% to 100%, with plotted observations consistent with
5-percentage-point increments. The x-axis labels are at 10-point intervals, but
the plotted curve vertices show the underlying 5-point grid. This is the basis
for interpreting the replication equity grid as 21 allocations from 0% through
100%. The article does not explicitly enumerate the 21 values in prose.

**Evidence classification:** ARTICLE — chart-derived (chart structure, axes, and
equity grid resolution)

### 1.7 Published Numerical Anchors

The following six values are **explicitly stated in the article text** and serve
as **acceptance anchors** for replication validation. Each anchor includes its
conditioning (whether it is an overall result or CAPE-conditioned).

| Experiment | Horizon | Equity | CAPE Condition | Result | Source |
|------------|---------|--------|----------------|--------|--------|
| A (4% SWR, 0% TV) | 30Y | 100% | Published overall result | 89% | Line 74: "89% success rate over 30 years" |
| A (4% SWR, 0% TV) | 60Y | 100% | CAPE 20–30 | 72% | Line 74: "72% success rate with 100% equities" (context: CAPE 27) |
| B (4% SWR, 50% TV) | 60Y | 100% | CAPE 20–30 | 71% | Line 84: "lowers the success probability to 71%, from 72%" |
| C (3.5% SWR, 50% TV) | 60Y | 100% | Published overall result | 96% | Line 88: "96% success probability preserving 50% of the final value" |
| C (3.5% SWR, 50% TV) | 60Y | 100% | CAPE 20–30 | 88% | Line 88: "goes down to 88% when the CAPE ratio is between 20 and 30" |
| D (3.25% SWR, 50% TV) | 60Y | 100% | Published overall result | 97% | Line 96: "97% success probability with 100% equities" |

**Key distinction (inferred — not explicitly documented by ERN):** The 89%, 96%,
and 97% figures are published overall results, with no CAPE-regime condition
stated in the article. The available article evidence is consistent with the
overall calculations covering the full retirement-start universe. The 72%, 71%,
and 88% figures are CAPE-conditioned results reported for the specified CAPE
regime. Use the graph definitions/results in Part 3 as the source of truth for
the CAPE-conditioned filtering rather than inventing a different filtering rule.

**Evidence classification:** RESOLVED — user-directed resolution (article evidence as source of truth)

**Historical article statement — not an acceptance anchor:**

The article also states (line 88): "for CAPE values below 20, the 100% equity
portfolio had a 100% success rate, both over 30 and 60-year horizons" (3.5% SWR,
50% TV). This statement is retained as historical evidence but is **not used as
an acceptance anchor** because it is not independently suitable as a replication
anchor. It is not invalidated by the 2023 erratum (§1.8); it is simply excluded
from the acceptance oracle for replication-validation purposes.

**Qualitative observations (not exact anchors):**
- "close to 100% with an equity share of 80-90%" (line 96) — chart-derived
- "For the 30-year 4% rule, CAPE <15 had 100% success for equity weights greater than 40%" (line 70) — ARTICLE — explicit, corrected by the 2023 erratum
- "hump-shaped curve for CAPE >30" (line 74) — article explicit

**Evidence classification:** ARTICLE — explicit (all six numerical anchors); ARTICLE — chart-derived ("close to 100%")

### 1.8 Erratum

The article contains a factual error that was identified and acknowledged in
the comments (September 27–28, 2023).

**Original statement in article (line 70):**
> "Quite intriguingly, over the 30-year horizon (top panel) and for equity weights
> greater than 40%, every single failure of the 4% rule occurred when the CAPE was
> above 20 at the start of the retirement. In contrast, for all CAPE<20 you have a
> 100% success rate."

**Correction (identified by reader John, acknowledged by ERN):**
> The threshold should be 15, not 20. Failures occur when CAPE > 15, and for all
> CAPE < 15 there is a 100% success rate.

**Corrected statements:**
- "every single failure of the 4% rule occurred when the CAPE was above **15**"
- "for all CAPE < **15** you have a 100% success rate"

**The four CAPE regime boundaries remain unchanged.** The erratum concerns the
interpretation of the threshold associated with failures (15 vs 20), not the
regime definitions. The regime boundaries (<15, 15-20, 20-30, ≥30) are a separate
methodological choice that remains as originally stated.

**Evidence classification:** ARTICLE — explicit (erratum acknowledged in comments)

### 1.9 CAPE and Forward Returns — Contextual Evidence

The article explicitly states the approximate subsequent 10-year real equity
return associated with each CAPE regime. These observations are **not SWR
acceptance anchors**; they are contextual evidence explaining the motivation
for the Part 3 CAPE-based analysis.

| CAPE Regime | Approximate Subsequent 10Y Real Equity Return |
|-------------|----------------------------------------------:|
| CAPE < 15   |                                           ~9% |
| 15 ≤ CAPE < 20 |                                      just under 6% |
| 20 ≤ CAPE < 30 |                                        ~3% |
| CAPE ≥ 30   |                                      below −1% |

These values are explicitly stated in the article immediately before the SWR
simulation section. They establish that CAPE regimes have materially different
forward-return distributions, which motivates the CAPE-conditioned SWR analysis.

**Do not turn these into simulation acceptance criteria** unless the future
replication explicitly reproduces this separate CAPE/forward-return analysis.

**Evidence classification:** ARTICLE — explicit (contextual numerical evidence,
NOT SWR acceptance anchors)

## 2. Data Requirements

### 2.1 Required Data Sources

**Primary data sources:**
1. **Shiller CAPE data:** `ie_data.xls` or `ie_data.csv` from Shiller's website
2. **S&P 500 total return data:** `spx_tr_real.csv` (real, inflation-adjusted)
3. **10Y Treasury total return data:** `bond_10y_tr_real.csv` (real, inflation-adjusted)

**Data period:** 1871–2016 (approximately)

### 2.2 Canonical Data Audit

**S&P 500 real total returns (`spx_tr_real.csv`):**
- Format: `YYYY-MM-DD,value` (decimal monthly returns)
- Period: 1871-01 through 2016-09
- Content: Monthly real total returns for S&P 500
- **Status:** Available in canonical form

**10Y Treasury real total returns (`bond_10y_tr_real.csv`):**
- Format: `YYYY-MM-DD,value` (decimal monthly returns)
- Period: 1871-01 through 2016-09
- Content: Monthly real total returns for 10Y Treasury bonds
- **Status:** Available in canonical form

**CAPE data (`ern_cape_1871_2016.json`):**
- Format: JSON with monthly snapshots
- Period: 1881-01-01 through 2023-09-01 (1,571 unique snapshots)
- Content: CAPE values (Shiller P/E10 ratio)
- Note: `index_levels` in this file are placeholder values (1.0) — this file is
  a CAPE lookup source, not a simulation input
- **Filename explanation:** The filename `ern_cape_1871_2016.json` is potentially
  misleading. Despite the name suggesting coverage through 2016, the file actually
  contains CAPE observations from 1881-01-01 through 2023-09-01. The "1871" in
  the name refers to the underlying Shiller dataset start year (1871), not the
  CAPE observation start year (1881, after 10-year rolling average warmup).
- **Status:** Available in canonical form
- **Data-contract question (open):** If CAPE is treated as a reusable dated
  numerical time series, its representation should be evaluated against the
  canonical `YYYY-MM-DD,value` contract. The question is whether the current JSON
  is: (1) a reusable dated numerical time series, (2) a research-specific derived
  artifact, or (3) cohort metadata used for classification. That distinction must
  be established before any future canonical-data migration. Do NOT migrate or
  modify it now; the purpose is to document the question, not resolve it by
  assumption.

**Cohort manifest (`cohort_manifest_part3.json`):**
- Format: JSON with per-cohort metadata
- Period: 1871-02-01 through 2015-12-01 (1,739 cohorts)
- Content: CAPE values, regimes, and horizon constraints for each cohort
- **Status:** Pre-computed deterministic join of market availability and CAPE availability

### 2.3 Data Sufficiency Assessment

**Question: Does the current canonical data contain everything required for Part 3?**

**Answer: Data availability is RESOLVED. The canonical asset-return data is
available in `canonical/ern_asset_returns`. The blocking issues are
Part 3-specific methodology questions, not data availability.**

The Part 3 pipeline requires two independent data streams:
1. **Market returns** for portfolio simulation (equity and bond returns)
2. **CAPE values** for cohort classification by valuation regime

Both are present in the canonical dataset:
- Market returns are available in `canonical/ern_asset_returns`
- CAPE values are in `ern_cape_1871_2016.json`
- The cohort manifest joins these two sources deterministically

**Data availability is not the blocking issue.** The three Part 3-specific
methodology questions have been resolved:

1. **CAPE observation timing** — RESOLVED: Use the actual date of the canonical
   CAPE observation (§4.1)
2. **Pre-1881 cohort handling** — RESOLVED: Include pre-1881 cohorts; CAPE series
   should eventually be extracted to canonical CSV (§3.4)
3. **CAPE-conditioned filtering** — RESOLVED: Use the article graph definitions
   as the source of truth (§1.7)

**Evidence classification:** All three methodology questions RESOLVED

The pipeline architecture correctly separates these concerns:
```
Canonical market returns → FBF simulation → per-cohort success/failure
                    +                                     |
Starting CAPE → CAPE regime classification ────────────────┘
                    │
                    v
          aggregate by regime
```

**No additional source files have been identified as missing at this stage.** The
normalized `index_levels` in the CAPE file are irrelevant because the CAPE file is
not used for simulation — only for CAPE value lookup. The simulation uses the market
return CSVs directly.

However, **methodological sufficiency** for faithful ERN replication has not been
established. The following remain unresolved (see §4):
- Temporal alignment (month-start vs month-end)
- Withdrawal/return ordering (first-month inclusion/exclusion)
- Terminal-value calculation semantics
- Exact cohort construction methodology

**Evidence classification:** FBF — verified implementation (data flow architecture); ASSUMPTION — unresolved (methodological sufficiency)

---

## 3. Cohort Scope

### 3.1 Definitions

For clarity, the following distinctions are made:

| Term | Definition | Count | Source |
|------|------------|-------|--------|
| **Market cohorts** | Retirement start dates with market return data available | 1,739 | FBF manifest |
| **CAPE cohorts** | Retirement start dates with CAPE data available | 1,485 | FBF manifest |
| **Article cohorts** | Retirement start dates in ERN's historical period | ~1,700+ | ARTICLE — explicit |
| **30Y-valid cohorts** | Cohorts where 30-year horizon fits within dataset | See §3.4 | ASSUMPTION |
| **60Y-valid cohorts** | Cohorts where 60-year horizon fits within dataset | See §3.4 | ASSUMPTION |

### 3.2 Historical Cohort Universe

The article uses a historical dataset spanning approximately 1871–2016. ERN states
"over 1,700 possible retirement start dates" in the article text (line 39).

**Key facts:**
- Market return data spans 1871-01 through 2016-09
- CAPE data spans 1881-01 through 2023-09
- The cohort manifest defines 1,739 monthly cohorts from 1871-02 to 2015-12

**ERN's cohort construction (from article text):**
The article states: "we run our simulations and then compute success probabilities,
not just averaging over **all** observations but we also bucket the over 1,700
possible retirement start dates in our study by how cheap or expensive equities
were at the time."

This implies ERN:
1. Simulates **all ~1,700 retirement start dates** (including pre-1881 without CAPE)
2. Computes published overall results, with no CAPE-regime condition stated in the article, across all cohorts
3. **Then classifies** cohorts by CAPE regime for conditioned analysis
4. The available article evidence is consistent with pre-1881 cohorts being excluded
   from CAPE-conditioned results because they lack a valid starting CAPE, but the
   article does not explicitly document this cohort-filtering rule.

**Evidence classification:** ARTICLE — explicit (simulation of all cohorts); ASSUMPTION — unresolved (exact handling of pre-1881 cohorts in CAPE-conditioned results)

### 3.3 FBF Fixed Cohort Universe

The FBF implementation uses the pre-computed manifest (`cohort_manifest_part3.json`)
which defines 1,739 cohorts. This is a fixed, deterministic artifact.

**Cohort range:** 1871-02-01 through 2015-12-01

**CAPE availability:**
- 254 cohorts (1871-02 through 1880-12) lack CAPE data (insufficient history for
  10-year rolling average)
- 1,485 cohorts (1881-01 through 2015-12) have CAPE data

**FBF convention (not necessarily ERN methodology):**
FBF uses a fixed 1,739-cohort universe for both horizons because the framework
derives the cohort universe from the longest configured horizon and uses shorter
horizons as slices of the same cohort set. This is an implementation convention,
not necessarily how ERN constructs the cohort universe.

**Evidence classification:** FBF — verified implementation (manifest structure); ASSUMPTION — unresolved (whether ERN uses identical cohort policy)

### 3.4 Relationship: CAPE Observations vs. Simulation Cohorts — RESOLVED

The pre-1881 CAPE values are already present in the canonical `ern_asset_returns`
data and should be included when the corresponding overall results require them.
The CAPE series should eventually be extracted into its own canonical CSV rather
than remaining embedded only in `ern_asset_returns`. This is a data-organization
task, not a methodology blocker.

Do not remove the pre-1881 cohorts merely because the CAPE dataset has historically
been treated separately.

**Evidence classification:** RESOLVED — user-directed resolution

---

## 4. Temporal Alignment

### 4.1 CAPE Observation Timing — RESOLVED

**Resolution:** CAPE is observed at the date on which the observation is recorded.
A CAPE value dated `31/01/1871` is the CAPE observation for `31/01/1871`.
Use the actual date of the canonical CAPE observation; do not shift it to the
beginning or end of another month.

**Evidence classification:** RESOLVED — user-directed resolution

### 4.2 Retirement Start Date

**Article convention:** The retirement start date is when the first withdrawal occurs.

**FBF convention:** The retirement start date is the cohort date from the manifest
(e.g., "1881-01-01"). The first withdrawal occurs at the start of the month.

**Alignment:** Both conventions appear consistent, but the article's exact
convention is not explicitly stated.

**Evidence classification:** ASSUMPTION — unresolved

### 4.3 Market Return Timing

**Article convention:** The article does not specify the exact timing of market
returns relative to withdrawal dates.

**FBF convention:** Market returns are applied monthly. The simulation compounds
returns from the cohort start date through the horizon.

**Ambiguity:** Whether the first month's return is included or excluded at the
cohort start is not explicitly specified in the article.

**Evidence classification:** ASSUMPTION — unresolved

### 4.4 Summary of Temporal Alignment

The temporal alignment between CAPE, retirement start, and market returns is
**assumed consistent** between the article and FBF implementation, but the
article does not provide sufficient detail to verify this assumption. The key
assumptions are:

1. CAPE is observed at month-start on the retirement date
2. The first withdrawal occurs at the start of the retirement month
3. Market returns compound from the retirement date forward
4. No one-month offset exists between CAPE observation and simulation start

These assumptions are plausible but not explicitly verified.

**Evidence classification:** ASSUMPTION — unresolved (all temporal alignment details)

---

## 5. FBF Implementation

### 5.1 Architecture

The FBF Part 3 implementation uses the existing simulation framework with a
research-specific orchestration layer:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Part 3 Research Pipeline                      │
├─────────────────────────────────────────────────────────────────┤
│  1. Load cohort manifest (CAPE classifications)                 │
│  2. Load market return dataset (for actual simulation)          │
│  3. Plan simulations (parameter sweep × cohort validation)      │
│  4. Execute simulations (engine + policies)                     │
│  5. Aggregate results (by CAPE regime, equity, horizon, etc.)  │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 Configuration

**Study YAML:** `examples/studies/ern_part3_replication.yaml`

**Current FBF configuration (needs future correction):**
- 5 equity weights: [0.10, 0.25, 0.50, 0.75, 1.00] **(incorrect — should be 21)**
- 3 withdrawal rates: [0.0325, 0.035, 0.04]
- 2 terminal value targets: [0.0, 0.5]
- 2 horizons: [30Y, 60Y]
- **Current total:** 5W × 3R × 2FV × 2H = 60 cells
- **Corrected total (once equity grid is fixed):** 3R × 2FV × 21E × 2H = 252 cells

**Strict ERN replication (from §1.4):**
- 4 experiment configurations with specific (W, FV) pairs:
  - 4.00% SWR + 0% final-value target
  - 4.00% SWR + 50% final-value target
  - 3.50% SWR + 50% final-value target
  - 3.25% SWR + 50% final-value target
- 21 equity allocations: 0%, 5%, 10%, …, 95%, 100% (chart-derived)
- 2 horizons: [30Y, 60Y] (explicit)
- **Total parameter cells:** 4 × 21 × 2 = **168 cells**

**Key discrepancy — the YAML does not yet represent the strict ERN experiment grid:**

The YAML uses a Cartesian product over all axes, which produces a superset of the
article's four configurations. Once the equity grid is corrected to 21 values, the
YAML would produce 3 rates × 2 FV targets × 21 equity × 2 horizons = **252 cells**.

The extra FBF combinations **not in the article** are:
- 3.25% SWR + 0% final-value target
- 3.50% SWR + 0% final-value target

Each produces 21 equity × 2 horizon = 42 additional cells, giving exactly 84
extra cells beyond the strict 168-cell replication.

**The article's methodology is experiment-oriented, not Cartesian.** The four
configurations are presented separately, each with its own chart. The future
implementation should either explicitly enumerate the four experiment
specifications or provide an equivalent representation that preserves those four
exact (withdrawal rate, final-value target) pairs. Do not define the strict
replication as an unrestricted Cartesian product.

**No YAML modification is performed in this audit.** The YAML discrepancy is
documented here and must be resolved when the actual Part 3 implementation is
performed.

### 5.3 Data Flow

The implementation correctly separates simulation data from classification metadata:

1. **Market returns** (`spx_tr_real.csv`, `bond_10y_tr_real.csv`)
   are loaded by `load_ern_dataset()` and used for actual portfolio simulation.

2. **CAPE values** (`ern_cape_1871_2016.json`) are pre-joined into the cohort
   manifest (`cohort_manifest_part3.json`) as metadata.

3. **CAPE never enters the simulation engine.** The engine receives only market
   trajectory, policies, and horizon.

4. **Aggregation** groups simulation results by CAPE regime using the manifest
   metadata.

**Evidence classification:** FBF — verified implementation (data flow architecture)

### 5.4 Current Implementation Status

**Verified from code inspection:**
- Market data can be loaded via `load_ern_dataset()`
- CAPE metadata can be loaded via `load_manifest()`
- Regime classification exists in `cape_regime.py`
- Simulations can be executed via `execute_study_plan()`
- Results can be aggregated by CAPE regime via `aggregate_part3_results()`

**Not yet verified against ERN:**
- Exact cohort universe (1,739 vs article's "~1,700")
- Exact temporal alignment (month-start vs month-end)
- Exact withdrawal/return ordering (first-month inclusion/exclusion)
- Exact terminal-value calculation semantics
- Exact CAPE conditioning in aggregation
- Exact reproduction of article chart results

**Conclusion:** The Part 3 pipeline has the **conceptual architecture** to produce
ERN-style results. However, "structurally complete" does not imply "replication-ready."
The implementation needs verification against the article's exact methodology before
it can be considered a faithful replication.

**Evidence classification:** FBF — verified implementation (architecture); ASSUMPTION — unresolved (replication fidelity)

---

## 6. Oracle Evidence

### 6.1 Published Numerical Anchors

The following six values are **explicitly stated in the article text** and serve
as **acceptance anchors** for replication validation. Each anchor includes its
conditioning dimension.

| Experiment | Horizon | Equity | CAPE Condition | Result | Source |
|------------|---------|--------|----------------|--------|--------|
| A (4% SWR, 0% TV) | 30Y | 100% | Published overall result | 89% | Line 74 |
| A (4% SWR, 0% TV) | 60Y | 100% | CAPE 20–30 | 72% | Line 74 |
| B (4% SWR, 50% TV) | 60Y | 100% | CAPE 20–30 | 71% | Line 84 |
| C (3.5% SWR, 50% TV) | 60Y | 100% | Published overall result | 96% | Line 88 |
| C (3.5% SWR, 50% TV) | 60Y | 100% | CAPE 20–30 | 88% | Line 88 |
| D (3.25% SWR, 50% TV) | 60Y | 100% | Published overall result | 97% | Line 96 |

**Key distinction (inferred — not explicitly documented by ERN):**
- **Published overall results (89%, 96%, 97%):** These published values are
  reported with no CAPE-regime condition stated in the article. The available
  article evidence is consistent with the overall calculations covering the full
  retirement-start universe. The exact cohort-filtering mechanics are not
  explicitly documented by ERN. Do not invent a formal ERN denominator or
  filtering algorithm that the article does not document.
- **CAPE-conditioned (72%, 71%, 88%):** These published values are reported for
  the specified CAPE regime. The available article evidence is consistent with the
  conditioned calculations using only cohorts with a valid starting CAPE falling
  within that regime.

**Historical article statement — not an acceptance anchor:**

The article also states (line 88): "for CAPE values below 20, the 100% equity
portfolio had a 100% success rate, both over 30 and 60-year horizons" (3.5% SWR,
50% TV). This statement is retained as historical evidence but is **not used as
an acceptance anchor** because it is not independently suitable as a replication
anchor. It is not invalidated by the 2023 erratum (§1.8); it is simply excluded
from the acceptance oracle for replication-validation purposes.

### 6.2 Qualitative Conclusions

The article states the following qualitative conclusions. Each is qualified with
its evidence classification.

- Success rates decrease with CAPE for most configurations (within same experiment)
  — ARTICLE — explicit, but with noted exception (hump-shaped for CAPE ≥30, 60Y, 4% SWR)
- Lower SWR → higher success rates (across experiments) — ARTICLE — explicit
- Higher terminal value target → lower success rates (at same SWR) — ARTICLE — explicit
- 30Y horizons → higher success rates than 60Y (at same parameters) — ARTICLE — explicit
- For CAPE <15, the article reports 100% success for 30-year 4% SWR portfolios with equity weights greater than 40% — ARTICLE — explicit (with equity condition)
- For CAPE ≥30, success rates are lower but improve with lower SWR — ARTICLE — chart-derived

**Note:** The article explicitly discusses a **hump-shaped** equity-success
relationship for CAPE ≥30 in the 60-year 4% case (line 74: "for a seriously
overvalued equity market (CAPE above 30) you do get a bit of a hump-shaped curve").
This is an exception to the general monotonic relationship between equity allocation
and success rate.

**Evidence classification:** ARTICLE — explicit (conclusions); ARTICLE — chart-derived (hump-shaped observation)

### 6.3 Chart Observations

The four chart pairs (Figures 1-4 in the article) show success rate curves
across equity allocations for each CAPE regime. These charts contain visual
information that is not explicitly quantified in the article text.

**Classification:** These are **approximate values readable from charts**.
They should not be used as exact numerical anchors without explicit
article confirmation.

**Evidence classification:** ARTICLE — chart-derived

---

## 7. Replication Scope

### 7.1 Strict Replication

For strict ERN Part 3 replication:

**Article experiment configurations (internal labels expA–expD; ERN does not name these):**
- expA: 4% SWR, 0% TV, 30Y/60Y, 0–100% equity in 5% increments
- expB: 4% SWR, 50% TV, 30Y/60Y, 0–100% equity in 5% increments
- expC: 3.5% SWR, 50% TV, 30Y/60Y, 0–100% equity in 5% increments
- expD: 3.25% SWR, 50% TV, 30Y/60Y, 0–100% equity in 5% increments

**Equity grid:** 21 allocations [0%, 5%, 10%, …, 95%, 100%] — ARTICLE — chart-derived

**Total:** 4 configurations × 21 equity allocations × 2 horizons = **168 parameter cells**

**Cohort range (article):** over 1,700 possible retirement start dates; exact
monthly range not explicitly specified.

**Cohort range (FBF):** 1,739 cohorts, 1871-02 through 2015-12, of which 1,485
have CAPE data.

**Simulation units (article):** 168 cells × ~1,700 cohorts ≈ 285,600 units (approximate)

**Simulation units (FBF):** 168 cells × 1,739 cohorts = 292,152 units

### 7.2 FBF Extended Configuration (not ERN replication)

The current FBF YAML uses a Cartesian product that, once the equity grid is
corrected to 21 values, would result in 252 parameter cells
(3R × 2FV × 21E × 2H), which is a superset of the article's 168 cells.

**Extra FBF combinations not in the article:**
- 3.25% SWR with 0% final-value target
- 3.50% SWR with 0% final-value target

Each produces 21 equity × 2 horizon = 42 additional cells, giving exactly 84
extra cells beyond the strict 168-cell replication. These extra combinations are
**not part of the canonical Part 3 replication**. They are FBF extensions that
must not be described as part of the ERN study.

**Current YAML state (not yet corrected):** The existing YAML uses only 5 equity
weights and therefore produces 60 cells. This is both a different equity grid
and a different experiment specification from the article. No YAML modification
is performed in this audit.

### 7.3 Validation Approach

For ERN-style validation:

1. **Numerical anchors:** Use the six explicitly stated numerical anchors from
   Section 6.1 (distinguishing overall vs CAPE-conditioned). The CAPE <20 / 100%
   historical article statement is not used as an acceptance anchor.
2. **Boundary verification:** Test CAPE regime boundaries exactly (<15, 15-20, 20-30, ≥30)
3. **Cross-regime comparisons:** Verify only the specific cross-regime relationships
   explicitly supported by the article. Do not impose universal monotonicity of
   success rates with CAPE as a framework invariant.
4. **Temporal consistency:** Verify 30Y vs. 60Y relationships
5. **Qualitative conclusions:** Verify the conclusions from Section 6.2

---

## 8. Gaps and Discrepancies

### 8.1 Data Gaps

**No missing source files have been identified.** The canonical market-return and
CAPE datasets required by the documented data flow are available. This does not
establish methodological sufficiency for faithful ERN replication; the unresolved
temporal, cohort, and simulation-ordering questions remain documented below.

### 8.2 Methodology Gaps

1. **Cohort count discrepancy**
   - Article: "over 1,700 possible retirement start dates" (line 39)
   - Manifest: 1,739 total cohorts, 1,485 with CAPE
   - **Impact:** FBF uses the manifest's fixed cohort universe, which is
     consistent with the article's approximate count
   - **Evidence classification:** ARTICLE — explicit (count); FBF — verified implementation (manifest)

2. **Experiment grid discrepancy**
   - Article: 4 experiment configurations with specific (W, FV) combinations,
     21 equity allocations (chart-derived), 2 horizons = 168 parameter cells
   - FBF YAML (current): 5 equity weights × 3 rates × 2 FV targets × 2 horizons = 60 cells
   - FBF YAML (once equity grid corrected): 21 equity × 3 rates × 2 FV × 2 horizons = 252 cells
   - **Impact:** The current FBF config has both a different equity grid (5 vs 21)
     and a different experiment specification (Cartesian product vs. 4 named
     configurations). Once the equity grid is corrected, the Cartesian product
     produces 84 extra cells (3.25%/0% and 3.5%/0% not in article). These should
     be documented as FBF extensions, not Part 3 replication.
   - **Evidence classification:** ARTICLE — explicit (experiments); ARTICLE — chart-derived (21 equity allocations); FBF — verified implementation (config)

3. **CAPE data period**
   - Article: ~1871-2016 (baseline)
   - FBF CAPE data: 1881-01-01 to 2023-09-01 (extended)
   - **Impact:** FBF includes post-2016 CAPE observations. Post-2016 CAPE
     observations must not silently participate in the Part 3 replication. The
     existence of later CAPE observations is not itself a problem, provided the
     historical cohort/date selection prevents them from entering the replication.
     A future E2E/data-selection test should prove this invariant.
   - **Evidence classification:** ARTICLE — explicit (baseline); FBF — verified implementation (data); replication invariant (post-2016 exclusion)

### 8.3 Implementation Gaps

**Verified from code inspection:**
- Market data loading works correctly
- CAPE metadata loading works correctly
- Regime classification exists and is correct
- Simulation execution works correctly
- Aggregation by CAPE regime works correctly

**Not yet verified against ERN:**
- Exact cohort universe construction
- Exact temporal alignment semantics
- Exact withdrawal/return ordering
- Exact terminal-value calculation
- Exact reproduction of article results

**Conclusion:** The implementation has the **conceptual architecture** to produce
ERN-style results, but replication fidelity has not been demonstrated.

**Evidence classification:** FBF — verified implementation (architecture); ASSUMPTION — unresolved (replication fidelity)

### 8.4 Temporal Alignment Ambiguity

The article does not explicitly specify:
- Whether CAPE is aligned to month-start or month-end
- The exact timing of market returns relative to withdrawal dates
- Whether the first month's return is included or excluded

The FBF implementation assumes month-start alignment consistent with the Shiller
dataset format. This assumption is plausible but not verified.

**Evidence classification:** ASSUMPTION — unresolved

---

## 9. Workload Summary

### 9.1 Current FBF Configuration (needs future correction)

| Parameter | Value |
|-----------|-------|
| Equity weights | 5 (10%, 25%, 50%, 75%, 100%) **(incorrect — article uses 21)** |
| Withdrawal rates | 3 (3.25%, 3.5%, 4.0%) |
| Terminal value targets | 2 (0%, 50%) |
| Horizons | 2 (30Y, 60Y) |
| Parameter cells (current) | 5 × 3 × 2 × 2 = 60 |
| Parameter cells (once equity corrected) | 21 × 3 × 2 × 2 = 252 |
| Cohorts (total) | 1,739 |
| Cohorts (CAPE-available) | 1,485 |
| **Simulation units (current)** | 60 × 1,739 = 104,340 |
| **Simulation units (once equity corrected)** | 252 × 1,739 = 438,228 |

### 9.2 Strict ERN Replication (article)

| Parameter | Value |
|-----------|-------|
| Experiment configurations | 4 (expA, expB, expC, expD; internal labels — ERN does not name these) |
| Equity allocations | 21 (0%, 5%, 10%, …, 95%, 100%) — chart-derived |
| Horizons | 2 (30Y, 60Y) — explicit |
| Parameter cells | 4 × 21 × 2 = **168** |
| Cohorts | ~1,700+ (article); 1,739 (FBF manifest) |
| **Simulation units** | 168 × ~1,700 ≈ 285,600 (article); 168 × 1,739 = 292,152 (FBF) |

### 9.3 Data Requirements

| Data | File | Status |
|------|------|--------|
| CAPE values | `ern_cape_1871_2016.json` | ✅ Available |
| S&P 500 returns | `spx_tr_real.csv` | ✅ Available |
| 10Y Treasury returns | `bond_10y_tr_real.csv` | ✅ Available |
| Cohort manifest | `cohort_manifest_part3.json` | ✅ Available |

---

## 10. Acceptance Criteria

### 10.1 Data Completeness

- [x] CAPE source traced to Shiller `ie_data.xls`
- [x] No synthetic CAPE values used
- [x] Market return data available in canonical CSVs
- [x] CAPE data available in canonical JSON
- [x] Cohort manifest available with deterministic join
- [x] Filename explanation for `ern_cape_1871_2016.json` documented

### 10.2 Methodology Fidelity

- [x] Article methodology documented (4 experiment configurations, 21 equity allocations, 2 horizons)
- [x] 21 equity allocations documented as chart-derived evidence
- [x] CAPE regime boundaries verified (<15, 15-20, 20-30, ≥30)
- [x] Article erratum documented (threshold 15, not 20)
- [x] Published overall vs CAPE-conditioned distinction documented (safer terminology)
- [x] CAPE forward-return contextual evidence documented (§1.9)
- [x] CAPE look-ahead prevention labeled as replication invariant
- [x] Known FBF conventions documented
- [x] YAML discrepancy documented (168 strict cells vs 252 FBF Cartesian cells)
- [ ] Exact ERN/FBF temporal equivalence verified
- [ ] Exact ERN cohort construction verified
- [ ] Exact ERN withdrawal/return ordering verified
- [ ] Exact CAPE cohort-filtering mechanics verified
- [ ] Post-2016 CAPE exclusion invariant verified

### 10.3 Numerical Validation

The following six anchors are the future replication acceptance criteria. Do not
mark them as passed merely because the current FBF implementation has not yet
been compared against them.

- [ ] 4% SWR, 0% TV, 60Y, 100% equity, CAPE 20–30: 72% (anchor)
- [ ] 4% SWR, 0% TV, 30Y, 100% equity, published overall result: 89% (anchor)
- [ ] 4% SWR, 50% TV, 60Y, 100% equity, CAPE 20–30: 71% (anchor)
- [ ] 3.5% SWR, 50% TV, 60Y, 100% equity, published overall result: 96% (anchor)
- [ ] 3.5% SWR, 50% TV, 60Y, 100% equity, CAPE 20–30: 88% (anchor)
- [ ] 3.25% SWR, 50% TV, 60Y, 100% equity, published overall result: 97% (anchor)
- [ ] Cross-regime patterns validated (article-specific relationships only, not universal monotonicity)

### 10.4 Implementation Completeness

- [x] Part 3 pipeline architecture verified
- [x] Market return data loading verified
- [x] CAPE metadata separation verified
- [x] Aggregation by regime verified
- [ ] Replication fidelity against article demonstrated

---

## 11. References

### 11.1 Primary Sources

- **ERN Part 3 Article:** https://earlyretirementnow.com/2016/12/21/the-ultimate-guide-to-safe-withdrawal-rates-part-3-equity-valuation/
- **Shiller Data:** http://www.econ.yale.edu/~shiller/data/ie_data.xls

### 11.2 FBF Documentation

- **Part 1 Replication:** `docs/research/ern_part1_replication.md`
- **Part 2 Replication:** `docs/research/ern_part2_replication.md`
- **Dataset Guide:** `DATASETS.md`
- **Architecture:** `ARCHITECTURE.md`

### 11.3 Code References

- **CAPE Regime Classification:** `src/fbf/core/domain/policies/cape_regime.py`
- **Part 3 Planner:** `src/fbf/core/research/part3_planner.py`
- **Part 3 Pipeline:** `src/fbf/core/research/part3_pipeline.py`
- **Part 3 Aggregation:** `src/fbf/core/research/part3_aggregation.py`
- **Part 3 YAML:** `examples/studies/ern_part3_replication.yaml`
- **Cohort Manifest:** `data/ern/cohort_manifest_part3.json`
