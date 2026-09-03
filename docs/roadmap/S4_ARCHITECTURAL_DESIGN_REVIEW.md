# S4 Architectural & Research Design Review

**Stage:** S4 — Part 49 Debt Foundation
**Status:** DESIGN REVISION
**Date:** 2026-09-03
**Prerequisite:** S0 P49 items CLOSED (S0-F5, S0-F6 DECIDED)

---

## A. S4 Identification

### A.1 ERN Study

| Property | Value |
|----------|-------|
| **Study** | ERN Part 49 — Using Leverage in Retirement |
| **Source** | https://earlyretirementnow.com/2021/11/16/leverage-in-retirement-swr-series-part-49/ |
| **Date** | November 16, 2021 |
| **Series** | Safe Withdrawal Rate Series, Part 49 |

### A.2 Objective

Implement the debt state transition model for margin-loan leverage in retirement. This stage defines the semantic foundation: draw timing, interest accrual, LTV evaluation, forced liquidation, and net-worth semantics. S4 is a **design and validation stage** — it establishes the mathematical model and proves whether the existing engine can represent these transitions without violating its domain boundaries.

### A.3 Methodology Summary

ERN Part 49 investigates using margin loans to fund retirement spending instead of liquidating assets. The core insight: avoid selling assets at depressed prices during bear markets (sequence risk mitigation).

**Key parameters:**
- **Horizon:** 30 years (360 months)
- **Allocation:** 75/25 stocks/bonds (primary); 100/0 (comparison)
- **Initial portfolio:** $1,000,000
- **Rebalancing:** Monthly
- **Real interest rates:** 0%, 1.5%, 3% (fixed real)
- **LTV constraint:** 75% (Interactive Brokers 25% margin requirement)
- **Interest treatment:** Capitalized (compounded into loan balance)
- **Loan timing:** Drawn during retirement
- **Loan repayment:** None (loan grows throughout horizon)
- **Net worth:** Portfolio Value − Loan Balance

**Partial leverage model (recommended starting point):**
- Total spending rate: 4% of initial portfolio ($40,000/year on $1M)
- Portfolio withdrawal rate: 3% ($30,000/year = $2,500/month)
- Margin loan draw rate: 1% ($10,000/year = $833.33/month)

---

## B. Repository State

### B.1 Relevant Existing Abstractions

| Abstraction | Location | Relevance to S4 |
|-------------|----------|-----------------|
| `SimulationState` | `src/fbf/core/execution/pipeline/simulation.py` | Must extend with debt fields |
| `DecisionContext` | `src/fbf/core/domain/model/decision_context.py` | Must expose immutable debt snapshot |
| `SimulationContext` | `src/fbf/core/execution/pipeline/simulation_context.py` | May need leverage parameters |
| `Portfolio` | `src/fbf/core/domain/model/portfolio.py` | Holds positive holdings only; no liability |
| `AssetHolding` | `src/fbf/core/domain/model/portfolio.py` | Immutable; no negative units |
| `Money` | `src/fbf/core/domain/model/money.py` | Decimal-based; suitable for debt amounts |
| `MarketSnapshot` | `src/fbf/core/domain/model/market_snapshot.py` | Has `is_ath`, `is_underwater` |
| `WithdrawalPolicy` | `src/fbf/core/domain/policies/withdrawal_policy.py` | May need leverage-aware variant |
| `AllocationPolicy` | `src/fbf/core/domain/policies/allocation_policy.py` | Needs leverage info in context |
| `FixedRealWithdrawalPolicy` | `src/fbf/core/domain/policies/concrete.py` | Existing withdrawal implementation |
| Pipeline steps | `src/fbf/core/execution/pipeline/steps/` | May need new steps for debt operations |
| `SimulationRunner` | `src/fbf/core/execution/pipeline/runner.py` | Orchestrates monthly loop |

### B.2 S1/S2/S3 Infrastructure Reused

| Infrastructure | Source Stage | Reuse for S4 |
|----------------|--------------|--------------|
| Glidepath policy (period-indexed, stateless) | S1 | Reuse pattern for stateless policy design |
| Accumulation phase (research-layer pre-processing) | S3 | Pattern for debt model if engine-level not needed |
| Multi-horizon execution | S1/S2 | Reuse for S4 grid execution |
| Research plan materialization | S1/S2/S3 | Reuse for S4 study definition |
| Decimal reference engine | S0 | Canonical mathematical reference |
| Process-based parallel execution | S1/S2/S3 | Reuse for S4 workload |

### B.3 Relevant Call Graph

```
Study YAML configuration
        ↓
Study/Grid builder
        ↓
ResearchPlan (materialized units)
        ↓
Execution scheduler
        ↓
SimulationContext
        ↓
SimulationRunner / Pipeline
        ↓
MonthlyResult / StudyResult
```

**S4 extension points:**
- `SimulationState` → debt fields (loan_balance, interest_rate, net_worth)
- `DecisionContext` → immutable debt snapshot for policies
- Pipeline steps → new steps for debt operations (draw, interest accrual, LTV check)
- `SimulationContext` → leverage parameters (borrow_rate, ltv_limit)

---

## C. Methodology Specification

### C.1 Dataset

| Property | Value | Source |
|----------|-------|--------|
| **Source** | `ern_swr_h720.json` | Existing FBF dataset |
| **Assets** | Equity (S&P 500 total return), Bond (10-year Treasury) | Article §1 |
| **Frequency** | Monthly | Article §1 |
| **Date range** | 1871-01 to 2015-12 (extrapolated) | Article §1 |
| **Inflation data** | CPI-adjusted (real returns) | Article §1 |
| **Valuation data** | Not used in Part 49 | — |
| **Missing-data rules** | Forward extrapolation beyond Sep 2016 | Existing FBF convention |
| **Transformations** | Real (inflation-adjusted) returns | Article §1 |
| **Assumptions** | Fixed real interest rates for margin loan | Article §1 |

### C.2 Portfolio

| Property | Value |
|----------|-------|
| **Initial wealth** | $1,000,000 (linearly scalable) |
| **Asset allocation** | 75/25 stocks/bonds (primary); 100/0 (comparison) |
| **Rebalancing** | Monthly, to target weights |
| **Expenses** | 0.05% p.a. weighted (article §1) |
| **Return calculation** | Historical real returns from dataset |
| **Contribution/withdrawal ordering** | See §E (semantic contract) |

### C.3 Cohorts

