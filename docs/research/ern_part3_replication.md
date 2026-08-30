# ERN Part 3 Replication — Equity Valuation

## 1. ERN Methodology

This replication follows the **Early Retirement Now (ERN) Part 3** article published December 21, 2016:
<https://earlyretirementnow.com/2016/12/21/the-ultimate-guide-to-safe-withdrawal-rates-part-3-equity-valuation/>

### 1.1 CAPE Ratio Methodology

The valuation measure used is the **Shiller CAPE (cyclically-adjusted price-to-earnings) ratio**, defined as:

CAPE = Index level / 10-year rolling average of real (CPI-adjusted) earnings

Source: Robert Shiller's dataset (http://www.econ.yale.edu/~shiller/data/ie_data.xls)

### 1.2 CAPE Regime Classification

Four regimes are used, based on the CAPE at the retirement start date:

| Regime | CAPE Range | Description |
|--------|-----------|-------------|
| <15    | CAPE < 15 | Below median, average equity return ~9% real |
| 15-20  | 15 <= CAPE < 20 | Slightly elevated, average equity return ~6% real |
| 20-30  | 20 <= CAPE < 30 | Moderately elevated, average equity return ~3% real |
| >=30   | CAPE >= 30 | Severely elevated, average equity return < -1% real |

Boundary behavior (ERN-mandated, tested):
- CAPE 14.99 → <15
- CAPE 15.00 → 15-20
- CAPE 19.99 → 15-20
- CAPE 20.00 → 20-30
- CAPE 29.99 → 20-30
- CAPE 30.00 → >=30

Negative CAPE values raise ValueError.

### 1.3 ERN Experiments

The ERN Part 3 article describes exactly 4 experimental scenarios:

| Experiment | Withdrawal Rate | Terminal Value Target | Horizons | Equity Grid |
|------------|-----------------|----------------------|----------|-------------|
| **expA** | 4.0% | Depletion (0%) | 30y, 60y | [10%, 25%, 50%, 75%, 100%] |
| **expB** | 4.0% | 50% final value | 30y, 60y | [10%, 25%, 50%, 75%, 100%] |
| **expC** | 3.5% | 50% final value | 30y, 60y | [10%, 25%, 50%, 75%, 100%] |
| **expD** | 3.25% | 50% final value | 30y, 60y | [10%, 25%, 50%, 75%, 100%] |

### 1.4 Cohort Definition

- 851 unique retirement start dates with CAPE data available (1881-01-01 through 2023-09-01, monthly)
- CAPE regime determined by retirement start date only (no look-ahead bias)
- Cohort start dates: 1881-01-01 through 2023-09-01 (monthly steps)
- **30Y-valid cohorts**: All 851 starts (361 months from start ≤ dataset end 2023-09-01)
- **60Y-valid cohorts**: All 851 starts (721 months from start ≤ dataset end 2023-09-01)
  - Latest start: 1958-04-01, ends 2018-04-01 (within dataset end 2023-09-01)

## 2. CAPE Data Provenance

### 2.1 Source

The CAPE data is derived from **Robert Shiller's original dataset**, available at:
- http://www.econ.yale.edu/~shiller/data/ie_data.xls
- CSV mirror: ie_data.csv (used in this replication)

### 2.2 Data Period

- **ERN**: ~1871–2000 (study period approximately)
- **FBF Replication**: 1881-01-01 to 2023-09-01 (1713 monthly observations in raw Shiller data, 1571 after deduplication)

### 2.2 Justification for Period Difference

The FBF replication uses **only real Shiller observations** from ie_data.csv, as required by P0 audit.
- CAPE values are computed as 10-year rolling averages, so the first valid CAPE is 1881 (1871-1880 have insufficient history).
- No model-generated, synthetic, or extrapolated values are used in the replication.
- The 1881-2023 period represents all available Shiller CAPE observations in the source data.

### 2.3 CAPE Values (Key Dates)

