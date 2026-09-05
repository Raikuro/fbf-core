# S6 — Part 52 Timing Leverage: Architecture Plan (Revised)

**Stage:** S6 — Architecture Plan (no implementation)  
**Status:** PLANNING — REVISED  
**Date:** 2026-09-05  
**Scope:** Part 52 timing-leverage semantics, architecture, implementation stages

---

## 1. Executive Summary

Part 52 extends Part 49's untimed leverage with **drawdown-triggered borrowing**
and **repayment at fresh all-time highs**. The existing Part 49 debt infrastructure
is highly reusable. The primary new work is:

1. A `Part52WithdrawalPolicy` that makes conditional draw/repay decisions
2. Index-level drawdown computation using existing `MarketSnapshot.running_ath`
3. FFR dataset sourcing and time-varying interest rate integration

**No engine modification is currently justified.** However, this conclusion
is provisional — S6 planning must prove that the existing pipeline contracts
can express all Part 52 semantics cleanly before authorizing implementation.

---

## 2. Part 52 Methodology

### 2.1 Parameters (VERIFIED from article)

| Parameter | Value | Notes |
|-----------|-------|-------|
| Horizon | 30 years (360 months) | Same as Part 49 |
| Allocation | 75/25 stocks/bonds | Fixed throughout |
| Initial portfolio | $1,000,000 | Same as Part 49 |
| Drawdown trigger | 20%+ below real S&P 500 TR ATH | **Index-level** (§2.3) |
| Thresholds tested | 20%, 25%, 30%, 35% | ERN tests multiple thresholds |
| Borrow% | Variable (solver output) | Share of budget funded by loan (§2.5) |
| FFR+spread | 0.50%, 1.25%, 2.75% | Floating-rate scenarios (§3) |
| LTV constraint | 50% (2x leverage max) | Tighter than Part 49's 75% |
| LTV enforcement | **ON** | Forced liquidation on breach |
| Repayment trigger | Fresh ATH in real S&P 500 TR | **Index-level** ATH (§2.4) |
| Repayment mechanism | Double withdrawal, excess pays loan | Temporary budget increase |
| Final net worth target | $250,000 (real) | Constraint for solver |
| Solver objective | Maximize WR | Subject to $250K + 50% LTV |
| Solver variables | WR + Borrow% | Two-dimensional optimization |

### 2.2 Drawdown Reference: Index-Level (NOT Portfolio-Level)

**The 20%/25%/30%/35% drawdown trigger is based on the S&P 500 real total
return index, NOT the simulated portfolio.**

Evidence:

1. **Article language:** "20%+ below real S&P 500 TR ATH" — explicitly references
   the S&P 500 TR index, not the portfolio.

2. **Dataset semantics:** `MarketSnapshot.running_ath` is the ATH of the S&P 500
   real total return index level (values ~100–200, not ~1,000,000). Confirmed
   by data inspection and `K.2` of the roadmap: "Underwater" refers exclusively
   to the S&P 500 index being below its all-time high.

3. **S0-F1 finding:** "'Underwater' refers exclusively to the S&P 500 index
   being below its all-time high. It does not refer to the simulated portfolio."

**Implication:** No new `peak_portfolio_value` state variable is needed for the
drawdown trigger. The drawdown magnitude is computed from the existing
`MarketSnapshot` fields:

```python
# In Part52WithdrawalPolicy:
equity_index = context.market_snapshot.index_levels[AssetClass.EQUITY]
running_ath = context.market_snapshot.running_ath
if running_ath > 0:
    drawdown = Decimal("1") - (equity_index / running_ath)
else:
    drawdown = Decimal("0")
```

**However**, the repayment trigger ("fresh ATH") may be portfolio-level
(§2.4). This requires separate verification.

### 2.3 Drawdown Trigger Timing

The drawdown is evaluated at the **beginning of the period**, using the
current period's `MarketSnapshot` (which was loaded at the end of the
previous period by `SimulationStateUpdateStep`).

**Concrete example (index-level drawdown):**

```
Period M-1 end:
  equity_index = 120.0
  running_ath = 150.0
  is_ath = false
  is_underwater = true

Period M start (beginning-of-period state):
  equity_index = 120.0 (from M-1 end)
  running_ath = 150.0
  drawdown = 1 - (120/150) = 20.0%

  IF drawdown >= 20% AND loan_balance == 0:
      BORROW
```

### 2.4 Repayment Trigger: Index-Level ATH (RESOLVED)

**The repayment trigger is based on the S&P 500 TR index reaching a
fresh all-time high, NOT the portfolio.**

Evidence from ERN Part 52:

> "if we reach a fresh all-time high in the S&P 500 Total Return Index,
> we'll start paying back the margin loan"

**Implementation:** Use `market_snapshot.is_ath` directly. No new state
needed. Repayment triggers when the S&P 500 TR index hits a new ATH.

See §10.2 for full resolution.

### 2.5 Borrow% Budget Base

**Borrow%** is the share of the total monthly budget funded by the loan.

```
budget = initial_wealth × withdrawal_rate / 12
portfolio_withdrawal = budget × (1 - borrow_pct)
loan_draw = budget × borrow_pct
```

At 50% Borrow% with 4% total withdrawal rate: 2% from portfolio + 2% from loan.

**Verification needed:** Compare against ERN's published Borrow% values to
confirm the budget base is `initial_wealth × withdrawal_rate`, not
`portfolio_value × withdrawal_rate` or some other definition.

### 2.6 LTV Evaluation: Periodic (End-of-Period), Not Continuous

The S0-F6 decision states "LTV constraint is evaluated continuously." In the
context of a discrete monthly simulation, this means **at every evaluation
point within the simulation's temporal resolution** — which is once per
period at end-of-month.

**Exact evaluation point:** Step 66 (`LTVEvaluationStep`), after:
- Step 60: Market evolution (returns applied)
- Step 65: Interest accrual (capitalized)

**Ordering within a single month:**

```
Step 30: WithdrawalExecution — loan_balance may decrease (repayment)
Step 60: MarketEvolution — portfolio_value changes
Step 65: InterestAccrual — loan_balance increases (interest)
Step 66: LTVEvaluation — ltv = loan_balance / portfolio_value
         IF ltv > 0.50 AND ltv_enforcement:
             liquidate to restore ltv = 0.50
```

**Key invariant:** LTV is evaluated AFTER interest accrual, so the constraint
accounts for the increased loan balance from capitalized interest. If the
interest accrual pushes LTV above 50%, liquidation occurs immediately.