| Property | Value |
|----------|-------|
| **Definition** | Retirement start date |
| **Cohort universe** | 1,700+ monthly cohorts (1871-02 to 2015-12) |
| **Conditioning variables** | None (all cohorts treated equally) |
| **Historical trajectory** | Each cohort uses historical returns from its start date |

### C.4 Parameters

| Dimension | Values | Cardinality |
|-----------|--------|-------------|
| **Equity allocation** | [0.75, 1.0] | 2 |
| **Withdrawal rate** | [0.03, 0.0325, 0.035, 0.0375, 0.04, 0.0425, 0.045, 0.0475, 0.05] | 9 |
| **Horizon** | [30] years | 1 |
| **Real interest rate** | [0.0, 0.015, 0.03] | 3 |
| **Leverage split** | Portfolio 3% + Loan 1% (fixed) | 1 |
| **LTV limit** | 0.75 | 1 |

**Total grid cells:** 2 × 9 × 1 × 3 × 1 × 1 = **54 cells**

**Note:** The leverage split is fixed at 3% portfolio + 1% loan = 4% total spending. This is the recommended starting point per the article. The grid explores sensitivity to interest rates and equity allocation.

### C.5 Horizons

S4 requires **one horizon** (30 years = 360 months). No horizon chaining needed.

**Temporal structure:**
```
Month 0: Initial state (portfolio, loan balance = 0)
Month 1–360: Monthly simulation with:
  - Portfolio withdrawal (3% of initial / 12)
  - Margin loan draw (1% of initial / 12)
  - Market evolution
  - Interest accrual (end of period)
  - Rebalancing
  - LTV evaluation
```

### C.6 Outputs

**Primary research metrics:**
- Maximum SWR (binary search for failsafe rate)
- Success rate by WR and configuration
- Terminal net worth (portfolio - loan balance)

**Diagnostic metrics:**
- Peak LTV (loan-to-value ratio)
- Maximum loan balance
- Final loan balance
- Terminal portfolio value
- Months to LTV breach (if any)

**Intermediate data:**
- Per-cohort trajectories (portfolio value, loan balance, LTV over time)
- Leverage utilization statistics

**Visualization/reporting data:**
- LTV time series for worst-case cohorts (1929, 1965)
- Portfolio vs loan balance charts
- Success rate by leverage parameters

---

## D. Semantic Contract

### D.1 Period Indexing

| Convention | Value | Source |
|------------|-------|--------|
| **Period index start** | 0 | FBF convention |
| **Period index semantics** | 0 = first retirement month | S0-F4 decision |
| **Dataset indexing** | period_index=M corresponds to dataset[M] | S0-F4 decision |

### D.2 Snapshot Semantics

| Property | Convention |
|----------|------------|
| **Beginning-of-period** | `dataset[M]` is the market state at the start of month M |
| **End-of-period** | `dataset[M+1]` is the market state at the end of month M |
| **is_underwater** | Precomputed metadata; S&P 500 below ATH at dataset[M] |

### D.3 Deterministic State-Transition Contract

**This is the authoritative monthly ordering for Part 49 debt operations.**

```
BEGINNING-OF-PERIOD STATE (month M):
  portfolio_value = sum(holding.units × price[holding.asset_class] for all holdings)
  loan_balance = loan_balance from previous period (or 0 at month 0)
  ltv = loan_balance / portfolio_value (if loan_balance > 0, else 0)
  net_worth = portfolio_value - loan_balance

STEP 1: WITHDRAWAL DECISION
  Observe beginning-of-period state
  Compute portfolio withdrawal = initial_wealth × withdrawal_rate / 12
  Compute margin loan draw = initial_wealth × loan_draw_rate / 12
  Both decisions observe beginning-of-period prices only

STEP 2: WITHDRAWAL EXECUTION
  Withdraw portfolio_amount from portfolio at dataset[M] prices
  Reduce portfolio holdings proportionally (sell assets to meet target allocation)

STEP 3: LOAN DRAW
  Increase loan_balance by loan_draw_amount
  Debt becomes active immediately upon borrowing (S0-F5)
  Newly borrowed funds are available for the current period

STEP 4: ALLOCATION DECISION
  Observe beginning-of-period state (including debt information)
  Policy makes allocation decision from immutable DecisionContext

STEP 5: PORTFOLIO REBALANCE
  Rebalance portfolio to target weights at dataset[M] prices
  Loan balance is NOT affected by rebalancing

STEP 6: MARKET EVOLUTION
  Apply dataset[M] → dataset[M+1] returns to portfolio holdings
  Portfolio value changes based on historical returns

STEP 7: INTEREST ACCRUAL
  monthly_rate = annual_interest_rate / 12
  interest = loan_balance × monthly_rate
  loan_balance += interest
  Interest is capitalized at end of period (S0-F5)

STEP 8: LTV EVALUATION
  Compute portfolio_value at dataset[M+1] prices
  Compute ltv = loan_balance / portfolio_value (if loan_balance > 0, else 0)
  If ltv > ltv_limit:
    MARGIN CALL TRIGGERED
    liquidation_amount = (loan_balance - ltv_limit × portfolio_value) / (1 - ltv_limit)
    If liquidation_amount > portfolio_value:
      FAILURE: margin_call_impossible
      liquidation_amount = portfolio_value
      Sell entire portfolio at dataset[M+1] prices
      Repay loan by liquidation_amount
      portfolio_value = 0
      loan_balance -= liquidation_amount
      Set failure_state = "margin_call_impossible"
      Set status = ExecutionStatus.FAILED
    Else:
      Sell assets worth liquidation_amount at dataset[M+1] prices
      Repay loan by liquidation_amount
      portfolio_value -= liquidation_amount
      loan_balance -= liquidation_amount
      # LTV is now exactly ltv_limit
  If ltv ≤ ltv_limit:
    No action required

STEP 9: NET WORTH CALCULATION
  net_worth = portfolio_value - loan_balance
  (This is a derived field, computed after all operations)

STEP 10: FAILURE DETECTION
  If portfolio_value ≤ 0:
    FAILURE: portfolio depleted
    Set failure_state = "depleted"
    Set status = ExecutionStatus.FAILED
  Else if loan_balance > portfolio_value AND loan_balance > 0:
    FAILURE: margin call unsatisfiable
    Set failure_state = "margin_call_impossible"
    Set status = ExecutionStatus.FAILED
  Else:
    Continue to next period

END-OF-PERIOD STATE (month M+1):
  period_index = M + 1
  current_date = dataset[M+1].date
  market_snapshot = dataset[M+1]
  portfolio = updated portfolio (after withdrawal, rebalance, evolution, liquidation)
  loan_balance = updated loan balance (after draw, interest accrual)
  net_worth = portfolio_value - loan_balance
```

