# T6.1 Implementation Plan: Part 49 Buy-and-Hold Capability

**Status:** PLANNING — PERSISTED FROM FORENSIC ANALYSIS  
**Source:** T6.1 forensic analysis (this session)  
**Roadmap reference:** `ERN_E2E_IMPLEMENTATION_ROADMAP.md` Phase 6, T6.1  
**Related documentation:** `docs/research/ern_part49_replication.md`

---

## 1. Objective

Implement the missing FBF buy-and-hold portfolio capability required to reproduce ERN Part 49 (Using Leverage in Retirement).

ERN Part 49 explicitly uses **buy-and-hold portfolio mechanics** for ALL scenarios:
- Preliminary analysis (Chart 01) — buy-and-hold (ARTICLE — explicit)
- November 1965 aggressive-leverage case — buy-and-hold (ARTICLE — explicit)
- Partial-leverage scenarios ($20k/$20k, $30k/$10k) — buy-and-hold with portfolio withdrawals; no monthly rebalancing (ARTICLE — explicit)

Current FBF has monthly rebalancing (`PortfolioRebalanceStep`) but **no buy-and-hold capability**. This is documented as a genuine FBF capability gap (§14.2 of `ern_part49_replication.md`).

---

## 2. Scope

The minimal implementation consists of:

1. **`AllocationPolicyType.BUY_AND_HOLD`** — enum entry for the new policy type
2. **`BuyAndHoldAllocationPolicy`** — domain policy that returns the same initial allocation target every period
3. **`build_allocation_policy()` support** — factory extension to instantiate the new policy
4. **`create_buy_and_hold_pipeline()`** — pipeline variant that omits periodic allocation decision and rebalancing steps while retaining initial allocation initialization
5. **Unit and integration validation** — tests confirming the capability works correctly
6. **Documentation update** — mark buy-and-hold as implemented in `ern_part49_replication.md` **only after implementation and tests are complete**

---

## 3. Explicit Semantic Requirement

**Buy-and-hold means:**

- The initial equity/bond allocation is established once at simulation start
- There is **no periodic portfolio rebalancing**
- Subsequent market movements naturally change portfolio weights
- Withdrawals may sell assets to obtain cash, but this must not become an implicit portfolio rebalance
- Existing debt/leverage mechanics remain unchanged

### Why merely returning the same allocation target is insufficient

`PortfolioRebalanceStep` (sequence_order=50) executes every month and calls `PortfolioRebalanceService.execute_rebalance()`, which **actively rebalances the portfolio to the target weights** by selling/buying assets. Even if `AllocationDecisionStep` (sequence_order=40) returns the same target every month, the rebalance step would still force the portfolio back to the target allocation — this is monthly rebalancing, not buy-and-hold.

**Therefore, the buy-and-hold pipeline must omit:**
- `AllocationDecisionStep` (seq 40) — no periodic allocation decisions
- `PortfolioRebalanceStep` (seq 50) — no periodic rebalancing

**While retaining:**
- `InitializeAllocationStep` (seq 0) — establishes initial portfolio allocation once

---

## 4. Planned Phases

### T6.1a — Domain Capability

**Files:**
- `src/fbf/core/domain/policies/types.py` — add `BUY_AND_HOLD` to `AllocationPolicyType`
- `src/fbf/core/domain/policies/concrete.py` — add `BuyAndHoldAllocationPolicy` class
- `src/fbf/core/study/builder.py` — extend `build_allocation_policy()` to handle new type

**Implementation details:**

```python
# types.py
class AllocationPolicyType(Enum):
    CONSTANT = ("ConstantAllocationPolicy", "Constant Allocation", "equity_allocation")
    GLIDEPATH = ("GlidepathAllocationPolicy", "Glidepath", "start_equity")
    BUY_AND_HOLD = ("BuyAndHoldAllocationPolicy", "Buy and Hold", "equity_allocation")
```

```python
# concrete.py
class BuyAndHoldAllocationPolicy(AllocationPolicy):
    def __init__(self, equity_allocation: Decimal) -> None:
        self.equity_allocation = equity_allocation
        self._initial_target: AllocationTarget | None = None
    
    def decide(self, context: DecisionContext) -> AllocationDecision:
        if self._initial_target is None:
            equity = AssetClass(id="equity", name="", description="")
            bond = AssetClass(id="bond", name="", description="")
            self._initial_target = AllocationTarget(weights={
                equity: self.equity_allocation,
                bond: Decimal("1") - self.equity_allocation,
            })
        return AllocationDecision(
            reason="BuyAndHoldAllocationPolicy",
            allocation_target=self._initial_target,
        )
```