**Not "continuous" in the mathematical sense.** The correct terminology is
**periodic/end-of-period evaluation**. Within a single month, the sequence
is deterministic and the constraint is enforced at the designated point.

### 2.7 Concrete Month-by-Month Example

**Setup:** 1965 cohort, 20% threshold, Borrow% = 41.08%, FFR+0.50%,
initial_wealth = $1M, withdrawal_rate = 3.91%.

```
Month 1 (period_index = 0):
  BEGINNING STATE:
    equity_index = 100.0 (from dataset)
    running_ath = 100.0
    drawdown = 0%
    portfolio_value = $1,000,000
    loan_balance = $0
    cash_balance = $0
    is_ath = true

  DECISION:
    drawdown (0%) < threshold (20%) → NO BORROW
    is_ath = true BUT loan_balance = 0 → NO REPAYMENT
    NORMAL: portfolio_withdrawal = $1M × 3.91% / 12 = $3,258.33

  EXECUTION:
    WithdrawalExecution: sell $3,258.33 from portfolio
    portfolio_value_after_withdrawal = $996,741.67

  MARKET EVOLUTION:
    equity_index = 105.0 (hypothetical return)
    portfolio_value = $1,046,579.75 (5% return on $996,741.67)

  END OF PERIOD:
    InterestAccrual: loan_balance = $0 → no interest
    LTVEvaluation: loan_balance = $0 → no evaluation
    monthly_result: debt_snapshot = None

Month 12 (period_index = 11):
  BEGINNING STATE:
    equity_index = 80.0 (market decline)
    running_ath = 100.0
    drawdown = 1 - (80/100) = 20.0%
    portfolio_value = $850,000 (declined with market)
    loan_balance = $0
    is_ath = false, is_underwater = true

  DECISION:
    drawdown (20%) >= threshold (20%) AND loan_balance = 0 → BORROW
    budget = $1M × 3.91% / 12 = $3,258.33
    loan_draw = $3,258.33 × 41.08% = $1,338.22
    portfolio_withdrawal = $3,258.33 × 58.92% = $1,920.11

  EXECUTION:
    LoanDrawStep: loan_balance = $1,338.22, cash_balance = $1,338.22
    WithdrawalExecution: consume cash ($1,338.22) + sell portfolio ($1,920.11)
    total_spending = $3,258.33
    portfolio_value_after = $850,000 - $1,920.11 = $848,079.89

  MARKET EVOLUTION:
    equity_index = 82.0 (slight recovery)
    portfolio_value = $864,761.49 (2% return)

  END OF PERIOD:
    InterestAccrual: interest = $1,338.22 × (0.50% + spread) / 12
                     loan_balance += interest
    LTVEvaluation: ltv = loan_balance / portfolio_value
                   IF ltv > 0.50 → liquidate

Month 25 (hypothetical — market recovers to new ATH):
  BEGINNING STATE:
    equity_index = 105.0 (new high)
    running_ath = 105.0
    is_ath = true
    portfolio_value = $920,000
    loan_balance = $1,400.00 (after interest accrual)
    cash_balance = $0

  DECISION:
    is_ath = true AND loan_balance > 0 → REPAY
    budget = $3,258.33
    portfolio_withdrawal = $3,258.33 × 2 = $6,516.66 (doubled)
    loan_draw = 0

  EXECUTION:
    WithdrawalExecution: sell $6,516.66 from portfolio
    excess = $6,516.66 - $3,258.33 = $3,258.33
    loan_balance -= $3,258.33 (if cash covers excess; otherwise
    sell more portfolio to generate cash for repayment)
    Actually: total_spending = $6,516.66
              cash_consumed = $0 (cash_balance = 0)
              portfolio_sale = $6,516.66
              The excess ($3,258.33) is used to repay loan
              loan_balance -= $3,258.33

  NOTE: The exact repayment mechanism needs clarification:
  - Does the double withdrawal generate cash that repays the loan?
  - Or does the policy set loan_draw_amount = -repayment_amount
    (negative draw = repayment)?
  - The LoanDrawStep currently rejects negative draws (ValueError).
```

**Repayment mechanism requires clarification.** The current `LoanDrawStep`
rejects negative draws. Repayment needs either:
(a) A negative `loan_draw_amount` (requires modifying `LoanDrawStep`), OR
(b) Direct `loan_balance` reduction in `WithdrawalExecutionStep`, OR
(c) A separate `LoanRepaymentStep`.

This is an architectural decision that must be resolved before S6.1.

### 2.8 Temporal Semantics (DECIDED in S0-F5, S0-F6)

1. **Drawdown evaluation uses beginning-of-period market state.** The policy
   observes the current period's `MarketSnapshot` (loaded at end of previous
   period).

2. **Repayment occurs in the same period as ATH detection.** The policy
   observes `is_ath` from the current period's `MarketSnapshot`. If the
   index hit ATH at the end of period M-1, `is_ath=true` in period M's
   snapshot, and repayment triggers in period M.

3. **Interest accrual is applied at end of period** (step 65), after market
   evolution (step 60).

4. **LTV is evaluated at end of period** (step 66), after interest accrual
   (step 65). This is periodic evaluation at the simulation's temporal
   resolution, not continuous evaluation in the mathematical sense.

### 2.9 Key Distinction from Part 49

| Aspect | Part 49 | Part 52 |
|--------|---------|---------|
| Loan draw | Every month (fixed rate) | Conditional (below index threshold) |
| Draw amount | Fixed fraction of initial_wealth | Borrow% × budget (variable) |
| Interest rate | Fixed real | FFR + spread (floating) |
| LTV limit | 75% (observation only) | 50% (enforced, periodic) |
| Repayment | None | At fresh ATH |
| Budget | Fixed | Doubled during repayment |
| Drawdown reference | N/A | S&P 500 TR index (not portfolio) |

---

## 3. FFR Investigation (PREREQUISITE)

FFR investigation must complete before S6.1 architecture is frozen. The
architecture must be designed to accommodate time-varying rates from the
start, even if the first implementation uses fixed-rate fixtures.

### 3.1 Open Questions

| # | Question | Status |
|---|----------|--------|
| 1 | Exact ERN FFR source | OPEN |
| 2 | Historical coverage (1871–2015?) | OPEN |
| 3 | Frequency (monthly?) | OPEN |
| 4 | Definition (effective FFR, target rate, proxy?) | OPEN |
| 5 | Monthly transformation (annual/12 or compound?) | OPEN |
| 6 | Date alignment (when does rate change take effect?) | OPEN |
| 7 | Mid-month handling | OPEN |
| 8 | Correspondence with ERN calculation | OPEN |

