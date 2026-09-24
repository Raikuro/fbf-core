# T2.6 Experiment E Implementation Design

**Status:** APPROVED — READY TO CODE
**Implementation Status:** NOT STARTED
**Phase:** T2.6 of ERN E2E Implementation Roadmap
**Authoritative Contract:** This document is the authoritative implementation contract for T2.6 Experiment E.

---

## 1. Scope

T2.6 implements **ERN Part 20 Experiment E** — the deterministic 10-year mechanical case study from Tables 01/05 of the article.

Experiment E is a **deterministic case study** requiring general-purpose core capabilities:

1. Prescribed deterministic return sequences;
2. Annual execution cadence for rebalancing;
3. Annual glidepath advancement;
4. Annual escalating withdrawals;
5. Deterministic single-trajectory execution;
5. Research-layer composition and anchor validation.

**Explicit constraint:** Experiment E itself must remain a **research-layer composition** of general capabilities. The underlying capabilities belong in reusable core abstractions; Experiment E is a configuration in the research layer.

---

## 2. Source Mechanics (Frozen)

### 2.1 Article Specification (Authoritative)

| Parameter | Value | Source |
|-----------|-------|--------|
| Initial portfolio | $1,000,000 | Article text |
| Initial withdrawal | $35,000 (3.5%) | Article text |
| Withdrawal escalation | 2% annually | Article text |
| Withdrawal frequency | Annual (beginning of year) | Article text |
| Rebalancing | Annual, simultaneous with withdrawal | Article text |
| Glidepath | 70% → 90% equity, linear 2pp/year | Article Tables 01/05 |
| Static comparison | 80% equity (fixed) | Article text |
| Horizon | 10 years | Article text |
| Returns | S&P 500 TR equity; 10-Year Treasury | Article text |
| Fee | 0.05% p.a. | Article comments |
| No separate inflation | Real returns / real withdrawals | Article text |
| Return sequences | Bear→Bull (Table 01), Bull→Bear (Table 05, reverse) | Article text |
| Ordering | Returns → Withdrawal → Rebalancing | Article (Part 19 §6.1) |
| Post-rebalance weights | Exact target weights | Article explicit |

### 2.2 Important Interpretation

> The existing engine's actual period timeline establishes that the **first market return is applied during `period_index=0`**, and **annual boundaries occur at `period_index % 12 == 0`**.

---

## 3. Period-Index Contract (Implementation Invariant)

### 3.1 Verified Timeline

```text
period_index 0   = first month / Year 1 start (1929-09)
period_index 11  = end of Year 1
period_index 12  = start of Year 2 (annual boundary #2)
period_index 23  = end of Year 2 (Year 2 checkpoint)
...
period_index 108 = start of Year 10 (annual boundary #10)
period_index 119 = end of Year 10 (Year 10 checkpoint, final)
```

### 3.2 Explicit Semantics

* **First withdrawal** occurs at `period_index=0` for annual withdrawal frequency;
* **First return** is applied at `period_index=0`;
* **Annual events** occur at `period_index = 0, 12, 24, ..., 108`;
* **Year 2 checkpoint** is `period_index = 23` (after 24 months);
* **Year 10 checkpoint** is `period_index = 119` (after 120 months);

This is an **implementation invariant** and must not be changed casually.

---

## 4. Glidepath Semantics (Frozen)

### 4.1 Annual Advancement Schedule

| Period | Target Equity | Notes |
|--------|---------------|-------|
| 0      | 70%           | Initial target |
| 12     | 72%           | First annual advancement |
| 24     | 74%           | Second annual advancement |
| ...    | ...           | ... |
| 108    | 88%           | Ninth advancement (Year 10 start) |
| 120    | 90%           | Capped at end allocation |

### 4.2 Advancement Function

```python
advancements = period_index // 12
target = min(start_equity + slope * advancements, end_equity)
```

Where `slope = Decimal("0.02")` (2 percentage points per annual advancement).

**Explicit invariant:** The implementation must NOT advance the glidepath at `period_index = 0`.

---

## 5. Existing Pipeline Reuse

### 5.1 Existing Pipeline Order (Reused for Annual Events)

The existing relevant pipeline order is:

```text
WithdrawalDecision      (sequence_order=20)
WithdrawalExecution     (sequence_order=30)
AllocationDecision      (sequence_order=40)
PortfolioRebalance      (sequence_order=50)
MarketEvolution         (sequence_order=60)
MonthlyResultBuilder    (sequence_order=70)
```

### 5.2 No New Pipeline Steps

**No new pipeline steps are required** for the annual ordering. Annual cadence is implemented by controlling when rebalancing executes and by making the glidepath policy annual-aware.

**Do NOT document an independent "glidepath advancement step"** — glidepath advancement is a policy calculation inside `AllocationDecision`.

### 5.3 Key Invariant

> At each annual rebalance, the portfolio is rebalanced to the target allocation applicable to the COMING year.

---

## 6. ReturnSequence and Prescribed Dataset

### 6.1 Architectural Boundary

```text
ReturnSequence (domain model)
      ↓
build_prescribed_dataset()
      ↓
existing Dataset (engine consumption)
```

* `ReturnSequence` represents the prescribed deterministic returns (domain layer).
* `build_prescribed_dataset()` adapts those returns into the existing `Dataset` abstraction consumed by the simulation engine (data layer).

**Dependency direction:** `src/fbf/core/datasets/prescribed.py` imports `ReturnSequence` and `Dataset`. No reverse dependency.

### 6.2 ReturnSequence Model

```python
@dataclass(frozen=True, slots=True)
class ReturnSequence:
    equity_returns: tuple[Decimal, ...]   # 120 monthly returns
    bond_returns: tuple[Decimal, ...]     # 120 monthly returns
    start_date: date
    frequency: str = "monthly"
    name: str = ""

    def reverse(self) -> "ReturnSequence":
        return ReturnSequence(
            equity_returns=tuple(reversed(self.equity_returns)),
            bond_returns=tuple(reversed(self.bond_returns)),
            start_date=self.start_date,
            name=f"{self.name}_reversed",
        )
```

### 6.3 Dataset Builder (Single Source of Truth)

```python
def build_prescribed_dataset(
    seq: ReturnSequence,
    initial_equity_level: Decimal = Decimal("100"),
    initial_bond_level: Decimal = Decimal("100"),
) -> Dataset:
    """Build a Dataset from prescribed monthly returns.
    
    Compounds levels from prescribed monthly returns.
    Computes ATH/underwater from equity trajectory.
    """
```

---

## 6. Annual → Monthly Conversion (Implementation Assumption)

### 6.1 Explicit Documentation

**The source article provides ANNUAL returns.** The existing simulation engine is monthly. The adapter expands each annual return into 12 equal compounded monthly returns:

```python
monthly_return = (1 + annual_return) ** (Decimal(1) / Decimal(12)) - 1
```

### 6.2 Mandatory Documentation Requirements

All of the following must be prominently documented in code and validation reports:

1. **This monthly series is an implementation adapter** — it is NOT claimed to be an article-published monthly series.
2. **Each 12-month block must compound exactly to its source annual return.**
3. **Bull→Bear reversal occurs at the annual-sequence level BEFORE monthly expansion.**

This assumption must also appear in the eventual Experiment E validation report.

---

## 7. Withdrawal Policy

### 7.1 General-Purpose Requirements

| Requirement | Specification |
|-------------|---------------|
| Initial withdrawal | 3.5% of initial wealth ($35,000 on $1M) |
| Escalation | +2% annually (compounded) |
| Year 1 | $35,000 |
| Year 2 | $35,700 |
| Year 3 | $36,414 |
| ... | ... |
| Year 10 | $41,828.24 |
| **Total 10 years** | **$383,240.12** (matches published) |

### 7.2 Contract Requirements

* **Currency** comes from the simulation's initial wealth (currency-agnostic).
* **Escalation** applies at each annual boundary (`period_index // 12` years elapsed).
* **Existing withdrawal behavior** (monthly FixedReal) must remain unchanged.
* **Policy must be currency-agnostic** — currency comes from simulation's initial wealth.

### 7.3 Policy Design

```python
@dataclass(frozen=True, slots=True)
class EscalatingWithdrawalPolicy(WithdrawalPolicy):
    withdrawal_rate: Decimal          # Initial rate (e.g., 0.035)
    escalation_rate: Decimal = Decimal("0.02")  # 2% annual increase
    frequency: WithdrawalFrequency = WithdrawalFrequency.ANNUAL
    
    def _decide_active(self, context: DecisionContext) -> WithdrawalDecision:
        initial_wealth: Money = context.simulation_context.initial_wealth
        years_elapsed = context.period_index // 12
        current_rate = self.withdrawal_rate * (Decimal("1") + self.escalation_rate) ** years_elapsed
        # ... compute amount based on frequency ...
```