### D.4 Answering the 14 Required Questions

#### 1. When LTV is evaluated?

**Answer:** LTV is evaluated **at Step 8, after market evolution and interest accrual**, using end-of-period portfolio value. This is the natural point because:
- Portfolio value has been updated to reflect market returns
- Interest has been capitalized into the loan balance
- The evaluator observes the true end-of-period financial state

**Rationale:** Evaluating LTV before market evolution would use stale prices. Evaluating after interest accrual ensures the loan balance reflects all obligations.

#### 2. When a margin call is triggered?

**Answer:** A margin call is triggered at **Step 8** when `ltv > ltv_limit` after market evolution and interest accrual. The trigger is immediate and deterministic.

**Rationale:** The margin call is a hard constraint enforcement, not a decision. It occurs at the end of the period after all other operations have completed.

#### 3. Whether LTV is evaluated before or after withdrawals/borrowing?

**Answer:** LTV is evaluated **after** withdrawals and borrowing. The ordering is:
1. Withdrawal execution (Step 2)
2. Loan draw (Step 3)
3. Market evolution (Step 6)
4. Interest accrual (Step 7)
5. LTV evaluation (Step 8)

**Rationale:** LTV is a portfolio-level constraint that depends on the final portfolio value after all operations. Evaluating before withdrawals would use an artificially high portfolio value.

#### 4. Whether market losses can trigger a margin call within the same period?

**Answer:** **Yes.** Market losses at Step 6 reduce portfolio value, which increases LTV. If the new LTV exceeds the limit, a margin call is triggered at Step 8 within the same period.

**Rationale:** This is the core mechanism that makes leverage risky. Market losses can cause margin calls even without additional borrowing.

#### 5. Exactly how much must be liquidated during a margin call?

**Answer:** The liquidation amount is:

```
liquidation_amount =
    (loan_balance - ltv_limit × portfolio_value)
    / (1 - ltv_limit)
```

**Derivation:** After selling assets worth `x` and using the proceeds to repay the loan:
- New portfolio value = P - x
- New loan balance = L - x
- LTV constraint: (L - x) / (P - x) ≤ λ
- Solving for x: x ≥ (L - λP) / (1 - λ)
- Therefore: liquidation_amount = (L - λP) / (1 - λ)

**Verification example:**
```
P = 100, L = 80, λ = 0.75
liquidation_amount = (80 - 0.75 × 100) / (1 - 0.75) = 20 / 0.25 = 20
After: P = 80, L = 60, LTV = 60/80 = 75% ✓
```

**Note:** The numerator alone (`loan_balance - ltv_limit × portfolio_value`) is insufficient. Selling that amount and repaying the loan would still leave LTV above the limit because the denominator shrinks proportionally.

**Rationale:** The margin call enforcement is minimal — sell only what is necessary to restore compliance, accounting for the proportional reduction in both portfolio and debt.

#### 6. Which assets are liquidated and according to what rule?

**Answer:** Assets are liquidated **proportionally to current holdings**. If the portfolio holds 75% equity and 25% bonds, the liquidation sells 75% equity and 25% bonds.

**Rationale:** Proportional liquidation preserves the target allocation after the forced sale. This is the standard margin-call enforcement mechanism.

#### 7. What happens when liquidation cannot restore the required LTV?

**Answer:** The liquidation operation is:

```
sell assets worth liquidation_amount
        ↓
liquidation proceeds
        ↓
repay outstanding loan by the same amount
```

Therefore:
- Portfolio value decreases by `liquidation_amount`
- Loan balance decreases by `liquidation_amount`

The **unsatisfiable margin call** condition is:

```
liquidation_amount > portfolio_value
```

This occurs when:
```
(loan_balance - ltv_limit × portfolio_value) / (1 - ltv_limit) > portfolio_value
```

Simplifying:
```
loan_balance - ltv_limit × portfolio_value > (1 - ltv_limit) × portfolio_value
loan_balance > portfolio_value
```

**Therefore, a margin call is unsatisfiable if and only if `loan_balance > portfolio_value`.**

When unsatisfiable:
```
liquidation_amount = portfolio_value  (sell entire portfolio)
portfolio_value = 0
loan_balance -= liquidation_amount   (partial repayment)
remaining_loan = loan_balance - portfolio_value (before sale)
Net worth = 0 - remaining_loan = -remaining_loan (negative)
FAILURE: margin_call_impossible
```

**Edge case: `loan_balance = portfolio_value`**

```
liquidation_amount = (P - λP) / (1 - λ) = P(1 - λ) / (1 - λ) = P
```

This sells the entire portfolio and repays the entire loan, leaving:
```
portfolio_value = 0
loan_balance = 0
net_worth = 0
```

This is a valid terminal state (not a failure) if the simulation has reached the horizon. If mid-horizon, it is a failure because the simulation cannot continue with zero portfolio.

**Rationale:** The unsatisfiable condition is mathematically equivalent to `loan_balance > portfolio_value`. This is the catastrophic failure mode that leverage introduces.

#### 8. Whether newly borrowed funds can immediately finance the withdrawal?

**Answer:** **Yes.** The loan draw (Step 3) occurs before market evolution (Step 6). Newly borrowed funds are part of the portfolio at the beginning of the period and participate in market returns.

**Rationale:** This is consistent with S0-F5: "Debt becomes active immediately upon borrowing."

#### 9. When newly incurred debt begins accruing interest?

**Answer:** Newly incurred debt begins accruing interest **at the end of the same period** (Step 7). The interest accrual uses the loan balance after the draw.

**Rationale:** This is consistent with S0-F5: "Interest is accrued at end of period."

#### 10. Whether interest is capitalized at the end of the period?

**Answer:** **Yes.** Interest is capitalized (added to loan balance) at Step 7. The loan balance grows through compound interest.

**Rationale:** ERN states interest is "capitalized" — added to the loan balance, not paid out of pocket.

#### 11. How debt interacts with rebalancing?

**Answer:** Debt does **not** interact with rebalancing. Rebalancing (Step 5) adjusts only portfolio holdings to target weights. The loan balance is unaffected by rebalancing.