### 3.2 FFR as Period Property vs Configuration Property

The interest rate for each period is a property of:

(a) **The simulation period** — derived from an external FFR dataset indexed
    by date, OR
(b) **The research configuration** — a fixed rate or spread specified in
    the study YAML.

For Part 52, the rate is `FFR(date) + spread`. The FFR component is a
period property; the spread is a configuration property.

**Architecture requirement:** The `InterestAccrualStep` must be able to
determine the annual rate for each period, either from a fixed value or
from a time-varying schedule. The rate schedule must be indexed by
`period_index` and aligned with the dataset's date sequence.

### 3.3 Rate Schedule Entry into SimulationContext

```python
@dataclass(frozen=True)
class SimulationContext:
    ...
    interest_rate: Decimal | None = None                    # Fixed rate
    interest_rate_schedule: tuple[Decimal, ...] | None = None  # Per-period rates
```

When `interest_rate_schedule` is present, `InterestAccrualStep` reads
`schedule[period_index]`. When absent, falls back to `interest_rate`.

The builder constructs the schedule from:
1. FFR dataset (JSON) → monthly rates indexed by date
2. Spread (from YAML config) → added to each monthly rate
3. Date alignment → map dataset dates to period indices

---

## 4. Existing Infrastructure Reuse

### 4.1 Directly Reusable (No Changes)

| Component | File | Reuse |
|-----------|------|-------|
| `LoanDrawStep` | `steps/loan_draw_step.py` | Executes loan draws from `WithdrawalDecision.loan_draw_amount` |
| `InterestAccrualStep` | `steps/interest_accrual_step.py` | Capitalizes interest (needs modification for time-varying rates) |
| `LTVEvaluationStep` | `steps/ltv_evaluation_step.py` | Enforces LTV when `ltv_enforcement=True` |
| `FailureDetectionStep` | `steps/failure_detection_step.py` | Detects depletion and margin-call-impossible |
| `SimulationState` debt fields | `simulation.py` | `loan_balance`, `cash_balance`, `interest_rate`, `ltv_limit`, `ltv_enforcement` |
| `DebtInfo` | `decision_context.py` | Snapshot of debt state for policy decisions |
| `WithdrawalDecision` | `decisions.py` | `loan_draw_amount` field bridges policy → pipeline |
| `MarketSnapshot.is_ath` | `market_snapshot.py` | Pre-computed ATH status (index-level) |
| `MarketSnapshot.is_underwater` | `market_snapshot.py` | Pre-computed underwater status (index-level) |
| `MarketSnapshot.running_ath` | `market_snapshot.py` | Pre-computed index ATH value |
| `MarketSnapshot.index_levels` | `market_snapshot.py` | Current index levels (for drawdown computation) |

### 4.2 Requires Modification

| Component | File | Change | Reason |
|-----------|------|--------|--------|
| `Part52WithdrawalPolicy` | **NEW** `policies/part52_withdrawal.py` | New policy class | Conditional draw/repay decisions |
| `BuildDecisionContextStep` | `steps/build_decision_context_step.py` | Pass `cash_balance` to `DebtInfo` | **Bug fix**: currently always 0 |
| `SimulationContext` | `simulation_context.py` | Add optional `interest_rate_schedule` | Time-varying rates |
| `InterestAccrualStep` | `steps/interest_accrual_step.py` | Read rate from schedule if available | Floating-rate support |
| `WithdrawalDecision` | `decisions.py` | Add `is_repayment: bool` field | Signal repayment to result builder |
| `MonthlyResult` | `simulation.py` | Add `is_repayment: bool` field | Track repayment events |

### 4.3 Requires Resolution Before Implementation

| Component | Issue | Resolution needed |
|-----------|-------|-------------------|
| Repayment mechanism | `LoanDrawStep` rejects negative draws | How does loan_balance decrease during repayment? |
| Drawdown computation | Index-level drawdown needs `equity` from `index_levels` | Policy must extract equity index from `MarketSnapshot` |
| Repayment trigger | Index-level or portfolio-level ATH? | Verify from ERN methodology |

### 4.4 Engine Modification Assessment

**No engine modification is currently justified.** However, this conclusion
is provisional. S6 planning must prove that the existing pipeline contracts
can express:

- Conditional borrowing (via policy-level `loan_draw_amount`)
- Index-level drawdown triggers (via `MarketSnapshot` fields)
- Repayment (requires resolution — see §4.3)
- Temporary increased withdrawals (via doubled `nominal_amount`)
- Period-varying interest (via `interest_rate_schedule`)
- Enforced LTV constraints (existing `LTVEvaluationStep`)

If any of these cannot be expressed cleanly without violating domain
boundaries, an engine modification may be proposed. Any such modification
must preserve the Decimal reference engine's mathematical behavior and
receive separate architectural justification.

---

## 5. Architecture Design

### 5.1 Drawdown Computation (Index-Level)

No new state variable needed. The policy computes drawdown from
`MarketSnapshot`:

```python
# In Part52WithdrawalPolicy.decide():
equity_index = context.market_snapshot.index_levels[AssetClass.EQUITY]
running_ath = context.market_snapshot.running_ath
if running_ath > 0:
    drawdown = Decimal("1") - (equity_index / running_ath)
else:
    drawdown = Decimal("0")
```

**Invariant:** `drawdown >= 0` when `equity_index <= running_ath`.
`drawdown = 0` when `equity_index = running_ath` (at ATH).

### 5.2 Part52WithdrawalPolicy

**Location:** `src/fbf/core/domain/policies/part52_withdrawal.py`

**Design:** Stateless policy. All state comes from `DecisionContext` and
`SimulationContext`.

**Constructor parameters:**
- `withdrawal_rate: Decimal` — annual portfolio withdrawal rate
- `borrow_pct: Decimal` — share of budget funded by loan (0.0 to 1.0)
- `drawdown_threshold: Decimal` — index drawdown trigger (e.g., 0.20 for 20%)

**Decision logic:**
```
budget = initial_wealth × withdrawal_rate / 12

# Compute index-level drawdown
equity_index = market_snapshot.index_levels[EQUITY]
drawdown = 1 - (equity_index / running_ath)

IF drawdown >= threshold AND loan_balance == 0:
    # BORROW: activate leverage
    loan_draw = budget × borrow_pct
    portfolio_withdrawal = budget × (1 - borrow_pct)
    is_repayment = False

ELIF market_snapshot.is_ath AND loan_balance > 0:
    # REPAY: double withdrawal, excess pays loan
    portfolio_withdrawal = budget × 2
    loan_draw = 0
    is_repayment = True

ELSE:
    # NORMAL: no leverage activity
    portfolio_withdrawal = budget
    loan_draw = 0
    is_repayment = False
```

