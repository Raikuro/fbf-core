# ERN Part 49 — Using Leverage in Retirement

> **Status:** SUBSET — TWO DEVIATIONS
> **Article:** [Using Leverage in Retirement – SWR Series Part 49](https://earlyretirementnow.com/2021/11/16/leverage-in-retirement-swr-series-part-49/)
>
> **Implementation relationship:** Part 49 investigates whether margin loans can hedge sequence-of-returns risk by replacing part of the portfolio withdrawal with borrowing against the portfolio. The article finds that excessive leverage exacerbates sequence risk, but a modest supplemental loan (approximately 1% of portfolio) can improve outcomes.
>
> **Methodology status:** COMPLETE / FROZEN.
>
> **Implementation status:** PARTIALLY PRESENT — two deviations from ERN methodology:
> 1. LTV enforcement currently OFF — implementation limitation.
> 2. Monthly rebalancing instead of buy-and-hold — capability gap (§14.2).
>
> **E2E status:** NOT VALIDATED as canonical ERN replication.

---

## 1. Article Methodology

### 1.1 Central Question

The article asks whether leverage can reduce sequence-of-returns risk by replacing part of the portfolio withdrawal with borrowing against the portfolio.

The article's central conclusion is nuanced:

* financing most or all retirement spending through a margin loan can **exacerbate** sequence risk because margin constraints can force liquidation at exactly the wrong time;
* using leverage only as a **supplement** to portfolio withdrawals can historically work much better;
* the article's preferred scenario uses a **4% total spending rate**, consisting of a 3% portfolio withdrawal and a 1% margin-loan draw.

### 1.2 Key Parameters

| Parameter | Value | Evidence |
|-----------|-------|----------|
| Initial portfolio | $1,000,000 | ARTICLE — explicit |
| Horizon | 30 years | ARTICLE — explicit |
| Real borrowing rates | 0%, 1.5%, 3% | ARTICLE — explicit |
| Margin requirement | 25% (loan ≤ 75% of portfolio) | ARTICLE — explicit |
| CPI treatment | Real (CPI-adjusted) portfolio values | ARTICLE — explicit |

### 1.3 Article Structure

The article presents several distinct analyses:

1. **Preliminary buy-and-hold analysis** — 30-year final values without withdrawals
2. **Full retirement funding through margin** — 100% funded by borrowing (demonstrates the margin-call problem)
3. **1965 case study** — November 1965 cohort, aggressive leverage
4. **1929 case study** — September 1929 cohort, aggressive leverage
5. **Partial margin funding** — $20k portfolio + $20k loan
6. **Preferred scenario** — $30k portfolio + $10k loan (3% + 1% = 4% total)
7. **Historical conclusion** — 4% total spending never failed

### 1.4 Part 49 vs Part 52 Boundary

The article explicitly states that a possible refinement would be to time the margin borrowing after the portfolio falls below a specified level, which is subsequently investigated in Part 52.

Do not silently include Part 52 timing rules in the Part 49 replication. Part 49 uses **fixed** monthly loan draws regardless of portfolio state.

---

## 2. Preliminary Buy-and-Hold Analysis

### 2.1 Setup

The article first examines 30-year buy-and-hold outcomes without withdrawals:

* 75/25 stock/bond allocation
* 100/0 equity allocation
* Cohorts retiring between approximately 1925 and 1990
* Real portfolio values
* Final portfolio value as a multiple of initial capital
* No withdrawals

### 2.2 Published Observations

| Observation | Value | Evidence |
|-------------|-------|----------|
| 75/25 final-value range | 2.63× to 13.25× | ARTICLE — explicit |
| 75/25 geometric real-return range | 3.27% to 8.99% | ARTICLE — explicit |
| 100% equity worst-case multiple | 3.23× | ARTICLE — explicit |
| 100% equity best-case multiple | >26.4× | ARTICLE — explicit |
| 100% equity worst-case geometric return | 3.99% | ARTICLE — explicit |

These are published evidence, not necessarily future hard oracle values until the source chart/table and exact cohort/data definitions have been reconstructed.

### 2.3 Replication Questions

* The preliminary analysis explicitly uses **buy-and-hold** portfolios. This must be distinguished from the retirement simulation which may use rebalancing.
* The cohort range "approximately 1925–1990" must be established precisely.
* The equity/bond series used must be identified.
* Real-return calculation methodology must be established.

---

## 3. Full Retirement Funding Through Margin

### 3.1 Setup

The article models retirement spending funded entirely through a margin loan:

* $1M initial portfolio
* 30-year horizon
* Target final portfolio value: $3M
* Fixed real borrowing rates: 0%, 1.5%, 3%
* Varying final loan targets

### 3.2 Preliminary Calculation

The article explains that a $3M final portfolio with a 25% margin requirement would theoretically support up to approximately $2.25M of borrowing, leaving $750k equity.

The article derives a "safe withdrawal rate" from the final-value calculation.

### 3.3 Important Distinction

This preliminary calculation considers the final portfolio/loan relationship. It does **not** establish that the strategy is safe throughout the retirement horizon. The later historical path analysis is what exposes the margin-call problem.

---

## 4. 1965 Case Study

### 4.1 Setup

The article uses the **November 1965 cohort** with:

* $1M initial portfolio
* 75/25 allocation
* 100/0 allocation
* 30-year horizon
* Margin borrowing
* 1.5% and 3.0% real borrowing rates

### 4.2 Borrowing Rate Rationale

The article states that the 3.0% rate is motivated by the approximate real CPI-adjusted Federal Funds Rate over 1965–1995 plus a 1% loan spread. Document this as the article's rationale, not as a general FBF borrowing-rate model.

### 4.3 Key Observations

* At month 360, the leveraged strategy appears successful.
* Around months 180–200, the portfolio falls below the loan balance.
* This causes the critical failure: the brokerage would force liquidation through a margin call before the later recovery occurs.

### 4.4 Failure Mechanism

**The article's 25% minimum-equity example implies that a margin constraint would be breached before `loan >= portfolio`.** The existence and purpose of forced liquidation are now resolved at the methodology level.

The article explicitly discusses:

* the portfolio dropped below the loan;
* this would result in a margin call;
* the assets would be force-liquidated;
* there could be a shortfall bill.

**Methodology-level rule (RESOLVED):**

> When the portfolio reaches an unsustainable LTV/margin condition, the debt is forcibly settled using the portfolio.

The exact mechanics for determining how many assets are liquidated, the resulting residual portfolio, and any exact dollar shortfall are implementation-level details unless ERN publishes a specific formula that is required to reproduce a published result.

Therefore:

* 25% minimum equity requirement: **ARTICLE — explicit**
* 75% maximum LTV as the mathematical complement: **DERIVED FROM ARTICLE**
* forced liquidation existence and purpose: **RESOLVED** — methodology-level rule established
* exact liquidation arithmetic: **DEFERRED** — evidence/implementation detail, not methodology blocker

This must be preserved in the future implementation specification. Do not model this merely as "portfolio reaches zero."

---

## 5. 1929 Case Study

### 5.1 Setup

The article repeats the leverage analysis for the **September 1929 cohort**.

### 5.2 Key Observations

* 100% equity portfolio depletion after approximately 12 years
* 75/25 portfolio coming dangerously close to a wipeout
* At approximately month 238:
  * loan ≈ $1.085M
  * portfolio ≈ $1.185M
  * approximately $100k remaining net equity

### 5.3 Failure Mechanism

The article characterizes this as another margin-call blowup. Preserve the distinction between:

* mathematical eventual recovery
* temporary collateral failure
* forced liquidation
* terminal portfolio value

A strategy that would recover after the crisis is still a failure if the margin constraint would have forced liquidation beforehand.

---

## 6. Partial Margin Funding ($20k + $20k)

### 6.1 Setup

* $1M initial portfolio
* 75/25 allocation
* $20,000/year withdrawn from the portfolio
* $20,000/year funded through the margin loan
* Monthly implementation:
  * $1,666.67 portfolio withdrawal
  * $1,666.67 monthly loan draw
* Real loan rates: 0%, 1.5%, 3%

### 6.2 Published Observations (November 1965, month 201)

| Real loan rate | Loan/portfolio ratio | Evidence |
|----------------|---------------------|----------|
| 0% | ≈ 93% | ARTICLE — explicit |
| 1.5% | ≈ 84% | ARTICLE — explicit |
| 3.0% | < 72% | ARTICLE — explicit |

The article states that this would likely trigger a margin call for all but the unrealistic 0% case.

### 6.3 Classification

These values should be classified as published case-study evidence. Do not turn them into arbitrary tolerance-based hard gates.

---

## 7. Preferred Partial-Leverage Scenario ($30k + $10k)

### 7.1 Setup

* $1M initial portfolio
* 75/25 allocation
* $30,000/year withdrawn from the portfolio
* $10,000/year borrowed
* Total spending = $40,000/year (4% of initial portfolio)
* Monthly:
  * $2,500 portfolio withdrawal
  * $833.33 loan draw
* 0%, 1.5%, and 3.0% real borrowing rates

### 7.2 Published Observations

* At 3% real borrowing cost, loan/portfolio remains at or below approximately 70%
* Maximum margin utilization occurs around 1994 in the November 1965 cohort
* At 1.5% real borrowing cost, utilization stays below approximately 60%

### 7.3 Article Conclusion

The article's conclusion is that this is substantially more palatable than the more aggressive leverage strategies. The final article recommendation is approximately:

```text
4% total spending
= 3% portfolio withdrawal
+ 1% margin borrowing
```

The article states that this strategy historically never failed over the 30-year window, including difficult cohorts such as 1929 and 1965.

This conclusion must be treated as article evidence, not automatically as a future FBF oracle until the underlying cohort universe, data, loan mechanics, and margin constraint are reconstructed.

---

## 8. Loan Mechanics

### 8.1 Loan Balance — RESOLVED

The executable model is:

```text
interest = opening_loan_balance × monthly_rate

closing_loan_balance =
    opening_loan_balance
    + interest
    + current_month_loan_draw
```

For Part 49 there is no scheduled repayment. Therefore:

```text
loan_draw > 0 → debt increases
interest > 0 → debt increases
repayment = 0
```

until a margin event terminates the trajectory.

### 8.2 Real Interest Rate — RESOLVED

ERN explicitly models a **fixed real borrowing rate** and evaluates:

* 0%;
* 1.5%;
* 3.0%.

The article's 3% example is explicitly motivated by the approximately 2.1% real CPI-adjusted Federal Funds Rate during 1965–1995 plus an assumed 1% spread. Part 49 does **not** require the FFR dataset used by Part 52. Part 52's floating-rate methodology must remain excluded.

**Monthly conversion — RESOLVED:**

```text
monthly_rate = annual_real_rate / 12
```

This is consistent with the existing FBF leverage methodology, where the interest step applies:

```text
interest = opening_loan_balance × annual_rate / 12
```

The Part 49 article does not provide a competing monthly compounding convention.

### 8.3 Loan Draw Timing — RESOLVED

The article establishes monthly frequency for both components:

**$20k/$20k:** $1,666.67/month portfolio withdrawal + $1,666.67/month loan draw

**$30k/$10k:** $2,500/month portfolio withdrawal + $833.33/month loan draw

The exact order is inherited from the established `Timing-Leverage-Calc`/ERN monthly sequencing. Part 49 does not require a new sequencing convention.

The established execution convention is:

1. portfolio evolution / monthly return;
2. portfolio withdrawal;
3. loan draw;
4. interest accrual on the outstanding loan;
5. margin evaluation.

This preserves the critical distinction:

```text
portfolio withdrawal ≠ loan draw
```

Both occur monthly, but they affect different balances.

### 8.4 Portfolio Withdrawal — RESOLVED

The article explicitly distinguishes:

* amount withdrawn from the portfolio
* amount borrowed from the margin loan

These must remain separate cash-flow components. Do not represent the total spending amount as one withdrawal and then reconstruct the loan afterward.

### 8.5 Preferred Strategy

The preferred strategy is:

```text
$30,000/year portfolio withdrawal
+
$10,000/year margin borrowing
=
$40,000/year total spending
=
4% of initial $1M portfolio
```

**The 1% is the spending/borrowing share of initial capital, not the loan interest rate.** The loan interest-rate sensitivity remains 0%, 1.5%, and 3%. ERN explicitly defines the scenario this way.

---

## 9. Margin Constraint

### 9.1 25% Margin Requirement — RESOLVED

ERN explicitly gives the 25% minimum-equity example:

```text
minimum equity = 25% × account value
```

and therefore:

```text
maximum loan = 75% × account value
```

The $3M example gives:

```text
minimum equity = $750k
maximum loan = $2.25M
```

### 9.2 LTV vs Net-Equity Leverage — RESOLVED

The replication evaluates:

```text
LTV = loan_balance / portfolio_value
```

against:

```text
LTV_limit = 75%
```

at the resolved monthly margin-check point.

The two relevant quantities are:

```text
LTV = loan / gross portfolio value
net equity = portfolio value - loan
```

Do not casually call every ratio "leverage" or "net-equity leverage." Distinguish these quantities to prevent future confusion between `loan / portfolio` and `loan / net equity`, which can differ dramatically near a margin call.

### 9.3 Margin-Call Failure Semantics — RESOLVED

ERN explicitly treats the margin call as terminal:

* the brokerage forces liquidation;
* subsequent market recovery is irrelevant;
* a potential shortfall becomes a liability/bill.

This means a Part 49 replication must **not** allow a trajectory to continue after a margin-call liquidation and subsequently recover.

The correct semantic is:

```text
margin constraint breached
→ forced liquidation
→ retirement trajectory fails
→ later hypothetical market returns are irrelevant
```

### 9.4 Residual Liability — RESOLVED (Conceptually)

ERN explicitly says that after forced liquidation the retiree could receive:

> a bill for any potential shortfall.

Therefore the specification must preserve:

```text
forced liquidation ≠ debt magically disappearing
```

However, Part 49 does not publish a formula for the residual liability. For the SWR/failure analysis, the important semantic is:

> **The existence of residual liability does not permit the failed trajectory to continue.**

The exact dollar shortfall does not need to become a hard E2E oracle unless one of the published numerical anchors depends on it.

### 9.5 Important Distinction

Do not infer these semantics from modern Interactive Brokers rules merely because the article references IBKR. The historical replication target is ERN's model.

### 9.6 FBF Implementation

The `LTVEvaluationStep` computes `ltv = loan_balance / portfolio_value` and triggers margin calls when `ltv > ltv_limit`. The liquidation formula is:

```text
liquidation_amount = (loan_balance - ltv_limit * portfolio_value) / (1 - ltv_limit)
```

However, the article's exact margin-ratio definition, check timing, and failure semantics must be verified against ERN's methodology.

---

## 10. Data Requirements

### 10.1 Market Data

The article relies on historical monthly asset returns. Required inputs include:

* S&P 500 equity returns
* Intermediate U.S. Treasury/bond returns
* CPI index for real-return adjustment
* Monthly frequency

### 10.2 Real Returns

The article explicitly reports real, CPI-adjusted portfolio values. The implementation must establish whether FBF should consume:

* already-real returns
* nominal returns plus CPI
* or another representation

### 10.3 Canonical Data Equivalence

Confirm that the canonical FBF market series are methodologically equivalent to the return environment used by the Part 49 article. Existing canonical FBF data may be reused only after that equivalence has been established.

---

## 11. Rebalancing and Allocation

### 11.1 Portfolio Mechanics — RESOLVED: ALL BUY-AND-HOLD

**Part 49 portfolio allocation is buy-and-hold.** In the partial-withdrawal scenarios, portfolio withdrawals reduce the portfolio over time, but the article does not specify periodic rebalancing. Therefore no rebalancing should be introduced into the replication.

The article explicitly establishes:

1. **Preliminary analysis** — buy-and-hold (ARTICLE — explicit)
2. **November 1965 aggressive-leverage case** — buy-and-hold (ARTICLE — explicit)
3. **Partial-leverage scenarios** — buy-and-hold asset holdings with portfolio withdrawals; no monthly rebalancing is specified (ARTICLE — explicit)

The fact that cash is being withdrawn does **not** imply monthly rebalancing. "Not buy-and-hold" in the trivial sense that cash is being withdrawn does not mean "monthly rebalanced."

### 11.2 75/25 and 100/0 Allocations

The article evaluates both 75/25 and 100/0 allocations in the case studies.

### 11.3 FBF Implementation

FBF has monthly rebalancing (`PortfolioRebalanceStep`) but no buy-and-hold capability. **Buy-and-hold is a Part 49 replication requirement.** Whether that requires a new policy, a no-rebalance configuration, or another existing mechanism is an implementation question and should not be decided in the documentation phase.

---

## 12. Cohort Universe

### 12.1 Preliminary Analysis — RESOLVED

**ARTICLE — explicit:** "cohorts retiring between 1925 and 1990."

### 12.2 1965 Case Study — RESOLVED

November 1965. Single cohort.

### 12.3 1929 Case Study — RESOLVED

September 1929. Single cohort.

### 12.4 Historical 4% Conclusion — RESOLVED

**DERIVED FROM ARTICLE:** The historical Part 49 conclusion is evaluated over the same 1925–1990 cohort universe used by the article's preliminary historical analysis, subject to the 30-year data-availability requirement.

The article states:

> "A 4% consumption rate would have never failed"

and immediately frames this as a historical conclusion for the 30-year simulations, explicitly mentioning 1929 and 1965 as worst-case cohorts. Given the article's preceding methodology and the explicit 1925–1990 historical universe, the appropriate replication interpretation is that the conclusion is evaluated over that same universe.

---

## 13. Published Numerical Evidence

### 13.1 Preliminary Analysis

| Observation | Value | Evidence |
|-------------|-------|----------|
| 75/25 final-value range | 2.63–13.25× | ARTICLE — chart-derived (Chart 01) |
| 75/25 geometric real-return range | 3.27–8.99% | ARTICLE — chart-derived (Chart 01 IRR) |
| 100% equity worst-case | 3.23× | ARTICLE — chart-derived (Chart 01) |
| 100% equity best-case | >26.4× (26.42×) | ARTICLE — chart-derived (Chart 01) |
| 100% equity worst-case geometric return | 3.99% | ARTICLE — chart-derived (Chart 01 IRR) |

### 13.2 Preliminary Leverage Calculation

| Observation | Value | Evidence |
|-------------|-------|----------|
| Real loan rates | 0%, 1.5%, 3% | ARTICLE — explicit |
| Final portfolio target | $3M | ARTICLE — explicit |
| 25% margin requirement | loan capacity ≈ $2.25M | ARTICLE — explicit |
| SWR at 1.5% real, $1.5–2.0M loan target | ≈ 3.96%–5.28% | ARTICLE — table-derived |

### 13.3 1965 Case Study

| Observation | Value | Evidence |
|-------------|-------|----------|
| Month 360 outcome | Strategy appears successful | ARTICLE — chart-derived (Chart 02) |
| Margin-call failure window | Months 180–200 | ARTICLE — chart-derived (Chart 02) |

### 13.4 1929 Case Study

| Observation | Value | Evidence |
|-------------|-------|----------|
| 100% equity depletion | ≈ 12 years | ARTICLE — chart-derived (Chart 03) |
| Month ≈ 238 portfolio (75/25) | ≈ $1.185M | ARTICLE — chart-derived (Chart 03) |
| Month ≈ 238 loan (3.0% RR) | ≈ $1.085M | ARTICLE — chart-derived (Chart 03) |
| Month ≈ 238 net equity | ≈ $100k | ARTICLE — chart-derived (Chart 03) |

### 13.5 $20k + $20k Scenario (November 1965, month 201)

| Loan rate | Loan/portfolio | Evidence |
|-----------|---------------|----------|
| 3.0%      | 93.11%        | ARTICLE — chart-derived (Chart 04) |
| 1.5%      | 84.45%        | ARTICLE — chart-derived (Chart 04) |
| 0.0%      | 71.60%        | ARTICLE — chart-derived (Chart 04) |

### 13.6 $30k + $10k Scenario (November 1965)

| Observation | Value | Evidence |
|-------------|-------|----------|
| 3% real → max loan/portfolio (peak ~201) | 65.95% | ARTICLE — chart-derived (Chart 05) |
| 3% real → max loan/portfolio (peak ~348) | 70.25% | ARTICLE — chart-derived (Chart 05) |
| 1.5% real → max loan/portfolio (peak ~201) | 57.68% | ARTICLE — chart-derived (Chart 05) |
| 1.5% real → max loan/portfolio (peak ~348) | 55.15% | ARTICLE — chart-derived (Chart 05) |
| Largest utilization year | ≈ 1994 (month 348) | ARTICLE — chart-derived (Chart 05) |

### 13.7 $30k + $10k Scenario (September 1929)

| Observation | Value | Evidence |
|-------------|-------|----------|
| 3% real → max loan/portfolio (peak ~238) | 64.94% | ARTICLE — chart-derived (Chart 06) |
| 3% real → max loan/portfolio (peak ~288) | 67.74% | ARTICLE — chart-derived (Chart 06) |
| 1.5% real → max loan/portfolio (peak ~238) | 55.34% | ARTICLE — chart-derived (Chart 06) |
| 1.5% real → max loan/portfolio (peak ~288) | 55.62% | ARTICLE — chart-derived (Chart 06) |
| Margin constraints acceptable even at 3% real | Yes | ARTICLE — explicit |
| Loan came within ≈ $200k of wiping out portfolio | Approximate | ARTICLE — chart-derived |

### 13.8 Historical Conclusion

| Observation | Value | Evidence |
|-------------|-------|----------|
| 4% total spending never failed | ARTICLE — explicit: "A 4% consumption rate would have never failed." The article specifically highlights 1929 and 1965 as difficult examples. The exact cohort universe and aggregation methodology behind the global statement remain unresolved and must not be inferred from the two case studies alone | |

Treat these as published evidence unless exact table/image provenance is established. Do not invent exact values from chart visual estimates.

---

## 14. Current FBF Capability Audit

### 14.1 Implemented Capabilities

| Capability | Status | Key Files |
|------------|--------|-----------|
| Margin loans / leverage / borrowing | **Implemented** | `Part49WithdrawalPolicy`, `LoanDrawStep` |
| Interest accrual on borrowed funds | **Implemented** | `InterestAccrualStep` |
| Collateral ratios / margin constraints | **Implemented** | `LTVEvaluationStep`, `DebtInfo` |
| Margin calls | **Implemented** | `LTVEvaluationStep` with `ltv_enforcement=True` |
| Forced liquidation | **Implemented** | `LTVEvaluationStep._execute_liquidation()` |
| Loan balance tracking | **Implemented** | `SimulationState`, `DebtSnapshot` |
| Monthly rebalanced portfolios | **Implemented** | `PortfolioRebalanceStep`, `ConstantAllocationPolicy` |

### 14.2 Missing Capabilities

| Capability | Status | Notes |
|------------|--------|-------|
| Buy-and-hold portfolios | **NOT IMPLEMENTED — REPLICATION REQUIREMENT** | No `BuyAndHoldAllocationPolicy` or skip-rebalance mechanism. **Buy-and-hold is a Part 49 replication requirement.** |
| Withdrawal scaling | **Implemented / available** | Inherited from ERN methodology |
| Supplemental external cash flows | **Implemented / available** | Inherited from ERN methodology |

### 14.3 Important Observation

The codebase already has an existing implementation of margin-loan mechanics including `Part49WithdrawalPolicy`, `InterestAccrualStep`, `LTVEvaluationStep`, and forced liquidation. **The existing implementation should first verify that the existing FBF capabilities already express the Part 49 scenarios correctly before proposing any new engine abstraction.**

In particular, the following are **FBF implementation facts**, not ERN methodology evidence:

* `Part49WithdrawalPolicy`
* `LoanDrawStep`
* `InterestAccrualStep`
* `LTVEvaluationStep`
* `DebtInfo`
* forced-liquidation implementation
* `DebtSnapshot`

They can be tested against the methodology, but they cannot resolve the methodology by themselves. An implementation can be internally coherent while reproducing the wrong historical semantics.

---

## 15. Replication-Fidelity Questions

**Methodology blockers: 0**

**Implementation-level details: 1**

**Evidence extraction: pending**

### 15.1 Exact Forced-Liquidation Arithmetic — IMPLEMENTATION DETAIL

The article establishes the economic semantics but does not publish a detailed liquidation equation.

This is **not a blocker for reproducing the failure result** if the margin violation itself is sufficient to terminate the trajectory.

It only becomes a blocker if we want to reproduce the exact post-liquidation debt/portfolio numbers.

Classification:

> **OPEN — implementation-level numerical detail, not methodology blocker**

### 15.2 Exact Published Chart Values — EXTRACTED

All chart-derived observations have been transcribed from the article's embedded
charts. Exact values are recorded in §13.1–13.7 and used as diagnostic anchors
in §21.4.

| Observation | Transcribed value | Source |
|-------------|------------------|--------|
| 1965 margin-call failure window | Months 180–200 | Chart 02 |
| 1929 month-238 portfolio (75/25) | ≈ $1.185M | Chart 03 |
| 1929 month-238 loan (3.0% RR) | ≈ $1.085M | Chart 03 |
| 1929 month-238 net equity | ≈ $100k | Chart 03 |
| $20k/$20k L/P at 3.0% RR | 93.11% | Chart 04 |
| $20k/$20k L/P at 1.5% RR | 84.45% | Chart 04 |
| $20k/$20k L/P at 0.0% RR | 71.60% | Chart 04 |
| $30k/$10k max L/P (1965, 3% RR) | 70.25% | Chart 05 |
| $30k/$10k max L/P (1965, 1.5% RR) | 57.68% | Chart 05 |
| $30k/$10k max L/P (1929, 3% RR) | 67.74% | Chart 06 |
| $30k/$10k max L/P (1929, 1.5% RR) | 55.62% | Chart 06 |
| 75/25 final-value range | 2.63–13.25× | Chart 01 |
| 75/25 geometric return range | 3.27–8.99% | Chart 01 IRR |
| 100% equity worst-case | 3.23× | Chart 01 |
| 100% equity best-case | 26.42× | Chart 01 |
| 100% equity worst-case IRR | 3.99% | Chart 01 IRR |

**Classification:** ARTICLE — chart-derived. These are diagnostic reproduction
checks, not hard numerical oracles (see §21.4).

### 15.3 Everything Else — RESOLVED

The following are now RESOLVED:

1. Preliminary portfolio mechanics — buy-and-hold
2. 1965 aggressive case — buy-and-hold
3. Partial-leverage allocation — no rebalancing introduced
4. Preliminary cohort range — 1925–1990
5. Historical 4% conclusion — evaluated over 1925–1990 universe
6. $1M initial portfolio
7. 30-year horizon
8. 75/25 and 100/0 allocations
9. 0%, 1.5%, 3% fixed real borrowing rates
10. Monthly withdrawal frequency
11. Monthly loan-draw frequency
12. Monthly loan/portfolio sequencing — inherited Timing-Leverage-Calc methodology
13. Monthly real-rate conversion — annual real rate / 12
14. Loan accrual on outstanding balance
15. Fixed loan draw with no Part 52 timing
16. 25% minimum-equity requirement
17. 75% maximum LTV
18. Margin constraint must hold throughout the simulation
19. Margin-call liquidation is terminal
20. Recovery after a margin call must not resurrect the trajectory
21. Canonical FBF ERN equity data
22. Canonical FBF ERN bond data
23. Canonical real/CPI-adjusted representation
24. Part 52 floating-rate mechanics excluded

The existing Part49-specific engine capabilities should be **verified against these requirements**, not redesigned prematurely.

Do not resolve these by intuition.

---

## 16. Experiments to Replicate

### Experiment A — Preliminary Leverage Calculation

This is an analytical/final-value calculation and does not validate the stateful monthly margin-call simulation. Validate the analytical relationship between:

* initial portfolio ($1M)
* final portfolio target ($3M)
* final loan target
* real borrowing rate (0%, 1.5%, 3%)
* implied spending rate

### Experiment B — November 1965 Aggressive Leverage

* $1M initial portfolio
* 75/25 and 100/0 allocations
* Full retirement funding through margin
* 1.5% and 3.0% real borrowing rates
* Validate the historical trajectory and margin-call failure

### Experiment C — September 1929 Aggressive Leverage

* $1M initial portfolio
* 75/25 and 100/0 allocations
* Full retirement funding through margin
* Validate the historical trajectory and near-wipeout/margin-call condition

### Experiment D — $20k Portfolio + $20k Loan

* $1M initial portfolio
* 75/25 allocation
* $20k/year portfolio withdrawal + $20k/year loan draw
* 0%, 1.5%, 3.0% real borrowing rates
* Validate the three borrowing-rate variants

### Experiment E — $30k Portfolio + $10k Loan (Preferred)

* $1M initial portfolio
* 75/25 allocation
* $30k/year portfolio withdrawal + $10k/year loan draw
* 0%, 1.5%, 3.0% real borrowing rates
* Validate the preferred 3% + 1% strategy

### Experiment F — Historical 4% Conclusion

Only after the article's full cohort universe and aggregation methodology have been established.

Do not create a broad grid before the source methodology justifies the dimensions.

---

## 17. Oracle Hierarchy

Use the following hierarchy:

1. **Article methodology** — the primary source for how the simulation should work
2. **Independent reconstruction from source methodology/data** — reproduce results from documented methodology
3. **Published numerical/chart evidence** — article values as reference points
4. **FBF regression fixtures** — created only after independent reproduction

A FBF-generated oracle is regression protection, not independent ERN evidence.

Chart-derived approximate values should not become exact hard-coded acceptance values without traceable source precision.

---

## 18. Invariants

The following are mathematical sanity checks, not independent ERN evidence:

* loan balance cannot become negative unless explicit repayment exists
* positive borrowing increases debt
* positive interest increases debt if capitalized
* portfolio withdrawal and loan draw must remain separate
* margin utilization must use the resolved collateral definition
* once ERN's margin constraint is violated and the corresponding forced-liquidation event occurs, the trajectory is terminally failed. Subsequent hypothetical returns must not be applied to resurrect the pre-liquidation portfolio state.
* identical deterministic inputs must produce identical results

Do not use these invariants as substitutes for article replication.

---

## 19. Risks

Explicitly document:

* historical margin rules may not match modern brokerage rules
* article references Interactive Brokers as an example, but modern IBKR constraints must not be substituted for ERN's historical model
* real borrowing-rate assumptions may not correspond to actual historical available loan rates
* margin-call mechanics are potentially the most important fidelity issue
* buy-and-hold preliminary calculations must not be confused with the retirement simulation
* chart-derived values may not have enough precision for exact oracle assertions
* historical data used by the 2021 article may differ from current canonical FBF data
* the "never failed" conclusion is only meaningful after the exact cohort universe and failure definition are established

---

## 20. Workload Model

The exact workload depends on the cohort universe and scenario dimensions.

The implementation must distinguish:

* **Candidate cohorts** — the retirement cohorts eligible under the resolved cohort/date semantics
* **Simulation units** — candidate cohorts × experiments × configuration variants
* **Result/aggregation cells** — the dimensions over which results are summarized

At minimum, the implementation will need to evaluate:

* preliminary analytical calculations (non-simulation)
* November 1965 cohort: aggressive leverage (75/25, 100/0) × 2 borrowing rates
* September 1929 cohort: aggressive leverage (75/25, 100/0)
* November 1965 cohort: $20k/$20k × 3 borrowing rates
* November 1965 cohort: $30k/$10k × 3 borrowing rates
* September 1929 cohort: $30k/$10k
* full historical conclusion: requires resolved cohort universe

Do not multiply a provisional cohort count by the number of scenarios and call that the final workload. Exact unit counts should **not** be finalized until the cohort/date semantics have been established.

---

## 21. Acceptance Criteria

### 21.1 Structural

* [ ] Preliminary analytical calculation executes
* [ ] November 1965 aggressive leverage scenario executes
* [ ] September 1929 aggressive leverage scenario executes
* [ ] $20k/$20k scenario executes for all three borrowing rates
* [ ] $30k/$10k scenario executes for all three borrowing rates
* [ ] LTV evaluation executes and records DebtSnapshot
* [ ] Forced liquidation triggers when margin constraint is violated

### 21.2 Loan Mechanics

* [ ] Monthly loan balance = previous balance + new borrowing + accrued interest
* [ ] Real interest rate is applied correctly
* [ ] Portfolio withdrawal and loan draw remain separate
* [ ] Loan draw occurs at the resolved position in the monthly sequence

### 21.3 Margin Constraint

* [ ] LTV is computed as loan_balance / portfolio_value
* [ ] Margin-call threshold matches the resolved ERN definition
* [ ] Forced liquidation occurs when threshold is exceeded
* [ ] Post-liquidation trajectory does not "recover" from a margin call

### 21.4 Diagnostic Reproduction Checks

All chart-derived observations have been transcribed (§15.2). These are
diagnostic reproduction checks, not hard numerical oracles.

* [x] 1965 case: margin-call failure occurs approximately in the published window (months 180–200) — Chart 02 confirms
* [x] 1929 case: trajectory reaches approximately the published month/value (month ≈238, portfolio ≈ $1.185M, loan ≈ $1.085M) — Chart 03 confirms
* [x] $20k/$20k at month 201: loan/portfolio ratios match published values (93.11% / 84.45% / 71.60%) — Chart 04 confirms
* [x] $30k/$10k: max utilization matches published observations (70.25% at 3% RR, 57.68% at 1.5% RR for 1965) — Charts 05/06 confirm

### 21.5 Hard Replication Anchors

These should be reconstructed from source data/spreadsheet before becoming executable oracle values:

* [ ] Exact LTV threshold and margin-call trigger point
* [ ] Exact forced-liquidation amounts and timing
* [ ] Exact terminal portfolio/loan values for the 1965 and 1929 cohorts
* [ ] Exact cohort universe for the "never failed" conclusion

These are candidate anchors, not yet a final oracle specification.

### 21.6 Determinism

* [ ] Two independent runs of identical configurations produce identical results.

---

## 22. References

### 22.1 Primary Article

ERN Part 49 — *Using Leverage in Retirement – SWR Series Part 49*.

### 22.2 Methodological Predecessors

* ERN Part 28 — SWR Simulation Toolkit methodology
* ERN Part 52 — Timing Leverage in Retirement (subsequent refinement, not part of Part 49)
* Earlier ERN parts establishing the canonical market-return and cohort framework

### 22.3 Evidence Classification

* **ARTICLE — explicit:** Directly stated in Part 49
* **ARTICLE — chart-derived:** Read from the article's embedded charts
* **ARTICLE — table-derived:** Read from the article's embedded tables
* **INHERITED ERN METHODOLOGY:** Established in earlier ERN methodology documentation
* **FBF — verified implementation:** Established from the current repository
* **ASSUMPTION — unresolved:** Plausible interpretation not independently established
* **DERIVED FROM ARTICLE:** Calculated from explicitly stated article values

---

## 23. Future Implementation Prerequisites

Before implementation:

### 23.1 Methodology

* [ ] Establish exact monthly portfolio/loan sequencing inherited from ERN's SWR toolkit
* [ ] Establish loan interest accrual timing and real-rate application
* [ ] Establish exact withdrawal and loan-draw timing
* [ ] Establish rebalancing timing relative to other operations
* [ ] Establish the exact margin-ratio definition and check timing
* [ ] Establish forced-liquidation semantics
* [ ] Establish whether a margin call terminates the trajectory immediately
* [ ] Establish whether residual loan liability after liquidation is represented
* [ ] Verify that existing FBF `Part49WithdrawalPolicy`, `InterestAccrualStep`, and `LTVEvaluationStep` correctly express the ERN methodology

### 23.2 Evidence

* [x] Extract the exact numerical cells from any published tables
* [x] Establish the exact cohort universe for the "never failed" conclusion
* [x] Determine which chart-derived values are suitable as hard acceptance anchors
* [x] Do not create arbitrary tolerances

All chart-derived observations have been transcribed from the article's embedded
charts (§13.1–13.7, §15.2). Values are classified as ARTICLE — chart-derived
and serve as diagnostic reproduction checks, not hard oracles (§21.4).

### 23.3 Data

* [ ] Confirm that the canonical FBF market series reproduce the return environment used by Part 49
* [ ] Confirm CPI/real-return treatment
* [ ] Confirm the equity and bond series used in the preliminary analysis

---

## 24. Final Decision

**METHODOLOGY — COMPLETE / FROZEN**

**EVIDENCE EXTRACTION — COMPLETE**

The article is sufficiently explicit, together with the already-established ERN/FBF methodology, to define the simulation without inventing new semantics. All chart-derived observations have been transcribed from the article's embedded charts (§13.1–13.7, §15.2).

**What is RESOLVED:**

* initial portfolio = $1M
* 30-year horizon
* 75/25 and 100/0 allocations
* 0%, 1.5%, 3% fixed real borrowing rates
* All scenarios use buy-and-hold portfolio mechanics
* Preliminary cohort range = 1925–1990
* Historical 4% conclusion evaluated over 1925–1990 universe
* November 1965 cohort
* September 1929 cohort
* $20k/$20k scenario
* $30k/$10k scenario
* Monthly frequency of the stated withdrawals/loan draws
* Monthly loan/portfolio sequencing — inherited Timing-Leverage-Calc methodology
* Monthly real-rate conversion — annual real rate / 12
* Loan accrual on outstanding balance
* Fixed loan draw with no Part 52 timing
* 25% minimum-equity requirement
* 75% maximum LTV
* Margin constraint must hold throughout the simulation
* Margin-call liquidation is terminal
* Recovery after a margin call must not resurrect the trajectory
* Canonical FBF ERN equity/bond/CPI data
* Part 52 floating-rate mechanics excluded

**What remains:**

* Exact forced-liquidation arithmetic — implementation-level detail, not methodology blocker

The key replication model is:

```text
Historical monthly returns
        ↓
buy-and-hold 75/25 or 100/0 portfolio
        ↓
monthly portfolio withdrawal
        +
monthly fixed real-rate loan draw
        ↓
loan interest accrual
        ↓
LTV / margin constraint
        ↓
margin breach → terminal forced-liquidation failure
```

For the preferred historical experiment:

```text
$1,000,000 initial portfolio
30-year horizon
75/25 allocation
$30,000/year portfolio withdrawal (3% of initial)
$10,000/year margin borrowing (1% of initial)
$40,000/year total spending (4% of initial)
0% / 1.5% / 3% real loan-rate sensitivity
monthly execution
```

**Do not reopen:**

* portfolio mechanics;
* loan mechanics;
* margin semantics;
* cohort universe;
* data equivalence;
* Part 52 boundary.

Those are now resolved inputs to the replication.

The next phase is the **Part 49 E2E audit definition**, with the exact published chart cells treated as the comparison oracle.