---

## 8. Execution Scheduling

### 8.1 Minimal Cadence Abstraction

```python
class StepCadence(Enum):
    EVERY_PERIOD = "every_period"    # Monthly (current default)
    ANNUAL = "annual"                # Execute only at period_index % 12 == 0

class ExecutionSchedule:
    step_cadences: dict[type, StepCadence]
    
    def should_execute(self, step_type: type, period_index: int) -> bool:
        cadence = self.step_cadences.get(step_type, StepCadence.EVERY_PERIOD)
        if cadence == StepCadence.EVERY_PERIOD:
            return True
        elif cadence == StepCadence.ANNUAL:
            return period_index % 12 == 0
        return False
```

### 8.2 Integration

* `SimulationRunner.run()` accepts optional `ExecutionSchedule`.
* `PortfolioRebalanceStep` receives `cadence` parameter.
* Default behavior (`EVERY_PERIOD`) preserves all existing behavior.

---

## 9. Deterministic Execution

### 9.1 Reuse Existing Engine

* `SimulationRunner` is already a **single-trajectory executor**.
* No second simulation engine is permitted.
* The deterministic API is a **thin construction/extraction layer** around the existing runner.

### 9.2 Deterministic Trajectory (Minimal)

```python
@dataclass(frozen=True, slots=True)
class DeterministicTrajectory:
    name: str
    initial_wealth: Money
    initial_allocation: AllocationTarget
    dataset: Dataset
    allocation_policy: AllocationPolicy
    withdrawal_policy: WithdrawalPolicy
    horizon_months: int
    expense_ratio: Decimal = Decimal("0")
    schedule: ExecutionSchedule | None = None
```

### 9.3 Execution Function (Thin Adapter)

```python
def execute_deterministic_trajectory(
    trajectory: DeterministicTrajectory,
    options: ExecutionOptions,
) -> DeterministicResult:
    # 1. Build SimulationContext from trajectory
    # 2. Create SimulationRunner with custom ExecutionSchedule
    # 3. Run runner.run(context)
    # 4. Extract year checkpoints from monthly_results
    # 5. Return DeterministicResult with checkpoints
```

### 9.4 Checkpoint Extraction (Reuses Existing Structures)

* `SimulationResult.timeline.monthly_results` already contains `MonthlyResult` with:
  - `date`, `period_index`, `portfolio_value`, `allocation`, `withdrawal_decision`
* **No new `MonthlySnapshot` / `YearCheckpoint` domain models** — reuse existing `MonthlyResult`.

```python
# Year 2 checkpoint = period_index 23 (after 24 months)
# Year 10 checkpoint = period_index 119 (after 120 months)
checkpoints = {mr.period_index: mr for mr in result.timeline.monthly_results 
               if mr.period_index in {23, 119}}
```

---

## 10. Experiment E Research Adapter

### 10.1 Construction (Research Layer Only)