### 5.3 Repayment Mechanism (RESOLVED)

**Architecture: Dedicated `LoanRepaymentStep` at sequence_order 32.**

ERN article describes: "double the withdrawals from the stock/bond
portfolio and use the excess to pay down the margin loan"

**Exact mechanism:**

```
WithdrawalDecision:
  portfolio_withdrawal = budget × 2  (double)
  loan_draw_amount = 0               (no new borrowing)
  is_repayment = True

LoanDrawStep (28):
  loan_balance += 0  (no change)

WithdrawalExecutionStep (30):
  cash_consumed = min(cash_balance, portfolio_withdrawal)
  portfolio_sold = portfolio_withdrawal - cash_consumed
  portfolio_value -= portfolio_sold

LoanRepaymentStep (32):
  IF is_repayment AND loan_balance > 0:
      excess = portfolio_withdrawal - budget
      repayment = min(excess, loan_balance)
      loan_balance -= repayment
```

**Edge cases:**

1. **loan_balance < excess**: Repay only `loan_balance`. The remaining
   excess stays in the portfolio (not spent).

2. **loan_balance = 0**: No repayment. `is_repayment` is True but
   no action needed.

3. **cash_balance > 0**: The double withdrawal consumes cash first,
   then sells portfolio. The excess is computed from the total
   portfolio_withdrawal, not from cash.

4. **Interaction with interest accrual**: Interest accrues at step 65
   (after repayment at step 32). If repayment reduces loan_balance
   to 0, no interest accrues.

5. **Interaction with LTV**: LTV is evaluated at step 66 (after
   interest accrual). If repayment reduces LTV below 50%, no
   liquidation needed.

6. **Interaction with failure detection**: Failure detection at step 75
   checks portfolio_value. Repayment reduces portfolio_value by the
   double withdrawal amount, which could affect failure detection.

**Why not negative loan_draw_amount:**
- `LoanDrawStep` rejects negative draws (ValueError)
- Repayment is a distinct financial state transition
- Cleaner separation of concerns
- Avoids coupling draw and repay logic

See §10.3 for full resolution.

### 5.4 Time-Varying Interest Rates

**Design:** Optional `interest_rate_schedule` on `SimulationContext`.

```python
@dataclass(frozen=True)
class SimulationContext:
    ...
    interest_rate: Decimal | None = None              # Fixed rate (backward compat)
    interest_rate_schedule: tuple[Decimal, ...] | None = None  # Per-period rates
```

**InterestAccrualStep modification:**
```python
def execute(self, state: SimulationState) -> SimulationState:
    if state.loan_balance <= 0:
        return state
    
    # Determine rate for this period
    if state.context.interest_rate_schedule is not None:
        if state.period_index < len(state.context.interest_rate_schedule):
            annual_rate = state.context.interest_rate_schedule[state.period_index]
        else:
            annual_rate = state.context.interest_rate or Decimal("0")
    else:
        annual_rate = state.interest_rate
    
    monthly_rate = annual_rate / Decimal("12")
    interest = state.loan_balance * monthly_rate
    state.loan_balance += interest
    return state
```

**FFR data flow:**
```
FFR dataset (JSON) → builder.py → interest_rate_schedule per unit
    → SimulationContext.interest_rate_schedule
    → InterestAccrualStep reads per-period rate
```

### 5.5 Bug Fix: DebtInfo.cash_balance

`BuildDecisionContextStep` currently constructs `DebtInfo` without passing
`cash_balance`, causing it to default to `Decimal("0")`. This means
`DebtInfo.net_worth` is incorrect.

**Fix:** Pass `cash_balance=state.cash_balance` to `DebtInfo` constructor.

**Regression requirement:** Prove `net_worth = portfolio_value + cash_balance
- loan_balance` for a non-zero cash balance. Verify that Part 49 results
are unchanged by this fix (Part 49 policies don't observe
`debt_info.net_worth`, so mathematical behavior is preserved).

### 5.6 Pipeline Order (Modified)

```
 0  InitializeAllocationStep
10  BuildDecisionContextStep      ← builds DecisionContext with DebtInfo (bug fix)
20  WithdrawalDecisionStep        ← Part52WithdrawalPolicy decides draw/repay
28  LoanDrawStep                  ← executes loan draw (if any)
30  WithdrawalExecutionStep       ← consumes cash, sells portfolio
32  LoanRepaymentStep (NEW)       ← executes repayment (if is_repayment)
40  AllocationDecisionStep
50  PortfolioRebalanceStep
60  MarketEvolutionStep           ← returns applied
65  InterestAccrualStep           ← capitalized (reads schedule if available)
66  LTVEvaluationStep             ← enforced at 50%
70  MonthlyResultBuilderStep      ← captures state, is_repayment flag
75  FailureDetectionStep
80  SimulationStateUpdateStep
```

**New step:** `LoanRepaymentStep` at sequence_order 32 (after withdrawal
execution, before allocation decision). This step:
- Reads `withdrawal_decision.is_repayment`
- If true, computes excess = total_spending - budget
- Reduces `loan_balance` by excess
- Reduces `cash_balance` by excess (if cash available)

---

## 6. Implementation Stages

### S6.P — Semantic/Data Closure (PREREQUISITE)

**Scope:** Close all open semantic questions before architecture is frozen.

**Deliverables:**
- FFR dataset sourced and documented
- Drawdown reference confirmed (index-level per §2.2)
- Repayment trigger confirmed (index-level or portfolio-level per §2.4)
- Repayment mechanism designed (§5.3)
- LTV evaluation semantics documented (§2.6)
- Borrow% budget base confirmed (§2.5)
- Solver scope classified (§7)

**Exit criteria:**
- All §2 open questions resolved
- FFR investigation complete (§3.1)
- Canonical monthly state-transition specification produced
- Architecture plan updated with resolved semantics

### S6.1 — Core Part 52 Execution

**Scope:** Implement the smallest architecture capable of expressing the
verified semantics. Include fixed-rate fixtures for deterministic testing.

**Deliverables:**
- `Part52WithdrawalPolicy` class
- `LoanRepaymentStep` (or equivalent repayment mechanism)
- `DebtInfo.cash_balance` bug fix with regression
- `is_repayment` field on `WithdrawalDecision` and `MonthlyResult`
- `interest_rate_schedule` on `SimulationContext` (optional, for FFR)
- `InterestAccrualStep` modification for per-period rates
- Unit tests for policy decision logic
- Integration tests for single-cohort Part 52 execution