**Rationale:** The margin loan is a separate financial instrument from the portfolio holdings. Rebalancing adjusts the mix of equity and bonds within the portfolio, not the debt level.

#### 12. Whether debt repayment is possible and when it occurs?

**Answer:** **No debt repayment in Part 49.** The loan grows throughout the horizon with no repayment. Part 52 introduces repayment at fresh ATH, but that is outside S4 scope.

**Rationale:** ERN Part 49 explicitly states: "No repayment (loan grows throughout horizon)."

#### 13. The exact definition of net worth?

**Answer:** Net worth is defined as:

```
net_worth = portfolio_value - loan_balance
```

Where:
- `portfolio_value` = sum(holding.units × price[holding.asset_class] for all holdings) at current market prices
- `loan_balance` = outstanding margin loan balance including capitalized interest

**Rationale:** This is the standard accounting identity for leveraged positions.

#### 14. The exact definition of simulation failure?

**Answer:** Simulation failure occurs when **any** of the following conditions is met:

1. **Portfolio depletion:** `portfolio_value ≤ 0` at any point during the simulation
2. **Unsatisfiable margin call:** `shortfall ≥ portfolio_value` when a margin call is triggered (portfolio cannot cover the required liquidation)
3. **Negative net worth at horizon end:** `net_worth < 0` at month 360 (for completeness, though this is typically preceded by condition 2)

**Rationale:** These conditions represent the fundamental failure modes of a leveraged retirement strategy.

### D.5 Beginning/End-of-Period State

| State | Beginning of Month M | End of Month M |
|-------|---------------------|----------------|
| **Portfolio** | Value at dataset[M] | Value at dataset[M+1] (after all operations) |
| **Loan balance** | Includes previous interest | Includes current interest (after Step 7) |
| **LTV** | loan_balance / portfolio_value (if loan > 0) | loan_balance / portfolio_value (after Step 7) |
| **Net worth** | portfolio_value - loan_balance | portfolio_value - loan_balance (after Step 8) |

### D.6 Contribution Ordering

Not applicable for Part 49 (no contributions during retirement).

### D.7 Withdrawal Ordering

```
Total spending = 4% of initial portfolio per year
  = $40,000/year on $1M portfolio
  = $3,333.33/month

Portfolio withdrawal = 3% = $2,500/month
Margin loan draw = 1% = $833.33/month

Ordering:
  1. Withdrawal from portfolio ($2,500) at Step 2
  2. Draw from margin loan ($833.33) at Step 3
  3. Both occur at beginning-of-period prices
```

### D.8 Rebalancing Timing

Monthly, after withdrawal and loan draw, before market evolution. Target weights are 75/25 or 100/0 (fixed). Rebalancing does not affect loan balance.

### D.9 Inflation Treatment

All values are real (inflation-adjusted). The margin loan interest rate is fixed real. No inflation deflation is applied to any monetary values.

### D.10 Expense Treatment

0.05% p.a. weighted expense ratio, applied to portfolio returns. Not applied to loan balance.

### D.11 Failure Definition

**Portfolio depletion:** Portfolio value reaches zero before horizon end.
**Unsatisfiable margin call:** Loan balance exceeds portfolio value when a margin call is triggered (portfolio cannot cover the required liquidation).
**Negative net worth at horizon end:** Net worth < 0 at month 360 (for completeness, though this is typically preceded by condition 2).

All conditions constitute failure. The simulation stops at the first failure condition.

**Edge case: `loan_balance = portfolio_value`**

This is a valid terminal state if the simulation has reached the horizon. If mid-horizon, it is a failure because the simulation cannot continue with zero portfolio.

**Edge case: `loan_balance = 0` and `portfolio_value = 0`**

This represents a depleted portfolio with no debt. It is a valid terminal state (not a margin call failure).

**Edge case: `loan_balance > 0` and `portfolio_value = 0`**

This is an unsatisfiable margin call because you cannot sell assets when the portfolio is already zero. The simulation terminates with `failure_state = "margin_call_impossible"`.

### D.12 Horizon Semantics

30-year horizon = 360 months. Loan grows throughout the horizon with no repayment. Terminal state is the portfolio value and loan balance at month 360.

### D.13 Terminal-Value Semantics

**Net worth** = Portfolio Value − Loan Balance

Success criterion: `net_worth >= final_value_target × initial_wealth`

For Part 49: `final_value_target = 0` (depletion mode). Success means portfolio survived 360 months without LTV breach or depletion.

### D.14 Cohort Boundaries

Each cohort starts at a unique monthly date. The historical return sequence is applied from that date forward. No look-ahead bias: the loan draw decision uses only beginning-of-period information.

### D.15 Parameter Inclusivity

All parameter values are inclusive. The grid explores the full range of withdrawal rates and interest rates.

### D.16 Rounding/Precision

All monetary values use `decimal.Decimal`. No float arithmetic for financial calculations. Interest accrual uses precise decimal multiplication.

### D.17 Currency Conventions

All values are in USD (or currency-neutral real units). The FBF codebase canonicalizes as `Money(amount, Currency.EUR)` but the mathematical result is identical regardless of currency label.

---

## E. Capability Matrix

| S4 Requirement | Already Supported? | Existing Abstraction | Gap | Proposed Solution |
|----------------|-------------------|---------------------|-----|-------------------|
| **Debt state tracking** | NO | None | SimulationState has no debt fields | EXTEND SimulationState with loan_balance, interest_rate |
| **DecisionContext leverage info** | NO | DecisionContext has no debt fields | Policies cannot observe debt state | EXTEND DecisionContext with immutable DebtInfo snapshot |
| **Margin loan draw** | NO | No pipeline step | No mechanism for borrowing | NEW: LoanDrawStep (between withdrawal and allocation) |
| **Interest accrual** | NO | No pipeline step | No mechanism for interest | NEW: InterestAccrualStep (after market evolution) |
| **LTV evaluation** | NO | No pipeline step | No mechanism for margin call | NEW: LTVEvaluationStep (after interest accrual) |
| **Forced liquidation** | NO | No mechanism | No margin call enforcement | NEW: Part of LTVEvaluationStep with correct liquidation formula |
| **Fixed real interest rate** | NO | No parameter | No interest rate in context | EXTEND SimulationContext with interest_rate |
| **Portfolio withdrawal (3%)** | YES | FixedRealWithdrawalPolicy | Already supports fixed real withdrawal | REUSE with appropriate rate |
| **Margin loan draw (1%)** | NO | No policy | No loan draw policy | NEW: MarginLoanDrawPolicy or extend withdrawal |
| **Rebalancing** | YES | PortfolioRebalanceStep | Already supports monthly rebalancing | REUSE |
| **Market evolution** | YES | MarketEvolutionStep | Already applies returns | REUSE |
| **Failure detection (depletion)** | YES | WithdrawalExecutionStep | Already detects depletion | REUSE |
| **Failure detection (LTV breach)** | NO | No mechanism | No margin call detection | NEW: LTVEvaluationStep |
| **Net worth calculation** | NO | No field | No net worth in state | NEW: Derived field in SimulationState |
| **Study plan materialization** | YES | ResearchPlan, builder | Already supports parameterized studies | REUSE with leverage parameters |
| **Multi-horizon execution** | YES | Multi-horizon strategy | Already supports prefix-consistent horizons | REUSE (single horizon for S4) |
| **Parallel execution** | YES | ProcessPoolExecutor | Already supports process-based parallelism | REUSE |
| **Decimal arithmetic** | YES | Domain model | All monetary values use Decimal | REUSE |