```python
def build_experiment_e_trajectories() -> list[DeterministicTrajectory]:
    # 1. Build Bear→Bull return sequence from Article Table 01
    bear_bull = build_ern_table01_return_sequence()
    bull_bear = bear_bull.reverse()  # Reverse at ANNUAL level, then expand
    
    # 2. Build Dataset from prescribed sequences
    bear_bull_ds = build_prescribed_dataset(bear_bull)
    bull_bear_ds = build_prescribed_dataset(bull_bear)
    
    # 3. 70→90% annual glidepath (2pp/year, passive)
    gp_70_90 = GlidepathAllocationPolicy(
        start_equity=Decimal("0.70"),
        end_equity=Decimal("0.90"),
        slope=Decimal("0.02"),      # 2pp per YEAR
        mode="passive",
        cadence=GlidepathCadence.ANNUAL,
        annual_advancement_month=0,  # January
    )
    
    # 4. Static 80%
    static_80 = ConstantAllocationPolicy(equity_allocation=Decimal("0.80"))
    
    # 5. Annual withdrawal with 2% escalation
    withdrawal = EscalatingWithdrawalPolicy(
        withdrawal_rate=Decimal("0.035"),
        escalation_rate=Decimal("0.02"),
        frequency=WithdrawalFrequency.ANNUAL,
    )
    
    schedule = ExecutionSchedule({
        PortfolioRebalanceStep: StepCadence.ANNUAL,
    })
    
    return [
        DeterministicTrajectory(
            name="E_bear_bull_static_080",
            initial_wealth=Money(Decimal("1000000"), Currency.USD),
            initial_allocation=AllocationTarget(weights={equity: Decimal("0.80"), bond: Decimal("0.20")}),
            dataset=bear_bull_ds,
            allocation_policy=static_80,
            withdrawal_policy=EscalatingWithdrawalPolicy(
                withdrawal_rate=Decimal("0.035"),
                escalation_rate=Decimal("0.02"),
                frequency=WithdrawalFrequency.ANNUAL,
            ),
            horizon_months=120,
            expense_ratio=Decimal("0.0005"),
            schedule=schedule,
        ),
        # ... 3 more trajectories
    ]
```

### 10.2 Strategy NOT Added to Part20 Universe

> The 70→90% annual glidepath MUST NOT be added to the standard 53-strategy Part20 strategy universe.
> 
> Experiment E is a separate deterministic case study. Adding an E-only strategy to the standard Part20 universe risks changing A–D matrix dimensions, execution counts, cache keys, existing fixtures, and performance characteristics.

---

## 11. Published Anchors (Authoritative)

### 11.1 Authoritative Table 01/05 Anchors

| # | Case | Strategy | Metric | Published Value | Precision |
|-----|------|----------|--------|-----------------|-----------|
| 1 | Bear→Bull | Glidepath | Year 2 portfolio | $733,314 | Exact USD |
| 2 | Bear→Bull | Static 80% | Year 2 portfolio | $691,746 | Exact USD |
| 3 | Bear→Bull | Glidepath | Year 10 portfolio | $1,074,558 | Exact USD |
| 4 | Bear→Bull | Static 80% | Year 10 portfolio | $995,378 | Exact USD |
| 5 | Bull→Bear | Glidepath | Year 10 portfolio | $1,089,990 | Exact USD |
| 6 | Bull→Bear | Static 80% | Year 10 portfolio | $1,162,099 | Exact USD |
| 7 | Bear→Bull | Glidepath | Year 2 allocation | 39.7% / 60.3% | 1 decimal |
| 8 | Bear→Bull | Static 80% | Year 2 allocation | 85.5% / 14.5% | 1 decimal |

---

## 12. Allocation-Anchor Contradiction (Explicitly Documented)

### 12.1 The Contradiction

| Published Anchor | Article Stated Mechanics | Mathematical Expectation |
|-----------------|-------------------------|--------------------------|
| Glidepath Year 2: **39.7% equity / 60.3% bond** | 70% → 90% at 2pp/yr → Year 2 target = **74% equity** | **39.7% ≠ 74%** |
| Static Year 2: **85.5% equity / 14.5% bond** | Static 80% equity with annual rebalancing | **85.5% ≠ 80%** |

### 12.2 Explicit Classification

> **SOURCE/REFERENCE AMBIGUITY** — The published allocation figures cannot currently be derived from the documented mechanics.

### 12.3 Implementation Decision

> **The implementation target is the documented article mechanics.** The eventual validation must classify the allocation discrepancy as `UNEXPLAINED DIFFERENCE` rather than silently changing the mechanics.

### 12.4 No Undocumented Mechanism

> No undocumented mechanism should be invented merely to make the allocation anchors pass.

---

## 13. Workbook Discrepancy (Documented)

The SWR Toolbox v2.0 workbook's `Case Study` sheet implements a **different** computation:

| Aspect | Article Specification | Workbook Implementation |
|--------|----------------------|------------------------|
| Glidepath | 70% → 90% equity | **60% → 80% equity** |
| Initial portfolio | $1,000,000 | **$3,000,000** |
| Withdrawal | $35,000 annual (2% growth) | Monthly from Cash Flow Assist |
| Rebalancing | Annual, simultaneous | **Monthly** |
| Return sequence | Synthetic Bear→Bull / Bull→Bear | **Historical 1929-09 only** (Bear→Bull) |
| Bull→Bear case | Reverse of Bear→Bull | **Not implemented** |