**Fixed-rate fixtures (for testing only):**
- Interest rate: fixed (e.g., 1.5%)
- Borrow%: fixed per cell
- Drawdown threshold: fixed per cell
- LTV enforcement: ON at 50%

**Validation anchors:**
- 1965 cohort, no timing, no leverage: WR ≈ 3.58%
- 1965 cohort, no timing, fixed rate: WR ≈ 3.78%, Borrow% ≈ 10.76%

**Exit criteria:**
- Policy correctly triggers borrowing below index threshold
- Policy correctly triggers repayment at ATH
- LTV enforcement works at 50%
- Bug fix regression passes
- Part 49 results unchanged

### S6.2 — FFR Integration

**Scope:** Materialize the verified FFR dataset. Integrate period-varying
rates. Validate rate alignment independently.

**Deliverables:**
- FFR dataset (JSON) committed to `data/ern/`
- Builder support for FFR + spread configuration
- Rate alignment validation (independent of full study)
- Floating-rate validation against ERN anchors

**Validation anchors:**
- 1965 cohort, 25% threshold, FFR+0.50%: WR ≈ 3.92%
- 1965 cohort, 25% threshold, FFR+1.25%: WR ≈ 3.87%
- 1965 cohort, 25% threshold, FFR+2.75%: WR ≈ 3.75%

**Exit criteria:**
- FFR dataset is sourced, documented, and committed
- Rate alignment is independently validated
- Floating-rate scenarios produce results consistent with ERN anchors
- Fixed-rate scenarios remain unaffected

### S6.3 — Canonical Part 52 Replication

**Scope:** Execute the defined ERN grid. Compare against independently
established anchors. Validate all components.

**Deliverables:**
- Full Part 52 study YAML configuration
- Grid execution across all threshold × Borrow% × FFR combinations
- Validation report comparing against ERN published results
- Performance benchmark

**Grid (approximate):**
- 4 thresholds × 5 Borrow% × 3 FFR scenarios = 60 cells
- × 1,739 cohorts = 104,340 units

**Validation anchors (all from §2.1):**
- 1965 cohort results (6 scenarios)
- 1929 cohort results (2 scenarios)

**Exit criteria:**
- All cells execute successfully
- Results are qualitatively consistent with ERN anchors
- Performance is comparable to Part 49 baseline
- Validation report is complete

### S6.4 — Optimization/Solver (Conditional)

**Scope:** Only if the goal is to reproduce ERN's optimization procedure
itself (maximizing WR subject to constraints).

**Classification:** This is NOT required for Part 52 replication if S6.3
validates against already-known ERN parameter points. It IS required if
the goal is to reproduce the ERN process of discovering those points.

**Candidate approaches:**
1. Manual parameter sweep (no new dependencies)
2. FBF optimization layer (if constraint support exists)
3. Grid refinement with binary search

---

## 7. Solver Scope Classification

### A. Framework Execution (S6.1–S6.3)

Can FBF execute a supplied `(withdrawal_rate, borrow_pct, threshold,
spread, etc.)` configuration and produce correct results?

**This does not require a solver.** This is the core replication goal.

### B. ERN Optimization Reproduction (S6.4)

Can FBF reproduce ERN's process of maximizing withdrawal rate subject to
the terminal-net-worth ($250K) and LTV (50%) constraints?

**This may require a solver/search procedure.** It is a separate concern
from framework execution.

**Classification:** S6.4 is deferred only if S6 initially targets
execution/replication of already-known ERN parameter points rather than
reproducing the optimization procedure itself. Do not silently omit it
from the definition of "full Part 52 replication."

---

## 8. Validation Strategy

### 8.1 Oracle Strategy

| Study | Independent Oracle | Published Anchors | Per-Cohort |
|-------|-------------------|-------------------|------------|
| Part 52 | PARTIAL | WR + Borrow% tables | LIMITED (2 cohorts) |

### 8.2 Validation Anchors

From ERN Part 52 (VERIFIED from article):

| Cohort | Threshold | FFR+spread | WR | Borrow% |
|--------|-----------|------------|-----|---------|
| 1965 | none | none | 3.58% | 0% |
| 1965 | none | +0.50% | 3.78% | 10.76% |
| 1965 | 20% | repayment | 3.91% | 41.08% |
| 1965 | 25% | +0.50% | 3.92% | — |
| 1965 | 25% | +1.25% | 3.87% | — |
| 1965 | 25% | +2.75% | 3.75% | — |
| 1929 | none | none | 4.39% | — |
| 1929 | 35% | repayment | 4.93% | — |

### 8.3 Validation Discipline

1. Independent methodology reconstruction
2. Independent oracle (where feasible)
3. FBF implementation
4. Per-cohort comparison
5. Published-result comparison (as validation anchors, not tuning targets)
6. Regression protection

---

## 9. Risk Register

| Risk | Severity | Probability | Mitigation | Status |
|------|----------|-------------|------------|--------|
| FFR data cannot be sourced | MEDIUM | LOW | Fixed-rate scenarios still valid; FFR is supplementary | **RESOLVED** §10.1 |
| Drawdown is actually portfolio-level | HIGH | LOW | Article language says index; verify against ERN | **RESOLVED** §10.2 |
| Repayment is portfolio-level ATH | MEDIUM | MEDIUM | Requires clarification in S6.P | **RESOLVED** §10.2 |
| Repayment mechanism conflicts with LoanDrawStep | MEDIUM | HIGH | New LoanRepaymentStep (§5.3) | **RESOLVED** §10.3 |
| DebtInfo.cash_balance bug affects Part 49 | MEDIUM | LOW | Fix with regression; Part 49 doesn't observe net_worth | PENDING S6.1 |
| LTV enforcement causes unexpected liquidation | MEDIUM | MEDIUM | Validate with controlled fixtures | PENDING S6.1 |
| Solver scope unclear | LOW | MEDIUM | Explicitly classify in §7 | **RESOLVED** §7 |
| FFR pre-1928 proxy uncertain | MEDIUM | MEDIUM | Use call money rate or T-bill as proxy | **RESOLVED** §10.1 |
| Repayment timing unclear | MEDIUM | LOW | Repayment in same period as ATH detection | **RESOLVED** §10.5 |
| Borrow% budget base incorrect | MEDIUM | LOW | Budget = initial_wealth × withdrawal_rate / 12 | **RESOLVED** §10.4 |

---

## 10. S6.P Findings (Semantic/Data Closure)

### 10.1 FFR Dataset Provenance and Transformation (RESOLVED)