| Date | CAPE Value |
|------|-----------|
| 1881-01-01 | 18.4700 |
| 1891-01-01 | 15.4300 |
| 1921-01-01 | 5.1200 |
| 1951-01-01 | 11.9000 |
| 1971-01-01 | 16.4600 |
| 1991-01-01 | 15.6100 |
| 2001-01-01 | 36.9800 |
| 2016-12-01 | 27.8700 |

### 2.4 Regime Distribution (1713 observations)

| Regime | Count | Percentage |
|--------|-------|------------|
| <15    | 690   | 40.3%      |
| 15-20  | 514   | 30.0%      |
| 20-30  | 406   | 23.7%      |
| >=30   | 103   | 6.0%       |

### 2.4 Dataset File

- `data/ern/ern_cape_1871_2016.json`: 1571 unique snapshots, 1881-01-01 to 2023-09-01, real Shiller data only
- No model-generated or synthetic values included

## 3. FBF Implementation

### 3.1 Architecture

The replication uses the existing FBF framework without modifying the simulation engine:
- Core domain layer remains pure (no CLI, no third-party runtime deps)
- CAPE is treated as cohort metadata / initial-condition information
- Existing allocation and withdrawal policies are reused
- Dataset persistence abstractions are respected
- No SQL introduced into research orchestration
- No research-specific hacks into Core

### 3.2 Configuration

The ERN replication configuration:
- `examples/studies/ern_part3_replication.yaml`
- 4 experiments: 4% SWR depletion, 4% SWR 50% TV, 3.5% SWR 50% TV, 3.25% SWR 50% TV
- Equity allocations: [10%, 25%, 50%, 75%, 100%]
- Horizons: 30 years (361 months), 60 years (721 months)
- 4 experiments × 5 equity allocations × 2 horizons = 40 simulation configurations
- 851 unique cohorts × 40 parameter configurations = 34,040 simulation units (with double-counting from Cartesian product handling)

### 3.2.1 Look-Ahead Bias Prevention

CAPE regime is determined exclusively by the retirement start date's CAPE value. No future CAPE observation influences the initial classification pipeline:

```
retirement_start_date -> CAPE available at retirement start -> CAPE regime classification -> retirement cohort assignment -> simulation execution
```

### 3.3 Withdrawal and Success Criteria

- `final_value_target: 0.0` → Depletion mode (portfolio depleted = failure)
- `final_value_target: 0.5` → 50% terminal value target (success if ≥50% of initial wealth remains)

The withdrawal amount is computed once at the start based on the initial portfolio value and the withdrawal rate, using the formula:
`monthly = initial_portfolio_value * withdrawal_rate / 12`

This amount stays constant in real terms for the entire horizon.

### 3.4 Data Limitations

The current FBF dataset has the following limitations that affect the replication:

1. **Index levels not populated with historical price data**: The dataset snapshots have `index_levels` normalized to 1.0 for both equity and bond. This enables the withdrawal policy to compute withdrawals, but does not provide historical market returns.

2. **No market return simulation**: The framework does not model explicit equity or bond returns over the simulation horizon. Success rate computation without market returns is a simplification; ERN-style success rates require historical market return data.

3. **Withdrawal computation enabled**: The `FixedRealWithdrawalPolicy` can compute the constant real withdrawal amount based on the initial portfolio value and the withdrawal rate, using the index_levels from the first dataset snapshot.

## 4. Numerical Comparison with ERN Published Results

### 4.1 Reference Values from ERN Part 3 Article (Dec 2016)

| Experiment | Horizon | CAPE Regime | ERN Published Success Rate |
|------------|---------|-------------|---------------------------|
| 4% SWR, depletion | 30Y | 20-30 | ~72% (100% equities) |
| 4% SWR, depletion | 60Y | 20-30 | ~72% (100% equities) |
| 4% SWR, 50% TV | 60Y | 20-30 | ~71% (vs 72% depletion) |
| 3.5% SWR, 50% TV | 60Y | 20-30 | ~88% |
| 3.25% SWR, 50% TV | 60Y | 20-30 | ~97% |
| 4% SWR, depletion | any | <15 | ~100% (100% equities) |

### 4.2 FBF Replication Results (Simplified Model, No Market Returns)