```python
# builder.py
def build_allocation_policy(policy_type: str, scalar: Decimal) -> AllocationPolicy:
    policy_enum = AllocationPolicyType.from_yaml_name(policy_type)
    if policy_enum is AllocationPolicyType.CONSTANT:
        return ConstantAllocationPolicy(equity_allocation=scalar)
    if policy_enum is AllocationPolicyType.BUY_AND_HOLD:
        return BuyAndHoldAllocationPolicy(equity_allocation=scalar)
    raise ValueError(f"Unsupported allocation policy type: {policy_type!r}")
```

**Validation:**
- Unit test: `BuyAndHoldAllocationPolicy` returns identical `AllocationTarget` on repeated calls
- Unit test: Initial allocation matches specified equity/bond split
- Unit test: Policy is stateless except for cached initial target

---

### T6.1b — Pipeline Capability

**File:**
- `src/fbf/core/execution/pipeline/default_pipeline.py` — add `create_buy_and_hold_pipeline()`

**Pipeline comparison:**

| Step | Default Pipeline | Buy-and-Hold Pipeline |
|------|------------------|----------------------|
| 0 | InitializeAllocationStep | InitializeAllocationStep |
| 5 | ExpenseDeductionStep | ExpenseDeductionStep |
| 10 | BuildDecisionContextStep | BuildDecisionContextStep |
| 20 | WithdrawalDecisionStep | WithdrawalDecisionStep |
| 26 | InterestAccrualStep | InterestAccrualStep |
| 28 | LoanDrawStep | LoanDrawStep |
| 30 | SupplementalCashFlowStep | SupplementalCashFlowStep |
| 32 | WithdrawalExecutionStep | WithdrawalExecutionStep |
| 32 | LoanRepaymentStep | LoanRepaymentStep |
| 40 | **AllocationDecisionStep** | **OMITTED** |
| 50 | **PortfolioRebalanceStep** | **OMITTED** |
| 60 | MarketEvolutionStep | MarketEvolutionStep |
| 66 | LTVEvaluationStep | LTVEvaluationStep |
| 70 | MonthlyResultBuilderStep | MonthlyResultBuilderStep |
| 75 | FailureDetectionStep | FailureDetectionStep |
| 80 | SimulationStateUpdateStep | SimulationStateUpdateStep |

**Validation:**
- Integration test: Pipeline executes without rebalance steps
- Integration test: `AllocationDecisionStep` and `PortfolioRebalanceStep` are NOT present in pipeline steps
- Integration test: `InitializeAllocationStep` correctly establishes initial holdings

---

### T6.1c — Part 49 Integration Validation

**File:**
- New test: `tests/integration/test_part49_buy_and_hold.py`

**Validation:**
- Execute single cohort (November 1965) with buy-and-hold pipeline
- Verify no periodic rebalancing occurs (portfolio weights drift naturally)
- Verify withdrawals sell assets for cash without rebalancing remaining portfolio
- Verify debt/leverage mechanics work unchanged (`LoanDrawStep`, `InterestAccrualStep`, `LTVEvaluationStep`)
- Compare trajectory against published chart values as **diagnostic checks only**:
  - 1965 margin-call window (months 180–200) — Chart 02
  - 1929 month 238 values (portfolio ≈$1.185M, loan ≈$1.085M) — Chart 03
  - $20k/$20k loan/portfolio ratios at month 201 — Chart 04
  - $30k/$10k max utilization — Charts 05/06

**Important:** Chart-derived values are explicitly classified as "diagnostic reproduction checks, not hard numerical oracles" (§21.4 of `ern_part49_replication.md`). They serve as implementation verification, not acceptance gates.

---

### T6.1d — Documentation

**File:**
- `docs/research/ern_part49_replication.md` — update §14.2 capability audit table

**Action:** Mark "Buy-and-hold portfolios" as **IMPLEMENTED** only after T6.1a–c are complete and validated.

**Do not update this documentation before implementation is complete.**

---

## 5. Reuse / YAGNI Decisions

### Intentionally reused (no changes required)