**ERN uses FFR (Federal Funds Rate) + spread** for the margin loan rate.
The article explicitly states: "x% over the Federal Funds Rate (FFR)" with
spreads of 0.50%, 1.25%, and 2.75%.

**FFR Data Sources:**

| Period | Source | Series ID | Frequency | Notes |
|--------|--------|-----------|-----------|-------|
| 1954-07 to present | FRED | FEDFUNDS | Monthly | Monthly average of daily effective FFR |
| 1928-04 to 1954-06 | FRED category 33951 | Various | Daily | From WSJ and NY Herald-Tribune |
| 1871-01 to 1928-03 | **Proxy required** | — | Monthly | FFR market didn't exist |

**Provenance:**

- **FEDFUNDS**: Board of Governors of the Federal Reserve System (US),
  H.15 Selected Interest Rates. Monthly averages of daily figures.
  URL: https://fred.stlouisfed.org/series/FEDFUNDS

- **1928-1954 daily FFR**: Anbil, Carlson, Hanes, Wheelock (2020),
  "A New Daily Federal Funds Rate Series and History of the Federal
  Funds Market, 1928-1954," FEDS 2020-059. Available on FRED category
  33951. Source data from Wall Street Journal and NY Herald-Tribune.

- **Pre-1928 proxy**: The federal funds market started in the 1920s.
  For 1871-1928, a proxy rate is required. Options:
  - Call money rate (FRED M1301AUSM156NNBR, 1857-1934)
  - 3-month T-bill rate (ERN uses this for cash returns in SWR toolbox)
  - Commercial paper rate

**Recommended proxy**: Use the same short-term rate ERN uses for cash
returns in the SWR toolbox (3-month T-bill from Shiller for 1871-1927),
or the call money rate (available from 1857). The call money rate is the
most historically accurate proxy for overnight lending rates before FFR.

**Transformation rules:**

1. FEDFUNDS (1954+): Use monthly values directly (already monthly averages)
2. 1928-1954 daily data: Average daily observations to monthly values
3. Pre-1928 proxy: Use monthly values directly (already monthly in NBER data)

**Date alignment:**
- FFR applies to the month it's observed in
- Interest accrual uses the FFR from the current period's dataset entry
- No lag or lead required (the rate is known at the start of the month)

**Missing/exceptional values:**
- 1928-1933: Some gaps in daily data (bank holidays, market closures)
- 1930s-1940s: FFR near zero lower bound (wartime pegs)
- 1951 Treasury-Fed Accord: Transition from pegged to market rates

**Spread scenarios:**
- FFR + 0.50%: Best case (box spread trade)
- FFR + 1.25%: Interactive Brokers margin loan
- FFR + 2.75%: HELOC / other brokers

### 10.2 Repayment Trigger: Index-Level ATH (RESOLVED)

**The repayment trigger is based on the S&P 500 TR index reaching a
fresh all-time high, NOT the portfolio.**

Evidence from ERN Part 52:

> "if we reach a fresh all-time high in the S&P 500 Total Return Index,
> we'll start paying back the margin loan"

> "I assume that we simply double the withdrawals from the stock/bond
> portfolio and use the excess to pay down the margin loan"

**Implementation:**
```python
# In Part52WithdrawalPolicy:
if context.market_snapshot.is_ath and state.loan_balance > 0:
    # REPAYMENT: double withdrawal, no loan draw
    portfolio_withdrawal = budget * 2
    loan_draw_amount = Decimal("0")
    is_repayment = True
```

**Key distinction preserved:**
- Drawdown trigger (borrowing): Index-level drawdown magnitude
- Repayment trigger: Index-level fresh ATH
- Both use `MarketSnapshot` fields, NOT portfolio-level tracking

### 10.3 Repayment Mechanism: LoanRepaymentStep (RESOLVED)

**Architecture: Dedicated `LoanRepaymentStep` at sequence_order 32.**

ERN article describes: "double the withdrawals from the stock/bond
portfolio and use the excess to pay down the margin loan"

**Exact mechanism:**

```
WithdrawalDecision:
  portfolio_withdrawal = budget × 2  (double)
  loan_draw_amount = 0               (no new borrowing)
  is_repayment = True

LoanDrawStep (28):
  loan_balance += 0  (no change)

WithdrawalExecutionStep (30):
  cash_consumed = min(cash_balance, portfolio_withdrawal)
  portfolio_sold = portfolio_withdrawal - cash_consumed
  portfolio_value -= portfolio_sold

LoanRepaymentStep (32):
  IF is_repayment AND loan_balance > 0:
      excess = portfolio_withdrawal - budget
      repayment = min(excess, loan_balance)
      loan_balance -= repayment
```

**Edge cases:**

1. **loan_balance < excess**: Repay only `loan_balance`. The remaining
   excess stays in the portfolio (not spent).

2. **loan_balance = 0**: No repayment. `is_repayment` is True but
   no action needed.

3. **cash_balance > 0**: The double withdrawal consumes cash first,
   then sells portfolio. The excess is computed from the total
   portfolio_withdrawal, not from cash.

4. **Interaction with interest accrual**: Interest accrues at step 65
   (after repayment at step 32). If repayment reduces loan_balance
   to 0, no interest accrues.

5. **Interaction with LTV**: LTV is evaluated at step 66 (after
   interest accrual). If repayment reduces LTV below 50%, no
   liquidation needed.

6. **Interaction with failure detection**: Failure detection at step 75
   checks portfolio_value. Repayment reduces portfolio_value by the
   double withdrawal amount, which could affect failure detection.

**Why not negative loan_draw_amount:**
- `LoanDrawStep` rejects negative draws (ValueError)
- Repayment is a distinct financial state transition
- Cleaner separation of concerns
- Avoids coupling draw and repay logic

### 10.4 Borrow% Budget Base (RESOLVED)

**Borrow% is the share of the total monthly budget funded by the loan.**

From ERN article:
- "4% annualized withdrawal rate"
- "a quarter of the monthly budget is financed through the margin loan"
- "the share of retirement budget funded by the margin loan"

**Formula:**
```
budget = initial_wealth × withdrawal_rate / 12
portfolio_withdrawal = budget × (1 - borrow_pct)
loan_draw = budget × borrow_pct
```

**Example (1965 cohort, no timing):**
- initial_wealth = $1,000,000
- withdrawal_rate = 4% = 0.04
- borrow_pct = 25% = 0.25
- budget = $1,000,000 × 0.04 / 12 = $3,333.33
- portfolio_withdrawal = $3,333.33 × 0.75 = $2,500.00
- loan_draw = $3,333.33 × 0.25 = $833.33

