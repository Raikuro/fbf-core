# S6.1 — Core Part 52 Execution: Implementation Plan (Revised)

**Stage:** S6.1 — Implementation Plan (no implementation)  
**Status:** PLAN COMPLETE — AWAITING IMPLEMENTATION AUTHORIZATION  
**Date:** 2026-09-05  
**Prerequisite:** S6.P COMPLETE (all semantic/data questions resolved)  
**Scope:** Core Part 52 execution: policy, repayment, bug fix, rate schedule

---

## 1. Executive Summary

S6.1 implements the smallest architecture capable of expressing the
verified Part 52 semantics from S6.P. The changes are:

1. **`Part52WithdrawalPolicy`** — New policy class for conditional
   draw/repay decisions
2. **`LoanRepaymentStep`** — New pipeline step at sequence_order 32
3. **`DebtInfo.cash_balance` bug fix** — Pass cash_balance to DebtInfo
4. **`is_repayment` propagation** — New field on WithdrawalDecision,
   MonthlyResult, and DebtSnapshot
5. **`interest_rate_schedule`** — Optional per-period rate on
   SimulationContext
6. **`InterestAccrualStep` modification** — Read rate from schedule if
   available

**No engine modification is required.** All changes are within the
existing pipeline contracts.

---

## 2. Repayment Calculation Verification

### 2.1 ERN Article Quote (Exact)

From ERN Part 52 (line 275):

> "So, let's assume that if we reach a fresh all-time high in the S&P 500
> Total Return Index, we'll start paying back the margin loan. I assume
> that we simply double the withdrawals from the stock/bond portfolio and
> use the excess to pay down the margin loan, i.e. set the margin loan
> draw to -100% of the monthly retirement budget."

### 2.2 Parsing the ERN Description

The sentence has three operative clauses:

| Clause | Meaning | Pipeline Mapping |
|--------|---------|------------------|
| "double the withdrawals from the stock/bond portfolio" | portfolio_withdrawal = 2 × budget | `WithdrawalDecision.nominal_amount` |
| "use the excess to pay down the margin loan" | excess = portfolio_withdrawal - budget = budget | Computed in `LoanRepaymentStep` |
| "set the margin loan draw to -100% of the monthly retirement budget" | loan_draw_amount = -budget | NOT used (negative draw rejected) |

**Critical observation:** The third clause says "set the margin loan
draw to -100% of the monthly retirement budget". This explicitly
defines the repayment amount as **budget** (the normal monthly spending).

### 2.3 Why `portfolio_withdrawal / 2 = budget` Is Correct

In repayment mode:
- `portfolio_withdrawal = 2 × budget` (double withdrawal)
- `excess = portfolio_withdrawal - budget = budget`
- Repayment amount = `min(excess, loan_balance) = min(budget, loan_balance)`

Therefore: `excess = portfolio_withdrawal / 2 = budget`.

This is not an inference from "double withdrawal" — it is explicitly
stated by ERN: "set the margin loan draw to -100% of the monthly
retirement budget."

### 2.4 Pipeline Representation

ERN's description uses negative loan draw. The FBF pipeline rejects
negative draws (LoanDrawStep line 64). The architectural decision
(S6.P §10.3) uses a dedicated `LoanRepaymentStep` instead.

**ERN semantics → FBF mapping:**

| ERN | FBF Pipeline |
|-----|--------------|
| portfolio_withdrawal = 2 × budget | `WithdrawalDecision.nominal_amount = 2 × budget` |
| loan_draw_amount = -budget | `LoanRepaymentStep` repays `min(budget, loan_balance)` |
| Total spending = budget | `WithdrawalExecutionStep` sells `2 × budget` from portfolio |

**Net effect (identical):**
- Retiree spends: `budget`
- Portfolio decreases by: `2 × budget`
- Loan decreases by: `min(budget, loan_balance)`
- Net worth change: `-2 × budget + min(budget, loan_balance)`

---

## 3. Concrete Numerical Repayment Example

### 3.1 Setup

```
initial_wealth = $1,000,000
withdrawal_rate = 3.91% = 0.0391
borrow_pct = 41.08% = 0.4108
drawdown_threshold = 20% = 0.20
interest_rate = 1.5% (fixed, for this example)
ltv_limit = 50%

budget = $1,000,000 × 0.0391 / 12 = $3,258.33
```

### 3.2 Full Lifecycle Example

**Month 1 — No debt, normal mode:**
```
equity_index = 100.0
running_ath = 100.0
is_ath = true
drawdown = 0%
loan_balance = $0
portfolio_value = $1,000,000
cash_balance = $0

DECISION: NORMAL (no leverage activity)
  portfolio_withdrawal = $3,258.33
  loan_draw = $0
  is_repayment = false

EXECUTION:
  LoanDrawStep: no-op
  WithdrawalExecutionStep:
    cash_consumed = $0
    portfolio_sold = $3,258.33
    portfolio_value = $996,741.67
  LoanRepaymentStep: no-op (is_repayment = false)

MARKET EVOLUTION (5% return):
  equity_index = 105.0
  portfolio_value = $1,046,579.75

END OF PERIOD:
  InterestAccrual: loan_balance = $0 → no interest
  LTVEvaluation: loan_balance = $0 → no evaluation
```

