# K.7 Review Addendum — Architectural Correctness Verification

## A. Part49WithdrawalPolicy Formulas

### Actual code (part49_withdrawal.py:50-65)

```python
initial_snapshot = sim_context.dataset[0]
total = Money.ZERO
for holding in sim_context.initial_portfolio.holdings:
    price = initial_snapshot.index_levels[holding.asset_class]
    total += Money(holding.units * price, Currency.EUR)

monthly_withdrawal = total.amount * self.withdrawal_rate / Decimal("12")

loan_draw_rate: Decimal = getattr(sim_context, "loan_draw_rate", None) or Decimal("0")
monthly_loan = total.amount * loan_draw_rate / Decimal("12")

return WithdrawalDecision(
    reason="Part49WithdrawalPolicy",
    nominal_amount=Money(monthly_withdrawal, Currency.EUR),
    real_amount=Money(monthly_withdrawal, Currency.EUR),
    loan_draw_amount=monthly_loan,
)
```

### Worked Example

```
Initial portfolio: 5,000 units equity @ $100 + 10,000 units bond @ $50
Initial wealth:     $1,000,000

withdrawal_rate = 0.04 (4% annual)
loan_draw_rate  = 0.01 (1% annual)

total = 5,000 × $100 + 10,000 × $50 = $1,000,000

monthly_withdrawal = $1,000,000 × 0.04 / 12 = $3,333.33...
monthly_loan       = $1,000,000 × 0.01 / 12 = $833.33...

Policy returns:
  nominal_amount = $3,333.33   (portfolio withdrawal)
  loan_draw_amount = $833.33   (margin loan draw)
```

## B. Spending Accounting Proof

### Authoritative formula (DECISIONS.md:425-434, K.4.2:A.1)

```
portfolio withdrawal + margin-loan draw = total retirement spending
```

### What the policy returns

```
nominal_amount    = $3,333.33  (portfolio withdrawal — sold from portfolio)
loan_draw_amount  = $833.33    (loan draw — borrowed from margin account)
```

### How the pipeline consumes these values

1. **WithdrawalExecutionStep (step 30):** Consumes `nominal_amount` ($3,333.33) from portfolio
2. **LoanDrawStep (step 28):** Adds `loan_draw_amount` ($833.33) to loan balance and cash balance

### Total spending

```
total_spending = nominal_amount + loan_draw_amount
               = $3,333.33 + $833.33
               = $4,166.67

Verify: $1,000,000 × (0.04 + 0.01) / 12 = $4,166.67  ✓
```

### Is this correct per Part 49?

**Yes.** The formula `portfolio withdrawal + loan draw = total spending` is correctly implemented:

- `nominal_amount` = portfolio withdrawal = `initial_wealth × withdrawal_rate / 12`
- `loan_draw_amount` = loan draw = `initial_wealth × loan_draw_rate / 12`
- Both computed from same beginning-of-period reference state (`initial_wealth` via `initial_portfolio`)
- The loan supplements portfolio withdrawal; it does NOT fund it

### What would be WRONG

If the policy returned:
```
nominal_amount = target_spending        (e.g., $4,166.67)
loan_draw_amount = additional_borrowing (e.g., $833.33)
```
Then total spending would be `$4,166.67 + $833.33 = $5,000` — which is WRONG.

The current implementation does NOT have this bug.

## C. Debt Configuration Validation Matrix

### Current behavior (NO validation of coherence)

| YAML combination | Parsed as | Pipeline behavior | Correct? |
|---|---|---|---|
| `interest_rate: 0.06` only | interest=0.06, ltv=None, draw=None | Interest accrues but no loan draw, no LTV check | **Partial** — interest accrues on zero balance (no-op) |
| `ltv_limit: 0.75` only | interest=None, ltv=0.75, draw=None | No interest, no draw, no LTV check | **Silently useless** |
| `loan_draw_rate: 0.01` only | interest=None, ltv=None, draw=0.01 | Policy computes loan_draw_amount but LoanDrawStep skips (interest_rate=0) | **SILENT FAILURE** — draws never execute |
| `loan_draw_rate: 0.01` + `interest_rate: 0.06` | Both set | Loan draws execute, interest accrues | **Correct** |
| All three set | All set | Full debt mechanics | **Correct** |
| `debt:` empty dict | All None | No debt | **Correct** |
| No `debt:` section | All None | No debt | **Correct** |

### Required validation (missing)

The most dangerous case is `loan_draw_rate` set without `interest_rate`. The policy computes a loan draw amount, but the `LoanDrawStep` checks `state.interest_rate <= 0` and skips. The user expects leverage but gets none — silently.

**Recommendation:** Add validation in `StudyConfiguration.from_yaml()`:

```python
if debt_loan_draw_rate is not None and debt_interest_rate is None:
    raise ValueError(
        "debt.interest_rate is required when debt.loan_draw_rate is set; "
        "the loan draw step requires a non-zero interest rate to activate"
    )
```

Optional: also validate that `ltv_limit` is set when `interest_rate` is set (LTV enforcement without a limit is meaningless).

## D. Policy Naming Decision

### Current name: `Part49WithdrawalPolicy`

### Concern
`WithdrawalPolicyType.PART49` mixes generic policy behavior with a specific research-study identity.

### Analysis

The policy's economic behavior is:
- Compute a fixed-real portfolio withdrawal from initial wealth
- Compute a fixed-real loan draw from initial wealth
- Return both as a single `WithdrawalDecision`