**Example (1965 cohort, with timing, 20% threshold):**
- withdrawal_rate = 3.91% = 0.0391
- borrow_pct = 41.08% = 0.4108
- budget = $1,000,000 × 0.0391 / 12 = $3,258.33
- portfolio_withdrawal = $3,258.33 × 0.5892 = $1,920.11
- loan_draw = $3,258.33 × 0.4108 = $1,338.22

**Verification:** The budget base is `initial_wealth × withdrawal_rate`,
NOT `portfolio_value × withdrawal_rate`. The withdrawal rate is calibrated
against the initial portfolio value, not the current value.

### 10.5 Repayment Timing (RESOLVED)

**Repayment occurs in the same period as ATH detection.**

Timeline:
1. Period M-1 end: `SimulationStateUpdateStep` loads `MarketSnapshot`
   with `is_ath = true` (S&P 500 TR index hit new ATH at end of M-1)
2. Period M start: `Part52WithdrawalPolicy` observes `is_ath = true`
3. Period M: Double withdrawal executed, excess repays loan

**Concrete example (1965 cohort):**

```
Month 84 (hypothetical):
  BEGINNING STATE:
    equity_index = 155.0 (new high)
    running_ath = 155.0
    is_ath = true
    loan_balance = $1,400.00
    cash_balance = $0
    portfolio_value = $920,000

  DECISION:
    is_ath = true AND loan_balance > 0 → REPAY
    budget = $3,258.33
    portfolio_withdrawal = $3,258.33 × 2 = $6,516.66
    loan_draw_amount = 0
    is_repayment = True

  EXECUTION:
    LoanDrawStep: no change
    WithdrawalExecutionStep:
      cash_consumed = $0 (cash_balance = 0)
      portfolio_sold = $6,516.66
      portfolio_value = $920,000 - $6,516.66 = $913,483.34
    LoanRepaymentStep:
      excess = $6,516.66 - $3,258.33 = $3,258.33
      repayment = min($3,258.33, $1,400.00) = $1,400.00
      loan_balance = $1,400.00 - $1,400.00 = $0

  MARKET EVOLUTION:
    equity_index = 158.0 (slight recovery)
    portfolio_value = $913,483.34 × (1 + return)

  END OF PERIOD:
    InterestAccrual: loan_balance = $0 → no interest
    LTVEvaluation: loan_balance = $0 → no evaluation
```

### 10.6 LTV Evaluation Timing (RESOLVED)

**LTV is evaluated at end-of-period (step 66), after interest accrual
(step 65). This is periodic evaluation, not continuous.**

Ordering within a single month:
```
Step 30: WithdrawalExecution — loan_balance may decrease (repayment)
Step 60: MarketEvolution — portfolio_value changes
Step 65: InterestAccrual — loan_balance increases (interest)
Step 66: LTVEvaluation — ltv = loan_balance / portfolio_value
         IF ltv > 0.50 AND ltv_enforcement:
             liquidate to restore ltv = 0.50
```

**Key invariant:** LTV is evaluated AFTER interest accrual, so the
constraint accounts for the increased loan balance from capitalized
interest. If the interest accrual pushes LTV above 50%, liquidation
occurs immediately.

### 10.7 Interest Rate Timing (RESOLVED)

**Interest accrues at end-of-period (step 65), using the FFR from
the current period's dataset entry.**

No lag or lead: the FFR for month M is the rate observed in month M.
Interest accrual formula:
```
annual_rate = FFR[period_index] + spread
monthly_rate = annual_rate / 12
interest = loan_balance × monthly_rate
loan_balance += interest
```

**FFR dataset alignment:**
- Dataset entry for month M provides the FFR for month M
- `interest_rate_schedule[period_index]` = FFR + spread for that month
- Interest accrues on the loan_balance at the start of the period

### 10.8 Failure Semantics Under Leveraged Repayment (RESOLVED)

**Failure detection occurs at step 75, after LTV evaluation.**

Failure conditions:
1. `portfolio_value <= 0` (depletion)
2. `portfolio_value < margin_call_minimum` AND `ltv_enforcement = True`
   (margin call impossible)

**Repayment interaction:**
- Repayment reduces `portfolio_value` by the double withdrawal amount
- This could push `portfolio_value` closer to depletion
- However, repayment also reduces `loan_balance`, which improves LTV
- Net effect: repayment reduces both assets and liabilities

**Edge case:**
- If `portfolio_value` is very low and repayment causes depletion,
  the simulation fails at step 75
- This is correct behavior: the retiree cannot sustain the double
  withdrawal

---

## 11. Open Questions (Requiring Resolution in S6.P)

| # | Question | Status | Resolution |
|---|----------|--------|------------|
| 1 | FFR source, coverage, transformation | **RESOLVED** | §10.1 |
| 2 | Repayment trigger: index or portfolio ATH? | **RESOLVED** | §10.2 |
| 3 | Repayment mechanism | **RESOLVED** | §10.3 |
| 4 | Borrow% budget base | **RESOLVED** | §10.4 |
| 5 | Repayment timing | **RESOLVED** | §10.5 |
| 6 | LTV evaluation timing | **RESOLVED** | §10.6 |
| 7 | Interest rate timing | **RESOLVED** | §10.7 |
| 8 | Failure semantics under repayment | **RESOLVED** | §10.8 |

**All S6.P semantic questions are RESOLVED.**

---

## 11. Documentation Updates Required

| Document | Update | When |
|----------|--------|------|
| `MULTI_STUDY_REPLICATION_ROADMAP.md` | Update S6 section with architecture reference | After plan approval |
| `TODO.md` | Update FFR prerequisite with investigation findings | During S6.P |
| `docs/DECISIONS.md` | Add Part 52 temporal semantics decisions | During S6.P |
| `examples/studies/ern_part52.yaml` | New study configuration | During S6.1 |

---

## 14. Canonical Monthly State Transition (Part 52)

This section defines the exact state transition for a single month in the
Part 52 simulation. All steps are ordered by sequence_number.

### 14.1 Step Sequence