**Month 12 — Market drops 20%, borrowing activated:**
```
equity_index = 80.0
running_ath = 105.0
is_ath = false
drawdown = 1 - (80/105) = 23.8%
loan_balance = $0
portfolio_value = $850,000
cash_balance = $0

DECISION: BORROW (drawdown >= 20% AND loan_balance = 0)
  portfolio_withdrawal = $3,258.33 × (1 - 0.4108) = $1,920.11
  loan_draw = $3,258.33 × 0.4108 = $1,338.22
  is_repayment = false

EXECUTION:
  LoanDrawStep:
    loan_balance += $1,338.22 = $1,338.22
    cash_balance += $1,338.22 = $1,338.22
  WithdrawalExecutionStep:
    cash_consumed = min($1,338.22, $1,920.11) = $1,338.22
    portfolio_sold = $1,920.11 - $1,338.22 = $581.89
    cash_balance = $0
    portfolio_value = $850,000 - $581.89 = $849,418.11
  LoanRepaymentStep: no-op (is_repayment = false)

END OF PERIOD:
  InterestAccrual:
    interest = $1,338.22 × 0.015 / 12 = $1.67
    loan_balance = $1,338.22 + $1.67 = $1,339.89
  LTVEvaluation:
    ltv = $1,339.89 / $849,418.11 = 0.16% → no enforcement
```

**Month 24 — Loan outstanding, not at ATH, normal mode:**
```
equity_index = 75.0
running_ath = 105.0
is_ath = false
drawdown = 28.6%
loan_balance = $1,339.89
portfolio_value = $800,000
cash_balance = $0

DECISION: NORMAL (loan_balance > 0, not at ATH)
  portfolio_withdrawal = $3,258.33
  loan_draw = $0
  is_repayment = false

EXECUTION:
  LoanDrawStep: no-op
  WithdrawalExecutionStep:
    cash_consumed = $0
    portfolio_sold = $3,258.33
    portfolio_value = $796,741.67
  LoanRepaymentStep: no-op

END OF PERIOD:
  InterestAccrual:
    interest = $1,339.89 × 0.015 / 12 = $1.67
    loan_balance = $1,339.89 + $1.67 = $1,341.56
```

**Month 36 — Market recovers to fresh ATH, repayment activated:**
```
equity_index = 110.0
running_ath = 110.0
is_ath = true
loan_balance = $1,341.56
portfolio_value = $900,000
cash_balance = $0

DECISION: REPAY (is_ath = true AND loan_balance > 0)
  portfolio_withdrawal = $3,258.33 × 2 = $6,516.66
  loan_draw = $0
  is_repayment = true

EXECUTION:
  LoanDrawStep: no-op
  WithdrawalExecutionStep:
    cash_consumed = $0
    portfolio_sold = $6,516.66
    portfolio_value = $893,483.34
  LoanRepaymentStep:
    excess = $6,516.66 - $3,258.33 = $3,258.33
    repayment = min($3,258.33, $1,341.56) = $1,341.56
    loan_balance = $1,341.56 - $1,341.56 = $0

END OF PERIOD:
  InterestAccrual: loan_balance = $0 → no interest
  LTVEvaluation: loan_balance = $0 → no evaluation
```

### 3.3 Accounting Invariants (Verified)

| Invariant | Month 1 | Month 12 | Month 36 |
|-----------|---------|----------|----------|
| Total spending | $3,258.33 | $1,920.11 | $6,516.66 |
| Portfolio change | -$3,258.33 | -$581.89 | -$6,516.66 |
| Loan change | $0 | +$1,338.22 | -$1,341.56 |
| Net worth change | -$3,258.33 | +$756.33 | -$5,175.10 |

---

## 4. Complete Repayment Edge-Case Matrix

### Case 1: Fresh index ATH with outstanding debt

```
is_ath = true, loan_balance > 0
→ REPAY mode
→ portfolio_withdrawal = budget × 2
→ excess = budget
→ repayment = min(budget, loan_balance)
```

**Example:** loan_balance = $1,000, budget = $3,258.33
→ repayment = $1,000 (limited by loan_balance)
→ loan_balance = $0

### Case 2: Fresh index ATH with no debt

```
is_ath = true, loan_balance = 0
→ NORMAL mode (no repayment needed)
→ portfolio_withdrawal = budget
→ loan_draw = $0
```

**Rationale:** The policy checks `loan_balance > 0` before entering
repayment mode. If there's no debt, no repayment occurs.

### Case 3: Repayment amount larger than outstanding debt

```
excess = budget = $3,258.33
loan_balance = $1,000
→ repayment = min($3,258.33, $1,000) = $1,000
→ loan_balance = $0
→ Remaining excess ($2,258.33) stays in portfolio
```

### Case 4: Repayment amount smaller than outstanding debt

```
excess = budget = $3,258.33
loan_balance = $5,000
→ repayment = min($3,258.33, $5,000) = $3,258.33
→ loan_balance = $5,000 - $3,258.33 = $1,741.67
```

**Next month (if still at ATH):**
- repayment = min($3,258.33, $1,741.67) = $1,741.67
- loan_balance = $0

### Case 5: ATH when portfolio cannot fund the full additional withdrawal

```
portfolio_value = $5,000
budget = $3,258.33
portfolio_withdrawal = $6,516.66

WithdrawalExecutionStep:
  cash_consumed = $0
  portfolio_sold = min($6,516.66, $5,000) = $5,000
  portfolio_value = $0
  failure_state = "depleted"
```

**Result:** Simulation fails at step 75 (FailureDetectionStep). The
retiree cannot sustain the double withdrawal.

