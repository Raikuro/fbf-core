# ERN Part 19 — Equity Glidepaths in Retirement

> **Status:** DOCUMENTATION — COMPLETE
>
> **Article:** [The Ultimate Guide to Safe Withdrawal Rates – Part 19: Equity Glidepaths in Retirement](https://earlyretirementnow.com/2017/09/13/the-ultimate-guide-to-safe-withdrawal-rates-part-19-equity-glidepaths/)
>
> **Implementation relationship:** Part 19 glidepath definitions are represented within the existing `ern_part20.yaml` configuration and `GlidepathAllocationPolicy`. Part 20 extends Part 19 with 8 additional passive-only glidepaths and 30-year horizons. Whether Part 20 reproduces Part 19 Experiment A is deferred.
>
> **Methodology status:** COMPLETE — global monthly sequencing and ATH rules established. FBF implementation execution order not yet aligned to established rule.
>
> **E2E status:** NOT YET VALIDATED as canonical ERN replication. Implementation alignment pending.

---

## 1. Article Methodology

### 1.1 Central Question

Do equity glidepaths (time-varying stock/bond allocations that increase equity exposure over retirement) improve safe withdrawal rates compared to static allocations?

### 1.2 Core Concept

A rising equity glidepath starts with a lower equity allocation and gradually increases it over time. The rationale is that during early retirement — the period of highest sequence-of-return risk — the retiree withdraws primarily from bonds, avoiding selling equities at depressed prices during a market downturn.

### 1.3 Simulation Assumptions

**Article — explicit:**
- Monthly data from January 1871 to July 2017
- 60-year retirement horizon (primary analysis)
- Retirement dates from January 1871 to December 2015 (with extrapolations using conservative return forecasts beyond July 2017)
- Final value targets of 0% (Capital Depletion), 50% of initial real value, and 100% of initial portfolio
- Portfolio assets: S&P 500 (equity) and 10-Year Treasury (bonds)
- Monthly CPI-inflation adjustment to withdrawals
- SWR = initial withdrawal rate that exactly achieves the final target value after the horizon

### 1.4 Static Allocations

The article simulates 21 static stock/bond allocations: 0% to 100% stocks in 5% increments.

### 1.5 Glidepath Parameters

**Article — explicit:**

| Dimension | Values | Source |
|-----------|--------|--------|
| End points (final equity weight) | 80%, 100% | Line ~50 |
| Starting points | 20, 40, 60 percentage points below end point | Line ~52 |
| Slopes | Two per starting-point combination | Line ~55 |
| Modes | Passive, Active | Line ~70 |

**Slope details (article — explicit):**
- Starting 20pp below end: slopes 0.2% and 0.3% per month
- Starting 40pp below end: slopes 0.3% and 0.4% per month
- Starting 60pp below end: slopes 0.4% and 0.5% per month

**Mode definitions (article — explicit):**
- **Passive:** Equity weight increases every month by the slope parameter, regardless of market conditions.
- **Active:** Equity weight increases only when the S&P 500 index is below its all-time high ("underwater"). When the market is at an all-time high, the allocation stays unchanged.

**Transition duration:** The article notes transitions take "anywhere between 5.5 and 13 years" depending on parameters.

### 1.6 Cohort Construction

**Article — explicit:**
- "over 1,700 possible retirement start dates" (line 39)
- Monthly frequency from 1871 to 2015
- For each cohort, the SWR that exactly achieves the final target is computed

### 1.7 Published Qualitative Conclusions

**Article — explicit:**

1. "There will be at least a few glidepaths with lower failure rates than the static allocations."
2. "The 80% to 100% and 60% to 100% glidepaths deliver consistently lowest failure rates, regardless of the final value target."
3. "The maximum long-term equity weight delivers the lowest risk."
4. "The very long transitions over 60 percentage points (20 to 80% and 40 to 100%) tend to be pretty consistently inferior to the other glidepaths."
5. "The 20 to 80% glidepaths are even inferior to the static 80% and 100% allocations."
6. "Most glidepaths pretty consistently beat the static equity weights" when CAPE > 20.
7. "The consistently best performers are the 60 to 100% glidepaths and the active glidepaths perform slightly better than the passive ones."
8. "The failure rates are less than half those in the static allocation simulations!" (for CAPE > 20)
9. "A glidepath will deliver a higher safe withdrawal rate if you have an equity drawdown early on in retirement. But the opposite is true as well."
10. "That 60 to 100% glidepath that performed so well during the major Sequence of Return Risk disasters will also underperform if stocks rally during the first few years of retirement."

### 1.8 Charts and Tables

**Article — explicit (4 charts + 1 table):**

1. **Failure Rates of 3.5% Rule — All CAPE:** 60%/80%/100% static vs glidepaths with 80% final (top) and 100% final (bottom)
2. **Failure Rates of 3.5% Rule — CAPE > 20:** Same structure as chart 1, conditional on CAPE > 20
3. **Failsafe and Percentile SWR Table:** Failsafe, 1st, 5th, 10th, 25th percentiles for static allocations and all 24 glidepaths, both All-CAPE and CAPE > 20
4. **SWR Comparison at Market Peaks/Troughs:** Static 60%/80%/100% vs 60→100% glidepath (0.4% slope, passive)

---

## 2. Part 19 Experiment Grid

### 2.1 Glidepaths

**Article — explicit (24 glidepaths):**

| # | Start | End | Slope | Mode | End-Start |
|---|-------|-----|-------|------|-----------|
| 1 | 60% | 80% | 0.2% | passive | 20pp |
| 2 | 60% | 80% | 0.3% | passive | 20pp |
| 3 | 60% | 80% | 0.2% | active | 20pp |
| 4 | 60% | 80% | 0.3% | active | 20pp |
| 5 | 40% | 80% | 0.3% | passive | 40pp |
| 6 | 40% | 80% | 0.4% | passive | 40pp |
| 7 | 40% | 80% | 0.3% | active | 40pp |
| 8 | 40% | 80% | 0.4% | active | 40pp |
| 9 | 20% | 80% | 0.4% | passive | 60pp |
| 10 | 20% | 80% | 0.5% | passive | 60pp |
| 11 | 20% | 80% | 0.4% | active | 60pp |
| 12 | 20% | 80% | 0.5% | active | 60pp |
| 13 | 80% | 100% | 0.2% | passive | 20pp |
| 14 | 80% | 100% | 0.3% | passive | 20pp |
| 15 | 80% | 100% | 0.2% | active | 20pp |
| 16 | 80% | 100% | 0.3% | active | 20pp |
| 17 | 60% | 100% | 0.3% | passive | 40pp |
| 18 | 60% | 100% | 0.4% | passive | 40pp |
| 19 | 60% | 100% | 0.3% | active | 40pp |
| 20 | 60% | 100% | 0.4% | active | 40pp |
| 21 | 40% | 100% | 0.4% | passive | 60pp |
| 22 | 40% | 100% | 0.5% | passive | 60pp |
| 23 | 40% | 100% | 0.4% | active | 60pp |
| 24 | 40% | 100% | 0.5% | active | 60pp |

**Verification:** 6 starting/end combinations × 2 slopes × 2 modes = 24 glidepaths. ARTICLE — explicit.

### 2.2 Other Parameter Dimensions

| Dimension | Values | Source |
|-----------|--------|--------|
| SWR | 3.5% (primary), failsafe computed | ARTICLE — explicit |
| Horizon | 60 years | ARTICLE — explicit |
| Final value targets | 0% (Capital Depletion), 50%, 100% | ARTICLE — explicit |
| Static allocations | 21 (0% to 100% in 5% steps) | ARTICLE — explicit |
| CAPE conditioning | All CAPE, CAPE > 20 | ARTICLE — explicit |

### 2.3 Experiment Structure

The article contains two distinct experiments with different outputs:

**Experiment A: Fixed 3.5% SWR failure-rate analysis**
- 27 allocation strategies (3 static allocations + 24 glidepaths)
  - Static allocations: 60%, 80%, 100% equity (the three shown in the failure-rate charts)
  - Glidepaths: all 24
- × 3 final value targets (0%, 50%, 100%)
- × 1 horizon (60Y)
- × 2 CAPE conditions (All CAPE, CAPE > 20)
- = **162 strategy × target × CAPE cells** (before aggregation)
- **Output:** failure rate at fixed 3.5% withdrawal rate (chart-derived, qualitative)

**Experiment B: Failsafe and percentile SWR analysis**
- 45 allocation strategies (21 static + 24 glidepaths)
  - Static allocations: all 21 (0% to 100% in 5% steps)
  - Glidepaths: all 24
- × 1 final value target (0% — capital depletion)
- × 1 horizon (60Y)
- × 2 CAPE conditions (All CAPE, CAPE > 20)
- = **90 strategy × CAPE cells**
- **Output:** per-cohort SWR distribution, failsafe SWR, and percentile SWRs (published numerical values)

**Key distinction:** Experiment A evaluates a fixed 3.5% withdrawal rate. Experiment B computes the distribution of cohort-specific SWRs and publishes explicit numerical values. Experiment B has stronger published numerical evidence than Experiment A.

**Overlap:** Experiment B's FV=0% allocation/CAPE combinations overlap with Experiment A's FV=0% cells (for the 3 static allocations and 24 glidepaths). However, the outputs are different: Experiment A produces failure rates at 3.5%, while Experiment B produces the SWR distribution. Computational reuse may reduce the execution workload, but the amount of reuse is an implementation decision and is not part of the replication specification.

**Evidence classification:** ARTICLE — explicit (structure); exact cell counts are inferred from article structure.

---

## 3. Glidepath Semantics

### 3.1 Passive Glidepath

**Article — explicit:**
- Equity weight increases every month by the slope parameter until reaching the endpoint
- The transition takes "anywhere between 5.5 and 13 years" depending on parameters

**FBF representation:** `min(start_equity + slope × month_index, end_equity)` — month 0 uses the starting allocation unchanged (see §6.3).

**FBF implementation:** `GlidepathAllocationPolicy(mode="passive")` — `src/fbf/core/domain/policies/glidepath.py:82-83`

### 3.2 Active Glidepath

**Article — explicit:**
- Equity weight increases only when the S&P 500 is "underwater" (below its all-time high)
- When the market is at an all-time high, the allocation stays unchanged

**ATH / underwater semantics — RESOLVED GLOBALLY:**

The ATH is always **Nominal + Total Return**. The established rule:

For each month (e.g., February):
1. February value = January value × (1 + January→February return)
2. If February value >= running_ATH → fresh ATH established; running_ATH = February value
3. If February value < running_ATH → market is underwater

**Comparison:** inclusive (`>=`). Being exactly at the ATH is **not underwater**.

**Running ATH:** maximum nominal total-return value observed so far.

**Fresh ATH:** current value reaches or exceeds the running ATH being tracked.

**FBF implementation:** `GlidepathAllocationPolicy(mode="active")` — `src/fbf/core/domain/policies/glidepath.py:86-89`

**FBF — implementation alignment pending:** The FBF implementation uses the equity total return index level from the dataset and computes `is_underwater = eq_level < running_ath`. The semantic is equivalent once the FBF execution order is aligned to the established sequencing rule (returns applied before cash-flow decisions).

### 3.3 Allocation Application Order

**Article — VERIFIED (Part 1 §3):**

ERN's monthly simulation sequence is:

1. The portfolio receives the current month's real return.
2. The withdrawal is then made.
3. The portfolio is rebalanced to the target equity/bond allocation.

The glidepath allocation is determined at the rebalancing step, after the return has been applied and the withdrawal has been taken.

**FBF implementation:** The pipeline applies allocations in this order:
1. Withdrawal (step 20-30)
2. Allocation decision (step 40)
3. Portfolio rebalance (step 50)
4. Market evolution (step 60)

**Material difference:** FBF applies returns last (after withdrawal and rebalancing), while ERN applies returns first (before withdrawal and rebalancing). This is a material algorithmic difference documented in §6.2.

### 3.4 Rebalancing

**Article — explicit:** The glidepath allocation changes monthly (the equity weight increases by the slope parameter each month in passive mode, or only when underwater in active mode).

**Article — not explicitly specified:** The exact rebalancing mechanics (how the portfolio is adjusted to match the target allocation, whether partial rebalancing is used, transaction cost handling).

**FBF — verified implementation:** `PortfolioRebalanceStep` (step 50) rebalances the portfolio to match the target allocation weights in full each month.

**ASSUMPTION — unresolved:** Whether the article's implicit rebalancing matches FBF's full monthly rebalancing. The article implies monthly rebalancing but does not explicitly state the complete algorithm.

---

## 4. Data Requirements and Canonical-Data Audit

### 4.1 Required Data

**Article — explicit (methodological inputs):**
- S&P 500 total return index (real, inflation-adjusted)
- 10-Year Treasury total return index (real, inflation-adjusted)
- CPI inflation index (used for inflation-adjusting withdrawals)
- Monthly frequency from 1871 to 2017

**FBF runtime inputs:**
- `spx_tr_real.csv` — canonical S&P 500 real returns (already inflation-adjusted)
- `bond_10y_tr_real.csv` — canonical 10Y bond real returns (already inflation-adjusted)
- `FixedRealWithdrawalPolicy` — withdrawals are specified as a real rate, no separate CPI dataset needed at runtime

The FBF runtime operates on pre-adjusted real return series. A separate CPI runtime dataset is not required unless the replication audit demonstrates that ERN's methodology applies inflation adjustment differently (e.g., nominal returns with explicit CPI adjustment vs. pre-computed real returns).

### 4.2 Canonical Data Available

| File | Coverage | Source |
|------|----------|--------|
| `spx_tr_real.csv` | 1871-01 through 2016-09 | FBF — verified |
| `bond_10y_tr_real.csv` | 1871-01 through 2016-09 | FBF — verified |
| `cape_shiller.csv` | 1881-01 through 2023-09 | FBF — verified |

**FBF dataset loader** (`src/fbf/core/datasets/ern.py`):
- Loads market return CSVs and constructs `MarketSnapshot` objects
- Computes running all-time-high and `is_underwater` flag (lines 152-180)
- Base snapshot: 1871-01-31 (index 0)
- First data point: 1871-02-01 (index 1)
- Historical data loop: 1871-03 through 2016-09 (applying monthly returns)
- Forward projection: 2016-10 through 2075-11 (constant-return forecasts)
- Monthly fee: 0.05% annual / 12

### 4.3 Data Sufficiency

**Forward projection — VERIFIED (Part 1 §4, Dec 7 2016):**

The forward-projection methodology is established from first-party ERN evidence. Part 1 §4 explicitly specifies:

> "We extrapolate past the current history and append equity and bond returns after September 2016. To this end, we assume long-term average returns for equities going forward (about 6.6% real p.a.). For bonds, we assume a low real return over the first 10 years: only 0% real p.a. [...] After the initial 10 years, bonds too will return their long-term average of 2.6% real per year."

**Canonical specification:**

| Parameter | Value | Source |
|-----------|-------|--------|
| Equity forward return | 6.6% real p.a. (constant) | Part 1 §4 |
| Bond return, months 1–120 | 0.0% real p.a. | Part 1 §4 |
| Bond return, month 121+ | 2.6% real p.a. | Part 1 §4 |
| Historical data end | September 2016 | Part 1 §4 |
| Forward projection start | October 2016 | Part 1 §4 |

**FBF forward projection** (`src/fbf/core/datasets/ern.py`):
- Historical period ends: 2016-10 (first forward month)
- Forward projection uses constant annual returns matching ERN Part 1 §4:
  - Equity: 6.6% annual (constant)
  - Bond: 0% for first 120 months, then 2.6% annual
- Projection extends to 2075-11

**Historical data gap note:** The article states "Monthly data from January 1871 to July 2017." The canonical CSVs contain data through June 2026 (historical) plus extrapolation through December 2076. The 10-month gap (Oct 2016 → Jul 2017) is filled by the forward projection — ERN's methodology applies constant returns from October 2016 onward, not just from July 2017.

**Evidence classification:** VERIFIED — first-party ERN evidence (Part 1 §4). The forward-projection constants are now sourced directly from the published article, not reverse-engineered from artifacts.

**Consequence for active glidepath:** The forward-projection methodology is now established. The remaining unresolved questions for active glidepath replication are ATH/underwater semantics and simulation ordering (see §3.2, §6).

### 4.4 All-Time-High / Underwater Computation

**FBF — verified implementation:** The dataset loader computes:
- `running_ath`: cumulative maximum of equity index level (lines 152-180)
- `is_ath`: whether current level equals or exceeds `running_ath`
- `is_underwater`: whether current level is below `running_ath`

This is computed at dataset load time and stored in each `MarketSnapshot`. The active glidepath mode reads `is_underwater` from the snapshot.

**ASSUMPTION — unresolved:** The article says "when the S&P 500 index is below its all-time high" but does not specify:
- Price index vs total return index
- Nominal vs real (inflation-adjusted)
- Exact monthly observation date
- Whether ATH is recomputed over full history

The FBF implementation uses the equity total return index level, inflation-adjusted, with cumulative maximum over the full dataset. Whether this matches the article's semantics is not established. This is important because the underwater state directly controls the active glidepath behavior.

---

## 5. Cohort Universe

### 5.1 Retirement-Start Universe

**Article — explicit:** "over 1,700 possible retirement start dates" (line 39), monthly from January 1871 to December 2015.

**FBF — verified implementation:** `CohortGenerator.generate_rolling_monthly()` generates all feasible monthly cohorts. For a 60-year horizon with dataset extending to 2075-11, the cohort range is derived from the canonical snapshot/base-date convention.

**Cohort-start alignment — unresolved:** ERN states January 1871–December 2015, while the current FBF cohort universe is derived from its canonical snapshot/base-date convention (base snapshot at 1871-01-31, first data point at 1871-02-01). Exact correspondence has not yet been demonstrated.

### 5.2 Cohort Count

**Article — explicit:** ~1,700+ cohorts.

**FBF — verified implementation:** 1,739 cohorts for 60-year horizon (derived from dataset coverage).

### 5.3 Horizon-Specific Validity

The same cohort universe is used for all allocation strategies. Each cohort runs the full 60-year simulation.

---

## 6. Temporal and Simulation Ordering

### 6.1 Monthly Simulation Steps

**FBF — verified implementation** (pipeline order):

| Step | Order | Description |
|------|-------|-------------|
| InitializeAllocation | 0 | Seed initial allocation |
| ExpenseDeduction | 5 | ERN expense ratio (0.05%/12) |
| BuildDecisionContext | 10 | Build context for policies |
| WithdrawalDecision | 20 | Compute withdrawal amount |
| InterestAccrual | 26 | Accrue interest |
| WithdrawalExecution | 30 | Sell assets for withdrawal |
| AllocationDecision | 40 | Call allocation policy (glidepath) |
| PortfolioRebalance | 50 | Rebalance to target allocation |
| MarketEvolution | 60 | Apply market returns |
| LTVEvaluation | 66 | Evaluate long-term value |
| MonthlyResultBuilder | 70 | Record monthly result |
| FailureDetection | 75 | Check for failure |
| SimulationStateUpdate | 80 | Advance to next month |

### 6.2 Simulation Ordering — RESOLVED GLOBALLY

**The monthly simulation sequence is now established as the canonical FBF/ERN rule, applicable to all Parts:**

For each month (e.g., January → February):

1. Start February with the ATH tracked through January.
2. Apply the January → February market return.
3. February's portfolio/index value is now known.
4. Determine whether February establishes an ATH (inclusive `>=` comparison).
5. Execute the month's cash-flow operation (withdrawal, contribution, loan draw, repayment).
6. Perform the required rebalancing after the cash-flow operation.

**State used for decisions in February = after applying January→February return, before February cash-flow operation.**

**Rebalancing occurs after the cash-flow operation when the methodology calls for rebalancing.** The previously documented shorthand "return → ATH → cash-flow" should not be interpreted as "return → cash-flow → no rebalance."

Example for a 60/40 portfolio:
- January portfolio after previous rebalance: €60/€40
- January→February returns produce €66/€42
- A €1 withdrawal is applied, leaving €65/€42 if taken entirely from first asset
- Total portfolio = €107; target allocation is €64.20/€42.80
- Rebalancing moves €0.80 from first asset to second

**Evidence classification:** RESOLVED — globally established FBF/ERN sequencing rule.

**FBF implementation — alignment pending:**

| Step | Order | Description |
|------|-------|-------------|
| WithdrawalDecision | 20 | Compute withdrawal amount |
| WithdrawalExecution | 30 | Sell assets for withdrawal |
| AllocationDecision | 40 | Call allocation policy (glidepath) |
| PortfolioRebalance | 50 | Rebalance to target allocation |
| MarketEvolution | 60 | Apply market returns |

**FBF sequence:**
1. Withdrawal (steps 20-30);
2. Allocation decision (step 40);
3. Rebalance (step 50);
4. Market evolution (step 60).

**Implementation alignment required:** The FBF implementation currently applies returns last (after withdrawal and rebalancing), while the established rule applies returns before cash-flow decisions. This is a known implementation gap. Once the FBF pipeline is aligned to the established sequencing rule, Parts 19/20 become canonical ERN replications.

**Consequence for active glidepath:** The established rule requires the underwater check to occur after the current month's market return is applied. The FBF implementation currently uses a pre-computed `is_underwater` flag from the dataset. Once the execution order is aligned, this behavior will match the established rule.

### 6.3 First-Month Semantics — Resolved

**ERN ordering — VERIFIED (first-party evidence):**

The first simulated month uses the **starting equity allocation unchanged**.

Example for a 60% → 100% glidepath at 0.4% per month:

- Month 0: **60.0%**
- Month 1: **60.4%**
- Month 2: **60.8%**
- …

The glidepath does not advance before the first monthly observation.

**FBF implementation — verified:**
- Month 0 uses `InitializeAllocationStep` to seed the starting allocation;
- The glidepath policy computes the allocation from `period_index`;
- The first withdrawal occurs in the first simulation step.

**Classification:** RESOLVED — FBF's month-0 indexing matches ERN's methodology.

---

## 7. Current FBF Capability Audit

### 7.1 Existing Capabilities

| Requirement | Status | Location |
|-------------|--------|----------|
| GlidepathAllocationPolicy (passive + active) | **Implemented** | `domain/policies/glidepath.py` |
| start_equity, end_equity, slope, mode parameters | **Implemented** | `glidepath.py:49-67` |
| Monthly allocation changes | **Implemented** | Pipeline step 40 |
| Rebalancing to target allocation | **Implemented** | Pipeline step 50 |
| All-time-high / underwater tracking | **Implemented** | `datasets/ern.py:152-180` |
| FixedRealWithdrawalPolicy | **Implemented** | `domain/policies/concrete.py:85-130` |
| Multiple final_value_target | **Implemented** | `builder.py:485`, `statistics_builder.py:53-63` |
| 60-year horizon support | **Implemented** | `ern_grid.yaml` uses `[30, 40, 50, 60]` |
| ~1,700 monthly cohorts | **Implemented** | `CohortGenerator.generate_rolling_monthly()` |
| CAPE regime classification (binary: > 20) | **Implemented** | `cape_regime.py:157-193` |
| YAML configuration for glidepaths | **Implemented** | `ern_part20.yaml` (contains Part 19 definitions) |
| SWR optimizer (binary search) | **Implemented** | `optimization/swr_optimizer.py` |
| Research aggregation by dimensions | **Implemented** | `part3_aggregation.py`, `cape_aggregation.py` |
| Expense ratio (ERN convention) | **Implemented** | `ExpenseDeductionStep` |

### 7.2 Part 20 Configuration (Contains Part 19 Glidepath Definitions)

The existing `ern_part20.yaml` contains:
- Lines 29-59: All 24 Part 19 glidepaths (6 combos × 2 slopes × 2 modes)
- Lines 60-70: 8 additional Part 20 glidepaths (passive only)
- Line 74: 5 SWR values [3.0%, 3.25%, 3.5%, 3.75%, 4.0%]
- Line 24: 2 horizons [30Y, 60Y]
- Line 76: Final value target [0.0]

**FBF framework representation:** The existing `ern_part20.yaml` contains the 24 Part 19 glidepath definitions as a subset. However, whether the data, timing, ATH semantics, and experiment dimensions match Part 19 is not established (see §4, §6).

### 7.3 Capability Assessment

**No confirmed FBF framework capability gaps have been identified. However, replication-fidelity gaps remain unresolved.**

The existing infrastructure appears capable of expressing:
- Static allocations (0-100% equity);
- Passive glidepaths (monthly increase);
- Active glidepaths (increase only when underwater);
- Final-value targets (0%, 50%, 100%);
- CAPE conditioning (binary: > 20);
- Monthly rebalancing;
- SWR optimization.

That is different from proving that the existing implementation is methodologically equivalent to ERN Part 19. The following have been resolved but require E2E quantification:
- Data coverage gap (2016-09 vs July 2017) — forward projection established;
- Forward projection equivalence — canonical values from Part 1 §4;
- ATH/underwater semantics — ERN uses nominal total-return index; FBF uses real;
- Simulation ordering — ERN: returns → withdrawal → rebalance; FBF differs;
- First-month semantics — month 0 uses starting allocation unchanged.

---

## 8. Implementation Gaps

### 8.1 Replication-Fidelity Gaps

| Gap | Description | Classification |
|-----|-------------|----------------|
| Forward projection constants | ~~FBF used legacy h720.json values (6.5467%/2.5487%/121mo)~~ Now corrected to ERN Part 1 §4 canonical values (6.6%/2.6%/120mo) | **RESOLVED** |
| First-forward-month bug | ~~Oct 2016 reused Sep 2016 return~~ Now fixed: Oct 2016 uses forward projection | **RESOLVED** |
| ATH semantics | FBF uses real total-return index; ERN uses nominal total-return index — potential difference must be quantified in E2E | **RESOLVED** — semantics defined; real vs nominal difference identified |
| Simulation ordering | FBF: withdrawal → allocation → rebalance → returns; ERN: returns → withdrawal → rebalance | **RESOLVED** — material difference identified (see §6.2) |
| First-month semantics | FBF: glidepath starts at period 0; ERN: month 0 uses starting allocation unchanged | **RESOLVED** — FBF matches ERN (see §6.3) |

### 8.2 Future Implementation Prerequisites

The following are implementation prerequisites, contingent on the E2E audit completing successfully:

1. **E2E audit (next step):** Quantify the impact of the known ordering difference (FBF: withdrawal→rebalancing→returns vs ERN: returns→withdrawal→rebalancing) and compare against ERN's published Part 19 results. Determine whether the real vs nominal ATH difference materially affects results.
2. **Part 19 YAML configuration:** Create `ern_part19.yaml` as a subset of `ern_part20.yaml` with only the 24 Part 19 glidepaths.
3. **Aggregation module:** Implement failure-rate aggregation across cohorts for the 3.5% SWR analysis.
4. **Failsafe computation:** Use `SWROptimizer` or dense grid scanning to compute failsafe SWRs.
5. **CAPE conditioning:** Use existing `CapeBinary` classification and aggregation to split results by CAPE > 20.
6. **Part 19-specific E2E test:** Create `test_part19_replication.py` with validation anchors from the article's table.

Do not assume that the existing Part 20 YAML can simply be reused without first establishing that its data, timing, ATH semantics, and experiment dimensions match Part 19.

---

## 9. Published Numerical Evidence

### 9.1 Primary Results (Failure Rates at 3.5% SWR)

**Article — chart-derived (from failure rate charts):**

The article presents failure rate charts but does not publish exact numerical values for each glidepath. The charts show:
- Static 60%/80%/100% equity have higher failure rates than most glidepaths
- 60→100% glidepaths consistently perform best
- 20→80% glidepaths are inferior to static allocations

**Evidence classification:** ARTICLE — chart-derived (qualitative observations from figures; no exact numerical values published for individual cells).

### 9.2 Failsafe and Percentile SWR Table

**Article — explicit (from table):**

The article publishes a table of failsafe and percentile SWRs for static allocations and all 24 glidepaths. The article highlights:

**Static allocation maximums (from table):**
- For each percentile column, the maximum over static allocations is at 75-100% equity
- "To make it through a 60-year retirement, you can't have a 60% or even 50% equity share"

**CAPE > 20 observations (article — explicit):**
- "With a CAPE>20 all numbers in the far right column are <4%, so the 4% had a failure rate of over 25% regardless of the equity glidepath"
- For CAPE > 20, failsafe at 75% static = 3.25%
- For CAPE > 20, 60→100% glidepath failsafe = 3.42% to 3.47%
- Improvement: 0.17% to 0.22% (5-7% of annual withdrawals)

**5th percentile observations (article — explicit):**
- For CAPE > 20, 5th percentile at 80% static = 3.47%
- For CAPE > 20, 5th percentile at 60→100% glidepath = 3.57% to 3.63%
- Improvement: ~0.16% (5% more consumption)

### 9.3 Published Numerical Evidence Summary

The article publishes the following numerical evidence:

| # | Description | Value | Type | Source | Classification |
|---|-------------|-------|------|--------|----------------|
| 1 | CAPE > 20, 75% static failsafe | 3.25% | Exact cell | Table | ARTICLE — explicit |
| 2 | CAPE > 20, 60→100% glidepath failsafe | 3.42%–3.47% | Range (multiple glidepath variants) | Table | ARTICLE — explicit |
| 3 | CAPE > 20, 80% static 5th percentile | 3.47% | Exact cell | Table | ARTICLE — explicit |
| 4 | CAPE > 20, 60→100% glidepath 5th percentile | 3.57%–3.63% | Range (multiple glidepath variants) | Table | ARTICLE — explicit |

**Note on ranges:** The ranges (e.g., 3.42%–3.47%) reflect that different 60→100% glidepath variants (different slopes, passive vs active) produce slightly different results. These are published range evidence, not single-cell acceptance anchors.

**Evidence classification:** ARTICLE — explicit (table-derived numerical values).

---

## 10. Validation/Oracle Strategy

### 10.1 Validation Levels

1. **Structural coverage:** Verify the grid produces the expected number of cells and cohorts.
2. **Computational execution:** Verify all cells produce real outcomes (not all 0% or 100%).
3. **Canonical replication:** Verify results are consistent with article observations.
4. **Internal consistency:** Verify glidepaths are generally among the best performers in CAPE > 20 scenarios.

### 10.2 Acceptance Criteria

**Published-value comparison rule:**
- An exact published cell value (e.g., 3.25%) must match the implementation result after applying the article's displayed precision/rounding.
- A published range (e.g., 3.42%–3.47%) must contain the corresponding implementation result after the same rounding convention.
- If the article does not expose enough information to determine the underlying unrounded value, do not invent a numerical tolerance.
- Rounding precision is part of the acceptance rule; "exact equality" at arbitrary precision is not.

**Experiment B — published numerical evidence (strongest replication gate):**
The article publishes explicit failsafe and percentile values for several configurations. These published values/ranges must be reproduced or any discrepancy must be explicitly investigated:
- CAPE > 20, static 75% equity failsafe = 3.25%
- CAPE > 20, 60→100% glidepath failsafe range = 3.42%–3.47%
- CAPE > 20, static 80% equity 5th percentile = 3.47%
- CAPE > 20, 60→100% glidepath 5th percentile range = 3.57%–3.63%

**Experiment A — qualitative consistency:**
- 60→100% glidepaths should be among the best performers.
- Active glidepaths perform slightly better than passive variants (article qualitative observation).
- Higher SWR should reduce success rates (internal consistency).

Do not impose universal pairwise inequalities (e.g., "every glidepath beats every static allocation") that the article does not establish.

### 10.3 Existing E2E Tests — Regression Coverage, Not Replication Evidence

The Part 20 E2E test (`tests/oracle/ern/test_part20_replication.py`) executes the full 320-cell grid (32 glidepaths × 5 SWR × 2 horizons), which includes the 24 Part 19 glidepath configurations.

**What the Part 20 E2E actually asserts** (from the test source):
- Structural coverage: 320 cells × 1,739 cohorts are represented
- Computational execution: cells produce real success rates in [0.0, 1.0]
- Internal consistency checks: success rates vary; at least one cell < 1.0 and one > 0.0
- Determinism: single-cell reproducibility across two independent CLI invocations
- Traceable ERN anchor: 60→100% at 3.34% rounds to 100%

**Important distinction:**

1. **Part 19 independent replication evidence:**
   - ERN methodology (article text);
   - ERN published numerical results (table values);
   - Independently reproduced results (not yet available).

2. **Part 20 regression evidence:**
   - FBF's existing implementation exercises the same glidepath definitions;
   - The Part 20 E2E provides regression coverage for the existing Part 20 implementation, including execution of the relevant glidepath configurations;
   - This is regression coverage for the FBF implementation, not independent Part 19 replication evidence.

Do not use the existence of the Part 20 E2E as proof that Part 19 has been independently replicated.

---

## 11. Workload Model

### 11.1 Parameter Cells

| Experiment | Strategies | FV Targets | CAPE Conditions | Cells |
|------------|-----------|------------|-----------------|-------|
| A: Fixed 3.5% failure-rate charts | 27 | 3 | 2 | 162 |
| B: Failsafe/percentile SWR | 45 | 1 (0%) | 2 | 90 |

**Note:** Experiment B's FV=0% cells overlap with Experiment A's FV=0% cells (for the 3 static allocations and 24 glidepaths). Computational reuse may reduce the execution workload, but the amount of reuse is an implementation decision and is not part of the replication specification.

### 11.2 Simulation Units

| Experiment | Cells | Cohorts | Units |
|------------|-------|---------|-------|
| A: Fixed 3.5% failure-rate charts | 162 | 1,739 | 281,718 |
| B: Failsafe/percentile SWR | 90 | 1,739 | 156,510 |

### 11.3 Execution Overhead

The glidepath allocation policy adds minimal overhead per simulation step. The active mode reads the precomputed underwater state once per simulation month, so policy evaluation is O(horizon) per cohort; ATH computation itself occurs during dataset preparation.

### 11.4 Part 20 Comparison

The existing Part 20 configuration contains the 24 Part 19 glidepath definitions as a subset, plus 8 additional passive-only glidepaths. Part 19 uses 24 glidepaths, 1 horizon (60Y), and focuses on 3.5% SWR (Experiment A) and failsafe computation (Experiment B). The experiments differ in horizons, SWR dimensions, outputs, aggregation, and conditioning.

---

## 12. Future Implementation Prerequisites

### 12.1 Prerequisite: Data and Methodology Resolution

Before implementation can begin, the following must be resolved:

1. ~~**Data coverage — methodological identity:** Determine what exact monthly observations ERN used from October 2016 through July 2017, and whether those observations are recoverable. If not, determine the exact extrapolation methodology ERN applied and whether the FBF forward series is mathematically equivalent.~~ **RESOLVED** — Forward projection uses constant returns from Part 1 §4 (6.6% equity, 0% bond for 120 months, 2.6% bond after).
2. ~~**ATH semantics clarification:** Determine whether ERN uses price index, total return index, nominal, or real for the all-time-high comparison.~~ **RESOLVED** — ERN uses nominal total-return index. FBF uses real total-return index. This potential difference must be quantified in the E2E audit.
3. ~~**Simulation ordering:** Establish whether FBF's ordering (withdrawal → allocation → rebalance → returns) matches ERN's methodology.~~ **RESOLVED** — ERN uses returns → withdrawal → rebalance (Part 1 §3). FBF uses the opposite ordering. This is a material difference documented in §6.2.
4. ~~**Glidepath month-0 indexing:** Establish whether the first month uses the starting allocation or advances the glidepath.~~ **RESOLVED** — Month 0 uses the starting allocation unchanged. FBF matches ERN.

### 12.2 Implementation Prerequisites (After Resolution)

The following are implementation prerequisites, contingent on the E2E audit completing successfully:

1. **E2E audit (next step):** Quantify the impact of the known ordering difference (FBF: withdrawal→rebalancing→returns vs ERN: returns→withdrawal→rebalancing) and compare against ERN's published Part 19 results. Determine whether the real vs nominal ATH difference materially affects results.
2. **Part 19 YAML configuration:** Create `ern_part19.yaml` as a subset of `ern_part20.yaml` with only the 24 Part 19 glidepaths.
3. **Aggregation module:** Implement failure-rate aggregation across cohorts for the 3.5% SWR analysis.
4. **Failsafe computation:** Use `SWROptimizer` or dense grid scanning to compute failsafe SWRs.
5. **CAPE conditioning:** Use existing `CapeBinary` classification and aggregation to split results by CAPE > 20.
6. **Part 19-specific E2E test:** Create `test_part19_replication.py` with validation anchors from the article's table.

---

## 13. Acceptance Criteria

### 13.1 Pre-Implementation Prerequisites

Before any implementation work begins:
- [x] Data coverage — methodological identity established (Part 1 §4: 6.6% equity, 0% bond for 120mo, 2.6% bond after)
- [x] ATH/underwater semantics clarified (ERN: nominal total-return index; FBF: real total-return index — difference identified, must be quantified in E2E)
- [x] Simulation ordering resolved (Part 1 §3: ERN returns → withdrawal → rebalance; FBF differs — see §6.2)
- [x] Glidepath month-0 indexing resolved (month 0 uses starting allocation unchanged — FBF matches ERN)

### 13.2 Structural

- [ ] 27 strategies (3 static + 24 glidepaths) × 3 FV targets × 2 CAPE conditions = 162 cells for Experiment A
- [ ] Each cell runs exactly 1,739 cohorts
- [ ] All start_equity, end_equity, slope, and mode values are represented

### 13.3 Computational (sanity checks, not replication evidence)

- [ ] Every cell produces a real success rate in [0.0, 1.0]
- [ ] Success rates vary across the grid
- [ ] At least one cell has success_rate < 1.0 (not trivially all-pass)
- [ ] At least one cell has success_rate > 0.0 (not trivially all-fail)

### 13.4 Hard Replication Criteria

**Experiment B — published numerical evidence (strongest replication gate):**
- [ ] CAPE > 20, static 75% equity failsafe = 3.25%
- [ ] CAPE > 20, 60→100% glidepath failsafe range = 3.42%–3.47%
- [ ] CAPE > 20, static 80% equity 5th percentile = 3.47%
- [ ] CAPE > 20, 60→100% glidepath 5th percentile range = 3.57%–3.63%
- Any discrepancy from these published values must be explicitly investigated.

### 13.5 Manual Article-Consistency Checks

These are valid manual article-consistency observations, not automated acceptance criteria:

- 60→100% glidepaths are consistently among the best performers in CAPE > 20 scenarios
- Active glidepaths perform slightly better than passive variants (article qualitative observation)
- Most glidepaths outperform static allocations in the CAPE > 20 analysis
- 20→80% glidepaths are consistently inferior to the stronger glidepaths

### 13.6 Determinism

- [ ] Two independent runs of the same configuration produce identical results

---

## 14. References

### 14.1 Article

- ERN Part 19: [Equity Glidepaths in Retirement](https://earlyretirementnow.com/2017/09/13/the-ultimate-guide-to-safe-withdrawal-rates-part-19-equity-glidepaths/)
- ERN Part 20: [More Thoughts on Equity Glidepaths](https://earlyretirementnow.com/2017/09/20/the-ultimate-guide-to-safe-withdrawal-rates-part-20-more-thoughts-on-equity-glidepaths/) (extends Part 19)
- Kitces/Pfau research on rising equity glidepaths (referenced in article)

### 14.2 FBF Code

| Component | File | Lines |
|-----------|------|-------|
| GlidepathAllocationPolicy | `src/fbf/core/domain/policies/glidepath.py` | 1-89 |
| Dataset loader (ATH computation) | `src/fbf/core/datasets/ern.py` | 152-180 |
| Part 20 YAML | `examples/studies/ern_part20.yaml` | 1-76 |
| Part 20 E2E test | `tests/oracle/ern/test_part20_replication.py` | 1-295 |
| Part 19 constants | `tests/oracle/ern/constants.py` | 139-171 |
| CAPE binary classification | `src/fbf/core/domain/policies/cape_regime.py` | 157-193 |
| SWR optimizer | `src/fbf/core/optimization/swr_optimizer.py` | 22-67 |

### 14.3 Evidence Classification Key

- **ARTICLE — explicit:** Directly stated in the article text
- **ARTICLE — chart-derived:** Read from figures but not numerically specified in text
- **FBF — verified implementation:** Established from the current repository
- **ASSUMPTION — unresolved:** Plausible interpretation not explicitly established by ERN

---

## 15. E2E Replication Audit Plan

### 15.1 Objective

Determine how closely the current FBF implementation reproduces ERN Part 19, and whether every material discrepancy can be explained by a documented methodological difference.

The objective is **not** to make FBF produce ERN's numbers by changing the implementation until the numbers match. The objective is to measure the discrepancy and attribute it to known differences.

### 15.2 Known Implementation Differences

The E2E audit must explicitly isolate two known differences between ERN's methodology and the current FBF implementation:

**Difference 1 — Monthly simulation ordering:**

| | ERN | FBF |
|---|-----|-----|
| Sequence | Returns → Withdrawal → Rebalancing | Withdrawal → Rebalancing → Returns |
| Source | Part 1 §3 | `default_pipeline.py` steps 20-60 |

**Difference 2 — ATH / underwater index type:**

| | ERN | FBF |
|---|-----|-----|
| Index | S&P 500 total-return, **nominal** | S&P 500 total-return, **real** |
| Source | First-party evidence | `datasets/ern.py` loads real returns |

These differences must not be silently "fixed" before the E2E. The purpose of the audit is precisely to determine their numerical impact.

### 15.3 Experiment Structure

The audit reproduces the Part 19 experiment structure described by ERN.

#### Experiment A — Fixed 3.5% SWR Failure-Rate Analysis

| Dimension | Values |
|-----------|--------|
| Static allocations | 60%, 80%, 100% equity (the three shown in failure-rate charts) |
| Glidepaths | All 24 |
| Final-value targets | 0%, 50%, 100% of initial real value |
| CAPE conditions | All CAPE, CAPE > 20 |
| Horizon | 60 years |
| SWR | 3.5% fixed |
| **Total cells** | **27 strategies × 3 FV targets × 2 CAPE = 162** |

**Output:** Failure rate at 3.5% withdrawal rate.

#### Experiment B — Failsafe / Percentile SWR Analysis

| Dimension | Values |
|-----------|--------|
| Static allocations | 21 (0%–100% equity in 5% increments) |
| Glidepaths | All 24 |
| Final-value targets | 0% (capital depletion) |
| CAPE conditions | All CAPE, CAPE > 20 |
| Horizon | 60 years |
| **Total cells** | **45 strategies × 2 CAPE = 90** |

**Output:** Per-cohort SWR distribution, failsafe SWR, percentile SWRs.

### 15.4 Published ERN Anchors

The E2E should explicitly test whether the implementation can reproduce the published Part 19 results.

**Experiment B — published numerical evidence (strongest replication gate):**

| # | Description | Published Value | Source |
|---|-------------|-----------------|--------|
| 1 | CAPE > 20, static 75% equity failsafe | 3.25% | Table |
| 2 | CAPE > 20, 60→100% glidepath failsafe range | 3.42%–3.47% | Table (multiple variants) |
| 3 | CAPE > 20, static 80% equity 5th percentile | 3.47% | Table |
| 4 | CAPE > 20, 60→100% glidepath 5th percentile range | 3.57%–3.63% | Table (multiple variants) |

**Experiment A — qualitative consistency:**

| # | Observation | Source |
|---|-------------|--------|
| 5 | 60→100% glidepaths consistently best performers | Article conclusion |
| 6 | Active glidepaths slightly better than passive variants | Article conclusion |
| 7 | Most glidepaths outperform static allocations in CAPE > 20 | Article conclusion |
| 8 | 20→80% glidepaths consistently inferior | Article conclusion |

The published ranges should be treated as validation targets, not as arbitrary tolerances.

### 15.5 Required Audit Outputs

The audit should produce a comparison table for each relevant Part 19 strategy/condition/target:

| Field | Description |
|-------|-------------|
| Strategy | Static allocation or glidepath identifier |
| Condition | CAPE regime (All CAPE, CAPE > 20) |
| FV target | 0%, 50%, 100% (Experiment A) or 0% (Experiment B) |
| FBF result | Computed failure rate or failsafe SWR |
| ERN result | Published value or published range |
| Discrepancy | Numerical difference (FBF − ERN) |
| Attribution | Simulation ordering / ATH index type / unexplained |
| Conclusion | REPRODUCED / EXPLAINED DIFFERENCE / UNEXPLAINED DIFFERENCE |

**Conclusion definitions:**

- **REPRODUCED:** FBF result matches published ERN value within stated precision.
- **EXPLAINED DIFFERENCE:** Discrepancy exists but is fully attributable to a documented methodological difference (ordering or ATH index type).
- **UNEXPLAINED DIFFERENCE:** Discrepancy cannot be attributed to a known difference. Requires further investigation.

### 15.6 Audit Execution Strategy

#### Phase 1 — Baseline Measurement

Run the current FBF implementation against the full Part 19 grid and record all results. No code changes.

#### Phase 2 — Difference Isolation

Quantify the impact of each known difference independently:

1. **Ordering impact:** Run a modified simulation with ERN's ordering (Returns → Withdrawal → Rebalancing) and compare against the baseline. The difference isolates the ordering effect.

2. **ATH index impact:** Run a modified simulation with nominal total-return index for underwater computation and compare against the baseline. The difference isolates the ATH index effect.

#### Phase 3 — Attribution

For each published anchor:

1. Compute the FBF baseline result.
2. Apply the ordering correction (if measurable).
3. Apply the ATH index correction (if measurable).
4. Compare the corrected result against the published ERN value.
5. Classify as REPRODUCED, EXPLAINED DIFFERENCE, or UNEXPLAINED DIFFERENCE.

#### Phase 4 — Conclusion

Document whether:

1. All discrepancies are explained by known differences → no code changes required.
2. Some discrepancies remain unexplained → reopen methodology/implementation investigation.
3. The known differences do not materially affect published results → current FBF implementation is acceptable as-is.

### 15.7 Constraints

- **No implementation changes** during the audit phase.
- **No silent fixes** — known differences must be measured, not corrected.
- **No cherry-picking** — all published anchors must be tested.
- **Attribution required** — every discrepancy must be traced to a specific cause.

### 15.8 Success Criteria

The audit is successful if:

1. Every published ERN anchor is tested.
2. Every discrepancy is attributed to a documented cause.
3. The conclusion clearly states whether FBF reproduces ERN Part 19 or whether implementation changes are justified.

### 15.9 Existing Infrastructure

The audit can reuse:

| Component | File | Purpose |
|-----------|------|---------|
| Part 19 glidepath constants | `tests/oracle/ern/constants.py:140-171` | 24 glidepath definitions |
| Part 20 YAML (superset) | `examples/studies/ern_part20.yaml` | Template for Part 19 YAML |
| Part 20 E2E test pattern | `tests/oracle/ern/test_part20_replication.py` | 3-level assertion pattern |
| CAPE aggregation | `src/fbf/core/research/cape_aggregation.py` | Regime-based aggregation |
| SWR optimizer | `src/fbf/core/optimization/swr_optimizer.py` | Binary search for failsafe |
| Dataset loader | `src/fbf/core/datasets/ern.py` | Canonical ERN dataset |