**Summary:**
- **REUSE:** 8 capabilities (portfolio withdrawal, rebalancing, market evolution, depletion detection, study planning, multi-horizon, parallel execution, Decimal arithmetic)
- **EXTEND:** 3 capabilities (SimulationState, DecisionContext, SimulationContext)
- **NEW:** 6 capabilities (loan draw, interest accrual, LTV evaluation, margin call detection, forced liquidation, net worth calculation)
- **NOT NEEDED:** 0

---

## F. Data/IO Analysis

### F.1 Data Path

```
data/ern/ern_swr_h720.json
   ↓
Dataset loader (once per study)
   ↓
Dataset (immutable, shared)
   ↓
Study plan materialization
   ↓
SimulationContext (per unit)
   ↓
Workers (deserialized per worker)
```

### F.2 Potential Duplication

S4 adds no new data sources. The margin loan parameters (interest rate, LTV limit, draw rate) are study-level constants, not dataset-dependent. No additional data loading or caching is required.

### F.3 Serialization Impact

The debt state (loan_balance, interest_rate) adds minimal serialization overhead:
- `loan_balance`: one `Decimal` value per unit
- `interest_rate`: one `Decimal` value per unit (shared across all units in a study)
- `ltv_limit`: one `Decimal` value per unit (shared)

Estimated overhead: <1% of existing plan serialization.

---

## G. Performance Model

### G.1 Expected Workload

```
Number of cohorts: 1,739
× Number of parameter combinations: 54 (2 equity × 9 WR × 3 interest rate)
× Number of horizons: 1
× Number of months: 360
= Total units: 334,236
```

**Note:** This is comparable to the ERN Part 19/20 workload (313,020 units). The additional debt operations (interest accrual, LTV check) add ~2 arithmetic operations per month per unit.

### G.2 Cost Breakdown

| Category | Expected Impact | Rationale |
|----------|----------------|-----------|
| **Mathematical work** | +5-10% vs baseline | Interest accrual: 1 multiply + 1 add per month; LTV check: 1 divide + 1 compare per month |
| **Execution overhead** | Negligible | No new process creation, IPC, or serialization patterns |
| **Data/IO overhead** | None | No new data sources; same dataset as existing studies |
| **Memory** | +2 fields per SimulationState | loan_balance (Decimal), interest_rate (Decimal) |

### G.3 Dominant Cost

**Mathematical work** is the dominant cost. The additional debt operations are O(1) per month per unit. Total additional work: 334,236 units × 360 months × ~2 operations = ~240M additional Decimal operations. This is negligible compared to the existing 56M+ months of simulation work.

---

## H. Oracle Strategy

### H.1 Independent Oracle

For every new mathematical transformation, establish an independent oracle:

| Transformation | Production Implementation | Independent Oracle | Fixture Strategy |
|----------------|--------------------------|-------------------|------------------|
| **Interest accrual** | `loan_balance × (1 + monthly_rate)` | Standalone Python script with Decimal arithmetic | Flat returns, known interest rate → exact expected balance |
| **LTV calculation** | `loan_balance / portfolio_value` | Simple division verification | Known loan and portfolio values → exact LTV |
| **Margin call detection** | `ltv > ltv_limit` | Boolean comparison | Boundary values: exactly at limit, just above, just below |
| **Net worth** | `portfolio_value - loan_balance` | Simple subtraction | Known values → exact net worth |
| **Forced liquidation** | Portfolio sold to cover shortfall | Economic model of forced sale | Known shortfall → expected liquidation amount |

### H.2 Published ERN Values

ERN Part 49 provides case study results for specific cohorts:

| Cohort | Configuration | Published Result | FBF Target |
|--------|---------------|------------------|------------|
| 1929 | 100% equity, full leverage | Depleted after 12 years | Match depletion timing |
| 1929 | 75/25, full leverage | Near wipeout at month 238 ($1.085M loan vs $1.185M portfolio) | Match LTV trajectory |
| 1965 | 75/25, partial leverage ($30k portfolio + $10k loan) | LTV stayed below 70% | Match LTV ceiling |
| 1965 | 75/25, 50% leverage ($20k portfolio + $20k loan) | LTV reached 84-93% depending on rate | Match LTV breach timing |

**Validation discipline:** Published values are diagnostic anchors, not tuning targets. If FBF results differ, investigate methodology differences and document them.

### H.3 Oracle Independence

The independent oracle must:
1. **Not import from `fbf.core` production code**
2. Not call `SimulationRunner`, production pipeline steps, `DebtState`, or production debt helpers
3. Implement the same mathematical operations using only `decimal.Decimal`
4. Be independently testable
5. Produce bit-exact results for controlled fixtures

**Oracle structure:**
```
Independent Part 49 oracle
        ↓
explicit debt state transition
        ↓
explicit LTV calculation
        ↓
explicit liquidation
        ↓
explicit interest calculation
```

The production engine and oracle are then compared on controlled scenarios.

---

## I. Architecture Alternatives

### Option A: Research-Layer Debt Model (like S3 Accumulation)

**Description:** Implement the debt state transitions as a research-layer pre-processing step, similar to the Part 42 accumulation phase. The debt state is computed once per cohort and fed into the retirement simulation.