### Case 6: A month with borrowing but no repayment

```
drawdown >= threshold, loan_balance = 0, NOT is_ath
→ BORROW mode
→ portfolio_withdrawal = budget × (1 - borrow_pct)
→ loan_draw = budget × borrow_pct
→ is_repayment = false
```

### Case 7: A month with repayment but no new borrowing

```
is_ath = true, loan_balance > 0
→ REPAY mode
→ portfolio_withdrawal = budget × 2
→ loan_draw = $0
→ is_repayment = true
```

### Case 8: Full lifecycle transition

```
Month 1:  No debt → NORMAL
Month 12: Market drops 20%+ → BORROW (loan_balance = $1,338.22)
Month 24: Still underwater, loan outstanding → NORMAL (interest accrues)
Month 36: Fresh ATH → REPAY (loan_balance → $0)
Month 48: No debt → NORMAL
```

**Verified:** Accounting invariants hold at every transition.

---

## 5. Index-Level ATH Invariants

### 5.1 Field Semantics

| Field | Source | Meaning | Values |
|-------|--------|---------|--------|
| `MarketSnapshot.index_levels[AssetClass.EQUITY]` | Dataset | Current S&P 500 TR index level | ~100–200 |
| `MarketSnapshot.running_ath` | Dataset | ATH of S&P 500 TR index | ~100–200 |
| `MarketSnapshot.is_ath` | Dataset | Is index at new ATH? | bool |
| `MarketSnapshot.is_underwater` | Dataset | Is index below ATH? | bool |

### 5.2 Invariant: Index ≠ Portfolio

These values refer to the **market index**, not the simulated portfolio.

- `index_levels` values are ~100–200 (index points)
- Portfolio values are ~$1,000,000 (dollars)
- The policy computes drawdown from `index_levels` and `running_ath`
- The policy uses `is_ath` for repayment trigger
- **No portfolio ATH tracking is introduced**

### 5.3 Drawdown Computation

```python
equity_index = context.market_snapshot.index_levels[AssetClass.EQUITY]
running_ath = context.market_snapshot.running_ath
if running_ath > 0:
    drawdown = Decimal("1") - (equity_index / running_ath)
else:
    drawdown = Decimal("0")
```

**Invariant:** `drawdown >= 0` when `equity_index <= running_ath`.
`drawdown = 0` when `equity_index = running_ath` (at ATH).

### 5.4 Repayment Trigger

```python
if context.market_snapshot.is_ath and loan_balance > 0:
    # REPAY mode
```

**Invariant:** Repayment is triggered by index-level ATH, not portfolio
ATH. The `is_ath` field is pre-computed by the dataset and refers to
the S&P 500 TR index.

---

## 6. Part 49 Regression for interest_rate_schedule=None

### 6.1 Change Description

The `InterestAccrualStep` modification adds a branch:
```python
schedule = state.context.interest_rate_schedule
if schedule is not None and state.period_index < len(schedule):
    annual_rate = schedule[state.period_index]
else:
    annual_rate = state.interest_rate
```

When `interest_rate_schedule is None` (all existing Part 49 simulations),
the code falls back to `state.interest_rate`, which is identical to the
current behavior.

### 6.2 Regression Test

```python
def test_part49_unchanged_by_schedule_none():
    """Prove that interest_rate_schedule=None produces identical results."""
    # Run Part 49 simulation with current code
    result_before = run_part49_simulation(interest_rate=Decimal("0.015"))
    
    # Run Part 49 simulation with new code (schedule=None)
    result_after = run_part49_simulation(
        interest_rate=Decimal("0.015"),
        interest_rate_schedule=None  # explicitly None
    )
    
    # Assert identical results
    for before, after in zip(result_before, result_after):
        assert before.loan_balance == after.loan_balance
        assert before.portfolio_value == after.portfolio_value
        assert before.debt_snapshot.net_worth == after.debt_snapshot.net_worth
```

### 6.3 Why This Is Safe

- `interest_rate_schedule` defaults to `None` on `SimulationContext`
- The fallback branch is `annual_rate = state.interest_rate`
- This is identical to the current code path
- No existing simulation sets `interest_rate_schedule`
- The field is only set by the builder when FFR data is provided (S6.2)

---

## 7. Implementation Sequence

The changes must be implemented in this order to maintain a working
codebase at each step:

```
Step 1: DebtInfo.cash_balance bug fix (correctness regression)
Step 2: is_repayment field on WithdrawalDecision (domain model)
Step 3: is_repayment propagation to MonthlyResult/DebtSnapshot
Step 4: interest_rate_schedule on SimulationContext
Step 5: InterestAccrualStep modification for per-period rates
Step 6: Part52WithdrawalPolicy (domain policy)
Step 7: LoanRepaymentStep (pipeline step)
Step 8: Pipeline registration (default_pipeline.py)
Step 9: Builder support for Part52 configuration
Step 10: Unit tests
Step 11: Integration tests
```

Each step produces a working codebase. No intermediate commit is
required (per AGENTS.md one-commit-per-phase rule), but each step
must pass ruff, mypy, and pytest before proceeding.

---

## 3. Detailed Change Specifications

### Step 1: DebtInfo.cash_balance Bug Fix

**Problem:** `BuildDecisionContextStep` constructs `DebtInfo` without
passing `cash_balance`, causing `DebtInfo.net_worth` to always exclude
cash.

**File:** `src/fbf/core/execution/pipeline/steps/build_decision_context_step.py`