**The workbook's `Case Study` formulas produce values completely different from the published Table 01/05 anchors.**

**The published Table 01/05 anchors do NOT come from the workbook.** They originate from the article text (manual or separate tool).

---

## 14. Backward Compatibility Invariants

These requirements are **non-negotiable**:

| Invariant | Status |
|-----------|--------|
| Part20 A–D unchanged | ✅ Must remain |
| 53-strategy universe unchanged | ✅ (E strategy in research adapter only) |
| Existing monthly glidepaths | ✅ Preserved (default `MONTHLY`) |
| Existing monthly rebalancing | ✅ Preserved (default `EVERY_PERIOD`) |
| Existing monthly withdrawal | ✅ Preserved (default `MONTHLY`) |
| Part3 behavior | ✅ Unchanged |
| Part52 behavior | ✅ Unchanged |
| Part20 oracle tests | ✅ Unchanged |
| No Part20-specific hacks in core | ✅ |
| Annual→monthly conversion documented | ✅ Required |
| Allocation contradiction documented | ✅ As `UNEXPLAINED DIFFERENCE` |

---

## 15. Implementation Freedom

The document is an implementation contract for **behavior and architecture**, NOT a requirement that the proposed class names or exact file layout be followed blindly.

The implementation agent may choose a different internal class/function decomposition if repository inspection demonstrates a cleaner existing abstraction.

**However, the following are non-negotiable:**

* Reuse the existing simulation engine;
* Preserve existing behavior;
* Keep Experiment E configuration in research;
* Do not pollute A–D;
* Preserve the temporal semantics;
* Preserve the annual return source;
* Document any implementation assumption;
* Do not tune mechanics to match contradictory allocation anchors.

---

## 16. Implementation Phases

### Phase 1: Return Sequence & Prescribed Dataset (Foundation)
**Files**: `return_sequence.py`, `prescribed.py`, tests
**Dependencies**: None

### Phase 2: Execution Schedule & Annual Rebalancing (Core Engine)
**Files**: `schedule.py`, `runner.py` (modify), `portfolio_rebalance_step.py` (modify), `default_pipeline.py` (modify)
**Dependencies**: Phase 1

### Phase 3: Annual Glidepath Cadence (Domain Policy)
**Files**: `glidepath.py` (modify), tests
**Dependencies**: Phase 1

### Phase 4: Escalating Withdrawal Policy (Domain Policy)
**Files**: `escalating_withdrawal.py`, `types.py` (add enum), tests
**Dependencies**: Phase 1

### Phase 5: Deterministic Execution API (Execution Layer)
**Files**: `deterministic.py`, `SimulationRunner.run()` modification (optional `schedule` param)
**Dependencies**: Phases 1–3

### Phase 6: Experiment E Adapter (Research Layer)
**Files**: `part20_experiment_e.py`, `part20_strategies.py` (add `gp_070_090_annual`? NO — per §10.2), fixtures
**Dependencies**: Phases 1–4

### Phase 7: Experiment E Integration Tests
**Files**: `test_experiment_e_anchors.py`, fixture updates
**Dependencies**: Phase 5

---

## 17. Validation Gates

After implementation:

1. ✅ Existing unit tests must pass;
2. ✅ Part20 A–D oracle tests must remain unchanged and pass;
3. ✅ Part3/Part52 tests must pass;
4. ✅ New deterministic tests must pass;
5. ✅ Experiment E must execute all four trajectories;
6. ✅ All eight anchors must be compared;
7. ✅ Unexplained differences must be reported rather than hidden;
8. ❌ No production code should be changed solely to force the published anchors to match.

---

## 18. Do Not Implement Yet

This document is **DOCUMENTATION ONLY**.

Do NOT:
* Modify production code;
* Modify tests;
* Modify fixtures;
* Modify the roadmap;
* Add new strategy entries;
* Commit.

After creating the document, inspect the diff and report:
1. Exact document path;
2. Summary of contents;
3. Confirmation that no non-document files changed;
4. Confirmation that no commit was created.

---

**End of Document**

---

**Document Status:** FROZEN — Ready for Implementation

T2.6 DESIGN DOCUMENT FROZEN — READY FOR IMPLEMENTATION