**Pros:**
- No engine modification required
- Follows S3 pattern
- Simple to implement and test

**Cons:**
- **Fundamentally incompatible with the debt lifecycle.** The debt state evolves *during* retirement, not before. Unlike accumulation (which is a pre-retirement phase), debt operations occur every month throughout retirement.
- Cannot model dynamic LTV constraints that depend on monthly portfolio evolution
- Cannot model margin calls that trigger mid-retirement

**Verdict:** REJECTED — the debt lifecycle is inherently part of the monthly simulation loop, not a pre-processing step.

### Option B: Policy-Layer Debt Model

**Description:** Implement the debt state as a stateful policy that tracks loan balance internally. The policy makes draw/interest/LTV decisions using its internal state.

**Pros:**
- No engine modification
- Policy has access to DecisionContext
- Stateful policy can track loan balance across months

**Cons:**
- Violates policy statelessness principle (DESIGN.md: "Policies are stateless; all state resides in DecisionContext")
- Policy would need to modify SimulationState (violating policy/service separation)
- Cannot enforce LTV constraint at the engine level (margin call is a hard constraint, not a policy decision)
- Interest accrual is a mechanical operation, not a decision

**Verdict:** REJECTED — violates architectural principles; debt operations are not purely decision-based.

### Option C: Engine-Level Debt State (Extend SimulationState)

**Description:** Add debt fields to `SimulationState` and new pipeline steps for debt operations. The debt state is part of the execution state, updated by dedicated steps.

**Pros:**
- Clean separation: debt state lives alongside portfolio state
- Pipeline steps enforce mechanical operations (interest accrual, LTV check)
- Policies can observe debt state through immutable DecisionContext
- Margin calls are enforced at the engine level (hard constraint)
- Follows existing pipeline architecture pattern

**Cons:**
- Requires extending SimulationState (minimal change)
- Requires new pipeline steps (3 new steps)
- Requires extending DecisionContext (minimal change)

**Verdict:** SELECTED — most architecturally clean; follows existing patterns; no principle violations.

### Option D: Domain-Layer Debt Concept

**Description:** Introduce a `DebtPosition` domain concept alongside `Portfolio`. The domain model includes loan balance, interest rate, and LTV as first-class value objects.

**Pros:**
- Rich domain model
- Debt is a peer of Portfolio (conceptually correct)
- Enables future leverage-aware domain operations

**Cons:**
- Domain layer must not import from execution (ARCHITECTURE.md)
- Debt state is execution-state, not domain-configuration
- Domain objects are immutable; debt state must evolve during simulation
- Would require mutable domain objects or state propagation

**Verdict:** REJECTED — debt state is execution-state, not domain-configuration. The domain model should remain pure.

### Option E: Extend Portfolio with Liability Holdings

**Description:** Add a "negative bond" holding to the Portfolio. The margin loan is represented as a negative AssetHolding.

**Pros:**
- Single source of truth for all financial state
- No new concepts; just negative units
- Portfolio already supports AssetHolding

**Cons:**
- Portfolio invariant: "AssetHolding units must not be negative" (portfolio.py:30)
- Violating this invariant would break all existing code that assumes positive holdings
- Interest accrual requires mutating the negative holding every month
- LTV calculation is a derived value, not a holding attribute
- Margin call is a hard constraint, not a portfolio property

**Verdict:** REJECTED — violates Portfolio invariant; would break existing code.

---

## J. Recommended Architecture

### J.1 Selected Approach: Option C — Engine-Level Debt State

The debt state lives in `SimulationState`, updated by dedicated pipeline steps. This is the cleanest architectural approach that:
1. Preserves policy statelessness
2. Enforces mechanical operations at the engine level
3. Exposes debt information to policies through immutable DecisionContext
4. Follows existing pipeline architecture patterns

### J.2 Architecture Diagram

```
SimulationState (extended)
├── portfolio: Portfolio
├── loan_balance: Decimal          ← NEW
├── interest_rate: Decimal         ← NEW
├── ltv_limit: Decimal             ← NEW
├── net_worth: Money               ← NEW (derived)
├── ...existing fields...
```

### J.3 Pipeline Steps (Extended)

```
00: InitializeAllocationStep          (existing)
10: BuildDecisionContextStep          (existing)
20: WithdrawalDecisionStep            (existing)
30: WithdrawalExecutionStep           (existing)
35: LoanDrawStep                      ← NEW (between withdrawal and allocation)
40: AllocationDecisionStep            (existing)
50: PortfolioRebalanceStep            (existing)
60: MarketEvolutionStep               (existing)
65: InterestAccrualStep               ← NEW (after market evolution)
70: MonthlyResultBuilderStep          (existing)
75: LTVEvaluationStep                 ← NEW (after result builder)
80: SimulationStateUpdateStep         (existing)
```

### J.4 DecisionContext Extension

**DecisionContext exposes an immutable debt snapshot, not mutable execution state.**

```python
@dataclass(frozen=True)
class DebtInfo:
    """Immutable debt information for policy decisions.
    
    This is a snapshot of the debt state at the beginning of the period.
    Policies observe this to make allocation decisions.
    Policies never mutate debt state.
    """
    loan_balance: Decimal
    interest_rate: Decimal
    ltv_limit: Decimal
    net_worth: Decimal

@dataclass(frozen=True)
class DecisionContext:
    """Immutable decision context used by Policies.
    
    The debt field provides an immutable snapshot of the debt state.
    Policies can observe debt information but cannot modify it.
    Debt mutations (draw, interest accrual, liquidation) are engine operations.
    """
    date: date
    period_index: int
    simulation_context: object
    portfolio: Portfolio
    current_allocation: Allocation
    target_allocation: AllocationTarget
    market_snapshot: MarketSnapshot
    dataset: Dataset
    debt: DebtInfo | None = None      ← NEW
```

**Key principle:** The policy observes the beginning-of-period state and makes a decision. It never:
- Mutates debt
- Performs liquidation
- Accrues interest

Those remain engine responsibilities.

### J.5 Mathematical Operations

**Interest accrual (monthly):**
```
monthly_rate = annual_rate / 12
interest = loan_balance × monthly_rate
loan_balance += interest
```

**LTV calculation:**
```
ltv = loan_balance / portfolio_value
```

**Margin call detection:**
```
if ltv > ltv_limit:
    # Forced liquidation
    shortfall = loan_balance - (ltv_limit × portfolio_value)
    # Sell portfolio assets to cover shortfall
```