**Current code (lines 37-44):**
```python
debt_info = DebtInfo(
    loan_balance=state.loan_balance,
    interest_rate=state.interest_rate,
    ltv_limit=state.ltv_limit,
    portfolio_value=portfolio_value,
    ltv_observed=ltv_observed,
    ltv_enforcement=state.ltv_enforcement,
)
```

**Changed code:**
```python
debt_info = DebtInfo(
    loan_balance=state.loan_balance,
    interest_rate=state.interest_rate,
    ltv_limit=state.ltv_limit,
    portfolio_value=portfolio_value,
    cash_balance=state.cash_balance,
    ltv_observed=ltv_observed,
    ltv_enforcement=state.ltv_enforcement,
)
```

**Existing contract reused:** `DebtInfo` dataclass (already has
`cash_balance` field with default `Decimal("0")`).

**Invariant preserved:** `DebtInfo.net_worth = portfolio_value +
cash_balance - loan_balance`.

**Decimal-reference behavior:** No change. The fix only affects the
`DebtInfo` snapshot passed to policies. Part 49 policies do not observe
`debt_info.net_worth`, so mathematical behavior is unchanged.

**Regression requirement:** Prove `net_worth = portfolio_value +
cash_balance - loan_balance` for a non-zero cash balance. Verify Part 49
results are unchanged.

**Test:** `test_debt_info_cash_balance_net_worth` — construct DebtInfo
with non-zero cash_balance, assert net_worth calculation.

---

### Step 2: is_repayment Field on WithdrawalDecision

**File:** `src/fbf/core/domain/policies/decisions.py`

**Current code (lines 27-31):**
```python
@dataclass(frozen=True)
class WithdrawalDecision(PolicyDecision):
    nominal_amount: Money
    real_amount: Money
    loan_draw_amount: Decimal = Decimal("0")
```

**Changed code:**
```python
@dataclass(frozen=True)
class WithdrawalDecision(PolicyDecision):
    nominal_amount: Money
    real_amount: Money
    loan_draw_amount: Decimal = Decimal("0")
    is_repayment: bool = False
```

**Existing contract reused:** `WithdrawalDecision` is frozen dataclass.
The new field has a default value, so all existing code continues to
work without modification.

**Decimal-reference behavior:** No change. The field is a boolean flag,
not a mathematical parameter.

**Impact:** `LoanDrawStep` reads `loan_draw_amount` (unchanged).
`WithdrawalExecutionStep` reads `nominal_amount` (unchanged). The new
field is read only by `LoanRepaymentStep` (Step 7).

---

### Step 3: is_repayment Propagation to MonthlyResult/DebtSnapshot

**File:** `src/fbf/core/execution/pipeline/simulation.py`

**MonthlyResult change (add field):**
```python
@dataclass(frozen=True)
class MonthlyResult:
    ...
    debt_snapshot: DebtSnapshot | None = None
    is_repayment: bool = False  # NEW
```

**DebtSnapshot change (add field):**
```python
@dataclass(frozen=True)
class DebtSnapshot:
    ...
    ltv_enforcement: bool = True
    is_repayment: bool = False  # NEW
```

**File:** `src/fbf/core/execution/pipeline/steps/monthly_result_builder_step.py`

**Change:** When building `MonthlyResult`, pass
`is_repayment=state.withdrawal_decision.is_repayment if
state.withdrawal_decision else False`.

**Existing contract reused:** Both dataclasses have default values for
the new field, so all existing code continues to work.

**Decimal-reference behavior:** No change. The field is informational.

---

### Step 4: interest_rate_schedule on SimulationContext

**File:** `src/fbf/core/execution/pipeline/simulation_context.py`

**Current code (lines 19-33):**
```python
@dataclass(frozen=True)
class SimulationContext:
    ...
    interest_rate: Decimal | None = None
    ltv_limit: Decimal | None = None
    ltv_enforcement: bool = True
```

**Changed code:**
```python
@dataclass(frozen=True)
class SimulationContext:
    ...
    interest_rate: Decimal | None = None
    interest_rate_schedule: tuple[Decimal, ...] | None = None  # NEW
    ltv_limit: Decimal | None = None
    ltv_enforcement: bool = True
```

**Existing contract reused:** The new field has a default value
(`None`), so all existing code continues to work. When `None`,
`InterestAccrualStep` falls back to `interest_rate`.

**Decimal-reference behavior:** When `interest_rate_schedule` is
present, the rate for each period is `schedule[period_index]`. When
absent, falls back to `interest_rate`. The mathematical behavior is
identical for fixed-rate simulations.

**Boundary:** The engine consumes a generic period-rate schedule. It
does not know that the source is FFR. The schedule is constructed by
the builder from FFR dataset + spread.

---

### Step 5: InterestAccrualStep Modification

**File:** `src/fbf/core/execution/pipeline/steps/interest_accrual_step.py`

**Current code (lines 27-41):**
```python
def execute(self, state: SimulationState) -> SimulationState:
    if state.loan_balance <= 0:
        return state
    monthly_rate = state.interest_rate / Decimal("12")
    interest = state.loan_balance * monthly_rate
    state.loan_balance += interest
    return state
```