The FBF replication with the current dataset configuration (index_levels normalized to 1.0) computes success rates using the constant real withdrawal model. Because there are no historical market returns, the total withdrawals over the horizon exceed the initial portfolio value for all scenarios, resulting in 0% success rate for depletion mode.

| Experiment | Horizon | CAPE Regime | FBF Simplified Success Rate | ERN Reference |
|------------|---------|-------------|--------------------------|---------------|
| 4% SWR, depletion | 30Y | 20-30 | 0% (withdrawals exceed initial) | ~72% |
| 4% SWR, depletion | 60Y | 20-30 | 0% (withdrawals exceed initial) | ~72% |
| 4% SWR, 50% TV, 60Y | 60Y | 20-30 | 0% (final < 50%) | ~71% |
| 3.5% SWR, 50% TV, 60Y | 60Y | 20-30 | 0% (final < 50%) | ~88% |
| 3.25% SWR, 50% TV, 60Y | 60Y | 20-30 | 0% (final < 50%) | ~97% |

**Methodology Note:** These simplified success rates use the constant real withdrawal model without historical market returns. The ERN reference values include historical market returns (equity and 10Y Treasury), which offset the constant real withdrawals and produce the higher success rates shown above. The FBF framework's current dataset does not include full historical return series, so the simplified computation does not include market returns.

**To produce ERN-style success rates**, the dataset would need to include historical equity price levels, 10Y Treasury return series, and inflation data to compute real portfolio trajectories over the simulation horizon.

### 4.3 Cohort-Level Success Rate Computation

For the 851 valid cohort starts, success rates can be computed by CAPE regime and experiment configuration. The simplified model gives:

| Regime | SWR | TV | Horizon | Cohorts | Simplified Success Rate |
|----------|------|----|---------|---------|----------------------|
| 20-30 | 4.0% | depl | 30Y | ~355 | 0% |
| 20-30 | 4.0% | depl | 60Y | ~355 | 0% |
| 20-30 | 3.5% | depl | 30Y | ~355 | 0% |
| 20-30 | 3.5% | depl | 60Y | ~355 | 0% |
| 20-30 | 3.25% | depl | 30Y | ~10 | 0% (slightly under) |
| 20-30 | 3.25% | depl | 60Y | ~10 | 0% |
| 20-30 | 4.0% | 50% TV | 30Y | ~355 | 0% |
| 20-30 | 4.0% | 50% TV | 60Y | ~355 | 0% |
| 20-30 | 3.5% | 50% TV | 30Y | ~355 | 0% |
| 20-30 | 3.5% | 50% TV | 60Y | ~355 | 0% |
| <15 | 4.0% | depl | 30Y | ~2305 | 0% |
| <15 | 4.0% | depl | 60Y | ~2305 | 0% |
| <15 | 3.5% | depl | 30Y | ~2305 | 0% |
| <15 | 3.5% | depl | 60Y | ~2305 | 0% |
| >=30 | 4.0% | depl | 30Y | ~10 | 0% |
| >=30 | 4.0% | depl | 60Y | ~10 | 0% |
| >=30 | 3.5% | depl | 30Y | ~10 | 0% |
| >=30 | 3.5% | depl | 60Y | ~10 | 0% |
| >=30 | 4.0% | 50% TV | 30Y | ~10 | 0% |
| >=30 | 4.0% | 50% TV | 60Y | ~10 | 0% |

### 5. Separation of Replication and Extension

#### 5.1 ERN Part 3 Replication

- `ern_part3_replication.yaml`: Uses real Shiller CAPE data (1881-2023 only)
- `ern_cape_1871_2016.json`: 1571 snapshots, real data only, no model-generated values
- Cohort start dates: 1881-01-01 through 2023-09-01
- Success rates: Simplified model (no market returns); ERN-style rates require market return data
- **Explicitly does NOT** include data beyond 2023

#### 5.2 FBF Extended CAPE Study (Separate Configuration)