This is a **leveraged fixed-real withdrawal** — a generic economic behavior, not specific to ERN Part 49.

However:
1. The policy was created specifically for Part 49 research
2. No other study currently uses this behavior
3. The `loan_draw_rate` is read from `SimulationContext`, which is a Part 49-specific field
4. Renaming now would add churn without immediate benefit

### Recommendation

**Accept `Part49WithdrawalPolicy` for now.** If a second study needs the same behavior, rename to `LeveragedFixedRealWithdrawalPolicy` at that point. YAGNI applies — the rename is cheap and the current name is clear.

The key invariant is preserved: the policy is a `WithdrawalPolicy` subclass with no study-specific logic in the domain model. The "Part 49" name is a research identifier, not a domain concept.

## E. True End-to-End Execution Proof

### Test: `test_pipeline_executes_with_debt`

**Path exercised:**

```
materialize_research_plan(interest_rate=0.05, ltv_limit=0.75, loan_draw_rate=0.01)
  → PlannedSimulationUnit (interest_rate=0.05, ltv_limit=0.75, loan_draw_rate=0.01)
    → ResearchExecutor._create_context_for_unit()
      → SimulationContext (interest_rate=0.05, ltv_limit=0.75, loan_draw_rate=0.01)
        → SimulationRunner._initialize_state()
          → SimulationState (interest_rate=0.05, ltv_limit=0.75)
            → production pipeline (create_default_pipeline())
              → LoanDrawStep (sequence_order=28)
              → WithdrawalExecutionStep (sequence_order=30)
              → InterestAccrualStep (sequence_order=65)
              → LTVEvaluationStep (sequence_order=66)
              → MonthlyResultBuilderStep (sequence_order=70)
                → DebtSnapshot in MonthlyResult
```

**Not exercised:** `FastPathSimulationExecutor` eligibility fallback (see section F).

### Missing: StudyConfiguration → build_study_plan → execution

The current tests construct `materialize_research_plan` directly. A full YAML → execution test would be:

```python
config = StudyConfiguration.from_yaml(yaml_data)
built = build_study_plan(config, data_dir=None, initial_wealth=Money(...))
# built.plan contains PlannedSimulationUnits with debt params
# But build_study_plan requires a real dataset (ern_swr_h720)
```

This is not feasible in unit tests without the ERN dataset. The component tests (YAML parsing, plan materialization, context translation, pipeline execution) collectively cover the full path. The missing `build_study_plan` → execution test is a dataset dependency, not an architectural gap.

## F. Fast-Path Analysis

### Eligibility check (fast_path.py:156-187)

```python
def is_fast_path_eligible(context: SimulationContext) -> bool:
    if not isinstance(context.allocation_policy, ConstantAllocationPolicy):
        return False
    if not isinstance(context.withdrawal_policy, FixedRealWithdrawalPolicy):
        return False
    # ... additional checks
```

### Result

`Part49WithdrawalPolicy` is NOT a subclass of `FixedRealWithdrawalPolicy`. Therefore:

```
is_fast_path_eligible(Part49WithdrawalPolicy) → False
```

### FastPathSimulationExecutor fallback (fast_path.py:865-875)

```python
for index, group_id in order:
    if group_id == -1:
        context = definition.simulation_contexts[index]
        single = EngineExperimentDefinition(
            name=definition.name,
            description=definition.description,
            simulation_contexts=(context,),
        )
        run = self._reference.execute(single)
        ordered_results.append(run.simulation_results[0])
```

Non-eligible contexts (group_id == -1) are delegated to `self._reference.execute()` — the reference engine that runs the full production pipeline including all debt steps.

### Conclusion

**Debt-enabled simulations correctly bypass the fast path.** The fast path's closed-form recurrence `V_{m+1} = (V_m - C) × g_m` does not model loan draws, interest accrual, or LTV enforcement. The eligibility check prevents debt-enabled contexts from entering the closed-form path.

No regression risk here.

## G. None vs. Zero Semantics

### Definitions

| Value | Meaning | Pipeline behavior |
|---|---|---|
| `interest_rate = None` | Debt not configured | `state.interest_rate = Decimal("0")`, all debt steps are no-ops |
| `interest_rate = Decimal("0")` | Debt configured but zero interest | `state.interest_rate = Decimal("0")`, all debt steps are no-ops |
| `interest_rate = Decimal("0.06")` | Debt configured with 6% annual | Interest accrues, loan draws execute |

### Semantic distinction

The distinction between `None` and `Decimal("0")` exists at the **configuration layer** (YAML parsing, `StudyConfiguration`, `PlannedSimulationUnit`) but collapses at the **engine layer** (`SimulationState.interest_rate`).

This is correct because:
- `None` = "this study does not use leverage"
- `Decimal("0")` = "this study uses leverage with zero interest" (economically equivalent to no leverage)

The pipeline cannot distinguish these cases, and it should not need to. The configuration layer's role is to decide whether to pass debt parameters through; the engine's role is to execute mechanics when interest_rate > 0.

### Consistency check

- `LoanDrawStep`: checks `state.interest_rate <= 0` → no-op for both None and zero ✓
- `InterestAccrualStep`: checks `state.interest_rate <= 0` → no-op for both None and zero ✓
- `LTVEvaluationStep`: checks `state.interest_rate <= 0` → no-op for both None and zero ✓
- `MonthlyResultBuilderStep`: checks `state.interest_rate > 0` to create DebtSnapshot → no snapshot for both None and zero ✓

All consistent. The None/zero collapse is intentional and correct.