```
Step 0:   InitializeAllocationStep
          - Initialize portfolio allocation (75/25 stocks/bonds)

Step 10:  BuildDecisionContextStep
          - Build DecisionContext with market snapshot, debt info
          - FIX: Pass cash_balance to DebtInfo (§5.5)

Step 20:  WithdrawalDecisionStep
          - Part52WithdrawalPolicy decides:
            - IF drawdown >= threshold AND loan_balance == 0:
                BORROW (activate leverage)
            - ELIF is_ath AND loan_balance > 0:
                REPAY (double withdrawal)
            - ELSE:
                NORMAL (no leverage activity)
          - Output: WithdrawalDecision with:
            - portfolio_withdrawal: Decimal
            - loan_draw_amount: Decimal
            - is_repayment: bool

Step 28:  LoanDrawStep
          - Execute loan draw (if loan_draw_amount > 0)
          - loan_balance += loan_draw_amount
          - cash_balance += loan_draw_amount

Step 30:  WithdrawalExecutionStep
          - Consume cash and sell portfolio to meet spending
          - cash_consumed = min(cash_balance, portfolio_withdrawal)
          - portfolio_sold = portfolio_withdrawal - cash_consumed
          - portfolio_value -= portfolio_sold
          - cash_balance -= cash_consumed

Step 32:  LoanRepaymentStep (NEW)
          - Execute repayment (if is_repayment AND loan_balance > 0)
          - excess = portfolio_withdrawal - budget
          - repayment = min(excess, loan_balance)
          - loan_balance -= repayment

Step 40:  AllocationDecisionStep
          - Determine target allocation based on current state

Step 50:  PortfolioRebalanceStep
          - Rebalance to target allocation (75/25)

Step 60:  MarketEvolutionStep
          - Apply returns to portfolio
          - Update equity_index and bond_index from dataset
          - Update running_ath, is_ath, is_underwater

Step 65:  InterestAccrualStep
          - Capitalize interest on loan
          - annual_rate = FFR[period_index] + spread
          - monthly_rate = annual_rate / 12
          - interest = loan_balance × monthly_rate
          - loan_balance += interest

Step 66:  LTVEvaluationStep
          - Evaluate LTV constraint (50% for Part 52)
          - ltv = loan_balance / portfolio_value
          - IF ltv > 0.50 AND ltv_enforcement:
              liquidate to restore ltv = 0.50

Step 70:  MonthlyResultBuilderStep
          - Capture monthly result
          - Include: is_repayment, debt_snapshot, ltv

Step 75:  FailureDetectionStep
          - Check depletion: portfolio_value <= 0
          - Check margin call: portfolio_value < minimum AND ltv_enforced

Step 80:  SimulationStateUpdateStep
          - Update simulation state for next period
          - Load next period's MarketSnapshot
```

### 14.2 State Variables Modified Per Step

| Step | Variable | Change |
|------|----------|--------|
| 28 | loan_balance | +loan_draw_amount |
| 28 | cash_balance | +loan_draw_amount |
| 30 | portfolio_value | -portfolio_sold |
| 30 | cash_balance | -cash_consumed |
| 32 | loan_balance | -repayment |
| 60 | portfolio_value | ×(1 + return) |
| 65 | loan_balance | +interest |
| 66 | portfolio_value | -liquidation (if LTV breach) |

### 14.3 Invariants

1. **Cash conservation**: Total spending = portfolio_withdrawal + loan_draw - repayment
2. **LTV constraint**: After step 66, ltv <= 0.50 (if enforcement enabled)
3. **No negative balances**: loan_balance >= 0, cash_balance >= 0, portfolio_value >= 0
4. **Repayment only when loan exists**: Repayment only occurs if loan_balance > 0
5. **Interest accrues after repayment**: Interest is calculated on post-repayment loan_balance

---

## 15. Authorization Boundary

```text
S6 PLANNING (current — REVISED)
    │
    ├── FFR investigation          ← must complete before S6.1
    ├── Semantic resolution (§10)   ← must complete before S6.1
    └── Architecture freeze         ← after semantic resolution
         │
         ▼
S6.P COMPLETE — SEMANTICS CLOSED
         │
         ▼
S6.1 Core Part 52 Execution        ← requires explicit authorization
         │
         ▼
S6.2 FFR Integration               ← requires explicit authorization
         │
         ▼
S6.3 Canonical Replication         ← requires explicit authorization
         │
         ▼
S6.4 Optimization/Solver           ← requires separate authorization
         │
         ▼
S6 COMPLETE
```

**Do not begin S6.1 implementation without explicit authorization.**
S6 planning is not complete until all §10 open questions are resolved.

---

## 13. Conclusion

### S6.P Status: COMPLETE

All semantic/data questions have been resolved:

| # | Question | Status | Resolution |
|---|----------|--------|------------|
| 1 | FFR source, coverage, transformation | **RESOLVED** | §10.1 |
| 2 | Repayment trigger: index or portfolio ATH? | **RESOLVED** | §10.2 |
| 3 | Repayment mechanism | **RESOLVED** | §10.3 |
| 4 | Borrow% budget base | **RESOLVED** | §10.4 |
| 5 | Repayment timing | **RESOLVED** | §10.5 |
| 6 | LTV evaluation timing | **RESOLVED** | §10.6 |
| 7 | Interest rate timing | **RESOLVED** | §10.7 |
| 8 | Failure semantics under repayment | **RESOLVED** | §10.8 |

### Key Findings

1. **FFR dataset**: FRED FEDFUNDS (1954+), FRED category 33951 (1928-1954),
   call money rate proxy (pre-1928). Provenance documented in §10.1.

2. **Drawdown and repayment triggers are both index-level.** Uses existing
   `MarketSnapshot.is_ath`, `running_ath`, and `index_levels`. No new
   state variables needed.

3. **Repayment mechanism**: Dedicated `LoanRepaymentStep` at sequence_order
   32. Double withdrawal, excess repays loan. Edge cases documented in §10.3.

4. **Borrow% budget base**: `initial_wealth × withdrawal_rate / 12`.
   Confirmed from ERN article. See §10.4.

5. **All timing semantics resolved**: Repayment in same period as ATH
   detection (§10.5). LTV evaluated at end-of-period after interest
   accrual (§10.6). Interest accrues using current period's FFR (§10.7).

6. **Solver scope classified**: Execution/replication (S6.1–S6.3) does
   not require a solver. Optimization reproduction (S6.4) is separate.

### Revised Implementation Sequence

```
S6.P  Semantic/data closure — COMPLETE
  ↓
S6.1  Core execution (policy, repayment, bug fix, fixed-rate fixtures)
  ↓
S6.2  FFR integration (dataset, time-varying rates)
  ↓
S6.3  Canonical replication (full grid, validation)
  ↓
S6.4  Optimization/solver (conditional, separate authorization)
```

### Recommended Next Step

**S6.1 — Core Part 52 Execution.** All semantic questions are resolved.
The architecture is frozen. Implementation may proceed with explicit
authorization.