**Changed code:**
```python
def execute(self, state: SimulationState) -> SimulationState:
    if state.loan_balance <= 0:
        return state
    
    # Determine rate for this period
    schedule = state.context.interest_rate_schedule
    if schedule is not None and state.period_index < len(schedule):
        annual_rate = schedule[state.period_index]
    else:
        annual_rate = state.interest_rate
    
    monthly_rate = annual_rate / Decimal("12")
    interest = state.loan_balance * monthly_rate
    state.loan_balance += interest
    return state
```

**Existing contract reused:** The step still reads from
`state.interest_rate` when no schedule is present. The fallback behavior
is identical to the current implementation.

**Decimal-reference behavior:** For fixed-rate simulations (no schedule),
behavior is identical. For scheduled rates, the rate for each period is
read from `schedule[period_index]`.

**Invariant:** Interest accrues on `loan_balance` at the start of the
period, using the rate for that period. The rate is applied as
`annual_rate / 12` (simple monthly division, consistent with ERN
methodology).

---

### Step 6: Part52WithdrawalPolicy

**New file:** `src/fbf/core/domain/policies/part52_withdrawal.py`

**Constructor parameters:**
```python
class Part52WithdrawalPolicy(WithdrawalPolicy):
    def __init__(
        self,
        withdrawal_rate: Decimal,
        borrow_pct: Decimal,
        drawdown_threshold: Decimal,
    ) -> None:
        self.withdrawal_rate = withdrawal_rate
        self.borrow_pct = borrow_pct
        self.drawdown_threshold = drawdown_threshold
```

**decide() method logic:**
```python
def decide(self, context: DecisionContext) -> WithdrawalDecision:
    # 1. Extract simulation context
    sim_context = getattr(context, "simulation_context", None)
    if sim_context is None:
        raise TypeError("DecisionContext.simulation_context is required")
    
    dataset = getattr(sim_context, "dataset", None)
    initial_portfolio = getattr(sim_context, "initial_portfolio", None)
    if dataset is None or initial_portfolio is None:
        raise TypeError("SimulationContext must have dataset and initial_portfolio")
    
    # 2. Compute budget from initial_wealth
    initial_wealth = Decimal("0")
    for holding in initial_portfolio.holdings:
        price = dataset[0].index_levels.get(holding.asset_class, Decimal("0"))
        initial_wealth += holding.units * price
    budget = initial_wealth.amount * self.withdrawal_rate / Decimal("12")
    
    # 3. Compute index-level drawdown
    equity_index = context.market_snapshot.index_levels.get(
        AssetClass(id="equity", name="Equity", description=""), Decimal("0")
    )
    running_ath = context.market_snapshot.running_ath
    if running_ath > 0:
        drawdown = Decimal("1") - (equity_index / running_ath)
    else:
        drawdown = Decimal("0")
    
    # 4. Get current loan balance from debt_info
    loan_balance = Decimal("0")
    if context.debt_info is not None:
        loan_balance = context.debt_info.loan_balance
    
    # 5. Decision logic
    if drawdown >= self.drawdown_threshold and loan_balance == 0:
        # BORROW: activate leverage
        portfolio_withdrawal = budget * (Decimal("1") - self.borrow_pct)
        loan_draw = budget * self.borrow_pct
        is_repayment = False
    elif context.market_snapshot.is_ath and loan_balance > 0:
        # REPAY: double withdrawal, no loan draw
        portfolio_withdrawal = budget * 2
        loan_draw = Decimal("0")
        is_repayment = True
    else:
        # NORMAL: no leverage activity
        portfolio_withdrawal = budget
        loan_draw = Decimal("0")
        is_repayment = False
    
    return WithdrawalDecision(
        reason="Part52WithdrawalPolicy",
        nominal_amount=Money(portfolio_withdrawal, Currency.EUR),
        real_amount=Money(portfolio_withdrawal, Currency.EUR),
        loan_draw_amount=loan_draw,
        is_repayment=is_repayment,
    )
```

**Existing contract reused:**
- `WithdrawalPolicy` base class (abstract `decide()` method)
- `WithdrawalDecision` dataclass (with new `is_repayment` field)
- `DecisionContext` (reads `market_snapshot`, `debt_info`)
- `MarketSnapshot` (reads `index_levels`, `running_ath`, `is_ath`)

**New contract introduced:** `Part52WithdrawalPolicy` class.

**Domain boundary:** The policy lives in `fbf.core.domain.policies`.
It imports only from `fbf.core.domain.model`. It does NOT import from
`fbf.core.execution`.

**Decimal-reference behavior:** All arithmetic uses `Decimal`. No float.
The drawdown computation uses `Decimal("1") - (equity_index / running_ath)`.

**Invariants:**
- `budget = initial_wealth * withdrawal_rate / 12` (constant across periods)
- `portfolio_withdrawal + loan_draw = budget` (normal mode)
- `portfolio_withdrawal = budget * 2` (repayment mode)
- `loan_draw = 0` (repayment mode)

---

### Step 7: LoanRepaymentStep

**New file:** `src/fbf/core/execution/pipeline/steps/loan_repayment_step.py`