| Component | Location | Rationale |
|-----------|----------|-----------|
| `AllocationPolicy` base class | `domain/policies/allocation_policy.py` | Existing abstraction |
| `ConstantAllocationPolicy` pattern | `domain/policies/concrete.py` | Model for new policy |
| `GlidepathAllocationPolicy` pattern | `domain/policies/glidepath.py` | Model for stateful policy |
| `AllocationPolicyType` enum | `domain/policies/types.py` | Single source of truth for policy types |
| `build_allocation_policy()` | `study/builder.py` | Existing factory pattern |
| `StudyConfiguration` | `study/builder.py` | Already supports debt/leverage parameters |
| `Part49WithdrawalPolicy` | `domain/policies/part49_withdrawal.py` | Already implemented and validated |
| `LoanDrawStep` | `execution/pipeline/steps/loan_draw_step.py` | Already implemented and validated |
| `InterestAccrualStep` | `execution/pipeline/steps/interest_accrual_step.py` | Already implemented and validated |
| `LTVEvaluationStep` | `execution/pipeline/steps/ltv_evaluation_step.py` | Already implemented and validated |
| `ResearchExecutor` / `SimulationRunner` | `execution/executor.py`, `execution/pipeline/runner.py` | Pipeline injected at test level |
| Existing test infrastructure | `tests/integration/`, `tests/oracle/ern/` | Patterns established |

### Explicitly NOT planned (YAGNI)

- **Pipeline registry or configuration system** — T6.1 only requires a focused capability; tests/E2E can explicitly use `create_buy_and_hold_pipeline()`
- **ResearchExecutor/SimulationRunner changes** — Pipeline is passed explicitly; no framework modification needed
- **Study YAML pipeline selection** — Not required for T6.1; can be deferred if/when multiple pipelines need configuration-driven selection
- **New allocation policy for Part 19/20** — Part 49 is independent; glidepath policies already exist for those articles
- **Hard numerical oracles from chart values** — Per `ern_part49_replication.md` §17/§21.4, chart values are diagnostic only; hard oracles require spreadsheet reconstruction (deferred to T6.2+)

---

## 6. Risks / Open Questions

### Confirmed requirements (from ERN methodology documentation)

| Requirement | Source | Status |
|-------------|--------|--------|
| Buy-and-hold for ALL Part 49 scenarios | §11.1, §14.2 | CONFIRMED |
| Initial allocation established once | §11.1 | CONFIRMED |
| No periodic rebalancing | §11.1, §11.3 | CONFIRMED |
| Withdrawals sell assets without rebalancing | §11.1 | CONFIRMED |
| Debt/leverage mechanics unchanged | §8, §9, §14.1 | CONFIRMED |
| 1925–1990 cohort universe for historical conclusion | §12.1, §12.4 | CONFIRMED |
| Chart-derived values are diagnostic, not hard oracles | §15.2, §17, §21.4 | CONFIRMED |

### Implementation assumptions (to be validated during T6.1)

| Assumption | Risk if wrong | Mitigation |
|------------|---------------|------------|
| `InitializeAllocationStep` works correctly without subsequent `AllocationDecisionStep` | Initial portfolio not properly established | Integration test validates initial holdings |
| `WithdrawalExecutionStep` sells assets for cash without rebalancing remainder | Implicit rebalancing via cash-funded withdrawal | Test verifies portfolio weights drift naturally |
| Drifting portfolio weights compatible with `LTVEvaluationStep` | LTV calculation breaks with unbalanced portfolio | LTV uses actual portfolio value; already tested in Part 49 integration tests |
| Pipeline selection remains explicit (no config-driven selection) | Future T6.2 E2E needs config-driven pipeline | Deferred; T6.1 scope is capability implementation only |

### Known risks

| Risk | Evidence | Mitigation |
|------|----------|------------|
| Pipeline selection is explicit rather than configuration-driven | `create_default_pipeline()` is hardcoded; tests inject pipeline directly | T6.1 scope doesn't require config-driven selection; T6.2 can address if needed |
| Initial allocation must work without subsequent allocation/rebalance steps | `InitializeAllocationStep` at seq 0; no AllocDec at seq 40 | Integration test validates initial allocation persists |
| Withdrawals must not accidentally introduce rebalancing semantics | `WithdrawalExecutionStep` sells assets proportionally? | Current implementation sells to fund withdrawal only; verify in test |
| Part 49 chart-derived values are diagnostic rather than authoritative | §15.2, §17, §21.4 explicitly state this | Use as diagnostic assertions only; hard oracles deferred |
| T6.2 E2E will require stronger oracle reconstruction | §21.5 lists "Hard Replication Anchors" as unresolved | T6.1 delivers capability; T6.2 owns oracle reconstruction |