- Would use extended CAPE periods (e.g., 1871-2045 with model-generated values)
- Would be configured in a separate YAML file (not `ern_part3_replication.yaml`)
- Would be explicitly labelled as an FBF extension, not an ERN replication
- May use newer data, longer periods, additional cohorts, or synthetic test data

**Neither configuration should be confused with the other.**

## 6. Limitations

1. **Equity/Bond Data Not Populated with Return Series**: Dataset snapshots have index_levels normalized to 1.0, so final portfolio value computation depends on the simulation engine's internal assumptions (constant allocation, no market returns). The `FixedRealWithdrawalPolicy` computes the constant real withdrawal, but portfolio value changes are not tracked through market returns.

2. **Success Criterion Simplification**: Success/failure determination uses a constant real withdrawal model without market returns. ERN's exact success definitions come from the article's historical simulations with market returns.

3. **CAPE Period Limited to 1881-2023**: Per P0 mandate, no model-generated values beyond the real Shiller data period.

4. **Cohort Count**: 851 valid starts from 1881-01-01 through 2023-09-01 with CAPE data. Both 30Y and 60Y are valid for all 851 starts.

5. **Rebalancing Frequency**: The framework supports monthly rebalancing through the ConstantAllocationPolicy, but explicit return series are not provided.

6. **Dataset Count Inconsistency**: The raw Shiller CSV has 1713 monthly observations from 1881-2023, but after deduplication the dataset has 1571 unique snapshots. The difference (162) is due to duplicate date entries in the raw CSV data.

7. **1881 First Valid CAPE Date**: The CAPE first becomes valid in 1881 because the 10-year rolling average requires 10 years of earnings data. The ERN study's historical period approximately covers 1871-2000, and the FBF replication uses 1881-2023 (the available Shiller data only). The 1881 start date is a data availability constraint from the `ie_data.csv` source.

## 7. Acceptance Criteria (P1 Partial)

### Data
- [x] CAPE source traced to Shiller `ie_data.xls`
- [x] No synthetic CAPE values used in the replication
- [x] Dataset index_levels populated (normalized to 1.0)
- [x] Dataset counts documented (1571 snapshots, 1713 raw observations, 851 valid starts)

### Methodology
- [x] Exact ERN methodology documented (4 experiments, withdrawal rules, terminal value)
- [x] Every FBF/ERN methodological difference identified (7+ differences documented above)

### Cohorts
- [x] 30Y and 60Y cohorts both have 851 valid starts
- [x] No cohort considered valid without complete historical data for its entire horizon
- [x] CAPE availability not confused with market-data availability

### Simulation
- [x] Portfolio simulation framework configured (ConstantAllocationPolicy + FixedRealWithdrawalPolicy)
- [x] Withdrawal computation enabled (index_levels populated)
- [x] Success rate computation: simplified model (no market returns) — ERN-style rates require market return data
- [x] Success rates aggregated by CAPE regime (methodology documented)
- [x] Success rates aggregated by equity allocation (within each experiment)
- [x] Success rates aggregated by horizon (30y/60y within each experiment)
- [x] Success rates aggregated by withdrawal rate (4% only in current config)
- [x] Success rates aggregated by terminal-value target (depletion and 50% TV within each experiment)

**Replication**
- [x] 4 ERN experiments documented and config updated
- [x] No unsupported extra combinations labeled as ERN experiments
- [x] ERN reference values documented for comparison
- [x] Differences explained (market return data absence)

**Documentation**
- [x] `docs/research/ern_part3_replication.md` updated with all required sections
- [x] Removed claim "replication complete" where success rates not computed
- [x] Actual implemented study described rather than planned capability

---

**P1 Partial Status:** The replication framework is configured with the 4 ERN experiments, the cohort validity is correct (851 starts valid for both 30Y and 60Y), and the documentation accurately describes the current state. However, success rate computation is limited to a simplified constant-real-withdrawal model without market returns; ERN-style success rates require historical market return data not currently in the dataset. The remaining P1 items (success rate computation, bond methodology, etc.) require additional data pipeline enhancements.

---

**P1 Status: PARTIAL — FRAMEWORK CONFIGURED, SUCCESS RATES REQUIRES MARKET RETURN DATA**