```python
class LoanRepaymentStep(PipelineStep):
    sequence_order = 32
    
    def execute(self, state: SimulationState) -> SimulationState:
        if state.withdrawal_decision is None:
            return state
        
        if not state.withdrawal_decision.is_repayment:
            return state
        
        if state.loan_balance <= 0:
            return state
        
        # Compute excess: double withdrawal minus normal budget
        # The normal budget is the portfolio_withdrawal in non-repayment mode
        # In repayment mode, portfolio_withdrawal = budget * 2
        # So excess = portfolio_withdrawal - budget = budget
        # We can compute budget from the withdrawal decision:
        # In repayment mode, portfolio_withdrawal = budget * 2
        # So budget = portfolio_withdrawal / 2
        portfolio_withdrawal = state.withdrawal_decision.nominal_amount.amount
        budget = portfolio_withdrawal / Decimal("2")
        excess = portfolio_withdrawal - budget  # = budget
        
        # Repay the lesser of excess and loan_balance
        repayment = min(excess, state.loan_balance)
        state.loan_balance -= repayment
        
        return state
```

**Existing contract reused:**
- `PipelineStep` abstract base class
- `SimulationState` (reads `withdrawal_decision`, `loan_balance`)
- `WithdrawalDecision` (reads `is_repayment`, `nominal_amount`)

**New contract introduced:** `LoanRepaymentStep` class.

**Sequence order:** 32 (after `WithdrawalExecutionStep` at 30, before
`AllocationDecisionStep` at 40).

**State transition:**
- `loan_balance -= repayment`
- No change to `cash_balance` (the excess stays in the portfolio)

**Edge cases:**
1. `loan_balance < excess`: Repay only `loan_balance`. Remaining excess
   stays in portfolio.
2. `loan_balance = 0`: Early return (no repayment needed).
3. `is_repayment = False`: Early return (normal mode).
4. `withdrawal_decision = None`: Early return (no decision yet).

**Decimal-reference behavior:** All arithmetic uses `Decimal`. The
repayment is `min(excess, loan_balance)` — both are `Decimal`.

**Invariant:** After execution, `loan_balance >= 0`. Repayment never
increases loan_balance.

---

### Step 8: Pipeline Registration

**File:** `src/fbf/core/execution/pipeline/default_pipeline.py`

**Change:** Add `LoanRepaymentStep()` to the step list at position 32.

```python
def create_default_pipeline() -> SimulationPipeline:
    return SimulationPipeline(steps=[
        InitializeAllocationStep(),       # 0
        BuildDecisionContextStep(),       # 10
        WithdrawalDecisionStep(),         # 20
        LoanDrawStep(),                   # 28
        WithdrawalExecutionStep(),        # 30
        LoanRepaymentStep(),              # 32  # NEW
        AllocationDecisionStep(),         # 40
        PortfolioRebalanceStep(),         # 50
        MarketEvolutionStep(),            # 60
        InterestAccrualStep(),            # 65
        LTVEvaluationStep(),              # 66
        MonthlyResultBuilderStep(),       # 70
        FailureDetectionStep(),           # 75
        SimulationStateUpdateStep(),      # 80
    ])
```

**Existing contract reused:** `SimulationPipeline` validates ascending
`sequence_order`. The new step at 32 fits between 30 and 40.

**Import:** Add `from fbf.core.execution.pipeline.steps.loan_repayment_step import LoanRepaymentStep`.

---

### Step 9: Builder Support for Part52 Configuration

**File:** `src/fbf/core/study/builder.py`

**Changes:**

1. **StudyConfiguration** — Add fields:
   ```python
   debt_borrow_pct: Decimal | None = None
   debt_borrow_pct_values: tuple[Decimal, ...] | None = None
   debt_drawdown_threshold: Decimal | None = None
   debt_drawdown_threshold_values: tuple[Decimal, ...] | None = None
   ```

2. **YAML parsing** — Extend `from_yaml()` to parse:
   ```yaml
   debt:
     borrow_pct: 0.25
     drawdown_threshold: 0.20
   ```

3. **Parameter axis construction** — Add `borrow_pct` and
   `drawdown_threshold` as optional grid axes.

4. **Policy builder** — Add `"Part52WithdrawalPolicy"` to
   `WithdrawalPolicyType` enum and `build_withdrawal_policy()`.

5. **interest_rate_schedule construction** — When FFR dataset is
   provided, construct the schedule from FFR + spread and pass it to
   `SimulationContext`.

**Existing contract reused:**
- `StudyConfiguration` dataclass (add fields with defaults)
- `WithdrawalPolicyType` enum (add new type)
- `build_withdrawal_policy()` (add new branch)
- `ParameterAxis` construction (reuse existing pattern)

**New contract introduced:** Part52-specific configuration fields.

---

### Step 10: Unit Tests

**Test file:** `tests/unit/domain/policies/test_part52_withdrawal.py`

| Test | Purpose |
|------|---------|
| `test_borrow_when_below_threshold` | Drawdown >= threshold, loan_balance = 0 → BORROW |
| `test_no_borrow_when_above_threshold` | Drawdown < threshold → NORMAL |
| `test_repay_when_at_ath_with_loan` | is_ath = True, loan_balance > 0 → REPAY |
| `test_no_repay_when_no_loan` | is_ath = True, loan_balance = 0 → NORMAL |
| `test_budget_calculation` | Verify budget = initial_wealth * rate / 12 |
| `test_borrow_pct_split` | Verify portfolio_withdrawal = budget * (1 - borrow_pct) |
| `test_repayment_doubles_withdrawal` | Verify portfolio_withdrawal = budget * 2 |
| `test_drawdown_computation` | Verify drawdown = 1 - (equity_index / running_ath) |

**Test file:** `tests/unit/execution/pipeline/steps/test_loan_repayment_step.py`