**Liquidation:**
```
liquidation_amount = (loan_balance - ltv_limit × portfolio_value) / (1 - ltv_limit)

# Sell proportionally from each holding
for each holding in portfolio:
    sale_fraction = liquidation_amount / portfolio_value
    holding.units -= holding.units × sale_fraction

# Repay loan with proceeds
loan_balance -= liquidation_amount

# Update portfolio value
portfolio_value -= liquidation_amount
```

**Net worth:**
```
net_worth = portfolio_value - loan_balance
```

---

## K. S4 Implementation Plan

### K.1 Stage Overview

S4 is a **design and validation stage**. The primary deliverables are:
1. Semantic contract documentation (complete deterministic state-transition contract)
2. Independent oracle implementation
3. Controlled fixture tests
4. Engine integration design & state-transition proof
5. Unit tests for debt operations and invariants
6. Integration test on small grid
7. Full regression and performance validation

S4 does **not** implement the full S4 study grid or E2E execution. That is S5's responsibility.

### K.2 Implementation Stages

#### Stage K.1: Complete Debt Semantic Contract

**Objective:** Document the complete deterministic state-transition contract for Part 49 debt operations in `docs/DECISIONS.md`. This is the authoritative specification that all subsequent stages implement and validate.

**Architectural responsibility:** Research layer documentation.

**Likely files affected:**
- `docs/DECISIONS.md` (extend with Part 49 debt temporal semantics)

**Tests:** Documentation review only.

**Benchmark/gate:** N/A (documentation stage).

**Acceptance criteria:**
- All 14 questions from §D.4 are answered with deterministic specifications
- Monthly ordering is completely deterministic (no ambiguity)
- Edge cases are explicitly handled (zero portfolio, negative net worth, margin call impossible)
- All financial operations are specified with exact formulas
- All invariants are documented (debt never negative, portfolio holdings valid, etc.)

**Dependencies:** None.

---

#### Stage K.2: Independent Debt-Transition Oracle

**Objective:** Implement an independent oracle for debt state transitions. The oracle must be genuinely independent — it must not call `SimulationRunner`, production pipeline steps, `DebtState`, or production debt helpers.

**Architectural responsibility:** Test infrastructure (Tier 3).

**Likely files affected:**
- `tests/oracle/ern/debt_oracle.py` (new)
- `tests/oracle/ern/test_debt_oracle.py` (new)

**Oracle structure:**
```
Independent Part 49 oracle
        ↓
explicit debt state transition
        ↓
explicit LTV calculation
        ↓
explicit liquidation
        ↓
explicit interest calculation
```

**Tests:**
- Interest accrual with known rate → exact balance
- LTV calculation with known values → exact ratio
- Margin call detection at boundary values
- Net worth calculation
- 360-month trajectory with flat returns → exact terminal values
- Liquidation mechanics with known shortfall

**Benchmark/gate:** Oracle produces bit-exact results for controlled fixtures.

**Acceptance criteria:**
- Oracle implements all debt operations using only `decimal.Decimal`
- Oracle is independently testable (no fbf.core imports)
- Oracle produces correct results for all controlled fixtures
- Oracle is structurally independent of production code

**Dependencies:** K.1 (semantic contract must be documented first).

---

#### Stage K.3: Controlled Fixture Tests

**Objective:** Create deterministic test fixtures that verify debt state transitions against the oracle. Fixtures must cover all edge cases identified in K.1.

**Architectural responsibility:** Test infrastructure (Tier 3).

**Likely files affected:**
- `tests/fixtures/debt.py` (new)
- `tests/unit/execution/test_debt_state.py` (new)

**Required fixtures:**
- Flat returns: loan grows at exactly the interest rate
- Zero portfolio: margin call triggered immediately
- Exact LTV boundary (75.00%): no margin call
- Just above LTV boundary (75.01%): margin call triggered
- Liquidation formula verification: P=100, L=80, λ=0.75 → x=20
- Liquidation with partial repayment: verify both portfolio and loan reduced
- Negative net worth: portfolio < loan balance
- Liquidation insufficient: loan > portfolio (unsatisfiable margin call)
- Multiple periods: compound interest over 360 months
- Full trajectory: 360-month run with known terminal values

**Benchmark/gate:** All fixtures pass with bit-exact comparison.

**Acceptance criteria:**
- Fixtures cover all edge cases identified in K.1
- Production implementation matches oracle on all fixtures
- No tolerance-based comparison (exact Decimal equality)

**Dependencies:** K.2 (oracle must exist first).

---

#### Stage K.4: Engine Integration Design & State-Transition Proof

**Objective:** Design and integrate `SimulationState`, pipeline steps, and `DecisionContext` for debt operations. Prove that the engine integration preserves all required invariants.

**Architectural responsibility:** Core architecture.

**Likely files affected:**
- `src/fbf/core/execution/pipeline/simulation.py` (extend SimulationState)
- `src/fbf/core/domain/model/decision_context.py` (extend DecisionContext)
- `src/fbf/core/execution/pipeline/simulation_context.py` (extend SimulationContext)
- `src/fbf/core/execution/pipeline/steps/loan_draw_step.py` (new)
- `src/fbf/core/execution/pipeline/steps/interest_accrual_step.py` (new)
- `src/fbf/core/execution/pipeline/steps/ltv_evaluation_step.py` (new)

**Invariant proofs required:**
1. **Debt is never negative:** `loan_balance ≥ 0` at all times
2. **Portfolio holdings remain valid:** All `holding.units ≥ 0` after every operation
3. **Borrowing increases both available portfolio resources and debt consistently:** Portfolio value increases by draw amount, loan balance increases by draw amount
4. **Interest increases debt according to the defined rule:** `loan_balance += loan_balance × monthly_rate`
5. **Liquidation reduces portfolio value and debt by the same amount:** Portfolio value decreases by `liquidation_amount`, loan balance decreases by `liquidation_amount`
6. **Liquidation never creates wealth:** `portfolio_value_after ≤ portfolio_value_before`
7. **Net worth follows the defined accounting identity:** `net_worth = portfolio_value - loan_balance`
8. **Margin-call mechanics are deterministic:** Same state → same liquidation amount
9. **Pipeline ordering is deterministic:** Same state → same sequence of operations
10. **Liquidation restores LTV to exactly the limit:** After liquidation, `ltv = ltv_limit` (within the same period)