---

## 6.5. Withdrawal Liquidation Behavior (Open T6.2 Validation Item)

**Finding from T6.1 implementation review:**

The existing `PortfolioWithdrawalService.execute_withdrawal()` performs **proportional liquidation** across all portfolio holdings when executing withdrawals. This means that when assets are sold to fund a withdrawal, they are sold in proportion to their current weights, which **maintains the current portfolio weights** — effectively a form of rebalancing at withdrawal time.

**T6.1 scope and decision:**
- T6.1 removes **periodic monthly** allocation/rebalancing (the `AllocationDecisionStep` and `PortfolioRebalanceStep` at seq 40/50).
- Existing withdrawal liquidation behavior is **unchanged** — T6.1 does not modify `WithdrawalExecutionStep` or `PortfolioWithdrawalService`.
- ERN Part 49 methodology states "buy-and-hold asset holdings with portfolio withdrawals; no monthly rebalancing is specified" (§11.1) but does **not** specify the precise asset-liquidation rule for withdrawals.
- Whether FBF's proportional liquidation matches the canonical Part 49 methodology is an **open validation question for T6.2**.
- This is **not a T6.1 blocker** — T6.1 delivers the buy-and-hold capability by removing periodic rebalancing; the withdrawal liquidation rule is a separate methodological detail to be validated against ERN's published results in T6.2.

**Do not claim** that proportional liquidation has been proven equivalent to ERN Part 49 methodology. This remains an open T6.2 validation item.

---

## 7. Acceptance Criteria (for T6.1 as a whole)

**T6.1 is complete when:**

- [ ] `AllocationPolicyType.BUY_AND_HOLD` exists and is importable from `fbf.core.domain.policies`
- [ ] `BuyAndHoldAllocationPolicy` class exists and is importable from `fbf.core.domain.policies.concrete`
- [ ] `build_allocation_policy("BuyAndHoldAllocationPolicy", Decimal("0.75"))` returns a valid policy
- [ ] `create_buy_and_hold_pipeline()` returns a `SimulationPipeline` without `AllocationDecisionStep` and `PortfolioRebalanceStep`
- [ ] Unit tests for domain policy pass
- [ ] Integration test executes Part 49 single cohort with buy-and-hold pipeline and validates no periodic rebalancing
- [ ] Integration test confirms debt/leverage mechanics work with buy-and-hold pipeline
- [ ] `ern_part49_replication.md` §14.2 updated to mark buy-and-hold as IMPLEMENTED

---

## 8. Relationship to Roadmap

This plan directly implements **T6.1** from `ERN_E2E_IMPLEMENTATION_ROADMAP.md`:

> **T6.1** Part 49 buy-and-hold capability
> - Target: Implement buy-and-hold portfolio mechanics in FBF
> - Prerequisite: Capability design and implementation
> - Acceptance criteria: Buy-and-hold mechanics validated; Part 49 E2E can be built against it
> - Known blocker: Genuine FBF capability gap
> - Dependencies: None (independent capability work)

**T6.2** (Part 49 canonical E2E) depends on T6.1 completion and is explicitly out of scope for this plan.

---

## 9. References

- `docs/roadmap/ERN_E2E_IMPLEMENTATION_ROADMAP.md` — Phase 6, T6.1
- `docs/research/ern_part49_replication.md` — §11, §14.2, §16, §17, §21
- `src/fbf/core/domain/policies/types.py` — `AllocationPolicyType`
- `src/fbf/core/domain/policies/concrete.py` — `ConstantAllocationPolicy`, `FixedRealWithdrawalPolicy`
- `src/fbf/core/study/builder.py` — `build_allocation_policy()`
- `src/fbf/core/execution/pipeline/default_pipeline.py` — `create_default_pipeline()`
- `src/fbf/core/execution/pipeline/steps/portfolio_rebalance_step.py` — `PortfolioRebalanceStep`

---

**End of T6.1 Implementation Plan**