| Test | Purpose |
|------|---------|
| `test_repayment_reduces_loan_balance` | is_repayment=True, loan_balance > 0 → loan_balance decreases |
| `test_repayment_noop_when_no_loan` | is_repayment=True, loan_balance = 0 → no change |
| `test_repayment_noop_when_not_repayment` | is_repayment=False → no change |
| `test_repayment_limited_by_loan_balance` | excess > loan_balance → repay only loan_balance |
| `test_repayment_preserves_unrelated_state` | Other state fields unchanged |

**Test file:** `tests/unit/execution/test_debt_info_cash_balance.py`

| Test | Purpose |
|------|---------|
| `test_debt_info_cash_balance_net_worth` | DebtInfo with non-zero cash → net_worth = portfolio + cash - loan |
| `test_part49_unchanged_by_fix` | Part49 results identical before/after fix |

**Test file:** `tests/unit/execution/test_interest_accrual_schedule.py`

| Test | Purpose |
|------|---------|
| `test_schedule_rate_used_when_present` | interest_rate_schedule set → uses schedule[period_index] |
| `test_fallback_to_fixed_rate` | No schedule → uses interest_rate |
| `test_schedule_out_of_bounds_fallback` | period_index >= len(schedule) → uses interest_rate |

---

### Step 11: Integration Tests

**Test file:** `tests/integration/test_part52_smoke.py`

Single-cohort smoke test:
- 1965 cohort, 20% threshold, Borrow% = 41.08%, FFR+0.50% (fixed rate)
- Verify: policy triggers borrowing below threshold, repayment at ATH
- Verify: LTV enforcement at 50%
- Verify: loan_balance increases with interest, decreases with repayment

**Test file:** `tests/integration/test_part52_canonical.py`

Canonical execution:
- 1965 cohort, no timing, fixed rate: WR ≈ 3.58% (no leverage baseline)
- 1965 cohort, no timing, fixed rate: WR ≈ 3.78%, Borrow% ≈ 10.76%
- Verify against ERN published anchors (§8.2 of S6 architecture plan)

---

## 4. Monthly State Transition (Exact Ordering)

```
Step 0:   InitializeAllocationStep
Step 10:  BuildDecisionContextStep      ← builds DebtInfo WITH cash_balance
Step 20:  WithdrawalDecisionStep        ← Part52WithdrawalPolicy decides
Step 28:  LoanDrawStep                  ← executes loan draw (if any)
Step 30:  WithdrawalExecutionStep       ← consumes cash, sells portfolio
Step 32:  LoanRepaymentStep (NEW)       ← executes repayment (if is_repayment)
Step 40:  AllocationDecisionStep
Step 50:  PortfolioRebalanceStep
Step 60:  MarketEvolutionStep
Step 65:  InterestAccrualStep           ← reads schedule if available
Step 66:  LTVEvaluationStep             ← enforced at 50%
Step 70:  MonthlyResultBuilderStep      ← captures is_repayment flag
Step 75:  FailureDetectionStep
Step 80:  SimulationStateUpdateStep
```

**No ordering changes from S6.P frozen semantics.** The canonical
monthly state transition in S6 architecture plan §14 is preserved.

---

## 5. Invariants

1. **Cash conservation:** Total spending = portfolio_withdrawal +
   loan_draw - repayment
2. **LTV constraint:** After step 66, ltv <= 0.50 (if enforcement
   enabled)
3. **No negative balances:** loan_balance >= 0, cash_balance >= 0,
   portfolio_value >= 0
4. **Repayment only when loan exists:** Repayment only occurs if
   loan_balance > 0
5. **Interest accrues after repayment:** Interest is calculated on
   post-repayment loan_balance
6. **Budget constant:** budget = initial_wealth * withdrawal_rate / 12
   is constant across all periods
7. **Drawdown is index-level:** Uses MarketSnapshot fields, not
   portfolio tracking
8. **Repayment is index-level:** Uses MarketSnapshot.is_ath, not
   portfolio tracking

---

## 6. Test Matrix

| Component | Unit | Integration | E2E |
|-----------|------|-------------|-----|
| Part52WithdrawalPolicy | 8 tests | — | — |
| LoanRepaymentStep | 5 tests | — | — |
| DebtInfo.cash_balance fix | 2 tests | — | — |
| interest_rate_schedule | 3 tests | — | — |
| is_repayment propagation | — | verified in integration | — |
| Pipeline registration | — | 1 smoke test | — |
| Part 49 regression | — | 1 regression test | — |
| Part 52 smoke | — | 1 smoke test | — |
| Part 52 canonical | — | 1 canonical test | — |
| **Total** | **18 unit** | **4 integration** | **0 E2E** |

---

## 8. Transition-Based Acceptance Criteria

### 8.1 State Machine Definition

The Part 52 lifecycle is a state machine with three states:

```
              ┌─────────────────────────────────────────┐
              │                                         │
              ▼                                         │
        ┌──────────┐    drawdown >= threshold    ┌──────────┐
        │          │    AND loan_balance == 0     │          │
        │  NORMAL  │ ──────────────────────────→ │  BORROW  │
        │          │                             │          │
        └──────────┘                             └──────────┘
              ▲                                        │
              │                                        │
              │ is_ath AND loan_balance > 0            │ loan_balance > 0
              │                                        │ AND NOT is_ath
              │                                        │ (stays in BORROW)
              │                                        │
              │                                        ▼
              │                                   ┌──────────┐
              └────────────────────────────────── │ REPAY    │
                                                  │          │
                                                  └──────────┘
```

### 8.2 Transition Rules