**Tests:**
- Unit tests for each new step
- Invariant verification tests (all 9 invariants above)
- Integration test: small grid (1 cohort × 1 config) completes
- Regression: existing S1/S2/S3 tests still pass
- Contract: domain purity, layer isolation

**Benchmark/gate:**
- `ruff check src tests` — All checks passed
- `mypy --strict src` — Success: no issues found
- `pytest -p no:cacheprovider` — 0 failed
- `pytest tests/contract/` — All contract tests pass

**Acceptance criteria:**
- SimulationState extended with debt fields (loan_balance, interest_rate, ltv_limit, net_worth)
- DecisionContext extended with immutable DebtInfo
- 3 new pipeline steps implemented and tested
- All 9 invariants are provably preserved
- Existing tests unaffected (debt fields default to None/0)
- Domain purity preserved (no new imports into domain layer)
- Layer isolation preserved (execution does not import optimization)

**Dependencies:** K.3 (fixtures must exist first).

---

#### Stage K.5: Unit Tests for Debt Operations and Invariants

**Objective:** Comprehensive unit tests for all debt state transitions and invariant verification.

**Architectural responsibility:** Test infrastructure (Tier 3).

**Likely files affected:**
- `tests/unit/execution/test_loan_draw_step.py` (new)
- `tests/unit/execution/test_interest_accrual_step.py` (new)
- `tests/unit/execution/test_ltv_evaluation_step.py` (new)
- `tests/unit/domain/test_debt_info.py` (new)

**Tests:**
- LoanDrawStep: draw amount, timing, loan balance update
- InterestAccrualStep: monthly compounding, rate application
- LTVEvaluationStep: margin call detection, forced liquidation
- Liquidation formula verification: P=100, L=80, λ=0.75 → x=20
- Liquidation with partial repayment: verify both portfolio and loan reduced
- Unsatisfiable margin call: loan > portfolio → failure
- DebtInfo: construction, immutability, field access
- Edge cases: zero loan, zero portfolio, negative net worth
- Invariant tests: all 10 invariants verified at each step

**Benchmark/gate:** All unit tests pass.

**Acceptance criteria:**
- 100% coverage of new code paths
- All edge cases tested
- All 9 invariants verified
- No tolerance-based comparison

**Dependencies:** K.4 (engine extension must exist first).

---

#### Stage K.6: Integration Test — Small Grid

**Objective:** End-to-end execution of a small S4 grid.

**Architectural responsibility:** Integration testing.

**Likely files affected:**
- `tests/integration/test_part49.py` (new)

**Tests:**
- 1 cohort × 1 SWR × 1 interest rate → completes
- 1 cohort × 2 interest rates → both complete
- Result contains debt fields (loan_balance, net_worth)
- No existing tests broken

**Benchmark/gate:** Small grid completes in <5 seconds.

**Acceptance criteria:**
- Integration test passes
- Results contain expected debt fields
- No regressions in existing tests

**Dependencies:** K.5 (unit tests must pass first).

---

#### Stage K.7: Full Regression, Performance Validation & Research-Level Validation

**Objective:** Full regression testing, performance validation, and research-level validation against ERN published values.

**Architectural responsibility:** Validation and quality assurance.

**Likely files affected:**
- `tests/oracle/ern/test_part49_e2e.py` (new)
- `tests/benchmarks/test_part49_performance.py` (new)

**Tests:**
- Full regression: all existing tests pass
- Performance: benchmark against non-leverage baseline
- Research validation: compare against ERN published values (as diagnostic anchors)
- Multi-cohort execution: 10+ cohorts complete successfully

**Benchmark/gate:**
- Performance: leverage execution within 2× non-leverage baseline
- All quality gates pass (ruff, mypy, pytest)
- Research validation: FBF results consistent with ERN methodology

**Acceptance criteria:**
- Full regression passes
- Performance within acceptable bounds
- Research validation documented (methodology differences identified)
- S4 stage complete

**Dependencies:** K.6 (integration test must pass first).

---

### K.3 Stage Dependencies

```
K.1 (Semantic Contract)
  ↓
K.2 (Independent Oracle)
  ↓
K.3 (Controlled Fixtures)
  ↓
K.4 (Engine Integration Design & Proof)
  ↓
K.5 (Unit Tests & Invariants)
  ↓
K.6 (Integration Test)
  ↓
K.7 (Full Regression & Validation)
```

Each stage must complete before the next begins. No parallel execution across stages.

---

## L. Risks and Unresolved Questions

### L.1 Risks

| Risk | Severity | Probability | Mitigation |
|------|----------|-------------|------------|
| **Engine extension breaks existing tests** | HIGH | LOW | Extend with defaults; regression gate after each stage |
| **Domain purity violation** | HIGH | LOW | Architectural review at K.4; contract tests enforce |
| **LTV constraint enforcement timing** | MEDIUM | MEDIUM | Document exact timing in K.1; oracle validates |
| **Margin call edge cases** | MEDIUM | LOW | Controlled fixtures test exact boundaries; liquidation formula corrected |
| **Interest compounding precision** | LOW | LOW | Decimal arithmetic; oracle validates |
| **Policy cannot observe debt state** | MEDIUM | LOW | DecisionContext extension at K.4 |

### L.2 Unresolved Questions

All 14 questions from §D.4 have been resolved in the semantic contract. The liquidation formula has been corrected to account for the proportional reduction in both portfolio and debt. No unresolved questions remain for S4.

---

## M. Explicit Decision

Based on this architectural and research design review:

**APPROVE DESIGN**

The design is sound, follows existing architectural patterns, preserves domain purity, and provides a clear implementation path. The 7-stage implementation plan (K.1–K.7) is well-defined with clear dependencies, acceptance criteria, and validation gates.

**Rationale:**
1. Option C (Engine-Level Debt State) is the cleanest architectural approach
2. No principle violations (policy statelessness, domain purity, layer isolation)
3. Follows existing pipeline architecture pattern
4. Independent oracle provides mathematical correctness verification
5. Controlled fixtures enable bit-exact validation
6. All 14 semantic questions are resolved with deterministic specifications
7. All 10 invariants are documented and provably preserved
8. Liquidation formula is mathematically correct and accounts for proportional reduction in both portfolio and debt
9. Edge cases are precisely defined (unsatisfiable margin call, zero portfolio, etc.)
10. Implementation is incremental and testable at each stage

**Authorization:** Ready for S4 implementation upon explicit user approval.