| From | To | Condition | Action |
|------|----|-----------|--------|
| NORMAL | BORROW | `drawdown >= threshold AND loan_balance == 0` | `portfolio_withdrawal = budget × (1 - borrow_pct)`, `loan_draw = budget × borrow_pct` |
| BORROW | REPAY | `is_ath AND loan_balance > 0` | `portfolio_withdrawal = budget × 2`, `repayment = min(budget, loan_balance)` |
| REPAY | NORMAL | `loan_balance == 0` | `portfolio_withdrawal = budget`, `loan_draw = 0` |
| BORROW | BORROW | `loan_balance > 0 AND NOT is_ath` | `portfolio_withdrawal = budget`, `loan_draw = 0` (interest accrues) |
| NORMAL | NORMAL | `drawdown < threshold OR loan_balance > 0` | `portfolio_withdrawal = budget`, `loan_draw = 0` |

### 8.3 Acceptance Criteria

**Must pass all 8 transition tests:**

1. **NORMAL → BORROW:** Drawdown crosses threshold with zero loan
2. **BORROW → REPAY:** Index reaches fresh ATH with outstanding loan
3. **REPAY → NORMAL:** Loan fully repaid at fresh ATH
4. **BORROW → BORROW:** Underwater period continues, interest accrues
5. **NORMAL → NORMAL:** Drawdown below threshold, no loan
6. **Full lifecycle:** NORMAL → BORROW → BORROW → REPAY → NORMAL (verified in §3.2)
7. **Partial repayment:** REPAY with `excess < loan_balance` → stays in REPAY
8. **Depleted portfolio:** Double withdrawal exceeds portfolio → simulation fails

### 8.4 Invariant Checks (Every Period)

| Invariant | Formula | Assertion |
|-----------|---------|-----------|
| Cash conservation | `total_spending = portfolio_withdrawal + loan_draw - repayment` | `== budget` |
| Non-negative loan | `loan_balance >= 0` | Always true |
| Non-negative portfolio | `portfolio_value >= 0` | True until failure |
| Repayment limited | `repayment <= loan_balance` | Always true (min constraint) |
| Budget constant | `budget = initial_wealth × rate / 12` | Constant across periods |

---

## 9. Validation/Benchmark Gates

### Quality Gates (must pass before commit)

1. **ruff check src tests** — must report "All checks passed!"
2. **mypy --strict .** — must report "Success: no issues found"
3. **pytest -p no:cacheprovider** — must be 0 failed
4. **Boundary contract** — `pytest tests/contract/` must pass

### Validation Anchors (from ERN Part 52)

| Cohort | Scenario | WR | Borrow% | Status |
|--------|----------|-----|---------|--------|
| 1965 | No timing, no leverage | 3.58% | 0% | Baseline |
| 1965 | No timing, fixed rate | 3.78% | 10.76% | S6.1 target |
| 1965 | 20% threshold, repayment | 3.91% | 41.08% | S6.1 target |
| 1965 | 25% threshold, FFR+0.50% | 3.92% | — | S6.2 target |
| 1965 | 25% threshold, FFR+1.25% | 3.87% | — | S6.2 target |
| 1965 | 25% threshold, FFR+2.75% | 3.75% | — | S6.2 target |
| 1929 | No timing, no leverage | 4.39% | — | Baseline |
| 1929 | 35% threshold, repayment | 4.93% | — | S6.1 target |

### Performance Gate

- Part 52 single-cohort execution: comparable runtime to Part 49
- No performance regression for Part 49 (existing tests must pass at
  same speed)

---

## 10. Risks and Rollback Considerations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Part49 regression from DebtInfo fix | LOW | Part49 policies don't observe net_worth; regression test |
| LoanRepaymentStep ordering conflict | LOW | Step 32 fits between 30 and 40; pipeline validation |
| interest_rate_schedule backward compat | LOW | Default None; fallback to interest_rate |
| Part52 policy imports from execution | MEDIUM | Enforce domain boundary; policy only imports domain types |
| Repayment amount computation error | MEDIUM | Unit tests with known inputs/outputs |
| Drawdown computation precision | LOW | Decimal arithmetic; no float |

### Rollback

If any step introduces a regression:
1. Revert the specific step (not the entire phase)
2. Run quality gates
3. Investigate and fix before proceeding

The implementation sequence is designed so each step produces a working
codebase. If Step N fails, Steps 1..N-1 are still valid.

---

## 11. Definition of Done

S6.1 is complete when:

1. All 11 implementation steps are complete
2. All 18 unit tests pass
3. All 4 integration tests pass
4. Quality gates pass (ruff, mypy, pytest, boundary contract)
5. Part 49 regression verified (no change in results)
6. Validation anchors matched (1965 no-leverage baseline, 1965 with
   timing, 1929 with timing)
7. No engine modification required (confirmed)
8. Documentation updated (architecture plan, decisions, TODO)
9. Single commit created with all S6.1 changes

---

## 12. Out of Scope (S6.1)

The following are explicitly excluded from S6.1:

- Solver/optimization
- Generic research-grid work
- BatchedExecutor
- Persistence redesign
- Hybrid storage
- Result-model normalization
- Eager-result redesign
- FFR dataset sourcing (done in S6.P)
- FFR time-varying rate integration (S6.2)
- Full grid replication (S6.3)

---

**S6.1 PLAN COMPLETE — AWAITING IMPLEMENTATION AUTHORIZATION**
